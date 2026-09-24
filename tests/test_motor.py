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


# --- sütun özelliği değiştirme: tabloyu tam tanımla yeniden kurma ------------------


def _satirlar(v: vt.Veritabani, sql: str) -> list[tuple[object, ...]]:
    with v.islem() as oturum:
        return [tuple(s) for s in oturum.execute(text(sql)).all()]


def _kisileri_doldur(v: vt.Veritabani) -> None:
    m.tablo_olustur(v, KISILER)
    with v.islem() as oturum:
        oturum.execute(
            text(
                "INSERT INTO kisiler (id, ad_soyad, dogum_tarihi, not_metni) VALUES "
                "(1, 'Ali', '1980-01-01', NULL), (2, 'Veli', NULL, 'x')"
            )
        )


KISILER_YENI = m.SutunOzelligiDegistirmeIstegi(
    tablo="kisiler",
    sutunlar=(
        m.Sutun("id", ("INTEGER", "PRIMARY KEY")),
        m.Sutun("ad_soyad", ("TEXT", "NOT NULL", "COLLATE NOCASE")),
        m.Sutun("dogum_tarihi", ("TEXT", "DEFAULT '1900-01-01'")),
        m.Sutun("not_metni", ("TEXT",)),
    ),
)


def test_sutun_ozelligi_degistirme_sql_adimlari_dokunmadan_uretir() -> None:
    assert m.sutun_ozelligi_degistirme_sql(KISILER_YENI) == (
        'CREATE TABLE "kisiler__yeniden_kurma" ("id" INTEGER PRIMARY KEY, '
        '"ad_soyad" TEXT NOT NULL COLLATE NOCASE, '
        '"dogum_tarihi" TEXT DEFAULT \'1900-01-01\', "not_metni" TEXT)',
        'INSERT INTO "kisiler__yeniden_kurma" '
        '("id", "ad_soyad", "dogum_tarihi", "not_metni") '
        'SELECT "id", "ad_soyad", "dogum_tarihi", "not_metni" FROM "kisiler"',
        'DROP TABLE "kisiler"',
        'ALTER TABLE "kisiler__yeniden_kurma" RENAME TO "kisiler"',
    )


def test_ozellikleri_degistirir_satirlari_korur(veritabani: vt.Veritabani) -> None:
    _kisileri_doldur(veritabani)

    m.sutun_ozelligi_degistir(veritabani, KISILER_YENI)

    assert _tablolar(veritabani) == {"kisiler"}  # geçici tablo kalmaz
    assert _sutunlar(veritabani, "kisiler") == [
        ("id", "INTEGER", 0, None),
        ("ad_soyad", "TEXT", 1, None),
        ("dogum_tarihi", "TEXT", 0, "'1900-01-01'"),
        ("not_metni", "TEXT", 0, None),
    ]
    assert _satirlar(veritabani, "SELECT * FROM kisiler ORDER BY id") == [
        (1, "Ali", "1980-01-01", None),
        (2, "Veli", None, "x"),
    ]
    # yeni özellik gerçekten uygulanıyor (COLLATE NOCASE)
    assert _satirlar(
        veritabani, "SELECT id FROM kisiler WHERE ad_soyad = 'ALİ' OR ad_soyad = 'ALI'"
    ) == [(1,)]


def test_baska_tablonun_bagi_yeniden_kurulan_tabloyu_izler(
    veritabani: vt.Veritabani,
) -> None:
    _kisileri_doldur(veritabani)
    m.tablo_olustur(
        veritabani,
        m.TabloOlusturmaIstegi(
            "notlar",
            (
                m.Sutun("id", ("INTEGER", "PRIMARY KEY")),
                m.Sutun("kisi_id", ("INTEGER", "NOT NULL", "REFERENCES kisiler(id)")),
            ),
        ),
    )
    with veritabani.islem() as oturum:
        oturum.execute(text("INSERT INTO notlar (kisi_id) VALUES (1)"))

    m.sutun_ozelligi_degistir(veritabani, KISILER_YENI)

    assert _satirlar(veritabani, "SELECT kisi_id FROM notlar") == [(1,)]
    with pytest.raises(IntegrityError, match="FOREIGN KEY"):  # denetim yeniden açık
        with veritabani.islem() as oturum:
            oturum.execute(text("INSERT INTO notlar (kisi_id) VALUES (9)"))


def test_uymayan_satirda_is_duser_eski_tablo_eksiksiz_kalir(
    veritabani: vt.Veritabani,
) -> None:
    """Veli'nin doğum tarihi NULL; NOT NULL isteği SQLite'ta düşer."""
    _kisileri_doldur(veritabani)
    istek = m.SutunOzelligiDegistirmeIstegi(
        "kisiler",
        (
            m.Sutun("id", ("INTEGER", "PRIMARY KEY")),
            m.Sutun("ad_soyad", ("TEXT", "NOT NULL")),
            m.Sutun("dogum_tarihi", ("TEXT", "NOT NULL")),
            m.Sutun("not_metni"),
        ),
    )

    with pytest.raises(m.MotorHatasi, match="NOT NULL"):
        m.sutun_ozelligi_degistir(veritabani, istek)

    _eski_kisiler_eksiksiz(veritabani)


def _eski_kisiler_eksiksiz(v: vt.Veritabani) -> None:
    assert _tablolar(v) >= {"kisiler"} and "kisiler__yeniden_kurma" not in _tablolar(v)
    assert _sutunlar(v, "kisiler") == [
        ("id", "INTEGER", 0, None),
        ("ad_soyad", "TEXT", 1, None),
        ("dogum_tarihi", "TEXT", 0, None),
        ("not_metni", "", 0, None),
    ]
    assert _satirlar(v, "SELECT * FROM kisiler ORDER BY id") == [
        (1, "Ali", "1980-01-01", None),
        (2, "Veli", None, "x"),
    ]


# --- emniyet kuralı: yalnız özellik; ekleme, silme, ad ve sıra değişikliği yok ------


@pytest.mark.parametrize(
    ("sutunlar", "neden"),
    [
        (  # eksik: not_metni yok (silme)
            (m.Sutun("id"), m.Sutun("ad_soyad"), m.Sutun("dogum_tarihi")),
            "eksik \\['not_metni'\\]",
        ),
        (  # fazla: sehir (ekleme)
            (
                m.Sutun("id"),
                m.Sutun("ad_soyad"),
                m.Sutun("dogum_tarihi"),
                m.Sutun("not_metni"),
                m.Sutun("sehir"),
            ),
            "fazla \\['sehir'\\]",
        ),
        (  # farklı ad (yeniden adlandırma)
            (
                m.Sutun("id"),
                m.Sutun("ad"),
                m.Sutun("dogum_tarihi"),
                m.Sutun("not_metni"),
            ),
            "eksik \\['ad_soyad'\\], fazla \\['ad'\\]",
        ),
        (  # sıra farklı
            (
                m.Sutun("id"),
                m.Sutun("dogum_tarihi"),
                m.Sutun("ad_soyad"),
                m.Sutun("not_metni"),
            ),
            "sıra farklı",
        ),
    ],
)
def test_sutun_adlari_birebir_ayni_degilse_dokunmadan_reddeder(
    veritabani: vt.Veritabani, sutunlar: tuple[m.Sutun, ...], neden: str
) -> None:
    _kisileri_doldur(veritabani)

    with pytest.raises(m.SutunlarUyusmuyor, match=neden):
        m.sutun_ozelligi_degistir(
            veritabani, m.SutunOzelligiDegistirmeIstegi("kisiler", sutunlar)
        )

    _eski_kisiler_eksiksiz(veritabani)


def test_olmayan_tablo_reddedilir(veritabani: vt.Veritabani) -> None:
    with pytest.raises(m.MotorHatasi, match="tablo yok"):
        m.sutun_ozelligi_degistir(
            veritabani, m.SutunOzelligiDegistirmeIstegi("yok", (m.Sutun("a"),))
        )
    assert _tablolar(veritabani) == set()


# --- bağlı nesneler taşınır: indeks, trigger, görünüm ---------------------------


BAGLI_NESNELER = (
    "CREATE INDEX ix_kisiler_ad ON kisiler (ad_soyad)",
    "CREATE UNIQUE INDEX ux_kisiler_id_ad ON kisiler (id, ad_soyad)",
    "CREATE TRIGGER tr_kisiler AFTER INSERT ON kisiler BEGIN "
    "UPDATE kisiler SET not_metni = 'yeni' WHERE id = NEW.id; END",
    "CREATE TABLE diger (id INTEGER)",
    "CREATE TRIGGER tr_diger AFTER INSERT ON diger BEGIN "
    "DELETE FROM kisiler WHERE id = NEW.id; END",
    "CREATE VIEW gorunum AS SELECT id, ad_soyad FROM kisiler",
    "CREATE VIEW gorunum_ust AS SELECT ad_soyad FROM gorunum",
)


def _nesneler(v: vt.Veritabani) -> list[tuple[str, str, str]]:
    """(tür, ad, cümle), oluşturma sırasıyla; tablolar hariç."""
    with v.islem() as oturum:
        satirlar = oturum.execute(
            text(
                "SELECT type, name, sql FROM sqlite_master "
                "WHERE type != 'table' AND sql IS NOT NULL ORDER BY rowid"
            )
        ).all()
    return [(str(r[0]), str(r[1]), str(r[2])) for r in satirlar]


def _bagli_nesneleri_kur(v: vt.Veritabani) -> list[tuple[str, str, str]]:
    _kisileri_doldur(v)
    with v.islem() as oturum:
        for cumle in BAGLI_NESNELER:
            oturum.execute(text(cumle))
    return _nesneler(v)


def test_indeks_trigger_ve_gorunumler_ayni_cumleyle_geri_acilir(
    veritabani: vt.Veritabani,
) -> None:
    oncesi = _bagli_nesneleri_kur(veritabani)
    assert {n[1] for n in oncesi} == {
        "ix_kisiler_ad",
        "ux_kisiler_id_ad",
        "tr_kisiler",
        "tr_diger",
        "gorunum",
        "gorunum_ust",
    }

    m.sutun_ozelligi_degistir(veritabani, KISILER_YENI)

    assert _nesneler(veritabani) == oncesi  # aynı cümle, aynı sıra
    assert _sutunlar(veritabani, "kisiler")[1] == ("ad_soyad", "TEXT", 1, None)
    # hepsi çalışıyor: indeks tabloya bağlı, trigger'lar ateşleniyor, görünüm okunuyor
    with veritabani.islem() as oturum:
        indeksler = oturum.execute(text('PRAGMA index_list("kisiler")')).all()
        assert {str(i[1]) for i in indeksler} >= {"ix_kisiler_ad", "ux_kisiler_id_ad"}
        oturum.execute(text("INSERT INTO kisiler (id, ad_soyad) VALUES (3, 'Can')"))
        oturum.execute(text("INSERT INTO diger (id) VALUES (2)"))
    assert _satirlar(veritabani, "SELECT id, not_metni FROM kisiler ORDER BY id") == [
        (1, None),
        (3, "yeni"),
    ]
    assert _satirlar(veritabani, "SELECT * FROM gorunum_ust ORDER BY 1") == [
        ("Ali",),
        ("Can",),
    ]


def test_dusen_iste_bagli_nesneler_de_eksiksiz_kalir(
    veritabani: vt.Veritabani,
) -> None:
    oncesi = _bagli_nesneleri_kur(veritabani)
    istek = m.SutunOzelligiDegistirmeIstegi(
        "kisiler",
        (
            m.Sutun("id", ("INTEGER", "PRIMARY KEY")),
            m.Sutun("ad_soyad", ("TEXT", "NOT NULL")),
            m.Sutun("dogum_tarihi", ("TEXT", "NOT NULL")),  # Veli'de NULL: düşer
            m.Sutun("not_metni"),
        ),
    )

    with pytest.raises(m.MotorHatasi, match="NOT NULL"):
        m.sutun_ozelligi_degistir(veritabani, istek)

    _eski_kisiler_eksiksiz(veritabani)
    assert _nesneler(veritabani) == oncesi


def test_baska_tablonun_nesneleri_oldugu_gibi_kalir(veritabani: vt.Veritabani) -> None:
    """Başka tablonun indeksine dokunulmaz; görünümü aynı cümleyle geri açılır."""
    _kisileri_doldur(veritabani)
    with veritabani.islem() as oturum:
        oturum.execute(text("CREATE TABLE kisiler_arsiv (id INTEGER, ad TEXT)"))
        oturum.execute(text("CREATE INDEX ix_arsiv ON kisiler_arsiv (ad)"))
        oturum.execute(text("CREATE VIEW g AS SELECT id FROM kisiler_arsiv"))
    oncesi = _nesneler(veritabani)

    m.sutun_ozelligi_degistir(veritabani, KISILER_YENI)

    assert _nesneler(veritabani) == oncesi


# --- sessiz kayıp yok: taşınamayan yapı tespit edilince reddedilir ------------------


@pytest.mark.parametrize(
    ("tanim", "sutunlar", "neden"),
    [
        (
            "CREATE TABLE t (a INTEGER, b TEXT, UNIQUE (a, b))",
            (m.Sutun("a"), m.Sutun("b")),
            "tablo düzeyi kısıt",
        ),
        (
            "CREATE TABLE t (a INTEGER, b TEXT, CHECK (a > 0 AND b IN ('x', 'y')))",
            (m.Sutun("a"), m.Sutun("b")),
            "tablo düzeyi kısıt",
        ),
        (
            "CREATE TABLE t (a INTEGER, b TEXT, PRIMARY KEY (a, b))",
            (m.Sutun("a"), m.Sutun("b")),
            "tablo düzeyi kısıt",
        ),
        (
            "CREATE TABLE t (a INTEGER, b TEXT, "
            "CONSTRAINT fk FOREIGN KEY (a) REFERENCES kisiler (id))",
            (m.Sutun("a"), m.Sutun("b")),
            "tablo düzeyi kısıt",
        ),
        (
            "CREATE TABLE t (a INTEGER PRIMARY KEY, b TEXT) WITHOUT ROWID",
            (m.Sutun("a"), m.Sutun("b")),
            "tablo seçeneği",
        ),
        (
            "CREATE TABLE t (a INTEGER, b TEXT) STRICT",
            (m.Sutun("a"), m.Sutun("b")),
            "tablo seçeneği",
        ),
        (
            "CREATE TABLE t (a INTEGER, b INTEGER GENERATED ALWAYS AS (a * 2) VIRTUAL)",
            (m.Sutun("a"), m.Sutun("b")),
            "gizli sütun",
        ),
    ],
)
def test_tablo_duzeyi_kisit_secenek_ve_gizli_sutun_reddedilir(
    veritabani: vt.Veritabani, tanim: str, sutunlar: tuple[m.Sutun, ...], neden: str
) -> None:
    _kisileri_doldur(veritabani)
    with veritabani.islem() as oturum:
        oturum.execute(text(tanim))

    with pytest.raises(m.DesteklenmeyenYapi, match=neden):
        m.sutun_ozelligi_degistir(
            veritabani, m.SutunOzelligiDegistirmeIstegi("t", sutunlar)
        )

    with veritabani.islem() as oturum:
        kalan = oturum.execute(
            text("SELECT sql FROM sqlite_master WHERE name = 't'")
        ).scalar_one()
    assert kalan == tanim


@pytest.mark.parametrize(
    ("sql", "beklenen"),
    [
        ('CREATE TABLE "t" ("a" INTEGER, "b" TEXT)', (2, "")),
        ("CREATE TABLE t ()", (0, "")),
        ("CREATE TABLE t (a)", (1, "")),
        # sütun düzeyi kısıtların içindeki virgül ve parantez parça saymaz
        (
            "CREATE TABLE t (a INTEGER REFERENCES x(p, q), "
            "b TEXT CHECK (b IN ('1,2', \"3)4\")) DEFAULT '(',  c)",
            (3, ""),
        ),
        # tırnak ve köşeli parantez içindeki virgüller
        (
            "CREATE TABLE t (`a,b` TEXT, [c,d] TEXT, 'e' TEXT DEFAULT 'it''s, ok')",
            (3, ""),
        ),
        # yorumlar
        ("CREATE TABLE t (a, -- b, c\n b /* , d) */)", (2, "")),
        ("CREATE TABLE t (a, b) WITHOUT ROWID", (2, "WITHOUT ROWID")),
        ("CREATE TABLE t (a, b, UNIQUE (a, b))", (3, "")),
    ],
)
def test_ust_duzey_parca_sayisi(sql: str, beklenen: tuple[int, str]) -> None:
    assert m._ust_duzey_parca_sayisi(sql) == beklenen  # pyright: ignore[reportPrivateUsage]


# --- inceleme bulguları (2026-09-24): INSTEAD OF trigger, AUTOINCREMENT, özellik sınırı


def test_gorunumun_instead_of_triggeri_silme_sirasini_bozmaz(
    veritabani: vt.Veritabani,
) -> None:
    """Görünüm silinince INSTEAD OF trigger'ı kendiliğinden gider; trigger'lar
    görünümlerden önce silinmezse ikinci DROP düşerdi."""
    _kisileri_doldur(veritabani)
    with veritabani.islem() as oturum:
        oturum.execute(text("CREATE VIEW g AS SELECT id, ad_soyad FROM kisiler"))
        oturum.execute(
            text(
                "CREATE TRIGGER g_ekle INSTEAD OF INSERT ON g BEGIN "
                "INSERT INTO kisiler (ad_soyad) VALUES (NEW.ad_soyad); END"
            )
        )
    oncesi = _nesneler(veritabani)

    m.sutun_ozelligi_degistir(veritabani, KISILER_YENI)

    assert _nesneler(veritabani) == oncesi
    with veritabani.islem() as oturum:
        oturum.execute(text("INSERT INTO g (ad_soyad) VALUES ('Can')"))
    assert _satirlar(veritabani, "SELECT ad_soyad FROM kisiler WHERE id = 3") == [
        ("Can",)
    ]


def test_autoincrement_sayaci_korunur(veritabani: vt.Veritabani) -> None:
    """Silinmiş kimlik yeniden dağıtılmaz: sayaç yeniden kurmadan sonra da 2'de."""
    m.tablo_olustur(
        veritabani,
        m.TabloOlusturmaIstegi(
            "sira",
            (m.Sutun("id", ("INTEGER", "PRIMARY KEY", "AUTOINCREMENT")), m.Sutun("ad")),
        ),
    )
    with veritabani.islem() as oturum:
        oturum.execute(text("INSERT INTO sira (ad) VALUES ('a'), ('b')"))
        oturum.execute(text("DELETE FROM sira WHERE id = 2"))

    m.sutun_ozelligi_degistir(
        veritabani,
        m.SutunOzelligiDegistirmeIstegi(
            "sira",
            (
                m.Sutun("id", ("INTEGER", "PRIMARY KEY", "AUTOINCREMENT")),
                m.Sutun("ad", ("TEXT",)),
            ),
        ),
    )

    assert _satirlar(
        veritabani, "SELECT seq FROM sqlite_sequence WHERE name='sira'"
    ) == [(2,)]
    with veritabani.islem() as oturum:
        oturum.execute(text("INSERT INTO sira (ad) VALUES ('c')"))
    assert _satirlar(veritabani, "SELECT id FROM sira ORDER BY id") == [(1,), (3,)]


def test_autoincrement_olmayan_tabloda_sayac_islemi_yok(
    veritabani: vt.Veritabani,
) -> None:
    _kisileri_doldur(veritabani)
    m.sutun_ozelligi_degistir(veritabani, KISILER_YENI)
    assert "sqlite_sequence" not in _tablolar(veritabani)


@pytest.mark.parametrize(
    "parca",
    [
        'TEXT, UNIQUE("a")',  # sütun tanımından çıkıp tablo düzeyi kısıt yazardı
        "TEXT)",
        "TEXT) , (b",
        "TEXT; DROP TABLE kisiler",
        "CHECK (a > 0",
        "TEXT DEFAULT 'kapanmayan",
        "TEXT /* kapanmayan",
        "",
        "   ",
    ],
)
def test_sutun_tanimindan_cikan_ozellik_dokunmadan_reddedilir(
    veritabani: vt.Veritabani, parca: str
) -> None:
    with pytest.raises(m.GecersizOzellik):
        m.tablo_olustur(
            veritabani, m.TabloOlusturmaIstegi("t", (m.Sutun("a", (parca,)),))
        )
    with pytest.raises(m.GecersizOzellik):
        m.sutun_ekle(veritabani, m.SutunEklemeIstegi("t", m.Sutun("a", (parca,))))
    with pytest.raises(m.GecersizOzellik):
        m.sutun_ozelligi_degistirme_sql(
            m.SutunOzelligiDegistirmeIstegi("t", (m.Sutun("a", (parca,)),))
        )

    assert not veritabani.yol.exists()


@pytest.mark.parametrize(
    "parca",
    [
        "CHECK (a IN ('x,y', 'z'))",
        "REFERENCES t(a, b)",
        "DEFAULT ','",
        "DEFAULT ';'",
        "DEFAULT '(' -- yorum, virgüllü",
        "CHECK (length(a) > 0 AND a NOT LIKE '%;%')",
        'COLLATE "NO,CASE"',
    ],
)
def test_parantez_ve_tirnak_icindeki_virgul_noktali_virgul_serbest(parca: str) -> None:
    assert m.ozelligi_dogrula(parca) == parca
    assert (
        m.tablo_olusturma_sql(m.TabloOlusturmaIstegi("t", (m.Sutun("a", (parca,)),)))
        == f'CREATE TABLE "t" ("a" {parca})'
    )


def test_motorun_actigi_tabloda_tablo_duzeyi_kisit_olamaz(
    veritabani: vt.Veritabani,
) -> None:
    """README iddiası: özellik parçası sınırı sayesinde motor tablo düzeyi kısıt
    yazamaz; dolayısıyla kendi açtığı tabloda yeniden kurma hiç reddedilmez."""
    m.tablo_olustur(
        veritabani,
        m.TabloOlusturmaIstegi(
            "t",
            (
                m.Sutun("a", ("INTEGER", "PRIMARY KEY")),
                m.Sutun("b", ("TEXT", "UNIQUE", "CHECK (b IN ('x', 'y'))")),
                m.Sutun("c", ("INTEGER", "REFERENCES t(a)")),
            ),
        ),
    )

    m.sutun_ozelligi_degistir(
        veritabani,
        m.SutunOzelligiDegistirmeIstegi(
            "t",
            (
                m.Sutun("a", ("INTEGER", "PRIMARY KEY")),
                m.Sutun("b", ("TEXT", "NOT NULL")),
                m.Sutun("c", ("INTEGER",)),
            ),
        ),
    )

    assert _sutunlar(veritabani, "t")[1] == ("b", "TEXT", 1, None)
