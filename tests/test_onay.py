import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import text

from defteruc import ayarlar as ay
from defteruc.cekirdek import motor as m
from defteruc.cekirdek import onay
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
    onay.sistem_tablosunu_hazirla(v)
    yield v
    v.kapat()


def _tablolar(v: vt.Veritabani) -> set[str]:
    with v.islem() as oturum:
        satirlar = oturum.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'table'")
        ).all()
    return {str(s[0]) for s in satirlar}


def _sutun_turleri(v: vt.Veritabani, tablo: str) -> dict[str, str]:
    with v.islem() as oturum:
        satirlar = oturum.execute(text(f'PRAGMA table_info("{tablo}")')).all()
    return {str(s[1]): str(s[2]) for s in satirlar}


KISILER = m.TabloOlusturmaIstegi(
    tablo="kisiler",
    sutunlar=(
        m.Sutun("id", ("INTEGER", "PRIMARY KEY")),
        m.Sutun("ad_soyad", ("TEXT", "NOT NULL")),
    ),
)
KISILER_YENI = m.SutunOzelligiDegistirmeIstegi(
    tablo="kisiler",
    sutunlar=(
        m.Sutun("id", ("INTEGER", "PRIMARY KEY")),
        m.Sutun("ad_soyad", ("TEXT", "NOT NULL", "DEFAULT ''")),
    ),
)
ORNEK_ISTEKLER: tuple[m.YapiIstegi, ...] = (
    m.TabloOlusturmaIstegi(
        "t",
        (m.Sutun("a", ("INTEGER",)), m.Sutun("b")),
        kisitlar=("UNIQUE (a, b)",),
        secenekler=("STRICT",),
    ),
    m.SutunEklemeIstegi("t", m.Sutun("c", ("TEXT", "DEFAULT 'ş'"))),
    m.SutunOzelligiDegistirmeIstegi(
        "t",
        (m.Sutun("a", ("INTEGER",)), m.Sutun("b", ("TEXT",))),
        kisitlar=("UNIQUE (a, b)",),
        secenekler=("STRICT",),
        deger_donusumu_izinli=("b",),
    ),
    m.IndeksOlusturmaIstegi(
        "ix_t_a", "t", ("a", "b DESC"), benzersiz=True, kosul="a > 0"
    ),
    m.IndeksSilmeIstegi("ix_t_a"),
)


# --- sistem tablosu -----------------------------------------------------------------


def test_sistem_tablosu_hazirlanir_ve_tekrar_cagri_zararsizdir(
    veritabani: vt.Veritabani,
) -> None:
    onay.sistem_tablosunu_hazirla(veritabani)
    assert onay.SISTEM_TABLOSU in _tablolar(veritabani)
    assert onay.bekleyenler(veritabani) == ()


def test_sistem_tablosu_motorun_ad_kuralina_uymaz() -> None:
    with pytest.raises(m.GecersizAd):
        m.adi_dogrula(onay.SISTEM_TABLOSU, "tablo")
    with pytest.raises(m.GecersizAd):
        m.istek_sql(m.SutunEklemeIstegi(onay.SISTEM_TABLOSU, m.Sutun("x")))


# --- istek bırakma ------------------------------------------------------------------


def test_istek_birakmak_uygulamaz_bekliyor_kaydeder(veritabani: vt.Veritabani) -> None:
    kimlik = onay.istek_birak(veritabani, KISILER)
    assert kimlik == 1
    assert "kisiler" not in _tablolar(veritabani)
    (kayit,) = onay.bekleyenler(veritabani)
    assert kayit.kimlik == 1
    assert kayit.tur == "tablo_olusturma"
    assert kayit.istek == KISILER
    assert kayit.sql == m.tablo_olusturma_sql(KISILER)
    assert kayit.durum is onay.Durum.BEKLIYOR
    assert kayit.olusturma.endswith("+00:00")
    assert kayit.karar is None and kayit.sonuc is None


def test_talep_kimligi_artar_ve_bekleyenler_sirayla_gelir(
    veritabani: vt.Veritabani,
) -> None:
    a = onay.istek_birak(veritabani, KISILER)
    b = onay.istek_birak(veritabani, m.IndeksSilmeIstegi("ix"))
    assert (a, b) == (1, 2)
    assert [k.kimlik for k in onay.bekleyenler(veritabani)] == [1, 2]


def test_gecersiz_istek_hic_kaydedilmez(veritabani: vt.Veritabani) -> None:
    with pytest.raises(m.GecersizAd):
        onay.istek_birak(veritabani, m.IndeksSilmeIstegi("Türkçe"))
    with pytest.raises(m.GecersizParca):
        onay.istek_birak(
            veritabani,
            m.TabloOlusturmaIstegi("t", (m.Sutun("a", ("TEXT, UNIQUE(a)",)),)),
        )
    assert onay.bekleyenler(veritabani) == ()


def test_silinen_talep_kimligi_yeniden_kullanilmaz(veritabani: vt.Veritabani) -> None:
    onay.istek_birak(veritabani, KISILER)
    onay.reddet(veritabani, 1)
    with veritabani.islem() as oturum:
        oturum.execute(text(f'DELETE FROM "{onay.SISTEM_TABLOSU}" WHERE kimlik = 1'))
    assert onay.istek_birak(veritabani, KISILER) == 2


def test_olmayan_talep_kimligi(veritabani: vt.Veritabani) -> None:
    with pytest.raises(onay.IstekYok):
        onay.kayit_getir(veritabani, 7)
    with pytest.raises(onay.IstekYok):
        onay.onayla(veritabani, 7)
    with pytest.raises(onay.IstekYok):
        onay.reddet(veritabani, 7)


# --- karar ---------------------------------------------------------------------------


def test_onay_motoru_calistirir_ve_uygulandi_yazar(veritabani: vt.Veritabani) -> None:
    kimlik = onay.istek_birak(veritabani, KISILER)
    kayit = onay.onayla(veritabani, kimlik)
    assert "kisiler" in _tablolar(veritabani)
    assert kayit.durum is onay.Durum.UYGULANDI
    assert kayit.karar is not None and kayit.sonuc is None
    assert onay.bekleyenler(veritabani) == ()


def test_onay_yeniden_kurma_isini_de_uygular(veritabani: vt.Veritabani) -> None:
    onay.onayla(veritabani, onay.istek_birak(veritabani, KISILER))
    with veritabani.islem() as oturum:
        oturum.execute(text("INSERT INTO kisiler (ad_soyad) VALUES ('A')"))
    kayit = onay.onayla(veritabani, onay.istek_birak(veritabani, KISILER_YENI))
    assert kayit.durum is onay.Durum.UYGULANDI
    with veritabani.islem() as oturum:
        oturum.execute(text("INSERT INTO kisiler (id) VALUES (5)"))
        satirlar = oturum.execute(text("SELECT ad_soyad FROM kisiler")).all()
    assert sorted(str(s[0]) for s in satirlar) == ["", "A"]


def test_red_motoru_calistirmaz(veritabani: vt.Veritabani) -> None:
    kimlik = onay.istek_birak(veritabani, KISILER)
    kayit = onay.reddet(veritabani, kimlik)
    assert "kisiler" not in _tablolar(veritabani)
    assert kayit.durum is onay.Durum.REDDEDILDI
    assert kayit.karar is not None
    assert onay.bekleyenler(veritabani) == ()


def test_motor_hatasi_uygulanamadi_olur_ve_yapi_degismez(
    veritabani: vt.Veritabani,
) -> None:
    onay.onayla(veritabani, onay.istek_birak(veritabani, KISILER))
    kimlik = onay.istek_birak(veritabani, KISILER)
    kayit = onay.onayla(veritabani, kimlik)
    assert kayit.durum is onay.Durum.UYGULANAMADI
    assert kayit.sonuc is not None and "already exists" in kayit.sonuc
    assert kayit.karar is not None
    assert onay.bekleyenler(veritabani) == ()
    assert _sutun_turleri(veritabani, "kisiler") == {
        "id": "INTEGER",
        "ad_soyad": "TEXT",
    }


def test_yabanci_anahtar_ihlali_uygulanamadi_olur(veritabani: vt.Veritabani) -> None:
    onay.onayla(veritabani, onay.istek_birak(veritabani, KISILER))
    notlar = m.TabloOlusturmaIstegi(
        "notlar",
        (m.Sutun("id", ("INTEGER", "PRIMARY KEY")), m.Sutun("kisi", ("INTEGER",))),
    )
    onay.onayla(veritabani, onay.istek_birak(veritabani, notlar))
    with veritabani.islem() as oturum:
        oturum.execute(text("INSERT INTO notlar (kisi) VALUES (99)"))
    istek = m.SutunOzelligiDegistirmeIstegi(
        "notlar",
        (
            m.Sutun("id", ("INTEGER", "PRIMARY KEY")),
            m.Sutun("kisi", ("INTEGER", "REFERENCES kisiler(id)")),
        ),
    )
    kayit = onay.onayla(veritabani, onay.istek_birak(veritabani, istek))
    assert kayit.durum is onay.Durum.UYGULANAMADI
    assert kayit.sonuc is not None and "yabancı anahtar ihlali" in kayit.sonuc
    with veritabani.islem() as oturum:
        tanim = oturum.execute(
            text("SELECT sql FROM sqlite_master WHERE name = 'notlar'")
        ).scalar_one()
    assert "REFERENCES" not in str(tanim)


def test_karar_verilmis_istege_ikinci_karar_yok(veritabani: vt.Veritabani) -> None:
    kimlik = onay.istek_birak(veritabani, KISILER)
    onay.onayla(veritabani, kimlik)
    with pytest.raises(onay.ZatenKararVerilmis):
        onay.onayla(veritabani, kimlik)
    with pytest.raises(onay.ZatenKararVerilmis):
        onay.reddet(veritabani, kimlik)
    kimlik = onay.istek_birak(veritabani, m.IndeksSilmeIstegi("ix"))
    onay.reddet(veritabani, kimlik)
    with pytest.raises(onay.ZatenKararVerilmis):
        onay.onayla(veritabani, kimlik)


def test_iki_surec_ayni_istege_karar_verirse_ikincisi_bekler_ve_reddedilir(
    veritabani: vt.Veritabani,
) -> None:
    kimlik = onay.istek_birak(veritabani, KISILER)
    ikinci = vt.Veritabani(veritabani.yol)
    ilk_yazdi = threading.Event()
    ikinci_bitti = threading.Event()
    sonuc: list[BaseException | None] = []

    def ikinci_onaylar() -> None:
        ilk_yazdi.wait()
        try:
            onay.onayla(ikinci, kimlik)
        except Exception as hata:
            sonuc.append(hata)
        else:
            sonuc.append(None)
        ikinci_bitti.set()

    is_parcasi = threading.Thread(target=ikinci_onaylar)
    try:
        with m.islem_ac(veritabani, KISILER) as baglanti:
            onay._karari_yaz(  # pyright: ignore[reportPrivateUsage]
                baglanti, kimlik, onay.Durum.REDDEDILDI, None
            )
            is_parcasi.start()
            ilk_yazdi.set()
            assert not ikinci_bitti.wait(0.5), "ikinci karar ilk commit'i beklemedi"
        is_parcasi.join(10)
    finally:
        ikinci.kapat()
    assert isinstance(sonuc[0], onay.ZatenKararVerilmis)
    assert onay.kayit_getir(veritabani, kimlik).durum is onay.Durum.REDDEDILDI
    assert "kisiler" not in _tablolar(veritabani)


# --- istek metni ----------------------------------------------------------------------


@pytest.mark.parametrize("istek", ORNEK_ISTEKLER, ids=lambda i: type(i).__name__)
def test_istek_json_gidip_gelir(istek: m.YapiIstegi) -> None:
    tur = onay.istek_turu(istek)
    assert onay.istek_coz(tur, onay.istek_json(istek)) == istek


def test_her_istek_turu_kaydedilip_geri_okunur(veritabani: vt.Veritabani) -> None:
    for istek in ORNEK_ISTEKLER:
        kimlik = onay.istek_birak(veritabani, istek)
        kayit = onay.kayit_getir(veritabani, kimlik)
        assert kayit.istek == istek
        assert kayit.sql == m.istek_sql(istek)


def test_bilinmeyen_tur_cozulmez() -> None:
    with pytest.raises(ValueError):
        onay.istek_coz("baska", "{}")
