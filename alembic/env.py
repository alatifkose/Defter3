"""Alembic ortamı: veritabanı yolu yalnız merkezi ayarlardan.

Komut satırından (``uv run alembic upgrade head``) çalışınca ``defteriki.ayarlar``
ortam değişkenlerini okur, ``Ayarlar.veritabani_yolu`` için engine kurar ve
göçleri uygular; yalnız veritabanı dosyasının dizinini açar, başka dizin
oluşturmaz. Süreç içinden (``defteriki.cekirdek.gocler.semayi_yukselt``)
çağrılınca hazır bağlantıyı (``config.attributes["connection"]``) kullanır;
ayar okumaz. ``fileConfig`` çağrılmaz; stdout'a hiçbir şey yazılmaz.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import Connection

from defteriki.ayarlar import ayarlari_yukle
from defteriki.cekirdek import tanim_tablolari
from defteriki.cekirdek.veritabani import TabloTabani, motor_olustur, veritabani_url

yapilandirma = context.config
hedef_metadata = TabloTabani.metadata
# Tablo modülleri import edilmeden metadata boştur; autogenerate ve şema
# karşılaştırması için tanım tabloları burada kayda girer.
assert set(tanim_tablolari.TANIM_TABLOLARI) <= set(hedef_metadata.tables)


def _gocleri_calistir(baglanti: Connection) -> None:
    context.configure(
        connection=baglanti,
        target_metadata=hedef_metadata,
        render_as_batch=True,  # SQLite: ALTER TABLE yerine tablo yeniden kurulur
    )
    with context.begin_transaction():
        context.run_migrations()


def cevrimici() -> None:
    hazir = yapilandirma.attributes.get("connection")
    if isinstance(hazir, Connection):
        _gocleri_calistir(hazir)
        return
    ayarlar = ayarlari_yukle()
    ayarlar.veritabani_yolu.parent.mkdir(parents=True, exist_ok=True)
    motor = motor_olustur(ayarlar.veritabani_yolu)
    try:
        with motor.begin() as baglanti:
            _gocleri_calistir(baglanti)
    finally:
        motor.dispose()


def cevrimdisi() -> None:
    """``--sql`` kipi: SQL üretir, veritabanına dokunmaz."""
    url = veritabani_url(ayarlari_yukle().veritabani_yolu)
    context.configure(
        url=url.render_as_string(hide_password=False),
        target_metadata=hedef_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    cevrimdisi()
else:
    cevrimici()
