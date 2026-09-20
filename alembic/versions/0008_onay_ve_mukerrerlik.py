"""Onay ve mükerrerlik (Aşama 4.6): şart, karar talebi, çözümleme, denetim izi.

Altı yeni tablo (şema ``mukerrerlik_tablolari`` ve ``denetim_tablolari`` ile
birebirdir; testte ORM metadata'sıyla karşılaştırılır). Var olan tablolara
dokunulmaz; satır yazılmaz.

* ``nesne_mukerrerlik_sarti`` / ``aday_nesne_mukerrerlik_sarti``: kullanıcının
  seçtiği şart özellikleri; iki bileşik dış anahtar aynı ``nesne_turu_id``
  üzerinden, yani başka türün özelliği veritabanında da şart olamaz;
  ``(sahip, özellik)`` benzersiz.
* ``karar_talebi``: mükerrerlik şüphesi ve kalıcı kullanıcı karar talebi.
  Uçlardan tam biri aday nesne, diğeri her zaman mevcut kesin nesnedir
  (kontrol kısıtı); kesin çiftte ``kaynak > hedef`` sırası zorlanır. Durum ile
  karar alanları birlikte tutarlıdır. **Kısmi benzersiz indeksler** aynı çift
  için ikinci bir *açık* talebi (eşzamanlı açma dahil) veritabanı düzeyinde
  engeller; çözülmüş talepler kısıt dışındadır ve satırda kalır.
* ``aday_nesne_cozumlemesi``: "bu aday şu kesin nesne olarak çözüldü"; Aşama
  4.8 bunu tahmin etmez, okur. Aday satır kesin tabloya taşınmaz.
* ``nesne_birlesimi``: birleşen kesin nesne silinmez, bu satırla kalıcı olarak
  hedefe bağlanır.
* ``denetim_izi``: aktörlü iş denetim izi; teknik günlükten ayrıdır. Hiç
  silinmeyen satırlara ``RESTRICT`` ile bağlanır; ``aday_nesne_id`` bilerek
  dış anahtar değildir (aday silinebilir, iz yaşamalıdır).

Geri alma altı tabloyu ters sırada düşürür; herhangi birinde satır varsa geri
alma uygulanmaz ve hata verir (veri sessizce silinmez; 0005 / 0006 / 0007
kalıbı).

Sürüm: 0008
Önceki: 0007
Oluşturma: 2026-09-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql.elements import conv

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TALEP_DURUMU_KOSULU = "durum IN ('acik', 'cozuldu')"
KARAR_KOSULU = "karar IS NULL OR karar IN ('ayni', 'ayri')"
DURUM_KARAR_KOSULU = (
    "(durum = 'acik' AND karar IS NULL AND karar_zamani IS NULL "
    "AND karar_aktor_turu IS NULL) OR "
    "(durum = 'cozuldu' AND karar IS NOT NULL AND karar_zamani IS NOT NULL "
    "AND karar_aktor_turu IS NOT NULL)"
)
TEK_UC_KOSULU = "(aday_nesne_id IS NULL) <> (kaynak_nesne_id IS NULL)"
KESIN_CIFT_SIRASI_KOSULU = "kaynak_nesne_id IS NULL OR kaynak_nesne_id > hedef_nesne_id"
OLAY_KOSULU = (
    "olay IN ('mukerrerlik_sarti_belirlendi', 'mukerrerlik_suphesi_acildi', "
    "'karar_talebi_acildi', 'kullanici_karari_verildi', "
    "'nesne_ayri_kabul_edildi', 'nesne_birlestirildi', "
    "'aday_nesneye_cozumlendi', 'paket_beklemeye_gecti', "
    "'paket_yeniden_calisiyor')"
)
AKTOR_TURU_KOSULU = "aktor_turu IN ('kullanici', 'ajan', 'sistem')"

ACIK_ADAY_INDEKSI = "ix_karar_talebi_acik_aday"
ACIK_KESIN_INDEKSI = "ix_karar_talebi_acik_kesin"

TABLOLAR = (
    "nesne_mukerrerlik_sarti",
    "aday_nesne_mukerrerlik_sarti",
    "karar_talebi",
    "aday_nesne_cozumlemesi",
    "nesne_birlesimi",
    "denetim_izi",
)

INDEKSLER: tuple[tuple[str, str, str], ...] = (
    (
        "ix_nesne_mukerrerlik_sarti_ozellik_tanimi_id",
        "nesne_mukerrerlik_sarti",
        "ozellik_tanimi_id",
    ),
    (
        "ix_aday_nesne_mukerrerlik_sarti_ozellik_tanimi_id",
        "aday_nesne_mukerrerlik_sarti",
        "ozellik_tanimi_id",
    ),
    ("ix_karar_talebi_islem_paketi_id", "karar_talebi", "islem_paketi_id"),
    ("ix_karar_talebi_durum", "karar_talebi", "durum"),
    ("ix_karar_talebi_hedef_nesne_id", "karar_talebi", "hedef_nesne_id"),
    ("ix_aday_nesne_cozumlemesi_nesne_id", "aday_nesne_cozumlemesi", "nesne_id"),
    ("ix_nesne_birlesimi_hedef_nesne_id", "nesne_birlesimi", "hedef_nesne_id"),
    ("ix_denetim_izi_olay", "denetim_izi", "olay"),
    ("ix_denetim_izi_islem_paketi_id", "denetim_izi", "islem_paketi_id"),
    ("ix_denetim_izi_karar_talebi_id", "denetim_izi", "karar_talebi_id"),
    ("ix_denetim_izi_nesne_id", "denetim_izi", "nesne_id"),
)


def upgrade() -> None:
    op.create_table(
        "nesne_mukerrerlik_sarti",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nesne_id", sa.Integer(), nullable=False),
        sa.Column("nesne_turu_id", sa.Integer(), nullable=False),
        sa.Column("ozellik_tanimi_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("pk_nesne_mukerrerlik_sarti")),
        sa.ForeignKeyConstraint(
            ["nesne_id", "nesne_turu_id"],
            ["nesne.id", "nesne.nesne_turu_id"],
            name=conv("fk_nesne_mukerrerlik_sarti_nesne_id_nesne_turu_id_nesne"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ozellik_tanimi_id", "nesne_turu_id"],
            ["ozellik_tanimi.id", "ozellik_tanimi.nesne_turu_id"],
            name=conv(
                "fk_nesne_mukerrerlik_sarti_ozellik_tanimi_id_nesne_turu_id_"
                "ozellik_tanimi"
            ),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "nesne_id",
            "ozellik_tanimi_id",
            name=conv("uq_nesne_mukerrerlik_sarti_nesne_id_ozellik_tanimi_id"),
        ),
    )
    op.create_table(
        "aday_nesne_mukerrerlik_sarti",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("aday_nesne_id", sa.Integer(), nullable=False),
        sa.Column("nesne_turu_id", sa.Integer(), nullable=False),
        sa.Column("ozellik_tanimi_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("pk_aday_nesne_mukerrerlik_sarti")),
        sa.ForeignKeyConstraint(
            ["aday_nesne_id", "nesne_turu_id"],
            ["aday_nesne.id", "aday_nesne.nesne_turu_id"],
            name=conv(
                "fk_aday_nesne_mukerrerlik_sarti_aday_nesne_id_nesne_turu_id_aday_nesne"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ozellik_tanimi_id", "nesne_turu_id"],
            ["ozellik_tanimi.id", "ozellik_tanimi.nesne_turu_id"],
            name=conv(
                "fk_aday_nesne_mukerrerlik_sarti_ozellik_tanimi_id_nesne_turu_id_"
                "ozellik_tanimi"
            ),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "aday_nesne_id",
            "ozellik_tanimi_id",
            name=conv(
                "uq_aday_nesne_mukerrerlik_sarti_aday_nesne_id_ozellik_tanimi_id"
            ),
        ),
    )
    op.create_table(
        "karar_talebi",
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
    )
    op.create_table(
        "aday_nesne_cozumlemesi",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("aday_nesne_id", sa.Integer(), nullable=False),
        sa.Column("nesne_turu_id", sa.Integer(), nullable=False),
        sa.Column("nesne_id", sa.Integer(), nullable=False),
        sa.Column("karar_talebi_id", sa.Integer(), nullable=False),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.Column("aktor_turu", sa.String(), nullable=False),
        sa.Column("aktor_kimligi", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("pk_aday_nesne_cozumlemesi")),
        sa.ForeignKeyConstraint(
            ["aday_nesne_id", "nesne_turu_id"],
            ["aday_nesne.id", "aday_nesne.nesne_turu_id"],
            name=conv(
                "fk_aday_nesne_cozumlemesi_aday_nesne_id_nesne_turu_id_aday_nesne"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["nesne_id", "nesne_turu_id"],
            ["nesne.id", "nesne.nesne_turu_id"],
            name=conv("fk_aday_nesne_cozumlemesi_nesne_id_nesne_turu_id_nesne"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["karar_talebi_id"],
            ["karar_talebi.id"],
            name=conv("fk_aday_nesne_cozumlemesi_karar_talebi_id_karar_talebi"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "aday_nesne_id", name=conv("uq_aday_nesne_cozumlemesi_aday_nesne_id")
        ),
        sa.UniqueConstraint(
            "karar_talebi_id", name=conv("uq_aday_nesne_cozumlemesi_karar_talebi_id")
        ),
    )
    op.create_table(
        "nesne_birlesimi",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kaynak_nesne_id", sa.Integer(), nullable=False),
        sa.Column("hedef_nesne_id", sa.Integer(), nullable=False),
        sa.Column("nesne_turu_id", sa.Integer(), nullable=False),
        sa.Column("karar_talebi_id", sa.Integer(), nullable=False),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.Column("aktor_turu", sa.String(), nullable=False),
        sa.Column("aktor_kimligi", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("pk_nesne_birlesimi")),
        sa.ForeignKeyConstraint(
            ["kaynak_nesne_id", "nesne_turu_id"],
            ["nesne.id", "nesne.nesne_turu_id"],
            name=conv("fk_nesne_birlesimi_kaynak_nesne_id_nesne_turu_id_nesne"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hedef_nesne_id", "nesne_turu_id"],
            ["nesne.id", "nesne.nesne_turu_id"],
            name=conv("fk_nesne_birlesimi_hedef_nesne_id_nesne_turu_id_nesne"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["karar_talebi_id"],
            ["karar_talebi.id"],
            name=conv("fk_nesne_birlesimi_karar_talebi_id_karar_talebi"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "kaynak_nesne_id", name=conv("uq_nesne_birlesimi_kaynak_nesne_id")
        ),
        sa.UniqueConstraint(
            "karar_talebi_id", name=conv("uq_nesne_birlesimi_karar_talebi_id")
        ),
        sa.CheckConstraint(
            "kaynak_nesne_id <> hedef_nesne_id",
            name=conv("ck_nesne_birlesimi_kaynak_hedeften_farkli"),
        ),
    )
    op.create_table(
        "denetim_izi",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("olay", sa.String(), nullable=False),
        sa.Column("olay_zamani", sa.DateTime(), nullable=False),
        sa.Column("aktor_turu", sa.String(), nullable=False),
        sa.Column("aktor_kimligi", sa.String(), nullable=False),
        sa.Column("islem_paketi_id", sa.Integer(), nullable=True),
        sa.Column("karar_talebi_id", sa.Integer(), nullable=True),
        sa.Column("nesne_id", sa.Integer(), nullable=True),
        sa.Column("ikincil_nesne_id", sa.Integer(), nullable=True),
        sa.Column("aday_nesne_id", sa.Integer(), nullable=True),
        sa.Column("ozellik_tanimi_id", sa.Integer(), nullable=True),
        sa.Column("gerekce", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=conv("pk_denetim_izi")),
        sa.ForeignKeyConstraint(
            ["islem_paketi_id"],
            ["islem_paketi.id"],
            name=conv("fk_denetim_izi_islem_paketi_id_islem_paketi"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["karar_talebi_id"],
            ["karar_talebi.id"],
            name=conv("fk_denetim_izi_karar_talebi_id_karar_talebi"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["nesne_id"],
            ["nesne.id"],
            name=conv("fk_denetim_izi_nesne_id_nesne"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ikincil_nesne_id"],
            ["nesne.id"],
            name=conv("fk_denetim_izi_ikincil_nesne_id_nesne"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ozellik_tanimi_id"],
            ["ozellik_tanimi.id"],
            name=conv("fk_denetim_izi_ozellik_tanimi_id_ozellik_tanimi"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(OLAY_KOSULU, name=conv("ck_denetim_izi_olay_gecerli")),
        sa.CheckConstraint(
            AKTOR_TURU_KOSULU, name=conv("ck_denetim_izi_aktor_turu_gecerli")
        ),
        sa.CheckConstraint(
            "length(aktor_kimligi) > 0", name=conv("ck_denetim_izi_aktor_kimligi_dolu")
        ),
    )
    for ad, tablo, sutun in INDEKSLER:
        op.create_index(ad, tablo, [sutun])
    # Kısmi benzersiz indeksler: aynı çift için ikinci bir AÇIK talep açılamaz.
    op.create_index(
        ACIK_ADAY_INDEKSI,
        "karar_talebi",
        ["aday_nesne_id", "hedef_nesne_id"],
        unique=True,
        sqlite_where=sa.text("durum = 'acik' AND aday_nesne_id IS NOT NULL"),
    )
    op.create_index(
        ACIK_KESIN_INDEKSI,
        "karar_talebi",
        ["kaynak_nesne_id", "hedef_nesne_id"],
        unique=True,
        sqlite_where=sa.text("durum = 'acik' AND kaynak_nesne_id IS NOT NULL"),
    )


def downgrade() -> None:
    baglanti = op.get_bind()
    dolu = [
        tablo
        for tablo in TABLOLAR
        if baglanti.execute(sa.text(f"SELECT count(*) FROM {tablo}")).scalar_one()
    ]
    if dolu:
        raise RuntimeError(
            "göç 0008 geri alınamaz: satır taşıyan tablo var "
            f"({', '.join(dolu)}); veri sessizce silinmez."
        )
    op.drop_index(ACIK_KESIN_INDEKSI, table_name="karar_talebi")
    op.drop_index(ACIK_ADAY_INDEKSI, table_name="karar_talebi")
    for ad, tablo, _ in reversed(INDEKSLER):
        op.drop_index(ad, table_name=tablo)
    for tablo in reversed(TABLOLAR):
        op.drop_table(tablo)
