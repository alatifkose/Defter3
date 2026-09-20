"""Ortak karar talebinin bütün paket bağlarını koru.

Mevcut taleplerin açıldığı paketler yeni bağ tablosuna taşınır; geçmiş
talep ve karar satırları değişmez. Birden fazla paket bağı eski şemada ifade
edilemediğinden bu veri varken geri alma reddedilir.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "karar_talebi_paketi",
        sa.Column("karar_talebi_id", sa.Integer(), nullable=False),
        sa.Column("islem_paketi_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("karar_talebi_id", "islem_paketi_id"),
        sa.ForeignKeyConstraint(
            ["karar_talebi_id"], ["karar_talebi.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["islem_paketi_id"], ["islem_paketi.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index(
        "ix_karar_talebi_paketi_islem_paketi_id",
        "karar_talebi_paketi",
        ["islem_paketi_id"],
    )
    op.execute(
        "INSERT INTO karar_talebi_paketi (karar_talebi_id, islem_paketi_id) "
        "SELECT id, islem_paketi_id FROM karar_talebi "
        "WHERE islem_paketi_id IS NOT NULL"
    )


def downgrade() -> None:
    ek_bag = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM karar_talebi_paketi AS b "
                "JOIN karar_talebi AS t ON t.id = b.karar_talebi_id "
                "WHERE t.islem_paketi_id IS NULL "
                "OR b.islem_paketi_id <> t.islem_paketi_id LIMIT 1"
            )
        )
        .first()
    )
    if ek_bag is not None:
        raise RuntimeError(
            "Ortak karar talebi paket bağları varken 0010 geri alınamaz."
        )
    op.drop_table("karar_talebi_paketi")
