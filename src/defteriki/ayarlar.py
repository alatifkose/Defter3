"""DEFTERIKI merkezi ayar yönetimi.

Çalışma ortamı, veri kökü, veritabanı dosyası, belge arşivi, log dizini ve
gelen dizini yalnızca buradan belirlenir. Yollar uygulamanın nereden başlatıldığına
bağlı değildir; çalışma dizinine göre çözümleme yapılmaz.

Modül import edildiğinde hiçbir ortam değişkeni okunmaz ve diske yazılmaz.
Ayarlar ``ayarlari_yukle()`` ile açıkça yüklenir; gerekli dizinler ayrıca
``dizinleri_hazirla()`` ile açıkça oluşturulur.

Öncelik sırası (yüksekten düşüğe):

1. ``DEFTERIKI_VERITABANI_YOLU``, ``DEFTERIKI_BELGE_DIZINI``,
   ``DEFTERIKI_LOG_DIZINI``, ``DEFTERIKI_GELEN_DIZINI``: verilmişse ilgili
   türetilmiş yolun yerine geçer. Gelen dizini, Cowork'un belge dosyalarını
   bıraktığı ve MCP araçlarının okumaya izinli olduğu tek dizindir. Bu
   tekil yollar ortam ayrımını geçersiz kılabilir; yani ``gelistirme``
   ortamında çalışırken bu değişkenlerle ``gercek`` ortamının dosyalarına
   işaret edilebilir. Tek istisna ``test`` ortamıdır: orada tekil yolların
   test veri kökünün dışına çıkması reddedilir. Bu sınır yolun yazılı
   biçimine değil fiziksel karşılığına bakar (``Path.resolve``): kök
   içindeki bir simgesel bağlantı ya da junction dışarıyı gösteriyorsa yol
   reddedilir ve hiçbir dizin oluşturulmaz. Diğer ortamların yol politikası
   değişmez.
2. ``DEFTERIKI_VERI_KOKU``: ortamların ortak üst dizini. Seçilen ortamın
   adı bunun altına eklenir (``<kök>/<ortam>``), türetilmiş yollar bu
   ortam kökünden üretilir.
3. Platform varsayılanı: Windows'ta ``%LOCALAPPDATA%\\DEFTERIKI``,
   macOS'ta ``~/Library/Application Support/DEFTERIKI``, diğer
   sistemlerde ``$XDG_DATA_HOME/DEFTERIKI`` ya da
   ``~/.local/share/DEFTERIKI``. ``test`` ortamında platform varsayılanına
   düşülmez; ``DEFTERIKI_VERI_KOKU`` zorunludur.

``DEFTERIKI_ORTAM`` verilmezse ``gelistirme`` kullanılır. Bilinmeyen ya da
boş ortam değeri, boş ya da göreli yol değeri açık hatayla reddedilir.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

UYGULAMA_DIZIN_ADI = "DEFTERIKI"
VERITABANI_DOSYA_ADI = "defteriki.sqlite3"
BELGE_DIZIN_ADI = "belgeler"
LOG_DIZIN_ADI = "logs"
GELEN_DIZIN_ADI = "gelen"

ORTAM_DEGISKENI = "DEFTERIKI_ORTAM"
VERI_KOKU_DEGISKENI = "DEFTERIKI_VERI_KOKU"
VERITABANI_YOLU_DEGISKENI = "DEFTERIKI_VERITABANI_YOLU"
BELGE_DIZINI_DEGISKENI = "DEFTERIKI_BELGE_DIZINI"
LOG_DIZINI_DEGISKENI = "DEFTERIKI_LOG_DIZINI"
GELEN_DIZINI_DEGISKENI = "DEFTERIKI_GELEN_DIZINI"


class Ortam(StrEnum):
    GELISTIRME = "gelistirme"
    TEST = "test"
    GERCEK = "gercek"


class AyarHatasi(ValueError):
    """Ortam değişkenlerinden geçerli bir ayar üretilemedi."""


class DizinHazirlamaHatasi(OSError):
    """Bir ayar dizini oluşturulamadı ya da kullanılamaz durumda."""


@dataclass(frozen=True, slots=True)
class Ayarlar:
    ortam: Ortam
    veri_koku: Path
    """Seçilen ortama ait kök: ``<ortak kök>/<ortam>``."""
    veritabani_yolu: Path
    belge_dizini: Path
    log_dizini: Path
    gelen_dizini: Path
    """Cowork'un dosya bıraktığı, MCP araçlarının okumaya izinli olduğu dizin."""

    def gerekli_dizinler(self) -> tuple[Path, ...]:
        """Uygulamanın çalışabilmesi için var olması gereken dizinler."""
        return (
            self.veritabani_yolu.parent,
            self.belge_dizini,
            self.log_dizini,
            self.gelen_dizini,
        )


def ayarlari_yukle() -> Ayarlar:
    """Ortam değişkenlerinden ayarları üretir. Diske hiçbir şey yazmaz."""
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
    """Gerekli dizinleri oluşturur. Tekrar çağrılabilir.

    Veritabanı ya da log dosyası oluşturmaz; yalnızca dizinleri hazırlar.
    Hata durumunda hangi yolda ne olduğunu bildiren
    ``DizinHazirlamaHatasi`` yükseltir.
    """
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
    """Yolun fiziksel karşılığı: var olan simgesel bağlantı ve junction'lar
    çözülür, var olmayan kuyruk olduğu gibi kalır. Diske yazmaz."""
    return yol.resolve()


def _yol_oku(degisken: str) -> Path | None:
    """Ortam değişkeninden mutlak yol okur; tanımsızsa None döner.

    Mutlak yollardaki ``..`` parçaları sözlüksel olarak sadeleştirilir;
    bu işlem çalışma dizinine bakmaz.
    """
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
