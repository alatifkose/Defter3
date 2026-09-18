"""Göç zinciri ve şema sürümü testleri (Aşama 4.1, 4.2).

Gerçek SQLite dosyaları, ``test`` ortamı, ``tmp_path`` altında kök. Süreç içi
``semayi_yukselt`` ve komut satırı (``alembic upgrade head``) aynı ``env.py``
üzerinden aynı sonucu verir; komut satırı yolu merkezi ayarlardan alır.
Aşama 4.2 ile zincir ``0002`` (tanım tabloları) ve ``0003`` (sürüm numarası
kontrol kısıtı, tablo açık SQL ile yeniden kurulur), Aşama 4.3 ile ``0004``
(nesne tabloları, hiyerarşi kuralı, özellik türü, sürüm kilidi), ``0005``
(genel ilişkide kendine dönüş kısıtı kalkar); ``upgrade →
downgrade → upgrade`` döngüsü, adım adım zincir ve göç şemasının ORM
metadata'sıyla birebirliği sınanır. Bütün göçler geçici test
veritabanlarında çalışır; kalıcı geliştirme veritabanına dokunulmaz.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from defteriki import ayarlar as ay
from defteriki import baslangic, gunluk
from defteriki.cekirdek import gocler
from defteriki.cekirdek import nesne_tablolari as nt
from defteriki.cekirdek import tanim_tablolari as tt
from defteriki.cekirdek import veritabani as vt

DEFTERIKI_DEGISKENLERI = (
    ay.ORTAM_DEGISKENI,
    ay.VERI_KOKU_DEGISKENI,
    ay.VERITABANI_YOLU_DEGISKENI,
    ay.BELGE_DIZINI_DEGISKENI,
    ay.LOG_DIZINI_DEGISKENI,
    ay.GELEN_DIZINI_DEGISKENI,
)
BEKLEME_SANIYE = 120
BASLANGIC_SURUMU = "0001"
GUNCEL_SURUM = "0005"
NESNE_SURUMU = "0004"
TANIM_SURUMU = "0002"
KISIT_SURUMU = "0003"
UYGULAMA_TABLOLARI = (*tt.TANIM_TABLOLARI, *nt.NESNE_TABLOLARI)
GUNCEL_TABLOLAR = sorted((gocler.SURUM_TABLOSU, *UYGULAMA_TABLOLARI))


@pytest.fixture(autouse=True)
def temiz_cevre(monkeypatch: pytest.MonkeyPatch) -> None:
    for degisken in DEFTERIKI_DEGISKENLERI:
        monkeypatch.delenv(degisken, raising=False)
    gunluk.gunlugu_kapat()


def _test_ayarlari(kok: Path, monkeypatch: pytest.MonkeyPatch) -> ay.Ayarlar:
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(kok))
    ayar = ay.ayarlari_yukle()
    ay.dizinleri_hazirla(ayar)
    return ayar


def _sema(v: vt.Veritabani) -> list[tuple[str, str, str | None]]:
    """``sqlite_master`` içeriği: tür, ad, SQL (sırayla)."""
    with v.islem() as oturum:
        satirlar = oturum.execute(
            text(
                "SELECT type, name, sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
            )
        ).all()
    return [(str(t), str(a), s) for t, a, s in satirlar]


def _yukselt(
    kok: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, list[tuple[str, str, str | None]]]:
    ayar = _test_ayarlari(kok, monkeypatch)
    v = vt.Veritabani(ayar.veritabani_yolu)
    try:
        surum = gocler.semayi_yukselt(v)
        return surum, _sema(v)
    finally:
        v.kapat()


# --- süreç içi -----------------------------------------------------------------------


def test_sifir_veritabanindan_upgrade_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ayar = _test_ayarlari(tmp_path / "kok", monkeypatch)
    v = vt.Veritabani(ayar.veritabani_yolu)
    try:
        assert gocler.sema_surumu(v) is None  # göç yok; dosya boş açıldı

        surum = gocler.semayi_yukselt(v)

        assert surum == GUNCEL_SURUM == gocler.beklenen_sema_surumu()
        assert gocler.sema_surumu(v) == GUNCEL_SURUM
        tablolar = [ad for tur, ad, _ in _sema(v) if tur == "table"]
        assert tablolar == GUNCEL_TABLOLAR  # sürüm tablosu + tanım tabloları
    finally:
        v.kapat()


def test_iki_sifir_veritabani_ayni_semayi_uretir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    birinci = _yukselt(tmp_path / "a", monkeypatch)
    ikinci = _yukselt(tmp_path / "b", monkeypatch)

    assert birinci == ikinci
    assert birinci[0] == GUNCEL_SURUM


def test_tekrar_upgrade_semayi_degistirmez(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ayar = _test_ayarlari(tmp_path / "kok", monkeypatch)
    v = vt.Veritabani(ayar.veritabani_yolu)
    try:
        gocler.semayi_yukselt(v)
        once = _sema(v)
        assert gocler.semayi_yukselt(v) == GUNCEL_SURUM
        assert _sema(v) == once
    finally:
        v.kapat()


# --- Aşama 4.2: downgrade döngüsü ve şema/ORM birebirliği -----------------------------


def test_upgrade_downgrade_upgrade_dongusu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``head`` → ``0001`` → ``head``: tanım tabloları gider, gelir; şema aynı kalır.
    ``0003``ün batch kipi de geri alınır (``0002``nin kısıtı döner)."""
    ayar = _test_ayarlari(tmp_path / "kok", monkeypatch)
    v = vt.Veritabani(ayar.veritabani_yolu)
    alembic = gocler.alembic_ayari()
    try:
        assert gocler.semayi_yukselt(v) == GUNCEL_SURUM
        tam_sema = _sema(v)

        with v.motor.begin() as baglanti:
            alembic.attributes["connection"] = baglanti
            command.downgrade(alembic, BASLANGIC_SURUMU)

        assert gocler.sema_surumu(v) == BASLANGIC_SURUMU
        assert [ad for tur, ad, _ in _sema(v) if tur == "table"] == [
            gocler.SURUM_TABLOSU
        ]
        assert [ad for tur, ad, _ in _sema(v) if tur == "index"] == []

        assert gocler.semayi_yukselt(v) == GUNCEL_SURUM
        assert _sema(v) == tam_sema
        with v.islem() as oturum:
            assert oturum.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"
    finally:
        v.kapat()


def test_goc_semasi_orm_metadata_ile_birebir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Elle yazılan ``0002`` + ``0003`` göçleri ile ``tanim_tablolari`` aynı şemayı
    üretir:
    Alembic karşılaştırması (tablo, sütun, tip, null, dış anahtar, benzersizlik,
    indeks) fark bulmaz."""
    ayar = _test_ayarlari(tmp_path / "kok", monkeypatch)
    v = vt.Veritabani(ayar.veritabani_yolu)
    try:
        gocler.semayi_yukselt(v)
        with v.motor.connect() as baglanti:
            baglam = MigrationContext.configure(
                baglanti, opts={"compare_type": True, "render_as_batch": True}
            )
            farklar = compare_metadata(baglam, vt.TabloTabani.metadata)
        assert farklar == []
        assert set(tt.TANIM_TABLOLARI) <= set(vt.TabloTabani.metadata.tables)
    finally:
        v.kapat()


def test_tanim_tablolarinin_kisitlari_isimli_ve_tam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ayar = _test_ayarlari(tmp_path / "kok", monkeypatch)
    v = vt.Veritabani(ayar.veritabani_yolu)
    try:
        gocler.semayi_yukselt(v)
        with v.motor.connect() as baglanti:
            denetci = inspect(baglanti)
            for tablo in UYGULAMA_TABLOLARI:
                assert denetci.get_pk_constraint(tablo)["name"] == f"pk_{tablo}"
                assert denetci.get_pk_constraint(tablo)["constrained_columns"] == ["id"]
                for fk in denetci.get_foreign_keys(tablo):
                    assert str(fk["name"]).startswith(f"fk_{tablo}_"), fk
                    assert fk.get("options", {}).get("ondelete") == "RESTRICT", fk
                for uq in denetci.get_unique_constraints(tablo):
                    assert str(uq["name"]).startswith(f"uq_{tablo}_"), uq
                for ck in denetci.get_check_constraints(tablo):
                    assert str(ck["name"]).startswith(f"ck_{tablo}_"), ck
                for ix in denetci.get_indexes(tablo):
                    assert str(ix["name"]).startswith(f"ix_{tablo}_"), ix
            dis_anahtarlar = {
                tablo: sorted(str(fk["name"]) for fk in denetci.get_foreign_keys(tablo))
                for tablo in UYGULAMA_TABLOLARI
            }
            assert dis_anahtarlar == {
                "tanim_paketi": [],
                "tanim_surumu": ["fk_tanim_surumu_tanim_paketi_id_tanim_paketi"],
                "nesne_turu": ["fk_nesne_turu_tanim_surumu_id_tanim_surumu"],
                "ozellik_tanimi": ["fk_ozellik_tanimi_nesne_turu_id_nesne_turu"],
                "iliski_tanimi": [
                    "fk_iliski_tanimi_hedef_nesne_turu_id_tanim_surumu_id_nesne_turu",
                    "fk_iliski_tanimi_kaynak_nesne_turu_id_tanim_surumu_id_nesne_turu",
                    "fk_iliski_tanimi_tanim_surumu_id_tanim_surumu",
                ],
                "kayit_turu": ["fk_kayit_turu_tanim_surumu_id_tanim_surumu"],
                "kayit_alani_tanimi": [
                    "fk_kayit_alani_tanimi_kayit_turu_id_kayit_turu"
                ],
                "hiyerarsi_kurali": [
                    "fk_hiyerarsi_kurali_iliski_tanimi_id_iliski_tanimi"
                ],
                "nesne": ["fk_nesne_nesne_turu_id_tanim_surumu_id_nesne_turu"],
                "nesne_ozelligi": [
                    "fk_nesne_ozelligi_nesne_id_nesne_turu_id_nesne",
                    "fk_nesne_ozelligi_ozellik_tanimi_id_nesne_turu_id_ozellik_tanimi",
                ],
                "nesne_iliskisi": [
                    "fk_nesne_iliskisi_hedef_nesne_id_hedef_nesne_turu_id_"
                    "tanim_surumu_id_nesne",
                    "fk_nesne_iliskisi_iliski_tanimi_id_tanim_surumu_id_"
                    "kaynak_nesne_turu_id_hedef_nesne_turu_id_iliski_tanimi",
                    "fk_nesne_iliskisi_kaynak_nesne_id_kaynak_nesne_turu_id_"
                    "tanim_surumu_id_nesne",
                ],
            }
            benzersizler = {
                tablo: sorted(
                    str(uq["name"]) for uq in denetci.get_unique_constraints(tablo)
                )
                for tablo in UYGULAMA_TABLOLARI
            }
            assert benzersizler == {
                "tanim_paketi": ["uq_tanim_paketi_kod"],
                "tanim_surumu": ["uq_tanim_surumu_tanim_paketi_id_surum_no"],
                "nesne_turu": [
                    "uq_nesne_turu_id_tanim_surumu_id",
                    "uq_nesne_turu_tanim_surumu_id_kod",
                ],
                "ozellik_tanimi": [
                    "uq_ozellik_tanimi_id_nesne_turu_id",
                    "uq_ozellik_tanimi_nesne_turu_id_kod",
                ],
                "iliski_tanimi": ["uq_iliski_tanimi_tanim_surumu_id_kod"],
                "kayit_turu": ["uq_kayit_turu_tanim_surumu_id_kod"],
                "kayit_alani_tanimi": ["uq_kayit_alani_tanimi_kayit_turu_id_kod"],
                "hiyerarsi_kurali": ["uq_hiyerarsi_kurali_iliski_tanimi_id"],
                "nesne": [
                    "uq_nesne_id_nesne_turu_id",
                    "uq_nesne_id_nesne_turu_id_tanim_surumu_id",
                ],
                "nesne_ozelligi": ["uq_nesne_ozelligi_nesne_id_ozellik_tanimi_id"],
                "nesne_iliskisi": [
                    "uq_nesne_iliskisi_iliski_tanimi_id_kaynak_nesne_id_hedef_nesne_id"
                ],
            }
            assert sorted(
                str(ix["name"]) for ix in denetci.get_indexes("iliski_tanimi")
            ) == [
                "ix_iliski_tanimi_hedef_nesne_turu_id",
                "ix_iliski_tanimi_id_tanim_surumu_id_kaynak_nesne_turu_id_"
                "hedef_nesne_turu_id",
                "ix_iliski_tanimi_kaynak_nesne_turu_id",
            ]
            [bilesik] = [
                ix
                for ix in denetci.get_indexes("iliski_tanimi")
                if str(ix["name"]).startswith("ix_iliski_tanimi_id_")
            ]
            assert bilesik["unique"]
            kontroller = {
                tablo: sorted(
                    str(ck["name"]) for ck in denetci.get_check_constraints(tablo)
                )
                for tablo in UYGULAMA_TABLOLARI
            }
            assert kontroller == {
                "tanim_paketi": [],
                "tanim_surumu": [
                    "ck_tanim_surumu_kilitli_ikili",
                    "ck_tanim_surumu_surum_no_pozitif_tamsayi",
                ],
                "nesne_turu": [],
                "ozellik_tanimi": [
                    "ck_ozellik_tanimi_deger_turu_gecerli",
                    "ck_ozellik_tanimi_zorunlu_ikili",
                ],
                "iliski_tanimi": [],
                "hiyerarsi_kurali": [
                    "ck_hiyerarsi_kurali_en_az_ust_dogal",
                    "ck_hiyerarsi_kurali_en_cok_ust_tutarli",
                    "ck_hiyerarsi_kurali_ust_yasam_durumu_gecerli",
                ],
                "kayit_turu": [],
                "kayit_alani_tanimi": [],
                "nesne": ["ck_nesne_yasam_durumu_gecerli"],
                "nesne_ozelligi": [],
                "nesne_iliskisi": [],
            }
            indeksler = {
                tablo: sorted(str(ix["name"]) for ix in denetci.get_indexes(tablo))
                for tablo in nt.NESNE_TABLOLARI
            }
            assert indeksler == {
                "nesne": ["ix_nesne_nesne_turu_id", "ix_nesne_tanim_surumu_id"],
                "nesne_ozelligi": ["ix_nesne_ozelligi_ozellik_tanimi_id"],
                "nesne_iliskisi": [
                    "ix_nesne_iliskisi_hedef_nesne_id",
                    "ix_nesne_iliskisi_kaynak_nesne_id",
                ],
            }
    finally:
        v.kapat()


def _kontrol_kisitlari(v: vt.Veritabani, tablo: str) -> list[tuple[str, str]]:
    with v.motor.connect() as baglanti:
        return sorted(
            (str(ck["name"]), str(ck["sqltext"]))
            for ck in inspect(baglanti).get_check_constraints(tablo)
        )


def _cocuk_sayilari(oturum: Session) -> tuple[int, int, int]:
    """``tanim_surumu``ya bağlı satır sayıları: nesne türü, kayıt türü, ilişki."""
    return (
        int(oturum.execute(text("SELECT count(*) FROM nesne_turu")).scalar_one()),
        int(oturum.execute(text("SELECT count(*) FROM kayit_turu")).scalar_one()),
        int(oturum.execute(text("SELECT count(*) FROM iliski_tanimi")).scalar_one()),
    )


def test_zincir_adim_adim_0001_0002_0003_0004_0005_ve_geri(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``0001 → 0002 → 0003 → 0004 → 0005 → 0002 → 0001 → head``: her adımda sürüm ve
    ``tanim_surumu`` kontrol kısıtı beklenen; ``0003``ün tablo yeniden kurması
    ``0002``de yazılmış satırı ve diğer kısıt adlarını korur; ``0002``de kabul
    edilen REAL sürüm numarası ``0003``te reddedilir."""
    ayar = _test_ayarlari(tmp_path / "kok", monkeypatch)
    v = vt.Veritabani(ayar.veritabani_yolu)
    alembic = gocler.alembic_ayari()
    eski_kisit = [("ck_tanim_surumu_surum_no_pozitif", "surum_no > 0")]
    yeni_kisit = [
        (
            "ck_tanim_surumu_surum_no_pozitif_tamsayi",
            "typeof(surum_no) = 'integer' AND surum_no > 0",
        )
    ]
    ekle = text(
        "INSERT INTO tanim_surumu (tanim_paketi_id, surum_no, olusturma_zamani) "
        "VALUES (1, :no, '2026-09-18 00:00:00')"
    )

    def goc(hedef: str, geri: bool = False) -> None:
        with v.motor.begin() as baglanti:
            alembic.attributes["connection"] = baglanti
            (command.downgrade if geri else command.upgrade)(alembic, hedef)

    try:
        goc(BASLANGIC_SURUMU)
        assert gocler.sema_surumu(v) == BASLANGIC_SURUMU
        assert [ad for tur, ad, _ in _sema(v) if tur == "table"] == [
            gocler.SURUM_TABLOSU
        ]

        goc(TANIM_SURUMU)
        assert gocler.sema_surumu(v) == TANIM_SURUMU
        assert _kontrol_kisitlari(v, "tanim_surumu") == eski_kisit
        with v.islem() as oturum:
            oturum.execute(
                text(
                    "INSERT INTO tanim_paketi (kod, gosterim_adi, olusturma_zamani) "
                    "VALUES ('DEMO', 'Demo', '2026-09-18 00:00:00')"
                )
            )
            oturum.execute(ekle, {"no": 1})
            # Çocuk satırlar (FK açıkken tablo yeniden kurmanın asıl sınavı)
            oturum.execute(
                text(
                    "INSERT INTO nesne_turu (tanim_surumu_id, kod, gosterim_adi) "
                    "VALUES (1, 'TEST_KISI', 'Kişi')"
                )
            )
            oturum.execute(
                text(
                    "INSERT INTO kayit_turu (tanim_surumu_id, kod, gosterim_adi) "
                    "VALUES (1, 'TEST_OLAY', 'Olay')"
                )
            )
            oturum.execute(
                text(
                    "INSERT INTO iliski_tanimi (tanim_surumu_id, kod, gosterim_adi, "
                    "kaynak_nesne_turu_id, hedef_nesne_turu_id) "
                    "VALUES (1, 'TANIR', 'Tanır', 1, 1)"
                )
            )
        with v.islem() as oturum:  # 0002'nin açığı: REAL geçer
            oturum.execute(ekle, {"no": 2.5})
        with v.islem() as oturum:
            oturum.execute(text("DELETE FROM tanim_surumu WHERE surum_no = 2.5"))

        goc(KISIT_SURUMU)
        assert gocler.sema_surumu(v) == KISIT_SURUMU
        assert _kontrol_kisitlari(v, "tanim_surumu") == yeni_kisit
        with v.motor.connect() as baglanti:
            denetci = inspect(baglanti)
            assert (
                denetci.get_pk_constraint("tanim_surumu")["name"] == "pk_tanim_surumu"
            )
            assert [fk["name"] for fk in denetci.get_foreign_keys("tanim_surumu")] == [
                "fk_tanim_surumu_tanim_paketi_id_tanim_paketi"
            ]
            assert [
                uq["name"] for uq in denetci.get_unique_constraints("tanim_surumu")
            ] == ["uq_tanim_surumu_tanim_paketi_id_surum_no"]
        with v.islem() as oturum:  # satır taşındı, çocuklar yerinde, FK temiz
            assert oturum.execute(
                text("SELECT tanim_paketi_id, surum_no FROM tanim_surumu")
            ).all() == [(1, 1)]
            assert _cocuk_sayilari(oturum) == (1, 1, 1)
            assert oturum.execute(text("PRAGMA foreign_key_check")).all() == []
            assert [
                ad
                for (ad,) in oturum.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE name LIKE 'tanim_surumu%'"
                    )
                ).all()
            ] == ["tanim_surumu"]  # geçici tablolar kalmadı
        with pytest.raises(IntegrityError, match="surum_no_pozitif_tamsayi"):
            with v.islem() as oturum:
                oturum.execute(ekle, {"no": 2.5})

        goc(NESNE_SURUMU)
        assert gocler.sema_surumu(v) == NESNE_SURUMU
        assert [ad for ad, _ in _kontrol_kisitlari(v, "tanim_surumu")] == [
            "ck_tanim_surumu_kilitli_ikili",
            "ck_tanim_surumu_surum_no_pozitif_tamsayi",
        ]
        assert [ad for ad, _ in _kontrol_kisitlari(v, "nesne_iliskisi")] == [
            "ck_nesne_iliskisi_kendine_degil"
        ]
        with v.islem() as oturum:
            assert _cocuk_sayilari(oturum) == (1, 1, 1)
            assert oturum.execute(text("PRAGMA foreign_key_check")).all() == []

        goc(GUNCEL_SURUM)
        assert gocler.sema_surumu(v) == GUNCEL_SURUM
        assert _kontrol_kisitlari(v, "nesne_iliskisi") == []
        with v.islem() as oturum:
            assert _cocuk_sayilari(oturum) == (1, 1, 1)
            assert oturum.execute(text("PRAGMA foreign_key_check")).all() == []

        goc(TANIM_SURUMU, geri=True)
        assert gocler.sema_surumu(v) == TANIM_SURUMU
        assert _kontrol_kisitlari(v, "tanim_surumu") == eski_kisit
        with v.islem() as oturum:  # satır ve çocuklar yine yerinde
            assert oturum.execute(text("SELECT surum_no FROM tanim_surumu")).all() == [
                (1,)
            ]
            assert _cocuk_sayilari(oturum) == (1, 1, 1)
            assert oturum.execute(text("PRAGMA foreign_key_check")).all() == []

        goc(BASLANGIC_SURUMU, geri=True)
        assert gocler.sema_surumu(v) == BASLANGIC_SURUMU

        assert gocler.semayi_yukselt(v) == GUNCEL_SURUM
        assert [ad for ad, _ in _kontrol_kisitlari(v, "tanim_surumu")] == [
            "ck_tanim_surumu_kilitli_ikili",
            "ck_tanim_surumu_surum_no_pozitif_tamsayi",
        ]
        with v.islem() as oturum:
            assert oturum.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"
    finally:
        v.kapat()


def test_0003_0004_gecisi_verili_tabloyu_korur(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``0003``te yazılmış tanımlar ``0004``e taşınır (özellik tanımı yeniden
    kurulurken satırlar kalır, yeni sütunlar varsayılan alır, kilit 0), geçici
    tablo kalmaz; ``0004 → 0003`` geri alınınca sütunlar gider satırlar kalır;
    tekrar ``head`` sıfırdan kurulanla aynı şemayı verir."""
    ayar = _test_ayarlari(tmp_path / "kok", monkeypatch)
    v = vt.Veritabani(ayar.veritabani_yolu)
    alembic = gocler.alembic_ayari()

    def goc(hedef: str, geri: bool = False) -> None:
        with v.motor.begin() as baglanti:
            alembic.attributes["connection"] = baglanti
            (command.downgrade if geri else command.upgrade)(alembic, hedef)

    def sutunlar(tablo: str) -> list[str]:
        with v.motor.connect() as baglanti:
            return [str(c["name"]) for c in inspect(baglanti).get_columns(tablo)]

    try:
        goc(KISIT_SURUMU)
        with v.islem() as oturum:
            oturum.execute(
                text(
                    "INSERT INTO tanim_paketi (kod, gosterim_adi, olusturma_zamani) "
                    "VALUES ('DEMO', 'Demo', '2026-09-18 00:00:00')"
                )
            )
            oturum.execute(
                text(
                    "INSERT INTO tanim_surumu (tanim_paketi_id, surum_no, "
                    "olusturma_zamani) VALUES (1, 1, '2026-09-18 00:00:00')"
                )
            )
            oturum.execute(
                text(
                    "INSERT INTO nesne_turu (tanim_surumu_id, kod, gosterim_adi) "
                    "VALUES (1, 'TEST_CIHAZ', 'Cihaz')"
                )
            )
            oturum.execute(
                text(
                    "INSERT INTO ozellik_tanimi (nesne_turu_id, kod, gosterim_adi, "
                    "aciklama) VALUES (1, 'seri_no', 'Seri', 'eski'), "
                    "(1, 'model', 'Model', NULL)"
                )
            )
            oturum.execute(
                text(
                    "INSERT INTO iliski_tanimi (tanim_surumu_id, kod, gosterim_adi, "
                    "kaynak_nesne_turu_id, hedef_nesne_turu_id) "
                    "VALUES (1, 'TANIR', 'Tanır', 1, 1)"
                )
            )

        goc(GUNCEL_SURUM)
        assert gocler.sema_surumu(v) == GUNCEL_SURUM
        assert sutunlar("ozellik_tanimi")[-2:] == ["deger_turu", "zorunlu"]
        assert sutunlar("tanim_surumu")[-1] == "kilitli"
        with v.islem() as oturum:
            assert oturum.execute(
                text(
                    "SELECT id, kod, aciklama, deger_turu, zorunlu FROM ozellik_tanimi "
                    "ORDER BY id"
                )
            ).all() == [
                (1, "seri_no", "eski", "metin", 0),
                (2, "model", None, "metin", 0),
            ]
            assert (
                oturum.execute(text("SELECT kilitli FROM tanim_surumu")).scalar_one()
                == 0
            )
            assert (
                oturum.execute(text("SELECT count(*) FROM iliski_tanimi")).scalar_one()
                == 1
            )
            assert [
                ad
                for (ad,) in oturum.execute(
                    text(
                        "SELECT name FROM sqlite_master "
                        "WHERE name LIKE 'ozellik_tanimi%'"
                    )
                ).all()
            ] == ["ozellik_tanimi"]
            assert oturum.execute(text("PRAGMA foreign_key_check")).all() == []
        with pytest.raises(IntegrityError, match="CHECK constraint failed"):
            with v.islem() as oturum:
                oturum.execute(text("UPDATE tanim_surumu SET kilitli = 2"))
        tam_sema = _sema(v)

        goc(KISIT_SURUMU, geri=True)
        assert gocler.sema_surumu(v) == KISIT_SURUMU
        assert "deger_turu" not in sutunlar("ozellik_tanimi")
        assert "kilitli" not in sutunlar("tanim_surumu")
        with v.islem() as oturum:
            assert oturum.execute(
                text("SELECT kod FROM ozellik_tanimi ORDER BY id")
            ).scalars().all() == ["seri_no", "model"]
            tablolar = (
                oturum.execute(
                    text("SELECT name FROM sqlite_master WHERE type = 'table'")
                )
                .scalars()
                .all()
            )
            assert not any(
                t.startswith("nesne") and t != "nesne_turu" for t in tablolar
            )
            assert "hiyerarsi_kurali" not in tablolar

        goc(GUNCEL_SURUM)
        assert _sema(v) == tam_sema
        assert _sema(v) == _yukselt(tmp_path / "sifir", monkeypatch)[1]
        with v.islem() as oturum:
            assert oturum.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"
            assert oturum.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        v.kapat()


def test_0003_tam_sayi_olmayan_surum_no_varken_dusmez_geri_alinir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``0002`` şemasında kalmış ``2.5`` gibi bir değer sessizce dönüştürülmez:
    ``0003`` geri yazma adımında kısıt hatası verir, sürüm ``0002``de kalır,
    eski tablo ve satırlar olduğu gibi durur, geçici tablo kalmaz."""
    ayar = _test_ayarlari(tmp_path / "kok", monkeypatch)
    v = vt.Veritabani(ayar.veritabani_yolu)
    alembic = gocler.alembic_ayari()
    try:
        with v.motor.begin() as baglanti:
            alembic.attributes["connection"] = baglanti
            command.upgrade(alembic, TANIM_SURUMU)
        with v.islem() as oturum:
            oturum.execute(
                text(
                    "INSERT INTO tanim_paketi (kod, gosterim_adi, olusturma_zamani) "
                    "VALUES ('DEMO', 'Demo', '2026-09-18 00:00:00')"
                )
            )
            oturum.execute(
                text(
                    "INSERT INTO tanim_surumu "
                    "(tanim_paketi_id, surum_no, olusturma_zamani) "
                    "VALUES (1, 2.5, '2026-09-18 00:00:00')"
                )
            )

        with pytest.raises(IntegrityError, match="surum_no_pozitif_tamsayi"):
            with v.motor.begin() as baglanti:
                alembic.attributes["connection"] = baglanti
                command.upgrade(alembic, "head")

        assert gocler.sema_surumu(v) == TANIM_SURUMU
        assert _kontrol_kisitlari(v, "tanim_surumu") == [
            ("ck_tanim_surumu_surum_no_pozitif", "surum_no > 0")
        ]
        with v.islem() as oturum:
            assert oturum.execute(
                text("SELECT surum_no, typeof(surum_no) FROM tanim_surumu")
            ).all() == [(2.5, "real")]
            assert [
                ad
                for (ad,) in oturum.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE name LIKE 'tanim_surumu%'"
                    )
                ).all()
            ] == ["tanim_surumu"]
            assert oturum.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"
    finally:
        v.kapat()


def test_0004_0005_gecisi_iliski_satirlarini_korur(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``0004``te yazılmış nesne ilişkisi ``0005``e taşınır, kendine dönen satır
    artık kabul edilir, indeksler ve kısıt adları korunur, geçici tablo kalmaz;
    ``head → 0004`` kendine dönen satır varken düşer ve geri alınır, satır
    silinince geri alınır ve kısıt döner; tekrar ``head`` sıfırdan kurulanla
    aynı şemayı verir."""
    ayar = _test_ayarlari(tmp_path / "kok", monkeypatch)
    v = vt.Veritabani(ayar.veritabani_yolu)
    alembic = gocler.alembic_ayari()

    def goc(hedef: str, geri: bool = False) -> None:
        with v.motor.begin() as baglanti:
            alembic.attributes["connection"] = baglanti
            (command.downgrade if geri else command.upgrade)(alembic, hedef)

    ekle = text(
        "INSERT INTO nesne_iliskisi (iliski_tanimi_id, tanim_surumu_id, "
        "kaynak_nesne_turu_id, hedef_nesne_turu_id, kaynak_nesne_id, hedef_nesne_id) "
        "VALUES (1, 1, 1, 1, :k, :h)"
    )
    try:
        goc(NESNE_SURUMU)
        with v.islem() as oturum:
            for sql in (
                "INSERT INTO tanim_paketi (kod, gosterim_adi, olusturma_zamani) "
                "VALUES ('DEMO', 'Demo', '2026-09-18 00:00:00')",
                "INSERT INTO tanim_surumu (tanim_paketi_id, surum_no, "
                "olusturma_zamani) VALUES (1, 1, '2026-09-18 00:00:00')",
                "INSERT INTO nesne_turu (tanim_surumu_id, kod, gosterim_adi) "
                "VALUES (1, 'TEST_KISI', 'Kişi')",
                "INSERT INTO iliski_tanimi (tanim_surumu_id, kod, gosterim_adi, "
                "kaynak_nesne_turu_id, hedef_nesne_turu_id) "
                "VALUES (1, 'TANIR', 'Tanır', 1, 1)",
                "INSERT INTO nesne (nesne_turu_id, tanim_surumu_id, yasam_durumu, "
                "olusturma_zamani) VALUES (1, 1, 'etkin', '2026-09-18'), "
                "(1, 1, 'etkin', '2026-09-18')",
            ):
                oturum.execute(text(sql))
            oturum.execute(ekle, {"k": 1, "h": 2})
        with pytest.raises(IntegrityError, match="kendine_degil"):
            with v.islem() as oturum:
                oturum.execute(ekle, {"k": 1, "h": 1})

        goc(GUNCEL_SURUM)
        assert gocler.sema_surumu(v) == GUNCEL_SURUM
        with v.islem() as oturum:
            assert oturum.execute(
                text("SELECT kaynak_nesne_id, hedef_nesne_id FROM nesne_iliskisi")
            ).all() == [(1, 2)]
            oturum.execute(ekle, {"k": 1, "h": 1})  # artık kabul
            assert [
                ad
                for (ad,) in oturum.execute(
                    text(
                        "SELECT name FROM sqlite_master "
                        "WHERE name LIKE 'nesne_iliskisi%'"
                    )
                ).all()
            ] == ["nesne_iliskisi"]
            assert oturum.execute(text("PRAGMA foreign_key_check")).all() == []
        with v.motor.connect() as baglanti:
            denetci = inspect(baglanti)
            assert denetci.get_check_constraints("nesne_iliskisi") == []
            assert sorted(
                str(ix["name"]) for ix in denetci.get_indexes("nesne_iliskisi")
            ) == [
                "ix_nesne_iliskisi_hedef_nesne_id",
                "ix_nesne_iliskisi_kaynak_nesne_id",
            ]
            assert sorted(
                str(fk["name"]) for fk in denetci.get_foreign_keys("nesne_iliskisi")
            ) == [
                "fk_nesne_iliskisi_hedef_nesne_id_hedef_nesne_turu_id_tanim_surumu_id_nesne",
                "fk_nesne_iliskisi_iliski_tanimi_id_tanim_surumu_id_"
                "kaynak_nesne_turu_id_hedef_nesne_turu_id_iliski_tanimi",
                "fk_nesne_iliskisi_kaynak_nesne_id_kaynak_nesne_turu_id_tanim_surumu_id_nesne",
            ]
        tam_sema = _sema(v)

        with pytest.raises(
            IntegrityError, match="kendine_degil"
        ):  # kendine dönen satır var
            goc(NESNE_SURUMU, geri=True)
        assert gocler.sema_surumu(v) == GUNCEL_SURUM  # geri alma uygulanmadı
        assert _sema(v) == tam_sema
        with v.islem() as oturum:
            assert (
                oturum.execute(text("SELECT count(*) FROM nesne_iliskisi")).scalar_one()
                == 2
            )
            oturum.execute(
                text(
                    "DELETE FROM nesne_iliskisi WHERE kaynak_nesne_id = hedef_nesne_id"
                )
            )

        goc(NESNE_SURUMU, geri=True)
        assert gocler.sema_surumu(v) == NESNE_SURUMU
        assert [ad for ad, _ in _kontrol_kisitlari(v, "nesne_iliskisi")] == [
            "ck_nesne_iliskisi_kendine_degil"
        ]
        with v.islem() as oturum:
            assert oturum.execute(
                text("SELECT kaynak_nesne_id, hedef_nesne_id FROM nesne_iliskisi")
            ).all() == [(1, 2)]

        goc(GUNCEL_SURUM)
        assert _sema(v) == tam_sema
        assert _sema(v) == _yukselt(tmp_path / "sifir", monkeypatch)[1]
        with v.islem() as oturum:
            assert oturum.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"
            assert oturum.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        v.kapat()


SENTETIK_GOC_BIR = '''"""sentetik: tablo oluşturur"""
revision = "s1"
down_revision = None
branch_labels = None
depends_on = None

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.create_table("sentetik_bir", sa.Column("id", sa.Integer(), primary_key=True))
    op.execute("INSERT INTO sentetik_bir (id) VALUES (1)")


def downgrade() -> None:
    op.drop_table("sentetik_bir")
'''

SENTETIK_GOC_IKI = '''"""sentetik: tablo oluşturur, sonra bilinçli düşer"""
revision = "s2"
down_revision = "s1"
branch_labels = None
depends_on = None

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.create_table("sentetik_iki", sa.Column("id", sa.Integer(), primary_key=True))
    raise RuntimeError("sentetik göç hatası")


def downgrade() -> None:
    op.drop_table("sentetik_iki")
'''


def _sentetik_goc_dizini(tmp_path: Path) -> Path:
    """Gerçek ``env.py`` ve şablonla, iki sentetik göçlü ayrı bir göç dizini.

    Gerçek ``0001_genel_altyapi`` zincirine dokunulmaz.
    """
    dizin = tmp_path / "sentetik_goc"
    (dizin / "versions").mkdir(parents=True)
    for ad in ("env.py", "script.py.mako"):
        (dizin / ad).write_bytes((gocler.GOC_DIZINI / ad).read_bytes())
    (dizin / "versions" / "s1_sentetik.py").write_text(SENTETIK_GOC_BIR, "utf-8")
    (dizin / "versions" / "s2_sentetik.py").write_text(SENTETIK_GOC_IKI, "utf-8")
    return dizin


def test_dusen_goc_adimi_ddl_dahil_tamamen_geri_alinir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """İkinci sentetik göç düşünce birinci göçün tablosu da kalmaz, sürüm ilerlemez,
    veritabanı kullanılabilir kalır."""
    ayar = _test_ayarlari(tmp_path / "kok", monkeypatch)
    v = vt.Veritabani(ayar.veritabani_yolu)
    sentetik = gocler.alembic_ayari()
    sentetik.set_main_option("script_location", str(_sentetik_goc_dizini(tmp_path)))
    try:
        with pytest.raises(RuntimeError, match="sentetik göç hatası"):
            with v.motor.begin() as baglanti:
                sentetik.attributes["connection"] = baglanti
                command.upgrade(sentetik, "head")

        tablolar = [ad for tur, ad, _ in _sema(v) if tur == "table"]
        assert "sentetik_bir" not in tablolar  # s1'in DDL'i de geri alındı
        assert "sentetik_iki" not in tablolar
        assert gocler.sema_surumu(v) is None  # sürüm ilerlemedi
        assert tablolar == []  # alembic_version bile yazılmadı

        assert gocler.semayi_yukselt(v) == GUNCEL_SURUM  # veritabanı kullanılabilir
        with v.islem() as oturum:
            assert oturum.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"
    finally:
        v.kapat()


def test_baslangic_goc_calistirmaz(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``uv run defteriki`` hazırlığı veritabanı dosyası oluşturmaz, göç uygulamaz."""
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(tmp_path / "kok"))

    ayar, _ = baslangic.ortami_hazirla()

    assert not ayar.veritabani_yolu.exists()
    assert list(ayar.veritabani_yolu.parent.glob("*.sqlite3*")) == []


def test_alembic_ini_veritabani_adresi_tasimaz() -> None:
    metin = gocler.ALEMBIC_INI.read_text(encoding="utf-8")
    assert "sqlalchemy.url" not in metin
    assert ".sqlite3" not in metin


# --- komut satırı: alembic upgrade head merkezi yolu kullanır ------------------------


def _cevre(kok: Path) -> dict[str, str]:
    temiz = {k: v for k, v in os.environ.items() if not k.startswith("DEFTERIKI_")}
    temiz[ay.ORTAM_DEGISKENI] = "test"
    temiz[ay.VERI_KOKU_DEGISKENI] = str(kok)
    temiz["PYTHONUTF8"] = "1"
    return temiz


def test_komut_satiri_upgrade_head_merkezi_yolu_kullanir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kok = tmp_path / "kok"
    calisma = tmp_path / "baska_yer"
    calisma.mkdir()

    sonuc = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic.config",
            "-c",
            str(gocler.ALEMBIC_INI),
            "upgrade",
            "head",
        ],
        cwd=calisma,
        env=_cevre(kok),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=BEKLEME_SANIYE,
        check=False,
    )

    assert sonuc.returncode == 0, sonuc.stderr
    assert sonuc.stdout == ""  # stdout'a hiçbir şey yazılmaz
    assert list(calisma.iterdir()) == []  # çalışma dizininde dosya yok
    assert not (gocler.PROJE_KOKU / "defteriki.sqlite3").exists()
    ayar = _test_ayarlari(kok, monkeypatch)
    assert ayar.veritabani_yolu.is_file()
    v = vt.Veritabani(ayar.veritabani_yolu)
    try:
        assert gocler.sema_surumu(v) == GUNCEL_SURUM
        assert _sema(v) == _yukselt(tmp_path / "surec_ici", monkeypatch)[1]
    finally:
        v.kapat()
