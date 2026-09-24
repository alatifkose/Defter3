"""Motor: tablo, sütun, sütun özelliği ve indeks işleri (karar 2026-09-24).

Motor yalnız bir araçtır. Cowork belgeyi okur, ne gerektiğine karar verir ve
motoru kullanır; **kullanıcı onayını uygulama alır**. Bu modül onay almaz ve
onay sormaz: motoru yalnız uygulama, onay alındıktan sonra çağırır.

Motorun yaptıkları:

* ``tablo_olustur``: verilen adla, verilen sütunlar, tablo düzeyi kısıtlar ve
  tablo seçenekleriyle tablo açar.
* ``sutun_ekle``: var olan tabloya sütun ekler.
* ``sutun_ozelligi_degistir``: var olan sütunların özelliğini değiştirir.
  SQLite sütunu yerinde değiştiremez; tablo, isteğin taşıdığı **tam** yeni
  tanımla yeniden kurulur (aşağıda "Sütun özelliği değiştirme").
* ``indeks_olustur`` / ``indeks_sil``: tabloya indeks açar, indeksi siler.

İstek ne taşırsa o yazılır; **hiçbir özellik, kısıt ya da seçenek koda gömülü
değildir**, geçerliliğini SQLite belirler:

* Sütun özelliği: ``Sutun.ozellikler``, sütun adından sonra sırayla yazılan
  parçalar (``("TEXT", "NOT NULL")``, ``("INTEGER", "REFERENCES kisiler(id)")``,
  ``("INTEGER", "GENERATED ALWAYS AS (adet * fiyat) STORED")``).
* Tablo düzeyi kısıt: ``kisitlar``, sütunlardan sonra yazılan parçalar
  (``"PRIMARY KEY (a, b)"``, ``"UNIQUE (a, b)"``, ``"CHECK (a < b)"``,
  ``"FOREIGN KEY (a) REFERENCES t(x)"``, ``"CONSTRAINT ad UNIQUE (a)"``).
* Tablo seçeneği: ``secenekler``, kapanış parantezinden sonra yazılan parçalar
  (``"WITHOUT ROWID"``, ``"STRICT"``).
* İndeks: ``IndeksOlusturmaIstegi.sutunlar`` sütun adı ya da ifade parçaları
  (``"ad_soyad"``, ``"lower(ad_soyad)"``, ``"tarih DESC"``), ``benzersiz``,
  ``kosul`` (kısmi indeks ``WHERE`` ifadesi).

Motorun yapmadıkları:

* Hazır tablo taşımaz ve hiçbir özelliği ismen bilmez. Sütunların görünen
  adı gibi tanım bilgileri de sıradan bir tablodur: Cowork o tabloyu da bu
  motorla açar, eşleşmeleri satır olarak yazar (kayıt). Motor bunu bilmez.
* Hafızası yoktur: işlemler arası durum tutmaz, katalog taşımaz.
* Mevcut yapıyı okumaz: tablonun var olup olmadığına, sütunun daha önce
  eklenip eklenmediğine bakmaz. Uygun düşmeyen istek SQLite'ta düşer ve
  ``MotorHatasi`` olarak yükselir. (Tek istisna: sütun özelliği değiştirmenin
  emniyet denetimi ve kopyalama listesi, aşağıda.)
* Bir şey göstermez ve karar vermez: dönüş değeri yoktur.
* Kural koymaz. İki teknik sınır vardır, ikisi de SQL'e güvenle yazılabilmek
  içindir: ad biçimi (``AD_BICIMI``: tablo, sütun ve indeks adları sade,
  Türkçe karaktersiz; karar 2026-09-24) ve parça bütünlüğü
  (``parcayi_dogrula``: bir parça kendi yerinde kalır; üst düzeyde virgül ya
  da noktalı virgül taşıyamaz, parantez ve tırnakları dengeli olmalıdır,
  boş olamaz, SQL yorumu (``--``, ``/* */``) içeremez). İkincisi olmadan
  ``"TEXT, UNIQUE(a)"`` gibi bir özellik parçası sütun tanımından çıkıp
  tablo düzeyi kısıt yazardı; parçalar boşlukla birleştiğinden ``"TEXT --
  aciklama"`` gibi bir satır sonu yorumu sonraki parçaları (``NOT NULL``,
  hatta sonraki sütunu) yutardı. Ek savunma: tablo oluşturma ve sütun
  eklemeden sonra SQLite'ın gerçekten açtığı sütunlar istekle karşılaştırılır,
  uymuyorsa iş geri alınır. Bunlar dışında tek istisna sütun özelliği
  değiştirmenin emniyet kurallarıdır (aşağıda).

Sütun özelliği değiştirme (karar 2026-09-24):

* İstek (``SutunOzelligiDegistirmeIstegi``) tablonun **yeni hâlini bütün
  sütunları, tablo düzeyi kısıtları ve seçenekleriyle** taşır; motor tanımı
  okuyup türetmez. Adımlar SQLite'ın resmî tablo yeniden kurma tarifidir:
  geçici adla yeni tablo, satırların aynı adlı sütunlar üzerinden taşınması,
  eski tablonun silinmesi, geçici tablonun eski adı alması. Hepsi
  ``foreign_keys=OFF`` ile tek transaction'dadır
  (``Veritabani.islem_yabanci_anahtar_denetimsiz``); ``commit`` öncesi
  ``PRAGMA foreign_key_check`` çalışır. Herhangi bir adım düşerse (örn. yeni
  özelliğe uymayan satır) iş bütünüyle geri alınır, eski tablo eksiksiz kalır.
* **Emniyet kuralı (sütunlar):** bu iş yalnız mevcut sütunların özelliğini
  değiştirir; sütun ekleyemez, silemez, adını ya da sırasını değiştiremez.
  Motor DDL'den önce ``PRAGMA table_xinfo`` ile mevcut sütun adlarını okur;
  istekteki adlarla sırasıyla birebir aynı değilse (eksik, fazla, farklı)
  hiçbir şey yapmadan ``SutunlarUyusmuyor`` verir.
* **Emniyet kuralı (kısıt ve seçenekler):** tablo düzeyi kısıtlar ve tablo
  seçenekleri ``CREATE TABLE`` metninin içindedir; ayrı nesne değildir ve
  metin ayrıştırılmadan geri yazılamaz. Bu yüzden istek onları da taşır ve
  motor **aynen korunduklarını** denetler: mevcut tablonun tablo düzeyi
  kısıtları ve seçenekleri istektekilerle (sıra, boşluk ve büyük/küçük harf
  dışında) birebir aynı olmalıdır; kısıt eklemek, silmek, içeriğini
  değiştirmek ve seçenek değiştirmek bu işin dışındadır. Uymuyorsa hiçbir
  şey yapmadan ``KisitlarUyusmuyor``. Karşılaştırma ayrıştırma değildir:
  metnin en dış parantezindeki üst düzey parçalar alınır, ilk N tanesi sütun
  (N = sütun sayısı), kalanı kısıttır; kuyruk seçeneklerdir. Sadeleştirme
  (``_sadelestir``) **tırnak içine dokunmaz** (``'A'`` ile ``'a'`` farklı
  kurallardır); tırnak dışında harf boyutunu, çoklu boşlukları ve parantez
  ile virgül çevresindeki boşlukları eşitler, yorumları atar. Daha ince
  eşdeğerlik (``a=1`` ile ``a = 1``) tanınmaz; belirsizlikte ret güvenli
  yöndür.
* **Geçici tablo denetimi:** parça sınırı bir kısıt parçasının gerçekten
  kısıt olduğunu bilemez (``"ekstra TEXT"`` geçerli bir sütun tanımıdır).
  Bu yüzden motor geçici tabloyu kurduktan sonra SQLite'ın gerçekten açtığı
  sütun listesini istekle karşılaştırır; farklıysa kopyalamadan önce
  ``SutunlarUyusmuyor`` ile iş geri alınır.
* **Kopyalama kayıpsızdır:** satırlar ``INSERT OR ABORT`` ile taşınır; yeni
  tanımdaki ``ON CONFLICT IGNORE/REPLACE`` düz ``INSERT``'i sessizce
  eksiltir ya da değer değiştirirdi, ``OR ABORT`` onu ezer ve çatışmada iş
  düşer. Kopyalamadan sonra iki tablonun satır sayısı karşılaştırılır.
  Örtük satır kimliği de taşınır (iki tablo da rowid tablosuysa):
  ``INTEGER PRIMARY KEY`` olmayan tabloda satır kimliği rowid'dir,
  görünümler ona dayanabilir. ``rowid`` / ``_rowid_`` / ``oid`` adlı gerçek
  bir sütun o takma adı gölgeler; motor gölgelenmemiş takma adı kullanır,
  üçü de gölgeliyse kimlik güvenle okunamaz ve iş ``MotorHatasi`` ile
  reddedilir. Rowid tablosu olup olmadığını ``PRAGMA table_list`` söyler.
* **Üretilen sütunlar:** değeri hesaplanan sütuna satır yazılamaz ama eski
  değeri okunabilir. Motor geçici tabloyu kurduktan sonra ``PRAGMA
  table_xinfo`` ile yeni tarafta hangi sütunların üretildiğini öğrenir ve
  yalnız yeni tarafta yazılabilir olan sütunları kopyalar; hangi sütunun
  üretildiğini SQLite söyler, motor anahtar kelime bilmez. Üretilen sütunu
  sıradan sütuna çevirince hesaplanmış değer korunur; sıradan sütunu
  üretilene çevirince değer formülden yeniden hesaplanır.
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
* Bu okumalar yalnız bu işe özeldir; motor okuduğunu tanıma dönüştürmez,
  karar vermez, göstermez.

Bir iş = bir transaction (``Veritabani.islem``): düşen istek bütünüyle geri
alınır. DDL metni ``exec_driver_sql`` ile sürücüye olduğu gibi verilir;
parçaların içindeki ``:`` bağlama parametresi sanılmaz. Sürücü tek seferde
tek ifade çalıştırır.

``tablo_olusturma_sql``, ``sutun_ekleme_sql``, ``sutun_ozelligi_degistirme_sql``,
``indeks_olusturma_sql`` ve ``indeks_silme_sql`` veritabanına dokunmaz;
uygulama onay penceresinde ne yapılacağını göstermek için kullanabilir.
Yeniden kurmanın kopyalama adımı önizlemede bütün sütunları gösterir; iş
anında üretilen sütunlar SQLite'ın bildirdiğine göre dışarıda kalır ve
rowid tablolarında ``rowid`` de taşınır.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise

from sqlalchemy import Connection
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from defteruc.cekirdek.veritabani import Veritabani, YabanciAnahtarIhlali

AD_BICIMI = re.compile(r"^[a-z][a-z0-9_]*$")
"""Tablo, sütun ve indeks adı: küçük ASCII harfle başlar; harf, rakam, alt çizgi."""

GECICI_AD_EKI = "__yeniden_kurma"
"""Yeniden kurma sırasında yeni tablonun geçici adı: ``<tablo>__yeniden_kurma``."""

ROWID_TAKMA_ADLARI = ("rowid", "_rowid_", "oid")
"""Örtük satır kimliğinin takma adları; aynı adlı gerçek sütun onu gölgeler."""


class MotorHatasi(Exception):
    """Motor isteği uygulayamadı; iş bütünüyle geri alındı."""


class GecersizAd(MotorHatasi, ValueError):
    """Tablo, sütun ya da indeks adı ``AD_BICIMI``'ne uymuyor."""


class GecersizParca(MotorHatasi, ValueError):
    """Parça (özellik, kısıt, seçenek, indeks sütunu, koşul) kendi yerinde
    kalmıyor: üst düzeyde virgül ya da noktalı virgül, dengesiz parantez,
    kapanmayan tırnak, SQL yorumu ya da boş. Veritabanına dokunulmadı.
    """


class SutunlarUyusmuyor(MotorHatasi):
    """Sütun özelliği değiştirme: istekteki sütun adları mevcut tablonunkilerle
    sırasıyla birebir aynı değil; veritabanına dokunulmadı."""


class KisitlarUyusmuyor(MotorHatasi):
    """Sütun özelliği değiştirme: istekteki tablo düzeyi kısıtlar ya da tablo
    seçenekleri mevcut tablonunkilerle birebir aynı değil; sessiz kayıp
    olmasın diye reddedildi, veritabanına dokunulmadı."""


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
    """``kisitlar``: sütunlardan sonra yazılan tablo düzeyi kısıt parçaları.
    ``secenekler``: kapanış parantezinden sonra yazılan tablo seçenekleri."""

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
    """Tablonun yeni hâli: bütün sütunlar (mevcutla aynı ad ve sırada, yeni
    özellikleriyle), tablo düzeyi kısıtlar ve tablo seçenekleri (ikisi de
    mevcutla birebir aynı)."""

    tablo: str
    sutunlar: tuple[Sutun, ...]
    kisitlar: tuple[str, ...] = ()
    secenekler: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IndeksOlusturmaIstegi:
    """``sutunlar``: sütun adı ya da ifade parçaları, olduğu gibi yazılır.
    ``benzersiz``: ``UNIQUE``. ``kosul``: kısmi indeks ``WHERE`` ifadesi, boşsa yok."""

    indeks: str
    tablo: str
    sutunlar: tuple[str, ...]
    benzersiz: bool = False
    kosul: str = ""


@dataclass(frozen=True, slots=True)
class IndeksSilmeIstegi:
    indeks: str


# --- ad ve parça sınırı: SQL'e güvenle yazılabilmek için ---------------------------


def adi_dogrula(ad: str, ne: str) -> str:
    """Adı ``AD_BICIMI``'ne göre denetler; uymuyorsa ``GecersizAd``."""
    if not AD_BICIMI.fullmatch(ad):
        raise GecersizAd(
            f"{ne} adı sade olmalı (küçük ASCII harfle başlar; harf, rakam, "
            f"alt çizgi; Türkçe karakter yok): {ad!r}"
        )
    return ad


def parcayi_dogrula(parca: str, ne: str = "parça") -> str:
    """Parçanın kendi yerinde kaldığını denetler; kalmıyorsa ``GecersizParca``.
    Parçanın anlamına bakılmaz (onu SQLite belirler); yalnız sınırı aşıp
    aşmadığına bakılır: üst düzeyde ``,`` ya da ``;`` yok, parantezler dengeli,
    tırnak ve yorumlar kapalı, boş değil."""
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
    """İsteğin ``CREATE TABLE`` metni; veritabanına dokunmaz."""
    tablo = adi_dogrula(istek.tablo, "tablo")
    return _tablo_tanimi(tablo, istek.sutunlar, istek.kisitlar, istek.secenekler)


def sutun_ekleme_sql(istek: SutunEklemeIstegi) -> str:
    """İsteğin ``ALTER TABLE ... ADD COLUMN`` metni; veritabanına dokunmaz."""
    tablo = adi_dogrula(istek.tablo, "tablo")
    return f"ALTER TABLE {_tirnakla(tablo)} ADD COLUMN {_sutun_tanimi(istek.sutun)}"


def _kopyalama_sql(
    gecici: str, tablo: str, adlar: tuple[str, ...], rowid_takma: str | None = None
) -> str:
    """``INSERT OR ABORT``: yeni tanımdaki ``ON CONFLICT IGNORE/REPLACE`` düz
    ``INSERT``'i sessizce eksiltirdi; ``OR ABORT`` çatışmada işi düşürür.
    ``rowid_takma`` verilirse örtük satır kimliği de o adla taşınır."""
    liste = ", ".join(_tirnakla(a) for a in adlar)
    if rowid_takma:
        liste = f"{rowid_takma}, {liste}"
    hedef, kaynak = _tirnakla(gecici), _tirnakla(tablo)
    return f"INSERT OR ABORT INTO {hedef} ({liste}) SELECT {liste} FROM {kaynak}"


def sutun_ozelligi_degistirme_sql(
    istek: SutunOzelligiDegistirmeIstegi,
) -> tuple[str, ...]:
    """Yeniden kurma adımlarının DDL metinleri, sırayla; veritabanına dokunmaz.
    Kopyalama adımı bütün sütunları gösterir; iş anında üretilen sütunlar
    (SQLite'ın bildirdiği) dışarıda kalır, rowid tablolarında ``rowid`` de
    taşınır."""
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
    """İsteğin ``CREATE [UNIQUE] INDEX`` metni; veritabanına dokunmaz."""
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
    """İsteğin ``DROP INDEX`` metni; veritabanına dokunmaz."""
    return f"DROP INDEX {_tirnakla(adi_dogrula(istek.indeks, 'indeks'))}"


# --- işler: her biri tek transaction -------------------------------------------------


def tablo_olustur(veritabani: Veritabani, istek: TabloOlusturmaIstegi) -> None:
    """Tabloyu açar; tek transaction. Açıldıktan sonra SQLite'ın gerçekten
    açtığı sütunlar istekle karşılaştırılır, uymuyorsa iş geri alınır."""
    ddl = tablo_olusturma_sql(istek)
    beklenen = tuple(s.ad for s in istek.sutunlar)
    _uygula(veritabani, ddl, lambda b: _sutunlari_dogrula(b, istek.tablo, beklenen))


def sutun_ekle(veritabani: Veritabani, istek: SutunEklemeIstegi) -> None:
    """Tabloya sütun ekler; tek transaction. Eklendikten sonra son sütunun
    istenen ad olduğu doğrulanır, değilse iş geri alınır."""
    ddl = sutun_ekleme_sql(istek)
    _uygula(
        veritabani, ddl, lambda b: _son_sutunu_dogrula(b, istek.tablo, istek.sutun.ad)
    )


def indeks_olustur(veritabani: Veritabani, istek: IndeksOlusturmaIstegi) -> None:
    """İndeks açar; tek transaction."""
    _uygula(veritabani, indeks_olusturma_sql(istek))


def indeks_sil(veritabani: Veritabani, istek: IndeksSilmeIstegi) -> None:
    """İndeksi siler; tek transaction."""
    _uygula(veritabani, indeks_silme_sql(istek))


def sutun_ozelligi_degistir(
    veritabani: Veritabani, istek: SutunOzelligiDegistirmeIstegi
) -> None:
    """Tabloyu isteğin tanımıyla yeniden kurar; tek transaction, ``foreign_keys=OFF``.

    Önce ad ve parça sınırı (dokunmadan), sonra transaction içinde ama DDL'den
    önce emniyet denetimleri: sütun adları birebir aynı mı
    (``SutunlarUyusmuyor``), kısıtlar ve seçenekler birebir aynı mı
    (``KisitlarUyusmuyor``). Denetimler geçmezse hiçbir DDL çalışmaz. Sonra
    görünüm ve trigger'lar silinir, geçici tablo kurulur ve SQLite'ın açtığı
    sütunlar istekle karşılaştırılır, yazılabilir sütunlar (ve rowid) ``OR
    ABORT`` ile kopyalanır ve satır sayısı doğrulanır, eski tablo silinir,
    geçici tablo eski adı alır, indeks/trigger/görünümler saklı cümleleriyle
    geri açılır, sayaç geri yazılır. Düşen iş bütünüyle geri alınır; eski
    tablo eksiksiz kalır.
    """
    kurma, _, silme, adlandirma = sutun_ozelligi_degistirme_sql(istek)
    tablo, gecici = istek.tablo, istek.tablo + GECICI_AD_EKI
    try:
        with veritabani.islem_yabanci_anahtar_denetimsiz() as baglanti:
            eski_sutunlar = _yeniden_kurma_on_denetimi(baglanti, istek)
            bagli = _bagli_nesneler(baglanti, tablo)
            sayac = _sayaci_oku(baglanti, tablo)

            for ddl in bagli.once_silinecek:
                baglanti.exec_driver_sql(ddl)
            baglanti.exec_driver_sql(kurma)
            yeni_sutunlar = _sutunlari_dogrula(baglanti, gecici, tuple(eski_sutunlar))
            kopyalanacak = tuple(
                ad for ad, uretilen in yeni_sutunlar.items() if not uretilen
            )
            rowid_takma = None
            if not _rowidsiz(baglanti, tablo) and not _rowidsiz(baglanti, gecici):
                rowid_takma = _rowid_takma_adi(tuple(eski_sutunlar))
                if rowid_takma is None:
                    raise MotorHatasi(
                        f"{tablo}: rowid, _rowid_ ve oid adlarının üçü de sütun; örtük "
                        "satır kimliği güvenle okunamaz, iş reddedildi"
                    )
            baglanti.exec_driver_sql(
                _kopyalama_sql(gecici, tablo, kopyalanacak, rowid_takma)
            )
            eski_sayi, yeni_sayi = (_satir_sayisi(baglanti, t) for t in (tablo, gecici))
            if eski_sayi != yeni_sayi:
                raise MotorHatasi(
                    f"{tablo}: kopyalama eksik ({eski_sayi} satırdan {yeni_sayi}); "
                    "iş geri alındı"
                )
            baglanti.exec_driver_sql(silme)
            baglanti.exec_driver_sql(adlandirma)
            for ddl in bagli.sonra_kurulacak:
                baglanti.exec_driver_sql(ddl)
            if sayac is not None:
                _sayaci_yaz(baglanti, tablo, sayac)
    except YabanciAnahtarIhlali as hata:
        raise MotorHatasi(f"istek uygulanamadı, geri alındı: {hata}") from hata
    except SQLAlchemyError as hata:
        raise _motor_hatasi(hata) from hata


# --- yeniden kurmanın okumaları: yalnız bu işe özel ---------------------------------


def _sutun_bilgisi(baglanti: Connection, tablo: str) -> dict[str, bool]:
    """``PRAGMA table_xinfo``: sütun adı -> üretilen mi (``hidden != 0``),
    tablo sırasıyla. Tablo yoksa boş."""
    satirlar = baglanti.exec_driver_sql(f"PRAGMA table_xinfo({_tirnakla(tablo)})").all()
    return {str(s[1]): int(s[6]) != 0 for s in satirlar}


def _rowid_takma_adi(sutun_adlari: tuple[str, ...]) -> str | None:
    """Gerçek bir sütunun gölgelemediği ilk takma ad; üçü de gölgeliyse ``None``."""
    golgeli = {ad.casefold() for ad in sutun_adlari}
    return next((t for t in ROWID_TAKMA_ADLARI if t not in golgeli), None)


def _sutunlari_dogrula(
    baglanti: Connection, tablo: str, beklenen: tuple[str, ...]
) -> dict[str, bool]:
    """SQLite'ın gerçekten açtığı sütunlar (ad ve sıra) istekle aynı mı; değilse
    ``SutunlarUyusmuyor`` (çağıranın transaction'ı geri alınır). Geçerse sütun
    bilgisini döner."""
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


def _rowidsiz(baglanti: Connection, tablo: str) -> bool:
    """``PRAGMA table_list``: tablo ``WITHOUT ROWID`` mi (``wr`` sütunu)."""
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
    """Emniyet denetimleri; geçerse mevcut sütun bilgisini döner."""
    tablo = istek.tablo
    mevcut_sutunlar = _sutun_bilgisi(baglanti, tablo)
    if not mevcut_sutunlar:
        raise MotorHatasi(f"tablo yok: {tablo}")

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
    """Kısıt/seçenek karşılaştırması için sadeleştirme. Tırnak içi (``'``,
    ``"``, backtick, ``[ ]``) **olduğu gibi** kalır; tırnak dışında harf
    boyutu küçültülür, boşluk dizileri tek boşluğa iner, parantez ve virgül
    çevresindeki boşluklar kalkar, yorumlar atılır, uçlar kırpılır."""
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


# --- tarayıcı: ayrıştırma değil, tırnak/yorum/parantez izleme -----------------------


def _acik_karakterler(sql: str) -> tuple[list[tuple[int, str, int]], int, bool]:
    """Tırnak ve yorum dışındaki karakterler ``(konum, karakter, derinlik)``
    olarak, bitişteki parantez derinliği ve yorum görülüp görülmediği.
    Tırnaklı bölüm tek bir ``"`` karakteri olarak temsil edilir (içeriği
    önemsiz, varlığı önemli). ``(`` kendi açtığı, ``)`` kendi kapattığı
    derinlikle verilir.

    Ayrıştırma değildir: yalnız tırnak (``"``, ``'``, backtick, ``[ ]``),
    yorum (``--``, ``/* */``) ve parantez derinliği izlenir. Kapanmayan tırnak
    ya da blok yorum ``ValueError``.
    """
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
    """``CREATE TABLE`` metninin en dış parantezindeki üst düzey (virgülle
    ayrılmış) parçaların metinleri ve kapanış parantezinden sonraki kuyruk.
    İlk parçalar sütun tanımları, kalanı tablo düzeyi kısıtlardır (SQLite
    gramerinde kısıtlar sütunlardan sonra gelir). Boş gövde boş liste.
    Ayrıştırma değildir (``_acik_karakterler``)."""
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
    """Metni üst düzey virgüllerden böler (tırnak ve parantez içi hariç); boş
    parçalar atılır. Tablo seçenekleri kuyruğu için."""
    karakterler, _, _ = _acik_karakterler(metin)
    kesimler = [k for k, c, d in karakterler if d == 0 and c == ","]
    sinirlar = [-1, *kesimler, len(metin)]
    parcalar = [metin[a + 1 : b] for a, b in pairwise(sinirlar)]
    return [p.strip() for p in parcalar if p.strip()]


# --- ortak uygulama ----------------------------------------------------------------


def _uygula(
    veritabani: Veritabani,
    ddl: str,
    sonra: Callable[[Connection], object] | None = None,
) -> None:
    """DDL'yi tek transaction'da uygular; ``sonra`` verilirse aynı transaction
    içinde çalışır (gerçek yapı denetimi), yükselttiği hata işi geri alır."""
    try:
        with veritabani.islem() as oturum:
            baglanti = oturum.connection()
            baglanti.exec_driver_sql(ddl)
            if sonra is not None:
                sonra(baglanti)
    except SQLAlchemyError as hata:
        raise _motor_hatasi(hata) from hata


def _motor_hatasi(hata: SQLAlchemyError) -> MotorHatasi:
    neden = hata.orig if isinstance(hata, DBAPIError) else hata
    return MotorHatasi(f"istek uygulanamadı, geri alındı: {neden}")
