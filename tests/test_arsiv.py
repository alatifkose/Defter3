"""Arşiv dosya katmanı testleri (Aşama 4.4): gelen dizini sınırı, akışla kopya,
SHA-256, içerik adresli atomik taşıma, bütünlük doğrulama, tarama.

Veritabanı yok; yalnız dosya sistemi (``tmp_path``). Dosyalar sentetiktir:
envanter listesi görünümlü PDF, sahte PNG / JPEG baytları, metin. Simgesel
bağlantı testleri Windows'ta yetki yoksa, junction testleri Windows dışında
atlanır (``test_ayarlar`` kalıbı).
"""

from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import BinaryIO

import pytest

from defteruc.cekirdek import arsiv

PDF = b"%PDF-1.7\n% envanter listesi: raf A1, 12 kalem\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 24
METIN = "raf;urun;adet\nA1;vida;12\n".encode()
VARSAYILAN = arsiv.VARSAYILAN_MIME


@pytest.fixture
def gelen(tmp_path: Path) -> Path:
    dizin = tmp_path / "gelen"
    dizin.mkdir()
    return dizin


@pytest.fixture
def arsiv_dizini(tmp_path: Path) -> Path:
    dizin = tmp_path / "belgeler"
    dizin.mkdir()
    return dizin


def _yaz(yol: Path, icerik: bytes) -> Path:
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_bytes(icerik)
    return yol


def _arsivle(yol: Path | str, gelen: Path, arsiv_dizini: Path) -> arsiv.ArsivlenenDosya:
    return arsiv.dosyayi_arsivle(yol, gelen_dizini=gelen, arsiv_dizini=arsiv_dizini)


def _dosyalar(dizin: Path) -> set[str]:
    return {p.relative_to(dizin).as_posix() for p in dizin.rglob("*") if p.is_file()}


def _gecici_yok(arsiv_dizini: Path) -> bool:
    gecici = arsiv.gecici_dizin(arsiv_dizini)
    return not gecici.exists() or list(gecici.iterdir()) == []


def _sha(icerik: bytes) -> str:
    return hashlib.sha256(icerik).hexdigest()


def _yol(icerik: bytes) -> str:
    ozet = _sha(icerik)
    return f"{ozet[:2]}/{ozet}"


def _simgesel_baglanti(baglanti: Path, hedef: Path) -> None:
    try:
        os.symlink(hedef, baglanti, target_is_directory=hedef.is_dir())
    except OSError as hata:
        pytest.skip(f"simgesel bağlantı kurulamadı (yetki?): {hata}")


def _junction(baglanti: Path, hedef: Path) -> None:
    if sys.platform != "win32":
        pytest.skip("junction yalnız Windows'ta var")
    sonuc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(baglanti), str(hedef)],
        capture_output=True,
        text=True,
        check=False,
    )
    if sonuc.returncode != 0 or not baglanti.exists():
        pytest.skip(f"junction kurulamadı: {sonuc.stderr.strip() or sonuc.stdout}")


# --- gelen dizini sınırı --------------------------------------------------------------


def test_gecerli_dosya_kabul_edilir(gelen: Path) -> None:
    dosya = _yaz(gelen / "alt" / "Envanter.PDF", PDF)

    assert arsiv.gelen_dosyayi_dogrula(str(dosya), gelen) == dosya
    assert arsiv.gelen_dosyayi_dogrula(dosya, gelen) == dosya


@pytest.mark.parametrize("yol", ["", "   "])
def test_bos_yol_reddedilir(gelen: Path, yol: str) -> None:
    with pytest.raises(arsiv.GelenDosyaGecersiz, match="boş olamaz"):
        arsiv.gelen_dosyayi_dogrula(yol, gelen)


def test_goreli_yol_reddedilir(gelen: Path) -> None:
    _yaz(gelen / "a.pdf", PDF)
    with pytest.raises(arsiv.GelenDosyaGecersiz, match="mutlak olmalı"):
        arsiv.gelen_dosyayi_dogrula("gelen/a.pdf", gelen)


def test_ust_dizin_parcasi_reddedilir(gelen: Path) -> None:
    _yaz(gelen / "a.pdf", PDF)
    with pytest.raises(arsiv.GelenDosyaGecersiz, match=r"\(\.\.\)"):
        arsiv.gelen_dosyayi_dogrula(str(gelen / "alt" / ".." / "a.pdf"), gelen)


def test_olmayan_dosya_reddedilir(gelen: Path) -> None:
    with pytest.raises(arsiv.GelenDosyaGecersiz, match="bulunamadı"):
        arsiv.gelen_dosyayi_dogrula(str(gelen / "yok.pdf"), gelen)


def test_dizin_reddedilir(gelen: Path) -> None:
    (gelen / "klasor").mkdir()
    with pytest.raises(arsiv.GelenDosyaGecersiz, match="sıradan bir dosya değil"):
        arsiv.gelen_dosyayi_dogrula(str(gelen / "klasor"), gelen)


def test_gelen_dizininin_kendisi_reddedilir(gelen: Path) -> None:
    with pytest.raises(arsiv.GelenDosyaGecersiz, match="dışında"):
        arsiv.gelen_dosyayi_dogrula(str(gelen), gelen)


def test_gelen_dizini_disi_reddedilir(tmp_path: Path, gelen: Path) -> None:
    disari = _yaz(tmp_path / "disari" / "a.pdf", PDF)
    with pytest.raises(arsiv.GelenDosyaGecersiz, match="dışında"):
        arsiv.gelen_dosyayi_dogrula(str(disari), gelen)


def test_on_ek_benzerligi_yetmez(tmp_path: Path, gelen: Path) -> None:
    """``gelen2/`` ``gelen/``in altı değildir."""
    benzer = _yaz(tmp_path / "gelen2" / "a.pdf", PDF)
    with pytest.raises(arsiv.GelenDosyaGecersiz, match="dışında"):
        arsiv.gelen_dosyayi_dogrula(str(benzer), gelen)


def test_gelen_dizini_mutlak_olmali(gelen: Path) -> None:
    with pytest.raises(ValueError, match="gelen dizini mutlak"):
        arsiv.gelen_dosyayi_dogrula(str(gelen / "a.pdf"), Path("gelen"))


def test_simgesel_baglanti_ile_disari_kacis_reddedilir(
    tmp_path: Path, gelen: Path, arsiv_dizini: Path
) -> None:
    disari = _yaz(tmp_path / "disari" / "gizli.pdf", PDF)
    once = disari.stat().st_mtime_ns
    _simgesel_baglanti(gelen / "bag.pdf", disari)

    with pytest.raises(arsiv.GelenDosyaGecersiz, match="bağlantı") as hata:
        _arsivle(gelen / "bag.pdf", gelen, arsiv_dizini)

    assert str(tmp_path) not in str(hata.value)
    assert disari.read_bytes() == PDF and disari.stat().st_mtime_ns == once
    assert _dosyalar(arsiv_dizini) == set()  # dışarıdaki dosyaya dokunulmadı


def test_simgesel_dizin_baglantisi_ile_iceride_gorunup_disari_cikma_reddedilir(
    tmp_path: Path, gelen: Path
) -> None:
    disari = tmp_path / "disari"
    _yaz(disari / "a.pdf", PDF)
    _simgesel_baglanti(gelen / "bag", disari)

    with pytest.raises(arsiv.GelenDosyaGecersiz, match="bağlantı"):
        arsiv.gelen_dosyayi_dogrula(str(gelen / "bag" / "a.pdf"), gelen)


def test_junction_ile_iceride_gorunup_disari_cikma_reddedilir(
    tmp_path: Path, gelen: Path
) -> None:
    disari = tmp_path / "disari"
    _yaz(disari / "a.pdf", PDF)
    _junction(gelen / "bag", disari)

    with pytest.raises(arsiv.GelenDosyaGecersiz, match="junction"):
        arsiv.gelen_dosyayi_dogrula(str(gelen / "bag" / "a.pdf"), gelen)


def test_iceriyi_gosteren_baglanti_da_reddedilir(gelen: Path) -> None:
    """Gelen dizini altındaki her bağlantı reddedilir; hedefi içeride olsa da."""
    _yaz(gelen / "ic" / "a.pdf", PDF)
    if sys.platform == "win32":
        _junction(gelen / "bag", gelen / "ic")
    else:
        _simgesel_baglanti(gelen / "bag", gelen / "ic")

    with pytest.raises(arsiv.GelenDosyaGecersiz, match="bağlantı|junction"):
        arsiv.gelen_dosyayi_dogrula(str(gelen / "bag" / "a.pdf"), gelen)


def test_gelen_dizininin_kendisi_baglanti_olabilir(tmp_path: Path) -> None:
    """Ayar gelen dizinini bağlantıyla gösteriyorsa altındaki düz dosya geçerlidir."""
    gercek = tmp_path / "gercek_gelen"
    dosya = _yaz(gercek / "a.pdf", PDF)
    bag = tmp_path / "bag"
    if sys.platform == "win32":
        _junction(bag, gercek)
    else:
        _simgesel_baglanti(bag, gercek)

    assert arsiv.gelen_dosyayi_dogrula(str(bag / "a.pdf"), bag) == bag / "a.pdf"
    assert arsiv.gelen_dosyayi_dogrula(str(dosya), bag / ".." / "gercek_gelen") == dosya


def test_okunamayan_dosya_reddedilir_gecici_kalmaz(
    gelen: Path, arsiv_dizini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dosya = _yaz(gelen / "a.pdf", PDF)

    def acilmaz(_yol: Path) -> BinaryIO:
        raise PermissionError("sentetik: okuma izni yok")

    monkeypatch.setattr(arsiv, "_kaynagi_ac", acilmaz)
    with pytest.raises(arsiv.DosyaOkunamadi) as hata:
        _arsivle(dosya, gelen, arsiv_dizini)

    assert "sentetik" not in str(hata.value) and str(gelen) not in str(hata.value)
    assert _dosyalar(arsiv_dizini) == set()


def test_hata_mesaji_yol_tasimaz(tmp_path: Path, gelen: Path) -> None:
    disari = _yaz(tmp_path / "disari" / "ozel-ad.pdf", PDF)
    with pytest.raises(arsiv.GelenDosyaGecersiz) as hata:
        arsiv.gelen_dosyayi_dogrula(str(disari), gelen)
    assert "ozel-ad" not in str(hata.value) and str(tmp_path) not in str(hata.value)


# --- arşivleme ------------------------------------------------------------------------


def test_dosya_icerik_adresli_uzantisiz_yola_tasinir(
    gelen: Path, arsiv_dizini: Path
) -> None:
    kaynak = _yaz(gelen / "Envanter.PDF", PDF)

    sonuc = _arsivle(kaynak, gelen, arsiv_dizini)

    assert sonuc == arsiv.ArsivlenenDosya(
        sha256=_sha(PDF),
        boyut=len(PDF),
        mime="application/pdf",
        kaynak_uzantisi=".pdf",
        kaynak_adi="Envanter.PDF",
        goreli_yol=_yol(PDF),
        diskte_zaten_vardi=False,
    )
    hedef = arsiv.arsiv_yolu(arsiv_dizini, sonuc.goreli_yol)
    assert hedef.suffix == "" and hedef.read_bytes() == PDF
    assert _dosyalar(arsiv_dizini) == {sonuc.goreli_yol}  # geçici dosya kalmadı
    assert kaynak.read_bytes() == PDF  # kaynak kopyalanır, silinmez
    assert (
        arsiv.arsiv_dosyasini_dogrula(
            arsiv_dizini, sonuc.goreli_yol, sonuc.boyut, sonuc.sha256
        )
        == hedef
    )


def test_bos_dosya_reddedilir(gelen: Path, arsiv_dizini: Path) -> None:
    kaynak = _yaz(gelen / "bos.txt", b"")

    with pytest.raises(arsiv.GelenDosyaGecersiz, match="boş dosya"):
        _arsivle(kaynak, gelen, arsiv_dizini)

    assert _dosyalar(arsiv_dizini) == set()


def test_boyut_siniri_50_mib() -> None:
    assert arsiv.AZAMI_DOSYA_BOYUTU == 50 * 1024 * 1024


def test_tam_sinirdaki_dosya_kabul_ustu_reddedilir(
    gelen: Path, arsiv_dizini: Path
) -> None:
    sinirda = _yaz(gelen / "sinirda.bin", b"z" * 100)
    ustunde = _yaz(gelen / "ustunde.bin", b"z" * 101)

    sonuc = arsiv.dosyayi_arsivle(
        sinirda, gelen_dizini=gelen, arsiv_dizini=arsiv_dizini, azami_boyut=100
    )
    assert sonuc.boyut == 100
    with pytest.raises(arsiv.DosyaCokBuyuk, match="kesilmez"):
        arsiv.dosyayi_arsivle(
            ustunde, gelen_dizini=gelen, arsiv_dizini=arsiv_dizini, azami_boyut=100
        )
    assert _dosyalar(arsiv_dizini) == {sonuc.goreli_yol}


def test_gercek_50_mib_kabul_bir_bayt_fazlasi_red(
    gelen: Path, arsiv_dizini: Path
) -> None:
    sinirda = gelen / "buyuk.bin"
    with sinirda.open("wb") as f:
        f.truncate(arsiv.AZAMI_DOSYA_BOYUTU)
    ustunde = gelen / "fazla.bin"
    with ustunde.open("wb") as f:
        f.truncate(arsiv.AZAMI_DOSYA_BOYUTU + 1)

    sonuc = _arsivle(sinirda, gelen, arsiv_dizini)
    assert sonuc.boyut == arsiv.AZAMI_DOSYA_BOYUTU
    with pytest.raises(arsiv.DosyaCokBuyuk):
        _arsivle(ustunde, gelen, arsiv_dizini)
    assert _dosyalar(arsiv_dizini) == {sonuc.goreli_yol}


def test_akis_sirasinda_buyuyen_dosya_da_reddedilir_gecici_kalmaz(
    gelen: Path, arsiv_dizini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``stat`` küçük gösterse de akış sınırı aşarsa kesilmez, reddedilir."""
    dosya = _yaz(gelen / "a.bin", b"k" * 10)

    def buyuk_akis(yol: Path) -> BinaryIO:
        yol.write_bytes(b"k" * 300)  # stat 10 gösterdi, akış 300 verecek
        return yol.open("rb")

    monkeypatch.setattr(arsiv, "_kaynagi_ac", buyuk_akis)

    with pytest.raises(arsiv.DosyaCokBuyuk):
        arsiv.dosyayi_arsivle(
            dosya, gelen_dizini=gelen, arsiv_dizini=arsiv_dizini, azami_boyut=100
        )

    assert _dosyalar(arsiv_dizini) == set()


def test_buyuk_dosya_parcali_okunur_ozet_dogru(gelen: Path, arsiv_dizini: Path) -> None:
    icerik = PNG + os.urandom(2 * arsiv.OKUMA_PARCA_BOYUTU + 17)
    kaynak = _yaz(gelen / "foto.png", icerik)

    sonuc = _arsivle(kaynak, gelen, arsiv_dizini)

    assert sonuc.sha256 == _sha(icerik) and sonuc.boyut == len(icerik)
    assert sonuc.mime == "image/png" and sonuc.goreli_yol == _yol(icerik)
    assert arsiv.arsiv_yolu(arsiv_dizini, sonuc.goreli_yol).read_bytes() == icerik


@pytest.mark.parametrize(
    ("ad", "icerik", "mime", "uzanti"),
    [
        ("liste.pdf", PDF, "application/pdf", ".pdf"),
        ("LISTE.PDF", PDF, "application/pdf", ".pdf"),
        ("raf.png", PNG, "image/png", ".png"),
        ("raf.jpg", JPEG, "image/jpeg", ".jpg"),
        ("raf.jpeg", JPEG, "image/jpeg", ".jpeg"),
        ("liste", PDF, "application/pdf", ""),  # uzantısız, imzadan
        ("liste.txt", METIN, "application/octet-stream", ".txt"),
        ("liste.xyz", METIN, "application/octet-stream", ".xyz"),
        ("liste", METIN, "application/octet-stream", ""),
        ("a.b.tar.gz", METIN, "application/octet-stream", ".gz"),
    ],
)
def test_imza_algilama_ve_guvenli_fallback(
    gelen: Path, arsiv_dizini: Path, ad: str, icerik: bytes, mime: str, uzanti: str
) -> None:
    sonuc = _arsivle(_yaz(gelen / ad, icerik), gelen, arsiv_dizini)

    assert (sonuc.mime, sonuc.kaynak_uzantisi, sonuc.kaynak_adi) == (mime, uzanti, ad)


@pytest.mark.parametrize(
    ("ad", "icerik", "mime", "uzanti"),
    [
        ("liste.png", PDF, "application/pdf", ".png"),  # PDF imzası, PNG uzantısı
        ("raf.pdf", PNG, "image/png", ".pdf"),
        ("raf.jpg", PNG, "image/png", ".jpg"),
        ("raf.PNG", JPEG, "image/jpeg", ".png"),
        ("liste.pdf", METIN, "application/octet-stream", ".pdf"),  # imzasız .pdf
        ("raf.png", METIN, "application/octet-stream", ".png"),
    ],
)
def test_imza_uzanti_uyusmazligi_red_sebebi_degil(
    gelen: Path, arsiv_dizini: Path, ad: str, icerik: bytes, mime: str, uzanti: str
) -> None:
    """Karar 2026-09-19: ad ve uzantı güvenilir içerik bilgisi değildir; MIME'ı
    imza belirler, uzantı yalnız metadata'dır, uyuşmazlık arşivlemeye engel
    değildir."""
    sonuc = _arsivle(_yaz(gelen / ad, icerik), gelen, arsiv_dizini)

    assert (sonuc.mime, sonuc.kaynak_uzantisi) == (mime, uzanti)
    assert sonuc.goreli_yol == _yol(icerik)
    assert arsiv.arsiv_yolu(arsiv_dizini, sonuc.goreli_yol).read_bytes() == icerik
    assert not hasattr(arsiv, "DosyaTuruUyusmuyor")


def test_uzanti_metadata_kurali(gelen: Path, arsiv_dizini: Path) -> None:
    """Çok uzun ya da alfasayısal olmayan uzantı boş sayılır; MIME etkilenmez."""
    sonuc = _arsivle(_yaz(gelen / "a.cokuzunbiruzanti", METIN), gelen, arsiv_dizini)
    assert sonuc.kaynak_uzantisi == ""
    sonuc = _arsivle(_yaz(gelen / "b.a-b", METIN), gelen, arsiv_dizini)
    assert sonuc.kaynak_uzantisi == ""


@pytest.mark.parametrize(
    ("adlar", "icerik", "mime"),
    [
        # Aynı PDF baytları: doğru uzantı, yanlış uzantı, başka imzanın uzantısı,
        # uzantısız, bilinmeyen uzantı → tek fiziksel dosya, MIME imzadan
        (("a.pdf", "a.bin", "a.png", "a", "herhangi.xyz"), PDF, "application/pdf"),
        (("foto.png", "foto.jpg", "foto", "foto.pdf", "x.dat"), PNG, "image/png"),
        (("r.jpg", "r.jpeg", "r.png", "r", "r.bin"), JPEG, "image/jpeg"),
        (("liste.pdf", "belge.PDF"), PDF, "application/pdf"),  # büyük-küçük harf
        (("a.pdf", "alt/a.pdf"), PDF, "application/pdf"),  # aynı ad, farklı dizin
        # İmzasız içerik: her ad octet-stream, yine tek dosya
        (("liste.txt", "belge.TXT", "dosya", "x.bin", "y.pdf"), METIN, VARSAYILAN),
    ],
)
def test_ayni_baytlar_tek_fiziksel_dosya(
    gelen: Path, arsiv_dizini: Path, adlar: tuple[str, ...], icerik: bytes, mime: str
) -> None:
    sonuclar = [_arsivle(_yaz(gelen / ad, icerik), gelen, arsiv_dizini) for ad in adlar]

    assert {s.sha256 for s in sonuclar} == {_sha(icerik)}
    assert {s.goreli_yol for s in sonuclar} == {_yol(icerik)}
    assert {s.mime for s in sonuclar} == {mime}
    assert [s.diskte_zaten_vardi for s in sonuclar] == [False] + [True] * (
        len(adlar) - 1
    )
    assert [s.kaynak_adi for s in sonuclar] == [Path(a).name for a in adlar]
    assert [s.kaynak_uzantisi for s in sonuclar] == [
        arsiv._uzanti(a)  # pyright: ignore[reportPrivateUsage]
        for a in adlar
    ]  # her gelişin kendi metadata'sı
    assert _dosyalar(arsiv_dizini) == {_yol(icerik)}


def test_gecici_yazma_hatasi_gecici_dosya_birakmaz(
    gelen: Path, arsiv_dizini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kaynak = _yaz(gelen / "a.pdf", PDF + os.urandom(arsiv.OKUMA_PARCA_BOYUTU + 5))

    class PatlayanYazici(io.FileIO):
        def write(self, b: object, /) -> int:
            super().write(b)  # type: ignore[arg-type]
            raise OSError("sentetik: disk dolu")

    def patlayan_ac(yol: Path) -> BinaryIO:
        return PatlayanYazici(yol, "xb")

    monkeypatch.setattr(arsiv, "_geciciyi_ac", patlayan_ac)
    with pytest.raises(arsiv.ArsivYazilamadi, match="geçici") as hata:
        _arsivle(kaynak, gelen, arsiv_dizini)

    assert "sentetik" not in str(hata.value)
    assert _dosyalar(arsiv_dizini) == set()


def test_tasima_hatasi_hedef_ve_gecici_birakmaz(
    gelen: Path, arsiv_dizini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kaynak = _yaz(gelen / "a.pdf", PDF)

    def tasinmaz(_g: Path, _h: Path) -> None:
        raise OSError("sentetik: taşıma hatası")

    monkeypatch.setattr(arsiv, "_yerine_koy", tasinmaz)
    with pytest.raises(arsiv.ArsivYazilamadi, match="taşınamadı"):
        _arsivle(kaynak, gelen, arsiv_dizini)

    assert _dosyalar(arsiv_dizini) == set()
    assert not arsiv.arsiv_yolu(arsiv_dizini, _yol(PDF)).exists()


def test_windows_tarzi_tasima_reddi_hedef_dogruysa_zaten_vardi(
    gelen: Path, arsiv_dizini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hedef, "yok" kontrolünden sonra başka süreççe yazılıp açık tutulduysa taşıma
    reddedilir; hedef özetle doğrulanır ve sonuç "zaten vardı" olur."""
    hedef = arsiv.arsiv_yolu(arsiv_dizini, _yol(PDF))

    def baska_surec_yazdi_ve_reddet(_g: Path, h: Path) -> None:
        h.write_bytes(PDF)
        raise PermissionError("sentetik: hedef kullanımda")

    monkeypatch.setattr(arsiv, "_yerine_koy", baska_surec_yazdi_ve_reddet)
    sonuc = _arsivle(_yaz(gelen / "b.pdf", PDF), gelen, arsiv_dizini)

    assert sonuc.diskte_zaten_vardi is True
    assert hedef.read_bytes() == PDF
    assert _dosyalar(arsiv_dizini) == {_yol(PDF)}


def test_tasima_reddi_hedef_yoksa_yazma_hatasi(
    gelen: Path, arsiv_dizini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reddet(_g: Path, _h: Path) -> None:
        raise PermissionError("sentetik: izin yok")

    monkeypatch.setattr(arsiv, "_yerine_koy", reddet)
    with pytest.raises(arsiv.ArsivYazilamadi):
        _arsivle(_yaz(gelen / "b.pdf", PDF), gelen, arsiv_dizini)
    assert _dosyalar(arsiv_dizini) == set()


def test_mevcut_hedef_bozuksa_duplicate_sayilmaz(
    gelen: Path, arsiv_dizini: Path
) -> None:
    hedef = arsiv.arsiv_yolu(arsiv_dizini, _yol(PDF))
    hedef.parent.mkdir(parents=True)
    bozuk = PDF[:-1] + b"X"  # aynı boyut, farklı içerik
    hedef.write_bytes(bozuk)

    with pytest.raises(arsiv.ArsivButunlukHatasi, match="özeti taşımıyor") as hata:
        _arsivle(_yaz(gelen / "a.pdf", PDF), gelen, arsiv_dizini)

    assert str(arsiv_dizini) not in str(hata.value)
    assert hedef.read_bytes() == bozuk  # sessiz onarım yok
    assert _dosyalar(arsiv_dizini) == {_yol(PDF)}  # geçici kalmadı


def test_mevcut_hedef_farkli_boyutta_bozuksa_hata(
    gelen: Path, arsiv_dizini: Path
) -> None:
    hedef = arsiv.arsiv_yolu(arsiv_dizini, _yol(PDF))
    hedef.parent.mkdir(parents=True)
    hedef.write_bytes(PDF + b"fazla")

    with pytest.raises(arsiv.ArsivButunlukHatasi, match="boyutu"):
        _arsivle(_yaz(gelen / "a.pdf", PDF), gelen, arsiv_dizini)


def test_eszamanli_ayni_icerik_tek_gecerli_dosya(
    gelen: Path, arsiv_dizini: Path
) -> None:
    icerik = PDF + os.urandom(arsiv.OKUMA_PARCA_BOYUTU // 2)
    kaynaklar = [_yaz(gelen / f"k{i}.pdf", icerik) for i in range(8)]

    def arsivle(kaynak: Path) -> arsiv.ArsivlenenDosya:
        return _arsivle(kaynak, gelen, arsiv_dizini)

    with ThreadPoolExecutor(max_workers=8) as havuz:
        sonuclar = list(havuz.map(arsivle, kaynaklar))

    assert {s.sha256 for s in sonuclar} == {_sha(icerik)}
    assert _dosyalar(arsiv_dizini) == {_yol(icerik)}
    assert arsiv.arsiv_yolu(arsiv_dizini, _yol(icerik)).read_bytes() == icerik
    assert _gecici_yok(arsiv_dizini)
    yeni_yazanlar = [s for s in sonuclar if not s.diskte_zaten_vardi]
    assert yeni_yazanlar
    if os.name == "nt":
        # Hedef bir kez oluştuktan sonra üstüne yazılmaz: yalnız ilk taşıyan yazar.
        assert len(yeni_yazanlar) == 1


@pytest.mark.skipif(
    os.name != "nt", reason="POSIX rename var olan hedefin üstüne yazar"
)
def test_tasima_var_olan_hedefin_ustune_yazmaz(arsiv_dizini: Path) -> None:
    """İçerik adresli hedef oluştuktan sonra değişmez; ikinci taşıma reddedilir ve
    hedefteki baytlar olduğu gibi kalır (Windows)."""
    hedef = _yaz(arsiv.arsiv_yolu(arsiv_dizini, _yol(PDF)), PDF)
    gecici = _yaz(arsiv.gecici_dizin(arsiv_dizini) / "x.tmp", PDF)
    with pytest.raises(FileExistsError):
        arsiv._yerine_koy(gecici, hedef)  # pyright: ignore[reportPrivateUsage]
    assert hedef.read_bytes() == PDF
    assert gecici.is_file()


def test_import_dizin_olusturmaz_arsivleme_kendi_dizinini_kurar(
    gelen: Path, tmp_path: Path
) -> None:
    yeni = tmp_path / "henuz" / "yok"
    sonuc = _arsivle(_yaz(gelen / "a.pdf", PDF), gelen, yeni)
    assert arsiv.arsiv_yolu(yeni, sonuc.goreli_yol).is_file()


# --- yol hesabı ve bütünlük -----------------------------------------------------------


def test_goreli_yol_yalniz_ozetten() -> None:
    ozet = _sha(PDF)
    assert arsiv.arsiv_goreli_yolu(ozet) == f"{ozet[:2]}/{ozet}"
    with pytest.raises(ValueError):
        arsiv.arsiv_goreli_yolu(ozet.upper())
    with pytest.raises(ValueError):
        arsiv.arsiv_goreli_yolu(ozet[:-1])


def test_arsiv_yolu_bicimi_denetlenir(arsiv_dizini: Path) -> None:
    ozet = _sha(PDF)
    assert arsiv.arsiv_yolu(arsiv_dizini, f"{ozet[:2]}/{ozet}") == (
        arsiv_dizini / ozet[:2] / ozet
    )
    for kotu in (f"zz/{ozet}", f"{ozet[:2]}/{ozet}.pdf", f"../{ozet[:2]}/{ozet}", ozet):
        with pytest.raises(ValueError):
            arsiv.arsiv_yolu(arsiv_dizini, kotu)


def test_arsiv_dosyasini_dogrula_eksik_bozuk_dizin(arsiv_dizini: Path) -> None:
    ozet, yol = _sha(PDF), _yol(PDF)
    with pytest.raises(arsiv.ArsivDosyasiEksik):
        arsiv.arsiv_dosyasini_dogrula(arsiv_dizini, yol, len(PDF), ozet)

    hedef = arsiv.arsiv_yolu(arsiv_dizini, yol)
    hedef.parent.mkdir(parents=True)
    hedef.write_bytes(PDF)
    assert arsiv.arsiv_dosyasini_dogrula(arsiv_dizini, yol, len(PDF), ozet) == hedef
    assert arsiv.arsiv_dosyasini_dogrula(arsiv_dizini, yol, len(PDF)) == hedef
    with pytest.raises(arsiv.ArsivButunlukHatasi, match="boyutu"):
        arsiv.arsiv_dosyasini_dogrula(arsiv_dizini, yol, len(PDF) + 1, ozet)

    hedef.write_bytes(PDF[:-1] + b"X")
    assert arsiv.arsiv_dosyasini_dogrula(arsiv_dizini, yol, len(PDF)) == hedef
    with pytest.raises(arsiv.ArsivButunlukHatasi, match="özeti"):
        arsiv.arsiv_dosyasini_dogrula(arsiv_dizini, yol, len(PDF), ozet)

    hedef.unlink()
    hedef.mkdir()
    with pytest.raises(arsiv.ArsivButunlukHatasi, match="sıradan dosya değil"):
        arsiv.arsiv_dosyasini_dogrula(arsiv_dizini, yol, len(PDF), ozet)


def test_sha256_hesapla(gelen: Path) -> None:
    icerik = os.urandom(arsiv.OKUMA_PARCA_BOYUTU + 3)
    assert arsiv.sha256_hesapla(_yaz(gelen / "a", icerik)) == (
        _sha(icerik),
        len(icerik),
    )
    with pytest.raises(arsiv.DosyaOkunamadi):
        arsiv.sha256_hesapla(gelen / "yok")


def test_arsivi_tara_siniflar(arsiv_dizini: Path, gelen: Path) -> None:
    sonuc = _arsivle(_yaz(gelen / "a.pdf", PDF), gelen, arsiv_dizini)
    sahipsiz = arsiv.arsiv_yolu(arsiv_dizini, _yol(PNG))
    sahipsiz.parent.mkdir(parents=True, exist_ok=True)
    sahipsiz.write_bytes(PNG)
    (arsiv.gecici_dizin(arsiv_dizini)).mkdir(exist_ok=True)
    (arsiv.gecici_dizin(arsiv_dizini) / "yarim.tmp").write_bytes(b"x")
    (arsiv_dizini / "notlar.txt").write_bytes(b"x")
    (arsiv_dizini / "ab").mkdir(exist_ok=True)
    (arsiv_dizini / "ab" / "kisa").write_bytes(b"x")

    tarama = arsiv.arsivi_tara(arsiv_dizini)

    assert set(tarama.adresli) == {sonuc.goreli_yol, _yol(PNG)}
    assert tarama.yarim == ("gecici/yarim.tmp",)
    assert set(tarama.taninmayan) == {"ab/kisa", "notlar.txt"}
    assert arsiv.arsivi_tara(arsiv_dizini / "yok") == arsiv.ArsivTaramasi((), (), ())


# --- dördüncü inceleme (2026-09-24): doğrulama ile açılış arasındaki yarış -----------


def test_dogrulama_ile_acilis_arasinda_yol_disari_baglantiya_donerse_reddedilir(
    tmp_path: Path, gelen: Path, arsiv_dizini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Doğrulama Path döndürüyor, açılış aynı yolu yeniden çözüyordu; arada yol
    dışarıdaki dosyaya simgesel bağlantıya çevrilince dışarıdaki baytlar
    arşivleniyordu. Şimdi açılan nesne tanıtıcı üzerinden yolla karşılaştırılır."""
    kaynak = _yaz(gelen / "belge.pdf", PDF + b"izinli icerik")
    disari = _yaz(tmp_path / "disari.pdf", PDF + b"disaridaki icerik")
    orijinal = arsiv._kaynagi_ac  # pyright: ignore[reportPrivateUsage]

    def degistir_sonra_ac(yol: Path) -> BinaryIO:
        if yol == kaynak:
            kaynak.unlink()
            _simgesel_baglanti(kaynak, disari)
        return orijinal(yol)

    monkeypatch.setattr(arsiv, "_kaynagi_ac", degistir_sonra_ac)

    with pytest.raises((arsiv.GelenDosyaGecersiz, arsiv.DosyaOkunamadi)):
        _arsivle(kaynak, gelen, arsiv_dizini)

    assert _dosyalar(arsiv_dizini) == set()
    assert _gecici_yok(arsiv_dizini)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows açık dosyanın yolunu değiştirmeye izin vermez; yarış orada kapalı",
)
def test_dogrulama_ile_acilis_arasinda_baska_dosya_gelirse_reddedilir(
    gelen: Path, arsiv_dizini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Açılan tanıtıcı ile yoldaki dosya aynı nesne değilse (açılıştan sonra yol
    başka dosyaya çevrildi) reddedilir; Windows'ta da çalışır (bağlantı yok)."""
    kaynak = _yaz(gelen / "belge.pdf", PDF + b"ilk")
    yedek = _yaz(gelen / "yedek.pdf", PDF + b"ikinci")
    orijinal = arsiv._kaynagi_ac  # pyright: ignore[reportPrivateUsage]

    def ac_sonra_degistir(yol: Path) -> BinaryIO:
        girdi = orijinal(yol)
        if yol == kaynak:
            os.replace(yedek, kaynak)  # açık dosyanın yolu başka dosyaya gider
        return girdi

    monkeypatch.setattr(arsiv, "_kaynagi_ac", ac_sonra_degistir)

    with pytest.raises(arsiv.GelenDosyaGecersiz, match="değişti"):
        _arsivle(kaynak, gelen, arsiv_dizini)

    assert _dosyalar(arsiv_dizini) == set()


def test_dogrulama_ile_acilis_arasinda_ust_dizin_junction_olursa_reddedilir(
    tmp_path: Path, gelen: Path, arsiv_dizini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows karşılığı: doğrulamadan sonra üst dizin dışarıya giden junction'a
    çevrilir; açılan dosya dışarıdaki dosyadır. Açılıştan sonra ara yollar
    yeniden denetlenir ve junction yakalanır (yetki gerektirmez)."""
    alt = gelen / "alt"
    kaynak = _yaz(alt / "belge.pdf", PDF + b"izinli icerik")
    disari = tmp_path / "disari"
    _yaz(disari / "belge.pdf", PDF + b"disaridaki icerik")
    orijinal = arsiv._kaynagi_ac  # pyright: ignore[reportPrivateUsage]

    def degistir_sonra_ac(yol: Path) -> BinaryIO:
        if yol == kaynak:
            alt.rename(gelen / "alt_eski")
            _junction(alt, disari)
        return orijinal(yol)

    monkeypatch.setattr(arsiv, "_kaynagi_ac", degistir_sonra_ac)

    with pytest.raises(arsiv.GelenDosyaGecersiz, match="junction"):
        _arsivle(kaynak, gelen, arsiv_dizini)

    assert _dosyalar(arsiv_dizini) == set()
    assert _gecici_yok(arsiv_dizini)
