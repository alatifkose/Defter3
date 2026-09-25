from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.engine import URL
from sqlalchemy.engine.interfaces import DBAPIConnection, ExceptionContext
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

SURUCU = "sqlite+pysqlite"

BAGLANTI_PRAGMALARI: tuple[tuple[str, str], ...] = (
    ("foreign_keys", "ON"),
    ("journal_mode", "WAL"),
)

BEKLEME_SANIYESI = 10.0

MESGUL_HATA_ADLARI = ("SQLITE_BUSY", "SQLITE_LOCKED")


def veritabani_url(yol: Path) -> URL:
    if not yol.is_absolute():
        raise ValueError(f"veritabanı yolu mutlak olmalı: {yol}")
    return URL.create(SURUCU, database=str(yol))


def motor_olustur(yol: Path, bekleme_saniyesi: float = BEKLEME_SANIYESI) -> Engine:
    motor = create_engine(
        veritabani_url(yol),
        connect_args={"autocommit": False, "timeout": bekleme_saniyesi},
    )
    event.listen(motor, "connect", _baglantiyi_ayarla)
    event.listen(motor, "handle_error", _mesgul_hatasini_cevir)
    return motor


def _mesgul_hatasini_cevir(baglam: ExceptionContext) -> None:
    hata = baglam.original_exception
    if (
        isinstance(hata, sqlite3.OperationalError)
        and getattr(hata, "sqlite_errorname", None) in MESGUL_HATA_ADLARI
    ):
        raise VeritabaniMesgul(
            "veritabanı başka bir süreç tarafından yazılıyor, bekleme süresi doldu; "
            "iş yapılmadı, yeniden denenebilir"
        ) from hata


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


class VeritabaniMesgul(Exception): ...


class YabanciAnahtarIhlali(Exception): ...


class DenetimGeriAcilamadi(Exception): ...


class Veritabani:
    def __init__(self, yol: Path, bekleme_saniyesi: float = BEKLEME_SANIYESI) -> None:
        self.yol = yol
        self.motor = motor_olustur(yol, bekleme_saniyesi)
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
