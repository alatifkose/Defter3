"""Nesne motoru (Aşama 4.3): nesne tabloları, hiyerarşi kuralı, özellik türü, kilit.

Değişiklikler:

* ``tanim_surumu``: ``kilitli`` sütunu (BOOLEAN, varsayılan 0, ikili kontrol
  kısıtı). ``ALTER TABLE ADD COLUMN`` ile; tablo yeniden kurulmaz.
* ``ozellik_tanimi``: ``deger_turu`` (metin / tam_sayi / mantiksal / ondalik,
  kontrol kısıtı) ve ``zorunlu`` (ikili) sütunları, nesne özelliğinin bileşik
  dış anahtarı için ``(id, nesne_turu_id)`` benzersizliği. SQLite ``ALTER
  TABLE`` ile benzersizlik ekleyemediğinden tablo açık SQL adımlarıyla
  yeniden kurulur; 0003'te ona bağlı çocuk tablo olmadığından FK erteleme
  gerekmez. Var olan satırlar (varsa) metin / isteğe bağlı sayılır.
* ``iliski_tanimi``: nesne ilişkisinin bileşik dış anahtarı için ``(id,
  tanim_surumu_id, kaynak_nesne_turu_id, hedef_nesne_turu_id)`` benzersiz
  indeksi.
* Yeni tablolar: ``hiyerarsi_kurali``, ``nesne``, ``nesne_ozelligi``,
  ``nesne_iliskisi`` (şema ``nesne_tablolari`` / ``tanim_tablolari`` ile
  birebir; testte ORM metadata'sıyla karşılaştırılır).

Geri alma tersini yapar; ``kilitli`` sütunu ``ALTER TABLE DROP COLUMN`` ile
düşer (SQLite ≥ 3.35). Satır yazılmaz.

Sürüm: 0004
Önceki: 0003
Oluşturma: 2026-09-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.schema import SchemaItem
from sqlalchemy.sql.elements import conv

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEGER_TURLERI = "'metin', 'tam_sayi', 'mantiksal', 'ondalik'"
YASAM_DURUMLARI = "'etkin', 'kapali'"
OZELLIK_ESKI_SUTUNLAR = "id, nesne_turu_id, kod, gosterim_adi, aciklama"
ILISKI_INDEKSI = (
    "ix_iliski_tanimi_id_tanim_surumu_id_kaynak_nesne_turu_id_hedef_nesne_turu_id"
)


def _ozellik_tanimi_kur(ad: str, yeni_sutunlar: bool) -> None:
    """``ozellik_tanimi`` şeması; ``yeni_sutunlar`` 0004 (True) ya da 0003 (False)."""
    ek_sutunlar: list[SchemaItem] = []
    ek_kisitlar: list[SchemaItem] = []
    if yeni_sutunlar:
        ek_sutunlar = [
            sa.Column(
                "deger_turu", sa.String(), nullable=False, server_default="metin"
            ),
            sa.Column(
                "zorunlu", sa.Boolean(), nullable=False, server_default=sa.text("0")
            ),
        ]
        ek_kisitlar = [
            sa.UniqueConstraint(
                "id", "nesne_turu_id", name=conv("uq_ozellik_tanimi_id_nesne_turu_id")
            ),
            sa.CheckConstraint(
                f"deger_turu IN ({DEGER_TURLERI})",
                name=conv("ck_ozellik_tanimi_deger_turu_gecerli"),
            ),
            sa.CheckConstraint(
                "zorunlu IN (0, 1)", name=conv("ck_ozellik_tanimi_zorunlu_ikili")
            ),
        ]
    op.create_table(
        ad,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nesne_turu_id", sa.Integer(), nullable=False),
        sa.Column("kod", sa.String(), nullable=False),
        sa.Column("gosterim_adi", sa.String(), nullable=False),
        sa.Column("aciklama", sa.Text(), nullable=True),
        *ek_sutunlar,
        sa.PrimaryKeyConstraint("id", name=conv("pk_ozellik_tanimi")),
        sa.ForeignKeyConstraint(
            ["nesne_turu_id"],
            ["nesne_turu.id"],
            name=conv("fk_ozellik_tanimi_nesne_turu_id_nesne_turu"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "nesne_turu_id", "kod", name=conv("uq_ozellik_tanimi_nesne_turu_id_kod")
        ),
        *ek_kisitlar,
    )


def _ozellik_tanimini_yeniden_kur(yeni_sutunlar: bool) -> None:
    """Tabloyu yeni ya da eski şemayla yeniden kurar; satırları taşır."""
    _ozellik_tanimi_kur("ozellik_tanimi_yeni", yeni_sutunlar)
    op.execute(
        sa.text(
            f"INSERT INTO ozellik_tanimi_yeni ({OZELLIK_ESKI_SUTUNLAR}) "
            f"SELECT {OZELLIK_ESKI_SUTUNLAR} FROM ozellik_tanimi"
        )
    )
    op.execute(sa.text("DROP TABLE ozellik_tanimi"))
    op.execute(sa.text("ALTER TABLE ozellik_tanimi_yeni RENAME TO ozellik_tanimi"))


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE tanim_surumu ADD COLUMN kilitli BOOLEAN NOT NULL DEFAULT 0 "
            "CONSTRAINT ck_tanim_surumu_kilitli_ikili CHECK (kilitli IN (0, 1))"
        )
    )
    _ozellik_tanimini_yeniden_kur(yeni_sutunlar=True)
    op.create_index(
        ILISKI_INDEKSI,
        "iliski_tanimi",
        ["id", "tanim_surumu_id", "kaynak_nesne_turu_id", "hedef_nesne_turu_id"],
        unique=True,
    )
    op.create_table(
        "hiyerarsi_kurali",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("iliski_tanimi_id", sa.Integer(), nullable=False),
        sa.Column("en_az_ust", sa.Integer(), nullable=False),
        sa.Column("en_cok_ust", sa.Integer(), nullable=True),
        sa.Column("ust_yasam_durumu", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=conv("pk_hiyerarsi_kurali")),
        sa.ForeignKeyConstraint(
            ["iliski_tanimi_id"],
            ["iliski_tanimi.id"],
            name=conv("fk_hiyerarsi_kurali_iliski_tanimi_id_iliski_tanimi"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "iliski_tanimi_id", name=conv("uq_hiyerarsi_kurali_iliski_tanimi_id")
        ),
        sa.CheckConstraint(
            "typeof(en_az_ust) = 'integer' AND en_az_ust >= 0",
            name=conv("ck_hiyerarsi_kurali_en_az_ust_dogal"),
        ),
        sa.CheckConstraint(
            "en_cok_ust IS NULL OR (typeof(en_cok_ust) = 'integer' "
            "AND en_cok_ust >= 1 AND en_cok_ust >= en_az_ust)",
            name=conv("ck_hiyerarsi_kurali_en_cok_ust_tutarli"),
        ),
        sa.CheckConstraint(
            f"ust_yasam_durumu IS NULL OR ust_yasam_durumu IN ({YASAM_DURUMLARI})",
            name=conv("ck_hiyerarsi_kurali_ust_yasam_durumu_gecerli"),
        ),
    )
    op.create_table(
        "nesne",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nesne_turu_id", sa.Integer(), nullable=False),
        sa.Column("tanim_surumu_id", sa.Integer(), nullable=False),
        sa.Column("yasam_durumu", sa.String(), nullable=False),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("pk_nesne")),
        sa.ForeignKeyConstraint(
            ["nesne_turu_id", "tanim_surumu_id"],
            ["nesne_turu.id", "nesne_turu.tanim_surumu_id"],
            name=conv("fk_nesne_nesne_turu_id_tanim_surumu_id_nesne_turu"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "id", "nesne_turu_id", name=conv("uq_nesne_id_nesne_turu_id")
        ),
        sa.UniqueConstraint(
            "id",
            "nesne_turu_id",
            "tanim_surumu_id",
            name=conv("uq_nesne_id_nesne_turu_id_tanim_surumu_id"),
        ),
        sa.CheckConstraint(
            f"yasam_durumu IN ({YASAM_DURUMLARI})",
            name=conv("ck_nesne_yasam_durumu_gecerli"),
        ),
    )
    op.create_index("ix_nesne_nesne_turu_id", "nesne", ["nesne_turu_id"])
    op.create_index("ix_nesne_tanim_surumu_id", "nesne", ["tanim_surumu_id"])
    op.create_table(
        "nesne_ozelligi",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nesne_id", sa.Integer(), nullable=False),
        sa.Column("nesne_turu_id", sa.Integer(), nullable=False),
        sa.Column("ozellik_tanimi_id", sa.Integer(), nullable=False),
        sa.Column("deger", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("pk_nesne_ozelligi")),
        sa.ForeignKeyConstraint(
            ["nesne_id", "nesne_turu_id"],
            ["nesne.id", "nesne.nesne_turu_id"],
            name=conv("fk_nesne_ozelligi_nesne_id_nesne_turu_id_nesne"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ozellik_tanimi_id", "nesne_turu_id"],
            ["ozellik_tanimi.id", "ozellik_tanimi.nesne_turu_id"],
            name=conv(
                "fk_nesne_ozelligi_ozellik_tanimi_id_nesne_turu_id_ozellik_tanimi"
            ),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "nesne_id",
            "ozellik_tanimi_id",
            name=conv("uq_nesne_ozelligi_nesne_id_ozellik_tanimi_id"),
        ),
    )
    op.create_index(
        "ix_nesne_ozelligi_ozellik_tanimi_id", "nesne_ozelligi", ["ozellik_tanimi_id"]
    )
    op.create_table(
        "nesne_iliskisi",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("iliski_tanimi_id", sa.Integer(), nullable=False),
        sa.Column("tanim_surumu_id", sa.Integer(), nullable=False),
        sa.Column("kaynak_nesne_turu_id", sa.Integer(), nullable=False),
        sa.Column("hedef_nesne_turu_id", sa.Integer(), nullable=False),
        sa.Column("kaynak_nesne_id", sa.Integer(), nullable=False),
        sa.Column("hedef_nesne_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("pk_nesne_iliskisi")),
        sa.ForeignKeyConstraint(
            [
                "iliski_tanimi_id",
                "tanim_surumu_id",
                "kaynak_nesne_turu_id",
                "hedef_nesne_turu_id",
            ],
            [
                "iliski_tanimi.id",
                "iliski_tanimi.tanim_surumu_id",
                "iliski_tanimi.kaynak_nesne_turu_id",
                "iliski_tanimi.hedef_nesne_turu_id",
            ],
            name=conv(
                "fk_nesne_iliskisi_iliski_tanimi_id_tanim_surumu_id_"
                "kaynak_nesne_turu_id_hedef_nesne_turu_id_iliski_tanimi"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["kaynak_nesne_id", "kaynak_nesne_turu_id", "tanim_surumu_id"],
            ["nesne.id", "nesne.nesne_turu_id", "nesne.tanim_surumu_id"],
            name=conv(
                "fk_nesne_iliskisi_kaynak_nesne_id_kaynak_nesne_turu_id_"
                "tanim_surumu_id_nesne"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hedef_nesne_id", "hedef_nesne_turu_id", "tanim_surumu_id"],
            ["nesne.id", "nesne.nesne_turu_id", "nesne.tanim_surumu_id"],
            name=conv(
                "fk_nesne_iliskisi_hedef_nesne_id_hedef_nesne_turu_id_"
                "tanim_surumu_id_nesne"
            ),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "iliski_tanimi_id",
            "kaynak_nesne_id",
            "hedef_nesne_id",
            name=conv(
                "uq_nesne_iliskisi_iliski_tanimi_id_kaynak_nesne_id_hedef_nesne_id"
            ),
        ),
        sa.CheckConstraint(
            "kaynak_nesne_id <> hedef_nesne_id",
            name=conv("ck_nesne_iliskisi_kendine_degil"),
        ),
    )
    op.create_index(
        "ix_nesne_iliskisi_kaynak_nesne_id", "nesne_iliskisi", ["kaynak_nesne_id"]
    )
    op.create_index(
        "ix_nesne_iliskisi_hedef_nesne_id", "nesne_iliskisi", ["hedef_nesne_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_nesne_iliskisi_hedef_nesne_id", table_name="nesne_iliskisi")
    op.drop_index("ix_nesne_iliskisi_kaynak_nesne_id", table_name="nesne_iliskisi")
    op.drop_table("nesne_iliskisi")
    op.drop_index("ix_nesne_ozelligi_ozellik_tanimi_id", table_name="nesne_ozelligi")
    op.drop_table("nesne_ozelligi")
    op.drop_index("ix_nesne_tanim_surumu_id", table_name="nesne")
    op.drop_index("ix_nesne_nesne_turu_id", table_name="nesne")
    op.drop_table("nesne")
    op.drop_table("hiyerarsi_kurali")
    op.drop_index(ILISKI_INDEKSI, table_name="iliski_tanimi")
    _ozellik_tanimini_yeniden_kur(yeni_sutunlar=False)
    op.execute(sa.text("ALTER TABLE tanim_surumu DROP COLUMN kilitli"))
