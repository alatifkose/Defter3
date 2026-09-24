"""Genel veritabanı altyapısı (Aşama 4.1): bağlantı, oturum, işlem sınırı.

Bu modül hiçbir domain'i bilmez ve hiçbir tablo tanımlamaz. Sağladıkları:

* ``TabloTabani``: bütün tabloların türeyeceği ortak taban ve tek ``metadata``
  (isimli kısıt kalıbıyla).
* ``veritabani_url``: SQLite bağlantı adresi. Yol yalnız çağıranın verdiği
  **mutlak** yoldur (uygulamada ``Ayarlar.veritabani_yolu``); çalışma
  dizininden türetilmez, metin birleştirilmez, SQLAlchemy ``URL`` ile üretilir.
* ``motor_olustur``: engine. Modül import edildiğinde engine kurulmaz; engine
  kurulmak diske dokunmaz, dosya ilk bağlantıda oluşur.
* SQLite bağlantı politikası tek yerde: her bağlantıda ``foreign_keys=ON`` ve
  ``journal_mode=WAL`` (``BAGLANTI_PRAGMALARI``).
* Transaction kontrolü: ``sqlite3`` modülünün Python 3.12+ ``autocommit=False``
  kipi (PEP 249). Eski kipte ``sqlite3`` yalnız DML öncesi örtük ``BEGIN``
  açar, DDL (``CREATE TABLE``) transaction dışında kalır ve geri alınamaz;
  yeni kipte bağlantı açılır açılmaz ve her ``commit``/``rollback`` sonrası
  ertelenmiş bir transaction başlar, DDL dahil her şey içinde kalır. Bu
  yüzden yarıda düşen bir yapı değişikliği (DDL) de geri alınır.
  PRAGMA'lar transaction içinde çalışmaz (``journal_mode`` değiştirilemez,
  ``foreign_keys`` sessizce yok sayılır); bağlantı olayında ``autocommit``
  geçici olarak açılıp PRAGMA'lar uygulanır, sonra kapatılır.
* ``Veritabani.islem``: işlem sınırı. Bir iş = bir kısa ömürlü oturum = bir
  transaction. Normal çıkışta ``commit``, istisnada ``rollback`` ve istisna
  yeniden yükselir, her durumda oturum kapanır. Model ya da ileride gelecek
  depo kodu kendi başına ``commit`` etmez; sahip bu bağlam yöneticisidir.
* ``Veritabani.islem_yabanci_anahtar_denetimsiz``: tabloyu yeniden kurma
  gibi, SQLite'ın resmî tarifi gereği ``foreign_keys=OFF`` ile yürümesi
  gereken işler için işlem sınırı. Denetim yalnız bu bağlantıda ve yalnız iş
  süresince kapanır; ``commit`` öncesi ``PRAGMA foreign_key_check`` çalışır,
  bir ihlal varsa iş geri alınır. Çıkışta (başarı, hata ya da ihlal) denetim
  aynı bağlantıda yeniden açılır; havuza denetimsiz bağlantı dönmez.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, MetaData, create_engine, event, text
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

BAGLANTI_ARGUMANLARI: dict[str, object] = {"autocommit": False}
"""``sqlite3.connect`` argümanları: modern transaction kontrolü (DDL dahil)."""


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
    motor = create_engine(veritabani_url(yol), connect_args=BAGLANTI_ARGUMANLARI)
    event.listen(motor, "connect", _baglantiyi_ayarla)
    return motor


def _baglantiyi_ayarla(
    dbapi_baglantisi: DBAPIConnection, _kayit: ConnectionPoolEntry
) -> None:
    """Yeni DBAPI bağlantısında bağlantı politikasını uygular."""
    _pragmalari_transaction_disinda_uygula(dbapi_baglantisi, BAGLANTI_PRAGMALARI)


def _pragmalari_transaction_disinda_uygula(
    dbapi_baglantisi: DBAPIConnection, pragmalar: tuple[tuple[str, str], ...]
) -> None:
    """PRAGMA'ları transaction dışında uygular.

    ``autocommit=False`` kipinde bağlantı açık bir (ertelenmiş) transaction ile
    gelir; PRAGMA'lar orada etkisiz kalır. ``autocommit`` geçici olarak açılır
    (boş transaction biter), PRAGMA'lar çalışır, sonra kapatılır (yeni
    ertelenmiş transaction başlar). Yalnız henüz hiçbir şey yazılmamış bir
    bağlantıda çağrılmalıdır; bekleyen bir transaction varsa commit edilirdi.
    """
    dbapi_baglantisi.autocommit = True
    try:
        imlec = dbapi_baglantisi.cursor()
        try:
            for ad, deger in pragmalar:
                imlec.execute(f"PRAGMA {ad}={deger}")
        finally:
            imlec.close()
    finally:
        dbapi_baglantisi.autocommit = False


class YabanciAnahtarIhlali(Exception):
    """Denetimsiz iş sonunda ``PRAGMA foreign_key_check`` ihlal buldu; iş geri
    alındı."""


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

    @contextmanager
    def islem_yabanci_anahtar_denetimsiz(self) -> Generator[Session, None, None]:
        """``foreign_keys=OFF`` ile bir iş = bir transaction (SQLite'ın tablo
        yeniden kurma tarifi). Denetim yalnız bu bağlantıda, yalnız iş
        süresince kapalıdır; ``commit`` öncesi ``PRAGMA foreign_key_check``
        çalışır, ihlal varsa ``YabanciAnahtarIhlali`` ile geri alınır. Her
        çıkışta denetim aynı bağlantıda yeniden açılır."""
        oturum = self._oturum_ac()
        try:
            ham = oturum.connection().connection.dbapi_connection
            if ham is None:  # pragma: no cover - havuz her zaman bağlantı verir
                raise RuntimeError("DBAPI bağlantısı alınamadı")
            _pragmalari_transaction_disinda_uygula(ham, (("foreign_keys", "OFF"),))
            try:
                yield oturum
                ihlaller = oturum.execute(text("PRAGMA foreign_key_check")).all()
                if ihlaller:
                    raise YabanciAnahtarIhlali(
                        f"{len(ihlaller)} yabancı anahtar ihlali: "
                        + ", ".join(f"{i[0]}(rowid {i[1]}) -> {i[2]}" for i in ihlaller)
                    )
                oturum.commit()
            except BaseException:
                oturum.rollback()
                raise
            finally:
                _pragmalari_transaction_disinda_uygula(ham, (("foreign_keys", "ON"),))
        finally:
            oturum.close()

    def kapat(self) -> None:
        """Bağlantı havuzunu boşaltır; dosya kilidi bırakılır (Windows'ta gerekli)."""
        self.motor.dispose()
