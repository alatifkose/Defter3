"""Mükerrerlik şartı, karar talebi ve çözümleme tabloları (Aşama 4.6).

Mükerrerlik **benzersizlik kısıtı değildir**. Eşleşme "bunlar kesinlikle aynı
nesnedir" demek değil, yalnız "mükerrerlik şüphesi var" demektir; kararı
kullanıcı verir. Çekirdek şart olarak seçilen özelliklerin anlamını bilmez;
yalnız ``ozellik_tanimi`` kimliklerini ve ``deger_kodlama`` ile üretilmiş
kanonik değerleri birebir karşılaştırır.

* ``NesneMukerrerlikSarti`` / ``AdayNesneMukerrerlikSarti`` — kullanıcının bir
  kesin nesne ya da aday nesne için şart olarak seçtiği özellik tanımları.
  Sıfır, bir ya da birden fazla şart seçilebilir; birden fazlaysa **VEYA**
  mantığı geçerlidir (herhangi biri eşleşirse şüphe). Şart seçilmemiş uç kendi
  şartını sunmaz. İki bileşik dış anahtar aynı ``nesne_turu_id`` üzerinden
  bağlanır: başka türün özelliği şart olarak veritabanında da seçilemez.
* ``KararTalebi`` — mükerrerlik şüphesi **ve** ona bağlı kalıcı kullanıcı
  karar talebi aynı satırdır. Ayrı iki tabloya bölünmedi: şüphenin açık olup
  olmaması ile talebin açık olup olmaması tek gerçektir ve "aynı çift için
  ikinci açık şüphe" kısıtı ancak tek satırda kısmi benzersiz indeksle
  ifade edilebilir (iki tablo iki doğruluk kaynağı ve eşzamanlılık boşluğu
  üretirdi). Talebin kimliği Aşama 3.4'te doğrulanan ``BEKLIYOR + talep
  kimliği`` protokolündeki kalıcı kimliktir.

  Uçlardan biri her zaman **mevcut kesin nesne** (``hedef_nesne_id``), diğeri
  ya bir aday nesne (``aday_nesne_id``) ya da başka bir kesin nesnedir
  (``kaynak_nesne_id``); tam olarak biri doludur (kontrol kısıtı). Kesin çift
  sırası normalleştirilir: ``kaynak_nesne_id > hedef_nesne_id``, yani ilk
  oluşturulan nesne korunacak olandır ve ``(A, B)`` ile ``(B, A)`` iki ayrı
  satır olamaz.

  ``durum`` ``acik`` iken ``karar`` boştur; ``cozuldu`` iken ``karar``
  ``ayni`` ya da ``ayri``dır (kontrol kısıtı). ``kararsiz`` kararı satıra
  yazılmaz: şüphe çözülmüş sayılmadığından talep açık kalır, karar yalnız
  denetim izinde görünür. Üçüncü ve terminal durum ``gecersiz``tir: karar
  verilmeden hükümsüz kalan talep. İki nedenle olur — paketi iptal edilmiştir
  ya da bir ucu birleşme sonucu kanonik olmaktan çıkmıştır; neden denetim
  izinin gerekçesindedir. ``karar`` yine boş kalır — ikisi de kullanıcı kararı
  değildir; satır silinmez, geçmişte görünür, ama açık talep kısmi benzersiz
  indeksinden ve "bu çift zaten değerlendirildi" denetiminden çıkar, böylece
  aynı çift yeniden değerlendirilebilir.
  ``gecersizlik_zamani`` yalnız bu durumda doludur (kontrol kısıtı).

  Kararı **yalnız kullanıcı** verir: ``karar_aktor_turu`` veritabanı düzeyinde
  de ``kullanici`` olmak zorundadır. Talebi açan aktör (``acan_aktor_turu``)
  üç türden biri olabilir; ajan tarama yapıp şüphe açabilir, karar veremez.
* ``AdayNesneCozumlemesi`` — ``AYNI`` kararından sonra "bu aday nesne şu
  mevcut kesin nesne olarak çözüldü" bilgisi. Aşama 4.8 paketi
  kesinleştirirken bunu tahmin etmez, buradan okur. Aday satır kesin tabloya
  taşınmaz; köprü ayrı tablodadır. ``nesne_id`` kararın verildiği andaki
  nesnedir ve değişmez; o nesne sonradan başka bir nesneye birleşirse güncel
  kanonik nesne ``NesneBirlesimi`` üzerinden tek adımda bulunur
  (``mukerrerlik_islemleri.adayin_kesin_nesnesi``).
* ``NesneBirlesimi`` — iki kesin nesnenin birleştirilmesi. Birleşen nesne
  silinmez; ilişkileri hedefe taşınır, yaşam durumu ``kapali`` olur ve bu satır
  onu kalıcı olarak hedefe bağlar. İki ayrı sütun vardır: ``hedef_nesne_id``
  kullanıcının o an verdiği kararın değişmez kaydıdır; ``kanonik_nesne_id``
  ise bugünkü kanonik nesnedir ve hiçbir zaman kendisi birleşmiş bir nesne
  olamaz. Hedef sonradan başka bir nesneye birleşirse eski satırların
  ``kanonik_nesne_id``si yeni kanonik nesneye bağlanır (zincir düzleştirilir,
  denetim izine ``birlesim_yeniden_baglandi`` yazılır); karar geçmişi
  bozulmaz, kanonik nesne her zaman tek sıçramada bulunur.

Bu modül ``nesne_tablolari``yı **import etmez**: ``taslak_islemleri`` bu modülü
kullanır ve taslak → kesin nesne import zinciri yasaktır
(``tests/test_mimari_sinir.py``). Kesin nesne tablosunun adı bu yüzden yerel
sabittir (``KESIN_NESNE``); adın doğruluğu testle korunur. Aktör türü
``denetim_tablolari``dan gelir; o modül de bu modülü import etmez (tablo adı
orada yerel sabittir), döngü yoktur. Bu modül yalnız şemadır: satır yazmaz,
``relationship`` içermez.
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from defteriki.cekirdek.denetim_tablolari import AktorTuru
from defteriki.cekirdek.tanim_tablolari import OZELLIK_TANIMI
from defteriki.cekirdek.taslak_tablolari import ADAY_NESNE, ISLEM_PAKETI
from defteriki.cekirdek.veritabani import TabloTabani

KESIN_NESNE = "nesne"
"""``nesne_tablolari.NESNE`` ile aynı ad; oradan import edilmez (modül
açıklamasındaki sınır). Eşitlik ``tests/test_mukerrerlik.py`` ile korunur."""

NESNE_MUKERRERLIK_SARTI = "nesne_mukerrerlik_sarti"
ADAY_NESNE_MUKERRERLIK_SARTI = "aday_nesne_mukerrerlik_sarti"
KARAR_TALEBI = "karar_talebi"
ADAY_NESNE_COZUMLEMESI = "aday_nesne_cozumlemesi"
NESNE_BIRLESIMI = "nesne_birlesimi"

MUKERRERLIK_TABLOLARI: tuple[str, ...] = (
    NESNE_MUKERRERLIK_SARTI,
    ADAY_NESNE_MUKERRERLIK_SARTI,
    KARAR_TALEBI,
    ADAY_NESNE_COZUMLEMESI,
    NESNE_BIRLESIMI,
)
"""Mükerrerlik tabloları, bağımlılık sırasıyla (göç ve testler için)."""


class TalepDurumu(StrEnum):
    """Karar talebinin yaşam durumu; ``COZULDU`` ve ``GECERSIZ`` terminaldir."""

    ACIK = "acik"
    COZULDU = "cozuldu"
    GECERSIZ = "gecersiz"
    """Karar verilmeden hükümsüz kalan talep: paketi iptal edilmiştir ya da bir
    ucu birleşme sonucu kanonik olmaktan çıkmıştır. Satır geçmişte durur, açık
    talep sayılmaz; neden denetim izindedir."""


ACIK_OLMAYAN_DURUMLAR: tuple[TalepDurumu, ...] = (
    TalepDurumu.COZULDU,
    TalepDurumu.GECERSIZ,
)
"""Talebin kapandığı terminal durumlar."""


class Karar(StrEnum):
    """Kullanıcının mükerrerlik kararı.

    ``KARARSIZ`` şüpheyi çözmez ve satıra yazılmaz; yalnız denetim izinde
    görünür, talep açık kalır (bkz. ``mukerrerlik_islemleri``).
    """

    AYNI = "ayni"
    AYRI = "ayri"
    KARARSIZ = "kararsiz"


COZEN_KARARLAR: tuple[Karar, ...] = (Karar.AYNI, Karar.AYRI)
"""Talebi kapatan, dolayısıyla satıra yazılabilen kararlar."""


def _sql_listesi(degerler: tuple[str, ...]) -> str:
    return ", ".join(f"'{d}'" for d in degerler)


TALEP_DURUMU_KOSULU = f"durum IN ({_sql_listesi(tuple(d.value for d in TalepDurumu))})"
_COZEN = _sql_listesi(tuple(k.value for k in COZEN_KARARLAR))
KARAR_KOSULU = f"karar IS NULL OR karar IN ({_COZEN})"
DURUM_KARAR_KOSULU = (
    f"(durum = '{TalepDurumu.ACIK.value}' AND karar IS NULL "
    "AND karar_zamani IS NULL AND karar_aktor_turu IS NULL "
    "AND gecersizlik_zamani IS NULL) OR "
    f"(durum = '{TalepDurumu.COZULDU.value}' AND karar IS NOT NULL "
    "AND karar_zamani IS NOT NULL AND karar_aktor_turu IS NOT NULL "
    "AND gecersizlik_zamani IS NULL) OR "
    f"(durum = '{TalepDurumu.GECERSIZ.value}' AND karar IS NULL "
    "AND karar_zamani IS NULL AND karar_aktor_turu IS NULL "
    "AND gecersizlik_zamani IS NOT NULL)"
)
"""Durum ile karar / geçersizlik alanları birlikte tutarlı olmak zorunda."""
ACAN_AKTOR_KOSULU = (
    f"acan_aktor_turu IN ({_sql_listesi(tuple(a.value for a in AktorTuru))})"
)
"""Şüpheyi ajan da açabilir; tür yine de tanımlı üç değerden biri olmalı."""
KARAR_AKTORU_KOSULU = (
    f"karar_aktor_turu IS NULL OR karar_aktor_turu = '{AktorTuru.KULLANICI.value}'"
)
"""Kararı yalnız kullanıcı verir; ham SQL de ajan / sistem kararı yazamaz.
Aşama 4.9 yeni bir karar kaynağı getirirse bu kısıt göçle genişletilir."""
COZEN_AKTOR_KOSULU = f"aktor_turu = '{AktorTuru.KULLANICI.value}'"
"""Çözümleme ve birleşim satırları yalnız kullanıcı kararından doğar."""
TEK_UC_KOSULU = "(aday_nesne_id IS NULL) <> (kaynak_nesne_id IS NULL)"
"""Karşı uç ya aday nesnedir ya kesin nesne; tam olarak biri."""
KESIN_CIFT_SIRASI_KOSULU = "kaynak_nesne_id IS NULL OR kaynak_nesne_id > hedef_nesne_id"
"""Kesin çiftte korunacak (önce oluşturulan) nesne hedeftir; çift tek yönlüdür."""


class NesneMukerrerlikSarti(TabloTabani):
    __tablename__ = NESNE_MUKERRERLIK_SARTI

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nesne_id: Mapped[int] = mapped_column(Integer, nullable=False)
    nesne_turu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    """Nesnenin türü; iki bileşik dış anahtarın ortak sütunu."""
    ozellik_tanimi_id: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["nesne_id", "nesne_turu_id"],
            [f"{KESIN_NESNE}.id", f"{KESIN_NESNE}.nesne_turu_id"],
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


class AdayNesneMukerrerlikSarti(TabloTabani):
    __tablename__ = ADAY_NESNE_MUKERRERLIK_SARTI

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aday_nesne_id: Mapped[int] = mapped_column(Integer, nullable=False)
    nesne_turu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ozellik_tanimi_id: Mapped[int] = mapped_column(Integer, nullable=False)

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


class KararTalebi(TabloTabani):
    __tablename__ = KARAR_TALEBI

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    """Kalıcı talep kimliği; ``BEKLIYOR`` yanıtında çağırana verilir."""
    durum: Mapped[str] = mapped_column(String, nullable=False)
    islem_paketi_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey(f"{ISLEM_PAKETI}.id", ondelete="RESTRICT")
    )
    """Şüphe bir işlem paketinden doğduysa paketi; iki kesin nesne arasındaki
    bağımsız şüphede boş olabilir."""
    nesne_turu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    """İki uç da aynı nesne türündedir; bileşik dış anahtarların ortak sütunu."""
    aday_nesne_id: Mapped[int | None] = mapped_column(Integer)
    kaynak_nesne_id: Mapped[int | None] = mapped_column(Integer)
    """Kesin çiftte birleşecek (sonra oluşturulan) nesne."""
    hedef_nesne_id: Mapped[int] = mapped_column(Integer, nullable=False)
    """Mevcut kesin nesne; ``AYNI`` kararında korunacak olandır."""
    eslesen_ozellik_tanimi_id: Mapped[int] = mapped_column(Integer, nullable=False)
    """Şüpheyi doğuran şart özelliği; kanıt referansıdır, değeri kopyalanmaz."""
    olusturma_zamani: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    acan_aktor_turu: Mapped[str] = mapped_column(String, nullable=False)
    acan_aktor_kimligi: Mapped[str] = mapped_column(String, nullable=False)
    karar: Mapped[str | None] = mapped_column(String)
    karar_zamani: Mapped[datetime | None] = mapped_column(DateTime)
    karar_aktor_turu: Mapped[str | None] = mapped_column(String)
    karar_aktor_kimligi: Mapped[str | None] = mapped_column(String)
    gecersizlik_zamani: Mapped[datetime | None] = mapped_column(DateTime)
    """Yalnız ``gecersiz`` durumda dolu: paketi iptal edildiği için talebin
    hükümsüz kaldığı an. Kim iptal etti bilgisi denetim izindedir."""
    gerekce: Mapped[str | None] = mapped_column(Text)
    """Kullanıcının kısa gerekçesi; belge içeriği ya da ham değer taşımaz."""

    __table_args__ = (
        ForeignKeyConstraint(
            ["aday_nesne_id", "nesne_turu_id"],
            [f"{ADAY_NESNE}.id", f"{ADAY_NESNE}.nesne_turu_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["kaynak_nesne_id", "nesne_turu_id"],
            [f"{KESIN_NESNE}.id", f"{KESIN_NESNE}.nesne_turu_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["hedef_nesne_id", "nesne_turu_id"],
            [f"{KESIN_NESNE}.id", f"{KESIN_NESNE}.nesne_turu_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["eslesen_ozellik_tanimi_id", "nesne_turu_id"],
            [f"{OZELLIK_TANIMI}.id", f"{OZELLIK_TANIMI}.nesne_turu_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(TALEP_DURUMU_KOSULU, name="durum_gecerli"),
        CheckConstraint(KARAR_KOSULU, name="karar_gecerli"),
        CheckConstraint(DURUM_KARAR_KOSULU, name="durum_karar_tutarli"),
        CheckConstraint(TEK_UC_KOSULU, name="tek_karsi_uc"),
        CheckConstraint(KESIN_CIFT_SIRASI_KOSULU, name="kesin_cift_sirasi"),
        CheckConstraint(ACAN_AKTOR_KOSULU, name="acan_aktor_turu_gecerli"),
        CheckConstraint(KARAR_AKTORU_KOSULU, name="karari_kullanici_verir"),
        # Aynı çift için ikinci bir AÇIK talep açılamaz (eşzamanlı açma dahil);
        # çözülmüş talepler kısıt dışıdır, satırda kalır.
        Index(
            "ix_karar_talebi_acik_aday",
            "aday_nesne_id",
            "hedef_nesne_id",
            unique=True,
            sqlite_where=text(
                f"durum = '{TalepDurumu.ACIK.value}' AND aday_nesne_id IS NOT NULL"
            ),
        ),
        Index(
            "ix_karar_talebi_acik_kesin",
            "kaynak_nesne_id",
            "hedef_nesne_id",
            unique=True,
            sqlite_where=text(
                f"durum = '{TalepDurumu.ACIK.value}' AND kaynak_nesne_id IS NOT NULL"
            ),
        ),
        Index(None, "islem_paketi_id"),
        Index(None, "durum"),
        Index(None, "hedef_nesne_id"),
    )


class AdayNesneCozumlemesi(TabloTabani):
    __tablename__ = ADAY_NESNE_COZUMLEMESI

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aday_nesne_id: Mapped[int] = mapped_column(Integer, nullable=False)
    nesne_turu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    nesne_id: Mapped[int] = mapped_column(Integer, nullable=False)
    """Adayın çözümlendiği mevcut kesin nesne."""
    karar_talebi_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{KARAR_TALEBI}.id", ondelete="RESTRICT"), nullable=False
    )
    olusturma_zamani: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    aktor_turu: Mapped[str] = mapped_column(String, nullable=False)
    aktor_kimligi: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["aday_nesne_id", "nesne_turu_id"],
            [f"{ADAY_NESNE}.id", f"{ADAY_NESNE}.nesne_turu_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["nesne_id", "nesne_turu_id"],
            [f"{KESIN_NESNE}.id", f"{KESIN_NESNE}.nesne_turu_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("aday_nesne_id"),
        UniqueConstraint("karar_talebi_id"),
        CheckConstraint(COZEN_AKTOR_KOSULU, name="karari_kullanici_verir"),
        Index(None, "nesne_id"),
    )


class NesneBirlesimi(TabloTabani):
    __tablename__ = NESNE_BIRLESIMI

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kaynak_nesne_id: Mapped[int] = mapped_column(Integer, nullable=False)
    """Birleşen nesne; silinmez, ``kapali`` olur ve burada kalıcı iz bırakır."""
    hedef_nesne_id: Mapped[int] = mapped_column(Integer, nullable=False)
    """Kullanıcının kararındaki hedef; değişmez tarihsel kayıttır."""
    kanonik_nesne_id: Mapped[int] = mapped_column(Integer, nullable=False)
    """Bugünkü kanonik nesne. Başlangıçta ``hedef_nesne_id`` ile aynıdır; hedef
    sonradan birleşirse buraya yeni kanonik nesne yazılır. Bu sütunun gösterdiği
    nesne hiçbir zaman kendisi birleşmiş olamaz, dolayısıyla kanonik nesne tek
    sıçramada bulunur (zincir yoktur)."""
    nesne_turu_id: Mapped[int] = mapped_column(Integer, nullable=False)
    karar_talebi_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{KARAR_TALEBI}.id", ondelete="RESTRICT"), nullable=False
    )
    olusturma_zamani: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    aktor_turu: Mapped[str] = mapped_column(String, nullable=False)
    aktor_kimligi: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["kanonik_nesne_id", "nesne_turu_id"],
            [f"{KESIN_NESNE}.id", f"{KESIN_NESNE}.nesne_turu_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["kaynak_nesne_id", "nesne_turu_id"],
            [f"{KESIN_NESNE}.id", f"{KESIN_NESNE}.nesne_turu_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["hedef_nesne_id", "nesne_turu_id"],
            [f"{KESIN_NESNE}.id", f"{KESIN_NESNE}.nesne_turu_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("kaynak_nesne_id"),
        UniqueConstraint("karar_talebi_id"),
        CheckConstraint(
            "kaynak_nesne_id <> hedef_nesne_id", name="kaynak_hedeften_farkli"
        ),
        CheckConstraint(
            "kaynak_nesne_id <> kanonik_nesne_id", name="kaynak_kanonikten_farkli"
        ),
        CheckConstraint(COZEN_AKTOR_KOSULU, name="karari_kullanici_verir"),
        Index(None, "hedef_nesne_id"),
        Index(None, "kanonik_nesne_id"),
    )
