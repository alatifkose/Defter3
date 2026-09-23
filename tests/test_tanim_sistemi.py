"""Tanım sistemi testleri (Aşama 4.2).

Gerçek SQLite dosyası, ``test`` ortamı, ``tmp_path`` altında kök; şema gerçek
göç zinciriyle (``semayi_yukselt``) kurulur. Tanımlar finans dışı sahte
paketlerdir (``DEMO``: ``TEST_KISI``, ``TEST_CIHAZ``, ``TEST_OLAY``;
``ENVANTER``: ``DEPO``, ``RAF``, ``URUN``); çekirdek bunların anlamını bilmez.

İki düzey sınanır: uygulama sözleşmesi (``tanim_islemleri`` hataları) ve
veritabanı kısıtları (ham SQL ile aynı ihlal ``IntegrityError`` verir).
"""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from defteruc import ayarlar as ay
from defteruc.cekirdek import gocler
from defteruc.cekirdek import tanim_islemleri as ti
from defteruc.cekirdek import tanim_tablolari as tt
from defteruc.cekirdek import veritabani as vt
from defteruc.cekirdek.tanim_tablolari import DegerTuru, YasamDurumu

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
    """Göç zinciri ``head``'e uygulanmış gerçek SQLite dosyası."""
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(tmp_path / "kok"))
    ayar = ay.ayarlari_yukle()
    ay.dizinleri_hazirla(ayar)
    v = vt.Veritabani(ayar.veritabani_yolu)
    gocler.semayi_yukselt(v)
    yield v
    v.kapat()


@dataclass(frozen=True, slots=True)
class Demo:
    """``DEMO`` paketinin kimlikleri."""

    paket_id: int
    surum_id: int
    kisi_id: int
    cihaz_id: int
    olay_id: int


@pytest.fixture
def demo(veritabani: vt.Veritabani) -> Demo:
    with veritabani.islem() as oturum:
        paket = ti.paket_tanimla(oturum, "DEMO", "Demo tanım paketi")
        surum = ti.surum_tanimla(oturum, paket.id, 1, "ilk sürüm")
        kisi = ti.nesne_turu_tanimla(oturum, surum.id, "TEST_KISI", "Kişi")
        cihaz = ti.nesne_turu_tanimla(oturum, surum.id, "TEST_CIHAZ", "Cihaz")
        olay = ti.kayit_turu_tanimla(oturum, surum.id, "TEST_OLAY", "Olay")
        return Demo(paket.id, surum.id, kisi.id, cihaz.id, olay.id)


def _sayi(v: vt.Veritabani, tablo: str) -> int:
    with v.islem() as oturum:
        return int(oturum.execute(text(f"SELECT count(*) FROM {tablo}")).scalar_one())


# --- tanım paketi ---------------------------------------------------------------------


def test_paket_tanimlanir_ve_okunur(veritabani: vt.Veritabani) -> None:
    with veritabani.islem() as oturum:
        paket = ti.paket_tanimla(oturum, "DEMO", "Demo tanım paketi", "açıklama")
        assert paket.id is not None

    with veritabani.islem() as oturum:
        bulunan = ti.paket_bul(oturum, "DEMO")
        assert bulunan is not None
        assert (bulunan.id, bulunan.kod, bulunan.gosterim_adi, bulunan.aciklama) == (
            paket.id,
            "DEMO",
            "Demo tanım paketi",
            "açıklama",
        )
        assert bulunan.olusturma_zamani.tzinfo is None  # UTC, saat dilimsiz
        assert [p.kod for p in ti.paketleri_listele(oturum)] == ["DEMO"]
        assert ti.paket_bul(oturum, "YOK") is None


def test_ayni_kodla_ikinci_paket_reddedilir(veritabani: vt.Veritabani) -> None:
    with veritabani.islem() as oturum:
        ti.paket_tanimla(oturum, "DEMO", "Demo")

    with pytest.raises(ti.MukerrerTanim, match="'DEMO' zaten var"):
        with veritabani.islem() as oturum:
            ti.paket_tanimla(oturum, "DEMO", "Başka gösterim adı")

    assert _sayi(veritabani, tt.TANIM_PAKETI) == 1


def test_paket_kodu_benzersizligi_veritabaninda_da_calisir(
    veritabani: vt.Veritabani,
) -> None:
    with veritabani.islem() as oturum:
        ti.paket_tanimla(oturum, "DEMO", "Demo")

    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        with veritabani.islem() as oturum:
            oturum.execute(
                text(
                    "INSERT INTO tanim_paketi (kod, gosterim_adi, olusturma_zamani) "
                    "VALUES ('DEMO', 'kopya', '2026-09-18 00:00:00')"
                )
            )

    assert _sayi(veritabani, tt.TANIM_PAKETI) == 1


def test_kod_buyuk_kucuk_harf_ayrimi_yapar(veritabani: vt.Veritabani) -> None:
    """Belgelenen davranış: kod verildiği gibi saklanır ve karşılaştırılır."""
    with veritabani.islem() as oturum:
        ti.paket_tanimla(oturum, "DEMO", "Büyük")
        ti.paket_tanimla(oturum, "Demo", "Karışık")

    with veritabani.islem() as oturum:
        assert [p.kod for p in ti.paketleri_listele(oturum)] == ["DEMO", "Demo"]


@pytest.mark.parametrize(
    "kod",
    ["", " ", "1DEMO", "DE MO", "DE-MO", "DEMO.1", "ÖRNEK", "demo!", "_DEMO"],
)
def test_gecersiz_kod_bicimi_reddedilir(veritabani: vt.Veritabani, kod: str) -> None:
    with pytest.raises(ti.GecersizTanim, match="geçersiz"):
        with veritabani.islem() as oturum:
            ti.paket_tanimla(oturum, kod, "Demo")

    assert _sayi(veritabani, tt.TANIM_PAKETI) == 0


@pytest.mark.parametrize("kod", ["DEMO", "demo", "Demo_2", "d", "TEST_KISI_01"])
def test_gecerli_kod_bicimleri_kabul_edilir(
    veritabani: vt.Veritabani, kod: str
) -> None:
    with veritabani.islem() as oturum:
        assert ti.paket_tanimla(oturum, kod, "Demo").kod == kod


def test_bos_gosterim_adi_reddedilir(veritabani: vt.Veritabani) -> None:
    with pytest.raises(ti.GecersizTanim, match="gösterim adı boş"):
        with veritabani.islem() as oturum:
            ti.paket_tanimla(oturum, "DEMO", "   ")


# --- tanım sürümü ---------------------------------------------------------------------


def test_surum_tanimlanir_ve_sirali_listelenir(veritabani: vt.Veritabani) -> None:
    with veritabani.islem() as oturum:
        paket = ti.paket_tanimla(oturum, "DEMO", "Demo")
        ikinci = ti.surum_tanimla(oturum, paket.id, 2, "ikinci")
        birinci = ti.surum_tanimla(oturum, paket.id, 1)

    with veritabani.islem() as oturum:
        surumler = ti.surumleri_listele(oturum, paket.id)
        assert [(s.id, s.surum_no, s.aciklama) for s in surumler] == [
            (birinci.id, 1, None),
            (ikinci.id, 2, "ikinci"),
        ]
        assert all(s.tanim_paketi_id == paket.id for s in surumler)


def test_ayni_pakette_ayni_surum_no_reddedilir(veritabani: vt.Veritabani) -> None:
    with veritabani.islem() as oturum:
        paket = ti.paket_tanimla(oturum, "DEMO", "Demo")
        ti.surum_tanimla(oturum, paket.id, 1)

    with pytest.raises(ti.MukerrerTanim, match="sürüm 1 zaten var"):
        with veritabani.islem() as oturum:
            ti.surum_tanimla(oturum, paket.id, 1)

    assert _sayi(veritabani, tt.TANIM_SURUMU) == 1


def test_farkli_paketler_ayni_surum_noyu_kullanabilir(
    veritabani: vt.Veritabani,
) -> None:
    with veritabani.islem() as oturum:
        a = ti.paket_tanimla(oturum, "DEMO", "Demo")
        b = ti.paket_tanimla(oturum, "ENVANTER", "Envanter")
        ti.surum_tanimla(oturum, a.id, 1)
        ti.surum_tanimla(oturum, b.id, 1)

    assert _sayi(veritabani, tt.TANIM_SURUMU) == 2


SURUM_NO_SOZLESMESI: tuple[tuple[Any, str | None], ...] = (
    (1, None),
    (7, None),
    (0, "pozitif olmalı"),
    (-1, "pozitif olmalı"),
    (1.5, "tam sayı olmalı"),
    (1.0, "tam sayı olmalı"),  # float, değeri tam olsa da
    (True, "tam sayı olmalı"),  # bool int alt sınıfı; sürüm numarası değil
    (False, "tam sayı olmalı"),
    ("1", "tam sayı olmalı"),
    ("abc", "tam sayı olmalı"),
)
"""``surum_tanimla`` sözleşmesi: (değer, beklenen hata parçası ya da kabul)."""


@pytest.mark.parametrize(("deger", "hata"), SURUM_NO_SOZLESMESI)
def test_surum_no_yalniz_pozitif_tam_sayi(
    veritabani: vt.Veritabani, deger: Any, hata: str | None
) -> None:
    """Tip ipucu çalışma zamanında denetlemez; sözleşme burada sabitlenir.
    Reddedilen değerler ham ``TypeError`` değil ``GecersizTanim`` verir."""
    with veritabani.islem() as oturum:
        paket = ti.paket_tanimla(oturum, "DEMO", "Demo")

    if hata is None:
        with veritabani.islem() as oturum:
            surum = ti.surum_tanimla(oturum, paket.id, deger)
        assert type(surum.surum_no) is int and surum.surum_no == deger
        assert _sayi(veritabani, tt.TANIM_SURUMU) == 1
        return

    with pytest.raises(ti.GecersizTanim, match=hata):
        with veritabani.islem() as oturum:
            ti.surum_tanimla(oturum, paket.id, deger)
    assert _sayi(veritabani, tt.TANIM_SURUMU) == 0


def test_surum_kisitlari_veritabaninda_da_calisir(veritabani: vt.Veritabani) -> None:
    with veritabani.islem() as oturum:
        paket = ti.paket_tanimla(oturum, "DEMO", "Demo")
        ti.surum_tanimla(oturum, paket.id, 1)

    ekle = (
        "INSERT INTO tanim_surumu (tanim_paketi_id, surum_no, olusturma_zamani) "
        "VALUES (:paket, :no, '2026-09-18 00:00:00')"
    )
    with pytest.raises(IntegrityError, match="CHECK constraint failed"):
        with veritabani.islem() as oturum:
            oturum.execute(text(ekle), {"paket": paket.id, "no": 0})
    with pytest.raises(
        IntegrityError, match="ck_tanim_surumu_surum_no_pozitif_tamsayi"
    ):
        with veritabani.islem() as oturum:
            oturum.execute(text(ekle), {"paket": paket.id, "no": 1.5})  # REAL
    with pytest.raises(
        IntegrityError, match="ck_tanim_surumu_surum_no_pozitif_tamsayi"
    ):
        with veritabani.islem() as oturum:
            oturum.execute(text(ekle), {"paket": paket.id, "no": "abc"})  # TEXT
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        with veritabani.islem() as oturum:
            oturum.execute(text(ekle), {"paket": paket.id, "no": 1})
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with veritabani.islem() as oturum:
            oturum.execute(text(ekle), {"paket": paket.id + 100, "no": 2})

    assert _sayi(veritabani, tt.TANIM_SURUMU) == 1


def test_surum_no_veritabaninda_integer_depolama_sinifiyla_saklanir(
    veritabani: vt.Veritabani,
) -> None:
    """SQLite INTEGER sütunu katı değildir; kontrol kısıtı depolama sınıfını
    zorlar. Kayıpsız dönüşen değerler (``2.0``, ``'3'``) SQLite tür yakınlığıyla
    kısıttan önce tam sayıya çevrilir ve tam sayı olarak saklanır; bu SQLite
    davranışıdır, uygulama katmanı bu türleri zaten reddeder."""
    with veritabani.islem() as oturum:
        paket = ti.paket_tanimla(oturum, "DEMO", "Demo")
        oturum.execute(
            text(
                "INSERT INTO tanim_surumu "
                "(tanim_paketi_id, surum_no, olusturma_zamani) "
                "VALUES (:paket, 2.0, '2026-09-18 00:00:00'), "
                "(:paket, '3', '2026-09-18 00:00:00')"
            ),
            {"paket": paket.id},
        )

    with veritabani.islem() as oturum:
        satirlar = oturum.execute(
            text(
                "SELECT surum_no, typeof(surum_no) FROM tanim_surumu ORDER BY surum_no"
            )
        ).all()
    assert [tuple(s) for s in satirlar] == [(2, "integer"), (3, "integer")]


def test_olmayan_pakete_surum_eklenemez(veritabani: vt.Veritabani) -> None:
    with pytest.raises(ti.TanimBulunamadi, match="tanım paketi bulunamadı"):
        with veritabani.islem() as oturum:
            ti.surum_tanimla(oturum, 999, 1)


# --- nesne türü -----------------------------------------------------------------------


def test_nesne_turu_tanimlanir_ve_listelenir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    with veritabani.islem() as oturum:
        turler = ti.nesne_turlerini_listele(oturum, demo.surum_id)
        assert [(t.kod, t.gosterim_adi) for t in turler] == [
            ("TEST_CIHAZ", "Cihaz"),
            ("TEST_KISI", "Kişi"),
        ]
        assert all(t.tanim_surumu_id == demo.surum_id for t in turler)


def test_ayni_surumde_ayni_nesne_turu_kodu_reddedilir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    with pytest.raises(ti.MukerrerTanim, match="'TEST_KISI' bu sürümde zaten var"):
        with veritabani.islem() as oturum:
            ti.nesne_turu_tanimla(oturum, demo.surum_id, "TEST_KISI", "Başka")

    assert _sayi(veritabani, tt.NESNE_TURU) == 2


def test_ayni_kod_farkli_surumde_serbest(veritabani: vt.Veritabani, demo: Demo) -> None:
    """Sürüm 2, sürüm 1'in türünü değiştirmez; kendi TEST_KISI satırını taşır."""
    with veritabani.islem() as oturum:
        surum2 = ti.surum_tanimla(oturum, demo.paket_id, 2)
        yeni = ti.nesne_turu_tanimla(oturum, surum2.id, "TEST_KISI", "Kişi (v2)")

    with veritabani.islem() as oturum:
        eski = [t for t in ti.nesne_turlerini_listele(oturum, demo.surum_id)]
        assert [t.kod for t in eski] == ["TEST_CIHAZ", "TEST_KISI"]
        assert [t.id for t in ti.nesne_turlerini_listele(oturum, surum2.id)] == [
            yeni.id
        ]
        assert yeni.id != demo.kisi_id


def test_olmayan_surume_nesne_turu_eklenemez(veritabani: vt.Veritabani) -> None:
    with pytest.raises(ti.TanimBulunamadi, match="tanım sürümü bulunamadı"):
        with veritabani.islem() as oturum:
            ti.nesne_turu_tanimla(oturum, 999, "TEST_KISI", "Kişi")

    assert _sayi(veritabani, tt.NESNE_TURU) == 0


def test_nesne_turu_dis_anahtari_veritabaninda_calisir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with veritabani.islem() as oturum:
            oturum.execute(
                text(
                    "INSERT INTO nesne_turu (tanim_surumu_id, kod, gosterim_adi) "
                    "VALUES (:surum, 'TEST_ARAC', 'Araç')"
                ),
                {"surum": demo.surum_id + 100},
            )

    assert _sayi(veritabani, tt.NESNE_TURU) == 2


# --- özellik tanımı -------------------------------------------------------------------


def test_ozellik_nesne_turune_baglanir(veritabani: vt.Veritabani, demo: Demo) -> None:
    with veritabani.islem() as oturum:
        seri = ti.ozellik_tanimla(
            oturum, demo.cihaz_id, "seri_no", "Seri numarası", DegerTuru.METIN
        )
        model = ti.ozellik_tanimla(
            oturum, demo.cihaz_id, "model", "Model", DegerTuru.METIN, aciklama="üretici"
        )

    with veritabani.islem() as oturum:
        ozellikler = ti.ozellik_tanimlarini_listele(oturum, demo.cihaz_id)
        assert [(o.id, o.kod, o.gosterim_adi, o.aciklama) for o in ozellikler] == [
            (seri.id, "seri_no", "Seri numarası", None),
            (model.id, "model", "Model", "üretici"),
        ]
        assert [(o.deger_turu, o.zorunlu) for o in ozellikler] == [
            ("metin", False),
            ("metin", False),
        ]
        assert all(o.nesne_turu_id == demo.cihaz_id for o in ozellikler)
        assert ti.ozellik_tanimlarini_listele(oturum, demo.kisi_id) == []


def test_ayni_turde_ayni_ozellik_kodu_reddedilir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    with veritabani.islem() as oturum:
        ti.ozellik_tanimla(oturum, demo.cihaz_id, "seri_no", "Seri", DegerTuru.METIN)

    with pytest.raises(ti.MukerrerTanim, match="'seri_no' nesne türü 'TEST_CIHAZ'"):
        with veritabani.islem() as oturum:
            ti.ozellik_tanimla(
                oturum, demo.cihaz_id, "seri_no", "Yine seri", DegerTuru.METIN
            )

    assert _sayi(veritabani, tt.OZELLIK_TANIMI) == 1


def test_ayni_ozellik_kodu_farkli_turde_serbest(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    with veritabani.islem() as oturum:
        ti.ozellik_tanimla(oturum, demo.cihaz_id, "ad", "Ad", DegerTuru.METIN)
        ti.ozellik_tanimla(oturum, demo.kisi_id, "ad", "Ad", DegerTuru.METIN)

    assert _sayi(veritabani, tt.OZELLIK_TANIMI) == 2


def test_olmayan_nesne_turune_ozellik_eklenemez(veritabani: vt.Veritabani) -> None:
    with pytest.raises(ti.TanimBulunamadi, match="nesne türü bulunamadı"):
        with veritabani.islem() as oturum:
            ti.ozellik_tanimla(oturum, 999, "seri_no", "Seri", DegerTuru.METIN)


def test_ozellik_dis_anahtari_veritabaninda_calisir(veritabani: vt.Veritabani) -> None:
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with veritabani.islem() as oturum:
            oturum.execute(
                text(
                    "INSERT INTO ozellik_tanimi (nesne_turu_id, kod, gosterim_adi) "
                    "VALUES (999, 'seri_no', 'Seri')"
                )
            )


# --- ilişki tanımı --------------------------------------------------------------------


def test_iliski_kaynak_ve_hedef_ture_yonlu_baglanir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    with veritabani.islem() as oturum:
        iliski = ti.iliski_tanimla(
            oturum, demo.surum_id, "KULLANIR", "Kullanır", demo.kisi_id, demo.cihaz_id
        )

    with veritabani.islem() as oturum:
        [bulunan] = ti.iliski_tanimlarini_listele(oturum, demo.surum_id)
        assert bulunan.id == iliski.id
        assert bulunan.kod == "KULLANIR"
        assert bulunan.tanim_surumu_id == demo.surum_id
        assert (bulunan.kaynak_nesne_turu_id, bulunan.hedef_nesne_turu_id) == (
            demo.kisi_id,
            demo.cihaz_id,
        )  # yön korunur: kişi → cihaz, tersi değil


def test_ters_yonlu_iliski_ayri_tanimdir(veritabani: vt.Veritabani, demo: Demo) -> None:
    with veritabani.islem() as oturum:
        ti.iliski_tanimla(
            oturum, demo.surum_id, "KULLANIR", "Kullanır", demo.kisi_id, demo.cihaz_id
        )
        ti.iliski_tanimla(
            oturum,
            demo.surum_id,
            "KULLANICISI",
            "Kullanıcısı",
            demo.cihaz_id,
            demo.kisi_id,
        )

    assert _sayi(veritabani, tt.ILISKI_TANIMI) == 2


def test_turun_kendisiyle_iliskisi_tanimlanabilir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    with veritabani.islem() as oturum:
        iliski = ti.iliski_tanimla(
            oturum, demo.surum_id, "TANIR", "Tanır", demo.kisi_id, demo.kisi_id
        )
    assert iliski.kaynak_nesne_turu_id == iliski.hedef_nesne_turu_id == demo.kisi_id


def test_ayni_surumde_ayni_iliski_kodu_reddedilir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    with veritabani.islem() as oturum:
        ti.iliski_tanimla(
            oturum, demo.surum_id, "KULLANIR", "Kullanır", demo.kisi_id, demo.cihaz_id
        )

    with pytest.raises(ti.MukerrerTanim, match="'KULLANIR' bu sürümde zaten var"):
        with veritabani.islem() as oturum:
            ti.iliski_tanimla(
                oturum, demo.surum_id, "KULLANIR", "Başka", demo.cihaz_id, demo.kisi_id
            )

    assert _sayi(veritabani, tt.ILISKI_TANIMI) == 1


@pytest.mark.parametrize("rol", ["kaynak", "hedef"])
def test_baska_surumdeki_tur_iliskiye_baglanamaz(
    veritabani: vt.Veritabani, demo: Demo, rol: str
) -> None:
    """Yanlış paket/sürüm ilişkisi: tür başka sürümde, ilişki bu sürümde."""
    with veritabani.islem() as oturum:
        surum2 = ti.surum_tanimla(oturum, demo.paket_id, 2)
        yabanci = ti.nesne_turu_tanimla(oturum, surum2.id, "TEST_ARAC", "Araç")

    kaynak, hedef = (
        (yabanci.id, demo.cihaz_id) if rol == "kaynak" else (demo.kisi_id, yabanci.id)
    )
    with pytest.raises(ti.TanimSurumuUyusmuyor, match=f"{rol} türü 'TEST_ARAC'"):
        with veritabani.islem() as oturum:
            ti.iliski_tanimla(
                oturum, demo.surum_id, "KULLANIR", "Kullanır", kaynak, hedef
            )

    assert _sayi(veritabani, tt.ILISKI_TANIMI) == 0


def test_capraz_surum_iliskisi_veritabaninda_da_reddedilir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    """Bileşik dış anahtar: (tür, sürüm) çifti nesne_turu'nda birlikte olmalı."""
    with veritabani.islem() as oturum:
        surum2 = ti.surum_tanimla(oturum, demo.paket_id, 2)
        yabanci = ti.nesne_turu_tanimla(oturum, surum2.id, "TEST_ARAC", "Araç")

    ekle = text(
        "INSERT INTO iliski_tanimi (tanim_surumu_id, kod, gosterim_adi, "
        "kaynak_nesne_turu_id, hedef_nesne_turu_id) "
        "VALUES (:surum, 'KULLANIR', 'Kullanır', :kaynak, :hedef)"
    )
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with veritabani.islem() as oturum:
            oturum.execute(
                ekle,
                {"surum": demo.surum_id, "kaynak": yabanci.id, "hedef": demo.cihaz_id},
            )
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with veritabani.islem() as oturum:
            oturum.execute(
                ekle,
                {"surum": demo.surum_id, "kaynak": demo.kisi_id, "hedef": yabanci.id},
            )
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with veritabani.islem() as oturum:
            oturum.execute(ekle, {"surum": demo.surum_id, "kaynak": 999, "hedef": 998})

    # Aynı sürümdeki çift geçer: kısıt gerçek ihlali ayırt ediyor.
    with veritabani.islem() as oturum:
        oturum.execute(
            ekle,
            {"surum": demo.surum_id, "kaynak": demo.kisi_id, "hedef": demo.cihaz_id},
        )
    assert _sayi(veritabani, tt.ILISKI_TANIMI) == 1


def test_olmayan_tur_iliskiye_baglanamaz(veritabani: vt.Veritabani, demo: Demo) -> None:
    with pytest.raises(ti.TanimBulunamadi, match="nesne türü bulunamadı: kimlik 999"):
        with veritabani.islem() as oturum:
            ti.iliski_tanimla(
                oturum, demo.surum_id, "KULLANIR", "Kullanır", demo.kisi_id, 999
            )


# --- kayıt türü ve kayıt alanı --------------------------------------------------------


def test_kayit_turu_tanimlanir(veritabani: vt.Veritabani, demo: Demo) -> None:
    with veritabani.islem() as oturum:
        [olay] = ti.kayit_turlerini_listele(oturum, demo.surum_id)
        assert (olay.id, olay.kod, olay.gosterim_adi) == (
            demo.olay_id,
            "TEST_OLAY",
            "Olay",
        )
        assert olay.tanim_surumu_id == demo.surum_id


def test_ayni_surumde_ayni_kayit_turu_kodu_reddedilir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    with pytest.raises(ti.MukerrerTanim, match="'TEST_OLAY' bu sürümde zaten var"):
        with veritabani.islem() as oturum:
            ti.kayit_turu_tanimla(oturum, demo.surum_id, "TEST_OLAY", "Başka")

    assert _sayi(veritabani, tt.KAYIT_TURU) == 1


def test_nesne_turu_ve_kayit_turu_ayni_kodu_tasiyabilir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    """Kapsamlar ayrı: nesne türü kodu ile kayıt türü kodu çakışmaz."""
    with veritabani.islem() as oturum:
        ti.kayit_turu_tanimla(oturum, demo.surum_id, "TEST_KISI", "Kişi olayı")

    assert _sayi(veritabani, tt.KAYIT_TURU) == 2


def test_olmayan_surume_kayit_turu_eklenemez(veritabani: vt.Veritabani) -> None:
    with pytest.raises(ti.TanimBulunamadi, match="tanım sürümü bulunamadı"):
        with veritabani.islem() as oturum:
            ti.kayit_turu_tanimla(oturum, 999, "TEST_OLAY", "Olay")


def test_kayit_alani_kayit_turune_baglanir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    with veritabani.islem() as oturum:
        aciklama = ti.kayit_alani_tanimla(
            oturum, demo.olay_id, "aciklama", "Açıklama", DegerTuru.METIN
        )
        miktar = ti.kayit_alani_tanimla(
            oturum, demo.olay_id, "miktar", "Miktar", DegerTuru.ONDALIK
        )

    with veritabani.islem() as oturum:
        alanlar = ti.kayit_alani_tanimlarini_listele(oturum, demo.olay_id)
        assert [(a.id, a.kod, a.gosterim_adi) for a in alanlar] == [
            (aciklama.id, "aciklama", "Açıklama"),
            (miktar.id, "miktar", "Miktar"),
        ]
        assert all(a.kayit_turu_id == demo.olay_id for a in alanlar)


def test_ayni_kayit_turunde_ayni_alan_kodu_reddedilir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    with veritabani.islem() as oturum:
        ti.kayit_alani_tanimla(
            oturum, demo.olay_id, "miktar", "Miktar", DegerTuru.ONDALIK
        )

    with pytest.raises(ti.MukerrerTanim, match="'miktar' kayıt türü 'TEST_OLAY'"):
        with veritabani.islem() as oturum:
            ti.kayit_alani_tanimla(
                oturum, demo.olay_id, "miktar", "Yine miktar", DegerTuru.METIN
            )

    assert _sayi(veritabani, tt.KAYIT_ALANI_TANIMI) == 1


def test_kayit_alani_deger_turu_ve_zorunlulugu_saklanir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    """Değer türü ve zorunluluk kayıt alanı tanımının parçasıdır (Aşama 4.7);
    varsayılan isteğe bağlıdır."""
    with veritabani.islem() as oturum:
        ti.kayit_alani_tanimla(
            oturum, demo.olay_id, "adet", "Adet", DegerTuru.TAM_SAYI, zorunlu=True
        )
        ti.kayit_alani_tanimla(oturum, demo.olay_id, "not", "Not", DegerTuru.METIN)

    with veritabani.islem() as oturum:
        alanlar = ti.kayit_alani_tanimlarini_listele(oturum, demo.olay_id)
        assert [(a.kod, a.deger_turu, a.zorunlu) for a in alanlar] == [
            ("adet", "tam_sayi", True),
            ("not", "metin", False),
        ]


def test_kayit_alani_gecersiz_deger_turu_reddedilir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    tur: Any = "sayi"
    with pytest.raises(ti.GecersizTanim, match="değer türü geçersiz"):
        with veritabani.islem() as oturum:
            ti.kayit_alani_tanimla(oturum, demo.olay_id, "adet", "Adet", tur)

    assert _sayi(veritabani, tt.KAYIT_ALANI_TANIMI) == 0


def test_kayit_alani_zorunlulugu_mantiksal_olmali(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    """Tip ipucu çalışma zamanında denetlemez: ``1`` mantıksal değildir."""
    zorunlu: Any = 1
    with pytest.raises(ti.GecersizTanim, match="mantıksal olmalı"):
        with veritabani.islem() as oturum:
            ti.kayit_alani_tanimla(
                oturum, demo.olay_id, "adet", "Adet", DegerTuru.TAM_SAYI, zorunlu
            )

    assert _sayi(veritabani, tt.KAYIT_ALANI_TANIMI) == 0


def test_kayit_alani_deger_turu_veritabaninda_da_dogrulanir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    """Servis atlansa bile kontrol kısıtı tanımsız değer türünü reddeder."""
    with pytest.raises(IntegrityError, match="CHECK constraint failed"):
        with veritabani.islem() as oturum:
            oturum.execute(
                text(
                    "INSERT INTO kayit_alani_tanimi (kayit_turu_id, kod, "
                    "gosterim_adi, deger_turu, zorunlu) "
                    f"VALUES ({demo.olay_id}, 'adet', 'Adet', 'sayi', 0)"
                )
            )

    assert _sayi(veritabani, tt.KAYIT_ALANI_TANIMI) == 0


def test_olmayan_kayit_turune_alan_eklenemez(veritabani: vt.Veritabani) -> None:
    with pytest.raises(ti.TanimBulunamadi, match="kayıt türü bulunamadı"):
        with veritabani.islem() as oturum:
            ti.kayit_alani_tanimla(oturum, 999, "miktar", "Miktar", DegerTuru.METIN)


def test_kayit_alani_dis_anahtari_veritabaninda_calisir(
    veritabani: vt.Veritabani,
) -> None:
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with veritabani.islem() as oturum:
            oturum.execute(
                text(
                    "INSERT INTO kayit_alani_tanimi (kayit_turu_id, kod, gosterim_adi) "
                    "VALUES (999, 'miktar', 'Miktar')"
                )
            )


# --- özellik değer türü ve zorunluluk (Aşama 4.3) -------------------------------------


def test_ozellik_deger_turu_ve_zorunlu_saklanir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    with veritabani.islem() as oturum:
        for kod, tur in (
            ("seri_no", DegerTuru.METIN),
            ("adet", DegerTuru.TAM_SAYI),
            ("aktif", DegerTuru.MANTIKSAL),
            ("agirlik", DegerTuru.ONDALIK),
        ):
            ti.ozellik_tanimla(oturum, demo.cihaz_id, kod, kod, tur, zorunlu=True)
    with veritabani.islem() as oturum:
        assert [
            (o.kod, o.deger_turu, o.zorunlu)
            for o in ti.ozellik_tanimlarini_listele(oturum, demo.cihaz_id)
        ] == [
            ("seri_no", "metin", True),
            ("adet", "tam_sayi", True),
            ("aktif", "mantiksal", True),
            ("agirlik", "ondalik", True),
        ]


def test_gecersiz_deger_turu_ve_zorunlu_reddedilir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    tur: Any = "tarih"
    with pytest.raises(ti.GecersizTanim, match="değer türü geçersiz"):
        with veritabani.islem() as oturum:
            ti.ozellik_tanimla(oturum, demo.cihaz_id, "x", "X", tur)
    zorunlu: Any = 1
    with pytest.raises(ti.GecersizTanim, match="mantıksal"):
        with veritabani.islem() as oturum:
            ti.ozellik_tanimla(
                oturum, demo.cihaz_id, "x", "X", DegerTuru.METIN, zorunlu
            )
    with pytest.raises(IntegrityError, match="CHECK constraint failed"):
        with veritabani.islem() as oturum:
            oturum.execute(
                text(
                    "INSERT INTO ozellik_tanimi (nesne_turu_id, kod, gosterim_adi, "
                    "deger_turu, zorunlu) VALUES (:t, 'x', 'X', 'tarih', 0)"
                ),
                {"t": demo.cihaz_id},
            )
    assert _sayi(veritabani, tt.OZELLIK_TANIMI) == 0


# --- hiyerarşi kuralı (Aşama 4.3) -----------------------------------------------------


def _iliski(veritabani: vt.Veritabani, demo: Demo) -> int:
    with veritabani.islem() as oturum:
        return ti.iliski_tanimla(
            oturum, demo.surum_id, "KULLANIR", "Kullanır", demo.cihaz_id, demo.kisi_id
        ).id


def test_hiyerarsi_kurali_tanimlanir_ve_listelenir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    iliski = _iliski(veritabani, demo)
    with veritabani.islem() as oturum:
        kural = ti.hiyerarsi_kurali_tanimla(oturum, iliski, 1, 2, YasamDurumu.ETKIN)
    with veritabani.islem() as oturum:
        [bulunan] = ti.hiyerarsi_kurallarini_listele(oturum, demo.surum_id)
        assert (
            bulunan.id,
            bulunan.iliski_tanimi_id,
            bulunan.en_az_ust,
            bulunan.en_cok_ust,
            bulunan.ust_yasam_durumu,
        ) == (kural.id, iliski, 1, 2, "etkin")
    with veritabani.islem() as oturum:  # sınırsız ve durumsuz kural
        iliski2 = ti.iliski_tanimla(
            oturum, demo.surum_id, "TANIR", "Tanır", demo.kisi_id, demo.kisi_id
        )
        kural2 = ti.hiyerarsi_kurali_tanimla(oturum, iliski2.id, 0, None)
        assert (kural2.en_cok_ust, kural2.ust_yasam_durumu) == (None, None)


@pytest.mark.parametrize(
    ("en_az", "en_cok", "durum", "hata"),
    [
        (-1, None, None, "negatif"),
        (2, 1, None, "küçük olmamalı"),
        (0, 0, None, "en az 1"),
        (1.0, None, None, "tam sayı"),
        (True, None, None, "tam sayı"),
        (1, "2", None, "tam sayı"),
        (1, None, "askida", "üst yaşam durumu geçersiz"),
    ],
)
def test_gecersiz_hiyerarsi_kurali_reddedilir(
    veritabani: vt.Veritabani,
    demo: Demo,
    en_az: Any,
    en_cok: Any,
    durum: Any,
    hata: str,
) -> None:
    iliski = _iliski(veritabani, demo)
    with pytest.raises(ti.GecersizTanim, match=hata):
        with veritabani.islem() as oturum:
            ti.hiyerarsi_kurali_tanimla(oturum, iliski, en_az, en_cok, durum)
    assert _sayi(veritabani, tt.HIYERARSI_KURALI) == 0


def test_hiyerarsi_kurali_kisitlari_veritabaninda_calisir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    iliski = _iliski(veritabani, demo)
    ekle = (
        "INSERT INTO hiyerarsi_kurali (iliski_tanimi_id, en_az_ust, en_cok_ust, "
        "ust_yasam_durumu) VALUES (:i, :az, :cok, :d)"
    )
    for az, cok, d in (
        (-1, None, None),
        (2, 1, None),
        (0, 0, None),
        (1.5, None, None),
        (0, None, "askida"),
    ):
        with pytest.raises(IntegrityError, match="CHECK constraint failed"):
            with veritabani.islem() as oturum:
                oturum.execute(text(ekle), {"i": iliski, "az": az, "cok": cok, "d": d})
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with veritabani.islem() as oturum:
            oturum.execute(text(ekle), {"i": 999, "az": 0, "cok": None, "d": None})
    with veritabani.islem() as oturum:
        oturum.execute(text(ekle), {"i": iliski, "az": 1, "cok": 1, "d": "etkin"})
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        with veritabani.islem() as oturum:
            oturum.execute(text(ekle), {"i": iliski, "az": 0, "cok": None, "d": None})
    assert _sayi(veritabani, tt.HIYERARSI_KURALI) == 1


def test_ayni_iliskiye_ikinci_kural_ve_olmayan_iliski_reddedilir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    iliski = _iliski(veritabani, demo)
    with veritabani.islem() as oturum:
        ti.hiyerarsi_kurali_tanimla(oturum, iliski, 0, None)
    with pytest.raises(ti.MukerrerTanim, match="hiyerarşi kuralı zaten var"):
        with veritabani.islem() as oturum:
            ti.hiyerarsi_kurali_tanimla(oturum, iliski, 1, None)
    with pytest.raises(ti.TanimBulunamadi, match="ilişki tanımı bulunamadı"):
        with veritabani.islem() as oturum:
            ti.hiyerarsi_kurali_tanimla(oturum, 999, 0, None)
    with veritabani.islem() as oturum:
        with pytest.raises(ti.TanimBulunamadi):
            ti.hiyerarsi_kurallarini_listele(oturum, 999)


# --- listeleme ve okuma sözleşmesi ----------------------------------------------------


def test_olmayan_ust_kayit_icin_listeleme_hata_verir(veritabani: vt.Veritabani) -> None:
    """Boş liste ile 'üst kayıt yok' karışmaz."""
    with veritabani.islem() as oturum:
        with pytest.raises(ti.TanimBulunamadi):
            ti.surumleri_listele(oturum, 999)
        with pytest.raises(ti.TanimBulunamadi):
            ti.nesne_turlerini_listele(oturum, 999)
        with pytest.raises(ti.TanimBulunamadi):
            ti.ozellik_tanimlarini_listele(oturum, 999)
        with pytest.raises(ti.TanimBulunamadi):
            ti.iliski_tanimlarini_listele(oturum, 999)
        with pytest.raises(ti.TanimBulunamadi):
            ti.kayit_turlerini_listele(oturum, 999)
        with pytest.raises(ti.TanimBulunamadi):
            ti.kayit_alani_tanimlarini_listele(oturum, 999)


def test_hatalar_ortak_tabandan_turer() -> None:
    for sinif in (
        ti.GecersizTanim,
        ti.TanimBulunamadi,
        ti.MukerrerTanim,
        ti.TanimSurumuUyusmuyor,
    ):
        assert issubclass(sinif, ti.TanimHatasi)
    assert issubclass(ti.GecersizTanim, ValueError)
    assert issubclass(ti.TanimBulunamadi, LookupError)


# --- işlem sınırı ---------------------------------------------------------------------


def test_islem_icindeki_hata_butun_tanimlari_geri_alir(
    veritabani: vt.Veritabani,
) -> None:
    with pytest.raises(RuntimeError, match="sentetik"):
        with veritabani.islem() as oturum:
            paket = ti.paket_tanimla(oturum, "DEMO", "Demo")
            surum = ti.surum_tanimla(oturum, paket.id, 1)
            tur = ti.nesne_turu_tanimla(oturum, surum.id, "TEST_KISI", "Kişi")
            ti.ozellik_tanimla(oturum, tur.id, "ad", "Ad", DegerTuru.METIN)
            raise RuntimeError("sentetik hata")

    for tablo in tt.TANIM_TABLOLARI:
        assert _sayi(veritabani, tablo) == 0, tablo


def test_mukerrerlik_hatasi_ayni_islemdeki_onceki_yazmalari_da_geri_alir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    with pytest.raises(ti.MukerrerTanim):
        with veritabani.islem() as oturum:
            ti.nesne_turu_tanimla(oturum, demo.surum_id, "TEST_ARAC", "Araç")
            ti.ozellik_tanimla(
                oturum, demo.cihaz_id, "seri_no", "Seri", DegerTuru.METIN
            )
            ti.nesne_turu_tanimla(oturum, demo.surum_id, "TEST_KISI", "kopya")

    assert _sayi(veritabani, tt.NESNE_TURU) == 2  # TEST_ARAC kalmadı
    assert _sayi(veritabani, tt.OZELLIK_TANIMI) == 0


def test_veritabani_kisit_hatasindan_sonra_kullanilabilir_kalir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    with pytest.raises(IntegrityError):
        with veritabani.islem() as oturum:
            ti.ozellik_tanimla(
                oturum, demo.cihaz_id, "seri_no", "Seri", DegerTuru.METIN
            )
            oturum.execute(
                text(
                    "INSERT INTO nesne_turu (tanim_surumu_id, kod, gosterim_adi) "
                    "VALUES (:surum, 'TEST_KISI', 'kopya')"
                ),
                {"surum": demo.surum_id},
            )

    assert _sayi(veritabani, tt.OZELLIK_TANIMI) == 0
    with veritabani.islem() as oturum:
        ti.ozellik_tanimla(oturum, demo.cihaz_id, "seri_no", "Seri", DegerTuru.METIN)
        assert oturum.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"
    assert _sayi(veritabani, tt.OZELLIK_TANIMI) == 1


def test_donen_nesneler_islem_kapaninca_okunabilir(veritabani: vt.Veritabani) -> None:
    """``expire_on_commit=False``: sütunlar elde kalır; gecikmeli yükleme yoktur."""
    with veritabani.islem() as oturum:
        paket = ti.paket_tanimla(oturum, "DEMO", "Demo")
        surum = ti.surum_tanimla(oturum, paket.id, 1)

    assert (paket.kod, surum.tanim_paketi_id, surum.surum_no) == ("DEMO", paket.id, 1)


# --- çekirdek domain bilmez -----------------------------------------------------------


def test_iki_farkli_sahte_domain_ayni_mekanizmayla_tanimlanir(
    veritabani: vt.Veritabani, demo: Demo
) -> None:
    """Plan madde 20: finans dışı iki paket aynı tablolarda, aynı işlevlerle."""
    with veritabani.islem() as oturum:
        envanter = ti.paket_tanimla(oturum, "ENVANTER", "Envanter")
        surum = ti.surum_tanimla(oturum, envanter.id, 1)
        depo = ti.nesne_turu_tanimla(oturum, surum.id, "DEPO", "Depo")
        raf = ti.nesne_turu_tanimla(oturum, surum.id, "RAF", "Raf")
        urun = ti.nesne_turu_tanimla(oturum, surum.id, "URUN", "Ürün")
        ti.ozellik_tanimla(oturum, urun.id, "barkod", "Barkod", DegerTuru.METIN)
        ti.iliski_tanimla(oturum, surum.id, "ICERIR", "İçerir", depo.id, raf.id)
        ti.iliski_tanimla(oturum, surum.id, "TASIR", "Taşır", raf.id, urun.id)
        sayim = ti.kayit_turu_tanimla(oturum, surum.id, "SAYIM", "Sayım")
        ti.kayit_alani_tanimla(oturum, sayim.id, "adet", "Adet", DegerTuru.TAM_SAYI)

    with veritabani.islem() as oturum:
        assert [p.kod for p in ti.paketleri_listele(oturum)] == ["DEMO", "ENVANTER"]
        assert [t.kod for t in ti.nesne_turlerini_listele(oturum, surum.id)] == [
            "DEPO",
            "RAF",
            "URUN",
        ]
        assert [t.kod for t in ti.nesne_turlerini_listele(oturum, demo.surum_id)] == [
            "TEST_CIHAZ",
            "TEST_KISI",
        ]
        assert [i.kod for i in ti.iliski_tanimlarini_listele(oturum, surum.id)] == [
            "ICERIR",
            "TASIR",
        ]
