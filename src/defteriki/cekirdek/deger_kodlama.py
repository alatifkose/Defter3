"""Özellik değerlerinin kanonik metin kodlaması (Aşama 4.3 kuralı; 4.5'te ortak).

Tek bir doğrulama ve kodlama mantığı, iki kullanıcı: kesin nesne özelliği
(``nesne_islemleri``) ve aday nesne özelliği (``taslak_islemleri``). Kural
``tanim_tablolari.DegerTuru`` ile sınırlıdır ve domain anlamı taşımaz:

* ``metin`` — ``str`` olduğu gibi;
* ``tam_sayi`` — yalnız gerçek ``int`` (``bool`` reddedilir), ``str(int)``;
* ``mantiksal`` — yalnız ``bool``, ``"1"`` / ``"0"``;
* ``ondalik`` — sonlu ``decimal.Decimal`` (``float`` reddedilir; ölçek ya da
  birim varsayımı yoktur), ``str(Decimal)``.

Çözme aynı kuralla Python değerine döner. Bu modül veritabanına dokunmaz,
``defteriki`` içinden yalnız ``tanim_tablolari.DegerTuru``'nü kullanır. Hata
``DegerKodlamaHatasi`` (``ValueError``); çağıran modüller bunu kendi hata
modeline sarar (``OzellikTuruUyusmuyor`` / ``GecersizAdayOzellik``).
"""

from __future__ import annotations

from decimal import Decimal

from defteriki.cekirdek.tanim_tablolari import DegerTuru


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
    return str(deger)


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
