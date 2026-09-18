"""Nesne motoru testleri (Aşama 4.3).

Gerçek SQLite dosyası, ``test`` ortamı, ``tmp_path`` altında kök; şema gerçek
göç zinciriyle kurulur. Tanım paketi finans dışı sahte ``ENVANTER`` dünyasıdır:
``DEPO``, ``BOLGE``, ``RAF``, ``URUN`` türleri; ``DEPODA`` (raf → depo, tam bir
etkin üst), ``BOLGEDE`` (raf → bölge, isteğe bağlı, en çok bir), ``RAFTA``
(ürün → raf, bir ila iki etkin üst) hiyerarşik, ``BENZER`` (ürün → ürün)
hiyerarşik olmayan ilişkiler. Çekirdek bunların anlamını bilmez; bütün sayılar
ve kurallar tanım verisidir.

İki düzey sınanır: uygulama sözleşmesi (``nesne_islemleri`` hataları) ve
veritabanı kısıtları (servisi atlayan ham SQL ile aynı ihlal ``IntegrityError``
verir).
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from defteriki import ayarlar as ay
from defteriki.cekirdek import gocler
from defteriki.cekirdek import nesne_islemleri as ni
from defteriki.cekirdek import nesne_tablolari as nt
from defteriki.cekirdek import tanim_islemleri as ti
from defteriki.cekirdek import tanim_tablolari as tt
from defteriki.cekirdek import veritabani as vt
from defteriki.cekirdek.tanim_tablolari import DegerTuru, YasamDurumu

DEFTERIKI_DEGISKENLERI = (
    ay.ORTAM_DEGISKENI,
    ay.VERI_KOKU_DEGISKENI,
    ay.VERITABANI_YOLU_DEGISKENI,
    ay.BELGE_DIZINI_DEGISKENI,
    ay.LOG_DIZINI_DEGISKENI,
    ay.GELEN_DIZINI_DEGISKENI,
)
ETKIN = YasamDurumu.ETKIN
KAPALI = YasamDurumu.KAPALI


@pytest.fixture(autouse=True)
def temiz_cevre(monkeypatch: pytest.MonkeyPatch) -> None:
    for degisken in DEFTERIKI_DEGISKENLERI:
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
    gocler.semayi_yukselt(v)
    yield v
    v.kapat()


@dataclass(frozen=True, slots=True)
class Envanter:
    """``ENVANTER`` paketinin sürüm 1 kimlikleri."""

    paket_id: int
    surum_id: int
    depo_id: int
    bolge_id: int
    raf_id: int
    urun_id: int
    depoda_id: int
    bolgede_id: int
    rafta_id: int
    benzer_id: int


@pytest.fixture
def env(veritabani: vt.Veritabani) -> Envanter:
    with veritabani.islem() as o:
        paket = ti.paket_tanimla(o, "ENVANTER", "Envanter")
        surum = ti.surum_tanimla(o, paket.id, 1)
        depo = ti.nesne_turu_tanimla(o, surum.id, "DEPO", "Depo")
        bolge = ti.nesne_turu_tanimla(o, surum.id, "BOLGE", "Bölge")
        raf = ti.nesne_turu_tanimla(o, surum.id, "RAF", "Raf")
        urun = ti.nesne_turu_tanimla(o, surum.id, "URUN", "Ürün")
        ti.ozellik_tanimla(o, depo.id, "ad", "Ad", DegerTuru.METIN, zorunlu=True)
        ti.ozellik_tanimla(o, bolge.id, "ad", "Ad", DegerTuru.METIN, zorunlu=True)
        ti.ozellik_tanimla(o, raf.id, "kod", "Kod", DegerTuru.METIN, zorunlu=True)
        ti.ozellik_tanimla(o, raf.id, "kapasite", "Kapasite", DegerTuru.TAM_SAYI)
        ti.ozellik_tanimla(
            o, urun.id, "barkod", "Barkod", DegerTuru.METIN, zorunlu=True
        )
        ti.ozellik_tanimla(o, urun.id, "agirlik", "Ağırlık", DegerTuru.ONDALIK)
        ti.ozellik_tanimla(o, urun.id, "kirilgan", "Kırılgan", DegerTuru.MANTIKSAL)
        ti.ozellik_tanimla(o, urun.id, "not_", "Not", DegerTuru.METIN)
        depoda = ti.iliski_tanimla(o, surum.id, "DEPODA", "Depoda", raf.id, depo.id)
        bolgede = ti.iliski_tanimla(o, surum.id, "BOLGEDE", "Bölgede", raf.id, bolge.id)
        rafta = ti.iliski_tanimla(o, surum.id, "RAFTA", "Rafta", urun.id, raf.id)
        benzer = ti.iliski_tanimla(o, surum.id, "BENZER", "Benzer", urun.id, urun.id)
        ti.hiyerarsi_kurali_tanimla(o, depoda.id, 1, 1, ETKIN)
        ti.hiyerarsi_kurali_tanimla(o, bolgede.id, 0, 1, None)
        ti.hiyerarsi_kurali_tanimla(o, rafta.id, 1, 2, ETKIN)
        return Envanter(
            paket.id,
            surum.id,
            depo.id,
            bolge.id,
            raf.id,
            urun.id,
            depoda.id,
            bolgede.id,
            rafta.id,
            benzer.id,
        )


def _sayi(v: vt.Veritabani, tablo: str) -> int:
    with v.islem() as o:
        return int(o.execute(text(f"SELECT count(*) FROM {tablo}")).scalar_one())


def _depo(v: vt.Veritabani, env: Envanter, ad: str = "Merkez") -> int:
    with v.islem() as o:
        return ni.nesne_olustur(o, env.depo_id, {"ad": ad}).id


def _raf(v: vt.Veritabani, env: Envanter, depo_id: int, kod: str = "A1") -> int:
    with v.islem() as o:
        return ni.nesne_olustur(
            o, env.raf_id, {"kod": kod}, [ni.UstBaglanti(env.depoda_id, depo_id)]
        ).id


def _urun(
    v: vt.Veritabani, env: Envanter, raf_idleri: list[int], barkod: str = "X1"
) -> int:
    with v.islem() as o:
        return ni.nesne_olustur(
            o,
            env.urun_id,
            {"barkod": barkod},
            [ni.UstBaglanti(env.rafta_id, r) for r in raf_idleri],
        ).id


def _durum(v: vt.Veritabani, nesne_id: int) -> str:
    with v.islem() as o:
        return ni.nesne_getir(o, nesne_id).yasam_durumu


# --- nesne ---------------------------------------------------------------------------


def test_gecerli_turle_nesne_olusturulur(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    with veritabani.islem() as o:
        nesne = ni.nesne_olustur(o, env.depo_id, {"ad": "Merkez"})

    with veritabani.islem() as o:
        bulunan = ni.nesne_getir(o, nesne.id)
        assert bulunan.nesne_turu_id == env.depo_id
        assert bulunan.tanim_surumu_id == env.surum_id  # üretildiği sürüm kalıcı
        assert bulunan.yasam_durumu == ETKIN.value
        assert bulunan.olusturma_zamani.tzinfo is None
        assert [n.id for n in ni.nesneleri_listele(o, env.depo_id)] == [nesne.id]
        assert ni.ozellikleri_oku(o, nesne.id) == {"ad": "Merkez"}


def test_olmayan_tur_reddedilir(veritabani: vt.Veritabani, env: Envanter) -> None:
    with pytest.raises(ti.TanimBulunamadi, match="nesne türü bulunamadı"):
        with veritabani.islem() as o:
            ni.nesne_olustur(o, 999, {"ad": "x"})
    assert _sayi(veritabani, nt.NESNE) == 0


def test_olmayan_nesne_bulunamaz(veritabani: vt.Veritabani, env: Envanter) -> None:
    with veritabani.islem() as o:
        with pytest.raises(ni.NesneBulunamadi):
            ni.nesne_getir(o, 999)
        with pytest.raises(ni.NesneBulunamadi):
            ni.ozellikleri_oku(o, 999)
        with pytest.raises(ni.NesneBulunamadi):
            ni.iliskileri_listele(o, 999)
        with pytest.raises(ni.NesneBulunamadi):
            ni.iliski_kaldir(o, 999)


def test_tur_ve_surum_uyusmazligi_veritabaninda_reddedilir(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    """Nesnenin türü gerçekten bağlı olduğu sürüme ait olmalı (bileşik FK)."""
    with veritabani.islem() as o:
        surum2 = ti.surum_tanimla(o, env.paket_id, 2)
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with veritabani.islem() as o:
            o.execute(
                text(
                    "INSERT INTO nesne (nesne_turu_id, tanim_surumu_id, yasam_durumu, "
                    "olusturma_zamani) VALUES (:tur, :surum, 'etkin', '2026-09-18')"
                ),
                {"tur": env.depo_id, "surum": surum2.id},
            )
    assert _sayi(veritabani, nt.NESNE) == 0


# --- özellik --------------------------------------------------------------------------


def test_dort_deger_turu_yazilir_ve_ayni_degerle_okunur(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    raf = _raf(veritabani, env, depo)
    with veritabani.islem() as o:
        urun = ni.nesne_olustur(
            o,
            env.urun_id,
            {
                "barkod": "869",
                "agirlik": Decimal("12.50"),
                "kirilgan": False,
                "not_": "",
            },
            [ni.UstBaglanti(env.rafta_id, raf)],
        )
        ni.ozellik_yaz(o, raf, "kapasite", 40)

    with veritabani.islem() as o:
        degerler = ni.ozellikleri_oku(o, urun.id)
        assert degerler == {
            "barkod": "869",
            "agirlik": Decimal("12.50"),
            "kirilgan": False,
            "not_": "",
        }
        assert type(degerler["kirilgan"]) is bool
        assert str(degerler["agirlik"]) == "12.50"  # kesinlik ve ölçek korunur
        raf_degerleri = ni.ozellikleri_oku(o, raf)
        assert raf_degerleri == {"kod": "A1", "kapasite": 40}
        assert type(raf_degerleri["kapasite"]) is int
        ham = (
            o.execute(
                text(
                    "SELECT deger FROM nesne_ozelligi WHERE nesne_id = :n ORDER BY id"
                ),
                {"n": urun.id},
            )
            .scalars()
            .all()
        )
        assert ham == ["869", "12.50", "0", ""]  # kanonik metin


def test_baska_turun_ozelligi_reddedilir(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    with pytest.raises(ni.GecersizOzellik, match="'barkod' adlı özellik tanımı yok"):
        with veritabani.islem() as o:
            ni.ozellik_yaz(o, depo, "barkod", "x")
    with pytest.raises(ni.GecersizOzellik, match="'barkod'"):
        with veritabani.islem() as o:
            ni.nesne_olustur(o, env.depo_id, {"ad": "İkinci", "barkod": "x"})
    assert _sayi(veritabani, nt.NESNE) == 1


def test_baska_turun_ozelligi_veritabaninda_da_reddedilir(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    """Bileşik FK: (özellik tanımı, tür) çifti ozellik_tanimi'nde birlikte olmalı."""
    depo = _depo(veritabani, env)
    with veritabani.islem() as o:
        [barkod] = [
            t
            for t in ti.ozellik_tanimlarini_listele(o, env.urun_id)
            if t.kod == "barkod"
        ]
    ekle = text(
        "INSERT INTO nesne_ozelligi "
        "(nesne_id, nesne_turu_id, ozellik_tanimi_id, deger) "
        "VALUES (:n, :tur, :tanim, 'x')"
    )
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with veritabani.islem() as o:  # ürün özelliği, depo türüyle
            o.execute(ekle, {"n": depo, "tur": env.depo_id, "tanim": barkod.id})
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with veritabani.islem() as o:  # depo nesnesi, ürün türü diye yazılmış
            o.execute(ekle, {"n": depo, "tur": env.urun_id, "tanim": barkod.id})
    assert _sayi(veritabani, nt.NESNE_OZELLIGI) == 1  # yalnız 'ad'


def test_tanimsiz_ozellik_reddedilir(veritabani: vt.Veritabani, env: Envanter) -> None:
    depo = _depo(veritabani, env)
    with pytest.raises(ni.GecersizOzellik, match="'renk'"):
        with veritabani.islem() as o:
            ni.ozellik_yaz(o, depo, "renk", "mavi")


YANLIS_TIPLER: tuple[tuple[str, Any], ...] = (
    ("kapasite", "10"),
    ("kapasite", 1.5),
    ("kapasite", True),
    ("kapasite", Decimal("10")),
    ("kod", 5),
    ("kod", None),
)


@pytest.mark.parametrize(("kod", "deger"), YANLIS_TIPLER)
def test_yanlis_veri_tipi_reddedilir(
    veritabani: vt.Veritabani, env: Envanter, kod: str, deger: Any
) -> None:
    depo = _depo(veritabani, env)
    raf = _raf(veritabani, env, depo)
    with pytest.raises(ni.OzellikTuruUyusmuyor, match=f"özellik '{kod}'"):
        with veritabani.islem() as o:
            ni.ozellik_yaz(o, raf, kod, deger)
    with veritabani.islem() as o:
        assert ni.ozellikleri_oku(o, raf) == {"kod": "A1"}


URUN_YANLIS_TIPLER: tuple[tuple[str, Any], ...] = (
    ("kirilgan", 1),
    ("kirilgan", "1"),
    ("agirlik", 1.5),
    ("agirlik", "1.5"),
    ("agirlik", 1),
    ("agirlik", Decimal("NaN")),
    ("agirlik", Decimal("Infinity")),
)


@pytest.mark.parametrize(("kod", "deger"), URUN_YANLIS_TIPLER)
def test_mantiksal_ve_ondalik_yanlis_tip_reddedilir(
    veritabani: vt.Veritabani, env: Envanter, kod: str, deger: Any
) -> None:
    depo = _depo(veritabani, env)
    raf = _raf(veritabani, env, depo)
    with pytest.raises(ni.OzellikTuruUyusmuyor):
        with veritabani.islem() as o:
            ni.nesne_olustur(
                o,
                env.urun_id,
                {"barkod": "x", kod: deger},
                [ni.UstBaglanti(env.rafta_id, raf)],
            )
    assert _sayi(veritabani, nt.NESNE) == 2  # depo ve raf; ürün kalmadı


def test_zorunlu_ozellik_olmadan_nesne_olusturulamaz(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    with pytest.raises(ni.ZorunluOzellikEksik, match="zorunlu özellik eksik: ad"):
        with veritabani.islem() as o:
            ni.nesne_olustur(o, env.depo_id)
    with pytest.raises(ni.ZorunluOzellikEksik):
        with veritabani.islem() as o:
            ni.nesne_olustur(o, env.depo_id, {})
    assert _sayi(veritabani, nt.NESNE) == 0
    assert _sayi(veritabani, nt.NESNE_OZELLIGI) == 0


def test_istege_bagli_ozellik_olmayabilir(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    raf = _raf(veritabani, env, depo)  # kapasite verilmedi
    with veritabani.islem() as o:
        assert ni.ozellikleri_oku(o, raf) == {"kod": "A1"}


def test_ozellik_yazma_gunceller_cift_satir_olmaz(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    raf = _raf(veritabani, env, depo)
    with veritabani.islem() as o:
        ilk = ni.ozellik_yaz(o, raf, "kapasite", 10)
        ikinci = ni.ozellik_yaz(o, raf, "kapasite", 20)
        ucuncu = ni.ozellik_yaz(o, raf, "kod", "B7")  # zorunlu da güncellenir
    assert ilk.id == ikinci.id
    with veritabani.islem() as o:
        assert ni.ozellikleri_oku(o, raf) == {"kod": "B7", "kapasite": 20}
        assert ni.ozellikleri_oku(o, raf)["kod"] == "B7" and ucuncu.deger == "B7"
    assert _sayi(veritabani, nt.NESNE_OZELLIGI) == 3  # depo.ad, raf.kod, raf.kapasite


def test_ayni_ozellik_veritabaninda_iki_kez_yazilamaz(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    with veritabani.islem() as o:
        [ad] = ti.ozellik_tanimlarini_listele(o, env.depo_id)
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        with veritabani.islem() as o:
            o.execute(
                text(
                    "INSERT INTO nesne_ozelligi (nesne_id, nesne_turu_id, "
                    "ozellik_tanimi_id, deger) VALUES (:n, :tur, :tanim, 'kopya')"
                ),
                {"n": depo, "tur": env.depo_id, "tanim": ad.id},
            )
    assert _sayi(veritabani, nt.NESNE_OZELLIGI) == 1


def test_ozellik_silme_kurallari(veritabani: vt.Veritabani, env: Envanter) -> None:
    depo = _depo(veritabani, env)
    raf = _raf(veritabani, env, depo)
    with veritabani.islem() as o:
        ni.ozellik_yaz(o, raf, "kapasite", 10)
        ni.ozellik_sil(o, raf, "kapasite")
        assert ni.ozellikleri_oku(o, raf) == {"kod": "A1"}
    with pytest.raises(ni.GecersizOzellik, match="zorunlu"):
        with veritabani.islem() as o:
            ni.ozellik_sil(o, raf, "kod")
    with pytest.raises(ni.GecersizOzellik, match="yazılı değil"):
        with veritabani.islem() as o:
            ni.ozellik_sil(o, raf, "kapasite")
    with veritabani.islem() as o:
        assert ni.ozellikleri_oku(o, raf) == {"kod": "A1"}


# --- ilişki ---------------------------------------------------------------------------


def test_gecerli_iliski_kurulur_ve_listelenir(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    raf = _raf(veritabani, env, depo)
    with veritabani.islem() as o:
        [iliski] = ni.iliskileri_listele(o, raf)
        assert (
            iliski.iliski_tanimi_id,
            iliski.kaynak_nesne_id,
            iliski.hedef_nesne_id,
        ) == (
            env.depoda_id,
            raf,
            depo,
        )
        assert (
            iliski.tanim_surumu_id,
            iliski.kaynak_nesne_turu_id,
            iliski.hedef_nesne_turu_id,
        ) == (env.surum_id, env.raf_id, env.depo_id)
        assert [i.id for i in ni.iliskileri_listele(o, depo)] == [
            iliski.id
        ]  # hedef yönü


def test_hiyerarsik_olmayan_iliski_sayi_kurali_tasimaz(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    raf = _raf(veritabani, env, depo)
    a = _urun(veritabani, env, [raf], "A")
    b = _urun(veritabani, env, [raf], "B")
    c = _urun(veritabani, env, [raf], "C")
    with veritabani.islem() as o:
        ni.iliski_kur(o, env.benzer_id, a, b)
        ni.iliski_kur(o, env.benzer_id, a, c)
        ni.iliski_kur(o, env.benzer_id, b, a)  # ters yön ayrı satır
        assert (
            len(
                [
                    i
                    for i in ni.iliskileri_listele(o, a)
                    if i.iliski_tanimi_id == env.benzer_id
                ]
            )
            == 3
        )


def test_ters_tur_cifti_reddedilir(veritabani: vt.Veritabani, env: Envanter) -> None:
    depo = _depo(veritabani, env)
    raf = _raf(veritabani, env, depo)
    with pytest.raises(ni.GecersizIliski, match="kaynak nesne"):
        with veritabani.islem() as o:
            ni.iliski_kur(o, env.depoda_id, depo, raf)  # depo → raf: ters
    ekle = text(
        "INSERT INTO nesne_iliskisi (iliski_tanimi_id, tanim_surumu_id, "
        "kaynak_nesne_turu_id, hedef_nesne_turu_id, kaynak_nesne_id, hedef_nesne_id) "
        "VALUES (:iliski, :surum, :kt, :ht, :k, :h)"
    )
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with (
            veritabani.islem() as o
        ):  # türler tanımla uyumlu yazılmış ama nesneler ters
            o.execute(
                ekle,
                {
                    "iliski": env.depoda_id,
                    "surum": env.surum_id,
                    "kt": env.raf_id,
                    "ht": env.depo_id,
                    "k": depo,
                    "h": raf,
                },
            )
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with veritabani.islem() as o:  # türler ters yazılmış, tanımla uyuşmaz
            o.execute(
                ekle,
                {
                    "iliski": env.depoda_id,
                    "surum": env.surum_id,
                    "kt": env.depo_id,
                    "ht": env.raf_id,
                    "k": depo,
                    "h": raf,
                },
            )
    assert _sayi(veritabani, nt.NESNE_ILISKISI) == 1


def test_baska_surumdeki_iliski_tanimi_reddedilir(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    raf = _raf(veritabani, env, depo)
    with veritabani.islem() as o:
        surum2 = ti.surum_tanimla(o, env.paket_id, 2)
        raf2 = ti.nesne_turu_tanimla(o, surum2.id, "RAF", "Raf")
        depo2 = ti.nesne_turu_tanimla(o, surum2.id, "DEPO", "Depo")
        depoda2 = ti.iliski_tanimla(o, surum2.id, "DEPODA", "Depoda", raf2.id, depo2.id)
    with pytest.raises(ni.GecersizIliski, match="kaynak nesne"):
        with veritabani.islem() as o:
            ni.iliski_kur(o, depoda2.id, raf, depo)  # sürüm 1 nesneleri, sürüm 2 tanımı
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with veritabani.islem() as o:
            o.execute(
                text(
                    "INSERT INTO nesne_iliskisi (iliski_tanimi_id, tanim_surumu_id, "
                    "kaynak_nesne_turu_id, hedef_nesne_turu_id, kaynak_nesne_id, "
                    "hedef_nesne_id) VALUES (:iliski, :surum, :kt, :ht, :k, :h)"
                ),
                {
                    "iliski": depoda2.id,
                    "surum": surum2.id,
                    "kt": raf2.id,
                    "ht": depo2.id,
                    "k": raf,
                    "h": depo,
                },
            )
    assert _sayi(veritabani, nt.NESNE_ILISKISI) == 1


def test_ayni_iliski_mukerrer_yazilamaz(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    raf = _raf(veritabani, env, depo)
    a = _urun(veritabani, env, [raf], "A")
    b = _urun(veritabani, env, [raf], "B")
    with veritabani.islem() as o:
        ni.iliski_kur(o, env.benzer_id, a, b)
    with pytest.raises(ni.MukerrerIliski, match="zaten var"):
        with veritabani.islem() as o:
            ni.iliski_kur(o, env.benzer_id, a, b)
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        with veritabani.islem() as o:
            o.execute(
                text(
                    "INSERT INTO nesne_iliskisi (iliski_tanimi_id, tanim_surumu_id, "
                    "kaynak_nesne_turu_id, hedef_nesne_turu_id, kaynak_nesne_id, "
                    "hedef_nesne_id) VALUES (:iliski, :surum, :t, :t, :k, :h)"
                ),
                {
                    "iliski": env.benzer_id,
                    "surum": env.surum_id,
                    "t": env.urun_id,
                    "k": a,
                    "h": b,
                },
            )
    assert _sayi(veritabani, nt.NESNE_ILISKISI) == 4  # raf→depo, a→raf, b→raf, a→b


def test_hiyerarsik_olmayan_iliski_kendine_donebilir(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    """Genel ilişkide A → A'ya çekirdek karışmaz; anlamı domain'in işidir."""
    depo = _depo(veritabani, env)
    raf = _raf(veritabani, env, depo)
    a = _urun(veritabani, env, [raf], "A")
    with veritabani.islem() as o:
        satir = ni.iliski_kur(o, env.benzer_id, a, a)
        assert (satir.kaynak_nesne_id, satir.hedef_nesne_id) == (a, a)
    # Satır veritabanından geçti (0005: kontrol kısıtı yok); aynı satır ikinci kez
    # yazılamaz, mükerrerlik benzersizliği hâlâ korunur.
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        with veritabani.islem() as o:
            o.execute(
                text(
                    "INSERT INTO nesne_iliskisi (iliski_tanimi_id, tanim_surumu_id, "
                    "kaynak_nesne_turu_id, hedef_nesne_turu_id, kaynak_nesne_id, "
                    "hedef_nesne_id) VALUES (:iliski, :surum, :t, :t, :a, :a)"
                ),
                {
                    "iliski": env.benzer_id,
                    "surum": env.surum_id,
                    "t": env.urun_id,
                    "a": a,
                },
            )


@dataclass(frozen=True, slots=True)
class Dugumler:
    """Çevrim testleri için sürüm 2: tek tür ``DUGUM``, iki hiyerarşik ilişki."""

    surum_id: int
    dugum_id: int
    ustu_id: int
    """``USTU``: düğüm → düğüm, hiyerarşik (0..sınırsız)."""
    bagli_id: int
    """``BAGLI``: düğüm → düğüm, ayrı tanım, yine hiyerarşik (0..sınırsız)."""


@pytest.fixture
def dugumler(veritabani: vt.Veritabani, env: Envanter) -> Dugumler:
    with veritabani.islem() as o:
        surum = ti.surum_tanimla(o, env.paket_id, 2)
        dugum = ti.nesne_turu_tanimla(o, surum.id, "DUGUM", "Düğüm")
        ustu = ti.iliski_tanimla(o, surum.id, "USTU", "Üstü", dugum.id, dugum.id)
        bagli = ti.iliski_tanimla(o, surum.id, "BAGLI", "Bağlı", dugum.id, dugum.id)
        ti.hiyerarsi_kurali_tanimla(o, ustu.id, 0, None)
        ti.hiyerarsi_kurali_tanimla(o, bagli.id, 0, None)
        return Dugumler(surum.id, dugum.id, ustu.id, bagli.id)


def _dugum(v: vt.Veritabani, d: Dugumler) -> int:
    with v.islem() as o:
        return ni.nesne_olustur(o, d.dugum_id).id


def test_hiyerarsik_iliski_kendine_donemez(
    veritabani: vt.Veritabani, dugumler: Dugumler
) -> None:
    a = _dugum(veritabani, dugumler)
    with pytest.raises(ni.HiyerarsiIhlali, match="çevrim"):
        with veritabani.islem() as o:
            ni.iliski_kur(o, dugumler.ustu_id, a, a)
    with pytest.raises(ni.HiyerarsiIhlali, match="çevrim"):
        with veritabani.islem() as o:
            ni.nesne_olustur(o, dugumler.dugum_id)  # kendine bağlantı verilemez zaten
            b = ni.nesne_olustur(o, dugumler.dugum_id)
            ni.iliski_kur(o, dugumler.ustu_id, b.id, b.id)
    assert _sayi(veritabani, nt.NESNE_ILISKISI) == 0


def test_hiyerarside_zincir_gecer_cevrim_reddedilir(
    veritabani: vt.Veritabani, dugumler: Dugumler
) -> None:
    a, b, c = (_dugum(veritabani, dugumler) for _ in range(3))
    with veritabani.islem() as o:
        ni.iliski_kur(o, dugumler.ustu_id, a, b)  # A → B
        ni.iliski_kur(o, dugumler.ustu_id, b, c)  # B → C
    with pytest.raises(ni.HiyerarsiIhlali, match="çevrim"):
        with veritabani.islem() as o:
            ni.iliski_kur(o, dugumler.ustu_id, c, a)  # C → A: çevrim
    with pytest.raises(ni.HiyerarsiIhlali, match="çevrim"):
        with veritabani.islem() as o:
            ni.iliski_kur(o, dugumler.ustu_id, b, a)  # B → A: iki düğümlü çevrim
    assert _sayi(veritabani, nt.NESNE_ILISKISI) == 2  # kısmi ilişki yok
    with veritabani.islem() as o:  # ağaç genişleyebilir: C → D
        d = ni.nesne_olustur(
            o, dugumler.dugum_id, None, [ni.UstBaglanti(dugumler.ustu_id, c)]
        )
        ni.iliski_kur(
            o, dugumler.ustu_id, d.id, a
        )  # D → A: A zaten üst değil, çevrim değil
    assert _sayi(veritabani, nt.NESNE_ILISKISI) == 4


def test_farkli_hiyerarsik_tanimlar_uzerinden_cevrim_reddedilir(
    veritabani: vt.Veritabani, dugumler: Dugumler
) -> None:
    a, b, c = (_dugum(veritabani, dugumler) for _ in range(3))
    with veritabani.islem() as o:
        ni.iliski_kur(o, dugumler.ustu_id, a, b)  # A →USTU B
        ni.iliski_kur(o, dugumler.bagli_id, b, c)  # B →BAGLI C
    with pytest.raises(ni.HiyerarsiIhlali, match="çevrim"):
        with veritabani.islem() as o:
            ni.iliski_kur(
                o, dugumler.ustu_id, c, a
            )  # C →USTU A: BAGLI üzerinden çevrim
    with pytest.raises(ni.HiyerarsiIhlali, match="çevrim"):
        with veritabani.islem() as o:
            ni.nesne_olustur(o, dugumler.dugum_id)  # sürüm kilitli; sorun değil
            ni.iliski_kur(o, dugumler.bagli_id, c, a)  # C →BAGLI A: aynı çevrim
    assert _sayi(veritabani, nt.NESNE_ILISKISI) == 2


def test_cevrim_denetimi_hiyerarsik_olmayan_iliskiyi_izlemez(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    """BENZER (kuralsız) A → B varken hiyerarşik olmayan yol çevrim sayılmaz."""
    depo = _depo(veritabani, env)
    raf = _raf(veritabani, env, depo)
    a = _urun(veritabani, env, [raf], "A")
    b = _urun(veritabani, env, [raf], "B")
    with veritabani.islem() as o:
        ni.iliski_kur(o, env.benzer_id, a, b)
        ni.iliski_kur(o, env.benzer_id, b, a)  # genel ilişkide çift yön serbest


def test_olmayan_iliski_tanimi_ve_nesne_reddedilir(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    raf = _raf(veritabani, env, depo)
    with pytest.raises(ti.TanimBulunamadi, match="ilişki tanımı bulunamadı"):
        with veritabani.islem() as o:
            ni.iliski_kur(o, 999, raf, depo)
    with pytest.raises(ni.NesneBulunamadi):
        with veritabani.islem() as o:
            ni.iliski_kur(o, env.depoda_id, raf, 999)
    with pytest.raises(ni.NesneBulunamadi):
        with veritabani.islem() as o:
            ni.nesne_olustur(
                o, env.raf_id, {"kod": "B"}, [ni.UstBaglanti(env.depoda_id, 999)]
            )
    assert _sayi(veritabani, nt.NESNE) == 2


# --- hiyerarşi ------------------------------------------------------------------------


def test_iki_farkli_ust_nesne_desteklenir(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    r1 = _raf(veritabani, env, depo, "A1")
    r2 = _raf(veritabani, env, depo, "A2")
    urun = _urun(veritabani, env, [r1, r2])
    with veritabani.islem() as o:
        ustler = sorted(i.hedef_nesne_id for i in ni.iliskileri_listele(o, urun))
    assert ustler == sorted([r1, r2])


def test_zorunlu_ust_olmadan_nesne_olusmaz(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    with pytest.raises(ni.HiyerarsiIhlali, match="'DEPODA' için en az 1 üst"):
        with veritabani.islem() as o:
            ni.nesne_olustur(o, env.raf_id, {"kod": "A1"})
    assert _sayi(veritabani, nt.NESNE) == 0
    assert _sayi(veritabani, nt.NESNE_OZELLIGI) == 0


def test_izin_verilmeyen_ust_turu_reddedilir(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    """Ürün doğrudan depoya bağlanamaz: böyle bir ilişki tanımı yok; DEPODA
    tanımı raf → depo olduğundan ürün kaynağı reddedilir."""
    depo = _depo(veritabani, env)
    raf = _raf(veritabani, env, depo)
    with pytest.raises(ni.GecersizIliski, match="kaynak nesne"):
        with veritabani.islem() as o:
            ni.nesne_olustur(
                o,
                env.urun_id,
                {"barkod": "x"},
                [
                    ni.UstBaglanti(env.rafta_id, raf),
                    ni.UstBaglanti(env.depoda_id, depo),
                ],
            )
    assert _sayi(veritabani, nt.NESNE) == 2


def test_en_cok_ust_sayisi_asilamaz(veritabani: vt.Veritabani, env: Envanter) -> None:
    depo = _depo(veritabani, env)
    r1, r2, r3 = (_raf(veritabani, env, depo, k) for k in ("A1", "A2", "A3"))
    with pytest.raises(ni.HiyerarsiIhlali, match="en çok 2 üst"):
        with veritabani.islem() as o:
            ni.nesne_olustur(
                o,
                env.urun_id,
                {"barkod": "x"},
                [ni.UstBaglanti(env.rafta_id, r) for r in (r1, r2, r3)],
            )
    assert _sayi(veritabani, nt.NESNE) == 4
    urun = _urun(veritabani, env, [r1, r2])
    with pytest.raises(ni.HiyerarsiIhlali, match="en çok 2 üst"):
        with veritabani.islem() as o:
            ni.iliski_kur(o, env.rafta_id, urun, r3)
    with veritabani.islem() as o:
        assert len(ni.iliskileri_listele(o, urun)) == 2


def test_ust_sayilari_tanim_verisinden_okunur(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    """Aynı çekirdek, başka sürümde başka sayılar: en az iki, en çok sınırsız üst.
    Sayılar koda değil tanım verisine bağlıdır."""
    with veritabani.islem() as o:
        surum2 = ti.surum_tanimla(o, env.paket_id, 2)
        depo2 = ti.nesne_turu_tanimla(o, surum2.id, "DEPO", "Depo")
        raf2 = ti.nesne_turu_tanimla(o, surum2.id, "RAF", "Raf")
        urun2 = ti.nesne_turu_tanimla(o, surum2.id, "URUN", "Ürün")
        depoda2 = ti.iliski_tanimla(o, surum2.id, "DEPODA", "Depoda", raf2.id, depo2.id)
        rafta2 = ti.iliski_tanimla(o, surum2.id, "RAFTA", "Rafta", urun2.id, raf2.id)
        ti.hiyerarsi_kurali_tanimla(o, depoda2.id, 1, None)
        ti.hiyerarsi_kurali_tanimla(o, rafta2.id, 2, None, ETKIN)
    with veritabani.islem() as o:
        d = ni.nesne_olustur(o, depo2.id)
        raflar = [
            ni.nesne_olustur(o, raf2.id, None, [ni.UstBaglanti(depoda2.id, d.id)]).id
            for _ in range(3)
        ]

    with pytest.raises(ni.HiyerarsiIhlali, match="en az 2 üst"):
        with veritabani.islem() as o:
            ni.nesne_olustur(o, urun2.id, None, [ni.UstBaglanti(rafta2.id, raflar[0])])
    with veritabani.islem() as o:
        assert ni.nesneleri_listele(o, urun2.id) == []

    with veritabani.islem() as o:  # sınırsız: üç üst kabul edilir
        urun = ni.nesne_olustur(
            o, urun2.id, None, [ni.UstBaglanti(rafta2.id, r) for r in raflar]
        )
        assert len(ni.iliskileri_listele(o, urun.id)) == 3


def test_zorunlu_son_ust_iliskisi_kaldirilamaz(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    r1 = _raf(veritabani, env, depo, "A1")
    r2 = _raf(veritabani, env, depo, "A2")
    urun = _urun(veritabani, env, [r1, r2])
    with veritabani.islem() as o:
        [ilk, ikinci] = ni.iliskileri_listele(o, urun)
        ni.iliski_kaldir(o, ilk.id)  # ikinci üst kalıyor, serbest
    with pytest.raises(ni.HiyerarsiIhlali, match="en az 1 üst"):
        with veritabani.islem() as o:
            ni.iliski_kaldir(o, ikinci.id)
    with veritabani.islem() as o:
        assert [i.id for i in ni.iliskileri_listele(o, urun)] == [ikinci.id]
    with pytest.raises(ni.HiyerarsiIhlali):
        with veritabani.islem() as o:
            [raf_depo] = ni.iliskileri_listele(o, r1)
            ni.iliski_kaldir(o, raf_depo.id)


def test_gerekli_durumda_olmayan_ust_reddedilir(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    kapali_depo = _depo(veritabani, env, "Kapalı")
    with veritabani.islem() as o:
        ni.yasam_durumunu_degistir(o, kapali_depo, KAPALI)
    with pytest.raises(ni.HiyerarsiIhlali, match="etkin durumda olmalı"):
        with veritabani.islem() as o:
            ni.nesne_olustur(
                o,
                env.raf_id,
                {"kod": "A1"},
                [ni.UstBaglanti(env.depoda_id, kapali_depo)],
            )
    assert _sayi(veritabani, nt.NESNE) == 1
    acik_depo = _depo(veritabani, env, "Açık")
    raf = _raf(veritabani, env, acik_depo)
    with pytest.raises(ni.HiyerarsiIhlali, match="etkin durumda olmalı"):
        with veritabani.islem() as o:
            ni.iliski_kur(o, env.depoda_id, raf, kapali_depo)


def test_ust_durum_degisikligi_cocugu_bozarsa_reddedilir(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    """Kural yaşam durumundan bağımsızdır: raf kapalı olsa da depo kapatılamaz,
    kapalı raf son zorunlu üstünü kaybedemez."""
    depo = _depo(veritabani, env)
    raf = _raf(veritabani, env, depo)
    with pytest.raises(ni.HiyerarsiIhlali, match="'DEPODA' için en az 1 üst"):
        with veritabani.islem() as o:
            ni.yasam_durumunu_degistir(o, depo, KAPALI)
    assert _durum(veritabani, depo) == ETKIN.value

    with veritabani.islem() as o:
        ni.yasam_durumunu_degistir(o, raf, KAPALI)
    with pytest.raises(ni.HiyerarsiIhlali, match="'DEPODA' için en az 1 üst"):
        with veritabani.islem() as o:
            ni.yasam_durumunu_degistir(o, depo, KAPALI)  # çocuk kapalı diye geçilmez
    assert _durum(veritabani, depo) == ETKIN.value
    with pytest.raises(ni.HiyerarsiIhlali, match="en az 1 üst"):
        with veritabani.islem() as o:
            [baglanti] = ni.iliskileri_listele(o, raf)
            ni.iliski_kaldir(o, baglanti.id)  # kapalı çocuk da son üstünü kaybedemez
    with veritabani.islem() as o:
        assert len(ni.iliskileri_listele(o, raf)) == 1
        ni.yasam_durumunu_degistir(o, raf, ETKIN)  # üst etkin: geri açılabilir
    assert _durum(veritabani, raf) == ETKIN.value


def test_cocuksuz_ust_kapatilip_acilabilir(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    with veritabani.islem() as o:
        ni.yasam_durumunu_degistir(o, depo, KAPALI)
    assert _durum(veritabani, depo) == KAPALI.value
    with pytest.raises(ni.HiyerarsiIhlali, match="etkin durumda olmalı"):
        with veritabani.islem() as o:
            ni.nesne_olustur(
                o, env.raf_id, {"kod": "A1"}, [ni.UstBaglanti(env.depoda_id, depo)]
            )
    with veritabani.islem() as o:
        ni.yasam_durumunu_degistir(o, depo, ETKIN)
    _raf(veritabani, env, depo)


def test_ikinci_ust_varken_biri_kapatilabilir(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    r1 = _raf(veritabani, env, depo, "A1")
    r2 = _raf(veritabani, env, depo, "A2")
    urun = _urun(veritabani, env, [r1, r2])
    with veritabani.islem() as o:
        ni.yasam_durumunu_degistir(o, r1, KAPALI)  # ürünün r2'si etkin
    assert _durum(veritabani, r1) == KAPALI.value
    with pytest.raises(ni.HiyerarsiIhlali):
        with veritabani.islem() as o:
            ni.yasam_durumunu_degistir(o, r2, KAPALI)
    assert _durum(veritabani, urun) == ETKIN.value


def test_istege_bagli_ust_kurali(veritabani: vt.Veritabani, env: Envanter) -> None:
    """BOLGEDE: en az 0, en çok 1, üst durumu fark etmez."""
    depo = _depo(veritabani, env)
    raf = _raf(veritabani, env, depo)  # bölgesiz raf geçerli
    with veritabani.islem() as o:
        b1 = ni.nesne_olustur(o, env.bolge_id, {"ad": "Kuzey"}).id
        b2 = ni.nesne_olustur(o, env.bolge_id, {"ad": "Güney"}).id
        ni.yasam_durumunu_degistir(o, b1, KAPALI)
        ni.iliski_kur(o, env.bolgede_id, raf, b1)  # kapalı bölge de olur
    with pytest.raises(ni.HiyerarsiIhlali, match="en çok 1 üst"):
        with veritabani.islem() as o:
            ni.iliski_kur(o, env.bolgede_id, raf, b2)
    with veritabani.islem() as o:
        [bolge_baglantisi] = [
            i
            for i in ni.iliskileri_listele(o, raf)
            if i.iliski_tanimi_id == env.bolgede_id
        ]
        ni.iliski_kaldir(o, bolge_baglantisi.id)  # isteğe bağlı: kaldırılabilir


# --- yaşam durumu ---------------------------------------------------------------------


def test_yasam_durumu_servisle_degisir(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    with veritabani.islem() as o:
        assert ni.yasam_durumunu_degistir(o, depo, KAPALI).yasam_durumu == "kapali"
        assert ni.yasam_durumunu_degistir(o, depo, KAPALI).yasam_durumu == "kapali"
        assert ni.yasam_durumunu_degistir(o, depo, ETKIN).yasam_durumu == "etkin"


def test_gecersiz_yasam_durumu_reddedilir(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    durum: Any = "askida"
    with pytest.raises(ni.YasamDurumuIhlali, match="askida"):
        with veritabani.islem() as o:
            ni.yasam_durumunu_degistir(o, depo, durum)
    with pytest.raises(IntegrityError, match="CHECK constraint failed"):
        with veritabani.islem() as o:
            o.execute(
                text("UPDATE nesne SET yasam_durumu = 'askida' WHERE id = :n"),
                {"n": depo},
            )
    assert _durum(veritabani, depo) == ETKIN.value


# --- transaction ----------------------------------------------------------------------


def test_ozellik_hatasinda_nesne_ve_kilit_kalmaz(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    with pytest.raises(ni.OzellikTuruUyusmuyor):
        with veritabani.islem() as o:
            ni.nesne_olustur(o, env.depo_id, {"ad": 5})
    assert _sayi(veritabani, nt.NESNE) == 0
    assert _sayi(veritabani, nt.NESNE_OZELLIGI) == 0
    with veritabani.islem() as o:
        assert ti.surum_kilitli_mi(o, env.surum_id) is False


def test_iliski_hatasinda_nesne_kalmaz(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    with pytest.raises(ni.GecersizIliski):
        with veritabani.islem() as o:
            ni.nesne_olustur(
                o, env.urun_id, {"barkod": "x"}, [ni.UstBaglanti(env.rafta_id, depo)]
            )
    assert _sayi(veritabani, nt.NESNE) == 1
    assert _sayi(veritabani, nt.NESNE_OZELLIGI) == 1
    assert _sayi(veritabani, nt.NESNE_ILISKISI) == 0


def test_hiyerarsi_hatasinda_hicbir_kismi_satir_kalmaz(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    raflar = [_raf(veritabani, env, depo, k) for k in ("A1", "A2", "A3")]
    once = (
        _sayi(veritabani, nt.NESNE),
        _sayi(veritabani, nt.NESNE_OZELLIGI),
        _sayi(veritabani, nt.NESNE_ILISKISI),
    )
    with pytest.raises(ni.HiyerarsiIhlali):
        with veritabani.islem() as o:
            ni.nesne_olustur(
                o,
                env.urun_id,
                {"barkod": "x", "kirilgan": True},
                [ni.UstBaglanti(env.rafta_id, r) for r in raflar],
            )
    assert (
        _sayi(veritabani, nt.NESNE),
        _sayi(veritabani, nt.NESNE_OZELLIGI),
        _sayi(veritabani, nt.NESNE_ILISKISI),
    ) == once


def test_veritabani_kisit_hatasindan_sonra_kullanilabilir_kalir(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    with pytest.raises(IntegrityError):
        with veritabani.islem() as o:
            ni.nesne_olustur(o, env.depo_id, {"ad": "İkinci"})
            o.execute(
                text("UPDATE nesne SET yasam_durumu = 'askida' WHERE id = :n"),
                {"n": depo},
            )
    assert _sayi(veritabani, nt.NESNE) == 1
    raf = _raf(veritabani, env, depo)
    with veritabani.islem() as o:
        assert ni.nesne_getir(o, raf).yasam_durumu == "etkin"
        assert o.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"
        assert o.execute(text("PRAGMA foreign_key_check")).all() == []


# --- tanım sürümü kilidi --------------------------------------------------------------


def test_kullanilmamis_surume_tanim_eklenebilir(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    with veritabani.islem() as o:
        assert ti.surum_kilitli_mi(o, env.surum_id) is False
        ti.nesne_turu_tanimla(o, env.surum_id, "PALET", "Palet")
        ti.ozellik_tanimla(o, env.raf_id, "renk", "Renk", DegerTuru.METIN)


def test_ilk_nesne_surumu_kilitler(veritabani: vt.Veritabani, env: Envanter) -> None:
    _depo(veritabani, env)
    with veritabani.islem() as o:
        assert ti.surum_kilitli_mi(o, env.surum_id) is True
        assert (
            o.execute(
                text("SELECT kilitli FROM tanim_surumu WHERE id = :s"),
                {"s": env.surum_id},
            ).scalar_one()
            == 1
        )


def test_rollback_olan_islemde_kilit_kalmaz(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    with pytest.raises(RuntimeError, match="sentetik"):
        with veritabani.islem() as o:
            ni.nesne_olustur(o, env.depo_id, {"ad": "Merkez"})
            assert ti.surum_kilitli_mi(o, env.surum_id) is True  # işlem içinde kilitli
            raise RuntimeError("sentetik hata")
    with veritabani.islem() as o:
        assert ti.surum_kilitli_mi(o, env.surum_id) is False
        ti.nesne_turu_tanimla(o, env.surum_id, "PALET", "Palet")  # hâlâ açık
    assert _sayi(veritabani, nt.NESNE) == 0


def test_kilitli_surume_tanim_eklenemez(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    _depo(veritabani, env)
    denemeler: list[Callable[[Session], object]] = [
        lambda o: ti.nesne_turu_tanimla(o, env.surum_id, "PALET", "Palet"),
        lambda o: ti.ozellik_tanimla(o, env.raf_id, "renk", "Renk", DegerTuru.METIN),
        lambda o: ti.iliski_tanimla(
            o, env.surum_id, "YANINDA", "Yanında", env.raf_id, env.raf_id
        ),
        lambda o: ti.hiyerarsi_kurali_tanimla(o, env.benzer_id, 0, None),
        lambda o: ti.kayit_turu_tanimla(o, env.surum_id, "SAYIM", "Sayım"),
    ]
    for deneme in denemeler:
        with pytest.raises(ti.TanimSurumuKilitli, match="kilitli"):
            with veritabani.islem() as o:
                deneme(o)
    assert _sayi(veritabani, tt.NESNE_TURU) == 4
    assert _sayi(veritabani, tt.HIYERARSI_KURALI) == 3
    assert _sayi(veritabani, tt.KAYIT_TURU) == 0


def test_kilitli_surume_kayit_alani_eklenemez(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    with veritabani.islem() as o:
        sayim = ti.kayit_turu_tanimla(o, env.surum_id, "SAYIM", "Sayım")
    _depo(veritabani, env)
    with pytest.raises(ti.TanimSurumuKilitli):
        with veritabani.islem() as o:
            ti.kayit_alani_tanimla(o, sayim.id, "adet", "Adet")
    assert _sayi(veritabani, tt.KAYIT_ALANI_TANIMI) == 0


def test_yeni_surum_acilir_ve_kendi_tanimlarini_tasir(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    with veritabani.islem() as o:
        surum2 = ti.surum_tanimla(o, env.paket_id, 2, "genişletme")
        assert ti.surum_kilitli_mi(o, surum2.id) is False
        depo2 = ti.nesne_turu_tanimla(o, surum2.id, "DEPO", "Depo")
        ti.nesne_turu_tanimla(o, surum2.id, "PALET", "Palet")
        ti.ozellik_tanimla(o, depo2.id, "ad", "Ad", DegerTuru.METIN, zorunlu=True)
        ti.ozellik_tanimla(o, depo2.id, "sehir", "Şehir", DegerTuru.METIN, zorunlu=True)
        assert [t.kod for t in ti.nesne_turlerini_listele(o, surum2.id)] == [
            "DEPO",
            "PALET",
        ]
    with veritabani.islem() as o:
        yeni = ni.nesne_olustur(o, depo2.id, {"ad": "Yeni", "sehir": "Edirne"})
        assert yeni.tanim_surumu_id == surum2.id
        assert ti.surum_kilitli_mi(o, surum2.id) is True
    assert _sayi(veritabani, nt.NESNE) == 2
    with veritabani.islem() as o:  # ilişki de sürümler arası kurulamaz
        with pytest.raises(ni.GecersizIliski):
            ni.iliski_kur(o, env.depoda_id, depo, yeni.id)


def test_eski_nesnenin_anlami_yeni_surumle_degismez(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    with veritabani.islem() as o:
        surum2 = ti.surum_tanimla(o, env.paket_id, 2)
        depo2 = ti.nesne_turu_tanimla(o, surum2.id, "DEPO", "Depo")
        ti.ozellik_tanimla(o, depo2.id, "sehir", "Şehir", DegerTuru.METIN, zorunlu=True)
    with veritabani.islem() as o:
        eski = ni.nesne_getir(o, depo)
        assert (eski.nesne_turu_id, eski.tanim_surumu_id) == (env.depo_id, env.surum_id)
        assert ni.ozellikleri_oku(o, depo) == {"ad": "Merkez"}
        assert [t.kod for t in ti.ozellik_tanimlarini_listele(o, env.depo_id)] == ["ad"]
        with pytest.raises(
            ni.GecersizOzellik
        ):  # sürüm 2'nin özelliği sürüm 1 nesnesine yok
            ni.ozellik_yaz(o, depo, "sehir", "Edirne")
        ni.yasam_durumunu_degistir(o, depo, KAPALI)  # eski nesne hâlâ yönetilebilir
    assert _durum(veritabani, depo) == KAPALI.value


# --- servis hata atomikliği (SAVEPOINT) -----------------------------------------------
# Hata çağıran tarafından aynı işlem içinde yakalanır, işlem normal commit olur;
# başarısız çağrının hiçbir kısmi değişikliği kalmamalı.


def test_eksik_zorunlu_ozellik_hatasi_yakalaninca_nesne_kalmaz(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    with veritabani.islem() as o:
        try:
            ni.nesne_olustur(o, env.depo_id, {})
        except ni.NesneHatasi:
            pass
    assert _sayi(veritabani, nt.NESNE) == 0
    assert _sayi(veritabani, nt.NESNE_OZELLIGI) == 0
    with veritabani.islem() as o:
        assert ti.surum_kilitli_mi(o, env.surum_id) is False


def test_hiyerarsi_hatasi_yakalaninca_nesne_ve_ozellik_kalmaz(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    """Zorunlu üst eksikliği nesne yazıldıktan sonra anlaşılır; SAVEPOINT geri alır."""
    with veritabani.islem() as o:
        try:
            ni.nesne_olustur(o, env.raf_id, {"kod": "A1", "kapasite": 3})
        except ni.HiyerarsiIhlali:
            pass
    assert _sayi(veritabani, nt.NESNE) == 0
    assert _sayi(veritabani, nt.NESNE_OZELLIGI) == 0
    assert _sayi(veritabani, nt.NESNE_ILISKISI) == 0
    with veritabani.islem() as o:
        assert ti.surum_kilitli_mi(o, env.surum_id) is False


def test_en_cok_ust_hatasi_yakalaninca_fazla_iliski_kalmaz(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    r1, r2, r3 = (_raf(veritabani, env, depo, k) for k in ("A1", "A2", "A3"))
    urun = _urun(veritabani, env, [r1, r2])
    with veritabani.islem() as o:
        try:
            ni.iliski_kur(o, env.rafta_id, urun, r3)
        except ni.HiyerarsiIhlali:
            pass
        try:
            ni.nesne_olustur(
                o,
                env.urun_id,
                {"barkod": "Y"},
                [ni.UstBaglanti(env.rafta_id, r) for r in (r1, r2, r3)],
            )
        except ni.HiyerarsiIhlali:
            pass
    with veritabani.islem() as o:
        assert sorted(
            i.hedef_nesne_id for i in ni.iliskileri_listele(o, urun)
        ) == sorted([r1, r2])
        assert [n.id for n in ni.nesneleri_listele(o, env.urun_id)] == [urun]


def test_son_ust_kaldirma_hatasi_yakalaninca_iliski_durur(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    raf = _raf(veritabani, env, depo)
    with veritabani.islem() as o:
        [baglanti] = ni.iliskileri_listele(o, raf)
        try:
            ni.iliski_kaldir(o, baglanti.id)
        except ni.HiyerarsiIhlali:
            pass
    with veritabani.islem() as o:
        assert [i.id for i in ni.iliskileri_listele(o, raf)] == [baglanti.id]


def test_ust_durum_hatasi_yakalaninca_eski_durum_korunur(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    depo = _depo(veritabani, env)
    _raf(veritabani, env, depo)
    with veritabani.islem() as o:
        try:
            ni.yasam_durumunu_degistir(o, depo, KAPALI)
        except ni.HiyerarsiIhlali:
            pass
        assert ni.nesne_getir(o, depo).yasam_durumu == ETKIN.value  # işlem içinde de
    assert _durum(veritabani, depo) == ETKIN.value


def test_cevrim_hatasi_yakalaninca_iliski_kalmaz(
    veritabani: vt.Veritabani, dugumler: Dugumler
) -> None:
    a, b = (_dugum(veritabani, dugumler) for _ in range(2))
    with veritabani.islem() as o:
        ni.iliski_kur(o, dugumler.ustu_id, a, b)
        try:
            ni.iliski_kur(o, dugumler.bagli_id, b, a)
        except ni.HiyerarsiIhlali:
            pass
    assert _sayi(veritabani, nt.NESNE_ILISKISI) == 1


def test_hatadan_sonra_ayni_islemde_gecerli_is_commit_olur(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    """Hata SAVEPOINT'i geri alır, dış işlem kullanılabilir kalır ve commit eder."""
    depo = _depo(veritabani, env)
    with veritabani.islem() as o:
        for deneme in (
            lambda: ni.nesne_olustur(o, env.raf_id, {"kod": "B"}),  # üst yok
            lambda: ni.ozellik_yaz(o, depo, "ad", 5),  # tür uyuşmaz
            lambda: ni.yasam_durumunu_degistir(
                o, depo, KAPALI
            ),  # önce çocuk yok, geçer
        ):
            try:
                deneme()
            except ni.NesneHatasi:
                pass
        ni.yasam_durumunu_degistir(o, depo, ETKIN)
        raf = ni.nesne_olustur(
            o, env.raf_id, {"kod": "A1"}, [ni.UstBaglanti(env.depoda_id, depo)]
        )
        try:
            ni.iliski_kur(o, env.depoda_id, raf.id, depo)  # mükerrer
        except ni.MukerrerIliski:
            pass
        ni.ozellik_yaz(o, raf.id, "kapasite", 12)
    with veritabani.islem() as o:
        assert [n.id for n in ni.nesneleri_listele(o, env.raf_id)] == [raf.id]
        assert ni.ozellikleri_oku(o, raf.id) == {"kod": "A1", "kapasite": 12}
        assert ni.ozellikleri_oku(o, depo) == {"ad": "Merkez"}
        assert len(ni.iliskileri_listele(o, raf.id)) == 1
        assert _durum(veritabani, depo) == ETKIN.value
        assert o.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"


def test_veritabani_kisit_hatasi_yakalaninca_islem_kullanilabilir_kalir(
    veritabani: vt.Veritabani, env: Envanter
) -> None:
    """Servis içindeki ``flush`` kısıt hatası verse de SAVEPOINT sayesinde dış
    işlem bozulmaz (ham SQL ile önceden çakıştırılmış bir satır üzerinden)."""
    depo = _depo(veritabani, env)
    with veritabani.islem() as o:
        [ad] = ti.ozellik_tanimlarini_listele(o, env.depo_id)
        o.execute(text("DELETE FROM nesne_ozelligi"))
        o.execute(
            text(
                "INSERT INTO nesne_ozelligi "
                "(nesne_id, nesne_turu_id, ozellik_tanimi_id, deger) "
                "VALUES (:n, :tur, :tanim, 'ham')"
            ),
            {"n": depo, "tur": env.depo_id, "tanim": ad.id},
        )
        o.execute(
            text("UPDATE tanim_paketi SET kod = 'ENVANTER2'")
        )  # işlemde başka geçerli değişiklik
        try:
            with o.begin_nested():
                o.execute(
                    text(
                        "INSERT INTO nesne_ozelligi (nesne_id, nesne_turu_id, "
                        "ozellik_tanimi_id, deger) VALUES (:n, :tur, :tanim, 'kopya')"
                    ),
                    {"n": depo, "tur": env.depo_id, "tanim": ad.id},
                )
        except IntegrityError:
            pass
        ni.ozellik_yaz(o, depo, "ad", "Güncel")
    with veritabani.islem() as o:
        assert ni.ozellikleri_oku(o, depo) == {"ad": "Güncel"}
        assert ti.paket_bul(o, "ENVANTER2") is not None
