"""Tanım sisteminin okuma yüzeyi (Aşama 4.2; ayrı modül 2026-09-20).

Tanım tablolarını (``tanim_tablolari``) yalnız **okur**: kimlikle getirme ve
listeleme. Yazma ``tanim_islemleri`` içindedir. Ayrım mimari sınır içindir:
ekleme-yalnız kilit (``tanim_islemleri``) mevcut kesin veriye bakmak için
kesin nesne tablolarını (``nesne_tablolari``) import eder; taslak modülleri
ise kesin nesne dünyasına hiçbir import biçimiyle ulaşamaz
(``tests/test_mimari_sinir.py``). Yalnız okumaya ihtiyacı olan modüller
(``nesne_islemleri``, ``taslak_islemleri``) bu modülü kullanır; ``tanim_islemleri``
bu adları yeniden dışa aktarır, tanım sisteminin tam yüzeyi orada kalır.

Her işlev açık bir ``Session`` alır ve ``Veritabani.islem`` bağlamı içinde
çağrılır. Olmayan kimlik ``TanimBulunamadi`` verir; üst kaydı olmayan
listeleme boş liste yerine bu hatayı verir, böylece boş liste ile "üst kayıt
yok" karışmaz. ``paket_bul`` arama sonucudur, yoksa ``None`` döner.

Bu modül veritabanına yazmaz, ``defteruc`` içinden yalnız ``tanim_tablolari``
kullanır ve domain bilmez.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from defteruc.cekirdek.tanim_tablolari import (
    HiyerarsiKurali,
    IliskiTanimi,
    KayitAlaniTanimi,
    KayitTuru,
    NesneTuru,
    OzellikTanimi,
    TanimPaketi,
    TanimSurumu,
)


class TanimHatasi(Exception):
    """Tanım sistemi hatalarının ortak tabanı."""


class TanimBulunamadi(TanimHatasi, LookupError):
    """Verilen kimlikle paket, sürüm, nesne türü, ilişki ya da kayıt türü yok."""


# --- kimlikle getirme ------------------------------------------------------------


def paket_getir(oturum: Session, tanim_paketi_id: int) -> TanimPaketi:
    """Kimlikle tanım paketi; yoksa ``TanimBulunamadi``."""
    paket = oturum.get(TanimPaketi, tanim_paketi_id)
    if paket is None:
        raise TanimBulunamadi(f"tanım paketi bulunamadı: kimlik {tanim_paketi_id}")
    return paket


def surum_getir(oturum: Session, tanim_surumu_id: int) -> TanimSurumu:
    """Kimlikle tanım sürümü; yoksa ``TanimBulunamadi``."""
    surum = oturum.get(TanimSurumu, tanim_surumu_id)
    if surum is None:
        raise TanimBulunamadi(f"tanım sürümü bulunamadı: kimlik {tanim_surumu_id}")
    return surum


def nesne_turu_getir(oturum: Session, nesne_turu_id: int) -> NesneTuru:
    """Kimlikle nesne türü; yoksa ``TanimBulunamadi``."""
    tur = oturum.get(NesneTuru, nesne_turu_id)
    if tur is None:
        raise TanimBulunamadi(f"nesne türü bulunamadı: kimlik {nesne_turu_id}")
    return tur


def iliski_tanimi_getir(oturum: Session, iliski_tanimi_id: int) -> IliskiTanimi:
    """Kimlikle ilişki tanımı; yoksa ``TanimBulunamadi``."""
    iliski = oturum.get(IliskiTanimi, iliski_tanimi_id)
    if iliski is None:
        raise TanimBulunamadi(f"ilişki tanımı bulunamadı: kimlik {iliski_tanimi_id}")
    return iliski


def kayit_turu_getir(oturum: Session, kayit_turu_id: int) -> KayitTuru:
    """Kimlikle kayıt türü; yoksa ``TanimBulunamadi``."""
    tur = oturum.get(KayitTuru, kayit_turu_id)
    if tur is None:
        raise TanimBulunamadi(f"kayıt türü bulunamadı: kimlik {kayit_turu_id}")
    return tur


# --- arama ve listeleme ----------------------------------------------------------


def paket_bul(oturum: Session, kod: str) -> TanimPaketi | None:
    """Koduyla paket; yoksa ``None`` (arama sonucu, hata değil)."""
    return oturum.execute(
        select(TanimPaketi).where(TanimPaketi.kod == kod)
    ).scalar_one_or_none()


def paketleri_listele(oturum: Session) -> list[TanimPaketi]:
    return list(oturum.execute(select(TanimPaketi).order_by(TanimPaketi.kod)).scalars())


def surumleri_listele(oturum: Session, tanim_paketi_id: int) -> list[TanimSurumu]:
    """Paketin sürümleri, numaraya göre artan; paket yoksa ``TanimBulunamadi``."""
    paket = paket_getir(oturum, tanim_paketi_id)
    return list(
        oturum.execute(
            select(TanimSurumu)
            .where(TanimSurumu.tanim_paketi_id == paket.id)
            .order_by(TanimSurumu.surum_no)
        ).scalars()
    )


def surum_kilitli_mi(oturum: Session, tanim_surumu_id: int) -> bool:
    """Sürüm altında kesin nesne üretilmiş mi (ekleme-yalnız kilit,
    ``tanim_islemleri``); sürüm yoksa ``TanimBulunamadi``."""
    return surum_getir(oturum, tanim_surumu_id).kilitli


def nesne_turlerini_listele(oturum: Session, tanim_surumu_id: int) -> list[NesneTuru]:
    surum = surum_getir(oturum, tanim_surumu_id)
    return list(
        oturum.execute(
            select(NesneTuru)
            .where(NesneTuru.tanim_surumu_id == surum.id)
            .order_by(NesneTuru.kod)
        ).scalars()
    )


def ozellik_tanimlarini_listele(
    oturum: Session, nesne_turu_id: int
) -> list[OzellikTanimi]:
    """Türün özellikleri, tanımlanma sırasıyla."""
    tur = nesne_turu_getir(oturum, nesne_turu_id)
    return list(
        oturum.execute(
            select(OzellikTanimi)
            .where(OzellikTanimi.nesne_turu_id == tur.id)
            .order_by(OzellikTanimi.id)
        ).scalars()
    )


def iliski_tanimlarini_listele(
    oturum: Session, tanim_surumu_id: int
) -> list[IliskiTanimi]:
    surum = surum_getir(oturum, tanim_surumu_id)
    return list(
        oturum.execute(
            select(IliskiTanimi)
            .where(IliskiTanimi.tanim_surumu_id == surum.id)
            .order_by(IliskiTanimi.kod)
        ).scalars()
    )


def hiyerarsi_kurallarini_listele(
    oturum: Session, tanim_surumu_id: int
) -> list[HiyerarsiKurali]:
    """Sürümdeki hiyerarşi kuralları, ilişki koduna göre."""
    surum = surum_getir(oturum, tanim_surumu_id)
    return list(
        oturum.execute(
            select(HiyerarsiKurali)
            .join(IliskiTanimi, IliskiTanimi.id == HiyerarsiKurali.iliski_tanimi_id)
            .where(IliskiTanimi.tanim_surumu_id == surum.id)
            .order_by(IliskiTanimi.kod)
        ).scalars()
    )


def kayit_turlerini_listele(oturum: Session, tanim_surumu_id: int) -> list[KayitTuru]:
    surum = surum_getir(oturum, tanim_surumu_id)
    return list(
        oturum.execute(
            select(KayitTuru)
            .where(KayitTuru.tanim_surumu_id == surum.id)
            .order_by(KayitTuru.kod)
        ).scalars()
    )


def kayit_alani_tanimlarini_listele(
    oturum: Session, kayit_turu_id: int
) -> list[KayitAlaniTanimi]:
    """Kayıt türünün alanları, tanımlanma sırasıyla."""
    tur = kayit_turu_getir(oturum, kayit_turu_id)
    return list(
        oturum.execute(
            select(KayitAlaniTanimi)
            .where(KayitAlaniTanimi.kayit_turu_id == tur.id)
            .order_by(KayitAlaniTanimi.id)
        ).scalars()
    )
