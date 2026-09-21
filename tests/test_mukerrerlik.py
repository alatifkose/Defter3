"""Onay ve mükerrerlik testleri (Aşama 4.6).

Gerçek SQLite dosyası, ``test`` ortamı, ``tmp_path`` altında kök; şema gerçek
göç zinciriyle kurulur. Tanım paketi finans dışı sahte ``ENVANTER``
dünyasıdır: ``DEPO``, ``RAF``, ``URUN`` türleri; ``DEPODA`` (raf → depo, tam
bir etkin üst), ``RAFTA`` (ürün → raf, bir ila iki etkin üst) ve ``ALTINDA``
(raf → raf, en çok bir üst) hiyerarşik, ``BENZER`` (ürün → ürün) hiyerarşik
olmayan ilişkiler; ``SAYIM`` kayıt türü. Mükerrerlik şartı olarak seçilen
özellikler (``harici_kimlik``, ``sehir``, ``seri_no``, ``agirlik``) de nötr
tanım verisidir; çekirdek anlamlarını bilmez.

Sınanan sözleşme: mükerrerlik bir benzersizlik kısıtı değildir; şartlar
kullanıcı tarafından seçilir ve çoklu şart VEYA mantığındadır; eşleşme yalnız
kalıcı şüphe ve karar talebi doğurur; paket açık talebi varken ``BEKLIYOR``
kalır; karar (AYNI / AYRI / KARARSIZ) kalıcıdır ve iki kez uygulanmaz;
birleştirme atomiktir ve nesne motorunun kurallarına uyar; denetim izi
aktörlüdür ve ham değer taşımaz.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from defteriki import ayarlar as ay
from defteriki.cekirdek import belge_islemleri as bi
from defteriki.cekirdek import denetim_islemleri as di
from defteriki.cekirdek import denetim_tablolari as dt
from defteriki.cekirdek import gocler
from defteriki.cekirdek import kayit_islemleri as ki
from defteriki.cekirdek import mukerrerlik_islemleri as mu
from defteriki.cekirdek import mukerrerlik_tablolari as mt
from defteriki.cekirdek import nesne_islemleri as ni
from defteriki.cekirdek import nesne_tablolari as nt
from defteriki.cekirdek import tanim_islemleri as ti
from defteriki.cekirdek import taslak_islemleri as tsi
from defteriki.cekirdek import veritabani as vt
from defteriki.cekirdek.denetim_tablolari import Aktor, AktorTuru, DenetimOlayi
from defteriki.cekirdek.mukerrerlik_tablolari import Karar, TalepDurumu
from defteriki.cekirdek.tanim_tablolari import DegerTuru, OzellikTanimi, YasamDurumu
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
OKUMA_ICERIGI: dict[str, Any] = {"satirlar": [{"raf": "A1", "urun": "vida"}]}
KULLANICI = Aktor(AktorTuru.KULLANICI, "test-kullanici")
AJAN = Aktor(AktorTuru.AJAN, "test-ajan")
CALISIYOR = PaketDurumu.CALISIYOR
BEKLIYOR = PaketDurumu.BEKLIYOR
IPTAL = PaketDurumu.IPTAL
HAM_DB_HATALARI = (IntegrityError, OperationalError)


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
    altinda_id: int
    benzer_id: int
    sayim_id: int


@pytest.fixture
def env(ortam: Ortam) -> Envanter:
    with ortam.veritabani.islem() as o:
        paket = ti.paket_tanimla(o, "ENVANTER", "Envanter")
        surum = ti.surum_tanimla(o, paket.id, 1)
        depo = ti.nesne_turu_tanimla(o, surum.id, "DEPO", "Depo")
        raf = ti.nesne_turu_tanimla(o, surum.id, "RAF", "Raf")
        urun = ti.nesne_turu_tanimla(o, surum.id, "URUN", "Ürün")
        ti.ozellik_tanimla(o, depo.id, "ad", "Ad", DegerTuru.METIN, zorunlu=True)
        ti.ozellik_tanimla(o, depo.id, "harici_kimlik", "Harici", DegerTuru.METIN)
        ti.ozellik_tanimla(o, depo.id, "sehir", "Şehir", DegerTuru.METIN)
        ti.ozellik_tanimla(o, raf.id, "kod", "Kod", DegerTuru.METIN, zorunlu=True)
        ti.ozellik_tanimla(o, raf.id, "seri_no", "Seri No", DegerTuru.METIN)
        ti.ozellik_tanimla(o, urun.id, "barkod", "Barkod", DegerTuru.METIN)
        ti.ozellik_tanimla(o, urun.id, "agirlik", "Ağırlık", DegerTuru.ONDALIK)
        depoda = ti.iliski_tanimla(o, surum.id, "DEPODA", "Depoda", raf.id, depo.id)
        rafta = ti.iliski_tanimla(o, surum.id, "RAFTA", "Rafta", urun.id, raf.id)
        altinda = ti.iliski_tanimla(o, surum.id, "ALTINDA", "Altında", raf.id, raf.id)
        benzer = ti.iliski_tanimla(o, surum.id, "BENZER", "Benzer", urun.id, urun.id)
        ti.hiyerarsi_kurali_tanimla(o, depoda.id, 1, 1, YasamDurumu.ETKIN)
        ti.hiyerarsi_kurali_tanimla(o, rafta.id, 1, 2, YasamDurumu.ETKIN)
        ti.hiyerarsi_kurali_tanimla(o, altinda.id, 0, 1, YasamDurumu.ETKIN)
        sayim = ti.kayit_turu_tanimla(o, surum.id, "SAYIM", "Sayım")
        ti.kayit_alani_tanimla(o, sayim.id, "adet", "Adet", DegerTuru.TAM_SAYI)
        return Envanter(
            paket.id,
            surum.id,
            depo.id,
            raf.id,
            urun.id,
            depoda.id,
            rafta.id,
            altinda.id,
            benzer.id,
            sayim.id,
        )


# --- yardımcılar ----------------------------------------------------------------------


def _depo(ortam: Ortam, env: Envanter, **ozellikler: object) -> int:
    with ortam.veritabani.islem() as o:
        return ni.nesne_olustur(o, env.depo_id, {"ad": "Depo", **ozellikler}).id


def _raf(ortam: Ortam, env: Envanter, depo_id: int, kod: str, **ek: object) -> int:
    with ortam.veritabani.islem() as o:
        return ni.nesne_olustur(
            o,
            env.raf_id,
            {"kod": kod, **ek},
            [ni.UstBaglanti(env.depoda_id, depo_id)],
        ).id


def _urun(ortam: Ortam, env: Envanter, raf_idleri: list[int], **ozellikler: object):
    with ortam.veritabani.islem() as o:
        return ni.nesne_olustur(
            o,
            env.urun_id,
            dict(ozellikler),
            [ni.UstBaglanti(env.rafta_id, r) for r in raf_idleri],
        ).id


def _sart(ortam: Ortam, nesne_id: int, kodlar: list[str]) -> None:
    with ortam.veritabani.islem() as o:
        mu.nesne_sarti_ekle(o, nesne_id, kodlar, KULLANICI)


def _denetle(ortam: Ortam, nesne_id: int, paket_id: int | None = None) -> list[int]:
    with ortam.veritabani.islem() as o:
        return [t.id for t in mu.nesneyi_denetle(o, nesne_id, KULLANICI, paket_id)]


def _paket(ortam: Ortam) -> int:
    yol = ortam.gelen / "envanter.pdf"
    yol.write_bytes(PDF)
    sonuc = bi.belge_al(
        ortam.veritabani, yol, gelen_dizini=ortam.gelen, arsiv_dizini=ortam.arsiv
    )
    with ortam.veritabani.islem() as o:
        okuma = bi.okuma_baslat(o, sonuc.belge.id, ortam.arsiv)
        bi.okuma_tamamla(o, okuma.id, OKUMA_ICERIGI)
        return tsi.paket_olustur(o, okuma.id).id


def _aday(
    ortam: Ortam,
    paket_id: int,
    nesne_turu_id: int,
    ozellikler: dict[str, object],
    sartlar: list[str] | None = None,
) -> int:
    with ortam.veritabani.islem() as o:
        aday = tsi.aday_nesne_ekle(o, paket_id, nesne_turu_id, ozellikler)
        if sartlar:
            mu.aday_sarti_ekle(o, aday.id, sartlar, KULLANICI)
        return aday.id


def _adayi_denetle(ortam: Ortam, aday_id: int) -> list[int]:
    with ortam.veritabani.islem() as o:
        return [t.id for t in mu.adayi_denetle(o, aday_id, KULLANICI)]


def _karar(
    ortam: Ortam, talep_id: int, karar: Karar, gerekce: str | None = None
) -> mu.KararSonucu:
    with ortam.veritabani.islem() as o:
        return mu.karar_ver(o, talep_id, karar, KULLANICI, gerekce)


def _iptal_et(ortam: Ortam, paket_id: int) -> None:
    with ortam.veritabani.islem() as o:
        tsi.paketi_iptal_et(o, paket_id, KULLANICI)


def _paket_durumu(ortam: Ortam, paket_id: int) -> str:
    with ortam.veritabani.islem() as o:
        return tsi.paket_getir(o, paket_id).durum


def _ozellik_id(ortam: Ortam, nesne_turu_id: int, kod: str) -> int:
    with ortam.veritabani.islem() as o:
        return int(
            o.execute(
                select(OzellikTanimi.id).where(
                    OzellikTanimi.nesne_turu_id == nesne_turu_id,
                    OzellikTanimi.kod == kod,
                )
            ).scalar_one()
        )


def _sayi(ortam: Ortam, tablo: str) -> int:
    with ortam.veritabani.islem() as o:
        return int(o.execute(text(f"SELECT count(*) FROM {tablo}")).scalar_one())


# --- 1-8: şart seçimi ve eşleşme semantiği --------------------------------------------


def test_sifir_sart_protokolu_calistirmaz(ortam: Ortam, env: Envanter) -> None:
    """Hiçbir uçta şart yoksa aynı değerler bile şüphe doğurmaz."""
    _depo(ortam, env, harici_kimlik="X1", sehir="Edirne")
    ikinci = _depo(ortam, env, harici_kimlik="X1", sehir="Edirne")
    assert _denetle(ortam, ikinci) == []
    assert _sayi(ortam, mt.KARAR_TALEBI) == 0


def test_tek_sart_eslesince_suphe_acilir(ortam: Ortam, env: Envanter) -> None:
    ilk = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, ilk, ["harici_kimlik"])
    ikinci = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, ikinci, ["harici_kimlik"])
    [talep_id] = _denetle(ortam, ikinci)
    with ortam.veritabani.islem() as o:
        talep = mu.karar_talebi_getir(o, talep_id)
        assert talep.hedef_nesne_id == ilk and talep.kaynak_nesne_id == ikinci
        assert talep.durum == TalepDurumu.ACIK.value
        assert talep.eslesen_ozellik_tanimi_id == _ozellik_id(
            ortam, env.depo_id, "harici_kimlik"
        )


@pytest.mark.parametrize(
    ("ikinci_ozellikler", "beklenen_kod"),
    [
        ({"harici_kimlik": "X1", "sehir": "Ankara"}, "harici_kimlik"),
        ({"harici_kimlik": "X9", "sehir": "Edirne"}, "sehir"),
    ],
)
def test_iki_sartta_veya_mantigi(
    ortam: Ortam,
    env: Envanter,
    ikinci_ozellikler: dict[str, object],
    beklenen_kod: str,
) -> None:
    """Birden fazla şart VE değil VEYA: yalnız biri eşleşse de şüphe doğar."""
    ilk = _depo(ortam, env, harici_kimlik="X1", sehir="Edirne")
    _sart(ortam, ilk, ["harici_kimlik", "sehir"])
    ikinci = _depo(ortam, env, **ikinci_ozellikler)
    _sart(ortam, ikinci, ["harici_kimlik", "sehir"])
    [talep_id] = _denetle(ortam, ikinci)
    with ortam.veritabani.islem() as o:
        talep = mu.karar_talebi_getir(o, talep_id)
    assert talep.eslesen_ozellik_tanimi_id == _ozellik_id(
        ortam, env.depo_id, beklenen_kod
    )


def test_hicbir_sart_eslesmezse_suphe_yok(ortam: Ortam, env: Envanter) -> None:
    ilk = _depo(ortam, env, harici_kimlik="X1", sehir="Edirne")
    _sart(ortam, ilk, ["harici_kimlik", "sehir"])
    ikinci = _depo(ortam, env, harici_kimlik="X9", sehir="Ankara")
    _sart(ortam, ikinci, ["harici_kimlik", "sehir"])
    assert _denetle(ortam, ikinci) == []


def test_secilmemis_ozellik_eslesse_de_suphe_yok(ortam: Ortam, env: Envanter) -> None:
    """Şart yalnız ``harici_kimlik``; ``sehir`` ikisinde de aynı ama şüphe yok."""
    ilk = _depo(ortam, env, harici_kimlik="X1", sehir="Edirne")
    _sart(ortam, ilk, ["harici_kimlik"])
    ikinci = _depo(ortam, env, harici_kimlik="X9", sehir="Edirne")
    _sart(ortam, ikinci, ["harici_kimlik"])
    assert _denetle(ortam, ikinci) == []


def test_iki_yonlu_tarama_sartsiz_ucu_de_yakalar(ortam: Ortam, env: Envanter) -> None:
    """Şart seçmemiş yeni nesne, şart seçmiş mevcut nesnenin korumasından kaçamaz."""
    ilk = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, ilk, ["harici_kimlik"])
    ikinci = _depo(ortam, env, harici_kimlik="X1")  # şart seçilmedi
    [talep_id] = _denetle(ortam, ikinci)
    with ortam.veritabani.islem() as o:
        assert mu.karar_talebi_getir(o, talep_id).kaynak_nesne_id == ikinci


def test_baska_turun_ozelligi_sart_secilemez(ortam: Ortam, env: Envanter) -> None:
    depo = _depo(ortam, env, harici_kimlik="X1")
    with pytest.raises(mu.GecersizSart, match="seri_no"):
        with ortam.veritabani.islem() as o:
            mu.nesne_sarti_ekle(o, depo, ["seri_no"], KULLANICI)
    with pytest.raises(mu.GecersizSart, match="en az bir"):
        with ortam.veritabani.islem() as o:
            mu.nesne_sarti_ekle(o, depo, [], KULLANICI)
    assert _sayi(ortam, mt.NESNE_MUKERRERLIK_SARTI) == 0


def test_baska_turun_ozelligi_veritabaninda_da_reddedilir(
    ortam: Ortam, env: Envanter
) -> None:
    """Servisi atlayan ham SQL aynı ihlali bileşik dış anahtarla reddeder."""
    depo = _depo(ortam, env, harici_kimlik="X1")
    seri_no = _ozellik_id(ortam, env.raf_id, "seri_no")
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with ortam.veritabani.islem() as o:
            o.execute(
                text(
                    "INSERT INTO nesne_mukerrerlik_sarti "
                    "(nesne_id, nesne_turu_id, ozellik_tanimi_id) "
                    "VALUES (:n, :t, :o)"
                ),
                {"n": depo, "t": env.depo_id, "o": seri_no},
            )


def test_ondalik_sayisal_esdegerlik_eslesir(ortam: Ortam, env: Envanter) -> None:
    """``12.50`` ile ``12.5`` aynı kanonik metne kodlanır ve eşleşir; ``12.6``
    eşleşmez (kanonik kodlama, Aşama 4.6 kendi karşılaştırmasını icat etmez)."""
    depo = _depo(ortam, env)
    raf = _raf(ortam, env, depo, "A1")
    ilk = _urun(ortam, env, [raf], barkod="B1", agirlik=Decimal("12.50"))
    _sart(ortam, ilk, ["agirlik"])
    esit = _urun(ortam, env, [raf], barkod="B2", agirlik=Decimal("12.5"))
    _sart(ortam, esit, ["agirlik"])
    farkli = _urun(ortam, env, [raf], barkod="B3", agirlik=Decimal("12.6"))
    _sart(ortam, farkli, ["agirlik"])
    assert len(_denetle(ortam, esit)) == 1
    assert _denetle(ortam, farkli) == []


# --- 9-11: şüphe kalıcıdır, otomatik karar yoktur -------------------------------------


def test_eslesme_otomatik_ayni_karari_vermez(ortam: Ortam, env: Envanter) -> None:
    """Eşleşme birleştirme değildir: iki nesne de etkin kalır, birleşim yoktur."""
    ilk = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, ilk, ["harici_kimlik"])
    ikinci = _depo(ortam, env, harici_kimlik="X1")
    [talep_id] = _denetle(ortam, ikinci)
    with ortam.veritabani.islem() as o:
        talep = mu.karar_talebi_getir(o, talep_id)
        assert talep.karar is None and talep.durum == TalepDurumu.ACIK.value
        assert ni.nesne_getir(o, ikinci).yasam_durumu == YasamDurumu.ETKIN.value
        assert mu.nesne_birlesimini_bul(o, ikinci) is None
    assert _sayi(ortam, mt.NESNE_BIRLESIMI) == 0


def test_suphe_kalici_karar_talebi_uretir(ortam: Ortam, env: Envanter) -> None:
    """Talep kimliği kalıcıdır: yeni bağlantıda da okunur (BEKLIYOR protokolü)."""
    ilk = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, ilk, ["harici_kimlik"])
    ikinci = _depo(ortam, env, harici_kimlik="X1")
    [talep_id] = _denetle(ortam, ikinci)
    ikinci_baglanti = vt.Veritabani(ortam.veritabani.yol)
    try:
        with ikinci_baglanti.islem() as o:
            talep = mu.karar_talebi_getir(o, talep_id)
            assert talep.acan_aktor_kimligi == KULLANICI.kimlik
            acik = mu.talepleri_listele(o, durum=TalepDurumu.ACIK)
            assert [t.id for t in acik] == [talep_id]
    finally:
        ikinci_baglanti.kapat()


def test_aday_suphesi_paketi_bekletir(ortam: Ortam, env: Envanter) -> None:
    mevcut = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, mevcut, ["harici_kimlik"])
    paket_id = _paket(ortam)
    aday_id = _aday(
        ortam,
        paket_id,
        env.depo_id,
        {"ad": "Depo", "harici_kimlik": "X1"},
        ["harici_kimlik"],
    )
    assert _paket_durumu(ortam, paket_id) == CALISIYOR.value
    [talep_id] = _adayi_denetle(ortam, aday_id)
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value
    with ortam.veritabani.islem() as o:
        talep = mu.karar_talebi_getir(o, talep_id)
        assert talep.aday_nesne_id == aday_id and talep.hedef_nesne_id == mevcut
        assert talep.islem_paketi_id == paket_id
        # bekleyen pakete taslak yazılamaz
        with pytest.raises(tsi.PaketDurumuGecersiz):
            tsi.aday_ozellik_yaz(o, aday_id, "sehir", "Edirne")


# --- 12-17: karar semantiği ve paket durumu -------------------------------------------


def test_ayri_karari_suphesi_kapatir_ve_paketi_calistirir(
    ortam: Ortam, env: Envanter
) -> None:
    mevcut = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, mevcut, ["harici_kimlik"])
    paket_id = _paket(ortam)
    aday_id = _aday(ortam, paket_id, env.depo_id, {"ad": "Depo", "harici_kimlik": "X1"})
    [talep_id] = _adayi_denetle(ortam, aday_id)
    sonuc = _karar(ortam, talep_id, Karar.AYRI, "ayrı depolar")
    assert sonuc.cozuldu and sonuc.paket_durumu is CALISIYOR
    assert sonuc.cozumleme is None and sonuc.birlesim is None
    with ortam.veritabani.islem() as o:
        talep = mu.karar_talebi_getir(o, talep_id)
        assert talep.durum == TalepDurumu.COZULDU.value
        assert talep.karar == Karar.AYRI.value
        assert talep.karar_aktor_kimligi == KULLANICI.kimlik
        assert mu.aday_cozumlemesi_bul(o, aday_id) is None
    assert _paket_durumu(ortam, paket_id) == CALISIYOR.value


def test_kararsiz_supheyi_cozmez_paket_bekliyor_kalir(
    ortam: Ortam, env: Envanter
) -> None:
    mevcut = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, mevcut, ["harici_kimlik"])
    paket_id = _paket(ortam)
    aday_id = _aday(ortam, paket_id, env.depo_id, {"ad": "Depo", "harici_kimlik": "X1"})
    [talep_id] = _adayi_denetle(ortam, aday_id)
    sonuc = _karar(ortam, talep_id, Karar.KARARSIZ, "emin değilim")
    assert not sonuc.cozuldu and sonuc.paket_durumu is BEKLIYOR
    with ortam.veritabani.islem() as o:
        talep = mu.karar_talebi_getir(o, talep_id)
        assert talep.durum == TalepDurumu.ACIK.value and talep.karar is None
        olaylar = [x.olay for x in di.olaylari_listele(o, karar_talebi_id=talep_id)]
    assert DenetimOlayi.KULLANICI_KARARI_VERILDI.value in olaylar
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value
    # kararsızdan sonra gerçek karar verilebilir
    assert _karar(ortam, talep_id, Karar.AYRI).cozuldu


def test_iki_acik_talepten_biri_cozulunce_paket_bekliyor_kalir(
    ortam: Ortam, env: Envanter
) -> None:
    """Kural açık talep sayısıdır: ilk karar tek başına paketi canlandırmaz."""
    ilk = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, ilk, ["harici_kimlik"])
    ikinci = _depo(ortam, env, harici_kimlik="X2")
    _sart(ortam, ikinci, ["harici_kimlik"])
    paket_id = _paket(ortam)
    a1 = _aday(ortam, paket_id, env.depo_id, {"ad": "D1", "harici_kimlik": "X1"})
    a2 = _aday(ortam, paket_id, env.depo_id, {"ad": "D2", "harici_kimlik": "X2"})
    [t1] = _adayi_denetle(ortam, a1)
    [t2] = _adayi_denetle(ortam, a2)
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value
    assert _karar(ortam, t1, Karar.AYRI).paket_durumu is BEKLIYOR
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value
    assert _karar(ortam, t2, Karar.AYRI).paket_durumu is CALISIYOR
    assert _paket_durumu(ortam, paket_id) == CALISIYOR.value
    assert (ilk, ikinci) == (ilk, ikinci)


def test_acik_talep_varken_paket_elle_devam_ettirilemez(
    ortam: Ortam, env: Envanter
) -> None:
    mevcut = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, mevcut, ["harici_kimlik"])
    paket_id = _paket(ortam)
    aday_id = _aday(ortam, paket_id, env.depo_id, {"ad": "Depo", "harici_kimlik": "X1"})
    _adayi_denetle(ortam, aday_id)
    with pytest.raises(tsi.PaketDurumuGecersiz, match="açık karar talebi"):
        with ortam.veritabani.islem() as o:
            tsi.paketi_devam_et(o, paket_id)
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value


def test_iptal_paket_kararla_canlanmaz(ortam: Ortam, env: Envanter) -> None:
    """İptal terminaldir: talebi ``gecersiz`` olur, karar verilemez, paket
    dirilmez. ``gecersiz`` bir ``AYRI`` kararı değildir: ``karar`` boş kalır."""
    mevcut = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, mevcut, ["harici_kimlik"])
    paket_id = _paket(ortam)
    aday_id = _aday(ortam, paket_id, env.depo_id, {"ad": "Depo", "harici_kimlik": "X1"})
    [talep_id] = _adayi_denetle(ortam, aday_id)
    _iptal_et(ortam, paket_id)
    with pytest.raises(mu.KararTalebiKapali, match="geçersiz"):
        _karar(ortam, talep_id, Karar.AYRI)
    with pytest.raises(tsi.PaketDurumuGecersiz, match="iptal"):
        _adayi_denetle(ortam, aday_id)
    assert _paket_durumu(ortam, paket_id) == IPTAL.value
    with ortam.veritabani.islem() as o:
        talep = mu.karar_talebi_getir(o, talep_id)
        assert talep.durum == TalepDurumu.GECERSIZ.value
        assert talep.karar is None and talep.gecersizlik_zamani is not None


# --- 18-20: tekrar ve eşzamanlılık ----------------------------------------------------


def test_ayni_suphe_tekrar_tekrar_uretilmez(ortam: Ortam, env: Envanter) -> None:
    """Açık talep varken ikinci tarama yeni talep açmaz; ``ayrı`` kararı
    verilmiş çift de aynı kanıtla yeniden durdurulmaz."""
    ilk = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, ilk, ["harici_kimlik"])
    ikinci = _depo(ortam, env, harici_kimlik="X1")
    [talep_id] = _denetle(ortam, ikinci)
    assert _denetle(ortam, ikinci) == []
    assert _denetle(ortam, ilk) == []
    _karar(ortam, talep_id, Karar.AYRI)
    assert _denetle(ortam, ikinci) == []
    assert _sayi(ortam, mt.KARAR_TALEBI) == 1


def test_ayni_cift_icin_ikinci_acik_talep_veritabaninda_reddedilir(
    ortam: Ortam, env: Envanter
) -> None:
    """Kısmi benzersiz indeks: servisi atlayan ham SQL de ikinci açık talebi
    yazamaz, çözülmüş talep kısıt dışındadır."""
    ilk = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, ilk, ["harici_kimlik"])
    ikinci = _depo(ortam, env, harici_kimlik="X1")
    [talep_id] = _denetle(ortam, ikinci)
    ekle = text(
        "INSERT INTO karar_talebi (durum, nesne_turu_id, kaynak_nesne_id, "
        "hedef_nesne_id, eslesen_ozellik_tanimi_id, olusturma_zamani, "
        "acan_aktor_turu, acan_aktor_kimligi, bagimsiz_koken) "
        "VALUES (:d, :t, :k, :h, :o, '2026-09-20', 'sistem', 'ham', 1)"
    )
    degerler = {
        "d": TalepDurumu.ACIK.value,
        "t": env.depo_id,
        "k": ikinci,
        "h": ilk,
        "o": _ozellik_id(ortam, env.depo_id, "harici_kimlik"),
    }
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        with ortam.veritabani.islem() as o:
            o.execute(ekle, degerler)
    _karar(ortam, talep_id, Karar.AYRI)
    with ortam.veritabani.islem() as o:  # çözülmüş talep varken yeni açık talep olur
        o.execute(ekle, degerler)
    assert _sayi(ortam, mt.KARAR_TALEBI) == 2


def test_ayni_talebe_ikinci_karar_uygulanmaz(ortam: Ortam, env: Envanter) -> None:
    ilk = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, ilk, ["harici_kimlik"])
    ikinci = _depo(ortam, env, harici_kimlik="X1")
    [talep_id] = _denetle(ortam, ikinci)
    _karar(ortam, talep_id, Karar.AYRI)
    for karar in (Karar.AYRI, Karar.AYNI, Karar.KARARSIZ):
        with pytest.raises(mu.KararTalebiKapali):
            _karar(ortam, talep_id, karar)
    with ortam.veritabani.islem() as o:
        assert mu.karar_talebi_getir(o, talep_id).karar == Karar.AYRI.value
    assert _sayi(ortam, mt.NESNE_BIRLESIMI) == 0


def _yaris(
    ortam: Ortam,
    hazirlik: Callable[[Session], object],
    islemler: list[Callable[[Session], object]],
) -> list[object]:
    """Her işlemi ayrı bağlantıda ve ayrı işlemde çalıştırır (4.5 kalıbı)."""
    bariyer = threading.Barrier(len(islemler), timeout=10)

    def kos(islem: Callable[[Session], object]) -> object:
        v = vt.Veritabani(ortam.veritabani.yol)
        try:
            with v.islem() as o:
                hazirlik(o)
                bariyer.wait()
                return islem(o)
        except Exception as hata:  # noqa: BLE001 - sözleşme testi: türü sınanır
            return hata
        finally:
            v.kapat()

    with ThreadPoolExecutor(max_workers=len(islemler)) as havuz:
        return list(havuz.map(kos, islemler))


def test_ayni_talebi_iki_baglanti_cevaplarsa_tek_karar_kazanir(
    ortam: Ortam, env: Envanter
) -> None:
    ilk = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, ilk, ["harici_kimlik"])
    ikinci = _depo(ortam, env, harici_kimlik="X1")
    [talep_id] = _denetle(ortam, ikinci)

    def cevapla(o: Session) -> object:
        return mu.karar_ver(o, talep_id, Karar.AYRI, KULLANICI)

    sonuclar = _yaris(
        ortam,
        lambda o: mu.karar_talebi_getir(o, talep_id),
        [cevapla, cevapla],
    )
    basarilar = [s for s in sonuclar if isinstance(s, mu.KararSonucu)]
    hatalar = [s for s in sonuclar if isinstance(s, Exception)]
    assert len(basarilar) == 1 and len(hatalar) == 1, sonuclar
    [hata] = hatalar
    assert isinstance(hata, mu.MukerrerlikHatasi), repr(hata)
    assert not isinstance(hata, HAM_DB_HATALARI), repr(hata)
    with ortam.veritabani.islem() as o:
        assert mu.karar_talebi_getir(o, talep_id).durum == TalepDurumu.COZULDU.value


def test_ayni_supheyi_iki_baglanti_acarsa_tek_talep_olusur(
    ortam: Ortam, env: Envanter
) -> None:
    ilk = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, ilk, ["harici_kimlik"])
    ikinci = _depo(ortam, env, harici_kimlik="X1")

    def denetle(o: Session) -> object:
        return mu.nesneyi_denetle(o, ikinci, KULLANICI)

    sonuclar = _yaris(ortam, lambda o: ni.nesne_getir(o, ikinci), [denetle, denetle])
    hatalar = [s for s in sonuclar if isinstance(s, Exception)]
    for hata in hatalar:
        assert isinstance(hata, mu.MukerrerlikHatasi), repr(hata)
        assert not isinstance(hata, HAM_DB_HATALARI), repr(hata)
    assert _sayi(ortam, mt.KARAR_TALEBI) == 1


# --- 21-25: birleştirme ---------------------------------------------------------------


def test_birlestirme_gelen_ve_giden_iliskileri_tasir(
    ortam: Ortam, env: Envanter
) -> None:
    """Gelen ilişki: rafların üst bağlantısı hedefe taşınır. Giden ilişki:
    hedef başka bir nesneye bağlıysa o bağlantı da taşınır."""
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    raf_hedef = _raf(ortam, env, hedef, "A1")
    raf_kaynak = _raf(ortam, env, kaynak, "B2")
    alt = _raf(ortam, env, kaynak, "C3")
    with ortam.veritabani.islem() as o:  # giden hiyerarşik ilişki: C3 altında B2
        ni.iliski_kur(o, env.altinda_id, alt, raf_kaynak)
    [talep_id] = _denetle(ortam, kaynak)
    sonuc = _karar(ortam, talep_id, Karar.AYNI)
    assert sonuc.devir is not None and sonuc.devir.tasinan == 2
    with ortam.veritabani.islem() as o:
        hedef_ustleri = {
            (i.kaynak_nesne_id, i.hedef_nesne_id)
            for i in ni.iliskileri_listele(o, hedef)
        }
        assert hedef_ustleri == {
            (raf_hedef, hedef),
            (raf_kaynak, hedef),
            (alt, hedef),
        }
        assert ni.iliskileri_listele(o, kaynak) == []
        assert ni.nesne_getir(o, kaynak).yasam_durumu == YasamDurumu.KAPALI.value
        birlesim = mu.nesne_birlesimini_bul(o, kaynak)
        assert birlesim is not None and birlesim.hedef_nesne_id == hedef
        assert birlesim.karar_talebi_id == talep_id


def test_birlestirmede_mukerrer_olacak_iliski_ikinci_kez_yazilmaz(
    ortam: Ortam, env: Envanter
) -> None:
    """Aynı ilişki hedefte zaten varsa ikinci satır oluşmaz; kaynaktaki düşer."""
    depo = _depo(ortam, env)
    raf = _raf(ortam, env, depo, "A1")
    hedef = _urun(ortam, env, [raf], barkod="B1", agirlik=Decimal("1.0"))
    _sart(ortam, hedef, ["agirlik"])
    kaynak = _urun(ortam, env, [raf], barkod="B2", agirlik=Decimal("1.00"))
    [talep_id] = _denetle(ortam, kaynak)
    sonuc = _karar(ortam, talep_id, Karar.AYNI)
    assert sonuc.devir is not None
    assert (sonuc.devir.tasinan, sonuc.devir.birlesen) == (0, 1)
    with ortam.veritabani.islem() as o:
        assert [
            (i.kaynak_nesne_id, i.hedef_nesne_id)
            for i in ni.iliskileri_listele(o, hedef)
        ] == [(hedef, raf)]


def test_kendine_donecek_baglanti_dusurulur(ortam: Ortam, env: Envanter) -> None:
    """Birleşen iki nesne arasındaki ilişki hedefte kendine dönerdi; yazılmaz."""
    depo = _depo(ortam, env)
    hedef = _raf(ortam, env, depo, "A1", seri_no="S1")
    _sart(ortam, hedef, ["seri_no"])
    kaynak = _raf(ortam, env, depo, "A2", seri_no="S1")
    with ortam.veritabani.islem() as o:
        ni.iliski_kur(o, env.altinda_id, hedef, kaynak)  # hedef, kaynağın altında
    [talep_id] = _denetle(ortam, kaynak)
    sonuc = _karar(ortam, talep_id, Karar.AYNI)
    assert sonuc.devir is not None and sonuc.devir.dusen == 1
    with ortam.veritabani.islem() as o:
        assert [
            (i.kaynak_nesne_id, i.hedef_nesne_id)
            for i in ni.iliskileri_listele(o, hedef)
        ] == [(hedef, depo)]


def test_hiyerarsi_ihlali_doguran_birlestirme_reddedilir_ve_geri_alinir(
    ortam: Ortam, env: Envanter
) -> None:
    """Ürün en çok iki rafa bağlanır; birleşim üçüncüyü getirirse hiçbir şey
    uygulanmaz: talep açık kalır, ilişkiler yerinde durur."""
    depo = _depo(ortam, env)
    r1 = _raf(ortam, env, depo, "A1")
    r2 = _raf(ortam, env, depo, "A2")
    r3 = _raf(ortam, env, depo, "A3")
    hedef = _urun(ortam, env, [r1, r2], barkod="B1", agirlik=Decimal("2"))
    _sart(ortam, hedef, ["agirlik"])
    kaynak = _urun(ortam, env, [r3], barkod="B2", agirlik=Decimal("2.0"))
    [talep_id] = _denetle(ortam, kaynak)
    with pytest.raises(ni.HiyerarsiIhlali):
        _karar(ortam, talep_id, Karar.AYNI)
    with ortam.veritabani.islem() as o:
        assert mu.karar_talebi_getir(o, talep_id).durum == TalepDurumu.ACIK.value
        assert len(ni.iliskileri_listele(o, hedef)) == 2
        assert len(ni.iliskileri_listele(o, kaynak)) == 1
        assert ni.nesne_getir(o, kaynak).yasam_durumu == YasamDurumu.ETKIN.value
        assert mu.nesne_birlesimini_bul(o, kaynak) is None
        assert di.olaylari_listele(o, karar_talebi_id=talep_id) != []
    assert _sayi(ortam, mt.NESNE_BIRLESIMI) == 0
    assert _sayi(ortam, dt.DENETIM_IZI) == 3  # şart, şüphe, talep (karar geri alındı)


def test_cevrim_doguran_birlestirme_reddedilir_ve_geri_alinir(
    ortam: Ortam, env: Envanter
) -> None:
    """``r1 → r2 → r3`` zincirinde r3 r1'e birleşirse ``r2 → r1`` çevrim yapar."""
    depo = _depo(ortam, env)
    r1 = _raf(ortam, env, depo, "A1", seri_no="S1")
    r2 = _raf(ortam, env, depo, "A2")
    r3 = _raf(ortam, env, depo, "A3", seri_no="S1")
    _sart(ortam, r1, ["seri_no"])
    with ortam.veritabani.islem() as o:
        ni.iliski_kur(o, env.altinda_id, r1, r2)
        ni.iliski_kur(o, env.altinda_id, r2, r3)
    [talep_id] = _denetle(ortam, r3)
    with pytest.raises(ni.HiyerarsiIhlali, match="çevrim"):
        _karar(ortam, talep_id, Karar.AYNI)
    with ortam.veritabani.islem() as o:
        assert mu.karar_talebi_getir(o, talep_id).durum == TalepDurumu.ACIK.value
        assert ni.nesne_getir(o, r3).yasam_durumu == YasamDurumu.ETKIN.value
        baglantilar = {
            (i.kaynak_nesne_id, i.hedef_nesne_id, i.iliski_tanimi_id)
            for i in ni.iliskileri_listele(o, r2)
        }
        assert (r1, r2, env.altinda_id) in baglantilar
        assert (r2, r3, env.altinda_id) in baglantilar


def test_birlesmis_nesne_yeniden_birlesemez_ve_taramaya_girmez(
    ortam: Ortam, env: Envanter
) -> None:
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    [talep_id] = _denetle(ortam, kaynak)
    _karar(ortam, talep_id, Karar.AYNI)
    assert _denetle(ortam, kaynak) == []  # birleşmiş nesne taranmaz
    ucuncu = _depo(ortam, env, harici_kimlik="X1")
    talepler = _denetle(ortam, ucuncu)
    with ortam.veritabani.islem() as o:
        hedefler = {mu.karar_talebi_getir(o, t).hedef_nesne_id for t in talepler}
    assert hedefler == {hedef}  # birleşmiş kaynak karşı uç olarak çıkmaz


# --- 26-28: aday çözümlemesi ve zincirleme --------------------------------------------


def test_aday_mevcut_nesneye_kalici_cozumlenir(ortam: Ortam, env: Envanter) -> None:
    """``AYNI`` kararı adayı kesin tabloya taşımaz; köprü satırı kalıcıdır ve
    4.8 onu tahmin etmeden okur."""
    mevcut = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, mevcut, ["harici_kimlik"])
    paket_id = _paket(ortam)
    aday_id = _aday(
        ortam,
        paket_id,
        env.depo_id,
        {"ad": "Aynı Depo", "harici_kimlik": "X1"},
        ["harici_kimlik"],
    )
    kesin_once = _sayi(ortam, nt.NESNE)
    [talep_id] = _adayi_denetle(ortam, aday_id)
    sonuc = _karar(ortam, talep_id, Karar.AYNI, "aynı depo")
    assert sonuc.cozumleme is not None and sonuc.birlesim is None
    assert sonuc.paket_durumu is CALISIYOR
    assert _sayi(ortam, nt.NESNE) == kesin_once  # kesin dünya büyümedi
    ikinci_baglanti = vt.Veritabani(ortam.veritabani.yol)
    try:
        with ikinci_baglanti.islem() as o:
            cozumleme = mu.aday_cozumlemesi_bul(o, aday_id)
            assert cozumleme is not None
            assert cozumleme.nesne_id == mevcut
            assert cozumleme.karar_talebi_id == talep_id
            assert cozumleme.aktor_kimligi == KULLANICI.kimlik
            assert tsi.aday_ozellikleri_oku(o, aday_id) == {
                "ad": "Aynı Depo",
                "harici_kimlik": "X1",
            }
    finally:
        ikinci_baglanti.kapat()


def test_cozumlenmis_aday_silinemez_ve_kayit_baglari_korunur(
    ortam: Ortam, env: Envanter
) -> None:
    mevcut = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, mevcut, ["harici_kimlik"])
    paket_id = _paket(ortam)
    aday_id = _aday(
        ortam,
        paket_id,
        env.depo_id,
        {"ad": "Depo", "harici_kimlik": "X1"},
        ["harici_kimlik"],
    )
    with ortam.veritabani.islem() as o:
        kayit = tsi.aday_kayit_ekle(o, paket_id, env.sayim_id, {"adet": 12})
        tsi.aday_kayit_nesne_bagla(o, kayit.id, aday_id)
        kayit_id = kayit.id
    [talep_id] = _adayi_denetle(ortam, aday_id)
    _karar(ortam, talep_id, Karar.AYNI)
    with ortam.veritabani.islem() as o:
        ayrinti = tsi.paket_ayrinti(o, paket_id)
        assert [b.aday_nesne_id for b in ayrinti.kayit_nesne_baglari] == [aday_id]
        assert tsi.aday_kayit_icerigi(o, kayit_id) == {"adet": 12}
        with pytest.raises(tsi.AdayKullanimda, match="aday kayda bağlı"):
            tsi.aday_nesne_sil(o, aday_id)
        tsi.aday_kayit_nesne_coz(o, kayit_id, aday_id)
        with pytest.raises(tsi.AdayKullanimda, match="karar talebine"):
            tsi.aday_nesne_sil(o, aday_id)


def test_karar_talebine_konu_aday_silinemez(ortam: Ortam, env: Envanter) -> None:
    mevcut = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, mevcut, ["harici_kimlik"])
    paket_id = _paket(ortam)
    aday_id = _aday(ortam, paket_id, env.depo_id, {"ad": "Depo", "harici_kimlik": "X1"})
    [talep_id] = _adayi_denetle(ortam, aday_id)
    _karar(ortam, talep_id, Karar.AYRI)
    with pytest.raises(tsi.AdayKullanimda, match="karar talebine"):
        with ortam.veritabani.islem() as o:
            tsi.aday_nesne_sil(o, aday_id)


def test_sartli_aday_silinince_sartlari_da_gider(ortam: Ortam, env: Envanter) -> None:
    paket_id = _paket(ortam)
    aday_id = _aday(
        ortam,
        paket_id,
        env.depo_id,
        {"ad": "Depo", "harici_kimlik": "X1"},
        ["harici_kimlik"],
    )
    assert _sayi(ortam, mt.ADAY_NESNE_MUKERRERLIK_SARTI) == 1
    with ortam.veritabani.islem() as o:
        tsi.aday_nesne_sil(o, aday_id)
    assert _sayi(ortam, mt.ADAY_NESNE_MUKERRERLIK_SARTI) == 0


def test_zincirleme_alt_nesne_suphesi_olusur(ortam: Ortam, env: Envanter) -> None:
    """İki depo birleşince altlarındaki aynı seri numaralı raflar yan yana gelir
    ve yeni bir karar talebi doğar; paket bütün talepler çözülene kadar bekler."""
    paket_id = _paket(ortam)
    hedef_depo = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef_depo, ["harici_kimlik"])
    kaynak_depo = _depo(ortam, env, harici_kimlik="X1")
    raf_a = _raf(ortam, env, hedef_depo, "A1", seri_no="S9")
    raf_b = _raf(ortam, env, kaynak_depo, "B1", seri_no="S9")
    _sart(ortam, raf_a, ["seri_no"])
    _sart(ortam, raf_b, ["seri_no"])
    [depo_talebi] = _denetle(ortam, kaynak_depo, paket_id)
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value
    sonuc = _karar(ortam, depo_talebi, Karar.AYNI)
    assert len(sonuc.yeni_talepler) == 1
    assert sonuc.paket_durumu is BEKLIYOR  # zincirleme talep paketi tutuyor
    [raf_talebi] = sonuc.yeni_talepler
    assert {raf_talebi.hedef_nesne_id, raf_talebi.kaynak_nesne_id} == {raf_a, raf_b}
    assert _karar(ortam, raf_talebi.id, Karar.AYRI).paket_durumu is CALISIYOR
    assert _paket_durumu(ortam, paket_id) == CALISIYOR.value


def test_zincirleme_denetim_sonsuz_donguye_girmez(ortam: Ortam, env: Envanter) -> None:
    """Birleşim → yeni talep → karar → yeniden birleşim zinciri sonlanır."""
    hedef_depo = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef_depo, ["harici_kimlik"])
    kaynak_depo = _depo(ortam, env, harici_kimlik="X1")
    raf_a = _raf(ortam, env, hedef_depo, "A1", seri_no="S9")
    raf_b = _raf(ortam, env, kaynak_depo, "B1", seri_no="S9")
    _sart(ortam, raf_a, ["seri_no"])
    _sart(ortam, raf_b, ["seri_no"])
    [depo_talebi] = _denetle(ortam, kaynak_depo)
    sonuc = _karar(ortam, depo_talebi, Karar.AYNI)
    [raf_talebi] = sonuc.yeni_talepler
    ikinci = _karar(ortam, raf_talebi.id, Karar.AYNI)
    assert ikinci.yeni_talepler == ()
    assert _sayi(ortam, mt.KARAR_TALEBI) == 2
    with ortam.veritabani.islem() as o:
        assert mu.talepleri_listele(o, durum=TalepDurumu.ACIK) == []


def test_birlesimden_sonra_hedef_yeniden_taranir(ortam: Ortam, env: Envanter) -> None:
    """Hedef, kaynağın şartlarını devraldığı için artık başka bir nesneyle
    eşleşebilir; zincirleme denetim hedefin kendisini de kapsar."""
    hedef = _depo(ortam, env, harici_kimlik="X1", sehir="Edirne")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, kaynak, ["sehir"])  # kaynağın değeri yok, şartı hedefe geçer
    ucuncu = _depo(ortam, env, sehir="Edirne")
    [talep_id] = _denetle(ortam, kaynak)
    sonuc = _karar(ortam, talep_id, Karar.AYNI)
    assert len(sonuc.yeni_talepler) == 1
    [yeni_talep] = sonuc.yeni_talepler
    assert (yeni_talep.hedef_nesne_id, yeni_talep.kaynak_nesne_id) == (hedef, ucuncu)
    assert yeni_talep.eslesen_ozellik_tanimi_id == _ozellik_id(
        ortam, env.depo_id, "sehir"
    )


def test_birlesmis_nesne_birlesim_hedefi_olamaz(ortam: Ortam, env: Envanter) -> None:
    """Birleşim zinciri kurulmaz: birleşmiş bir nesneye ikinci birleşim
    bağlanamaz (servis normal akışta böyle bir talep zaten açmaz)."""
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    ucuncu = _depo(ortam, env, harici_kimlik="X1")
    [talep_id] = _denetle(ortam, kaynak)
    _karar(ortam, talep_id, Karar.AYNI)
    with ortam.veritabani.islem() as o:  # ham SQL: birleşmiş nesneyi hedef yap
        o.execute(
            text(
                "INSERT INTO karar_talebi (durum, nesne_turu_id, kaynak_nesne_id, "
                "hedef_nesne_id, eslesen_ozellik_tanimi_id, olusturma_zamani, "
                "acan_aktor_turu, acan_aktor_kimligi, bagimsiz_koken) VALUES "
                "('acik', :t, :k, :h, :o, '2026-09-20', 'sistem', 'ham', 1)"
            ),
            {
                "t": env.depo_id,
                "k": ucuncu,
                "h": kaynak,
                "o": _ozellik_id(ortam, env.depo_id, "harici_kimlik"),
            },
        )
        zorlama_id = int(
            o.execute(text("SELECT max(id) FROM karar_talebi")).scalar_one()
        )
    with pytest.raises(mu.BirlestirmeGecersiz, match="birleşim zinciri"):
        _karar(ortam, zorlama_id, Karar.AYNI)
    with ortam.veritabani.islem() as o:
        assert mu.karar_talebi_getir(o, zorlama_id).durum == TalepDurumu.ACIK.value
        assert ni.nesne_getir(o, ucuncu).yasam_durumu == YasamDurumu.ETKIN.value


def test_uzun_gerekce_karari_uygulamadan_reddedilir(
    ortam: Ortam, env: Envanter
) -> None:
    """Sınır en başta denetlenir: talep kapanmaz, yarım karar kalmaz."""
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    [talep_id] = _denetle(ortam, kaynak)
    with pytest.raises(mu.GecersizSart, match="sınırını aşıyor"):
        _karar(ortam, talep_id, Karar.AYNI, "a" * (di.AZAMI_GEREKCE_UZUNLUGU + 1))
    with ortam.veritabani.islem() as o:
        assert mu.karar_talebi_getir(o, talep_id).durum == TalepDurumu.ACIK.value
        assert mu.nesne_birlesimini_bul(o, kaynak) is None


# --- 29-32: denetim izi, gizlilik, nötr domain ----------------------------------------


def test_denetim_izi_aktoru_ve_olaylari_tasir(ortam: Ortam, env: Envanter) -> None:
    mevcut = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, mevcut, ["harici_kimlik"])
    paket_id = _paket(ortam)
    aday_id = _aday(
        ortam,
        paket_id,
        env.depo_id,
        {"ad": "Depo", "harici_kimlik": "X1"},
        ["harici_kimlik"],
    )
    [talep_id] = _adayi_denetle(ortam, aday_id)
    _karar(ortam, talep_id, Karar.AYNI, "aynı depo")
    with ortam.veritabani.islem() as o:
        olaylar = di.olaylari_listele(o)
        turler = [x.olay for x in olaylar]
        assert all(x.aktor_kimligi == KULLANICI.kimlik for x in olaylar)
        assert all(x.aktor_turu == AktorTuru.KULLANICI.value for x in olaylar)
        assert all(x.olay_zamani.tzinfo is None for x in olaylar)
    for beklenen in (
        DenetimOlayi.MUKERRERLIK_SARTI_BELIRLENDI,
        DenetimOlayi.MUKERRERLIK_SUPHESI_ACILDI,
        DenetimOlayi.KARAR_TALEBI_ACILDI,
        DenetimOlayi.PAKET_BEKLEMEYE_GECTI,
        DenetimOlayi.KULLANICI_KARARI_VERILDI,
        DenetimOlayi.ADAY_NESNEYE_COZUMLENDI,
        DenetimOlayi.PAKET_YENIDEN_CALISIYOR,
    ):
        assert beklenen.value in turler, beklenen


def test_denetim_izi_ayri_ve_birlestirme_olaylarini_ayirir(
    ortam: Ortam, env: Envanter
) -> None:
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    [talep_id] = _denetle(ortam, kaynak)
    _karar(ortam, talep_id, Karar.AYNI)
    ucuncu = _depo(ortam, env, harici_kimlik="X1")
    [ikinci_talep] = _denetle(ortam, ucuncu)
    _karar(ortam, ikinci_talep, Karar.AYRI)
    with ortam.veritabani.islem() as o:
        birlesme = di.olaylari_listele(o, karar_talebi_id=talep_id)
        ayrilma = di.olaylari_listele(o, karar_talebi_id=ikinci_talep)
    assert DenetimOlayi.NESNE_BIRLESTIRILDI.value in [x.olay for x in birlesme]
    assert DenetimOlayi.NESNE_AYRI_KABUL_EDILDI.value in [x.olay for x in ayrilma]
    [birlestirme_olayi] = [
        x for x in birlesme if x.olay == DenetimOlayi.NESNE_BIRLESTIRILDI.value
    ]
    assert birlestirme_olayi.nesne_id == hedef
    assert birlestirme_olayi.ikincil_nesne_id == kaynak


def test_denetim_izinde_ham_ozellik_degeri_yoktur(ortam: Ortam, env: Envanter) -> None:
    """İz kimlik / referans saklar; şart değeri, aday kayıt içeriği ve belge
    içeriği hiçbir sütuna kopyalanmaz."""
    gizli = "COK-OZEL-DEGER-42"
    mevcut = _depo(ortam, env, harici_kimlik=gizli, sehir="Edirne")
    _sart(ortam, mevcut, ["harici_kimlik"])
    paket_id = _paket(ortam)
    aday_id = _aday(
        ortam,
        paket_id,
        env.depo_id,
        {"ad": "Depo", "harici_kimlik": gizli},
        ["harici_kimlik"],
    )
    with ortam.veritabani.islem() as o:
        tsi.aday_kayit_ekle(o, paket_id, env.sayim_id, {"adet": 12, "not": gizli})
    [talep_id] = _adayi_denetle(ortam, aday_id)
    _karar(ortam, talep_id, Karar.AYNI, "kullanıcı gerekçesi")
    with ortam.veritabani.islem() as o:
        satirlar = o.execute(text("SELECT * FROM denetim_izi")).all()
        metin = " | ".join(str(hucre) for satir in satirlar for hucre in satir)
        talep_metni = " | ".join(
            str(hucre)
            for satir in o.execute(text("SELECT * FROM karar_talebi")).all()
            for hucre in satir
        )
    assert gizli not in metin, metin
    assert gizli not in talep_metni, talep_metni
    assert "kullanıcı gerekçesi" in metin  # kullanıcının kendi açıklaması kalır


def test_uzun_gerekce_reddedilir(ortam: Ortam, env: Envanter) -> None:
    """Denetim izi bir içerik deposu değildir."""
    with pytest.raises(di.GecersizDenetimKaydi, match="sınırını aşıyor"):
        with ortam.veritabani.islem() as o:
            di.olay_yaz(
                o,
                DenetimOlayi.KULLANICI_KARARI_VERILDI,
                KULLANICI,
                gerekce="a" * (di.AZAMI_GEREKCE_UZUNLUGU + 1),
            )
    with pytest.raises(di.GecersizDenetimKaydi, match="aktör kimliği"):
        with ortam.veritabani.islem() as o:
            di.olay_yaz(
                o,
                DenetimOlayi.KULLANICI_KARARI_VERILDI,
                Aktor(AktorTuru.SISTEM, "   "),
            )


def test_aktor_turleri_domain_bagimsizdir(ortam: Ortam, env: Envanter) -> None:
    """Üç nötr aktör türü; finansal rol yoktur.

    Ajanın yetkili olduğu iş taramadır: şüphe açar, denetim olayı üretir.
    Şart seçimi ve karar kullanıcıya aittir (``SartKaynagiGecersiz`` /
    ``KararKaynagiGecersiz``), o yüzden burada ajanla tarama yaptırılır.
    """
    assert {a.value for a in AktorTuru} == {"kullanici", "ajan", "sistem"}
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    with ortam.veritabani.islem() as o:
        assert len(mu.nesneyi_denetle(o, kaynak, AJAN)) == 1
        ajan_olaylari = [
            olay
            for olay in di.olaylari_listele(o)
            if olay.aktor_turu == AktorTuru.AJAN.value
        ]
    assert ajan_olaylari
    assert {olay.aktor_kimligi for olay in ajan_olaylari} == {"test-ajan"}


# --- 33-45: 2026-09-20 incelemesi — karar yaşam döngüsü ve kanonik kimlik -------------
# Bulgular gerçek kodla yeniden üretildi; her testin başlığı kapatılan bulgudur.


def _talep_uclari(ortam: Ortam, talep_id: int) -> tuple[int | None, int, str]:
    with ortam.veritabani.islem() as o:
        talep = mu.karar_talebi_getir(o, talep_id)
        return talep.kaynak_nesne_id, talep.hedef_nesne_id, talep.durum


def _birlesimler(ortam: Ortam) -> list[tuple[int, int, int]]:
    """``(kaynak, karar hedefi, kanonik)`` üçlüleri, kimlik sırasıyla."""
    with ortam.veritabani.islem() as o:
        return [
            (b.kaynak_nesne_id, b.hedef_nesne_id, b.kanonik_nesne_id)
            for b in o.execute(
                select(mt.NesneBirlesimi).order_by(mt.NesneBirlesimi.id)
            ).scalars()
        ]


def _olaylar(ortam: Ortam) -> list[str]:
    with ortam.veritabani.islem() as o:
        return [x.olay for x in di.olaylari_listele(o)]


def _butunluk_temiz(ortam: Ortam) -> None:
    with ortam.veritabani.islem() as o:
        assert o.execute(text("PRAGMA foreign_key_check")).all() == []
        assert o.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"


# Bulgu 1 — iptal paketin açık talebi çifti sonsuza kadar kilitliyordu.


def test_iptal_paketin_talebi_cifti_gelecekte_kilitlemez(
    ortam: Ortam, env: Envanter
) -> None:
    """P1 iptal edilince talebi ``gecersiz`` olur; P2 aynı çifti yeniden
    denetleyebilir, yeni talep açılır ve P2 ``BEKLIYOR``a geçer. Eski talep
    geçmişte durur, karar taşımaz."""
    p1 = _paket(ortam)
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    [eski_talep] = _denetle(ortam, kaynak, p1)
    assert _paket_durumu(ortam, p1) == BEKLIYOR.value

    _iptal_et(ortam, p1)
    assert _talep_uclari(ortam, eski_talep) == (
        kaynak,
        hedef,
        TalepDurumu.GECERSIZ.value,
    )

    p2 = _paket(ortam)
    [yeni_talep] = _denetle(ortam, kaynak, p2)
    assert yeni_talep != eski_talep
    assert _talep_uclari(ortam, yeni_talep) == (kaynak, hedef, TalepDurumu.ACIK.value)
    assert _paket_durumu(ortam, p2) == BEKLIYOR.value
    assert _paket_durumu(ortam, p1) == IPTAL.value  # iptal paket canlanmadı

    with ortam.veritabani.islem() as o:  # eski talep geçmişte, kararsız
        eski = mu.karar_talebi_getir(o, eski_talep)
        assert eski.karar is None and eski.karar_aktor_turu is None
        assert eski.gecersizlik_zamani is not None
    assert _karar(ortam, yeni_talep, Karar.AYRI).paket_durumu is CALISIYOR
    _butunluk_temiz(ortam)


def test_gecersiz_talebe_kullanici_karari_verilemez(
    ortam: Ortam, env: Envanter
) -> None:
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    paket_id = _paket(ortam)
    [talep_id] = _denetle(ortam, kaynak, paket_id)
    _iptal_et(ortam, paket_id)
    for karar in (Karar.AYNI, Karar.AYRI, Karar.KARARSIZ):
        with pytest.raises(mu.KararTalebiKapali, match="geçersiz"):
            _karar(ortam, talep_id, karar)
    with ortam.veritabani.islem() as o:
        assert mu.karar_talebi_getir(o, talep_id).karar is None
        assert mu.nesne_birlesimini_bul(o, kaynak) is None


def test_iptal_denetim_izine_gecersizlik_olayini_yazar(
    ortam: Ortam, env: Envanter
) -> None:
    """Olay ``karar_talebi_gecersiz_kaldi``dır; ``kullanici_karari_verildi``
    değildir — kullanıcının vermediği karar kimseye yazılmaz."""
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    paket_id = _paket(ortam)
    [talep_id] = _denetle(ortam, kaynak, paket_id)
    _iptal_et(ortam, paket_id)
    with ortam.veritabani.islem() as o:
        olaylar = di.olaylari_listele(o, karar_talebi_id=talep_id)
    assert olaylar[-1].olay == DenetimOlayi.KARAR_TALEBI_GECERSIZ_KALDI.value
    assert olaylar[-1].aktor_turu == AktorTuru.KULLANICI.value
    assert f"paketi {paket_id}" in str(olaylar[-1].gerekce)
    assert DenetimOlayi.KULLANICI_KARARI_VERILDI.value not in [x.olay for x in olaylar]


def test_iptal_ile_karar_yarisi_tutarsizlik_uretmez(
    ortam: Ortam, env: Envanter
) -> None:
    """İki bağlantı aynı anda iptal eder ve karar verirse tam biri kazanır;
    talep ya ``cozuldu`` ya ``gecersiz`` olur, ikisi birden olamaz."""
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    paket_id = _paket(ortam)
    [talep_id] = _denetle(ortam, kaynak, paket_id)

    sonuclar = _yaris(
        ortam,
        lambda o: mu.karar_talebi_getir(o, talep_id),
        [
            lambda o: tsi.paketi_iptal_et(o, paket_id, KULLANICI),
            lambda o: mu.karar_ver(o, talep_id, Karar.AYRI, KULLANICI),
        ],
    )
    hatalar = [s for s in sonuclar if isinstance(s, Exception)]
    assert len(hatalar) == 1, sonuclar
    [hata] = hatalar
    assert isinstance(hata, (mu.MukerrerlikHatasi, tsi.IslemPaketiHatasi)), repr(hata)
    assert not isinstance(hata, HAM_DB_HATALARI), repr(hata)
    with ortam.veritabani.islem() as o:
        talep = mu.karar_talebi_getir(o, talep_id)
    assert talep.durum in (TalepDurumu.COZULDU.value, TalepDurumu.GECERSIZ.value)
    assert (talep.karar is None) == (talep.durum == TalepDurumu.GECERSIZ.value)
    _butunluk_temiz(ortam)


# Bulgu 3 — karar kaynağı kodda zorlanmıyordu.


@pytest.mark.parametrize(
    "aktor",
    [Aktor(AktorTuru.AJAN, "tarayici"), Aktor(AktorTuru.SISTEM, "defteriki")],
)
@pytest.mark.parametrize("karar", [Karar.AYNI, Karar.AYRI, Karar.KARARSIZ])
def test_kullanici_disindaki_aktor_karar_veremez(
    ortam: Ortam, env: Envanter, aktor: Aktor, karar: Karar
) -> None:
    """Reddedilen çağrı talebi değiştirmez, denetim izine yazmaz, paketi
    etkilemez."""
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    paket_id = _paket(ortam)
    [talep_id] = _denetle(ortam, kaynak, paket_id)
    onceki_olaylar = _olaylar(ortam)

    with pytest.raises(mu.KararKaynagiGecersiz, match="yalnız kullanıcı"):
        with ortam.veritabani.islem() as o:
            mu.karar_ver(o, talep_id, karar, aktor)

    assert _talep_uclari(ortam, talep_id)[2] == TalepDurumu.ACIK.value
    assert _olaylar(ortam) == onceki_olaylar
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value
    assert _sayi(ortam, mt.NESNE_BIRLESIMI) == 0


def test_ajan_tarama_yapip_suphe_acabilir(ortam: Ortam, env: Envanter) -> None:
    """Yasak yalnız karardır: ajan tarar, şüphe açar, denetim olayı üretir."""
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    with ortam.veritabani.islem() as o:
        [talep] = mu.nesneyi_denetle(o, kaynak, AJAN)
        assert talep.acan_aktor_turu == AktorTuru.AJAN.value


def test_ham_sql_ajan_karari_yazamaz(ortam: Ortam, env: Envanter) -> None:
    """Sözleşme veritabanında da duruyor: ``karar_aktor_turu`` kontrol kısıtı."""
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    [talep_id] = _denetle(ortam, kaynak)
    with pytest.raises(IntegrityError, match="karari_kullanici_verir"):
        with ortam.veritabani.islem() as o:
            o.execute(
                text(
                    "UPDATE karar_talebi SET durum = 'cozuldu', karar = 'ayni', "
                    "karar_zamani = '2026-09-20', karar_aktor_turu = 'ajan', "
                    "karar_aktor_kimligi = 'ham' WHERE id = :t"
                ),
                {"t": talep_id},
            )


# Bulgu 4 — birleşim zinciri kurulabiliyordu.


def _zincir_kurulumu(ortam: Ortam, env: Envanter) -> tuple[int, int, int]:
    """``N3`` yalnız ``N2`` ile, ``N2`` yalnız ``N1`` ile eşleşir.

    İki şüphe iki ayrı kimlikten doğar (``harici_kimlik`` ve ``sehir``), yani
    ``N1`` ile ``N3`` arasında hiç şüphe ve dolayısıyla hiç ``AYRI`` kararı
    yoktur: zincir düzleştirmesi geçmiş bir kullanıcı kararıyla çelişmeden
    sınanır.
    """
    n1 = _depo(ortam, env, sehir="EDIRNE")
    _sart(ortam, n1, ["sehir"])
    n2 = _depo(ortam, env, sehir="EDIRNE", harici_kimlik="A")
    n3 = _depo(ortam, env, harici_kimlik="A")
    _sart(ortam, n3, ["harici_kimlik"])
    return n1, n2, n3


def _uc_depo_zinciri(ortam: Ortam, env: Envanter) -> tuple[int, int, int]:
    """``N3 → N2`` ardından ``N2 → N1``: kullanıcı kararlarıyla gerçek akış."""
    n1, n2, n3 = _zincir_kurulumu(ortam, env)
    [ilk] = _denetle(ortam, n3)
    assert _talep_uclari(ortam, ilk)[:2] == (n3, n2)
    sonuc = _karar(ortam, ilk, Karar.AYNI)
    [zincirleme] = [t for t in sonuc.yeni_talepler if t.hedef_nesne_id == n1]
    _karar(ortam, zincirleme.id, Karar.AYNI)
    return n1, n2, n3


def test_birlesim_zinciri_duzlestirilir(ortam: Ortam, env: Envanter) -> None:
    """``3 → 2`` sonra ``2 → 1``: hiçbir satır birleşmiş bir nesneyi kanonik
    göstermez, kanonik hedef tek sıçramada bulunur."""
    n1, n2, n3 = _uc_depo_zinciri(ortam, env)
    satirlar = _birlesimler(ortam)
    assert {(k, kan) for k, _, kan in satirlar} == {(n3, n1), (n2, n1)}
    kaynaklar = {k for k, _, _ in satirlar}
    assert not (kaynaklar & {kan for _, _, kan in satirlar})  # zincir yok
    with ortam.veritabani.islem() as o:
        for nesne_id in (n2, n3):
            assert mu.kanonik_nesneyi_bul(o, nesne_id) == n1
        assert mu.kanonik_nesneyi_bul(o, n1) == n1
    _butunluk_temiz(ortam)


def test_zincir_duzlesince_eski_karar_gecmisi_korunur(
    ortam: Ortam, env: Envanter
) -> None:
    """``hedef_nesne_id`` kullanıcının o günkü kararıdır, değişmez; değişen
    yalnız ``kanonik_nesne_id``dir ve her yeniden bağlama denetim izinde."""
    n1, n2, n3 = _uc_depo_zinciri(ortam, env)
    [(kaynak_ucu, karar_hedefi, kanonik)] = [
        s for s in _birlesimler(ortam) if s[0] == n3
    ]
    assert (kaynak_ucu, karar_hedefi, kanonik) == (n3, n2, n1)
    with ortam.veritabani.islem() as o:
        birlesim = mu.nesne_birlesimini_bul(o, n3)
        assert birlesim is not None
        talep = mu.karar_talebi_getir(o, birlesim.karar_talebi_id)
        assert (talep.hedef_nesne_id, talep.kaynak_nesne_id) == (n2, n3)
        assert talep.karar == Karar.AYNI.value
        yeniden = [
            x
            for x in di.olaylari_listele(o)
            if x.olay == DenetimOlayi.BIRLESIM_YENIDEN_BAGLANDI.value
        ]
    assert [(x.nesne_id, x.ikincil_nesne_id) for x in yeniden] == [(n1, n3)]


def test_birlesmis_nesne_ikinci_kez_kaynak_olamaz(ortam: Ortam, env: Envanter) -> None:
    """Düzleştirme, birleşmiş nesnenin yeniden birleşmesi demek değildir."""
    n1, _, _ = _uc_depo_zinciri(ortam, env)
    dorduncu = _depo(ortam, env, sehir="EDIRNE", harici_kimlik="A")
    talepler = _denetle(ortam, dorduncu)
    with ortam.veritabani.islem() as o:
        hedefler = {mu.karar_talebi_getir(o, t).hedef_nesne_id for t in talepler}
    assert hedefler == {n1}  # n2 ve n3 kanonik n1'e eşlendi


def test_ikinci_karar_duserse_ilk_birlesim_bozulmaz(
    ortam: Ortam, env: Envanter
) -> None:
    """İkinci karar düşerse ilk birleşimin kanonik bağı olduğu gibi kalır;
    yarım düzleştirme olmaz."""
    n1, n2, n3 = _zincir_kurulumu(ortam, env)
    [ilk] = _denetle(ortam, n3)
    sonuc = _karar(ortam, ilk, Karar.AYNI)
    [zincirleme] = [t for t in sonuc.yeni_talepler if t.hedef_nesne_id == n1]
    # Karar gerekçe sınırında düşer: ikinci birleşim hiç uygulanmaz.
    with pytest.raises(mu.GecersizSart):
        _karar(ortam, zincirleme.id, Karar.AYNI, "a" * (di.AZAMI_GEREKCE_UZUNLUGU + 1))
    assert _birlesimler(ortam) == [(n3, n2, n2)]
    with ortam.veritabani.islem() as o:
        assert mu.kanonik_nesneyi_bul(o, n3) == n2
        assert mu.karar_talebi_getir(o, zincirleme.id).durum == TalepDurumu.ACIK.value


# Bulgu 5 — birleşen kaynağın kimlik değerleri korumadan düşüyordu.


def test_birlesen_kaynagin_eski_kimligi_ucuncu_nesneyi_yakalar(
    ortam: Ortam, env: Envanter
) -> None:
    """Kaynakta değer + şart, hedefte değer yok. Birleşimden sonra kaynağın
    eski değeriyle gelen üçüncü nesne kanonik hedefle şüphe doğurur."""
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1", sehir="EDIRNE")
    _sart(ortam, kaynak, ["sehir"])
    [talep_id] = _denetle(ortam, kaynak)
    _karar(ortam, talep_id, Karar.AYNI)

    ucuncu = _depo(ortam, env, sehir="EDIRNE")
    [yeni] = _denetle(ortam, ucuncu)
    kaynak_ucu, hedef_ucu, _ = _talep_uclari(ortam, yeni)
    assert (hedef_ucu, kaynak_ucu) == (hedef, ucuncu)  # kanonik hedef gösterilir
    with ortam.veritabani.islem() as o:
        assert mu.karar_talebi_getir(o, yeni).eslesen_ozellik_tanimi_id == _ozellik_id(
            ortam, env.depo_id, "sehir"
        )


def test_hedef_ve_kaynagin_farkli_degerleri_birlikte_korunur(
    ortam: Ortam, env: Envanter
) -> None:
    """Aynı özellikte iki tarihsel değer varsa ikisi de kimlik kanıtıdır;
    çekirdek hangisinin doğru güncel değer olduğunu söylemez (kaynağın
    özellik satırı hedefe kopyalanmaz)."""
    hedef = _depo(ortam, env, harici_kimlik="X1", sehir="EDIRNE")
    _sart(ortam, hedef, ["harici_kimlik", "sehir"])
    kaynak = _depo(ortam, env, harici_kimlik="X1", sehir="ANKARA")
    [talep_id] = _denetle(ortam, kaynak)
    _karar(ortam, talep_id, Karar.AYNI)

    with ortam.veritabani.islem() as o:  # hedefin kendi değeri değişmedi
        degerler = ni.ozellikleri_oku(o, hedef)
    assert degerler["sehir"] == "EDIRNE"

    for sehir in ("EDIRNE", "ANKARA"):
        yeni_depo = _depo(ortam, env, sehir=sehir)
        [talep] = _denetle(ortam, yeni_depo)
        assert _talep_uclari(ortam, talep)[1] == hedef
        _karar(ortam, talep, Karar.AYRI)


def test_birlesmis_kaynak_bagimsiz_eslesme_olarak_donmez(
    ortam: Ortam, env: Envanter
) -> None:
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1", sehir="EDIRNE")
    _sart(ortam, kaynak, ["sehir"])
    [talep_id] = _denetle(ortam, kaynak)
    _karar(ortam, talep_id, Karar.AYNI)
    ucuncu = _depo(ortam, env, harici_kimlik="X1", sehir="EDIRNE")
    talepler = _denetle(ortam, ucuncu)
    with ortam.veritabani.islem() as o:
        hedefler = [mu.karar_talebi_getir(o, t).hedef_nesne_id for t in talepler]
    assert hedefler == [hedef]  # tek talep, kanonik uç; kaynak görünmez


# Bulgu 2 — aynı aday birden fazla kesin nesneyle eşleşebiliyordu.


def _aday_iki_kesin(ortam: Ortam, env: Envanter) -> tuple[int, int, int, list[int]]:
    """``X`` bir kimlikten, ``Y`` başka bir kimlikten aynı adayla eşleşir."""
    x = _depo(ortam, env, harici_kimlik="A")
    _sart(ortam, x, ["harici_kimlik"])
    y = _depo(ortam, env, sehir="B")
    _sart(ortam, y, ["sehir"])
    paket_id = _paket(ortam)
    z = _aday(
        ortam, paket_id, env.depo_id, {"ad": "Depo", "harici_kimlik": "A", "sehir": "B"}
    )
    talepler = _adayi_denetle(ortam, z)
    assert len(talepler) == 2
    return x, y, z, talepler


def test_aday_iki_kesin_nesneyle_eslesir_ve_paket_bekler(
    ortam: Ortam, env: Envanter
) -> None:
    x, y, _, talepler = _aday_iki_kesin(ortam, env)
    with ortam.veritabani.islem() as o:
        hedefler = {mu.karar_talebi_getir(o, t).hedef_nesne_id for t in talepler}
        paket_id = mu.karar_talebi_getir(o, talepler[0]).islem_paketi_id
    assert hedefler == {x, y}
    assert paket_id is not None
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value


def test_aday_ayni_sonra_ayri_tek_cozumleme_birakir(
    ortam: Ortam, env: Envanter
) -> None:
    """A vakası: ``Z = X`` ve ``Z ≠ Y``. Birleşim doğmaz, paket çalışır."""
    x, _, z, talepler = _aday_iki_kesin(ortam, env)
    with ortam.veritabani.islem() as o:
        x_talebi = next(
            t for t in talepler if mu.karar_talebi_getir(o, t).hedef_nesne_id == x
        )
    y_talebi = next(t for t in talepler if t != x_talebi)
    assert _karar(ortam, x_talebi, Karar.AYNI).paket_durumu is BEKLIYOR
    assert _karar(ortam, y_talebi, Karar.AYRI).paket_durumu is CALISIYOR
    assert _sayi(ortam, mt.ADAY_NESNE_COZUMLEMESI) == 1
    assert _sayi(ortam, mt.NESNE_BIRLESIMI) == 0
    with ortam.veritabani.islem() as o:
        assert mu.adayin_kesin_nesnesi(o, z) == x
    _butunluk_temiz(ortam)


def test_iki_ayni_karari_kesin_nesneleri_birlestirir(
    ortam: Ortam, env: Envanter
) -> None:
    """B vakası: ``Z = X`` ve ``Z = Y`` ise ``X = Y``. İkinci ``AYNI`` ham
    benzersizlik hatasına düşmez, kaybolmaz; iki kesin nesne birleşir ve
    adayın kesin hedefi belirsiz kalmaz."""
    x, y, z, talepler = _aday_iki_kesin(ortam, env)
    _karar(ortam, talepler[0], Karar.AYNI)
    sonuc = _karar(ortam, talepler[1], Karar.AYNI)

    assert sonuc.cozuldu and sonuc.birlesim is not None and sonuc.devir is not None
    hedef, kaynak = min(x, y), max(x, y)
    assert _birlesimler(ortam) == [(kaynak, hedef, hedef)]
    assert _sayi(ortam, mt.ADAY_NESNE_COZUMLEMESI) == 1
    with ortam.veritabani.islem() as o:
        assert mu.adayin_kesin_nesnesi(o, z) == hedef
        cozumleme = mu.aday_cozumlemesi_bul(o, z)
        assert cozumleme is not None
        birlesim = mu.nesne_birlesimini_bul(o, kaynak)
        assert birlesim is not None
        # hangi kararın hangi birleşime yol açtığı denetimden okunur
        assert birlesim.karar_talebi_id == talepler[1]
        olaylar = [x.olay for x in di.olaylari_listele(o, karar_talebi_id=talepler[1])]
    assert DenetimOlayi.NESNE_BIRLESTIRILDI.value in olaylar
    assert cozumleme.nesne_id in (x, y)  # karar satırı değişmedi
    assert sonuc.paket_durumu is CALISIYOR
    _butunluk_temiz(ortam)


def test_ikinci_ayni_onceki_ayri_kararina_carparsa_reddedilir(
    ortam: Ortam, env: Envanter
) -> None:
    """C vakası: ``X`` ile ``Y`` için daha önce ``AYRI`` denmişse çelişki
    sessizce çözülmez; işlem tamamen geri alınır, talep açık kalır."""
    x = _depo(ortam, env, ad="Ortak", harici_kimlik="A")
    _sart(ortam, x, ["ad", "harici_kimlik"])
    y = _depo(ortam, env, ad="Ortak", sehir="B")
    _sart(ortam, y, ["ad", "sehir"])
    assert x < y
    [ayri_talebi] = _denetle(ortam, y)
    _karar(ortam, ayri_talebi, Karar.AYRI)

    paket_id = _paket(ortam)
    z = _aday(
        ortam,
        paket_id,
        env.depo_id,
        {"ad": "Baska", "harici_kimlik": "A", "sehir": "B"},
    )
    talepler = _adayi_denetle(ortam, z)
    assert len(talepler) == 2
    _karar(ortam, talepler[0], Karar.AYNI)
    onceki_olaylar = _olaylar(ortam)

    with pytest.raises(mu.KararCelismesi, match="ayrı"):
        _karar(ortam, talepler[1], Karar.AYNI)

    assert _talep_uclari(ortam, talepler[1])[2] == TalepDurumu.ACIK.value
    assert _olaylar(ortam) == onceki_olaylar
    assert _sayi(ortam, mt.NESNE_BIRLESIMI) == 0
    assert _sayi(ortam, mt.ADAY_NESNE_COZUMLEMESI) == 1
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value
    assert _karar(ortam, talepler[1], Karar.AYRI).paket_durumu is CALISIYOR
    _butunluk_temiz(ortam)


def test_cozumlenmis_adayin_kesin_hedefi_birlesimden_sonra_belirsiz_kalmaz(
    ortam: Ortam, env: Envanter
) -> None:
    """D vakası: aday ``X``e çözümlendikten sonra ``X`` başka bir nesneye
    birleşirse adayın kesin hedefi tek adımda yeni kanonik nesnedir; karar
    satırı ise değişmez."""
    w = _depo(ortam, env, sehir="EDIRNE")
    _sart(ortam, w, ["sehir"])
    x = _depo(ortam, env, harici_kimlik="A", sehir="EDIRNE")
    _sart(ortam, x, ["harici_kimlik"])
    paket_id = _paket(ortam)
    z = _aday(ortam, paket_id, env.depo_id, {"ad": "Depo", "harici_kimlik": "A"})
    [talep_id] = _adayi_denetle(ortam, z)
    _karar(ortam, talep_id, Karar.AYNI)

    [birlesim_talebi] = _denetle(ortam, x)
    assert _talep_uclari(ortam, birlesim_talebi)[:2] == (x, w)
    _karar(ortam, birlesim_talebi, Karar.AYNI)

    with ortam.veritabani.islem() as o:
        cozumleme = mu.aday_cozumlemesi_bul(o, z)
        assert cozumleme is not None and cozumleme.nesne_id == x  # karar değişmedi
        assert mu.adayin_kesin_nesnesi(o, z) == w  # kanonik hedef tek adımda
    _butunluk_temiz(ortam)


def test_ayni_kanonige_ikinci_ayni_yeni_satir_yazmaz(
    ortam: Ortam, env: Envanter
) -> None:
    """İki talep aynı kanonik nesneye çıkıyorsa ikinci ``AYNI`` çözümlemeyi
    tekrarlamaz; karar yine denetim izine yazılır."""
    x, y, _, talepler = _aday_iki_kesin(ortam, env)
    _karar(ortam, talepler[0], Karar.AYNI)
    _karar(ortam, talepler[1], Karar.AYNI)  # X ile Y birleşti
    hedef = min(x, y)

    paket2 = _paket(ortam)
    z2 = _aday(
        ortam,
        paket2,
        env.depo_id,
        {"ad": "Depo", "harici_kimlik": "A", "sehir": "B"},
    )
    yeni_talepler = _adayi_denetle(ortam, z2)
    assert len(yeni_talepler) == 1  # iki kimlik tek kanonik nesneye çıkar
    sonuc = _karar(ortam, yeni_talepler[0], Karar.AYNI)
    assert sonuc.birlesim is None
    with ortam.veritabani.islem() as o:
        assert mu.adayin_kesin_nesnesi(o, z2) == hedef
    assert _sayi(ortam, mt.ADAY_NESNE_COZUMLEMESI) == 2
    assert _sayi(ortam, mt.NESNE_BIRLESIMI) == 1


def test_eszamanli_iki_birlesim_tutarsiz_graf_uretmez(
    ortam: Ortam, env: Envanter
) -> None:
    """İki bağlantı aynı anda birleştirirse tam biri yazar; kalan graf yine
    zincirsizdir."""
    n1 = _depo(ortam, env, harici_kimlik="X1")
    n2 = _depo(ortam, env, harici_kimlik="X1")
    n3 = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, n3, ["harici_kimlik"])
    _sart(ortam, n2, ["harici_kimlik"])
    with ortam.veritabani.islem() as o:
        talepler = {
            (t.hedef_nesne_id, t.kaynak_nesne_id): t.id
            for t in mu.nesneyi_denetle(o, n3, KULLANICI)
        }
        talepler.update(
            {
                (t.hedef_nesne_id, t.kaynak_nesne_id): t.id
                for t in mu.nesneyi_denetle(o, n2, KULLANICI)
            }
        )
    ucuncu = talepler[(n1, n3)]
    ikinci = talepler[(n2, n3)]
    sonuclar = _yaris(
        ortam,
        lambda o: ni.nesne_getir(o, n3),
        [
            lambda o: mu.karar_ver(o, ucuncu, Karar.AYNI, KULLANICI),
            lambda o: mu.karar_ver(o, ikinci, Karar.AYNI, KULLANICI),
        ],
    )
    for hata in (s for s in sonuclar if isinstance(s, Exception)):
        assert isinstance(hata, mu.MukerrerlikHatasi), repr(hata)
        assert not isinstance(hata, HAM_DB_HATALARI), repr(hata)
    satirlar = _birlesimler(ortam)
    kaynaklar = {k for k, _, _ in satirlar}
    assert not (kaynaklar & {kan for _, _, kan in satirlar})
    _butunluk_temiz(ortam)


# Bulgu 6 — silinen aday kimliği yeniden kullanılabiliyordu.


def test_silinen_aday_kimligi_yeniden_kullanilmaz(ortam: Ortam, env: Envanter) -> None:
    """Denetim izindeki ``aday_nesne_id`` dış anahtar değildir; kimlik yeniden
    dağıtılsaydı eski iz yeni adayı gösterirdi."""
    paket_id = _paket(ortam)
    ilk = _aday(
        ortam,
        paket_id,
        env.depo_id,
        {"ad": "Depo", "harici_kimlik": "A"},
        ["harici_kimlik"],
    )
    with ortam.veritabani.islem() as o:
        izler = [
            x.aday_nesne_id
            for x in di.olaylari_listele(o)
            if x.aday_nesne_id is not None
        ]
    assert izler == [ilk]
    with ortam.veritabani.islem() as o:
        tsi.aday_nesne_sil(o, ilk)
    ikinci = _aday(ortam, paket_id, env.depo_id, {"ad": "Depo", "harici_kimlik": "B"})
    assert ikinci > ilk
    with ortam.veritabani.islem() as o:
        assert tsi.aday_nesne_getir(o, ikinci).id == ikinci
        with pytest.raises(tsi.AdayBulunamadi):
            tsi.aday_nesne_getir(o, ilk)


def test_aday_kimlikleri_paket_icinde_de_yeniden_kullanilmaz(
    ortam: Ortam, env: Envanter
) -> None:
    """``islem_paketi_id + aday_nesne_id`` tek başına yetmezdi: aynı paket
    içinde silinen en büyük kimlik eskiden yeniden dağıtılıyordu."""
    paket_id = _paket(ortam)
    kimlikler: list[int] = []
    for sira in range(3):
        aday_id = _aday(ortam, paket_id, env.depo_id, {"ad": f"Depo {sira}"})
        kimlikler.append(aday_id)
        with ortam.veritabani.islem() as o:
            tsi.aday_nesne_sil(o, aday_id)
    assert kimlikler == sorted(set(kimlikler))
    assert len(set(kimlikler)) == 3


# --- 46-58: 2026-09-20 ikinci incelemesi — AYRI geçmişi ve atomiklik ------------------


class EnjekteHata(Exception):
    """Hata enjeksiyonu testlerinin kendi hatası; başka hiçbir şeye karışmaz."""


def _patlat(*_a: object, **_k: object) -> object:
    raise EnjekteHata("enjekte edilmiş hata")


def _talep_durumu(ortam: Ortam, talep_id: int) -> str:
    with ortam.veritabani.islem() as o:
        return mu.karar_talebi_getir(o, talep_id).durum


def _acik_talepler(ortam: Ortam) -> list[tuple[int, int | None, int]]:
    """Açık talepler: ``(kimlik, kaynak ucu, hedef ucu)``."""
    with ortam.veritabani.islem() as o:
        return [
            (t.id, t.kaynak_nesne_id, t.hedef_nesne_id)
            for t in mu.talepleri_listele(o, durum=TalepDurumu.ACIK)
        ]


def _uc_esit_depo(ortam: Ortam, env: Envanter) -> tuple[int, int, int, dict[int, int]]:
    """Üç eş depo; ``N3`` taranınca ``N1`` ve ``N2`` ile iki şüphe doğar."""
    n1 = _depo(ortam, env, harici_kimlik="X1")
    n2 = _depo(ortam, env, harici_kimlik="X1")
    n3 = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, n3, ["harici_kimlik"])
    with ortam.veritabani.islem() as o:
        talepler = {
            t.hedef_nesne_id: t.id for t in mu.nesneyi_denetle(o, n3, KULLANICI)
        }
    assert set(talepler) == {n1, n2}
    return n1, n2, n3, talepler


# Bulgu 1 — geçmiş AYRI kararı birleşmelerle aşılabiliyordu.


def test_birlesmis_eski_kimlik_uzerindeki_ayri_karari_korunur(
    ortam: Ortam, env: Envanter
) -> None:
    """``N1 ≠ N3`` dendikten sonra ``N3 → N2`` olursa ``N1 = N2`` kararı eski
    kararı aşar. Reddedilir; eski karar silinmez, işlem iz bırakmaz."""
    n1, n2, n3, talepler = _uc_esit_depo(ortam, env)
    _karar(ortam, talepler[n1], Karar.AYRI)
    sonuc = _karar(ortam, talepler[n2], Karar.AYNI)  # N3 → N2
    [zincir] = [t for t in sonuc.yeni_talepler if t.hedef_nesne_id == n1]
    onceki_olaylar = _olaylar(ortam)
    onceki_birlesimler = _birlesimler(ortam)

    with pytest.raises(mu.KararCelismesi, match="'ayrı'"):
        _karar(ortam, zincir.id, Karar.AYNI)

    assert _talep_durumu(ortam, zincir.id) == TalepDurumu.ACIK.value
    assert _olaylar(ortam) == onceki_olaylar
    assert _birlesimler(ortam) == onceki_birlesimler == [(n3, n2, n2)]
    with ortam.veritabani.islem() as o:  # eski AYRI kararı olduğu gibi duruyor
        eski = mu.karar_talebi_getir(o, talepler[n1])
        assert (eski.durum, eski.karar) == (TalepDurumu.COZULDU.value, "ayri")
        assert (eski.hedef_nesne_id, eski.kaynak_nesne_id) == (n1, n3)
        assert ni.nesne_getir(o, n2).yasam_durumu == YasamDurumu.ETKIN.value
    _butunluk_temiz(ortam)


def test_ayri_karari_ters_yonde_de_birlesmeyi_durdurur(
    ortam: Ortam, env: Envanter
) -> None:
    """``AYRI`` satırında hedef ucu birleşecek **kaynak** kümesinde, kaynak ucu
    **hedef** kümesinde olabilir; yön sonucu değiştirmez. İki kümenin de birden
    fazla üyesi vardır."""
    d1 = _depo(ortam, env, ad="D1", sehir="EDIRNE")
    _sart(ortam, d1, ["sehir"])
    d2 = _depo(ortam, env, ad="ORTAK", harici_kimlik="A")
    _sart(ortam, d2, ["ad", "harici_kimlik"])
    d3 = _depo(ortam, env, ad="D3", harici_kimlik="A")
    _sart(ortam, d3, ["harici_kimlik"])
    d4 = _depo(ortam, env, ad="ORTAK", sehir="EDIRNE")
    _sart(ortam, d4, ["ad", "sehir"])

    with ortam.veritabani.islem() as o:
        dort = {t.hedef_nesne_id: t.id for t in mu.nesneyi_denetle(o, d4, KULLANICI)}
    assert set(dort) == {d1, d2}
    _karar(ortam, dort[d2], Karar.AYRI)  # AYRI satırı: hedef d2, kaynak d4
    _karar(ortam, dort[d1], Karar.AYNI)  # d4 → d1;  küme(d1) = {d1, d4}
    [uc] = _denetle(ortam, d3)
    sonuc = _karar(ortam, uc, Karar.AYNI)  # d3 → d2;  küme(d2) = {d2, d3}
    del sonuc

    [(talep_id, kaynak_ucu, hedef_ucu)] = [
        t for t in _acik_talepler(ortam) if t[1] == d2 and t[2] == d1
    ]
    assert (kaynak_ucu, hedef_ucu) == (d2, d1)
    onceki_birlesimler = _birlesimler(ortam)
    with pytest.raises(mu.KararCelismesi, match="'ayrı'"):
        _karar(ortam, talep_id, Karar.AYNI)
    assert _birlesimler(ortam) == onceki_birlesimler
    assert _talep_durumu(ortam, talep_id) == TalepDurumu.ACIK.value
    _butunluk_temiz(ortam)


def test_cok_adimli_zincirin_derinindeki_ayri_karari_korunur(
    ortam: Ortam, env: Envanter
) -> None:
    """``N3`` iki birleşme sonra ``N1``in kimlik geçmişindedir; ``N4 ≠ N3``
    kararı ``N4 = N1`` birleşmesini yine durdurur."""
    n1 = _depo(ortam, env, ad="D1", sehir="EDIRNE")
    _sart(ortam, n1, ["sehir"])
    _depo(ortam, env, ad="D2", sehir="EDIRNE", harici_kimlik="A")  # köprü
    n3 = _depo(ortam, env, ad="ORTAK", harici_kimlik="A")
    _sart(ortam, n3, ["harici_kimlik"])
    n4 = _depo(ortam, env, ad="ORTAK")
    _sart(ortam, n4, ["ad"])

    [dort_uc] = _denetle(ortam, n4)
    assert _talep_uclari(ortam, dort_uc)[:2] == (n4, n3)
    _karar(ortam, dort_uc, Karar.AYRI)  # N4 ≠ N3

    [ilk] = _denetle(ortam, n3)
    sonuc = _karar(ortam, ilk, Karar.AYNI)  # N3 → N2
    [zincir] = [t for t in sonuc.yeni_talepler if t.hedef_nesne_id == n1]
    ikinci = _karar(ortam, zincir.id, Karar.AYNI)  # N2 → N1; küme(N1) = üçü
    with ortam.veritabani.islem() as o:
        assert mu.kanonik_nesneyi_bul(o, n3) == n1  # iki adım derinde
    [son] = [t for t in ikinci.yeni_talepler if t.kaynak_nesne_id == n4]

    with pytest.raises(mu.KararCelismesi, match="'ayrı'"):
        _karar(ortam, son.id, Karar.AYNI)
    assert _talep_durumu(ortam, son.id) == TalepDurumu.ACIK.value
    assert _karar(ortam, son.id, Karar.AYRI).cozuldu  # çıkış yolu açık
    _butunluk_temiz(ortam)


def test_ilgisiz_ayri_karari_gecerli_birlesmeyi_engellemez(
    ortam: Ortam, env: Envanter
) -> None:
    """Denetim yalnız birleşecek iki kümenin üyelerine bakar; başka nesneler
    arasındaki ``AYRI`` kararı geçerli birleşmeyi durdurmaz."""
    baska_a = _depo(ortam, env, ad="BASKA", sehir="ANKARA")
    _sart(ortam, baska_a, ["sehir"])
    baska_b = _depo(ortam, env, ad="BASKA", sehir="ANKARA")
    [ilgisiz] = _denetle(ortam, baska_b)
    _karar(ortam, ilgisiz, Karar.AYRI)

    n1, n2, n3 = _uc_depo_zinciri(ortam, env)  # çelişkisiz zincir yine çalışır
    assert {(k, kan) for k, _, kan in _birlesimler(ortam)} == {(n3, n1), (n2, n1)}
    _butunluk_temiz(ortam)


# Bulgu 1 — birleşmeden sonra açık talepler bayat kimliğe takılı kalıyordu.


def test_birlesme_bayat_acik_talebi_kanonik_uca_tasir(
    ortam: Ortam, env: Envanter
) -> None:
    """``N1 ?= N3`` açıkken ``N3 → N2`` olursa eski talep hükümsüz kalır ve
    soru kanonik uçlarla (``N1 ?= N2``) tek bir açık talep olarak sorulur."""
    paket_id = _paket(ortam)
    n1 = _depo(ortam, env, harici_kimlik="X1")
    n2 = _depo(ortam, env, harici_kimlik="X1")
    n3 = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, n3, ["harici_kimlik"])
    with ortam.veritabani.islem() as o:
        talepler = {
            t.hedef_nesne_id: t.id
            for t in mu.nesneyi_denetle(o, n3, KULLANICI, paket_id)
        }
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value

    sonuc = _karar(ortam, talepler[n2], Karar.AYNI)  # N3 → N2

    assert [t.id for t in sonuc.gecersiz_kalan_talepler] == [talepler[n1]]
    with ortam.veritabani.islem() as o:
        bayat = mu.karar_talebi_getir(o, talepler[n1])
        assert bayat.durum == TalepDurumu.GECERSIZ.value
        assert bayat.karar is None and bayat.gecersizlik_zamani is not None
        assert (bayat.hedef_nesne_id, bayat.kaynak_nesne_id) == (n1, n3)  # geçmiş
        olaylar = di.olaylari_listele(o, karar_talebi_id=bayat.id)
    assert olaylar[-1].olay == DenetimOlayi.KARAR_TALEBI_GECERSIZ_KALDI.value
    assert "kanonik" in str(olaylar[-1].gerekce)

    [(yeni_id, kaynak_ucu, hedef_ucu)] = _acik_talepler(ortam)
    assert (kaynak_ucu, hedef_ucu) == (n2, n1)  # kanonik uçlar
    assert yeni_id not in (talepler[n1], talepler[n2])
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value  # tek açık talep tutuyor
    assert _karar(ortam, yeni_id, Karar.AYRI).paket_durumu is CALISIYOR
    _butunluk_temiz(ortam)


def test_hukumsuz_kalan_bayat_talebe_karar_verilemez(
    ortam: Ortam, env: Envanter
) -> None:
    n1, n2, _, talepler = _uc_esit_depo(ortam, env)
    _karar(ortam, talepler[n2], Karar.AYNI)
    for karar in (Karar.AYNI, Karar.AYRI, Karar.KARARSIZ):
        with pytest.raises(mu.KararTalebiKapali, match="geçersiz"):
            _karar(ortam, talepler[n1], karar)
    assert _talep_durumu(ortam, talepler[n1]) == TalepDurumu.GECERSIZ.value


def test_iki_ucu_ayni_kanonige_dusen_talep_karar_beklemez(
    ortam: Ortam, env: Envanter
) -> None:
    """Açık ``X ?= Y`` talebi varken aday üzerinden ``X`` ile ``Y`` birleşirse
    talebin iki ucu aynı kanonik nesneye düşer; soru kendiliğinden yanıtlanmış
    olur, kullanıcıdan ikinci bir karar beklenmez."""
    x = _depo(ortam, env, ad="ORTAK", harici_kimlik="A")
    _sart(ortam, x, ["ad", "harici_kimlik"])
    y = _depo(ortam, env, ad="ORTAK", sehir="B")
    _sart(ortam, y, ["ad", "sehir"])
    [kesin_talep] = _denetle(ortam, y)  # açık bırakılır
    assert _talep_uclari(ortam, kesin_talep)[:2] == (y, x)

    paket_id = _paket(ortam)
    z = _aday(
        ortam,
        paket_id,
        env.depo_id,
        {"ad": "BASKA", "harici_kimlik": "A", "sehir": "B"},
    )
    aday_talepleri = _adayi_denetle(ortam, z)
    assert len(aday_talepleri) == 2
    _karar(ortam, aday_talepleri[0], Karar.AYNI)
    sonuc = _karar(ortam, aday_talepleri[1], Karar.AYNI)  # X = Y

    assert [t.id for t in sonuc.gecersiz_kalan_talepler] == [kesin_talep]
    assert _talep_durumu(ortam, kesin_talep) == TalepDurumu.GECERSIZ.value
    assert _acik_talepler(ortam) == []  # kimse yeniden sormuyor
    assert _paket_durumu(ortam, paket_id) == CALISIYOR.value
    assert _birlesimler(ortam) == [(y, x, x)]
    with ortam.veritabani.islem() as o:
        assert mu.adayin_kesin_nesnesi(o, z) == x
    _butunluk_temiz(ortam)


def test_bayat_talep_baska_pakete_aitse_o_paket_de_esitlenir(
    ortam: Ortam, env: Envanter
) -> None:
    """Kanonik soru tek kalır; iki paket de ortak sorunun cevabını bekler."""
    p1 = _paket(ortam)
    p2 = _paket(ortam)
    n1 = _depo(ortam, env, harici_kimlik="X1")
    n2 = _depo(ortam, env, harici_kimlik="X1")
    n3 = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, n3, ["harici_kimlik"])
    with ortam.veritabani.islem() as o:  # N1 ?= N3 talebi P2'ye ait
        [bayat] = mu.nesneyi_denetle(o, n1, KULLANICI, p2)
    assert (bayat.hedef_nesne_id, bayat.kaynak_nesne_id) == (n1, n3)
    assert _paket_durumu(ortam, p2) == BEKLIYOR.value
    with ortam.veritabani.islem() as o:  # N2 ?= N3 talebi P1'e ait
        [ikinci] = [
            t
            for t in mu.nesneyi_denetle(o, n3, KULLANICI, p1)
            if t.hedef_nesne_id == n2
        ]

    _karar(ortam, ikinci.id, Karar.AYNI)  # N3 → N2

    assert _talep_durumu(ortam, bayat.id) == TalepDurumu.GECERSIZ.value
    assert _paket_durumu(ortam, p2) == BEKLIYOR.value
    assert _paket_durumu(ortam, p1) == BEKLIYOR.value  # soru P1'de duruyor
    with ortam.veritabani.islem() as o:
        [ortak] = mu.talepleri_listele(o, durum=TalepDurumu.ACIK)
        for p in (p1, p2):
            assert [
                t.id
                for t in mu.talepleri_listele(
                    o, islem_paketi_id=p, durum=TalepDurumu.ACIK
                )
            ] == [ortak.id]
    _karar(ortam, ortak.id, Karar.AYRI)
    assert _paket_durumu(ortam, p1) == CALISIYOR.value
    assert _paket_durumu(ortam, p2) == CALISIYOR.value
    _butunluk_temiz(ortam)


# Bulgu 2 — karar ve paket iptali bütünüyle atomik değildi.


@pytest.mark.parametrize(
    "kesme_noktasi",
    [
        "iliskileri_devret",  # ilk değişiklikten hemen sonra
        "_birlesimleri_kanonige_bagla",  # birleşim satırı yazıldıktan sonra
        "_acik_talepleri_uzlastir",  # birleştirmenin son adımı
        "_paket_durumunu_esitle",  # servisin en son adımı
    ],
)
def test_karar_duserse_hicbir_kalici_degisiklik_kalmaz(
    ortam: Ortam,
    env: Envanter,
    monkeypatch: pytest.MonkeyPatch,
    kesme_noktasi: str,
) -> None:
    """Çağıran hatayı yutup dış transaction'ı commit etse bile yarım karar
    kalmaz; çağıranın servisten **önce** yaptığı bağımsız değişiklik durur."""
    paket_id = _paket(ortam)
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    [talep_id] = _denetle(ortam, kaynak, paket_id)
    onceki_olaylar = _olaylar(ortam)

    with ortam.veritabani.islem() as o:
        bagimsiz = ni.nesne_olustur(o, env.depo_id, {"ad": "Bağımsız"}).id
        monkeypatch.setattr(mu, kesme_noktasi, _patlat)
        with pytest.raises(EnjekteHata):
            mu.karar_ver(o, talep_id, Karar.AYNI, KULLANICI)
        monkeypatch.undo()
    # dış transaction commit edildi; kalıcı durum yeni oturumdan okunur

    with ortam.veritabani.islem() as o:
        talep = mu.karar_talebi_getir(o, talep_id)
        assert (talep.durum, talep.karar) == (TalepDurumu.ACIK.value, None)
        assert talep.karar_zamani is None and talep.karar_aktor_turu is None
        assert mu.nesne_birlesimini_bul(o, kaynak) is None
        assert ni.nesne_getir(o, kaynak).yasam_durumu == YasamDurumu.ETKIN.value
        assert ni.nesne_getir(o, bagimsiz).id == bagimsiz  # bağımsız değişiklik durdu
    assert _sayi(ortam, mt.NESNE_BIRLESIMI) == 0
    assert _olaylar(ortam) == onceki_olaylar  # yarım denetim izi de yok
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value
    _butunluk_temiz(ortam)


def test_aday_cozumlemesi_duserse_yarim_cozumleme_kalmaz(
    ortam: Ortam, env: Envanter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Aday yolunda da aynı sınır: çözümleme satırı yazıldıktan sonra düşen
    adım her şeyi geri alır."""
    mevcut = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, mevcut, ["harici_kimlik"])
    paket_id = _paket(ortam)
    aday_id = _aday(ortam, paket_id, env.depo_id, {"ad": "Depo", "harici_kimlik": "X1"})
    [talep_id] = _adayi_denetle(ortam, aday_id)
    onceki_olaylar = _olaylar(ortam)

    with ortam.veritabani.islem() as o:
        monkeypatch.setattr(mu, "_paket_durumunu_esitle", _patlat)
        with pytest.raises(EnjekteHata):
            mu.karar_ver(o, talep_id, Karar.AYNI, KULLANICI)
        monkeypatch.undo()

    with ortam.veritabani.islem() as o:
        assert mu.karar_talebi_getir(o, talep_id).durum == TalepDurumu.ACIK.value
        assert mu.aday_cozumlemesi_bul(o, aday_id) is None
    assert _sayi(ortam, mt.ADAY_NESNE_COZUMLEMESI) == 0
    assert _olaylar(ortam) == onceki_olaylar
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value


@pytest.mark.parametrize("kesme_noktasi", ["_acik_talepleri_gecersiz_kil", "olay_yaz"])
def test_paket_iptali_duserse_yarim_iptal_kalmaz(
    ortam: Ortam,
    env: Envanter,
    monkeypatch: pytest.MonkeyPatch,
    kesme_noktasi: str,
) -> None:
    """Durum geçişi ile talep hükümsüzleştirmesi tek sınırdadır: paket iptal
    olup talebi açık kalamaz."""
    paket_id = _paket(ortam)
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    [talep_id] = _denetle(ortam, kaynak, paket_id)
    onceki_olaylar = _olaylar(ortam)

    with ortam.veritabani.islem() as o:
        bagimsiz = ni.nesne_olustur(o, env.depo_id, {"ad": "Bağımsız"}).id
        monkeypatch.setattr(tsi, kesme_noktasi, _patlat)
        with pytest.raises(EnjekteHata):
            tsi.paketi_iptal_et(o, paket_id, KULLANICI)
        monkeypatch.undo()

    with ortam.veritabani.islem() as o:
        assert tsi.paket_getir(o, paket_id).durum == BEKLIYOR.value
        assert mu.karar_talebi_getir(o, talep_id).durum == TalepDurumu.ACIK.value
        assert ni.nesne_getir(o, bagimsiz).id == bagimsiz
    assert _olaylar(ortam) == onceki_olaylar
    # iptal yeniden denenince olağan biçimde çalışır
    _iptal_et(ortam, paket_id)
    assert _paket_durumu(ortam, paket_id) == IPTAL.value
    assert _talep_durumu(ortam, talep_id) == TalepDurumu.GECERSIZ.value


@pytest.mark.parametrize("once_ayri", [False, True])
@pytest.mark.parametrize("ters", [False, True])
def test_aday_ayri_karari_kesin_birlesmede_korunur(
    ortam: Ortam, env: Envanter, once_ayri: bool, ters: bool
) -> None:
    x, y, z, talepler = _aday_iki_kesin(ortam, env)
    if ters:
        x, y = y, x
    with ortam.veritabani.islem() as o:
        hedefler = {mu.karar_talebi_getir(o, t).hedef_nesne_id: t for t in talepler}
    if once_ayri:
        _karar(ortam, hedefler[y], Karar.AYRI)
    _karar(ortam, hedefler[x], Karar.AYNI)
    if not once_ayri:
        _karar(ortam, hedefler[y], Karar.AYRI)
    _sart(ortam, x, ["ad"])
    [talep] = _denetle(ortam, y)
    once = _olaylar(ortam)
    with ortam.veritabani.islem() as o:
        bagimsiz = ni.nesne_olustur(o, env.depo_id, {"ad": "Bağımsız"}).id
        with pytest.raises(mu.KararCelismesi):
            mu.karar_ver(o, talep, Karar.AYNI, KULLANICI)
    with ortam.veritabani.islem() as o:
        assert mu.adayin_kesin_nesnesi(o, z) == x
        assert mu.kanonik_nesneyi_bul(o, y) == y
        assert mu.karar_talebi_getir(o, talep).durum == TalepDurumu.ACIK.value
        assert ni.nesne_getir(o, bagimsiz).id == bagimsiz
    assert _olaylar(ortam) == once


def test_adayin_ilk_cozumlemesi_tarihsel_ayriyi_asamaz(
    ortam: Ortam, env: Envanter
) -> None:
    """``Z ≠ Y`` dendikten sonra ``Y`` ``X``e birleşirse ``Z ?= X`` sorusu
    artık cevaplanmış sayılır: gereksiz soru hükümsüz olur (2026-09-20 üçüncü
    turu, bulgu 3), kullanıcıdan ikinci karar istenmez ve aday hiçbir şekilde
    o kanonik nesneye çözümlenmez."""
    x, y, z, talepler = _aday_iki_kesin(ortam, env)
    _karar(ortam, talepler[1], Karar.AYRI)
    _sart(ortam, x, ["ad"])
    [talep] = _denetle(ortam, y)
    _karar(ortam, talep, Karar.AYNI)
    with ortam.veritabani.islem() as o:
        bayat = mu.karar_talebi_getir(o, talepler[0])
        assert bayat.durum == TalepDurumu.GECERSIZ.value
        assert bayat.karar is None  # kullanıcı adına karar yazılmadı
    once = _olaylar(ortam)
    with ortam.veritabani.islem() as o:
        with pytest.raises(mu.KararTalebiKapali):
            mu.karar_ver(o, talepler[0], Karar.AYNI, KULLANICI)
    with ortam.veritabani.islem() as o:
        assert mu.adayin_kesin_nesnesi(o, z) is None
    assert _olaylar(ortam) == once


def test_aday_cozumlemesi_tarihsel_ayri_kararini_ham_yolda_da_asamaz(
    ortam: Ortam, env: Envanter
) -> None:
    """Derinlemesine savunma: uzlaştırma atlansa bile (ham SQL ile yeniden
    açılan soru) ``_adayi_cozumle`` tarihsel ``AYRI`` kararını korur."""
    x, y, z, talepler = _aday_iki_kesin(ortam, env)
    _karar(ortam, talepler[1], Karar.AYRI)
    _sart(ortam, x, ["ad"])
    [talep] = _denetle(ortam, y)
    _karar(ortam, talep, Karar.AYNI)
    with ortam.veritabani.islem() as o:  # hükümsüz soruyu zorla yeniden aç
        o.execute(
            text(
                "UPDATE karar_talebi SET durum = 'acik', gecersizlik_zamani = NULL "
                "WHERE id = :t"
            ),
            {"t": talepler[0]},
        )
    once = _olaylar(ortam)
    with ortam.veritabani.islem() as o:
        with pytest.raises(mu.KararCelismesi):
            mu.karar_ver(o, talepler[0], Karar.AYNI, KULLANICI)
    with ortam.veritabani.islem() as o:
        assert mu.adayin_kesin_nesnesi(o, z) is None
        assert mu.karar_talebi_getir(o, talepler[0]).karar is None
    assert _olaylar(ortam) == once


@pytest.mark.parametrize("cozum_hedefi", [0, 1])
def test_cozulmus_aday_kanonik_kimligi_tekrar_sormaz(
    ortam: Ortam, env: Envanter, cozum_hedefi: int
) -> None:
    x, y, z, talepler = _aday_iki_kesin(ortam, env)
    _karar(ortam, talepler[cozum_hedefi], Karar.AYNI)
    _sart(ortam, x, ["ad"])
    [talep] = _denetle(ortam, y)
    _karar(ortam, talep, Karar.AYNI)
    with ortam.veritabani.islem() as o:
        assert mu.adayin_kesin_nesnesi(o, z) == x
        eski = mu.karar_talebi_getir(o, talepler[1 - cozum_hedefi])
        assert eski.durum == TalepDurumu.GECERSIZ.value
        assert eski.karar is None
        assert eski.islem_paketi_id is not None
        assert tsi.paket_getir(o, eski.islem_paketi_id).durum == CALISIYOR.value
    assert _adayi_denetle(ortam, z) == []
    assert _acik_talepler(ortam) == []


def _iki_paket_ortak_soru(ortam: Ortam, env: Envanter) -> tuple[int, int, int]:
    p1, p2 = _paket(ortam), _paket(ortam)
    n1 = _depo(ortam, env, harici_kimlik="X1")
    n2 = _depo(ortam, env, harici_kimlik="X1")
    n3 = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, n3, ["harici_kimlik"])
    _denetle(ortam, n1, p2)
    with ortam.veritabani.islem() as o:
        birlesme = next(
            t.id
            for t in mu.nesneyi_denetle(o, n3, KULLANICI, p1)
            if t.hedef_nesne_id == n2
        )
    _karar(ortam, birlesme, Karar.AYNI)
    [(ortak, _, _)] = _acik_talepler(ortam)
    return p1, p2, ortak


def test_aday_ayri_karari_baska_aday_uzerinden_de_asilamaz(
    ortam: Ortam, env: Envanter
) -> None:
    x, y, _, talepler = _aday_iki_kesin(ortam, env)
    _karar(ortam, talepler[0], Karar.AYNI)
    _karar(ortam, talepler[1], Karar.AYRI)
    p2 = _paket(ortam)
    z2 = _aday(
        ortam,
        p2,
        env.depo_id,
        {"ad": "İkinci aday", "harici_kimlik": "A", "sehir": "B"},
    )
    ikinci = _adayi_denetle(ortam, z2)
    _karar(ortam, ikinci[1], Karar.AYNI)
    with pytest.raises(mu.KararCelismesi):
        _karar(ortam, ikinci[0], Karar.AYNI)
    with ortam.veritabani.islem() as o:
        assert mu.adayin_kesin_nesnesi(o, z2) == y
        assert mu.kanonik_nesneyi_bul(o, x) == x
    assert _paket_durumu(ortam, p2) == BEKLIYOR.value


def test_aday_talebi_kapatma_duserse_birlesme_geri_alinir(
    ortam: Ortam, env: Envanter, monkeypatch: pytest.MonkeyPatch
) -> None:
    x, y, z, talepler = _aday_iki_kesin(ortam, env)
    _karar(ortam, talepler[1], Karar.AYNI)
    _sart(ortam, x, ["ad"])
    [birlesme] = _denetle(ortam, y)
    once = _olaylar(ortam)
    kapat: Callable[[Session, mt.KararTalebi, Aktor], list[mt.KararTalebi]] = getattr(
        mu, "_aday_talepleri_uzlastir"
    )

    def kapat_ve_patlat(
        o: Session, talep: mt.KararTalebi, aktor: Aktor
    ) -> list[mt.KararTalebi]:
        assert len(kapat(o, talep, aktor)) == 1
        raise EnjekteHata("aday talebi kapandıktan sonra")

    with ortam.veritabani.islem() as o:
        monkeypatch.setattr(mu, "_aday_talepleri_uzlastir", kapat_ve_patlat)
        with pytest.raises(EnjekteHata):
            mu.karar_ver(o, birlesme, Karar.AYNI, KULLANICI)
        monkeypatch.undo()
    with ortam.veritabani.islem() as o:
        assert mu.adayin_kesin_nesnesi(o, z) == y
        assert mu.nesne_birlesimini_bul(o, y) is None
        assert mu.karar_talebi_getir(o, talepler[0]).durum == TalepDurumu.ACIK.value
        assert mu.karar_talebi_getir(o, birlesme).durum == TalepDurumu.ACIK.value
    assert _olaylar(ortam) == once


def test_ortak_paket_iptali_hatasi_baglari_ve_beklemeyi_korur(
    ortam: Ortam, env: Envanter, monkeypatch: pytest.MonkeyPatch
) -> None:
    p1, p2, talep = _iki_paket_ortak_soru(ortam, env)
    _iptal_et(ortam, p1)
    once = _olaylar(ortam)
    with ortam.veritabani.islem() as o:
        monkeypatch.setattr(tsi, "olay_yaz", _patlat)
        with pytest.raises(EnjekteHata):
            tsi.paketi_iptal_et(o, p2, KULLANICI)
        monkeypatch.undo()
    assert _paket_durumu(ortam, p1) == IPTAL.value
    assert _paket_durumu(ortam, p2) == BEKLIYOR.value
    assert _talep_durumu(ortam, talep) == TalepDurumu.ACIK.value
    assert _olaylar(ortam) == once
    _karar(ortam, talep, Karar.AYRI)
    assert _paket_durumu(ortam, p2) == CALISIYOR.value


@pytest.mark.parametrize("iptal_indeksi", [0, 1])
@pytest.mark.parametrize("karar", [Karar.AYNI, Karar.AYRI])
def test_ortak_soru_paket_iptaliyle_kaybolmaz(
    ortam: Ortam, env: Envanter, iptal_indeksi: int, karar: Karar
) -> None:
    p1, p2, talep = _iki_paket_ortak_soru(ortam, env)
    iptal, kalan = (p1, p2) if iptal_indeksi == 0 else (p2, p1)
    for p in (p1, p2):
        with pytest.raises(tsi.PaketDurumuGecersiz):
            _aday(ortam, p, env.depo_id, {"ad": "Erken"})
        with ortam.veritabani.islem() as o:
            with pytest.raises(tsi.PaketDurumuGecersiz):
                tsi.paketi_devam_et(o, p)
    _iptal_et(ortam, iptal)
    assert _paket_durumu(ortam, kalan) == BEKLIYOR.value
    assert _talep_durumu(ortam, talep) == TalepDurumu.ACIK.value
    _karar(ortam, talep, Karar.KARARSIZ, "Henüz karar yok")
    assert _paket_durumu(ortam, kalan) == BEKLIYOR.value
    _karar(ortam, talep, karar)
    assert _paket_durumu(ortam, kalan) == CALISIYOR.value
    assert _paket_durumu(ortam, iptal) == IPTAL.value
    _aday(ortam, kalan, env.depo_id, {"ad": "Cevaptan sonra"})
    _butunluk_temiz(ortam)


def test_ortak_son_paket_iptali_soruyu_gecersiz_kilar(
    ortam: Ortam, env: Envanter
) -> None:
    p1, p2, talep = _iki_paket_ortak_soru(ortam, env)
    _iptal_et(ortam, p1)
    _iptal_et(ortam, p2)
    assert _talep_durumu(ortam, talep) == TalepDurumu.GECERSIZ.value
    with ortam.veritabani.islem() as o:
        eski = mu.karar_talebi_getir(o, talep)
        assert eski.karar is None
        assert eski.kaynak_nesne_id is not None
        kaynak = eski.kaynak_nesne_id
    p3 = _paket(ortam)
    assert len(_denetle(ortam, kaynak, p3)) == 1
    assert _paket_durumu(ortam, p3) == BEKLIYOR.value


def test_ayni_soru_yeni_paketi_de_bekletir_tekrar_acilmaz(
    ortam: Ortam, env: Envanter
) -> None:
    p1, p2 = _paket(ortam), _paket(ortam)
    x = _depo(ortam, env, harici_kimlik="A")
    y = _depo(ortam, env, harici_kimlik="A")
    _sart(ortam, x, ["harici_kimlik"])
    [talep] = _denetle(ortam, y, p1)
    for _ in range(2):
        assert _denetle(ortam, y, p2) == []
    assert _paket_durumu(ortam, p2) == BEKLIYOR.value
    assert _sayi(ortam, mt.KARAR_TALEBI) == 1
    assert _sayi(ortam, mt.KARAR_TALEBI_PAKETI) == 2
    _karar(ortam, talep, Karar.AYRI)
    assert _paket_durumu(ortam, p1) == CALISIYOR.value
    assert _paket_durumu(ortam, p2) == CALISIYOR.value


@pytest.mark.parametrize("kesme", ["_talebi_pakete_bagla", "_kanonik_soruyu_koru"])
def test_paket_bagi_aktarimi_duserse_karar_tamamen_geri_alinir(
    ortam: Ortam, env: Envanter, monkeypatch: pytest.MonkeyPatch, kesme: str
) -> None:
    p1, p2, ortak = _iki_paket_ortak_soru(ortam, env)
    with ortam.veritabani.islem() as o:
        eski = mu.karar_talebi_getir(o, ortak)
        assert eski.kaynak_nesne_id is not None
        n2 = eski.kaynak_nesne_id
    n4 = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, n4, ["harici_kimlik"])
    talepler = _denetle(ortam, n4, p1)
    with ortam.veritabani.islem() as o:
        birlesme = next(
            t for t in talepler if mu.karar_talebi_getir(o, t).hedef_nesne_id == n2
        )
    once = _olaylar(ortam)
    bag_sayisi = _sayi(ortam, mt.KARAR_TALEBI_PAKETI)
    with ortam.veritabani.islem() as o:
        monkeypatch.setattr(mu, kesme, _patlat)
        with pytest.raises(EnjekteHata):
            mu.karar_ver(o, birlesme, Karar.AYNI, KULLANICI)
        monkeypatch.undo()
    assert _olaylar(ortam) == once
    assert _sayi(ortam, mt.KARAR_TALEBI_PAKETI) == bag_sayisi
    assert _talep_durumu(ortam, birlesme) == TalepDurumu.ACIK.value
    assert _paket_durumu(ortam, p2) == BEKLIYOR.value
    with ortam.veritabani.islem() as o:
        assert mu.nesne_birlesimini_bul(o, n4) is None


# --- 2026-09-20 üçüncü turu: bağımsız köken, tarama atomikliği, aday uzlaştırması ----


def _koken(ortam: Ortam, talep_id: int) -> tuple[str, int | None, bool]:
    """``(durum, tarihsel açılış paketi, bağımsız köken)``."""
    with ortam.veritabani.islem() as o:
        t = mu.karar_talebi_getir(o, talep_id)
        return t.durum, t.islem_paketi_id, bool(t.bagimsiz_koken)


def _uc_esit_depo_paketsiz(ortam: Ortam, env: Envanter) -> tuple[int, int, int, int]:
    """N1, N2, N3 aynı değerde; N1 paketsiz taranınca N1–N3 sorusu doğar."""
    n1 = _depo(ortam, env, harici_kimlik="X1")
    n2 = _depo(ortam, env, harici_kimlik="X1")
    n3 = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, n3, ["harici_kimlik"])
    [bagimsiz] = _denetle(ortam, n1)  # paketsiz soru: N1 ?= N3
    assert _talep_uclari(ortam, bagimsiz)[:2] == (n3, n1)
    return n1, n2, n3, bagimsiz


def _n3_n2_birlestir(
    ortam: Ortam, env: Envanter, n2: int, n3: int, paket_id: int
) -> int:
    with ortam.veritabani.islem() as o:
        [talep] = [
            t
            for t in mu.nesneyi_denetle(o, n3, KULLANICI, paket_id)
            if t.hedef_nesne_id == n2
        ]
    _karar(ortam, talep.id, Karar.AYNI)
    return talep.id


# Bulgu 1 — bağımsız soru birleşme sonrası paket iptaliyle kayboluyordu.


def test_bagimsiz_soru_birlesme_ve_iptalden_sonra_cevaplanabilir_kalir(
    ortam: Ortam, env: Envanter
) -> None:
    """Paketten bağımsız doğan soru, kanonik halefine taşınırken kökenini de
    taşır; bağlı bütün paketler iptal edilse de açık ve cevaplanabilir kalır.
    Halef burada zincirleme denetimin **zaten açtığı** sorudur."""
    n1, n2, n3, bagimsiz = _uc_esit_depo_paketsiz(ortam, env)
    p = _paket(ortam)
    _n3_n2_birlestir(ortam, env, n2, n3, p)

    assert _koken(ortam, bagimsiz)[0] == TalepDurumu.GECERSIZ.value
    [(halef, kaynak_ucu, hedef_ucu)] = _acik_talepler(ortam)
    assert (kaynak_ucu, hedef_ucu) == (n2, n1)
    _, acilis_paketi, koken = _koken(ortam, halef)
    assert koken is True  # bağımsız köken devredildi
    assert acilis_paketi == p  # tarihsel açılış paketi değişmedi

    _iptal_et(ortam, p)
    assert _talep_durumu(ortam, halef) == TalepDurumu.ACIK.value
    assert _paket_durumu(ortam, p) == IPTAL.value
    sonuc = _karar(ortam, halef, Karar.AYRI)  # hâlâ cevaplanabilir
    assert sonuc.cozuldu
    _butunluk_temiz(ortam)


def test_bagimsiz_koken_yeni_acilan_kanonik_soruya_da_gecer(
    ortam: Ortam, env: Envanter
) -> None:
    """Halef zincirleme denetimden gelmiyorsa ``_kanonik_soruyu_koru`` yeni
    soruyu kendisi açar; köken o yolda da korunur."""
    n1, n2, n3, bagimsiz = _uc_esit_depo_paketsiz(ortam, env)
    with ortam.veritabani.islem() as o:  # N1 artık eşleşmiyor: halef zincirden gelmez
        ni.ozellik_yaz(o, n1, "harici_kimlik", "X9")
    p = _paket(ortam)
    _n3_n2_birlestir(ortam, env, n2, n3, p)

    assert _talep_durumu(ortam, bagimsiz) == TalepDurumu.GECERSIZ.value
    [(halef, kaynak_ucu, hedef_ucu)] = _acik_talepler(ortam)
    assert (kaynak_ucu, hedef_ucu) == (n2, n1)
    assert _koken(ortam, halef) == (TalepDurumu.ACIK.value, None, True)

    _iptal_et(ortam, p)
    assert _talep_durumu(ortam, halef) == TalepDurumu.ACIK.value
    _butunluk_temiz(ortam)


def test_bagimsiz_koken_ardisik_birlesmelerde_de_kalir(
    ortam: Ortam, env: Envanter
) -> None:
    """Köken her aktarımda taşınır: iki birleşme ve iki paket iptalinden sonra
    soru hâlâ ayakta."""
    n1, n2, n3, _bagimsiz = _uc_esit_depo_paketsiz(ortam, env)
    p1 = _paket(ortam)
    _n3_n2_birlestir(ortam, env, n2, n3, p1)  # birinci birleşme: N3 → N2
    [(halef1, _, _)] = _acik_talepler(ortam)
    assert _koken(ortam, halef1)[2] is True

    n4 = _depo(ortam, env, harici_kimlik="X1")  # kanonik N2 ile eşleşen dördüncü
    p2 = _paket(ortam)
    with ortam.veritabani.islem() as o:
        [dort] = [
            t
            for t in mu.nesneyi_denetle(o, n4, KULLANICI, p2)
            if t.kaynak_nesne_id == n4 and t.hedef_nesne_id == n2
        ]
    _karar(ortam, dort.id, Karar.AYNI)  # ikinci birleşme: N4 → N2

    _iptal_et(ortam, p1)
    _iptal_et(ortam, p2)
    acik = [t for t in _acik_talepler(ortam) if t[2] == n1]
    assert len(acik) == 1
    assert _koken(ortam, acik[0][0])[2] is True
    assert _karar(ortam, acik[0][0], Karar.AYRI).cozuldu
    _butunluk_temiz(ortam)


def test_birlesme_yoksa_bagimsiz_soru_iptalden_etkilenmez(
    ortam: Ortam, env: Envanter
) -> None:
    """Olumlu kontrol: birleşme olmadan da bağımsız soru iptalle düşmez."""
    _, _, n3, bagimsiz = _uc_esit_depo_paketsiz(ortam, env)
    p = _paket(ortam)
    with ortam.veritabani.islem() as o:
        mu.nesneyi_denetle(o, n3, KULLANICI, p)  # aynı soruya paket bağlanır
    assert _paket_durumu(ortam, p) == BEKLIYOR.value
    _iptal_et(ortam, p)
    assert _koken(ortam, bagimsiz) == (TalepDurumu.ACIK.value, None, True)
    assert _karar(ortam, bagimsiz, Karar.AYRI).cozuldu


def test_paket_kaynakli_soru_son_etkin_paket_iptalinde_hukumsuz_olur(
    ortam: Ortam, env: Envanter
) -> None:
    """Olumlu kontrol: bağımsız kökeni olmayan soru eski davranışını korur —
    üç paket paylaşır, ilk ikisinin iptali bekletmeyi sürdürür, sonuncusunda
    hükümsüz olur."""
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    paketler = [_paket(ortam) for _ in range(3)]
    with ortam.veritabani.islem() as o:
        [ortak] = mu.nesneyi_denetle(o, kaynak, KULLANICI, paketler[0])
        for p in paketler[1:]:
            mu.nesneyi_denetle(o, kaynak, KULLANICI, p)
    assert _koken(ortam, ortak.id) == (TalepDurumu.ACIK.value, paketler[0], False)
    for p in paketler:
        assert _paket_durumu(ortam, p) == BEKLIYOR.value

    _iptal_et(ortam, paketler[0])
    assert _talep_durumu(ortam, ortak.id) == TalepDurumu.ACIK.value
    _iptal_et(ortam, paketler[1])
    assert _talep_durumu(ortam, ortak.id) == TalepDurumu.ACIK.value
    assert _paket_durumu(ortam, paketler[2]) == BEKLIYOR.value
    _iptal_et(ortam, paketler[2])
    assert _talep_durumu(ortam, ortak.id) == TalepDurumu.GECERSIZ.value
    _butunluk_temiz(ortam)


# Bulgu 2 — tarama servislerinde yarım yazma ve bekleme engelinin aşılması.


def _tarama_dustu(
    ortam: Ortam,
    monkeypatch: pytest.MonkeyPatch,
    env: Envanter,
    tarama: Callable[[Session], object],
) -> int:
    """Çağıran önce bağımsız bir değişiklik yapar, tarama ``paketi_beklet``
    adımında düşer, çağıran hatayı yutar ve dış işlemi commit eder."""
    with ortam.veritabani.islem() as o:
        bagimsiz = ni.nesne_olustur(o, env.depo_id, {"ad": "Bağımsız"}).id
        monkeypatch.setattr(mu, "paketi_beklet", _patlat)
        with pytest.raises(EnjekteHata):
            tarama(o)
        monkeypatch.undo()
    return bagimsiz


def test_kesin_tarama_duserse_yeni_soru_kalmaz(
    ortam: Ortam, env: Envanter, monkeypatch: pytest.MonkeyPatch
) -> None:
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    paket_id = _paket(ortam)
    onceki_olaylar = _olaylar(ortam)

    bagimsiz = _tarama_dustu(
        ortam,
        monkeypatch,
        env,
        lambda o: mu.nesneyi_denetle(o, kaynak, KULLANICI, paket_id),
    )

    with ortam.veritabani.islem() as o:
        assert mu.talepleri_listele(o) == []
        assert ni.nesne_getir(o, bagimsiz).id == bagimsiz  # bağımsız değişiklik durdu
    assert _sayi(ortam, mt.KARAR_TALEBI_PAKETI) == 0
    assert _olaylar(ortam) == onceki_olaylar
    assert _paket_durumu(ortam, paket_id) == CALISIYOR.value
    # yeniden denenince olağan biçimde çalışır ve paket gerçekten bekler
    [talep_id] = _denetle(ortam, kaynak, paket_id)
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value
    with pytest.raises(tsi.PaketDurumuGecersiz):
        with ortam.veritabani.islem() as o:
            tsi.aday_nesne_ekle(o, paket_id, env.depo_id, {"ad": "Yeni"})
    assert _karar(ortam, talep_id, Karar.AYRI).cozuldu


def test_paket_bagi_yazmasi_duserse_bag_kalmaz(
    ortam: Ortam, env: Envanter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mevcut ortak soruya başka paketin bağlanması da aynı sınırdadır."""
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    [ortak] = _denetle(ortam, kaynak)  # paketsiz ortak soru
    paket_id = _paket(ortam)
    onceki_olaylar = _olaylar(ortam)

    bagimsiz = _tarama_dustu(
        ortam,
        monkeypatch,
        env,
        lambda o: mu.nesneyi_denetle(o, kaynak, KULLANICI, paket_id),
    )

    assert _sayi(ortam, mt.KARAR_TALEBI_PAKETI) == 0
    assert _talep_durumu(ortam, ortak) == TalepDurumu.ACIK.value
    with ortam.veritabani.islem() as o:
        assert ni.nesne_getir(o, bagimsiz).id == bagimsiz
    assert _olaylar(ortam) == onceki_olaylar
    assert _paket_durumu(ortam, paket_id) == CALISIYOR.value
    with ortam.veritabani.islem() as o:  # yeniden denemede bağ kurulur
        assert mu.nesneyi_denetle(o, kaynak, KULLANICI, paket_id) == []
    assert _sayi(ortam, mt.KARAR_TALEBI_PAKETI) == 1
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value


def test_aday_taramasi_duserse_soru_kalmaz(
    ortam: Ortam, env: Envanter, monkeypatch: pytest.MonkeyPatch
) -> None:
    mevcut = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, mevcut, ["harici_kimlik"])
    paket_id = _paket(ortam)
    aday_id = _aday(ortam, paket_id, env.depo_id, {"ad": "Depo", "harici_kimlik": "X1"})
    onceki_olaylar = _olaylar(ortam)

    bagimsiz = _tarama_dustu(
        ortam, monkeypatch, env, lambda o: mu.adayi_denetle(o, aday_id, KULLANICI)
    )

    with ortam.veritabani.islem() as o:
        assert mu.talepleri_listele(o) == []
        assert ni.nesne_getir(o, bagimsiz).id == bagimsiz
    assert _sayi(ortam, mt.KARAR_TALEBI_PAKETI) == 0
    assert _olaylar(ortam) == onceki_olaylar
    assert _paket_durumu(ortam, paket_id) == CALISIYOR.value
    [talep_id] = _adayi_denetle(ortam, aday_id)
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value
    assert _karar(ortam, talep_id, Karar.AYRI).cozuldu


def test_karar_icindeki_zincirleme_tarama_duserse_karar_da_geri_alinir(
    ortam: Ortam, env: Envanter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``karar_ver`` taramayı kendi dış SAVEPOINT'i içinden çağırır; iç içe
    SAVEPOINT davranışı korunur ve iç tarama düşerse karar da geri alınır."""
    _, n2, n3, _ = _uc_esit_depo_paketsiz(ortam, env)
    paket_id = _paket(ortam)
    with ortam.veritabani.islem() as o:
        [talep] = [
            t
            for t in mu.nesneyi_denetle(o, n3, KULLANICI, paket_id)
            if t.hedef_nesne_id == n2
        ]
    onceki_olaylar = _olaylar(ortam)

    with ortam.veritabani.islem() as o:  # zincirleme tarama yeni soru açarken düşer
        monkeypatch.setattr(mu, "_talep_ac", _patlat)
        with pytest.raises(EnjekteHata):
            mu.karar_ver(o, talep.id, Karar.AYNI, KULLANICI)
        monkeypatch.undo()

    with ortam.veritabani.islem() as o:
        assert mu.karar_talebi_getir(o, talep.id).durum == TalepDurumu.ACIK.value
        assert mu.nesne_birlesimini_bul(o, n3) is None
    assert _olaylar(ortam) == onceki_olaylar
    _butunluk_temiz(ortam)


# Bulgu 3 — çözümlenmemiş adaya aynı kanonik kimlik için tekrar soru soruluyordu.


def _aday_iki_kanonik(
    ortam: Ortam, env: Envanter
) -> tuple[int, int, int, int, list[int]]:
    """``Z`` adayı ``X`` ve ``Y`` ile eşleşir; ``X ?= Y`` sorusu da açıktır."""
    x = _depo(ortam, env, ad="ORTAK", harici_kimlik="A")
    _sart(ortam, x, ["ad", "harici_kimlik"])
    y = _depo(ortam, env, ad="ORTAK", sehir="B")
    _sart(ortam, y, ["ad", "sehir"])
    paket_id = _paket(ortam)
    z = _aday(
        ortam,
        paket_id,
        env.depo_id,
        {"ad": "BASKA", "harici_kimlik": "A", "sehir": "B"},
    )
    talepler = _adayi_denetle(ortam, z)
    assert len(talepler) == 2
    [kesin] = _denetle(ortam, y)
    return x, y, z, paket_id, [*talepler, kesin]


def test_cozumlenmemis_adaya_ayni_kanonik_icin_tek_soru_kalir(
    ortam: Ortam, env: Envanter
) -> None:
    """``Y → X`` birleşince adayın iki sorusu aynı kanonik nesneyi gösterir;
    biri gerekçeli hükümsüz olur, kullanıcı adına karar yazılmaz."""
    _, _, z, _, talepler = _aday_iki_kanonik(ortam, env)
    aday_talepleri, kesin = talepler[:2], talepler[2]

    _karar(ortam, kesin, Karar.AYNI)  # Y → X

    with ortam.veritabani.islem() as o:
        assert mu.adayin_kesin_nesnesi(o, z) is None  # aday hâlâ çözümlenmemiş
        durumlar = [mu.karar_talebi_getir(o, t).durum for t in aday_talepleri]
        kararlar = [mu.karar_talebi_getir(o, t).karar for t in aday_talepleri]
    assert sorted(durumlar) == [TalepDurumu.ACIK.value, TalepDurumu.GECERSIZ.value]
    assert kararlar == [None, None]  # kullanıcı adına AYNI/AYRI yazılmadı
    [hukumsuz] = [
        t for t, d in zip(aday_talepleri, durumlar) if d == TalepDurumu.GECERSIZ.value
    ]
    with ortam.veritabani.islem() as o:
        [olay] = [
            x
            for x in di.olaylari_listele(o, karar_talebi_id=hukumsuz)
            if x.olay == DenetimOlayi.KARAR_TALEBI_GECERSIZ_KALDI.value
        ]
    assert "aynı kanonik nesneyi soruyor" in str(olay.gerekce)
    _butunluk_temiz(ortam)


def test_kalan_tek_soru_cevaplaninca_paket_beklemeyi_birakir(
    ortam: Ortam, env: Envanter
) -> None:
    """Gereksiz soru kaldırıldığı için ilk cevap paketi serbest bırakır."""
    _, _, z, paket_id, talepler = _aday_iki_kanonik(ortam, env)
    _karar(ortam, talepler[2], Karar.AYNI)
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value
    [(acik_id, _, _)] = [t for t in _acik_talepler(ortam) if t[0] in talepler[:2]]
    assert _karar(ortam, acik_id, Karar.AYRI).paket_durumu is CALISIYOR
    assert _paket_durumu(ortam, paket_id) == CALISIYOR.value
    with ortam.veritabani.islem() as o:
        assert mu.adayin_kesin_nesnesi(o, z) is None


def test_farkli_kanonik_hedefler_icin_iki_soru_acik_kalir(
    ortam: Ortam, env: Envanter
) -> None:
    """Olumlu kontrol: kanonikler ayrıysa uzlaştırma hiçbir soruyu düşürmez."""
    _, _, _, paket_id, talepler = _aday_iki_kanonik(ortam, env)
    _karar(ortam, talepler[2], Karar.AYRI)  # X ile Y ayrı kalır
    acik = {t[0] for t in _acik_talepler(ortam)}
    assert acik == set(talepler[:2])
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value


def test_hukumsuz_aday_sorusunun_paketi_kalan_soruda_durur(
    ortam: Ortam, env: Envanter
) -> None:
    """Aday sorusu adayın kendi paketine aittir; gereksiz soru düşünce paket
    korunan soruda bağlı kalır ve cevap gelene kadar beklemeyi sürdürür."""
    _, _, _, paket_id, talepler = _aday_iki_kanonik(ortam, env)
    _karar(ortam, talepler[2], Karar.AYNI)  # Y → X, bir soru hükümsüz kalır

    [(kalan, _, _)] = [t for t in _acik_talepler(ortam) if t[0] in talepler[:2]]
    with ortam.veritabani.islem() as o:
        paketler = mu.talebin_paketleri(o, mu.karar_talebi_getir(o, kalan))
    assert paketler == {paket_id}
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value
    _butunluk_temiz(ortam)


# --- şema ve mimari sınır -------------------------------------------------------------


def test_kesin_nesne_tablo_adi_dogrudur() -> None:
    """``mukerrerlik_tablolari`` kesin nesne modülünü import etmez (taslak →
    kesin zincirini kırmamak için); adın doğruluğu burada korunur."""
    assert mt.KESIN_NESNE == nt.NESNE


def test_denetim_tablolarinin_yerel_tablo_adlari_dogrudur() -> None:
    """``denetim_tablolari`` de kesin nesne ve mükerrerlik modüllerini import
    etmez: ``taslak_islemleri`` iptal ederken denetim izine yazar ve taslak →
    kesin import zinciri kurulamaz; ``mukerrerlik_tablolari`` ise aktör türünü
    denetim modülünden alır (ters yön bir döngü olurdu)."""
    assert dt.KESIN_NESNE == nt.NESNE
    assert dt.KARAR_TALEBI == mt.KARAR_TALEBI


def test_taslak_tablolari_hala_kesin_nesneye_baglanmaz(ortam: Ortam) -> None:
    """4.6 tabloları köprüyü kurar; taslak tablolarının kendisi kesin nesne
    tablolarına bağlanmaz (Aşama 4.5 ayrımı korunur)."""
    from defteriki.cekirdek import taslak_tablolari as tst

    with ortam.veritabani.motor.connect() as baglanti:
        denetci = inspect(baglanti)
        for tablo in tst.TASLAK_TABLOLARI:
            hedefler = {fk["referred_table"] for fk in denetci.get_foreign_keys(tablo)}
            assert not hedefler & set(nt.NESNE_TABLOLARI), (tablo, hedefler)
        koprü = {
            fk["referred_table"]
            for fk in denetci.get_foreign_keys(mt.ADAY_NESNE_COZUMLEMESI)
        }
        assert koprü == {"aday_nesne", "nesne", mt.KARAR_TALEBI}


def test_dort_altiya_ait_moduller_finansa_baglanmaz() -> None:
    """Çekirdek → finans yasağı yeni modüllerde de geçerli (ayrıntılı denetim
    ``tests/test_mimari_sinir.py``; burada doğrudan import sınanır)."""
    import ast

    kok = Path(__file__).resolve().parent.parent / "src" / "defteriki" / "cekirdek"
    for ad in (
        "mukerrerlik_tablolari.py",
        "mukerrerlik_islemleri.py",
        "denetim_tablolari.py",
        "denetim_islemleri.py",
    ):
        agac = ast.parse((kok / ad).read_text(encoding="utf-8"))
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.ImportFrom):
                assert "finans" not in (dugum.module or ""), (ad, dugum.lineno)
            elif isinstance(dugum, ast.Import):
                for takma in dugum.names:
                    assert "finans" not in takma.name, (ad, dugum.lineno)


def test_veritabani_butunlugu_akis_sonrasi_temiz(ortam: Ortam, env: Envanter) -> None:
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    _raf(ortam, env, kaynak, "B2")
    [talep_id] = _denetle(ortam, kaynak)
    _karar(ortam, talep_id, Karar.AYNI)
    with ortam.veritabani.islem() as o:
        assert o.execute(text("PRAGMA foreign_key_check")).all() == []
        assert o.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"


# --- 2026-09-20 beşinci turu: köken devri, toplu tarama, şart kapıları ----------------


def _iki_rafli_bagimsiz_soru(ortam: Ortam, env: Envanter) -> tuple[int, int, int, int]:
    """Paketli ama bağımsız kökenli bir soru ve altında eşleşecek iki raf.

    ``_uc_esit_depo_paketsiz`` + ``_n3_n2_birlestir`` zinciri, tarihsel açılış
    paketi dolu olduğu hâlde bağımsız kökenli bir halef soru bırakır (üçüncü tur
    testleri). Raflar birleşmeden **sonra** eklenir ki ilk birleşmenin zincirleme
    denetimi onları görmesin; eşleşme ikinci karardan doğsun.
    """
    n1, n2, n3, _ = _uc_esit_depo_paketsiz(ortam, env)
    p = _paket(ortam)
    _n3_n2_birlestir(ortam, env, n2, n3, p)
    [(halef, kaynak_ucu, hedef_ucu)] = _acik_talepler(ortam)
    assert (kaynak_ucu, hedef_ucu) == (n2, n1)
    assert _koken(ortam, halef) == (TalepDurumu.ACIK.value, p, True)
    r1 = _raf(ortam, env, n1, "A1", seri_no="SN")
    r2 = _raf(ortam, env, n2, "A2", seri_no="SN")
    _sart(ortam, r1, ["seri_no"])
    _sart(ortam, r2, ["seri_no"])
    return p, halef, r1, r2


@pytest.mark.parametrize("once_iptal", [False, True])
def test_bagimsiz_koken_zincirleme_soruya_da_gecer(
    ortam: Ortam, env: Envanter, once_iptal: bool
) -> None:
    """Bağımsız bir sorunun kararından doğan alt soru da bağımsızdır.

    Devir olmadan sonuç, paketin karardan önce mi sonra mı iptal edildiğine
    bağlıydı: karardan **sonra** iptalde alt soru pakete ait sayılıp cevapsız
    ``gecersiz`` oluyor, karardan **önce** iptalde bağımsız doğup açık
    kalıyordu. Aynı soru, aynı karar, iki farklı sonuç. İki sıra da artık aynı
    sonucu verir.
    """
    p, halef, r1, r2 = _iki_rafli_bagimsiz_soru(ortam, env)
    if once_iptal:
        _iptal_et(ortam, p)

    sonuc = _karar(ortam, halef, Karar.AYNI)
    [alt] = sonuc.yeni_talepler
    assert (alt.hedef_nesne_id, alt.kaynak_nesne_id) == (min(r1, r2), max(r1, r2))

    if not once_iptal:
        _iptal_et(ortam, p)

    durum, _acilis, koken = _koken(ortam, alt.id)
    assert durum == TalepDurumu.ACIK.value
    assert koken is True
    assert _karar(ortam, alt.id, Karar.AYRI).cozuldu  # hâlâ cevaplanabilir
    _butunluk_temiz(ortam)


def _iki_adayli_paket(ortam: Ortam, env: Envanter) -> int:
    """İkisi de mevcut birer kesin nesneyle eşleşen iki adaylı çalışan paket."""
    for deger in ("X1", "X2"):
        _sart(ortam, _depo(ortam, env, harici_kimlik=deger), ["harici_kimlik"])
    paket_id = _paket(ortam)
    for ad, deger in (("A", "X1"), ("B", "X2")):
        _aday(
            ortam,
            paket_id,
            env.depo_id,
            {"ad": ad, "harici_kimlik": deger},
            ["harici_kimlik"],
        )
    return paket_id


def test_toplu_aday_taramasi_butun_adaylari_tarar(ortam: Ortam, env: Envanter) -> None:
    paket_id = _iki_adayli_paket(ortam, env)
    with ortam.veritabani.islem() as o:
        talepler = mu.paketin_adaylarini_denetle(o, paket_id, KULLANICI)
    assert len(talepler) == 2
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value
    _butunluk_temiz(ortam)


def test_toplu_aday_taramasi_duserse_ilk_adayin_yazmalari_da_kalmaz(
    ortam: Ortam, env: Envanter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tekil tarama üçüncü turda atomik yapılmıştı; onu çağıran toplu işlev
    değildi. İkinci aday düşerse ilkinin talepleri, denetim izleri ve paketin
    ``bekliyor`` durumu da kalmaz — çağıran hatayı yutup commit etse bile."""
    paket_id = _iki_adayli_paket(ortam, env)
    onceki_olaylar = _olaylar(ortam)
    gercek = mu.adayi_denetle
    sayac = 0

    def ikincide_patla(
        oturum: Session, aday_nesne_id: int, aktor: Aktor
    ) -> list[mt.KararTalebi]:
        nonlocal sayac
        sayac += 1
        if sayac == 2:
            raise EnjekteHata("ikinci aday taranırken")
        return gercek(oturum, aday_nesne_id, aktor)

    with ortam.veritabani.islem() as o:
        monkeypatch.setattr(mu, "adayi_denetle", ikincide_patla)
        with pytest.raises(EnjekteHata):
            mu.paketin_adaylarini_denetle(o, paket_id, KULLANICI)
        monkeypatch.undo()
    # dış transaction commit edildi; kalıcı durum yeni oturumdan okunur

    assert sayac == 2
    assert _sayi(ortam, mt.KARAR_TALEBI) == 0
    assert _olaylar(ortam) == onceki_olaylar
    assert _paket_durumu(ortam, paket_id) == CALISIYOR.value
    _butunluk_temiz(ortam)


def test_bekleyen_paketler_acik_sorusu_olani_verir(ortam: Ortam, env: Envanter) -> None:
    bos = _paket(ortam)
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    bekleyen = _paket(ortam)
    [talep] = _denetle(ortam, kaynak, bekleyen)

    with ortam.veritabani.islem() as o:
        assert [p.id for p in mu.bekleyen_paketler(o)] == [bekleyen]

    _karar(ortam, talep, Karar.AYRI)
    with ortam.veritabani.islem() as o:
        assert mu.bekleyen_paketler(o) == []
    assert _paket_durumu(ortam, bos) == CALISIYOR.value


def test_aday_sarti_yalniz_calisiyor_pakette_secilir(
    ortam: Ortam, env: Envanter
) -> None:
    """Aday şartı aday veridir (aday nesneyle birlikte silinir), dolayısıyla
    taslak yazma kapısına tabidir: bekleyen ve terminal iptal pakette yazılamaz.
    Şart kaldırma işlevi olmadığı için böyle bir satır orada kalıcı olurdu."""
    _sart(ortam, _depo(ortam, env, harici_kimlik="X1"), ["harici_kimlik"])
    paket_id = _paket(ortam)
    aday = _aday(
        ortam,
        paket_id,
        env.depo_id,
        {"ad": "A", "harici_kimlik": "X1"},
        ["harici_kimlik"],
    )
    _adayi_denetle(ortam, aday)
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value
    with ortam.veritabani.islem() as o:
        with pytest.raises(tsi.PaketDurumuGecersiz):
            mu.aday_sarti_ekle(o, aday, ["sehir"], KULLANICI)

    _iptal_et(ortam, paket_id)
    with ortam.veritabani.islem() as o:
        with pytest.raises(tsi.PaketDurumuGecersiz):
            mu.aday_sarti_ekle(o, aday, ["sehir"], KULLANICI)

    assert _sayi(ortam, mt.ADAY_NESNE_MUKERRERLIK_SARTI) == 1
    _butunluk_temiz(ortam)


def test_birlesmis_nesneye_sart_secilemez_koruma_tek_yonlu_kalmaz(
    ortam: Ortam, env: Envanter
) -> None:
    """Şart birleşmiş nesnede kalırsa tarama tek yönlü olurdu: taranan uç kendi
    kimlik geçmişinin şartlarını kullanır, ama karşı ucun şartı kanonik nesne
    üzerinden aranır. Kanonik nesneye seçilince koruma iki yönlü çalışır."""
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    [talep] = _denetle(ortam, kaynak)
    _karar(ortam, talep, Karar.AYNI)

    with ortam.veritabani.islem() as o:
        assert mu.kanonik_nesneyi_bul(o, kaynak) == hedef
        with pytest.raises(mu.NesneBirlesmis):
            mu.nesne_sarti_ekle(o, kaynak, ["sehir"], KULLANICI)
    assert _sayi(ortam, mt.NESNE_MUKERRERLIK_SARTI) == 1

    with ortam.veritabani.islem() as o:
        ni.ozellik_yaz(o, hedef, "sehir", "Edirne")
    _sart(ortam, hedef, ["sehir"])
    sartsiz_yeni = _depo(ortam, env, sehir="Edirne")
    assert len(_denetle(ortam, sartsiz_yeni)) == 1  # şartsız uç korumadan kaçamaz
    _butunluk_temiz(ortam)


# --- 2026-09-20 altıncı turu: köken devri (mevcut soru), şart kaynağı, sorgu adı -----


def test_bagimsiz_koken_mevcut_acik_alt_soruya_da_gecer(
    ortam: Ortam, env: Envanter
) -> None:
    """Alt soru daha önce **başka bir paket** tarafından açılmışsa da köken geçer.

    Beşinci turda devir yalnız zincirleme denetimin **yeni açtığı** taleplere
    uygulanıyordu. Alt soru zaten açıksa tarama onu yeniden soruyor ama kökenini
    almıyordu; bütün paketler iptal edilince soru cevapsız ``gecersiz`` oluyordu.
    ``_kanonik_soruyu_koru`` aynı durumda kökeni mevcut açık halefe zaten
    devrediyordu; kural iki yerde de aynı olmalı.
    """
    p, halef, _r1, r2 = _iki_rafli_bagimsiz_soru(ortam, env)
    p2 = _paket(ortam)
    [alt] = _denetle(ortam, r2, p2)  # alt soru ÖNCE başka paketten açılır
    assert _koken(ortam, alt) == (TalepDurumu.ACIK.value, p2, False)

    sonuc = _karar(ortam, halef, Karar.AYNI)
    assert sonuc.yeni_talepler == ()  # soru zaten vardı, yenisi açılmadı
    assert _koken(ortam, alt)[2] is True  # köken yine de devredildi

    _iptal_et(ortam, p)
    _iptal_et(ortam, p2)
    assert _talep_durumu(ortam, alt) == TalepDurumu.ACIK.value
    assert _karar(ortam, alt, Karar.AYRI).cozuldu  # hâlâ cevaplanabilir
    _butunluk_temiz(ortam)


def test_paket_kaynakli_karar_mevcut_soruya_koken_yazmaz(
    ortam: Ortam, env: Envanter
) -> None:
    """Devir yalnız bağımsız kökenli karardan olur; paket kaynaklı karar mevcut
    soruyu bağımsız yapmaz (aksi hâlde koruma gereğinden geniş olurdu)."""
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    r1 = _raf(ortam, env, hedef, "A1", seri_no="SN")
    r2 = _raf(ortam, env, kaynak, "A2", seri_no="SN")
    _sart(ortam, r1, ["seri_no"])
    _sart(ortam, r2, ["seri_no"])
    p1, p2 = _paket(ortam), _paket(ortam)
    [ust] = _denetle(ortam, kaynak, p1)
    [alt] = _denetle(ortam, r2, p2)

    _karar(ortam, ust, Karar.AYNI)
    assert _koken(ortam, alt)[2] is False

    _iptal_et(ortam, p1)
    _iptal_et(ortam, p2)
    assert _talep_durumu(ortam, alt) == TalepDurumu.GECERSIZ.value
    _butunluk_temiz(ortam)


@pytest.mark.parametrize("aktor", [AJAN, Aktor(AktorTuru.SISTEM, "test-sistem")])
def test_mukerrerlik_sartini_yalniz_kullanici_secer(
    ortam: Ortam, env: Envanter, aktor: Aktor
) -> None:
    """Sözlük ve modül açıklaması şartı kullanıcının seçtiğini söylüyordu; kod
    aktör türüne bakmıyordu. Şart geri alınamadığı için yanlış seçim kalıcı bir
    yanlış şüphe kaynağı olurdu. Reddedilen çağrı hiçbir şey yazmaz."""
    depo = _depo(ortam, env, harici_kimlik="X1")
    paket_id = _paket(ortam)
    with ortam.veritabani.islem() as o:
        aday = tsi.aday_nesne_ekle(o, paket_id, env.depo_id, {"ad": "A"}).id
    onceki_olaylar = _olaylar(ortam)

    with ortam.veritabani.islem() as o:
        with pytest.raises(mu.SartKaynagiGecersiz):
            mu.nesne_sarti_ekle(o, depo, ["harici_kimlik"], aktor)
        with pytest.raises(mu.SartKaynagiGecersiz):
            mu.aday_sarti_ekle(o, aday, ["harici_kimlik"], aktor)

    assert _sayi(ortam, mt.NESNE_MUKERRERLIK_SARTI) == 0
    assert _sayi(ortam, mt.ADAY_NESNE_MUKERRERLIK_SARTI) == 0
    assert _olaylar(ortam) == onceki_olaylar
    # aynı şartı kullanıcı seçebilir
    _sart(ortam, depo, ["harici_kimlik"])
    assert _sayi(ortam, mt.NESNE_MUKERRERLIK_SARTI) == 1


def test_ajan_sart_secemez_ama_tarayip_suphe_acabilir(
    ortam: Ortam, env: Envanter
) -> None:
    """Kapı taramayı kısıtlamaz: ajan şüphe açar, kullanıcı karar verir."""
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    with ortam.veritabani.islem() as o:
        [talep] = mu.nesneyi_denetle(o, kaynak, AJAN)
        assert talep.acan_aktor_turu == AktorTuru.AJAN.value
        with pytest.raises(mu.KararKaynagiGecersiz):
            mu.karar_ver(o, talep.id, Karar.AYNI, AJAN)
        talep_id = talep.id
    assert _karar(ortam, talep_id, Karar.AYNI).cozuldu


def test_paket_yalniz_acik_soru_yuzunden_bekler(ortam: Ortam, env: Envanter) -> None:
    """``bekliyor`` tek anlamlıdır (karar 2026-09-20).

    Önceden ``paketi_beklet`` sebepsiz çağrılabiliyordu ve
    ``_paket_durumunu_esitle`` iki bekleme nedenini ayırt edemediği için
    eşleşmesiz bir tarama bile paketi kendiliğinden ``calisiyor`` yapıyordu.
    Artık sebepsiz bekletme reddedilir; soru varken bekleme kurulur, soru
    çözülünce kalkar.
    """
    bos = _paket(ortam)
    with ortam.veritabani.islem() as o:
        with pytest.raises(tsi.PaketDurumuGecersiz, match="Elle duraklatma yoktur"):
            tsi.paketi_beklet(o, bos)
    assert _paket_durumu(ortam, bos) == CALISIYOR.value

    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    soruyla = _paket(ortam)
    [talep] = _denetle(ortam, kaynak, soruyla)
    assert _paket_durumu(ortam, soruyla) == BEKLIYOR.value

    with ortam.veritabani.islem() as o:
        assert [p.id for p in mu.bekleyen_paketler(o)] == [soruyla]

    _karar(ortam, talep, Karar.AYRI)
    assert _paket_durumu(ortam, soruyla) == CALISIYOR.value
    with ortam.veritabani.islem() as o:
        assert mu.bekleyen_paketler(o) == []


def test_eslesmesiz_tarama_bekleyen_paketi_calistirmaz(
    ortam: Ortam, env: Envanter
) -> None:
    """Açık sorusu olan paket, başka bir nesnenin eşleşmesiz taramasıyla
    kendiliğinden çalışmaya dönmez."""
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    paket_id = _paket(ortam)
    [talep] = _denetle(ortam, kaynak, paket_id)
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value

    yalniz = _depo(ortam, env, harici_kimlik="Z9")  # hiçbir şeyle eşleşmez
    assert _denetle(ortam, yalniz, paket_id) == []
    assert _paket_durumu(ortam, paket_id) == BEKLIYOR.value  # soru hâlâ açık

    _karar(ortam, talep, Karar.AYNI)
    assert _paket_durumu(ortam, paket_id) == CALISIYOR.value
    _butunluk_temiz(ortam)


@pytest.mark.parametrize("adayli", [False, True])
def test_toplu_tarama_iptal_paketi_her_durumda_reddeder(
    ortam: Ortam, env: Envanter, adayli: bool
) -> None:
    """Aynı geçersiz durum iki farklı davranış üretmemeli: önceden adayı olan
    iptal paket hata veriyor, boş iptal paket sessizce ``[]`` dönüyordu."""
    paket_id = _paket(ortam)
    if adayli:
        _aday(ortam, paket_id, env.depo_id, {"ad": "A"})
    _iptal_et(ortam, paket_id)
    with ortam.veritabani.islem() as o:
        with pytest.raises(tsi.PaketDurumuGecersiz):
            mu.paketin_adaylarini_denetle(o, paket_id, KULLANICI)


def test_denetim_izinde_talep_acildi_yalniz_gercek_acilisi_anlatir(
    ortam: Ortam, env: Envanter
) -> None:
    """Köken devri ve paket bağlama artık kendi adlarıyla yazılır (göç ``0012``).

    Üçü de ``karar_talebi_acildi`` yazdığı sürece denetim izinden "kaç karar
    talebi açıldı" diye saymak yanlış sonuç veriyordu; altıncı tur köken
    devrini mevcut açık sorulara da uygulayınca sapma büyüdü.
    """
    _p, halef, _r1, r2 = _iki_rafli_bagimsiz_soru(ortam, env)
    p2 = _paket(ortam)
    [alt] = _denetle(ortam, r2, p2)
    talep_once = _sayi(ortam, mt.KARAR_TALEBI)
    once = _olaylar(ortam)  # kurulumdaki birleşme de köken devretmişti

    _karar(ortam, halef, Karar.AYNI)  # yeni talep açılmaz: köken devri + paket bağı

    eklenen = _olaylar(ortam)[len(once) :]
    assert _sayi(ortam, mt.KARAR_TALEBI) == talep_once
    assert DenetimOlayi.KARAR_TALEBI_ACILDI.value not in eklenen
    assert eklenen.count(DenetimOlayi.KARAR_TALEBI_KOKENI_DEVREDILDI.value) == 1
    assert eklenen.count(DenetimOlayi.KARAR_TALEBI_PAKETE_BAGLANDI.value) == 1
    assert _koken(ortam, alt)[2] is True
    _butunluk_temiz(ortam)


def test_acilan_talep_sayisi_denetim_izinden_dogru_sayilir(
    ortam: Ortam, env: Envanter
) -> None:
    """İki paket aynı soruyu sorarsa talep bir tanedir; iz de bir açılış der."""
    hedef = _depo(ortam, env, harici_kimlik="X1")
    _sart(ortam, hedef, ["harici_kimlik"])
    kaynak = _depo(ortam, env, harici_kimlik="X1")
    p1, p2 = _paket(ortam), _paket(ortam)
    [talep] = _denetle(ortam, kaynak, p1)
    assert _denetle(ortam, kaynak, p2) == []  # aynı soru, ikinci talep yok

    olaylar = _olaylar(ortam)
    assert _sayi(ortam, mt.KARAR_TALEBI) == 1
    assert olaylar.count(DenetimOlayi.KARAR_TALEBI_ACILDI.value) == 1
    assert olaylar.count(DenetimOlayi.KARAR_TALEBI_PAKETE_BAGLANDI.value) == 1
    assert _talep_durumu(ortam, talep) == TalepDurumu.ACIK.value


# --- birleşmede kesin kayıt bağları (Aşama 4.7/4) -------------------------------------


def _kesin_kayit(
    ortam: Ortam, env: Envanter, paket_id: int, nesneler: list[int]
) -> int:
    with ortam.veritabani.islem() as o:
        return ki.kayit_olustur(
            o, paket_id, env.sayim_id, {"adet": 1}, nesneler, KULLANICI
        ).id


def test_birlesmede_kayit_baglari_kanonige_tasinir(ortam: Ortam, env: Envanter) -> None:
    """Birleşen nesne ``kapali`` olur; kayıtları orada kalsaydı kullanılmayan
    bir kimliğe asılı kalırdı. Kayıtların kendisi değişmez, bağın ucu değişir."""
    depo = _depo(ortam, env)
    raf = _raf(ortam, env, depo, "A1")
    hedef = _urun(ortam, env, [raf], barkod="B1", agirlik=Decimal("1.0"))
    _sart(ortam, hedef, ["agirlik"])
    kaynak = _urun(ortam, env, [raf], barkod="B2", agirlik=Decimal("1.00"))
    paket_id = _paket(ortam)
    kayit_id = _kesin_kayit(ortam, env, paket_id, [kaynak])

    [talep_id] = _denetle(ortam, kaynak)
    _karar(ortam, talep_id, Karar.AYNI)

    with ortam.veritabani.islem() as o:
        assert ki.kaydin_nesneleri(o, kayit_id) == [hedef]
        assert [k.id for k in ki.nesnenin_kayitlari(o, hedef)] == [kayit_id]
        assert ki.nesnenin_kayitlari(o, kaynak) == []
        # kaydın kendisi değişmedi: kökeni hâlâ kendi paketi
        assert ki.kaydin_kokeni(o, kayit_id).islem_paketi.id == paket_id
        olaylar = [iz.olay for iz in di.olaylari_listele(o, nesne_id=hedef)]
    assert DenetimOlayi.KAYIT_BAGLARI_DEVREDILDI.value in olaylar


def test_iki_uca_bagli_kayit_birlesmede_tek_satir_kalir(
    ortam: Ortam, env: Envanter
) -> None:
    """Aynı kayıt hem hedefe hem kaynağa bağlıysa hedefte ikinci satır
    yazılmaz; bağ rolsüzdür ve bir kez bulunur."""
    depo = _depo(ortam, env)
    raf = _raf(ortam, env, depo, "A1")
    hedef = _urun(ortam, env, [raf], barkod="B1", agirlik=Decimal("1.0"))
    _sart(ortam, hedef, ["agirlik"])
    kaynak = _urun(ortam, env, [raf], barkod="B2", agirlik=Decimal("1.00"))
    paket_id = _paket(ortam)
    kayit_id = _kesin_kayit(ortam, env, paket_id, [hedef, kaynak])

    [talep_id] = _denetle(ortam, kaynak)
    _karar(ortam, talep_id, Karar.AYNI)

    with ortam.veritabani.islem() as o:
        assert ki.kaydin_nesneleri(o, kayit_id) == [hedef]
    assert _sayi(ortam, "kayit_nesne") == 1


def test_birlestirme_geri_alinirsa_kayit_baglari_da_geri_alinir(
    ortam: Ortam, env: Envanter
) -> None:
    """Hiyerarşi ihlali birleşmeyi düşürünce kayıt bağı da yerinde kalır:
    devir birleşmenin atomik bütününün parçasıdır."""
    depo = _depo(ortam, env)
    r1 = _raf(ortam, env, depo, "A1")
    r2 = _raf(ortam, env, depo, "A2")
    r3 = _raf(ortam, env, depo, "A3")
    hedef = _urun(ortam, env, [r1, r2], barkod="B1", agirlik=Decimal("2"))
    _sart(ortam, hedef, ["agirlik"])
    kaynak = _urun(ortam, env, [r3], barkod="B2", agirlik=Decimal("2.0"))
    paket_id = _paket(ortam)
    kayit_id = _kesin_kayit(ortam, env, paket_id, [kaynak])

    [talep_id] = _denetle(ortam, kaynak)
    with pytest.raises(ni.HiyerarsiIhlali):
        _karar(ortam, talep_id, Karar.AYNI)

    with ortam.veritabani.islem() as o:
        assert ki.kaydin_nesneleri(o, kayit_id) == [kaynak]
        assert ki.nesnenin_kayitlari(o, hedef) == []
        olaylar = [iz.olay for iz in di.olaylari_listele(o, nesne_id=hedef)]
        assert DenetimOlayi.KAYIT_BAGLARI_DEVREDILDI.value not in olaylar
    assert _sayi(ortam, "kayit_nesne") == 1
