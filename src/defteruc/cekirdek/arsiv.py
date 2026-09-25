from __future__ import annotations

import hashlib
import os
import re
import stat
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

AZAMI_DOSYA_BOYUTU = 50 * 1024 * 1024
OKUMA_PARCA_BOYUTU = 1024 * 1024
GECICI_DIZIN_ADI = "gecici"
GECICI_UZANTI = ".tmp"
AZAMI_UZANTI_UZUNLUGU = 10
VARSAYILAN_MIME = "application/octet-stream"

SHA256_BICIMI = re.compile(r"[0-9a-f]{64}")
GORELI_YOL_BICIMI = re.compile(r"([0-9a-f]{2})/([0-9a-f]{64})")

_IMZALAR: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)


class ArsivHatasi(Exception): ...


class GelenDosyaGecersiz(ArsivHatasi, ValueError): ...


class DosyaOkunamadi(ArsivHatasi): ...


class DosyaCokBuyuk(ArsivHatasi): ...


class ArsivYazilamadi(ArsivHatasi): ...


class ArsivDosyasiEksik(ArsivHatasi): ...


class ArsivButunlukHatasi(ArsivHatasi): ...


@dataclass(frozen=True, slots=True)
class ArsivlenenDosya:
    sha256: str
    boyut: int
    mime: str
    kaynak_uzantisi: str
    kaynak_adi: str
    goreli_yol: str
    diskte_zaten_vardi: bool


@dataclass(frozen=True, slots=True)
class ArsivTaramasi:
    adresli: tuple[str, ...]
    yarim: tuple[str, ...]
    taninmayan: tuple[str, ...]


# --- gelen dizini sınırı --------------------------------------------------------------


def gelen_dosyayi_dogrula(yol: str | Path, gelen_dizini: Path) -> Path:
    if not gelen_dizini.is_absolute():
        raise ValueError("gelen dizini mutlak bir yol olmalı.")
    metin = str(yol)
    if not metin.strip():
        raise GelenDosyaGecersiz("dosya yolu boş olamaz.")
    verilen = Path(metin)
    if not verilen.is_absolute():
        raise GelenDosyaGecersiz("dosya yolu mutlak olmalı; göreli yol kabul edilmez.")
    if ".." in verilen.parts:
        raise GelenDosyaGecersiz("dosya yolunda üst dizin parçası (..) olamaz.")

    sade = Path(os.path.normpath(verilen))
    gelen_sade = Path(os.path.normpath(gelen_dizini))
    if not _sozluksel_altinda(sade, gelen_sade):
        raise GelenDosyaGecersiz("dosya izinli gelen dizininin dışında.")

    try:
        os.lstat(sade)
    except FileNotFoundError:
        raise GelenDosyaGecersiz("dosya bulunamadı.") from None
    except OSError:
        raise DosyaOkunamadi("dosya yoluna erişilemedi.") from None

    _ara_yollari_denetle(sade, gelen_sade)
    return sade


def _ara_yollari_denetle(sade: Path, gelen_sade: Path) -> None:
    for ara in _inen_parcalar(sade, gelen_sade):
        if ara.is_symlink() or os.path.isjunction(ara):
            raise GelenDosyaGecersiz(
                "gelen dizini altında simgesel bağlantı ya da junction kabul edilmez."
            )

    try:
        fiziksel = sade.resolve(strict=True)
    except FileNotFoundError:
        raise GelenDosyaGecersiz("dosya bulunamadı.") from None
    except (OSError, RuntimeError):
        raise DosyaOkunamadi("dosya yolu çözülemedi.") from None
    if not fiziksel.is_relative_to(gelen_sade.resolve()):
        raise GelenDosyaGecersiz("dosyanın fiziksel yolu gelen dizininin dışında.")
    if not fiziksel.is_file():
        raise GelenDosyaGecersiz("yol sıradan bir dosya değil.")


def _sozluksel_altinda(yol: Path, dizin: Path) -> bool:
    y = Path(os.path.normcase(str(yol)))
    d = Path(os.path.normcase(str(dizin)))
    return y != d and y.is_relative_to(d)


def _inen_parcalar(yol: Path, dizin: Path) -> Iterator[Path]:
    parcalar = yol.parts[len(dizin.parts) :]
    simdiki = dizin
    for parca in parcalar:
        simdiki = simdiki / parca
        yield simdiki


# --- yol hesabı -----------------------------------------------------------------------


def arsiv_goreli_yolu(sha256: str) -> str:
    if not SHA256_BICIMI.fullmatch(sha256):
        raise ValueError("SHA-256 64 karakter küçük harf onaltılık olmalı.")
    return f"{sha256[:2]}/{sha256}"


def arsiv_yolu(arsiv_dizini: Path, goreli_yol: str) -> Path:
    eslesme = GORELI_YOL_BICIMI.fullmatch(goreli_yol)
    if eslesme is None or eslesme.group(1) != eslesme.group(2)[:2]:
        raise ValueError("arşiv göreli yolu <2hex>/<sha256> biçiminde olmalı.")
    return arsiv_dizini / eslesme.group(1) / eslesme.group(2)


def gecici_dizin(arsiv_dizini: Path) -> Path:
    return arsiv_dizini / GECICI_DIZIN_ADI


# --- özet ve bütünlük -----------------------------------------------------------------


KAYNAK_ACMA_BAYRAKLARI = (
    os.O_RDONLY
    | getattr(os, "O_BINARY", 0)
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)


def _kaynagi_ac(yol: Path) -> BinaryIO:
    return os.fdopen(os.open(yol, KAYNAK_ACMA_BAYRAKLARI), "rb")


def _acilani_dogrula(girdi: BinaryIO, yol: Path, gelen_sade: Path) -> None:
    try:
        acilan = os.fstat(girdi.fileno())
        yoldaki = os.lstat(yol)
    except OSError:
        raise DosyaOkunamadi("dosya okunamadı.") from None
    if not stat.S_ISREG(acilan.st_mode) or not stat.S_ISREG(yoldaki.st_mode):
        raise GelenDosyaGecersiz("yol sıradan bir dosya değil.")
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if getattr(yoldaki, "st_file_attributes", 0) & reparse:
        raise GelenDosyaGecersiz(
            "gelen dizini altında simgesel bağlantı ya da junction kabul edilmez."
        )
    if (acilan.st_dev, acilan.st_ino) != (yoldaki.st_dev, yoldaki.st_ino):
        raise GelenDosyaGecersiz("dosya doğrulama ile açılış arasında değişti.")
    _ara_yollari_denetle(yol, gelen_sade)


def _geciciyi_ac(yol: Path) -> BinaryIO:
    return yol.open("xb")


def _yerine_koy(gecici: Path, hedef: Path) -> None:
    os.rename(gecici, hedef)


def sha256_hesapla(yol: Path) -> tuple[str, int]:
    ozet = hashlib.sha256()
    boyut = 0
    try:
        with _kaynagi_ac(yol) as girdi:
            while parca := girdi.read(OKUMA_PARCA_BOYUTU):
                ozet.update(parca)
                boyut += len(parca)
    except OSError:
        raise DosyaOkunamadi("dosya okunamadı.") from None
    return ozet.hexdigest(), boyut


def arsiv_dosyasini_dogrula(
    arsiv_dizini: Path, goreli_yol: str, boyut: int, sha256: str | None = None
) -> Path:
    yol = arsiv_yolu(arsiv_dizini, goreli_yol)
    kisa = goreli_yol[3:15]
    try:
        bilgi = os.lstat(yol)
    except FileNotFoundError:
        raise ArsivDosyasiEksik(f"arşiv dosyası eksik: {kisa}…") from None
    except OSError:
        raise ArsivButunlukHatasi(f"arşiv dosyasına erişilemedi: {kisa}…") from None
    if not os.path.isfile(yol) or os.path.islink(yol) or os.path.isjunction(yol):
        raise ArsivButunlukHatasi(f"arşiv yolu sıradan dosya değil: {kisa}…")
    if bilgi.st_size != boyut:
        raise ArsivButunlukHatasi(
            f"arşiv dosyası boyutu beklenenden farklı: {kisa}… "
            f"({bilgi.st_size} ≠ {boyut})."
        )
    if sha256 is not None:
        try:
            gercek, gercek_boyut = sha256_hesapla(yol)
        except DosyaOkunamadi:
            raise ArsivButunlukHatasi(f"arşiv dosyası okunamadı: {kisa}…") from None
        if gercek != sha256 or gercek_boyut != boyut:
            raise ArsivButunlukHatasi(
                f"arşiv dosyası içeriği beklenen özeti taşımıyor: {kisa}…"
            )
    return yol


# --- arşivleme ------------------------------------------------------------------------


def dosyayi_arsivle(
    yol: str | Path,
    *,
    gelen_dizini: Path,
    arsiv_dizini: Path,
    azami_boyut: int = AZAMI_DOSYA_BOYUTU,
) -> ArsivlenenDosya:
    kaynak = gelen_dosyayi_dogrula(yol, gelen_dizini)
    uzanti = _uzanti(kaynak.name)
    try:
        if kaynak.stat().st_size > azami_boyut:
            raise DosyaCokBuyuk(_boyut_mesaji(azami_boyut))
    except OSError:
        raise DosyaOkunamadi("dosya okunamadı.") from None

    gecici = _gecici_ad(arsiv_dizini)
    gelen_sade = Path(os.path.normpath(gelen_dizini))
    try:
        ozet, boyut, mime = _akisla_kopyala(kaynak, gecici, azami_boyut, gelen_sade)
        goreli_yol = arsiv_goreli_yolu(ozet)
        hedef = arsiv_yolu(arsiv_dizini, goreli_yol)
        _dizini_hazirla(hedef.parent)
        zaten_vardi = _hedefe_tasi(gecici, arsiv_dizini, goreli_yol, ozet, boyut)
    finally:
        gecici.unlink(missing_ok=True)

    return ArsivlenenDosya(
        sha256=ozet,
        boyut=boyut,
        mime=mime,
        kaynak_uzantisi=uzanti,
        kaynak_adi=kaynak.name,
        goreli_yol=goreli_yol,
        diskte_zaten_vardi=zaten_vardi,
    )


def _gecici_ad(arsiv_dizini: Path) -> Path:
    dizin = gecici_dizin(arsiv_dizini)
    _dizini_hazirla(dizin)
    return dizin / f"{uuid.uuid4().hex}{GECICI_UZANTI}"


def _dizini_hazirla(dizin: Path) -> None:
    try:
        dizin.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise ArsivYazilamadi("arşiv dizini hazırlanamadı.") from None


def _akisla_kopyala(
    kaynak: Path, gecici: Path, azami_boyut: int, gelen_sade: Path
) -> tuple[str, int, str]:
    ozet = hashlib.sha256()
    boyut = 0
    try:
        girdi = _kaynagi_ac(kaynak)
    except OSError:
        raise DosyaOkunamadi("dosya okunamadı.") from None
    with girdi:
        _acilani_dogrula(girdi, kaynak, gelen_sade)
        try:
            parca = girdi.read(OKUMA_PARCA_BOYUTU)
        except OSError:
            raise DosyaOkunamadi("dosya okunamadı.") from None
        if not parca:
            raise GelenDosyaGecersiz("boş dosya belge olamaz.")
        mime = _mime_belirle(parca)
        try:
            with _geciciyi_ac(gecici) as cikti:
                while parca:
                    boyut += len(parca)
                    if boyut > azami_boyut:
                        raise DosyaCokBuyuk(_boyut_mesaji(azami_boyut))
                    ozet.update(parca)
                    cikti.write(parca)
                    parca = girdi.read(OKUMA_PARCA_BOYUTU)
                cikti.flush()
                os.fsync(cikti.fileno())
        except DosyaCokBuyuk:
            raise
        except OSError:
            raise ArsivYazilamadi("geçici arşiv dosyası yazılamadı.") from None
    return ozet.hexdigest(), boyut, mime


def _hedefe_tasi(
    gecici: Path, arsiv_dizini: Path, goreli_yol: str, ozet: str, boyut: int
) -> bool:
    hedef = arsiv_yolu(arsiv_dizini, goreli_yol)
    if hedef.exists() or hedef.is_symlink():
        arsiv_dosyasini_dogrula(arsiv_dizini, goreli_yol, boyut, ozet)
        return True
    try:
        _yerine_koy(gecici, hedef)
    except (PermissionError, FileExistsError):
        if hedef.exists():
            arsiv_dosyasini_dogrula(arsiv_dizini, goreli_yol, boyut, ozet)
            return True
        raise ArsivYazilamadi("arşiv dosyası hedefe taşınamadı.") from None
    except OSError:
        raise ArsivYazilamadi("arşiv dosyası hedefe taşınamadı.") from None
    _dizini_esle(hedef.parent)
    return False


def _dizini_esle(dizin: Path) -> None:
    if os.name == "nt":
        return
    try:
        fd = os.open(dizin, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _boyut_mesaji(azami_boyut: int) -> str:
    return f"dosya {azami_boyut} bayt sınırını aşıyor; kesilmez, reddedilir."


def _uzanti(ad: str) -> str:
    uzanti = Path(ad).suffix.lower()
    govde = uzanti[1:]
    if not govde or len(govde) > AZAMI_UZANTI_UZUNLUGU or not govde.isalnum():
        return ""
    return uzanti


def _mime_belirle(bas: bytes) -> str:
    for imza, mime in _IMZALAR:
        if bas.startswith(imza):
            return mime
    return VARSAYILAN_MIME


# --- tarama ---------------------------------------------------------------------------


def arsivi_tara(arsiv_dizini: Path) -> ArsivTaramasi:
    adresli: list[str] = []
    yarim: list[str] = []
    taninmayan: list[str] = []
    if not arsiv_dizini.is_dir():
        return ArsivTaramasi((), (), ())
    for dosya in sorted(arsiv_dizini.rglob("*")):
        if not dosya.is_file() and not dosya.is_symlink():
            continue
        goreli = dosya.relative_to(arsiv_dizini).as_posix()
        if goreli.startswith(f"{GECICI_DIZIN_ADI}/"):
            yarim.append(goreli)
            continue
        eslesme = GORELI_YOL_BICIMI.fullmatch(goreli)
        if eslesme is not None and eslesme.group(1) == eslesme.group(2)[:2]:
            adresli.append(goreli)
        else:
            taninmayan.append(goreli)
    return ArsivTaramasi(tuple(adresli), tuple(yarim), tuple(taninmayan))
