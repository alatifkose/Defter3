"""Birinci motor testleri (karar 2026-09-24).

Gerçek SQLite dosyasıyla, ``test`` ortamında ``tmp_path`` altında. Motor
yapıyı okumaz; yapıyı **testler** okur (``PRAGMA table_info``) ve motorun
istenileni olduğu gibi yazdığını doğrular.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from defteruc import ayarlar as ay
from defteruc.cekirdek import motor as m
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
    yield v
    v.kapat()


def _sutunlar(v: vt.Veritabani, tablo: str) -> list[tuple[str, str, int, object]]:
    """(ad, tür, notnull, varsayılan): testin okuması, motorun değil."""
    with v.islem() as oturum:
        satirlar = oturum.execute(text(f'PRAGMA table_info("{tablo}")')).all()
    return [(str(s[1]), str(s[2]), int(s[3]), s[4]) for s in satirlar]


def _tablolar(v: vt.Veritabani) -> set[str]:
    with v.islem() as oturum:
        satirlar = oturum.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'table'")
        ).all()
    return {str(s[0]) for s in satirlar}


KISILER = m.TabloOlusturmaIstegi(
    tablo="kisiler",
    sutunlar=(
        m.Sutun("id", ("INTEGER", "PRIMARY KEY")),
        m.Sutun("ad_soyad", ("TEXT", "NOT NULL")),
        m.Sutun("dogum_tarihi", ("TEXT",)),
        m.Sutun("not_metni"),
    ),
)


# --- SQL üretimi veritabanına dokunmaz ---------------------------------------------


def test_tablo_olusturma_sql_istenileni_oldugu_gibi_yazar() -> None:
    assert m.tablo_olusturma_sql(KISILER) == (
        'CREATE TABLE "kisiler" ("id" INTEGER PRIMARY KEY, '
        '"ad_soyad" TEXT NOT NULL, "dogum_tarihi" TEXT, "not_metni")'
    )


def test_sutun_ekleme_sql_istenileni_oldugu_gibi_yazar() -> None:
    istek = m.SutunEklemeIstegi(
        "kisiler", m.Sutun("sehir", ("TEXT", "DEFAULT 'Edirne'"))
    )
    assert m.sutun_ekleme_sql(istek) == (
        'ALTER TABLE "kisiler" ADD COLUMN "sehir" TEXT DEFAULT \'Edirne\''
    )


# --- tablo oluşturma -----------------------------------------------------------------


def test_tablo_olusturur_ve_ozellikleri_oldugu_gibi_yazar(
    veritabani: vt.Veritabani,
) -> None:
    m.tablo_olustur(veritabani, KISILER)

    assert _tablolar(veritabani) == {"kisiler"}  # motor başka tablo açmaz
    assert _sutunlar(veritabani, "kisiler") == [
        ("id", "INTEGER", 0, None),
        ("ad_soyad", "TEXT", 1, None),
        ("dogum_tarihi", "TEXT", 0, None),
        ("not_metni", "", 0, None),
    ]


def test_ozellikler_koda_gomulu_degil_baska_tabloya_bag_dahil(
    veritabani: vt.Veritabani,
) -> None:
    """Motor özellik listesi tutmaz; ``REFERENCES`` de sıradan bir parçadır
    ve veritabanı onu gerçekten uygular."""
    m.tablo_olustur(veritabani, KISILER)
    m.tablo_olustur(
        veritabani,
        m.TabloOlusturmaIstegi(
            "notlar",
            (
                m.Sutun("id", ("INTEGER", "PRIMARY KEY")),
                m.Sutun("kisi_id", ("INTEGER", "NOT NULL", "REFERENCES kisiler(id)")),
                m.Sutun("metin", ("TEXT", "CHECK (length(metin) > 0)")),
            ),
        ),
    )

    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        with veritabani.islem() as oturum:
            oturum.execute(text("INSERT INTO notlar (kisi_id, metin) VALUES (9, 'x')"))


def test_ozellikteki_iki_nokta_bag_parametresi_sanilmaz(
    veritabani: vt.Veritabani,
) -> None:
    m.tablo_olustur(
        veritabani,
        m.TabloOlusturmaIstegi(
            "ayarlar_tablosu",
            (m.Sutun("saat", ("TEXT", "DEFAULT '09:30'")),),
        ),
    )

    assert _sutunlar(veritabani, "ayarlar_tablosu") == [("saat", "TEXT", 0, "'09:30'")]


def test_sutun_tanimlari_da_siradan_bir_tablodur(veritabani: vt.Veritabani) -> None:
    """Görünen ad gibi tanım bilgileri motorda değil, Cowork'un motorla açtığı
    sıradan bir tabloda durur; eşleşme o tabloya satır eklemektir (kayıt)."""
    m.tablo_olustur(veritabani, KISILER)
    m.tablo_olustur(
        veritabani,
        m.TabloOlusturmaIstegi(
            "sutun_tanimlari",
            (
                m.Sutun("tablo_adi", ("TEXT", "NOT NULL")),
                m.Sutun("sutun_adi", ("TEXT", "NOT NULL")),
                m.Sutun("gorunen_ad", ("TEXT",)),
            ),
        ),
    )
    with veritabani.islem() as oturum:  # kayıt: onaysız, motorsuz
        oturum.execute(
            text(
                "INSERT INTO sutun_tanimlari (tablo_adi, sutun_adi, gorunen_ad) "
                "VALUES ('kisiler', 'dogum_tarihi', 'Doğum Tarihi')"
            )
        )

    with veritabani.islem() as oturum:
        satir = oturum.execute(
            text(
                "SELECT gorunen_ad FROM sutun_tanimlari WHERE sutun_adi='dogum_tarihi'"
            )
        ).scalar_one()
    assert satir == "Doğum Tarihi"


# --- sütun ekleme --------------------------------------------------------------------


def test_sutun_ekler(veritabani: vt.Veritabani) -> None:
    m.tablo_olustur(veritabani, KISILER)

    m.sutun_ekle(
        veritabani, m.SutunEklemeIstegi("kisiler", m.Sutun("sehir", ("TEXT",)))
    )

    assert _sutunlar(veritabani, "kisiler")[-1] == ("sehir", "TEXT", 0, None)


# --- motor okumaz, reddetmez; uymayan istek veritabanında düşer ve geri alınır -----


def test_var_olan_tabloyu_yeniden_acma_istegi_veritabaninda_duser(
    veritabani: vt.Veritabani,
) -> None:
    m.tablo_olustur(veritabani, KISILER)

    with pytest.raises(m.MotorHatasi, match="already exists"):
        m.tablo_olustur(veritabani, KISILER)

    assert _sutunlar(veritabani, "kisiler")[0] == ("id", "INTEGER", 0, None)


def test_olmayan_tabloya_sutun_ekleme_veritabaninda_duser(
    veritabani: vt.Veritabani,
) -> None:
    with pytest.raises(m.MotorHatasi, match="no such table"):
        m.sutun_ekle(veritabani, m.SutunEklemeIstegi("yok", m.Sutun("a", ("TEXT",))))

    assert _tablolar(veritabani) == set()


def test_dusen_istek_tablo_birakmaz(veritabani: vt.Veritabani) -> None:
    """Aynı sütun iki kez: SQLite reddeder, tablo kalmaz."""
    with pytest.raises(m.MotorHatasi, match="duplicate column"):
        m.tablo_olustur(
            veritabani,
            m.TabloOlusturmaIstegi(
                "tekrar", (m.Sutun("a", ("TEXT",)), m.Sutun("a", ("TEXT",)))
            ),
        )

    assert _tablolar(veritabani) == set()


# --- ad biçimi: sade, Türkçe karaktersiz ---------------------------------------------


@pytest.mark.parametrize(
    "ad", ["Ödeme", "odeme tarihi", "Odeme", "1odeme", "", 'a"b', "ödeme_tarihi"]
)
def test_sade_olmayan_ad_veritabanina_dokunmadan_reddedilir(
    veritabani: vt.Veritabani, ad: str
) -> None:
    with pytest.raises(m.GecersizAd):
        m.tablo_olustur(veritabani, m.TabloOlusturmaIstegi(ad, (m.Sutun("a"),)))
    with pytest.raises(m.GecersizAd):
        m.tablo_olustur(veritabani, m.TabloOlusturmaIstegi("t", (m.Sutun(ad),)))

    assert not veritabani.yol.exists()
