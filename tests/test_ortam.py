"""Test ortamı kontrolü.

Bu dosya DEFTERUC'ün bir davranışını sınamaz. Yalnızca pytest'in ve
geçici dizin fikstürünün bu makinede çalıştığını doğrular.
"""

from pathlib import Path


def test_gecici_dizine_yazilip_geri_okunur(tmp_path: Path) -> None:
    dosya = tmp_path / "deneme.txt"
    dosya.write_text("merhaba", encoding="utf-8")

    assert dosya.read_text(encoding="utf-8") == "merhaba"
