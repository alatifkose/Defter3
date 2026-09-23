"""Değer kodlaması testleri: ondalık kanonik biçim (karar 2026-09-19).

Sınanan sözleşme: matematiksel olarak eşit iki ``Decimal`` aynı metni verir,
farklı iki değer farklı metin verir, çözme tam hassasiyette geri döner; kural
``decimal`` bağlam hassasiyetinden bağımsızdır; bütün sıfırlar tek ``0``dır;
çok büyük ve küçük üsler kısa kalır. Tür reddi (``float``, ``bool``, ``NaN``,
sonsuz) değişmez. Kesin ve aday özelliğin aynı biçimi kullandığı
``test_islem_paketi`` içinde ham tablo metniyle ayrıca sınanır.
"""

from decimal import Decimal, localcontext

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from defteruc.cekirdek import deger_kodlama as dk
from defteruc.cekirdek.tanim_tablolari import DegerTuru

ONDALIK = DegerTuru.ONDALIK.value

sonlu_ondaliklar = st.decimals(allow_nan=False, allow_infinity=False)


def _kodla(deger: Decimal) -> str:
    return dk.degeri_kodla(ONDALIK, "x", deger)


def _coz(metin: str) -> Decimal:
    deger = dk.degeri_coz(ONDALIK, metin)
    assert isinstance(deger, Decimal)
    return deger


ESIT_KUMELER: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("1e0", ("1", "1.0", "1.00", "1E+0", "01", "1.000000")),
    ("1e2", ("100", "100.0", "1E+2", "10E+1", "0.1E3")),
    ("0", ("0", "0.0", "-0", "-0.00", "0E+5", "-0E-5", "000")),
    ("125e-1", ("12.5", "12.50", "12.500", "1250E-2")),
    ("1e-2", ("0.01", "0.0100", "1E-2")),
    ("-5e0", ("-5", "-5.0", "-50E-1")),
)


@pytest.mark.parametrize(("beklenen", "yazimlar"), ESIT_KUMELER)
def test_esit_degerler_ayni_metni_verir(
    beklenen: str, yazimlar: tuple[str, ...]
) -> None:
    for yazim in yazimlar:
        assert _kodla(Decimal(yazim)) == beklenen, yazim
        assert _coz(beklenen) == Decimal(yazim)


def test_farkli_degerler_farkli_metin_verir() -> None:
    metinler = {_kodla(Decimal(y)) for y in ("1", "10", "0.1", "-1", "1.5", "0")}
    assert len(metinler) == 6


def test_cok_buyuk_ve_kucuk_usler_kisa_kalir() -> None:
    for yazim in ("1E+999999", "1E-999999", "-7.5E+123456", "123456789E-987654"):
        metin = _kodla(Decimal(yazim))
        assert len(metin) < 40, metin
        assert "." not in metin
        assert _coz(metin) == Decimal(yazim)


def test_yuksek_hassasiyet_basamak_kaybetmez() -> None:
    yazim = "1." + "0123456789" * 6 + "1"
    metin = _kodla(Decimal(yazim))
    assert _coz(metin) == Decimal(yazim)
    assert len(metin) >= len(yazim)


def test_baglam_hassasiyetinden_bagimsiz() -> None:
    """``decimal`` bağlamı 5 basamağa düşürülse bile kodlama yuvarlamaz."""
    yazim = "1234567890.123456789"
    with localcontext() as baglam:
        baglam.prec = 5
        metin = _kodla(Decimal(yazim))
        geri = _coz(metin)
    assert metin == "1234567890123456789e-9"
    assert geri == Decimal(yazim)


@pytest.mark.parametrize(
    "deger",
    [1.5, 1, True, "1.5", None, Decimal("NaN"), Decimal("Infinity"), Decimal("-Inf")],
)
def test_ondalik_olmayan_ve_sonlu_olmayan_reddedilir(deger: object) -> None:
    with pytest.raises(dk.DegerKodlamaHatasi):
        dk.degeri_kodla(ONDALIK, "x", deger)


def test_ondaligi_kodla_sonlu_olmayani_reddeder() -> None:
    with pytest.raises(dk.DegerKodlamaHatasi):
        dk.ondaligi_kodla(Decimal("NaN"))


@given(sonlu_ondaliklar)
@settings(max_examples=300)
def test_ozellik_cozme_kodlamayi_geri_alir(deger: Decimal) -> None:
    assert _coz(_kodla(deger)) == deger


@given(sonlu_ondaliklar, st.integers(min_value=0, max_value=12))
@settings(max_examples=300)
def test_ozellik_esit_degerler_ayni_metin(deger: Decimal, sifir_sayisi: int) -> None:
    """Aynı değerin sona sıfır eklenmiş yazımı (``1.5`` → ``1.500``) ve
    eksi sıfır dahil bütün yazımları aynı metni verir."""
    isaret, basamaklar, us = deger.as_tuple()
    assert isinstance(us, int)
    genis = Decimal(
        (isaret, tuple(basamaklar) + (0,) * sifir_sayisi, us - sifir_sayisi)
    )
    assert genis == deger
    assert _kodla(genis) == _kodla(deger)


@given(sonlu_ondaliklar, sonlu_ondaliklar)
@settings(max_examples=300)
def test_ozellik_farkli_degerler_farkli_metin(a: Decimal, b: Decimal) -> None:
    assert (a == b) == (_kodla(a) == _kodla(b))


@given(sonlu_ondaliklar)
@settings(max_examples=200)
def test_ozellik_sifirlar_tek_metin(deger: Decimal) -> None:
    if deger == 0:
        assert _kodla(deger) == dk.SIFIR
    else:
        assert _kodla(deger) != dk.SIFIR
