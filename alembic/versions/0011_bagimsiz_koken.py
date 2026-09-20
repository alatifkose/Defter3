"""Karar talebinin bağımsız kökeni: paket iptali bağımsız soruyu düşürmesin.

2026-09-20 üçüncü inceleme turu, bulgu 1. Paketten bağımsız doğan bir soru
(``islem_paketi_id IS NULL``) bugüne kadar iptalden korunuyordu, ama bir
birleşmeden sonra aynı soru kanonik uçlarla yeniden sorulurken hâlihazırda bir
pakete ait açık soruyla birleşebiliyordu; o anda bağımsız köken kayboluyor ve
o paket iptal edilince hâlâ geçerli olan soru cevapsız düşüyordu.

Köken artık ayrı ve kalıcı bir alanda durur: ``karar_talebi.bagimsiz_koken``.
Tarihsel açılış paketi (``islem_paketi_id``) **değiştirilmez**; devredilen
yalnız "bu soruyu soran tek şey bir paket değil" bilgisidir. Kontrol kısıtı
``islem_paketi_id IS NULL`` iken alanın ``1`` olmasını zorlar; tersi serbesttir
çünkü paketli doğmuş bir soru bağımsız bir sorudan köken devralabilir.

Veri aktarımı: mevcut satırlarda ``bagimsiz_koken`` değeri
``islem_paketi_id IS NULL`` koşulundan türetilir, yani bugünkü davranış birebir
korunur.

SQLite ``ALTER TABLE`` ile kısıt ekleyemez ve ``NOT NULL`` sütunu kısıtla
birlikte koyamaz; ``karar_talebi`` ``0003``ün açık SQL kalıbıyla yeniden
kurulur (Alembic ``batch`` kipi bu projede ana tablolarda kullanılamaz, bkz.
``0003``). Tablonun çocukları (``aday_nesne_cozumlemesi``, ``nesne_birlesimi``,
``denetim_izi``, ``karar_talebi_paketi``) durduğu için ``PRAGMA
defer_foreign_keys = ON`` ile taşıma tablosu kalıbı kullanılır.

Geri alma sütunu düşürür. Devralınmış köken (``bagimsiz_koken = 1`` olduğu
hâlde ``islem_paketi_id`` dolu) eski şemada ifade edilemez; böyle satır varsa
geri alma uygulanmaz ve hata verir, veri sessizce silinmez.

Sürüm: 0011
Önceki: 0010
Oluşturma: 2026-09-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql.elements import conv

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLO = "karar_talebi"
TASIMA_TABLOSU = "karar_talebi_tasima"
YENI_TABLO = "karar_talebi_yeni"

AKTOR_TURLERI = "'kullanici', 'ajan', 'sistem'"
TALEP_DURUMU_KOSULU = "durum IN ('acik', 'cozuldu', 'gecersiz')"
KARAR_KOSULU = "karar IS NULL OR karar IN ('ayni', 'ayri')"
DURUM_KARAR_KOSULU = (
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
KARAR_AKTORU_KOSULU = "karar_aktor_turu IS NULL OR karar_aktor_turu = 'kullanici'"
BAGIMSIZ_KOKEN_KOSULU = (
    "bagimsiz_koken IN (0, 1) AND (islem_paketi_id IS NOT NULL OR bagimsiz_koken = 1)"
)

SUTUNLAR_0010 = (
    "id, durum, islem_paketi_id, nesne_turu_id, aday_nesne_id, kaynak_nesne_id, "
    "hedef_nesne_id, eslesen_ozellik_tanimi_id, olusturma_zamani, acan_aktor_turu, "
    "acan_aktor_kimligi, karar, karar_zamani, karar_aktor_turu, karar_aktor_kimligi, "
    "gecersizlik_zamani, gerekce"
)
SUTUNLAR_0011 = SUTUNLAR_0010.replace(
    "gecersizlik_zamani, gerekce", "gecersizlik_zamani, bagimsiz_koken, gerekce"
)
KOKEN_TURETMESI = SUTUNLAR_0010.replace(
    "gecersizlik_zamani, gerekce",
    "gecersizlik_zamani, CASE WHEN islem_paketi_id IS NULL THEN 1 ELSE 0 END, gerekce",
)

ACIK_ADAY_INDEKSI = "ix_karar_talebi_acik_aday"
ACIK_KESIN_INDEKSI = "ix_karar_talebi_acik_kesin"
INDEKSLER: tuple[tuple[str, str], ...] = (
    ("ix_karar_talebi_islem_paketi_id", "islem_paketi_id"),
    ("ix_karar_talebi_durum", "durum"),
    ("ix_karar_talebi_hedef_nesne_id", "hedef_nesne_id"),
)


def _kur(ad: str, *, koken_sutunu: bool) -> None:
    """``karar_talebi``yi ``0010`` ya da ``0011`` şemasıyla kurar."""
    # ``0009`` bu iki kısıtı ``create_table`` çağrısından **önce** kuruyordu;
    # SQLAlchemy kontrol kısıtlarını oluşturma sırasına göre yazdığı için aynı
    # sıra burada da korunur, yoksa geri alınan şema ``0009``unkinden ayrışır.
    onceki_kisitlar: list[sa.schema.SchemaItem] = [
        sa.CheckConstraint(
            ACAN_AKTOR_KOSULU, name=conv("ck_karar_talebi_acan_aktor_turu_gecerli")
        ),
        sa.CheckConstraint(
            KARAR_AKTORU_KOSULU, name=conv("ck_karar_talebi_karari_kullanici_verir")
        ),
    ]
    ek_sutunlar: list[sa.Column[bool]] = []
    if koken_sutunu:
        ek_sutunlar.append(
            sa.Column(
                "bagimsiz_koken",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        onceki_kisitlar.append(
            sa.CheckConstraint(
                BAGIMSIZ_KOKEN_KOSULU,
                name=conv("ck_karar_talebi_bagimsiz_koken_tutarli"),
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
        sa.Column("gecersizlik_zamani", sa.DateTime(), nullable=True),
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
            TALEP_DURUMU_KOSULU, name=conv("ck_karar_talebi_durum_gecerli")
        ),
        sa.CheckConstraint(KARAR_KOSULU, name=conv("ck_karar_talebi_karar_gecerli")),
        sa.CheckConstraint(
            DURUM_KARAR_KOSULU, name=conv("ck_karar_talebi_durum_karar_tutarli")
        ),
        sa.CheckConstraint(TEK_UC_KOSULU, name=conv("ck_karar_talebi_tek_karsi_uc")),
        sa.CheckConstraint(
            KESIN_CIFT_SIRASI_KOSULU, name=conv("ck_karar_talebi_kesin_cift_sirasi")
        ),
        *onceki_kisitlar,
    )


def _indeksleri_kur() -> None:
    for ad, sutun in INDEKSLER:
        op.create_index(ad, TABLO, [sutun])
    op.create_index(
        ACIK_ADAY_INDEKSI,
        TABLO,
        ["aday_nesne_id", "hedef_nesne_id"],
        unique=True,
        sqlite_where=sa.text("durum = 'acik' AND aday_nesne_id IS NOT NULL"),
    )
    op.create_index(
        ACIK_KESIN_INDEKSI,
        TABLO,
        ["kaynak_nesne_id", "hedef_nesne_id"],
        unique=True,
        sqlite_where=sa.text("durum = 'acik' AND kaynak_nesne_id IS NOT NULL"),
    )


def _yeniden_kur(*, koken_sutunu: bool, okunan: str, yazilan: str, secim: str) -> None:
    op.execute(sa.text("PRAGMA defer_foreign_keys = ON"))
    op.execute(
        sa.text(f"CREATE TABLE {TASIMA_TABLOSU} AS SELECT {okunan} FROM {TABLO}")
    )
    _kur(YENI_TABLO, koken_sutunu=koken_sutunu)
    op.execute(sa.text(f"DROP TABLE {TABLO}"))
    op.execute(sa.text(f"ALTER TABLE {YENI_TABLO} RENAME TO {TABLO}"))
    op.execute(
        sa.text(f"INSERT INTO {TABLO} ({yazilan}) SELECT {secim} FROM {TASIMA_TABLOSU}")
    )
    op.execute(sa.text(f"DROP TABLE {TASIMA_TABLOSU}"))
    _indeksleri_kur()
    ihlaller = op.get_bind().execute(sa.text("PRAGMA foreign_key_check")).all()
    if ihlaller:
        raise RuntimeError(f"göç sonrası dış anahtar ihlali: {len(ihlaller)} satır")


def upgrade() -> None:
    _yeniden_kur(
        koken_sutunu=True,
        okunan=SUTUNLAR_0010,
        yazilan=SUTUNLAR_0011,
        secim=KOKEN_TURETMESI,
    )


def downgrade() -> None:
    devralinmis = (
        op.get_bind()
        .execute(
            sa.text(
                f"SELECT count(*) FROM {TABLO} "
                "WHERE bagimsiz_koken = 1 AND islem_paketi_id IS NOT NULL"
            )
        )
        .scalar_one()
    )
    if devralinmis:
        raise RuntimeError(
            f"göç 0011 geri alınamaz: {devralinmis} karar talebi bağımsız kökeni "
            "bir paketten devralmış; bu bilgi eski şemada ifade edilemez ve "
            "sessizce silinmez."
        )
    _yeniden_kur(
        koken_sutunu=False,
        okunan=SUTUNLAR_0011,
        yazilan=SUTUNLAR_0010,
        secim=SUTUNLAR_0010,
    )
