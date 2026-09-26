from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from defteruc import gunluk, komutlar
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


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return _calistir(argv)
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


def _ayristirici() -> argparse.ArgumentParser:
    ayristirici = argparse.ArgumentParser(
        prog="defteruc", description="DEFTERUC kişisel finans kayıt sistemi"
    )
    komut = ayristirici.add_subparsers(dest="komut")
    komut.add_parser(
        komutlar.KOMUT_BEKLEYENLER, help="bekleyen yapı isteklerini göster"
    )
    komut.add_parser(komutlar.KOMUT_PENCERE, help="onay penceresini aç")
    for ad, aciklama in (
        (komutlar.KOMUT_ONAYLA, "bekleyen yapı isteğini onayla ve uygula"),
        (komutlar.KOMUT_REDDET, "bekleyen yapı isteğini reddet"),
    ):
        alt = komut.add_parser(ad, help=aciklama)
        alt.add_argument("kimlik", type=int, help="talep kimliği")
        if ad == komutlar.KOMUT_ONAYLA:
            alt.add_argument(
                "--onizleme",
                required=True,
                help="bekleyenler çıktısında gösterilen önizleme kodu",
            )
    return ayristirici


def _calistir(argv: Sequence[str] | None) -> int:
    secenekler = _ayristirici().parse_args(argv)
    try:
        ayarlar, log_dosyasi = ortami_hazirla()
    except BaslangicHatasi as hata:
        _hata_yaz(str(hata))
        return CIKIS_HATALI

    match secenekler.komut:
        case komutlar.KOMUT_BEKLEYENLER:
            return komutlar.bekleyenleri_goster(ayarlar)
        case komutlar.KOMUT_ONAYLA:
            return komutlar.onayla(
                ayarlar,
                int(secenekler.kimlik),
                gorulen_onizleme=secenekler.onizleme,
            )
        case komutlar.KOMUT_REDDET:
            return komutlar.reddet(ayarlar, int(secenekler.kimlik))
        case komutlar.KOMUT_PENCERE:
            return komutlar.pencere(ayarlar)
        case _:
            return _baslat(ayarlar, log_dosyasi)


def _baslat(ayarlar: Ayarlar, log_dosyasi: Path) -> int:
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
