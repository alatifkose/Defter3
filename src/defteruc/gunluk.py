from __future__ import annotations

import copy
import logging
import sys
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import IO

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

GUNLUK_ADI = "defteruc"
GUNLUK_DOSYA_ADI = "defteruc.log"
DOSYA_ISLEYICI_ADI = "defteruc.dosya"
KUTUPHANE_ISLEYICI_ADI = "defteruc.kutuphane"
HATA_TURU_BILINMIYOR = "bilinmiyor"
AZAMI_DOSYA_BOYUTU = 1_000_000
YEDEK_SAYISI = 5
KILIT_UZANTISI = ".lock"
KILIT_BEKLEME_SANIYESI = 0.002
SATIR_BICIMI = "%(asctime)s | %(levelname)s | %(olay)s | %(message)s"
OLAY_YOKSA = "-"

_YONLENDIRILEN_KUTUPHANELER: set[str] = set()


class GunlukKurulumHatasi(OSError): ...


class _OlayAlaniniTamamla(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.__dict__.setdefault("olay", OLAY_YOKSA)
        return True


class _KilitliDonduren(logging.Handler):
    def __init__(self, dosya: Path, azami_boyut: int, yedek_sayisi: int) -> None:
        super().__init__()
        self.dosya = dosya
        self.azami_boyut = azami_boyut
        self.yedek_sayisi = yedek_sayisi
        self._kilit: IO[bytes] = open(
            dosya.with_name(dosya.name + KILIT_UZANTISI), "a+b"
        )
        with open(dosya, "a", encoding="utf-8"):
            pass

    def emit(self, record: logging.LogRecord) -> None:
        try:
            satir = self.format(record) + "\n"
            self.acquire()
            try:
                self._surecler_arasi_kilitle()
                try:
                    self._gerekirse_dondur()
                    with open(self.dosya, "a", encoding="utf-8") as f:
                        f.write(satir)
                finally:
                    self._surecler_arasi_ac()
            finally:
                self.release()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        try:
            self._kilit.close()
        finally:
            super().close()

    def _gerekirse_dondur(self) -> None:
        if not self.dosya.exists() or self.dosya.stat().st_size < self.azami_boyut:
            return
        for i in range(self.yedek_sayisi - 1, 0, -1):
            kaynak = self._yedek(i)
            if kaynak.exists():
                kaynak.replace(self._yedek(i + 1))
        if self.yedek_sayisi > 0:
            self.dosya.replace(self._yedek(1))
        else:
            self.dosya.unlink()

    def _yedek(self, sira: int) -> Path:
        return self.dosya.with_name(f"{self.dosya.name}.{sira}")

    def _surecler_arasi_kilitle(self) -> None:
        if sys.platform == "win32":
            while True:
                try:
                    self._kilit.seek(0)
                    msvcrt.locking(self._kilit.fileno(), msvcrt.LK_NBLCK, 1)
                    return
                except OSError:
                    time.sleep(KILIT_BEKLEME_SANIYESI)
        else:
            fcntl.flock(self._kilit.fileno(), fcntl.LOCK_EX)

    def _surecler_arasi_ac(self) -> None:
        if sys.platform == "win32":
            self._kilit.seek(0)
            msvcrt.locking(self._kilit.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(self._kilit.fileno(), fcntl.LOCK_UN)


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
        isleyici = _KilitliDonduren(dosya, AZAMI_DOSYA_BOYUTU, YEDEK_SAYISI)
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
