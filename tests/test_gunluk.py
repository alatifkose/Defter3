"""Teknik hata günlüğü testleri.

Log dosyaları yalnızca tmp_path altında açılır. Her testten sonra handler
kapatılır; böylece handler birikmez ve Windows'ta geçici dosya kilitli
kalmaz.
"""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from defteriki import gunluk


@pytest.fixture(autouse=True)
def gunlugu_temizle() -> Iterator[None]:
    gunluk.gunlugu_kapat()
    yield
    gunluk.gunlugu_kapat()


@pytest.fixture
def log_dizini(tmp_path: Path) -> Path:
    dizin = tmp_path / "logs"
    dizin.mkdir()
    return dizin


def _satirlar(dosya: Path) -> list[str]:
    return dosya.read_text(encoding="utf-8").splitlines()


def _dosya_isleyicileri() -> list[logging.Handler]:
    """Bu modülün kurduğu handler'lar; pytest'in kendi yakalayıcıları sayılmaz."""
    return [
        isleyici
        for isleyici in logging.getLogger(gunluk.GUNLUK_ADI).handlers
        if isleyici.get_name() == gunluk.DOSYA_ISLEYICI_ADI
    ]


def test_import_dosya_olusturmaz(log_dizini: Path) -> None:
    assert not gunluk.kurulu()
    assert list(log_dizini.iterdir()) == []


def test_kurulum_log_dizininde_dosya_acar(log_dizini: Path) -> None:
    dosya = gunluk.gunlugu_kur(log_dizini)

    assert dosya == log_dizini / gunluk.GUNLUK_DOSYA_ADI
    assert dosya.is_file()
    assert gunluk.kurulu()


def test_olay_satirinda_zaman_seviye_ve_olay_turu_bulunur(log_dizini: Path) -> None:
    dosya = gunluk.gunlugu_kur(log_dizini)

    gunluk.olay_kaydet("baslangic", "ortam=test")

    (satir,) = _satirlar(dosya)
    zaman, seviye, olay, mesaj = (parca.strip() for parca in satir.split("|"))
    assert zaman[:4].isdigit() and ":" in zaman
    assert seviye == "INFO"
    assert olay == "baslangic"
    assert mesaj == "ortam=test"


def test_tekrar_kurulum_mukerrer_satir_uretmez(log_dizini: Path) -> None:
    gunluk.gunlugu_kur(log_dizini)
    gunluk.gunlugu_kur(log_dizini)
    dosya = gunluk.gunlugu_kur(log_dizini)

    gunluk.olay_kaydet("baslangic", "tek olay")

    assert len(_dosya_isleyicileri()) == 1
    satirlar = _satirlar(dosya)
    assert len(satirlar) == 1
    assert "tek olay" in satirlar[0]


def test_gunluk_kok_logger_a_yayilmaz(log_dizini: Path) -> None:
    gunluk.gunlugu_kur(log_dizini)

    assert logging.getLogger(gunluk.GUNLUK_ADI).propagate is False


def test_hata_kaydi_yalniz_hata_turunu_tasir(log_dizini: Path) -> None:
    dosya = gunluk.gunlugu_kur(log_dizini)
    hassas = "IBAN TR00 0000 0000 0000 0000 0000 00 KISI ALFA sifre=gizli123"

    try:
        raise ValueError(hassas)
    except ValueError as hata:
        gunluk.hata_kaydet("baslangic_hatasi", hata)

    icerik = dosya.read_text(encoding="utf-8")
    assert "ERROR" in icerik
    assert "baslangic_hatasi" in icerik
    assert "builtins.ValueError" in icerik
    for parca in ("TR00", "KISI ALFA", "gizli123", "IBAN", "Traceback"):
        assert parca not in icerik


def test_olay_turu_verilmeyen_kayit_varsayilan_olayla_yazilir(
    log_dizini: Path,
) -> None:
    dosya = gunluk.gunlugu_kur(log_dizini)

    logging.getLogger(gunluk.GUNLUK_ADI).warning("olaysız uyarı")

    (satir,) = _satirlar(dosya)
    assert f"| WARNING | {gunluk.OLAY_YOKSA} | olaysız uyarı" in satir


def test_boyut_siniri_asilinca_dondurulur_ve_yedek_sayisi_sinirlidir(
    log_dizini: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gunluk, "AZAMI_DOSYA_BOYUTU", 200)
    monkeypatch.setattr(gunluk, "YEDEK_SAYISI", 2)
    dosya = gunluk.gunlugu_kur(log_dizini)

    for i in range(200):
        gunluk.olay_kaydet("deneme", f"satır {i} " + "x" * 50)

    dosyalar = sorted(yol.name for yol in log_dizini.iterdir())
    assert dosyalar == [dosya.name, f"{dosya.name}.1", f"{dosya.name}.2"]
    assert all((log_dizini / ad).stat().st_size <= 300 for ad in dosyalar)


def test_log_dizini_yoksa_acik_hata(tmp_path: Path) -> None:
    with pytest.raises(gunluk.GunlukKurulumHatasi, match="Log dizini yok"):
        gunluk.gunlugu_kur(tmp_path / "yok")

    assert not gunluk.kurulu()


def test_dosya_acilamazsa_acik_hata(log_dizini: Path) -> None:
    (log_dizini / gunluk.GUNLUK_DOSYA_ADI).mkdir()

    with pytest.raises(gunluk.GunlukKurulumHatasi, match="Log dosyası açılamadı"):
        gunluk.gunlugu_kur(log_dizini)

    assert not gunluk.kurulu()


def test_kapatma_handler_i_kaldirir(log_dizini: Path) -> None:
    gunluk.gunlugu_kur(log_dizini)

    gunluk.gunlugu_kapat()

    assert not gunluk.kurulu()
    assert _dosya_isleyicileri() == []


# --- kütüphane günlüğü yönlendirme -----------------------------------------


def test_kutuphane_gunlugu_ayni_dosyaya_yazilir_ve_yayilmaz(log_dizini: Path) -> None:
    dosya = gunluk.gunlugu_kur(log_dizini)

    gunluk.kutuphane_gunlugunu_yonlendir("deneme_kutuphane")
    logging.getLogger("deneme_kutuphane.alt").warning("kütüphane uyarısı")

    (satir,) = _satirlar(dosya)
    assert f"| WARNING | {gunluk.OLAY_YOKSA} | kütüphane uyarısı" in satir
    assert logging.getLogger("deneme_kutuphane").propagate is False


def test_kapatma_kutuphane_yonlendirmesini_cozer(log_dizini: Path) -> None:
    gunluk.gunlugu_kur(log_dizini)
    gunluk.kutuphane_gunlugunu_yonlendir("deneme_kutuphane")

    gunluk.gunlugu_kapat()

    kutuphane = logging.getLogger("deneme_kutuphane")
    assert kutuphane.handlers == []
    assert kutuphane.propagate is True


def test_yonlendirme_gunluk_kurulu_degilse_hata() -> None:
    with pytest.raises(gunluk.GunlukKurulumHatasi, match="kurulu değil"):
        gunluk.kutuphane_gunlugunu_yonlendir("deneme_kutuphane")


GIZLI_METIN = "SENTETIK-GIZLI IBAN TR00 0000 0000 0000 0000 00"


class _KayitYakalayici(logging.Handler):
    """Aynı logger'a bağlı ikinci handler; gördüğü kayıt nesnelerini saklar."""

    def __init__(self) -> None:
        super().__init__()
        self.kayitlar: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.kayitlar.append(record)


def test_kutuphane_istisnasi_yalniz_hata_turuyle_yazilir(log_dizini: Path) -> None:
    dosya = gunluk.gunlugu_kur(log_dizini)
    gunluk.kutuphane_gunlugunu_yonlendir("deneme_kutuphane")

    try:
        raise ValueError(GIZLI_METIN)
    except ValueError:
        logging.getLogger("deneme_kutuphane.alt").exception("kütüphane hata %s", "ek")

    (satir,) = _satirlar(dosya)
    assert f"| ERROR | {gunluk.OLAY_YOKSA} | hata türü: builtins.ValueError" in satir
    icerik = dosya.read_text(encoding="utf-8")
    assert GIZLI_METIN not in icerik
    assert "Traceback" not in icerik
    assert "kütüphane hata" not in icerik


def test_kutuphane_sabit_uyarisi_oldugu_gibi_yazilir(log_dizini: Path) -> None:
    dosya = gunluk.gunlugu_kur(log_dizini)
    gunluk.kutuphane_gunlugunu_yonlendir("deneme_kutuphane")

    logging.getLogger("deneme_kutuphane").warning("stdio bağlantısı kapandı")

    (satir,) = _satirlar(dosya)
    assert "| WARNING | - | stdio bağlantısı kapandı" in satir


def test_kutuphane_parametreli_kaydin_degerleri_gizlenir(log_dizini: Path) -> None:
    """SDK'nın beklenen hata yolu: istisnasız INFO, hata metni parametrede."""
    dosya = gunluk.gunlugu_kur(log_dizini)
    gunluk.kutuphane_gunlugunu_yonlendir("deneme_kutuphane")

    logging.getLogger("deneme_kutuphane").info(
        "Tool %r failed: %r", "sistem_durumu", GIZLI_METIN
    )
    logging.getLogger("deneme_kutuphane").info(
        "Processing request of type %s (%d)", "CallToolRequest", 3
    )

    ilk, ikinci = _satirlar(dosya)
    assert "| INFO | - | Tool %r failed: %r [parametreler gizlendi: str, str]" in ilk
    assert "[parametreler gizlendi: str, int]" in ikinci
    icerik = dosya.read_text(encoding="utf-8")
    assert GIZLI_METIN not in icerik
    assert "sistem_durumu" not in icerik
    assert "CallToolRequest" not in icerik


def test_kutuphane_metin_olmayan_mesaj_turuyle_yazilir(log_dizini: Path) -> None:
    dosya = gunluk.gunlugu_kur(log_dizini)
    gunluk.kutuphane_gunlugunu_yonlendir("deneme_kutuphane")

    logging.getLogger("deneme_kutuphane").warning(ValueError(GIZLI_METIN))

    (satir,) = _satirlar(dosya)
    assert "| WARNING | - | [mesaj gizlendi: builtins.ValueError]" in satir
    assert GIZLI_METIN not in satir


def test_kutuphane_suzgeci_ortak_kaydi_degistirmez(log_dizini: Path) -> None:
    gunluk.gunlugu_kur(log_dizini)
    gunluk.kutuphane_gunlugunu_yonlendir("deneme_kutuphane")
    yakalayici = _KayitYakalayici()
    kutuphane = logging.getLogger("deneme_kutuphane")
    kutuphane.addHandler(yakalayici)
    try:
        try:
            raise ValueError(GIZLI_METIN)
        except ValueError:
            kutuphane.exception("kütüphane hata")
    finally:
        kutuphane.removeHandler(yakalayici)

    (kayit,) = yakalayici.kayitlar
    assert kayit.msg == "kütüphane hata"
    assert kayit.exc_info is not None and kayit.exc_info[0] is ValueError
    assert "olay" not in kayit.__dict__


def test_kutuphane_parametre_suzgeci_ortak_kaydi_degistirmez(log_dizini: Path) -> None:
    gunluk.gunlugu_kur(log_dizini)
    gunluk.kutuphane_gunlugunu_yonlendir("deneme_kutuphane")
    yakalayici = _KayitYakalayici()
    kutuphane = logging.getLogger("deneme_kutuphane")
    kutuphane.addHandler(yakalayici)
    try:
        kutuphane.info("Tool %r failed: %r", "sistem_durumu", GIZLI_METIN)
    finally:
        kutuphane.removeHandler(yakalayici)

    (kayit,) = yakalayici.kayitlar
    assert kayit.msg == "Tool %r failed: %r"
    assert kayit.args == ("sistem_durumu", GIZLI_METIN)
    assert kayit.getMessage() == f"Tool 'sistem_durumu' failed: {GIZLI_METIN!r}"
