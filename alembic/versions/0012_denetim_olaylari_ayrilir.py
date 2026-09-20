"""Denetim izinde "talep açıldı" yalnız gerçekten açılanı anlatsın.

2026-09-20 bağımsız denetim, bulgu 2. ``karar_talebi_acildi`` olayı üç yerde
yazılıyordu ve yalnız biri gerçekten talep açıyordu:

* ``_talep_ac`` — talep açıldı (doğru kullanım);
* ``_talebi_pakete_bagla`` — mevcut talebe bir paket daha bağlandı;
* ``_kokeni_devret`` — mevcut talebin bağımsız kökeni devredildi.

Sonuç: denetim izinden "kaç karar talebi açıldı" diye saymak yanlış sonuç
veriyordu. Altıncı tur köken devrini mevcut açık sorulara da uyguladığı için
sapma büyüdü. İki yeni olay adı eklenir ve o iki yer kendi adını kullanır:

* ``karar_talebi_pakete_baglandi``
* ``karar_talebi_kokeni_devredildi``

Mevcut satırlar **dönüştürülmez**: geçmişte yazılmış ``karar_talebi_acildi``
satırlarının hangisinin gerçek açılış olduğunu geriye dönük bilmek için
gerekçe metnini yorumlamak gerekirdi; denetim izi yorumla değiştirilmez.
Ayrım bu göçten sonra yazılan satırlarda geçerlidir.

``denetim_izi`` yalnız kontrol kısıtı yüzünden yeniden kurulur. Tabloya
**dış anahtarla bağlanan başka tablo yoktur** (kendisi dört tabloya bağlanır),
bu yüzden ``0003`` / ``0011``in taşıma tablosu kalıbına gerek kalmaz: yeni
tablo kurulur, satırlar kopyalanır, eski tablo düşürülür, yeni tablo eski adı
alır, indeksler yeniden kurulur. Alembic ``batch`` kipi bu projede ana
tablolarda kullanılmaz (bkz. ``0003``).

Geri alma dar listeyi geri koyar. İki yeni olaydan satır varsa geri alma
uygulanmaz ve hata verir; denetim izi sessizce silinmez.

Sürüm: 0012
Önceki: 0011
Oluşturma: 2026-09-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql.elements import conv

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLO = "denetim_izi"
YENI_TABLO = "denetim_izi_yeni"

OLAYLAR_0011: tuple[str, ...] = (
    "mukerrerlik_sarti_belirlendi",
    "mukerrerlik_suphesi_acildi",
    "karar_talebi_acildi",
    "kullanici_karari_verildi",
    "nesne_ayri_kabul_edildi",
    "nesne_birlestirildi",
    "aday_nesneye_cozumlendi",
    "paket_beklemeye_gecti",
    "paket_yeniden_calisiyor",
    "karar_talebi_gecersiz_kaldi",
    "birlesim_yeniden_baglandi",
)
YENI_OLAYLAR: tuple[str, ...] = (
    "karar_talebi_pakete_baglandi",
    "karar_talebi_kokeni_devredildi",
)
OLAYLAR_0012: tuple[str, ...] = (*OLAYLAR_0011, *YENI_OLAYLAR)

AKTOR_TURU_KOSULU = "aktor_turu IN ('kullanici', 'ajan', 'sistem')"

SUTUNLAR = (
    "id, olay, olay_zamani, aktor_turu, aktor_kimligi, islem_paketi_id, "
    "karar_talebi_id, nesne_id, ikincil_nesne_id, aday_nesne_id, "
    "ozellik_tanimi_id, gerekce"
)

INDEKSLER: tuple[tuple[str, str], ...] = (
    ("ix_denetim_izi_olay", "olay"),
    ("ix_denetim_izi_islem_paketi_id", "islem_paketi_id"),
    ("ix_denetim_izi_karar_talebi_id", "karar_talebi_id"),
    ("ix_denetim_izi_nesne_id", "nesne_id"),
)


def _olay_kosulu(olaylar: Sequence[str]) -> str:
    return "olay IN ({})".format(", ".join(f"'{o}'" for o in olaylar))


def _tabloyu_kur(ad: str, olaylar: Sequence[str]) -> None:
    """``denetim_izi`` şemasını verilen adla ve verilen olay listesiyle kurar.

    Kısıt adları her zaman son tablo adına göredir (``conv`` ile açıkça
    verilir); tablo yeniden adlandırıldığında adlar doğru kalır.
    """
    op.create_table(
        ad,
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
        sa.CheckConstraint(
            _olay_kosulu(olaylar), name=conv("ck_denetim_izi_olay_gecerli")
        ),
        sa.CheckConstraint(
            AKTOR_TURU_KOSULU, name=conv("ck_denetim_izi_aktor_turu_gecerli")
        ),
        sa.CheckConstraint(
            "length(aktor_kimligi) > 0", name=conv("ck_denetim_izi_aktor_kimligi_dolu")
        ),
    )


def _yeniden_kur(olaylar: Sequence[str]) -> None:
    """Tabloyu verilen olay listesiyle yeniden kurar; satırlar korunur."""
    _tabloyu_kur(YENI_TABLO, olaylar)
    op.execute(f"INSERT INTO {YENI_TABLO} ({SUTUNLAR}) SELECT {SUTUNLAR} FROM {TABLO}")
    for ad, _sutun in INDEKSLER:
        op.drop_index(ad, table_name=TABLO)
    op.drop_table(TABLO)
    op.rename_table(YENI_TABLO, TABLO)
    for ad, sutun in INDEKSLER:
        op.create_index(ad, TABLO, [sutun])


def upgrade() -> None:
    _yeniden_kur(OLAYLAR_0012)


def downgrade() -> None:
    kalan = (
        op.get_bind()
        .execute(
            sa.text(
                f"SELECT count(*) FROM {TABLO} WHERE olay IN "
                "('karar_talebi_pakete_baglandi', 'karar_talebi_kokeni_devredildi')"
            )
        )
        .scalar_one()
    )
    if kalan:
        raise RuntimeError(
            f"{TABLO}: {kalan} satır 0012 ile gelen olay adlarını taşıyor; geri "
            "alma bu satırları anlamsız kılardı. Denetim izi sessizce "
            "değiştirilmez: önce bu satırların ne olacağına karar verin."
        )
    _yeniden_kur(OLAYLAR_0011)
