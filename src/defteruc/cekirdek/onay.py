from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Connection

from defteruc.cekirdek import motor as m
from defteruc.cekirdek.veritabani import Veritabani

SISTEM_TABLOSU = "_defteruc_yapi_istekleri"


class Durum(StrEnum):
    BEKLIYOR = "BEKLIYOR"
    UYGULANDI = "UYGULANDI"
    REDDEDILDI = "REDDEDILDI"
    UYGULANAMADI = "UYGULANAMADI"


class OnayHatasi(Exception): ...


class IstekYok(OnayHatasi): ...


class ZatenKararVerilmis(OnayHatasi): ...


ISTEK_TURLERI: dict[str, type[m.YapiIstegi]] = {
    "tablo_olusturma": m.TabloOlusturmaIstegi,
    "sutun_ekleme": m.SutunEklemeIstegi,
    "sutun_ozelligi_degistirme": m.SutunOzelligiDegistirmeIstegi,
    "indeks_olusturma": m.IndeksOlusturmaIstegi,
    "indeks_silme": m.IndeksSilmeIstegi,
}


@dataclass(frozen=True, slots=True)
class YapiIstegiKaydi:
    kimlik: int
    tur: str
    istek: m.YapiIstegi
    sql: str
    durum: Durum
    olusturma: str
    karar: str | None
    sonuc: str | None


_DURUMLAR = ", ".join(f"'{d.value}'" for d in Durum)

TABLO_DDL = f"""CREATE TABLE IF NOT EXISTS "{SISTEM_TABLOSU}" (
    kimlik INTEGER PRIMARY KEY AUTOINCREMENT,
    tur TEXT NOT NULL,
    istek TEXT NOT NULL,
    sql TEXT NOT NULL,
    durum TEXT NOT NULL CHECK (durum IN ({_DURUMLAR})),
    olusturma TEXT NOT NULL,
    karar TEXT,
    sonuc TEXT
) STRICT"""

SUTUNLAR = "kimlik, tur, istek, sql, durum, olusturma, karar, sonuc"


def sistem_tablosunu_hazirla(veritabani: Veritabani) -> None:
    with veritabani.islem() as oturum:
        oturum.connection().exec_driver_sql(TABLO_DDL)


def istek_birak(veritabani: Veritabani, istek: m.YapiIstegi) -> int:
    tur = istek_turu(istek)
    sql = m.istek_sql(istek)
    with veritabani.islem() as oturum:
        sonuc = oturum.connection().exec_driver_sql(
            f'INSERT INTO "{SISTEM_TABLOSU}" (tur, istek, sql, durum, olusturma) '
            "VALUES (?, ?, ?, ?, ?)",
            (tur, istek_json(istek), sql, Durum.BEKLIYOR.value, _simdi()),
        )
        kimlik = sonuc.lastrowid
    return int(kimlik)


def bekleyenler(veritabani: Veritabani) -> tuple[YapiIstegiKaydi, ...]:
    with veritabani.islem() as oturum:
        satirlar = (
            oturum.connection()
            .exec_driver_sql(
                f'SELECT {SUTUNLAR} FROM "{SISTEM_TABLOSU}" WHERE durum = ? '
                "ORDER BY kimlik",
                (Durum.BEKLIYOR.value,),
            )
            .all()
        )
    return tuple(_kayit(tuple(s)) for s in satirlar)


def son_kararlar(veritabani: Veritabani, sinir: int) -> tuple[YapiIstegiKaydi, ...]:
    with veritabani.islem() as oturum:
        satirlar = (
            oturum.connection()
            .exec_driver_sql(
                f'SELECT {SUTUNLAR} FROM "{SISTEM_TABLOSU}" WHERE durum != ? '
                "ORDER BY karar DESC, kimlik DESC LIMIT ?",
                (Durum.BEKLIYOR.value, sinir),
            )
            .all()
        )
    return tuple(_kayit(tuple(s)) for s in satirlar)


def kayit_getir(veritabani: Veritabani, kimlik: int) -> YapiIstegiKaydi:
    with veritabani.islem() as oturum:
        satir = (
            oturum.connection()
            .exec_driver_sql(
                f'SELECT {SUTUNLAR} FROM "{SISTEM_TABLOSU}" WHERE kimlik = ?', (kimlik,)
            )
            .first()
        )
    if satir is None:
        raise IstekYok(f"talep kimliği {kimlik} yok")
    return _kayit(tuple(satir))


def onayla(veritabani: Veritabani, kimlik: int) -> YapiIstegiKaydi:
    kayit = _bekleyen_kayit(veritabani, kimlik)
    try:
        with m.islem_ac(veritabani, kayit.istek) as baglanti:
            _karari_yaz(baglanti, kimlik, Durum.UYGULANDI, None)
            m.uygula_baglantida(baglanti, kayit.istek)
    except m.MotorHatasi as hata:
        with veritabani.islem() as oturum:
            _karari_yaz(oturum.connection(), kimlik, Durum.UYGULANAMADI, str(hata))
    return kayit_getir(veritabani, kimlik)


def reddet(veritabani: Veritabani, kimlik: int) -> YapiIstegiKaydi:
    _bekleyen_kayit(veritabani, kimlik)
    with veritabani.islem() as oturum:
        _karari_yaz(oturum.connection(), kimlik, Durum.REDDEDILDI, None)
    return kayit_getir(veritabani, kimlik)


def _bekleyen_kayit(veritabani: Veritabani, kimlik: int) -> YapiIstegiKaydi:
    kayit = kayit_getir(veritabani, kimlik)
    if kayit.durum is not Durum.BEKLIYOR:
        raise ZatenKararVerilmis(
            f"talep {kimlik} için karar verilmiş: {kayit.durum.value} ({kayit.karar})"
        )
    return kayit


def _karari_yaz(
    baglanti: Connection, kimlik: int, durum: Durum, sonuc: str | None
) -> None:
    guncellenen = baglanti.exec_driver_sql(
        f'UPDATE "{SISTEM_TABLOSU}" SET durum = ?, karar = ?, sonuc = ? '
        "WHERE kimlik = ? AND durum = ?",
        (durum.value, _simdi(), sonuc, kimlik, Durum.BEKLIYOR.value),
    ).rowcount
    if guncellenen != 1:
        raise ZatenKararVerilmis(
            f"talep {kimlik} bu arada başka bir yerden karara bağlandı; "
            "bu karar uygulanmadı"
        )


def istek_aciklamasi(kayit: YapiIstegiKaydi) -> str:
    istek = kayit.istek
    if (
        isinstance(istek, m.SutunOzelligiDegistirmeIstegi)
        and istek.deger_donusumu_izinli
    ):
        sutunlar = ", ".join(istek.deger_donusumu_izinli)
        return (
            f"Değer dönüşümüne izin verilen sütunlar: {sutunlar}. Bu sütunlarda "
            "kopyalanan değerin ve saklama sınıfının aynı kaldığı denetlenmez; tür "
            "değişimiyle gelen hassasiyet kaybı geri alınmaz. Diğer sütunlar ve "
            "kimlik her zaman aynen korunur."
        )
    return ""


def _simdi() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _kayit(satir: tuple[Any, ...]) -> YapiIstegiKaydi:
    kimlik, tur, istek, sql, durum, olusturma, karar, sonuc = satir
    return YapiIstegiKaydi(
        kimlik=int(kimlik),
        tur=str(tur),
        istek=istek_coz(str(tur), str(istek)),
        sql=str(sql),
        durum=Durum(str(durum)),
        olusturma=str(olusturma),
        karar=None if karar is None else str(karar),
        sonuc=None if sonuc is None else str(sonuc),
    )


# --- istek metni: JSON'a yaz, JSON'dan çöz ------------------------------------------


def istek_turu(istek: m.YapiIstegi) -> str:
    for tur, sinif in ISTEK_TURLERI.items():
        if type(istek) is sinif:
            return tur
    raise TypeError(f"bilinmeyen istek türü: {type(istek).__name__}")


def istek_json(istek: m.YapiIstegi) -> str:
    return json.dumps(asdict(istek), ensure_ascii=False)


def istek_coz(tur: str, metin: str) -> m.YapiIstegi:
    if tur not in ISTEK_TURLERI:
        raise ValueError(f"bilinmeyen istek türü: {tur!r}")
    veri: dict[str, Any] = json.loads(metin)
    match tur:
        case "tablo_olusturma":
            return m.TabloOlusturmaIstegi(
                tablo=str(veri["tablo"]),
                sutunlar=_sutunlar(veri["sutunlar"]),
                kisitlar=_metinler(veri["kisitlar"]),
                secenekler=_metinler(veri["secenekler"]),
            )
        case "sutun_ekleme":
            return m.SutunEklemeIstegi(
                tablo=str(veri["tablo"]), sutun=_sutun(veri["sutun"])
            )
        case "sutun_ozelligi_degistirme":
            return m.SutunOzelligiDegistirmeIstegi(
                tablo=str(veri["tablo"]),
                sutunlar=_sutunlar(veri["sutunlar"]),
                kisitlar=_metinler(veri["kisitlar"]),
                secenekler=_metinler(veri["secenekler"]),
                deger_donusumu_izinli=_metinler(veri["deger_donusumu_izinli"]),
            )
        case "indeks_olusturma":
            return m.IndeksOlusturmaIstegi(
                indeks=str(veri["indeks"]),
                tablo=str(veri["tablo"]),
                sutunlar=_metinler(veri["sutunlar"]),
                benzersiz=bool(veri["benzersiz"]),
                kosul=str(veri["kosul"]),
            )
        case _:
            return m.IndeksSilmeIstegi(indeks=str(veri["indeks"]))


def _metinler(veri: Any) -> tuple[str, ...]:
    return tuple(str(v) for v in veri)


def _sutun(veri: Any) -> m.Sutun:
    return m.Sutun(ad=str(veri["ad"]), ozellikler=_metinler(veri["ozellikler"]))


def _sutunlar(veri: Any) -> tuple[m.Sutun, ...]:
    return tuple(_sutun(v) for v in veri)
