"""İş denetim izinin tablosu ve aktör modeli (Aşama 4.6).

Teknik hata günlüğü (``defteriki.gunluk``) ile iş denetim izi **ayrı**
mekanizmalardır: günlük teknik arıza içindir ve dosyaya yazar, denetim izi
işin kendisinin kalıcı kaydıdır ve veritabanında durur. İkisi birleştirilmez.

Her satır bir olayı, olayın zamanını, **aktörü** ve olayın anlaşılması için
gereken kimlik referanslarını taşır. Aktör baştan zorunludur: 4.6'nın durum
değiştiren servisleri aktörü açıkça alır, "kim yaptı belli değil" varsayımı
yoktur.

Gizlilik: denetim izine belge ham içeriği, özelliklerin ham değerleri, sır ya
da dosya içeriği yazılmaz. Kimlik / referans saklamak yeterliyse değer tekrar
kopyalanmaz; ``gerekce`` yalnız kullanıcının kısa açıklaması içindir ve
uzunluğu ``denetim_islemleri`` tarafından sınırlanır.

Dış anahtarlar: hiç silinmeyen satırlara (``islem_paketi``, ``karar_talebi``,
``nesne``, ``ozellik_tanimi``) ``RESTRICT`` ile bağlanır. ``aday_nesne_id``
bilerek dış anahtar **değildir**: aday nesne taslak yaşam döngüsünde
silinebilir ve denetim izi silinen satırdan sonra da yaşamalıdır; denetim izi
bir iş işlemini engellemez. Silinen adayın kimliği yeni bir adaya **yeniden
verilmez**: ``aday_nesne`` ``AUTOINCREMENT`` kullanır (göç ``0009``), böylece
yıllar sonra okunan bir iz başka bir adayı anlatıyor olamaz.

Bu modül ``nesne_tablolari``yı ve ``mukerrerlik_tablolari``yı **import
etmez**: ``taslak_islemleri`` bu modülün yazma işlevlerini kullanır ve taslak
→ kesin nesne import zinciri yasaktır (``tests/test_mimari_sinir.py``).
Bağlanılan iki tablonun adı bu yüzden yerel sabittir (``KESIN_NESNE``,
``KARAR_TALEBI``); adların doğruluğu testle korunur.

Bu modül yalnız şemadır: satır yazmaz, ``relationship`` içermez.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from defteriki.cekirdek.tanim_tablolari import OZELLIK_TANIMI
from defteriki.cekirdek.taslak_tablolari import ISLEM_PAKETI
from defteriki.cekirdek.veritabani import TabloTabani

KESIN_NESNE = "nesne"
"""``nesne_tablolari.NESNE`` ile aynı ad; oradan import edilmez (modül
açıklamasındaki sınır). Eşitlik ``tests/test_mukerrerlik.py`` ile korunur."""

KARAR_TALEBI = "karar_talebi"
"""``mukerrerlik_tablolari.KARAR_TALEBI`` ile aynı ad; oradan import edilmez
(import döngüsü olurdu: mükerrerlik şeması aktör türünü buradan alır)."""

DENETIM_IZI = "denetim_izi"

DENETIM_TABLOLARI: tuple[str, ...] = (DENETIM_IZI,)


class AktorTuru(StrEnum):
    """Olayı yapan tarafın türü; domain anlamı taşımaz."""

    KULLANICI = "kullanici"
    AJAN = "ajan"
    SISTEM = "sistem"


class DenetimOlayi(StrEnum):
    """Denetim izine yazılabilen iş olayları (Aşama 4.6 kapsamı)."""

    MUKERRERLIK_SARTI_BELIRLENDI = "mukerrerlik_sarti_belirlendi"
    MUKERRERLIK_SUPHESI_ACILDI = "mukerrerlik_suphesi_acildi"
    KARAR_TALEBI_ACILDI = "karar_talebi_acildi"
    KULLANICI_KARARI_VERILDI = "kullanici_karari_verildi"
    NESNE_AYRI_KABUL_EDILDI = "nesne_ayri_kabul_edildi"
    NESNE_BIRLESTIRILDI = "nesne_birlestirildi"
    ADAY_NESNEYE_COZUMLENDI = "aday_nesneye_cozumlendi"
    PAKET_BEKLEMEYE_GECTI = "paket_beklemeye_gecti"
    PAKET_YENIDEN_CALISIYOR = "paket_yeniden_calisiyor"
    KARAR_TALEBI_GECERSIZ_KALDI = "karar_talebi_gecersiz_kaldi"
    """Paketi iptal edilen talep terminal ``gecersiz`` duruma geçti; karar
    verilmedi, satır geçmişte kalır."""
    BIRLESIM_YENIDEN_BAGLANDI = "birlesim_yeniden_baglandi"
    """Eski bir birleşimin kanonik hedefi, hedefin kendisi birleşince yeni
    kanonik nesneye bağlandı (zincir düzleştirildi)."""
    KARAR_TALEBI_PAKETE_BAGLANDI = "karar_talebi_pakete_baglandi"
    """Mevcut bir talebe bir paket daha bağlandı; yeni talep açılmadı."""
    KARAR_TALEBI_KOKENI_DEVREDILDI = "karar_talebi_kokeni_devredildi"
    """Mevcut bir talep bağımsız kökeni devraldı; yeni talep açılmadı.

    Bu ikisi 2026-09-20 bağımsız denetiminin 2. bulgusuyla ayrıldı (göç
    ``0012``): üçü de ``KARAR_TALEBI_ACILDI`` yazdığı için denetim izinden
    "kaç karar talebi açıldı" diye saymak yanlış sonuç veriyordu. Artık o ad
    yalnız gerçekten açılan talebi anlatır (``_talep_ac``)."""


@dataclass(frozen=True, slots=True)
class Aktor:
    """Olayı yapan taraf: tür ve serbest kimlik metni.

    Kimlik çekirdek için anlamsız bir etikettir (kullanıcı adı, ajan adı,
    ``defteriki``); çekirdek onu yorumlamaz, yalnız kaydeder.
    """

    tur: AktorTuru
    kimlik: str


OLAY_KOSULU = "olay IN ({})".format(", ".join(f"'{o.value}'" for o in DenetimOlayi))
AKTOR_TURU_KOSULU = "aktor_turu IN ({})".format(
    ", ".join(f"'{a.value}'" for a in AktorTuru)
)


class DenetimIzi(TabloTabani):
    __tablename__ = DENETIM_IZI

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    olay: Mapped[str] = mapped_column(String, nullable=False)
    olay_zamani: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    aktor_turu: Mapped[str] = mapped_column(String, nullable=False)
    aktor_kimligi: Mapped[str] = mapped_column(String, nullable=False)
    islem_paketi_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey(f"{ISLEM_PAKETI}.id", ondelete="RESTRICT")
    )
    karar_talebi_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey(f"{KARAR_TALEBI}.id", ondelete="RESTRICT")
    )
    nesne_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey(f"{KESIN_NESNE}.id", ondelete="RESTRICT")
    )
    ikincil_nesne_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey(f"{KESIN_NESNE}.id", ondelete="RESTRICT")
    )
    """Olayın ikinci ucu: birleşimde kaynak nesne, şüphede karşı uç."""
    aday_nesne_id: Mapped[int | None] = mapped_column(Integer)
    """Dış anahtar değildir (modül açıklaması): aday nesne silinebilir."""
    ozellik_tanimi_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey(f"{OZELLIK_TANIMI}.id", ondelete="RESTRICT")
    )
    """Şüpheyi doğuran şart özelliği; değeri değil, kimliği saklanır."""
    gerekce: Mapped[str | None] = mapped_column(Text)
    """Kısa, insan yazımı açıklama; ham değer ya da içerik taşımaz."""

    __table_args__ = (
        CheckConstraint(OLAY_KOSULU, name="olay_gecerli"),
        CheckConstraint(AKTOR_TURU_KOSULU, name="aktor_turu_gecerli"),
        CheckConstraint("length(aktor_kimligi) > 0", name="aktor_kimligi_dolu"),
        Index(None, "olay"),
        Index(None, "islem_paketi_id"),
        Index(None, "karar_talebi_id"),
        Index(None, "nesne_id"),
    )
