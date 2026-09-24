"""Birinci motor: tablo oluşturur, sütun ekler (karar 2026-09-24).

Motor yalnız bir araçtır. Cowork belgeyi okur, ne gerektiğine karar verir ve
motoru kullanır; **kullanıcı onayını uygulama alır**. Bu modül onay almaz ve
onay sormaz: motoru yalnız uygulama, onay alındıktan sonra çağırır.

Motorun yaptıkları:

* ``tablo_olustur``: verilen adla, verilen sütunlarla tablo açar.
* ``sutun_ekle``: var olan tabloya sütun ekler.
* Sütun özelliği, ekleme isteğinin içinde gider: ``Sutun.ozellikler`` sütun
  adından sonra yazılacak parçalardır (ör. ``("TEXT", "NOT NULL")``,
  ``("INTEGER", "REFERENCES kisiler(id)")``). **Özellik listesi koda gömülü
  değildir;** istekte ne geldiyse o yazılır. Geçerliliğini SQLite belirler.
* Görünen ad, sütun tanımının motor tarafından yönetilen özelliğidir. Motor
  bunu tek bir sütun tanımları tablosunda (``sutun_tanimlari``: tablo_adi,
  sutun_adi, gorunen_ad) kalıcı saklar; arayüz oradan okur. Görünen ad
  verilmemişse arayüz geçici olarak teknik adı gösterebilir.

Motorun yapmadıkları:

* Hafızası yoktur: işlemler arası durum tutmaz, katalog taşımaz. (Kalıcı
  bilgi veritabanına yazılır; bu hafıza değildir.)
* Mevcut yapıyı okumaz: tablonun var olup olmadığına, sütunun daha önce
  eklenip eklenmediğine bakmaz. Uygun düşmeyen istek SQLite'ta düşer ve
  ``MotorHatasi`` olarak yükselir.
* Bir şey göstermez ve karar vermez: dönüş değeri yoktur.
* Kural koymaz. Tek teknik sınır ad biçimidir (``AD_BICIMI``): tablo ve sütun
  adları sade yazılır, Türkçe karakter yoktur (karar 2026-09-24); görünen ad
  serbest metindir. Bu sınır SQL'e adın güvenle yazılabilmesi içindir.

Bir iş = bir transaction (``Veritabani.islem``): yapı değişikliği ve sütun
tanımı satırları birlikte kalır ya da birlikte geri alınır. DDL metni
``exec_driver_sql`` ile sürücüye olduğu gibi verilir; özellik parçalarının
içindeki ``:`` bağlama parametresi sanılmaz. Sürücü tek seferde tek ifade
çalıştırır.

``tablo_olusturma_sql`` ve ``sutun_ekleme_sql`` veritabanına dokunmaz;
uygulama onay penceresinde ne yapılacağını göstermek için kullanabilir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from defteruc.cekirdek.veritabani import Veritabani

TANIM_TABLOSU = "sutun_tanimlari"
"""Motorun yönettiği tek sütun tanımları tablosu."""

AD_BICIMI = re.compile(r"^[a-z][a-z0-9_]*$")
"""Tablo ve sütun adı: küçük ASCII harfle başlar; harf, rakam, alt çizgi."""

_TANIM_TABLOSU_SQL = (
    f'CREATE TABLE IF NOT EXISTS "{TANIM_TABLOSU}" ('
    '"tablo_adi" TEXT NOT NULL, '
    '"sutun_adi" TEXT NOT NULL, '
    '"gorunen_ad" TEXT, '
    'PRIMARY KEY ("tablo_adi", "sutun_adi"))'
)
_TANIM_EKLE_SQL = text(
    f'INSERT INTO "{TANIM_TABLOSU}" ("tablo_adi", "sutun_adi", "gorunen_ad") '
    "VALUES (:tablo_adi, :sutun_adi, :gorunen_ad)"
)


class MotorHatasi(Exception):
    """Motor isteği uygulayamadı; iş bütünüyle geri alındı."""


class GecersizAd(MotorHatasi, ValueError):
    """Tablo ya da sütun adı ``AD_BICIMI``'ne uymuyor."""


@dataclass(frozen=True, slots=True)
class Sutun:
    """Bir sütun isteği.

    ``ad``: teknik ad (sade, Türkçe karaktersiz).
    ``ozellikler``: sütun adından sonra sırayla yazılacak parçalar; istekte ne
    geldiyse o. Boş olabilir (SQLite türsüz sütuna izin verir).
    ``gorunen_ad``: arayüzde gösterilecek ad; serbest metin, verilmeyebilir.
    """

    ad: str
    ozellikler: tuple[str, ...] = ()
    gorunen_ad: str | None = None


@dataclass(frozen=True, slots=True)
class TabloOlusturmaIstegi:
    tablo: str
    sutunlar: tuple[Sutun, ...]


@dataclass(frozen=True, slots=True)
class SutunEklemeIstegi:
    tablo: str
    sutun: Sutun


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


def tablo_olustur(veritabani: Veritabani, istek: TabloOlusturmaIstegi) -> None:
    """Tabloyu açar ve sütun tanımlarını yazar; tek transaction."""
    sql = tablo_olusturma_sql(istek)
    _uygula(veritabani, sql, istek.tablo, istek.sutunlar)


def sutun_ekle(veritabani: Veritabani, istek: SutunEklemeIstegi) -> None:
    """Tabloya sütun ekler ve sütun tanımını yazar; tek transaction."""
    sql = sutun_ekleme_sql(istek)
    _uygula(veritabani, sql, istek.tablo, (istek.sutun,))


def _uygula(
    veritabani: Veritabani, ddl: str, tablo: str, sutunlar: tuple[Sutun, ...]
) -> None:
    try:
        with veritabani.islem() as oturum:
            baglanti = oturum.connection()
            baglanti.exec_driver_sql(_TANIM_TABLOSU_SQL)
            baglanti.exec_driver_sql(ddl)
            for sutun in sutunlar:
                oturum.execute(
                    _TANIM_EKLE_SQL,
                    {
                        "tablo_adi": tablo,
                        "sutun_adi": sutun.ad,
                        "gorunen_ad": sutun.gorunen_ad,
                    },
                )
    except SQLAlchemyError as hata:
        neden = hata.orig if isinstance(hata, DBAPIError) else hata
        raise MotorHatasi(f"istek uygulanamadı, geri alındı: {neden}") from hata
