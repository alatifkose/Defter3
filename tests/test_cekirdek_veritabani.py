"""Genel veritabanı altyapısı testleri (Aşama 4.1).

Gerçek SQLite dosyalarıyla, ``test`` ortamında ve ``tmp_path`` altındaki bir
veri köküyle; ``:memory:`` kullanılmaz. Böylece dosya yolu, WAL, dış anahtar
ve işlem sınırı gerçek dosya üzerinde sınanır. Tablolar testin kendi ham SQL
tablolarıdır; uygulama tablosu yoktur.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from defteruc import ayarlar as ay
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
def ayarlar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ay.Ayarlar:
    """Test ortamı, kök ``tmp_path/kok``; dizinler hazır, veritabanı dosyası yok."""
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(tmp_path / "kok"))
    ayar = ay.ayarlari_yukle()
    ay.dizinleri_hazirla(ayar)
    return ayar


@pytest.fixture
def veritabani(ayarlar: ay.Ayarlar) -> Iterator[vt.Veritabani]:
    v = vt.Veritabani(ayarlar.veritabani_yolu)
    yield v
    v.kapat()


def _tablolari_kur(v: vt.Veritabani) -> None:
    with v.islem() as oturum:
        oturum.execute(text("CREATE TABLE ust (id INTEGER PRIMARY KEY)"))
        oturum.execute(
            text(
                "CREATE TABLE alt (id INTEGER PRIMARY KEY, "
                "ust_id INTEGER NOT NULL REFERENCES ust(id))"
            )
        )


def _alt_sayisi(v: vt.Veritabani) -> int:
    with v.islem() as oturum:
        return int(oturum.execute(text("SELECT count(*) FROM alt")).scalar_one())


# --- import ve engine diske dokunmaz ----------------------------------------------


def test_import_ve_motor_kurulumu_dosya_olusturmaz(ayarlar: ay.Ayarlar) -> None:
    motor = vt.motor_olustur(ayarlar.veritabani_yolu)
    v = vt.Veritabani(ayarlar.veritabani_yolu)

    assert not ayarlar.veritabani_yolu.exists()
    assert list(ayarlar.veritabani_yolu.parent.glob("*.sqlite3*")) == []
    motor.dispose()
    v.kapat()


# --- bağlantı adresi yalnız verilen mutlak yoldan ----------------------------------


def test_url_verilen_mutlak_yoldan_uretilir(ayarlar: ay.Ayarlar) -> None:
    url = vt.veritabani_url(ayarlar.veritabani_yolu)

    assert url.drivername == vt.SURUCU
    assert url.database == str(ayarlar.veritabani_yolu)
    assert Path(url.database or "").is_absolute()


def test_goreli_yol_reddedilir() -> None:
    with pytest.raises(ValueError, match="mutlak"):
        vt.veritabani_url(Path("defteruc.sqlite3"))


def test_motor_calisma_dizininden_bagimsiz(
    ayarlar: ay.Ayarlar, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baska = tmp_path / "baska_yer"
    baska.mkdir()
    monkeypatch.chdir(baska)
    v = vt.Veritabani(ayarlar.veritabani_yolu)
    try:
        with v.islem() as oturum:
            oturum.execute(text("SELECT 1"))
    finally:
        v.kapat()

    assert ayarlar.veritabani_yolu.is_file()
    assert list(baska.iterdir()) == []


# --- bağlantı politikası ------------------------------------------------------------


def test_foreign_keys_ve_wal_her_baglantida_acik(veritabani: vt.Veritabani) -> None:
    """İki ayrı fiziksel DBAPI bağlantısı aynı anda açık; ikisinde de politika."""
    with veritabani.motor.connect() as birinci, veritabani.motor.connect() as ikinci:
        ham_birinci = birinci.connection.dbapi_connection
        ham_ikinci = ikinci.connection.dbapi_connection
        assert ham_birinci is not None and ham_ikinci is not None
        assert ham_birinci is not ham_ikinci  # havuzdan aynı bağlantı değil
        for baglanti in (birinci, ikinci):
            assert baglanti.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
            assert baglanti.execute(text("PRAGMA journal_mode")).scalar_one() == "wal"

    veritabani.kapat()  # havuz boşaldı; sonraki bağlantı yeniden kurulur
    with veritabani.islem() as oturum:
        assert oturum.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert oturum.execute(text("PRAGMA journal_mode")).scalar_one() == "wal"


def test_baglanti_modern_transaction_kipinde(veritabani: vt.Veritabani) -> None:
    """``autocommit=False``: bağlantı transaction içinde gelir (DDL de geri alınır)."""
    with veritabani.motor.connect() as baglanti:
        ham = baglanti.connection.dbapi_connection
        assert ham is not None
        assert ham.autocommit is False
        baglanti.execute(text("SELECT 1"))
        assert baglanti.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_hatali_dis_anahtar_yazimi_gercekten_reddedilir(
    veritabani: vt.Veritabani,
) -> None:
    _tablolari_kur(veritabani)

    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with veritabani.islem() as oturum:
            oturum.execute(text("INSERT INTO alt (ust_id) VALUES (999)"))

    assert _alt_sayisi(veritabani) == 0


def test_gecerli_dis_anahtar_yazimi_kabul_edilir(veritabani: vt.Veritabani) -> None:
    _tablolari_kur(veritabani)

    with veritabani.islem() as oturum:
        oturum.execute(text("INSERT INTO ust (id) VALUES (1)"))
        oturum.execute(text("INSERT INTO alt (ust_id) VALUES (1)"))

    assert _alt_sayisi(veritabani) == 1


# --- işlem sınırı --------------------------------------------------------------------


def test_basarili_islem_commit_olur(veritabani: vt.Veritabani) -> None:
    _tablolari_kur(veritabani)

    with veritabani.islem() as oturum:
        oturum.execute(text("INSERT INTO ust (id) VALUES (1)"))
        oturum.execute(text("INSERT INTO alt (ust_id) VALUES (1)"))

    assert _alt_sayisi(veritabani) == 1


def test_hata_alan_islem_tamamen_rollback_olur_ve_hata_yukselir(
    veritabani: vt.Veritabani,
) -> None:
    _tablolari_kur(veritabani)
    acilanlar: list[Session] = []

    with pytest.raises(RuntimeError, match="sentetik"):
        with veritabani.islem() as oturum:
            acilanlar.append(oturum)
            oturum.execute(text("INSERT INTO ust (id) VALUES (1)"))
            oturum.execute(text("INSERT INTO alt (ust_id) VALUES (1)"))
            raise RuntimeError("sentetik hata")

    assert acilanlar[0].in_transaction() is False  # oturum kapandı
    assert _alt_sayisi(veritabani) == 0
    with veritabani.islem() as oturum:
        assert oturum.execute(text("SELECT count(*) FROM ust")).scalar_one() == 0


def test_ddl_de_islem_icinde_geri_alinir(veritabani: vt.Veritabani) -> None:
    """CREATE TABLE transaction içindedir: hata olunca tablo kalmaz."""
    with pytest.raises(RuntimeError, match="sentetik"):
        with veritabani.islem() as oturum:
            oturum.execute(text("CREATE TABLE gecici (id INTEGER PRIMARY KEY)"))
            oturum.execute(text("INSERT INTO gecici (id) VALUES (1)"))
            raise RuntimeError("sentetik hata")

    with veritabani.islem() as oturum:
        tablolar = (
            oturum.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            .scalars()
            .all()
        )
    assert "gecici" not in tablolar


def test_islem_bittiginde_oturum_kapalidir(veritabani: vt.Veritabani) -> None:
    with veritabani.islem() as oturum:
        oturum.execute(text("SELECT 1"))
    assert oturum.in_transaction() is False


# --- test veritabanı izolasyonu ------------------------------------------------------


def test_test_veritabani_yalniz_test_kokunde_olusur(
    ayarlar: ay.Ayarlar, veritabani: vt.Veritabani, tmp_path: Path
) -> None:
    _tablolari_kur(veritabani)

    kok = tmp_path / "kok" / "test"
    assert ayarlar.veritabani_yolu.is_relative_to(kok)
    dosyalar = [d for d in tmp_path.rglob("*") if d.is_file()]
    assert dosyalar, "veritabanı dosyası oluşmalıydı"
    assert all(d.is_relative_to(kok) for d in dosyalar), dosyalar
    assert ayarlar.veritabani_yolu.with_name(
        ayarlar.veritabani_yolu.name + "-wal"
    ).exists()  # WAL gerçekten dosyada


# --- yabancı anahtar denetimsiz işlem sınırı ------------------------------------------


def test_denetimsiz_islemde_denetim_kapali_sonra_yeniden_acik(
    veritabani: vt.Veritabani,
) -> None:
    _tablolari_kur(veritabani)
    with veritabani.islem_yabanci_anahtar_denetimsiz() as oturum:
        assert oturum.execute(text("PRAGMA foreign_keys")).scalar_one() == 0
        oturum.execute(text("INSERT INTO ust (id) VALUES (1)"))
        oturum.execute(text("INSERT INTO alt (ust_id) VALUES (1)"))

    assert _alt_sayisi(veritabani) == 1  # commit oldu
    with veritabani.islem() as oturum:  # aynı havuz bağlantısı; denetim geri açık
        assert oturum.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        with pytest.raises(IntegrityError, match="FOREIGN KEY"):
            oturum.execute(text("INSERT INTO alt (ust_id) VALUES (99)"))


def test_denetimsiz_islem_sonunda_ihlal_varsa_geri_alinir(
    veritabani: vt.Veritabani,
) -> None:
    _tablolari_kur(veritabani)
    with pytest.raises(vt.YabanciAnahtarIhlali, match=r"1 yabancı anahtar ihlali"):
        with veritabani.islem_yabanci_anahtar_denetimsiz() as oturum:
            oturum.execute(text("INSERT INTO alt (ust_id) VALUES (99)"))  # denetim yok

    assert _alt_sayisi(veritabani) == 0
    with veritabani.islem() as oturum:
        assert oturum.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_denetimsiz_islemde_hata_geri_alir_ve_denetimi_acar(
    veritabani: vt.Veritabani,
) -> None:
    _tablolari_kur(veritabani)
    with pytest.raises(RuntimeError, match="kasıtlı"):
        with veritabani.islem_yabanci_anahtar_denetimsiz() as oturum:
            oturum.execute(text("INSERT INTO ust (id) VALUES (1)"))
            raise RuntimeError("kasıtlı")

    with veritabani.islem() as oturum:
        assert oturum.execute(text("SELECT count(*) FROM ust")).scalar_one() == 0
        assert oturum.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
