"""Kesin kayıt testleri (Aşama 4.7): şema (4.7/2) ve servis (4.7/3).

Gerçek SQLite dosyası, ``test`` ortamı, ``tmp_path`` altında kök; şema gerçek
göç zinciriyle kurulur. Tanım paketi finans dışı sahte ``ENVANTER``
dünyasıdır: ``RAF`` türü, ``SAYIM`` ve ``DENETIM`` kayıt türleri. Çekirdek
bunların anlamını bilmez; hepsi tanım verisidir.

İki düzey sınanır. Şema bölümünde satırlar **ham SQL** ile yazılır: bileşik
dış anahtarlar, benzersizlikler ve zorunluluklar servis atlansa da aynı
ihlalleri reddetmelidir. Servis bölümünde ``kayit_islemleri.kayit_olustur``
sınanır: doğrulama mutasyondan önce biter, kayıt alanları ve bağlarıyla tek
işte doğar, hata hiçbir parça bırakmaz.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from defteriki import ayarlar as ay
from defteriki.cekirdek import belge_islemleri as bi
from defteriki.cekirdek import denetim_islemleri as di
from defteriki.cekirdek import denetim_tablolari as dnt
from defteriki.cekirdek import gocler
from defteriki.cekirdek import kayit_islemleri as ki
from defteriki.cekirdek import kayit_tablolari as kt
from defteriki.cekirdek import nesne_islemleri as ni
from defteriki.cekirdek import tanim_islemleri as ti
from defteriki.cekirdek import taslak_islemleri as tsi
from defteriki.cekirdek import veritabani as vt
from defteriki.cekirdek.denetim_tablolari import Aktor, AktorTuru
from defteriki.cekirdek.tanim_tablolari import DegerTuru, YasamDurumu

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
OKUMA_ICERIGI: dict[str, Any] = {"satirlar": [{"raf": "A1", "adet": 12}]}
AJAN = Aktor(AktorTuru.AJAN, "test-ajan")
KULLANICI = Aktor(AktorTuru.KULLANICI, "test-kullanici")


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
    """``ENVANTER`` paketinin kimlikleri; sürüm 2 yalnız sürüm sınırını
    sınamak için vardır."""

    surum_id: int
    ikinci_surum_id: int
    raf_id: int
    sayim_id: int
    denetim_id: int
    ikinci_surum_sayim_id: int
    adet_id: int
    not_id: int
    denetim_alani_id: int
    nesne_id: int


@pytest.fixture
def env(ortam: Ortam) -> Envanter:
    with ortam.veritabani.islem() as o:
        paket = ti.paket_tanimla(o, "ENVANTER", "Envanter")
        surum = ti.surum_tanimla(o, paket.id, 1)
        ikinci = ti.surum_tanimla(o, paket.id, 2)
        raf = ti.nesne_turu_tanimla(o, surum.id, "RAF", "Raf")
        ti.ozellik_tanimla(o, raf.id, "kod", "Kod", DegerTuru.METIN, zorunlu=True)
        sayim = ti.kayit_turu_tanimla(o, surum.id, "SAYIM", "Sayım")
        adet = ti.kayit_alani_tanimla(
            o, sayim.id, "adet", "Adet", DegerTuru.TAM_SAYI, zorunlu=True
        )
        notu = ti.kayit_alani_tanimla(o, sayim.id, "not", "Not", DegerTuru.METIN)
        denetim = ti.kayit_turu_tanimla(o, surum.id, "DENETIM", "Denetim")
        denetim_alani = ti.kayit_alani_tanimla(
            o, denetim.id, "sonuc", "Sonuç", DegerTuru.METIN, zorunlu=True
        )
        ti.kayit_alani_tanimla(o, denetim.id, "agirlik", "Ağırlık", DegerTuru.ONDALIK)
        ti.kayit_alani_tanimla(o, denetim.id, "gecerli", "Geçerli", DegerTuru.MANTIKSAL)
        ikinci_sayim = ti.kayit_turu_tanimla(o, ikinci.id, "SAYIM", "Sayım")
        nesne = ni.nesne_olustur(o, raf.id, {"kod": "A1"})
        return Envanter(
            surum.id,
            ikinci.id,
            raf.id,
            sayim.id,
            denetim.id,
            ikinci_sayim.id,
            adet.id,
            notu.id,
            denetim_alani.id,
            nesne.id,
        )


# --- yardımcılar ----------------------------------------------------------------------


def _paket(o: Ortam, ad: str = "envanter.pdf", icerik: bytes = PDF) -> tuple[int, int]:
    """Belge → okuma → paket zinciri; ``(paket_id, okuma_id)`` döndürür."""
    yol = o.gelen / ad
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_bytes(icerik)
    belge_id = bi.belge_al(
        o.veritabani, yol, gelen_dizini=o.gelen, arsiv_dizini=o.arsiv
    ).belge.id
    with o.veritabani.islem() as oturum:
        okuma = bi.okuma_baslat(oturum, belge_id, o.arsiv)
        bi.okuma_tamamla(oturum, okuma.id, OKUMA_ICERIGI)
        okuma_id = okuma.id
    with o.veritabani.islem() as oturum:
        return tsi.paket_olustur(oturum, okuma_id).id, okuma_id


def _kaynak(o: Ortam, okuma_id: int) -> int:
    with o.veritabani.islem() as oturum:
        return bi.kaynak_olustur(oturum, okuma_id, {"satir": 1}).id


def _kayit_yaz(
    o: Ortam,
    *,
    kayit_turu_id: int,
    tanim_surumu_id: int,
    islem_paketi_id: int,
    okuma_id: int,
    kaynak_id: int | None = None,
) -> int:
    """Ham SQL ile kesin kayıt satırı (servis 4.7/3'te gelir)."""
    with o.veritabani.islem() as oturum:
        oturum.execute(
            text(
                "INSERT INTO kayit (kayit_turu_id, tanim_surumu_id, islem_paketi_id, "
                "okuma_id, kaynak_id, olusturma_zamani) VALUES (:t, :s, :p, :o, :k, "
                "'2026-09-21 00:00:00')"
            ),
            {
                "t": kayit_turu_id,
                "s": tanim_surumu_id,
                "p": islem_paketi_id,
                "o": okuma_id,
                "k": kaynak_id,
            },
        )
        return int(oturum.execute(text("SELECT max(id) FROM kayit")).scalar_one())


def _sayi(o: Ortam, tablo: str) -> int:
    with o.veritabani.islem() as oturum:
        return int(oturum.execute(text(f"SELECT count(*) FROM {tablo}")).scalar_one())


# --- şemanın kendisi ------------------------------------------------------------------


def test_kayit_durum_sutunu_tasimaz(ortam: Ortam) -> None:
    """Karar 2026-09-21: satırın varlığı kesinliktir; taslak / kesinleşme
    durumu kesin kayıt tablosunda yoktur."""
    with ortam.veritabani.motor.connect() as baglanti:
        sutunlar = {s["name"] for s in inspect(baglanti).get_columns(kt.KAYIT)}
    assert sutunlar == {
        "id",
        "kayit_turu_id",
        "tanim_surumu_id",
        "islem_paketi_id",
        "okuma_id",
        "kaynak_id",
        "olusturma_zamani",
    }


def test_denetim_izi_kayit_sabiti_gercek_tabloyla_ayni() -> None:
    """``denetim_tablolari`` kayıt şemasını import etmez (taslak → denetim →
    kesin nesne zinciri olurdu); adın doğruluğu burada korunur."""
    assert dnt.KESIN_KAYIT == kt.KAYIT


def test_kayit_yazilir_ve_kokenini_tasir(ortam: Ortam, env: Envanter) -> None:
    paket_id, okuma_id = _paket(ortam)
    kaynak_id = _kaynak(ortam, okuma_id)
    kayit_id = _kayit_yaz(
        ortam,
        kayit_turu_id=env.sayim_id,
        tanim_surumu_id=env.surum_id,
        islem_paketi_id=paket_id,
        okuma_id=okuma_id,
        kaynak_id=kaynak_id,
    )
    with ortam.veritabani.islem() as oturum:
        oturum.execute(
            text(
                "INSERT INTO kayit_alani (kayit_id, kayit_turu_id, "
                "kayit_alani_tanimi_id, deger) VALUES (:k, :t, :a, '12')"
            ),
            {"k": kayit_id, "t": env.sayim_id, "a": env.adet_id},
        )
        oturum.execute(
            text("INSERT INTO kayit_nesne (kayit_id, nesne_id) VALUES (:k, :n)"),
            {"k": kayit_id, "n": env.nesne_id},
        )
    with ortam.veritabani.islem() as oturum:
        assert oturum.execute(
            text("SELECT islem_paketi_id, okuma_id, kaynak_id FROM kayit")
        ).all() == [(paket_id, okuma_id, kaynak_id)]
        assert oturum.execute(text("PRAGMA foreign_key_check")).all() == []


# --- köken (provenance) ---------------------------------------------------------------


def test_kayit_paketsiz_yazilamaz(ortam: Ortam, env: Envanter) -> None:
    """``islem_paketi_id`` zorunludur (karar 2026-09-21): kesin kayıt her zaman
    paket → okuma → belge zincirine dayanır."""
    _, okuma_id = _paket(ortam)
    with pytest.raises(IntegrityError, match="NOT NULL"):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(
                text(
                    "INSERT INTO kayit (kayit_turu_id, tanim_surumu_id, okuma_id, "
                    "olusturma_zamani) VALUES (:t, :s, :o, '2026-09-21')"
                ),
                {"t": env.sayim_id, "s": env.surum_id, "o": okuma_id},
            )
    assert _sayi(ortam, kt.KAYIT) == 0


def test_kayit_okumasi_paketin_okumasi_olmali(ortam: Ortam, env: Envanter) -> None:
    paket_id, _ = _paket(ortam)
    _, baska_okuma = _paket(ortam, "ikinci.pdf", PDF2)
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        _kayit_yaz(
            ortam,
            kayit_turu_id=env.sayim_id,
            tanim_surumu_id=env.surum_id,
            islem_paketi_id=paket_id,
            okuma_id=baska_okuma,
        )
    assert _sayi(ortam, kt.KAYIT) == 0


def test_kayit_kaynagi_ayni_okumadan_olmali(ortam: Ortam, env: Envanter) -> None:
    paket_id, okuma_id = _paket(ortam)
    _, baska_okuma = _paket(ortam, "ikinci.pdf", PDF2)
    baska_kaynak = _kaynak(ortam, baska_okuma)
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        _kayit_yaz(
            ortam,
            kayit_turu_id=env.sayim_id,
            tanim_surumu_id=env.surum_id,
            islem_paketi_id=paket_id,
            okuma_id=okuma_id,
            kaynak_id=baska_kaynak,
        )
    assert _sayi(ortam, kt.KAYIT) == 0


def test_kayit_turu_kendi_surumunde_olmali(ortam: Ortam, env: Envanter) -> None:
    """Tür ve sürüm iki rastgele kimlik değildir: ikinci sürümün ``SAYIM``ı
    birinci sürümle yazılamaz."""
    paket_id, okuma_id = _paket(ortam)
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        _kayit_yaz(
            ortam,
            kayit_turu_id=env.ikinci_surum_sayim_id,
            tanim_surumu_id=env.surum_id,
            islem_paketi_id=paket_id,
            okuma_id=okuma_id,
        )
    assert _sayi(ortam, kt.KAYIT) == 0


# --- alanlar --------------------------------------------------------------------------


def test_kayit_alani_baska_turun_alani_olamaz(ortam: Ortam, env: Envanter) -> None:
    paket_id, okuma_id = _paket(ortam)
    kayit_id = _kayit_yaz(
        ortam,
        kayit_turu_id=env.sayim_id,
        tanim_surumu_id=env.surum_id,
        islem_paketi_id=paket_id,
        okuma_id=okuma_id,
    )
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(
                text(
                    "INSERT INTO kayit_alani (kayit_id, kayit_turu_id, "
                    "kayit_alani_tanimi_id, deger) VALUES (:k, :t, :a, 'x')"
                ),
                {"k": kayit_id, "t": env.sayim_id, "a": env.denetim_alani_id},
            )
    assert _sayi(ortam, kt.KAYIT_ALANI) == 0


def test_kayit_alani_kaydin_turunu_tasimali(ortam: Ortam, env: Envanter) -> None:
    """Alan satırı kaydın türünü taşır; başka tür yazılırsa hem kayda hem alan
    tanımına giden bileşik dış anahtarlar düşer."""
    paket_id, okuma_id = _paket(ortam)
    kayit_id = _kayit_yaz(
        ortam,
        kayit_turu_id=env.sayim_id,
        tanim_surumu_id=env.surum_id,
        islem_paketi_id=paket_id,
        okuma_id=okuma_id,
    )
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(
                text(
                    "INSERT INTO kayit_alani (kayit_id, kayit_turu_id, "
                    "kayit_alani_tanimi_id, deger) VALUES (:k, :t, :a, 'x')"
                ),
                {"k": kayit_id, "t": env.denetim_id, "a": env.denetim_alani_id},
            )
    assert _sayi(ortam, kt.KAYIT_ALANI) == 0


def test_ayni_alan_kayitta_iki_kez_bulunamaz(ortam: Ortam, env: Envanter) -> None:
    paket_id, okuma_id = _paket(ortam)
    kayit_id = _kayit_yaz(
        ortam,
        kayit_turu_id=env.sayim_id,
        tanim_surumu_id=env.surum_id,
        islem_paketi_id=paket_id,
        okuma_id=okuma_id,
    )
    with ortam.veritabani.islem() as oturum:
        oturum.execute(
            text(
                "INSERT INTO kayit_alani (kayit_id, kayit_turu_id, "
                "kayit_alani_tanimi_id, deger) VALUES (:k, :t, :a, '12')"
            ),
            {"k": kayit_id, "t": env.sayim_id, "a": env.adet_id},
        )
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(
                text(
                    "INSERT INTO kayit_alani (kayit_id, kayit_turu_id, "
                    "kayit_alani_tanimi_id, deger) VALUES (:k, :t, :a, '13')"
                ),
                {"k": kayit_id, "t": env.sayim_id, "a": env.adet_id},
            )
    assert _sayi(ortam, kt.KAYIT_ALANI) == 1


# --- nesne bağı -----------------------------------------------------------------------


def test_kayit_nesne_bagi_mukerrer_olamaz(ortam: Ortam, env: Envanter) -> None:
    paket_id, okuma_id = _paket(ortam)
    kayit_id = _kayit_yaz(
        ortam,
        kayit_turu_id=env.sayim_id,
        tanim_surumu_id=env.surum_id,
        islem_paketi_id=paket_id,
        okuma_id=okuma_id,
    )
    with ortam.veritabani.islem() as oturum:
        oturum.execute(
            text("INSERT INTO kayit_nesne (kayit_id, nesne_id) VALUES (:k, :n)"),
            {"k": kayit_id, "n": env.nesne_id},
        )
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(
                text("INSERT INTO kayit_nesne (kayit_id, nesne_id) VALUES (:k, :n)"),
                {"k": kayit_id, "n": env.nesne_id},
            )
    assert _sayi(ortam, kt.KAYIT_NESNE) == 1


def test_kayit_olmayan_nesneye_baglanamaz(ortam: Ortam, env: Envanter) -> None:
    paket_id, okuma_id = _paket(ortam)
    kayit_id = _kayit_yaz(
        ortam,
        kayit_turu_id=env.sayim_id,
        tanim_surumu_id=env.surum_id,
        islem_paketi_id=paket_id,
        okuma_id=okuma_id,
    )
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(
                text("INSERT INTO kayit_nesne (kayit_id, nesne_id) VALUES (:k, 999)"),
                {"k": kayit_id},
            )
    assert _sayi(ortam, kt.KAYIT_NESNE) == 0


def test_kayit_baska_surumdeki_nesneye_baglanabilir(
    ortam: Ortam, env: Envanter
) -> None:
    """Karar 2026-09-21: sürüm eşitliği aranmaz. İkinci sürümde üretilen kayıt,
    birinci sürümde doğmuş etkin nesneye bağlanabilir."""
    paket_id, okuma_id = _paket(ortam)
    kayit_id = _kayit_yaz(
        ortam,
        kayit_turu_id=env.ikinci_surum_sayim_id,
        tanim_surumu_id=env.ikinci_surum_id,
        islem_paketi_id=paket_id,
        okuma_id=okuma_id,
    )
    with ortam.veritabani.islem() as oturum:
        oturum.execute(
            text("INSERT INTO kayit_nesne (kayit_id, nesne_id) VALUES (:k, :n)"),
            {"k": kayit_id, "n": env.nesne_id},
        )
        assert oturum.execute(text("PRAGMA foreign_key_check")).all() == []
    assert _sayi(ortam, kt.KAYIT_NESNE) == 1


# --- denetim izi ----------------------------------------------------------------------


def test_denetim_izi_kayda_baglanir_ve_kayit_silinemez(
    ortam: Ortam, env: Envanter
) -> None:
    """İz kayda dış anahtarla bağlanır ve ``RESTRICT``tir: ize konu olan kayıt
    sessizce silinemez."""
    paket_id, okuma_id = _paket(ortam)
    kayit_id = _kayit_yaz(
        ortam,
        kayit_turu_id=env.sayim_id,
        tanim_surumu_id=env.surum_id,
        islem_paketi_id=paket_id,
        okuma_id=okuma_id,
    )
    with ortam.veritabani.islem() as oturum:
        oturum.execute(
            text(
                "INSERT INTO denetim_izi (olay, olay_zamani, aktor_turu, "
                "aktor_kimligi, kayit_id) VALUES ('kayit_olusturuldu', "
                "'2026-09-21', 'ajan', 'test', :k)"
            ),
            {"k": kayit_id},
        )
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(text("DELETE FROM kayit WHERE id = :k"), {"k": kayit_id})
    assert _sayi(ortam, kt.KAYIT) == 1


def test_denetim_izi_tanimsiz_olayi_reddeder(ortam: Ortam) -> None:
    with pytest.raises(IntegrityError, match="CHECK constraint failed"):
        with ortam.veritabani.islem() as oturum:
            oturum.execute(
                text(
                    "INSERT INTO denetim_izi (olay, olay_zamani, aktor_turu, "
                    "aktor_kimligi) VALUES ('kayit_silindi', '2026-09-21', "
                    "'ajan', 'test')"
                )
            )


# --- kayıt oluşturma servisi (Aşama 4.7/3) --------------------------------------------


def _kayit(
    ortam: Ortam,
    env: Envanter,
    paket_id: int,
    *,
    alanlar: dict[str, Any] | None = None,
    nesneler: list[int] | None = None,
    kaynak_id: int | None = None,
    kayit_turu_id: int | None = None,
) -> int:
    with ortam.veritabani.islem() as oturum:
        return ki.kayit_olustur(
            oturum,
            paket_id,
            kayit_turu_id if kayit_turu_id is not None else env.sayim_id,
            alanlar if alanlar is not None else {"adet": 12},
            nesneler if nesneler is not None else [env.nesne_id],
            AJAN,
            kaynak_id=kaynak_id,
        ).id


def test_servis_kaydi_alanlari_ve_baglariyla_yazar(ortam: Ortam, env: Envanter) -> None:
    paket_id, okuma_id = _paket(ortam)
    kaynak_id = _kaynak(ortam, okuma_id)
    kayit_id = _kayit(
        ortam,
        env,
        paket_id,
        alanlar={"adet": 12, "not": "ç ğ ş"},
        kaynak_id=kaynak_id,
    )
    with ortam.veritabani.islem() as oturum:
        kayit = ki.kayit_getir(oturum, kayit_id)
        assert kayit.tanim_surumu_id == env.surum_id  # türden alınır
        assert kayit.okuma_id == okuma_id  # paketten alınır
        assert kayit.kaynak_id == kaynak_id
        assert ki.kayit_alanlarini_oku(oturum, kayit_id) == {"adet": 12, "not": "ç ğ ş"}
        assert ki.kaydin_nesneleri(oturum, kayit_id) == [env.nesne_id]
        assert [k.id for k in ki.nesnenin_kayitlari(oturum, env.nesne_id)] == [kayit_id]
        assert [k.id for k in ki.paketin_kayitlari(oturum, paket_id)] == [kayit_id]


def test_servis_kaydi_kaynaksiz_da_yazar(ortam: Ortam, env: Envanter) -> None:
    """Kaynak isteğe bağlıdır; köken okuma düzeyinde her hâlükârda vardır."""
    paket_id, okuma_id = _paket(ortam)
    kayit_id = _kayit(ortam, env, paket_id)
    with ortam.veritabani.islem() as oturum:
        koken = ki.kaydin_kokeni(oturum, kayit_id)
        assert koken.kaynak_id is None
        assert koken.islem_paketi.id == paket_id
        assert koken.okuma.id == okuma_id
        assert koken.belge.id == koken.okuma.belge_id
        assert koken.arsiv_dosyasi.id == koken.belge.arsiv_dosyasi_id


def test_ondalik_ve_mantiksal_deger_kanonik_saklanir(
    ortam: Ortam, env: Envanter
) -> None:
    """Sayısal değer ``deger_kodlama`` ile kanonik metne çevrilir; ölçek ya da
    birim varsayımı yoktur."""
    paket_id, _ = _paket(ortam)
    kayit_id = _kayit(
        ortam,
        env,
        paket_id,
        alanlar={"sonuc": "tamam", "agirlik": Decimal("12.50"), "gecerli": True},
        kayit_turu_id=env.denetim_id,
    )
    with ortam.veritabani.islem() as oturum:
        okunan = ki.kayit_alanlarini_oku(oturum, kayit_id)
        assert okunan["agirlik"] == Decimal("12.5")
        assert okunan["gecerli"] is True
        ham = oturum.execute(
            text(
                "SELECT deger FROM kayit_alani ka JOIN kayit_alani_tanimi t "
                "ON t.id = ka.kayit_alani_tanimi_id "
                "WHERE ka.kayit_id = :k AND t.kod = 'agirlik'"
            ),
            {"k": kayit_id},
        ).scalar_one()
    assert ham == "125e-1"


def test_float_deger_reddedilir(ortam: Ortam, env: Envanter) -> None:
    paket_id, _ = _paket(ortam)
    with pytest.raises(ki.KayitAlaniDegeriGecersiz, match="ondalik bekler"):
        _kayit(
            ortam,
            env,
            paket_id,
            alanlar={"sonuc": "tamam", "agirlik": 12.5},
            kayit_turu_id=env.denetim_id,
        )
    assert _sayi(ortam, kt.KAYIT) == 0


def test_zorunlu_alan_eksikse_kayit_olusmaz(ortam: Ortam, env: Envanter) -> None:
    """Karar 2026-09-21: eksik kesin kayıt veritabanında bulunamaz; tamlık
    kaydın açılışında denetlenir, 4.8'e bırakılmaz."""
    paket_id, _ = _paket(ortam)
    with pytest.raises(ki.ZorunluKayitAlaniEksik, match="adet"):
        _kayit(ortam, env, paket_id, alanlar={"not": "eksik"})
    assert _sayi(ortam, kt.KAYIT) == 0
    assert _sayi(ortam, kt.KAYIT_ALANI) == 0
    assert _sayi(ortam, kt.KAYIT_NESNE) == 0


def test_tanimsiz_alan_reddedilir(ortam: Ortam, env: Envanter) -> None:
    paket_id, _ = _paket(ortam)
    with pytest.raises(ki.TanimsizKayitAlani, match="'renk' adlı alan tanımı yok"):
        _kayit(ortam, env, paket_id, alanlar={"adet": 1, "renk": "mavi"})
    assert _sayi(ortam, kt.KAYIT) == 0


def test_baska_turun_alani_reddedilir(ortam: Ortam, env: Envanter) -> None:
    """``sonuc`` DENETIM türünün alanıdır; SAYIM kaydına verilemez."""
    paket_id, _ = _paket(ortam)
    with pytest.raises(ki.TanimsizKayitAlani, match="'sonuc'"):
        _kayit(ortam, env, paket_id, alanlar={"adet": 1, "sonuc": "tamam"})
    assert _sayi(ortam, kt.KAYIT) == 0


def test_nesnesiz_kayit_olusmaz(ortam: Ortam, env: Envanter) -> None:
    paket_id, _ = _paket(ortam)
    with pytest.raises(ki.KayitNesneBagiGecersiz, match="en az bir nesneye"):
        _kayit(ortam, env, paket_id, nesneler=[])
    assert _sayi(ortam, kt.KAYIT) == 0


def test_ayni_nesne_iki_kez_verilemez(ortam: Ortam, env: Envanter) -> None:
    paket_id, _ = _paket(ortam)
    with pytest.raises(ki.KayitNesneBagiGecersiz, match="birden fazla kez"):
        _kayit(ortam, env, paket_id, nesneler=[env.nesne_id, env.nesne_id])
    assert _sayi(ortam, kt.KAYIT) == 0


def test_kapali_nesneye_baglanamaz(ortam: Ortam, env: Envanter) -> None:
    paket_id, _ = _paket(ortam)
    with ortam.veritabani.islem() as oturum:
        ni.yasam_durumunu_degistir(oturum, env.nesne_id, YasamDurumu.KAPALI)
    with pytest.raises(ki.KayitNesneBagiGecersiz, match="yalnız etkin"):
        _kayit(ortam, env, paket_id)
    assert _sayi(ortam, kt.KAYIT) == 0


def test_olmayan_nesne_reddedilir(ortam: Ortam, env: Envanter) -> None:
    paket_id, _ = _paket(ortam)
    with pytest.raises(ki.KayitNesneBagiGecersiz, match="nesne bulunamadı"):
        _kayit(ortam, env, paket_id, nesneler=[999])
    assert _sayi(ortam, kt.KAYIT) == 0


def test_baska_okumanin_kaynagi_servis_tarafindan_reddedilir(
    ortam: Ortam, env: Envanter
) -> None:
    paket_id, _ = _paket(ortam)
    _, baska_okuma = _paket(ortam, "ikinci.pdf", PDF2)
    baska_kaynak = _kaynak(ortam, baska_okuma)
    with pytest.raises(ki.KayitKokeniGecersiz, match="ait değil"):
        _kayit(ortam, env, paket_id, kaynak_id=baska_kaynak)
    assert _sayi(ortam, kt.KAYIT) == 0


def test_calismayan_pakete_kayit_yazilamaz(ortam: Ortam, env: Envanter) -> None:
    """Paket kapısı taslak dünyasının kapısıdır: iptal edilmiş paketten kesin
    kayıt doğmaz."""
    paket_id, _ = _paket(ortam)
    with ortam.veritabani.islem() as oturum:
        tsi.paketi_iptal_et(oturum, paket_id, KULLANICI)
    with pytest.raises(tsi.PaketDurumuGecersiz):
        _kayit(ortam, env, paket_id)
    assert _sayi(ortam, kt.KAYIT) == 0


def test_olmayan_paket_ve_kayit_turu_reddedilir(ortam: Ortam, env: Envanter) -> None:
    paket_id, _ = _paket(ortam)
    with pytest.raises(tsi.PaketBulunamadi):
        _kayit(ortam, env, 999)
    with pytest.raises(ti.TanimBulunamadi, match="kayıt türü"):
        _kayit(ortam, env, paket_id, kayit_turu_id=999)
    assert _sayi(ortam, kt.KAYIT) == 0


def test_kayit_olusturma_denetim_izine_yazilir(ortam: Ortam, env: Envanter) -> None:
    """Kayıt düzeyinde tek olay; alan başına olay yazılmaz ve ham değer ize
    girmez."""
    paket_id, _ = _paket(ortam)
    kayit_id = _kayit(ortam, env, paket_id, alanlar={"adet": 12, "not": "gizli"})
    with ortam.veritabani.islem() as oturum:
        izler = di.olaylari_listele(oturum, kayit_id=kayit_id)
    assert [iz.olay for iz in izler] == ["kayit_olusturuldu"]
    assert izler[0].islem_paketi_id == paket_id
    assert izler[0].aktor_kimligi == AJAN.kimlik
    assert izler[0].gerekce is None


def test_hata_yutulsa_da_yarim_kayit_kalmaz(ortam: Ortam, env: Envanter) -> None:
    """Çağıran hatayı yakalayıp işleme devam etse bile hiçbir parça kalmaz."""
    paket_id, _ = _paket(ortam)
    with ortam.veritabani.islem() as oturum:
        onceki = ki.kayit_olustur(
            oturum, paket_id, env.sayim_id, {"adet": 1}, [env.nesne_id], AJAN
        ).id
        try:
            ki.kayit_olustur(oturum, paket_id, env.sayim_id, {"adet": 2}, [999], AJAN)
        except ki.KayitNesneBagiGecersiz:
            pass
        # aynı işlemde yazmaya devam edilebilir: oturum kullanılabilir durumda
        sonraki = ki.kayit_olustur(
            oturum, paket_id, env.sayim_id, {"adet": 3}, [env.nesne_id], AJAN
        ).id
    with ortam.veritabani.islem() as oturum:
        assert [k.id for k in ki.paketin_kayitlari(oturum, paket_id)] == [
            onceki,
            sonraki,
        ]
        assert oturum.execute(text("PRAGMA foreign_key_check")).all() == []
    assert _sayi(ortam, kt.KAYIT_ALANI) == 2
    assert _sayi(ortam, kt.KAYIT_NESNE) == 2


def test_kayit_silme_ve_kesinlestirme_islevi_yok() -> None:
    """Düzeltme ve geri alma 4.14'ün, kesinleştirme 4.8'in işidir; bu modülde
    öyle bir kapı yoktur."""
    yasak = [
        ad
        for ad in dir(ki)
        if not ad.startswith("_")
        and any(
            parca in ad
            for parca in ("sil", "degistir", "guncelle", "kesinlestir", "kaydet")
        )
    ]
    assert yasak == []


def test_esli_yazmada_kaybeden_cakisma_alir(ortam: Ortam, env: Envanter) -> None:
    """İki bağlantı aynı anda yazarsa kaybeden ham SQLite hatası değil
    ``KayitYazmaCakismasi`` alır; yeniden deneme çağıranındır (retry döngüsü
    yoktur)."""
    paket_id, _ = _paket(ortam)
    ikinci = vt.Veritabani(ortam.veritabani.yol)
    try:
        with ortam.veritabani.islem() as birinci_oturum:
            ki.kayit_olustur(
                birinci_oturum,
                paket_id,
                env.sayim_id,
                {"adet": 1},
                [env.nesne_id],
                AJAN,
            )
            # birinci işlem hâlâ açık: ikinci bağlantı yazmaya kalkarsa kilit
            with pytest.raises(ki.KayitYazmaCakismasi, match="eşzamanlı yazma"):
                with ikinci.islem() as ikinci_oturum:
                    ki.kayit_olustur(
                        ikinci_oturum,
                        paket_id,
                        env.sayim_id,
                        {"adet": 2},
                        [env.nesne_id],
                        AJAN,
                    )
    finally:
        ikinci.kapat()
    assert _sayi(ortam, kt.KAYIT) == 1


# --- bağ devri (Aşama 4.7/4) ----------------------------------------------------------


def _ikinci_nesne(ortam: Ortam, env: Envanter, kod: str = "A2") -> int:
    with ortam.veritabani.islem() as oturum:
        return ni.nesne_olustur(oturum, env.raf_id, {"kod": kod}).id


def test_bag_devri_kaydin_kendisini_degistirmez(ortam: Ortam, env: Envanter) -> None:
    paket_id, _ = _paket(ortam)
    kayit_id = _kayit(ortam, env, paket_id)
    hedef_id = _ikinci_nesne(ortam, env)
    with ortam.veritabani.islem() as oturum:
        ozet = ki.kayit_baglarini_devret(oturum, env.nesne_id, hedef_id, AJAN)
    assert (ozet.tasinan, ozet.birlesen) == (1, 0)
    with ortam.veritabani.islem() as oturum:
        assert ki.kaydin_nesneleri(oturum, kayit_id) == [hedef_id]
        assert ki.kayit_alanlarini_oku(oturum, kayit_id) == {"adet": 12}
        assert ki.kayit_getir(oturum, kayit_id).islem_paketi_id == paket_id
    assert _sayi(ortam, kt.KAYIT_NESNE) == 1


def test_hedefte_zaten_bagli_kayit_ikinci_kez_yazilmaz(
    ortam: Ortam, env: Envanter
) -> None:
    paket_id, _ = _paket(ortam)
    hedef_id = _ikinci_nesne(ortam, env)
    kayit_id = _kayit(ortam, env, paket_id, nesneler=[env.nesne_id, hedef_id])
    with ortam.veritabani.islem() as oturum:
        ozet = ki.kayit_baglarini_devret(oturum, env.nesne_id, hedef_id, AJAN)
    assert (ozet.tasinan, ozet.birlesen) == (0, 1)
    with ortam.veritabani.islem() as oturum:
        assert ki.kaydin_nesneleri(oturum, kayit_id) == [hedef_id]
    assert _sayi(ortam, kt.KAYIT_NESNE) == 1


def test_bagi_olmayan_nesnenin_devri_iz_birakmaz(ortam: Ortam, env: Envanter) -> None:
    """Taşınacak bağ yoksa denetim izine olay yazılmaz: iz gürültü deposu
    değildir."""
    hedef_id = _ikinci_nesne(ortam, env)
    with ortam.veritabani.islem() as oturum:
        ozet = ki.kayit_baglarini_devret(oturum, env.nesne_id, hedef_id, AJAN)
    assert (ozet.tasinan, ozet.birlesen) == (0, 0)
    with ortam.veritabani.islem() as oturum:
        assert di.olaylari_listele(oturum, nesne_id=hedef_id) == []


def test_bag_devri_kendine_ve_kapali_hedefe_yapilamaz(
    ortam: Ortam, env: Envanter
) -> None:
    paket_id, _ = _paket(ortam)
    _kayit(ortam, env, paket_id)
    hedef_id = _ikinci_nesne(ortam, env)
    with pytest.raises(ki.KayitNesneBagiGecersiz, match="kendisine devredilemez"):
        with ortam.veritabani.islem() as oturum:
            ki.kayit_baglarini_devret(oturum, env.nesne_id, env.nesne_id, AJAN)
    with ortam.veritabani.islem() as oturum:
        ni.yasam_durumunu_degistir(oturum, hedef_id, YasamDurumu.KAPALI)
    with pytest.raises(ki.KayitNesneBagiGecersiz, match="yalnız etkin nesneye"):
        with ortam.veritabani.islem() as oturum:
            ki.kayit_baglarini_devret(oturum, env.nesne_id, hedef_id, AJAN)
    with pytest.raises(ki.KayitNesneBagiGecersiz, match="nesne bulunamadı"):
        with ortam.veritabani.islem() as oturum:
            ki.kayit_baglarini_devret(oturum, env.nesne_id, 999, AJAN)
    assert _sayi(ortam, kt.KAYIT_NESNE) == 1
