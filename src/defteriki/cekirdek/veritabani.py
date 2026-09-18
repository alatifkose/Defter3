"""Genel veritabanı altyapısı (Aşama 4.1): bağlantı, oturum, işlem sınırı.

Bu modül hiçbir domain'i bilmez ve hiçbir tablo tanımlamaz. Sağladıkları:

* ``TabloTabani``: bütün tabloların türeyeceği ortak taban ve tek ``metadata``
  (isimli kısıt kalıbıyla; SQLite'ta Alembic ``batch`` kipi için gerekir).
* ``veritabani_url``: SQLite bağlantı adresi. Yol yalnız çağıranın verdiği
  **mutlak** yoldur (uygulamada ``Ayarlar.veritabani_yolu``); çalışma
  dizininden türetilmez, metin birleştirilmez, SQLAlchemy ``URL`` ile üretilir.
* ``motor_olustur``: engine. Modül import edildiğinde engine kurulmaz; engine
  kurulmak diske dokunmaz, dosya ilk bağlantıda oluşur.
* SQLite bağlantı politikası tek yerde: her bağlantıda ``foreign_keys=ON`` ve
  ``journal_mode=WAL`` (``BAGLANTI_PRAGMALARI``).
* ``Veritabani.islem``: işlem sınırı. Bir iş = bir kısa ömürlü oturum = bir
  transaction. Normal çıkışta ``commit``, istisnada ``rollback`` ve istisna
  yeniden yükselir, her durumda oturum kapanır. Model ya da ileride gelecek
  depo kodu kendi başına ``commit`` etmez; sahip bu bağlam yöneticisidir.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, MetaData, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

SURUCU = "sqlite+pysqlite"

KISIT_ADLANDIRMA = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
"""Kısıt adları tablo ve sütunlardan türer; SQLite'ta adsız kısıt değiştirilemez."""

BAGLANTI_PRAGMALARI: tuple[tuple[str, str], ...] = (
    ("foreign_keys", "ON"),
    ("journal_mode", "WAL"),
)
"""Her yeni bağlantıda sırayla uygulanır; ``journal_mode`` dosyada kalıcıdır,
``foreign_keys`` bağlantı başınadır ve her seferinde açılmalıdır."""


class TabloTabani(DeclarativeBase):
    """Bütün tabloların ortak tabanı; tek ``metadata`` buradadır."""

    metadata = MetaData(naming_convention=KISIT_ADLANDIRMA)


def veritabani_url(yol: Path) -> URL:
    """Mutlak dosya yolundan SQLite bağlantı adresi; göreli yol reddedilir."""
    if not yol.is_absolute():
        raise ValueError(f"veritabanı yolu mutlak olmalı: {yol}")
    return URL.create(SURUCU, database=str(yol))


def motor_olustur(yol: Path) -> Engine:
    """Engine kurar; diske dokunmaz. Bağlantı politikası her bağlantıda uygulanır."""
    motor = create_engine(veritabani_url(yol))
    event.listen(motor, "connect", _baglantiyi_ayarla)
    return motor


def _baglantiyi_ayarla(
    dbapi_baglantisi: DBAPIConnection, _kayit: ConnectionPoolEntry
) -> None:
    imlec = dbapi_baglantisi.cursor()
    try:
        for ad, deger in BAGLANTI_PRAGMALARI:
            imlec.execute(f"PRAGMA {ad}={deger}")
    finally:
        imlec.close()


class Veritabani:
    """Bir SQLite dosyasına bağlı engine ve işlem sınırı."""

    def __init__(self, yol: Path) -> None:
        self.yol = yol
        self.motor = motor_olustur(yol)
        self._oturum_ac = sessionmaker(bind=self.motor, expire_on_commit=False)

    @contextmanager
    def islem(self) -> Generator[Session, None, None]:
        """Bir iş = bir transaction: çıkışta commit, istisnada rollback + yeniden
        yükseltme, her durumda oturum kapanır."""
        oturum = self._oturum_ac()
        try:
            yield oturum
            oturum.commit()
        except BaseException:
            oturum.rollback()
            raise
        finally:
            oturum.close()

    def kapat(self) -> None:
        """Bağlantı havuzunu boşaltır; dosya kilidi bırakılır (Windows'ta gerekli)."""
        self.motor.dispose()
