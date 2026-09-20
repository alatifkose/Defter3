"""Karar yaşam döngüsü ve kanonik mükerrerlik kimliği (Aşama 4.6 incelemesi).

2026-09-20 bağımsız incelemesinin şema gerektiren bulguları. ``0008``
düzeltilmez; değişiklikler bu göçle gelir.

* ``karar_talebi``: üçüncü ve terminal durum ``gecersiz`` (paketi iptal edilen
  talep hükümsüz kalır; ``karar`` boş kalır, satır geçmişte durur ama açık
  talep sayılmaz, böylece aynı çift başka bir pakette yeniden
  değerlendirilebilir) ve ona bağlı ``gecersizlik_zamani`` sütunu; durum /
  karar tutarlılığı kısıtı üç dala çıkar. Ayrıca kararı **yalnız kullanıcı**
  verebilir (``karar_aktor_turu`` kısıtı) ve talebi açan aktör türü tanımlı üç
  değerden biri olmak zorundadır.
* ``aday_nesne_cozumlemesi``: ``aktor_turu`` yalnız ``kullanici``.
* ``nesne_birlesimi``: yeni ``kanonik_nesne_id`` sütunu. ``hedef_nesne_id``
  kullanıcının o günkü kararıdır ve değişmez; ``kanonik_nesne_id`` bugünkü
  kanonik nesnedir ve hiçbir zaman kendisi birleşmiş bir nesne olamaz
  (birleşim zinciri kurulmaz, kanonik nesne tek sıçramada bulunur). Ayrıca
  ``aktor_turu`` yalnız ``kullanici`` ve ``kaynak_nesne_id <>
  kanonik_nesne_id``.
* ``denetim_izi``: iki yeni olay — ``karar_talebi_gecersiz_kaldi`` ve
  ``birlesim_yeniden_baglandi``.
* ``aday_nesne``: birincil anahtar ``AUTOINCREMENT`` olur. Aday silinebildiği
  için SQLite en büyük ``rowid``ı yeniden dağıtabiliyordu; denetim izindeki
  ``aday_nesne_id`` dış anahtar olmadığından eski bir iz yeni bir adayı
  gösterebilirdi. ``AUTOINCREMENT`` kimliği bir daha dağıtmaz. Bedeli:
  birincil anahtar kısıtı sütun içinde yazılır ve ``pk_aday_nesne`` adını
  taşıyamaz (SQLite dilbilgisi ``AUTOINCREMENT``a yalnız sütun kısıtında izin
  verir).

SQLite ``ALTER TABLE`` ile kısıt değiştiremez; beş tablo da ``0003``ün açık
SQL kalıbıyla yeniden kurulur (Alembic ``batch`` kipi bu projede ana
tablolarda kullanılamaz, bkz. ``0003``): ``PRAGMA defer_foreign_keys = ON`` →
satırlar kısıtsız taşıma tablosuna → yeni tablo aynı kısıt adlarıyla → eski
tablo düşer → yeni tablo eski adı alır → satırlar geri yazılır → taşıma
tablosu düşer → ``PRAGMA foreign_key_check`` boş olmalı. Bir adım düşerse
transaction tamamen geri alınır.

``nesne_birlesimi`` satırları taşınırken ``kanonik_nesne_id`` başlangıçta
``hedef_nesne_id`` olur ve sonrasında **doğrulanır**: ``0008`` birleşim
zincirine izin verdiğinden eski bir veritabanında zincir bulunabilir. Böyle
bir satır varsa göç sessizce bir kanonik nesne uydurmaz, hata verir; zincirin
hangi nesnede toplanacağı kullanıcı kararlarının konusudur.

Geri alma bütün şema değişikliklerini geri alır ama ``0009``a özgü **veri**
varsa uygulanmaz ve hata verir (``_geri_alinabilir_mi``): ``gecersiz`` durumda
talep, kanonik hedefi değişmiş birleşim ve iki yeni denetim olayı eski şemada
ifade edilemez, sütun düşürülerek sessizce atılamaz. Geri alındıktan sonra
``aday_nesne`` kimlikleri yeniden dağıtılabilir hâle döner; bu bir veri kaybı
değil, ``0008``in bilinen açığıdır.

Sürüm: 0009
Önceki: 0008
Oluşturma: 2026-09-20
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql.elements import conv

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KULLANICI = "kullanici"
AKTOR_TURLERI = "'kullanici', 'ajan', 'sistem'"

ESKI_TALEP_DURUMU_KOSULU = "durum IN ('acik', 'cozuldu')"
YENI_TALEP_DURUMU_KOSULU = "durum IN ('acik', 'cozuldu', 'gecersiz')"
KARAR_KOSULU = "karar IS NULL OR karar IN ('ayni', 'ayri')"
ESKI_DURUM_KARAR_KOSULU = (
    "(durum = 'acik' AND karar IS NULL AND karar_zamani IS NULL "
    "AND karar_aktor_turu IS NULL) OR "
    "(durum = 'cozuldu' AND karar IS NOT NULL AND karar_zamani IS NOT NULL "
    "AND karar_aktor_turu IS NOT NULL)"
)
YENI_DURUM_KARAR_KOSULU = (
    "(durum = 'acik' AND karar IS NULL AND karar_zamani IS NULL "
    "AND karar_aktor_turu IS NULL AND gecersizlik_zamani IS NULL) OR "
    "(durum = 'cozuldu' AND karar IS NOT NULL AND karar_zamani IS NOT NULL "
    "AND karar_aktor_turu IS NOT NULL AND gecersizlik_zamani IS NULL) OR "
    "(durum = 'gecersiz' AND karar IS NULL AND karar_zamani IS NULL "
    "AND karar_aktor_turu IS NULL AND gecersizlik_zamani IS NOT NULL)"
)
TEK_UC_KOSULU = "(aday_nesne_id IS NULL) <> (kaynak_nesne_id IS NULL)"
KESIN_CIFT_SIRASI_KOSULU = "kaynak_nesne_id IS NULL OR kaynak_nesne_id > hedef_nesne_id"
ACAN_AKTOR_KOSULU = f"acan_aktor_turu IN ({AKTOR_TURLERI})"
KARAR_AKTORU_KOSULU = f"karar_aktor_turu IS NULL OR karar_aktor_turu = '{KULLANICI}'"
COZEN_AKTOR_KOSULU = f"aktor_turu = '{KULLANICI}'"

ESKI_OLAYLAR = (
    "'mukerrerlik_sarti_belirlendi', 'mukerrerlik_suphesi_acildi', "
    "'karar_talebi_acildi', 'kullanici_karari_verildi', "
    "'nesne_ayri_kabul_edildi', 'nesne_birlestirildi', "
    "'aday_nesneye_cozumlendi', 'paket_beklemeye_gecti', "
    "'paket_yeniden_calisiyor'"
)
YENI_OLAYLAR = (
    f"{ESKI_OLAYLAR}, 'karar_talebi_gecersiz_kaldi', 'birlesim_yeniden_baglandi'"
)
AKTOR_TURU_KOSULU = f"aktor_turu IN ({AKTOR_TURLERI})"

ACIK_ADAY_INDEKSI = "ix_karar_talebi_acik_aday"
ACIK_KESIN_INDEKSI = "ix_karar_talebi_acik_kesin"

TALEP_SUTUNLARI_0008 = (
    "id, durum, islem_paketi_id, nesne_turu_id, aday_nesne_id, kaynak_nesne_id, "
    "hedef_nesne_id, eslesen_ozellik_tanimi_id, olusturma_zamani, acan_aktor_turu, "
    "acan_aktor_kimligi, karar, karar_zamani, karar_aktor_turu, karar_aktor_kimligi, "
    "gerekce"
)
TALEP_SUTUNLARI_0009 = (
    "id, durum, islem_paketi_id, nesne_turu_id, aday_nesne_id, kaynak_nesne_id, "
    "hedef_nesne_id, eslesen_ozellik_tanimi_id, olusturma_zamani, acan_aktor_turu, "
    "acan_aktor_kimligi, karar, karar_zamani, karar_aktor_turu, karar_aktor_kimligi, "
    "gecersizlik_zamani, gerekce"
)
COZUMLEME_SUTUNLARI = (
    "id, aday_nesne_id, nesne_turu_id, nesne_id, karar_talebi_id, olusturma_zamani, "
    "aktor_turu, aktor_kimligi"
)
BIRLESIM_SUTUNLARI_0008 = (
    "id, kaynak_nesne_id, hedef_nesne_id, nesne_turu_id, karar_talebi_id, "
    "olusturma_zamani, aktor_turu, aktor_kimligi"
)
BIRLESIM_SUTUNLARI_0009 = (
    "id, kaynak_nesne_id, hedef_nesne_id, kanonik_nesne_id, nesne_turu_id, "
    "karar_talebi_id, olusturma_zamani, aktor_turu, aktor_kimligi"
)
IZ_SUTUNLARI = (
    "id, olay, olay_zamani, aktor_turu, aktor_kimligi, islem_paketi_id, "
    "karar_talebi_id, nesne_id, ikincil_nesne_id, aday_nesne_id, ozellik_tanimi_id, "
    "gerekce"
)
ADAY_SUTUNLARI = (
    "id, islem_paketi_id, okuma_id, nesne_turu_id, tanim_surumu_id, kaynak_id, "
    "olusturma_zamani"
)

TALEP_INDEKSLERI: tuple[tuple[str, str], ...] = (
    ("ix_karar_talebi_islem_paketi_id", "islem_paketi_id"),
    ("ix_karar_talebi_durum", "durum"),
    ("ix_karar_talebi_hedef_nesne_id", "hedef_nesne_id"),
)
ADAY_INDEKSLERI: tuple[tuple[str, str], ...] = (
    ("ix_aday_nesne_islem_paketi_id", "islem_paketi_id"),
    ("ix_aday_nesne_nesne_turu_id", "nesne_turu_id"),
    ("ix_aday_nesne_kaynak_id", "kaynak_id"),
)
IZ_INDEKSLERI: tuple[tuple[str, str], ...] = (
    ("ix_denetim_izi_olay", "olay"),
    ("ix_denetim_izi_islem_paketi_id", "islem_paketi_id"),
    ("ix_denetim_izi_karar_talebi_id", "karar_talebi_id"),
    ("ix_denetim_izi_nesne_id", "nesne_id"),
)


# --- ortak yeniden kurma kalıbı (0003) ------------------------------------------------


def _yeniden_kur(
    tablo: str,
    kur: Callable[[str], None],
    *,
    okunan_sutunlar: str,
    yazilan_sutunlar: str,
    secim: str,
) -> None:
    """Tabloyu ``kur`` ile yeniden kurar, satırları taşıma tablosu üzerinden korur.

    ``okunan_sutunlar`` eski tablodan alınanlar, ``yazilan_sutunlar`` yeni
    tablonun hedef sütunları, ``secim`` taşıma tablosundan okunan ifadedir
    (yeni sütun burada türetilir).
    """
    tasima = f"{tablo}_tasima"
    yeni = f"{tablo}_yeni"
    op.execute(sa.text("PRAGMA defer_foreign_keys = ON"))
    op.execute(
        sa.text(f"CREATE TABLE {tasima} AS SELECT {okunan_sutunlar} FROM {tablo}")
    )
    kur(yeni)
    op.execute(sa.text(f"DROP TABLE {tablo}"))
    op.execute(sa.text(f"ALTER TABLE {yeni} RENAME TO {tablo}"))
    op.execute(
        sa.text(
            f"INSERT INTO {tablo} ({yazilan_sutunlar}) SELECT {secim} FROM {tasima}"
        )
    )
    op.execute(sa.text(f"DROP TABLE {tasima}"))


def _dis_anahtarlari_dogrula() -> None:
    ihlaller = op.get_bind().execute(sa.text("PRAGMA foreign_key_check")).all()
    if ihlaller:
        raise RuntimeError(f"göç sonrası dış anahtar ihlali: {len(ihlaller)} satır")


# --- karar_talebi ---------------------------------------------------------------------


def _karar_talebi_kur(ad: str, *, gecersiz_durum: bool) -> None:
    ek_sutunlar: list[sa.Column[Any]] = []
    if gecersiz_durum:
        ek_sutunlar.append(
            sa.Column("gecersizlik_zamani", sa.DateTime(), nullable=True)
        )
    ek_kisitlar: list[sa.schema.SchemaItem] = []
    if gecersiz_durum:
        ek_kisitlar.extend(
            (
                sa.CheckConstraint(
                    ACAN_AKTOR_KOSULU,
                    name=conv("ck_karar_talebi_acan_aktor_turu_gecerli"),
                ),
                sa.CheckConstraint(
                    KARAR_AKTORU_KOSULU,
                    name=conv("ck_karar_talebi_karari_kullanici_verir"),
                ),
            )
        )
    op.create_table(
        ad,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("durum", sa.String(), nullable=False),
        sa.Column("islem_paketi_id", sa.Integer(), nullable=True),
        sa.Column("nesne_turu_id", sa.Integer(), nullable=False),
        sa.Column("aday_nesne_id", sa.Integer(), nullable=True),
        sa.Column("kaynak_nesne_id", sa.Integer(), nullable=True),
        sa.Column("hedef_nesne_id", sa.Integer(), nullable=False),
        sa.Column("eslesen_ozellik_tanimi_id", sa.Integer(), nullable=False),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.Column("acan_aktor_turu", sa.String(), nullable=False),
        sa.Column("acan_aktor_kimligi", sa.String(), nullable=False),
        sa.Column("karar", sa.String(), nullable=True),
        sa.Column("karar_zamani", sa.DateTime(), nullable=True),
        sa.Column("karar_aktor_turu", sa.String(), nullable=True),
        sa.Column("karar_aktor_kimligi", sa.String(), nullable=True),
        *ek_sutunlar,
        sa.Column("gerekce", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=conv("pk_karar_talebi")),
        sa.ForeignKeyConstraint(
            ["aday_nesne_id", "nesne_turu_id"],
            ["aday_nesne.id", "aday_nesne.nesne_turu_id"],
            name=conv("fk_karar_talebi_aday_nesne_id_nesne_turu_id_aday_nesne"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["kaynak_nesne_id", "nesne_turu_id"],
            ["nesne.id", "nesne.nesne_turu_id"],
            name=conv("fk_karar_talebi_kaynak_nesne_id_nesne_turu_id_nesne"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hedef_nesne_id", "nesne_turu_id"],
            ["nesne.id", "nesne.nesne_turu_id"],
            name=conv("fk_karar_talebi_hedef_nesne_id_nesne_turu_id_nesne"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["eslesen_ozellik_tanimi_id", "nesne_turu_id"],
            ["ozellik_tanimi.id", "ozellik_tanimi.nesne_turu_id"],
            name=conv(
                "fk_karar_talebi_eslesen_ozellik_tanimi_id_nesne_turu_id_ozellik_tanimi"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["islem_paketi_id"],
            ["islem_paketi.id"],
            name=conv("fk_karar_talebi_islem_paketi_id_islem_paketi"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            YENI_TALEP_DURUMU_KOSULU if gecersiz_durum else ESKI_TALEP_DURUMU_KOSULU,
            name=conv("ck_karar_talebi_durum_gecerli"),
        ),
        sa.CheckConstraint(KARAR_KOSULU, name=conv("ck_karar_talebi_karar_gecerli")),
        sa.CheckConstraint(
            YENI_DURUM_KARAR_KOSULU if gecersiz_durum else ESKI_DURUM_KARAR_KOSULU,
            name=conv("ck_karar_talebi_durum_karar_tutarli"),
        ),
        sa.CheckConstraint(TEK_UC_KOSULU, name=conv("ck_karar_talebi_tek_karsi_uc")),
        sa.CheckConstraint(
            KESIN_CIFT_SIRASI_KOSULU, name=conv("ck_karar_talebi_kesin_cift_sirasi")
        ),
        *ek_kisitlar,
    )


def _karar_talebi_indeksleri() -> None:
    for ad, sutun in TALEP_INDEKSLERI:
        op.create_index(ad, "karar_talebi", [sutun])
    op.create_index(
        ACIK_ADAY_INDEKSI,
        "karar_talebi",
        ["aday_nesne_id", "hedef_nesne_id"],
        unique=True,
        sqlite_where=sa.text("durum = 'acik' AND aday_nesne_id IS NOT NULL"),
    )
    op.create_index(
        ACIK_KESIN_INDEKSI,
        "karar_talebi",
        ["kaynak_nesne_id", "hedef_nesne_id"],
        unique=True,
        sqlite_where=sa.text("durum = 'acik' AND kaynak_nesne_id IS NOT NULL"),
    )


# --- aday_nesne_cozumlemesi -----------------------------------------------------------


def _cozumleme_kur(ad: str, *, aktor_kisiti: bool) -> None:
    ek_kisitlar: list[sa.schema.SchemaItem] = []
    if aktor_kisiti:
        ek_kisitlar.append(
            sa.CheckConstraint(
                COZEN_AKTOR_KOSULU,
                name=conv("ck_aday_nesne_cozumlemesi_karari_kullanici_verir"),
            )
        )
    op.create_table(
        ad,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("aday_nesne_id", sa.Integer(), nullable=False),
        sa.Column("nesne_turu_id", sa.Integer(), nullable=False),
        sa.Column("nesne_id", sa.Integer(), nullable=False),
        sa.Column("karar_talebi_id", sa.Integer(), nullable=False),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.Column("aktor_turu", sa.String(), nullable=False),
        sa.Column("aktor_kimligi", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("pk_aday_nesne_cozumlemesi")),
        sa.ForeignKeyConstraint(
            ["aday_nesne_id", "nesne_turu_id"],
            ["aday_nesne.id", "aday_nesne.nesne_turu_id"],
            name=conv(
                "fk_aday_nesne_cozumlemesi_aday_nesne_id_nesne_turu_id_aday_nesne"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["nesne_id", "nesne_turu_id"],
            ["nesne.id", "nesne.nesne_turu_id"],
            name=conv("fk_aday_nesne_cozumlemesi_nesne_id_nesne_turu_id_nesne"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["karar_talebi_id"],
            ["karar_talebi.id"],
            name=conv("fk_aday_nesne_cozumlemesi_karar_talebi_id_karar_talebi"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "aday_nesne_id", name=conv("uq_aday_nesne_cozumlemesi_aday_nesne_id")
        ),
        sa.UniqueConstraint(
            "karar_talebi_id", name=conv("uq_aday_nesne_cozumlemesi_karar_talebi_id")
        ),
        *ek_kisitlar,
    )


# --- nesne_birlesimi ------------------------------------------------------------------


def _birlesim_kur(ad: str, *, kanonik: bool) -> None:
    ek_sutunlar: list[sa.Column[Any]] = []
    ek_kisitlar: list[sa.schema.SchemaItem] = []
    if kanonik:
        ek_sutunlar.append(sa.Column("kanonik_nesne_id", sa.Integer(), nullable=False))
        ek_kisitlar.extend(
            (
                sa.ForeignKeyConstraint(
                    ["kanonik_nesne_id", "nesne_turu_id"],
                    ["nesne.id", "nesne.nesne_turu_id"],
                    name=conv(
                        "fk_nesne_birlesimi_kanonik_nesne_id_nesne_turu_id_nesne"
                    ),
                    ondelete="RESTRICT",
                ),
                sa.CheckConstraint(
                    "kaynak_nesne_id <> kanonik_nesne_id",
                    name=conv("ck_nesne_birlesimi_kaynak_kanonikten_farkli"),
                ),
                sa.CheckConstraint(
                    COZEN_AKTOR_KOSULU,
                    name=conv("ck_nesne_birlesimi_karari_kullanici_verir"),
                ),
            )
        )
    op.create_table(
        ad,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kaynak_nesne_id", sa.Integer(), nullable=False),
        sa.Column("hedef_nesne_id", sa.Integer(), nullable=False),
        *ek_sutunlar,
        sa.Column("nesne_turu_id", sa.Integer(), nullable=False),
        sa.Column("karar_talebi_id", sa.Integer(), nullable=False),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.Column("aktor_turu", sa.String(), nullable=False),
        sa.Column("aktor_kimligi", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("pk_nesne_birlesimi")),
        sa.ForeignKeyConstraint(
            ["kaynak_nesne_id", "nesne_turu_id"],
            ["nesne.id", "nesne.nesne_turu_id"],
            name=conv("fk_nesne_birlesimi_kaynak_nesne_id_nesne_turu_id_nesne"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hedef_nesne_id", "nesne_turu_id"],
            ["nesne.id", "nesne.nesne_turu_id"],
            name=conv("fk_nesne_birlesimi_hedef_nesne_id_nesne_turu_id_nesne"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["karar_talebi_id"],
            ["karar_talebi.id"],
            name=conv("fk_nesne_birlesimi_karar_talebi_id_karar_talebi"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "kaynak_nesne_id", name=conv("uq_nesne_birlesimi_kaynak_nesne_id")
        ),
        sa.UniqueConstraint(
            "karar_talebi_id", name=conv("uq_nesne_birlesimi_karar_talebi_id")
        ),
        sa.CheckConstraint(
            "kaynak_nesne_id <> hedef_nesne_id",
            name=conv("ck_nesne_birlesimi_kaynak_hedeften_farkli"),
        ),
        *ek_kisitlar,
    )


def _zincir_yok_mu() -> None:
    """Hiçbir birleşim satırı, kendisi birleşmiş bir nesneyi kanonik göstermemeli."""
    zincir = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM nesne_birlesimi WHERE kanonik_nesne_id IN "
                "(SELECT kaynak_nesne_id FROM nesne_birlesimi)"
            )
        )
        .scalar_one()
    )
    if zincir:
        raise RuntimeError(
            f"göç 0009: {zincir} birleşim satırı kendisi birleşmiş bir nesneyi "
            "kanonik gösteriyor (0008 birleşim zincirine izin veriyordu). "
            "Zincirin hangi nesnede toplanacağı bir kullanıcı kararıdır; göç "
            "kanonik nesne uydurmaz."
        )


# --- denetim_izi ----------------------------------------------------------------------


def _iz_kur(ad: str, *, yeni_olaylar: bool) -> None:
    op.create_table(
        ad,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("olay", sa.String(), nullable=False),
        sa.Column("olay_zamani", sa.DateTime(), nullable=False),
        sa.Column("aktor_turu", sa.String(), nullable=False),
        sa.Column("aktor_kimligi", sa.String(), nullable=False),
        sa.Column("islem_paketi_id", sa.Integer(), nullable=True),
        sa.Column("karar_talebi_id", sa.Integer(), nullable=True),
        sa.Column("nesne_id", sa.Integer(), nullable=True),
        sa.Column("ikincil_nesne_id", sa.Integer(), nullable=True),
        sa.Column("aday_nesne_id", sa.Integer(), nullable=True),
        sa.Column("ozellik_tanimi_id", sa.Integer(), nullable=True),
        sa.Column("gerekce", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=conv("pk_denetim_izi")),
        sa.ForeignKeyConstraint(
            ["islem_paketi_id"],
            ["islem_paketi.id"],
            name=conv("fk_denetim_izi_islem_paketi_id_islem_paketi"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["karar_talebi_id"],
            ["karar_talebi.id"],
            name=conv("fk_denetim_izi_karar_talebi_id_karar_talebi"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["nesne_id"],
            ["nesne.id"],
            name=conv("fk_denetim_izi_nesne_id_nesne"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ikincil_nesne_id"],
            ["nesne.id"],
            name=conv("fk_denetim_izi_ikincil_nesne_id_nesne"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ozellik_tanimi_id"],
            ["ozellik_tanimi.id"],
            name=conv("fk_denetim_izi_ozellik_tanimi_id_ozellik_tanimi"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"olay IN ({YENI_OLAYLAR if yeni_olaylar else ESKI_OLAYLAR})",
            name=conv("ck_denetim_izi_olay_gecerli"),
        ),
        sa.CheckConstraint(
            AKTOR_TURU_KOSULU, name=conv("ck_denetim_izi_aktor_turu_gecerli")
        ),
        sa.CheckConstraint(
            "length(aktor_kimligi) > 0", name=conv("ck_denetim_izi_aktor_kimligi_dolu")
        ),
    )


# --- aday_nesne -----------------------------------------------------------------------


def _aday_nesne_kur(ad: str, *, otomatik_artan: bool) -> None:
    ek_ayarlar: dict[str, bool] = (
        {"sqlite_autoincrement": True} if otomatik_artan else {}
    )
    op.create_table(
        ad,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("islem_paketi_id", sa.Integer(), nullable=False),
        sa.Column("okuma_id", sa.Integer(), nullable=False),
        sa.Column("nesne_turu_id", sa.Integer(), nullable=False),
        sa.Column("tanim_surumu_id", sa.Integer(), nullable=False),
        sa.Column("kaynak_id", sa.Integer(), nullable=True),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("pk_aday_nesne")),
        sa.ForeignKeyConstraint(
            ["islem_paketi_id", "okuma_id"],
            ["islem_paketi.id", "islem_paketi.okuma_id"],
            name=conv("fk_aday_nesne_islem_paketi_id_okuma_id_islem_paketi"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["nesne_turu_id", "tanim_surumu_id"],
            ["nesne_turu.id", "nesne_turu.tanim_surumu_id"],
            name=conv("fk_aday_nesne_nesne_turu_id_tanim_surumu_id_nesne_turu"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["kaynak_id", "okuma_id"],
            ["kaynak.id", "kaynak.okuma_id"],
            name=conv("fk_aday_nesne_kaynak_id_okuma_id_kaynak"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "id", "islem_paketi_id", name=conv("uq_aday_nesne_id_islem_paketi_id")
        ),
        sa.UniqueConstraint(
            "id", "nesne_turu_id", name=conv("uq_aday_nesne_id_nesne_turu_id")
        ),
        sa.UniqueConstraint(
            "id",
            "islem_paketi_id",
            "nesne_turu_id",
            "tanim_surumu_id",
            name=conv("uq_aday_nesne_id_islem_paketi_id_nesne_turu_id_tanim_surumu_id"),
        ),
        **ek_ayarlar,
    )


# --- göç ------------------------------------------------------------------------------


def _gec(*, ileri: bool) -> None:
    _yeniden_kur(
        "karar_talebi",
        lambda ad: _karar_talebi_kur(ad, gecersiz_durum=ileri),
        okunan_sutunlar=TALEP_SUTUNLARI_0008 if ileri else TALEP_SUTUNLARI_0009,
        yazilan_sutunlar=TALEP_SUTUNLARI_0009 if ileri else TALEP_SUTUNLARI_0008,
        secim=(
            f"{TALEP_SUTUNLARI_0008.replace(', gerekce', '')}, NULL, gerekce"
            if ileri
            else TALEP_SUTUNLARI_0008
        ),
    )
    _karar_talebi_indeksleri()
    _yeniden_kur(
        "aday_nesne_cozumlemesi",
        lambda ad: _cozumleme_kur(ad, aktor_kisiti=ileri),
        okunan_sutunlar=COZUMLEME_SUTUNLARI,
        yazilan_sutunlar=COZUMLEME_SUTUNLARI,
        secim=COZUMLEME_SUTUNLARI,
    )
    op.create_index(
        "ix_aday_nesne_cozumlemesi_nesne_id", "aday_nesne_cozumlemesi", ["nesne_id"]
    )
    _yeniden_kur(
        "nesne_birlesimi",
        lambda ad: _birlesim_kur(ad, kanonik=ileri),
        okunan_sutunlar=BIRLESIM_SUTUNLARI_0008 if ileri else BIRLESIM_SUTUNLARI_0009,
        yazilan_sutunlar=BIRLESIM_SUTUNLARI_0009 if ileri else BIRLESIM_SUTUNLARI_0008,
        secim=(
            "id, kaynak_nesne_id, hedef_nesne_id, hedef_nesne_id, nesne_turu_id, "
            "karar_talebi_id, olusturma_zamani, aktor_turu, aktor_kimligi"
            if ileri
            else BIRLESIM_SUTUNLARI_0008
        ),
    )
    op.create_index(
        "ix_nesne_birlesimi_hedef_nesne_id", "nesne_birlesimi", ["hedef_nesne_id"]
    )
    if ileri:
        op.create_index(
            "ix_nesne_birlesimi_kanonik_nesne_id",
            "nesne_birlesimi",
            ["kanonik_nesne_id"],
        )
        _zincir_yok_mu()
    _yeniden_kur(
        "denetim_izi",
        lambda ad: _iz_kur(ad, yeni_olaylar=ileri),
        okunan_sutunlar=IZ_SUTUNLARI,
        yazilan_sutunlar=IZ_SUTUNLARI,
        secim=IZ_SUTUNLARI,
    )
    for ad, sutun in IZ_INDEKSLERI:
        op.create_index(ad, "denetim_izi", [sutun])
    _yeniden_kur(
        "aday_nesne",
        lambda ad: _aday_nesne_kur(ad, otomatik_artan=ileri),
        okunan_sutunlar=ADAY_SUTUNLARI,
        yazilan_sutunlar=ADAY_SUTUNLARI,
        secim=ADAY_SUTUNLARI,
    )
    for ad, sutun in ADAY_INDEKSLERI:
        op.create_index(ad, "aday_nesne", [sutun])
    _dis_anahtarlari_dogrula()


def _geri_alinabilir_mi() -> None:
    """0009'a özgü veri varsa geri alma sessizce çalışmaz.

    Geri alınan şema ne ``gecersiz`` talebi ne de ``hedef``ten farklı bir
    kanonik nesneyi ifade edebilir; ikisi de kullanıcı kararlarının sonucudur
    ve sütun düşürülerek sessizce atılamaz. Yeni denetim olayları da eski
    kontrol kısıtına sığmaz.
    """
    baglanti = op.get_bind()
    engeller: list[str] = []
    sayimlar = (
        (
            "geçersiz karar talebi",
            "SELECT count(*) FROM karar_talebi WHERE durum = 'gecersiz'",
        ),
        (
            "kanonik hedefi değişmiş birleşim",
            "SELECT count(*) FROM nesne_birlesimi "
            "WHERE kanonik_nesne_id <> hedef_nesne_id",
        ),
        (
            "0009 denetim olayı",
            "SELECT count(*) FROM denetim_izi WHERE olay IN "
            "('karar_talebi_gecersiz_kaldi', 'birlesim_yeniden_baglandi')",
        ),
    )
    for ad, sorgu in sayimlar:
        adet = baglanti.execute(sa.text(sorgu)).scalar_one()
        if adet:
            engeller.append(f"{adet} {ad}")
    if engeller:
        raise RuntimeError(
            "göç 0009 geri alınamaz: " + ", ".join(engeller) + "; bu satırlar "
            "eski şemada ifade edilemez ve veri sessizce silinmez."
        )


def upgrade() -> None:
    _gec(ileri=True)


def downgrade() -> None:
    _geri_alinabilir_mi()
    _gec(ileri=False)
