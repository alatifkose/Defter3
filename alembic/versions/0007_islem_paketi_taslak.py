"""İşlem paketi ve taslak (Aşama 4.5): işlem paketi ve beş aday tablosu.

"Yazmak ≠ kaydetmek": aday veri kesin nesne tablolarından fiziksel olarak
ayrı tablolarda yaşar; bu göç kesin tablolara (``nesne``, ``nesne_ozelligi``,
``nesne_iliskisi``) dokunmaz ve yeni tabloların hiçbiri onlara dış anahtar
taşımaz. Şema ``taslak_tablolari`` ile birebirdir (testte ORM metadata'sıyla
karşılaştırılır). Satır yazılmaz.

* ``kaynak`` üzerine ``(id, okuma_id)`` benzersiz indeksi: aday nesne ve aday
  kayıt satırlarının provenance bileşik dış anahtar hedefi (bir aday öğe
  yalnız kendi paketinin okumasına ait kaynağa bağlanabilir). Tablo yeniden
  kurulmaz; ``CREATE UNIQUE INDEX`` yeterlidir.
* ``islem_paketi``: ``okuma_id → okuma``; ``durum IN ('calisiyor',
  'bekliyor', 'iptal')``; ``(id, okuma_id)`` benzersiz.
* ``aday_nesne``: ``(islem_paketi_id, okuma_id) → islem_paketi (id,
  okuma_id)``; ``(nesne_turu_id, tanim_surumu_id) → nesne_turu``;
  ``(kaynak_id, okuma_id) → kaynak (id, okuma_id)`` (kaynak isteğe bağlı);
  alt tablolar için ``(id, paket)``, ``(id, tür)``, ``(id, paket, tür,
  sürüm)`` benzersiz.
* ``aday_nesne_ozelligi``: iki bileşik dış anahtar aynı ``nesne_turu_id``
  üzerinden; ``(aday_nesne_id, ozellik_tanimi_id)`` benzersiz.
* ``aday_nesne_iliskisi``: dörtlü dış anahtar ``iliski_tanimi``, iki dörtlü
  dış anahtar ``aday_nesne (id, paket, tür, sürüm)``: kaynak ve hedef aday
  aynı pakette ve tanıma uygun türde; ``(tanım, kaynak, hedef)`` benzersiz.
* ``aday_kayit``: pakete ve okumaya bileşik dış anahtar, ``kayit_turu``,
  isteğe bağlı kaynak; ``icerik`` geçerli JSON nesnesi (``json_valid`` ve
  ``json_type = 'object'``); ``(id, paket)`` benzersiz.
* ``aday_kayit_nesne``: iki bileşik dış anahtar ``islem_paketi_id``
  üzerinden (iki taraf aynı pakette); ``(kayıt, nesne)`` benzersiz.

Geri alma altı tabloyu ters sırada düşürür ve ``kaynak`` indeksini kaldırır;
herhangi bir tabloda satır varsa geri alma uygulanmaz ve hata verir (veri
sessizce silinmez; 0005 / 0006 kalıbı).

Sürüm: 0007
Önceki: 0006
Oluşturma: 2026-09-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql.elements import conv

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PAKET_DURUMU_KOSULU = "durum IN ('calisiyor', 'bekliyor', 'iptal')"
ADAY_KAYIT_ICERIK_KOSULU = "json_valid(icerik) AND json_type(icerik) = 'object'"
KAYNAK_INDEKSI = "ix_kaynak_id_okuma_id"

TABLOLAR = (
    "islem_paketi",
    "aday_nesne",
    "aday_nesne_ozelligi",
    "aday_nesne_iliskisi",
    "aday_kayit",
    "aday_kayit_nesne",
)

INDEKSLER: tuple[tuple[str, str, str], ...] = (
    ("ix_islem_paketi_okuma_id", "islem_paketi", "okuma_id"),
    ("ix_islem_paketi_durum", "islem_paketi", "durum"),
    ("ix_aday_nesne_islem_paketi_id", "aday_nesne", "islem_paketi_id"),
    ("ix_aday_nesne_nesne_turu_id", "aday_nesne", "nesne_turu_id"),
    ("ix_aday_nesne_kaynak_id", "aday_nesne", "kaynak_id"),
    (
        "ix_aday_nesne_ozelligi_ozellik_tanimi_id",
        "aday_nesne_ozelligi",
        "ozellik_tanimi_id",
    ),
    (
        "ix_aday_nesne_iliskisi_islem_paketi_id",
        "aday_nesne_iliskisi",
        "islem_paketi_id",
    ),
    (
        "ix_aday_nesne_iliskisi_kaynak_aday_nesne_id",
        "aday_nesne_iliskisi",
        "kaynak_aday_nesne_id",
    ),
    (
        "ix_aday_nesne_iliskisi_hedef_aday_nesne_id",
        "aday_nesne_iliskisi",
        "hedef_aday_nesne_id",
    ),
    ("ix_aday_kayit_islem_paketi_id", "aday_kayit", "islem_paketi_id"),
    ("ix_aday_kayit_kayit_turu_id", "aday_kayit", "kayit_turu_id"),
    ("ix_aday_kayit_kaynak_id", "aday_kayit", "kaynak_id"),
    ("ix_aday_kayit_nesne_islem_paketi_id", "aday_kayit_nesne", "islem_paketi_id"),
    ("ix_aday_kayit_nesne_aday_nesne_id", "aday_kayit_nesne", "aday_nesne_id"),
)


def upgrade() -> None:
    op.create_index(KAYNAK_INDEKSI, "kaynak", ["id", "okuma_id"], unique=True)
    op.create_table(
        "islem_paketi",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("okuma_id", sa.Integer(), nullable=False),
        sa.Column("durum", sa.String(), nullable=False),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.Column("durum_zamani", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("pk_islem_paketi")),
        sa.ForeignKeyConstraint(
            ["okuma_id"],
            ["okuma.id"],
            name=conv("fk_islem_paketi_okuma_id_okuma"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "okuma_id", name=conv("uq_islem_paketi_id_okuma_id")),
        sa.CheckConstraint(
            PAKET_DURUMU_KOSULU, name=conv("ck_islem_paketi_durum_gecerli")
        ),
    )
    op.create_table(
        "aday_nesne",
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
    )
    op.create_table(
        "aday_nesne_ozelligi",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("aday_nesne_id", sa.Integer(), nullable=False),
        sa.Column("nesne_turu_id", sa.Integer(), nullable=False),
        sa.Column("ozellik_tanimi_id", sa.Integer(), nullable=False),
        sa.Column("deger", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("pk_aday_nesne_ozelligi")),
        sa.ForeignKeyConstraint(
            ["aday_nesne_id", "nesne_turu_id"],
            ["aday_nesne.id", "aday_nesne.nesne_turu_id"],
            name=conv("fk_aday_nesne_ozelligi_aday_nesne_id_nesne_turu_id_aday_nesne"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ozellik_tanimi_id", "nesne_turu_id"],
            ["ozellik_tanimi.id", "ozellik_tanimi.nesne_turu_id"],
            name=conv(
                "fk_aday_nesne_ozelligi_ozellik_tanimi_id_nesne_turu_id_ozellik_tanimi"
            ),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "aday_nesne_id",
            "ozellik_tanimi_id",
            name=conv("uq_aday_nesne_ozelligi_aday_nesne_id_ozellik_tanimi_id"),
        ),
    )
    op.create_table(
        "aday_nesne_iliskisi",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("islem_paketi_id", sa.Integer(), nullable=False),
        sa.Column("iliski_tanimi_id", sa.Integer(), nullable=False),
        sa.Column("tanim_surumu_id", sa.Integer(), nullable=False),
        sa.Column("kaynak_nesne_turu_id", sa.Integer(), nullable=False),
        sa.Column("hedef_nesne_turu_id", sa.Integer(), nullable=False),
        sa.Column("kaynak_aday_nesne_id", sa.Integer(), nullable=False),
        sa.Column("hedef_aday_nesne_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("pk_aday_nesne_iliskisi")),
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
                "fk_aday_nesne_iliskisi_iliski_tanimi_id_tanim_surumu_id_"
                "kaynak_nesne_turu_id_hedef_nesne_turu_id_iliski_tanimi"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "kaynak_aday_nesne_id",
                "islem_paketi_id",
                "kaynak_nesne_turu_id",
                "tanim_surumu_id",
            ],
            [
                "aday_nesne.id",
                "aday_nesne.islem_paketi_id",
                "aday_nesne.nesne_turu_id",
                "aday_nesne.tanim_surumu_id",
            ],
            name=conv(
                "fk_aday_nesne_iliskisi_kaynak_aday_nesne_id_islem_paketi_id_"
                "kaynak_nesne_turu_id_tanim_surumu_id_aday_nesne"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "hedef_aday_nesne_id",
                "islem_paketi_id",
                "hedef_nesne_turu_id",
                "tanim_surumu_id",
            ],
            [
                "aday_nesne.id",
                "aday_nesne.islem_paketi_id",
                "aday_nesne.nesne_turu_id",
                "aday_nesne.tanim_surumu_id",
            ],
            name=conv(
                "fk_aday_nesne_iliskisi_hedef_aday_nesne_id_islem_paketi_id_"
                "hedef_nesne_turu_id_tanim_surumu_id_aday_nesne"
            ),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "iliski_tanimi_id",
            "kaynak_aday_nesne_id",
            "hedef_aday_nesne_id",
            name=conv(
                "uq_aday_nesne_iliskisi_iliski_tanimi_id_kaynak_aday_nesne_id_"
                "hedef_aday_nesne_id"
            ),
        ),
    )
    op.create_table(
        "aday_kayit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("islem_paketi_id", sa.Integer(), nullable=False),
        sa.Column("okuma_id", sa.Integer(), nullable=False),
        sa.Column("kayit_turu_id", sa.Integer(), nullable=False),
        sa.Column("kaynak_id", sa.Integer(), nullable=True),
        sa.Column("icerik", sa.Text(), nullable=False),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("pk_aday_kayit")),
        sa.ForeignKeyConstraint(
            ["islem_paketi_id", "okuma_id"],
            ["islem_paketi.id", "islem_paketi.okuma_id"],
            name=conv("fk_aday_kayit_islem_paketi_id_okuma_id_islem_paketi"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["kaynak_id", "okuma_id"],
            ["kaynak.id", "kaynak.okuma_id"],
            name=conv("fk_aday_kayit_kaynak_id_okuma_id_kaynak"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["kayit_turu_id"],
            ["kayit_turu.id"],
            name=conv("fk_aday_kayit_kayit_turu_id_kayit_turu"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "id", "islem_paketi_id", name=conv("uq_aday_kayit_id_islem_paketi_id")
        ),
        sa.CheckConstraint(
            ADAY_KAYIT_ICERIK_KOSULU, name=conv("ck_aday_kayit_icerik_json_nesnesi")
        ),
    )
    op.create_table(
        "aday_kayit_nesne",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("islem_paketi_id", sa.Integer(), nullable=False),
        sa.Column("aday_kayit_id", sa.Integer(), nullable=False),
        sa.Column("aday_nesne_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("pk_aday_kayit_nesne")),
        sa.ForeignKeyConstraint(
            ["aday_kayit_id", "islem_paketi_id"],
            ["aday_kayit.id", "aday_kayit.islem_paketi_id"],
            name=conv("fk_aday_kayit_nesne_aday_kayit_id_islem_paketi_id_aday_kayit"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["aday_nesne_id", "islem_paketi_id"],
            ["aday_nesne.id", "aday_nesne.islem_paketi_id"],
            name=conv("fk_aday_kayit_nesne_aday_nesne_id_islem_paketi_id_aday_nesne"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "aday_kayit_id",
            "aday_nesne_id",
            name=conv("uq_aday_kayit_nesne_aday_kayit_id_aday_nesne_id"),
        ),
    )
    for ad, tablo, sutun in INDEKSLER:
        op.create_index(ad, tablo, [sutun])


def downgrade() -> None:
    baglanti = op.get_bind()
    dolu = [
        tablo
        for tablo in TABLOLAR
        if baglanti.execute(sa.text(f"SELECT count(*) FROM {tablo}")).scalar_one()
    ]
    if dolu:
        raise RuntimeError(
            "göç 0007 geri alınamaz: satır taşıyan tablo var "
            f"({', '.join(dolu)}); veri sessizce silinmez."
        )
    for ad, tablo, _ in reversed(INDEKSLER):
        op.drop_index(ad, table_name=tablo)
    for tablo in reversed(TABLOLAR):
        op.drop_table(tablo)
    op.drop_index(KAYNAK_INDEKSI, table_name="kaynak")
