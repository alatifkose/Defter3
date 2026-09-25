from collections.abc import Sequence
from pathlib import Path

import kontrol


def _adimlar() -> tuple[kontrol.Adim, ...]:
    return (
        kontrol.Adim("bir", ("bir",)),
        kontrol.Adim("iki", ("iki",)),
        kontrol.Adim("uc", ("uc",)),
    )


def test_hepsi_basariliysa_sifir_doner(tmp_path: Path) -> None:
    calisanlar: list[str] = []

    def calistirici(komut: Sequence[str], kok: Path) -> int:
        calisanlar.append(komut[0])
        assert kok == tmp_path
        return 0

    assert kontrol.hepsini_calistir(_adimlar(), tmp_path, calistirici) == 0
    assert calisanlar == ["bir", "iki", "uc"]


def test_biri_basarisizsa_digerleri_calisir_ve_sonuc_basarisiz(
    tmp_path: Path,
) -> None:
    calisanlar: list[str] = []

    def calistirici(komut: Sequence[str], kok: Path) -> int:
        calisanlar.append(komut[0])
        return 3 if komut[0] == "bir" else 0

    assert kontrol.hepsini_calistir(_adimlar(), tmp_path, calistirici) != 0
    assert calisanlar == ["bir", "iki", "uc"]


def test_arac_baslatilamazsa_sonuc_basarisiz(tmp_path: Path) -> None:
    calisanlar: list[str] = []

    def calistirici(komut: Sequence[str], kok: Path) -> int:
        calisanlar.append(komut[0])
        if komut[0] == "iki":
            raise FileNotFoundError("iki bulunamadı")
        return 0

    assert kontrol.hepsini_calistir(_adimlar(), tmp_path, calistirici) != 0
    assert calisanlar == ["bir", "iki", "uc"]


def test_baslatilamayan_adim_yok_olarak_raporlanir(tmp_path: Path) -> None:
    def calistirici(komut: Sequence[str], kok: Path) -> int:
        raise FileNotFoundError("yok")

    sonuc = kontrol.adimi_calistir(_adimlar()[0], tmp_path, calistirici)

    assert sonuc.cikis_kodu is None
    assert not sonuc.basarili
    assert "başlatılamadı" in sonuc.aciklama


def test_adimlar_calistiran_python_yorumlayicisini_kullanir() -> None:
    adimlar = kontrol.adimlar("/ornek/python")

    assert [a.komut[0] for a in adimlar] == ["/ornek/python"] * 4
    assert all(a.komut[1] == "-m" for a in adimlar)
    assert [a.komut[2] for a in adimlar] == ["ruff", "ruff", "pyright", "pytest"]


def test_adimlar_kaynak_degistirmez() -> None:
    for adim in kontrol.adimlar():
        assert "--fix" not in adim.komut
        if "format" in adim.komut:
            assert "--check" in adim.komut
