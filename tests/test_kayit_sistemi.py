"""Kesin kayıt şeması testleri (Aşama 4.7/2).

Gerçek SQLite dosyası, ``test`` ortamı, ``tmp_path`` altında kök; şema gerçek
göç zinciriyle kurulur. Tanım paketi finans dışı sahte ``ENVANTER``
dünyasıdır: ``RAF`` ve ``URUN`` türleri, ``SAYIM`` ve ``DENETIM`` kayıt
türleri. Çekirdek bunların anlamını bilmez; hepsi tanım verisidir.

Bu teslimde kayıt servisi (``kayit_islemleri``) henüz yoktur: satırlar ham SQL
ile yazılır ve sınanan şey **veritabanının kendisidir** — bileşik dış
anahtarlar, benzersizlikler ve zorunluluklar servis atlansa da aynı ihlalleri
reddeder mi.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from defteriki import ayarlar as ay
from defteriki.cekirdek import belge_islemleri as bi
from defteriki.cekirdek import denetim_tablolari as dnt
from defteriki.cekirdek import gocler
from defteriki.cekirdek import kayit_tablolari as kt
from defteriki.cekirdek import nesne_islemleri as ni
from defteriki.cekirdek import tanim_islemleri as ti
from defteriki.cekirdek import taslak_islemleri as tsi
from defteriki.cekirdek import veritabani as vt
from defteriki.cekirdek.tanim_tablolari import DegerTuru

DEFTERIKI_DEGISKENLERI = (
    ay.ORTAM_DEGISKENI,
    ay.VERI_KOKU_DEGISKENI,
    ay.VERITABANI_YOLU_DEGISKENI,
    ay.BELGE_DIZINI_DEGISKENI,
    ay.LOG_DIZINI_DEGISKENI,
    ay.GELEN_DIZINI_DEGISKENI,
)
PDF = b"%PDF-1.7\n% envanter listesi: raf A1, 12 kalem\n"
PDF2 = b"%PDF-1.7\n% envanter listesi: raf B2, 3 kalem\n"
OKUMA_ICERIGI: dict[str, Any] = {"satirlar": [{"raf": "A1", "adet": 12}]}


@pytest.fixture(autouse=True)
def temiz_cevre(monkeypatch: pytest.MonkeyPatch) -> None:
    for degisken in DEFTERIKI_DEGISKENLERI:
        monkeypatch.delenv(degisken, raising=False)


@dataclass(frozen=True, slots=True)
class Ortam:
    veritabani: vt.Veritabani
    gelen: Path
    arsiv: Path


@pytest.fixture
def ortam(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Ortam]:
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(tmp_path / "kok"))
    ayar = ay.ayarlari_yukle()
    ay.dizinleri_hazirla(ayar)
    v = vt.Veritabani(ayar.veritabani_yolu)
    gocler.semayi_yukselt(v)
    yield Ortam(v, ayar.gelen_dizini, ayar.belge_dizini)
    v.kapat()


@dataclass(frozen=True, slots=True)
class Envanter:
    """``ENVANTER`` paketinin kimlikleri; sürüm 2 yalnız sürüm sınırını
    sınamak için vardır."""

    surum_id: int
    ikinci_surum_id: int
    raf_id: int
    sayim_id: int
    denetim_id: int
    ikinci_surum_sayim_id: int
    adet_id: int
    not_id: int
    denetim_alani_id: int
    nesne_id: int


@pytest.fixture
def env(ortam: Ortam) -> Envanter:
    with ortam.veritabani.islem() as o:
        paket = ti.paket_tanimla(o, "ENVANTER", "Envanter")
        surum = ti.surum_tanimla(o, paket.id, 1)
        ikinci = ti.surum_tanimla(o, paket.id, 2)
        raf = ti.nesne_turu_tanimla(o, surum.id, "RAF", "Raf")
        ti.ozellik_tanimla(o, raf.id, "kod", "Kod", DegerTuru.METIN, zorunlu=True)
        sayim = ti.kayit_turu_tanimla(o, surum.id, "SAYIM", "Sayım")
        adet = ti.kayit_alani_tanimla(
            o, sayim.id, "adet", "Adet", DegerTuru.TAM_SAYI, zorunlu=True
        )
        notu = ti.kayit_alani_tanimla(o, sayim.id, "not", "Not", DegerTuru.METIN)
        denetim = ti.kayit_turu_tanimla(o, surum.id, "DENETIM", "Denetim")
        denetim_alani = ti.kayit_alani_tanimla(
            o, denetim.id, "sonuc", "Sonuç", DegerTuru.METIN
        )
        ikinci_sayim = ti.kayit_turu_tanimla(o, ikinci.id, "SAYIM", "Sayım")
        nesne = ni.nesne_olustur(o, raf.id, {"kod": "A1"})
        return Envanter(
            surum.id,
            ikinci.id,
            raf.id,
            sayim.id,
            denetim.id,
            ikinci_sayim.id,
            adet.id,
            notu.id,
            denetim_alani.id,
            nesne.id,
        )


# --- yardımcılar ----------------------------------------------------------------------


def _paket(o: Ortam, ad: str = "envanter.pdf", icerik: bytes = PDF) -> tuple[int, int]:
    """Belge → okuma → paket zinciri; ``(paket_id, okuma_id)`` döndürür."""
    yol = o.gelen / ad
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_bytes(icerik)
    belge_id = bi.belge_al(
        o.veritabani, yol, gelen_dizini=o.gelen, arsiv_dizini=o.arsiv
    ).belge.id
    with o.veritabani.islem() as oturum:
        okuma = bi.okuma_baslat(oturum, belge_id, o.arsiv)
        bi.okuma_tamamla(oturum, okuma.id, OKUMA_ICERIGI)
        okuma_id = okuma.id
    with o.veritabani.islem() as oturum:
        return tsi.paket_olustur(oturum, okuma_id).id, okuma_id


def _kaynak(o: Ortam, okuma_id: int) -> int:
    with o.veritabani.islem() as oturum:
        return bi.kaynak_olustur(oturum, okuma_id, {"satir": 1}).id


def _kayit_yaz(
    o: Ortam,
    *,
    kayit_turu_id: int,
    tanim_surumu_id: int,
    islem_paketi_id: int,
    okuma_id: int,
    kaynak_id: int | None = None,
) -> int:
    """Ham SQL ile kesin kayıt satırı (servis 4.7/3'te gelir)."""
    with o.veritabani.islem() as oturum:
        oturum.execute(
            text(
                "INSERT INTO kayit (kayit_turu_id, tanim_surumu_id, islem_paketi_id, "
                "okuma_id, kaynak_id, olusturma_zamani) VALUES (:t, :s, :p, :o, :k, "
                "'2026-09-21 00:00:00')"
            ),
            {
                "t": kayit_turu_id,
                "s": tanim_surumu_id,
                "p": islem_paketi_id,
                "o": okuma_id,
                "k": kaynak_id,
            },
        )
        return int(oturum.execute(text("SELECT max(id) FROM kayit")).scalar_one())


def _sayi(o: Ortam, tablo: str) -> int:
    with o.veritabani.islem() as oturum:
        return int(oturum.execute(text(f"SELECT count(*) FROM {tablo}")).scalar_one())


# --- şemanın kendisi ------------------------------------------------------------------


def test_kayit_durum_sutunu_tasimaz(ortam: Ortam) -> None:
    """Karar 2026-09-21: satırın varlığı kesinliktir; taslak / kesinleşme
    durumu kesin kayıt tablosunda yoktur."""
    with ortam.veritabani.motor.connect() as baglanti:
        sutunlar = {s["name"] for s in inspect(baglanti).get_columns(kt.KAYIT)}
    assert sutunlar == {
        "id",
        "kayit_turu_id",
        "tanim_surumu_id",
        "islem_paketi_id",
        "okuma_id",
        "kaynak_id",
        "olusturma_zamani",
    }


def test_denetim_izi_kayit_sabiti_gercek_tabloyla_ayni() -> None:
    """``denetim_tablolari`` kayıt şemasını import etmez (taslak → denetim →
    kesin nesne zinciri olurdu); adın doğruluğu burada korunur."""
    assert dnt.KESIN_KAYIT == kt.KAYIT


def test_kayit_yazilir_ve_kokenini_tasir(ortam: Ortam, env: Envanter) -> None:
    paket_id, okuma_id = _paket(ortam)
    kaynak_id = _kaynak(ortam, okuma_id)
    kayit_id = _kayit_yaz(
        ortam,
        kayit_turu_id=env.sayim_id,
        tanim_surumu_id=env.surum_id,
        islem_paketi_id=paket_id,
        okuma_id=okuma_id,
        kaynak_id=kaynak_id,
    )
    with ortam.veritabani.islem() as oturum:
        oturum.execute(
            text(
                "INSERT INTO kayit_alani (kayit_id, kayit_turu_id, "
                "kayit_alani_tanimi_id, deger) VALUES (:k, :t, :a, '12')"
            ),
            {"k": kayit_id, "t": env.sayim_id, "a": env.adet_id},
        )
        oturum.execute(
            text("INSERT INTO kayit_nesne (kayit_id, nesne_id) VALUES (:k, :n)"),
            {"k": kayit_id, "n": env.nesne_id},
        )
    with ortam.veritabani.islem() as oturum:
        assert oturum.execute(
            text("SELECT islem_paketi_id, okuma_id, kaynak_id FROM kayit")
        ).all() == [(paket_id, okuma_id, kaynak_id)]
        assert oturum.execute(text("PRAGMA foreign_key_check")).all() == []


# --- köken (provenance) ---------------------------------------------------------------


def test_kayit_paketsiz_yazilamaz(ortam: Ortam, env: Envanter) -> None:
    """``islem_paketi_id`` zorunludur (karar 2026-09-21): kesin kayıt her zaman
    paket → okuma → belge zincirine dayanır."""
    _, okuma_id = _paket(ortam)
    with pytest.raises(IntegrityError, match="NOT NULL"):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(
                text(
                    "INSERT INTO kayit (kayit_turu_id, tanim_surumu_id, okuma_id, "
                    "olusturma_zamani) VALUES (:t, :s, :o, '2026-09-21')"
                ),
                {"t": env.sayim_id, "s": env.surum_id, "o": okuma_id},
            )
    assert _sayi(ortam, kt.KAYIT) == 0


def test_kayit_okumasi_paketin_okumasi_olmali(ortam: Ortam, env: Envanter) -> None:
    paket_id, _ = _paket(ortam)
    _, baska_okuma = _paket(ortam, "ikinci.pdf", PDF2)
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        _kayit_yaz(
            ortam,
            kayit_turu_id=env.sayim_id,
            tanim_surumu_id=env.surum_id,
            islem_paketi_id=paket_id,
            okuma_id=baska_okuma,
        )
    assert _sayi(ortam, kt.KAYIT) == 0


def test_kayit_kaynagi_ayni_okumadan_olmali(ortam: Ortam, env: Envanter) -> None:
    paket_id, okuma_id = _paket(ortam)
    _, baska_okuma = _paket(ortam, "ikinci.pdf", PDF2)
    baska_kaynak = _kaynak(ortam, baska_okuma)
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        _kayit_yaz(
            ortam,
            kayit_turu_id=env.sayim_id,
            tanim_surumu_id=env.surum_id,
            islem_paketi_id=paket_id,
            okuma_id=okuma_id,
            kaynak_id=baska_kaynak,
        )
    assert _sayi(ortam, kt.KAYIT) == 0


def test_kayit_turu_kendi_surumunde_olmali(ortam: Ortam, env: Envanter) -> None:
    """Tür ve sürüm iki rastgele kimlik değildir: ikinci sürümün ``SAYIM``ı
    birinci sürümle yazılamaz."""
    paket_id, okuma_id = _paket(ortam)
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        _kayit_yaz(
            ortam,
            kayit_turu_id=env.ikinci_surum_sayim_id,
            tanim_surumu_id=env.surum_id,
            islem_paketi_id=paket_id,
            okuma_id=okuma_id,
        )
    assert _sayi(ortam, kt.KAYIT) == 0


# --- alanlar --------------------------------------------------------------------------


def test_kayit_alani_baska_turun_alani_olamaz(ortam: Ortam, env: Envanter) -> None:
    paket_id, okuma_id = _paket(ortam)
    kayit_id = _kayit_yaz(
        ortam,
        kayit_turu_id=env.sayim_id,
        tanim_surumu_id=env.surum_id,
        islem_paketi_id=paket_id,
        okuma_id=okuma_id,
    )
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(
                text(
                    "INSERT INTO kayit_alani (kayit_id, kayit_turu_id, "
                    "kayit_alani_tanimi_id, deger) VALUES (:k, :t, :a, 'x')"
                ),
                {"k": kayit_id, "t": env.sayim_id, "a": env.denetim_alani_id},
            )
    assert _sayi(ortam, kt.KAYIT_ALANI) == 0


def test_kayit_alani_kaydin_turunu_tasimali(ortam: Ortam, env: Envanter) -> None:
    """Alan satırı kaydın türünü taşır; başka tür yazılırsa hem kayda hem alan
    tanımına giden bileşik dış anahtarlar düşer."""
    paket_id, okuma_id = _paket(ortam)
    kayit_id = _kayit_yaz(
        ortam,
        kayit_turu_id=env.sayim_id,
        tanim_surumu_id=env.surum_id,
        islem_paketi_id=paket_id,
        okuma_id=okuma_id,
    )
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(
                text(
                    "INSERT INTO kayit_alani (kayit_id, kayit_turu_id, "
                    "kayit_alani_tanimi_id, deger) VALUES (:k, :t, :a, 'x')"
                ),
                {"k": kayit_id, "t": env.denetim_id, "a": env.denetim_alani_id},
            )
    assert _sayi(ortam, kt.KAYIT_ALANI) == 0


def test_ayni_alan_kayitta_iki_kez_bulunamaz(ortam: Ortam, env: Envanter) -> None:
    paket_id, okuma_id = _paket(ortam)
    kayit_id = _kayit_yaz(
        ortam,
        kayit_turu_id=env.sayim_id,
        tanim_surumu_id=env.surum_id,
        islem_paketi_id=paket_id,
        okuma_id=okuma_id,
    )
    with ortam.veritabani.islem() as oturum:
        oturum.execute(
            text(
                "INSERT INTO kayit_alani (kayit_id, kayit_turu_id, "
                "kayit_alani_tanimi_id, deger) VALUES (:k, :t, :a, '12')"
            ),
            {"k": kayit_id, "t": env.sayim_id, "a": env.adet_id},
        )
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(
                text(
                    "INSERT INTO kayit_alani (kayit_id, kayit_turu_id, "
                    "kayit_alani_tanimi_id, deger) VALUES (:k, :t, :a, '13')"
                ),
                {"k": kayit_id, "t": env.sayim_id, "a": env.adet_id},
            )
    assert _sayi(ortam, kt.KAYIT_ALANI) == 1


# --- nesne bağı -----------------------------------------------------------------------


def test_kayit_nesne_bagi_mukerrer_olamaz(ortam: Ortam, env: Envanter) -> None:
    paket_id, okuma_id = _paket(ortam)
    kayit_id = _kayit_yaz(
        ortam,
        kayit_turu_id=env.sayim_id,
        tanim_surumu_id=env.surum_id,
        islem_paketi_id=paket_id,
        okuma_id=okuma_id,
    )
    with ortam.veritabani.islem() as oturum:
        oturum.execute(
            text("INSERT INTO kayit_nesne (kayit_id, nesne_id) VALUES (:k, :n)"),
            {"k": kayit_id, "n": env.nesne_id},
        )
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(
                text("INSERT INTO kayit_nesne (kayit_id, nesne_id) VALUES (:k, :n)"),
                {"k": kayit_id, "n": env.nesne_id},
            )
    assert _sayi(ortam, kt.KAYIT_NESNE) == 1


def test_kayit_olmayan_nesneye_baglanamaz(ortam: Ortam, env: Envanter) -> None:
    paket_id, okuma_id = _paket(ortam)
    kayit_id = _kayit_yaz(
        ortam,
        kayit_turu_id=env.sayim_id,
        tanim_surumu_id=env.surum_id,
        islem_paketi_id=paket_id,
        okuma_id=okuma_id,
    )
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(
                text("INSERT INTO kayit_nesne (kayit_id, nesne_id) VALUES (:k, 999)"),
                {"k": kayit_id},
            )
    assert _sayi(ortam, kt.KAYIT_NESNE) == 0


def test_kayit_baska_surumdeki_nesneye_baglanabilir(
    ortam: Ortam, env: Envanter
) -> None:
    """Karar 2026-09-21: sürüm eşitliği aranmaz. İkinci sürümde üretilen kayıt,
    birinci sürümde doğmuş etkin nesneye bağlanabilir."""
    paket_id, okuma_id = _paket(ortam)
    kayit_id = _kayit_yaz(
        ortam,
        kayit_turu_id=env.ikinci_surum_sayim_id,
        tanim_surumu_id=env.ikinci_surum_id,
        islem_paketi_id=paket_id,
        okuma_id=okuma_id,
    )
    with ortam.veritabani.islem() as oturum:
        oturum.execute(
            text("INSERT INTO kayit_nesne (kayit_id, nesne_id) VALUES (:k, :n)"),
            {"k": kayit_id, "n": env.nesne_id},
        )
        assert oturum.execute(text("PRAGMA foreign_key_check")).all() == []
    assert _sayi(ortam, kt.KAYIT_NESNE) == 1


# --- denetim izi ----------------------------------------------------------------------


def test_denetim_izi_kayda_baglanir_ve_kayit_silinemez(
    ortam: Ortam, env: Envanter
) -> None:
    """İz kayda dış anahtarla bağlanır ve ``RESTRICT``tir: ize konu olan kayıt
    sessizce silinemez."""
    paket_id, okuma_id = _paket(ortam)
    kayit_id = _kayit_yaz(
        ortam,
        kayit_turu_id=env.sayim_id,
        tanim_surumu_id=env.surum_id,
        islem_paketi_id=paket_id,
        okuma_id=okuma_id,
    )
    with ortam.veritabani.islem() as oturum:
        oturum.execute(
            text(
                "INSERT INTO denetim_izi (olay, olay_zamani, aktor_turu, "
                "aktor_kimligi, kayit_id) VALUES ('kayit_olusturuldu', "
                "'2026-09-21', 'ajan', 'test', :k)"
            ),
            {"k": kayit_id},
        )
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(text("DELETE FROM kayit WHERE id = :k"), {"k": kayit_id})
    assert _sayi(ortam, kt.KAYIT) == 1


def test_denetim_izi_tanimsiz_olayi_reddeder(ortam: Ortam) -> None:
    with pytest.raises(IntegrityError, match="CHECK constraint failed"):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(
                text(
                    "INSERT INTO denetim_izi (olay, olay_zamani, aktor_turu, "
                    "aktor_kimligi) VALUES ('kayit_silindi', '2026-09-21', "
                    "'ajan', 'test')"
                )
            )
