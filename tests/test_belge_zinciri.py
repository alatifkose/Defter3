"""Belge zinciri testleri (Aşama 4.4): belge, okuma, kaynak, dosya/DB hata
senaryoları ve uzlaştırma.

Gerçek SQLite dosyası, ``test`` ortamı, ``tmp_path`` altında kök; şema gerçek
göç zinciriyle kurulur; gelen dizini ve arşiv dizini ayarlardan gelir ama
servislere açıkça verilir. Belgeler sentetiktir (envanter listesi PDF'i, metin,
sahte PNG); finansal belge yoktur ve çekirdek belge türü bilmez.

İki düzey sınanır: uygulama sözleşmesi (``belge_islemleri`` / ``arsiv``
hataları) ve veritabanı kısıtları (servisi atlayan ham SQL aynı ihlali
``IntegrityError`` ile reddeder).
"""

from __future__ import annotations

import hashlib
import io
import json
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, BinaryIO

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from defteruc import ayarlar as ay
from defteruc.cekirdek import arsiv, gocler
from defteruc.cekirdek import belge_islemleri as bi
from defteruc.cekirdek import belge_tablolari as bt
from defteruc.cekirdek import veritabani as vt
from defteruc.cekirdek.belge_tablolari import OkumaDurumu

DEFTERUC_DEGISKENLERI = (
    ay.ORTAM_DEGISKENI,
    ay.VERI_KOKU_DEGISKENI,
    ay.VERITABANI_YOLU_DEGISKENI,
    ay.BELGE_DIZINI_DEGISKENI,
    ay.LOG_DIZINI_DEGISKENI,
    ay.GELEN_DIZINI_DEGISKENI,
)
PDF = b"%PDF-1.7\n% envanter listesi: raf A1, 12 kalem\n"
METIN = "raf;urun;adet\nA1;vida;12\n".encode()
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
ICERIK: dict[str, Any] = {
    "baslik": "Envanter sayımı",
    "satirlar": [{"raf": "A1", "urun": "vida", "adet": 12}, {"raf": "A2"}],
    "not": "ç ğ ş",
}
KONUM: dict[str, Any] = {"sayfa": 1, "satir": 3}


@pytest.fixture(autouse=True)
def temiz_cevre(monkeypatch: pytest.MonkeyPatch) -> None:
    for degisken in DEFTERUC_DEGISKENLERI:
        monkeypatch.delenv(degisken, raising=False)


@dataclass(frozen=True, slots=True)
class Ortam:
    veritabani: vt.Veritabani
    gelen: Path
    arsiv: Path
    kok: Path


@pytest.fixture
def ortam(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Ortam]:
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(tmp_path / "kok"))
    ayar = ay.ayarlari_yukle()
    ay.dizinleri_hazirla(ayar)
    v = vt.Veritabani(ayar.veritabani_yolu)
    gocler.semayi_yukselt(v)
    yield Ortam(v, ayar.gelen_dizini, ayar.belge_dizini, tmp_path / "kok")
    v.kapat()


def _yaz(yol: Path, icerik: bytes) -> Path:
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_bytes(icerik)
    return yol


def _belge_al(o: Ortam, ad: str, icerik: bytes = PDF) -> bi.BelgeSonucu:
    return bi.belge_al(
        o.veritabani,
        _yaz(o.gelen / ad, icerik),
        gelen_dizini=o.gelen,
        arsiv_dizini=o.arsiv,
    )


def _sayi(o: Ortam, tablo: str) -> int:
    with o.veritabani.islem() as oturum:
        return int(oturum.execute(text(f"SELECT count(*) FROM {tablo}")).scalar_one())


def _sayilar(o: Ortam) -> tuple[int, int, int, int]:
    return tuple(_sayi(o, t) for t in bt.BELGE_TABLOLARI)  # type: ignore[return-value]


def _dosyalar(dizin: Path) -> set[str]:
    return {p.relative_to(dizin).as_posix() for p in dizin.rglob("*") if p.is_file()}


def _sha(icerik: bytes) -> str:
    return hashlib.sha256(icerik).hexdigest()


def _yol(icerik: bytes) -> str:
    ozet = _sha(icerik)
    return f"{ozet[:2]}/{ozet}"


def _okuma(o: Ortam, belge_id: int) -> int:
    with o.veritabani.islem() as oturum:
        return bi.okuma_baslat(oturum, belge_id, o.arsiv).id


def _tamamla(o: Ortam, okuma_id: int, icerik: dict[str, Any] | None = None) -> None:
    with o.veritabani.islem() as oturum:
        bi.okuma_tamamla(oturum, okuma_id, ICERIK if icerik is None else icerik)


def _tamam_okuma(o: Ortam, belge_id: int) -> int:
    """Başlatılıp tamamlanmış okuma (kaynak yalnız tamamlanmış okumadan)."""
    okuma_id = _okuma(o, belge_id)
    _tamamla(o, okuma_id)
    return okuma_id


def _ham_arsiv_dosyasi(
    oturum: Session, sha: str, yol: str | None = None, boyut: int = 10
) -> None:
    oturum.execute(
        text(
            "INSERT INTO arsiv_dosyasi (sha256, boyut, mime, kaynak_uzantisi, "
            "kaynak_adi, goreli_yol, olusturma_zamani) VALUES (:s, :b, 'x/y', '', "
            "'a', :y, '2026-09-19 00:00:00')"
        ),
        {"s": sha, "b": boyut, "y": yol if yol is not None else f"{sha[:2]}/{sha}"},
    )


# --- belge ----------------------------------------------------------------------------


def test_ilk_dosya_yeni_belge_olusturur(ortam: Ortam) -> None:
    sonuc = _belge_al(ortam, "Envanter.PDF")

    assert (sonuc.zaten_vardi, sonuc.dosya_zaten_vardi) == (False, False)
    dosya, belge = sonuc.arsiv_dosyasi, sonuc.belge
    assert dosya.sha256 == _sha(PDF) and dosya.boyut == len(PDF)
    assert dosya.goreli_yol == _yol(PDF) and dosya.mime == "application/pdf"
    assert (dosya.kaynak_adi, dosya.kaynak_uzantisi) == ("Envanter.PDF", ".pdf")
    assert dosya.olusturma_zamani.tzinfo is None
    assert belge.arsiv_dosyasi_id == dosya.id
    assert _sayilar(ortam) == (1, 1, 0, 0)
    assert _dosyalar(ortam.arsiv) == {dosya.goreli_yol}
    assert not (ortam.arsiv / dosya.goreli_yol).suffix
    with ortam.veritabani.islem() as oturum:
        assert bi.belge_getir(oturum, belge.id).id == belge.id
        assert bi.arsiv_dosyasi_getir(oturum, dosya.id).sha256 == dosya.sha256
        bulunan = bi.belge_bul(oturum, dosya.sha256)
        assert bulunan is not None and bulunan.id == belge.id
        assert [b.id for b in bi.belgeleri_listele(oturum)] == [belge.id]
        assert oturum.execute(
            text("SELECT goreli_yol FROM arsiv_dosyasi")
        ).scalar_one() == _yol(PDF)  # tam yerel yol DB'de yok


def test_tam_yerel_yol_veritabanina_yazilmaz(ortam: Ortam) -> None:
    _belge_al(ortam, "a.pdf")
    with ortam.veritabani.islem() as oturum:
        satir = oturum.execute(text("SELECT * FROM arsiv_dosyasi")).one()
    assert not any(str(ortam.kok) in str(deger) for deger in satir)


def test_ayni_sha_tekrar_gelince_mevcut_belge_doner(ortam: Ortam) -> None:
    ilk = _belge_al(ortam, "a.pdf")
    ikinci = _belge_al(ortam, "alt/baska-ad.PDF")
    ucuncu = _belge_al(ortam, "uzantisiz")

    for sonuc in (ikinci, ucuncu):
        assert (sonuc.zaten_vardi, sonuc.dosya_zaten_vardi) == (True, True)
        assert sonuc.belge.id == ilk.belge.id
        assert sonuc.arsiv_dosyasi.id == ilk.arsiv_dosyasi.id
        assert sonuc.arsiv_dosyasi.kaynak_adi == "a.pdf"  # ilk metadata kalır
    assert _sayilar(ortam) == (1, 1, 0, 0)
    assert _dosyalar(ortam.arsiv) == {_yol(PDF)}


def test_farkli_icerik_farkli_belge(ortam: Ortam) -> None:
    a = _belge_al(ortam, "a.pdf", PDF)
    b = _belge_al(ortam, "b.txt", METIN)
    c = _belge_al(ortam, "c.png", PNG)

    assert len({a.belge.id, b.belge.id, c.belge.id}) == 3
    assert _sayilar(ortam) == (3, 3, 0, 0)
    assert _dosyalar(ortam.arsiv) == {_yol(PDF), _yol(METIN), _yol(PNG)}


def test_gelen_dizini_disi_belge_olmaz(ortam: Ortam, tmp_path: Path) -> None:
    disari = _yaz(tmp_path / "disari" / "a.pdf", PDF)
    with pytest.raises(arsiv.GelenDosyaGecersiz):
        bi.belge_al(
            ortam.veritabani, disari, gelen_dizini=ortam.gelen, arsiv_dizini=ortam.arsiv
        )
    assert _sayilar(ortam) == (0, 0, 0, 0)
    assert _dosyalar(ortam.arsiv) == set()


def test_olmayan_belge_ve_arsiv_dosyasi_bulunamaz(ortam: Ortam) -> None:
    with ortam.veritabani.islem() as oturum:
        with pytest.raises(bi.BelgeBulunamadi):
            bi.belge_getir(oturum, 99)
        with pytest.raises(bi.BelgeBulunamadi):
            bi.arsiv_dosyasi_getir(oturum, 99)
        with pytest.raises(bi.BelgeBulunamadi):
            bi.okumalari_listele(oturum, 99)
        with pytest.raises(bi.BelgeBulunamadi):
            bi.okuma_baslat(oturum, 99, ortam.arsiv)
        assert bi.belge_bul(oturum, "0" * 64) is None


def test_veritabani_kisitlari_ham_sql_ile_de_calisir(ortam: Ortam) -> None:
    sonuc = _belge_al(ortam, "a.pdf")
    sha = sonuc.arsiv_dosyasi.sha256
    baska = _sha(METIN)

    # Özet ve yol kontrol kısıtıyla birbirine bağlı; hangi benzersizlik önce
    # yakalarsa yakalasın ikinci satır giremez.
    with pytest.raises(
        IntegrityError,
        match=r"UNIQUE constraint failed: arsiv_dosyasi\.(sha256|goreli_yol)",
    ):
        with ortam.veritabani.islem() as oturum:
            _ham_arsiv_dosyasi(oturum, sha)  # aynı özet, aynı yol
    with pytest.raises(IntegrityError, match="ck_arsiv_dosyasi_goreli_yol_icerikten"):
        with ortam.veritabani.islem() as oturum:
            _ham_arsiv_dosyasi(oturum, baska, f"{sha[:2]}/{sha}")  # yol başkasının
    with pytest.raises(IntegrityError, match="ck_arsiv_dosyasi_goreli_yol_icerikten"):
        with ortam.veritabani.islem() as oturum:
            _ham_arsiv_dosyasi(oturum, baska, f"{baska[:2]}/{baska}.pdf")
    with pytest.raises(IntegrityError, match="ck_arsiv_dosyasi_sha256_bicimi"):
        with ortam.veritabani.islem() as oturum:
            _ham_arsiv_dosyasi(oturum, baska.upper(), f"{baska[:2]}/{baska.upper()}")
    with pytest.raises(IntegrityError, match="ck_arsiv_dosyasi_sha256_bicimi"):
        with ortam.veritabani.islem() as oturum:
            _ham_arsiv_dosyasi(oturum, baska[:-1], f"{baska[:2]}/{baska[:-1]}")
    for boyut in (0, -1, 1.5):
        with pytest.raises(IntegrityError, match="boyut_pozitif_tamsayi"):
            with ortam.veritabani.islem() as oturum:
                _ham_arsiv_dosyasi(oturum, baska, boyut=boyut)  # type: ignore[arg-type]
    with pytest.raises(
        IntegrityError, match="UNIQUE constraint failed: belge.arsiv_dosyasi_id"
    ):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(
                text(
                    "INSERT INTO belge (arsiv_dosyasi_id, olusturma_zamani) "
                    "VALUES (:d, '2026-09-19 00:00:00')"
                ),
                {"d": sonuc.arsiv_dosyasi.id},
            )
    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(
                text(
                    "INSERT INTO belge (arsiv_dosyasi_id, olusturma_zamani) "
                    "VALUES (99, '2026-09-19 00:00:00')"
                )
            )
    assert _sayilar(ortam) == (1, 1, 0, 0)


def test_belge_tanimla_fiziksel_dosya_yoksa_yazmaz(ortam: Ortam) -> None:
    """Sözleşme: DB'de dosyasız belge oluşmaz; arşiv sonucu uydurulsa bile."""
    uydurma = arsiv.ArsivlenenDosya(
        sha256=_sha(PDF),
        boyut=len(PDF),
        mime="application/pdf",
        kaynak_uzantisi=".pdf",
        kaynak_adi="a.pdf",
        goreli_yol=_yol(PDF),
        diskte_zaten_vardi=False,
    )
    with pytest.raises(arsiv.ArsivDosyasiEksik):
        with ortam.veritabani.islem() as oturum:
            bi.belge_tanimla(oturum, uydurma, ortam.arsiv)
    assert _sayilar(ortam) == (0, 0, 0, 0)


def test_belge_tanimla_arsiv_satiri_var_belge_yoksa_tamamlar(ortam: Ortam) -> None:
    """Ham SQL ile yalnız arşiv satırı bırakılmışsa belge tamamlanır, satır
    yinelenmez."""
    dosya = _yaz(ortam.gelen / "a.pdf", PDF)
    arsivlenen = arsiv.dosyayi_arsivle(
        dosya, gelen_dizini=ortam.gelen, arsiv_dizini=ortam.arsiv
    )
    with ortam.veritabani.islem() as oturum:
        _ham_arsiv_dosyasi(oturum, arsivlenen.sha256, boyut=arsivlenen.boyut)

    with ortam.veritabani.islem() as oturum:
        sonuc = bi.belge_tanimla(oturum, arsivlenen, ortam.arsiv)

    assert sonuc.zaten_vardi is False
    assert _sayilar(ortam) == (1, 1, 0, 0)


def test_belge_tanimla_hata_atomikligi(
    ortam: Ortam, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Arşiv satırı yazıldıktan sonra belge satırında hata: aynı dış işlemde
    yakalansa bile arşiv satırı kalmaz, dış işlem kullanılabilir kalır."""
    a = arsiv.dosyayi_arsivle(
        _yaz(ortam.gelen / "a.pdf", PDF),
        gelen_dizini=ortam.gelen,
        arsiv_dizini=ortam.arsiv,
    )
    b = arsiv.dosyayi_arsivle(
        _yaz(ortam.gelen / "b.txt", METIN),
        gelen_dizini=ortam.gelen,
        arsiv_dizini=ortam.arsiv,
    )
    gercek = bi.simdi_utc
    sayac = {"n": 0}

    def ikincide_patla() -> Any:
        sayac["n"] += 1
        if sayac["n"] == 2:
            raise RuntimeError("sentetik: belge satırı yazılamadı")
        return gercek()

    monkeypatch.setattr(bi, "simdi_utc", ikincide_patla)
    with ortam.veritabani.islem() as oturum:
        with pytest.raises(RuntimeError, match="sentetik"):
            bi.belge_tanimla(oturum, a, ortam.arsiv)
        assert (
            oturum.execute(text("SELECT count(*) FROM arsiv_dosyasi")).scalar_one() == 0
        )
        sonuc = bi.belge_tanimla(oturum, b, ortam.arsiv)  # aynı işlemde geçerli iş

    assert _sayilar(ortam) == (1, 1, 0, 0)
    with ortam.veritabani.islem() as oturum:
        assert bi.belge_getir(oturum, sonuc.belge.id).arsiv_dosyasi_id == (
            sonuc.arsiv_dosyasi.id
        )
        assert bi.arsiv_dosyasi_getir(oturum, sonuc.arsiv_dosyasi.id).sha256 == b.sha256


# --- okuma ----------------------------------------------------------------------------


def test_okuma_baslatilir_ve_belgeye_baglidir(ortam: Ortam) -> None:
    belge_id = _belge_al(ortam, "a.pdf").belge.id

    with ortam.veritabani.islem() as oturum:
        okuma = bi.okuma_baslat(oturum, belge_id, ortam.arsiv)

    assert (okuma.belge_id, okuma.surum_no, okuma.durum) == (
        belge_id,
        1,
        OkumaDurumu.BASLADI.value,
    )
    assert okuma.icerik is None and okuma.tamamlanma_zamani is None
    with ortam.veritabani.islem() as oturum:
        assert bi.okuma_getir(oturum, okuma.id).id == okuma.id
        assert [o.id for o in bi.okumalari_listele(oturum, belge_id)] == [okuma.id]
        assert bi.okuma_icerigi(oturum, okuma.id) is None


def test_ayni_belge_birden_cok_surum_okunur(ortam: Ortam) -> None:
    belge_id = _belge_al(ortam, "a.pdf").belge.id
    baska_id = _belge_al(ortam, "b.txt", METIN).belge.id

    surumler = [_okuma(ortam, belge_id) for _ in range(3)]
    baska = _okuma(ortam, baska_id)

    with ortam.veritabani.islem() as oturum:
        assert [o.surum_no for o in bi.okumalari_listele(oturum, belge_id)] == [1, 2, 3]
        assert [o.id for o in bi.okumalari_listele(oturum, belge_id)] == surumler
        assert [o.surum_no for o in bi.okumalari_listele(oturum, baska_id)] == [1]
        assert bi.okuma_getir(oturum, baska).surum_no == 1


def test_okuma_tamamlanir_icerik_saklanir(ortam: Ortam) -> None:
    belge_id = _belge_al(ortam, "a.pdf").belge.id
    okuma_id = _okuma(ortam, belge_id)

    with ortam.veritabani.islem() as oturum:
        okuma = bi.okuma_tamamla(oturum, okuma_id, ICERIK)

    assert okuma.durum == OkumaDurumu.TAMAMLANDI.value
    assert okuma.tamamlanma_zamani is not None
    assert okuma.icerik is not None and json.loads(okuma.icerik) == ICERIK
    assert okuma.icerik == json.dumps(
        ICERIK, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    with ortam.veritabani.islem() as oturum:
        assert bi.okuma_icerigi(oturum, okuma_id) == ICERIK


def test_tamamlanan_okuma_sessizce_degistirilemez(ortam: Ortam) -> None:
    belge_id = _belge_al(ortam, "a.pdf").belge.id
    okuma_id = _okuma(ortam, belge_id)
    _tamamla(ortam, okuma_id)

    with pytest.raises(bi.OkumaDurumuGecersiz, match="değiştirilmez"):
        _tamamla(ortam, okuma_id, {"baslik": "değişti"})

    with ortam.veritabani.islem() as oturum:
        assert bi.okuma_icerigi(oturum, okuma_id) == ICERIK
    assert not hasattr(bi, "okuma_icerigini_guncelle")


def test_yeni_okuma_yeni_surum_olur(ortam: Ortam) -> None:
    belge_id = _belge_al(ortam, "a.pdf").belge.id
    ilk = _okuma(ortam, belge_id)
    _tamamla(ortam, ilk)
    ikinci = _okuma(ortam, belge_id)
    _tamamla(ortam, ikinci, {"baslik": "ikinci"})

    with ortam.veritabani.islem() as oturum:
        okumalar = bi.okumalari_listele(oturum, belge_id)
        assert [(o.surum_no, o.durum) for o in okumalar] == [
            (1, "tamamlandi"),
            (2, "tamamlandi"),
        ]
        assert bi.okuma_icerigi(oturum, ilk) == ICERIK
        assert bi.okuma_icerigi(oturum, ikinci) == {"baslik": "ikinci"}


@pytest.mark.parametrize(
    "icerik",
    [
        ["liste"],
        "metin",
        7,
        None,
        {"a": float("nan")},
        {"a": float("inf")},
        {"a": [1, {"b": float("-inf")}]},
        {"a": Decimal("1.5")},
        {"a": b"bayt"},
        {"a": {1, 2}},
        {1: "a", "b": 2},  # karışık anahtar türü sıralanamaz
    ],
)
def test_gecersiz_okuma_icerigi_reddedilir(ortam: Ortam, icerik: object) -> None:
    belge_id = _belge_al(ortam, "a.pdf").belge.id
    okuma_id = _okuma(ortam, belge_id)

    with pytest.raises(bi.OkumaIcerigiGecersiz):
        with ortam.veritabani.islem() as oturum:
            bi.okuma_tamamla(oturum, okuma_id, icerik)  # type: ignore[arg-type]

    with ortam.veritabani.islem() as oturum:
        okuma = bi.okuma_getir(oturum, okuma_id)
        assert okuma.durum == "basladi" and okuma.icerik is None


def test_asiri_okuma_icerigi_reddedilir(
    ortam: Ortam, monkeypatch: pytest.MonkeyPatch
) -> None:
    belge_id = _belge_al(ortam, "a.pdf").belge.id
    okuma_id = _okuma(ortam, belge_id)
    monkeypatch.setattr(bi, "AZAMI_OKUMA_ICERIGI_BOYUTU", 64)

    _tamamla(ortam, _okuma(ortam, belge_id), {"k": "x" * 40})  # sınır içinde
    with pytest.raises(bi.OkumaIcerigiGecersiz, match="sınırını aşıyor") as hata:
        _tamamla(ortam, okuma_id, {"k": "x" * 100})
    assert "xxx" not in str(hata.value)  # içerik mesaja dökülmez

    with ortam.veritabani.islem() as oturum:
        assert bi.okuma_getir(oturum, okuma_id).durum == "basladi"


def test_arsiv_dosyasi_eksikken_okuma_baslamaz(ortam: Ortam) -> None:
    sonuc = _belge_al(ortam, "a.pdf")
    (ortam.arsiv / sonuc.arsiv_dosyasi.goreli_yol).unlink()

    with pytest.raises(arsiv.ArsivDosyasiEksik):
        _okuma(ortam, sonuc.belge.id)
    assert _sayi(ortam, "okuma") == 0


@pytest.mark.parametrize("bozuk", [PDF[:-1] + b"X", PDF + b"fazla", PDF[:-3]])
def test_arsiv_dosyasi_bozukken_okuma_baslamaz(ortam: Ortam, bozuk: bytes) -> None:
    sonuc = _belge_al(ortam, "a.pdf")
    (ortam.arsiv / sonuc.arsiv_dosyasi.goreli_yol).write_bytes(bozuk)

    with pytest.raises(arsiv.ArsivButunlukHatasi):
        _okuma(ortam, sonuc.belge.id)
    assert _sayi(ortam, "okuma") == 0


def test_okuma_hata_atomikligi(ortam: Ortam, monkeypatch: pytest.MonkeyPatch) -> None:
    """Yazma sırasında hata: aynı dış işlemde yakalansa bile yarım okuma satırı
    kalmaz; sonraki geçerli okuma aynı işlemde açılıp commit edilir."""
    belge_id = _belge_al(ortam, "a.pdf").belge.id
    gercek = bi.simdi_utc
    patlat = {"aktif": True}

    def bir_kez_patla() -> Any:
        if patlat["aktif"]:
            patlat["aktif"] = False
            raise RuntimeError("sentetik: okuma satırı yazılamadı")
        return gercek()

    monkeypatch.setattr(bi, "simdi_utc", bir_kez_patla)
    with ortam.veritabani.islem() as oturum:
        with pytest.raises(RuntimeError, match="sentetik"):
            bi.okuma_baslat(oturum, belge_id, ortam.arsiv)
        assert oturum.execute(text("SELECT count(*) FROM okuma")).scalar_one() == 0
        okuma = bi.okuma_baslat(oturum, belge_id, ortam.arsiv)
        assert okuma.surum_no == 1

    assert _sayi(ortam, "okuma") == 1


def test_okuma_tamamla_hata_atomikligi(
    ortam: Ortam, monkeypatch: pytest.MonkeyPatch
) -> None:
    belge_id = _belge_al(ortam, "a.pdf").belge.id
    okuma_id = _okuma(ortam, belge_id)

    def patla() -> Any:
        raise RuntimeError("sentetik")

    with ortam.veritabani.islem() as oturum:
        monkeypatch.setattr(bi, "simdi_utc", patla)
        with pytest.raises(RuntimeError, match="sentetik"):
            bi.okuma_tamamla(oturum, okuma_id, ICERIK)
        monkeypatch.undo()
        assert bi.okuma_getir(oturum, okuma_id).durum == "basladi"
        bi.okuma_tamamla(oturum, okuma_id, ICERIK)

    with ortam.veritabani.islem() as oturum:
        assert bi.okuma_icerigi(oturum, okuma_id) == ICERIK


def test_okuma_kisitlari_ham_sql_ile_de_calisir(ortam: Ortam) -> None:
    belge_id = _belge_al(ortam, "a.pdf").belge.id
    okuma_id = _okuma(ortam, belge_id)
    ekle = text(
        "INSERT INTO okuma (belge_id, surum_no, durum, icerik, olusturma_zamani, "
        "tamamlanma_zamani) VALUES (:b, :s, :d, :i, '2026-09-19 00:00:00', :t)"
    )

    def dene(eslesme: str, **degerler: object) -> None:
        with pytest.raises(IntegrityError, match=eslesme):
            with ortam.veritabani.islem() as oturum:
                oturum.execute(ekle, degerler)

    dene(
        "UNIQUE constraint failed: okuma.belge_id",
        b=belge_id,
        s=1,
        d="basladi",
        i=None,
        t=None,
    )
    dene("surum_no_pozitif_tamsayi", b=belge_id, s=0, d="basladi", i=None, t=None)
    dene("surum_no_pozitif_tamsayi", b=belge_id, s=2.5, d="basladi", i=None, t=None)
    dene("durum_icerik_tutarli", b=belge_id, s=2, d="basladi", i="{}", t=None)
    dene("durum_icerik_tutarli", b=belge_id, s=2, d="tamamlandi", i=None, t=None)
    dene(
        "durum_icerik_tutarli",
        b=belge_id,
        s=2,
        d="tamamlandi",
        i="{}",
        t=None,
    )
    dene("durum_icerik_tutarli", b=belge_id, s=2, d="taslak", i=None, t=None)
    dene(
        "icerik_json",
        b=belge_id,
        s=2,
        d="tamamlandi",
        i="{bozuk",
        t="2026-09-19 00:00:01",
    )
    dene("FOREIGN KEY", b=99, s=1, d="basladi", i=None, t=None)
    with pytest.raises(IntegrityError, match="durum_icerik_tutarli"):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(
                text("UPDATE okuma SET icerik = '{}' WHERE id = :o"), {"o": okuma_id}
            )
    assert _sayi(ortam, "okuma") == 1


def test_olmayan_okuma_bulunamaz(ortam: Ortam) -> None:
    with ortam.veritabani.islem() as oturum:
        for islev in (bi.okuma_getir, bi.okuma_icerigi, bi.kaynaklari_listele):
            with pytest.raises(bi.OkumaBulunamadi):
                islev(oturum, 99)
        with pytest.raises(bi.OkumaBulunamadi):
            bi.okuma_tamamla(oturum, 99, ICERIK)
        with pytest.raises(bi.OkumaBulunamadi):
            bi.kaynak_olustur(oturum, 99)


# --- kaynak ---------------------------------------------------------------------------


def test_kaynak_belge_okuma_ve_konum_zincirini_tasir(ortam: Ortam) -> None:
    sonuc = _belge_al(ortam, "a.pdf")
    okuma_id = _tamam_okuma(ortam, sonuc.belge.id)

    with ortam.veritabani.islem() as oturum:
        kaynak = bi.kaynak_olustur(oturum, okuma_id, KONUM)

    assert (kaynak.belge_id, kaynak.okuma_id) == (sonuc.belge.id, okuma_id)
    assert kaynak.konum is not None and json.loads(kaynak.konum) == KONUM
    assert kaynak.olusturma_zamani.tzinfo is None
    with ortam.veritabani.islem() as oturum:
        assert bi.kaynak_getir(oturum, kaynak.id).id == kaynak.id
        assert [k.id for k in bi.kaynaklari_listele(oturum, okuma_id)] == [kaynak.id]
        assert bi.kaynak_konumu(oturum, kaynak.id) == KONUM
        zincir = bi.kaynak_zinciri(oturum, kaynak.id)
        assert zincir.kaynak.id == kaynak.id and zincir.okuma.id == okuma_id
        assert zincir.belge.id == sonuc.belge.id
        assert zincir.arsiv_dosyasi.sha256 == _sha(PDF)


def test_konumsuz_kaynak_desteklenir(ortam: Ortam) -> None:
    okuma_id = _tamam_okuma(ortam, _belge_al(ortam, "a.pdf").belge.id)
    with ortam.veritabani.islem() as oturum:
        kaynak = bi.kaynak_olustur(oturum, okuma_id)
    assert kaynak.konum is None
    with ortam.veritabani.islem() as oturum:
        assert bi.kaynak_konumu(oturum, kaynak.id) is None


def test_genel_json_konum_saklanir(ortam: Ortam) -> None:
    okuma_id = _tamam_okuma(ortam, _belge_al(ortam, "a.png", PNG).belge.id)
    konum: dict[str, Any] = {
        "sayfa": 2,
        "bolge": {"x": 10.5, "y": 20, "w": 100, "h": 12},
        "hucre": ["B", 7],
        "etiket": "ç",
    }
    with ortam.veritabani.islem() as oturum:
        kaynak = bi.kaynak_olustur(oturum, okuma_id, konum)
    with ortam.veritabani.islem() as oturum:
        assert bi.kaynak_konumu(oturum, kaynak.id) == konum


@pytest.mark.parametrize(
    "konum",
    [["sayfa", 1], "sayfa 1", 3, {"x": float("nan")}, {"x": Decimal(1)}, {"x": b""}],
)
def test_gecersiz_konum_reddedilir(ortam: Ortam, konum: object) -> None:
    okuma_id = _tamam_okuma(ortam, _belge_al(ortam, "a.pdf").belge.id)
    with pytest.raises(bi.KaynakKonumuGecersiz):
        with ortam.veritabani.islem() as oturum:
            bi.kaynak_olustur(oturum, okuma_id, konum)  # type: ignore[arg-type]
    assert _sayi(ortam, "kaynak") == 0


def test_boyut_asan_konum_reddedilir(ortam: Ortam) -> None:
    okuma_id = _tamam_okuma(ortam, _belge_al(ortam, "a.pdf").belge.id)
    buyuk = {"metin": "x" * (bi.AZAMI_KAYNAK_KONUMU_BOYUTU + 1)}
    with pytest.raises(bi.KaynakKonumuGecersiz, match="sınırını aşıyor") as hata:
        with ortam.veritabani.islem() as oturum:
            bi.kaynak_olustur(oturum, okuma_id, buyuk)
    assert "xxx" not in str(hata.value)
    assert _sayi(ortam, "kaynak") == 0


def test_okumanin_ait_olmadigi_belgeyle_kaynak_yazilamaz(ortam: Ortam) -> None:
    """Servis ``belge_id`` almaz; ham SQL'de bileşik dış anahtar reddeder."""
    a = _belge_al(ortam, "a.pdf", PDF).belge.id
    b = _belge_al(ortam, "b.txt", METIN).belge.id
    okuma_a = _tamam_okuma(ortam, a)
    ekle = text(
        "INSERT INTO kaynak (belge_id, okuma_id, konum, olusturma_zamani) "
        "VALUES (:b, :o, :k, '2026-09-19 00:00:00')"
    )

    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(ekle, {"b": b, "o": okuma_a, "k": None})
    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(ekle, {"b": a, "o": 99, "k": None})
    with pytest.raises(IntegrityError, match="ck_kaynak_konum_json"):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(ekle, {"b": a, "o": okuma_a, "k": "{bozuk"})
    with ortam.veritabani.islem() as oturum:  # doğru çift geçer
        oturum.execute(ekle, {"b": a, "o": okuma_a, "k": '{"sayfa":1}'})
    assert _sayi(ortam, "kaynak") == 1


def test_kaynak_uzerinden_deterministik_geri_gidilir(ortam: Ortam) -> None:
    belgeler = [_belge_al(ortam, ad, ic) for ad, ic in (("a.pdf", PDF), ("b", METIN))]
    kaynaklar: list[tuple[int, int, int]] = []
    for sonuc in belgeler:
        for _ in range(2):
            okuma_id = _tamam_okuma(ortam, sonuc.belge.id)
            with ortam.veritabani.islem() as oturum:
                k = bi.kaynak_olustur(oturum, okuma_id, {"okuma": okuma_id})
            kaynaklar.append((k.id, okuma_id, sonuc.belge.id))

    with ortam.veritabani.islem() as oturum:
        for kaynak_id, okuma_id, belge_id in kaynaklar:
            zincir = bi.kaynak_zinciri(oturum, kaynak_id)
            assert (zincir.okuma.id, zincir.belge.id) == (okuma_id, belge_id)
            assert zincir.okuma.belge_id == belge_id
            assert zincir.belge.arsiv_dosyasi_id == zincir.arsiv_dosyasi.id
        with pytest.raises(bi.KaynakBulunamadi):
            bi.kaynak_zinciri(oturum, 99)
        with pytest.raises(bi.KaynakBulunamadi):
            bi.kaynak_konumu(oturum, 99)


def test_kaynak_hata_atomikligi(ortam: Ortam, monkeypatch: pytest.MonkeyPatch) -> None:
    okuma_id = _tamam_okuma(ortam, _belge_al(ortam, "a.pdf").belge.id)

    def patla() -> Any:
        raise RuntimeError("sentetik")

    with ortam.veritabani.islem() as oturum:
        monkeypatch.setattr(bi, "simdi_utc", patla)
        with pytest.raises(RuntimeError, match="sentetik"):
            bi.kaynak_olustur(oturum, okuma_id, KONUM)
        monkeypatch.undo()
        assert oturum.execute(text("SELECT count(*) FROM kaynak")).scalar_one() == 0
        bi.kaynak_olustur(oturum, okuma_id, KONUM)

    assert _sayi(ortam, "kaynak") == 1


# --- dosya / veritabanı hata senaryoları ----------------------------------------------


def test_senaryo_1_kaynak_okunurken_hata(
    ortam: Ortam, monkeypatch: pytest.MonkeyPatch
) -> None:
    def acilmaz(_yol: Path) -> BinaryIO:
        raise PermissionError("sentetik")

    monkeypatch.setattr(arsiv, "_kaynagi_ac", acilmaz)
    with pytest.raises(arsiv.DosyaOkunamadi):
        _belge_al(ortam, "a.pdf")

    assert _sayilar(ortam) == (0, 0, 0, 0)
    assert _dosyalar(ortam.arsiv) == set()


def test_senaryo_2_gecici_dosya_yazilirken_hata(
    ortam: Ortam, monkeypatch: pytest.MonkeyPatch
) -> None:
    class PatlayanYazici(io.FileIO):
        def write(self, b: object, /) -> int:
            raise OSError("sentetik: disk dolu")

    def patlayan_ac(yol: Path) -> BinaryIO:
        return PatlayanYazici(yol, "xb")

    monkeypatch.setattr(arsiv, "_geciciyi_ac", patlayan_ac)
    with pytest.raises(arsiv.ArsivYazilamadi):
        _belge_al(ortam, "a.pdf")

    assert _sayilar(ortam) == (0, 0, 0, 0)
    assert _dosyalar(ortam.arsiv) == set()


def test_senaryo_3_atomik_tasima_hatasi(
    ortam: Ortam, monkeypatch: pytest.MonkeyPatch
) -> None:
    def tasinmaz(_g: Path, _h: Path) -> None:
        raise OSError("sentetik")

    monkeypatch.setattr(arsiv, "_yerine_koy", tasinmaz)
    with pytest.raises(arsiv.ArsivYazilamadi):
        _belge_al(ortam, "a.pdf")

    assert _sayilar(ortam) == (0, 0, 0, 0)
    assert _dosyalar(ortam.arsiv) == set()


def test_senaryo_4_ve_5_arsiv_basarili_db_hatali_sonra_yeniden_deneme(
    ortam: Ortam, monkeypatch: pytest.MonkeyPatch
) -> None:
    def yazilmaz(_o: Session, _a: arsiv.ArsivlenenDosya) -> bt.ArsivDosyasi:
        raise RuntimeError("sentetik: veritabanı yazma hatası")

    with monkeypatch.context() as m:
        m.setattr(bi, "_arsiv_dosyasi_yaz", yazilmaz)
        with pytest.raises(RuntimeError, match="sentetik"):
            _belge_al(ortam, "a.pdf")

    # 4: fiziksel dosya kaldı, belge kaydı yok; uzlaştırma sahipsiz sayar
    assert _dosyalar(ortam.arsiv) == {_yol(PDF)}
    assert _sayilar(ortam) == (0, 0, 0, 0)
    with ortam.veritabani.islem() as oturum:
        rapor = bi.arsivi_uzlastir(oturum, ortam.arsiv)
    assert rapor.sahipsiz == (_yol(PDF),) and not rapor.temiz_mi
    assert _dosyalar(ortam.arsiv) == {_yol(PDF)}  # uzlaştırma silmedi

    # 5: aynı dosya yeniden gelir, DB bu kez başarılı: ikinci kopya yok
    sonuc = _belge_al(ortam, "a.pdf")

    assert (sonuc.zaten_vardi, sonuc.dosya_zaten_vardi) == (False, True)
    assert _sayilar(ortam) == (1, 1, 0, 0)
    assert _dosyalar(ortam.arsiv) == {_yol(PDF)}
    with ortam.veritabani.islem() as oturum:
        assert bi.arsivi_uzlastir(oturum, ortam.arsiv).temiz_mi
        okuma = bi.okuma_baslat(oturum, sonuc.belge.id, ortam.arsiv)
    assert okuma.surum_no == 1


def test_senaryo_4_gercek_veritabani_hatasi(ortam: Ortam, tmp_path: Path) -> None:
    """Enjeksiyonsuz: açılamayan veritabanı dosyası. Arşiv adımı biter, DB düşer."""
    bozuk = vt.Veritabani(tmp_path / "yok" / "olmayan" / "defteruc.sqlite3")
    try:
        with pytest.raises(OperationalError):
            bi.belge_al(
                bozuk,
                _yaz(ortam.gelen / "a.pdf", PDF),
                gelen_dizini=ortam.gelen,
                arsiv_dizini=ortam.arsiv,
            )
    finally:
        bozuk.kapat()

    assert _dosyalar(ortam.arsiv) == {_yol(PDF)}
    assert _sayilar(ortam) == (0, 0, 0, 0)
    sonuc = _belge_al(ortam, "a.pdf")
    assert (sonuc.zaten_vardi, sonuc.dosya_zaten_vardi) == (False, True)
    assert _sayilar(ortam) == (1, 1, 0, 0)


def test_senaryo_6_db_belge_var_dosya_silinmis(ortam: Ortam) -> None:
    sonuc = _belge_al(ortam, "a.pdf")
    (ortam.arsiv / sonuc.arsiv_dosyasi.goreli_yol).unlink()

    with ortam.veritabani.islem() as oturum:
        rapor = bi.arsivi_uzlastir(oturum, ortam.arsiv)
        assert rapor.eksik == (sonuc.arsiv_dosyasi.id,) and rapor.temiz == ()
        with pytest.raises(arsiv.ArsivDosyasiEksik):
            bi.okuma_baslat(oturum, sonuc.belge.id, ortam.arsiv)
    assert _sayi(ortam, "okuma") == 0


def test_senaryo_7_db_belge_var_dosya_degistirilmis(ortam: Ortam) -> None:
    sonuc = _belge_al(ortam, "a.pdf")
    hedef = ortam.arsiv / sonuc.arsiv_dosyasi.goreli_yol
    hedef.write_bytes(PDF[:-1] + b"X")  # aynı boyut, farklı özet

    with ortam.veritabani.islem() as oturum:
        rapor = bi.arsivi_uzlastir(oturum, ortam.arsiv)
        assert rapor.bozuk == (sonuc.arsiv_dosyasi.id,) and rapor.temiz == ()
        with pytest.raises(arsiv.ArsivButunlukHatasi, match="özeti"):
            bi.okuma_baslat(oturum, sonuc.belge.id, ortam.arsiv)
    assert hedef.read_bytes() == PDF[:-1] + b"X"  # sessiz onarım yok
    # Aynı içerik yeniden gelirse bozuk hedef duplicate sayılmaz
    with pytest.raises(arsiv.ArsivButunlukHatasi):
        _belge_al(ortam, "tekrar.pdf")
    assert _sayilar(ortam) == (1, 1, 0, 0)


# --- uzlaştırma -----------------------------------------------------------------------


def test_uzlastirma_bes_durumu_ayirt_eder_ve_silmez(ortam: Ortam) -> None:
    temiz = _belge_al(ortam, "a.pdf", PDF).arsiv_dosyasi
    eksik = _belge_al(ortam, "b.txt", METIN).arsiv_dosyasi
    bozuk = _belge_al(ortam, "c.png", PNG).arsiv_dosyasi
    (ortam.arsiv / eksik.goreli_yol).unlink()
    (ortam.arsiv / bozuk.goreli_yol).write_bytes(PNG + b"bozuk")
    sahipsiz_icerik = b"sahipsiz"
    sahipsiz = arsiv.arsiv_yolu(ortam.arsiv, _yol(sahipsiz_icerik))
    sahipsiz.parent.mkdir(parents=True, exist_ok=True)
    sahipsiz.write_bytes(sahipsiz_icerik)
    gecici = arsiv.gecici_dizin(ortam.arsiv)
    gecici.mkdir(exist_ok=True)
    (gecici / "yarim.tmp").write_bytes(b"yarim")
    (ortam.arsiv / "README.txt").write_bytes(b"not")
    once = _dosyalar(ortam.arsiv)

    with ortam.veritabani.islem() as oturum:
        rapor = bi.arsivi_uzlastir(oturum, ortam.arsiv)

    assert rapor == bi.UzlastirmaRaporu(
        temiz=(temiz.id,),
        eksik=(eksik.id,),
        bozuk=(bozuk.id,),
        sahipsiz=(_yol(sahipsiz_icerik),),
        yarim=("gecici/yarim.tmp",),
        taninmayan=("README.txt",),
    )
    assert not rapor.temiz_mi
    assert _dosyalar(ortam.arsiv) == once  # hiçbir şey silinmedi, değişmedi
    assert _sayilar(ortam) == (3, 3, 0, 0)


def test_uzlastirma_temiz_arsiv(ortam: Ortam) -> None:
    dosyalar = [_belge_al(ortam, ad, ic) for ad, ic in (("a.pdf", PDF), ("b", METIN))]
    with ortam.veritabani.islem() as oturum:
        rapor = bi.arsivi_uzlastir(oturum, ortam.arsiv)
    assert rapor.temiz_mi
    assert rapor.temiz == tuple(d.arsiv_dosyasi.id for d in dosyalar)
    with ortam.veritabani.islem() as oturum:
        assert bi.arsivi_uzlastir(oturum, ortam.kok / "olmayan").eksik == rapor.temiz


# --- inceleme düzeltmeleri (2026-09-19) -----------------------------------------------


def _arsivlenen(ortam: Ortam, ad: str, icerik: bytes) -> arsiv.ArsivlenenDosya:
    return arsiv.dosyayi_arsivle(
        _yaz(ortam.gelen / ad, icerik),
        gelen_dizini=ortam.gelen,
        arsiv_dizini=ortam.arsiv,
    )


def test_belge_tanimla_ayni_boyutta_bozuk_dosyayi_baglamaz(ortam: Ortam) -> None:
    """DB yazılmadan önce SHA-256 de doğrulanır: aynı boyutta bozuk fiziksel dosya
    belgeye bağlanamaz; hiçbir satır oluşmaz."""
    arsivlenen = _arsivlenen(ortam, "a.pdf", PDF)
    hedef = ortam.arsiv / arsivlenen.goreli_yol
    hedef.write_bytes(PDF[:-1] + b"X")  # aynı boyut, farklı içerik

    with pytest.raises(arsiv.ArsivButunlukHatasi, match="özeti"):
        with ortam.veritabani.islem() as oturum:
            bi.belge_tanimla(oturum, arsivlenen, ortam.arsiv)

    assert _sayilar(ortam) == (0, 0, 0, 0)
    assert hedef.read_bytes() == PDF[:-1] + b"X"  # sessiz onarım yok


def test_belge_tanimla_bozuk_dosya_hatasi_dis_islemi_bozmaz(ortam: Ortam) -> None:
    bozuk = _arsivlenen(ortam, "a.pdf", PDF)
    (ortam.arsiv / bozuk.goreli_yol).write_bytes(PDF[:-1] + b"X")
    saglam = _arsivlenen(ortam, "b.txt", METIN)

    with ortam.veritabani.islem() as oturum:
        with pytest.raises(arsiv.ArsivButunlukHatasi):
            bi.belge_tanimla(oturum, bozuk, ortam.arsiv)
        assert (
            oturum.execute(text("SELECT count(*) FROM arsiv_dosyasi")).scalar_one() == 0
        )
        sonuc = bi.belge_tanimla(oturum, saglam, ortam.arsiv)

    assert _sayilar(ortam) == (1, 1, 0, 0)
    with ortam.veritabani.islem() as oturum:
        assert bi.arsiv_dosyasi_getir(oturum, sonuc.arsiv_dosyasi.id).sha256 == _sha(
            METIN
        )


def test_uzanti_uyusmazligi_belge_almaya_engel_degil(ortam: Ortam) -> None:
    """Aynı PDF baytları beş farklı adla: tek fiziksel dosya, tek arşiv satırı,
    tek belge, MIME imzadan; ilk gelişin uzantısı metadata olarak kalır."""
    adlar = ("a.pdf", "a.bin", "a.png", "a", "herhangi.xyz")
    sonuclar = [_belge_al(ortam, ad, PDF) for ad in adlar]

    assert [s.zaten_vardi for s in sonuclar] == [False, True, True, True, True]
    assert {s.belge.id for s in sonuclar} == {sonuclar[0].belge.id}
    assert sonuclar[0].arsiv_dosyasi.mime == "application/pdf"
    assert sonuclar[0].arsiv_dosyasi.kaynak_uzantisi == ".pdf"
    assert _sayilar(ortam) == (1, 1, 0, 0)
    assert _dosyalar(ortam.arsiv) == {_yol(PDF)}
    imzasiz = _belge_al(ortam, "imzasiz.pdf", METIN)  # .pdf adlı imzasız dosya
    assert imzasiz.arsiv_dosyasi.mime == arsiv.VARSAYILAN_MIME
    assert imzasiz.arsiv_dosyasi.kaynak_uzantisi == ".pdf"


def test_basladi_okumadan_kaynak_uretilemez(ortam: Ortam) -> None:
    belge_id = _belge_al(ortam, "a.pdf").belge.id
    okuma_id = _okuma(ortam, belge_id)

    for konum in (KONUM, None):
        with pytest.raises(bi.OkumaDurumuGecersiz, match="tamamlandi okumadan"):
            with ortam.veritabani.islem() as oturum:
                bi.kaynak_olustur(oturum, okuma_id, konum)
    assert _sayi(ortam, "kaynak") == 0

    _tamamla(ortam, okuma_id)
    with ortam.veritabani.islem() as oturum:
        kaynak = bi.kaynak_olustur(oturum, okuma_id, KONUM)
        konumsuz = bi.kaynak_olustur(oturum, okuma_id)
    with ortam.veritabani.islem() as oturum:
        assert bi.kaynak_konumu(oturum, kaynak.id) == KONUM
        assert bi.kaynak_konumu(oturum, konumsuz.id) is None
        assert [k.id for k in bi.kaynaklari_listele(oturum, okuma_id)] == [
            kaynak.id,
            konumsuz.id,
        ]


def test_basladi_okuma_kaynak_reddi_dis_islemi_bozmaz(ortam: Ortam) -> None:
    belge_id = _belge_al(ortam, "a.pdf").belge.id
    basladi = _okuma(ortam, belge_id)
    tamam = _tamam_okuma(ortam, belge_id)

    with ortam.veritabani.islem() as oturum:
        with pytest.raises(bi.OkumaDurumuGecersiz):
            bi.kaynak_olustur(oturum, basladi, KONUM)
        kaynak = bi.kaynak_olustur(oturum, tamam, KONUM)  # aynı işlemde geçerli iş

    assert _sayi(ortam, "kaynak") == 1
    with ortam.veritabani.islem() as oturum:
        assert bi.kaynak_zinciri(oturum, kaynak.id).okuma.id == tamam


def test_eszamanli_ayni_belge_tek_belgeye_uzlasir(
    ortam: Ortam, monkeypatch: pytest.MonkeyPatch
) -> None:
    """İki bağımsız işlem (ayrı iş parçacığı, ayrı bağlantı) aynı SHA-256'yı aynı
    anda ``belge_al`` ile verir. Yarış zorlanır: ikisi de "satır yok" görüp
    yazmaya kalkar (bariyer). Sonuç tek dosya, tek arşiv satırı, tek belge;
    biri yeni, diğeri mevcut belge; ham ``IntegrityError`` / ``database is
    locked`` dışarı çıkmaz."""
    kaynaklar = [_yaz(ortam.gelen / f"k{i}.pdf", PDF) for i in range(2)]
    bariyer = threading.Barrier(2, timeout=10)
    gercek_yaz = bi._arsiv_dosyasi_yaz  # pyright: ignore[reportPrivateUsage]
    bariyerden_gecenler: set[int] = set()
    kilit = threading.Lock()

    def bekleyip_yaz(oturum: Session, a: arsiv.ArsivlenenDosya) -> bt.ArsivDosyasi:
        with kilit:
            ilk = threading.get_ident() not in bariyerden_gecenler
            bariyerden_gecenler.add(threading.get_ident())
        if ilk:
            bariyer.wait()  # ikisi de SELECT'i geçti, ikisi de satır görmedi
        return gercek_yaz(oturum, a)  # yeniden denemede bariyer yok

    monkeypatch.setattr(bi, "_arsiv_dosyasi_yaz", bekleyip_yaz)

    def isle(yol: Path) -> bi.BelgeSonucu:
        v = vt.Veritabani(ortam.veritabani.yol)  # bağımsız bağlantı
        try:
            return bi.belge_al(
                v, yol, gelen_dizini=ortam.gelen, arsiv_dizini=ortam.arsiv
            )
        finally:
            v.kapat()

    with ThreadPoolExecutor(max_workers=2) as havuz:
        sonuclar = list(havuz.map(isle, kaynaklar))

    assert sorted(s.zaten_vardi for s in sonuclar) == [False, True]
    assert {s.belge.id for s in sonuclar} == {sonuclar[0].belge.id}
    assert {s.arsiv_dosyasi.sha256 for s in sonuclar} == {_sha(PDF)}
    assert _sayilar(ortam) == (1, 1, 0, 0)
    assert _dosyalar(ortam.arsiv) == {_yol(PDF)}
    with ortam.veritabani.islem() as oturum:
        assert bi.arsivi_uzlastir(oturum, ortam.arsiv).temiz_mi


def test_cakisma_denemeleri_tukenince_acik_hata(
    ortam: Ortam, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Her denemede benzersizlik ihlali üretilirse sınırlı denemeden sonra
    ``BelgeYazmaCakismasi``; ham IntegrityError sızmaz; sonsuz döngü yok."""
    sayac = {"n": 0}

    def hep_cakis(oturum: Session, a: arsiv.ArsivlenenDosya) -> bt.ArsivDosyasi:
        sayac["n"] += 1
        oturum.execute(
            text(
                "INSERT INTO arsiv_dosyasi (sha256, boyut, mime, kaynak_uzantisi, "
                "kaynak_adi, goreli_yol, olusturma_zamani) VALUES (:s, 1, 'x', '', "
                "'a', :y, '2026-09-19 00:00:00')"
            ),
            {"s": "b" * 64, "y": "bb/" + "b" * 64},
        )
        oturum.execute(  # aynı satır ikinci kez → UNIQUE
            text(
                "INSERT INTO arsiv_dosyasi (sha256, boyut, mime, kaynak_uzantisi, "
                "kaynak_adi, goreli_yol, olusturma_zamani) VALUES (:s, 1, 'x', '', "
                "'a', :y, '2026-09-19 00:00:00')"
            ),
            {"s": "b" * 64, "y": "bb/" + "b" * 64},
        )
        raise AssertionError("erişilmez")

    monkeypatch.setattr(bi, "_arsiv_dosyasi_yaz", hep_cakis)
    with pytest.raises(bi.BelgeYazmaCakismasi, match="uzlaştırılamadı"):
        _belge_al(ortam, "a.pdf")

    assert sayac["n"] == bi.BELGE_YAZMA_DENEMESI
    assert _sayilar(ortam) == (0, 0, 0, 0)  # her deneme geri alındı
    assert _dosyalar(ortam.arsiv) == {_yol(PDF)}  # dosya arşivde kaldı


def test_cakisma_olmayan_veritabani_hatasi_yeniden_denenmez(
    ortam: Ortam, monkeypatch: pytest.MonkeyPatch
) -> None:
    sayac = {"n": 0}

    def baska_hata(oturum: Session, a: arsiv.ArsivlenenDosya) -> bt.ArsivDosyasi:
        sayac["n"] += 1
        oturum.execute(text("INSERT INTO olmayan_tablo VALUES (1)"))
        raise AssertionError("erişilmez")

    monkeypatch.setattr(bi, "_arsiv_dosyasi_yaz", baska_hata)
    with pytest.raises(OperationalError):
        _belge_al(ortam, "a.pdf")
    assert sayac["n"] == 1
