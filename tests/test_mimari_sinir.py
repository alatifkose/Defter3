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

İkinci denetim (Aşama 4.2): çekirdek ağacı ve göç dosyaları finansal **ad**
taşıyamaz. Tanımlayıcılar ve metin sabitleri parçalara ayrılır, yasak ad tam
parça olarak aranır (``YASAK_FINANS_ADLARI``); docstring ve yorum denetim
dışıdır. Ayrıntı dosyanın sonundaki bölümde.

Üçüncü denetim (Aşama 4.5): taslak (aday) dünyası ile kesin nesne dünyası
kaynak kodunda da ayrıdır. ``taslak_islemleri`` / ``taslak_tablolari`` kesin
nesne tablolarını ve nesne motorunu import etmez (taslak veri kesin tablolara
yazılamaz); ``nesne_islemleri`` / ``nesne_tablolari`` taslak modüllerini
import etmez (kesin sorgular taslakları göremez). Ayrıntı dosyanın sonunda.
"""

import ast
import re
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


# --- finansal ad denetimi (Aşama 4.2) -----------------------------------------
# Bağımlılık yönü tek başına yetmez: çekirdek finansı import etmeden de
# ``BANKA = "BANKA"`` ya da ``class HesapHareketi`` yazarak finansal anlam
# taşıyabilir. Bu denetim çekirdek kaynak ağacında ve göç dosyalarında Python
# AST'sinden tanımlayıcıları (ad, sınıf, fonksiyon, parametre, nitelik, anahtar
# argüman, import adı) ve metin sabitlerini okur, her birini parçalara ayırır
# (``HesapHareketi`` → HESAP, HAREKETI; ``para_birimi`` → PARA, BIRIMI; Türkçe
# harfler ASCII'ye indirgenir) ve yasak adı **tam parça** olarak arar. Böylece
# ``hesapla`` ya da ``kartela`` yakalanmaz, ``hesap_kodu`` ve ``kart_limiti``
# yakalanır. Belge metinleri (docstring ve nitelik açıklamaları: tek başına
# duran metin ifadeleri) ve yorumlar denetlenmez; sınır anlatılabilir, ad ve
# veri değeri olarak taşınamaz.

GOC_DIZINI = PROJE_KOKU / "alembic" / "versions"

YASAK_FINANS_ADLARI: tuple[str, ...] = (
    "BANKA",
    "HESAP",
    "KART",
    "KREDI",
    "KMH",
    "PARA_BIRIMI",
    "VARLIK",
    "BORC",
    "GIDER",
    "BAKIYE",
)
"""Çekirdekte tanımlayıcı ya da metin sabiti olarak geçemeyecek finansal adlar.
Çok parçalı ad (``PARA_BIRIMI``) ardışık parçalar olarak aranır."""

_TURKCE_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
_AD_PARCASI = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")
_YASAK_PARCA_DIZILERI = tuple(tuple(ad.split("_")) for ad in YASAK_FINANS_ADLARI)


def ad_parcalari(metin: str) -> list[str]:
    """``HesapHareketi`` → ``["HESAP", "HAREKETI"]``, ``para_birimi`` →
    ``["PARA", "BIRIMI"]``; Türkçe harfler ASCII'ye indirgenir, büyük harf."""
    return [p.upper() for p in _AD_PARCASI.findall(metin.translate(_TURKCE_ASCII))]


def yasak_finans_adi(metin: str) -> str | None:
    """Metindeki ilk yasak finansal ad (tam parça eşleşmesi); yoksa ``None``."""
    parcalar = ad_parcalari(metin)
    for dizi in _YASAK_PARCA_DIZILERI:
        n = len(dizi)
        for i in range(len(parcalar) - n + 1):
            if tuple(parcalar[i : i + n]) == dizi:
                return "_".join(dizi)
    return None


def _belge_metinleri(agac: ast.AST) -> set[int]:
    """Tek başına duran metin ifadeleri (docstring, nitelik açıklaması) — düğüm
    kimlikleri; bunlar denetim dışıdır."""
    return {
        id(dugum.value)
        for dugum in ast.walk(agac)
        if isinstance(dugum, ast.Expr)
        and isinstance(dugum.value, ast.Constant)
        and isinstance(dugum.value.value, str)
    }


def finansal_adlar(dosya: Path) -> list[str]:
    """Dosyadaki yasak finansal adlar: ``satır: tür 'metin' (YASAK_AD)``."""
    agac = ast.parse(dosya.read_text(encoding="utf-8"), filename=str(dosya))
    belge = _belge_metinleri(agac)
    bulgular: list[str] = []

    def kaydet(metin: str, satir: int, tur: str) -> None:
        yasak = yasak_finans_adi(metin)
        if yasak is None:
            return
        bulgu = f"{satir}: {tur} {metin!r} ({yasak})"
        if bulgu not in bulgular:
            bulgular.append(bulgu)

    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Name):
            kaydet(dugum.id, dugum.lineno, "ad")
        elif isinstance(dugum, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            kaydet(dugum.name, dugum.lineno, "tanım")
        elif isinstance(dugum, ast.arg):
            kaydet(dugum.arg, dugum.lineno, "parametre")
        elif isinstance(dugum, ast.Attribute):
            kaydet(dugum.attr, dugum.lineno, "nitelik")
        elif isinstance(dugum, ast.keyword) and dugum.arg is not None:
            kaydet(dugum.arg, dugum.lineno, "anahtar")
        elif isinstance(dugum, ast.alias):
            kaydet(dugum.asname or dugum.name, dugum.lineno, "import")
        elif isinstance(dugum, ast.ImportFrom) and dugum.module:
            kaydet(dugum.module, dugum.lineno, "import")
        elif (
            isinstance(dugum, ast.Constant)
            and isinstance(dugum.value, str)
            and id(dugum) not in belge
        ):
            kaydet(dugum.value, dugum.lineno, "metin")
    return bulgular


def finansal_ad_ihlalleri(*dizinler: Path) -> dict[str, list[str]]:
    """Verilen ağaçlardaki her ``.py`` için bulgu listesi (proje köküne göre yol)."""
    ihlaller: dict[str, list[str]] = {}
    for dizin in dizinler:
        for dosya in sorted(dizin.rglob("*.py")):
            bulgular = finansal_adlar(dosya)
            if bulgular:
                ihlaller[dosya.relative_to(PROJE_KOKU).as_posix()] = bulgular
    return ihlaller


def test_cekirdek_ve_gocler_finansal_ad_tasimaz() -> None:
    ihlaller = finansal_ad_ihlalleri(CEKIRDEK_DIZINI, GOC_DIZINI)

    mesaj = "\n".join(
        f"{dosya}: {'; '.join(bulgular)}" for dosya, bulgular in ihlaller.items()
    )
    assert ihlaller == {}, (
        "çekirdek kaynak kodu ve göçler finansal ad taşıyamaz (Aşama 4.2 denetimi); "
        f"finansal anlam tanım verisine yazılır:\n{mesaj}"
    )


YASAK_ADLI_BICIMLER: tuple[tuple[str, str], ...] = (
    ('BANKA = "x"\n', "BANKA"),
    ("class HesapHareketi:\n    pass\n", "HESAP"),
    ("def bakiye_hesapla(x):\n    return x\n", "BAKIYE"),
    ('KURUM_TURLERI = ("TEST", "KART")\n', "KART"),
    ('x = {"para_birimi": 1}\n', "PARA_BIRIMI"),
    ("ParaBirimi = 1\n", "PARA_BIRIMI"),
    ("from enum import Enum\n\nclass Eksen(Enum):\n    VARLIK = 1\n", "VARLIK"),
    ("def f(kredi_id):\n    return kredi_id\n", "KREDI"),
    ("def f(n):\n    n.kmh_limiti = 1\n", "KMH"),
    ("def f(**k):\n    pass\n\nf(borc=1)\n", "BORC"),
    ("from defteriki.yardimci import gider_topla\n", "GIDER"),
    ("import defteriki.yardimci as banka_yardimcisi\n", "BANKA"),
    ('def f(x):\n    return f"hesap {x}"\n', "HESAP"),
    ('def f():\n    raise ValueError("para birimi geçersiz")\n', "PARA_BIRIMI"),
    ("BAKİYE = 1\n", "BAKIYE"),  # Türkçe harf ASCII'ye indirgenir
    ("def f():\n    return dict(hesap_no=1)\n", "HESAP"),
)


def test_ad_denetleyicisi_her_yasak_bicimi_yakalar(tmp_path: Path) -> None:
    kacan: list[str] = []
    for sira, (icerik, beklenen) in enumerate(YASAK_ADLI_BICIMLER):
        dosya = tmp_path / f"y{sira}.py"
        dosya.write_text(icerik, encoding="utf-8")
        bulgular = finansal_adlar(dosya)
        if not any(b.endswith(f"({beklenen})") for b in bulgular):
            kacan.append(f"{icerik!r} → {bulgular}")
    assert kacan == [], "yakalanmayan yasak adlar:\n" + "\n".join(kacan)


IZINLI_ADLI_BICIMLER: tuple[str, ...] = (
    "def hesapla(x):\n    return x\n",  # 'hesapla' ≠ 'hesap' (tam parça)
    "kartela = 1\nborclu = 2\nbankalar = 3\nkmhler = 4\n",  # ön ek eşleşmesi yetmez
    '"""Bu modül banka, hesap ve kart bilmez."""\n',  # modül docstring
    'KOD = 1\n"""Kart ya da banka kodu değil; nötr kimlik."""\n',  # nitelik açıklaması
    'class A:\n    """hesap"""\n\n    def f(self):\n        """banka"""\n',
    "# banka hesap kart\nx = 1\n",  # yorumlar AST'de yok
    'x = "tanım paketi bulunamadı: kimlik 3"\n',
    "from sqlalchemy import Integer, String\nfrom pathlib import Path\n",
    "def f(kaynak_nesne_turu_id, hedef_nesne_turu_id):\n    return 0\n",
    'x = "kredibilite"\n',  # 'kredibilite' ≠ 'kredi'
)


def test_ad_denetleyicisi_izinli_bicimlere_dokunmaz(tmp_path: Path) -> None:
    takilan: list[str] = []
    for sira, icerik in enumerate(IZINLI_ADLI_BICIMLER):
        dosya = tmp_path / f"i{sira}.py"
        dosya.write_text(icerik, encoding="utf-8")
        bulgular = finansal_adlar(dosya)
        if bulgular:
            takilan.append(f"{icerik!r} → {bulgular}")
    assert takilan == [], "yanlış yakalanan izinli biçimler:\n" + "\n".join(takilan)


def test_ad_denetleyicisi_ihlali_dosya_ve_satirla_bildirir(tmp_path: Path) -> None:
    kok = tmp_path / "src" / "defteriki" / "cekirdek"
    kok.mkdir(parents=True)
    (kok / "a.py").write_text('import os\n\nTURLER = ("BANKA",)\n', encoding="utf-8")
    (kok / "b.py").write_text("x = 1\n", encoding="utf-8")

    ihlaller = {
        dosya: bulgular
        for dosya, bulgular in (
            (d.name, finansal_adlar(d)) for d in sorted(kok.glob("*.py"))
        )
        if bulgular
    }

    assert ihlaller == {"a.py": ["3: metin 'BANKA' (BANKA)"]}


def test_ad_parcalama_kurali() -> None:
    assert ad_parcalari("HesapHareketi") == ["HESAP", "HAREKETI"]
    assert ad_parcalari("para_birimi") == ["PARA", "BIRIMI"]
    assert ad_parcalari("PARA_BIRIMI") == ["PARA", "BIRIMI"]
    assert ad_parcalari("KMHLimiti") == ["KMH", "LIMITI"]
    assert ad_parcalari("bakıye_öz") == ["BAKIYE", "OZ"]
    assert ad_parcalari("tanım paketi bulunamadı: kimlik 3") == [
        "TANIM",
        "PAKETI",
        "BULUNAMADI",
        "KIMLIK",
        "3",
    ]
    assert yasak_finans_adi("hesapla") is None
    assert yasak_finans_adi("hesap_kodu") == "HESAP"
    assert yasak_finans_adi("para birimi listesi") == "PARA_BIRIMI"
    assert yasak_finans_adi("para ve birim") is None  # ardışık değil


# --- taslak / kesin ayrımı (Aşama 4.5) ------------------------------------------------
# "Yazmak ≠ kaydetmek" şemada fiziksel tablo ayrımıyla korunur
# (``tests/test_islem_paketi.py``); burada aynı ayrımın kaynak kodunda da
# durduğu sınanır: taslak servisleri kesin nesne tablolarına ve nesne motoruna
# hiçbir import biçimiyle ulaşmaz, kesin nesne modülleri taslak modüllerine
# ulaşmaz. Denetim aynı AST bağımlılık çözümleyicisiyle (``bagimliliklar``)
# yapılır; dolaylı zincir de aranır.

TASLAK_MODULLERI = (
    "defteriki.cekirdek.taslak_tablolari",
    "defteriki.cekirdek.taslak_islemleri",
)
KESIN_NESNE_MODULLERI = (
    "defteriki.cekirdek.nesne_tablolari",
    "defteriki.cekirdek.nesne_islemleri",
)
KAYIT_MODULLERI = ("defteriki.cekirdek.kayit_tablolari",)
"""Kesin kayıt modülleri (Aşama 4.7). Kayıt hem kesin nesneye hem işlem
paketine bağlandığından ``KESIN_NESNE_MODULLERI``ne katılmaz; ayrımı aşağıdaki
tek yönlü denetimler korur: taslak ve nesne motoru kayıt dünyasına ulaşmaz,
kayıt modülü ise ikisini de görebilir (kesin kaydın kökeni pakettir)."""


def _modul_zinciri(
    baslangic: str, yasak: tuple[str, ...], kaynak_koku: Path
) -> list[str] | None:
    """``baslangic``tan ``yasak`` modüllerden birine giden en kısa statik import
    zinciri (üst paket ``__init__``leri dahil); yoksa ``None``."""
    dosyalar = _modul_dosyalari(kaynak_koku)
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
            if b.hedef in yasak or any(b.hedef.startswith(y + ".") for y in yasak):
                return [*yol, b.hedef]
            if _uygulama_ici_mi(b.hedef):
                ekle(b.hedef, yol)
    return None


def test_taslak_modulleri_kesin_nesne_dunyasina_ulasmaz() -> None:
    """Taslak veri kesin nesne tablolarına yazılamaz: taslak modülleri
    ``Nesne`` / ``NesneOzelligi`` / ``NesneIliskisi`` tablolarını ve nesne
    motorunu doğrudan ya da dolaylı import etmez."""
    ihlaller = {
        modul: zincir
        for modul in TASLAK_MODULLERI
        if (zincir := _modul_zinciri(modul, KESIN_NESNE_MODULLERI, KAYNAK_KOKU))
    }
    assert ihlaller == {}, (
        "taslak modülü kesin nesne dünyasına ulaşıyor (Aşama 4.5 ayrımı):\n"
        + "\n".join(f"{m}: {' → '.join(z)}" for m, z in ihlaller.items())
    )


def test_kesin_nesne_modulleri_taslak_dunyasina_ulasmaz() -> None:
    """Kesin sorgular taslak veriyi göremez: nesne motoru ve nesne tabloları
    taslak modüllerini doğrudan ya da dolaylı import etmez."""
    ihlaller = {
        modul: zincir
        for modul in KESIN_NESNE_MODULLERI
        if (zincir := _modul_zinciri(modul, TASLAK_MODULLERI, KAYNAK_KOKU))
    }
    assert ihlaller == {}, (
        "kesin nesne modülü taslak dünyasına ulaşıyor (Aşama 4.5 ayrımı):\n"
        + "\n".join(f"{m}: {' → '.join(z)}" for m, z in ihlaller.items())
    )


def test_taslak_ve_nesne_motoru_kayit_dunyasina_ulasmaz() -> None:
    """Kayıt bağımlılığı tek yönlüdür (Aşama 4.7): taslak modülleri ve nesne
    motoru kesin kayıt şemasını doğrudan ya da dolaylı import etmez. Denetim
    izi de etmez: ``taslak_islemleri`` onu kullanır, oradan kayıt şemasına bir
    zincir açılırsa taslak dünyası kesin nesneye de ulaşırdı."""
    ihlaller = {
        modul: zincir
        for modul in (
            *TASLAK_MODULLERI,
            *KESIN_NESNE_MODULLERI,
            "defteriki.cekirdek.denetim_tablolari",
            "defteriki.cekirdek.denetim_islemleri",
        )
        if (zincir := _modul_zinciri(modul, KAYIT_MODULLERI, KAYNAK_KOKU))
    }
    assert ihlaller == {}, (
        "modül kesin kayıt dünyasına ulaşıyor (Aşama 4.7 ayrımı):\n"
        + "\n".join(f"{m}: {' → '.join(z)}" for m, z in ihlaller.items())
    )


def test_taslak_ayrimi_denetleyicisi_ihlali_yakalar(tmp_path: Path) -> None:
    kok = _sentetik_agac(
        tmp_path,
        "from defteriki.cekirdek import yardimci\n",
        "cekirdek/taslak_islemleri.py",
        ek_dosyalar={
            "cekirdek/yardimci.py": (
                "from defteriki.cekirdek.nesne_tablolari import Nesne\n"
            ),
            "cekirdek/nesne_tablolari.py": "Nesne = 1\n",
        },
    )
    assert _modul_zinciri(
        "defteriki.cekirdek.taslak_islemleri", KESIN_NESNE_MODULLERI, kok
    ) == [
        "defteriki.cekirdek.taslak_islemleri",
        "defteriki.cekirdek.yardimci",
        "defteriki.cekirdek.nesne_tablolari",
    ]
    assert (
        _modul_zinciri("defteriki.cekirdek.nesne_tablolari", TASLAK_MODULLERI, kok)
        is None
    )


def test_taslak_modulleri_ham_sql_kullanmaz() -> None:
    """Import olmadan da kesin tabloya yazılamaz: taslak modülleri ham SQL
    (``sqlalchemy.text``) içermez; veritabanına yalnız kendi ORM tablolarıyla
    ulaşır, kesin nesne tablolarının ORM sınıfları ise import edilmez."""
    bulgular: list[str] = []
    for modul in TASLAK_MODULLERI:
        dosya = KAYNAK_KOKU / Path(*modul.split(".")).with_suffix(".py")
        agac = ast.parse(dosya.read_text(encoding="utf-8"), filename=str(dosya))
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.ImportFrom) and dugum.module == "sqlalchemy":
                for ad in dugum.names:
                    if ad.name == "text":
                        bulgular.append(f"{modul}:{dugum.lineno}: import text")
            elif (
                isinstance(dugum, ast.Call)
                and isinstance(dugum.func, ast.Attribute)
                and dugum.func.attr == "text"
            ):
                bulgular.append(f"{modul}:{dugum.lineno}: .text(...) çağrısı")
    assert bulgular == [], "; ".join(bulgular)
