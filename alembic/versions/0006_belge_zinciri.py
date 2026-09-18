"""Belge zinciri (Aşama 4.4): arşiv dosyası, belge, okuma, kaynak tabloları.

Yeni tablolar (şema ``belge_tablolari`` ile birebir; testte ORM metadata'sıyla
karşılaştırılır). Var olan tablolara dokunulmaz; satır yazılmaz.

* ``arsiv_dosyasi``: ``sha256`` ve ``goreli_yol`` benzersiz; kontrol
  kısıtları: 64 karakter küçük harf onaltılık özet, göreli yol yalnız
  özetten türer (``substr(sha256, 1, 2) || '/' || sha256``), pozitif tam sayı
  boyut.
* ``belge``: ``arsiv_dosyasi_id`` benzersiz (bir arşiv dosyasından tek belge).
* ``okuma``: ``(belge_id, surum_no)`` ve ``(id, belge_id)`` benzersiz; kontrol
  kısıtları: pozitif tam sayı sürüm, durum ile içerik / tamamlanma zamanı
  tutarlılığı, içerik geçerli JSON (``json_valid``).
* ``kaynak``: ``(okuma_id, belge_id)`` bileşik dış anahtarla
  ``okuma (id, belge_id)``; konum geçerli JSON; belge ve okuma indeksleri.

Geri alma dört tabloyu ters sırada düşürür; herhangi birinde satır varsa
geri alma uygulanmaz ve hata verir (veri sessizce silinmez; 0005 kalıbı).

Sürüm: 0006
Önceki: 0005
Oluşturma: 2026-09-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql.elements import conv

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SHA256_KOSULU = "length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'"
GORELI_YOL_KOSULU = "goreli_yol = substr(sha256, 1, 2) || '/' || sha256"
BOYUT_KOSULU = "typeof(boyut) = 'integer' AND boyut > 0"
SURUM_NO_KOSULU = "typeof(surum_no) = 'integer' AND surum_no > 0"
OKUMA_DURUMU_KOSULU = (
    "(durum = 'basladi' AND icerik IS NULL AND tamamlanma_zamani IS NULL) OR "
    "(durum = 'tamamlandi' AND icerik IS NOT NULL AND tamamlanma_zamani IS NOT NULL)"
)
ICERIK_JSON_KOSULU = "icerik IS NULL OR json_valid(icerik)"
KONUM_JSON_KOSULU = "konum IS NULL OR json_valid(konum)"


def upgrade() -> None:
    op.create_table(
        "arsiv_dosyasi",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("boyut", sa.Integer(), nullable=False),
        sa.Column("mime", sa.String(), nullable=False),
        sa.Column("kaynak_uzantisi", sa.String(), nullable=False),
        sa.Column("kaynak_adi", sa.String(), nullable=False),
        sa.Column("goreli_yol", sa.String(), nullable=False),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("pk_arsiv_dosyasi")),
        sa.UniqueConstraint("sha256", name=conv("uq_arsiv_dosyasi_sha256")),
        sa.UniqueConstraint("goreli_yol", name=conv("uq_arsiv_dosyasi_goreli_yol")),
        sa.CheckConstraint(SHA256_KOSULU, name=conv("ck_arsiv_dosyasi_sha256_bicimi")),
        sa.CheckConstraint(
            GORELI_YOL_KOSULU, name=conv("ck_arsiv_dosyasi_goreli_yol_icerikten")
        ),
        sa.CheckConstraint(
            BOYUT_KOSULU, name=conv("ck_arsiv_dosyasi_boyut_pozitif_tamsayi")
        ),
    )
    op.create_table(
        "belge",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("arsiv_dosyasi_id", sa.Integer(), nullable=False),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("pk_belge")),
        sa.ForeignKeyConstraint(
            ["arsiv_dosyasi_id"],
            ["arsiv_dosyasi.id"],
            name=conv("fk_belge_arsiv_dosyasi_id_arsiv_dosyasi"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("arsiv_dosyasi_id", name=conv("uq_belge_arsiv_dosyasi_id")),
    )
    op.create_table(
        "okuma",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("belge_id", sa.Integer(), nullable=False),
        sa.Column("surum_no", sa.Integer(), nullable=False),
        sa.Column("durum", sa.String(), nullable=False),
        sa.Column("icerik", sa.Text(), nullable=True),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.Column("tamamlanma_zamani", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=conv("pk_okuma")),
        sa.ForeignKeyConstraint(
            ["belge_id"],
            ["belge.id"],
            name=conv("fk_okuma_belge_id_belge"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "belge_id", "surum_no", name=conv("uq_okuma_belge_id_surum_no")
        ),
        sa.UniqueConstraint("id", "belge_id", name=conv("uq_okuma_id_belge_id")),
        sa.CheckConstraint(
            SURUM_NO_KOSULU, name=conv("ck_okuma_surum_no_pozitif_tamsayi")
        ),
        sa.CheckConstraint(
            OKUMA_DURUMU_KOSULU, name=conv("ck_okuma_durum_icerik_tutarli")
        ),
        sa.CheckConstraint(ICERIK_JSON_KOSULU, name=conv("ck_okuma_icerik_json")),
    )
    op.create_table(
        "kaynak",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("belge_id", sa.Integer(), nullable=False),
        sa.Column("okuma_id", sa.Integer(), nullable=False),
        sa.Column("konum", sa.Text(), nullable=True),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("pk_kaynak")),
        sa.ForeignKeyConstraint(
            ["okuma_id", "belge_id"],
            ["okuma.id", "okuma.belge_id"],
            name=conv("fk_kaynak_okuma_id_belge_id_okuma"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(KONUM_JSON_KOSULU, name=conv("ck_kaynak_konum_json")),
    )
    op.create_index("ix_kaynak_belge_id", "kaynak", ["belge_id"])
    op.create_index("ix_kaynak_okuma_id", "kaynak", ["okuma_id"])


TABLOLAR = ("arsiv_dosyasi", "belge", "okuma", "kaynak")


def downgrade() -> None:
    baglanti = op.get_bind()
    dolu = [
        tablo
        for tablo in TABLOLAR
        if baglanti.execute(sa.text(f"SELECT count(*) FROM {tablo}")).scalar_one()
    ]
    if dolu:
        raise RuntimeError(
            "göç 0006 geri alınamaz: satır taşıyan tablo var "
            f"({', '.join(dolu)}); veri sessizce silinmez."
        )
    op.drop_index("ix_kaynak_okuma_id", table_name="kaynak")
    op.drop_index("ix_kaynak_belge_id", table_name="kaynak")
    op.drop_table("kaynak")
    op.drop_table("okuma")
    op.drop_table("belge")
    op.drop_table("arsiv_dosyasi")
