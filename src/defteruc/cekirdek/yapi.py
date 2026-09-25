from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection

from defteruc.cekirdek.veritabani import Veritabani

SISTEM_ON_EKI = "_defteruc_"

ROWID_TAKMA_ADLARI = ("rowid", "_rowid_", "oid")


class KimlikYok(Exception): ...


@dataclass(frozen=True, slots=True)
class Kimlik:
    sutunlar: tuple[str, ...]
    ortuk: bool


type Deger = str | int | float | bool | bytes | None


@dataclass(frozen=True, slots=True)
class SutunBilgisi:
    ad: str
    tur: str
    zorunlu: bool
    varsayilan: str | None
    anahtar_sirasi: int
    uretilen: bool


@dataclass(frozen=True, slots=True)
class IndeksBilgisi:
    ad: str
    benzersiz: bool
    sql: str


@dataclass(frozen=True, slots=True)
class TabloBilgisi:
    ad: str
    sql: str
    sutunlar: tuple[SutunBilgisi, ...]
    indeksler: tuple[IndeksBilgisi, ...]
    satir_sayisi: int


def anahtar_sutunlari(baglanti: Connection, tablo: str) -> tuple[str, ...]:
    satirlar = baglanti.exec_driver_sql(f'PRAGMA table_xinfo("{tablo}")').all()
    anahtar = sorted((int(s[5]), str(s[1])) for s in satirlar if int(s[5]) > 0)
    return tuple(ad for _, ad in anahtar)


def rowid_takma_adi(sutun_adlari: tuple[str, ...]) -> str | None:
    golgeli = {ad.casefold() for ad in sutun_adlari}
    return next((t for t in ROWID_TAKMA_ADLARI if t not in golgeli), None)


def rowidsiz(baglanti: Connection, tablo: str) -> bool:
    satirlar = baglanti.exec_driver_sql(f'PRAGMA table_list("{tablo}")').all()
    return any(
        str(s[1]) == tablo and str(s[0]) == "main" and int(s[4]) != 0 for s in satirlar
    )


def _anahtar_otomatik_indeksli(baglanti: Connection, tablo: str) -> bool:
    satirlar = baglanti.exec_driver_sql(f'PRAGMA index_list("{tablo}")').all()
    return any(str(s[3]) == "pk" for s in satirlar)


def satir_kimligi(baglanti: Connection, tablo: str) -> Kimlik:
    satirlar = baglanti.exec_driver_sql(f'PRAGMA table_xinfo("{tablo}")').all()
    anahtar = sorted(
        (int(s[5]), str(s[1]), str(s[2]), int(s[3]) != 0)
        for s in satirlar
        if int(s[5]) > 0
    )
    if anahtar:
        adlar = tuple(ad for _, ad, _, _ in anahtar)
        if all(dolu for _, _, _, dolu in anahtar):
            return Kimlik(adlar, ortuk=False)
        (_, _, tur, _) = anahtar[0]
        if (
            len(anahtar) == 1
            and tur.casefold() == "integer"
            and not rowidsiz(baglanti, tablo)
            and not _anahtar_otomatik_indeksli(baglanti, tablo)
        ):
            return Kimlik(adlar, ortuk=False)
    takma = rowid_takma_adi(tuple(str(s[1]) for s in satirlar))
    if takma is None:
        raise KimlikYok(
            f"{tablo}: rowid, _rowid_ ve oid adlarının üçü de sütun; örtük satır "
            "kimliği güvenle okunamaz"
        )
    return Kimlik((takma,), ortuk=True)


def yazma_kilidi_al(baglanti: Connection, tablo: str) -> None:
    baglanti.exec_driver_sql(f'DELETE FROM "{tablo}" WHERE 0')


def kimlik_secimi(kimlik: Kimlik) -> str:
    if kimlik.ortuk:
        return kimlik.sutunlar[0]
    return ", ".join(f'"{ad}"' for ad in kimlik.sutunlar)


def yapiyi_oku(veritabani: Veritabani) -> tuple[TabloBilgisi, ...]:
    with veritabani.islem() as oturum:
        baglanti = oturum.connection()
        tablolar = baglanti.exec_driver_sql(
            "SELECT name, sql FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE ? ESCAPE '\\' AND name NOT LIKE ? ESCAPE '\\' "
            "ORDER BY name",
            (_like_on_eki("sqlite_"), _like_on_eki(SISTEM_ON_EKI)),
        ).all()
        return tuple(_tablo(baglanti, str(t[0]), str(t[1])) for t in tablolar)


def _like_on_eki(on_ek: str) -> str:
    return on_ek.replace("\\", "\\\\").replace("_", "\\_").replace("%", "\\%") + "%"


def _tablo(baglanti: Connection, ad: str, sql: str) -> TabloBilgisi:
    tirnakli = f'"{ad}"'
    sutunlar = tuple(
        SutunBilgisi(
            ad=str(s[1]),
            tur=str(s[2]),
            zorunlu=int(s[3]) != 0,
            varsayilan=None if s[4] is None else str(s[4]),
            anahtar_sirasi=int(s[5]),
            uretilen=int(s[6]) != 0,
        )
        for s in baglanti.exec_driver_sql(f"PRAGMA table_xinfo({tirnakli})").all()
    )
    benzersizler = {
        str(i[1]): int(i[2]) != 0
        for i in baglanti.exec_driver_sql(f"PRAGMA index_list({tirnakli})").all()
    }
    indeksler = tuple(
        IndeksBilgisi(ad=str(i[0]), benzersiz=benzersizler[str(i[0])], sql=str(i[1]))
        for i in baglanti.exec_driver_sql(
            "SELECT name, sql FROM sqlite_master WHERE type = 'index' "
            "AND tbl_name = ? AND sql IS NOT NULL ORDER BY name",
            (ad,),
        ).all()
    )
    satir_sayisi = int(
        baglanti.exec_driver_sql(f"SELECT count(*) FROM {tirnakli}").scalar_one()
    )
    return TabloBilgisi(ad, sql, sutunlar, indeksler, satir_sayisi)
