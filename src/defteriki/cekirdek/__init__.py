"""DEFTERIKI genel çekirdeği.

Bu paket hiçbir domain'i tanımaz: ``defteriki.finans`` paketini ve alt
modüllerini import edemez, finansal tip, enum ya da iş kuralı içeremez.
Sınır ``tests/test_mimari_sinir.py`` ile korunur (karar 2026-09-18, README
"Mimari sınır" bölümü). Aşama 4.1: ``veritabani`` (bağlantı, işlem sınırı) ve
``gocler`` (Alembic şema sürümü). İş tabloları sonraki aşamalarda gelir.
"""
