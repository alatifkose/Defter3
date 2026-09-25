import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import text

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from defteruc import ayarlar as ay  # noqa: E402
from defteruc import baslangic, gunluk, komutlar, pencere  # noqa: E402
from defteruc.cekirdek import motor as m  # noqa: E402
from defteruc.cekirdek import onay  # noqa: E402
from defteruc.cekirdek import veritabani as vt  # noqa: E402

DEFTERUC_DEGISKENLERI = (
    ay.ORTAM_DEGISKENI,
    ay.VERI_KOKU_DEGISKENI,
    ay.VERITABANI_YOLU_DEGISKENI,
    ay.BELGE_DIZINI_DEGISKENI,
    ay.LOG_DIZINI_DEGISKENI,
    ay.GELEN_DIZINI_DEGISKENI,
)

KISILER = m.TabloOlusturmaIstegi(
    "kisiler",
    (m.Sutun("id", ("INTEGER", "PRIMARY KEY")), m.Sutun("ad_soyad", ("TEXT",))),
)


@pytest.fixture(scope="module")
def uygulama() -> QApplication:
    mevcut = QApplication.instance()
    if isinstance(mevcut, QApplication):
        return mevcut
    return QApplication([])


@pytest.fixture(autouse=True)
def temiz_cevre_ve_gunluk(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for degisken in DEFTERUC_DEGISKENLERI:
        monkeypatch.delenv(degisken, raising=False)
    gunluk.gunlugu_kapat()
    yield
    gunluk.gunlugu_kapat()


@pytest.fixture
def ayar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ay.Ayarlar:
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(tmp_path / "kok"))
    ayarlar = ay.ayarlari_yukle()
    ay.dizinleri_hazirla(ayarlar)
    gunluk.gunlugu_kur(ayarlar.log_dizini)
    return ayarlar


@pytest.fixture
def veritabani(ayar: ay.Ayarlar) -> Iterator[vt.Veritabani]:
    v = vt.Veritabani(ayar.veritabani_yolu)
    onay.sistem_tablosunu_hazirla(v)
    yield v
    v.kapat()


@pytest.fixture
def pencere_(
    uygulama: QApplication, veritabani: vt.Veritabani
) -> Iterator[pencere.OnayPenceresi]:
    p = pencere.OnayPenceresi(veritabani, yenileme_ms=0)
    yield p
    p.close()


def _liste(widget: object) -> list[str]:
    from PySide6.QtWidgets import QListWidget

    assert isinstance(widget, QListWidget)
    return [widget.item(i).text() for i in range(widget.count())]


def _tablolar(v: vt.Veritabani) -> set[str]:
    with v.islem() as oturum:
        satirlar = oturum.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'table'")
        ).all()
    return {str(s[0]) for s in satirlar}


def _log(ayar: ay.Ayarlar) -> str:
    return (ayar.log_dizini / gunluk.GUNLUK_DOSYA_ADI).read_text(encoding="utf-8")


# --- görünüm ---------------------------------------------------------------------


def test_bos_durum(pencere_: pencere.OnayPenceresi) -> None:
    assert pencere_.windowTitle() == pencere.PENCERE_BASLIGI
    assert _liste(pencere_.bekleyenler) == []
    assert pencere_.secili_kimlik() is None
    assert pencere_.sql.toPlainText() == ""
    assert pencere_.sql.placeholderText() == "Bekleyen yapı isteği yok."
    assert not pencere_.onayla_dugmesi.isEnabled()
    assert not pencere_.reddet_dugmesi.isEnabled()


def test_bekleyenler_listelenir_ve_secilenin_sqli_gosterilir(
    pencere_: pencere.OnayPenceresi, veritabani: vt.Veritabani
) -> None:
    onay.istek_birak(veritabani, KISILER)
    onay.istek_birak(veritabani, m.IndeksSilmeIstegi("ix"))
    pencere_.yenile()
    satirlar = _liste(pencere_.bekleyenler)
    assert satirlar[0].startswith("[1] tablo_olusturma · 20")
    assert satirlar[1].startswith("[2] indeks_silme · 20")
    assert pencere_.secili_kimlik() == 1
    assert pencere_.sql.toPlainText() == m.tablo_olusturma_sql(KISILER)
    assert pencere_.onayla_dugmesi.isEnabled() and pencere_.reddet_dugmesi.isEnabled()
    pencere_.bekleyenler.setCurrentRow(1)
    assert pencere_.secili_kimlik() == 2
    assert pencere_.sql.toPlainText() == 'DROP INDEX "ix"'


def test_yenileme_disaridan_gelen_istegi_gorur_ve_secimi_korur(
    pencere_: pencere.OnayPenceresi, veritabani: vt.Veritabani
) -> None:
    onay.istek_birak(veritabani, KISILER)
    onay.istek_birak(veritabani, m.IndeksSilmeIstegi("ix"))
    pencere_.yenile()
    pencere_.bekleyenler.setCurrentRow(1)
    baska = vt.Veritabani(veritabani.yol)
    try:
        onay.istek_birak(baska, m.IndeksSilmeIstegi("iy"))
    finally:
        baska.kapat()
    pencere_.yenile_dugmesi.click()
    assert len(_liste(pencere_.bekleyenler)) == 3
    assert pencere_.secili_kimlik() == 2


# --- kararlar ---------------------------------------------------------------------


def test_onayla_uygular_listeyi_yeniler_ve_gunluge_yazar(
    pencere_: pencere.OnayPenceresi, veritabani: vt.Veritabani, ayar: ay.Ayarlar
) -> None:
    onay.istek_birak(veritabani, KISILER)
    pencere_.yenile()
    pencere_.onayla_dugmesi.click()
    assert "kisiler" in _tablolar(veritabani)
    assert _liste(pencere_.bekleyenler) == []
    assert pencere_.mesaj.text() == "Talep 1 onaylandı ve uygulandı (tablo_olusturma)."
    (karar,) = _liste(pencere_.kararlar)
    assert karar.startswith("[1] tablo_olusturma · UYGULANDI · 20")
    assert (
        f"| {komutlar.OLAY_ONAY_KARARI} | talep=1 tur=tablo_olusturma durum=UYGULANDI"
        in _log(ayar)
    )
    assert not pencere_.onayla_dugmesi.isEnabled()


def test_reddet_uygulamaz(
    pencere_: pencere.OnayPenceresi, veritabani: vt.Veritabani
) -> None:
    onay.istek_birak(veritabani, KISILER)
    pencere_.yenile()
    pencere_.reddet_dugmesi.click()
    assert "kisiler" not in _tablolar(veritabani)
    assert pencere_.mesaj.text() == "Talep 1 reddedildi (tablo_olusturma)."
    assert _liste(pencere_.kararlar)[0].startswith("[1] tablo_olusturma · REDDEDILDI")


def test_uygulanamayan_onay_sebebiyle_gosterilir(
    pencere_: pencere.OnayPenceresi, veritabani: vt.Veritabani
) -> None:
    onay.onayla(veritabani, onay.istek_birak(veritabani, KISILER))
    onay.istek_birak(veritabani, KISILER)
    pencere_.yenile()
    pencere_.onayla_dugmesi.click()
    assert pencere_.mesaj.text().startswith("Talep 2 onaylandı ama uygulanamadı")
    assert "already exists" in pencere_.mesaj.text()
    kararlar = _liste(pencere_.kararlar)
    assert kararlar[0].startswith("[2] tablo_olusturma · UYGULANAMADI")
    assert "already exists" in kararlar[0]
    assert kararlar[1].startswith("[1] tablo_olusturma · UYGULANDI")


def test_baska_yerden_karar_verilmis_istek(
    pencere_: pencere.OnayPenceresi, veritabani: vt.Veritabani
) -> None:
    kimlik = onay.istek_birak(veritabani, KISILER)
    pencere_.yenile()
    baska = vt.Veritabani(veritabani.yol)
    try:
        onay.reddet(baska, kimlik)
    finally:
        baska.kapat()
    pencere_.onayla_dugmesi.click()
    assert "karar verilmiş: REDDEDILDI" in pencere_.mesaj.text()
    assert "kisiler" not in _tablolar(veritabani)
    assert _liste(pencere_.bekleyenler) == []


def test_secim_yokken_dugmeler_bir_sey_yapmaz(
    pencere_: pencere.OnayPenceresi, veritabani: vt.Veritabani
) -> None:
    pencere_.onayla()
    pencere_.reddet()
    assert pencere_.mesaj.text() == ""
    assert onay.bekleyenler(veritabani) == ()


def test_son_kararlar_en_yeniden_eskiye_ve_sinirli(veritabani: vt.Veritabani) -> None:
    for i in range(3):
        onay.reddet(
            veritabani, onay.istek_birak(veritabani, m.IndeksSilmeIstegi(f"ix{i}"))
        )
    onay.istek_birak(veritabani, KISILER)
    kararlar = onay.son_kararlar(veritabani, 2)
    assert [k.kimlik for k in kararlar] == [3, 2]
    assert all(k.durum is onay.Durum.REDDEDILDI for k in kararlar)


# --- komut satırından açma ----------------------------------------------------------


def test_pencere_komutu_pencereyi_calistirir(
    ayar: ay.Ayarlar, monkeypatch: pytest.MonkeyPatch
) -> None:
    cagrilar: list[ay.Ayarlar] = []

    def sahte(ayarlar: ay.Ayarlar) -> int:
        cagrilar.append(ayarlar)
        return 0

    monkeypatch.setattr(pencere, "calistir", sahte)
    assert baslangic.main([komutlar.KOMUT_PENCERE]) == 0
    assert cagrilar == [ayar]
