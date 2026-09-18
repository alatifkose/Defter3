"""Genel tanım sisteminin tabloları (Aşama 4.2).

Çekirdek hangi nesne türlerinin, özelliklerin, ilişkilerin ve kayıt türlerinin
var olduğunu bilmez; bunları **veri** olarak tutar. Bir domain (ileride
``defteriki.finans``; testlerde nötr sahte paketler) kendi kavramlarını bu
tablolara tanım satırları olarak yazar. Buradaki hiçbir sınıf, sütun ya da
kısıt belirli bir domain'e ait anlam taşımaz; aynı şema kütüphane, envanter
ya da sağlık tanımları için de aynen kullanılır.

Yapı (üstten alta, her satır bir üstteki satıra dış anahtarla bağlı):

* ``TanimPaketi`` — bir domain'in tanımlarını gruplayan paket; ``kod`` tüm
  paketler arasında benzersiz.
* ``TanimSurumu`` — paketin bir sürümü; ``(tanim_paketi_id, surum_no)``
  benzersiz. Tanımlar pakete değil sürüme bağlıdır: paketin yeni sürümü
  eskisinin satırlarını değiştirmez, kendi satırlarını taşır. Böylece ileride
  bir kaydın hangi tanım dünyasında üretildiği sürüm kimliğiyle izlenir.
* ``NesneTuru`` — sürüm içinde ``kod`` benzersiz.
* ``OzellikTanimi`` — bir nesne türünün özelliği; tür içinde ``kod`` benzersiz.
* ``IliskiTanimi`` — iki nesne türü arasında yönlü ilişki (kaynak → hedef);
  sürüm içinde ``kod`` benzersiz. Kaynak ve hedef tür ilişkinin kendi
  sürümünde olmak zorundadır; bu, bileşik dış anahtarlarla veritabanında
  zorlanır (``NesneTuru`` üzerindeki ``(id, tanim_surumu_id)`` benzersizliği
  bunun için vardır).
* ``KayitTuru`` — sürüm içinde ``kod`` benzersiz.
* ``KayitAlaniTanimi`` — bir kayıt türünün alanı; tür içinde ``kod`` benzersiz.

Her tanımda ``kod`` makine kimliğidir (kararlı, ``tanim_islemleri.KOD_BICIMI``
biçiminde), ``gosterim_adi`` insan için başlıktır; ikisi karıştırılmaz.
Zaman damgaları UTC'dir ve saat dilimi bilgisi olmadan saklanır (SQLite
``DateTime`` saat dilimi taşımaz).

Bu modül yalnız şemadır: satır yazmaz, doğrulama yapmaz, ``defteriki``
içinden başka modül import etmez (``veritabani.TabloTabani`` dışında).
Yazma ve okuma ``tanim_islemleri`` üzerinden yapılır; ORM sınıfları
``Veritabani.islem`` dışında doğrudan kullanılmaz. Sınıflarda ``relationship``
bilerek yoktur: oturum kapandıktan sonra elde kalan nesne yalnız kendi
sütunlarını taşır, gecikmeli yükleme tuzağı olmaz.
"""

from __future__ import annotations

from datetime import UTC, datetime

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

from defteriki.cekirdek.veritabani import TabloTabani

TANIM_PAKETI = "tanim_paketi"
TANIM_SURUMU = "tanim_surumu"
NESNE_TURU = "nesne_turu"
OZELLIK_TANIMI = "ozellik_tanimi"
ILISKI_TANIMI = "iliski_tanimi"
KAYIT_TURU = "kayit_turu"
KAYIT_ALANI_TANIMI = "kayit_alani_tanimi"

TANIM_TABLOLARI: tuple[str, ...] = (
    TANIM_PAKETI,
    TANIM_SURUMU,
    NESNE_TURU,
    OZELLIK_TANIMI,
    ILISKI_TANIMI,
    KAYIT_TURU,
    KAYIT_ALANI_TANIMI,
)
"""Aşama 4.2'nin tabloları, bağımlılık sırasıyla (göç ve testler için)."""


def simdi_utc() -> datetime:
    """Şu anki UTC zamanı, saat dilimi bilgisi olmadan (sütunlarla aynı biçim)."""
    return datetime.now(UTC).replace(tzinfo=None)


class TanimPaketi(TabloTabani):
    __tablename__ = TANIM_PAKETI

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kod: Mapped[str] = mapped_column(String, nullable=False)
    """Paketin makine kimliği; bütün paketler arasında benzersiz."""
    gosterim_adi: Mapped[str] = mapped_column(String, nullable=False)
    aciklama: Mapped[str | None] = mapped_column(Text)
    olusturma_zamani: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (UniqueConstraint("kod"),)


class TanimSurumu(TabloTabani):
    __tablename__ = TANIM_SURUMU

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tanim_paketi_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{TANIM_PAKETI}.id", ondelete="RESTRICT"), nullable=False
    )
    surum_no: Mapped[int] = mapped_column(Integer, nullable=False)
    """Paket içinde artan, pozitif tam sayı; çağıran verir, sistem türetmez."""
    aciklama: Mapped[str | None] = mapped_column(Text)
    olusturma_zamani: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("tanim_paketi_id", "surum_no"),
        CheckConstraint("surum_no > 0", name="surum_no_pozitif"),
    )


class NesneTuru(TabloTabani):
    __tablename__ = NESNE_TURU

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tanim_surumu_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{TANIM_SURUMU}.id", ondelete="RESTRICT"), nullable=False
    )
    kod: Mapped[str] = mapped_column(String, nullable=False)
    gosterim_adi: Mapped[str] = mapped_column(String, nullable=False)
    aciklama: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("tanim_surumu_id", "kod"),
        # İlişki tanımının bileşik dış anahtarı için: (id, sürüm) çifti hedef olur.
        UniqueConstraint("id", "tanim_surumu_id"),
    )


class OzellikTanimi(TabloTabani):
    __tablename__ = OZELLIK_TANIMI

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nesne_turu_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{NESNE_TURU}.id", ondelete="RESTRICT"), nullable=False
    )
    kod: Mapped[str] = mapped_column(String, nullable=False)
    gosterim_adi: Mapped[str] = mapped_column(String, nullable=False)
    aciklama: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("nesne_turu_id", "kod"),)


class IliskiTanimi(TabloTabani):
    __tablename__ = ILISKI_TANIMI

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tanim_surumu_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{TANIM_SURUMU}.id", ondelete="RESTRICT"), nullable=False
    )
    kod: Mapped[str] = mapped_column(String, nullable=False)
    gosterim_adi: Mapped[str] = mapped_column(String, nullable=False)
    aciklama: Mapped[str | None] = mapped_column(Text)
    kaynak_nesne_turu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    """İlişkinin çıktığı tür; yön kaynak → hedef."""
    hedef_nesne_turu_id: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("tanim_surumu_id", "kod"),
        # Kaynak ve hedef tür ilişkinin kendi sürümünde olmak zorunda: bileşik
        # dış anahtar (tür kimliği, sürüm) → nesne_turu (id, tanim_surumu_id).
        ForeignKeyConstraint(
            ["kaynak_nesne_turu_id", "tanim_surumu_id"],
            [f"{NESNE_TURU}.id", f"{NESNE_TURU}.tanim_surumu_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["hedef_nesne_turu_id", "tanim_surumu_id"],
            [f"{NESNE_TURU}.id", f"{NESNE_TURU}.tanim_surumu_id"],
            ondelete="RESTRICT",
        ),
        Index(None, "kaynak_nesne_turu_id"),
        Index(None, "hedef_nesne_turu_id"),
    )


class KayitTuru(TabloTabani):
    __tablename__ = KAYIT_TURU

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tanim_surumu_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{TANIM_SURUMU}.id", ondelete="RESTRICT"), nullable=False
    )
    kod: Mapped[str] = mapped_column(String, nullable=False)
    gosterim_adi: Mapped[str] = mapped_column(String, nullable=False)
    aciklama: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("tanim_surumu_id", "kod"),)


class KayitAlaniTanimi(TabloTabani):
    __tablename__ = KAYIT_ALANI_TANIMI

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kayit_turu_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{KAYIT_TURU}.id", ondelete="RESTRICT"), nullable=False
    )
    kod: Mapped[str] = mapped_column(String, nullable=False)
    gosterim_adi: Mapped[str] = mapped_column(String, nullable=False)
    aciklama: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("kayit_turu_id", "kod"),)
