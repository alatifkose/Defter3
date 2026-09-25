from __future__ import annotations

from collections.abc import Mapping, Sequence

from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from defteruc.cekirdek.motor import adi_dogrula
from defteruc.cekirdek.veritabani import Veritabani

type Deger = str | int | float | bool | None


class KayitHatasi(Exception): ...


def satirlar_ekle(
    veritabani: Veritabani, tablo: str, satirlar: Sequence[Mapping[str, Deger]]
) -> int:
    adi_dogrula(tablo, "tablo")
    if not satirlar:
        raise KayitHatasi("eklenecek satır yok")
    cumleler = tuple(_ekleme_sql(tablo, satir) for satir in satirlar)
    try:
        with veritabani.islem() as oturum:
            baglanti = oturum.connection()
            for sql, degerler in cumleler:
                baglanti.exec_driver_sql(sql, degerler)
    except SQLAlchemyError as hata:
        neden = hata.orig if isinstance(hata, DBAPIError) else hata
        raise KayitHatasi(
            f"{tablo}: satırlar eklenemedi, hiçbiri yazılmadı: {neden}"
        ) from hata
    return len(satirlar)


def _ekleme_sql(
    tablo: str, satir: Mapping[str, Deger]
) -> tuple[str, tuple[Deger, ...]]:
    if not satir:
        raise KayitHatasi(f"{tablo}: boş satır eklenemez")
    adlar = tuple(adi_dogrula(ad, "sütun") for ad in satir)
    liste = ", ".join(f'"{ad}"' for ad in adlar)
    yerler = ", ".join("?" for _ in adlar)
    return (
        f'INSERT INTO "{tablo}" ({liste}) VALUES ({yerler})',
        tuple(satir[ad] for ad in adlar),
    )
