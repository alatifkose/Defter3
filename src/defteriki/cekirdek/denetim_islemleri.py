"""İş denetim izinin yazma ve okuma işlevleri (Aşama 4.6).

Denetim izi (``denetim_tablolari.DenetimIzi``) iş olaylarının kalıcı
kaydıdır; teknik hata günlüğünden (``defteriki.gunluk``) ayrıdır ve onunla
birleştirilmez. Her yazma aktörü açıkça alır.

İşlem sınırı 4.1 kuralıdır: her işlev açık bir ``Session`` alır, çağıran
``Veritabani.islem`` transaction'ının sahibidir. Denetim satırı işin kendisiyle
**aynı** transaction içinde yazılır: iş geri alınırsa izi de geri alınır, yarım
karar yarım iz bırakmaz.

Gizlilik: ``gerekce`` kullanıcının kısa açıklamasıdır; belge içeriği,
özellik ham değeri, sır ya da dosya içeriği geçirilmemelidir ve uzunluğu
``AZAMI_GEREKCE_UZUNLUGU`` ile sınırlıdır. Olayın nesnesi kimlik referansıyla
gösterilir, değeri kopyalanmaz.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from defteriki.cekirdek.denetim_tablolari import Aktor, DenetimIzi, DenetimOlayi
from defteriki.cekirdek.tanim_tablolari import simdi_utc

AZAMI_GEREKCE_UZUNLUGU = 500
"""Karakter; aşılırsa ``GecersizDenetimKaydi``. İz bir anlatı deposu değildir."""


class DenetimHatasi(Exception):
    """Denetim izi hatalarının ortak tabanı."""


class GecersizDenetimKaydi(DenetimHatasi, ValueError):
    """Aktör kimliği boş ya da gerekçe sınırı aşıyor."""


def olay_yaz(
    oturum: Session,
    olay: DenetimOlayi,
    aktor: Aktor,
    *,
    islem_paketi_id: int | None = None,
    karar_talebi_id: int | None = None,
    nesne_id: int | None = None,
    ikincil_nesne_id: int | None = None,
    aday_nesne_id: int | None = None,
    ozellik_tanimi_id: int | None = None,
    gerekce: str | None = None,
) -> DenetimIzi:
    """Bir iş olayını denetim izine yazar; satırı döndürür.

    Aktör zorunludur ve kimliği boş olamaz. Referanslar isteğe bağlıdır;
    olayın sonucunu anlamaya yetecek kadarı verilir.
    """
    kimlik = aktor.kimlik.strip()
    if not kimlik:
        raise GecersizDenetimKaydi("aktör kimliği boş olamaz.")
    if gerekce is not None and len(gerekce) > AZAMI_GEREKCE_UZUNLUGU:
        raise GecersizDenetimKaydi(
            f"gerekçe {AZAMI_GEREKCE_UZUNLUGU} karakter sınırını aşıyor "
            f"({len(gerekce)}); denetim izi içerik deposu değildir."
        )
    satir = DenetimIzi(
        olay=DenetimOlayi(olay).value,
        olay_zamani=simdi_utc(),
        aktor_turu=aktor.tur.value,
        aktor_kimligi=kimlik,
        islem_paketi_id=islem_paketi_id,
        karar_talebi_id=karar_talebi_id,
        nesne_id=nesne_id,
        ikincil_nesne_id=ikincil_nesne_id,
        aday_nesne_id=aday_nesne_id,
        ozellik_tanimi_id=ozellik_tanimi_id,
        gerekce=gerekce,
    )
    oturum.add(satir)
    oturum.flush()
    return satir


def olaylari_listele(
    oturum: Session,
    *,
    islem_paketi_id: int | None = None,
    karar_talebi_id: int | None = None,
    nesne_id: int | None = None,
) -> list[DenetimIzi]:
    """Denetim olayları, kimlik sırasıyla (deterministik).

    Verilen süzgeçler birlikte uygulanır; ``nesne_id`` olayın iki ucundan
    herhangi birinde arar.
    """
    sorgu = select(DenetimIzi).order_by(DenetimIzi.id)
    if islem_paketi_id is not None:
        sorgu = sorgu.where(DenetimIzi.islem_paketi_id == islem_paketi_id)
    if karar_talebi_id is not None:
        sorgu = sorgu.where(DenetimIzi.karar_talebi_id == karar_talebi_id)
    if nesne_id is not None:
        sorgu = sorgu.where(
            (DenetimIzi.nesne_id == nesne_id)
            | (DenetimIzi.ikincil_nesne_id == nesne_id)
        )
    return list(oturum.execute(sorgu).scalars())
