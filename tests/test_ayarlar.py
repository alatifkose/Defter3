"""Merkezi ayar yönetimi testleri.

Bütün yollar tmp_path altındadır. Kullanıcının kendi DEFTERUC_* ortam
değişkenleri her testten önce temizlenir; gerçek kullanıcı dizinlerine
dokunulmaz.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from defteruc import ayarlar as ay

DEFTERUC_DEGISKENLERI = (
    ay.ORTAM_DEGISKENI,
    ay.VERI_KOKU_DEGISKENI,
    ay.VERITABANI_YOLU_DEGISKENI,
    ay.BELGE_DIZINI_DEGISKENI,
    ay.LOG_DIZINI_DEGISKENI,
    ay.GELEN_DIZINI_DEGISKENI,
)
YOL_DEGISKENLERI = DEFTERUC_DEGISKENLERI[1:]
TEKIL_YOL_DEGISKENLERI = DEFTERUC_DEGISKENLERI[2:]


@pytest.fixture(autouse=True)
def temiz_cevre(monkeypatch: pytest.MonkeyPatch) -> None:
    for degisken in DEFTERUC_DEGISKENLERI:
        monkeypatch.delenv(degisken, raising=False)


@pytest.fixture
def ortak_kok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    kok = tmp_path / "kok"
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(kok))
    return kok


# --- varsayılan ortam ve yol türetme ---------------------------------------


def test_ortam_verilmezse_gelistirme_kullanilir(ortak_kok: Path) -> None:
    ayar = ay.ayarlari_yukle()

    assert ayar.ortam is ay.Ortam.GELISTIRME
    assert ayar.veri_koku == ortak_kok / "gelistirme"
    assert ayar.veritabani_yolu == ortak_kok / "gelistirme" / "defteruc.sqlite3"
    assert ayar.belge_dizini == ortak_kok / "gelistirme" / "belgeler"
    assert ayar.log_dizini == ortak_kok / "gelistirme" / "logs"
    assert ayar.gelen_dizini == ortak_kok / "gelistirme" / "gelen"


def test_yollar_pathlib_path_olarak_tutulur(ortak_kok: Path) -> None:
    ayar = ay.ayarlari_yukle()

    yollar = (
        ayar.veri_koku,
        ayar.veritabani_yolu,
        ayar.belge_dizini,
        ayar.log_dizini,
        ayar.gelen_dizini,
    )

    assert all(isinstance(yol, Path) for yol in yollar)


def test_gelistirme_ve_gercek_yollari_ayrilir(
    ortak_kok: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "gelistirme")
    gelistirme = ay.ayarlari_yukle()
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "gercek")
    gercek = ay.ayarlari_yukle()

    assert gelistirme.veri_koku == ortak_kok / "gelistirme"
    assert gercek.veri_koku == ortak_kok / "gercek"
    assert gelistirme.veritabani_yolu != gercek.veritabani_yolu
    assert gelistirme.belge_dizini != gercek.belge_dizini
    assert gelistirme.log_dizini != gercek.log_dizini
    assert gelistirme.gelen_dizini != gercek.gelen_dizini


# --- platform varsayılanları -----------------------------------------------


def test_windows_varsayilan_kok_localappdata_altindadir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ay.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))

    ayar = ay.ayarlari_yukle()

    assert ayar.veri_koku == tmp_path / "Local" / "DEFTERUC" / "gelistirme"


def test_windows_localappdata_yoksa_aciklayici_hata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ay.sys, "platform", "win32")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    with pytest.raises(ay.AyarHatasi, match="LOCALAPPDATA"):
        ay.ayarlari_yukle()


def _ev_dizinini_sabitle(monkeypatch: pytest.MonkeyPatch, ev: Path) -> None:
    def ev_dizini(cls: type[Path]) -> Path:
        return ev

    monkeypatch.setattr(Path, "home", classmethod(ev_dizini))


def test_linux_varsayilan_kok_xdg_veya_ev_altindadir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ay.sys, "platform", "linux")
    _ev_dizinini_sabitle(monkeypatch, tmp_path / "ev")

    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert ay.ayarlari_yukle().veri_koku == (
        tmp_path / "ev" / ".local" / "share" / "DEFTERUC" / "gelistirme"
    )

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert ay.ayarlari_yukle().veri_koku == (
        tmp_path / "xdg" / "DEFTERUC" / "gelistirme"
    )


def test_macos_varsayilan_kok_application_support_altindadir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ay.sys, "platform", "darwin")
    _ev_dizinini_sabitle(monkeypatch, tmp_path / "ev")

    assert ay.ayarlari_yukle().veri_koku == (
        tmp_path / "ev" / "Library" / "Application Support" / "DEFTERUC" / "gelistirme"
    )


# --- ortam değişkeni önceliği ----------------------------------------------


def test_veri_koku_degiskeni_platform_varsayilanini_gecer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(tmp_path / "ozel"))

    assert ay.ayarlari_yukle().veri_koku == tmp_path / "ozel" / "gelistirme"


def test_tekil_yol_degiskenleri_turetilmis_yollari_gecer(
    tmp_path: Path, ortak_kok: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ay.VERITABANI_YOLU_DEGISKENI, str(tmp_path / "vt" / "a.sqlite3"))
    monkeypatch.setenv(ay.BELGE_DIZINI_DEGISKENI, str(tmp_path / "arsiv"))
    monkeypatch.setenv(ay.LOG_DIZINI_DEGISKENI, str(tmp_path / "gunluk"))
    monkeypatch.setenv(ay.GELEN_DIZINI_DEGISKENI, str(tmp_path / "kutu"))

    ayar = ay.ayarlari_yukle()

    assert ayar.veri_koku == ortak_kok / "gelistirme"
    assert ayar.veritabani_yolu == tmp_path / "vt" / "a.sqlite3"
    assert ayar.belge_dizini == tmp_path / "arsiv"
    assert ayar.log_dizini == tmp_path / "gunluk"
    assert ayar.gelen_dizini == tmp_path / "kutu"


def test_tekil_yol_ortam_ayrimini_gecersiz_kilabilir(
    ortak_kok: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gercek_vt = ortak_kok / "gercek" / "defteruc.sqlite3"
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "gelistirme")
    monkeypatch.setenv(ay.VERITABANI_YOLU_DEGISKENI, str(gercek_vt))

    ayar = ay.ayarlari_yukle()

    assert ayar.ortam is ay.Ortam.GELISTIRME
    assert ayar.veritabani_yolu == gercek_vt


# --- geçersiz değerlerin reddi ---------------------------------------------


@pytest.mark.parametrize("deger", ["", "   ", "uretim", "GELISTIRME", "prod"])
def test_gecersiz_ortam_reddedilir(
    ortak_kok: Path, monkeypatch: pytest.MonkeyPatch, deger: str
) -> None:
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, deger)

    with pytest.raises(ay.AyarHatasi, match=ay.ORTAM_DEGISKENI):
        ay.ayarlari_yukle()


@pytest.mark.parametrize("degisken", YOL_DEGISKENLERI)
@pytest.mark.parametrize("deger", ["", "  "])
def test_bos_yol_degeri_reddedilir(
    ortak_kok: Path, monkeypatch: pytest.MonkeyPatch, degisken: str, deger: str
) -> None:
    monkeypatch.setenv(degisken, deger)

    with pytest.raises(ay.AyarHatasi, match=f"{degisken} boş olamaz"):
        ay.ayarlari_yukle()


@pytest.mark.parametrize("degisken", YOL_DEGISKENLERI)
@pytest.mark.parametrize("deger", ["veri", "./veri", "../veri"])
def test_goreli_yol_reddedilir(
    ortak_kok: Path, monkeypatch: pytest.MonkeyPatch, degisken: str, deger: str
) -> None:
    monkeypatch.setenv(degisken, deger)

    with pytest.raises(ay.AyarHatasi, match="mutlak"):
        ay.ayarlari_yukle()


# --- çalışma dizininden bağımsızlık ----------------------------------------


def test_calisma_dizini_degisse_de_ayni_yollar(
    tmp_path: Path, ortak_kok: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    birinci = tmp_path / "birinci"
    ikinci = tmp_path / "ikinci"
    birinci.mkdir()
    ikinci.mkdir()

    monkeypatch.chdir(birinci)
    ayar_1 = ay.ayarlari_yukle()
    monkeypatch.chdir(ikinci)
    ayar_2 = ay.ayarlari_yukle()

    assert ayar_1 == ayar_2
    assert ayar_1.veri_koku.is_absolute()


# --- yükleme yazmaz, hazırlama yazar ---------------------------------------


def test_ayar_yukleme_diske_yazmaz(ortak_kok: Path) -> None:
    ayar = ay.ayarlari_yukle()

    assert not ortak_kok.exists()
    assert not ayar.veri_koku.exists()


def test_dizin_hazirlama_gerekli_dizinleri_olusturur(ortak_kok: Path) -> None:
    ayar = ay.ayarlari_yukle()

    ay.dizinleri_hazirla(ayar)

    assert ayar.veritabani_yolu.parent.is_dir()
    assert ayar.belge_dizini.is_dir()
    assert ayar.log_dizini.is_dir()
    assert ayar.gelen_dizini.is_dir()
    assert not ayar.veritabani_yolu.exists()
    assert list(ayar.log_dizini.iterdir()) == []


def test_dizin_hazirlama_tekrar_cagrilabilir(ortak_kok: Path) -> None:
    ayar = ay.ayarlari_yukle()

    ay.dizinleri_hazirla(ayar)
    (ayar.belge_dizini / "iz.txt").write_text("var", encoding="utf-8")
    ay.dizinleri_hazirla(ayar)

    assert (ayar.belge_dizini / "iz.txt").read_text(encoding="utf-8") == "var"


def test_dizin_yerine_dosya_varsa_acik_hata(ortak_kok: Path) -> None:
    ayar = ay.ayarlari_yukle()
    ayar.veri_koku.mkdir(parents=True)
    ayar.log_dizini.write_text("bu bir dosya", encoding="utf-8")

    with pytest.raises(ay.DizinHazirlamaHatasi, match="zaten bir dosya") as bilgi:
        ay.dizinleri_hazirla(ayar)

    assert str(ayar.log_dizini) in str(bilgi.value)
    assert isinstance(bilgi.value.__cause__, FileExistsError)


def test_erisim_hatasi_yol_ile_bildirilir(
    ortak_kok: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ayar = ay.ayarlari_yukle()

    def erisim_reddet(self: Path, *args: object, **kwargs: object) -> None:
        raise PermissionError(13, "Erişim reddedildi")

    monkeypatch.setattr(Path, "mkdir", erisim_reddet)

    with pytest.raises(ay.DizinHazirlamaHatasi, match="Erişim reddedildi") as bilgi:
        ay.dizinleri_hazirla(ayar)

    assert str(ayar.veritabani_yolu.parent) in str(bilgi.value)
    assert isinstance(bilgi.value.__cause__, PermissionError)


# --- test ortamı kuralları -------------------------------------------------


def test_test_ortami_veri_koku_ister(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))

    with pytest.raises(ay.AyarHatasi, match=ay.VERI_KOKU_DEGISKENI):
        ay.ayarlari_yukle()


def test_test_ortami_verilen_kokun_altina_turetir(
    ortak_kok: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")

    ayar = ay.ayarlari_yukle()

    assert ayar.ortam is ay.Ortam.TEST
    assert ayar.veri_koku == ortak_kok / "test"
    assert ayar.veritabani_yolu == ortak_kok / "test" / "defteruc.sqlite3"


def test_test_ortaminda_kok_ici_tekil_yol_kabul_edilir(
    ortak_kok: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.LOG_DIZINI_DEGISKENI, str(ortak_kok / "test" / "gunluk"))

    assert ay.ayarlari_yukle().log_dizini == ortak_kok / "test" / "gunluk"


@pytest.mark.parametrize("degisken", TEKIL_YOL_DEGISKENLERI)
def test_test_ortaminda_kok_disi_tekil_yol_reddedilir(
    tmp_path: Path, ortak_kok: Path, monkeypatch: pytest.MonkeyPatch, degisken: str
) -> None:
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(degisken, str(tmp_path / "disari"))

    with pytest.raises(ay.AyarHatasi, match="test veri kökünün dışına"):
        ay.ayarlari_yukle()


def test_test_ortaminda_ust_dizin_ile_kacis_reddedilir(
    ortak_kok: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    kacan_yol = ortak_kok / "test" / ".." / "gercek"
    monkeypatch.setenv(ay.BELGE_DIZINI_DEGISKENI, str(kacan_yol))

    with pytest.raises(ay.AyarHatasi, match="test veri kökünün dışına"):
        ay.ayarlari_yukle()


# --- test ortamı: fiziksel yol sınırı (2026-09-18) --------------------------
# Sınır yolun yazılı biçimine değil fiziksel karşılığına bakar: kök içindeki
# bir bağlantı dışarıyı gösteriyorsa yol reddedilir, hiçbir dizin oluşmaz.


def _simgesel_baglanti(baglanti: Path, hedef: Path) -> None:
    """Dizin simgesel bağlantısı; yetki yoksa (Windows'ta sık) test atlanır."""
    try:
        os.symlink(hedef, baglanti, target_is_directory=True)
    except OSError as hata:
        pytest.skip(f"simgesel bağlantı kurulamadı (yetki?): {hata}")


def _junction(baglanti: Path, hedef: Path) -> None:
    """Windows junction (yetki gerektirmez); başka platformda test atlanır."""
    if sys.platform != "win32":
        pytest.skip("junction yalnız Windows'ta var")
    sonuc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(baglanti), str(hedef)],
        capture_output=True,
        text=True,
        check=False,
    )
    if sonuc.returncode != 0 or not baglanti.exists():
        pytest.skip(f"junction kurulamadı: {sonuc.stderr.strip() or sonuc.stdout}")


def _kok_ve_disari(tmp_path: Path, ortak_kok: Path) -> tuple[Path, Path]:
    kok_test = ortak_kok / "test"
    kok_test.mkdir(parents=True)
    disari = tmp_path / "disari"
    disari.mkdir()
    return kok_test, disari


def _disariya_kacan_baglanti_reddedilir(
    kok_test: Path, disari: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.LOG_DIZINI_DEGISKENI, str(kok_test / "bag" / "logs"))

    with pytest.raises(ay.AyarHatasi, match="fiziksel karşılığı") as hata:
        ay.ayarlari_yukle()

    assert "test veri kökünün dışına" in str(hata.value)
    assert list(disari.iterdir()) == []  # dışarıda hiçbir şey oluşmadı
    assert not (kok_test / "bag" / "logs").exists()


def test_test_ortaminda_simgesel_baglanti_ile_kacis_reddedilir(
    tmp_path: Path, ortak_kok: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kok_test, disari = _kok_ve_disari(tmp_path, ortak_kok)
    _simgesel_baglanti(kok_test / "bag", disari)

    _disariya_kacan_baglanti_reddedilir(kok_test, disari, monkeypatch)


def test_test_ortaminda_junction_ile_kacis_reddedilir(
    tmp_path: Path, ortak_kok: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kok_test, disari = _kok_ve_disari(tmp_path, ortak_kok)
    _junction(kok_test / "bag", disari)

    _disariya_kacan_baglanti_reddedilir(kok_test, disari, monkeypatch)


def test_test_ortaminda_kok_icini_gosteren_baglanti_kabul_edilir(
    tmp_path: Path, ortak_kok: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kok_test, _ = _kok_ve_disari(tmp_path, ortak_kok)
    (kok_test / "ic").mkdir()
    if sys.platform == "win32":
        _junction(kok_test / "bag", kok_test / "ic")
    else:
        _simgesel_baglanti(kok_test / "bag", kok_test / "ic")
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.LOG_DIZINI_DEGISKENI, str(kok_test / "bag" / "logs"))

    ayar = ay.ayarlari_yukle()

    assert ayar.log_dizini == kok_test / "bag" / "logs"  # verilen yol korunur


def test_gelistirme_ortaminda_kok_disi_tekil_yol_serbest_kalir(
    tmp_path: Path, ortak_kok: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fiziksel sınır yalnız test ortamınındır; diğer ortamların politikası aynı."""
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "gelistirme")
    monkeypatch.setenv(ay.LOG_DIZINI_DEGISKENI, str(tmp_path / "disari" / "logs"))

    assert ay.ayarlari_yukle().log_dizini == tmp_path / "disari" / "logs"
