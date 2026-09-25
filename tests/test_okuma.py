from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import text

from defteruc import ayarlar as ay
from defteruc.cekirdek import kayit, motor, okuma, onay
from defteruc.cekirdek import veritabani as vt

DEFTERUC_DEGISKENLERI = (
    ay.ORTAM_DEGISKENI,
    ay.VERI_KOKU_DEGISKENI,
    ay.VERITABANI_YOLU_DEGISKENI,
    ay.BELGE_DIZINI_DEGISKENI,
    ay.LOG_DIZINI_DEGISKENI,
    ay.GELEN_DIZINI_DEGISKENI,
)


@pytest.fixture(autouse=True)
def temiz_cevre(monkeypatch: pytest.MonkeyPatch) -> None:
    for degisken in DEFTERUC_DEGISKENLERI:
        monkeypatch.delenv(degisken, raising=False)


@pytest.fixture
def veritabani(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[vt.Veritabani]:
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(tmp_path / "kok"))
    ayar = ay.ayarlari_yukle()
    ay.dizinleri_hazirla(ayar)
    v = vt.Veritabani(ayar.veritabani_yolu)
    onay.sistem_tablosunu_hazirla(v)
    yield v
    v.kapat()


def _uygula(v: vt.Veritabani, istek: motor.YapiIstegi) -> None:
    with motor.islem_ac(v, istek) as baglanti:
        motor.uygula_baglantida(baglanti, istek)


KISILER = motor.TabloOlusturmaIstegi(
    "kisiler",
    (
        motor.Sutun("id", ("INTEGER", "PRIMARY KEY")),
        motor.Sutun("ad", ("TEXT", "NOT NULL")),
        motor.Sutun("puan", ("REAL",)),
    ),
)


@pytest.fixture
def dolu(veritabani: vt.Veritabani) -> vt.Veritabani:
    _uygula(veritabani, KISILER)
    kayit.satirlar_ekle(
        veritabani,
        "kisiler",
        [{"ad": f"kisi{i:03d}", "puan": float(i % 3)} for i in range(1, 251)],
    )
    return veritabani


# --- okuma ------------------------------------------------------------------------


def test_bos_tablo(veritabani: vt.Veritabani) -> None:
    _uygula(veritabani, KISILER)
    sonuc = okuma.satirlari_oku(veritabani, "kisiler")
    assert sonuc == okuma.OkumaSonucu(("id", "ad", "puan"), (), 0, 0, 0, False)


def test_varsayilan_sinir_ve_devami(dolu: vt.Veritabani) -> None:
    sonuc = okuma.satirlari_oku(dolu, "kisiler")
    assert (sonuc.eslesen_toplam, sonuc.donen, sonuc.devami_var) == (250, 100, True)
    assert sonuc.satirlar[0] == (1, "kisi001", 1.0)
    assert sonuc.satirlar[-1][0] == 100
    devam = okuma.satirlari_oku(dolu, "kisiler", baslangic=200)
    assert (devam.donen, devam.baslangic, devam.devami_var) == (50, 200, False)
    assert devam.satirlar[0][0] == 201
    son = okuma.satirlari_oku(dolu, "kisiler", baslangic=250)
    assert (son.donen, son.devami_var, son.eslesen_toplam) == (0, False, 250)


def test_kosul_parametreyle_ve_eslesen_toplam_kosula_gore(dolu: vt.Veritabani) -> None:
    sonuc = okuma.satirlari_oku(
        dolu, "kisiler", "puan = ? AND ad > ?", (2.0, "kisi100"), sinir=5
    )
    assert sonuc.eslesen_toplam == 50
    assert sonuc.donen == 5 and sonuc.devami_var
    assert [s[1] for s in sonuc.satirlar] == [
        "kisi101",
        "kisi104",
        "kisi107",
        "kisi110",
        "kisi113",
    ]


def test_deger_parametre_olarak_gecer(dolu: vt.Veritabani) -> None:
    sonuc = okuma.satirlari_oku(dolu, "kisiler", "ad = ?", ("x' OR 1=1 --",))
    assert sonuc.eslesen_toplam == 0


def test_siralama_anahtara_gore_without_rowid_dahil(veritabani: vt.Veritabani) -> None:
    _uygula(
        veritabani,
        motor.TabloOlusturmaIstegi(
            "bilesik",
            (motor.Sutun("yil", ("INTEGER",)), motor.Sutun("no", ("INTEGER",))),
            kisitlar=("PRIMARY KEY (yil, no)",),
            secenekler=("WITHOUT ROWID",),
        ),
    )
    kayit.satirlar_ekle(
        veritabani,
        "bilesik",
        [{"yil": 2026, "no": 2}, {"yil": 2025, "no": 9}, {"yil": 2026, "no": 1}],
    )
    sonuc = okuma.satirlari_oku(veritabani, "bilesik")
    assert sonuc.satirlar == ((2025, 9), (2026, 1), (2026, 2))


def test_sinir_ve_baslangic_denetimi(dolu: vt.Veritabani) -> None:
    with pytest.raises(okuma.OkumaHatasi, match="sınır"):
        okuma.satirlari_oku(dolu, "kisiler", sinir=0)
    with pytest.raises(okuma.OkumaHatasi, match="sınır"):
        okuma.satirlari_oku(dolu, "kisiler", sinir=okuma.SINIR_AZAMI + 1)
    with pytest.raises(okuma.OkumaHatasi, match="negatif"):
        okuma.satirlari_oku(dolu, "kisiler", baslangic=-1)


def test_olmayan_tablo_ve_bozuk_kosul(dolu: vt.Veritabani) -> None:
    with pytest.raises(okuma.OkumaHatasi, match="no such table"):
        okuma.satirlari_oku(dolu, "yok")
    with pytest.raises(okuma.OkumaHatasi, match="no such column"):
        okuma.satirlari_oku(dolu, "kisiler", "yok = 1")
    with pytest.raises(motor.GecersizAd):
        okuma.satirlari_oku(dolu, "Kisiler")


# --- erişim sınırı: yetkilendirme kancası -------------------------------------------


@pytest.mark.parametrize(
    "kosul",
    [
        "1 = 1; DROP TABLE kisiler",
        "1 = 1 -- yorum",
        "id IN (SELECT 1) )",
    ],
)
def test_parca_kurali_kosula_uygulanir(dolu: vt.Veritabani, kosul: str) -> None:
    with pytest.raises(motor.GecersizParca):
        okuma.satirlari_oku(dolu, "kisiler", kosul)


def test_sistem_tablosu_dogrudan_okunamaz(dolu: vt.Veritabani) -> None:
    with pytest.raises(okuma.OkumaHatasi, match="sistem tablosu okunamaz"):
        okuma.satirlari_oku(dolu, "_defteruc_yapi_istekleri")


@pytest.mark.parametrize(
    "kosul",
    [
        f'ad IN (SELECT sql FROM "{onay.SISTEM_TABLOSU}")',
        f'EXISTS (SELECT 1 FROM "{onay.SISTEM_TABLOSU}")',
        "ad IN (SELECT sql FROM sqlite_master)",
        "ad IN (SELECT name FROM sqlite_schema)",
        "load_extension('x') IS NULL",
    ],
)
def test_alt_sorguyla_sistem_tablosu_ve_tehlikeli_islev_reddedilir(
    dolu: vt.Veritabani, kosul: str
) -> None:
    with pytest.raises(okuma.OkumaHatasi, match="prohibited|not authorized"):
        okuma.satirlari_oku(dolu, "kisiler", kosul)


def test_kosulda_siradan_islev_ve_alt_sorgu_serbest(dolu: vt.Veritabani) -> None:
    sonuc = okuma.satirlari_oku(
        dolu,
        "kisiler",
        "upper(ad) = ? AND id IN (SELECT id FROM kisiler)",
        ("KISI007",),
    )
    assert sonuc.eslesen_toplam == 1 and sonuc.satirlar[0][0] == 7


def test_okuma_sonrasi_baglanti_yeniden_yazabilir(dolu: vt.Veritabani) -> None:
    okuma.satirlari_oku(dolu, "kisiler", sinir=1)
    with pytest.raises(okuma.OkumaHatasi):
        okuma.satirlari_oku(dolu, "kisiler", "ad IN (SELECT sql FROM sqlite_master)")
    sonuc = kayit.satirlar_ekle(dolu, "kisiler", [{"ad": "sonra"}])
    assert sonuc.anahtarlar == ((251,),)
    with dolu.islem() as oturum:
        assert oturum.execute(text("PRAGMA table_info(kisiler)")).all()
    assert okuma.satirlari_oku(dolu, "kisiler").eslesen_toplam == 251
