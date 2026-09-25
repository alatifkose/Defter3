from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Connection
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from defteruc.cekirdek import yapi
from defteruc.cekirdek.motor import adi_dogrula, parcayi_dogrula
from defteruc.cekirdek.veritabani import Veritabani

Deger = yapi.Deger

SINIR_VARSAYILAN = 100
SINIR_AZAMI = 1000
YASAK_ISLEVLER = frozenset({"load_extension"})


class OkumaHatasi(Exception): ...


@dataclass(frozen=True, slots=True)
class OkumaSonucu:
    sutunlar: tuple[str, ...]
    satirlar: tuple[tuple[Deger, ...], ...]
    eslesen_toplam: int
    donen: int
    baslangic: int
    devami_var: bool
    anahtar_sutunlari: tuple[str, ...]
    anahtarlar: tuple[tuple[Deger, ...], ...]


def satirlari_oku(
    veritabani: Veritabani,
    tablo: str,
    kosul: str = "",
    parametreler: Sequence[Deger] = (),
    sinir: int = SINIR_VARSAYILAN,
    baslangic: int = 0,
) -> OkumaSonucu:
    if tablo.startswith(yapi.SISTEM_ON_EKI):
        raise OkumaHatasi(f"{tablo}: sistem tablosu okunamaz")
    adi_dogrula(tablo, "tablo")
    if not 1 <= sinir <= SINIR_AZAMI:
        raise OkumaHatasi(f"sınır 1 ile {SINIR_AZAMI} arasında olmalı: {sinir}")
    if baslangic < 0:
        raise OkumaHatasi(f"başlangıç negatif olamaz: {baslangic}")
    nerede = f" WHERE {parcayi_dogrula(kosul, 'koşul')}" if kosul.strip() else ""
    degerler = tuple(parametreler)
    try:
        with veritabani.islem() as oturum:
            baglanti = oturum.connection()
            kimlik = yapi.satir_kimligi(baglanti, tablo)
            kimlik_secimi = ", ".join(yapi.sutun_adi(a) for a in kimlik)
            with _yalniz_okuma(baglanti):
                toplam = int(
                    baglanti.exec_driver_sql(
                        f'SELECT count(*) FROM "{tablo}"{nerede}', degerler
                    ).scalar_one()
                )
                sonuc = baglanti.exec_driver_sql(
                    f'SELECT {kimlik_secimi}, * FROM "{tablo}"{nerede} '
                    f"ORDER BY {kimlik_secimi} LIMIT ? OFFSET ?",
                    (*degerler, sinir, baslangic),
                )
                sutunlar = tuple(str(k) for k in sonuc.keys())[len(kimlik) :]
                ham = tuple(tuple(s) for s in sonuc.all())
                anahtarlar = tuple(s[: len(kimlik)] for s in ham)
                satirlar = tuple(s[len(kimlik) :] for s in ham)
    except yapi.KimlikYok as hata:
        raise OkumaHatasi(f"{tablo}: okunamadı: {hata}") from hata
    except SQLAlchemyError as hata:
        neden = hata.orig if isinstance(hata, DBAPIError) else hata
        raise OkumaHatasi(f"{tablo}: okunamadı: {neden}") from hata
    return OkumaSonucu(
        sutunlar=sutunlar,
        satirlar=satirlar,
        eslesen_toplam=toplam,
        donen=len(satirlar),
        baslangic=baslangic,
        devami_var=baslangic + len(satirlar) < toplam,
        anahtar_sutunlari=kimlik,
        anahtarlar=anahtarlar,
    )


class _yalniz_okuma:
    def __init__(self, baglanti: Connection) -> None:
        ham = baglanti.connection.dbapi_connection
        if not isinstance(ham, sqlite3.Connection):  # pragma: no cover
            raise OkumaHatasi("okuma yalnız sqlite3 bağlantısında kısıtlanabilir")
        self._baglanti = baglanti
        self._ham = ham

    def __enter__(self) -> None:
        self._ham.set_authorizer(_yetki)

    def __exit__(self, *_: object) -> None:
        try:
            self._ham.set_authorizer(None)
        except Exception:
            self._baglanti.invalidate()
            raise


def _yetki(eylem: int, birinci: str | None, ikinci: str | None, *_: object) -> int:
    if eylem == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK
    if eylem == sqlite3.SQLITE_READ:
        tablo = birinci or ""
        if tablo.startswith(yapi.SISTEM_ON_EKI) or tablo.startswith("sqlite_"):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    if eylem == sqlite3.SQLITE_FUNCTION:
        return sqlite3.SQLITE_DENY if ikinci in YASAK_ISLEVLER else sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY
