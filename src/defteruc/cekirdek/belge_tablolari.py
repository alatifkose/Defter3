"""Belge zincirinin tabloları (Aşama 4.4): arşiv dosyası, belge, okuma, kaynak.

Zincirin bu aşamada kurulan kısmı ``DOSYA → ARŞİV → BELGE → OKUMA → KAYNAK``.
Çekirdek belgenin ne olduğunu bilmez: bir PDF ile bir envanter listesi
arasında burada fark yoktur; belge türü, alan adı ya da içerik anlamı hiçbir
sütunda yer almaz.

* ``ArsivDosyasi`` — arşivdeki **değişmez baytların** kaydı. Fiziksel kimlik
  yalnız ``sha256``'dır: ``goreli_yol`` içerikten türer
  (``<ilk iki hex>/<sha256>``, uzantısız) ve bu türetme kontrol kısıtıyla
  veritabanında da zorlanır. Kaynak dosya adı, uzantı ve MIME metadata'dır;
  kimliğin parçası değildir. Tam yerel yol yazılmaz; fiziksel yol çalışma
  zamanında ``arşiv dizini + goreli_yol`` ile kurulur.
* ``Belge`` — uygulamadaki belge kimliği; fiziksel dosyanın kendisi değildir.
  Bir arşiv dosyasından en çok bir belge olur (``arsiv_dosyasi_id`` benzersiz);
  aynı baytlar ikinci kez gelince mevcut belge döner.
* ``Okuma`` — dış okuyucunun (Cowork) belgeden çıkardığı yapılandırılmış
  içeriğin belirli bir sürümü. Aynı belge birden çok kez okunabilir;
  ``(belge_id, surum_no)`` benzersiz, sürüm numarası pozitif tam sayı. Teknik
  yaşam durumu iki değerdir (``OkumaDurumu``): ``basladi`` (içerik yok) ve
  ``tamamlandi`` (içerik var, tamamlanma zamanı var); bu tutarlılık kontrol
  kısıtıyla zorlanır. İçerik JSON metnidir (``json_valid``). Tamamlanan okuma
  sonradan değiştirilmez; yeni okuma gerekiyorsa yeni sürüm açılır
  (``belge_islemleri``). Bu içerik kesin kayıt değildir.
* ``Kaynak`` — provenance çapası: bu veri hangi belgenin hangi okumasından ve
  mümkünse belgenin neresinden geldi? ``belge_id`` ile ``okuma_id`` iki
  bağımsız dış anahtar değildir: ``(okuma_id, belge_id)`` bileşik dış anahtarla
  ``okuma (id, belge_id)`` çiftine bağlıdır; okumanın gerçekten o belgeye ait
  olduğu veritabanında zorlanır. ``konum`` isteğe bağlı, küçük, genel bir JSON
  yapıdır (sayfa, satır, bölge gibi yalnız yer bilgisi); belge içeriğinin
  ikinci kopyası değildir. Kaynak satırı değişmez; yanlışsa yenisi üretilir.
  ``(id, okuma_id)`` benzersiz indeksi (göç 0007) aday nesne / aday kayıt
  satırlarının bileşik dış anahtar hedefidir: bir aday öğe yalnız kendi
  paketinin okumasına ait kaynağa bağlanabilir (``taslak_tablolari``).

Zaman damgaları UTC'dir, saat dilimi bilgisi olmadan saklanır
(``tanim_tablolari.simdi_utc``). Bu modül yalnız şemadır: satır yazmaz,
dosyaya dokunmaz, ``relationship`` içermez (bkz. ``tanim_tablolari``).
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

from defteruc.cekirdek.veritabani import TabloTabani

ARSIV_DOSYASI = "arsiv_dosyasi"
BELGE = "belge"
OKUMA = "okuma"
KAYNAK = "kaynak"

BELGE_TABLOLARI: tuple[str, ...] = (ARSIV_DOSYASI, BELGE, OKUMA, KAYNAK)
"""Belge zinciri tabloları, bağımlılık sırasıyla (göç ve testler için)."""


class OkumaDurumu(StrEnum):
    """Okumanın teknik yaşam durumu; yalnız iki değer. Taslak, bekleme, onay
    gibi durumlar Aşama 4.5 ve sonrasının işidir, buraya girmez."""

    BASLADI = "basladi"
    TAMAMLANDI = "tamamlandi"


SHA256_KOSULU = "length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'"
"""64 karakter, yalnız küçük harf onaltılık (GLOB büyük-küçük harfe duyarlı)."""
GORELI_YOL_KOSULU = "goreli_yol = substr(sha256, 1, 2) || '/' || sha256"
"""Arşiv yolu yalnız içerikten türer; başka bir yol yazılamaz."""
BOYUT_KOSULU = "typeof(boyut) = 'integer' AND boyut > 0"
SURUM_NO_KOSULU = "typeof(surum_no) = 'integer' AND surum_no > 0"
OKUMA_DURUMU_KOSULU = (
    f"(durum = '{OkumaDurumu.BASLADI.value}' AND icerik IS NULL "
    "AND tamamlanma_zamani IS NULL) OR "
    f"(durum = '{OkumaDurumu.TAMAMLANDI.value}' AND icerik IS NOT NULL "
    "AND tamamlanma_zamani IS NOT NULL)"
)
"""Durum ile içerik / tamamlanma zamanı birlikte tutarlı olmak zorunda."""
ICERIK_JSON_KOSULU = "icerik IS NULL OR json_valid(icerik)"
KONUM_JSON_KOSULU = "konum IS NULL OR json_valid(konum)"


class ArsivDosyasi(TabloTabani):
    __tablename__ = ARSIV_DOSYASI

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sha256: Mapped[str] = mapped_column(String, nullable=False)
    """Dosya baytlarının SHA-256 özeti, küçük harf onaltılık; tek fiziksel kimlik."""
    boyut: Mapped[int] = mapped_column(Integer, nullable=False)
    """Bayt sayısı; boş dosya belge olamaz."""
    mime: Mapped[str] = mapped_column(String, nullable=False)
    """İçerik imzasından belirlenen MIME; metadata."""
    kaynak_uzantisi: Mapped[str] = mapped_column(String, nullable=False)
    """Gelen dosya adındaki küçük harfli uzantı (``.pdf``); yoksa boş. Metadata."""
    kaynak_adi: Mapped[str] = mapped_column(String, nullable=False)
    """Gelen dizinindeki dosya adı (dizin yok); metadata."""
    goreli_yol: Mapped[str] = mapped_column(String, nullable=False)
    """Arşiv dizinine göre POSIX yol: ``<ilk iki hex>/<sha256>``; uzantısız."""
    olusturma_zamani: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("sha256"),
        UniqueConstraint("goreli_yol"),
        CheckConstraint(SHA256_KOSULU, name="sha256_bicimi"),
        CheckConstraint(GORELI_YOL_KOSULU, name="goreli_yol_icerikten"),
        CheckConstraint(BOYUT_KOSULU, name="boyut_pozitif_tamsayi"),
    )


class Belge(TabloTabani):
    __tablename__ = BELGE

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    arsiv_dosyasi_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{ARSIV_DOSYASI}.id", ondelete="RESTRICT"),
        nullable=False,
    )
    olusturma_zamani: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (UniqueConstraint("arsiv_dosyasi_id"),)


class Okuma(TabloTabani):
    __tablename__ = OKUMA

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    belge_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{BELGE}.id", ondelete="RESTRICT"), nullable=False
    )
    surum_no: Mapped[int] = mapped_column(Integer, nullable=False)
    """Belge içinde artan pozitif tam sayı; sistem türetir."""
    durum: Mapped[str] = mapped_column(String, nullable=False)
    icerik: Mapped[str | None] = mapped_column(Text)
    """Tamamlanınca yapılandırılmış içerik, kanonik JSON metni; öncesinde NULL."""
    olusturma_zamani: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    tamamlanma_zamani: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint("belge_id", "surum_no"),
        # Kaynağın bileşik dış anahtarı için: (id, belge) çifti hedef olur.
        UniqueConstraint("id", "belge_id"),
        CheckConstraint(SURUM_NO_KOSULU, name="surum_no_pozitif_tamsayi"),
        CheckConstraint(OKUMA_DURUMU_KOSULU, name="durum_icerik_tutarli"),
        CheckConstraint(ICERIK_JSON_KOSULU, name="icerik_json"),
    )


class Kaynak(TabloTabani):
    __tablename__ = KAYNAK

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    belge_id: Mapped[int] = mapped_column(Integer, nullable=False)
    okuma_id: Mapped[int] = mapped_column(Integer, nullable=False)
    konum: Mapped[str | None] = mapped_column(Text)
    """Belge içindeki yer bilgisi, kanonik JSON metni; isteğe bağlı."""
    olusturma_zamani: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["okuma_id", "belge_id"],
            [f"{OKUMA}.id", f"{OKUMA}.belge_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(KONUM_JSON_KOSULU, name="konum_json"),
        Index(None, "belge_id"),
        Index(None, "okuma_id"),
        # Aday nesne / aday kayıt provenance bileşik dış anahtarı için (göç
        # 0007): kaynak satırı okumasıyla birlikte hedef olur.
        Index(None, "id", "okuma_id", unique=True),
    )
