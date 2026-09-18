"""Genel altyapı: göç zincirinin başlangıcı, uygulama tablosu yok.

Aşama 4.1 yalnız persistence temelini kurar: bu göç hiçbir uygulama tablosu
oluşturmaz. Alembic kendi ``alembic_version`` tablosunu bu göçle yazar ve
şema sürümü bundan sonra oradan okunur. İlk genel tanım tabloları Aşama 4.2'de
yeni bir göçle gelir; bu dosya değişmez.

Sürüm: 0001
Önceki: yok
Oluşturma: 2026-09-18
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
