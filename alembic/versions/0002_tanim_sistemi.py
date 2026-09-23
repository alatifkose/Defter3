"""Tanım sistemi: genel tanım tabloları (Aşama 4.2).

Yedi tablo: ``tanim_paketi``, ``tanim_surumu``, ``nesne_turu``,
``ozellik_tanimi``, ``iliski_tanimi``, ``kayit_turu``, ``kayit_alani_tanimi``.
Şema ``defteruc.cekirdek.tanim_tablolari`` ile birebirdir; kısıt adları
``veritabani.KISIT_ADLANDIRMA`` kalıbıyla açıkça yazılmıştır (testte ORM
metadata'sı ile karşılaştırılır). Hiçbir satır yazılmaz: tanım verisi (hangi
türler, özellikler, ilişkiler) domain paketinin işidir, göçün değil.

Sürüm: 0002
Önceki: 0001
Oluşturma: 2026-09-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tanim_paketi",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kod", sa.String(), nullable=False),
        sa.Column("gosterim_adi", sa.String(), nullable=False),
        sa.Column("aciklama", sa.Text(), nullable=True),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_tanim_paketi"),
        sa.UniqueConstraint("kod", name="uq_tanim_paketi_kod"),
    )
    op.create_table(
        "tanim_surumu",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tanim_paketi_id", sa.Integer(), nullable=False),
        sa.Column("surum_no", sa.Integer(), nullable=False),
        sa.Column("aciklama", sa.Text(), nullable=True),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_tanim_surumu"),
        sa.ForeignKeyConstraint(
            ["tanim_paketi_id"],
            ["tanim_paketi.id"],
            name="fk_tanim_surumu_tanim_paketi_id_tanim_paketi",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tanim_paketi_id",
            "surum_no",
            name="uq_tanim_surumu_tanim_paketi_id_surum_no",
        ),
        sa.CheckConstraint("surum_no > 0", name="surum_no_pozitif"),
    )
    op.create_table(
        "nesne_turu",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tanim_surumu_id", sa.Integer(), nullable=False),
        sa.Column("kod", sa.String(), nullable=False),
        sa.Column("gosterim_adi", sa.String(), nullable=False),
        sa.Column("aciklama", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_nesne_turu"),
        sa.ForeignKeyConstraint(
            ["tanim_surumu_id"],
            ["tanim_surumu.id"],
            name="fk_nesne_turu_tanim_surumu_id_tanim_surumu",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tanim_surumu_id", "kod", name="uq_nesne_turu_tanim_surumu_id_kod"
        ),
        sa.UniqueConstraint(
            "id", "tanim_surumu_id", name="uq_nesne_turu_id_tanim_surumu_id"
        ),
    )
    op.create_table(
        "ozellik_tanimi",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nesne_turu_id", sa.Integer(), nullable=False),
        sa.Column("kod", sa.String(), nullable=False),
        sa.Column("gosterim_adi", sa.String(), nullable=False),
        sa.Column("aciklama", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_ozellik_tanimi"),
        sa.ForeignKeyConstraint(
            ["nesne_turu_id"],
            ["nesne_turu.id"],
            name="fk_ozellik_tanimi_nesne_turu_id_nesne_turu",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "nesne_turu_id", "kod", name="uq_ozellik_tanimi_nesne_turu_id_kod"
        ),
    )
    op.create_table(
        "iliski_tanimi",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tanim_surumu_id", sa.Integer(), nullable=False),
        sa.Column("kod", sa.String(), nullable=False),
        sa.Column("gosterim_adi", sa.String(), nullable=False),
        sa.Column("aciklama", sa.Text(), nullable=True),
        sa.Column("kaynak_nesne_turu_id", sa.Integer(), nullable=False),
        sa.Column("hedef_nesne_turu_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_iliski_tanimi"),
        sa.ForeignKeyConstraint(
            ["tanim_surumu_id"],
            ["tanim_surumu.id"],
            name="fk_iliski_tanimi_tanim_surumu_id_tanim_surumu",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["kaynak_nesne_turu_id", "tanim_surumu_id"],
            ["nesne_turu.id", "nesne_turu.tanim_surumu_id"],
            name="fk_iliski_tanimi_kaynak_nesne_turu_id_tanim_surumu_id_nesne_turu",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hedef_nesne_turu_id", "tanim_surumu_id"],
            ["nesne_turu.id", "nesne_turu.tanim_surumu_id"],
            name="fk_iliski_tanimi_hedef_nesne_turu_id_tanim_surumu_id_nesne_turu",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tanim_surumu_id", "kod", name="uq_iliski_tanimi_tanim_surumu_id_kod"
        ),
    )
    op.create_index(
        "ix_iliski_tanimi_kaynak_nesne_turu_id",
        "iliski_tanimi",
        ["kaynak_nesne_turu_id"],
    )
    op.create_index(
        "ix_iliski_tanimi_hedef_nesne_turu_id",
        "iliski_tanimi",
        ["hedef_nesne_turu_id"],
    )
    op.create_table(
        "kayit_turu",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tanim_surumu_id", sa.Integer(), nullable=False),
        sa.Column("kod", sa.String(), nullable=False),
        sa.Column("gosterim_adi", sa.String(), nullable=False),
        sa.Column("aciklama", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_kayit_turu"),
        sa.ForeignKeyConstraint(
            ["tanim_surumu_id"],
            ["tanim_surumu.id"],
            name="fk_kayit_turu_tanim_surumu_id_tanim_surumu",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tanim_surumu_id", "kod", name="uq_kayit_turu_tanim_surumu_id_kod"
        ),
    )
    op.create_table(
        "kayit_alani_tanimi",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kayit_turu_id", sa.Integer(), nullable=False),
        sa.Column("kod", sa.String(), nullable=False),
        sa.Column("gosterim_adi", sa.String(), nullable=False),
        sa.Column("aciklama", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_kayit_alani_tanimi"),
        sa.ForeignKeyConstraint(
            ["kayit_turu_id"],
            ["kayit_turu.id"],
            name="fk_kayit_alani_tanimi_kayit_turu_id_kayit_turu",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "kayit_turu_id", "kod", name="uq_kayit_alani_tanimi_kayit_turu_id_kod"
        ),
    )


def downgrade() -> None:
    op.drop_table("kayit_alani_tanimi")
    op.drop_table("kayit_turu")
    op.drop_index("ix_iliski_tanimi_hedef_nesne_turu_id", table_name="iliski_tanimi")
    op.drop_index("ix_iliski_tanimi_kaynak_nesne_turu_id", table_name="iliski_tanimi")
    op.drop_table("iliski_tanimi")
    op.drop_table("ozellik_tanimi")
    op.drop_table("nesne_turu")
    op.drop_table("tanim_surumu")
    op.drop_table("tanim_paketi")
