"""Özellik değerlerinin kanonik metin kodlaması (Aşama 4.3 kuralı; 4.5'te ortak).

Tek bir doğrulama ve kodlama mantığı, iki kullanıcı: kesin nesne özelliği
(``nesne_islemleri``) ve aday nesne özelliği (``taslak_islemleri``). Kural
``tanim_tablolari.DegerTuru`` ile sınırlıdır ve domain anlamı taşımaz:

* ``metin`` — ``str`` olduğu gibi;
* ``tam_sayi`` — yalnız gerçek ``int`` (``bool`` reddedilir), ``str(int)``;
* ``mantiksal`` — yalnız ``bool``, ``"1"`` / ``"0"``;
* ``ondalik`` — sonlu ``decimal.Decimal`` (``float`` reddedilir; ölçek ya da
  birim varsayımı yoktur), **sayısal olarak kanonik** metin (aşağıda).

**Ondalık kanonik biçim (karar 2026-09-19).** Matematiksel olarak eşit iki
``Decimal`` her zaman aynı metni verir; farklı iki değer farklı metin verir.
Biçim ``<işaret><katsayı>e<üs>``: katsayı sondaki sıfırlardan arındırılmış
rakam dizisi, üs buna göre düzeltilmiş tam sayı; bütün sıfırlar (``-0``,
``0.00`` dahil) tek ``0`` metnidir. Örnekler: ``1``, ``1.0``, ``1.00`` ve
``1E+0`` → ``1e0``; ``100`` ve ``1E+2`` → ``1e2``; ``12.50`` → ``125e-1``;
``0.0100`` → ``1e-2``; ``-0.00`` → ``0``. Kodlama ``Decimal.as_tuple`` üzerinden
yapılır: ``decimal`` bağlam hassasiyetinden bağımsızdır, ``normalize()``
kullanılmaz (bağlamda yuvarlayabilir), hiçbir basamak kaybolmaz ve çok büyük
ya da küçük üsler sabit noktalı dev metne açılmaz. Çözme ``Decimal(metin)``
ile tam hassasiyette geri döner; dönen değer sayısal olarak aynıdır, ölçek
(sondaki sıfır sayısı) korunmaz: ``12.50`` yazılır, ``Decimal("12.5")`` ile
eşit bir değer okunur. Bu biçim iç depolama içindir, ekrana basılmaz.

Çözme aynı kuralla Python değerine döner. Bu modül veritabanına dokunmaz,
``defteruc`` içinden yalnız ``tanim_tablolari.DegerTuru``'nü kullanır. Hata
``DegerKodlamaHatasi`` (``ValueError``); çağıran modüller bunu kendi hata
modeline sarar (``OzellikTuruUyusmuyor`` / ``GecersizAdayOzellik``).
"""

from __future__ import annotations

from decimal import Decimal

from defteruc.cekirdek.tanim_tablolari import DegerTuru

SIFIR = "0"
"""Bütün sıfır değerlerin (``0``, ``0.00``, ``-0``) tek kanonik metni."""


class DegerKodlamaHatasi(ValueError):
    """Değer, özellik tanımının değer türüne uymuyor."""


def degeri_kodla(deger_turu: str, kod: str, deger: object) -> str:
    """Python değerini türe göre doğrular, kanonik metne çevirir; ``kod``
    yalnız hata mesajı içindir."""
    tur = DegerTuru(deger_turu)
    hata = DegerKodlamaHatasi(
        f"özellik {kod!r} {tur.value} bekler, {type(deger).__name__} verildi."
    )
    if tur is DegerTuru.METIN:
        if not isinstance(deger, str):
            raise hata
        return deger
    if tur is DegerTuru.TAM_SAYI:
        if type(deger) is not int:
            raise hata
        return str(deger)
    if tur is DegerTuru.MANTIKSAL:
        if type(deger) is not bool:
            raise hata
        return "1" if deger else "0"
    if not isinstance(deger, Decimal) or not deger.is_finite():
        raise hata
    return ondaligi_kodla(deger)


def ondaligi_kodla(deger: Decimal) -> str:
    """Sonlu ``Decimal`` için sayısal olarak kanonik metin (modül açıklaması).
    Sonlu olmayan değer ``DegerKodlamaHatasi`` verir."""
    isaret, basamaklar, us = deger.as_tuple()
    if not isinstance(us, int):
        raise DegerKodlamaHatasi("ondalık değer sonlu olmalı.")
    rakamlar = list(basamaklar)
    if not any(rakamlar):
        return SIFIR
    while rakamlar[-1] == 0:
        rakamlar.pop()
        us += 1
    govde = "".join(str(r) for r in rakamlar)
    return f"{'-' if isaret else ''}{govde}e{us}"


def degeri_coz(deger_turu: str, metin: str) -> object:
    """Saklanan kanonik metni Python değerine çevirir."""
    tur = DegerTuru(deger_turu)
    if tur is DegerTuru.METIN:
        return metin
    if tur is DegerTuru.TAM_SAYI:
        return int(metin)
    if tur is DegerTuru.MANTIKSAL:
        return metin == "1"
    return Decimal(metin)
