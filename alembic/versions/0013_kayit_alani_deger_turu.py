"""Kayıt tanımı genişlemesi (Aşama 4.7/1): alan değer türü ve anahtar hedefleri.

Kesin kayıt tabloları bu göçte **yoktur** (0014); burada yalnız tanım tarafı
kesin kaydı taşıyabilecek hâle gelir:

* ``kayit_alani_tanimi``: ``deger_turu`` (metin / tam_sayi / mantiksal /
  ondalik, kontrol kısıtı) ve ``zorunlu`` (ikili) sütunları; kayıt alanının
  bileşik dış anahtarı için ``(id, kayit_turu_id)`` benzersizliği. SQLite
  ``ALTER TABLE`` ile benzersizlik ve kontrol kısıtı ekleyemediğinden tablo
  açık SQL adımlarıyla yeniden kurulur (0003 / 0004 kalıbı); tablonun çocuğu
  henüz olmadığından FK erteleme gerekmez. Var olan satırlar (varsa) metin /
  isteğe bağlı sayılır.
* ``kayit_turu``: kesin kaydın bileşik dış anahtarı için ``(id,
  tanim_surumu_id)`` benzersiz indeksi; tablo yeniden kurulmaz.

Geri alma tersini yapar: indeks düşer, tablo eski şemasıyla yeniden kurulur ve
satırlar korunur (yeni sütunlar kaybolur, başka veri silinmez).

Sürüm: 0013
Önceki: 0012
Oluşturma: 2026-09-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.schema import SchemaItem
from sqlalchemy.sql.elements import conv

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEGER_TURLERI = "'metin', 'tam_sayi', 'mantiksal', 'ondalik'"
ALAN_ESKI_SUTUNLAR = "id, kayit_turu_id, kod, gosterim_adi, aciklama"
KAYIT_TURU_INDEKSI = "ix_kayit_turu_id_tanim_surumu_id"


def _kayit_alani_tanimi_kur(ad: str, yeni_sutunlar: bool) -> None:
    """``kayit_alani_tanimi`` şeması; ``yeni_sutunlar`` 0013 (True) ya da
    0012 (False)."""
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
                "id",
                "kayit_turu_id",
                name=conv("uq_kayit_alani_tanimi_id_kayit_turu_id"),
            ),
            sa.CheckConstraint(
                f"deger_turu IN ({DEGER_TURLERI})",
                name=conv("ck_kayit_alani_tanimi_deger_turu_gecerli"),
            ),
            sa.CheckConstraint(
                "zorunlu IN (0, 1)", name=conv("ck_kayit_alani_tanimi_zorunlu_ikili")
            ),
        ]
    op.create_table(
        ad,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kayit_turu_id", sa.Integer(), nullable=False),
        sa.Column("kod", sa.String(), nullable=False),
        sa.Column("gosterim_adi", sa.String(), nullable=False),
        sa.Column("aciklama", sa.Text(), nullable=True),
        *ek_sutunlar,
        sa.PrimaryKeyConstraint("id", name=conv("pk_kayit_alani_tanimi")),
        sa.ForeignKeyConstraint(
            ["kayit_turu_id"],
            ["kayit_turu.id"],
            name=conv("fk_kayit_alani_tanimi_kayit_turu_id_kayit_turu"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "kayit_turu_id", "kod", name=conv("uq_kayit_alani_tanimi_kayit_turu_id_kod")
        ),
        *ek_kisitlar,
    )


def _kayit_alani_tanimini_yeniden_kur(yeni_sutunlar: bool) -> None:
    """Tabloyu yeni ya da eski şemayla yeniden kurar; satırları taşır."""
    _kayit_alani_tanimi_kur("kayit_alani_tanimi_yeni", yeni_sutunlar)
    op.execute(
        sa.text(
            f"INSERT INTO kayit_alani_tanimi_yeni ({ALAN_ESKI_SUTUNLAR}) "
            f"SELECT {ALAN_ESKI_SUTUNLAR} FROM kayit_alani_tanimi"
        )
    )
    op.execute(sa.text("DROP TABLE kayit_alani_tanimi"))
    op.execute(
        sa.text("ALTER TABLE kayit_alani_tanimi_yeni RENAME TO kayit_alani_tanimi")
    )


def upgrade() -> None:
    _kayit_alani_tanimini_yeniden_kur(yeni_sutunlar=True)
    op.create_index(
        KAYIT_TURU_INDEKSI,
        "kayit_turu",
        ["id", "tanim_surumu_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(KAYIT_TURU_INDEKSI, table_name="kayit_turu")
    _kayit_alani_tanimini_yeniden_kur(yeni_sutunlar=False)
