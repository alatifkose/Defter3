"""Hypothesis ortam kontrolü.

Bu dosya DEFTERUC'ün bir davranışını sınamaz. Yalnızca Hypothesis'in
özellik tabanlı testleri üretip çalıştırabildiğini doğrular.
"""

from hypothesis import given
from hypothesis import strategies as st


@given(st.lists(st.integers()))
def test_iki_kez_ters_cevirme_baslangici_verir(liste: list[int]) -> None:
    assert list(reversed(list(reversed(liste)))) == liste
