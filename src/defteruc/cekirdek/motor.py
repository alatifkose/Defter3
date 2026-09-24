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

Motorun yapmadıkları:

* Hazır tablo taşımaz ve hiçbir özelliği ismen bilmez. Sütunların görünen
  adı gibi tanım bilgileri de sıradan bir tablodur: Cowork o tabloyu da bu
  motorla açar, eşleşmeleri satır olarak yazar (kayıt). Motor bunu bilmez.
* Hafızası yoktur: işlemler arası durum tutmaz, katalog taşımaz.
* Mevcut yapıyı okumaz: tablonun var olup olmadığına, sütunun daha önce
  eklenip eklenmediğine bakmaz. Uygun düşmeyen istek SQLite'ta düşer ve
  ``MotorHatasi`` olarak yükselir.
* Bir şey göstermez ve karar vermez: dönüş değeri yoktur.
* Kural koymaz. Tek teknik sınır ad biçimidir (``AD_BICIMI``): tablo ve sütun
  adları sade yazılır, Türkçe karakter yoktur (karar 2026-09-24). Bu sınır
  SQL'e adın güvenle yazılabilmesi içindir.

Bir iş = bir transaction (``Veritabani.islem``): düşen istek bütünüyle geri
alınır. DDL metni ``exec_driver_sql`` ile sürücüye olduğu gibi verilir;
özellik parçalarının içindeki ``:`` bağlama parametresi sanılmaz. Sürücü tek
seferde tek ifade çalıştırır.

``tablo_olusturma_sql`` ve ``sutun_ekleme_sql`` veritabanına dokunmaz;
uygulama onay penceresinde ne yapılacağını göstermek için kullanabilir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from defteruc.cekirdek.veritabani import Veritabani

AD_BICIMI = re.compile(r"^[a-z][a-z0-9_]*$")
"""Tablo ve sütun adı: küçük ASCII harfle başlar; harf, rakam, alt çizgi."""


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
    """Tabloyu açar; tek transaction."""
    _uygula(veritabani, tablo_olusturma_sql(istek))


def sutun_ekle(veritabani: Veritabani, istek: SutunEklemeIstegi) -> None:
    """Tabloya sütun ekler; tek transaction."""
    _uygula(veritabani, sutun_ekleme_sql(istek))


def _uygula(veritabani: Veritabani, ddl: str) -> None:
    try:
        with veritabani.islem() as oturum:
            oturum.connection().exec_driver_sql(ddl)
    except SQLAlchemyError as hata:
        neden = hata.orig if isinstance(hata, DBAPIError) else hata
        raise MotorHatasi(f"istek uygulanamadı, geri alındı: {neden}") from hata
