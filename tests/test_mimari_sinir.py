"""Çekirdek / finans bağımlılık sınırı (karar 2026-09-18).

``defteriki.cekirdek`` altındaki hiçbir kaynak dosya ``defteriki.finans``
paketini ya da alt modüllerini import edemez. Denetim Python AST üzerinden
yapılır; metin araması değildir ve finansal kelime aramaz. Korunan şey
bağımlılık yönüdür: finans çekirdeği kullanabilir, çekirdek finansı asla.

Yakalanan biçimler: ``import defteriki.finans[.x]``, ``from defteriki.finans[.x]
import y``, çekirdek içinden göreli import (``from .. import finans``,
``from ..finans import x``), ``importlib.import_module("defteriki.finans...")``
ve ``__import__("defteriki.finans...")``.
"""

import ast
from pathlib import Path

PROJE_KOKU = Path(__file__).resolve().parent.parent
KAYNAK_KOKU = PROJE_KOKU / "src"
CEKIRDEK_DIZINI = KAYNAK_KOKU / "defteriki" / "cekirdek"
FINANS_DIZINI = KAYNAK_KOKU / "defteriki" / "finans"

YASAK_PAKET = "defteriki.finans"


def _modul_adi(dosya: Path, kaynak_koku: Path) -> str:
    """``src/defteriki/cekirdek/a/b.py`` → ``defteriki.cekirdek.a.b``."""
    parcalar = list(dosya.relative_to(kaynak_koku).with_suffix("").parts)
    if parcalar[-1] == "__init__":
        parcalar.pop()
    return ".".join(parcalar)


def _paket_adi(modul_adi: str, dosya: Path) -> str:
    """Göreli importların çözüldüğü paket: ``__init__`` için modülün kendisi."""
    if dosya.name == "__init__.py":
        return modul_adi
    return modul_adi.rpartition(".")[0]


def _goreli_cozumle(paket: str, seviye: int, modul: str | None) -> str:
    """``from ..x import y`` biçimini mutlak modül adına çevirir."""
    govde = paket.split(".")
    if seviye > 1:
        govde = govde[: len(govde) - (seviye - 1)]
    taban = ".".join(govde)
    if modul:
        return f"{taban}.{modul}" if taban else modul
    return taban


def _yasak_mi(modul_adi: str) -> bool:
    return modul_adi == YASAK_PAKET or modul_adi.startswith(YASAK_PAKET + ".")


def _cagri_hedefi(dugum: ast.Call) -> str | None:
    """``importlib.import_module("...")`` ya da ``__import__("...")`` ilk metni."""
    islev = dugum.func
    adi: str | None = None
    if isinstance(islev, ast.Name):
        adi = islev.id
    elif isinstance(islev, ast.Attribute):
        adi = islev.attr
    if adi not in ("import_module", "__import__"):
        return None
    if not dugum.args:
        return None
    ilk = dugum.args[0]
    if isinstance(ilk, ast.Constant) and isinstance(ilk.value, str):
        return ilk.value
    return None


def yasak_importlar(dosya: Path, kaynak_koku: Path) -> list[str]:
    """Dosyadaki ``defteriki.finans`` bağımlılıkları, ``satır: ifade`` biçiminde."""
    agac = ast.parse(dosya.read_text(encoding="utf-8"), filename=str(dosya))
    modul = _modul_adi(dosya, kaynak_koku)
    paket = _paket_adi(modul, dosya)
    bulgular: list[str] = []
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Import):
            for ad in dugum.names:
                if _yasak_mi(ad.name):
                    bulgular.append(f"{dugum.lineno}: import {ad.name}")
        elif isinstance(dugum, ast.ImportFrom):
            kaynak = (
                _goreli_cozumle(paket, dugum.level, dugum.module)
                if dugum.level
                else (dugum.module or "")
            )
            hedefler = [kaynak] + [f"{kaynak}.{ad.name}" for ad in dugum.names]
            if any(_yasak_mi(h) for h in hedefler):
                adlar = ", ".join(ad.name for ad in dugum.names)
                bulgular.append(
                    f"{dugum.lineno}: from {'.' * dugum.level}{dugum.module or ''} "
                    f"import {adlar}"
                )
        elif isinstance(dugum, ast.Call):
            hedef = _cagri_hedefi(dugum)
            if hedef is not None and _yasak_mi(hedef):
                bulgular.append(f"{dugum.lineno}: dinamik import {hedef!r}")
    return bulgular


def sinir_ihlalleri(cekirdek_dizini: Path, kaynak_koku: Path) -> dict[str, list[str]]:
    """Çekirdek ağacındaki her ``.py`` için ihlal listesi; temiz dosyalar yer almaz."""
    ihlaller: dict[str, list[str]] = {}
    for dosya in sorted(cekirdek_dizini.rglob("*.py")):
        bulgular = yasak_importlar(dosya, kaynak_koku)
        if bulgular:
            ihlaller[dosya.relative_to(kaynak_koku).as_posix()] = bulgular
    return ihlaller


# --- gerçek kaynak ağacı --------------------------------------------------------


def test_iki_paket_var() -> None:
    assert (CEKIRDEK_DIZINI / "__init__.py").is_file()
    assert (FINANS_DIZINI / "__init__.py").is_file()


def test_cekirdek_finansi_import_etmez() -> None:
    ihlaller = sinir_ihlalleri(CEKIRDEK_DIZINI, KAYNAK_KOKU)

    mesaj = "\n".join(
        f"{dosya}: {'; '.join(bulgular)}" for dosya, bulgular in ihlaller.items()
    )
    assert ihlaller == {}, (
        "çekirdek → finans bağımlılığı yasak (karar 2026-09-18); ihlal eden "
        f"çekirdek dosyaları:\n{mesaj}"
    )


# --- denetleyicinin kendisi -----------------------------------------------------
# Çekirdek henüz boşken testin yeşil olması bir şey kanıtlamaz; denetleyicinin
# her yasak biçimi gerçekten yakaladığı sentetik bir ağaçta sınanır.


def _sentetik_agac(tmp_path: Path, icerik: str, yol: str = "cekirdek/a.py") -> Path:
    kaynak = tmp_path / "src"
    for paket in ("defteriki", "defteriki/cekirdek", "defteriki/finans"):
        (kaynak / paket).mkdir(parents=True, exist_ok=True)
        (kaynak / paket / "__init__.py").write_text("", encoding="utf-8")
    dosya = kaynak / "defteriki" / yol
    dosya.parent.mkdir(parents=True, exist_ok=True)
    dosya.write_text(icerik, encoding="utf-8")
    return kaynak


YASAK_BICIMLER = (
    "import defteriki.finans\n",
    "import defteriki.finans.hesap\n",
    "import defteriki.finans as f\n",
    "from defteriki.finans import x\n",
    "from defteriki.finans.hesap import y\n",
    "from defteriki import finans\n",
    "from .. import finans\n",
    "from ..finans import x\n",
    "from ..finans.hesap import y\n",
    "import importlib\nimportlib.import_module('defteriki.finans')\n",
    "__import__('defteriki.finans.hesap')\n",
    "def f():\n    from defteriki.finans import x\n    return x\n",
)


def test_denetleyici_her_yasak_bicimi_yakalar(tmp_path: Path) -> None:
    kacan: list[str] = []
    for sira, icerik in enumerate(YASAK_BICIMLER):
        kok = _sentetik_agac(tmp_path / str(sira), icerik)
        if not sinir_ihlalleri(kok / "defteriki" / "cekirdek", kok):
            kacan.append(icerik)
    assert kacan == [], f"yakalanmayan yasak import biçimleri: {kacan}"


def test_denetleyici_alt_paketteki_goreli_importu_cozer(tmp_path: Path) -> None:
    kok = _sentetik_agac(tmp_path, "from ...finans import x\n", "cekirdek/alt/b.py")
    (kok / "defteriki" / "cekirdek" / "alt" / "__init__.py").write_text("")

    ihlaller = sinir_ihlalleri(kok / "defteriki" / "cekirdek", kok)

    assert list(ihlaller) == ["defteriki/cekirdek/alt/b.py"]


def test_denetleyici_ihlali_dosya_ve_satirla_bildirir(tmp_path: Path) -> None:
    kok = _sentetik_agac(tmp_path, "import os\n\nfrom defteriki.finans import x\n")

    ihlaller = sinir_ihlalleri(kok / "defteriki" / "cekirdek", kok)

    assert ihlaller == {
        "defteriki/cekirdek/a.py": ["3: from defteriki.finans import x"]
    }


IZINLI_BICIMLER = (
    "import os\nfrom pathlib import Path\n",
    "from defteriki import ayarlar\n",
    "from defteriki.cekirdek import x\n",
    "from . import x\n",
    "import defteriki.finansal_olmayan\n",  # ön ek benzerliği yasak değil
    "from defteriki.finanslar import x\n",
    "x = 'defteriki.finans'\n",  # düz metin import değildir
)


def test_denetleyici_izinli_importlara_dokunmaz(tmp_path: Path) -> None:
    takilan: list[str] = []
    for sira, icerik in enumerate(IZINLI_BICIMLER):
        kok = _sentetik_agac(tmp_path / str(sira), icerik)
        if sinir_ihlalleri(kok / "defteriki" / "cekirdek", kok):
            takilan.append(icerik)
    assert takilan == [], f"yanlış yakalanan izinli biçimler: {takilan}"


def test_finans_cekirdegi_kullanabilir(tmp_path: Path) -> None:
    """Ters yön denetlenmez: finans içindeki çekirdek importu ihlal değildir."""
    kok = _sentetik_agac(
        tmp_path, "from defteriki.cekirdek import x\n", "finans/hesap.py"
    )

    assert sinir_ihlalleri(kok / "defteriki" / "cekirdek", kok) == {}
