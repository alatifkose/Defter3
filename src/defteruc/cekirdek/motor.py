from __future__ import annotations

import re
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import pairwise

from sqlalchemy import Connection
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from defteruc.cekirdek import yapi
from defteruc.cekirdek.veritabani import Veritabani, YabanciAnahtarIhlali

AD_BICIMI = re.compile(r"^[a-z][a-z0-9_]*$")

GECICI_AD_EKI = "__yeniden_kurma"

ROWID_TAKMA_ADLARI = ("rowid", "_rowid_", "oid")


class MotorHatasi(Exception): ...


class GecersizAd(MotorHatasi, ValueError): ...


class GecersizParca(MotorHatasi, ValueError): ...


class SutunlarUyusmuyor(MotorHatasi): ...


class KopyaDegerDegisti(MotorHatasi): ...


class KisitlarUyusmuyor(MotorHatasi): ...


@dataclass(frozen=True, slots=True)
class Sutun:
    ad: str
    ozellikler: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TabloOlusturmaIstegi:
    tablo: str
    sutunlar: tuple[Sutun, ...]
    kisitlar: tuple[str, ...] = ()
    secenekler: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SutunEklemeIstegi:
    tablo: str
    sutun: Sutun


@dataclass(frozen=True, slots=True)
class SutunOzelligiDegistirmeIstegi:
    tablo: str
    sutunlar: tuple[Sutun, ...]
    kisitlar: tuple[str, ...] = ()
    secenekler: tuple[str, ...] = ()
    deger_donusumu_izinli: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IndeksOlusturmaIstegi:
    indeks: str
    tablo: str
    sutunlar: tuple[str, ...]
    benzersiz: bool = False
    kosul: str = ""


@dataclass(frozen=True, slots=True)
class IndeksSilmeIstegi:
    indeks: str


type YapiIstegi = (
    TabloOlusturmaIstegi
    | SutunEklemeIstegi
    | SutunOzelligiDegistirmeIstegi
    | IndeksOlusturmaIstegi
    | IndeksSilmeIstegi
)


# --- ad ve parça sınırı: SQL'e güvenle yazılabilmek için ---------------------------


def adi_dogrula(ad: str, ne: str) -> str:
    if not AD_BICIMI.fullmatch(ad):
        raise GecersizAd(
            f"{ne} adı sade olmalı (küçük ASCII harfle başlar; harf, rakam, "
            f"alt çizgi; Türkçe karakter yok): {ad!r}"
        )
    return ad


def parcayi_dogrula(parca: str, ne: str = "parça") -> str:
    if not parca.strip():
        raise GecersizParca(f"{ne} boş olamaz")
    try:
        karakterler, son_derinlik, yorum_var = _acik_karakterler(parca)
    except ValueError as hata:
        raise GecersizParca(f"{ne}: {hata}: {parca!r}") from None
    if yorum_var:
        raise GecersizParca(
            f"{ne} SQL yorumu içeremez (-- ya da /* */); parçalar birleşince "
            f"yorum sonraki parçayı yutar: {parca!r}"
        )
    for _, c, derinlik in karakterler:
        if derinlik == 0 and c in ",;":
            raise GecersizParca(
                f"{ne} kendi yerinde kalmalı; üst düzeyde {c!r} olamaz: {parca!r}"
            )
        if c == ")" and derinlik == 0:
            raise GecersizParca(f"{ne}: parantez dengesiz: {parca!r}")
    if son_derinlik != 0:
        raise GecersizParca(f"{ne}: parantez dengesiz: {parca!r}")
    return parca


def _tirnakla(ad: str) -> str:
    return f'"{ad}"'


# --- SQL üretimi: veritabanına dokunmaz -------------------------------------------


def _sutun_tanimi(sutun: Sutun) -> str:
    parcalar = [
        _tirnakla(adi_dogrula(sutun.ad, "sütun")),
        *(parcayi_dogrula(p, "özellik parçası") for p in sutun.ozellikler),
    ]
    return " ".join(parcalar)


def _tablo_tanimi(
    tablo: str,
    sutunlar: tuple[Sutun, ...],
    kisitlar: tuple[str, ...],
    secenekler: tuple[str, ...],
) -> str:
    govde = ", ".join(
        (
            *(_sutun_tanimi(s) for s in sutunlar),
            *(parcayi_dogrula(k, "tablo kısıtı") for k in kisitlar),
        )
    )
    kuyruk = ", ".join(parcayi_dogrula(s, "tablo seçeneği") for s in secenekler)
    return f"CREATE TABLE {_tirnakla(tablo)} ({govde})" + (
        f" {kuyruk}" if kuyruk else ""
    )


def tablo_olusturma_sql(istek: TabloOlusturmaIstegi) -> str:
    tablo = adi_dogrula(istek.tablo, "tablo")
    return _tablo_tanimi(tablo, istek.sutunlar, istek.kisitlar, istek.secenekler)


def sutun_ekleme_sql(istek: SutunEklemeIstegi) -> str:
    tablo = adi_dogrula(istek.tablo, "tablo")
    return f"ALTER TABLE {_tirnakla(tablo)} ADD COLUMN {_sutun_tanimi(istek.sutun)}"


def _kopyalama_sql(
    gecici: str, tablo: str, adlar: tuple[str, ...], rowid_takma: str | None = None
) -> str:
    liste = ", ".join(_tirnakla(a) for a in adlar)
    if rowid_takma:
        liste = f"{rowid_takma}, {liste}"
    hedef, kaynak = _tirnakla(gecici), _tirnakla(tablo)
    return f"INSERT OR ABORT INTO {hedef} ({liste}) SELECT {liste} FROM {kaynak}"


def sutun_ozelligi_degistirme_sql(
    istek: SutunOzelligiDegistirmeIstegi,
) -> tuple[str, ...]:
    tablo = adi_dogrula(istek.tablo, "tablo")
    gecici = tablo + GECICI_AD_EKI
    adlar = tuple(adi_dogrula(s.ad, "sütun") for s in istek.sutunlar)
    return (
        _tablo_tanimi(gecici, istek.sutunlar, istek.kisitlar, istek.secenekler),
        _kopyalama_sql(gecici, tablo, adlar),
        f"DROP TABLE {_tirnakla(tablo)}",
        f"ALTER TABLE {_tirnakla(gecici)} RENAME TO {_tirnakla(tablo)}",
    )


def indeks_olusturma_sql(istek: IndeksOlusturmaIstegi) -> str:
    indeks = adi_dogrula(istek.indeks, "indeks")
    tablo = adi_dogrula(istek.tablo, "tablo")
    if not istek.sutunlar:
        raise GecersizParca("indeksin en az bir sütunu ya da ifadesi olmalı")
    sutunlar = ", ".join(parcayi_dogrula(s, "indeks sütunu") for s in istek.sutunlar)
    benzersiz = "UNIQUE " if istek.benzersiz else ""
    kosul = (
        f" WHERE {parcayi_dogrula(istek.kosul, 'indeks koşulu')}" if istek.kosul else ""
    )
    return (
        f"CREATE {benzersiz}INDEX {_tirnakla(indeks)} ON {_tirnakla(tablo)} "
        f"({sutunlar}){kosul}"
    )


def indeks_silme_sql(istek: IndeksSilmeIstegi) -> str:
    return f"DROP INDEX {_tirnakla(adi_dogrula(istek.indeks, 'indeks'))}"


# --- işler: tek transaction, bağlantı çağırandan gelir ---------------------------


def istek_sql(istek: YapiIstegi) -> str:
    match istek:
        case TabloOlusturmaIstegi():
            return tablo_olusturma_sql(istek)
        case SutunEklemeIstegi():
            return sutun_ekleme_sql(istek)
        case SutunOzelligiDegistirmeIstegi():
            return ";\n".join(sutun_ozelligi_degistirme_sql(istek))
        case IndeksOlusturmaIstegi():
            return indeks_olusturma_sql(istek)
        case IndeksSilmeIstegi():
            return indeks_silme_sql(istek)


def yeniden_kurma_gerekir(istek: YapiIstegi) -> bool:
    return isinstance(istek, SutunOzelligiDegistirmeIstegi)


@contextmanager
def islem_ac(
    veritabani: Veritabani, istek: YapiIstegi
) -> Generator[Connection, None, None]:
    istek_sql(istek)
    try:
        if yeniden_kurma_gerekir(istek):
            with veritabani.islem_yabanci_anahtar_denetimsiz() as baglanti:
                yield baglanti
        else:
            with veritabani.islem() as oturum:
                yield oturum.connection()
    except YabanciAnahtarIhlali as hata:
        raise MotorHatasi(f"istek uygulanamadı, geri alındı: {hata}") from hata


def uygula_baglantida(baglanti: Connection, istek: YapiIstegi) -> None:
    try:
        match istek:
            case TabloOlusturmaIstegi():
                _tablo_olustur(baglanti, istek)
            case SutunEklemeIstegi():
                _sutun_ekle(baglanti, istek)
            case SutunOzelligiDegistirmeIstegi():
                _sutun_ozelligi_degistir(baglanti, istek)
            case IndeksOlusturmaIstegi():
                baglanti.exec_driver_sql(indeks_olusturma_sql(istek))
            case IndeksSilmeIstegi():
                baglanti.exec_driver_sql(indeks_silme_sql(istek))
    except SQLAlchemyError as hata:
        raise _motor_hatasi(hata) from hata


def _tablo_olustur(baglanti: Connection, istek: TabloOlusturmaIstegi) -> None:
    baglanti.exec_driver_sql(tablo_olusturma_sql(istek))
    _sutunlari_dogrula(baglanti, istek.tablo, tuple(s.ad for s in istek.sutunlar))


def _sutun_ekle(baglanti: Connection, istek: SutunEklemeIstegi) -> None:
    baglanti.exec_driver_sql(sutun_ekleme_sql(istek))
    _son_sutunu_dogrula(baglanti, istek.tablo, istek.sutun.ad)


def _sutun_ozelligi_degistir(
    baglanti: Connection, istek: SutunOzelligiDegistirmeIstegi
) -> None:
    kurma, _, silme, adlandirma = sutun_ozelligi_degistirme_sql(istek)
    tablo, gecici = istek.tablo, istek.tablo + GECICI_AD_EKI
    eski_sutunlar = _yeniden_kurma_on_denetimi(baglanti, istek)
    bagli = _bagli_nesneler(baglanti, tablo)
    sayac = _sayaci_oku(baglanti, tablo)

    for ddl in bagli.once_silinecek:
        baglanti.exec_driver_sql(ddl)
    baglanti.exec_driver_sql(kurma)
    yeni_sutunlar = _sutunlari_dogrula(baglanti, gecici, tuple(eski_sutunlar))
    kopyalanacak = tuple(ad for ad, uretilen in yeni_sutunlar.items() if not uretilen)
    rowid_takma = None
    if not _rowidsiz(baglanti, tablo) and not _rowidsiz(baglanti, gecici):
        rowid_takma = _rowid_takma_adi(tuple(eski_sutunlar))
        if rowid_takma is None:
            raise MotorHatasi(
                f"{tablo}: rowid, _rowid_ ve oid adlarının üçü de sütun; örtük "
                "satır kimliği güvenle okunamaz, iş reddedildi"
            )
    baglanti.exec_driver_sql(_kopyalama_sql(gecici, tablo, kopyalanacak, rowid_takma))
    eski_sayi, yeni_sayi = (_satir_sayisi(baglanti, t) for t in (tablo, gecici))
    if eski_sayi != yeni_sayi:
        raise MotorHatasi(
            f"{tablo}: kopyalama eksik ({eski_sayi} satırdan {yeni_sayi}); "
            "iş geri alındı"
        )
    _kopyayi_dogrula(
        baglanti,
        tablo,
        gecici,
        eski_sayi,
        kopyalanacak,
        rowid_takma,
        istek.deger_donusumu_izinli,
    )
    baglanti.exec_driver_sql(silme)
    baglanti.exec_driver_sql(adlandirma)
    for ddl in bagli.sonra_kurulacak:
        baglanti.exec_driver_sql(ddl)
    if sayac is not None:
        _sayaci_yaz(baglanti, tablo, sayac)


# --- yeniden kurmanın okumaları: yalnız bu işe özel ---------------------------------


def _sutun_bilgisi(baglanti: Connection, tablo: str) -> dict[str, bool]:
    satirlar = baglanti.exec_driver_sql(f"PRAGMA table_xinfo({_tirnakla(tablo)})").all()
    return {str(s[1]): int(s[6]) != 0 for s in satirlar}


def _rowid_takma_adi(sutun_adlari: tuple[str, ...]) -> str | None:
    golgeli = {ad.casefold() for ad in sutun_adlari}
    return next((t for t in ROWID_TAKMA_ADLARI if t not in golgeli), None)


def _sutunlari_dogrula(
    baglanti: Connection, tablo: str, beklenen: tuple[str, ...]
) -> dict[str, bool]:
    sutunlar = _sutun_bilgisi(baglanti, tablo)
    if tuple(sutunlar) != beklenen:
        raise SutunlarUyusmuyor(
            f"{tablo}: SQLite'ın açtığı sütunlar {list(sutunlar)}, istenen "
            f"{list(beklenen)}; bir parça sütun listesini değiştirdi. İş geri alındı."
        )
    return sutunlar


def _son_sutunu_dogrula(baglanti: Connection, tablo: str, ad: str) -> None:
    sutunlar = tuple(_sutun_bilgisi(baglanti, tablo))
    if not sutunlar or sutunlar[-1] != ad:
        raise SutunlarUyusmuyor(
            f"{tablo}: SQLite'ın eklediği son sütun {sutunlar[-1:]}, istenen {ad!r}; "
            "iş geri alındı."
        )


DEGER_DENETIMI_GRUP_BOYUTU = 64


def _kopyayi_dogrula(
    baglanti: Connection,
    tablo: str,
    gecici: str,
    satir_sayisi: int,
    kopyalanan: tuple[str, ...],
    rowid_takma: str | None,
    donusum_izinli: tuple[str, ...],
) -> None:
    anahtarlar: tuple[str, ...]
    if rowid_takma is not None:
        anahtarlar = (rowid_takma,)
    else:
        anahtarlar = yapi.anahtar_sutunlari(baglanti, tablo)
    if not anahtarlar:  # pragma: no cover - WITHOUT ROWID tablonun anahtarı vardır
        raise MotorHatasi(f"{tablo}: satırları eşleştirecek anahtar yok; iş reddedildi")
    e, y = _tirnakla(tablo), _tirnakla(gecici)
    anahtar_adlari = [a if a == rowid_takma else _tirnakla(a) for a in anahtarlar]
    anahtar_kosulu = _dengeli_baglac(
        [
            f"(typeof(e.{a}) IS typeof(y.{a}) AND e.{a} IS y.{a} COLLATE BINARY)"
            for a in anahtar_adlari
        ],
        "AND",
    )
    kaynak = f"FROM {e} AS e JOIN {y} AS y ON {anahtar_kosulu}"
    eslesen = int(baglanti.exec_driver_sql(f"SELECT count(*) {kaynak}").scalar_one())
    if eslesen != satir_sayisi:
        raise KopyaDegerDegisti(
            f"{tablo}: satır kimlikleri korunamadı ({satir_sayisi} satırdan "
            f"{eslesen} eşleşti; anahtar {list(anahtarlar)}); iş geri alındı"
        )
    korunacak = [a for a in kopyalanan if a not in donusum_izinli]
    for i in range(0, len(korunacak), DEGER_DENETIMI_GRUP_BOYUTU):
        grup = korunacak[i : i + DEGER_DENETIMI_GRUP_BOYUTU]
        farklar = _dengeli_baglac(
            [
                f"(typeof(e.{_tirnakla(a)}) IS NOT typeof(y.{_tirnakla(a)}) "
                f"OR e.{_tirnakla(a)} IS NOT y.{_tirnakla(a)} COLLATE BINARY)"
                for a in grup
            ],
            "OR",
        )
        degisen = int(
            baglanti.exec_driver_sql(
                f"SELECT count(*) {kaynak} WHERE {farklar}"
            ).scalar_one()
        )
        if degisen:
            raise KopyaDegerDegisti(
                f"{tablo}: kopyada {degisen} satırın değeri ya da saklama sınıfı "
                f"değişti (sütunlar {grup}); bilerek dönüştürme için "
                "deger_donusumu_izinli kullanılır. İş geri alındı"
            )


def _dengeli_baglac(kosullar: list[str], baglac: str) -> str:
    if len(kosullar) == 1:
        return kosullar[0]
    orta = len(kosullar) // 2
    sol = _dengeli_baglac(kosullar[:orta], baglac)
    sag = _dengeli_baglac(kosullar[orta:], baglac)
    return f"({sol} {baglac} {sag})"


def _rowidsiz(baglanti: Connection, tablo: str) -> bool:
    satirlar = baglanti.exec_driver_sql(f"PRAGMA table_list({_tirnakla(tablo)})").all()
    return any(
        str(s[1]) == tablo and str(s[0]) == "main" and int(s[4]) != 0 for s in satirlar
    )


def _satir_sayisi(baglanti: Connection, tablo: str) -> int:
    return int(
        baglanti.exec_driver_sql(
            f"SELECT count(*) FROM {_tirnakla(tablo)}"
        ).scalar_one()
    )


def _yeniden_kurma_on_denetimi(
    baglanti: Connection, istek: SutunOzelligiDegistirmeIstegi
) -> dict[str, bool]:
    tablo = istek.tablo
    mevcut_sutunlar = _sutun_bilgisi(baglanti, tablo)
    if not mevcut_sutunlar:
        raise MotorHatasi(f"tablo yok: {tablo}")
    izinsiz = [a for a in istek.deger_donusumu_izinli if a not in mevcut_sutunlar]
    if izinsiz:
        raise SutunlarUyusmuyor(
            f"{tablo}: deger_donusumu_izinli tablonun sütunu olmalı: {izinsiz}"
        )
    kimlik = yapi.anahtar_sutunlari(baglanti, tablo)
    kimlikte = [a for a in istek.deger_donusumu_izinli if a in kimlik]
    if kimlikte:
        raise SutunlarUyusmuyor(
            f"{tablo}: kimlik sütununa dönüşüm izni verilemez: {kimlikte} "
            f"(kimlik {list(kimlik)}); kimlik her zaman aynen korunur"
        )
    temp = baglanti.exec_driver_sql(
        "SELECT type, name FROM sqlite_temp_master WHERE type IN ('trigger', 'view')"
    ).all()
    if temp:
        raise MotorHatasi(
            f"{tablo}: bağlantıda TEMP nesne var ({[f'{t[0]} {t[1]}' for t in temp]}); "
            "yeniden kurma TEMP trigger/görünümü taşıyamaz, iş reddedildi"
        )

    mevcut = tuple(mevcut_sutunlar)
    istenen = tuple(s.ad for s in istek.sutunlar)
    if mevcut != istenen:
        eksik = [a for a in mevcut if a not in istenen]
        fazla = [a for a in istenen if a not in mevcut]
        neden = f"eksik {eksik}, fazla {fazla}" if eksik or fazla else "sıra farklı"
        raise SutunlarUyusmuyor(
            f"{tablo}: sütun adları birebir aynı olmalı ({neden}); "
            f"mevcut {list(mevcut)}, istenen {list(istenen)}. Sütun ekleme, "
            "silme ve yeniden adlandırma bu işin dışındadır."
        )

    tanim = str(
        baglanti.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (tablo,)
        ).scalar_one()
    )
    try:
        parcalar, kuyruk = _tanim_parcalari(tanim)
    except ValueError as hata:
        raise MotorHatasi(f"{tablo}: tanım metni okunamadı: {hata}") from None
    mevcut_kisit = sorted(_sadelestir(k) for k in parcalar[len(mevcut) :])
    istenen_kisit = sorted(_sadelestir(k) for k in istek.kisitlar)
    if mevcut_kisit != istenen_kisit:
        raise KisitlarUyusmuyor(
            f"{tablo}: tablo düzeyi kısıtlar birebir aynı olmalı; mevcut "
            f"{mevcut_kisit}, istenen {istenen_kisit}. Kısıt ekleme, silme ve "
            "değiştirme bu işin dışındadır."
        )
    mevcut_secenek = sorted(_sadelestir(s) for s in _ust_duzey_parcalar(kuyruk))
    istenen_secenek = sorted(_sadelestir(s) for s in istek.secenekler)
    if mevcut_secenek != istenen_secenek:
        raise KisitlarUyusmuyor(
            f"{tablo}: tablo seçenekleri aynı olmalı; mevcut {mevcut_secenek}, "
            f"istenen {istenen_secenek}. Seçenek değiştirme bu işin dışındadır."
        )
    return mevcut_sutunlar


def _sadelestir(parca: str) -> str:
    bolumler: list[str] = []
    i, n = 0, len(parca)
    disari: list[str] = []

    def disariyi_kapat() -> None:
        metin = re.sub(r"\s+", " ", "".join(disari)).casefold()
        metin = re.sub(r"\s*([(),])\s*", r"\1", metin)
        bolumler.append(metin)
        disari.clear()

    while i < n:
        c = parca[i]
        if c in "\"'`[":
            kapanis = "]" if c == "[" else c
            j = parca.find(kapanis, i + 1)
            j = n - 1 if j < 0 else j
            disariyi_kapat()
            bolumler.append(parca[i : j + 1])
            i = j + 1
            continue
        if parca.startswith("--", i):
            j = parca.find("\n", i)
            i = n if j < 0 else j + 1
            disari.append(" ")
            continue
        if parca.startswith("/*", i):
            j = parca.find("*/", i + 2)
            i = n if j < 0 else j + 2
            disari.append(" ")
            continue
        disari.append(c)
        i += 1
    disariyi_kapat()
    return "".join(bolumler).strip()


@dataclass(frozen=True, slots=True)
class _BagliNesneler:
    once_silinecek: tuple[str, ...]
    sonra_kurulacak: tuple[str, ...]


def _bagli_nesneler(baglanti: Connection, tablo: str) -> _BagliNesneler:
    satirlar = baglanti.exec_driver_sql(
        "SELECT type, name, tbl_name, sql FROM sqlite_master "
        "WHERE type IN ('index', 'trigger', 'view') AND sql IS NOT NULL "
        "ORDER BY rowid"
    ).all()
    triggerlar: list[str] = []
    gorunumler: list[str] = []
    kurulacak: list[str] = []
    for tur, ad, tbl, sql in (
        (str(r[0]), str(r[1]), str(r[2]), str(r[3])) for r in satirlar
    ):
        if tur == "index":
            if tbl == tablo:
                kurulacak.append(sql)
            continue
        kurulacak.append(sql)
        dusur = f'DROP {tur.upper()} "{ad.replace(chr(34), chr(34) * 2)}"'
        (triggerlar if tur == "trigger" else gorunumler).append(dusur)
    # Önce bütün trigger'lar, sonra görünümler; ikisi de oluşturma sırasının
    # tersinden. Görünüm silinince INSTEAD OF trigger'ı kendiliğinden gider.
    silinecek = (*reversed(triggerlar), *reversed(gorunumler))
    return _BagliNesneler(silinecek, tuple(kurulacak))


def _sayaci_oku(baglanti: Connection, tablo: str) -> int | None:
    var = baglanti.exec_driver_sql(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sqlite_sequence'"
    ).first()
    if var is None:
        return None
    satir = baglanti.exec_driver_sql(
        "SELECT seq FROM sqlite_sequence WHERE name = ?", (tablo,)
    ).first()
    return None if satir is None else int(satir[0])


def _sayaci_yaz(baglanti: Connection, tablo: str, sayac: int) -> None:
    sonuc = baglanti.exec_driver_sql(
        "UPDATE sqlite_sequence SET seq = ? WHERE name = ?", (sayac, tablo)
    )
    if sonuc.rowcount == 0:
        baglanti.exec_driver_sql(
            "INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)", (tablo, sayac)
        )


# --- tarayıcı: ayrıştırma değil, tırnak/yorum/parantez izleme -----------------------


def _acik_karakterler(sql: str) -> tuple[list[tuple[int, str, int]], int, bool]:
    sonuc: list[tuple[int, str, int]] = []
    i, n, derinlik = 0, len(sql), 0
    yorum_var = False
    while i < n:
        c = sql[i]
        if c in "\"'`[":
            kapanis = "]" if c == "[" else c
            j = sql.find(kapanis, i + 1)
            if j < 0:
                raise ValueError(f"kapanmayan tırnak {c}")
            sonuc.append((i, '"', derinlik))
            i = j + 1
            continue
        if sql.startswith("--", i):
            yorum_var = True
            j = sql.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if sql.startswith("/*", i):
            yorum_var = True
            j = sql.find("*/", i + 2)
            if j < 0:
                raise ValueError("kapanmayan yorum")
            i = j + 2
            continue
        if c == "(":
            derinlik += 1
            sonuc.append((i, c, derinlik))
        elif c == ")":
            sonuc.append((i, c, derinlik))
            derinlik -= 1
        else:
            sonuc.append((i, c, derinlik))
        i += 1
    return sonuc, derinlik, yorum_var


def _tanim_parcalari(sql: str) -> tuple[list[str], str]:
    karakterler, _, _ = _acik_karakterler(sql)
    parcalar: list[str] = []
    baslangic = -1
    for konum, c, derinlik in karakterler:
        if derinlik == 0:
            continue
        if c == "(" and derinlik == 1:
            parcalar, baslangic = [], konum + 1
        elif derinlik == 1 and c in ",)":
            parca = sql[baslangic:konum].strip()
            if parca:
                parcalar.append(parca)
            if c == ")":
                return parcalar, sql[konum + 1 :].strip()
            baslangic = konum + 1
    return [], ""


def _ust_duzey_parcalar(metin: str) -> list[str]:
    karakterler, _, _ = _acik_karakterler(metin)
    kesimler = [k for k, c, d in karakterler if d == 0 and c == ","]
    sinirlar = [-1, *kesimler, len(metin)]
    parcalar = [metin[a + 1 : b] for a, b in pairwise(sinirlar)]
    return [p.strip() for p in parcalar if p.strip()]


# --- hata çevirisi ----------------------------------------------------------------


def _motor_hatasi(hata: SQLAlchemyError) -> MotorHatasi:
    neden = hata.orig if isinstance(hata, DBAPIError) else hata
    return MotorHatasi(f"istek uygulanamadı, geri alındı: {neden}")
