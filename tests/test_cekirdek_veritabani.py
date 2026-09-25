import sqlite3
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


def test_denetimsiz_islem_baglantiyi_denetim_acilana_kadar_havuza_vermez(
    veritabani: vt.Veritabani,
) -> None:
    """İnceleme 2 bulgusu: Session.commit bağlantıyı denetim yeniden açılmadan
    havuza bırakıyordu; başka bir oturum foreign_keys=0 bağlantı alabiliyordu.
    Şimdi bağlantı iş boyunca sahiplenilir; havuza her dönüşte denetim açık."""
    from sqlalchemy import event

    _tablolari_kur(veritabani)
    donusler: list[int] = []

    def kaydet(dbapi_baglantisi: sqlite3.Connection, _kayit: object) -> None:
        satir = dbapi_baglantisi.execute("PRAGMA foreign_keys").fetchone()
        assert satir is not None
        donusler.append(int(satir[0]))

    event.listen(veritabani.motor, "checkin", kaydet)
    try:
        with veritabani.islem_yabanci_anahtar_denetimsiz() as baglanti:
            baglanti.execute(text("INSERT INTO ust (id) VALUES (1)"))
            with veritabani.islem() as diger:  # aynı anda başka oturum: denetimli
                assert diger.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        with pytest.raises(vt.YabanciAnahtarIhlali):
            with veritabani.islem_yabanci_anahtar_denetimsiz() as baglanti:
                baglanti.execute(text("INSERT INTO alt (ust_id) VALUES (99)"))
        with pytest.raises(RuntimeError):
            with veritabani.islem_yabanci_anahtar_denetimsiz():
                raise RuntimeError("kasıtlı")
    finally:
        event.remove(veritabani.motor, "checkin", kaydet)

    assert len(donusler) >= 4 and all(d == 1 for d in donusler), donusler


@pytest.mark.parametrize("govde_hatasi", [False, True])
def test_denetim_yeniden_acilamazsa_baglanti_havuza_donmez(
    veritabani: vt.Veritabani, govde_hatasi: bool
) -> None:
    """İnceleme 3: PRAGMA foreign_keys=ON düşerse bağlantı FK=0 ile havuza
    dönüyordu. Şimdi bağlantı geçersizleştirilir (havuza dönmez). Gövde
    başarılıysa DenetimGeriAcilamadi yükselir ve commit geri alınmış sayılmaz;
    gövde hatalıysa asıl hata yükselir. Hata enjeksiyonu: sqlite3 authorizer."""
    from sqlalchemy import event

    _tablolari_kur(veritabani)
    donusler: list[int] = []

    def kaydet(dbapi_baglantisi: sqlite3.Connection | None, _kayit: object) -> None:
        if dbapi_baglantisi is None:  # geçersizleştirilmiş bağlantı: havuza dönmedi
            donusler.append(-1)
            return
        satir = dbapi_baglantisi.execute("PRAGMA foreign_keys").fetchone()
        assert satir is not None
        donusler.append(int(satir[0]))

    def yetkilendirici(
        eylem: int, a: str | None, b: str | None, _vt: str | None, _k: str | None
    ) -> int:
        if eylem == sqlite3.SQLITE_PRAGMA and a == "foreign_keys" and b == "ON":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    event.listen(veritabani.motor, "checkin", kaydet)
    hamlar: list[sqlite3.Connection] = []
    try:
        beklenen: type[BaseException] = (
            RuntimeError if govde_hatasi else vt.DenetimGeriAcilamadi
        )
        with pytest.raises(beklenen) as bilgi:
            with veritabani.islem_yabanci_anahtar_denetimsiz() as baglanti:
                baglanti.execute(text("INSERT INTO ust (id) VALUES (1)"))
                ham = baglanti.connection.dbapi_connection
                assert isinstance(ham, sqlite3.Connection)
                hamlar.append(ham)
                ham.set_authorizer(yetkilendirici)
                if govde_hatasi:
                    raise RuntimeError("kasıtlı")
        if govde_hatasi:
            assert any("yeniden açılamadı" in n for n in bilgi.value.__notes__)
    finally:
        event.remove(veritabani.motor, "checkin", kaydet)
        for ham in hamlar:
            try:
                ham.set_authorizer(None)
            except sqlite3.ProgrammingError:  # geçersizleştirilmiş: zaten kapalı
                pass

    assert all(d in (1, -1) for d in donusler), donusler  # FK=0 hiç dönmedi
    with veritabani.islem() as oturum:  # sonraki oturum: yeni, denetimli bağlantı
        assert oturum.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        sayi = oturum.execute(text("SELECT count(*) FROM ust")).scalar_one()
        assert sayi == (0 if govde_hatasi else 1)  # rollback / commit ayrımı korunur
        with pytest.raises(IntegrityError, match="FOREIGN KEY"):
            oturum.execute(text("INSERT INTO alt (ust_id) VALUES (99)"))
