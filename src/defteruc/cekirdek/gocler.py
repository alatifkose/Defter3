"""Şema sürümü ve göçler (Alembic) — Aşama 4.1.

Şema sürümünü Alembic'in kendi ``alembic_version`` tablosu tutar; ayrı bir
sürüm tablosu yoktur. Göçler ``alembic/versions`` altındadır; ilk göç
``0001`` uygulama tablosu içermez (genel altyapı).

Göç çalıştırmak açık bir işlemdir: uygulama başlangıcı (``uv run defteruc``,
``uv run defteruc-mcp``) göç çalıştırmaz. Resmî yol komut satırıdır::

    uv run alembic upgrade head

Komut veritabanı yolunu ``alembic.ini``'den değil merkezi ayarlardan alır
(``alembic/env.py`` → ``defteruc.ayarlar``). Aynı iş süreç içinde
``semayi_yukselt`` ile de yapılır (testler); ikisi aynı ``env.py``'den geçer.

Bu modül finansı bilmez; ``defteruc.ayarlar``ı da import etmez, yolu
çağıranın verdiği ``Veritabani`` üzerinden kullanır.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from defteruc.cekirdek.veritabani import Veritabani

PROJE_KOKU = Path(__file__).resolve().parents[3]
ALEMBIC_INI = PROJE_KOKU / "alembic.ini"
GOC_DIZINI = PROJE_KOKU / "alembic"
SURUM_TABLOSU = "alembic_version"


def alembic_ayari() -> Config:
    """Proje kökündeki ``alembic.ini`` ve göç dizini; veritabanı adresi taşımaz."""
    ayar = Config(str(ALEMBIC_INI))
    ayar.set_main_option("script_location", str(GOC_DIZINI))
    return ayar


def beklenen_sema_surumu() -> str:
    """Göç zincirinin başı (``head``); kodun beklediği şema sürümü."""
    bas = ScriptDirectory.from_config(alembic_ayari()).get_current_head()
    if bas is None:
        raise RuntimeError("göç zinciri boş; alembic/versions altında göç yok")
    return bas


def sema_surumu(veritabani: Veritabani) -> str | None:
    """Veritabanındaki Alembic sürümü; göç hiç uygulanmamışsa ``None``.

    Bağlantı açar: dosya yoksa SQLite boş dosyayı oluşturur.
    """
    with veritabani.motor.connect() as baglanti:
        if not inspect(baglanti).has_table(SURUM_TABLOSU):
            return None
        deger = baglanti.execute(
            text(f"SELECT version_num FROM {SURUM_TABLOSU}")
        ).scalar()
        return str(deger) if deger is not None else None


def semayi_yukselt(veritabani: Veritabani) -> str:
    """Göçleri ``head``'e kadar tek transaction içinde uygular; sürümü döndürür.

    Bir adım düşerse hiçbiri kalmaz (SQLite'ta DDL transaction içindedir).
    """
    ayar = alembic_ayari()
    with veritabani.motor.begin() as baglanti:
        ayar.attributes["connection"] = baglanti
        command.upgrade(ayar, "head")
    surum = sema_surumu(veritabani)
    if surum is None:
        raise RuntimeError("göç uygulandı ama sürüm tablosu boş")
    return surum
