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

BAGLANTI_PRAGMALARI: tuple[tuple[str, str], ...] = (
    ("foreign_keys", "ON"),
    ("journal_mode", "WAL"),
)

BAGLANTI_ARGUMANLARI: dict[str, object] = {"autocommit": False}


class TabloTabani(DeclarativeBase):
    metadata = MetaData(naming_convention=KISIT_ADLANDIRMA)


def veritabani_url(yol: Path) -> URL:
    if not yol.is_absolute():
        raise ValueError(f"veritabanı yolu mutlak olmalı: {yol}")
    return URL.create(SURUCU, database=str(yol))


def motor_olustur(yol: Path) -> Engine:
    motor = create_engine(veritabani_url(yol), connect_args=BAGLANTI_ARGUMANLARI)
    event.listen(motor, "connect", _baglantiyi_ayarla)
    return motor


def _baglantiyi_ayarla(
    dbapi_baglantisi: DBAPIConnection, _kayit: ConnectionPoolEntry
) -> None:
    _pragmalari_transaction_disinda_uygula(dbapi_baglantisi, BAGLANTI_PRAGMALARI)


def _pragmalari_transaction_disinda_uygula(
    dbapi_baglantisi: DBAPIConnection, pragmalar: tuple[tuple[str, str], ...]
) -> None:
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


class YabanciAnahtarIhlali(Exception): ...


class DenetimGeriAcilamadi(Exception): ...


class Veritabani:
    def __init__(self, yol: Path) -> None:
        self.yol = yol
        self.motor = motor_olustur(yol)
        self._oturum_ac = sessionmaker(bind=self.motor, expire_on_commit=False)

    @contextmanager
    def islem(self) -> Generator[Session, None, None]:
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
        self.motor.dispose()
