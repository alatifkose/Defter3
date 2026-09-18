"""Genel tanım sisteminin tabloları (Aşama 4.2, hiyerarşi kuralı ve kilit 4.3).

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
  eskisinin satırlarını değiştirmez, kendi satırlarını taşır. ``kilitli``
  (Aşama 4.3): sürüm altında ilk nesne üretilince sürüm kilitlenir ve artık
  tanım alamaz; böylece var olan nesnelerin anlamı sessizce değişmez.
* ``NesneTuru`` — sürüm içinde ``kod`` benzersiz.
* ``OzellikTanimi`` — bir nesne türünün özelliği; tür içinde ``kod`` benzersiz.
  ``deger_turu`` (``DegerTuru``: metin, tam sayı, mantıksal, ondalık) ve
  ``zorunlu`` tanım verisinin parçasıdır (Aşama 4.3).
* ``IliskiTanimi`` — iki nesne türü arasında yönlü ilişki (kaynak → hedef);
  sürüm içinde ``kod`` benzersiz. Kaynak ve hedef tür ilişkinin kendi
  sürümünde olmak zorundadır; bu, bileşik dış anahtarlarla veritabanında
  zorlanır (``NesneTuru`` üzerindeki ``(id, tanim_surumu_id)`` benzersizliği
  bunun için vardır).
* ``HiyerarsiKurali`` — bir ilişki tanımını hiyerarşik üst bağlantısı yapar
  (Aşama 4.3). Kural satırı varsa ilişki hiyerarşiktir; yön sabittir: ilişkinin
  **kaynağı çocuk, hedefi üst** türdür. Kural en az / en çok üst sayısını ve
  üstün gerekli yaşam durumunu verir; zorunluluk ``en_az_ust >= 1`` demektir.
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
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from defteriki.cekirdek.veritabani import TabloTabani

TANIM_PAKETI = "tanim_paketi"
TANIM_SURUMU = "tanim_surumu"
NESNE_TURU = "nesne_turu"
OZELLIK_TANIMI = "ozellik_tanimi"
ILISKI_TANIMI = "iliski_tanimi"
HIYERARSI_KURALI = "hiyerarsi_kurali"
KAYIT_TURU = "kayit_turu"
KAYIT_ALANI_TANIMI = "kayit_alani_tanimi"

TANIM_TABLOLARI: tuple[str, ...] = (
    TANIM_PAKETI,
    TANIM_SURUMU,
    NESNE_TURU,
    OZELLIK_TANIMI,
    ILISKI_TANIMI,
    HIYERARSI_KURALI,
    KAYIT_TURU,
    KAYIT_ALANI_TANIMI,
)
"""Tanım tabloları, bağımlılık sırasıyla (göç ve testler için)."""


class DegerTuru(StrEnum):
    """Özellik değerinin teknik türü; domain anlamı taşımaz.

    ``ONDALIK`` kesin ondalık sayıdır (``decimal.Decimal``); ``float`` ve REAL
    kullanılmaz, ölçek ya da birim varsayımı yoktur. Değerler ``nesne_ozelligi``
    tablosunda metin olarak, türe göre kanonik biçimde saklanır
    (``nesne_islemleri``).
    """

    METIN = "metin"
    TAM_SAYI = "tam_sayi"
    MANTIKSAL = "mantiksal"
    ONDALIK = "ondalik"


class YasamDurumu(StrEnum):
    """Nesnenin genel yaşam durumu (Aşama 4.3): yalnız iki değer. Taslak, onay,
    şüphe gibi durumlar sonraki aşamaların işidir ve buraya girmez."""

    ETKIN = "etkin"
    KAPALI = "kapali"


def _sql_listesi(degerler: type[StrEnum]) -> str:
    return ", ".join(f"'{d.value}'" for d in degerler)


DEGER_TURU_KOSULU = f"deger_turu IN ({_sql_listesi(DegerTuru)})"
YASAM_DURUMU_KOSULU = f"yasam_durumu IN ({_sql_listesi(YasamDurumu)})"
UST_YASAM_DURUMU_KOSULU = (
    f"ust_yasam_durumu IS NULL OR ust_yasam_durumu IN ({_sql_listesi(YasamDurumu)})"
)


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
    """Paket içinde benzersiz pozitif tam sayı; çağıran verir, sistem türetmez.
    Kontrol kısıtı depolama sınıfını da zorlar (``typeof = 'integer'``)."""
    aciklama: Mapped[str | None] = mapped_column(Text)
    olusturma_zamani: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    kilitli: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0")
    )
    """Sürüm altında ilk nesne üretilince ``True`` olur; kilitli sürüme tanım
    eklenemez (göç 0004)."""

    __table_args__ = (
        UniqueConstraint("tanim_paketi_id", "surum_no"),
        # SQLite INTEGER sütunu katı değildir (1.5 REAL olarak saklanır);
        # depolama sınıfı da kontrol edilir. Göç 0003 (0002'deki ``surum_no > 0``
        # kısıtının yerine).
        CheckConstraint(
            "typeof(surum_no) = 'integer' AND surum_no > 0",
            name="surum_no_pozitif_tamsayi",
        ),
        CheckConstraint("kilitli IN (0, 1)", name="kilitli_ikili"),
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
        # İlişki tanımı ve nesne tablolarının bileşik dış anahtarları için:
        # (id, sürüm) çifti hedef olur.
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
    deger_turu: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text(f"'{DegerTuru.METIN.value}'")
    )
    """``DegerTuru`` değeri; göç 0004 öncesi satırlar (varsa) metin sayılır."""
    zorunlu: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0")
    )
    """Zorunluysa nesne bu özellik olmadan oluşturulamaz ve özellik silinemez."""

    __table_args__ = (
        UniqueConstraint("nesne_turu_id", "kod"),
        # Nesne özelliğinin bileşik dış anahtarı için: (id, tür) çifti hedef olur.
        UniqueConstraint("id", "nesne_turu_id"),
        CheckConstraint(DEGER_TURU_KOSULU, name="deger_turu_gecerli"),
        CheckConstraint("zorunlu IN (0, 1)", name="zorunlu_ikili"),
    )


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
        # Nesne ilişkisinin bileşik dış anahtarı için benzersiz indeks (göç 0004):
        # ilişki satırı tanımın sürümünü ve kaynak/hedef türünü de taşır.
        Index(
            None,
            "id",
            "tanim_surumu_id",
            "kaynak_nesne_turu_id",
            "hedef_nesne_turu_id",
            unique=True,
        ),
    )


class HiyerarsiKurali(TabloTabani):
    """Bir ilişki tanımını hiyerarşik üst bağlantısı yapan kural (Aşama 4.3).

    İlişkinin kaynak türü çocuk, hedef türü üsttür. ``en_az_ust`` etkin çocuğun
    gerekli durumdaki en az üst sayısı (0 = isteğe bağlı), ``en_cok_ust`` toplam
    üst bağlantısı sınırı (``None`` = sınırsız), ``ust_yasam_durumu`` üstün
    olması gereken yaşam durumu (``None`` = fark etmez). Sayılar tanım
    verisidir; çekirdek seviye ya da sabit sayı varsaymaz.
    """

    __tablename__ = HIYERARSI_KURALI

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    iliski_tanimi_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{ILISKI_TANIMI}.id", ondelete="RESTRICT"), nullable=False
    )
    en_az_ust: Mapped[int] = mapped_column(Integer, nullable=False)
    en_cok_ust: Mapped[int | None] = mapped_column(Integer)
    ust_yasam_durumu: Mapped[str | None] = mapped_column(String)

    __table_args__ = (
        UniqueConstraint("iliski_tanimi_id"),
        CheckConstraint(
            "typeof(en_az_ust) = 'integer' AND en_az_ust >= 0", name="en_az_ust_dogal"
        ),
        CheckConstraint(
            "en_cok_ust IS NULL OR (typeof(en_cok_ust) = 'integer' "
            "AND en_cok_ust >= 1 AND en_cok_ust >= en_az_ust)",
            name="en_cok_ust_tutarli",
        ),
        CheckConstraint(UST_YASAM_DURUMU_KOSULU, name="ust_yasam_durumu_gecerli"),
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
