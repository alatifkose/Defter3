"""Motor: tablo oluşturur, sütun ekler, sütun özelliği değiştirir (karar 2026-09-24).

Motor yalnız bir araçtır. Cowork belgeyi okur, ne gerektiğine karar verir ve
motoru kullanır; **kullanıcı onayını uygulama alır**. Bu modül onay almaz ve
onay sormaz: motoru yalnız uygulama, onay alındıktan sonra çağırır.

Motorun yaptıkları:

* ``tablo_olustur``: verilen adla, verilen sütunlarla tablo açar.
* ``sutun_ekle``: var olan tabloya sütun ekler.
* ``sutun_ozelligi_degistir``: var olan sütunların özelliğini değiştirir.
  SQLite sütunu yerinde değiştiremez; tablo, isteğin taşıdığı **tam** yeni
  tanımla yeniden kurulur (aşağıda "Sütun özelliği değiştirme").
* Sütun özelliği, ekleme isteğinin içinde gider: ``Sutun.ozellikler`` sütun
  adından sonra yazılacak parçalardır (ör. ``("TEXT", "NOT NULL")``,
  ``("INTEGER", "REFERENCES kisiler(id)")``). **Özellik listesi koda gömülü
  değildir;** istekte ne geldiyse o yazılır. Geçerliliğini SQLite belirler.

Motorun yapmadıkları:

* Hazır tablo taşımaz ve hiçbir özelliği ismen bilmez. Sütunların görünen
  adı gibi tanım bilgileri de sıradan bir tablodur: Cowork o tabloyu da bu
  motorla açar, eşleşmeleri satır olarak yazar (kayıt). Motor bunu bilmez.
* Hafızası yoktur: işlemler arası durum tutmaz, katalog taşımaz.
* Mevcut yapıyı okumaz: tablonun var olup olmadığına, sütunun daha önce
  eklenip eklenmediğine bakmaz. Uygun düşmeyen istek SQLite'ta düşer ve
  ``MotorHatasi`` olarak yükselir. (Tek istisna: sütun özelliği değiştirmenin
  yalnız reddetmek için yaptığı ön denetim, aşağıda.)
* Bir şey göstermez ve karar vermez: dönüş değeri yoktur.
* Kural koymaz. Tek teknik sınır ad biçimidir (``AD_BICIMI``): tablo ve sütun
  adları sade yazılır, Türkçe karakter yoktur (karar 2026-09-24). Bu sınır
  SQL'e adın güvenle yazılabilmesi içindir. Tek istisna sütun özelliği
  değiştirmenin emniyet kurallarıdır (aşağıda).

Sütun özelliği değiştirme (karar 2026-09-24):

* İstek (``SutunOzelligiDegistirmeIstegi``) tablonun **yeni hâlini bütün
  sütunlarıyla** taşır; motor tanımı okuyup türetmez. Adımlar SQLite'ın resmî
  tablo yeniden kurma tarifidir: geçici adla yeni tablo, satırların aynı adlı
  sütunlar üzerinden taşınması, eski tablonun silinmesi, geçici tablonun eski
  adı alması. Hepsi ``foreign_keys=OFF`` ile tek transaction'dadır
  (``Veritabani.islem_yabanci_anahtar_denetimsiz``); ``commit`` öncesi
  ``PRAGMA foreign_key_check`` çalışır. Herhangi bir adım düşerse (örn. yeni
  özelliğe uymayan satır) iş bütünüyle geri alınır, eski tablo eksiksiz kalır.
* **Emniyet kuralı:** bu iş yalnız mevcut sütunların özelliğini değiştirir;
  sütun ekleyemez, silemez, adını ya da sırasını değiştiremez. Motor DDL'den
  önce ``PRAGMA table_xinfo`` ile mevcut sütun adlarını okur; istekteki
  adlarla sırasıyla birebir aynı değilse (eksik, fazla, farklı) hiçbir şey
  yapmadan ``SutunlarUyusmuyor`` verir.
* **Sessiz kayıp yok:** yeniden kurma, tabloya bağlı indeksleri, trigger'ları
  ve tablo düzeyi kısıtları (``PRIMARY KEY (a, b)``, ``UNIQUE (...)``,
  ``CHECK (...)``, ``FOREIGN KEY ...``, ``CONSTRAINT ...``) ve tablo
  seçeneklerini (``WITHOUT ROWID``, ``STRICT``) taşımaz; bunlar henüz
  desteklenmez. Motor DDL'den önce bunları tespit eder (``PRAGMA
  index_list``, ``sqlite_master``) ve bulursa ``DesteklenmeyenYapi`` ile
  reddeder. Tablo düzeyi kısıt tespiti ``sqlite_master`` metnini
  **ayrıştırmaz**: metnin en dış parantezindeki üst düzey parça sayısı sütun
  sayısından fazlaysa sütun olmayan bir parça vardır. Tabloya adıyla değinen
  görünüm ve trigger'lar da reddedilir (yeniden adlandırma onları bozar).
  Üretilen/gizli sütunlar da desteklenmez.
* Bu okumalar yalnız bu işe özeldir ve yalnız reddetmek içindir; motor
  okuduğunu tanıma dönüştürmez, karar vermez, göstermez.

Bir iş = bir transaction (``Veritabani.islem``): düşen istek bütünüyle geri
alınır. DDL metni ``exec_driver_sql`` ile sürücüye olduğu gibi verilir;
özellik parçalarının içindeki ``:`` bağlama parametresi sanılmaz. Sürücü tek
seferde tek ifade çalıştırır.

``tablo_olusturma_sql``, ``sutun_ekleme_sql`` ve
``sutun_ozelligi_degistirme_sql`` veritabanına dokunmaz; uygulama onay
penceresinde ne yapılacağını göstermek için kullanabilir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import Connection
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from defteruc.cekirdek.veritabani import Veritabani, YabanciAnahtarIhlali

AD_BICIMI = re.compile(r"^[a-z][a-z0-9_]*$")
"""Tablo ve sütun adı: küçük ASCII harfle başlar; harf, rakam, alt çizgi."""


class MotorHatasi(Exception):
    """Motor isteği uygulayamadı; iş bütünüyle geri alındı."""


class GecersizAd(MotorHatasi, ValueError):
    """Tablo ya da sütun adı ``AD_BICIMI``'ne uymuyor."""


class SutunlarUyusmuyor(MotorHatasi):
    """Sütun özelliği değiştirme: istekteki sütun adları mevcut tablonunkilerle
    sırasıyla birebir aynı değil; veritabanına dokunulmadı."""


class DesteklenmeyenYapi(MotorHatasi):
    """Sütun özelliği değiştirme: tabloda yeniden kurmanın taşıyamayacağı bir
    yapı var (indeks, trigger, görünüm, tablo düzeyi kısıt, tablo seçeneği,
    gizli sütun); sessizce kaybetmemek için reddedildi, veritabanına
    dokunulmadı."""


@dataclass(frozen=True, slots=True)
class Sutun:
    """Bir sütun isteği.

    ``ad``: teknik ad (sade, Türkçe karaktersiz).
    ``ozellikler``: sütun adından sonra sırayla yazılacak parçalar; istekte ne
    geldiyse o. Boş olabilir (SQLite türsüz sütuna izin verir).
    """

    ad: str
    ozellikler: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TabloOlusturmaIstegi:
    tablo: str
    sutunlar: tuple[Sutun, ...]


@dataclass(frozen=True, slots=True)
class SutunEklemeIstegi:
    tablo: str
    sutun: Sutun


@dataclass(frozen=True, slots=True)
class SutunOzelligiDegistirmeIstegi:
    """Tablonun yeni hâli: bütün sütunlar, mevcutla aynı ad ve sırada, yeni
    özellikleriyle."""

    tablo: str
    sutunlar: tuple[Sutun, ...]


GECICI_AD_EKI = "__yeniden_kurma"
"""Yeniden kurma sırasında yeni tablonun geçici adı: ``<tablo>__yeniden_kurma``."""


def adi_dogrula(ad: str, ne: str) -> str:
    """Adı ``AD_BICIMI``'ne göre denetler; uymuyorsa ``GecersizAd``."""
    if not AD_BICIMI.fullmatch(ad):
        raise GecersizAd(
            f"{ne} adı sade olmalı (küçük ASCII harfle başlar; harf, rakam, "
            f"alt çizgi; Türkçe karakter yok): {ad!r}"
        )
    return ad


def _sutun_tanimi(sutun: Sutun) -> str:
    parcalar = [f'"{adi_dogrula(sutun.ad, "sütun")}"', *sutun.ozellikler]
    return " ".join(parcalar)


def tablo_olusturma_sql(istek: TabloOlusturmaIstegi) -> str:
    """İsteğin ``CREATE TABLE`` metni; veritabanına dokunmaz."""
    tablo = adi_dogrula(istek.tablo, "tablo")
    govde = ", ".join(_sutun_tanimi(s) for s in istek.sutunlar)
    return f'CREATE TABLE "{tablo}" ({govde})'


def sutun_ekleme_sql(istek: SutunEklemeIstegi) -> str:
    """İsteğin ``ALTER TABLE ... ADD COLUMN`` metni; veritabanına dokunmaz."""
    tablo = adi_dogrula(istek.tablo, "tablo")
    return f'ALTER TABLE "{tablo}" ADD COLUMN {_sutun_tanimi(istek.sutun)}'


def sutun_ozelligi_degistirme_sql(
    istek: SutunOzelligiDegistirmeIstegi,
) -> tuple[str, ...]:
    """Yeniden kurma adımlarının DDL metinleri, sırayla; veritabanına dokunmaz."""
    tablo = adi_dogrula(istek.tablo, "tablo")
    gecici = tablo + GECICI_AD_EKI
    adlar = ", ".join(f'"{adi_dogrula(s.ad, "sütun")}"' for s in istek.sutunlar)
    return (
        tablo_olusturma_sql(TabloOlusturmaIstegi(gecici, istek.sutunlar)),
        f'INSERT INTO "{gecici}" ({adlar}) SELECT {adlar} FROM "{tablo}"',
        f'DROP TABLE "{tablo}"',
        f'ALTER TABLE "{gecici}" RENAME TO "{tablo}"',
    )


def tablo_olustur(veritabani: Veritabani, istek: TabloOlusturmaIstegi) -> None:
    """Tabloyu açar; tek transaction."""
    _uygula(veritabani, tablo_olusturma_sql(istek))


def sutun_ekle(veritabani: Veritabani, istek: SutunEklemeIstegi) -> None:
    """Tabloya sütun ekler; tek transaction."""
    _uygula(veritabani, sutun_ekleme_sql(istek))


def sutun_ozelligi_degistir(
    veritabani: Veritabani, istek: SutunOzelligiDegistirmeIstegi
) -> None:
    """Tabloyu isteğin tanımıyla yeniden kurar; tek transaction, ``foreign_keys=OFF``.

    Önce ad biçimi (dokunmadan), sonra transaction içinde ama DDL'den önce
    emniyet denetimleri: sütun adları birebir aynı mı (``SutunlarUyusmuyor``),
    taşınamayacak yapı var mı (``DesteklenmeyenYapi``). Denetimler geçmezse
    hiçbir DDL çalışmaz. Düşen iş bütünüyle geri alınır; eski tablo kalır.
    """
    adimlar = sutun_ozelligi_degistirme_sql(istek)
    try:
        with veritabani.islem_yabanci_anahtar_denetimsiz() as oturum:
            baglanti = oturum.connection()
            _yeniden_kurma_on_denetimi(baglanti, istek)
            for ddl in adimlar:
                baglanti.exec_driver_sql(ddl)
    except YabanciAnahtarIhlali as hata:
        raise MotorHatasi(f"istek uygulanamadı, geri alındı: {hata}") from hata
    except SQLAlchemyError as hata:
        raise _motor_hatasi(hata) from hata


def _yeniden_kurma_on_denetimi(
    baglanti: Connection, istek: SutunOzelligiDegistirmeIstegi
) -> None:
    tablo = istek.tablo
    xinfo = baglanti.exec_driver_sql(f'PRAGMA table_xinfo("{tablo}")').all()
    if not xinfo:
        raise MotorHatasi(f"tablo yok: {tablo}")
    gizli = [str(s[1]) for s in xinfo if int(s[6]) != 0]
    if gizli:
        raise DesteklenmeyenYapi(f"{tablo}: üretilen/gizli sütun: {gizli}")

    mevcut = tuple(str(s[1]) for s in xinfo)
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

    indeksler = baglanti.exec_driver_sql(f'PRAGMA index_list("{tablo}")').all()
    acik_indeksler = [str(i[1]) for i in indeksler if i[3] == "c"]
    if acik_indeksler:
        raise DesteklenmeyenYapi(f"{tablo}: indeks var: {acik_indeksler}")

    deginen = re.compile(rf"\b{re.escape(tablo)}\b", re.IGNORECASE)
    bagimlilar = baglanti.exec_driver_sql(
        "SELECT type, name, sql FROM sqlite_master "
        "WHERE type IN ('trigger', 'view') AND sql IS NOT NULL"
    ).all()
    ilgili = [f"{b[0]} {b[1]}" for b in bagimlilar if deginen.search(str(b[2]))]
    if ilgili:
        raise DesteklenmeyenYapi(f"{tablo}: tabloya değinen trigger/görünüm: {ilgili}")

    tanim = baglanti.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (tablo,)
    ).scalar_one()
    parca_sayisi, kuyruk = _ust_duzey_parca_sayisi(str(tanim))
    if parca_sayisi != len(mevcut):
        raise DesteklenmeyenYapi(
            f"{tablo}: tablo düzeyi kısıt var (sütun olmayan "
            f"{parca_sayisi - len(mevcut)} parça); yeniden kurma taşımaz"
        )
    if kuyruk:
        raise DesteklenmeyenYapi(f"{tablo}: tablo seçeneği var: {kuyruk!r}")


def _ust_duzey_parca_sayisi(sql: str) -> tuple[int, str]:
    """``CREATE TABLE`` metninin en dış parantezindeki üst düzey (virgülle
    ayrılmış) parça sayısı ve kapanış parantezinden sonraki kuyruk.

    Ayrıştırma değildir: yalnız tırnak (``"``, ``'``, backtick, ``[ ]``),
    yorum (``--``, ``/* */``) ve parantez derinliği izlenir. Boş gövde 0
    parçadır.
    """
    i, n = 0, len(sql)
    derinlik = 0
    parca = 0
    govde_dolu = False
    while i < n:
        c = sql[i]
        if c in "\"'`[":
            kapanis = "]" if c == "[" else c
            j = sql.find(kapanis, i + 1)
            i = n if j < 0 else j + 1
            govde_dolu = govde_dolu or derinlik == 1
            continue
        if sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c == "(":
            derinlik += 1
            if derinlik == 1:
                parca, govde_dolu = 0, False
            else:
                govde_dolu = True
        elif c == ")":
            derinlik -= 1
            if derinlik == 0:
                return (parca + 1 if govde_dolu else 0, sql[i + 1 :].strip())
        elif derinlik == 1:
            if c == ",":
                parca += 1
            elif not c.isspace():
                govde_dolu = True
        i += 1
    return 0, ""


def _uygula(veritabani: Veritabani, ddl: str) -> None:
    try:
        with veritabani.islem() as oturum:
            oturum.connection().exec_driver_sql(ddl)
    except SQLAlchemyError as hata:
        raise _motor_hatasi(hata) from hata


def _motor_hatasi(hata: SQLAlchemyError) -> MotorHatasi:
    neden = hata.orig if isinstance(hata, DBAPIError) else hata
    return MotorHatasi(f"istek uygulanamadı, geri alındı: {neden}")
