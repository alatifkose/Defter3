"""DEFTERUC genel çekirdeği.

Bu paket hiçbir domain'i tanımaz: ``defteruc.finans`` paketini ve alt
modüllerini import edemez, finansal tip, enum ya da iş kuralı içeremez.
Sınır ``tests/test_mimari_sinir.py`` ile korunur (karar 2026-09-18, README
"Mimari sınır" bölümü).

Modüller: ``veritabani`` (bağlantı, işlem sınırı), ``arsiv`` (gelen dizini
sınırı, akışla SHA-256, içerik adresli atomik arşiv, bütünlük doğrulama) ve
``motor`` (birinci motor: tablo oluşturma, sütun ekleme).

2026-09-24: çekirdek yeniden tasarlanıyor. Veritabanında hazır tablo yoktur;
tabloları Cowork, motoru kullanarak ve kullanıcı onayıyla oluşturur (README
"Durum"). Eski tanım, nesne, taslak, mükerrerlik, kayıt, denetim, belge ve göç
modülleri kaldırıldı.
"""
