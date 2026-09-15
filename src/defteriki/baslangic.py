"""DEFTERIKI uygulama başlangıcı.

``uv run defteriki`` bu modülün ``main`` fonksiyonunu çalıştırır. Sıra:

1. ``ayarlari_yukle()`` ile ayarlar ortam değişkenlerinden okunur.
2. ``dizinleri_hazirla()`` ile seçilen ortamın dizinleri açılır.
3. ``gunlugu_kur()`` ile teknik günlük log dizininde kurulur.
4. Başlangıç olayı günlüğe yazılır, kısa bir mesajla sıfır çıkış kodu döner.

Herhangi bir adım başarısızsa anlaşılır bir hata stderr'e yazılır ve çıkış
kodu 1 olur. Ayarlar ya da günlük kurulmadan oluşan hatalar da stderr'e
gider; günlük kurulamadıysa başarılı başlangıç mesajı verilmez.

İlk üç adım ``ortami_hazirla()`` içindedir; MCP kapısı da aynı işlevle
başlar, böylece iki giriş noktası aynı ayarları ve aynı günlüğü kullanır.

Modül import edildiğinde dizin ya da dosya oluşturulmaz.
"""

from __future__ import annotations

import sys
from pathlib import Path

from defteriki import gunluk
from defteriki.ayarlar import (
    AyarHatasi,
    Ayarlar,
    DizinHazirlamaHatasi,
    ayarlari_yukle,
    dizinleri_hazirla,
)

OLAY_BASLANGIC = "baslangic"
OLAY_BASLANGIC_HATASI = "baslangic_hatasi"

CIKIS_BASARILI = 0
CIKIS_HATALI = 1


class BaslangicHatasi(Exception):
    """Ayarlar, dizinler ya da günlük hazırlanamadı.

    Mesajı kullanıcıya gösterilmeye uygundur; hangi adımın düştüğünü söyler.
    """


def main() -> int:
    """Uygulamayı başlatır; çıkış kodunu döndürür."""
    try:
        return _baslat()
    except Exception as hata:
        _hata_yaz(f"Beklenmeyen hata ({type(hata).__name__}): {hata}")
        if gunluk.kurulu():
            gunluk.hata_kaydet(OLAY_BASLANGIC_HATASI, hata)
        return CIKIS_HATALI


def ortami_hazirla() -> tuple[Ayarlar, Path]:
    """Ayarları yükler, dizinleri açar, günlüğü kurar.

    Başarıda ayarları ve log dosyasının yolunu döndürür. Bir adım düşerse
    ``BaslangicHatasi`` yükseltir; günlük kurulmamış kalır.
    """
    try:
        ayarlar = ayarlari_yukle()
    except AyarHatasi as hata:
        raise BaslangicHatasi(f"Ayar hatası: {hata}") from hata

    try:
        dizinleri_hazirla(ayarlar)
    except DizinHazirlamaHatasi as hata:
        raise BaslangicHatasi(f"Dizin hazırlama hatası: {hata}") from hata

    try:
        log_dosyasi = gunluk.gunlugu_kur(ayarlar.log_dizini)
    except gunluk.GunlukKurulumHatasi as hata:
        raise BaslangicHatasi(f"Günlük kurulum hatası: {hata}") from hata

    return ayarlar, log_dosyasi


def _baslat() -> int:
    try:
        ayarlar, log_dosyasi = ortami_hazirla()
    except BaslangicHatasi as hata:
        _hata_yaz(str(hata))
        return CIKIS_HATALI

    gunluk.olay_kaydet(
        OLAY_BASLANGIC, f"ortam={ayarlar.ortam.value} veri_koku={ayarlar.veri_koku}"
    )
    _basariyi_bildir(ayarlar, log_dosyasi)
    return CIKIS_BASARILI


def _basariyi_bildir(ayarlar: Ayarlar, log_dosyasi: Path) -> None:
    print(
        f"DEFTERIKI başlatıldı. Ortam: {ayarlar.ortam.value}. "
        f"Veri kökü: {ayarlar.veri_koku}. Günlük: {log_dosyasi}",
        flush=True,
    )


def _hata_yaz(mesaj: str) -> None:
    print(f"DEFTERIKI başlatılamadı. {mesaj}", file=sys.stderr, flush=True)
