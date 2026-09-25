from __future__ import annotations

import sys
from pathlib import Path

from defteruc import gunluk
from defteruc.ayarlar import (
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


class BaslangicHatasi(Exception): ...


def main() -> int:
    try:
        return _baslat()
    except Exception as hata:
        _hata_yaz(f"Beklenmeyen hata ({type(hata).__name__}): {hata}")
        if gunluk.kurulu():
            gunluk.hata_kaydet(OLAY_BASLANGIC_HATASI, hata)
        return CIKIS_HATALI


def ortami_hazirla() -> tuple[Ayarlar, Path]:
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
        f"DEFTERUC başlatıldı. Ortam: {ayarlar.ortam.value}. "
        f"Veri kökü: {ayarlar.veri_koku}. Günlük: {log_dosyasi}",
        flush=True,
    )


def _hata_yaz(mesaj: str) -> None:
    print(f"DEFTERUC başlatılamadı. {mesaj}", file=sys.stderr, flush=True)
