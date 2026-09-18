"""Çekirdek / finans bağımlılık sınırı (karar 2026-09-18).

``defteriki.cekirdek`` altındaki hiçbir kaynak dosya ``defteriki.finans``
paketine ya da alt modüllerine ne doğrudan ne de ``defteriki`` içindeki başka
bir modül üzerinden dolaylı olarak bağlanamaz. Denetim Python AST üzerinden
yapılır; metin araması değildir ve finansal kelime aramaz. Korunan şey
bağımlılık yönüdür: finans çekirdeği kullanabilir, çekirdek finansı asla.

Kapsam (yakalanan biçimler):

* ``import defteriki.finans[.x]`` (``as`` takma adıyla da), ``from
  defteriki.finans[.x] import y``, ``from defteriki import finans``;
* göreli import: ``from .. import finans``, ``from ..finans import x`` (derin
  paketlerde ``...``);
* metin hedefli dinamik import: ``importlib.import_module("defteriki.finans")``
  ve ``__import__(...)``; hedef ilk konumsal argüman ya da ``name=``;
  ``package=`` ile ya da dosyanın kendi paketine göre çözülen göreli hedef
  (``".finans"``); ``import importlib as il`` ve ``from importlib import
  import_module as im`` takma adları;
* fonksiyon gövdesi içindeki importlar;
* dolaylı bağımlılık: çekirdek modülünün ``defteriki`` içindeki statik import
  grafiği üzerinden (aynı biçimlerle) finansa ulaşması; zincir raporlanır.
  Python bir alt modülü yüklerken üst paketlerin ``__init__.py`` dosyalarını
  da çalıştırdığından bunlar grafiğe dahildir (``from defteriki.yardimci.alt
  import veri`` → ``defteriki/__init__`` ve ``defteriki/yardimci/__init__``
  de yüklenir); zincirde ``(üst paket, X yüklenirken)`` etiketiyle görünür.

Kapsam dışı (bilinçli sınır): çalışma anında kurulan metinler
(``import_module(ad)`` değişkenle), ``sys.modules`` erişimi, ``getattr``,
``exec``/``eval``, üçüncü taraf paketlerin içinden geçen yollar. Bunlar
statik denetimle çözülemez; kod incelemesinin konusudur.
"""

import ast
from collections import deque
from dataclasses import dataclass
from pathlib import Path

PROJE_KOKU = Path(__file__).resolve().parent.parent
KAYNAK_KOKU = PROJE_KOKU / "src"
CEKIRDEK_DIZINI = KAYNAK_KOKU / "defteriki" / "cekirdek"
FINANS_DIZINI = KAYNAK_KOKU / "defteriki" / "finans"

UYGULAMA_PAKETI = "defteriki"
YASAK_PAKET = "defteriki.finans"
DINAMIK_IMPORT_ADLARI = ("import_module", "__import__")


@dataclass(frozen=True, slots=True)
class Bagimlilik:
    hedef: str
    """Mutlak modül adı."""
    satir: int
    ifade: str
    """İnsan okunur import ifadesi."""


# --- ad çözümleme -------------------------------------------------------------


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
    """``from ..x import y`` ya da ``"..x"`` metnini mutlak modül adına çevirir."""
    govde = paket.split(".")
    if seviye > 1:
        govde = govde[: len(govde) - (seviye - 1)]
    taban = ".".join(govde)
    if modul:
        return f"{taban}.{modul}" if taban else modul
    return taban


def _yasak_mi(modul_adi: str) -> bool:
    return modul_adi == YASAK_PAKET or modul_adi.startswith(YASAK_PAKET + ".")


def _uygulama_ici_mi(modul_adi: str) -> bool:
    return modul_adi == UYGULAMA_PAKETI or modul_adi.startswith(UYGULAMA_PAKETI + ".")


# --- bir dosyanın bağımlılıkları ------------------------------------------------


def _metin_arg(dugum: ast.Call, konum: int, anahtar: str) -> str | None:
    """Çağrının ``konum``. konumsal ya da ``anahtar=`` argümanı, metin sabitiyse."""
    aday: ast.expr | None = None
    if len(dugum.args) > konum:
        aday = dugum.args[konum]
    else:
        for kw in dugum.keywords:
            if kw.arg == anahtar:
                aday = kw.value
    if isinstance(aday, ast.Constant) and isinstance(aday.value, str):
        return aday.value
    return None


def _dinamik_hedef(dugum: ast.Call, paket: str, dinamik_adlar: set[str]) -> str | None:
    """``import_module`` / ``__import__`` çağrısının mutlak hedefi; değilse ``None``."""
    islev = dugum.func
    if isinstance(islev, ast.Name):
        if islev.id not in dinamik_adlar:
            return None
    elif isinstance(islev, ast.Attribute):
        if islev.attr not in DINAMIK_IMPORT_ADLARI:
            return None
    else:
        return None
    ad = _metin_arg(dugum, 0, "name")
    if ad is None:
        return None
    if not ad.startswith("."):
        return ad
    seviye = len(ad) - len(ad.lstrip("."))
    govde = ad.lstrip(".") or None
    return _goreli_cozumle(_metin_arg(dugum, 1, "package") or paket, seviye, govde)


def bagimliliklar(dosya: Path, kaynak_koku: Path) -> list[Bagimlilik]:
    """Dosyanın statik ve metin hedefli dinamik importları, mutlak adlarla."""
    agac = ast.parse(dosya.read_text(encoding="utf-8"), filename=str(dosya))
    paket = _paket_adi(_modul_adi(dosya, kaynak_koku), dosya)

    dinamik_adlar = {"__import__"}
    for dugum in ast.walk(agac):
        if (
            isinstance(dugum, ast.ImportFrom)
            and dugum.level == 0
            and dugum.module == "importlib"
        ):
            for ad in dugum.names:
                if ad.name == "import_module":
                    dinamik_adlar.add(ad.asname or ad.name)

    sonuc: list[Bagimlilik] = []
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Import):
            for ad in dugum.names:
                sonuc.append(Bagimlilik(ad.name, dugum.lineno, f"import {ad.name}"))
        elif isinstance(dugum, ast.ImportFrom):
            kaynak = (
                _goreli_cozumle(paket, dugum.level, dugum.module)
                if dugum.level
                else (dugum.module or "")
            )
            adlar = ", ".join(ad.name for ad in dugum.names)
            ifade = f"from {'.' * dugum.level}{dugum.module or ''} import {adlar}"
            sonuc.append(Bagimlilik(kaynak, dugum.lineno, ifade))
            for ad in dugum.names:
                sonuc.append(Bagimlilik(f"{kaynak}.{ad.name}", dugum.lineno, ifade))
        elif isinstance(dugum, ast.Call):
            hedef = _dinamik_hedef(dugum, paket, dinamik_adlar)
            if hedef is not None:
                sonuc.append(
                    Bagimlilik(hedef, dugum.lineno, f"dinamik import {hedef!r}")
                )
    return sonuc


def yasak_importlar(dosya: Path, kaynak_koku: Path) -> list[str]:
    """Dosyadaki doğrudan ``defteriki.finans`` bağımlılıkları, ``satır: ifade``."""
    bulgular: list[str] = []
    for b in bagimliliklar(dosya, kaynak_koku):
        if _yasak_mi(b.hedef):
            metin = f"{b.satir}: {b.ifade}"
            if metin not in bulgular:
                bulgular.append(metin)
    return bulgular


def sinir_ihlalleri(cekirdek_dizini: Path, kaynak_koku: Path) -> dict[str, list[str]]:
    """Çekirdek ağacındaki her ``.py`` için doğrudan ihlal listesi."""
    ihlaller: dict[str, list[str]] = {}
    for dosya in sorted(cekirdek_dizini.rglob("*.py")):
        bulgular = yasak_importlar(dosya, kaynak_koku)
        if bulgular:
            ihlaller[dosya.relative_to(kaynak_koku).as_posix()] = bulgular
    return ihlaller


# --- dolaylı bağımlılık (statik import grafiği) ---------------------------------


def _modul_dosyalari(kaynak_koku: Path) -> dict[str, Path]:
    """``defteriki`` altındaki bütün modüller: ad → dosya."""
    return {
        _modul_adi(d, kaynak_koku): d
        for d in sorted((kaynak_koku / UYGULAMA_PAKETI).rglob("*.py"))
    }


def _yukleme_adimlari(hedef: str) -> list[tuple[str, str]]:
    """``hedef`` import edilince Python'un çalıştırdığı modüller: önce üst
    paketlerin ``__init__``'leri, sonra hedefin kendisi. (modül adı, zincirde
    gösterilecek etiket) çiftleri."""
    parcalar = hedef.split(".")
    adimlar: list[tuple[str, str]] = []
    for i in range(1, len(parcalar)):
        ust = ".".join(parcalar[:i])
        adimlar.append((ust, f"{ust} (üst paket, {hedef} yüklenirken)"))
    adimlar.append((hedef, hedef))
    return adimlar


def _finansa_giden_zincir(
    baslangic: str, dosyalar: dict[str, Path], kaynak_koku: Path
) -> list[str] | None:
    """En kısa ``baslangic → ... → defteriki.finans*`` zinciri; yoksa ``None``.

    Genişlik öncelikli tarama; her modül bir kez ziyaret edilir (döngüler
    bitirir). Bir hedef yüklenirken çalışacak üst paket ``__init__``'leri de
    düğüm olarak eklenir; zincirde ``(üst paket, X yüklenirken)`` etiketiyle
    görünür. Başlangıç modülünün kendi üst paketleri de dahildir.
    """
    kuyruk: deque[tuple[str, list[str]]] = deque()
    gorulen: set[str] = set()

    def ekle(hedef: str, yol: list[str]) -> None:
        for modul, etiket in _yukleme_adimlari(hedef):
            if modul in gorulen or modul not in dosyalar:
                continue
            gorulen.add(modul)
            kuyruk.append((modul, [*yol, etiket] if modul != baslangic else yol))

    ekle(baslangic, [baslangic])
    while kuyruk:
        modul, yol = kuyruk.popleft()
        for b in bagimliliklar(dosyalar[modul], kaynak_koku):
            if _yasak_mi(b.hedef):
                return [*yol, b.hedef]
            if _uygulama_ici_mi(b.hedef):
                ekle(b.hedef, yol)
    return None


def dolayli_ihlaller(cekirdek_dizini: Path, kaynak_koku: Path) -> dict[str, list[str]]:
    """Çekirdek dosyası → finansa giden en kısa modül zinciri (dolaylı dahil)."""
    dosyalar = _modul_dosyalari(kaynak_koku)
    ihlaller: dict[str, list[str]] = {}
    for dosya in sorted(cekirdek_dizini.rglob("*.py")):
        zincir = _finansa_giden_zincir(
            _modul_adi(dosya, kaynak_koku), dosyalar, kaynak_koku
        )
        if zincir:
            ihlaller[dosya.relative_to(kaynak_koku).as_posix()] = zincir
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


def test_cekirdek_finansa_dolayli_ulasmaz() -> None:
    ihlaller = dolayli_ihlaller(CEKIRDEK_DIZINI, KAYNAK_KOKU)

    mesaj = "\n".join(
        f"{dosya}: {' → '.join(zincir)}" for dosya, zincir in ihlaller.items()
    )
    assert ihlaller == {}, (
        "çekirdek, defteriki içindeki başka bir modül üzerinden finansa ulaşıyor "
        f"(karar 2026-09-18):\n{mesaj}"
    )


# --- denetleyicinin kendisi -----------------------------------------------------
# Çekirdek henüz boşken testin yeşil olması bir şey kanıtlamaz; denetleyicinin
# her yasak biçimi gerçekten yakaladığı sentetik bir ağaçta sınanır.


def _sentetik_agac(
    tmp_path: Path,
    icerik: str,
    yol: str = "cekirdek/a.py",
    ek_dosyalar: dict[str, str] | None = None,
) -> Path:
    kaynak = tmp_path / "src"
    for paket in ("defteriki", "defteriki/cekirdek", "defteriki/finans"):
        (kaynak / paket).mkdir(parents=True, exist_ok=True)
        (kaynak / paket / "__init__.py").write_text("", encoding="utf-8")
    for ek_yol, ek_icerik in {yol: icerik, **(ek_dosyalar or {})}.items():
        dosya = kaynak / "defteriki" / ek_yol
        dosya.parent.mkdir(parents=True, exist_ok=True)
        dosya.write_text(ek_icerik, encoding="utf-8")
    return kaynak


def _cekirdek(kok: Path) -> Path:
    return kok / "defteriki" / "cekirdek"


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
    "import importlib\nimportlib.import_module(name='defteriki.finans')\n",
    "import importlib\nimportlib.import_module('.finans', package='defteriki')\n",
    "import importlib\nimportlib.import_module('.finans', 'defteriki')\n",
    "import importlib\n"
    "importlib.import_module('..finans', package='defteriki.cekirdek')\n",
    "import importlib as il\nil.import_module('defteriki.finans')\n",
    "from importlib import import_module as im\nim('defteriki.finans')\n",
    "from importlib import import_module\nimport_module('defteriki.finans.hesap')\n",
    "__import__('defteriki.finans.hesap')\n",
    "__import__(name='defteriki.finans')\n",
    "def f():\n    from defteriki.finans import x\n    return x\n",
)


def test_denetleyici_her_yasak_bicimi_yakalar(tmp_path: Path) -> None:
    kacan: list[str] = []
    for sira, icerik in enumerate(YASAK_BICIMLER):
        kok = _sentetik_agac(tmp_path / str(sira), icerik)
        if not sinir_ihlalleri(_cekirdek(kok), kok):
            kacan.append(icerik)
    assert kacan == [], f"yakalanmayan yasak import biçimleri: {kacan}"


def test_denetleyici_alt_paketteki_goreli_importu_cozer(tmp_path: Path) -> None:
    kok = _sentetik_agac(
        tmp_path,
        "from ...finans import x\n",
        "cekirdek/alt/b.py",
        ek_dosyalar={"cekirdek/alt/__init__.py": ""},
    )

    assert list(sinir_ihlalleri(_cekirdek(kok), kok)) == ["defteriki/cekirdek/alt/b.py"]


def test_denetleyici_ihlali_dosya_ve_satirla_bildirir(tmp_path: Path) -> None:
    kok = _sentetik_agac(tmp_path, "import os\n\nfrom defteriki.finans import x\n")

    assert sinir_ihlalleri(_cekirdek(kok), kok) == {
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
    "import importlib\nimportlib.import_module('defteriki.cekirdek.x')\n",
    "import importlib\nimportlib.import_module('.finans')\n",  # kendi paketine göre
    # çalışma anı metni kapsam dışı (bilinçli sınır)
    "import importlib\nad = 'defteriki.finans'\nimportlib.import_module(ad)\n",
    "def import_module(ad):\n    return ad\nimport_module('defteriki.finans')\n",
)


def test_denetleyici_izinli_importlara_dokunmaz(tmp_path: Path) -> None:
    takilan: list[str] = []
    for sira, icerik in enumerate(IZINLI_BICIMLER):
        kok = _sentetik_agac(tmp_path / str(sira), icerik)
        if sinir_ihlalleri(_cekirdek(kok), kok) or dolayli_ihlaller(
            _cekirdek(kok), kok
        ):
            takilan.append(icerik)
    assert takilan == [], f"yanlış yakalanan izinli biçimler: {takilan}"


def test_finans_cekirdegi_kullanabilir(tmp_path: Path) -> None:
    """Ters yön denetlenmez: finans içindeki çekirdek importu ihlal değildir."""
    kok = _sentetik_agac(
        tmp_path, "from defteriki.cekirdek import x\n", "finans/hesap.py"
    )

    assert sinir_ihlalleri(_cekirdek(kok), kok) == {}
    assert dolayli_ihlaller(_cekirdek(kok), kok) == {}


def test_dolayli_bagimlilik_zincirle_yakalanir(tmp_path: Path) -> None:
    kok = _sentetik_agac(
        tmp_path,
        "from defteriki import yardimci\n",
        ek_dosyalar={
            "yardimci.py": "from defteriki import ara\n",
            "ara.py": "import importlib\nimportlib.import_module('defteriki.finans')\n",
        },
    )

    assert sinir_ihlalleri(_cekirdek(kok), kok) == {}  # doğrudan ihlal yok
    assert dolayli_ihlaller(_cekirdek(kok), kok) == {
        "defteriki/cekirdek/a.py": [
            "defteriki.cekirdek.a",
            "defteriki.yardimci",
            "defteriki.ara",
            "defteriki.finans",
        ]
    }


def test_ust_paket_initializer_uzerinden_finansa_ulasma_yakalanir(
    tmp_path: Path,
) -> None:
    """İnceleme örneği: alt modül temiz, üst paketin __init__'i finansı yüklüyor."""
    kok = _sentetik_agac(
        tmp_path,
        "from defteriki.yardimci.alt import veri\n",
        ek_dosyalar={
            "yardimci/__init__.py": "from defteriki import finans\n",
            "yardimci/alt.py": "veri = 1\n",
        },
    )

    assert sinir_ihlalleri(_cekirdek(kok), kok) == {}  # doğrudan ihlal yok
    assert dolayli_ihlaller(_cekirdek(kok), kok) == {
        "defteriki/cekirdek/a.py": [
            "defteriki.cekirdek.a",
            "defteriki.yardimci (üst paket, defteriki.yardimci.alt yüklenirken)",
            "defteriki.finans",
        ]
    }


def test_baslangic_modulunun_kendi_ust_paketi_de_denetlenir(tmp_path: Path) -> None:
    """defteriki/__init__ finansı yüklerse hiçbir çekirdek modülü onsuz yüklenemez."""
    kok = _sentetik_agac(
        tmp_path,
        "import os\n",
        ek_dosyalar={"__init__.py": "import defteriki.finans\n"},
    )

    assert dolayli_ihlaller(_cekirdek(kok), kok) == {
        "defteriki/cekirdek/__init__.py": [
            "defteriki.cekirdek",
            "defteriki (üst paket, defteriki.cekirdek yüklenirken)",
            "defteriki.finans",
        ],
        "defteriki/cekirdek/a.py": [
            "defteriki.cekirdek.a",
            "defteriki (üst paket, defteriki.cekirdek.a yüklenirken)",
            "defteriki.finans",
        ],
    }


def test_finansa_baglanmayan_ust_paket_izinli_kalir(tmp_path: Path) -> None:
    kok = _sentetik_agac(
        tmp_path,
        "from defteriki.yardimci.alt import veri\n",
        ek_dosyalar={
            "yardimci/__init__.py": "import os\nfrom . import alt\n",
            "yardimci/alt.py": "veri = 1\n",
        },
    )

    assert dolayli_ihlaller(_cekirdek(kok), kok) == {}


def test_dolayli_tarama_dongude_biter(tmp_path: Path) -> None:
    kok = _sentetik_agac(
        tmp_path,
        "from defteriki.yardimci.alt import veri\n",
        ek_dosyalar={
            "yardimci/__init__.py": "from defteriki import ara\n",
            "yardimci/alt.py": "from defteriki import yardimci\n",
            "ara.py": "from defteriki.yardimci import alt\n",  # ara ↔ yardimci döngüsü
        },
    )

    assert dolayli_ihlaller(_cekirdek(kok), kok) == {}


def test_dolayli_denetim_finansa_ulasmayan_yardimciyi_gecirir(tmp_path: Path) -> None:
    kok = _sentetik_agac(
        tmp_path,
        "from defteriki import yardimci\nfrom defteriki.cekirdek import b\n",
        ek_dosyalar={
            "yardimci.py": "import os\nfrom defteriki import ayarlar\n",
            "ayarlar.py": "from pathlib import Path\n",
            "cekirdek/b.py": "from . import a\n",  # çekirdek içi döngü sorun değil
        },
    )

    assert dolayli_ihlaller(_cekirdek(kok), kok) == {}
