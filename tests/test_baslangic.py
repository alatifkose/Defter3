"""Uygulama başlangıç akışı testleri.

Bütün yollar tmp_path altındadır; ortam ``test`` seçilir ve veri kökü açıkça
verilir, böylece kullanıcının gerçek veri ve belge dizinlerine dokunulmaz.
"""

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from defteruc import ayarlar as ay
from defteruc import baslangic, gunluk

DEFTERUC_DEGISKENLERI = (
    ay.ORTAM_DEGISKENI,
    ay.VERI_KOKU_DEGISKENI,
    ay.VERITABANI_YOLU_DEGISKENI,
    ay.BELGE_DIZINI_DEGISKENI,
    ay.LOG_DIZINI_DEGISKENI,
    ay.GELEN_DIZINI_DEGISKENI,
)


@pytest.fixture(autouse=True)
def temiz_cevre_ve_gunluk(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for degisken in DEFTERUC_DEGISKENLERI:
        monkeypatch.delenv(degisken, raising=False)
    gunluk.gunlugu_kapat()
    yield
    gunluk.gunlugu_kapat()


@pytest.fixture
def test_koku(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    kok = tmp_path / "kok"
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(kok))
    return kok / "test"


def _log_satirlari(test_koku: Path) -> list[str]:
    dosya = test_koku / ay.LOG_DIZIN_ADI / gunluk.GUNLUK_DOSYA_ADI
    return dosya.read_text(encoding="utf-8").splitlines()


# --- başarılı başlangıç ----------------------------------------------------


def test_basarili_baslangic_sifir_doner_ve_mesaj_verir(
    test_koku: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kod = baslangic.main()

    cikti = capsys.readouterr()
    assert kod == 0
    assert cikti.err == ""
    assert "DEFTERUC başlatıldı" in cikti.out
    assert "Ortam: test" in cikti.out
    assert str(test_koku) in cikti.out


def test_basarili_baslangic_dizinleri_hazirlar_ve_olay_yazar(test_koku: Path) -> None:
    baslangic.main()

    assert (test_koku / ay.BELGE_DIZIN_ADI).is_dir()
    assert (test_koku / ay.LOG_DIZIN_ADI).is_dir()
    assert not (test_koku / ay.VERITABANI_DOSYA_ADI).exists()
    (satir,) = _log_satirlari(test_koku)
    assert f"| INFO | {baslangic.OLAY_BASLANGIC} | ortam=test" in satir


def test_tekrar_baslatma_her_seferinde_tek_satir_ekler(test_koku: Path) -> None:
    assert baslangic.main() == 0
    assert baslangic.main() == 0

    satirlar = _log_satirlari(test_koku)
    assert len(satirlar) == 2
    assert all(baslangic.OLAY_BASLANGIC in satir for satir in satirlar)


def test_farkli_calisma_dizinlerinden_ayni_yollar(
    tmp_path: Path,
    test_koku: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    birinci = tmp_path / "birinci"
    ikinci = tmp_path / "ikinci"
    birinci.mkdir()
    ikinci.mkdir()

    monkeypatch.chdir(birinci)
    assert baslangic.main() == 0
    cikti_1 = capsys.readouterr().out
    monkeypatch.chdir(ikinci)
    assert baslangic.main() == 0
    cikti_2 = capsys.readouterr().out

    assert cikti_1 == cikti_2
    assert str(test_koku) in cikti_1
    assert not any(birinci.iterdir())
    assert not any(ikinci.iterdir())
    assert len(_log_satirlari(test_koku)) == 2


# --- başarısız başlangıç ---------------------------------------------------


def test_ayar_hatasi_stderr_e_yazilir_ve_sifirdan_farkli_doner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "uretim")
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(tmp_path / "kok"))

    kod = baslangic.main()

    cikti = capsys.readouterr()
    assert kod != 0
    assert cikti.out == ""
    assert "DEFTERUC başlatılamadı" in cikti.err
    assert "Ayar hatası" in cikti.err
    assert ay.ORTAM_DEGISKENI in cikti.err
    assert not (tmp_path / "kok").exists()
    assert not gunluk.kurulu()


def test_dizin_hatasi_stderr_e_yazilir(
    test_koku: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    test_koku.mkdir(parents=True)
    (test_koku / ay.LOG_DIZIN_ADI).write_text("dosya", encoding="utf-8")

    kod = baslangic.main()

    cikti = capsys.readouterr()
    assert kod != 0
    assert cikti.out == ""
    assert "Dizin hazırlama hatası" in cikti.err
    assert str(test_koku / ay.LOG_DIZIN_ADI) in cikti.err
    assert not gunluk.kurulu()


def test_gunluk_kurulamazsa_basari_mesaji_verilmez(
    test_koku: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (test_koku / ay.LOG_DIZIN_ADI / gunluk.GUNLUK_DOSYA_ADI).mkdir(parents=True)

    kod = baslangic.main()

    cikti = capsys.readouterr()
    assert kod != 0
    assert cikti.out == ""
    assert "Günlük kurulum hatası" in cikti.err
    assert not gunluk.kurulu()


def test_beklenmeyen_hata_gunluge_yalniz_turuyle_gecer(
    test_koku: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    hassas = "IBAN TR00 0000 0000 0000 0000 0000 00 KISI ALFA"

    def patlat(ayarlar: ay.Ayarlar, log_dosyasi: Path) -> None:
        raise RuntimeError(hassas)

    monkeypatch.setattr(baslangic, "_basariyi_bildir", patlat)

    kod = baslangic.main()

    cikti = capsys.readouterr()
    assert kod != 0
    assert "Beklenmeyen hata (RuntimeError)" in cikti.err
    icerik = "\n".join(_log_satirlari(test_koku))
    assert f"| ERROR | {baslangic.OLAY_BASLANGIC_HATASI} | " in icerik
    assert "builtins.RuntimeError" in icerik
    assert "TR00" not in icerik
    assert "KISI ALFA" not in icerik


def test_gunluk_kurulmadan_olusan_beklenmeyen_hata_stderr_e_gider(
    test_koku: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def patlat() -> ay.Ayarlar:
        raise RuntimeError("ayar yüklenirken beklenmeyen durum")

    monkeypatch.setattr(baslangic, "ayarlari_yukle", patlat)

    kod = baslangic.main()

    cikti = capsys.readouterr()
    assert kod != 0
    assert "Beklenmeyen hata (RuntimeError)" in cikti.err
    assert not test_koku.exists()
    assert not gunluk.kurulu()


# --- ayrı süreçte çıkış kodu -----------------------------------------------


def _ayri_surecte_baslat(
    cwd: Path, cevre: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    temiz = {k: v for k, v in os.environ.items() if not k.startswith("DEFTERUC_")}
    temiz.update(cevre)
    temiz["PYTHONUTF8"] = "1"
    komut = "import sys; from defteruc.baslangic import main; sys.exit(main())"
    return subprocess.run(
        [sys.executable, "-c", komut],
        cwd=cwd,
        env=temiz,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_ayri_surecte_basarili_baslangic_sifir_cikis_kodu(tmp_path: Path) -> None:
    kok = tmp_path / "kok"
    calisma = tmp_path / "baska_yer"
    calisma.mkdir()

    sonuc = _ayri_surecte_baslat(
        calisma, {ay.ORTAM_DEGISKENI: "test", ay.VERI_KOKU_DEGISKENI: str(kok)}
    )

    assert sonuc.returncode == 0, sonuc.stderr
    assert "DEFTERUC başlatıldı" in sonuc.stdout
    assert (kok / "test" / ay.LOG_DIZIN_ADI / gunluk.GUNLUK_DOSYA_ADI).is_file()
    assert not any(calisma.iterdir())


def test_ayri_surecte_basarisiz_baslangic_sifirdan_farkli_cikis_kodu(
    tmp_path: Path,
) -> None:
    # Veri kökü verilmedi; test ortamı bunu zorunlu tutar.
    sonuc = _ayri_surecte_baslat(tmp_path, {ay.ORTAM_DEGISKENI: "test"})

    assert sonuc.returncode == 1
    assert sonuc.stdout == ""
    assert "DEFTERUC başlatılamadı" in sonuc.stderr
    assert ay.VERI_KOKU_DEGISKENI in sonuc.stderr
