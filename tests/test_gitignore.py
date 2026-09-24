"""Kritik Git dışlama kurallarının doğrulanması.

Kişisel finans verisi taşıyan dosyalar (veritabanı, WAL/SHM, belgeler, loglar,
yedekler, sırlar) depoya girmemeli; kaynak dosyalar ise girmeli. Kontrol
``git check-ignore --no-index`` ile yapılır; hiçbir dosya oluşturulmaz, depo
değişmez. Git bulunamazsa test atlanır.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

PROJE_KOKU = Path(__file__).resolve().parent.parent

DISLANMALI = (
    "defteruc.sqlite3",
    "defteruc.sqlite3-wal",
    "defteruc.sqlite3-shm",
    "defteruc.sqlite3-journal",
    "veri/gercek/defteruc.db",
    "veri/gercek/defteruc.db-wal",
    "belgeler/ekstre.pdf",
    "logs/defteruc.log",
    "logs/defteruc.log.1",
    "yedek/2026-09-11.zip",
    "defteruc.bak",
    ".env",
    ".env.gercek",
    "secrets.json",
    "anahtar.pem",
    "anahtar.key",
    ".venv/Lib/site-packages/x.py",
    "src/defteruc/__pycache__/ayarlar.cpython-313.pyc",
    "DEFTERUC-Gelistirme-Plani.md",
    "DEFTERUC-Yurutme-Plani-2026-09-13.md",
)

DISLANMAMALI = (
    "README.md",
    "pyproject.toml",
    "uv.lock",
    ".gitignore",
    ".gitattributes",
    "kavramlar_sozlugu.md",
    "src/defteruc/__init__.py",
    "src/defteruc/ayarlar.py",
    "src/defteruc/baslangic.py",
    "src/defteruc/gunluk.py",
    "src/defteruc/mcp_kapisi.py",
    "src/defteruc/cekirdek/__init__.py",
    "src/defteruc/cekirdek/veritabani.py",
    "src/defteruc/cekirdek/arsiv.py",
    "src/defteruc/finans/__init__.py",
    "scripts/kontrol.py",
    ".pre-commit-config.yaml",
    "tests/test_gitignore.py",
    "tests/test_mimari_sinir.py",
)


def _dislananlar(yollar: tuple[str, ...]) -> set[str]:
    """Verilen yollardan .gitignore kurallarına takılanları döndürür."""
    git = shutil.which("git")
    if git is None:
        pytest.skip("git bulunamadı")
    sonuc = subprocess.run(
        [git, "check-ignore", "--no-index", "--", *yollar],
        cwd=PROJE_KOKU,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    # 0: en az biri dışlanıyor, 1: hiçbiri dışlanmıyor, 128: hata
    assert sonuc.returncode in (0, 1), sonuc.stderr
    return {satir.strip() for satir in sonuc.stdout.splitlines() if satir.strip()}


def test_kisisel_veri_ve_sirlar_git_disinda() -> None:
    dislananlar = _dislananlar(DISLANMALI)

    eksik = [yol for yol in DISLANMALI if yol not in dislananlar]
    assert eksik == [], f"dışlanması gerekirken dışlanmayan: {eksik}"


def test_kaynak_dosyalar_git_icinde() -> None:
    dislananlar = _dislananlar(DISLANMAMALI)

    assert dislananlar == set(), f"yanlışlıkla dışlanan: {sorted(dislananlar)}"
