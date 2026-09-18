"""Genel nesne motorunun tabloları (Aşama 4.3).

Çekirdek bir nesnenin ne olduğunu bilmez: nesne yalnız bir nesne türü tanımına
bağlı kimlik, yaşam durumu ve zaman damgasıdır; anlamı tanım verisinden gelir.

* ``Nesne`` — türü ve tanım sürümü ayrı iki rastgele dış anahtar değildir:
  ``(nesne_turu_id, tanim_surumu_id)`` bileşik dış anahtarla
  ``nesne_turu (id, tanim_surumu_id)`` çiftine bağlıdır, yani türün gerçekten
  o sürüme ait olduğu veritabanında zorlanır. Nesne hangi sürümde üretildiyse
  o bilgi satırda kalıcıdır.
* ``NesneOzelligi`` — ``NESNE → NESNE ÖZELLİĞİ → ÖZELLİK TANIMI``. Değerler ana
  tabloya sütun olarak eklenmez. Satır nesnenin türünü de taşır ve iki bileşik
  dış anahtarla hem nesneye (``nesne (id, nesne_turu_id)``) hem özellik
  tanımına (``ozellik_tanimi (id, nesne_turu_id)``) aynı tür üzerinden
  bağlanır: başka türün özelliği veritabanında da yazılamaz. Aynı nesnede aynı
  özellik tanımı bir kez bulunur. ``deger`` türüne göre kanonik metindir
  (``nesne_islemleri``).
* ``NesneIliskisi`` — ``kaynak nesne → ilişki tanımı → hedef nesne``. Satır
  tanım sürümünü ve kaynak/hedef türünü taşır; bileşik dış anahtarlar ilişki
  tanımının (id, sürüm, kaynak tür, hedef tür) dörtlüsüne ve iki nesnenin
  (id, tür, sürüm) üçlüsüne bağlanır. Böylece kaynak nesnenin türü tanımın
  kaynak türü, hedefinki hedef türü ve üçü aynı sürümde olmak zorundadır;
  ters tür çifti ya da başka sürüm veritabanında da reddedilir. Aynı tanım,
  aynı iki nesne arasında bir kez yazılır. Nesnenin kendisine dönen genel
  ilişkiye çekirdek karışmaz (0004'teki kontrol kısıtı 0005 ile kalktı);
  hiyerarşik ilişkide çevrim ``nesne_islemleri`` içinde engellenir.

Yaşam durumu ``tanim_tablolari.YasamDurumu`` (etkin / kapalı) ile sınırlıdır.
Hiyerarşi kuralları (en az / en çok üst, üstün gerekli durumu) veri olarak
``hiyerarsi_kurali`` tablosundadır; sayım ve çevrim kuralları SQL ile güvenli
ifade edilemediğinden ``nesne_islemleri`` içinde doğrulanır.

Bu modül yalnız şemadır; ``relationship`` yoktur (bkz. ``tanim_tablolari``).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from defteriki.cekirdek.tanim_tablolari import (
    ILISKI_TANIMI,
    NESNE_TURU,
    OZELLIK_TANIMI,
    YASAM_DURUMU_KOSULU,
)
from defteriki.cekirdek.veritabani import TabloTabani

NESNE = "nesne"
NESNE_OZELLIGI = "nesne_ozelligi"
NESNE_ILISKISI = "nesne_iliskisi"

NESNE_TABLOLARI: tuple[str, ...] = (NESNE, NESNE_OZELLIGI, NESNE_ILISKISI)
"""Nesne tabloları, bağımlılık sırasıyla (göç ve testler için)."""


class Nesne(TabloTabani):
    __tablename__ = NESNE

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nesne_turu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tanim_surumu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    """Nesnenin üretildiği tanım sürümü; kalıcıdır, sonradan değişmez."""
    yasam_durumu: Mapped[str] = mapped_column(String, nullable=False)
    olusturma_zamani: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["nesne_turu_id", "tanim_surumu_id"],
            [f"{NESNE_TURU}.id", f"{NESNE_TURU}.tanim_surumu_id"],
            ondelete="RESTRICT",
        ),
        # Alt tabloların bileşik dış anahtarları için hedef çiftler / üçlüler.
        UniqueConstraint("id", "nesne_turu_id"),
        UniqueConstraint("id", "nesne_turu_id", "tanim_surumu_id"),
        CheckConstraint(YASAM_DURUMU_KOSULU, name="yasam_durumu_gecerli"),
        Index(None, "nesne_turu_id"),
        Index(None, "tanim_surumu_id"),
    )


class NesneOzelligi(TabloTabani):
    __tablename__ = NESNE_OZELLIGI

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nesne_id: Mapped[int] = mapped_column(Integer, nullable=False)
    nesne_turu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    """Nesnenin türü; iki bileşik dış anahtarın ortak sütunu."""
    ozellik_tanimi_id: Mapped[int] = mapped_column(Integer, nullable=False)
    deger: Mapped[str] = mapped_column(Text, nullable=False)
    """Türe göre kanonik metin (bkz. ``nesne_islemleri``)."""

    __table_args__ = (
        ForeignKeyConstraint(
            ["nesne_id", "nesne_turu_id"],
            [f"{NESNE}.id", f"{NESNE}.nesne_turu_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["ozellik_tanimi_id", "nesne_turu_id"],
            [f"{OZELLIK_TANIMI}.id", f"{OZELLIK_TANIMI}.nesne_turu_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("nesne_id", "ozellik_tanimi_id"),
        Index(None, "ozellik_tanimi_id"),
    )


class NesneIliskisi(TabloTabani):
    __tablename__ = NESNE_ILISKISI

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    iliski_tanimi_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tanim_surumu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    kaynak_nesne_turu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    hedef_nesne_turu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    kaynak_nesne_id: Mapped[int] = mapped_column(Integer, nullable=False)
    hedef_nesne_id: Mapped[int] = mapped_column(Integer, nullable=False)

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
            ["kaynak_nesne_id", "kaynak_nesne_turu_id", "tanim_surumu_id"],
            [f"{NESNE}.id", f"{NESNE}.nesne_turu_id", f"{NESNE}.tanim_surumu_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["hedef_nesne_id", "hedef_nesne_turu_id", "tanim_surumu_id"],
            [f"{NESNE}.id", f"{NESNE}.nesne_turu_id", f"{NESNE}.tanim_surumu_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("iliski_tanimi_id", "kaynak_nesne_id", "hedef_nesne_id"),
        Index(None, "kaynak_nesne_id"),
        Index(None, "hedef_nesne_id"),
    )
