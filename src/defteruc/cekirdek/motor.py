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
* Kural koymaz. İki teknik sınır vardır, ikisi de SQL'e güvenle yazılabilmek
  içindir: ad biçimi (``AD_BICIMI``: tablo ve sütun adları sade, Türkçe
  karaktersiz; karar 2026-09-24) ve özellik parçası bütünlüğü
  (``ozelligi_dogrula``: bir parça tek sütunun tanımında kalır; üst düzeyde
  virgül ya da noktalı virgül taşıyamaz, parantez ve tırnakları dengeli
  olmalıdır). İkincisi olmadan ``"TEXT, UNIQUE(a)"`` gibi bir parça sütun
  tanımından çıkıp tablo düzeyi kısıt yazardı. Bunlar dışında tek istisna
  sütun özelliği değiştirmenin emniyet kurallarıdır (aşağıda).

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
* **Bağlı nesneler taşınır:** tablonun indeksleri ve trigger'ları tabloyla
  birlikte silinir; tabloya değinen görünümler ve başka tabloların
  trigger'ları ise yeniden adlandırmayı düşürür (SQLite şemayı yeniden
  ayrıştırır, tablo o an yoktur). Hangi görünümün tabloya değindiği
  ayrıştırmadan bilinemez (görünümün görünümü). Bu yüzden motor tablonun
  indekslerini ve veritabanındaki **bütün** görünüm ve trigger'ları
  ``sqlite_master``'dan **oluşturma cümleleriyle** alır (SQLite cümleyi
  olduğu gibi saklar; ayrıştırma yoktur), görünüm ve trigger'ları işten
  önce siler (önce bütün trigger'lar, sonra görünümler, her biri oluşturma
  sırasının tersinden: görünüm silinince ``INSTEAD OF`` trigger'ı da
  gider, tersi sırada ikinci ``DROP`` düşerdi), tabloyu kurar, sonra
  hepsini oluşturma sırasıyla aynı cümleyle geri açar. Aynı transaction'da
  aynı cümleyle geri açılan nesne kayıpsızdır. Bir cümle yeni tanıma
  uymuyorsa SQLite düşürür, iş geri alınır.
* **AUTOINCREMENT sayacı korunur:** tablo silinince ``sqlite_sequence``
  kaydı da silinir, yeni tablonun sayacı taşınan en büyük kimlikten başlar
  ve silinmiş kimlikler yeniden dağıtılırdı. Motor sayacı işten önce okur,
  yeniden kurmadan sonra aynı değere geri yazar.
* **Sessiz kayıp yok:** tablo düzeyi kısıtlar (``PRIMARY KEY (a, b)``,
  ``UNIQUE (...)``, ``CHECK (...)``, ``FOREIGN KEY ...``, ``CONSTRAINT ...``)
  ve tablo seçenekleri (``WITHOUT ROWID``, ``STRICT``) ``CREATE TABLE``
  metninin içindedir; motor bu metni ayrıştırmadığı ve istek onları
  taşımadığı için yeniden kurmada kaybolurlardı. Bunlar henüz desteklenmez;
  motor DDL'den önce tespit eder ve ``DesteklenmeyenYapi`` ile reddeder.
  Tespit ayrıştırma değildir: metnin en dış parantezindeki üst düzey parça
  sayısı sütun sayısından fazlaysa sütun olmayan bir parça vardır.
  Üretilen/gizli sütunlar da desteklenmez. Motorun kendi açtığı tablolarda
  bunlar olmaz (``tablo_olustur`` yalnız sütun yazar).
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


class GecersizOzellik(MotorHatasi, ValueError):
    """Özellik parçası tek sütunun tanımında kalmıyor (üst düzeyde virgül ya da
    noktalı virgül, dengesiz parantez, kapanmayan tırnak/yorum) ya da boş.
    Veritabanına dokunulmadı."""


class SutunlarUyusmuyor(MotorHatasi):
    """Sütun özelliği değiştirme: istekteki sütun adları mevcut tablonunkilerle
    sırasıyla birebir aynı değil; veritabanına dokunulmadı."""


class DesteklenmeyenYapi(MotorHatasi):
    """Sütun özelliği değiştirme: tabloda yeniden kurmanın taşıyamayacağı bir
    yapı var (tablo düzeyi kısıt, tablo seçeneği, gizli sütun); sessizce
    kaybetmemek için reddedildi, veritabanına dokunulmadı."""


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


def ozelligi_dogrula(parca: str) -> str:
    """Özellik parçasının tek sütunun tanımında kaldığını denetler; kalmıyorsa
    ``GecersizOzellik``. Parçanın anlamına bakılmaz (onu SQLite belirler);
    yalnız sınırı aşıp aşmadığına bakılır: üst düzeyde ``,`` ya da ``;`` yok,
    parantezler dengeli, tırnak ve yorumlar kapalı, boş değil."""
    if not parca.strip():
        raise GecersizOzellik("özellik parçası boş olamaz")
    try:
        karakterler, son_derinlik = _acik_karakterler(parca)
    except ValueError as hata:
        raise GecersizOzellik(f"özellik parçası: {hata}: {parca!r}") from None
    for _, c, derinlik in karakterler:
        if derinlik == 0 and c in ",;":
            raise GecersizOzellik(
                f"özellik parçası tek sütunun tanımında kalmalı; üst düzeyde "
                f"{c!r} olamaz: {parca!r}"
            )
        if c == ")" and derinlik == 0:
            raise GecersizOzellik(f"özellik parçasında parantez dengesiz: {parca!r}")
    if son_derinlik != 0:
        raise GecersizOzellik(f"özellik parçasında parantez dengesiz: {parca!r}")
    return parca


def _sutun_tanimi(sutun: Sutun) -> str:
    parcalar = [
        f'"{adi_dogrula(sutun.ad, "sütun")}"',
        *(ozelligi_dogrula(p) for p in sutun.ozellikler),
    ]
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
    hiçbir DDL çalışmaz. Sonra tabloya bağlı görünüm ve trigger'lar silinir,
    tablo yeniden kurulur, indeks/trigger/görünümler saklı oluşturma
    cümleleriyle geri açılır. Düşen iş bütünüyle geri alınır; eski tablo kalır.
    """
    adimlar = sutun_ozelligi_degistirme_sql(istek)
    try:
        with veritabani.islem_yabanci_anahtar_denetimsiz() as oturum:
            baglanti = oturum.connection()
            _yeniden_kurma_on_denetimi(baglanti, istek)
            bagli = _bagli_nesneler(baglanti, istek.tablo)
            sayac = _sayaci_oku(baglanti, istek.tablo)
            for ddl in (*bagli.once_silinecek, *adimlar, *bagli.sonra_kurulacak):
                baglanti.exec_driver_sql(ddl)
            if sayac is not None:
                _sayaci_yaz(baglanti, istek.tablo, sayac)
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

    tanim = baglanti.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (tablo,)
    ).scalar_one()
    try:
        parca_sayisi, kuyruk = _ust_duzey_parca_sayisi(str(tanim))
    except ValueError as hata:
        raise DesteklenmeyenYapi(f"{tablo}: tanım metni okunamadı: {hata}") from None
    if parca_sayisi != len(mevcut):
        raise DesteklenmeyenYapi(
            f"{tablo}: tablo düzeyi kısıt var (sütun olmayan "
            f"{parca_sayisi - len(mevcut)} parça); yeniden kurma taşımaz"
        )
    if kuyruk:
        raise DesteklenmeyenYapi(f"{tablo}: tablo seçeneği var: {kuyruk!r}")


@dataclass(frozen=True, slots=True)
class _BagliNesneler:
    """Yeniden kurmada taşınacak nesneler: önce silinecek ``DROP`` cümleleri ve
    sonra oluşturma sırasıyla geri açılacak saklı ``CREATE`` cümleleri."""

    once_silinecek: tuple[str, ...]
    sonra_kurulacak: tuple[str, ...]


def _bagli_nesneler(baglanti: Connection, tablo: str) -> _BagliNesneler:
    """Tablonun indeksleri (tabloyla silinir) ve veritabanındaki bütün görünüm
    ve trigger'lar (tabloya değinenler yeniden adlandırmayı düşürür; hangisi
    değiniyor ayrıştırmadan bilinemez). Otomatik indekslerin (``sql`` boş;
    kısıtlardan gelir) cümlesi yoktur, yeni ``CREATE TABLE`` ile oluşur."""
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
    """Tablonun ``AUTOINCREMENT`` sayacı (``sqlite_sequence``); yoksa ``None``."""
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
    """``sqlite_sequence``'ta ad benzersiz değildir; ``INSERT OR REPLACE`` ikinci
    satır açar. Var olan satır güncellenir, yoksa eklenir."""
    sonuc = baglanti.exec_driver_sql(
        "UPDATE sqlite_sequence SET seq = ? WHERE name = ?", (sayac, tablo)
    )
    if sonuc.rowcount == 0:
        baglanti.exec_driver_sql(
            "INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)", (tablo, sayac)
        )


def _acik_karakterler(sql: str) -> tuple[list[tuple[int, str, int]], int]:
    """Tırnak ve yorum dışındaki karakterler ``(konum, karakter, derinlik)``
    olarak, ve bitişteki parantez derinliği. Tırnaklı bölüm tek bir ``"``
    karakteri olarak temsil edilir (içeriği önemsiz, varlığı önemli).
    ``(`` kendi açtığı, ``)`` kendi kapattığı derinlikle verilir.

    Ayrıştırma değildir: yalnız tırnak (``"``, ``'``, backtick, ``[ ]``),
    yorum (``--``, ``/* */``) ve parantez derinliği izlenir. Kapanmayan tırnak
    ya da yorum ``ValueError``.
    """
    sonuc: list[tuple[int, str, int]] = []
    i, n, derinlik = 0, len(sql), 0
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
            j = sql.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if sql.startswith("/*", i):
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
    return sonuc, derinlik


def _ust_duzey_parca_sayisi(sql: str) -> tuple[int, str]:
    """``CREATE TABLE`` metninin en dış parantezindeki üst düzey (virgülle
    ayrılmış) parça sayısı ve kapanış parantezinden sonraki kuyruk. Boş gövde
    0 parçadır. Ayrıştırma değildir (``_acik_karakterler``)."""
    karakterler, _ = _acik_karakterler(sql)
    parca = 0
    govde_dolu = False
    for konum, c, derinlik in karakterler:
        if derinlik == 0:
            continue
        if c == "(" and derinlik == 1:
            parca, govde_dolu = 0, False
        elif c == ")" and derinlik == 1:
            return (parca + 1 if govde_dolu else 0, sql[konum + 1 :].strip())
        elif derinlik == 1 and c == ",":
            parca += 1
        elif not c.isspace():
            govde_dolu = True
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
