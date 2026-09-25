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
"""Bayt; aşılınca dosya döndürülür."""
YEDEK_SAYISI = 5
"""Döndürülmüş eski dosyalardan en fazla kaç tanesinin tutulacağı."""
SATIR_BICIMI = "%(asctime)s | %(levelname)s | %(olay)s | %(message)s"
OLAY_YOKSA = "-"

_YONLENDIRILEN_KUTUPHANELER: set[str] = set()
"""Dosya günlüğüne bağlanmış dış kütüphane logger adları; kapatmada çözülür."""


class GunlukKurulumHatasi(OSError):
    """Log dosyası açılamadı ya da log dizini kullanılamaz durumda."""


class _OlayAlaniniTamamla(logging.Filter):
    """Olay türü verilmeden yazılan kayıtlara varsayılan olay değeri koyar."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.__dict__.setdefault("olay", OLAY_YOKSA)
        return True


class _KutuphaneIsleyicisi(logging.Handler):
    """Dış kütüphane kayıtlarını dosya handler'ına gizlilik kuralıyla iletir.

    İstisna taşıyan kayıtta mesaj ``hata türü: <modül.ad>`` olur; ``exc_info``,
    ``exc_text`` ve ``stack_info`` atılır. Parametreli kayıtta yalnız şablon
    kalır, değerler yerine türleri yazılır. Metin olmayan mesaj türüyle
    yazılır. Kayıt kopyalanır: logger'ın diğer handler'larına giden asıl
    ``LogRecord`` değişmez.
    """

    def __init__(self, dosya_isleyicisi: logging.Handler) -> None:
        super().__init__()
        self._dosya = dosya_isleyicisi

    def emit(self, record: logging.LogRecord) -> None:
        self._dosya.handle(_guvenli_kopya(record))


def _guvenli_kopya(record: logging.LogRecord) -> logging.LogRecord:
    """Kütüphane kaydının dosyaya gidecek kopyası; asıl kayıt değişmez."""
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
    """``hata_kaydet`` ile aynı biçim: ``modül.ad`` (``builtins.ValueError``)."""
    return f"{tur.__module__}.{tur.__qualname__}"


def gunlugu_kur(log_dizini: Path) -> Path:
    """Dosya günlüğünü kurar; log dosyasının yolunu döndürür.

    Tekrar çağrılabilir: önceki kurulumun handler'ı kapatılıp kaldırılır,
    böylece aynı olay birden fazla kez yazılmaz. Log dizini yoksa ya da
    dosya açılamazsa ``GunlukKurulumHatasi`` yükseltir.
    """
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
    """Bu modülün kurduğu dosya handler'ını kapatır ve kaldırır.

    Yönlendirilmiş kütüphane günlükleri de çözülür: handler kaldırılır,
    yayılım (propagate) eski hâline döner.
    """
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
    """Dosya günlüğü şu an kurulu mu?"""
    return _dosya_isleyicisi() is not None


def kutuphane_gunlugunu_yonlendir(ad: str) -> None:
    """Bir dış kütüphanenin günlüğünü DEFTERUC dosya günlüğüne bağlar.

    ``ad`` adlı logger (ve altındakiler) aynı dosyaya aynı satır biçimiyle
    yazar; kök logger'a yayılmaz, dolayısıyla stderr'e düşmez. Olay türü
    olmadığından olay sütunu ``-`` olur. İstisna taşıyan kayıtlar yalnız hata
    türüyle yazılır (``_KutuphaneIsleyicisi``). Dosya günlüğü kurulu değilse
    ``GunlukKurulumHatasi`` yükseltir.
    """
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
    """Kontrollü bir teknik olayı yazar.

    ``mesaj`` çağıranın kendi yazdığı kısa teknik bilgidir; belge ya da
    kayıt içeriği, kimlik bilgisi ya da ortam değişkeni geçirilmemelidir.
    """
    logging.getLogger(GUNLUK_ADI).log(seviye, mesaj, extra={"olay": olay})


def hata_kaydet(olay: str, hata: BaseException) -> None:
    """Bir hatayı yalnızca türüyle kaydeder.

    Hata mesajı ve traceback bilerek yazılmaz: bunlar dosya adı, belge
    içeriği ya da kimlik bilgisi taşıyabilir.
    """
    tur = type(hata)
    olay_kaydet(olay, f"hata türü: {tur.__module__}.{tur.__qualname__}", logging.ERROR)
