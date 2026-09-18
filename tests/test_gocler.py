"""Göç zinciri ve şema sürümü testleri (Aşama 4.1).

Gerçek SQLite dosyaları, ``test`` ortamı, ``tmp_path`` altında kök. Süreç içi
``semayi_yukselt`` ve komut satırı (``alembic upgrade head``) aynı ``env.py``
üzerinden aynı sonucu verir; komut satırı yolu merkezi ayarlardan alır.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import text

from defteriki import ayarlar as ay
from defteriki import baslangic, gunluk
from defteriki.cekirdek import gocler
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

        assert surum == "0001" == gocler.beklenen_sema_surumu()
        assert gocler.sema_surumu(v) == "0001"
        tablolar = [ad for tur, ad, _ in _sema(v) if tur == "table"]
        assert tablolar == [gocler.SURUM_TABLOSU]  # uygulama tablosu yok
    finally:
        v.kapat()


def test_iki_sifir_veritabani_ayni_semayi_uretir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    birinci = _yukselt(tmp_path / "a", monkeypatch)
    ikinci = _yukselt(tmp_path / "b", monkeypatch)

    assert birinci == ikinci
    assert birinci[0] == "0001"


def test_tekrar_upgrade_semayi_degistirmez(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ayar = _test_ayarlari(tmp_path / "kok", monkeypatch)
    v = vt.Veritabani(ayar.veritabani_yolu)
    try:
        gocler.semayi_yukselt(v)
        once = _sema(v)
        assert gocler.semayi_yukselt(v) == "0001"
        assert _sema(v) == once
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

        assert gocler.semayi_yukselt(v) == "0001"  # veritabanı kullanılabilir
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
        assert gocler.sema_surumu(v) == "0001"
        assert _sema(v) == _yukselt(tmp_path / "surec_ici", monkeypatch)[1]
    finally:
        v.kapat()
