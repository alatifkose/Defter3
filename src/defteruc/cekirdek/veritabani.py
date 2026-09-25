from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Connection, Engine, MetaData, create_engine, event, text
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


class DenetimGeriAcilamadi(Exception):
    """Denetimsiz iş **commit edildi**, ama yabancı anahtar denetimi bağlantıda
    yeniden açılamadı; bağlantı geçersizleştirildi (havuza dönmedi). İş geri
    alınmış değildir."""


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
    def islem_yabanci_anahtar_denetimsiz(self) -> Generator[Connection, None, None]:
        """``foreign_keys=OFF`` ile bir iş = bir transaction (SQLite'ın tablo
        yeniden kurma tarifi). Bağlantı iş boyunca **sahiplenilir**: denetim
        yalnız o bağlantıda kapanır, ``commit`` öncesi ``PRAGMA
        foreign_key_check`` çalışır (ihlalde ``YabanciAnahtarIhlali`` ile geri
        alınır) ve denetim aynı bağlantıda yeniden açılmadan bağlantı havuza
        dönmez. Denetim kapatılamaz ya da yeniden açılamazsa bağlantı
        **geçersizleştirilir** (havuza dönmez, kapatılır): gövde başarılıysa
        ``DenetimGeriAcilamadi`` yükselir (iş commit edilmiştir, geri alınmış
        sayılmaz); gövde hatalıysa asıl hata yükselir, temizleme hatası ona
        not olarak eklenir. (İnceleme 2 ve 3, 2026-09-24.)"""
        with self.motor.connect() as baglanti:
            ham = baglanti.connection.dbapi_connection
            if ham is None:  # pragma: no cover - havuz her zaman bağlantı verir
                raise RuntimeError("DBAPI bağlantısı alınamadı")
            try:
                _pragmalari_transaction_disinda_uygula(ham, (("foreign_keys", "OFF"),))
            except Exception:
                baglanti.invalidate()
                raise
            govde_hatasi: BaseException | None = None
            try:
                with baglanti.begin():
                    yield baglanti
                    ihlaller = baglanti.execute(text("PRAGMA foreign_key_check")).all()
                    if ihlaller:
                        raise YabanciAnahtarIhlali(
                            f"{len(ihlaller)} yabancı anahtar ihlali: "
                            + ", ".join(
                                f"{i[0]}(rowid {i[1]}) -> {i[2]}" for i in ihlaller
                            )
                        )
            except BaseException as hata:
                govde_hatasi = hata
                raise
            finally:
                try:
                    _pragmalari_transaction_disinda_uygula(
                        ham, (("foreign_keys", "ON"),)
                    )
                except Exception as hata:
                    baglanti.invalidate()
                    mesaj = (
                        "yabancı anahtar denetimi bağlantıda yeniden açılamadı "
                        f"({hata}); bağlantı havuzdan çıkarıldı"
                    )
                    if govde_hatasi is None:
                        raise DenetimGeriAcilamadi(
                            f"iş commit edildi; {mesaj}"
                        ) from hata
                    govde_hatasi.add_note(f"ayrıca: {mesaj}")

    def kapat(self) -> None:
        """Bağlantı havuzunu boşaltır; dosya kilidi bırakılır (Windows'ta gerekli)."""
        self.motor.dispose()
