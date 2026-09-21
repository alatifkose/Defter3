"""İşlem paketi ve taslak testleri (Aşama 4.5): "yazmak ≠ kaydetmek".

Gerçek SQLite dosyası, ``test`` ortamı, ``tmp_path`` altında kök; şema gerçek
göç zinciriyle kurulur. Tanım paketi finans dışı sahte ``ENVANTER``
dünyasıdır: ``DEPO``, ``RAF``, ``URUN`` türleri; ``DEPODA`` (raf → depo, tam
bir etkin üst) ve ``RAFTA`` (ürün → raf, bir ila iki etkin üst) hiyerarşik,
``BENZER`` (ürün → ürün) hiyerarşik olmayan ilişkiler; ``SAYIM`` ve
``DENETIM`` kayıt türleri. Belge sentetik envanter PDF'idir. Çekirdek bunların
anlamını bilmez; hepsi tanım verisidir.

Üç düzey sınanır: uygulama sözleşmesi (``taslak_islemleri`` hataları),
veritabanı kısıtları (servisi atlayan ham SQL aynı ihlali ``IntegrityError``
ile reddeder) ve şema ayrımı (taslak satırlar kesin nesne tablolarına hiçbir
biçimde girmez).
"""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from defteriki import ayarlar as ay
from defteriki.cekirdek import belge_islemleri as bi
from defteriki.cekirdek import gocler
from defteriki.cekirdek import nesne_islemleri as ni
from defteriki.cekirdek import nesne_tablolari as nt
from defteriki.cekirdek import tanim_islemleri as ti
from defteriki.cekirdek import taslak_islemleri as tsi
from defteriki.cekirdek import taslak_tablolari as tst
from defteriki.cekirdek import veritabani as vt
from defteriki.cekirdek.denetim_tablolari import Aktor, AktorTuru
from defteriki.cekirdek.tanim_tablolari import DegerTuru, YasamDurumu
from defteriki.cekirdek.taslak_tablolari import PaketDurumu

DEFTERIKI_DEGISKENLERI = (
    ay.ORTAM_DEGISKENI,
    ay.VERI_KOKU_DEGISKENI,
    ay.VERITABANI_YOLU_DEGISKENI,
    ay.BELGE_DIZINI_DEGISKENI,
    ay.LOG_DIZINI_DEGISKENI,
    ay.GELEN_DIZINI_DEGISKENI,
)
PDF = b"%PDF-1.7\n% envanter listesi: raf A1, 12 kalem\n"
PDF2 = b"%PDF-1.7\n% envanter listesi: raf B2, 3 kalem\n"
OKUMA_ICERIGI: dict[str, Any] = {"satirlar": [{"raf": "A1", "urun": "vida"}]}
SAYIM_ICERIGI: dict[str, Any] = {"adet": 12, "not": "ç ğ ş", "raf": "A1"}
CALISIYOR = PaketDurumu.CALISIYOR
BEKLIYOR = PaketDurumu.BEKLIYOR
IPTAL = PaketDurumu.IPTAL
KULLANICI = Aktor(AktorTuru.KULLANICI, "test-kullanici")


def _iptal_et(oturum: Session, paket_id: int) -> tst.IslemPaketi:
    """``paketi_iptal_et`` artik aktor alir (Asama 4.6: iptal acik karar
    taleplerini gecersiz kilar ve denetim izine yazar)."""
    return tsi.paketi_iptal_et(oturum, paket_id, KULLANICI)


def _beklet(oturum: Session, paket_id: int) -> tst.IslemPaketi:
    """Durum makinesini mekanik olarak ``bekliyor``a alir.

    ``_beklet`` 2026-09-20 kararindan beri acik karar talebi ister
    (elle duraklatma yoktur, bkz. ``taslak_islemleri``). Bu modulun testleri
    mukerrerlik motorunu kurmadan ``bekliyor`` durumunun kendisini sinayabilsin
    diye gecis mekanizmasi dogrudan cagrilir; kapinin kendisi
    ``test_paket_acik_soru_olmadan_bekletilemez`` ile sinanir.
    """
    # Bilerek ic mekanizma: kapiyi degil durumun kendisini siniyoruz.
    return tsi._durumu_degistir(  # pyright: ignore[reportPrivateUsage]
        oturum, paket_id, tst.PaketDurumu.BEKLIYOR
    )


KESIN_NESNE_TABLOLARI = nt.NESNE_TABLOLARI


@pytest.fixture(autouse=True)
def temiz_cevre(monkeypatch: pytest.MonkeyPatch) -> None:
    for degisken in DEFTERIKI_DEGISKENLERI:
        monkeypatch.delenv(degisken, raising=False)


@dataclass(frozen=True, slots=True)
class Ortam:
    veritabani: vt.Veritabani
    gelen: Path
    arsiv: Path


@pytest.fixture
def ortam(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Ortam]:
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(tmp_path / "kok"))
    ayar = ay.ayarlari_yukle()
    ay.dizinleri_hazirla(ayar)
    v = vt.Veritabani(ayar.veritabani_yolu)
    gocler.semayi_yukselt(v)
    yield Ortam(v, ayar.gelen_dizini, ayar.belge_dizini)
    v.kapat()


@dataclass(frozen=True, slots=True)
class Envanter:
    """``ENVANTER`` paketinin sürüm 1 kimlikleri."""

    paket_id: int
    surum_id: int
    depo_id: int
    raf_id: int
    urun_id: int
    depoda_id: int
    rafta_id: int
    benzer_id: int
    sayim_id: int
    denetim_id: int


@pytest.fixture
def env(ortam: Ortam) -> Envanter:
    with ortam.veritabani.islem() as o:
        paket = ti.paket_tanimla(o, "ENVANTER", "Envanter")
        surum = ti.surum_tanimla(o, paket.id, 1)
        depo = ti.nesne_turu_tanimla(o, surum.id, "DEPO", "Depo")
        raf = ti.nesne_turu_tanimla(o, surum.id, "RAF", "Raf")
        urun = ti.nesne_turu_tanimla(o, surum.id, "URUN", "Ürün")
        ti.ozellik_tanimla(o, depo.id, "ad", "Ad", DegerTuru.METIN, zorunlu=True)
        ti.ozellik_tanimla(o, raf.id, "kod", "Kod", DegerTuru.METIN, zorunlu=True)
        ti.ozellik_tanimla(o, raf.id, "kapasite", "Kapasite", DegerTuru.TAM_SAYI)
        ti.ozellik_tanimla(
            o, urun.id, "barkod", "Barkod", DegerTuru.METIN, zorunlu=True
        )
        ti.ozellik_tanimla(o, urun.id, "agirlik", "Ağırlık", DegerTuru.ONDALIK)
        ti.ozellik_tanimla(o, urun.id, "kirilgan", "Kırılgan", DegerTuru.MANTIKSAL)
        depoda = ti.iliski_tanimla(o, surum.id, "DEPODA", "Depoda", raf.id, depo.id)
        rafta = ti.iliski_tanimla(o, surum.id, "RAFTA", "Rafta", urun.id, raf.id)
        benzer = ti.iliski_tanimla(o, surum.id, "BENZER", "Benzer", urun.id, urun.id)
        ti.hiyerarsi_kurali_tanimla(o, depoda.id, 1, 1, YasamDurumu.ETKIN)
        ti.hiyerarsi_kurali_tanimla(o, rafta.id, 1, 2, YasamDurumu.ETKIN)
        sayim = ti.kayit_turu_tanimla(o, surum.id, "SAYIM", "Sayım")
        ti.kayit_alani_tanimla(o, sayim.id, "adet", "Adet", DegerTuru.TAM_SAYI)
        denetim = ti.kayit_turu_tanimla(o, surum.id, "DENETIM", "Denetim")
        return Envanter(
            paket.id,
            surum.id,
            depo.id,
            raf.id,
            urun.id,
            depoda.id,
            rafta.id,
            benzer.id,
            sayim.id,
            denetim.id,
        )


# --- yardımcılar ----------------------------------------------------------------------


def _belge(o: Ortam, ad: str = "envanter.pdf", icerik: bytes = PDF) -> int:
    yol = o.gelen / ad
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_bytes(icerik)
    return bi.belge_al(
        o.veritabani, yol, gelen_dizini=o.gelen, arsiv_dizini=o.arsiv
    ).belge.id


def _okuma(o: Ortam, belge_id: int, tamamla: bool = True) -> int:
    with o.veritabani.islem() as oturum:
        okuma = bi.okuma_baslat(oturum, belge_id, o.arsiv)
        if tamamla:
            bi.okuma_tamamla(oturum, okuma.id, OKUMA_ICERIGI)
        return okuma.id


def _tamam_okuma(o: Ortam, ad: str = "envanter.pdf", icerik: bytes = PDF) -> int:
    return _okuma(o, _belge(o, ad, icerik))


def _paket(o: Ortam, okuma_id: int | None = None) -> int:
    if okuma_id is None:
        okuma_id = _tamam_okuma(o)
    with o.veritabani.islem() as oturum:
        return tsi.paket_olustur(oturum, okuma_id).id


def _sayi(o: Ortam, tablo: str) -> int:
    with o.veritabani.islem() as oturum:
        return int(oturum.execute(text(f"SELECT count(*) FROM {tablo}")).scalar_one())


def _kesin_sayilar(o: Ortam) -> dict[str, int]:
    return {t: _sayi(o, t) for t in KESIN_NESNE_TABLOLARI}


def _taslak_sayilar(o: Ortam) -> dict[str, int]:
    return {t: _sayi(o, t) for t in tst.TASLAK_TABLOLARI}


def _durum(o: Ortam, paket_id: int) -> str:
    with o.veritabani.islem() as oturum:
        return tsi.paket_getir(oturum, paket_id).durum


def _aday(
    o: Ortam,
    paket_id: int,
    tur_id: int,
    ozellikler: dict[str, object] | None = None,
    kaynak_id: int | None = None,
) -> int:
    with o.veritabani.islem() as oturum:
        return tsi.aday_nesne_ekle(oturum, paket_id, tur_id, ozellikler, kaynak_id).id


def _tablolar(o: Ortam) -> list[str]:
    with o.veritabani.motor.connect() as baglanti:
        return sorted(inspect(baglanti).get_table_names())


# --- paket yaşam döngüsü --------------------------------------------------------------


def test_tamamlanmis_okumadan_paket_olusturulur(ortam: Ortam) -> None:
    belge_id = _belge(ortam)
    okuma_id = _okuma(ortam, belge_id)
    with ortam.veritabani.islem() as oturum:
        paket = tsi.paket_olustur(oturum, okuma_id)

    assert paket.durum == CALISIYOR.value
    assert paket.okuma_id == okuma_id
    assert paket.olusturma_zamani == paket.durum_zamani
    assert paket.olusturma_zamani.tzinfo is None
    with ortam.veritabani.islem() as oturum:
        assert tsi.paket_getir(oturum, paket.id).id == paket.id
        assert tsi.paket_belgesi(oturum, paket.id).id == belge_id
        assert [p.id for p in tsi.paketleri_listele(oturum)] == [paket.id]
        assert [p.id for p in tsi.paketleri_listele(oturum, CALISIYOR)] == [paket.id]
        assert tsi.paketleri_listele(oturum, BEKLIYOR) == []
        ayrinti = tsi.paket_ayrinti(oturum, paket.id)
        assert ayrinti.durum is CALISIYOR
        assert (ayrinti.aday_nesne_sayisi, ayrinti.aday_kayit_sayisi) == (0, 0)
    assert _kesin_sayilar(ortam) == dict.fromkeys(KESIN_NESNE_TABLOLARI, 0)


def test_basladi_okumadan_paket_olusturulamaz(ortam: Ortam) -> None:
    okuma_id = _okuma(ortam, _belge(ortam), tamamla=False)
    with pytest.raises(tsi.OkumaDurumuGecersiz, match="basladi"):
        with ortam.veritabani.islem() as oturum:
            tsi.paket_olustur(oturum, okuma_id)
    assert _sayi(ortam, tst.ISLEM_PAKETI) == 0


def test_olmayan_okumadan_paket_olusturulamaz(ortam: Ortam) -> None:
    with pytest.raises(bi.OkumaBulunamadi):
        with ortam.veritabani.islem() as oturum:
            tsi.paket_olustur(oturum, 99)
    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(
                text(
                    "INSERT INTO islem_paketi (okuma_id, durum, olusturma_zamani, "
                    "durum_zamani) VALUES (99, 'calisiyor', '2026-09-19', '2026-09-19')"
                )
            )
    assert _sayi(ortam, tst.ISLEM_PAKETI) == 0


def test_ayni_okumadan_birden_cok_paket_acilabilir(ortam: Ortam) -> None:
    okuma_id = _tamam_okuma(ortam)
    birinci = _paket(ortam, okuma_id)
    ikinci = _paket(ortam, okuma_id)
    assert birinci != ikinci
    with ortam.veritabani.islem() as oturum:
        assert [p.id for p in tsi.paketleri_listele(oturum)] == [birinci, ikinci]


def test_olmayan_paket_bulunamaz(ortam: Ortam) -> None:
    with ortam.veritabani.islem() as oturum:
        for islev in (
            tsi.paket_getir,
            tsi.paket_ayrinti,
            tsi.paket_belgesi,
            tsi.paketi_beklet,
            tsi.paketi_devam_et,
            _iptal_et,
        ):
            with pytest.raises(tsi.PaketBulunamadi):
                islev(oturum, 99)
        with pytest.raises(tsi.PaketBulunamadi):
            tsi.aday_nesne_ekle(oturum, 99, 1)
        with pytest.raises(tsi.PaketBulunamadi):
            tsi.aday_kayit_ekle(oturum, 99, 1, {})


@pytest.mark.parametrize(
    ("adimlar", "beklenen"),
    [
        ((_beklet,), BEKLIYOR),
        ((_beklet, tsi.paketi_devam_et), CALISIYOR),
        ((_iptal_et,), IPTAL),
        ((_beklet, _iptal_et), IPTAL),
        ((_beklet, tsi.paketi_devam_et, _beklet), BEKLIYOR),
    ],
)
def test_izinli_gecisler(
    ortam: Ortam,
    adimlar: tuple[Callable[[Session, int], Any], ...],
    beklenen: PaketDurumu,
) -> None:
    paket_id = _paket(ortam)
    for adim in adimlar:
        with ortam.veritabani.islem() as oturum:
            sonuc = adim(oturum, paket_id)
        assert isinstance(sonuc, tst.IslemPaketi)
    assert _durum(ortam, paket_id) == beklenen.value
    with ortam.veritabani.islem() as oturum:
        paket = tsi.paket_getir(oturum, paket_id)
        assert paket.durum_zamani >= paket.olusturma_zamani
        assert [p.id for p in tsi.paketleri_listele(oturum, beklenen)] == [paket_id]


@pytest.mark.parametrize(
    ("hazirlik", "adim"),
    [
        ((), tsi.paketi_devam_et),  # calisiyor → calisiyor
        ((_beklet,), _beklet),  # bekliyor → bekliyor
        ((_iptal_et,), tsi.paketi_devam_et),  # iptal → calisiyor
        ((_iptal_et,), _beklet),  # iptal → bekliyor
        ((_iptal_et,), _iptal_et),  # iptal → iptal
    ],
)
def test_izinsiz_gecisler_reddedilir(
    ortam: Ortam,
    hazirlik: tuple[Callable[[Session, int], Any], ...],
    adim: Callable[[Session, int], Any],
) -> None:
    paket_id = _paket(ortam)
    for h in hazirlik:
        with ortam.veritabani.islem() as oturum:
            h(oturum, paket_id)
    once = _durum(ortam, paket_id)
    with pytest.raises(tsi.PaketDurumuGecersiz, match="izinli değil"):
        with ortam.veritabani.islem() as oturum:
            adim(oturum, paket_id)
    assert _durum(ortam, paket_id) == once


def test_iptal_terminaldir(ortam: Ortam) -> None:
    paket_id = _paket(ortam)
    with ortam.veritabani.islem() as oturum:
        _iptal_et(oturum, paket_id)
    assert tsi.IZINLI_GECISLER[IPTAL] == frozenset()
    with pytest.raises(tsi.PaketDurumuGecersiz, match="iptal terminaldir"):
        with ortam.veritabani.islem() as oturum:
            tsi.paketi_devam_et(oturum, paket_id)


def test_durum_yalniz_izinli_degerlerden_biri(ortam: Ortam) -> None:
    paket_id = _paket(ortam)
    for deger in ("taslak", "kaydedildi", "CALISIYOR", ""):
        with pytest.raises(IntegrityError, match="durum_gecerli"):
            with ortam.veritabani.islem() as oturum:
                oturum.execute(
                    text("UPDATE islem_paketi SET durum = :d WHERE id = :p"),
                    {"d": deger, "p": paket_id},
                )
    assert _durum(ortam, paket_id) == CALISIYOR.value


def test_ayni_islemde_araya_giren_durum_degisikligi_reddedilir(
    ortam: Ortam, env: Envanter
) -> None:
    """Aynı bağlantıda (eşzamanlılık değil) durum ham SQL ile önceden değişmişse
    koşullu güncelleme satır etkilemez; servis ham hata değil
    ``PaketDurumuGecersiz`` verir, dış işlem kullanılabilir kalır. Gerçek iki
    bağlantılı yarışlar dosyanın sonundaki bölümde."""
    paket_id = _paket(ortam)
    with ortam.veritabani.islem() as oturum:
        paket = tsi.paket_getir(oturum, paket_id)  # kimlik haritasına girdi
        assert paket.durum == CALISIYOR.value
        oturum.execute(
            text("UPDATE islem_paketi SET durum = 'iptal' WHERE id = :p"),
            {"p": paket_id},
        )
        with pytest.raises(tsi.PaketDurumuGecersiz, match="eşzamanlı"):
            _beklet(oturum, paket_id)
        assert tsi.paket_getir(oturum, paket_id).durum == IPTAL.value
        oturum.execute(text("UPDATE tanim_paketi SET kod = 'ENVANTER2'"))
    assert _durum(ortam, paket_id) == IPTAL.value
    with ortam.veritabani.islem() as oturum:
        assert ti.paket_bul(oturum, "ENVANTER2") is not None  # dış işlem commit etti


# --- yazma yetkisi paket durumundan ---------------------------------------------------


def _yazma_islevleri(
    ortam: Ortam, env: Envanter, paket_id: int
) -> list[Callable[[Session], Any]]:
    """Çalışan pakette hazırlanan taslak üzerinde bütün yazma yüzeyi."""
    with ortam.veritabani.islem() as o:
        raf = tsi.aday_nesne_ekle(o, paket_id, env.raf_id, {"kod": "A1"})
        depo = tsi.aday_nesne_ekle(o, paket_id, env.depo_id)
        urun = tsi.aday_nesne_ekle(o, paket_id, env.urun_id)
        fazla = tsi.aday_nesne_ekle(o, paket_id, env.urun_id)
        iliski = tsi.aday_iliski_ekle(o, env.depoda_id, raf.id, depo.id)
        kayit = tsi.aday_kayit_ekle(o, paket_id, env.sayim_id, {"adet": 1})
        bos_kayit = tsi.aday_kayit_ekle(o, paket_id, env.denetim_id, {})
        tsi.aday_kayit_nesne_bagla(o, kayit.id, raf.id)
    return [
        lambda o: tsi.aday_nesne_ekle(o, paket_id, env.raf_id, {"kod": "B"}),
        lambda o: tsi.aday_nesne_sil(o, fazla.id),
        lambda o: tsi.aday_ozellik_yaz(o, raf.id, "kapasite", 3),
        lambda o: tsi.aday_ozellik_sil(o, raf.id, "kod"),
        lambda o: tsi.aday_iliski_ekle(o, env.rafta_id, urun.id, raf.id),
        lambda o: tsi.aday_iliski_kaldir(o, iliski.id),
        lambda o: tsi.aday_kayit_ekle(o, paket_id, env.sayim_id, {}),
        lambda o: tsi.aday_kayit_icerigini_degistir(o, kayit.id, {"adet": 2}),
        lambda o: tsi.aday_kayit_sil(o, bos_kayit.id),
        lambda o: tsi.aday_kayit_nesne_bagla(o, kayit.id, depo.id),
        lambda o: tsi.aday_kayit_nesne_coz(o, kayit.id, raf.id),
    ]


@pytest.mark.parametrize("hedef", [BEKLIYOR, IPTAL])
def test_bekleyen_ve_iptal_pakette_aday_veri_degistirilemez(
    ortam: Ortam, env: Envanter, hedef: PaketDurumu
) -> None:
    paket_id = _paket(ortam)
    islevler = _yazma_islevleri(ortam, env, paket_id)
    with ortam.veritabani.islem() as o:
        (_beklet if hedef is BEKLIYOR else _iptal_et)(o, paket_id)
        once = tsi.paket_ayrinti(o, paket_id)
    taslak_once = _taslak_sayilar(ortam)

    for islev in islevler:
        with pytest.raises(tsi.PaketDurumuGecersiz, match=hedef.value):
            with ortam.veritabani.islem() as o:
                islev(o)

    assert _taslak_sayilar(ortam) == taslak_once
    with ortam.veritabani.islem() as o:  # sorgulanabilir, içeriği okunabilir
        sonra = tsi.paket_ayrinti(o, paket_id)
        assert sonra.durum is hedef
        assert [n.id for n in sonra.aday_nesneler] == [n.id for n in once.aday_nesneler]
        assert [k.id for k in sonra.aday_kayitlar] == [k.id for k in once.aday_kayitlar]
        raf_id = once.aday_nesneler[0].id
        assert tsi.aday_ozellikleri_oku(o, raf_id) == {"kod": "A1"}
        assert tsi.aday_kayit_icerigi(o, once.aday_kayitlar[0].id) == {"adet": 1}
        assert [p.id for p in tsi.paketleri_listele(o, hedef)] == [paket_id]


def test_devam_edilen_pakette_ayni_taslaklarla_yazilir(
    ortam: Ortam, env: Envanter
) -> None:
    paket_id = _paket(ortam)
    islevler = _yazma_islevleri(ortam, env, paket_id)
    with ortam.veritabani.islem() as o:
        _beklet(o, paket_id)
        once = tsi.paket_ayrinti(o, paket_id)
    with ortam.veritabani.islem() as o:
        tsi.paketi_devam_et(o, paket_id)
        sonra = tsi.paket_ayrinti(o, paket_id)
        assert [n.id for n in sonra.aday_nesneler] == [n.id for n in once.aday_nesneler]
        assert [i.id for i in sonra.aday_iliskiler] == [
            i.id for i in once.aday_iliskiler
        ]
        assert [k.id for k in sonra.aday_kayitlar] == [k.id for k in once.aday_kayitlar]
        assert [b.id for b in sonra.kayit_nesne_baglari] == [
            b.id for b in once.kayit_nesne_baglari
        ]
        for islev in islevler:
            islev(o)  # hepsi çalışır
    assert _sayi(ortam, tst.ISLEM_PAKETI) == 1  # yeni paket açılmadı, kopya yok


# --- aday nesne ve özellik ------------------------------------------------------------


def test_aday_nesne_kesin_nesne_uretmez(ortam: Ortam, env: Envanter) -> None:
    paket_id = _paket(ortam)
    with ortam.veritabani.islem() as o:
        aday = tsi.aday_nesne_ekle(
            o, paket_id, env.urun_id, {"barkod": "X1", "agirlik": Decimal("12.50")}
        )
        assert aday.nesne_turu_id == env.urun_id
        assert aday.tanim_surumu_id == env.surum_id
        assert aday.islem_paketi_id == paket_id
        assert aday.kaynak_id is None
        assert aday.olusturma_zamani.tzinfo is None

    assert _kesin_sayilar(ortam) == dict.fromkeys(KESIN_NESNE_TABLOLARI, 0)
    with ortam.veritabani.islem() as o:
        assert ni.nesneleri_listele(o, env.urun_id) == []
        with pytest.raises(ni.NesneBulunamadi):
            ni.nesne_getir(o, aday.id)  # aday kimliği nesne kimliği değildir
        assert tsi.aday_nesne_getir(o, aday.id).id == aday.id
        assert tsi.aday_ozellikleri_oku(o, aday.id) == {
            "barkod": "X1",
            "agirlik": Decimal("12.50"),
        }
        assert not ti.surum_kilitli_mi(o, env.surum_id)  # aday sürümü kilitlemez


def test_zorunlu_ozellik_eksikken_aday_nesne_olusur(
    ortam: Ortam, env: Envanter
) -> None:
    paket_id = _paket(ortam)
    bos = _aday(ortam, paket_id, env.urun_id)
    yarim = _aday(ortam, paket_id, env.urun_id, {"kirilgan": True})
    with ortam.veritabani.islem() as o:
        assert tsi.aday_ozellikleri_oku(o, bos) == {}
        assert tsi.aday_ozellikleri_oku(o, yarim) == {"kirilgan": True}
        tsi.aday_ozellik_yaz(o, bos, "barkod", "sonradan")  # sonradan tamamlanır
        assert tsi.aday_ozellikleri_oku(o, bos) == {"barkod": "sonradan"}
    with pytest.raises(ni.ZorunluOzellikEksik):  # kesin nesne aynı eksikliği reddeder
        with ortam.veritabani.islem() as o:
            ni.nesne_olustur(o, env.urun_id, {"kirilgan": True})


def test_olmayan_tur_ve_tanimsiz_ozellik_reddedilir(
    ortam: Ortam, env: Envanter
) -> None:
    paket_id = _paket(ortam)
    with pytest.raises(ti.TanimBulunamadi, match="nesne türü"):
        with ortam.veritabani.islem() as o:
            tsi.aday_nesne_ekle(o, paket_id, 999)
    with pytest.raises(tsi.GecersizAdayOzellik, match="'renk'"):
        with ortam.veritabani.islem() as o:
            tsi.aday_nesne_ekle(o, paket_id, env.raf_id, {"renk": "mavi"})
    assert _sayi(ortam, tst.ADAY_NESNE) == 0
    aday = _aday(ortam, paket_id, env.raf_id)
    with pytest.raises(tsi.GecersizAdayOzellik, match="'renk'"):
        with ortam.veritabani.islem() as o:
            tsi.aday_ozellik_yaz(o, aday, "renk", "mavi")
    with pytest.raises(tsi.GecersizAdayOzellik, match="yazılı değil"):
        with ortam.veritabani.islem() as o:
            tsi.aday_ozellik_sil(o, aday, "kapasite")
    with pytest.raises(tsi.AdayBulunamadi):
        with ortam.veritabani.islem() as o:
            tsi.aday_ozellik_yaz(o, 999, "kod", "x")


def test_tur_surum_uyusmazligi_veritabaninda_korunur(
    ortam: Ortam, env: Envanter
) -> None:
    paket_id = _paket(ortam)
    with ortam.veritabani.islem() as o:
        surum2 = ti.surum_tanimla(o, env.paket_id, 2)
        okuma_id = tsi.paket_getir(o, paket_id).okuma_id
    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        with ortam.veritabani.islem() as o:
            o.execute(
                text(
                    "INSERT INTO aday_nesne (islem_paketi_id, okuma_id, nesne_turu_id, "
                    "tanim_surumu_id, olusturma_zamani) "
                    "VALUES (:p, :o, :t, :s, '2026-09-19')"
                ),
                {"p": paket_id, "o": okuma_id, "t": env.raf_id, "s": surum2.id},
            )
    assert _sayi(ortam, tst.ADAY_NESNE) == 0


@pytest.mark.parametrize(
    ("kod", "deger"),
    [
        ("kod", 5),
        ("kapasite", "12"),
        ("kapasite", True),
        ("kapasite", 1.5),
    ],
)
def test_raf_yanlis_veri_tipi_reddedilir(
    ortam: Ortam, env: Envanter, kod: str, deger: object
) -> None:
    paket_id = _paket(ortam)
    aday = _aday(ortam, paket_id, env.raf_id, {"kod": "A1"})
    with pytest.raises(tsi.GecersizAdayOzellik, match=f"özellik '{kod}'"):
        with ortam.veritabani.islem() as o:
            tsi.aday_ozellik_yaz(o, aday, kod, deger)
    with pytest.raises(tsi.GecersizAdayOzellik):
        with ortam.veritabani.islem() as o:
            tsi.aday_nesne_ekle(o, paket_id, env.raf_id, {kod: deger})
    with ortam.veritabani.islem() as o:
        assert tsi.aday_ozellikleri_oku(o, aday) == {"kod": "A1"}
    assert _sayi(ortam, tst.ADAY_NESNE) == 1


@pytest.mark.parametrize(
    ("kod", "deger"),
    [
        ("kirilgan", 1),
        ("kirilgan", "1"),
        ("agirlik", 1.5),
        ("agirlik", "1.5"),
        ("agirlik", 1),
        ("agirlik", Decimal("NaN")),
        ("agirlik", Decimal("Infinity")),
    ],
)
def test_urun_mantiksal_ve_ondalik_yanlis_tip_reddedilir(
    ortam: Ortam, env: Envanter, kod: str, deger: object
) -> None:
    paket_id = _paket(ortam)
    aday = _aday(ortam, paket_id, env.urun_id)
    with pytest.raises(tsi.GecersizAdayOzellik):
        with ortam.veritabani.islem() as o:
            tsi.aday_ozellik_yaz(o, aday, kod, deger)
    with ortam.veritabani.islem() as o:
        assert tsi.aday_ozellikleri_oku(o, aday) == {}


def test_dort_deger_turu_kesin_ozellikle_ayni_kanonik_biciminde(
    ortam: Ortam, env: Envanter
) -> None:
    """Aday özellik ve kesin özellik aynı kodlama kuralını kullanır: aynı değer
    iki tabloda da aynı metindir."""
    paket_id = _paket(ortam)
    degerler: dict[str, object] = {
        "barkod": "X1",
        "agirlik": Decimal("12.50"),
        "kirilgan": False,
    }
    aday = _aday(ortam, paket_id, env.urun_id, degerler)
    with ortam.veritabani.islem() as o:
        depo = ni.nesne_olustur(o, env.depo_id, {"ad": "Merkez"})
        raf = ni.nesne_olustur(
            o,
            env.raf_id,
            {"kod": "A1", "kapasite": 7},
            [ni.UstBaglanti(env.depoda_id, depo.id)],
        )
        kesin = ni.nesne_olustur(
            o, env.urun_id, degerler, [ni.UstBaglanti(env.rafta_id, raf.id)]
        )
        aday_raf = tsi.aday_nesne_ekle(o, paket_id, env.raf_id, {"kapasite": 7})
    with ortam.veritabani.islem() as o:
        assert tsi.aday_ozellikleri_oku(o, aday) == ni.ozellikleri_oku(o, kesin.id)
        aday_metin = (
            o.execute(
                text(
                    "SELECT deger FROM aday_nesne_ozelligi WHERE aday_nesne_id = :a "
                    "ORDER BY ozellik_tanimi_id"
                ),
                {"a": aday},
            )
            .scalars()
            .all()
        )
        kesin_metin = (
            o.execute(
                text(
                    "SELECT deger FROM nesne_ozelligi WHERE nesne_id = :n "
                    "ORDER BY ozellik_tanimi_id"
                ),
                {"n": kesin.id},
            )
            .scalars()
            .all()
        )
        assert aday_metin == kesin_metin == ["X1", "125e-1", "0"]
        assert (
            o.execute(
                text("SELECT deger FROM aday_nesne_ozelligi WHERE aday_nesne_id = :a"),
                {"a": aday_raf.id},
            ).scalar_one()
            == "7"
        )


def test_baska_turun_ozelligi_reddedilir(ortam: Ortam, env: Envanter) -> None:
    paket_id = _paket(ortam)
    raf = _aday(ortam, paket_id, env.raf_id)
    with pytest.raises(tsi.GecersizAdayOzellik, match="'barkod'"):
        with ortam.veritabani.islem() as o:
            tsi.aday_ozellik_yaz(o, raf, "barkod", "X")  # ürünün özelliği
    with ortam.veritabani.islem() as o:
        [barkod] = [
            t
            for t in ti.ozellik_tanimlarini_listele(o, env.urun_id)
            if t.kod == "barkod"
        ]
    ekle = text(
        "INSERT INTO aday_nesne_ozelligi (aday_nesne_id, nesne_turu_id, "
        "ozellik_tanimi_id, deger) VALUES (:a, :tur, :tanim, 'X')"
    )
    for tur in (env.raf_id, env.urun_id):  # hangi türü yazarsa yazsın iki FK'dan biri
        with pytest.raises(IntegrityError, match="FOREIGN KEY"):
            with ortam.veritabani.islem() as o:
                o.execute(ekle, {"a": raf, "tur": tur, "tanim": barkod.id})
    assert _sayi(ortam, tst.ADAY_NESNE_OZELLIGI) == 0


def test_ozellik_guncellenir_cift_satir_olmaz(ortam: Ortam, env: Envanter) -> None:
    paket_id = _paket(ortam)
    raf = _aday(ortam, paket_id, env.raf_id, {"kod": "A1"})
    with ortam.veritabani.islem() as o:
        birinci = tsi.aday_ozellik_yaz(o, raf, "kod", "A2")
        ikinci = tsi.aday_ozellik_yaz(o, raf, "kod", "A3")
        assert birinci.id == ikinci.id
        tsi.aday_ozellik_yaz(o, raf, "kapasite", 9)
        assert tsi.aday_ozellikleri_oku(o, raf) == {"kod": "A3", "kapasite": 9}
    assert _sayi(ortam, tst.ADAY_NESNE_OZELLIGI) == 2
    with ortam.veritabani.islem() as o:
        [kod] = [
            t for t in ti.ozellik_tanimlarini_listele(o, env.raf_id) if t.kod == "kod"
        ]
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        with ortam.veritabani.islem() as o:
            o.execute(
                text(
                    "INSERT INTO aday_nesne_ozelligi (aday_nesne_id, nesne_turu_id, "
                    "ozellik_tanimi_id, deger) VALUES (:a, :tur, :tanim, 'kopya')"
                ),
                {"a": raf, "tur": env.raf_id, "tanim": kod.id},
            )
    with ortam.veritabani.islem() as o:  # zorunlu olsa da taslakta silinebilir
        tsi.aday_ozellik_sil(o, raf, "kod")
        assert tsi.aday_ozellikleri_oku(o, raf) == {"kapasite": 9}


def test_aday_nesne_silme_kurallari(ortam: Ortam, env: Envanter) -> None:
    paket_id = _paket(ortam)
    with ortam.veritabani.islem() as o:
        raf = tsi.aday_nesne_ekle(o, paket_id, env.raf_id, {"kod": "A1"})
        depo = tsi.aday_nesne_ekle(o, paket_id, env.depo_id)
        urun = tsi.aday_nesne_ekle(o, paket_id, env.urun_id, {"barkod": "X"})
        iliski = tsi.aday_iliski_ekle(o, env.depoda_id, raf.id, depo.id)
        kayit = tsi.aday_kayit_ekle(o, paket_id, env.sayim_id, {})
        tsi.aday_kayit_nesne_bagla(o, kayit.id, urun.id)

    for aday, mesaj in ((raf.id, "ilişkide"), (urun.id, "kayda bağlı")):
        with pytest.raises(tsi.AdayKullanimda, match=mesaj):
            with ortam.veritabani.islem() as o:
                tsi.aday_nesne_sil(o, aday)
    assert _sayi(ortam, tst.ADAY_NESNE) == 3
    with pytest.raises(IntegrityError, match="FOREIGN KEY"):  # ham SQL de silemez
        with ortam.veritabani.islem() as o:
            o.execute(text("DELETE FROM aday_nesne WHERE id = :a"), {"a": depo.id})

    with ortam.veritabani.islem() as o:
        tsi.aday_iliski_kaldir(o, iliski.id)
        tsi.aday_nesne_sil(o, raf.id)  # özellikleri de gider
        tsi.aday_kayit_nesne_coz(o, kayit.id, urun.id)
        tsi.aday_nesne_sil(o, urun.id)
        with pytest.raises(tsi.AdayBulunamadi):
            tsi.aday_nesne_getir(o, raf.id)
        with pytest.raises(tsi.AdayBulunamadi):
            tsi.aday_nesne_sil(o, raf.id)
    assert _sayi(ortam, tst.ADAY_NESNE) == 1
    assert _sayi(ortam, tst.ADAY_NESNE_OZELLIGI) == 0
    assert _sayi(ortam, tst.ADAY_KAYIT) == 1  # kayıt durur, bağı yok


# --- aday ilişki ----------------------------------------------------------------------


def test_ayni_pakette_dogru_turler_arasinda_aday_iliski(
    ortam: Ortam, env: Envanter
) -> None:
    paket_id = _paket(ortam)
    with ortam.veritabani.islem() as o:
        raf = tsi.aday_nesne_ekle(o, paket_id, env.raf_id)
        depo = tsi.aday_nesne_ekle(o, paket_id, env.depo_id)
        urun_a = tsi.aday_nesne_ekle(o, paket_id, env.urun_id)
        urun_b = tsi.aday_nesne_ekle(o, paket_id, env.urun_id)
        depoda = tsi.aday_iliski_ekle(o, env.depoda_id, raf.id, depo.id)
        benzer = tsi.aday_iliski_ekle(o, env.benzer_id, urun_a.id, urun_b.id)
        kendine = tsi.aday_iliski_ekle(o, env.benzer_id, urun_a.id, urun_a.id)

    assert (depoda.islem_paketi_id, depoda.tanim_surumu_id) == (paket_id, env.surum_id)
    assert (depoda.kaynak_nesne_turu_id, depoda.hedef_nesne_turu_id) == (
        env.raf_id,
        env.depo_id,
    )
    with ortam.veritabani.islem() as o:
        ayrinti = tsi.paket_ayrinti(o, paket_id)
        assert [i.id for i in ayrinti.aday_iliskiler] == [
            depoda.id,
            benzer.id,
            kendine.id,
        ]
    assert _sayi(ortam, nt.NESNE_ILISKISI) == 0


def test_yanlis_kaynak_ve_hedef_turu_reddedilir(ortam: Ortam, env: Envanter) -> None:
    paket_id = _paket(ortam)
    with ortam.veritabani.islem() as o:
        raf = tsi.aday_nesne_ekle(o, paket_id, env.raf_id)
        depo = tsi.aday_nesne_ekle(o, paket_id, env.depo_id)
        urun = tsi.aday_nesne_ekle(o, paket_id, env.urun_id)
    with pytest.raises(tsi.GecersizAdayIliski, match="kaynak aday nesne"):
        with ortam.veritabani.islem() as o:
            tsi.aday_iliski_ekle(o, env.depoda_id, depo.id, raf.id)  # ters
    with pytest.raises(tsi.GecersizAdayIliski, match="hedef aday nesne"):
        with ortam.veritabani.islem() as o:
            tsi.aday_iliski_ekle(o, env.depoda_id, raf.id, urun.id)
    with pytest.raises(ti.TanimBulunamadi):
        with ortam.veritabani.islem() as o:
            tsi.aday_iliski_ekle(o, 999, raf.id, depo.id)
    with pytest.raises(tsi.AdayBulunamadi):
        with ortam.veritabani.islem() as o:
            tsi.aday_iliski_ekle(o, env.depoda_id, raf.id, 999)
    ekle = text(
        "INSERT INTO aday_nesne_iliskisi (islem_paketi_id, iliski_tanimi_id, "
        "tanim_surumu_id, kaynak_nesne_turu_id, hedef_nesne_turu_id, "
        "kaynak_aday_nesne_id, hedef_aday_nesne_id) "
        "VALUES (:p, :i, :s, :kt, :ht, :k, :h)"
    )
    for kt, ht, k, h in (
        (env.depo_id, env.raf_id, depo.id, raf.id),  # tanımın tür çifti ters
        (env.raf_id, env.depo_id, depo.id, raf.id),  # adayların türü uymuyor
        (env.raf_id, env.depo_id, raf.id, urun.id),
    ):
        with pytest.raises(IntegrityError, match="FOREIGN KEY"):
            with ortam.veritabani.islem() as o:
                o.execute(
                    ekle,
                    {
                        "p": paket_id,
                        "i": env.depoda_id,
                        "s": env.surum_id,
                        "kt": kt,
                        "ht": ht,
                        "k": k,
                        "h": h,
                    },
                )
    assert _sayi(ortam, tst.ADAY_NESNE_ILISKISI) == 0


def test_farkli_paketin_aday_nesnesi_baglanamaz(ortam: Ortam, env: Envanter) -> None:
    birinci = _paket(ortam)
    ikinci = _paket(ortam, _tamam_okuma(ortam, "b.pdf", PDF2))
    raf = _aday(ortam, birinci, env.raf_id)
    depo = _aday(ortam, ikinci, env.depo_id)
    with pytest.raises(tsi.PaketUyusmazligi, match="tek paket"):
        with ortam.veritabani.islem() as o:
            tsi.aday_iliski_ekle(o, env.depoda_id, raf, depo)
    for paket in (birinci, ikinci):
        with pytest.raises(IntegrityError, match="FOREIGN KEY"):
            with ortam.veritabani.islem() as o:
                o.execute(
                    text(
                        "INSERT INTO aday_nesne_iliskisi (islem_paketi_id, "
                        "iliski_tanimi_id, tanim_surumu_id, kaynak_nesne_turu_id, "
                        "hedef_nesne_turu_id, kaynak_aday_nesne_id, "
                        "hedef_aday_nesne_id) VALUES (:p, :i, :s, :kt, :ht, :k, :h)"
                    ),
                    {
                        "p": paket,
                        "i": env.depoda_id,
                        "s": env.surum_id,
                        "kt": env.raf_id,
                        "ht": env.depo_id,
                        "k": raf,
                        "h": depo,
                    },
                )
    assert _sayi(ortam, tst.ADAY_NESNE_ILISKISI) == 0


def test_ayni_aday_iliski_iki_kez_olusmaz(ortam: Ortam, env: Envanter) -> None:
    paket_id = _paket(ortam)
    with ortam.veritabani.islem() as o:
        raf = tsi.aday_nesne_ekle(o, paket_id, env.raf_id)
        depo = tsi.aday_nesne_ekle(o, paket_id, env.depo_id)
        tsi.aday_iliski_ekle(o, env.depoda_id, raf.id, depo.id)
    with pytest.raises(tsi.MukerrerAday, match="zaten var"):
        with ortam.veritabani.islem() as o:
            tsi.aday_iliski_ekle(o, env.depoda_id, raf.id, depo.id)
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        with ortam.veritabani.islem() as o:
            o.execute(
                text(
                    "INSERT INTO aday_nesne_iliskisi (islem_paketi_id, "
                    "iliski_tanimi_id, tanim_surumu_id, kaynak_nesne_turu_id, "
                    "hedef_nesne_turu_id, kaynak_aday_nesne_id, hedef_aday_nesne_id) "
                    "VALUES (:p, :i, :s, :kt, :ht, :k, :h)"
                ),
                {
                    "p": paket_id,
                    "i": env.depoda_id,
                    "s": env.surum_id,
                    "kt": env.raf_id,
                    "ht": env.depo_id,
                    "k": raf.id,
                    "h": depo.id,
                },
            )
    assert _sayi(ortam, tst.ADAY_NESNE_ILISKISI) == 1


def test_zorunlu_hiyerarsi_eksik_taslak_var_olabilir(
    ortam: Ortam, env: Envanter
) -> None:
    """``RAFTA`` en az bir etkin üst ister; aday ürün üstsüz durur, üst sonra
    bağlanır ve tekrar kaldırılabilir. Kesin nesne aynı durumu reddeder."""
    paket_id = _paket(ortam)
    with ortam.veritabani.islem() as o:
        urun = tsi.aday_nesne_ekle(o, paket_id, env.urun_id, {"barkod": "X"})
        raf = tsi.aday_nesne_ekle(o, paket_id, env.raf_id)
        assert tsi.paket_ayrinti(o, paket_id).aday_iliskiler == ()
        rafta = tsi.aday_iliski_ekle(o, env.rafta_id, urun.id, raf.id)
        tsi.aday_iliski_kaldir(o, rafta.id)  # en az üst kuralı aranmaz
        with pytest.raises(tsi.AdayBulunamadi):
            tsi.aday_iliski_kaldir(o, rafta.id)
    assert _sayi(ortam, tst.ADAY_NESNE) == 2
    with pytest.raises(ni.HiyerarsiIhlali):
        with ortam.veritabani.islem() as o:
            ni.nesne_olustur(o, env.urun_id, {"barkod": "X"})


# --- aday kayıt -----------------------------------------------------------------------


def test_genel_kayit_turune_bagli_aday_kayit(ortam: Ortam, env: Envanter) -> None:
    paket_id = _paket(ortam)
    with ortam.veritabani.islem() as o:
        sayim = tsi.aday_kayit_ekle(o, paket_id, env.sayim_id, SAYIM_ICERIGI)
        denetim = tsi.aday_kayit_ekle(o, paket_id, env.denetim_id, {})

    assert sayim.kayit_turu_id == env.sayim_id and sayim.islem_paketi_id == paket_id
    assert sayim.kaynak_id is None and sayim.olusturma_zamani.tzinfo is None
    assert sayim.icerik == '{"adet":12,"not":"ç ğ ş","raf":"A1"}'  # kanonik
    assert denetim.icerik == "{}"
    with ortam.veritabani.islem() as o:
        assert tsi.aday_kayit_icerigi(o, sayim.id) == SAYIM_ICERIGI
        assert tsi.aday_kayit_icerigi(o, denetim.id) == {}
        assert [k.id for k in tsi.paket_ayrinti(o, paket_id).aday_kayitlar] == [
            sayim.id,
            denetim.id,
        ]
        with pytest.raises(ti.TanimBulunamadi, match="kayıt türü"):
            tsi.aday_kayit_ekle(o, paket_id, 999, {})
        with pytest.raises(tsi.AdayBulunamadi):
            tsi.aday_kayit_icerigi(o, 999)


def test_aday_kayit_kesin_kayit_degildir(ortam: Ortam, env: Envanter) -> None:
    """Aday kayıt yalnız aday tablodadır: Aşama 4.7'nin kesin ``kayit``
    tabloları (4.7/2'den beri şemada) taslak yazmalarından etkilenmez ve boş
    kalır; kesin kayıt yalnız 4.8'in kesinleştirmesiyle doğar."""
    paket_id = _paket(ortam)
    with ortam.veritabani.islem() as o:
        tsi.aday_kayit_ekle(o, paket_id, env.sayim_id, SAYIM_ICERIGI)
    tablolar = _tablolar(ortam)
    assert [t for t in tablolar if "kayit" in t] == [
        "aday_kayit",
        "aday_kayit_nesne",
        "kayit",
        "kayit_alani",
        "kayit_alani_tanimi",
        "kayit_nesne",
        "kayit_turu",
    ]
    assert _sayi(ortam, tst.ADAY_KAYIT) == 1
    for kesin in ("kayit", "kayit_alani", "kayit_nesne"):
        assert _sayi(ortam, kesin) == 0


@pytest.mark.parametrize(
    "icerik",
    [
        ["liste"],
        "metin",
        None,
        {"x": float("nan")},
        {"x": float("inf")},
        {"x": Decimal("1")},
        {"x": b"bayt"},
        {"x": {1, 2}},
        {1: "sayı", "a": 1},
    ],
)
def test_bozuk_veya_desteklenmeyen_icerik_reddedilir(
    ortam: Ortam, env: Envanter, icerik: Any
) -> None:
    paket_id = _paket(ortam)
    with pytest.raises(tsi.GecersizTaslakIcerik):
        with ortam.veritabani.islem() as o:
            tsi.aday_kayit_ekle(o, paket_id, env.sayim_id, icerik)
    with ortam.veritabani.islem() as o:
        kayit = tsi.aday_kayit_ekle(o, paket_id, env.sayim_id, {"adet": 1})
    with pytest.raises(tsi.GecersizTaslakIcerik):
        with ortam.veritabani.islem() as o:
            tsi.aday_kayit_icerigini_degistir(o, kayit.id, icerik)
    with ortam.veritabani.islem() as o:
        assert tsi.aday_kayit_icerigi(o, kayit.id) == {"adet": 1}
    assert _sayi(ortam, tst.ADAY_KAYIT) == 1


def test_asiri_icerik_reddedilir(ortam: Ortam, env: Envanter) -> None:
    paket_id = _paket(ortam)
    sinir = tsi.AZAMI_ADAY_KAYIT_ICERIGI_BOYUTU
    with pytest.raises(tsi.GecersizTaslakIcerik, match=f"{sinir} bayt"):
        with ortam.veritabani.islem() as o:
            tsi.aday_kayit_ekle(o, paket_id, env.sayim_id, {"x": "a" * sinir})
    with ortam.veritabani.islem() as o:  # sınırın hemen altı geçer
        kayit = tsi.aday_kayit_ekle(o, paket_id, env.sayim_id, {"x": "a" * (sinir - 8)})
        assert len(kayit.icerik.encode()) == sinir


def test_icerik_kisitlari_ham_sql_ile_de_calisir(ortam: Ortam, env: Envanter) -> None:
    paket_id = _paket(ortam)
    with ortam.veritabani.islem() as o:
        okuma_id = tsi.paket_getir(o, paket_id).okuma_id
    ekle = text(
        "INSERT INTO aday_kayit (islem_paketi_id, okuma_id, kayit_turu_id, icerik, "
        "olusturma_zamani) VALUES (:p, :o, :t, :i, '2026-09-19')"
    )
    for icerik in ("{bozuk", "[1, 2]", '"metin"', "1", "null"):
        with pytest.raises(IntegrityError, match="icerik_json_nesnesi"):
            with ortam.veritabani.islem() as o:
                o.execute(
                    ekle, {"p": paket_id, "o": okuma_id, "t": env.sayim_id, "i": icerik}
                )
    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        with ortam.veritabani.islem() as o:
            o.execute(ekle, {"p": paket_id, "o": okuma_id, "t": 999, "i": "{}"})
    with pytest.raises(IntegrityError, match="FOREIGN KEY"):  # okuma paketinki değil
        with ortam.veritabani.islem() as o:
            o.execute(ekle, {"p": paket_id, "o": 99, "t": env.sayim_id, "i": "{}"})
    assert _sayi(ortam, tst.ADAY_KAYIT) == 0


def test_aday_kayit_icerigi_degistirilir_ve_silinir(
    ortam: Ortam, env: Envanter
) -> None:
    paket_id = _paket(ortam)
    with ortam.veritabani.islem() as o:
        kayit = tsi.aday_kayit_ekle(o, paket_id, env.sayim_id, {"adet": 1})
        raf = tsi.aday_nesne_ekle(o, paket_id, env.raf_id)
        tsi.aday_kayit_nesne_bagla(o, kayit.id, raf.id)
        tsi.aday_kayit_icerigini_degistir(o, kayit.id, {"adet": 2, "raf": "A1"})
        assert tsi.aday_kayit_icerigi(o, kayit.id) == {"adet": 2, "raf": "A1"}
        tsi.aday_kayit_sil(o, kayit.id)  # bağı da gider, aday nesne kalır
        with pytest.raises(tsi.AdayBulunamadi):
            tsi.aday_kayit_sil(o, kayit.id)
        ayrinti = tsi.paket_ayrinti(o, paket_id)
        assert ayrinti.aday_kayitlar == () and ayrinti.kayit_nesne_baglari == ()
        assert [n.id for n in ayrinti.aday_nesneler] == [raf.id]


# --- aday kayıt ↔ aday nesne ----------------------------------------------------------


def test_aday_kayit_birden_cok_aday_nesneye_baglanir(
    ortam: Ortam, env: Envanter
) -> None:
    paket_id = _paket(ortam)
    with ortam.veritabani.islem() as o:
        raf = tsi.aday_nesne_ekle(o, paket_id, env.raf_id)
        urun = tsi.aday_nesne_ekle(o, paket_id, env.urun_id)
        kayit = tsi.aday_kayit_ekle(o, paket_id, env.sayim_id, {"adet": 3})
        diger = tsi.aday_kayit_ekle(o, paket_id, env.denetim_id, {})
        bag1 = tsi.aday_kayit_nesne_bagla(o, kayit.id, raf.id)
        bag2 = tsi.aday_kayit_nesne_bagla(o, kayit.id, urun.id)
        bag3 = tsi.aday_kayit_nesne_bagla(o, diger.id, raf.id)  # nesne iki kayıtta

    assert bag1.islem_paketi_id == paket_id
    with ortam.veritabani.islem() as o:
        baglar = tsi.paket_ayrinti(o, paket_id).kayit_nesne_baglari
        assert [(b.id, b.aday_kayit_id, b.aday_nesne_id) for b in baglar] == [
            (bag1.id, kayit.id, raf.id),
            (bag2.id, kayit.id, urun.id),
            (bag3.id, diger.id, raf.id),
        ]
        tsi.aday_kayit_nesne_coz(o, kayit.id, urun.id)
        with pytest.raises(tsi.AdayBulunamadi, match="bağı yok"):
            tsi.aday_kayit_nesne_coz(o, kayit.id, urun.id)
        with pytest.raises(tsi.AdayBulunamadi):
            tsi.aday_kayit_nesne_bagla(o, 999, raf.id)
        with pytest.raises(tsi.AdayBulunamadi):
            tsi.aday_kayit_nesne_bagla(o, kayit.id, 999)
    assert _sayi(ortam, tst.ADAY_KAYIT_NESNE) == 2


def test_baska_paketin_aday_nesnesi_kayda_baglanamaz(
    ortam: Ortam, env: Envanter
) -> None:
    birinci = _paket(ortam)
    ikinci = _paket(ortam, _tamam_okuma(ortam, "b.pdf", PDF2))
    raf = _aday(ortam, ikinci, env.raf_id)
    with ortam.veritabani.islem() as o:
        kayit = tsi.aday_kayit_ekle(o, birinci, env.sayim_id, {})
    with pytest.raises(tsi.PaketUyusmazligi, match="tek paket"):
        with ortam.veritabani.islem() as o:
            tsi.aday_kayit_nesne_bagla(o, kayit.id, raf)
    for paket in (birinci, ikinci):
        with pytest.raises(IntegrityError, match="FOREIGN KEY"):
            with ortam.veritabani.islem() as o:
                o.execute(
                    text(
                        "INSERT INTO aday_kayit_nesne (islem_paketi_id, aday_kayit_id, "
                        "aday_nesne_id) VALUES (:p, :k, :n)"
                    ),
                    {"p": paket, "k": kayit.id, "n": raf},
                )
    assert _sayi(ortam, tst.ADAY_KAYIT_NESNE) == 0


def test_ayni_kayit_nesne_bagi_iki_kez_olusmaz(ortam: Ortam, env: Envanter) -> None:
    paket_id = _paket(ortam)
    with ortam.veritabani.islem() as o:
        raf = tsi.aday_nesne_ekle(o, paket_id, env.raf_id)
        kayit = tsi.aday_kayit_ekle(o, paket_id, env.sayim_id, {})
        tsi.aday_kayit_nesne_bagla(o, kayit.id, raf.id)
    with pytest.raises(tsi.MukerrerAday, match="zaten var"):
        with ortam.veritabani.islem() as o:
            tsi.aday_kayit_nesne_bagla(o, kayit.id, raf.id)
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        with ortam.veritabani.islem() as o:
            o.execute(
                text(
                    "INSERT INTO aday_kayit_nesne (islem_paketi_id, aday_kayit_id, "
                    "aday_nesne_id) VALUES (:p, :k, :n)"
                ),
                {"p": paket_id, "k": kayit.id, "n": raf.id},
            )
    assert _sayi(ortam, tst.ADAY_KAYIT_NESNE) == 1


# --- kaynak / provenance --------------------------------------------------------------


def test_aday_ogeler_paketin_okumasindaki_kaynaga_baglanir(
    ortam: Ortam, env: Envanter
) -> None:
    okuma_id = _tamam_okuma(ortam)
    paket_id = _paket(ortam, okuma_id)
    with ortam.veritabani.islem() as o:
        kaynak = bi.kaynak_olustur(o, okuma_id, {"sayfa": 1, "satir": 3})
        raf = tsi.aday_nesne_ekle(o, paket_id, env.raf_id, kaynak_id=kaynak.id)
        kayit = tsi.aday_kayit_ekle(
            o, paket_id, env.sayim_id, {"adet": 1}, kaynak_id=kaynak.id
        )
        kaynaksiz = tsi.aday_nesne_ekle(o, paket_id, env.depo_id)
    assert raf.kaynak_id == kaynak.id and raf.okuma_id == okuma_id
    assert kayit.kaynak_id == kaynak.id and kayit.okuma_id == okuma_id
    assert kaynaksiz.kaynak_id is None and kaynaksiz.okuma_id == okuma_id
    with ortam.veritabani.islem() as o:
        zincir = bi.kaynak_zinciri(o, kaynak.id)
        assert zincir.belge.id == tsi.paket_belgesi(o, paket_id).id
        with pytest.raises(bi.KaynakBulunamadi):
            tsi.aday_nesne_ekle(o, paket_id, env.raf_id, kaynak_id=999)


def test_baska_okumanin_kaynagi_baglanamaz(ortam: Ortam, env: Envanter) -> None:
    okuma_a = _tamam_okuma(ortam)
    okuma_b = _tamam_okuma(ortam, "b.pdf", PDF2)
    paket_id = _paket(ortam, okuma_a)
    with ortam.veritabani.islem() as o:
        yabanci = bi.kaynak_olustur(o, okuma_b)
    with pytest.raises(tsi.PaketUyusmazligi, match="okuma"):
        with ortam.veritabani.islem() as o:
            tsi.aday_nesne_ekle(o, paket_id, env.raf_id, kaynak_id=yabanci.id)
    with pytest.raises(tsi.PaketUyusmazligi, match="okuma"):
        with ortam.veritabani.islem() as o:
            tsi.aday_kayit_ekle(o, paket_id, env.sayim_id, {}, kaynak_id=yabanci.id)
    # Ham SQL: okuma_id sütunu hangi değeri alırsa alsın iki bileşik FK'dan biri düşer.
    for okuma in (okuma_a, okuma_b):
        with pytest.raises(IntegrityError, match="FOREIGN KEY"):
            with ortam.veritabani.islem() as o:
                o.execute(
                    text(
                        "INSERT INTO aday_nesne (islem_paketi_id, okuma_id, "
                        "nesne_turu_id, tanim_surumu_id, kaynak_id, olusturma_zamani) "
                        "VALUES (:p, :o, :t, :s, :k, '2026-09-19')"
                    ),
                    {
                        "p": paket_id,
                        "o": okuma,
                        "t": env.raf_id,
                        "s": env.surum_id,
                        "k": yabanci.id,
                    },
                )
        with pytest.raises(IntegrityError, match="FOREIGN KEY"):
            with ortam.veritabani.islem() as o:
                o.execute(
                    text(
                        "INSERT INTO aday_kayit (islem_paketi_id, okuma_id, "
                        "kayit_turu_id, kaynak_id, icerik, olusturma_zamani) "
                        "VALUES (:p, :o, :t, :k, '{}', '2026-09-19')"
                    ),
                    {"p": paket_id, "o": okuma, "t": env.sayim_id, "k": yabanci.id},
                )
    assert _sayi(ortam, tst.ADAY_NESNE) == 0 and _sayi(ortam, tst.ADAY_KAYIT) == 0


# --- ANA KABUL TESTİ: yazmak ≠ kaydetmek ---------------------------------------------


def test_yazmak_kaydetmek_degildir(ortam: Ortam, env: Envanter) -> None:
    """Tam çalışma alanı yazılır; kesin dünya hiç değişmez; beklet / devam et /
    iptal boyunca taslak korunur ve iptal sonrası da sorgulanabilir kalır."""
    # Kesin dünyada önceden var olan bir şey: değişmediği daha güçlü görülsün.
    with ortam.veritabani.islem() as o:
        merkez = ni.nesne_olustur(o, env.depo_id, {"ad": "Merkez"})
    kesin_once = _kesin_sayilar(ortam)
    assert kesin_once == {nt.NESNE: 1, nt.NESNE_OZELLIGI: 1, nt.NESNE_ILISKISI: 0}
    tablolar_once = _tablolar(ortam)
    okuma_id = _tamam_okuma(ortam)
    paket_id = _paket(ortam, okuma_id)

    with ortam.veritabani.islem() as o:
        kaynak = bi.kaynak_olustur(o, okuma_id, {"sayfa": 1})
        raf = tsi.aday_nesne_ekle(
            o, paket_id, env.raf_id, {"kod": "A1", "kapasite": 12}, kaynak.id
        )
        urun = tsi.aday_nesne_ekle(o, paket_id, env.urun_id, {"barkod": "X1"})
        tsi.aday_ozellik_yaz(o, urun.id, "agirlik", Decimal("0.250"))
        rafta = tsi.aday_iliski_ekle(o, env.rafta_id, urun.id, raf.id)
        kayit = tsi.aday_kayit_ekle(o, paket_id, env.sayim_id, SAYIM_ICERIGI, kaynak.id)
        bag_raf = tsi.aday_kayit_nesne_bagla(o, kayit.id, raf.id)
        bag_urun = tsi.aday_kayit_nesne_bagla(o, kayit.id, urun.id)

    def kesin_dunya_degismedi() -> None:
        assert _kesin_sayilar(ortam) == kesin_once
        assert _tablolar(ortam) == tablolar_once  # kesin kayıt tablosu oluşmadı
        with ortam.veritabani.islem() as o:
            assert [n.id for n in ni.nesneleri_listele(o, env.depo_id)] == [merkez.id]
            assert ni.nesneleri_listele(o, env.raf_id) == []
            assert ni.nesneleri_listele(o, env.urun_id) == []
            assert ni.ozellikleri_oku(o, merkez.id) == {"ad": "Merkez"}
            assert ni.iliskileri_listele(o, merkez.id) == []
            assert (
                o.execute(
                    text(
                        "SELECT count(*) FROM nesne_ozelligi "
                        "WHERE deger IN ('A1', 'X1')"
                    )
                ).scalar_one()
                == 0
            )

    def taslak_tam() -> tsi.PaketAyrintisi:
        with ortam.veritabani.islem() as o:
            a = tsi.paket_ayrinti(o, paket_id)
            assert [n.id for n in a.aday_nesneler] == [raf.id, urun.id]
            assert a.aday_nesne_sayisi == 2 and a.aday_kayit_sayisi == 1
            assert {(p.aday_nesne_id, p.deger) for p in a.aday_ozellikler} == {
                (raf.id, "A1"),
                (raf.id, "12"),
                (urun.id, "X1"),
                (urun.id, "25e-2"),
            }
            assert [i.id for i in a.aday_iliskiler] == [rafta.id]
            assert [k.id for k in a.aday_kayitlar] == [kayit.id]
            assert [b.id for b in a.kayit_nesne_baglari] == [bag_raf.id, bag_urun.id]
            assert tsi.aday_ozellikleri_oku(o, raf.id) == {"kod": "A1", "kapasite": 12}
            assert tsi.aday_ozellikleri_oku(o, urun.id) == {
                "barkod": "X1",
                "agirlik": Decimal("0.250"),
            }
            assert tsi.aday_kayit_icerigi(o, kayit.id) == SAYIM_ICERIGI
            assert a.aday_nesneler[0].kaynak_id == kaynak.id
            assert a.aday_kayitlar[0].kaynak_id == kaynak.id
            return a

    kesin_dunya_degismedi()
    assert taslak_tam().durum is CALISIYOR

    with ortam.veritabani.islem() as o:  # BEKLIYOR: korunur, yazma durur
        _beklet(o, paket_id)
    assert taslak_tam().durum is BEKLIYOR
    with pytest.raises(tsi.PaketDurumuGecersiz):
        with ortam.veritabani.islem() as o:
            tsi.aday_ozellik_yaz(o, raf.id, "kod", "A2")
    kesin_dunya_degismedi()

    with ortam.veritabani.islem() as o:  # CALISIYOR: aynı taslaklardan devam
        tsi.paketi_devam_et(o, paket_id)
        tsi.aday_ozellik_yaz(o, raf.id, "kod", "A1")  # aynı değer; yazma çalışır
    assert taslak_tam().durum is CALISIYOR
    assert _sayi(ortam, tst.ISLEM_PAKETI) == 1

    with ortam.veritabani.islem() as o:  # IPTAL: kesin dünya yine değişmedi
        _iptal_et(o, paket_id)
    kesin_dunya_degismedi()
    assert taslak_tam().durum is IPTAL  # paket ve taslak içeriği sorgulanabilir
    for tablo, beklenen in {
        tst.ISLEM_PAKETI: 1,
        tst.ADAY_NESNE: 2,
        tst.ADAY_NESNE_OZELLIGI: 4,
        tst.ADAY_NESNE_ILISKISI: 1,
        tst.ADAY_KAYIT: 1,
        tst.ADAY_KAYIT_NESNE: 2,
    }.items():
        assert _sayi(ortam, tablo) == beklenen, tablo
    assert _sayi(ortam, "kaynak") == 1 and _sayi(ortam, "okuma") == 1
    assert _sayi(ortam, "belge") == 1 and _sayi(ortam, "arsiv_dosyasi") == 1
    kilitli: list[Callable[[Session], Any]] = [
        lambda o: tsi.aday_ozellik_yaz(o, raf.id, "kod", "A2"),
        lambda o: tsi.aday_iliski_kaldir(o, rafta.id),
        lambda o: tsi.aday_kayit_sil(o, kayit.id),
        lambda o: tsi.paketi_devam_et(o, paket_id),
    ]
    for islev in kilitli:
        with pytest.raises(tsi.PaketDurumuGecersiz):
            with ortam.veritabani.islem() as o:
                islev(o)
    kesin_dunya_degismedi()
    with ortam.veritabani.islem() as o:
        assert o.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"
        assert o.execute(text("PRAGMA foreign_key_check")).all() == []


# --- şema ayrımı ----------------------------------------------------------------------


def test_taslak_tablolari_kesin_nesne_tablolarina_dis_anahtar_tasimaz(
    ortam: Ortam,
) -> None:
    """Fiziksel ayrım: hiçbir taslak tablo ``nesne`` / ``nesne_ozelligi`` /
    ``nesne_iliskisi`` tablosuna bağlanmaz ve kesin tablolar taslak tablolara
    bağlanmaz. Aday tablolar yalnız tanım, belge zinciri ve birbirlerine bağlıdır."""
    with ortam.veritabani.motor.connect() as baglanti:
        denetci = inspect(baglanti)
        for tablo in tst.TASLAK_TABLOLARI:
            hedefler = {fk["referred_table"] for fk in denetci.get_foreign_keys(tablo)}
            assert not hedefler & set(KESIN_NESNE_TABLOLARI), (tablo, hedefler)
        for tablo in KESIN_NESNE_TABLOLARI:
            hedefler = {fk["referred_table"] for fk in denetci.get_foreign_keys(tablo)}
            assert not hedefler & set(tst.TASLAK_TABLOLARI), (tablo, hedefler)
        assert {
            fk["referred_table"] for fk in denetci.get_foreign_keys(tst.ADAY_NESNE)
        } == {tst.ISLEM_PAKETI, "nesne_turu", "kaynak"}


# --- servis hata atomikliği -----------------------------------------------------------


def test_aday_nesne_yazma_ortasinda_hata_kismi_satir_birakmaz(
    ortam: Ortam, env: Envanter, monkeypatch: pytest.MonkeyPatch
) -> None:
    paket_id = _paket(ortam)
    gercek = tsi.simdi_utc
    patlat = {"aktif": True}

    def bir_kez_patla() -> Any:
        if patlat["aktif"]:
            patlat["aktif"] = False
            raise RuntimeError("sentetik: aday nesne yazılamadı")
        return gercek()

    monkeypatch.setattr(tsi, "simdi_utc", bir_kez_patla)
    with ortam.veritabani.islem() as o:
        with pytest.raises(RuntimeError, match="sentetik"):
            tsi.aday_nesne_ekle(o, paket_id, env.raf_id, {"kod": "A1"})
        assert tsi.paket_ayrinti(o, paket_id).aday_nesneler == ()
        raf = tsi.aday_nesne_ekle(o, paket_id, env.raf_id, {"kod": "A1"})
    assert _sayi(ortam, tst.ADAY_NESNE) == 1
    assert _sayi(ortam, tst.ADAY_NESNE_OZELLIGI) == 1
    with ortam.veritabani.islem() as o:
        assert tsi.aday_ozellikleri_oku(o, raf.id) == {"kod": "A1"}


def test_aday_ozellik_yazma_ortasinda_db_hatasi_kismi_satir_birakmaz(
    ortam: Ortam, env: Envanter
) -> None:
    """Ham SQL ile önceden çakıştırılmış satır: servisin ``flush``ı kısıt hatası
    verir; SAVEPOINT sayesinde dış işlem bozulmaz ve sonraki geçerli iş commit
    olur."""
    paket_id = _paket(ortam)
    raf = _aday(ortam, paket_id, env.raf_id)
    with ortam.veritabani.islem() as o:
        [kod] = [
            t for t in ti.ozellik_tanimlarini_listele(o, env.raf_id) if t.kod == "kod"
        ]
        o.execute(
            text(
                "INSERT INTO aday_nesne_ozelligi (aday_nesne_id, nesne_turu_id, "
                "ozellik_tanimi_id, deger) VALUES (:a, :tur, :tanim, 'ham')"
            ),
            {"a": raf, "tur": env.raf_id, "tanim": kod.id},
        )
        o.execute(text("UPDATE tanim_paketi SET kod = 'ENVANTER2'"))
        try:
            with o.begin_nested():
                o.execute(
                    text(
                        "INSERT INTO aday_nesne_ozelligi (aday_nesne_id, "
                        "nesne_turu_id, ozellik_tanimi_id, deger) "
                        "VALUES (:a, :tur, :tanim, 'kopya')"
                    ),
                    {"a": raf, "tur": env.raf_id, "tanim": kod.id},
                )
        except IntegrityError:
            pass
        tsi.aday_ozellik_yaz(o, raf, "kapasite", 4)
    with ortam.veritabani.islem() as o:
        assert tsi.aday_ozellikleri_oku(o, raf) == {"kod": "ham", "kapasite": 4}
        assert ti.paket_bul(o, "ENVANTER2") is not None


def test_hatalar_ayni_islemde_yakalanir_sonraki_is_commit_olur(
    ortam: Ortam, env: Envanter
) -> None:
    """Aday ilişki tür hatası, aday kayıt JSON hatası, kayıt-nesne paket
    uyuşmazlığı ve paket durum hatası aynı dış işlemde yakalanır; hiçbiri kısmi
    satır bırakmaz; sonraki geçerli işler commit edilir."""
    birinci = _paket(ortam)
    ikinci = _paket(ortam, _tamam_okuma(ortam, "b.pdf", PDF2))
    yabanci = _aday(ortam, ikinci, env.raf_id)
    with ortam.veritabani.islem() as o:
        raf = tsi.aday_nesne_ekle(o, birinci, env.raf_id)
        depo = tsi.aday_nesne_ekle(o, birinci, env.depo_id)
        kayit = tsi.aday_kayit_ekle(o, birinci, env.sayim_id, {})
        for deneme in (
            lambda: tsi.aday_iliski_ekle(o, env.depoda_id, depo.id, raf.id),  # ters
            lambda: tsi.aday_iliski_ekle(o, env.depoda_id, raf.id, yabanci),  # paket
            lambda: tsi.aday_kayit_ekle(o, birinci, env.sayim_id, ["liste"]),  # type: ignore[arg-type]
            lambda: tsi.aday_kayit_icerigini_degistir(o, kayit.id, {"x": float("nan")}),
            lambda: tsi.aday_kayit_nesne_bagla(o, kayit.id, yabanci),
            lambda: tsi.aday_nesne_ekle(o, birinci, env.raf_id, {"kapasite": "x"}),
            lambda: tsi.paketi_devam_et(o, birinci),  # calisiyor → calisiyor
        ):
            try:
                deneme()
            except tsi.IslemPaketiHatasi:
                pass
        iliski = tsi.aday_iliski_ekle(o, env.depoda_id, raf.id, depo.id)
        tsi.aday_kayit_nesne_bagla(o, kayit.id, raf.id)
        tsi.aday_kayit_icerigini_degistir(o, kayit.id, {"adet": 5})
        _beklet(o, birinci)
    with ortam.veritabani.islem() as o:
        a = tsi.paket_ayrinti(o, birinci)
        assert a.durum is BEKLIYOR
        assert [n.id for n in a.aday_nesneler] == [raf.id, depo.id]
        assert a.aday_ozellikler == ()
        assert [i.id for i in a.aday_iliskiler] == [iliski.id]
        assert [k.id for k in a.aday_kayitlar] == [kayit.id]
        assert [(b.aday_kayit_id, b.aday_nesne_id) for b in a.kayit_nesne_baglari] == [
            (kayit.id, raf.id)
        ]
        assert tsi.aday_kayit_icerigi(o, kayit.id) == {"adet": 5}
        assert o.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"
    assert _sayi(ortam, tst.ADAY_KAYIT) == 1


def test_paket_durum_degisimi_yazma_hatasi_durumu_korur(
    ortam: Ortam, monkeypatch: pytest.MonkeyPatch
) -> None:
    paket_id = _paket(ortam)

    def patla() -> Any:
        raise RuntimeError("sentetik")

    with ortam.veritabani.islem() as o:
        monkeypatch.setattr(tsi, "simdi_utc", patla)
        with pytest.raises(RuntimeError, match="sentetik"):
            _beklet(o, paket_id)
        monkeypatch.undo()
        assert tsi.paket_getir(o, paket_id).durum == CALISIYOR.value
        _beklet(o, paket_id)
    assert _durum(ortam, paket_id) == BEKLIYOR.value


def test_paket_olusturma_hatasi_satir_birakmaz(
    ortam: Ortam, monkeypatch: pytest.MonkeyPatch
) -> None:
    okuma_id = _tamam_okuma(ortam)

    def patla() -> Any:
        raise RuntimeError("sentetik")

    with ortam.veritabani.islem() as o:
        monkeypatch.setattr(tsi, "simdi_utc", patla)
        with pytest.raises(RuntimeError, match="sentetik"):
            tsi.paket_olustur(o, okuma_id)
        monkeypatch.undo()
        assert tsi.paketleri_listele(o) == []
        paket = tsi.paket_olustur(o, okuma_id)
    assert _durum(ortam, paket.id) == CALISIYOR.value


# --- gerçek eşzamanlılık: iki bağımsız bağlantı ---------------------------------------
# Her senaryoda iki iş parçacığı kendi ``Veritabani`` örneğiyle (ayrı engine, ayrı
# DBAPI bağlantısı) aynı dosyaya bağlanır. İkisi de kendi işleminde önce okur
# (WAL anlık görüntüsü kurulur), bariyerde buluşur ve servisi çağırır: ikisi de
# ön denetimde "satır yok / paket calisiyor" görür ve yazmaya kalkar. SQLite tam
# birini yazdırır; diğeri kilit / anlık görüntü çakışması alır ve bu ham hata
# servis sınırında ``TaslakYazmaCakismasi``ye çevrilir. Hangi iş parçacığının
# kazanacağı zamanlamaya bağlıdır; testler sonucu değil sözleşmeyi doğrular:
# tek başarılı yazma, ham DB hatası yok, yarım satır yok, yeniden denemede
# olağan domain sonucu.

HAM_DB_HATALARI = (IntegrityError, OperationalError)


def _yaris(
    ortam: Ortam,
    hazirlik: Callable[[Session], object],
    islemler: list[Callable[[Session], object]],
) -> list[object]:
    """Her işlemi ayrı bağlantı ve ayrı işlemde çalıştırır; sonuç ya dönüş değeri
    ya da yükselen istisnadır (aynı sırayla)."""
    bariyer = threading.Barrier(len(islemler), timeout=10)

    def kos(islem: Callable[[Session], object]) -> object:
        v = vt.Veritabani(ortam.veritabani.yol)  # bağımsız bağlantı
        try:
            with v.islem() as o:
                hazirlik(o)  # anlık görüntü bu okumayla kurulur
                bariyer.wait()  # ikisi de aynı eski görüntüyle yazmaya gider
                return islem(o)
        except Exception as hata:  # noqa: BLE001 - sözleşme testi: türü sınanır
            return hata
        finally:
            v.kapat()

    with ThreadPoolExecutor(max_workers=len(islemler)) as havuz:
        return list(havuz.map(kos, islemler))


def _tek_basari(sonuclar: list[object], tur: type) -> tuple[object, Exception]:
    """Tam bir başarı (``tur`` örneği) ve bir domain hatası; ham DB hatası yok."""
    basarilar = [s for s in sonuclar if isinstance(s, tur)]
    hatalar = [s for s in sonuclar if isinstance(s, Exception)]
    assert len(basarilar) == 1 and len(hatalar) == 1, sonuclar
    [hata] = hatalar
    assert not isinstance(hata, HAM_DB_HATALARI), repr(hata)
    assert isinstance(hata, tsi.IslemPaketiHatasi), repr(hata)
    return basarilar[0], hata


def _hazirlik(paket_id: int) -> Callable[[Session], object]:
    return lambda o: tsi.paket_getir(o, paket_id)


def test_yaris_a_ayni_aday_iliski_tek_satir(ortam: Ortam, env: Envanter) -> None:
    paket_id = _paket(ortam)
    raf = _aday(ortam, paket_id, env.raf_id)
    depo = _aday(ortam, paket_id, env.depo_id)

    def ekle(o: Session) -> object:
        return tsi.aday_iliski_ekle(o, env.depoda_id, raf, depo)

    sonuclar = _yaris(ortam, _hazirlik(paket_id), [ekle, ekle])

    _, hata = _tek_basari(sonuclar, tst.AdayNesneIliskisi)
    assert isinstance(hata, (tsi.MukerrerAday, tsi.TaslakYazmaCakismasi))
    assert _sayi(ortam, tst.ADAY_NESNE_ILISKISI) == 1
    with pytest.raises(tsi.MukerrerAday):  # kaybeden yeni işlemde yeniden dener
        with ortam.veritabani.islem() as o:
            ekle(o)
    assert _sayi(ortam, tst.ADAY_NESNE_ILISKISI) == 1


def test_yaris_b_ayni_kayit_nesne_bagi_tek_satir(ortam: Ortam, env: Envanter) -> None:
    paket_id = _paket(ortam)
    raf = _aday(ortam, paket_id, env.raf_id)
    with ortam.veritabani.islem() as o:
        kayit_id = tsi.aday_kayit_ekle(o, paket_id, env.sayim_id, {}).id

    def bagla(o: Session) -> object:
        return tsi.aday_kayit_nesne_bagla(o, kayit_id, raf)

    sonuclar = _yaris(ortam, _hazirlik(paket_id), [bagla, bagla])

    _, hata = _tek_basari(sonuclar, tst.AdayKayitNesne)
    assert isinstance(hata, (tsi.MukerrerAday, tsi.TaslakYazmaCakismasi))
    assert _sayi(ortam, tst.ADAY_KAYIT_NESNE) == 1
    with pytest.raises(tsi.MukerrerAday):
        with ortam.veritabani.islem() as o:
            bagla(o)
    assert _sayi(ortam, tst.ADAY_KAYIT_NESNE) == 1


def test_yaris_c_ayni_yeni_aday_ozellik_farkli_degerler(
    ortam: Ortam, env: Envanter
) -> None:
    """İki bağlantı aynı aday nesnede henüz olmayan aynı özelliğe farklı değer
    yazar: tek satır, değer kazananınki, kaybeden açık çatışma hatası alır;
    sessiz "son yazan kazanır" yok."""
    paket_id = _paket(ortam)
    raf = _aday(ortam, paket_id, env.raf_id)

    def yaz(deger: int) -> Callable[[Session], object]:
        return lambda o: tsi.aday_ozellik_yaz(o, raf, "kapasite", deger)

    sonuclar = _yaris(ortam, _hazirlik(paket_id), [yaz(3), yaz(7)])

    kazanan, hata = _tek_basari(sonuclar, tst.AdayNesneOzelligi)
    assert isinstance(hata, tsi.TaslakYazmaCakismasi)
    assert isinstance(kazanan, tst.AdayNesneOzelligi)
    assert _sayi(ortam, tst.ADAY_NESNE_OZELLIGI) == 1
    with ortam.veritabani.islem() as o:
        assert tsi.aday_ozellikleri_oku(o, raf) == {"kapasite": int(kazanan.deger)}
        assert int(kazanan.deger) in (3, 7)


def test_yaris_d_paket_durumu_tek_gecis(ortam: Ortam) -> None:
    """İki bağlantı aynı ``calisiyor`` paketi aynı anda farklı duruma götürür:
    tam bir geçiş başarılı, diğeri açık domain hatası; ham ``database is
    locked`` sızmaz."""
    paket_id = _paket(ortam)
    sonuclar = _yaris(
        ortam,
        _hazirlik(paket_id),
        [
            lambda o: _beklet(o, paket_id),
            lambda o: _iptal_et(o, paket_id),
        ],
    )

    kazanan, hata = _tek_basari(sonuclar, tst.IslemPaketi)
    assert isinstance(hata, (tsi.TaslakYazmaCakismasi, tsi.PaketDurumuGecersiz))
    assert isinstance(kazanan, tst.IslemPaketi)
    assert kazanan.durum in (BEKLIYOR.value, IPTAL.value)
    assert _durum(ortam, paket_id) == kazanan.durum
    if kazanan.durum == IPTAL.value:  # kaybeden yeniden denerse terminal red
        with pytest.raises(tsi.PaketDurumuGecersiz):
            with ortam.veritabani.islem() as o:
                _beklet(o, paket_id)
        assert _durum(ortam, paket_id) == IPTAL.value


@pytest.mark.parametrize("gecis_gecikmesi", [0.0, 0.2])
def test_yaris_taslak_yazma_ile_paket_durum_gecisi(
    ortam: Ortam, env: Envanter, gecis_gecikmesi: float
) -> None:
    """Bir bağlantı aday nesne yazarken diğeri paketi iptal eder. Kabul edilen
    iki sonuç: taslak önce yazılır sonra durum değişir; ya da durum önce
    değişir ve taslak yazımı çatışma hatası alır, yeniden denemede
    ``PaketDurumuGecersiz``. Yarım satır ve iptal pakete sessiz yazma yok.
    Gecikmesiz koşuda gözlenen sıra "geçiş önce"; geçiş iş parçacığı
    bariyerden sonra kısa beklerse "taslak önce" dalı da gerçekten koşar."""
    paket_id = _paket(ortam)

    def yaz(o: Session) -> object:
        return tsi.aday_nesne_ekle(o, paket_id, env.raf_id, {"kod": "A1"})

    def iptal(o: Session) -> object:
        time.sleep(gecis_gecikmesi)
        return _iptal_et(o, paket_id)

    sonuclar = _yaris(ortam, _hazirlik(paket_id), [yaz, iptal])
    yazma, gecis = sonuclar

    assert not any(isinstance(s, HAM_DB_HATALARI) for s in sonuclar), sonuclar
    if gecis_gecikmesi:  # yazım bitmiş, geçişin anlık görüntüsü eskimiştir
        assert isinstance(yazma, tst.AdayNesne), sonuclar
    if isinstance(yazma, tst.AdayNesne):  # taslak önce yazıldı
        assert isinstance(gecis, tsi.TaslakYazmaCakismasi)
        assert _durum(ortam, paket_id) == CALISIYOR.value
        with ortam.veritabani.islem() as o:  # geçiş yeni işlemde tamamlanır
            iptal(o)
        assert _durum(ortam, paket_id) == IPTAL.value
        assert _sayi(ortam, tst.ADAY_NESNE) == 1
        assert _sayi(ortam, tst.ADAY_NESNE_OZELLIGI) == 1
    else:  # durum önce değişti
        assert isinstance(gecis, tst.IslemPaketi) and gecis.durum == IPTAL.value
        assert isinstance(yazma, tsi.TaslakYazmaCakismasi)
        assert _sayi(ortam, tst.ADAY_NESNE) == 0
        assert _sayi(ortam, tst.ADAY_NESNE_OZELLIGI) == 0
        with pytest.raises(tsi.PaketDurumuGecersiz, match="iptal"):
            with ortam.veritabani.islem() as o:
                yaz(o)
        assert _sayi(ortam, tst.ADAY_NESNE) == 0
    with ortam.veritabani.islem() as o:
        assert o.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"
        assert o.execute(text("PRAGMA foreign_key_check")).all() == []


# --- hata eşlemesi dar: yalnız çakışma ve kendi tablosunun benzersizliği -------------


def _sqlite_hatasi(
    tur: type[Exception], mesaj: str
) -> IntegrityError | OperationalError:
    orijinal = tur(mesaj)
    if issubclass(tur, sqlite3.IntegrityError):
        return IntegrityError("stmt", {}, orijinal)
    return OperationalError("stmt", {}, orijinal)


def test_hata_esleme_yardimcilari_dar() -> None:
    kilit = _sqlite_hatasi(sqlite3.OperationalError, "database is locked")
    mesgul = _sqlite_hatasi(sqlite3.OperationalError, "database is busy")
    disk = _sqlite_hatasi(sqlite3.OperationalError, "disk I/O error")
    tablo = _sqlite_hatasi(sqlite3.OperationalError, "no such table: x")
    assert isinstance(kilit, OperationalError) and tsi.kilit_cakismasi_mi(kilit)
    assert isinstance(mesgul, OperationalError) and tsi.kilit_cakismasi_mi(mesgul)
    assert isinstance(disk, OperationalError) and not tsi.kilit_cakismasi_mi(disk)
    assert isinstance(tablo, OperationalError) and not tsi.kilit_cakismasi_mi(tablo)

    ayni = _sqlite_hatasi(
        sqlite3.IntegrityError,
        "UNIQUE constraint failed: aday_nesne_iliskisi.iliski_tanimi_id, "
        "aday_nesne_iliskisi.kaynak_aday_nesne_id",
    )
    baska = _sqlite_hatasi(
        sqlite3.IntegrityError, "UNIQUE constraint failed: aday_kayit_nesne.x"
    )
    fk = _sqlite_hatasi(sqlite3.IntegrityError, "FOREIGN KEY constraint failed")
    kontrol = _sqlite_hatasi(
        sqlite3.IntegrityError, "CHECK constraint failed: ck_aday_kayit_icerik"
    )
    assert isinstance(ayni, IntegrityError)
    assert tsi.benzersizlik_ihlali_mi(ayni, tst.ADAY_NESNE_ILISKISI)
    for hata in (baska, fk, kontrol):
        assert isinstance(hata, IntegrityError)
        assert not tsi.benzersizlik_ihlali_mi(hata, tst.ADAY_NESNE_ILISKISI)


def test_yazma_siniri_yalniz_kendi_tablosunun_benzersizligini_esler(
    ortam: Ortam, env: Envanter
) -> None:
    """Gerçek veritabanında: aynı tablonun benzersizlik ihlali verilen domain
    hatasına döner; başka tablonun benzersizliği, dış anahtar ve kontrol
    kısıtı ham ``IntegrityError`` olarak yükselir; dış işlem kullanılabilir
    kalır."""
    paket_id = _paket(ortam)
    with ortam.veritabani.islem() as o:
        raf = tsi.aday_nesne_ekle(o, paket_id, env.raf_id)
        depo = tsi.aday_nesne_ekle(o, paket_id, env.depo_id)
        tsi.aday_iliski_ekle(o, env.depoda_id, raf.id, depo.id)
        kayit = tsi.aday_kayit_ekle(o, paket_id, env.sayim_id, {})
        tsi.aday_kayit_nesne_bagla(o, kayit.id, raf.id)
        okuma_id = tsi.paket_getir(o, paket_id).okuma_id
    iliski_kopya = text(
        "INSERT INTO aday_nesne_iliskisi (islem_paketi_id, iliski_tanimi_id, "
        "tanim_surumu_id, kaynak_nesne_turu_id, hedef_nesne_turu_id, "
        "kaynak_aday_nesne_id, hedef_aday_nesne_id) VALUES (:p, :i, :s, :kt, :ht, "
        ":k, :h)"
    )
    iliski_degerleri = {
        "p": paket_id,
        "i": env.depoda_id,
        "s": env.surum_id,
        "kt": env.raf_id,
        "ht": env.depo_id,
        "k": raf.id,
        "h": depo.id,
    }
    bag_kopya = text(
        "INSERT INTO aday_kayit_nesne (islem_paketi_id, aday_kayit_id, "
        "aday_nesne_id) VALUES (:p, :k, :n)"
    )
    bag_degerleri = {"p": paket_id, "k": kayit.id, "n": raf.id}
    sinir = tsi._yazma_siniri  # pyright: ignore[reportPrivateUsage]

    with ortam.veritabani.islem() as o:
        with pytest.raises(tsi.MukerrerAday, match="sentetik"):
            with sinir(o, tst.ADAY_NESNE_ILISKISI, tsi.MukerrerAday, "sentetik"):
                o.execute(iliski_kopya, iliski_degerleri)
        with pytest.raises(IntegrityError, match="UNIQUE"):  # başka tablo
            with sinir(o, tst.ADAY_NESNE_ILISKISI, tsi.MukerrerAday, "sentetik"):
                o.execute(bag_kopya, bag_degerleri)
        with pytest.raises(IntegrityError, match="FOREIGN KEY"):
            with sinir(o, tst.ADAY_KAYIT, tsi.MukerrerAday, "sentetik"):
                o.execute(
                    text(
                        "INSERT INTO aday_kayit (islem_paketi_id, okuma_id, "
                        "kayit_turu_id, icerik, olusturma_zamani) "
                        "VALUES (:p, :o, 999, '{}', '2026-09-19')"
                    ),
                    {"p": paket_id, "o": okuma_id},
                )
        with pytest.raises(IntegrityError, match="CHECK"):
            with sinir(o, tst.ADAY_KAYIT, tsi.MukerrerAday, "sentetik"):
                o.execute(
                    text(
                        "INSERT INTO aday_kayit (islem_paketi_id, okuma_id, "
                        "kayit_turu_id, icerik, olusturma_zamani) "
                        "VALUES (:p, :o, :t, '[]', '2026-09-19')"
                    ),
                    {"p": paket_id, "o": okuma_id, "t": env.sayim_id},
                )
        with pytest.raises(IntegrityError, match="UNIQUE"):  # tablo verilmedi
            with sinir(o):
                o.execute(iliski_kopya, iliski_degerleri)
        tsi.aday_ozellik_yaz(o, raf.id, "kod", "A1")  # dış işlem kullanılabilir
    with ortam.veritabani.islem() as o:
        assert tsi.aday_ozellikleri_oku(o, raf.id) == {"kod": "A1"}
    assert _sayi(ortam, tst.ADAY_NESNE_ILISKISI) == 1
    assert _sayi(ortam, tst.ADAY_KAYIT_NESNE) == 1


def test_paket_acik_soru_olmadan_bekletilemez(ortam: Ortam) -> None:
    """Elle duraklatma yoktur (karar 2026-09-20): ``bekliyor`` tek bir anlama
    gelir, cevaplanmamis bir karar talebi var. Acik soru olmadan bekletme
    reddedilir ve durum degismez; mukerrerlik motoru soruyu yazdiktan sonra
    ayni kapidan gecer (``test_mukerrerlik``)."""
    paket_id = _paket(ortam)
    with pytest.raises(tsi.PaketDurumuGecersiz, match="Elle duraklatma yoktur"):
        with ortam.veritabani.islem() as oturum:
            tsi.paketi_beklet(oturum, paket_id)
    assert _durum(ortam, paket_id) == CALISIYOR.value
