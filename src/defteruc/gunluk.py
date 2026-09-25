from __future__ import annotations

import copy
import logging
from collections.abc import Iterable, Mapping
from logging.handlers import RotatingFileHandler
from pathlib import Path

GUNLUK_ADI = "defteruc"
GUNLUK_DOSYA_ADI = "defteruc.log"
DOSYA_ISLEYICI_ADI = "defteruc.dosya"
KUTUPHANE_ISLEYICI_ADI = "defteruc.kutuphane"
HATA_TURU_BILINMIYOR = "bilinmiyor"
AZAMI_DOSYA_BOYUTU = 1_000_000
YEDEK_SAYISI = 5
SATIR_BICIMI = "%(asctime)s | %(levelname)s | %(olay)s | %(message)s"
OLAY_YOKSA = "-"

_YONLENDIRILEN_KUTUPHANELER: set[str] = set()


class GunlukKurulumHatasi(OSError): ...


class _OlayAlaniniTamamla(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.__dict__.setdefault("olay", OLAY_YOKSA)
        return True


class _KutuphaneIsleyicisi(logging.Handler):
    def __init__(self, dosya_isleyicisi: logging.Handler) -> None:
        super().__init__()
        self._dosya = dosya_isleyicisi

    def emit(self, record: logging.LogRecord) -> None:
        self._dosya.handle(_guvenli_kopya(record))


def _guvenli_kopya(record: logging.LogRecord) -> logging.LogRecord:
    kopya = copy.copy(record)
    if record.exc_info is not None or record.exc_text is not None or record.stack_info:
        tur = record.exc_info[0] if record.exc_info else None
        tur_adi = HATA_TURU_BILINMIYOR
        if tur is not None:
            tur_adi = _tur_adi(tur)
        kopya.msg = f"hata türü: {tur_adi}"
        kopya.args = ()
        kopya.exc_info = None
        kopya.exc_text = None
        kopya.stack_info = None
        return kopya
    mesaj: object = record.msg
    if not isinstance(mesaj, str):
        kopya.msg = f"[mesaj gizlendi: {_tur_adi(type(mesaj))}]"
        kopya.args = ()
        return kopya
    if record.args:
        degerler: Iterable[object] = (
            record.args.values() if isinstance(record.args, Mapping) else record.args
        )
        turler = ", ".join(type(d).__name__ for d in degerler)
        kopya.msg = f"{mesaj} [parametreler gizlendi: {turler}]"
        kopya.args = ()
    return kopya


def _tur_adi(tur: type) -> str:
    return f"{tur.__module__}.{tur.__qualname__}"


def gunlugu_kur(log_dizini: Path) -> Path:
    if not log_dizini.is_dir():
        raise GunlukKurulumHatasi(f"Log dizini yok ya da dizin değil: {log_dizini}")
    dosya = log_dizini / GUNLUK_DOSYA_ADI

    gunluk = logging.getLogger(GUNLUK_ADI)
    gunlugu_kapat()
    try:
        isleyici = RotatingFileHandler(
            dosya,
            maxBytes=AZAMI_DOSYA_BOYUTU,
            backupCount=YEDEK_SAYISI,
            encoding="utf-8",
        )
    except OSError as hata:
        raise GunlukKurulumHatasi(
            f"Log dosyası açılamadı: {dosya} ({hata.strerror or type(hata).__name__})"
        ) from hata
    isleyici.set_name(DOSYA_ISLEYICI_ADI)
    isleyici.setFormatter(logging.Formatter(SATIR_BICIMI))
    isleyici.addFilter(_OlayAlaniniTamamla())
    gunluk.addHandler(isleyici)
    gunluk.setLevel(logging.INFO)
    gunluk.propagate = False
    return dosya


def gunlugu_kapat() -> None:
    for ad in _YONLENDIRILEN_KUTUPHANELER:
        kutuphane = logging.getLogger(ad)
        for isleyici in list(kutuphane.handlers):
            if isleyici.get_name() in (KUTUPHANE_ISLEYICI_ADI, DOSYA_ISLEYICI_ADI):
                kutuphane.removeHandler(isleyici)
        kutuphane.propagate = True
    _YONLENDIRILEN_KUTUPHANELER.clear()

    gunluk = logging.getLogger(GUNLUK_ADI)
    for isleyici in list(gunluk.handlers):
        if isleyici.get_name() == DOSYA_ISLEYICI_ADI:
            gunluk.removeHandler(isleyici)
            isleyici.close()


def kurulu() -> bool:
    return _dosya_isleyicisi() is not None


def kutuphane_gunlugunu_yonlendir(ad: str) -> None:
    isleyici = _dosya_isleyicisi()
    if isleyici is None:
        raise GunlukKurulumHatasi(
            "Dosya günlüğü kurulu değil; önce gunlugu_kur() çağrılmalı."
        )
    kutuphane = logging.getLogger(ad)
    if not any(i.get_name() == KUTUPHANE_ISLEYICI_ADI for i in kutuphane.handlers):
        sarmalayici = _KutuphaneIsleyicisi(isleyici)
        sarmalayici.set_name(KUTUPHANE_ISLEYICI_ADI)
        kutuphane.addHandler(sarmalayici)
    kutuphane.setLevel(logging.INFO)
    kutuphane.propagate = False
    _YONLENDIRILEN_KUTUPHANELER.add(ad)


def _dosya_isleyicisi() -> logging.Handler | None:
    gunluk = logging.getLogger(GUNLUK_ADI)
    for isleyici in gunluk.handlers:
        if isleyici.get_name() == DOSYA_ISLEYICI_ADI:
            return isleyici
    return None


def olay_kaydet(olay: str, mesaj: str, seviye: int = logging.INFO) -> None:
    logging.getLogger(GUNLUK_ADI).log(seviye, mesaj, extra={"olay": olay})


def hata_kaydet(olay: str, hata: BaseException) -> None:
    tur = type(hata)
    olay_kaydet(olay, f"hata türü: {tur.__module__}.{tur.__qualname__}", logging.ERROR)
