from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import text

from defteruc import ayarlar as ay
from defteruc.cekirdek import kayit, motor, onay, yapi
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


def _satirlar(v: vt.Veritabani, sql: str) -> list[tuple[object, ...]]:
    with v.islem() as oturum:
        return [tuple(s) for s in oturum.execute(text(sql)).all()]


KISILER = motor.TabloOlusturmaIstegi(
    tablo="kisiler",
    sutunlar=(
        motor.Sutun("id", ("INTEGER", "PRIMARY KEY", "AUTOINCREMENT")),
        motor.Sutun("ad_soyad", ("TEXT", "NOT NULL")),
        motor.Sutun("puan", ("REAL", "DEFAULT 0")),
        motor.Sutun("buyuk_harf", ("TEXT", "GENERATED ALWAYS AS (upper(ad_soyad))")),
    ),
    kisitlar=("UNIQUE (ad_soyad)",),
)


# --- yapıyı okuma ------------------------------------------------------------------


def test_bos_veritabaninda_tablo_yok_sistem_tablosu_gorunmez(
    veritabani: vt.Veritabani,
) -> None:
    assert yapi.yapiyi_oku(veritabani) == ()


def test_yapi_sutun_indeks_ve_satir_sayisiyla_okunur(veritabani: vt.Veritabani) -> None:
    _uygula(veritabani, KISILER)
    _uygula(veritabani, motor.IndeksOlusturmaIstegi("ix_puan", "kisiler", ("puan",)))
    _uygula(
        veritabani,
        motor.IndeksOlusturmaIstegi("ux_ad", "kisiler", ("ad_soyad",), benzersiz=True),
    )
    kayit.satirlar_ekle(veritabani, "kisiler", [{"ad_soyad": "A"}, {"ad_soyad": "B"}])

    (tablo,) = yapi.yapiyi_oku(veritabani)
    assert tablo.ad == "kisiler"
    assert tablo.sql == motor.tablo_olusturma_sql(KISILER)
    assert tablo.satir_sayisi == 2
    assert [s.ad for s in tablo.sutunlar] == ["id", "ad_soyad", "puan", "buyuk_harf"]
    kimlik, ad, puan, uretilen = tablo.sutunlar
    assert (kimlik.tur, kimlik.anahtar_sirasi, kimlik.uretilen) == ("INTEGER", 1, False)
    assert (ad.zorunlu, ad.varsayilan, ad.anahtar_sirasi) == (True, None, 0)
    assert (puan.zorunlu, puan.varsayilan) == (False, "0")
    assert uretilen.uretilen is True
    assert [(i.ad, i.benzersiz) for i in tablo.indeksler] == [
        ("ix_puan", False),
        ("ux_ad", True),
    ]
    assert (
        tablo.indeksler[1].sql == 'CREATE UNIQUE INDEX "ux_ad" ON "kisiler" (ad_soyad)'
    )


def test_yapi_tablolari_ada_gore_siralar(veritabani: vt.Veritabani) -> None:
    for ad in ("zeytin", "armut", "elma"):
        _uygula(veritabani, motor.TabloOlusturmaIstegi(ad, (motor.Sutun("a"),)))
    assert [t.ad for t in yapi.yapiyi_oku(veritabani)] == ["armut", "elma", "zeytin"]


# --- satır ekleme -------------------------------------------------------------------


def test_satirlar_tek_islemde_eklenir_ve_sayi_doner(veritabani: vt.Veritabani) -> None:
    _uygula(veritabani, KISILER)
    eklenen = kayit.satirlar_ekle(
        veritabani,
        "kisiler",
        [
            {"ad_soyad": "Ayşe", "puan": 1.5},
            {"ad_soyad": "Ali", "puan": None},
            {"ad_soyad": "Can", "puan": True},
        ],
    )
    assert eklenen == kayit.EklemeSonucu(3, ("id",), ((1,), (2,), (3,)))
    assert _satirlar(
        veritabani, "SELECT ad_soyad, puan, buyuk_harf FROM kisiler ORDER BY id"
    ) == [("Ayşe", 1.5, "AYşE"), ("Ali", None, "ALI"), ("Can", 1.0, "CAN")]
    # SQLite'ın upper() işlevi yalnız ASCII harfleri büyütür; REAL sütun
    # doğru/yanlış değerini 1.0/0.0 olarak saklar.


def test_anahtar_turleri_metin_anahtar_rowid_ve_bilesik(
    veritabani: vt.Veritabani,
) -> None:
    _uygula(
        veritabani,
        motor.TabloOlusturmaIstegi(
            "kodlar", (motor.Sutun("kod", ("TEXT", "PRIMARY KEY")), motor.Sutun("a"))
        ),
    )
    _uygula(veritabani, motor.TabloOlusturmaIstegi("serbest", (motor.Sutun("a"),)))
    _uygula(
        veritabani,
        motor.TabloOlusturmaIstegi(
            "bilesik",
            (motor.Sutun("yil", ("INTEGER",)), motor.Sutun("no", ("INTEGER",))),
            kisitlar=("PRIMARY KEY (yil, no)",),
            secenekler=("WITHOUT ROWID",),
        ),
    )
    assert kayit.satirlar_ekle(
        veritabani, "kodlar", [{"kod": "X1"}, {"kod": "X2", "a": 1}]
    ) == kayit.EklemeSonucu(2, ("kod",), (("X1",), ("X2",)))
    assert kayit.satirlar_ekle(
        veritabani, "serbest", [{"a": 1}, {"a": 2}]
    ) == kayit.EklemeSonucu(2, ("rowid",), ((1,), (2,)))
    assert kayit.satirlar_ekle(
        veritabani, "bilesik", [{"yil": 2026, "no": 7}]
    ) == kayit.EklemeSonucu(1, ("yil", "no"), ((2026, 7),))


def test_bir_satir_reddedilirse_hicbiri_yazilmaz(veritabani: vt.Veritabani) -> None:
    _uygula(veritabani, KISILER)
    with pytest.raises(kayit.KayitHatasi, match="hiçbiri yazılmadı"):
        kayit.satirlar_ekle(
            veritabani,
            "kisiler",
            [{"ad_soyad": "Ayşe"}, {"ad_soyad": None}, {"ad_soyad": "Can"}],
        )
    assert _satirlar(veritabani, "SELECT count(*) FROM kisiler") == [(0,)]
    with pytest.raises(kayit.KayitHatasi, match="hiçbiri yazılmadı"):
        kayit.satirlar_ekle(
            veritabani, "kisiler", [{"ad_soyad": "Ayşe"}, {"ad_soyad": "Ayşe"}]
        )
    assert _satirlar(veritabani, "SELECT count(*) FROM kisiler") == [(0,)]


def test_bilinmeyen_sutun_ve_olmayan_tablo(veritabani: vt.Veritabani) -> None:
    _uygula(veritabani, KISILER)
    with pytest.raises(kayit.KayitHatasi, match="no column named yok"):
        kayit.satirlar_ekle(veritabani, "kisiler", [{"ad_soyad": "A", "yok": 1}])
    with pytest.raises(kayit.KayitHatasi, match="no such table"):
        kayit.satirlar_ekle(veritabani, "yok", [{"a": 1}])
    assert _satirlar(veritabani, "SELECT count(*) FROM kisiler") == [(0,)]


def test_bos_liste_ve_bos_satir_reddedilir(veritabani: vt.Veritabani) -> None:
    _uygula(veritabani, KISILER)
    with pytest.raises(kayit.KayitHatasi, match="eklenecek satır yok"):
        kayit.satirlar_ekle(veritabani, "kisiler", [])
    with pytest.raises(kayit.KayitHatasi, match="boş satır"):
        kayit.satirlar_ekle(veritabani, "kisiler", [{"ad_soyad": "A"}, {}])
    assert _satirlar(veritabani, "SELECT count(*) FROM kisiler") == [(0,)]


@pytest.mark.parametrize("ad", [onay.SISTEM_TABLOSU, "Kisiler", "a b", 'a"b', ""])
def test_sade_olmayan_tablo_adi_dokunmadan_reddedilir(
    veritabani: vt.Veritabani, ad: str
) -> None:
    with pytest.raises(motor.GecersizAd):
        kayit.satirlar_ekle(veritabani, ad, [{"a": 1}])


def test_sade_olmayan_sutun_adi_dokunmadan_reddedilir(
    veritabani: vt.Veritabani,
) -> None:
    _uygula(veritabani, KISILER)
    with pytest.raises(motor.GecersizAd):
        kayit.satirlar_ekle(
            veritabani, "kisiler", [{"ad_soyad": "A"}, {'ad_soyad") VALUES ("x': 1}]
        )
    assert _satirlar(veritabani, "SELECT count(*) FROM kisiler") == [(0,)]


def test_degerler_parametre_olarak_gecer_sql_degil(veritabani: vt.Veritabani) -> None:
    _uygula(veritabani, KISILER)
    kotu = "x'); DROP TABLE kisiler; --"
    kayit.satirlar_ekle(veritabani, "kisiler", [{"ad_soyad": kotu}])
    assert _satirlar(veritabani, "SELECT ad_soyad FROM kisiler") == [(kotu,)]


def test_blob_anahtar_kayipsiz_ve_json_uyumlu_doner(veritabani: vt.Veritabani) -> None:
    import json
    from dataclasses import asdict

    _uygula(
        veritabani,
        motor.TabloOlusturmaIstegi(
            "binary_pk",
            (
                motor.Sutun("id", ("BLOB", "PRIMARY KEY", "DEFAULT (randomblob(8))")),
                motor.Sutun("ad", ("TEXT",)),
            ),
        ),
    )
    sonuc = kayit.satirlar_ekle(veritabani, "binary_pk", [{"ad": "A"}, {"ad": "B"}])
    json.dumps(asdict(sonuc))
    (a,), (b,) = sonuc.anahtarlar
    assert isinstance(a, str) and a.startswith("X'") and len(a) == 2 + 16 + 1
    assert a != b
    assert _satirlar(veritabani, f"SELECT ad FROM binary_pk WHERE id = {a}") == [("A",)]


# --- inceleme 2026-09-25, bulgu 3: rowid adlı sütun anahtar sanılmaz ----------------


def test_rowid_adli_sutun_golgelerse_gercek_kimlik_doner(
    veritabani: vt.Veritabani,
) -> None:
    _uygula(
        veritabani,
        motor.TabloOlusturmaIstegi(
            "shadow", (motor.Sutun("rowid", ("TEXT",)), motor.Sutun("ad", ("TEXT",)))
        ),
    )
    sonuc = kayit.satirlar_ekle(
        veritabani,
        "shadow",
        [{"rowid": "same", "ad": "A"}, {"rowid": "same", "ad": "B"}],
    )
    assert sonuc.anahtar_sutunlari == ("_rowid_",)
    assert sonuc.anahtarlar == ((1,), (2,))
    assert _satirlar(veritabani, "SELECT rowid, ad FROM shadow ORDER BY _rowid_") == [
        ("same", "A"),
        ("same", "B"),
    ]


def test_uc_takma_ad_da_golgeliyse_kayit_reddedilir(veritabani: vt.Veritabani) -> None:
    # Motor alt çizgiyle başlayan ad açmaz; böyle bir tablo ancak dışarıdan gelir.
    with veritabani.islem() as oturum:
        oturum.execute(text('CREATE TABLE "golge" ("rowid", "_rowid_", "oid")'))
    with pytest.raises(kayit.KayitHatasi, match="satır kimliği"):
        kayit.satirlar_ekle(veritabani, "golge", [{"rowid": 1}])
    assert _satirlar(veritabani, "SELECT count(*) FROM golge") == [(0,)]
