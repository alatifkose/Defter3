"""DEFTERIKI genel çekirdeği.

Bu paket hiçbir domain'i tanımaz: ``defteriki.finans`` paketini ve alt
modüllerini import edemez, finansal tip, enum ya da iş kuralı içeremez.
Sınır ``tests/test_mimari_sinir.py`` ile korunur (karar 2026-09-18, README
"Mimari sınır" bölümü). Aşama 4.1: ``veritabani`` (bağlantı, işlem sınırı) ve
``gocler`` (Alembic şema sürümü). Aşama 4.2: ``tanim_tablolari`` (tanım
paketi, sürüm, nesne türü, özellik, ilişki, kayıt türü, kayıt alanı
tabloları) ve ``tanim_islemleri`` (tanım yazma/okuma, hata modeli). Aşama
4.3: ``nesne_tablolari`` (nesne, nesne özelliği, nesne ilişkisi) ve
``nesne_islemleri`` (nesne oluşturma, özellik doğrulama, ilişki, hiyerarşi,
yaşam durumu, tanım sürümü kilidi). Aşama 4.4: ``arsiv`` (gelen dizini
sınırı, akışla SHA-256, içerik adresli atomik arşiv, bütünlük doğrulama),
``belge_tablolari`` (arşiv dosyası, belge, okuma, kaynak tabloları) ve
``belge_islemleri`` (belge alma, okuma sürümleri, kaynak izi, dosya/DB
uzlaştırma). Tanımlar veridir; çekirdek hangi türlerin var olacağını, ne
anlama geldiğini ve bir belgenin ne belgesi olduğunu bilmez.
"""
