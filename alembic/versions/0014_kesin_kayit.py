"""Kesin kayıt (Aşama 4.7/2): kayıt, kayıt alanı, kayıt-nesne bağı.

Üç yeni tablo (şema ``kayit_tablolari`` ile birebirdir; testte ORM
metadata'sıyla karşılaştırılır). Satır yazılmaz.

* ``kayit``: türü ve tanım sürümü bileşik dış anahtarla ``kayit_turu (id,
  tanim_surumu_id)`` çiftine bağlı; ``islem_paketi_id`` zorunlu ve
  ``okuma_id`` üzerinden hem pakete hem (verilmişse) kaynağa kilitli. Durum
  sütunu **yoktur**: satırın varlığı kesinliktir.
* ``kayit_alani``: iki bileşik dış anahtar aynı ``kayit_turu_id`` üzerinden,
  yani başka kayıt türünün alanı yazılamaz; ``(kayit_id,
  kayit_alani_tanimi_id)`` benzersiz.
* ``kayit_nesne``: rolsüz çoktan çoğa bağ; ``(kayit_id, nesne_id)`` benzersiz.

``denetim_izi`` yalnız ``kayit_id`` sütunu ve iki yeni olay adı
(``kayit_olusturuldu``, ``kayit_baglari_devredildi``) için yeniden kurulur;
kalıp ``0012``deki ile aynıdır (tabloya dış anahtarla bağlanan başka tablo
yoktur, satırlar kopyalanır, indeksler yeniden kurulur).

Geri alma üç tabloyu ters sırada düşürür ve denetim izini eski şemasına
döndürür; kayıt satırı ya da yeni olay adını taşıyan iz satırı varsa geri alma
uygulanmaz ve hata verir (``0005``–``0012`` kalıbı: veri sessizce silinmez).

Sürüm: 0014
Önceki: 0013
Oluşturma: 2026-09-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql.elements import conv

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KAYIT_TABLOLARI: tuple[str, ...] = ("kayit", "kayit_alani", "kayit_nesne")

DENETIM = "denetim_izi"
DENETIM_YENI = "denetim_izi_yeni"

OLAYLAR_0012: tuple[str, ...] = (
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
    "karar_talebi_pakete_baglandi",
    "karar_talebi_kokeni_devredildi",
)
YENI_OLAYLAR: tuple[str, ...] = ("kayit_olusturuldu", "kayit_baglari_devredildi")
OLAYLAR_0014: tuple[str, ...] = (*OLAYLAR_0012, *YENI_OLAYLAR)

AKTOR_TURU_KOSULU = "aktor_turu IN ('kullanici', 'ajan', 'sistem')"

DENETIM_ESKI_SUTUNLAR = (
    "id, olay, olay_zamani, aktor_turu, aktor_kimligi, islem_paketi_id, "
    "karar_talebi_id, nesne_id, ikincil_nesne_id, aday_nesne_id, "
    "ozellik_tanimi_id, gerekce"
)

DENETIM_INDEKSLERI: tuple[tuple[str, str], ...] = (
    ("ix_denetim_izi_olay", "olay"),
    ("ix_denetim_izi_islem_paketi_id", "islem_paketi_id"),
    ("ix_denetim_izi_karar_talebi_id", "karar_talebi_id"),
    ("ix_denetim_izi_nesne_id", "nesne_id"),
)
KAYIT_INDEKSI = ("ix_denetim_izi_kayit_id", "kayit_id")


def _olay_kosulu(olaylar: Sequence[str]) -> str:
    return "olay IN ({})".format(", ".join(f"'{o}'" for o in olaylar))


def _kayit_tablolarini_kur() -> None:
    op.create_table(
        "kayit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kayit_turu_id", sa.Integer(), nullable=False),
        sa.Column("tanim_surumu_id", sa.Integer(), nullable=False),
        sa.Column("islem_paketi_id", sa.Integer(), nullable=False),
        sa.Column("okuma_id", sa.Integer(), nullable=False),
        sa.Column("kaynak_id", sa.Integer(), nullable=True),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("pk_kayit")),
        sa.ForeignKeyConstraint(
            ["kayit_turu_id", "tanim_surumu_id"],
            ["kayit_turu.id", "kayit_turu.tanim_surumu_id"],
            name=conv("fk_kayit_kayit_turu_id_tanim_surumu_id_kayit_turu"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["islem_paketi_id", "okuma_id"],
            ["islem_paketi.id", "islem_paketi.okuma_id"],
            name=conv("fk_kayit_islem_paketi_id_okuma_id_islem_paketi"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["kaynak_id", "okuma_id"],
            ["kaynak.id", "kaynak.okuma_id"],
            name=conv("fk_kayit_kaynak_id_okuma_id_kaynak"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "id", "kayit_turu_id", name=conv("uq_kayit_id_kayit_turu_id")
        ),
    )
    op.create_index("ix_kayit_kayit_turu_id", "kayit", ["kayit_turu_id"])
    op.create_index("ix_kayit_tanim_surumu_id", "kayit", ["tanim_surumu_id"])
    op.create_index("ix_kayit_islem_paketi_id", "kayit", ["islem_paketi_id"])
    op.create_index("ix_kayit_kaynak_id", "kayit", ["kaynak_id"])

    op.create_table(
        "kayit_alani",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kayit_id", sa.Integer(), nullable=False),
        sa.Column("kayit_turu_id", sa.Integer(), nullable=False),
        sa.Column("kayit_alani_tanimi_id", sa.Integer(), nullable=False),
        sa.Column("deger", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("pk_kayit_alani")),
        sa.ForeignKeyConstraint(
            ["kayit_id", "kayit_turu_id"],
            ["kayit.id", "kayit.kayit_turu_id"],
            name=conv("fk_kayit_alani_kayit_id_kayit_turu_id_kayit"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["kayit_alani_tanimi_id", "kayit_turu_id"],
            ["kayit_alani_tanimi.id", "kayit_alani_tanimi.kayit_turu_id"],
            name=conv(
                "fk_kayit_alani_kayit_alani_tanimi_id_kayit_turu_id_kayit_alani_tanimi"
            ),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "kayit_id",
            "kayit_alani_tanimi_id",
            name=conv("uq_kayit_alani_kayit_id_kayit_alani_tanimi_id"),
        ),
    )
    op.create_index(
        "ix_kayit_alani_kayit_alani_tanimi_id", "kayit_alani", ["kayit_alani_tanimi_id"]
    )

    op.create_table(
        "kayit_nesne",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kayit_id", sa.Integer(), nullable=False),
        sa.Column("nesne_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=conv("pk_kayit_nesne")),
        sa.ForeignKeyConstraint(
            ["kayit_id"],
            ["kayit.id"],
            name=conv("fk_kayit_nesne_kayit_id_kayit"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["nesne_id"],
            ["nesne.id"],
            name=conv("fk_kayit_nesne_nesne_id_nesne"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "kayit_id", "nesne_id", name=conv("uq_kayit_nesne_kayit_id_nesne_id")
        ),
    )
    op.create_index("ix_kayit_nesne_nesne_id", "kayit_nesne", ["nesne_id"])


def _denetim_izini_kur(ad: str, olaylar: Sequence[str], kayit_sutunu: bool) -> None:
    """``denetim_izi`` şeması; ``kayit_sutunu`` 0014 (True) ya da 0013 (False).

    Kısıt adları her zaman son tablo adına göredir (``conv`` ile açıkça
    verilir); tablo yeniden adlandırıldığında adlar doğru kalır.
    """
    kayit_sutunlari = (
        [sa.Column("kayit_id", sa.Integer(), nullable=True)] if kayit_sutunu else []
    )
    kayit_anahtarlari = (
        [
            sa.ForeignKeyConstraint(
                ["kayit_id"],
                ["kayit.id"],
                name=conv("fk_denetim_izi_kayit_id_kayit"),
                ondelete="RESTRICT",
            )
        ]
        if kayit_sutunu
        else []
    )
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
        *kayit_sutunlari,
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
        *kayit_anahtarlari,
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


def _denetim_izini_yeniden_kur(olaylar: Sequence[str], kayit_sutunu: bool) -> None:
    """Denetim izini verilen olay listesi ve sütun düzeniyle yeniden kurar;
    satırlar korunur (``kayit_id`` geri almada düşer, başka veri silinmez)."""
    _denetim_izini_kur(DENETIM_YENI, olaylar, kayit_sutunu)
    op.execute(
        f"INSERT INTO {DENETIM_YENI} ({DENETIM_ESKI_SUTUNLAR}) "
        f"SELECT {DENETIM_ESKI_SUTUNLAR} FROM {DENETIM}"
    )
    eski_indeksler = (
        (*DENETIM_INDEKSLERI, KAYIT_INDEKSI) if not kayit_sutunu else DENETIM_INDEKSLERI
    )
    for ad, _sutun in eski_indeksler:
        op.drop_index(ad, table_name=DENETIM)
    op.drop_table(DENETIM)
    op.rename_table(DENETIM_YENI, DENETIM)
    yeni_indeksler = (
        (*DENETIM_INDEKSLERI, KAYIT_INDEKSI) if kayit_sutunu else DENETIM_INDEKSLERI
    )
    for ad, sutun in yeni_indeksler:
        op.create_index(ad, DENETIM, [sutun])


def upgrade() -> None:
    _kayit_tablolarini_kur()
    _denetim_izini_yeniden_kur(OLAYLAR_0014, kayit_sutunu=True)


def downgrade() -> None:
    baglanti = op.get_bind()
    for tablo in KAYIT_TABLOLARI:
        kalan = baglanti.execute(sa.text(f"SELECT count(*) FROM {tablo}")).scalar_one()
        if kalan:
            raise RuntimeError(
                f"{tablo}: {kalan} satır var; geri alma kesin kayıt verisini "
                "silerdi. Önce bu satırların ne olacağına karar verin."
            )
    kalan_iz = baglanti.execute(
        sa.text(
            f"SELECT count(*) FROM {DENETIM} WHERE olay IN "
            "('kayit_olusturuldu', 'kayit_baglari_devredildi')"
        )
    ).scalar_one()
    if kalan_iz:
        raise RuntimeError(
            f"{DENETIM}: {kalan_iz} satır 0014 ile gelen olay adlarını taşıyor; "
            "geri alma bu satırları anlamsız kılardı. Denetim izi sessizce "
            "değiştirilmez: önce bu satırların ne olacağına karar verin."
        )
    _denetim_izini_yeniden_kur(OLAYLAR_0012, kayit_sutunu=False)
    for tablo in reversed(KAYIT_TABLOLARI):
        op.drop_table(tablo)
