from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from defteruc.cekirdek import yapi
from defteruc.cekirdek.motor import adi_dogrula
from defteruc.cekirdek.veritabani import Veritabani

Deger = yapi.Deger


class KayitHatasi(Exception): ...


@dataclass(frozen=True, slots=True)
class EklemeSonucu:
    eklenen: int
    anahtar_sutunlari: tuple[str, ...]
    anahtarlar: tuple[tuple[Deger, ...], ...]


def satirlar_ekle(
    veritabani: Veritabani, tablo: str, satirlar: Sequence[Mapping[str, Deger]]
) -> EklemeSonucu:
    adi_dogrula(tablo, "tablo")
    if not satirlar:
        raise KayitHatasi("eklenecek satır yok")
    cumleler = tuple(_ekleme_sql(tablo, satir) for satir in satirlar)
    try:
        with veritabani.islem() as oturum:
            baglanti = oturum.connection()
            anahtar = yapi.satir_kimligi(baglanti, tablo)
            donus = " RETURNING " + ", ".join(yapi.sutun_adi(a) for a in anahtar)
            anahtarlar = tuple(
                tuple(
                    yapi.deger_json(d)
                    for d in baglanti.exec_driver_sql(sql + donus, degerler).one()
                )
                for sql, degerler in cumleler
            )
    except yapi.KimlikYok as hata:
        raise KayitHatasi(
            f"satır kimliği belirlenemedi, hiçbiri yazılmadı: {hata}"
        ) from hata
    except SQLAlchemyError as hata:
        neden = hata.orig if isinstance(hata, DBAPIError) else hata
        raise KayitHatasi(
            f"{tablo}: satırlar eklenemedi, hiçbiri yazılmadı: {neden}"
        ) from hata
    return EklemeSonucu(len(satirlar), anahtar, anahtarlar)


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
