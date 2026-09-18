"""Genel ilişkide kendine dönüş serbest: ``nesne_iliskisi`` kontrol kısıtı kalkar.

Aşama 4.3 incelemesi: ``0004`` bütün nesne ilişkilerine ``kaynak_nesne_id <>
hedef_nesne_id`` kısıtı koymuştu. Bu, hiyerarşik olmayan genel ilişkiler için
çekirdeğin vermemesi gereken evrensel bir anlam kararıdır; hiyerarşik
ilişkilerde çevrim (kendine dönüş dahil) ise servis düzeyinde, bütün hiyerarşik
ilişki tanımları üzerinden denetlenir. Bu göç yalnız o kısıtı kaldırır.

SQLite kısıt düşüremediğinden tablo açık SQL adımlarıyla aynı kısıt adları ve
sabit sırayla yeniden kurulur; satırlar taşınır. ``nesne_iliskisi``'ye bağlı
çocuk tablo olmadığından dış anahtar erteleme gerekmez. İndeksler tabloyla
gider, yeniden kurulur. Geri alma kısıtı geri getirir; kendine dönen satır
varsa geri alma kısıt hatasıyla düşer ve uygulanmaz (veri sessizce silinmez).

Sürüm: 0005
Önceki: 0004
Oluşturma: 2026-09-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.schema import SchemaItem
from sqlalchemy.sql.elements import conv

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLO = "nesne_iliskisi"
YENI_TABLO = "nesne_iliskisi_yeni"
SUTUNLAR = (
    "id, iliski_tanimi_id, tanim_surumu_id, kaynak_nesne_turu_id, "
    "hedef_nesne_turu_id, kaynak_nesne_id, hedef_nesne_id"
)


def _yeniden_kur(kendine_yasak: bool) -> None:
    """``nesne_iliskisi``'yi 0004 (``kendine_yasak``) ya da 0005 şemasıyla kurar."""
    ek_kisitlar: list[SchemaItem] = []
    if kendine_yasak:
        ek_kisitlar.append(
            sa.CheckConstraint(
                "kaynak_nesne_id <> hedef_nesne_id",
                name=conv("ck_nesne_iliskisi_kendine_degil"),
            )
        )
    op.create_table(
        YENI_TABLO,
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
        *ek_kisitlar,
    )
    op.execute(
        sa.text(f"INSERT INTO {YENI_TABLO} ({SUTUNLAR}) SELECT {SUTUNLAR} FROM {TABLO}")
    )
    op.execute(sa.text(f"DROP TABLE {TABLO}"))
    op.execute(sa.text(f"ALTER TABLE {YENI_TABLO} RENAME TO {TABLO}"))
    op.create_index("ix_nesne_iliskisi_kaynak_nesne_id", TABLO, ["kaynak_nesne_id"])
    op.create_index("ix_nesne_iliskisi_hedef_nesne_id", TABLO, ["hedef_nesne_id"])


def upgrade() -> None:
    _yeniden_kur(kendine_yasak=False)


def downgrade() -> None:
    _yeniden_kur(kendine_yasak=True)
