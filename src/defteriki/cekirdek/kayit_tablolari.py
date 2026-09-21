"""Kesin kayıt tabloları (Aşama 4.7).

Kayıt nesne değildir: bir ya da daha fazla nesneyle ilişkilendirilen olaydır.
Çekirdek hangi kayıt türlerinin var olduğunu bilmez; tür, alanları ve alanların
değer türü tanım verisidir (``tanim_tablolari``). Buradaki hiçbir sütun bir
domain'e ait anlam taşımaz: ne yön, ne eksen, ne ölçek, ne birim vardır.
Sayısal alan değeri de ``deger_kodlama`` ile kanonik metne çevrilir; ölçek ve
birim, gerekirse, tanım verisinin ya da domain katmanının işidir.

* ``Kayit`` — kaydın kimliği, türü, üretildiği tanım sürümü ve kökeni. Tür ile
  sürüm iki rastgele kimlik değildir: ``(kayit_turu_id, tanim_surumu_id)``
  bileşik dış anahtarla ``kayit_turu (id, tanim_surumu_id)`` çiftine bağlanır.
  **Durum sütunu yoktur** (karar 2026-09-21): satırın varlığı kesinliktir.
  Taslak dünyası ayrı tablolardadır (``taslak_tablolari``) ve geri alma /
  düzeltme yaşam döngüsü kendi semantiğiyle Aşama 4.14'te tasarlanacaktır;
  şimdiden yarım bir durum modeli açılmaz.
* ``KayitAlani`` — ``KAYIT → KAYIT ALANI → KAYIT ALANI TANIMI``. Değerler ana
  tabloya sütun olarak eklenmez. Satır kaydın türünü de taşır ve iki bileşik
  dış anahtarla hem kayda (``kayit (id, kayit_turu_id)``) hem alan tanımına
  (``kayit_alani_tanimi (id, kayit_turu_id)``) aynı tür üzerinden bağlanır:
  başka kayıt türünün alanı veritabanında da yazılamaz. Aynı kayıtta aynı alan
  bir kez bulunur; değeri olmayan alanın satırı yoktur (``NULL`` değer yok).
* ``KayitNesne`` — kayıt ile nesne arasında çoktan çoğa, **rolsüz** bağ. Hangi
  ucun ne anlama geldiği (asıl taraf, karşı taraf, ödeyen gibi) çekirdeğin
  bilgisi değildir; gerekirse tanım verisiyle ifade edilir. Aynı çift bir kez
  yazılır.

**Köken (provenance).** ``islem_paketi_id`` zorunludur (karar 2026-09-21):
kesin kayıt her zaman bir işlem paketine, dolayısıyla paketin okumasına ve
belgesine dayanır. ``kaynak_id`` isteğe bağlıdır; verilirse kaydın hangi belge
parçasından çıktığını gösterir. İkisi de ``okuma_id`` üzerinden bileşik dış
anahtarla aynı okumaya kilitlenir (4.4 / 4.5 kalıbı): başka okumanın kaynağı
ya da paketle tutarsız bir okuma veritabanı düzeyinde reddedilir.

Kayıt ile bağlandığı nesnenin aynı tanım sürümünde olması **zorunlu değildir**
(karar 2026-09-21): yeni sürümde üretilen kayıt, eski sürümde doğmuş etkin bir
nesneye bağlanabilir. Kayıt türü ile nesne türü arasında semantik uygunluk
gerekirse bu, tanım ve kural sisteminin (Aşama 4.9) konusudur.

Bu modül yalnız şemadır; ``relationship`` yoktur (bkz. ``tanim_tablolari``).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from defteriki.cekirdek.belge_tablolari import KAYNAK
from defteriki.cekirdek.nesne_tablolari import NESNE
from defteriki.cekirdek.tanim_tablolari import KAYIT_ALANI_TANIMI, KAYIT_TURU
from defteriki.cekirdek.taslak_tablolari import ISLEM_PAKETI
from defteriki.cekirdek.veritabani import TabloTabani

KAYIT = "kayit"
KAYIT_ALANI = "kayit_alani"
KAYIT_NESNE = "kayit_nesne"

KAYIT_TABLOLARI: tuple[str, ...] = (KAYIT, KAYIT_ALANI, KAYIT_NESNE)
"""Kesin kayıt tabloları, bağımlılık sırasıyla (göç ve testler için)."""


class Kayit(TabloTabani):
    __tablename__ = KAYIT

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kayit_turu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tanim_surumu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    """Kaydın üretildiği tanım sürümü; kalıcıdır, sonradan değişmez."""
    islem_paketi_id: Mapped[int] = mapped_column(Integer, nullable=False)
    """Kaydı doğuran işlem paketi; zorunlu köken."""
    okuma_id: Mapped[int] = mapped_column(Integer, nullable=False)
    """Paketin okuması; paket ve kaynak bu sütun üzerinden aynı okumaya bağlanır."""
    kaynak_id: Mapped[int | None] = mapped_column(Integer)
    """Belgenin hangi parçasından çıktığı; isteğe bağlı, okuma düzeyinde köken
    her hâlükârda vardır."""
    olusturma_zamani: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["kayit_turu_id", "tanim_surumu_id"],
            [f"{KAYIT_TURU}.id", f"{KAYIT_TURU}.tanim_surumu_id"],
            ondelete="RESTRICT",
        ),
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
        # Kayıt alanının bileşik dış anahtarı için hedef çift.
        UniqueConstraint("id", "kayit_turu_id"),
        Index(None, "kayit_turu_id"),
        Index(None, "tanim_surumu_id"),
        Index(None, "islem_paketi_id"),
        Index(None, "kaynak_id"),
    )


class KayitAlani(TabloTabani):
    __tablename__ = KAYIT_ALANI

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kayit_id: Mapped[int] = mapped_column(Integer, nullable=False)
    kayit_turu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    """Kaydın türü; iki bileşik dış anahtarın ortak sütunu."""
    kayit_alani_tanimi_id: Mapped[int] = mapped_column(Integer, nullable=False)
    deger: Mapped[str] = mapped_column(Text, nullable=False)
    """Türe göre kanonik metin (``deger_kodlama``)."""

    __table_args__ = (
        ForeignKeyConstraint(
            ["kayit_id", "kayit_turu_id"],
            [f"{KAYIT}.id", f"{KAYIT}.kayit_turu_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["kayit_alani_tanimi_id", "kayit_turu_id"],
            [f"{KAYIT_ALANI_TANIMI}.id", f"{KAYIT_ALANI_TANIMI}.kayit_turu_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("kayit_id", "kayit_alani_tanimi_id"),
        Index(None, "kayit_alani_tanimi_id"),
    )


class KayitNesne(TabloTabani):
    __tablename__ = KAYIT_NESNE

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kayit_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{KAYIT}.id", ondelete="RESTRICT"), nullable=False
    )
    nesne_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{NESNE}.id", ondelete="RESTRICT"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("kayit_id", "nesne_id"),
        Index(None, "nesne_id"),
    )
