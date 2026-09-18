"""Sürüm numarası kontrol kısıtı: pozitif ve INTEGER depolama sınıfı.

Aşama 4.2 incelemesi: ``0002``'deki ``surum_no > 0`` kısıtı SQLite'ta ``1.5``
gibi pozitif REAL değerleri engellemiyordu (INTEGER sütunu katı tür değildir).
Bu göç kısıtı ``typeof(surum_no) = 'integer' AND surum_no > 0`` ile değiştirir.

SQLite ``ALTER TABLE`` ile kısıt değiştiremez; tablo yeniden kurulur. Alembic
``batch`` kipi burada kullanılamaz: göçler 4.1 politikasıyla ``foreign_keys=ON``
bağlantıda ve tek transaction içinde çalışır, ``PRAGMA foreign_keys`` transaction
içinde etkisizdir, ve ``batch`` ana tabloyu çocuk satırlar (``nesne_turu``,
``iliski_tanimi``, ``kayit_turu`` → ``tanim_surumu``) dururken düşürdüğü için
``FOREIGN KEY constraint failed`` verir. Bunun yerine adımlar açık yazılır:

1. ``PRAGMA defer_foreign_keys = ON`` (transaction içinde izinli): ana tablo
   düşürülürken oluşan ihlaller commit'e ertelenir.
2. Satırlar kısıtsız bir taşıma tablosuna kopyalanır.
3. Yeni tablo yeni kısıtla, aynı kısıt adlarıyla ve sabit sırayla kurulur.
4. Eski tablo düşürülür (ertelenmiş ihlal sayacı çocuk satır kadar artar).
5. Yeni tablo eski adı alır; çocuk tabloların ``REFERENCES tanim_surumu``
   metni değişmeden yeni tabloyu gösterir.
6. Satırlar taşıma tablosundan geri yazılır: ana tabloya giren her satır
   eşleşen çocuk satırlar için sayacı düşürür, commit'te sayaç sıfırdır.
7. Taşıma tablosu düşürülür.

Bir adım düşerse transaction tamamen geri alınır (4.1 atomiklik kanıtı).
Göç sonunda ``PRAGMA foreign_key_check`` boş dönmezse göç hata verir.
Veri dönüştürülmez: mevcut ``surum_no`` değerleri tam sayı olmalıdır; değilse
geri yazma adımı kısıt hatasıyla düşer ve göç uygulanmaz.

Sürüm: 0003
Önceki: 0002
Oluşturma: 2026-09-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql.elements import conv

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLO = "tanim_surumu"
YENI_TABLO = "tanim_surumu_yeni"
TASIMA_TABLOSU = "tanim_surumu_tasima"
SUTUNLAR = "id, tanim_paketi_id, surum_no, aciklama, olusturma_zamani"

YENI_KISIT = "ck_tanim_surumu_surum_no_pozitif_tamsayi"
YENI_KOSUL = "typeof(surum_no) = 'integer' AND surum_no > 0"
ESKI_KISIT = "ck_tanim_surumu_surum_no_pozitif"
ESKI_KOSUL = "surum_no > 0"


def _yeniden_kur(kisit_adi: str, kosul: str) -> None:
    """``tanim_surumu``'yu verilen kontrol kısıtıyla yeniden kurar, satırları korur."""
    op.execute(sa.text("PRAGMA defer_foreign_keys = ON"))
    op.execute(
        sa.text(f"CREATE TABLE {TASIMA_TABLOSU} AS SELECT {SUTUNLAR} FROM {TABLO}")
    )
    # Kısıt adları tam verilir; ``conv`` adlandırma kalıbının bir daha önek
    # eklemesini engeller. Sıra 0002 ile aynıdır: pk, fk, uq, ck.
    op.create_table(
        YENI_TABLO,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tanim_paketi_id", sa.Integer(), nullable=False),
        sa.Column("surum_no", sa.Integer(), nullable=False),
        sa.Column("aciklama", sa.Text(), nullable=True),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("pk_tanim_surumu")),
        sa.ForeignKeyConstraint(
            ["tanim_paketi_id"],
            ["tanim_paketi.id"],
            name=conv("fk_tanim_surumu_tanim_paketi_id_tanim_paketi"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tanim_paketi_id",
            "surum_no",
            name=conv("uq_tanim_surumu_tanim_paketi_id_surum_no"),
        ),
        sa.CheckConstraint(kosul, name=conv(kisit_adi)),
    )
    op.execute(sa.text(f"DROP TABLE {TABLO}"))
    op.execute(sa.text(f"ALTER TABLE {YENI_TABLO} RENAME TO {TABLO}"))
    op.execute(
        sa.text(
            f"INSERT INTO {TABLO} ({SUTUNLAR}) SELECT {SUTUNLAR} FROM {TASIMA_TABLOSU}"
        )
    )
    op.execute(sa.text(f"DROP TABLE {TASIMA_TABLOSU}"))
    ihlaller = op.get_bind().execute(sa.text("PRAGMA foreign_key_check")).all()
    if ihlaller:
        raise RuntimeError(f"göç sonrası dış anahtar ihlali: {len(ihlaller)} satır")


def upgrade() -> None:
    _yeniden_kur(YENI_KISIT, YENI_KOSUL)


def downgrade() -> None:
    _yeniden_kur(ESKI_KISIT, ESKI_KOSUL)
