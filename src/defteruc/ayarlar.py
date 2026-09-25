from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

UYGULAMA_DIZIN_ADI = "DEFTERUC"
VERITABANI_DOSYA_ADI = "defteruc.sqlite3"
BELGE_DIZIN_ADI = "belgeler"
LOG_DIZIN_ADI = "logs"
GELEN_DIZIN_ADI = "gelen"

ORTAM_DEGISKENI = "DEFTERUC_ORTAM"
VERI_KOKU_DEGISKENI = "DEFTERUC_VERI_KOKU"
VERITABANI_YOLU_DEGISKENI = "DEFTERUC_VERITABANI_YOLU"
BELGE_DIZINI_DEGISKENI = "DEFTERUC_BELGE_DIZINI"
LOG_DIZINI_DEGISKENI = "DEFTERUC_LOG_DIZINI"
GELEN_DIZINI_DEGISKENI = "DEFTERUC_GELEN_DIZINI"


class Ortam(StrEnum):
    GELISTIRME = "gelistirme"
    TEST = "test"
    GERCEK = "gercek"


class AyarHatasi(ValueError): ...


class DizinHazirlamaHatasi(OSError): ...


@dataclass(frozen=True, slots=True)
class Ayarlar:
    ortam: Ortam
    veri_koku: Path
    veritabani_yolu: Path
    belge_dizini: Path
    log_dizini: Path
    gelen_dizini: Path

    def gerekli_dizinler(self) -> tuple[Path, ...]:
        return (
            self.veritabani_yolu.parent,
            self.belge_dizini,
            self.log_dizini,
            self.gelen_dizini,
        )


def ayarlari_yukle() -> Ayarlar:
    ortam = _ortami_oku()
    veri_koku = _ortak_koku_belirle(ortam) / ortam.value

    veritabani_yolu = (
        _yol_oku(VERITABANI_YOLU_DEGISKENI) or veri_koku / VERITABANI_DOSYA_ADI
    )
    belge_dizini = _yol_oku(BELGE_DIZINI_DEGISKENI) or veri_koku / BELGE_DIZIN_ADI
    log_dizini = _yol_oku(LOG_DIZINI_DEGISKENI) or veri_koku / LOG_DIZIN_ADI
    gelen_dizini = _yol_oku(GELEN_DIZINI_DEGISKENI) or veri_koku / GELEN_DIZIN_ADI

    if ortam is Ortam.TEST:
        kok_fiziksel = _fiziksel_yol(veri_koku)
        for degisken, yol in (
            (VERITABANI_YOLU_DEGISKENI, veritabani_yolu),
            (BELGE_DIZINI_DEGISKENI, belge_dizini),
            (LOG_DIZINI_DEGISKENI, log_dizini),
            (GELEN_DIZINI_DEGISKENI, gelen_dizini),
        ):
            yol_fiziksel = _fiziksel_yol(yol)
            if not yol_fiziksel.is_relative_to(kok_fiziksel):
                ayrinti = str(yol)
                if yol_fiziksel != yol:
                    ayrinti += f" (fiziksel karşılığı {yol_fiziksel})"
                raise AyarHatasi(
                    f"{degisken} test ortamında test veri kökünün dışına çıkamaz: "
                    f"{ayrinti} kökün ({veri_koku}) altında değil."
                )

    return Ayarlar(
        ortam=ortam,
        veri_koku=veri_koku,
        veritabani_yolu=veritabani_yolu,
        belge_dizini=belge_dizini,
        log_dizini=log_dizini,
        gelen_dizini=gelen_dizini,
    )


def dizinleri_hazirla(ayarlar: Ayarlar) -> None:
    for dizin in ayarlar.gerekli_dizinler():
        try:
            dizin.mkdir(parents=True, exist_ok=True)
        except FileExistsError as hata:
            raise DizinHazirlamaHatasi(
                f"Dizin oluşturulamadı, yol zaten bir dosya: {dizin}"
            ) from hata
        except OSError as hata:
            raise DizinHazirlamaHatasi(
                f"Dizin oluşturulamadı: {dizin} ({hata.strerror or hata})"
            ) from hata
        if not dizin.is_dir():
            raise DizinHazirlamaHatasi(f"Yol bir dizin değil: {dizin}")


def _ortami_oku() -> Ortam:
    if ORTAM_DEGISKENI not in os.environ:
        return Ortam.GELISTIRME
    deger = os.environ[ORTAM_DEGISKENI].strip()
    gecerli = ", ".join(o.value for o in Ortam)
    if not deger:
        raise AyarHatasi(f"{ORTAM_DEGISKENI} boş olamaz; geçerli değerler: {gecerli}.")
    try:
        return Ortam(deger)
    except ValueError:
        raise AyarHatasi(
            f"{ORTAM_DEGISKENI} bilinmeyen değer: {deger!r}; "
            f"geçerli değerler: {gecerli}."
        ) from None


def _ortak_koku_belirle(ortam: Ortam) -> Path:
    verilen = _yol_oku(VERI_KOKU_DEGISKENI)
    if verilen is not None:
        return verilen
    if ortam is Ortam.TEST:
        raise AyarHatasi(
            f"test ortamı için {VERI_KOKU_DEGISKENI} açıkça verilmelidir; "
            "kullanıcı veri dizinine düşülmez."
        )
    return _platform_veri_koku()


def _platform_veri_koku() -> Path:
    if sys.platform == "win32":
        deger = os.environ.get("LOCALAPPDATA", "").strip()
        if not deger:
            raise AyarHatasi(
                "Windows'ta varsayılan veri kökü için LOCALAPPDATA gerekli "
                f"ama tanımlı değil; {VERI_KOKU_DEGISKENI} ile açıkça verin."
            )
        taban = Path(deger)
        if not taban.is_absolute():
            raise AyarHatasi(f"LOCALAPPDATA mutlak bir yol değil: {deger!r}")
        return taban / UYGULAMA_DIZIN_ADI

    try:
        ev = Path.home()
    except RuntimeError as hata:
        raise AyarHatasi(
            "Kullanıcı ev dizini belirlenemedi; "
            f"{VERI_KOKU_DEGISKENI} ile açıkça verin."
        ) from hata

    if sys.platform == "darwin":
        return ev / "Library" / "Application Support" / UYGULAMA_DIZIN_ADI

    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg and Path(xdg).is_absolute():
        return Path(xdg) / UYGULAMA_DIZIN_ADI
    return ev / ".local" / "share" / UYGULAMA_DIZIN_ADI


def _fiziksel_yol(yol: Path) -> Path:
    return yol.resolve()


def _yol_oku(degisken: str) -> Path | None:
    if degisken not in os.environ:
        return None
    deger = os.environ[degisken]
    if not deger.strip():
        raise AyarHatasi(f"{degisken} boş olamaz.")
    yol = Path(deger)
    if not yol.is_absolute():
        raise AyarHatasi(
            f"{degisken} mutlak bir yol olmalı, göreli yol kabul edilmez: {deger!r}"
        )
    return Path(os.path.normpath(yol))
