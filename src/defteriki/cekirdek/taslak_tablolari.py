"""İşlem paketi ve taslak (aday) verinin tabloları (Aşama 4.5).

"Yazmak ≠ kaydetmek": dış okuyucunun (Cowork) belgeden çıkarıp sisteme
yazdığı bilgi bir **işlem paketi** altında, **taslak** olarak yaşar; kesin
kayıt değildir. Kesin dünya (``nesne``, ``nesne_ozelligi``, ``nesne_iliskisi``;
ileride kesin kayıt) ile taslak dünya **fiziksel olarak ayrı tablolardadır**:
aday satır kesin tabloya yazılmaz, kesin sorgular (``nesneleri_listele`` vb.)
taslak tabloları hiç görmez. Ayrım şemadan gelir; ``WHERE durum != 'taslak'``
gibi unutulabilir bir sorgu filtresine dayanmaz. Bu modüldeki hiçbir tablo
kesin nesne tablolarına dış anahtar taşımaz.

* ``IslemPaketi`` — tamamlanmış bir okumadan doğan çalışma alanı. Yalnız
  ``okuma_id`` tutar; belge ``okuma → belge`` zincirinden deterministik
  bulunur (ayrı ``belge_id`` yok, iki bağımsız dış anahtar tuzağı yok).
  ``durum`` üç değerdir (``PaketDurumu``): ``calisiyor`` (taslak yazılabilir),
  ``bekliyor`` (korunur, değiştirilmez; 4.6'nın kullanıcı kararı için
  hazırlık), ``iptal`` (terminal; satırlar silinmez). Kesin kayıt anlamına
  gelen durum (kaydedildi / kesinleşti) yoktur; Aşama 4.8'in işidir.
  ``(id, okuma_id)`` benzersizliği aday tabloların provenance bileşik dış
  anahtarı içindir.
* ``AdayNesne`` — ``İŞLEM PAKETİ → ADAY NESNE``. Kesin ``Nesne`` değildir,
  ``nesne.id`` üretmez. Türü ve sürümü ``(nesne_turu_id, tanim_surumu_id)``
  bileşik dış anahtarla ``nesne_turu (id, tanim_surumu_id)`` çiftine bağlıdır
  (4.3 kalıbı). ``okuma_id`` paketten kopyalanır ve ``(islem_paketi_id,
  okuma_id)`` bileşik dış anahtarla pakete bağlıdır; isteğe bağlı ``kaynak_id``
  ``(kaynak_id, okuma_id)`` bileşik dış anahtarla ``kaynak (id, okuma_id)``
  çiftine bağlıdır: başka okumanın kaynağı veritabanında da bağlanamaz
  (SQLite bileşik dış anahtarda bir sütun NULL ise denetim yapılmaz; kaynaksız
  aday geçerlidir). Zorunlu özellik ya da zorunlu üst eksik olabilir; taslak
  dünyası çalışma alanıdır.
* ``AdayNesneOzelligi`` — ``ADAY NESNE → ADAY ÖZELLİK → ÖZELLİK TANIMI``; iki
  bileşik dış anahtar aynı ``nesne_turu_id`` üzerinden (başka türün özelliği
  veritabanında da yazılamaz); ``(aday_nesne_id, ozellik_tanimi_id)``
  benzersiz. Değer kesin özellikle aynı kanonik metindir (``deger_kodlama``).
* ``AdayNesneIliskisi`` — ``ADAY NESNE → ADAY İLİŞKİ → ADAY NESNE``. Satır
  paketi, tanım sürümünü ve kaynak/hedef türü taşır; dörtlü bileşik dış
  anahtar ``iliski_tanimi (id, sürüm, kaynak tür, hedef tür)``, iki dörtlü
  bileşik dış anahtar ``aday_nesne (id, paket, tür, sürüm)``: kaynak ve hedef
  aday **aynı pakette**, türleri tanımın kaynak/hedef türü, üçü aynı sürümde
  olmak zorundadır. Hiyerarşi tamlığı ve çevrim aranmaz (4.8); ama açıkça
  yanlış tür eşleştirmesi ya da başka paketin adayı veritabanında reddedilir.
  ``(iliski_tanimi_id, kaynak_aday_nesne_id, hedef_aday_nesne_id)`` benzersiz.
* ``AdayKayit`` — paketin aday kaydı; kesin ``Kayit`` değildir (kesin kayıt
  tablosu ve alan motoru Aşama 4.7). Genel ``kayit_turu`` tanımına bağlıdır;
  içerik domain bağımsız JSON **nesnesidir** (``json_valid`` ve ``json_type =
  'object'`` kontrol kısıtları). Provenance ``AdayNesne`` ile aynı:
  ``(islem_paketi_id, okuma_id)`` ve isteğe bağlı ``(kaynak_id, okuma_id)``.
* ``AdayKayitNesne`` — ``ADAY KAYIT ↔ ADAY NESNE`` çoktan çoğa bağı; iki
  bileşik dış anahtar ``islem_paketi_id`` üzerinden: iki taraf aynı pakette
  olmak zorundadır. Rol yoktur (domain semantiği icat edilmez).
  ``(aday_kayit_id, aday_nesne_id)`` benzersiz.

Bütün dış anahtarlar ``ON DELETE RESTRICT``; taslak silme kuralları
``taslak_islemleri`` içindedir ve paket iptali hiçbir satırı silmez. Zaman
damgaları UTC'dir, saat dilimi bilgisi olmadan saklanır. Bu modül yalnız
şemadır: satır yazmaz, ``relationship`` içermez (bkz. ``tanim_tablolari``).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from defteriki.cekirdek.belge_tablolari import KAYNAK, OKUMA
from defteriki.cekirdek.tanim_tablolari import (
    ILISKI_TANIMI,
    KAYIT_TURU,
    NESNE_TURU,
    OZELLIK_TANIMI,
)
from defteriki.cekirdek.veritabani import TabloTabani

ISLEM_PAKETI = "islem_paketi"
ADAY_NESNE = "aday_nesne"
ADAY_NESNE_OZELLIGI = "aday_nesne_ozelligi"
ADAY_NESNE_ILISKISI = "aday_nesne_iliskisi"
ADAY_KAYIT = "aday_kayit"
ADAY_KAYIT_NESNE = "aday_kayit_nesne"

TASLAK_TABLOLARI: tuple[str, ...] = (
    ISLEM_PAKETI,
    ADAY_NESNE,
    ADAY_NESNE_OZELLIGI,
    ADAY_NESNE_ILISKISI,
    ADAY_KAYIT,
    ADAY_KAYIT_NESNE,
)
"""Taslak tabloları, bağımlılık sırasıyla (göç ve testler için)."""


class PaketDurumu(StrEnum):
    """İşlem paketinin yaşam durumu. Kesin kayıt anlamı taşıyan değer yoktur."""

    CALISIYOR = "calisiyor"
    BEKLIYOR = "bekliyor"
    IPTAL = "iptal"


PAKET_DURUMU_KOSULU = "durum IN ({})".format(
    ", ".join(f"'{d.value}'" for d in PaketDurumu)
)
ADAY_KAYIT_ICERIK_KOSULU = "json_valid(icerik) AND json_type(icerik) = 'object'"
"""Aday kayıt içeriği geçerli JSON ve JSON nesnesi (anahtar → değer) olmalı."""


class IslemPaketi(TabloTabani):
    __tablename__ = ISLEM_PAKETI

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    okuma_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{OKUMA}.id", ondelete="RESTRICT"), nullable=False
    )
    """Paketin doğduğu tamamlanmış okuma; belge buradan bulunur."""
    durum: Mapped[str] = mapped_column(String, nullable=False)
    olusturma_zamani: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    durum_zamani: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    """Son durum değişiminin zamanı; oluşturulunca oluşturma zamanına eşit."""

    __table_args__ = (
        # Aday tabloların provenance bileşik dış anahtarı için hedef çift.
        UniqueConstraint("id", "okuma_id"),
        CheckConstraint(PAKET_DURUMU_KOSULU, name="durum_gecerli"),
        Index(None, "okuma_id"),
        Index(None, "durum"),
    )


class AdayNesne(TabloTabani):
    __tablename__ = ADAY_NESNE

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    """Paket içinde kullanılacak kararlı kimlik; ``nesne.id`` değildir. Aday
    silinebildiği için bu kimlik ``AUTOINCREMENT`` ile verilir (aşağıdaki
    ``sqlite_autoincrement``): silinen adayın kimliği bir daha kullanılmaz."""
    islem_paketi_id: Mapped[int] = mapped_column(Integer, nullable=False)
    okuma_id: Mapped[int] = mapped_column(Integer, nullable=False)
    """Paketin okuması (kopya); kaynak bağının aynı okumada kalması için."""
    nesne_turu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tanim_surumu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    kaynak_id: Mapped[int | None] = mapped_column(Integer)
    """İsteğe bağlı provenance: paketin okumasına ait bir kaynak satırı."""
    olusturma_zamani: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["islem_paketi_id", "okuma_id"],
            [f"{ISLEM_PAKETI}.id", f"{ISLEM_PAKETI}.okuma_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["nesne_turu_id", "tanim_surumu_id"],
            [f"{NESNE_TURU}.id", f"{NESNE_TURU}.tanim_surumu_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["kaynak_id", "okuma_id"],
            [f"{KAYNAK}.id", f"{KAYNAK}.okuma_id"],
            ondelete="RESTRICT",
        ),
        # Alt tabloların bileşik dış anahtarları için hedef çift / dörtlü.
        UniqueConstraint("id", "islem_paketi_id"),
        UniqueConstraint("id", "nesne_turu_id"),
        UniqueConstraint("id", "islem_paketi_id", "nesne_turu_id", "tanim_surumu_id"),
        Index(None, "islem_paketi_id"),
        Index(None, "nesne_turu_id"),
        Index(None, "kaynak_id"),
        # Kimlik yeniden kullanılmaz: silinen adayın kimliği yeni adaya
        # verilirse denetim izindeki ``aday_nesne_id`` (dış anahtar değildir)
        # yıllar sonra başka bir adayı gösterir. SQLite ``AUTOINCREMENT``
        # olmadan en büyük ``rowid`` silinince onu yeniden dağıtır. Bunun
        # bedeli: birincil anahtar kısıtı sütun içinde yazılır, dolayısıyla
        # ``pk_aday_nesne`` adını taşıyamaz (SQLite dilbilgisi izin vermez).
        {"sqlite_autoincrement": True},
    )


class AdayNesneOzelligi(TabloTabani):
    __tablename__ = ADAY_NESNE_OZELLIGI

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aday_nesne_id: Mapped[int] = mapped_column(Integer, nullable=False)
    nesne_turu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    """Aday nesnenin türü; iki bileşik dış anahtarın ortak sütunu."""
    ozellik_tanimi_id: Mapped[int] = mapped_column(Integer, nullable=False)
    deger: Mapped[str] = mapped_column(Text, nullable=False)
    """Türe göre kanonik metin (``deger_kodlama``)."""

    __table_args__ = (
        ForeignKeyConstraint(
            ["aday_nesne_id", "nesne_turu_id"],
            [f"{ADAY_NESNE}.id", f"{ADAY_NESNE}.nesne_turu_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["ozellik_tanimi_id", "nesne_turu_id"],
            [f"{OZELLIK_TANIMI}.id", f"{OZELLIK_TANIMI}.nesne_turu_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("aday_nesne_id", "ozellik_tanimi_id"),
        Index(None, "ozellik_tanimi_id"),
    )


class AdayNesneIliskisi(TabloTabani):
    __tablename__ = ADAY_NESNE_ILISKISI

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    islem_paketi_id: Mapped[int] = mapped_column(Integer, nullable=False)
    iliski_tanimi_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tanim_surumu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    kaynak_nesne_turu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    hedef_nesne_turu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    kaynak_aday_nesne_id: Mapped[int] = mapped_column(Integer, nullable=False)
    hedef_aday_nesne_id: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            [
                "iliski_tanimi_id",
                "tanim_surumu_id",
                "kaynak_nesne_turu_id",
                "hedef_nesne_turu_id",
            ],
            [
                f"{ILISKI_TANIMI}.id",
                f"{ILISKI_TANIMI}.tanim_surumu_id",
                f"{ILISKI_TANIMI}.kaynak_nesne_turu_id",
                f"{ILISKI_TANIMI}.hedef_nesne_turu_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "kaynak_aday_nesne_id",
                "islem_paketi_id",
                "kaynak_nesne_turu_id",
                "tanim_surumu_id",
            ],
            [
                f"{ADAY_NESNE}.id",
                f"{ADAY_NESNE}.islem_paketi_id",
                f"{ADAY_NESNE}.nesne_turu_id",
                f"{ADAY_NESNE}.tanim_surumu_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "hedef_aday_nesne_id",
                "islem_paketi_id",
                "hedef_nesne_turu_id",
                "tanim_surumu_id",
            ],
            [
                f"{ADAY_NESNE}.id",
                f"{ADAY_NESNE}.islem_paketi_id",
                f"{ADAY_NESNE}.nesne_turu_id",
                f"{ADAY_NESNE}.tanim_surumu_id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "iliski_tanimi_id", "kaynak_aday_nesne_id", "hedef_aday_nesne_id"
        ),
        Index(None, "islem_paketi_id"),
        Index(None, "kaynak_aday_nesne_id"),
        Index(None, "hedef_aday_nesne_id"),
    )


class AdayKayit(TabloTabani):
    __tablename__ = ADAY_KAYIT

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    islem_paketi_id: Mapped[int] = mapped_column(Integer, nullable=False)
    okuma_id: Mapped[int] = mapped_column(Integer, nullable=False)
    kayit_turu_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{KAYIT_TURU}.id", ondelete="RESTRICT"), nullable=False
    )
    kaynak_id: Mapped[int | None] = mapped_column(Integer)
    icerik: Mapped[str] = mapped_column(Text, nullable=False)
    """Taslak / ham yapılandırılmış içerik, kanonik JSON nesnesi metni. Kesin
    kayıt alanları değildir; eksik ya da boş (``{}``) olabilir."""
    olusturma_zamani: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["islem_paketi_id", "okuma_id"],
            [f"{ISLEM_PAKETI}.id", f"{ISLEM_PAKETI}.okuma_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["kaynak_id", "okuma_id"],
            [f"{KAYNAK}.id", f"{KAYNAK}.okuma_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "islem_paketi_id"),
        CheckConstraint(ADAY_KAYIT_ICERIK_KOSULU, name="icerik_json_nesnesi"),
        Index(None, "islem_paketi_id"),
        Index(None, "kayit_turu_id"),
        Index(None, "kaynak_id"),
    )


class AdayKayitNesne(TabloTabani):
    __tablename__ = ADAY_KAYIT_NESNE

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    islem_paketi_id: Mapped[int] = mapped_column(Integer, nullable=False)
    aday_kayit_id: Mapped[int] = mapped_column(Integer, nullable=False)
    aday_nesne_id: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["aday_kayit_id", "islem_paketi_id"],
            [f"{ADAY_KAYIT}.id", f"{ADAY_KAYIT}.islem_paketi_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["aday_nesne_id", "islem_paketi_id"],
            [f"{ADAY_NESNE}.id", f"{ADAY_NESNE}.islem_paketi_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("aday_kayit_id", "aday_nesne_id"),
        Index(None, "islem_paketi_id"),
        Index(None, "aday_nesne_id"),
    )
