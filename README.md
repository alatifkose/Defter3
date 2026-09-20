# DEFTERIKI

Kişisel finans kayıt sistemi. Belgeler Cowork tarafından okunur, MCP kapısından
DEFTERIKI'ye yazılır; uygulama kayıtları tutar, denetler ve gösterir.

## Durum

Aşama 2 (proje temeli) ve Aşama 3 (gerçek Cowork MCP denemesi) tamamlandı;
Aşama 3'ün dört teslimi ve ölçümleri "Cowork entegrasyonu" bölümünde, geçici
deneme araçları kaldırıldı. Aşama 4.0 (2026-09-18): çekirdek / finans mimari
sınırı kuruldu ve testle korunuyor ("Mimari sınır" bölümü). Bu hat
(`yeniden-insa`, depo [alatifkose/Defter3](https://github.com/alatifkose/Defter3))
Aşama 3 kapısından yeniden başlar; önceki Aşama 4-6 geliştirme hattı
[alatifkose/DefterIki](https://github.com/alatifkose/DefterIki) deposunun
`main` dalında yedek olarak durur, oraya yazılmaz. Aşama 4.1 (genel
veritabanı altyapısı) ve Aşama 4.2 (tanım sistemi) 2026-09-18'de, Aşama 4.3
(nesne motoru), Aşama 4.4 (belge, arşiv, okuma ve kaynak) ve Aşama 4.5
(işlem paketi ve taslak durumu) 2026-09-19'da, Aşama 4.6 (onay ve
mükerrerlik) 2026-09-20'de bitti; 4.6'nın bağımsız inceleme bulguları aynı gün
üçüncü tur düzeltmeleriyle tamamlandı (göç `0010`, "Aday kararları ve ortak
paket beklemesi"). Aşama 4.7 (kesin kayıt)
sırada.
Bitenler:

* uv ile paket iskeleti (`src/defteriki`)
* Merkezi ayar yönetimi (`src/defteriki/ayarlar.py`)
* Başlangıç akışı: `uv run defteriki` (`src/defteriki/baslangic.py`)
* Teknik hata günlüğü (`src/defteriki/gunluk.py`)
* Test altyapısı (pytest + Hypothesis)
* Tek komutluk kalite kontrolü (Ruff, Pyright strict, pytest)
* `.gitignore` ve `.gitattributes`; kritik dışlama kuralları testle doğrulanır
  (`tests/test_gitignore.py`)
* MCP kapısı iskeleti: `uv run defteriki-mcp`, tek araç `sistem_durumu`
  (`src/defteriki/mcp_kapisi.py`); Cowork ile bağlantı, dosya erişimi ve
  çok adımlı protokol gerçek istemciyle ölçüldü
* Mimari sınır: `src/defteriki/cekirdek/` (Aşama 4.1'den beri dolu) ve
  `src/defteriki/finans/` (henüz boş) paketleri ve bağımlılık yönünü koruyan
  AST testi (`tests/test_mimari_sinir.py`)
* İnceleme düzeltmeleri (2026-09-18): SDK günlüğü gizlilik kuralına bağlandı
  ("Teknik hata günlüğü"), mimari sınır denetimi genişletildi, başlangıç
  testleri gelen dizini değişkenini temizler, test ortamı yol sınırı fiziksel
  karşılığa bakar ("Ayarlar"), Defter3 yerel verisi eski hattan ayrıldı
  ("Defter3 yerel kurulumu")
* Genel veritabanı altyapısı (Aşama 4.1): SQLAlchemy + Alembic,
  `defteriki.cekirdek.veritabani` (bağlantı politikası, işlem sınırı) ve
  `defteriki.cekirdek.gocler` (şema sürümü); ilk göç `0001` uygulama tablosu
  içermez ("Veritabanı" bölümü)
* Tanım sistemi (Aşama 4.2): tanım paketi, sürüm, nesne türü, özellik,
  ilişki, kayıt türü ve kayıt alanı tanımlarını veri olarak tutan yedi tablo
  (göç `0002`), `defteriki.cekirdek.tanim_tablolari`,
  `defteriki.cekirdek.tanim_sorgulari` (okuma; 2026-09-20'de ayrıldı) ve
  `defteriki.cekirdek.tanim_islemleri` (yazma, ekleme-yalnız kilit); çekirdek
  hangi türlerin var olduğunu bilmez, testler nötr sahte paketlerle çalışır
  ("Tanım sistemi" bölümü)
* Nesne motoru (Aşama 4.3): nesne, nesne özelliği ve nesne ilişkisi
  tabloları, hiyerarşi kuralı, özellik değer türü ve zorunluluğu, tanım
  sürümü kilidi, yaşam durumu (göç `0004`); `defteriki.cekirdek.nesne_tablolari`
  ve `defteriki.cekirdek.nesne_islemleri` ("Nesne motoru" bölümü)
* Belge zinciri (Aşama 4.4): gelen dizini sınırı, akışla SHA-256, içerik
  adresli atomik arşiv, belge, okuma sürümleri, kaynak izi ve dosya/DB
  uzlaştırma (göç `0006`); `defteriki.cekirdek.arsiv`,
  `defteriki.cekirdek.belge_tablolari`, `defteriki.cekirdek.belge_islemleri`
  ("Belge zinciri" bölümü)
* İşlem paketi ve taslak (Aşama 4.5): "yazmak ≠ kaydetmek"; tamamlanmış
  okumadan doğan işlem paketi (`calisiyor / bekliyor / iptal`), kesin nesne
  tablolarından fiziksel olarak ayrı aday nesne / özellik / ilişki / kayıt
  tabloları ve aday kayıt ↔ aday nesne bağı (göç `0007`);
  `defteriki.cekirdek.taslak_tablolari`, `defteriki.cekirdek.taslak_islemleri`,
  ortak değer kodlaması `defteriki.cekirdek.deger_kodlama` ("İşlem paketi ve
  taslak" bölümü)
* Onay ve mükerrerlik (Aşama 4.6): kullanıcı tarafından seçilen mükerrerlik
  şartları, iki yönlü tarama, kalıcı şüphe ve kullanıcı karar talebi,
  `BEKLIYOR` protokolü, `AYNI / AYRI / KARARSIZ` kararı, aday → mevcut nesne
  çözümlemesi, iki kesin nesnenin birleştirilmesi, zincirleme denetim ve
  aktörlü iş denetim izi (göç `0008`);
  `defteriki.cekirdek.mukerrerlik_tablolari`,
  `defteriki.cekirdek.mukerrerlik_islemleri`,
  `defteriki.cekirdek.denetim_tablolari`, `defteriki.cekirdek.denetim_islemleri`
  ("Onay ve mükerrerlik" bölümü)
* Aşama 4.6 inceleme düzeltmeleri (2026-09-20, göç `0009`): kararı yalnız
  kullanıcı verir (servis kapısı + kontrol kısıtları), iptal edilen paketin
  açık talepleri terminal `gecersiz` olur ve çifti kilitlemez, kanonik kesin
  nesne tek sıçramada bulunur (`kanonik_nesne_id`, birleşim zinciri
  düzleştirilir), aynı adayın iki `AYNI` kararı kesin nesneleri birleştirir,
  birleşen nesnenin kimlik geçmişi mükerrerlik korumasından düşmez, aday
  kimlikleri yeniden dağıtılmaz (`AUTOINCREMENT`) ("Karar kaynağı, iptal ve
  kanonik kimlik")
* Aşama 4.6 ikinci inceleme turu (2026-09-20, şema değişmedi): geçmiş `AYRI`
  kararları kimlikler birleşmelerle değişse de korunur (iki kanonik kümenin
  bütün üyeleri denetlenir), birleşmeden sonra bayat kalan açık talepler
  kanonik uçlara uzlaştırılır, `karar_ver` ve `paketi_iptal_et` tek bir dış
  SAVEPOINT ile bütünüyle atomiktir ("AYRI geçmişi ve karar atomikliği")

Henüz yok: kesin kayıt (hareket) verisi (Aşama 4.7), kesin kaydetme / paketi
kesinleştirme (4.8), genel kural motoru (4.9), finans tanım paketi
(`finans/` boş, 4.10), GUI, ürün verisi yazan MCP aracı (belge alan, işlem
paketi ve karar araçları dahil; 4.11).

## Veritabanı

Aşama 4.1 (2026-09-18; Yeniden İnşa Teknik Planı madde 26). Güvenilir
persistence temeli. Uygulama tabloları bugün Aşama 4.2'nin sekiz tanım
tablosu ("Tanım sistemi" bölümü), Aşama 4.3'ün üç nesne tablosu ("Nesne
motoru" bölümü), Aşama 4.4'ün dört belge zinciri tablosu ("Belge zinciri"
bölümü), Aşama 4.5'in altı taslak tablosu ("İşlem paketi ve taslak" bölümü)
ve Aşama 4.6'nın altı onay / mükerrerlik / denetim tablosudur ("Onay ve
mükerrerlik" bölümü). Finansal tablo yoktur, `finans/` boştur.

**Bağlantı (`src/defteriki/cekirdek/veritabani.py`).** SQLite dosyasının yolu
tek kaynaktan gelir: `Ayarlar.veritabani_yolu`. Çekirdek bu yolu çağırandan
`Path` olarak alır; `defteriki.ayarlar`ı import etmez, çalışma dizinine
bakmaz. Adres metin birleştirilerek değil SQLAlchemy `URL.create` ile üretilir
(`sqlite+pysqlite`, Windows yolu olduğu gibi); göreli yol reddedilir. Engine
modül importunda değil `motor_olustur(yol)` ile açıkça kurulur ve kurulmak
diske dokunmaz; dosya ilk bağlantıda oluşur. Bağlantı politikası tek yerde,
her yeni bağlantıda uygulanır: `PRAGMA foreign_keys=ON` (bağlantı başına
zorunlu) ve `PRAGMA journal_mode=WAL`. `TabloTabani` bütün tabloların ortak
tabanıdır; tek `metadata`, isimli kısıt kalıbı (SQLite'ta Alembic `batch`
kipi için gerekir).

**Transaction kontrolü.** Bağlantılar `sqlite3` modülünün Python 3.12+
`autocommit=False` kipiyle açılır (`connect_args`). Eski kipte `sqlite3`
yalnız DML öncesi örtük `BEGIN` açar; `CREATE TABLE` gibi DDL transaction
dışında kalır ve geri alınamaz (Alembic de SQLite için `transactional_ddl`
saymaz). Yeni kipte bağlantı ertelenmiş bir transaction ile gelir ve her
`commit`/`rollback` sonrası yenisi başlar; DDL dahil her şey içinde kalır.
PRAGMA'lar transaction içinde çalışmadığından (`journal_mode` değiştirilemez,
`foreign_keys` sessizce yok sayılır) bağlantı olayında `autocommit` geçici
olarak açılır, PRAGMA'lar uygulanır, sonra kapatılır. Bu düzenleme 2026-09-18
incelemesinde eklendi; önceki metin göçlerin tek transaction olduğunu
kanıtsız söylüyordu.

**İşlem sınırı.** `Veritabani(yol).islem()` bağlam yöneticisi: bir iş = bir
kısa ömürlü oturum = bir transaction. Normal çıkışta `commit`, istisnada
`rollback` ve istisna yeniden yükselir, her durumda oturum kapanır. Model ya
da ileride gelecek depo kodu kendi başına `commit` etmez; sahip bu bağlam
yöneticisidir. `kapat()` havuzu boşaltır (Windows'ta dosya kilidi için).

**Göçler ve şema sürümü (`src/defteriki/cekirdek/gocler.py`, `alembic/`).**
Şema sürümünü Alembic'in kendi `alembic_version` tablosu tutar; ayrı sürüm
tablosu yoktur. Göçler `alembic/versions/` altında; `0001_genel_altyapi`
zincirin başıdır ve tablo oluşturmaz, `0002_tanim_sistemi` yedi tanım
tablosunu ekler, `0003_surum_no_tamsayi` `tanim_surumu` kontrol kısıtını
depolama sınıfını da denetleyen biçimiyle değiştirir, `0004_nesne_motoru`
nesne tablolarını, hiyerarşi kuralını, özellik değer türü / zorunluluk
sütunlarını ve sürüm kilidini ekler, `0005_iliski_kendine_serbest`
`nesne_iliskisi` üzerindeki `kaynak_nesne_id <> hedef_nesne_id` kontrol
kısıtını kaldırır (tablo açık SQL ile aynı kısıt adlarıyla yeniden kurulur;
geri alma kendine dönen satır varsa kısıt hatasıyla düşer, veri silinmez),
`0006_belge_zinciri` dört belge zinciri tablosunu ekler (var olan tablolara
dokunmaz; geri alma dört tabloyu düşürür ama herhangi birinde satır varsa
uygulanmaz ve hata verir, veri sessizce silinmez), `0007_islem_paketi_taslak`
işlem paketi ve beş aday tablosunu ekler ve `kaynak` üzerine `(id, okuma_id)`
benzersiz indeksini koyar (var olan tablolar yeniden kurulmaz; geri alma aynı
politikayla, satır varken uygulanmaz) `0008_onay_ve_mukerrerlik` (altı
onay / mükerrerlik / denetim tablosu, iki kısmi benzersiz indeks; aynı
politikayla, satır varken uygulanmaz) ve
`0009_karar_yasam_dongusu_ve_kanonik_kimlik` (2026-09-20 incelemesi: karar
talebine terminal `gecersiz` durumu ve `gecersizlik_zamani`, `nesne_birlesimi`
üzerine `kanonik_nesne_id`, "kararı yalnız kullanıcı verir" kontrol kısıtları,
iki yeni denetim olayı, `aday_nesne` birincil anahtarına `AUTOINCREMENT`; beş
tablo `0003`ün açık SQL kalıbıyla yeniden kurulur, `0009`a özgü veri varsa
geri alma uygulanmaz), `0010_karar_talebi_paketleri` (ortak soruların paket
bağları, mevcut taleplerin paketlerinden doldurulur; ek paket bağı varsa
geri alma reddedilir) (zincirin başı bugün `0010`; ayrıntı "Nesne motoru",
"Belge zinciri", "İşlem paketi ve taslak" ve "Onay ve mükerrerlik"
bölümlerinde).
**Kalıcı geliştirme veritabanı** (`C:\dev\Defter3-veri\gelistirme\
defteriki.sqlite3`) bilinçli olarak hâlâ `0003` sürümündedir; `0004`–`0010`
ona uygulanmamıştır ve yalnız Abdüllatif'in açık talimatıyla uygulanır. Göç
testleri yalnız `tmp_path` altındaki geçici veritabanlarında çalışır. `0003`
tabloyu açık SQL adımlarıyla yeniden kurar,
Alembic `batch`
kipiyle değil: göçler `foreign_keys=ON` bağlantıda ve tek transaction içinde
çalıştığından (`PRAGMA foreign_keys` transaction içinde etkisizdir) `batch`
ana tabloyu çocuk satırlar dururken düşürünce `FOREIGN KEY constraint
failed` verir; bu 2026-09-18 incelemesinde çocuk satırlı testle görüldü.
Kullanılan sıra: `PRAGMA defer_foreign_keys=ON` (transaction içinde izinli),
satırlar kısıtsız taşıma tablosuna, yeni tablo aynı kısıt adlarıyla ve sabit
sırayla kurulur, eski tablo düşürülür, yeni tablo eski adı alır, satırlar
geri yazılır (ana tabloya giren her satır ertelenmiş ihlal sayacını
düşürür), taşıma tablosu düşürülür, `PRAGMA foreign_key_check` boş değilse
göç hata verir. Bir adım düşerse transaction tamamen geri alınır. Açık
karar: `env.py`'deki `render_as_batch=True` bu politikayla ana tablolarda
kullanılamaz; ileride ya göç bağlantısı FK kapalı açılır (Alembic'in
SQLite önerisi) ya da her kısıt değişikliği bu açık kalıpla yazılır.
`alembic/env.py` tanım tablo
modülünü import eder ki `TabloTabani.metadata` dolu olsun (autogenerate ve
şema karşılaştırması için). `alembic.ini` veritabanı adresi taşımaz;
`alembic/env.py` yolu merkezi ayarlardan (ortam değişkenleri) alır, komut
satırında yalnız veritabanı dosyasının dizinini açar. Göç çalıştırma açık bir
işlemdir; `uv run defteriki` ve `uv run defteriki-mcp` göç çalıştırmaz,
veritabanı dosyası oluşturmaz (testle sabit). Resmî komut:

```bash
uv run alembic upgrade head
```

Süreç içinde aynı iş `gocler.semayi_yukselt(veritabani)` ile yapılır (tek
transaction, aynı `env.py`); `gocler.sema_surumu` sürümü okur,
`gocler.beklenen_sema_surumu` zincirin başını verir. Otomatik göç (dağıtım
politikası) ayrı bir karardır, bugün yoktur. Atomiklik kanıtı
(`test_dusen_goc_adimi_ddl_dahil_tamamen_geri_alinir`): gerçek `env.py` ve
şablonla kurulmuş ayrı bir sentetik göç dizininde birinci göç tablo
oluşturup satır yazar, ikincisi tablo oluşturup bilinçli düşer; `upgrade
head` hata verir, iki tablo da kalmaz, `alembic_version` yazılmamıştır
(sürüm ilerlememiştir), ardından gerçek zincir aynı dosyada zincirin başına
(bugün `0005`) çıkar ve `integrity_check` temizdir. Gerçek `0001_genel_altyapi` göçüne dokunulmaz.
Aynı senaryo eski `sqlite3` kipinde denendiğinde birinci göçün tablosu
(`sentetik_bir`) ve boş bir `alembic_version` tablosu geride kalıyordu;
kanıt bu farktır.

Dikkat: komut hangi veritabanına gideceğini ortam değişkenlerinden okur.
Kullanıcı düzeyi `setx DEFTERIKI_VERI_KOKU` hâlâ eski hattın kökünü
gösteriyorsa, terminalden düz `uv run alembic upgrade head` eski veritabanını
hedefler; eski dosya bu zincirde olmayan `0002` sürümünü taşıdığından Alembic
"Can't locate revision" hatasıyla durur ve hiçbir şey değiştirmez, ama komut
öncesi `DEFTERIKI_VERI_KOKU=C:\dev\Defter3-veri` açıkça verilmelidir. Defter3
verisi için ilk göç 2026-09-18'de bu şekilde uygulandı:
`C:\dev\Defter3-veri\gelistirme\defteriki.sqlite3`, sürüm `0001`; göç `0002` aynı
gün aynı komutla uygulandı, göç `0003` de aynı gün
aynı komutla uygulandı. 2026-09-18 akşamı Abdüllatif'in talimatıyla
geliştirme veritabanı sıfırdan yeniden kuruldu: eski dosya
`defteriki.sqlite3.eski-2026-09-18` adına alındı, yeni dosya `0001 → 0002 →
0003` zinciriyle `0003` sürümünde ve boş. Göç `0004`, `0005` ve `0006` bu
dosyaya uygulanmadı; dosya `0003`te kalır, kod `0006` bekler ve bu bilinçli,
istenen bir durumdur (2026-09-19'da Aşama 4.4 sonunda yeniden doğrulandı:
dosyadaki `alembic_version` hâlâ `0003`).

**Geliştirme veritabanına göç politikası (karar 2026-09-18, Abdüllatif).**
Geliştirme veritabanı depo dışındadır; commit ve geri alma fiziksel dosyayı
geri almaz. Bu yüzden: göç geliştirme ve doğrulaması kalıcı geliştirme
veritabanında yapılmaz, yalnız geçici / sıfır test veritabanlarında
(`tmp_path`) yapılır; kalıcı dosyaya göç ancak Abdüllatif'in açık
talimatıyla uygulanır; aşama bitişinde otomatik `upgrade head` yoktur;
README'ye "geliştirme veritabanına uygulandı" kaydı ancak gerçekten onun
talimatıyla yapıldıysa yazılır; göç zincirinin doğruluk kaynağı fiziksel
dosya değil, Git'teki göç dosyaları ve sıfır veritabanından koşan testlerdir.

**Testler** (`tests/test_cekirdek_veritabani.py`, `tests/test_gocler.py`):
gerçek SQLite dosyalarıyla, `test` ortamı ve `tmp_path` altında kök;
`:memory:` yok. Kanıtlananlar: import ve engine kurulumu dosya oluşturmaz;
adres verilen mutlak yoldan üretilir, göreli yol reddedilir, çalışma dizini
etkisizdir; aynı anda açık iki ayrı fiziksel DBAPI bağlantısında (kimlikleri
farklı) ve havuz boşaltıldıktan sonra kurulan yeni bağlantıda
`foreign_keys=1` ve `journal_mode=wal`; bağlantı `autocommit=False`
kipindedir; hatalı dış anahtar yazımı gerçekten reddedilir, geçerli olan
kabul edilir; başarılı işlem commit olur, hata alan işlem tamamen rollback
olur ve hata yükselir, oturum kapanır; işlem içindeki DDL de geri alınır
(`CREATE TABLE` + hata → tablo yok); test veritabanı ve WAL dosyası yalnız
test kökünde oluşur; sıfır
veritabanından `upgrade head` `0008`e çıkar ve tablolar `alembic_version` +
sekiz tanım tablosu + üç nesne tablosu + dört belge zinciri tablosu + altı
taslak tablosu + yedi onay / mükerrerlik / denetim tablosudur; iki
sıfır veritabanı aynı şemayı
üretir; tekrar
`upgrade` şemayı değiştirmez; `head → 0001 → head` döngüsünde tanım tabloları
ve indeksleri gider, geri gelir ve `sqlite_master` birebir aynıdır,
`integrity_check` temizdir; adım adım `0001 → 0002 → 0003 → 0002 → 0001 →
head` zincirinde her adımda `tanim_surumu` kontrol kısıtı beklenen addadır,
`0002`de yazılan sürüm satırı ve ona bağlı çocuk satırlar (nesne türü, kayıt
türü, ilişki) `0003`ün tablo yeniden kurmasından ve geri alınmasından sağ
çıkar, zincir `0004`, `0005`, `0006` ve `0007`ye kadar sürer ve her adımda
`nesne_iliskisi` kontrol kısıtı beklenen durumdadır, belge zinciri tabloları
`0006`dan, taslak tabloları `0007`den itibaren vardır, `foreign_key_check`
boş kalır, geçici tablo kalmaz,
diğer kısıt adları
korunur, `0002`de kabul edilen REAL sürüm numarası `0003`te reddedilir;
`0002` şemasında REAL sürüm numarası varken `0003` uygulanamaz ve tamamen
geri alınır (sürüm `0002`de kalır, satır dönüştürülmez, geçici tablo kalmaz);
`0004`te yazılmış nesne ilişkisi `0005`e taşınır, kendine dönen satır artık
kabul edilir, indeks ve kısıt adları korunur, `head → 0004` kendine dönen
satır varken kısıt hatasıyla düşüp geri alınır, satır silinince geri alınır
ve kısıt döner, tekrar `head` sıfırdan kurulanla aynı şemayı verir;
`0005`te yazılmış tanım / nesne / özellik / ilişki / hiyerarşi satırları
`0006`ya olduğu gibi taşınır, belge zinciri tabloları boş gelir, belge
zinciri satırı varken `0006 → 0005` düşer ve uygulanmaz, satırlar silinince
geri alınır ve tablolar gider, tekrar `0006` aynı şemayı ve `head` sıfırdan
kurulanla aynı şemayı verir; `0006`da yazılmış tanım / nesne / belge / okuma /
kaynak satırları `0007`ye olduğu gibi taşınır, taslak tabloları boş gelir,
`kaynak (id, okuma_id)` benzersiz indeksi eklenir, taslak satırı varken `0007
→ 0006` düşer ve uygulanmaz, satırlar silinince geri alınır, tablolar ve
indeks gider, eski veri yerinde kalır, tekrar `head` sıfırdan kurulanla aynı
şemayı verir; elle yazılan göçlerin ürettiği şema ORM
metadata'sıyla Alembic karşılaştırmasında farksızdır; her uygulama tablosunun
birincil anahtar, dış anahtar (`RESTRICT`), benzersizlik, kontrol ve indeks
adları `KISIT_ADLANDIRMA` kalıbındadır ve beklenen listeyle birebirdir;
başlangıç akışı göç çalıştırmaz; `alembic.ini` adres
taşımaz; komut satırı `alembic upgrade head` başka bir çalışma dizininden
merkezi yolu kullanır, stdout'a yazmaz, süreç içi göçle aynı şemayı verir.

## Tanım sistemi

Aşama 4.2 (2026-09-18; Yeniden İnşa Teknik Planı madde 6 ve 27). Çekirdek
hangi nesne türlerinin, özelliklerin, ilişkilerin ve kayıt türlerinin var
olduğunu bilmez; bunları **tanım verisi** olarak tutar. Bir domain (ileride
`defteriki.finans`) kendi kavramlarını bu tablolara satır olarak yazar.
Çekirdek `TEST_KISI` ile `BANKA` arasında fark görmez; aynı şema ve işlevler
kütüphane, envanter ya da sağlık tanımları için de aynen çalışır. Bu aşamada
gerçek finans tanımı yüklenmez, `finans/` boştur; testler nötr sahte
paketlerle (`DEMO`: `TEST_KISI`, `TEST_CIHAZ`, `TEST_OLAY`; `ENVANTER`: `DEPO`,
`RAF`, `URUN`) çalışır.

**Tablolar (`src/defteriki/cekirdek/tanim_tablolari.py`, göç `0002`).** Her
satır bir üsttekine dış anahtarla (`ON DELETE RESTRICT`) bağlıdır; bütün
kısıtlar isimlidir (`pk_`, `fk_`, `uq_`, `ck_`, `ix_` kalıbı).

| Tablo | Ne tutar | Benzersizlik |
|---|---|---|
| `tanim_paketi` | bir domain'in tanımlarını gruplayan paket | `kod` |
| `tanim_surumu` | paketin sürümü; `typeof(surum_no) = 'integer' AND surum_no > 0` (kontrol kısıtı, göç `0003`); `kilitli` (göç `0004`: altında nesne üretilince 1, ikili kontrol kısıtı) | `(tanim_paketi_id, surum_no)` |
| `nesne_turu` | sürümdeki nesne türü | `(tanim_surumu_id, kod)`; ayrıca `(id, tanim_surumu_id)` bileşik dış anahtar hedefi |
| `ozellik_tanimi` | nesne türünün özelliği; `deger_turu` (metin / tam_sayi / mantiksal / ondalik, kontrol kısıtı) ve `zorunlu` (ikili) göç `0004` ile | `(nesne_turu_id, kod)`; ayrıca `(id, nesne_turu_id)` bileşik dış anahtar hedefi |
| `iliski_tanimi` | iki nesne türü arasında yönlü ilişki (kaynak → hedef) | `(tanim_surumu_id, kod)`; kaynak ve hedef için `ix_` indeksleri; `(id, tanim_surumu_id, kaynak_nesne_turu_id, hedef_nesne_turu_id)` benzersiz indeksi nesne ilişkisinin bileşik dış anahtarı için (göç `0004`) |
| `hiyerarsi_kurali` | bir ilişki tanımını hiyerarşik üst bağlantısı yapan kural (göç `0004`): `en_az_ust` ≥ 0, `en_cok_ust` ≥ 1 ve ≥ en az ya da NULL (sınırsız), `ust_yasam_durumu` (etkin / kapali / NULL); kontrol kısıtları depolama sınıfını da denetler | `iliski_tanimi_id` (bir ilişkinin en çok bir kuralı) |
| `kayit_turu` | sürümdeki kayıt (olay) türü | `(tanim_surumu_id, kod)` |
| `kayit_alani_tanimi` | kayıt türünün alanı | `(kayit_turu_id, kod)` |

Tanımlar pakete değil **sürüme** bağlıdır: paketin yeni sürümü eskisinin
satırlarını değiştirmez, kendi satırlarını taşır; aynı kod iki sürümde iki
ayrı satırdır. Böylece ileride bir nesne ya da kayıt hangi tanım sürümü
altında üretildiğini sürüm kimliğiyle taşır ve mevcut verinin anlamı bir
tanım değişince sessizce değişmez. İlişkinin kaynak ve hedef türü ilişkinin
kendi sürümünde olmak zorundadır; bu, `iliski_tanimi` üzerindeki iki bileşik
dış anahtarla (`(kaynak_nesne_turu_id, tanim_surumu_id)` ve `(hedef_...,
tanim_surumu_id)` → `nesne_turu(id, tanim_surumu_id)`) veritabanında da
zorlanır. Her tanımda `kod` makine kimliğidir, `gosterim_adi` insan için
başlıktır; ikisi karıştırılmaz. `aciklama` isteğe bağlıdır. Paket ve sürüm
`olusturma_zamani` taşır (UTC, saat dilimsiz). ORM sınıflarında `relationship`
yoktur; işlem kapandıktan sonra elde kalan nesne yalnız kendi sütunlarını
taşır.

**Kod biçimi** (`tanim_islemleri.KOD_BICIMI`): ASCII harfle başlar, harf,
rakam ve alt çizgi ile sürer; büyük-küçük harf ayrımı vardır, kod verildiği
gibi saklanır ve karşılaştırılır (`Demo` ile `DEMO` iki ayrı koddur). Gösterim
adı boş olamaz. Sürüm numarası çağıranın verdiği pozitif tam sayıdır; sistem
türetmez, sıralama zorunluluğu yoktur. "Tam sayı" gerçek `int` demektir:
tip ipucu çalışma zamanında denetlemediğinden `surum_tanimla` `float`
(`1.5`, `1.0`), `bool` (`True`, `False`) ve metin (`"1"`, `"abc"`) değerleri
`GecersizTanim` ile reddeder, ham `TypeError` sızmaz (2026-09-18
incelemesi). Veritabanında da SQLite INTEGER sütunu katı tür olmadığından
kontrol kısıtı depolama sınıfını denetler: `1.5` (REAL) ve `'abc'` (TEXT)
ham SQL ile de reddedilir. Kayıpsız dönüşen `2.0` ya da `'3'` SQLite tür
yakınlığıyla kısıttan önce tam sayıya çevrilir ve tam sayı olarak saklanır;
bu SQLite davranışıdır, uygulama katmanı bu türleri zaten kabul etmez.

**İşlevler (`tanim_islemleri.py` ve `tanim_sorgulari.py`).** İki modül,
tek yüzey: yazma işlevleri ve hata modelinin yazma tarafı `tanim_islemleri`
içindedir; kimlikle getirme ve listeleme ile `TanimHatasi` / `TanimBulunamadi`
`tanim_sorgulari` içindedir ve `tanim_islemleri` bunları yeniden dışa
aktarır. Ayrımın nedeni mimari sınırdır (2026-09-20): ekleme-yalnız kilit
mevcut kesin veriye bakmak için `nesne_tablolari` import eder; taslak
modülleri kesin nesne dünyasına ulaşamayacağından (`tests/test_mimari_sinir.py`)
yalnız okuyan modüller (`nesne_islemleri`, `taslak_islemleri`) `tanim_sorgulari`
kullanır. Her işlev açık bir `Session` alır ve `Veritabani.islem()` içinde
çağrılır, kendi başına commit etmez. Yazma:
`paket_tanimla`, `surum_tanimla`, `nesne_turu_tanimla`, `ozellik_tanimla`
(Aşama 4.3'ten beri `deger_turu: DegerTuru` zorunlu, `zorunlu: bool = False`),
`iliski_tanimla`, `hiyerarsi_kurali_tanimla` (4.3), `kayit_turu_tanimla`,
`kayit_alani_tanimla` (satırı ekler, `flush` eder, kimlik atanmış ORM
nesnesini döndürür). Okuma: `paket_bul`, `paketleri_listele`,
`surumleri_listele`, `surum_kilitli_mi` (4.3), `nesne_turlerini_listele`,
`nesne_turu_getir`, `ozellik_tanimlarini_listele`, `iliski_tanimlarini_listele`,
`iliski_tanimi_getir`, `hiyerarsi_kurallarini_listele` (4.3),
`kayit_turlerini_listele`, `kayit_alani_tanimlarini_listele`. Üst kaydı
olmayan listeleme boş liste değil hata verir; boş liste ile "üst kayıt yok"
karışmaz. Tanım silme ve güncelleme işlevi yoktur.

**Hata modeli.** Hepsi `TanimHatasi` altında, domain bağımsız:
`GecersizTanim` (kod biçimi, boş gösterim adı, pozitif tam sayı olmayan sürüm no;
`ValueError`), `TanimBulunamadi` (verilen paket/sürüm/tür kimliği yok;
`LookupError`), `MukerrerTanim` (aynı kapsamda aynı kod ya da sürüm no),
`TanimSurumuUyusmuyor` (ilişkinin kaynak/hedef türü başka sürümde),
`TanimSurumuKilitli` (4.3; 2026-09-19'dan beri ekleme-yalnız: ekleme mevcut
kesin veriyi bozardı, bkz. "Nesne motoru" bölümünde "Tanım sürümü kilidi").
Bu denetimler uygulama sözleşmesidir; veritabanı kısıtları son savunmadır ve
aynı durumları ham `IntegrityError` ile de reddeder (testte iki düzey ayrı
ayrı sınanır). Herhangi bir hata `islem()` bağlamında yükselir ve aynı
işlemdeki bütün yazmalar geri alınır.

**Testler** (`tests/test_tanim_sistemi.py`, gerçek SQLite, göç zinciriyle
kurulmuş şema): paket tanımlanır ve okunur; aynı kodla ikinci paket hem
uygulama hem veritabanı düzeyinde reddedilir; büyük-küçük harf ayrımı;
geçersiz kod biçimleri (boş, boşluklu, rakamla ya da alt çizgiyle başlayan,
Türkçe harfli, noktalama) ve boş gösterim adı reddedilir; sürüm tanımlanır ve
numaraya göre listelenir, aynı pakette aynı numara reddedilir, farklı
paketlerde serbesttir, sürüm numarası sözleşmesi on değerle sabittir (`1`,
`7` kabul; `0`, `-1`, `1.5`, `1.0`, `True`, `False`, `"1"`, `"abc"`
`GecersizTanim`), kontrol/benzersizlik/dış anahtar kısıtları ham SQL ile de
çalışır ve REAL/TEXT sürüm numarası veritabanında reddedilir; nesne türü tanımlanır, aynı sürümde aynı
kod reddedilir, aynı kod başka sürümde ayrı satırdır, olmayan sürüme
eklenemez, dış anahtar veritabanında çalışır; özellik türe bağlanır ve
tanımlanma sırasıyla listelenir, aynı türde aynı kod reddedilir, farklı türde
serbesttir; ilişki kaynak ve hedefe yönlü bağlanır, ters yön ayrı tanımdır,
türün kendisiyle ilişkisi kurulabilir, aynı kod reddedilir, başka sürümdeki
tür kaynak ya da hedef olarak reddedilir ve aynı çapraz sürüm bileşik dış
anahtarla veritabanında da reddedilirken aynı sürümdeki çift geçer; kayıt
türü ve alanı için aynı kurallar; hatalar ortak tabandan türer; işlem
içindeki hata (sentetik, mükerrerlik, veritabanı kısıtı) aynı işlemdeki
önceki yazmaları da geri alır ve veritabanı kullanılabilir kalır; işlem
kapandıktan sonra dönen nesneler okunabilir; iki farklı sahte domain (`DEMO`,
`ENVANTER`) aynı tablolarda aynı işlevlerle yan yana tanımlanır.

**Aşama 4.3 ile gelenler:** özellik değer türü ve zorunluluk, hiyerarşi
kuralı (çokluk, zorunluluk, üstün gerekli durumu), sürüm kilidi — hepsi
"Nesne motoru" bölümünde. **Hâlâ yok (bilinçli):** kayıt alanı için veri
tipi (kayıt sistemi Aşama 4.7'de); tanım silme ve güncelleme; finans tanım
paketi (Aşama 4.10).

## Nesne motoru

Aşama 4.3 (2026-09-19; Yeniden İnşa Teknik Planı madde 7, 8 ve 28). Çekirdek
bir nesnenin ne olduğunu bilmez: nesne, bir nesne türü tanımına bağlı kimlik,
yaşam durumu ve zaman damgasıdır; anlamı, özellikleri, ilişkileri ve
hiyerarşi kuralları tanım verisinden gelir. Aynı kod envanter, kütüphane ya
da başka bir alan için değişmeden çalışır; testler nötr `ENVANTER` dünyasıyla
(`DEPO`, `BOLGE`, `RAF`, `URUN`) yapılır, `finans/` boştur.

**Tablolar (`src/defteriki/cekirdek/nesne_tablolari.py`, göç `0004`).** Bütün
kısıtlar isimlidir; dış anahtarlar `ON DELETE RESTRICT`.

| Tablo | Ne tutar | Veritabanı düzeyinde korunan |
|---|---|---|
| `nesne` | `nesne_turu_id`, `tanim_surumu_id`, `yasam_durumu`, `olusturma_zamani` | tür ve sürüm iki rastgele dış anahtar değildir: `(nesne_turu_id, tanim_surumu_id)` bileşik dış anahtarla `nesne_turu (id, tanim_surumu_id)` çiftine bağlıdır, türün o sürüme ait olduğu zorlanır; `yasam_durumu IN ('etkin', 'kapali')`; `(id, nesne_turu_id)` ve `(id, nesne_turu_id, tanim_surumu_id)` benzersiz (alt tabloların bileşik dış anahtar hedefleri); tür ve sürüm indeksleri |
| `nesne_ozelligi` | `nesne_id`, `nesne_turu_id`, `ozellik_tanimi_id`, `deger` (kanonik metin) | iki bileşik dış anahtar aynı `nesne_turu_id` üzerinden: `(nesne_id, nesne_turu_id) → nesne` ve `(ozellik_tanimi_id, nesne_turu_id) → ozellik_tanimi`; başka türün özelliği yazılamaz; `(nesne_id, ozellik_tanimi_id)` benzersiz (aynı özellik iki kez yok) |
| `nesne_iliskisi` | `iliski_tanimi_id`, `tanim_surumu_id`, kaynak/hedef tür ve nesne kimlikleri | dörtlü bileşik dış anahtar `iliski_tanimi (id, sürüm, kaynak tür, hedef tür)`, üçlü bileşik dış anahtarlar `nesne (id, tür, sürüm)` kaynak ve hedef için: kaynak nesnenin türü tanımın kaynak türü, hedefinki hedef türü, üçü aynı sürümde; `(iliski_tanimi_id, kaynak_nesne_id, hedef_nesne_id)` benzersiz (mükerrer ilişki yok); kaynak ve hedef indeksleri. Kendine dönüş kısıtı yoktur (`0004`teki kısıt `0005` ile kalktı) |

`iliski_tanimi` üzerindeki `(id, tanim_surumu_id, kaynak_nesne_turu_id,
hedef_nesne_turu_id)` benzersiz indeksi ve `ozellik_tanimi` üzerindeki `(id,
nesne_turu_id)` benzersizliği bu bileşik dış anahtarların hedefleridir.
Sayım kuralları (en az / en çok üst) ve hiyerarşik çevrim SQL ile güvenli
ifade edilemediğinden yalnız serviste doğrulanır; tetikleyici yoktur.

**Nesne modeli.** `nesne_olustur(oturum, nesne_turu_id, ozellikler,
ust_baglantilar)` tek işte nesneyi (etkin), başlangıç özelliklerini ve üst
bağlantılarını yazar, türün bütün hiyerarşi kurallarını doğrular ve tanım
sürümünü kilitler. Başarılı dönüşte nesne zorunlu özelliklerini taşır ve
kuralları sağlar; "önce boş nesne, sonra belki özellik" yolu yoktur (taslak
Aşama 4.5'in işidir). Nesne hangi sürümde üretildiyse `tanim_surumu_id` kalıcıdır.

**Servis hata atomikliği (2026-09-19 incelemesi).** Servisler dış işlemin
sahibi değildir, commit ve dış rollback yapmaz; ama başarısız bir çağrı,
hatası çağıran tarafından aynı işlem içinde yakalansa bile kendi yarattığı
hiçbir kısmi değişikliği bırakmaz. Yöntem iki katmanlıdır: mümkün olan her
doğrulama yazmadan önce yapılır (özellik kodu, tür ve zorunluluk; ilişkide
tür, sürüm, mükerrerlik, üstün durumu, en çok üst ve çevrim; kaldırmada bu
bağlantı sayılmadan en az üst; durum değişiminde aday durumla çocuklar), ve
her yazma işlevi kendi SAVEPOINT'i içinde çalışır (`Session.begin_nested`),
böylece yazma sonrası ancak anlaşılan ihlaller (nesne oluşturmada bütün
bağlantılar yazıldıktan sonra en az üst kuralı) ve veritabanı kısıt hataları
yalnız o çağrının değişikliklerini geri alır; dış işlem kullanılabilir kalır
ve sonraki geçerli iş commit edilir. SAVEPOINT'in 4.1'in `autocommit=False`
bağlantı kipinde çalıştığı doğrulanmıştır.

**Özellik modeli ve değer türleri.** `NESNE → NESNE ÖZELLİĞİ → ÖZELLİK
TANIMI`; değerler ana tabloya sütun olarak eklenmez. `OzellikTanimi.deger_turu`
dört teknik, domain bağımsız türden biridir (`DegerTuru`): `metin` (`str`),
`tam_sayi` (`int`; `bool` reddedilir), `mantiksal` (`bool`), `ondalik`
(`decimal.Decimal`, sonlu; `float` reddedilir, ölçek ya da birim varsayımı
yoktur). Değer tanımın türüne göre doğrulanır ve kanonik metin olarak
saklanır (metin olduğu gibi, `str(int)`, `"1"`/`"0"`, ondalık aşağıdaki
sayısal kanonik biçimde); `ozellikleri_oku` aynı kuralla Python değerine
döner. Kodlama kuralı Aşama 4.5'ten itibaren
`src/defteriki/cekirdek/deger_kodlama.py` içindedir ve aday özellikle
(`taslak_islemleri`) ortaktır; nesne motoru hatayı kendi modeline
(`OzellikTuruUyusmuyor`) sarar. Yanlış tür `OzellikTuruUyusmuyor`, tanımsız ya da başka türün
özelliği `GecersizOzellik`, eksik zorunlu özellik `ZorunluOzellikEksik` verir.

**Ondalık kanonik biçim (karar 2026-09-19, inceleme bulgusu).** Önceki
`str(Decimal)` kodlaması sayısal olarak kanonik değildi: `1.0`, `1.00` ve
`1E+2` gibi eşit değerler farklı metin veriyordu; Aşama 4.6'nın mükerrerlik
şartı "birebir değer" karşılaştırmasına dayandığından bu sessiz kaçırma
demekti. Yeni kural: matematiksel olarak eşit iki `Decimal` her zaman aynı
metni verir, farklı iki değer farklı metin verir. Biçim
`<işaret><katsayı>e<üs>`: katsayı sondaki sıfırlardan arındırılmış rakam
dizisi, üs buna göre düzeltilmiş tam sayı; bütün sıfırlar (`-0`, `0.00`) tek
`0`. Örnek: `1`, `1.0`, `1.00`, `1E+0` → `1e0`; `100`, `1E+2` → `1e2`;
`12.50` → `125e-1`; `0.0100` → `1e-2`; `-0.00` → `0`. Kodlama
`Decimal.as_tuple` ile yapılır: `decimal` bağlam hassasiyetinden bağımsızdır
(`normalize()` bilerek kullanılmaz, bağlamda yuvarlayabilir), basamak
kaybolmaz, çok büyük / küçük üsler (`1E+999999`) sabit noktalı dev metne
açılmaz. Çözme `Decimal(metin)` ile tam hassasiyette geri döner; değer
sayısal olarak aynıdır, **ölçek korunmaz** (`12.50` yazılır, `Decimal("12.5")`
ile eşit değer okunur). Bu biçim iç depolamadır, ekranda gösterim GUI'nin
işidir; okunabilirlik bilinçli olarak feda edilmiştir. `float`, `bool`, `NaN`
ve sonsuz reddi değişmedi. Testler (`tests/test_deger_kodlama.py`): örnek
kümeleri, bağlam hassasiyeti 5'e düşürülmüşken yuvarlamama, yüksek
hassasiyet, uç üsler ve Hypothesis özellikleri (`a == b` ⇔ aynı metin;
`çöz(kodla(a)) == a`; sona sıfır eklenmiş yazım aynı metin; sıfırlar tek
metin). Kesin ve aday özelliğin aynı metni yazdığı `tests/test_islem_paketi.py`
içinde ham tablo metniyle sınanır.
`ozellik_yaz` var olan değeri günceller (aynı özellik iki satır olmaz),
`ozellik_sil` isteğe bağlı özelliği kaldırır, zorunluyu kaldırmaz. IBAN, kart
numarası, para birimi gibi domain doğrulamaları yoktur; bunlar ileride tanım
ve kural verisinin işidir.

**İlişkiler.** `iliski_kur(oturum, iliski_tanimi_id, kaynak_nesne_id,
hedef_nesne_id)`: tanım var mı, iki nesne var mı, kaynak nesnenin türü
tanımın kaynak türü mü, hedefinki hedef türü mü, üçü aynı tanım sürümünde mi,
aynı ilişki zaten var mı; hepsi serviste (`GecersizIliski`,
`MukerrerIliski`) ve bileşik dış anahtar / benzersizlik kısıtlarıyla
veritabanında reddedilir. Hiyerarşik olmayan genel ilişkide nesnenin
kendisine dönmesine (`A → A`) çekirdek karışmaz; geçerli olup olmadığı
domain'in işidir (2026-09-19 incelemesi; önceki evrensel yasak ve `0004`teki
kontrol kısıtı kaldırıldı). `iliski_kaldir` hiyerarşik ilişkide çocuğun en
az üst kuralını bozamaz. `iliskileri_listele` nesnenin kaynak ya da hedef
olduğu ilişkileri verir.

**Hiyerarşi.** Genel ilişki ile hiyerarşik üst bağlantısı ayrıdır: bir
ilişki tanımının `hiyerarsi_kurali` satırı varsa hiyerarşiktir; yön sabittir,
ilişkinin **kaynağı çocuk, hedefi üst** türdür. Kural tanım verisiyle şu
soruları cevaplar: çocuk tür (kaynak), üst tür (hedef), en az üst sayısı
(`en_az_ust`; zorunluluk = `en_az_ust >= 1`), en çok üst sayısı (`en_cok_ust`;
NULL sınırsız), üstün gerekli yaşam durumu (`ust_yasam_durumu`; NULL fark
etmez). Sayısal seviye kavramı yoktur; çekirdek beş seviyeli ya da başka bir
sabit yapı varsaymaz, `if seviye == 3` benzeri dal içermez. Aynı çocuk
birden fazla üste bağlanabilir (testte ürün iki rafa, başka sürümde üç rafa).
Kural her zaman korunur, yalnız oluştururken değil: üst olmadan çocuk
oluşturmak, gerekli son üst bağlantısını kaldırmak, en çok üst sayısını
aşmak, gerekli durumda olmayan üste bağlanmak ve üstün yaşam durumunu
değiştirip mevcut çocuğu geçersiz bırakmak `HiyerarsiIhlali` ile reddedilir.
Sayım kuralı yaşam durumundan bağımsızdır: toplam üst bağlantısı
`en_cok_ust`'ü aşamaz; gerekli durumdaki üst sayısı `en_az_ust`'ten az olamaz,
çocuk kapalı olsa da. Yani etkin ya da kapalı çocuk son zorunlu üstünü
kaybedemez ve üstün durum değişikliği kuralı ihlal ediyorsa çocuk kapalı
diye sessizce geçilmez (2026-09-19 incelemesi; kapalı çocuk istisnası koddan
kaldırıldı, böyle bir esneklik istenirse tanım verisi kararı olur). Sonuç:
`DEPODA` gibi "tam bir etkin üst" kuralı olan bir çocuk varken üst
kapatılamaz; önce bağlantı kuralın izin verdiği biçimde değişmelidir.

**Çevrim yasağı.** Hiyerarşik ilişki eklenirken (nesne oluştururken verilen
bağlantılar dahil) çocuğun zaten üstün dolaylı üstü olup olmadığı denetlenir:
üstten başlayarak bütün hiyerarşik ilişki tanımlarının üst bağlantıları
yukarı doğru genişlik öncelikli izlenir, çocuğa ulaşılırsa `HiyerarsiIhlali`.
Nesne kendi üstü olamaz, `A → B → … → A` oluşamaz; çevrim farklı hiyerarşik
ilişki tanımları üzerinden de olsa yakalanır. Denetim yalnız kuralı olan
ilişkileri izler; hiyerarşik olmayan ilişkiler grafiğe girmez.

**Yaşam durumu.** `YasamDurumu`: `etkin` / `kapali`; nesne etkin doğar, geçiş
yalnız `yasam_durumunu_degistir` ile. Her değişimde ondan durum isteyen
kuralların çocukları aday durumla, yazmadan önce doğrulanır; ihlal varsa
durum değişmez. Taslak, bekliyor, onay, şüpheli, mükerrer, reddedildi
gibi durumlar yoktur; Aşama 4.5 / 4.6'nın işidir.

**Tanım sürümü kilidi: ekleme-yalnız (karar 2026-09-19, inceleme bulgusu).**
Sürüm altında ilk kesin nesne üretilirken, aynı işlem içinde
`tanim_surumu.kilitli` 1 yapılır; işlem rollback olursa kilit de kalkar.
4.3'teki ilk kural kilitli sürümü tamamen kapatıyordu; incelemede şu sonuç
görüldü: ilişki tanımı, kaynak ve hedef nesne aynı sürümde olmak zorunda ve
nesnenin sürümü kalıcı olduğundan, tek bir özellik eklemek için açılan yeni
sürümün nesneleri eski sürümün nesnelerine bağlanamıyor, her ekleme defteri
bölüyordu. Yeni kural: kilit "hiçbir şey eklenemez" değil, "mevcut kesin
verinin anlamını ya da geçerliliğini geriye dönük bozan ekleme yapılamaz"
demektir. Denetim sürüm bayrağına değil **yerel veriye** bakar (bayrak yalnız
hızlı ön kontroldür; kilitsiz sürümün altında kesin nesne olamaz):

* yeni nesne türü, yeni ilişki, yeni kayıt türü, yeni kayıt alanı her zaman
  serbest (yeni tanımın altında veri yoktur);
* yeni isteğe bağlı özellik her zaman serbest (eski nesnede yalnız
  "yazılmamış" sayılır, `ozellikleri_oku` onu döndürmez);
* yeni **zorunlu** özellik yalnız o nesne türünün altında kesin nesne (etkin
  ya da kapalı) yoksa; kilitten sonra eklenen, henüz kullanılmamış tür
  zorunlu özellik alabilir; kullanılan türe `TanimSurumuKilitli`;
* hiyerarşi kuralı yalnız o ilişkiyle kurulmuş kesin bağlantı yoksa (mevcut
  bağlantılar `en_cok_ust` sınırını ya da çevrim yasağını ihlal ediyor
  olabilir) **ve** `en_az_ust > 0` ise kaynak türün altında kesin nesne yoksa
  (yalnız "bağlantı yok" yetmez: 50 raf olup hiç bağlantı olmayabilir,
  `en_az_ust = 1` hepsini bir anda kurala aykırı yapardı);
* tanım değiştirme ve silme işlevi yoktur; test bunu sınar. Bu API
  düzeyinde korumadır: oturuma doğrudan erişen kod ORM alanını
  değiştirebilir, bu kapsam dışıdır ve bilinçli sınırdır (MCP ve GUI oturuma
  değil işlevlere erişir).

Aday (taslak) nesneler sayılmaz. Çapraz sürüm ilişki yasağı aynen durur ve
sürümler arası nesne taşıma ilk sürümde desteklenmez; bozan değişiklik
gerçekten gerekirse yeni sürüm açılır (`surum_tanimla` serbest) ama yeni
sürümün nesneleri eskilerle bağlanamaz. **Sonuç:** ilk sürüm pratikte tek
tanım sürümünü ekleme-yalnız büyüterek yaşar. Ayrı bir "yayınla" iş akışı
yoktur. Kilit yalnız uygulama düzeyindedir (tetikleyicisiz SQLite'ta ifade
edilemez; bilinçli sınır). Bilinen sınır: yerel sayım veriye baktığından,
biri zorunlu özellik eklerken diğeri o türden ilk nesneyi yazarsa SQLite
ikisinden birini kilit / anlık görüntü çakışmasıyla durdurur; tanım tarafı bu
ham hatayı çevirmez ("İşlem paketi ve taslak" bölümündeki eşzamanlı yazma
sözleşmesi yalnız taslak modülündedir).

**Hata modeli (`NesneHatasi` altında):** `NesneBulunamadi` (`LookupError`),
`GecersizOzellik` (`ValueError`) ve alt sınıfları `OzellikTuruUyusmuyor`,
`ZorunluOzellikEksik`; `GecersizIliski` (`ValueError`) ve alt sınıfı
`MukerrerIliski`; `HiyerarsiIhlali` (en az / en çok üst, üstün durumu,
çevrim); `YasamDurumuIhlali`. Tanım hataları
(`TanimBulunamadi`, `TanimSurumuKilitli`) `tanim_islemleri`'nden olduğu gibi
gelir. Ham `IntegrityError` sözleşme değildir; veritabanı kısıtları servisi
atlayan yazmaya karşı son savunmadır.

**İşlem sınırı.** 4.1 kuralı: servisler `commit` etmez; çağıran
`Veritabani.islem()` sahibidir. Nesne, özellikleri, bağlantıları ve sürüm
kilidi tek transaction'dadır; ortada hata çıkarsa hiçbir parça kalmaz.

**Servis yüzeyi (`src/defteriki/cekirdek/nesne_islemleri.py`):**
`nesne_olustur`, `nesne_getir`, `nesneleri_listele`,
`yasam_durumunu_degistir`, `ozellik_yaz`, `ozellik_sil`, `ozellikleri_oku`,
`iliski_kur`, `iliski_kaldir`, `iliskileri_listele`; `UstBaglanti`
(`iliski_tanimi_id`, `hedef_nesne_id`) nesne oluştururken verilen bağlantı.

**Testler** (`tests/test_nesne_motoru.py`, gerçek SQLite, göç zinciriyle
kurulmuş şema; tanım tarafı `tests/test_tanim_sistemi.py`): geçerli türle
nesne oluşturulur ve üretildiği sürüm kalıcıdır; olmayan tür reddedilir; tür
ve sürüm uyuşmazlığı ham SQL ile bileşik dış anahtarca reddedilir; dört değer
türü yazılır ve aynı değerle okunur (kanonik metin doğrulanır); başka türün
özelliği serviste ve iki bileşik dış anahtarla veritabanında reddedilir;
tanımsız özellik, on üç yanlış tür durumu (`"10"`, `1.5`, `True`, `Decimal`
tam sayıya; `5`, `None` metne; `1`, `"1"` mantıksala; `1.5`, `"1.5"`, `1`,
`NaN`, `Infinity` ondalığa) reddedilir; zorunlu özellik olmadan nesne
oluşmaz, isteğe bağlı olmayabilir; `ozellik_yaz` günceller ve tek satır
kalır, ham SQL ile ikinci satır benzersizlikçe reddedilir; silme kuralları;
geçerli ilişki kurulur ve iki yönden listelenir; hiyerarşik olmayan ilişki
sayı kuralı taşımaz; ters tür çifti, başka sürümdeki tanım ve mükerrer ilişki
hem serviste hem veritabanında reddedilir; hiyerarşik olmayan ilişki kendine
dönebilir; hiyerarşik `A → A` reddedilir; hiyerarşik `A → B`, `B → C` geçer,
`C → A` ve `B → A` reddedilir ve kısmi ilişki kalmaz; farklı hiyerarşik
tanımlar üzerinden oluşan çevrim de reddedilir; hiyerarşik olmayan yol
çevrim sayılmaz; olmayan tanım /
nesne reddedilir; iki farklı üst desteklenir; zorunlu üst olmadan nesne
oluşmaz ve hiçbir satır kalmaz; izin verilmeyen üst türü reddedilir; en çok
üst hem oluştururken hem sonradan aşılamaz; üst sayıları tanım verisinden
okunur (başka sürümde en az iki, sınırsız üst); zorunlu son üst bağlantısı
kaldırılamaz, fazladan olan kaldırılabilir; kapalı üste bağlanılamaz; üstü
kapatmak çocuğu bozuyorsa çocuk etkin de kapalı da olsa reddedilir, kapalı
çocuk son zorunlu üstünü kaybedemez, çocuksuz üst kapatılıp açılabilir;
ikinci üst varken biri kapatılabilir; isteğe bağlı üst kuralı (bölgesiz raf,
kapalı bölge olur, ikinci bölge olmaz, bağlantı kaldırılabilir); yaşam durumu
servisle değişir, aynı duruma geçiş etkisizdir, geçersiz değer serviste ve
kontrol kısıtıyla reddedilir; özellik / ilişki / hiyerarşi hatasında nesne ve
kısmi satır kalmaz, kilit de kalkar; veritabanı kısıt hatasından sonra
veritabanı kullanılabilir kalır; servis hata atomikliği: eksik zorunlu
özellik, zorunlu üst eksikliği, en çok üst, son üstü kaldırma, üst durum
değişikliği ve çevrim hataları aynı işlem içinde yakalanınca nesne / fazla
ilişki / durum değişikliği kalmaz ve kilit oluşmaz, hatadan sonra aynı
işlemde geçerli iş yapılıp commit edilir, servis içi kısıt hatası dış işlemi
bozmaz; ekleme-yalnız kilit: kullanılmamış sürüme tanım eklenir, ilk nesne
kilitler (satırda `kilitli = 1`), rollback olan işlemde kilit kalmaz, kilitli
sürüme yeni tür ve kullanılmamış türe zorunlu özellik / zorunlu üst şartı
eklenir ve o türden nesne üretilir, kullanılan türe isteğe bağlı özellik ve
kayıt türü / alanı eklenir ve eski nesne geçerli kalır (okunur, yeni özellik
yazılır, durumu değişir), kullanılan türe zorunlu özellik reddedilir (kapalı
nesne de sayılır), kullanılan kaynak türe `en_az_ust > 0` kuralı reddedilir
ama `en_az_ust = 0` eklenir, kesin bağlantısı olan ilişkiye kural eklenemez,
kullanılan türe zaten var olan zorunlu özellik "kilitli" değil "zaten var"
ile reddedilir (mükerrerlik denetimi kilitten önce), tanım değiştirme / silme
API'si yoktur, yeni sürüm açılır ve kendi
tanımlarını taşır, eski nesnenin anlamı yeni sürümle değişmez.

**Bilinçli kapsam dışı (Aşama 4.3'te yok):** belge ve arşiv, kaynak izi, işlem
paketi ve taslak nesne, BEKLIYOR protokolü, kullanıcı onayı, mükerrerlik ve
birleştirme, kayıt / hareket sistemi, kural motoru, projection, finans tanım
paketi, MCP nesne araçları, GUI; nesne silme; tanım silme ve güncelleme;
kilit ve çevrim için veritabanı düzeyi koruma.

## Belge zinciri

Aşama 4.4 (2026-09-19; Yeniden İnşa Teknik Planı madde 11, 12, 13, 20, 23, 24
ve 29). Belge zincirinin bu aşamada kurulan kısmı:

```
DOSYA → ARŞİV → BELGE → OKUMA → KAYNAK
```

Aday nesneler / kayıtlar, doğrulama, onay / şüphe / mükerrerlik ve kaydet
halkaları sonraki aşamalardır. Çekirdek belgenin ne olduğunu bilmez: banka
ekstresi, fatura, fiş gibi belge türleri Python kodunda yoktur; bir PDF ile bir
envanter listesi arasında çekirdek açısından fark yoktur. Aynı sistem sağlık,
envanter, arşiv ya da hukuk belgeleri için kullanılabilir; `finans/` boştur.
Testler sentetik envanter PDF'i, metin ve sahte PNG / JPEG baytlarıyla çalışır.

**Kavramlar.** *Arşiv dosyası* arşivdeki değişmez baytların kaydıdır. *Belge*
uygulamadaki belge kimliğidir; fiziksel dosyanın kendisi değildir ve bir
arşiv dosyasından en çok bir belge olur. *Okuma* dış okuyucunun (Cowork)
belgeden çıkardığı yapılandırılmış içeriğin belirli bir sürümüdür; çekirdek
belgeyi kendisi okumaz, LLM çağırmaz. *Kaynak* provenance çapasıdır: bu veri
hangi belgenin hangi okumasından ve mümkünse belgenin neresinden geldi?
Okuma içeriği kesin kayıt değildir; "okuma tamamlandı = deftere kaydedildi"
semantiği yoktur ("Yazmak ve kayıt etmek" ayrımı, Aşama 4.5 ve sonrası).

**Ayarlar ve bağımlılık.** Gelen dizini `Ayarlar.gelen_dizini`, arşiv dizini
`Ayarlar.belge_dizini`dir; çekirdek modüller (`arsiv`, `belge_islemleri`)
`defteriki.ayarlar`ı import etmez, iki dizini çağırandan `Path` olarak alır.
Import edildiklerinde dizin / dosya oluşturmaz, ortam değişkeni okumaz.

**Gelen dizini sınırı (`src/defteriki/cekirdek/arsiv.py`,
`gelen_dosyayi_dogrula`).** Dosya yalnız izinli gelen dizininden alınır.
Sırayla: yol boş olamaz → mutlak olmalı → `..` parçası olamaz → sözlüksel
olarak gelen dizininin altında olmalı (Windows'ta büyük-küçük harf ayrımsız;
`gelen2/` `gelen/`in altı değildir) → var olmalı → gelen dizininden dosyaya
inen hiçbir parça simgesel bağlantı ya da Windows junction olamaz (hedefi
içeride olsa da) → fiziksel çözülmüş yol (`Path.resolve`) gelen dizininin
fiziksel çözülmüş yolunun altında olmalı → sıradan dosya olmalı (dizin
reddedilir). Gelen dizininin kendisi bağlantı olabilir (ayar kararıdır).
Hata mesajları kategoriktir; yerel yol ya da dosya adı taşımaz.

**Dosya doğrulama.** Domain bağımsızdır. Boş dosya belge değildir. Teknik
kaynak sınırı 50 MiB (`AZAMI_DOSYA_BOYUTU`; finans kuralı değil): aşan dosya
kesilerek kabul edilmez, tamamı reddedilir; `stat` ön denetimine ek olarak
akış sırasında da denetlenir. MIME yalnız ilk baytlardaki imzadan belirlenir
(PDF, PNG, JPEG); imza bilinmiyorsa güvenli genel değer
`application/octet-stream` kullanılır, bilinmeyen tür belgeyi engellemez.
Karar (2026-09-19, inceleme): dosyanın adı ve uzantısı güvenilir içerik bilgisi
**değildir**; uzantı yalnız metadata'dır, imzayla uyuşmaması red sebebi
değildir. `.png` adlı PDF `application/pdf` olarak, `.pdf` adlı imzasız dosya
`application/octet-stream` olarak arşive girer; arşiv baytları saklar,
belgeyi çalıştırmaz. MIME, uzantı ve kaynak dosya adı metadata'dır, fiziksel
kimliğe girmez.

**Arşiv kimliği ve fiziksel yol.** Fiziksel kimliğin tek kaynağı dosya
baytlarının SHA-256 özetidir; uygulama özeti gerçek baytlardan, akışla
(1 MiB parçalar, bütün dosya belleğe alınmaz) kendisi hesaplar. Arşiv yolu
yalnız içerikten türer: `<sha256'nın ilk iki hex karakteri>/<sha256>`,
uzantısız (`ab/abcdef…`). Aynı PDF baytları `a.pdf`, `a.bin`, `a.png`, `a` ya
da `herhangi.xyz` adıyla gelse de tek fiziksel dosyadır ve MIME'ı
`application/pdf`tir; `kaynak_uzantisi` her gelişin kendi metadata'sıdır, DB
kaydında ilk gelişinki kalır. Yol dizin
taramasıyla ya da "SHA ile başlayan dosya" aramasıyla değil doğrudan özetten
hesaplanır. Veritabanına tam yerel yol yazılmaz; `arsiv_dosyasi.goreli_yol`
arşiv köküne göre POSIX yoldur ve `belge_dizini + goreli_yol` çalışma
zamanında kurulur.

**Arşive atomik yazma (`dosyayi_arsivle`).** Gelen dosya doğrulanır → kaynak
akışla okunur, ilk parçadan MIME belirlenir (boş dosya geçici dosya
açılmadan reddedilir) → `<arşiv>/gecici/<rastgele>.tmp` adına
yazılırken SHA-256 ve boyut hesaplanır → `flush` + `fsync` → hedef yol
özetten üretilir, üst dizin oluşturulur → `os.replace` ile aynı dosya sistemi
üzerinde atomik taşınır (POSIX'te dizin girdisi de eşlenir) → geçici dosya
temizlenir. Hangi adım düşerse düşsün geçici dosya silinir; yarım arşiv
dosyası kalmaz. Hedef zaten varsa yalnız boyuta güvenilmez: mevcut dosya
baştan sona özetlenir; aynıysa kopya atılır ve sonuç "diskte zaten vardı"
olur, değilse açık `ArsivButunlukHatasi` (bozuk hedef sessizce duplicate
sayılmaz, onarılmaz). Eşzamanlı iki süreç aynı içeriği getirirse ikisi de
aynı baytları aynı yola bırakır; sonuç tek geçerli dosyadır. Windows'ta hedef
o an açıkken taşıma reddedilirse hedef yine özetle doğrulanır.

**Tablolar (`src/defteriki/cekirdek/belge_tablolari.py`, göç `0006`).** Bütün
kısıtlar isimlidir; dış anahtarlar `ON DELETE RESTRICT`.

| Tablo | Ne tutar | Veritabanı düzeyinde korunan |
|---|---|---|
| `arsiv_dosyasi` | `sha256`, `boyut`, `mime`, `kaynak_uzantisi`, `kaynak_adi`, `goreli_yol`, `olusturma_zamani` | `sha256` benzersiz; `goreli_yol` benzersiz; `sha256` 64 karakter küçük harf onaltılık (`length = 64 AND NOT GLOB '*[^0-9a-f]*'`); `goreli_yol = substr(sha256, 1, 2) \|\| '/' \|\| sha256` (yol yalnız içerikten türer); `typeof(boyut) = 'integer' AND boyut > 0` |
| `belge` | `arsiv_dosyasi_id`, `olusturma_zamani` | `arsiv_dosyasi_id` benzersiz (bir arşiv dosyasından ikinci belge yok) ve dış anahtar |
| `okuma` | `belge_id`, `surum_no`, `durum`, `icerik` (JSON metni), `olusturma_zamani`, `tamamlanma_zamani` | `(belge_id, surum_no)` benzersiz; `(id, belge_id)` benzersiz (kaynağın bileşik dış anahtar hedefi); `typeof(surum_no) = 'integer' AND surum_no > 0`; durum ile içerik / tamamlanma zamanı tutarlılığı (`basladi` ⇒ ikisi NULL, `tamamlandi` ⇒ ikisi dolu; başka durum değeri yok); `icerik IS NULL OR json_valid(icerik)` |
| `kaynak` | `belge_id`, `okuma_id`, `konum` (JSON metni, isteğe bağlı), `olusturma_zamani` | `(okuma_id, belge_id)` bileşik dış anahtarla `okuma (id, belge_id)`: okumanın gerçekten o belgeye ait olduğu zorlanır, iki bağımsız dış anahtar yoktur; `konum IS NULL OR json_valid(konum)`; belge ve okuma indeksleri; `(id, okuma_id)` benzersiz indeksi (göç `0007`; aday nesne / aday kayıt provenance bileşik dış anahtarının hedefi) |

**Servisler (`src/defteriki/cekirdek/belge_islemleri.py`).** Her servis açık
`Session` alır; çağıran `Veritabani.islem` işleminin sahibidir. Servis hata
atomikliği 4.3 kuralıyla sürer: doğrulama yazmadan önce, yazma kendi
SAVEPOINT'inde (`begin_nested`); başarısız çağrı aynı dış işlemde yakalansa
bile kısmi satır bırakmaz, dış işlem kullanılabilir kalır.

* `belge_al(veritabani, yol, gelen_dizini=…, arsiv_dizini=…)` — **tek
  istisna**: dosya sistemi ile SQLite aynı transaction'a giremez, bu
  saklanmaz. Sıra: gelen dosya doğrulanır → içerik güvenli biçimde arşive
  yazılır → SHA-256 kesinleşir → kısa `Veritabani.islem` işleminde
  `belge_tanimla`. Sınırı dardır: başka hiçbir servis kendi işlemini açmaz.
* `belge_tanimla(oturum, arsivlenen, arsiv_dizini)` — hiçbir satır yazmadan
  önce fiziksel dosyanın yerinde, sıradan dosya, beklenen boyutta **ve
  beklenen SHA-256'da** olduğunu baştan sona bir daha doğrular (inceleme
  düzeltmesi 2026-09-19: aynı boyutta bozuk dosya DB'ye bağlanamaz;
  invariant: veritabanındaki belge hiçbir zaman arşive güvenli biçimde
  yazılmamış ya da bozuk dosyaya dayanmaz). Aynı SHA-256 varsa mevcut belgeyi
  `zaten_vardi=True` ile döndürür: ikinci `arsiv_dosyasi`, ikinci fiziksel
  dosya, ikinci `belge` oluşmaz; ilk gelen dosyanın adı / uzantısı metadata
  olarak kalır. Sonuç ayrıca `dosya_zaten_vardi` (fiziksel dosya arşivde
  zaten vardı) bilgisini taşır. Bu **belge seviyesinde SHA-256 duplicate
  algılamasıdır**; işlem anahtarı (işlem seviyesi, madde 23) ve mükerrer
  nesne (nesne seviyesi) ayrı mekanizmalardır ve bu aşamada kurulmadı.
  **Eşzamanlı aynı belge:** iki bağımsız işlem (ayrı süreç ya da iş
  parçacığı, ayrı bağlantı) aynı SHA-256'yı aynı anda `belge_al` ile
  verirse ikisi de "satır yok" görüp yazmaya kalkabilir. Veritabanı
  benzersizliği son savunmadır: ikinci yazımı `IntegrityError` ya da SQLite
  WAL anlık görüntü çakışması (`database is locked`; SQLite açık okuma
  işlemi olan bağlantıyı yazmaya yükseltirken beklemez) durdurur. `belge_al`
  bu iki hatayı yakalar, işlemi geri alır, kısa ve sınırlı bekler
  (`YENIDEN_DENEME_BEKLEMELERI`: 20 ms, 100 ms, 500 ms) ve DB adımını yeni
  işlemde en çok `BELGE_YAZMA_DENEMESI` (4) kez yeniden dener; yeni işlem
  commit edilmiş satırı görür ve normal duplicate sonucu döner. Global kilit
  yok, sonsuz retry yok; denemeler tükenirse `BelgeYazmaCakismasi`,
  çakışma olmayan veritabanı hatası olduğu gibi yükselir. Sonuç her zaman
  tek fiziksel dosya, tek `arsiv_dosyasi`, tek `belge`dir.
* `okuma_baslat(oturum, belge_id, arsiv_dizini)` — önce arşiv dosyasının
  var, sıradan dosya, beklenen boyutta ve beklenen SHA-256'da olduğu
  doğrulanır (DB satırına kör güvenilmez; eksikse `ArsivDosyasiEksik`,
  bozuksa `ArsivButunlukHatasi`, okuma açılmaz); sonra belge içinde bir
  sonraki sürüm numarasıyla `basladi` durumunda satır. Aynı belge birden çok
  kez okunabilir; sürüm numarası sistem türetir.
* `okuma_tamamla(oturum, okuma_id, icerik)` — yalnız `basladi` okuma; içerik
  JSON nesnesi (anahtar → değer) olmalı, JSON'a çevrilebilmeli (`NaN` /
  sonsuz, `Decimal`, `bytes` reddedilir), UTF-8 kanonik JSON metni 4 MiB'ı
  (`AZAMI_OKUMA_ICERIGI_BOYUTU`) aşmamalı. Tamamlanan okuma değiştirilmez:
  ikinci çağrı `OkumaDurumuGecersiz`, içerik güncelleyen işlev yok; yeni
  okuma gerekiyorsa yeni sürüm açılır. Okuma yaşam döngüsü yalnız iki teknik
  durumdur (`basladi`, `tamamlandi`); TASLAK / BEKLIYOR / paket / kullanıcı
  kararı buraya girmez. İçerik domain bağımsızdır: çekirdek hesap numarası,
  tarih, tutar gibi alanları bilmez. `okuma_icerigi` JSON'u çözüp döndürür.
* `kaynak_olustur(oturum, okuma_id, konum=None)` — yalnız `tamamlandi`
  okumadan üretilir (karar 2026-09-19): kaynak "bu veri hangi okumanın
  neresinden geldi?" sorusunun cevabıdır, içeriği henüz oluşmamış `basladi`
  okuma kararlı kaynak olamaz; `basladi` okuma için `OkumaDurumuGecersiz`,
  konumsuz kaynak da aynı kurala tabidir. Bu servis invariantıdır;
  veritabanında tetikleyici yoktur. `belge_id` okumadan
  alınır, çağıran veremez (servis düzeyinde uyuşmazlık imkânsız; ham SQL'de
  bileşik dış anahtar reddeder). Konum isteğe bağlı, küçük, genel bir JSON
  nesnesidir (sayfa, satır, hücre, görsel bölge gibi yalnız yer bilgisi;
  banka ekstresi satırı gibi özel alan yoktur), 4 KiB
  (`AZAMI_KAYNAK_KONUMU_BOYUTU`) ile sınırlıdır ve belge içeriğinin ikinci
  kopyası değildir. Kaynak satırı değişmez provenance verisidir: güncelleyen
  işlev yoktur, yanlışsa yeni kaynak üretilir. `kaynak_zinciri` kaynaktan
  okumaya, belgeye ve arşiv dosyasına deterministik geri gider. Kaynak bu
  aşamada nesneye ya da kayda bağlanmaz; aday nesne (4.5) ve kesin kayıt
  (4.7) yapıları ileride bu kararlı kimliğe referans verir.
* `arsivi_uzlastir(oturum, arsiv_dizini)` — dosya/DB bütünlük kontrol yüzeyi.
  Her `arsiv_dosyasi` satırı için fiziksel dosya boyut ve özetle doğrulanır;
  arşiv dizini taranır. Rapor altı durumu ayırt eder: **temiz** (satır var,
  dosya doğru), **eksik** (satır var, dosya yok), **bozuk** (satır var,
  hedefte yanlış boyut / özet ya da sıradan dosya değil), **sahipsiz**
  (içerik adresli dosya var, satır yok), **yarım** (`gecici/` altında kalmış
  artık), **tanınmayan** (arşiv düzenine uymayan başka dosya). Yalnız tespit
  eder ve raporlar; silmez, onarmaz. Sahipsiz dosya özellikle silinmez:
  DB hatası sonrası yeniden deneme ya da eşzamanlı işlem olabilir.

**Dosya/DB atomik olmama politikası ve sahipsiz dosya.** Fiziksel dosya önce
güvenli biçimde arşive girer, DB kaydı sonra açılır. DB adımı düşerse
kesinlikle DB'de dosyasız belge kaydı kalmaz; arşivde sahipsiz dosya
kalabilir. Bu yarım belge kaydı değil, dosya/DB atomik olmamasının doğal
sonucudur ve uzlaştırılabilir: aynı dosya yeniden geldiğinde arşiv mevcut
hedefi özetle doğrulayıp kullanır (ikinci fiziksel kopya yok) ve belge kaydı
tamamlanır.

**Hata modeli.** Dosya katmanı `arsiv.ArsivHatasi` altında:
`GelenDosyaGecersiz` (yol kuralları, boş dosya), `DosyaOkunamadi`,
`DosyaCokBuyuk`, `ArsivYazilamadi`, `ArsivDosyasiEksik`,
`ArsivButunlukHatasi` (`DosyaTuruUyusmuyor` 2026-09-19 kararıyla kaldırıldı).
Servis katmanı `belge_islemleri.BelgeHatasi` altında: `BelgeBulunamadi`,
`OkumaBulunamadi`, `KaynakBulunamadi`, `OkumaDurumuGecersiz`,
`OkumaIcerigiGecersiz`, `KaynakKonumuGecersiz`, `BelgeYazmaCakismasi`. Ham
`OSError`, `IntegrityError`, `database is locked` ve SQLite hata metni
doğrulama ve eşzamanlılık yollarında sözleşme değildir. Mesajlarda belge
içeriği ve tam yerel yol yoktur.

**Teknik log ≠ iş denetim izi.** Bu aşamanın modülleri hiçbir şeyi günlüğe
yazmaz; belge baytları, okuma içeriği, kaynak konumu ve tam yerel dosya yolu
teknik loga hiçbir zaman yazılmaz. Teknik Plan madde 24'teki iş denetim izi
("belge alındı", "okuma tamamlandı" gibi olaylar) ayrı bir mekanizmadır ve
Aşama 4.6 kapsamındadır; burada erkenden kurulmadı.

**Testler** (`tests/test_arsiv.py`, `tests/test_belge_zinciri.py`;
`tests/test_gocler.py` göç `0006` için). Gelen dizini: geçerli dosya, boş
yol, göreli yol, `..`, dosya yok, dizin, gelen dizininin kendisi, dizin dışı,
ön ek benzerliği, simgesel bağlantıyla dışarı kaçış (Windows'ta yetki yoksa
atlanır), simgesel dizin bağlantısı / junction ile içeride görünürken
fiziksel dışarı çıkma, içeriyi gösteren bağlantı, gelen dizininin kendisinin
bağlantı olması, okunamayan dosya (enjeksiyon), test kökü dışındaki dosyaya
dokunulmaması, hata mesajının yol taşımaması. Arşiv: içerik adresli
uzantısız yol, boş dosya, 50 MiB sabiti, tam sınırda kabul / bir bayt fazlası
red (küçük sınırla ve gerçek 50 MiB ile), akış sırasında büyüyen dosya,
parçalı okuma ve özet, PDF / PNG / JPEG imza algılama ve `octet-stream`
fallback, imza / uzantı uyuşmazlığının red sebebi olmaması (MIME imzadan,
uzantı metadata), uzantı metadata kuralı, aynı PDF / PNG / JPEG baytları
doğru uzantı / yanlış uzantı / başka imzanın uzantısı / uzantısız / bilinmeyen
uzantı → tek fiziksel dosya ve tek MIME, geçici yazma hatası ve taşıma
hatasında artık kalmaması,
Windows tarzı taşıma reddi, bozuk mevcut hedef (aynı ve farklı boyut)
duplicate sayılmaz, sekiz iş parçacığı aynı içerik → tek geçerli dosya,
yol hesabı ve bütünlük doğrulama, tarama sınıflaması. Belge: ilk dosya yeni
belge, aynı SHA mevcut belge (ikinci satır / dosya yok, ilk metadata kalır),
farklı içerik farklı belge, tam yerel yol DB'de yok, benzersizlik ve kontrol
kısıtları ham SQL ile, dosyasız arşiv sonucuyla belge yazılmaz, aynı boyutta
bozuk dosyayla `belge_tanimla` `ArsivButunlukHatasi` verir ve hiçbir satır
oluşmaz (dış işlem kullanılabilir kalır), yalnız arşiv satırı varken belge
tamamlanır, servis hata atomikliği, aynı PDF baytları beş adla tek belge,
eşzamanlı aynı belge (iki iş parçacığı, ayrı bağlantı, bariyerle zorlanan
yarış) tek dosya / tek satır / tek belgeye uzlaşır ve biri yeni diğeri
mevcut belgedir, her denemede çakışma üretilince sınırlı denemeden sonra
`BelgeYazmaCakismasi` ve her deneme geri alınmış olur, çakışma olmayan DB
hatası yeniden denenmez. Okuma: başlatma,
çoklu sürüm, tamamlama ve kanonik JSON, tamamlananın değiştirilememesi, yeni
sürüm, geçersiz içerik (liste / metin / `NaN` / sonsuz / `Decimal` / `bytes` /
küme / karışık anahtar), aşırı içerik, arşiv eksik / bozukken başlamama,
yazma hatasında yarım satır kalmaması, kısıtlar ham SQL ile. Kaynak: zincir,
konumsuz kaynak, genel JSON konum, geçersiz / aşırı konum, başka belgeyle
kaynak yazılamaması (bileşik dış anahtar ham SQL ile), deterministik geri
gidiş, hata atomikliği, `basladi` okumadan kaynak (konumlu ve konumsuz)
reddedilir ve satır kalmaz, tamamlandıktan sonra aynı konumla üretilir, red
dış işlemi bozmaz. Dosya/DB hata senaryoları (sentetik enjeksiyon):
kaynak okunurken hata, geçici dosya yazılırken hata, atomik taşıma hatası
(DB'de hiçbir şey yok, artık yok); arşiv başarılı + DB hatası (dosya kalır,
belge kaydı yok, uzlaştırma sahipsiz sayar) ve aynı dosyanın yeniden
denenmesi (ikinci kopya yok, belge açılır); enjeksiyonsuz gerçek DB hatası
(açılamayan dosya); DB belge var + dosya silinmiş (uzlaştırma eksik, okuma
açık hata); DB belge var + dosya değiştirilmiş (uzlaştırma bozuk, okuma ve
yeniden geliş açık hata, sessiz onarım yok). Uzlaştırma altı durumu birlikte
ayırt eder ve hiçbir dosyayı silmez.

**Bilinçli kapsam dışı (Aşama 4.4'te yok):** aday nesne / kayıt, işlem paketi,
TASLAK ve BEKLIYOR durumları, kullanıcı onayı, şüphe, mükerrer nesne
protokolü, kesin kaydetme, geri alma, projection, kural motoru, finans tanım
paketi ve belge türleri, tutar / bakiye / mutabakat, kayıt-kaynak bağı, genel
işlem anahtarı sistemi, iş denetim izi, MCP belge araçları (`belge_al` aracı
Aşama 4.11), GUI; okuma için "vazgeçildi" / "iptal" / "hata" gibi ek durum
(yaşam döngüsü yalnız `basladi → tamamlandi`; yarım kalmış `basladi` okuma
bu aşamada veri bütünlüğü kusuru değildir, gerekirse sonraki aşamalarda ele
alınır); tamamlanan okuma ve kaynak satırı için
veritabanı düzeyi değişmezlik (yalnız uygulama düzeyi; SQLite'ta
tetikleyicisiz ifade edilemez); sahipsiz / yarım / bozuk dosyaların otomatik
temizliği ya da onarımı.

## İşlem paketi ve taslak

Aşama 4.5 (2026-09-19; Yeniden İnşa Teknik Planı madde 9, 11, 12, 13, 20, 23,
24 ve 30). **Yazmak ≠ kaydetmek.** Cowork'un (dış okuyucunun) belgeyi okuyup
sisteme bilgi yazması kesin kayıt değildir; bu bilgi bir **işlem paketi**
altında **taslak** (aday) olarak yaşar. Zincirin bu aşamada kurulan kısmı:

```
OKUMA / KAYNAK → İŞLEM PAKETİ → ADAY NESNE / ÖZELLİK / İLİŞKİ / KAYIT
```

Kesin kaydetme (paketi kesinleştirme, tamlık kapısı, atomik finalizasyon,
belgeyi kayıtlı duruma geçirme) Aşama 4.8'in işidir ve **henüz yoktur**:
4.5 sonunda hiçbir aday veri kesinleşmemiştir. Çekirdek burada da finansı
bilmez; testler nötr `ENVANTER` dünyasıyla (`DEPO`, `RAF`, `URUN`; kayıt
türleri `SAYIM`, `DENETIM`) çalışır, `finans/` boştur. Finans paketini silip
başka bir alan tanımı yüklemek `cekirdek/` kodunda değişiklik gerektirmez.

**Taslak ile kesin fiziksel olarak ayrıdır.** Aday veri kesin nesne
tablolarına (`nesne`, `nesne_ozelligi`, `nesne_iliskisi`) yazılmaz; "önce
`nesne` satırı oluştur, sonra taslak diye işaretle" yolu yoktur. Aday satırlar
kendi tablolarındadır; kesin sorgular (`nesneleri_listele`, `ozellikleri_oku`,
`iliskileri_listele`) taslak tabloları hiç görmez. Ayrım şemadan gelir,
`WHERE durum != 'taslak'` gibi unutulabilir bir sorgu filtresine dayanmaz.
Hiçbir taslak tablo kesin nesne tablolarına dış anahtar taşımaz ve tersi de
yoktur; kaynak kodunda `taslak_*` modülleri nesne tablolarını ve nesne
motorunu, `nesne_*` modülleri taslak modüllerini import etmez, taslak
servisleri ham SQL kullanmaz (`tests/test_mimari_sinir.py`, üçüncü denetim).
Taslak servisleri tanım sistemini yalnız okuma yüzeyi `tanim_sorgulari`
üzerinden kullanır; yazma modülü `tanim_islemleri` ekleme-yalnız kilit için
kesin nesne tablolarını import ettiğinden taslak onu import etmez.
Aday nesne `nesne.id` üretmez; aday kimliği kesin nesne kimliği değildir.
Aday nesne oluşturmak tanım sürümünü kilitlemez.

**Tablolar (`src/defteriki/cekirdek/taslak_tablolari.py`, göç `0007`).**
Bütün kısıtlar isimlidir; dış anahtarlar `ON DELETE RESTRICT`.

| Tablo | Ne tutar | Veritabanı düzeyinde korunan |
|---|---|---|
| `islem_paketi` | `okuma_id`, `durum`, `olusturma_zamani`, `durum_zamani` | `okuma_id → okuma` (paketin okuması var); `durum IN ('calisiyor', 'bekliyor', 'iptal')`; `(id, okuma_id)` benzersiz (aday tabloların provenance bileşik dış anahtar hedefi); okuma ve durum indeksleri. Ayrı `belge_id` yoktur: belge `okuma → belge` zincirinden bulunur |
| `aday_nesne` | `islem_paketi_id`, `okuma_id` (paketten kopya), `nesne_turu_id`, `tanim_surumu_id`, `kaynak_id` (isteğe bağlı), `olusturma_zamani` | `(islem_paketi_id, okuma_id) → islem_paketi (id, okuma_id)`; `(nesne_turu_id, tanim_surumu_id) → nesne_turu (id, tanim_surumu_id)` (4.3 kalıbı: tür gerçekten o sürümde); `(kaynak_id, okuma_id) → kaynak (id, okuma_id)`: başka okumanın kaynağı bağlanamaz (kaynak NULL ise denetim yok); `(id, paket)`, `(id, tür)`, `(id, paket, tür, sürüm)` benzersiz (alt tabloların hedefleri) |
| `aday_nesne_ozelligi` | `aday_nesne_id`, `nesne_turu_id`, `ozellik_tanimi_id`, `deger` (kanonik metin) | iki bileşik dış anahtar aynı `nesne_turu_id` üzerinden: `(aday_nesne_id, nesne_turu_id) → aday_nesne` ve `(ozellik_tanimi_id, nesne_turu_id) → ozellik_tanimi`; başka türün özelliği yazılamaz; `(aday_nesne_id, ozellik_tanimi_id)` benzersiz |
| `aday_nesne_iliskisi` | `islem_paketi_id`, `iliski_tanimi_id`, `tanim_surumu_id`, kaynak/hedef tür ve aday nesne kimlikleri | dörtlü bileşik dış anahtar `iliski_tanimi (id, sürüm, kaynak tür, hedef tür)`; iki dörtlü bileşik dış anahtar `aday_nesne (id, paket, tür, sürüm)` kaynak ve hedef için: iki aday **aynı pakette**, türleri tanımın kaynak / hedef türü, üçü aynı sürümde; `(iliski_tanimi_id, kaynak_aday_nesne_id, hedef_aday_nesne_id)` benzersiz |
| `aday_kayit` | `islem_paketi_id`, `okuma_id`, `kayit_turu_id`, `kaynak_id` (isteğe bağlı), `icerik` (JSON metni), `olusturma_zamani` | `(islem_paketi_id, okuma_id) → islem_paketi`; `kayit_turu_id → kayit_turu` (genel tanım; finansal tür yok); `(kaynak_id, okuma_id) → kaynak (id, okuma_id)`; `json_valid(icerik) AND json_type(icerik) = 'object'`; `(id, islem_paketi_id)` benzersiz |
| `aday_kayit_nesne` | `islem_paketi_id`, `aday_kayit_id`, `aday_nesne_id` | `(aday_kayit_id, islem_paketi_id) → aday_kayit` ve `(aday_nesne_id, islem_paketi_id) → aday_nesne`: iki taraf aynı pakette; `(aday_kayit_id, aday_nesne_id)` benzersiz; rol sütunu yok |

Tanım ve nesne tablolarına dokunulmaz; `kaynak` yalnız `(id, okuma_id)`
benzersiz indeksini alır. Aday özellik ve aday ilişki bu aşamada ayrı kaynak
taşımaz; provenance nesne / kayıt düzeyinde ve en azından paket (okuma)
düzeyindedir.

**İşlem paketi.** `paket_olustur(oturum, okuma_id)` yalnız `tamamlandi`
okumadan paket açar (`basladi` okuma `OkumaDurumuGecersiz`, olmayan okuma
`OkumaBulunamadi`); yeni paket `calisiyor` doğar. Aynı okumadan birden çok
paket açılabilir. Normal çekirdek servisidir: açık `Session` alır, kendi
işlemini açmaz (4.4'teki `belge_al` istisnası burada yoktur).

**Yaşam döngüsü (`PaketDurumu`).**

```
calisiyor → bekliyor → calisiyor      paketi_beklet / paketi_devam_et
calisiyor → iptal,  bekliyor → iptal  paketi_iptal_et (terminal)
```

* `calisiyor`: taslak yazılır / değiştirilir.
* `bekliyor`: paket korunur; sorgulanır, içeriği okunur, devam ettirilir ya da
  iptal edilir, ama aday veri değiştirilmez. Aşama 4.6'nın kullanıcı karar
  mekanizması paketi bu duruma alacaktır; 4.5'te karar talebi yoktur.
* `iptal`: terminaldir; sorgulanır ve okunur, değiştirilemez, devam
  ettirilemez. **İptal fiziksel silme değildir:** hiçbir aday nesne / özellik
  / ilişki / kayıt / bağ, kaynak, okuma, belge ya da arşiv dosyası silinmez;
  paket ve taslak içeriği sorgulanabilir kalır. İptal edilen paket kesin
  dünyayı zaten hiç değiştirmediği için başka geri alma gerekmez. Aşama 4.6'dan
  beri `paketi_iptal_et` aktör alır ve başka etkin paketle paylaşılmayan talepleri aynı
  işlemde terminal `gecersiz` duruma geçirir ("Karar kaynağı, iptal ve kanonik
  kimlik"); talep silinmez, karar yazılmaz.
* `kaydedildi` / `kesinleşti` / `tamamlandi` gibi kesin kayıt durumu yoktur
  (4.8).

Yeniden devam edildiğinde aynı paket aynı taslaklarla sürer; yeni paket
açılıp içerik kopyalanmaz. Paket durumu yazma yetkisini belirler: aday veriyi
değiştiren bütün servisler tek merkezi denetimden geçer (`_yazilabilir_paket`);
her servise ayrı durum mantığı yoktur. Durum geçişi koşullu güncellemedir
(`UPDATE … WHERE durum = eski`): aynı bağlantıda araya giren bir değişiklik
satır etkilemez ve `PaketDurumuGecersiz` verir.

**Eşzamanlı yazma sözleşmesi (2026-09-19 incelemesi).** Servisler önce
okur (SQLite WAL anlık görüntüsü), sonra yazar. İki bağımsız bağlantı aynı
satırı ya da aynı paketi aynı anda değiştirmeye kalkarsa SQLite tam olarak
birini yazdırır; diğeri yazma anında kilit / anlık görüntü çakışması alır
(`database is locked` / `busy`; `SQLITE_BUSY_SNAPSHOT` için busy handler
çağrılmaz) ya da yarışan ilk yazımda benzersizlik ihlali. Bu ham hatalar
servis sözleşmesi değildir: her yazma tek sınırdan geçer (`_yazma_siniri`,
SAVEPOINT + dar eşleme) ve yalnız şunlar çevrilir:

| Veritabanı hatası | Servis sonucu |
|---|---|
| `OperationalError`, metinde `locked` ya da `busy` (kilit / anlık görüntü çakışması) | `TaslakYazmaCakismasi` |
| `IntegrityError`, `UNIQUE constraint failed: aday_nesne_iliskisi.…` (aday ilişki eklerken) | `MukerrerAday` |
| `IntegrityError`, `UNIQUE constraint failed: aday_kayit_nesne.…` (bağ eklerken) | `MukerrerAday` |
| `IntegrityError`, `UNIQUE constraint failed: aday_nesne_ozelligi.…` (aday özelliğin ilk yazımında) | `TaslakYazmaCakismasi` (iki ilk yazım yarıştı; "son yazan kazanır" icat edilmez) |
| başka her veritabanı hatası (dış anahtar, kontrol kısıtı, başka tablonun benzersizliği, disk / dosya) | olduğu gibi yükselir |

`TaslakYazmaCakismasi` alan çağıranın işlemi artık yazamaz (anlık görüntü
eskidir): işlemi geri alır ve yeni işlemde yeniden dener; yeniden denemede ön
denetim güncel veriyi görür ve olağan sonucu verir (mükerrerse
`MukerrerAday`, paket artık `calisiyor` değilse `PaketDurumuGecersiz`, değilse
yazma başarılı). Yeniden deneme çağıranındır; serviste retry döngüsü, sonsuz
deneme ya da iyimser kilit çerçevesi yoktur. Kanıt yalnız aşağıdaki iki
bağlantılı testlerin kapsadığı senaryolardır: aynı aday ilişki, aynı
kayıt-nesne bağı, aynı yeni aday özellik, aynı paketin durum geçişi, taslak
yazımı ile durum geçişi. Daha genel bir "sistem eşzamanlılığı destekler"
iddiası yoktur.

**Aday nesne, özellik, ilişki.** `aday_nesne_ekle(oturum, paket_id,
nesne_turu_id, ozellikler=None, kaynak_id=None)`; `aday_ozellik_yaz`
(var olan değeri günceller, aynı özellik iki satır olmaz), `aday_ozellik_sil`
(zorunlu olsa da silinebilir), `aday_ozellikleri_oku`; `aday_iliski_ekle(oturum,
iliski_tanimi_id, kaynak_aday_nesne_id, hedef_aday_nesne_id)`,
`aday_iliski_kaldir`; `aday_nesne_sil`. Özellik değeri kesin özellikle aynı
kuralla doğrulanır ve aynı kanonik metne kodlanır (`deger_kodlama`: metin,
tam sayı — `bool` reddedilir, mantıksal `"1"`/`"0"`, sonlu `Decimal` — `float`
reddedilir, sayısal kanonik biçim `125e-1`; "Nesne motoru" bölümündeki
"Ondalık kanonik biçim"); aynı değer iki tabloda aynı metindir. Aday ilişkide kaynak /
hedef türü ve sürüm tanıma uymalıdır; hiyerarşi sayımı ve çevrim aranmaz.

**Taslak eksik olabilir, yapısal olarak anlamsız olamaz.** Çalışma alanında
geçici olarak mümkün olanlar: zorunlu özelliği eksik aday nesne (Cowork önce
nesneyi fark edip aday açar, özelliği sonra ekler), zorunlu üst bağlantısı
henüz kurulmamış aday nesne (`RAFTA` en az bir üst istese de aday ürün üstsüz
durur), içeriği tamamlanmamış (`{}` dahil) aday kayıt, henüz bağlanmamış
kayıt-nesne bağı. Buna karşılık yine reddedilenler: olmayan tanıma referans
(`TanimBulunamadi`), başka türün özelliği ya da yanlış veri tipi
(`GecersizAdayOzellik`), ilişki tanımına uymayan kaynak / hedef türü ya da
sürüm (`GecersizAdayIliski`), başka paketin adayını bağlamak ve başka
okumanın kaynağını bağlamak (`PaketUyusmazligi`), mükerrer aday ilişki ya da
bağ (`MukerrerAday`); aynı ihlaller ham SQL'e karşı bileşik dış anahtar ve
benzersizlik kısıtlarıyla da reddedilir. Bütün zorunlu özellikler tamam mı,
hiyerarşi tamam mı, mükerrer var mı, kesin kayda dönüşebilir mi gibi nihai
kapı 4.8'in işidir; `paket_kaydedilebilir_mi` benzeri yarım bir motor yoktur.

**Aday kayıt ve aday kayıt ↔ aday nesne.** Kesin `kayit` tablosu, kayıt alanı
motoru ve kayıt durumu Aşama 4.7'dedir ve yoktur (testle doğrulanır).
`aday_kayit_ekle(oturum, paket_id, kayit_turu_id, icerik, kaynak_id=None)`
genel `kayit_turu` tanımına bağlı aday kayıt açar; içerik domain bağımsız
JSON **nesnesidir** (`{}` dahil), 4.4 kuralıyla kodlanır (yalnız nesne, `NaN` /
sonsuz / `Decimal` / `bytes` reddedilir, kanonik metin, 64 KiB
`AZAMI_ADAY_KAYIT_ICERIGI_BOYUTU`), loga ve hata mesajına yazılmaz.
`aday_kayit_icerigini_degistir`, `aday_kayit_icerigi`, `aday_kayit_sil`.
Aday kayıt bir ya da daha fazla aday nesneye bağlanır
(`aday_kayit_nesne_bagla`, `aday_kayit_nesne_coz`; çoktan çoğa, rolsüz —
asıl / borç / ödeme gibi rol semantiği icat edilmez); iki taraf aynı pakette
olmalıdır.

**Kaynak / provenance.** Paket düzeyinde `okuma_id` zorunludur; belge
`paket_belgesi` ile `okuma → belge` zincirinden deterministik bulunur. Aday
nesne ve aday kayıt isteğe bağlı bir `kaynak` satırına gerçek dış anahtarla
bağlanır (kaynak kimliği JSON içinde saklanmaz); kaynak paketin okumasına ait
olmak zorundadır, servis `PaketUyusmazligi` verir ve veritabanı `(kaynak_id,
okuma_id)` bileşik dış anahtarıyla başka okumanın kaynağını reddeder.
Kaynaksız aday öğe geçerlidir; en azından okuma düzeyinde provenance vardır.
Çok-kaynak altyapısı kurulmadı (gereksinim yok).

**Taslak silme.** Çalışan pakette aday nesne, ilişki, kayıt ve bağ
kaldırılabilir. Aday nesnenin kendi özellikleri onun parçasıdır, nesneyle
birlikte silinir; aday nesne bir aday ilişkide ya da kayıt-nesne bağında
kullanılıyorsa silme açıkça reddedilir (`AdayKullanimda`), sessiz cascade
yoktur ve ham `DELETE` de dış anahtarla düşer. Aday kaydın kendi kayıt-nesne
bağları kaydın ekidir, kayıtla birlikte silinir, bağlı aday nesneler kalır.

**Sorgulama.** `paket_getir`, `paketleri_listele(oturum, durum=None)`,
`paket_belgesi`, `paket_ayrinti` (bütün çalışma alanı tek `PaketAyrintisi`
içinde: paket, aday nesneler, özellikler, ilişkiler, kayıtlar, bağlar; her
liste kimlik sırasıyla, deterministik; `durum`, `aday_nesne_sayisi`,
`aday_kayit_sayisi` mekanik bilgiler), `aday_nesne_getir`, `aday_kayit_getir`,
`aday_ozellikleri_oku`, `aday_kayit_icerigi`. Sorgular durumdan bağımsızdır
(bekleyen ve iptal paket dahil). Listeler veritabanının tesadüfi satır
sırasına bırakılmaz; ileride Cowork'un "pakette şu anda ne var?" sorusuna
kararlı yanıt bunun içindir. MCP aracı ve GUI bu aşamada yoktur.

**Servis hata atomikliği ve işlem sınırı.** 4.1 / 4.3 kuralı sürer: her
servis açık `Session` alır, çağıran `Veritabani.islem()` sahibidir, `commit`
/ dış `rollback` yoktur; doğrulama yazmadan önce, yazma kendi SAVEPOINT'inde
(`begin_nested`). Başarısız çağrı aynı dış işlemde yakalansa bile kısmi satır
bırakmaz (aday nesne yazıldıktan sonra özellik yazımında hata → ikisi de
yok), dış işlem kullanılabilir kalır ve sonraki geçerli iş commit edilir.

**Hata modeli (`IslemPaketiHatasi` altında):** `PaketBulunamadi`,
`AdayBulunamadi` (`LookupError`); `PaketDurumuGecersiz`; `PaketUyusmazligi`;
`GecersizAdayOzellik`, `GecersizAdayIliski`, `GecersizTaslakIcerik`
(`ValueError`); `MukerrerAday`; `AdayKullanimda`; `TaslakYazmaCakismasi`
(eşzamanlı yazma çatışması; yeni işlemde yeniden denenir). `TanimBulunamadi`,
`OkumaBulunamadi`, `OkumaDurumuGecersiz`, `KaynakBulunamadi` kendi
modüllerinden olduğu gibi gelir. Ham `IntegrityError` / `OperationalError`
yalnız yukarıdaki tablodaki dar eşlemeyle çevrilir, kalanı olduğu gibi
yükselir. Genel
`islem_anahtari` (idempotency) sistemi ve denetim olay sistemi bu aşamada
kurulmadı (4.11 ve 4.6); satırlar yalnız mekanik zaman damgası taşır.

**Testler** (`tests/test_islem_paketi.py`; `tests/test_gocler.py` göç `0007`
için; `tests/test_mimari_sinir.py` taslak / kesin ayrımı için). Paket:
tamamlanmış okumadan oluşturma, `basladi` ve olmayan okumadan red (ham SQL
ile de), aynı okumadan çoklu paket, bütün izinli ve izinsiz geçişler,
`iptal` terminal, durum değeri kontrol kısıtı, aynı bağlantıda araya giren
durum değişikliğinde koşullu güncelleme reddi. Yazma yetkisi: on bir yazma
servisi bekleyen ve
iptal pakette reddedilir, içerik sorgulanabilir kalır; devam edilen pakette
aynı taslaklarla hepsi çalışır, yeni paket açılmaz. Aday nesne: kesin `nesne`
satırı oluşmaz, `nesneleri_listele` boş, aday kimliği nesne kimliği değil,
sürüm kilitlenmez; zorunlu özellik eksikken oluşur ve sonradan tamamlanır
(kesin nesne aynı eksikliği reddeder); olmayan tür, tanımsız özellik, tür /
sürüm uyuşmazlığı (ham SQL), yanlış veri tipi (dört tür; `bool` / `int`,
`float`, `NaN`, sonsuz), başka türün özelliği (servis ve iki bileşik dış
anahtar), güncelleme çift satır üretmez (benzersizlik ham SQL ile), zorunlu
özellik taslakta silinebilir, aday ile kesin özellik aynı kanonik metni verir,
silme kuralları (`AdayKullanimda`, ham `DELETE` dış anahtarla düşer,
özellikler nesneyle gider). Aday ilişki: doğru türler ve kendine dönen
genel ilişki, yanlış kaynak / hedef türü (servis ve dış anahtar), farklı
paketin adayı (servis ve dış anahtar, iki paket kimliğiyle de), mükerrer
(servis ve benzersizlik), zorunlu hiyerarşi eksikken taslak var olur ve
bağlantı kaldırılabilir. Aday kayıt: genel kayıt türü, kanonik JSON, `{}`,
kesin `kayit` tablosunun yokluğu, bozuk / desteklenmeyen içerik (dokuz
biçim), aşırı içerik ve sınırın hemen altı, içerik kısıtları ham SQL ile
(`json_type = 'object'`), içerik değiştirme ve silme (bağlar gider, nesne
kalır). Bağ: çoklu nesneye bağ, çözme, başka paketin adayı (servis ve dış
anahtar), mükerrer bağ. Kaynak: paketin okumasındaki kaynağa bağlanma,
kaynaksız aday, başka okumanın kaynağı (servis ve bileşik dış anahtar, iki
okuma kimliğiyle de). **Ana kabul testi** `test_yazmak_kaydetmek_degildir`:
önceden var olan kesin nesne yanında paket açılır; iki aday nesne, dört
özellik, bir aday ilişki, bir aday kayıt ve iki bağ yazılır; `nesne`,
`nesne_ozelligi`, `nesne_iliskisi` sayıları ve tablo listesi değişmez, kesin
sorgular adayları görmez, paket sorgusu bütün taslakları görür; `bekliyor`da
taslak korunur ve yazma durur; `calisiyor`a dönünce aynı taslaklardan devam
edilir; `iptal`de kesin dünya yine değişmemiştir, paket ve taslak içeriği
(satır sayıları dahil) sorgulanabilir, hiçbir yazma ve devam mümkün değildir,
`integrity_check` ve `foreign_key_check` temizdir. Şema ayrımı: hiçbir taslak
tablo kesin nesne tablolarına, hiçbir kesin tablo taslak tablolara dış
anahtar taşımaz. Atomiklik: aday nesne yazma ortasında sentetik hata, aday
özellik yazımında ham SQL ile çakıştırılmış kısıt hatası, aynı dış işlemde
yakalanan yedi farklı hata (tür, paket, JSON, `NaN`, bağ, tip, geçiş)
sonrası geçerli işlerin commit'i, durum değişimi ve paket oluşturma yazma
hatası. Mimari sınır: taslak modülleri kesin nesne modüllerine, kesin nesne
modülleri taslak modüllerine doğrudan / dolaylı ulaşmaz (denetleyicinin
kendisi sentetik ağaçta sınanır), taslak modülleri ham SQL kullanmaz;
finansal ad denetimi ve çekirdek → finans yasağı yeni modülleri ve `0007`yi
kapsar. **Gerçek eşzamanlılık (iki bağımsız `Veritabani`, ayrı bağlantı,
ayrı iş parçacığı, bariyerle zorlanan yarış; ikisi de kendi anlık
görüntüsüyle "satır yok / paket calisiyor" görüp yazmaya gider):** aynı aday
ilişki → tek satır, biri başarılı, diğeri `MukerrerAday` ya da
`TaslakYazmaCakismasi`, yeniden denemede `MukerrerAday`; aynı kayıt-nesne
bağı → aynı sözleşme; aynı yeni aday özelliğe iki farklı değer → tek satır,
değer kazananınki, kaybeden `TaslakYazmaCakismasi`, sessiz üzerine yazma yok;
aynı `calisiyor` paket aynı anda `bekliyor` ve `iptal`e → tam bir geçiş,
diğeri `TaslakYazmaCakismasi` / `PaketDurumuGecersiz`, son durum kazananınki,
kazanan `iptal` ise yeniden deneme `PaketDurumuGecersiz`; aday nesne yazımı
ile paket iptali (iki varyant) → gecikmesiz koşuda gözlenen sıra "geçiş
önce": yazım `TaslakYazmaCakismasi` alır, yeniden denemede
`PaketDurumuGecersiz`, satır yok; geçiş iş parçacığı bariyerden sonra 0,2 s
beklerse "taslak önce": yazım tamamlanır, geçişin anlık görüntüsü eskidiği
için geçiş `TaslakYazmaCakismasi` alır ve yeni işlemde tamamlanır; hiçbir
dalda yarım satır ya da iptal pakete yazılmış satır yok, `integrity_check` /
`foreign_key_check` temiz. Hiçbir senaryoda
ham `IntegrityError` / `OperationalError` dışarı çıkmaz. Hata eşlemesi dar:
yardımcı yüklemler (`kilit_cakismasi_mi`, `benzersizlik_ihlali_mi`) sentetik
hatalarla, yazma sınırı gerçek veritabanında (aynı tablonun benzersizliği
domain hatasına döner; başka tablonun benzersizliği, dış anahtar, kontrol
kısıtı ve tablo verilmeyen çağrı ham `IntegrityError` olarak yükselir, dış
işlem kullanılabilir kalır).

**Bilinçli kapsam dışı (Aşama 4.5'te yok):** kullanıcı karar talebi, onay
tablosu, seçim seçenekleri, mükerrerlik şartları / arama, nesne birleştirme,
ilişkileri taşıma, denetim izi (4.6); kesin kayıt tablosu, kayıt alanı
motoru, kesin kayıt ↔ nesne ve kayıt ↔ kaynak bağı (4.7); `kaydet`, paketi
kesinleştirme, tamlık kapısı, atomik finalizasyon, belgeyi kayıtlı duruma
geçirme (4.8); projection, kural motoru, finans tanım paketi, MCP işlem paketi
araçları, GUI, kesin kayıt geri alma (sonraki aşamalar); aday özellik ve aday
ilişki için ayrı kaynak bağı, çok-kaynak; hiyerarşi çevrimi ve sayım
denetiminin taslak dünyasında çalıştırılması; genel işlem anahtarı; iyimser
kilit çerçevesi ve serviste yeniden deneme (çatışmada yeniden deneme
çağıranındır); eşzamanlılık iddiası yalnız yukarıdaki beş yarış senaryosuyla
sınırlıdır.

## Onay ve mükerrerlik

Aşama 4.6 (2026-09-20; Yeniden İnşa Teknik Planı madde 31). Altı yeni tablo
(göç `0008`), iki yeni modül çifti: `mukerrerlik_tablolari` /
`mukerrerlik_islemleri` ve `denetim_tablolari` / `denetim_islemleri`.

**Mükerrerlik bir benzersizlik kısıtı değildir.** Eşleşme "bunlar kesinlikle
aynı nesnedir" demek değildir; yalnız kalıcı bir **şüphe** ve ona bağlı bir
**kullanıcı karar talebi** doğurur. Otomatik birleştirme yoktur, veritabanı
`UNIQUE` kısıtı mükerrerlik sistemi yerine kullanılmaz. Çekirdek şart olarak
seçilen özelliklerin anlamını bilmez: yalnız `ozellik_tanimi` kimliklerini ve
`deger_kodlama` ile üretilmiş kanonik metinleri **birebir** karşılaştırır.
Küçük harfe indirme, boşluk kırpma, yaklaşık eşleşme, regex, güven puanı, LLM
değeri ya da ad tahmini yoktur.

**Şartlar kullanıcı tarafından seçilir.** `nesne_sarti_ekle` ve
`aday_sarti_ekle` bir kesin nesne ya da aday nesne için sıfır, bir veya birden
fazla özelliği mükerrerlik şartı yapar; seçim eklenir, kaldırma işlevi yoktur
(koruma zayıflatılamaz). Birden fazla şart **VEYA** mantığındadır: herhangi
biri eşleşirse şüphe doğar, hepsinin eşleşmesi gerekmez. Seçilmemiş bir
özelliğin eşitliği şüphe üretmez. Başka türün özelliği şart seçilemez (servis
`GecersizSart`, veritabanında iki bileşik dış anahtar).

**Tarama iki yönlüdür.** Taranan ucun kendi şartları karşı ucun aynı
özelliğindeki değerle, karşı ucun şartları da taranan ucun değeriyle
karşılaştırılır. Böylece şart seçmemiş yeni bir nesne, şart seçmiş mevcut bir
nesnenin korumasından kaçamaz. Hiçbir uçta şart yoksa karşılaştırma yapılmaz.
Karşılaştırma aynı nesne türü içindedir (özellik tanımı bir türe aittir).
Birleştirilmiş nesneler taramaya girmez.

**Şüphe → talep → `BEKLIYOR`.** Şüphe `karar_talebi` satırı olarak kalıcı
yazılır; satırın kimliği Aşama 3.4'te gerçek Cowork ile doğrulanan
`BEKLIYOR + talep kimliği` protokolündeki kalıcı kimliktir. Paket durumu artık
**açık talep sayısından türer**: açık talep varken `BEKLIYOR`, hiç kalmayınca
`CALISIYOR`. İlk kararın tek başına paketi canlandırmaması bu kuraldan gelir;
`taslak_islemleri.paketi_devam_et` de açık talep varken reddeder. `IPTAL`
terminaldir: paket diriltilmez. Başka etkin paketle paylaşılan sorular açık
kalır ve kalan paket adına cevaplanabilir; paylaşılmayan paket kaynaklı
talepler terminal `gecersiz` olur ("Aday kararları ve ortak paket beklemesi").
Bekleyen karar yalnız ilgili paketi ve şüpheli ucu durdurur; mevcut kesin
nesneler sistem genelinde kilitlenmez.

**Karar kalıcıdır.** `AYRI` şüpheyi kapatır ve aynı çift aynı kanıtla yeniden
durdurulmaz; kimlikler sonraki birleşmelerle değişse de bu karar korunur
("AYRI geçmişi ve karar atomikliği"). `AYNI` çözümlemeyi ya da birleştirmeyi
tek transaction içinde uygular. `KARARSIZ` şüpheyi çözmez: talep açık kalır, paket `BEKLIYOR` kalır,
karar yalnız denetim izine yazılır (bu yüzden `karar` sütununa `kararsiz`
yazılmaz). Aynı talebe ikinci kez karar uygulanmaz: kapatma koşullu
güncellemedir (`UPDATE ... WHERE durum = 'acik'`), iki bağlantı aynı anda
cevaplarsa yalnız biri kazanır, diğeri `KararTalebiKapali` alır.

**Aday → mevcut nesne çözümlemesi.** `AYNI` kararında aday nesne kesin tabloya
taşınmaz; `aday_nesne_cozumlemesi` satırı "bu aday şu kesin nesne olarak
çözüldü" bilgisini ilişkisel ve kalıcı tutar. Aşama 4.8 paketi kesinleştirirken
bunu tahmin etmez, buradan okur. Adayın özellikleri, aday ilişkileri ve aday
kayıt bağları olduğu gibi korunur (provenance bozulmaz). `AYRI` kararında aday
aday kalır ve 4.8'de yeni kesin nesneye dönüşebilir. Çözümlenmiş ya da bir
karar talebine konu olmuş aday silinemez (`AdayKullanimda`).

**İki kesin nesnenin birleştirilmesi.** Çift her zaman `kaynak > hedef`
sırasına normalleştirilir: önce oluşturulan korunur (kontrol kısıtı). İlişkiler
`nesne_islemleri.iliskileri_devret` ile taşınır; ikinci bir ilişki motoru
yoktur, bütün 4.3 doğrulamaları (tür, sürüm, mükerrer ilişki, üst yaşam
durumu, en çok / en az üst, çevrim) çalışır. Fark yalnız adım adım değil **son
durum** doğrulanmasıdır: bütün satırlar kaldırılır, hedef üzerinden yeniden
kurulur, sonra hedefin ve üstü değişen çocukların kuralları denetlenir. Hedefte
zaten olan ilişki ikinci kez yazılmaz; kaynak ile hedef arasındaki bağlantı
kendine döneceği için yazılmaz. Herhangi bir ihlalde **her şey** geri alınır:
yarım ilişki taşınmaz, kaynak yarım kapanmaz, karar yarım uygulanmaz, denetim
izi yarım kalmaz. Kaynağın şartları hedefe **kopyalanır** (kaynaktan
silinmez); kaynak silinmez, yaşam durumu `kapali` olur ve `nesne_birlesimi`
satırı onu kalıcı olarak hedefe bağlar. Kaynağın özellik değerleri kaynakta
kalır: hangi değerin doğru güncel değer olduğu bir domain yorumudur, çekirdek
karar vermez — ama o değerler mükerrerlik açısından korumadan düşmez ("Karar
kaynağı, iptal ve kanonik kimlik"). Birleşim zinciri kurulmaz. Devir sonrası
kaynağın kendi
"en az üst" kuralı aranmaz; birleşim kaydı onu artık bağımsız nesne olmaktan
çıkarır.

**Zincirleme mükerrerlik.** Birleşimden sonra hedefin kendisi (kaynağın
şartlarını ve kimlik değerlerini devraldı) ve hedefin hiyerarşik çocukları
yeniden denetlenir; yeni
eşleşme yeni talep açar ve paket bütün talepler çözülene kadar `BEKLIYOR`
kalır. Döngü olamaz: aynı çift için ikinci talep açılmaz (açık talep kısmi
benzersiz indeksle veritabanı düzeyinde, çözülmüş talep servis denetimiyle) ve
bu adım birleştirme yapmaz.

**Aktörlü iş denetim izi.** `denetim_izi` tablosu teknik hata günlüğünden
(`defteriki.gunluk`) ayrıdır; ikisi birleştirilmez. Her satır olay türü, olay
zamanı, `aktor_turu` (`kullanici` / `ajan` / `sistem`), `aktor_kimligi` ve
olayı anlamaya yetecek kimlik referansları taşır. 4.6'nın durum değiştiren
bütün servisleri aktörü açıkça alır. Ayırt edilen olaylar: mükerrerlik şartı
belirlendi, mükerrerlik şüphesi açıldı, karar talebi açıldı, kullanıcı kararı
verildi, nesne ayrı kabul edildi, nesne birleştirildi, aday nesneye
çözümlendi, paket beklemeye geçti, paket yeniden çalışıyor, karar talebi
geçersiz kaldı, birleşim yeniden bağlandı. **Gizlilik:** ize
belge ham içeriği, özelliklerin ham değerleri, sır ya da dosya içeriği
yazılmaz; kimlik / referans saklamak yeterliyse değer tekrar kopyalanmaz.
`gerekce` yalnız kullanıcının kısa açıklamasıdır ve
`AZAMI_GEREKCE_UZUNLUGU` (500 karakter) ile sınırlıdır; sınır kararın en
başında denetlenir. Denetim satırı işin kendisiyle aynı transaction içinde
yazılır: iş geri alınırsa izi de geri alınır.

**Tablolar (göç `0008`, `0009` ve `0010` ile genişledi).**

`0010` ile eklenen `karar_talebi_paketi`, `(karar_talebi_id, islem_paketi_id)`
bileşik anahtarı ve iki `RESTRICT` dış anahtarıyla tek talebin paketlerini tutar.

| Tablo | Ne tutar | Kısıtlar |
|---|---|---|
| `nesne_mukerrerlik_sarti` | kesin nesnenin şart özellikleri | iki bileşik dış anahtar aynı `nesne_turu_id` üzerinden (`nesne` ve `ozellik_tanimi`): başka türün özelliği veritabanında da şart olamaz; `(nesne_id, ozellik_tanimi_id)` benzersiz |
| `aday_nesne_mukerrerlik_sarti` | aday nesnenin şart özellikleri | aynı kalıp, `aday_nesne` üzerinden |
| `karar_talebi` | şüphe **ve** kalıcı karar talebi (tek satır) | uçlardan tam biri aday / kesin (`(aday_nesne_id IS NULL) <> (kaynak_nesne_id IS NULL)`); kesin çiftte `kaynak > hedef`; durum (`acik` / `cozuldu` / `gecersiz`) ile karar ve `gecersizlik_zamani` alanları tutarlı; `karar_aktor_turu` yalnız `kullanici`; dört bileşik dış anahtar `nesne_turu_id` üzerinden; iki **kısmi benzersiz indeks** açık talepler için |
| `aday_nesne_cozumlemesi` | aday → kesin nesne köprüsü | `aday_nesne_id` ve `karar_talebi_id` benzersiz; iki bileşik dış anahtar aynı tür üzerinden |
| `nesne_birlesimi` | birleşen → karar hedefi (`hedef_nesne_id`, değişmez) ve bugünkü kanonik nesne (`kanonik_nesne_id`) | `kaynak_nesne_id` ve `karar_talebi_id` benzersiz; `kaynak <> hedef`; `kaynak <> kanonik`; `aktor_turu` yalnız `kullanici` |
| `denetim_izi` | aktörlü iş olayı | olay ve aktör türü kontrol kısıtı, boş olmayan aktör kimliği; `aday_nesne_id` bilerek dış anahtar **değil** (aday silinebilir, iz yaşamalı; kimlik `AUTOINCREMENT` sayesinde yeniden dağıtılmaz) |

Şüphe ile talep bilerek ayrı tablolara bölünmedi: şüphenin açık olup olmaması
ile talebin açık olup olmaması tek gerçektir ve "aynı çift için ikinci açık
şüphe" kısıtı ancak tek satırda kısmi benzersiz indeksle ifade edilebilir; iki
tablo iki doğruluk kaynağı ve eşzamanlılık boşluğu üretirdi.

### Karar kaynağı, iptal ve kanonik kimlik

2026-09-20 bağımsız incelemesinin kapattığı altı bulgu. Hepsi gerçek kodla
yeniden üretildi, düzeltme göç `0009`u gerektirdi.

**Kararı yalnız kullanıcı verir, artık kodda da.** `karar_ver` aktörü
`KULLANICI` olmayan çağrıyı `KararKaynagiGecersiz` ile en başta reddeder:
talep değişmez, denetim izine yazılmaz, paket durumu değişmez. Veritabanı da
aynı şeyi söyler: `karar_talebi.karar_aktor_turu`, `aday_nesne_cozumlemesi` ve
`nesne_birlesimi` üzerindeki `aktor_turu` kontrol kısıtları yalnız `kullanici`
kabul eder, ham SQL de ajan kararı yazamaz. Ajan ve sistem tarama yapar, şüphe
açar, denetim olayı üretir. Daha önce README bunu söylüyor ama hiçbir şey
zorlamıyordu.

**İptal edilen paketin talebi çifti kilitlemez.** `paketi_iptal_et` aktör alır
ve başka etkin paketle paylaşılmayan talepleri aynı işlemde `gecersiz` yapar
(`gecersizlik_zamani` dolar, denetim izine `karar_talebi_gecersiz_kaldi`
yazılır). `gecersiz` bir `AYRI` kararı **değildir**: `karar` boş kalır, satır
geçmişte durur, kullanıcı kararı verilemez. Ama artık açık talep sayılmaz;
kısmi benzersiz indeksten ve "bu çift zaten değerlendirildi" denetiminden
çıkar, böylece aynı çift başka bir pakette yeniden değerlendirilebilir. Eskiden
iptal edilen paketin talebi hem cevaplanamıyor hem de o çifti kalıcı olarak
susturuyordu.

**Kanonik kesin nesne tek sıçramada bulunur.** Bir gerçek nesnenin sistemdeki
karşılığı tek bir kanonik kesin nesnedir. `nesne_birlesimi.hedef_nesne_id`
kullanıcının o günkü kararıdır ve değişmez; `kanonik_nesne_id` bugünkü kanonik
nesnedir ve hiçbir zaman kendisi birleşmiş bir nesneyi göstermez. `3 → 2`
varken `2 → 1` birleşirse eski satır `1`e yeniden bağlanır (zincir düzleşir,
denetim izine `birlesim_yeniden_baglandi` yazılır, `karar_talebi_id` bağları
korunur). `kanonik_nesneyi_bul` ve `adayin_kesin_nesnesi` tek adımda çalışır;
Aşama 4.8 kanonik hedefi tahmin etmek zorunda kalmaz.

**Aynı aday birden fazla kesin nesneyle eşleşebilir.** Kullanıcı ikisine de
`AYNI` derse aday için ikinci çözümleme satırı yazılmaz (eskiden ham
`UNIQUE` hatası sızıyordu); mantıksal sonuç — `Z = X` ve `Z = Y` ise `X = Y` —
iki kesin nesnenin birleştirilmesi olarak uygulanır ve birleşim bu karara
bağlanır, yani hangi kararın hangi birleşime yol açtığı denetimden okunur.
İkisi zaten aynı kanonik nesneye çıkıyorsa yeni satır yazılmaz, karar yine ize
geçer. O çift için daha önce `AYRI` denmişse çelişki sessizce çözülmez:
`KararCelismesi` yükselir, işlem tamamen geri alınır, talep açık kalır.
Kullanıcının eski kararını ezmek de yeni kararını yok saymak da çekirdeğin işi
değildir.

**Birleşen nesnenin kimlik geçmişi korumadan düşmez.** Mükerrerlik taraması
kanonik nesnenin değerleri olarak ona birleşmiş kaynakların değerlerini de
sayar; karşı ucun şartı da kanonik nesne üzerinden aranır (şartlar birleşimde
kanonik nesnede toplanır). Birleşmiş nesne eşleşme sonucunda kendi başına
görünmez, kanonik nesnesine eşlenir ve karar talebi kanonik nesneyi gösterir.
Kaynağın değerleri hedefin özelliği **yapılmaz**: aynı özellikte iki farklı
değer varsa hangisinin doğru olduğu bir domain yorumudur, ikisi de kimlik
kanıtı olarak kalır. Nesnenin normal özellik okuması değişmez; geçmiş yalnız
mükerrerlik motorunda kullanılır.

**Denetim izindeki aday kimliği karışmaz.** `denetim_izi.aday_nesne_id` dış
anahtar değildir (aday silinebilir, iz yaşamalı), `aday_nesne.id` ise SQLite
`rowid` takma adıydı: en büyük kimlik silinince yeniden dağıtılıyor ve eski iz
yeni adayı gösteriyordu. `0009` ile `aday_nesne` birincil anahtarı
`AUTOINCREMENT` oldu; kimlik bir daha dağıtılmaz. Bedeli: SQLite
`AUTOINCREMENT`a yalnız sütun kısıtında izin verdiğinden bu tablonun birincil
anahtarı `pk_aday_nesne` adını taşıyamaz — projedeki tek ad istisnası.

**Modül sınırı.** `denetim_tablolari` artık `nesne_tablolari`yı ve
`mukerrerlik_tablolari`yı import etmez (iki tablo adı yerel sabit, doğruluğu
testle korunur); böylece `taslak_islemleri` iptal ederken denetim izine
yazabilir ve taslak → kesin nesne import zinciri kurulmaz. Aktör türü tek
yerde tanımlıdır ve `mukerrerlik_tablolari` onu denetim modülünden alır.

### AYRI geçmişi ve karar atomikliği

2026-09-20 ikinci inceleme turunun kapattığı iki bulgu. Şema değişmedi; göç
zincirinin başı `0009`da kaldı.

**Geçmiş `AYRI` kararı birleşmelerle aşılamaz.** Eskiden çelişki denetimi
yalnız doğrudan kimlik çiftine bakıyordu, kesin ↔ kesin birleştirme yolunda
ise hiç yoktu. Kimlikler birleşmelerle değiştiği için bu yetmiyordu: kullanıcı
`N1 ≠ N3` dedikten sonra `N3 → N2` olunca `N1 = N2` kararı eski kararı sessizce
aşıyordu. Artık birleşmeden **önce** iki kanonik kümenin bütün üyeleri
karşılaştırılır — kümeye önceki birleşmelerle katılanlar dahil, zincir kaç adım
derin olursa olsun, `AYRI` satırının yönü ne olursa olsun. Herhangi iki üye
arasında kullanıcının verdiği bir `AYRI` varsa birleşme `KararCelismesi` ile
reddedilir. Eski karar silinmez, değiştirilmez, bağlantısı koparılmaz;
reddedilen işlem hiçbir kalıcı değişiklik bırakmaz. Kullanıcının çıkış yolu
açıktır: bu talebe `AYRI` der ya da eski kararı kendisi ele alır. Çelişki
çekirdek tarafından çözülmez, çünkü hangi kararın geçerli olduğu bir kullanıcı
kararıdır.

**Birleşmeden sonra açık talepler kanonik uçlara uzlaştırılır.** `N1 ?= N3`
talebi `N3 → N2` olduktan sonra fiilen `N1 ?= N2`dir. Açık bırakılsaydı üç
sorun çıkardı: `AYNI` cevabı `BirlestirmeGecersiz` ile reddedilirdi (kalıcı
bekleme), zincirleme denetimin kanonik uçlarla açtığı talep aynı soruyu ikinci
kez sorardı (mükerrer karar) ve iki açık talep aynı kanonik çifte düşünce kısmi
benzersiz indeks ihlal edilebilirdi. Bu yüzden birleşen nesneyi gösteren açık
**kesin çift** talepleri terminal `gecersiz` duruma geçer ve soru, hâlâ
geçerliyse, aynı işlem içinde çalışan zincirleme denetimle kanonik uçlarla
yeniden açılır. İki ucu aynı kanonik nesneye düşen talep yeniden açılmaz:
soru kendiliğinden yanıtlanmıştır, kullanıcıdan ikinci bir karar beklenmez.
Hükümsüz kalan talebin bütün etkin paket bağları kanonik soruda korunur;
paketler cevap verilmeden serbest kalmaz. Aday zaten sorunun kanonik
hedefine çözümlenmişse aday talebi de hükümsüz kalır. `gecersiz`
"karar verilmeden hükümsüz kalan talep" demektir, hükümsüzlük nedeni
denetim izinin gerekçesinde yazar (`karar_talebi_gecersiz_kaldi`). Talep
geçmişi bozulmaz: satırın eski uçları ve açılış bilgisi yerinde kalır, `karar`
boş kalır.

**`karar_ver` ve `paketi_iptal_et` bütünüyle atomiktir.** Yardımcıların kendi
SAVEPOINT'leri yetmiyordu: talebi kapatan SAVEPOINT kendi başına tamamlandığı
için, sonraki adım düşer ve çağıran hatayı yakalayıp dış transaction'ı commit
ederse "talep `cozuldu/ayni` ama birleşim yok" ya da "paket `iptal` ama talebi
hâlâ açık" gibi yarım bir durum kalıcı olabiliyordu. İki servis de artık
bütün yazmalarını **tek bir dış SAVEPOINT** içinde yapar: talebin kapatılması,
denetim olayları, çözümleme, birleştirme, kanonik yeniden bağlama, açık talep
uzlaştırması ve paket durumu aynı atomiklik sınırındadır. Servis dış
transaction'a dokunmaz (ne commit ne rollback), dolayısıyla çağıranın bu
çağrıdan **önce** yaptığı bağımsız değişiklikler korunur. Gerçek veritabanıyla
hata enjeksiyonu testleri bunu kanıtlar: ilk değişiklikten sonraki ve sonraki
kritik adımlardaki hatalar çağıran tarafında yakalanır, dış transaction commit
edilir, kalıcı durum yeni bir oturumdan okunur.

### Aday kararları ve ortak paket beklemesi

Üçüncü inceleme düzeltmesi (göç `0010`): adayın kalıcı `AYRI` kararı,
adayın çözümlendiği kesin kimlikle birlikte birleşme kontrolüne katılır.
`Z = X`, `Z ≠ Y` sonrasında `X = Y` reddedilir. Önce `Z ≠ Y`, sonra
`Y → X` olmuşsa ilk `Z = X` çözümlemesi de reddedilir. Reddedilen karar
talebi açık kalır; karar geçmişi ve dış işlemin önceki yazmaları korunur.

`karar_talebi_paketi`, tek soruyu bekleyen bütün paketleri bağlar.
`karar_talebi.islem_paketi_id` açılış paketini tarihsel olarak saklar;
pakete göre listeleme ve devam/yazma engeli ortak bağları da dikkate alır.
Birleşmeden dolayı eski talep hükümsüz olduğunda soru tek kanonik çift
olarak korunur ve eski paket bağları buna aktarılır. Aynı soruyu başka
pakette taramak ikinci soru açmaz, o paketi mevcut soruya bağlar.

Bir paketi iptal etmek diğer etkin paketlerin sorusunu kapatmaz. Açılış
paketi iptal edilmişse kullanıcı kararı kalan etkin paket adına uygulanır;
iptal paket diriltilmez. Son etkin paket iptal edilince paket kaynaklı soru
`gecersiz` olur. Paketten bağımsız açılan sorular iptalle kapanmaz.
Göç mevcut taleplerin paket bağlarını doldurur; ek bağlar varsa geri alma
reddedilir. Geliştirme veritabanına göç uygulanmadı.

Aday zaten talebin güncel kanonik hedefine çözümlüyse gereksiz açık soru
`gecersiz` olur; kullanıcı adına `AYNI` yazılmaz. Yeniden tarama da aynı
kimliği tekrar sormaz. Paket bağları, hükümsüzleştirme ve paket durumları
mevcut karar SAVEPOINT'inin içindedir.

**Eşzamanlılık.** Her yazma kendi SAVEPOINT'inde çalışır ve dar hata
eşlemesinden geçer (4.5 kalıbı): kilit / anlık görüntü çakışması
`MukerrerlikYazmaCakismasi`, aynı çift için eşzamanlı ikinci açık talep
`SupheZatenAcik`, kapalı talebe ikinci karar `KararTalebiKapali`; başka
veritabanı hataları olduğu gibi yükselir. Yeniden deneme çağıranındır,
serviste retry döngüsü yoktur. İki bağlantılı gerçek yarış testleri hem aynı
şüphenin açılmasını hem aynı talebin cevaplanmasını kanıtlar. Aşama 4.6
dışındaki eski modüller bu tura dahil edilmedi ("Bilinen teknik borç").

**Kapsam dışı, bilinçli.** Güvenli karar motoru, güven puanı ve sezgisel kural
yoktur; karar kaynağı yalnız kullanıcıdır ve bu artık sözde değil kodda ve
şemada zorlanır ("Karar kaynağı, iptal ve kanonik kimlik"). Aşama 4.9 yeni bir
karar kaynağı getirirse hem servis kapısı hem `karar_aktor_turu` kısıtı birlikte
genişletilir. İki aday nesnenin birbiriyle mükerrerliği aranmaz (paket içi
çözüm 4.8'in işidir). Kesin kayıt (`Kayit` / `KayitAlani`) tablosu **hâlâ
yoktur**; 4.6 "kayıtları taşıma" gereksinimini 4.7 tablolarını erken açarak
değil, mevcut dünya üzerinde çözer: aday kayıt bağları hiç ellenmez, aday →
kesin nesne çözümlemesi ayrı bir köprü tabloda ilişkisel durur. Kesinleştirme
4.8'dedir. `finans/` hâlâ boştur.

**Testler** (`tests/test_mukerrerlik.py`, 109 test): sıfır şart protokolü
çalıştırmaz; tek şart eşleşince şüphe; iki şartta yalnız birincisi ya da
yalnız ikincisi eşleşse de şüphe (VEYA); hiçbiri eşleşmezse şüphe yok;
seçilmemiş özellik eşleşse de şüphe yok; iki yönlü tarama şartsız ucu yakalar;
başka türün özelliği servis ve ham SQL ile reddedilir; ondalık sayısal
eşdeğerlik (`12.50` ↔ `12.5`) eşleşir, `12.6` eşleşmez; eşleşme otomatik
"aynı" kararı vermez; şüphe kalıcı talep üretir ve yeni bağlantıda okunur;
paket `BEKLIYOR` olur ve taslak yazılamaz; `AYRI` kapatır; `KARARSIZ` açık
bırakır; iki açık talebin biri çözülünce paket hâlâ bekler, sonuncusu
çözülünce çalışır; açık talep varken elle devam edilemez; iptal paket
canlanmaz; aynı şüphe tekrar üretilmez (servis ve kısmi benzersiz indeks);
aynı talebe ikinci karar uygulanmaz; iki bağlantı yarışında tek karar kazanır
ve tek talep oluşur; gelen ve giden ilişkiler taşınır; mükerrer olacak ilişki
ikinci kez yazılmaz; kendine dönecek bağlantı düşer; en çok üst ihlali ve
hiyerarşi çevrimi birleştirmeyi reddeder ve her şey geri alınır; birleşmiş
nesne yeniden birleşemez ve taramaya girmez; birleşimden sonra hedef yeniden
taranır; aday çözümlemesi kalıcıdır ve kesin dünya büyümez; aday kayıt bağları
korunur; çözümlenmiş ve talebe konu aday silinemez; şartlı aday silinince
şartları da gider; zincirleme alt nesne şüphesi oluşur ve döngüye girmez;
denetim izi aktör ve olayları taşır, ham özellik değeri taşımaz, uzun gerekçe
reddedilir; şema ayrımı ve `çekirdek → finans` yasağı korunur;
`foreign_key_check` ve `integrity_check` temizdir.

2026-09-20 incelemesinin regresyon testleri aynı dosyada: iptal paketin talebi
`gecersiz` olur ve aynı çift yeni pakette yeniden değerlendirilir, eski talep
geçmişte karar taşımadan durur ve karara açılmaz, denetim izinde
`karar_talebi_gecersiz_kaldi` görünür, iptal ile karar yarışında tam biri
kazanır; ajan ve sistem aktörü `AYNI` / `AYRI` / `KARARSIZ` veremez (üç karar
× iki aktör) ve reddedilen çağrı hiçbir şeyi değiştirmez, ajan yine tarayıp
şüphe açabilir, ham SQL ajan kararı yazamaz; `3 → 2` ardından `2 → 1`
birleşiminde zincir kalmaz, eski karar hedefi ve `karar_talebi_id` bağı
korunur, kanonik nesne tek sıçramada bulunur, ikinci karar düşerse ilk
birleşim bozulmaz, eşzamanlı iki birleşim tutarsız graf üretmez; birleşen
kaynağın eski kimlik değeri üçüncü nesneyi yakalar ve karar talebi kanonik
hedefi gösterir, hedef ile kaynağın farklı değerleri birlikte korunur,
birleşmiş kaynak bağımsız eşleşme olarak dönmez; aynı aday iki kesin nesneyle
eşleşir ve paket bekler, `AYNI` + `AYRI` tek çözümleme bırakır, iki `AYNI`
kesin nesneleri birleştirir ve adayın kesin hedefi belirsiz kalmaz, önceki
`AYRI` kararına çarpan ikinci `AYNI` reddedilir ve her şey geri alınır,
çözümlenmiş adayın hedefi birleşimden sonra tek adımda bulunur; silinen aday
kimliği yeniden kullanılmaz (aynı paket içinde de).

İkinci inceleme turunun regresyon testleri: birleşmiş eski kimlik üzerindeki
`AYRI` kararı korunur ve işlem iz bırakmadan reddedilir, `AYRI` satırının ters
yönü de (hedef ucu kaynak kümesinde) birleşmeyi durdurur, çok adımlı zincirin
iki merge derinindeki üyesi de sayılır ve kullanıcıya `AYRI` çıkışı kalır,
ilgisiz bir `AYRI` geçerli birleşmeyi engellemez; bayat açık talep hükümsüz
kalır ve soru kanonik uçlarla tek talep olarak yeniden sorulur, hükümsüz
talebe karar verilemez, iki ucu aynı kanonik nesneye düşen talep yeniden
sorulmaz, başka pakete ait bayat talep o paketi de cevap gelene kadar bekletir; `karar_ver`
dört ayrı kesme noktasında (ilk değişiklikten hemen sonrası, birleşim satırı
yazıldıktan sonrası, uzlaştırma ve servisin son adımı) hiçbir kalıcı değişiklik
bırakmaz ve çağıranın önceki bağımsız değişikliği korunur, aday çözümlemesi
yolunda da yarım satır kalmaz, `paketi_iptal_et` iki kesme noktasında yarım
iptal bırakmaz ve yeniden denenince olağan biçimde çalışır.

Göç testleri (`tests/test_gocler.py`): `0007 → 0008 → 0007 → 0008` ve
`0008 → 0009 → 0008 → 0009` döngüleri, satır varken geri almanın reddi
(`0009`da geçersiz talep / kanonik hedefi değişmiş birleşim / yeni denetim
olayı için ayrı ayrı), `0008`de kalmış birleşim zinciri varken `0009`un
kanonik nesne uydurmayı reddetmesi, sıfır veritabanından `head` ile ORM
metadata birebirliği, bütün kısıt ve indeks adlarının kalıba uygunluğu.

## Mimari sınır: çekirdek ve finans

Karar (2026-09-18, Abdüllatif). Önceki geliştirme hattında genel mekanik ile
finansal domain birbirine karıştı: para birimi, kuruş, eksen (VARLIK / BORC /
GIDER), yön (ARTTIR / AZALT), HESAP_HAREKETI, bakiye ve ekstre mutabakatı
ortak katmana girdi. Yeniden inşada finans bilgisi yok edilmez; yeri
belirlenir.

* DEFTERIKI iki kavramsal katmana ayrılır: genel **çekirdek**
  (`defteriki.cekirdek`) ve finansal **domain** (`defteriki.finans`).
* `finans → çekirdek` bağımlılığına izin vardır: finans çekirdeği kullanabilir.
* `çekirdek → finans` bağımlılığı yasaktır: çekirdek `defteriki.finans`
  paketini ve alt modüllerini hiçbir import biçimiyle kullanamaz.
* Çekirdek finansal anlam taşımaz: finansal tip, enum, iş kuralı çekirdekte
  bulunmaz.
* Finansal kavramlar finans paketinin sorumluluğudur.
* İsim değiştirmek domain bağımsızlığı sayılmaz; aynı finansal varsayım başka
  adla da çekirdeğe taşınamaz.
* Finansal semantik (para birimi, eksen, yön, işlem türü, mutabakat kuralı
  gibi) Python enum'larına, sabitlerine ya da formüllerine değil, finans
  paketinin okuduğu **tanım verisine** yazılır; çekirdek bu veriyi anlamını
  bilmeden taşır ve denetler.
* Bu sınır otomatik testle korunur.

Test (`tests/test_mimari_sinir.py`) `src/defteriki/cekirdek/**/*.py`
dosyalarını Python AST ile okur; `defteriki.finans` bağımlılığı bulursa dosya
ve satırla, dolaylı bağımlılık bulursa modül zinciriyle düşer. Kapsam:

* `import defteriki.finans[.x]` (`as` ile de), `from defteriki.finans[.x]
  import y`, `from defteriki import finans`;
* göreli import: `from .. import finans`, `from ..finans import x`, derin
  paketlerde `...`;
* metin hedefli dinamik import: `importlib.import_module(...)` ve
  `__import__(...)`; hedef ilk konumsal argüman ya da `name=`; `package=` ile
  ya da dosyanın kendi paketine göre çözülen göreli hedef (`".finans"`);
  `import importlib as il` ve `from importlib import import_module as im`
  takma adları;
* fonksiyon gövdesi içindeki importlar;
* dolaylı bağımlılık: çekirdek modülünün `defteriki` içindeki statik import
  grafiği üzerinden (aynı biçimlerle) finansa ulaşması, örneğin çekirdek →
  `defteriki.yardimci` → `defteriki.finans`. Python bir alt modülü yüklerken
  üst paketlerin `__init__.py` dosyalarını da çalıştırdığından bunlar grafiğe
  dahildir: `from defteriki.yardimci.alt import veri` yazan bir çekirdek
  modülü, `alt.py` temiz olsa bile `yardimci/__init__.py` finansı yüklüyorsa
  ihlaldir; başlangıç modülünün kendi üst paketleri de (`defteriki/__init__`,
  `cekirdek/__init__`) sayılır. Zincir en kısa yol olarak ve üst paket adımı
  `(üst paket, X yüklenirken)` etiketiyle raporlanır; her modül bir kez
  ziyaret edilir, döngüler taramayı bitirir.

Kapsam dışı, bilinçli sınır: çalışma anında kurulan metinler
(`import_module(ad)` değişkenle), `sys.modules` erişimi, `getattr`,
`exec`/`eval`, üçüncü taraf paketlerin içinden geçen yollar. Test bütün
Python dinamiklerini çözdüğünü iddia etmez; bunlar kod incelemesinin
konusudur. Bağımlılık denetimi kelime aramaz; korunan şey bağımlılık
yönüdür (kelime denetimi aşağıda ayrı bir mekanizmadır). Denetleyicinin her yasak biçimi
yakaladığı, izinli biçimlere dokunmadığı ve dolaylı zinciri doğru
raporladığı sentetik ağaçta ayrıca sınanır; çekirdek boşken yeşil kalması tek
başına kanıt sayılmaz.

**Finansal ad denetimi (Aşama 4.2, 2026-09-18).** Bağımlılık yönü tek başına
yetmez: çekirdek finansı import etmeden de `BANKA = "BANKA"` ya da `class
HesapHareketi` yazarak finansal anlam taşıyabilir. Aynı test dosyasındaki
ikinci denetim `src/defteriki/cekirdek/**/*.py` ve `alembic/versions/*.py`
dosyalarını AST ile okur; tanımlayıcıları (değişken, sınıf, fonksiyon,
parametre, nitelik, anahtar argüman, import adı) ve metin sabitlerini
(f-string parçaları dahil) parçalara ayırır (`HesapHareketi` → HESAP,
HAREKETI; `para_birimi` → PARA, BIRIMI; Türkçe harfler ASCII'ye indirgenir)
ve yasak adı **tam parça** olarak arar: `BANKA`, `HESAP`, `KART`, `KREDI`,
`KMH`, `PARA_BIRIMI` (ardışık iki parça), `VARLIK`, `BORC`, `GIDER`,
`BAKIYE`. `hesapla`, `kartela`, `borclu`, `kredibilite` yakalanmaz;
`hesap_kodu`, `kmh_limiti`, `dict(hesap_no=1)`, `f"hesap {x}"` yakalanır.
Docstring'ler, nitelik açıklamaları (tek başına duran metin ifadeleri) ve
yorumlar denetim dışıdır: sınır anlatılabilir, ad ya da veri değeri olarak
taşınamaz. Denetleyici sentetik dosyalarda her yasak biçimi yakaladığı ve
izinli biçimlere dokunmadığı ile ayrıca sınanır. Bilinçli sınır: liste
sabittir ve tam parça arar; `bankalar` gibi çekimli biçimler ve listede
olmayan kavramlar yakalanmaz, bunlar kod incelemesinin konusudur. Gerçek
semantik sızıntı (adsız finansal varsayım: sabit ölçek, sabit formül)
sonraki aşamalarda ayrıca denetlenir.

Aşama 4.0'da iki paket de boş açıldı. Aşama 4.1 sonrası `cekirdek/`
`veritabani.py` (SQLite bağlantı politikası, `TabloTabani`, işlem sınırı) ve
`gocler.py` (Alembic şema sürümü ve göç) modüllerini içerir. Aşama 4.2
`tanim_tablolari.py` ve `tanim_islemleri.py` modüllerini ekledi: tanım
tabloları ve yazma/okuma işlevleri, hiçbir domain'in türünü bilmeden
("Tanım sistemi" bölümü). Aşama 4.3 `nesne_tablolari.py` ve
`nesne_islemleri.py` modüllerini ekledi: nesne, özellik, ilişki, hiyerarşi
ve yaşam durumu, yine hiçbir domain'in türünü, özellik adını ya da ilişki
adını bilmeden; çekirdekte yalnız teknik değer türleri (metin, tam sayı,
mantıksal, ondalık) ve iki yaşam durumu (etkin, kapalı) sabittir ("Nesne
motoru" bölümü). Bütün finans tanımları silinip yerine envanter gibi başka
bir alanın tanımları konsa çekirdek kaynak kodu değişmez; nötr `ENVANTER`
testleri bunun kanıtıdır. `finans/` hâlâ boştur (`__init__.py` yalnız
docstring taşır). Eski hattan modül taşınmamış, iş modeli yazılmamıştır.

## Bilinen teknik borç

2026-09-19 incelemesinde tespit edildi; kararla ertelendi. Bu bölüm borç
kapanınca silinir.

**1. Göç kaynakları kaynak dizini düzenine bağlı; paketlenmiş uygulamada
çalışmaz.** Üç yer birlikte bu varsayımı taşır:

* `src/defteriki/cekirdek/gocler.py`: `PROJE_KOKU = Path(__file__).resolve().parents[3]`
  ile `alembic.ini` ve `alembic/` dizini modül konumundan üç klasör yukarıda
  aranır; bu yalnız düzenlenebilir (editable) kaynak kurulumunda doğrudur.
* `alembic.ini` içindeki `prepend_sys_path = src`: paketi kaynak ağacından
  yükler.
* Depo kökündeki `alembic/env.py` ve `alembic/versions/`: kurulu paketin
  parçası değildir.

Yürütme planındaki Windows masaüstü paketi ve "önceki sürümden yükseltme"
adımında `parents[3]` yanlış yere düşer ve şema yükseltme çalışmaz. Hedef
çözüm (paketleme aşamasından önce, kod o zaman yazılır): göç betikleri
`src/defteriki/` altında paket kaynağı olarak dağıtılır; yol `importlib.resources`
ya da paketleme biçimine uygun eşdeğer mekanizmayla, dizin varsayımı
olmadan bulunur; `alembic.ini` gerekliliği kalkar, yapılandırma programda
üretilir; şema yükseltmesi uygulamanın kendi komutuyla yapılır (örneğin
`defteriki sema-yukselt`). Korunacak karar: şema yükseltmesi uygulama
başlangıcında otomatik yapılmaz, açık bir işlem olarak çalıştırılır.
`uv run alembic upgrade head` biçiminin aynen korunması ürün gereksinimi
değildir.

**2. Eşzamanlı yazma eşlemesi yalnız taslak modülünde.** SQLite iki bağlantı
aynı anda yazmaya kalkınca birini durdurur; bu güvence her modülde geçerlidir.
Ama yalnız `taslak_islemleri` bu ham hatayı (`database is locked` / `busy`,
yarışan benzersizlik ihlali) `TaslakYazmaCakismasi` gibi anlamlı hataya
çevirir ve `belge_al` kendi içinde yeniden dener; tanım, nesne ve okuma
servisleri ham `OperationalError` / `IntegrityError` yükseltir (örnek: iki
bağlantı aynı belgede `okuma_baslat` çağırırsa ikisi de aynı sürüm numarasını
hesaplar, ikincisi benzersizlik hatası alır; ekleme-yalnız kilit sayımı ile
ilk nesne yazımı yarışırsa biri kilit hatası alır). Tek kullanıcılı
masaüstünde kabul edilir. Çok istemci (GUI açıkken Cowork yazıyor) ya da çok
kullanıcı gündeme gelince taslak modülündeki yazma sınırı kalıbı
(`_yazma_siniri`) diğer modüllere yayılır ve yeniden deneme noktası çağıranda
(MCP aracı, GUI) kurulur. Çok kullanıcı duruşu (2026-09-19): bugün ek mimari
kurulmaz; SQLite'a özgü SQL (`typeof`, `json_valid` gibi) şema ve göç
sınırında kalır, servis katmanına yayılmaz; Aşama 4.6 denetim izine "kim
yaptı" (aktör) alanı baştan konur.

## Kurulum

```bash
uv sync
```

Python 3.13 ve uv gerekir. `uv sync` sanal ortamı ve geliştirme
bağımlılıklarını (pytest, hypothesis, ruff, pyright, pre-commit) kurar.

Klon sonrası bir kez, commit öncesi kontrol kancasını yükle:

```bash
uv run pre-commit install
```

## Başlatma

```bash
uv run defteriki
```

Komut sırayla ayarları ortam değişkenlerinden yükler, seçilen ortamın
dizinlerini (veritabanı dizini, `belgeler/`, `logs/`) açar, teknik günlüğü
kurar ve başlangıç olayını günlüğe yazar. Başarılıysa tek satırlık bir mesaj
(ortam, veri kökü, günlük dosyası) basar ve `0` ile çıkar. Henüz veritabanı
oluşturmaz; finansal iş yapmaz.

Herhangi bir adım başarısızsa (`DEFTERIKI_ORTAM` bilinmeyen değer, test
ortamında veri kökü verilmemiş, dizin yerine dosya var, log dosyası
açılamıyor...) anlaşılır bir hata stderr'e yazılır ve çıkış kodu `1` olur.
Günlük kurulamadıysa başarılı başlangıç mesajı verilmez. Yollar
uygulamanın hangi dizinden başlatıldığına bağlı değildir; modüller import
edildiğinde dizin ya da dosya oluşturulmaz.

## MCP kapısı

Cowork'un DEFTERIKI'ye ulaştığı tek kapı. stdio taşımasıyla çalışır:

```bash
uv run defteriki-mcp
```

Komut `uv run defteriki` ile aynı hazırlığı yapar (ayarlar, dizinler, günlük),
ardından MCP sunucusunu stdin/stdout üzerinde çalıştırır. İstemci bağlantıyı
kapatınca `0` ile çıkar. Hazırlık düşerse hata stderr'e yazılır, çıkış kodu
`1` olur; stdout'a hiçbir şey yazılmaz.

Bu sürümde tek araç var: `sistem_durumu`. Uygulama sürümü, ortam adı, şema
sürümü ve yetenek listesini döndürür; yol, anahtar ya da ortam değişkeni
içermez. Şema sürümü gerçektir (Aşama 4.1): veritabanı dosyası varsa
Alembic'in `alembic_version` tablosundaki sürüm (mevcut göç zincirinin
başı neyse o), dosya yoksa ya da göç uygulanmamışsa `yok`. Dosya yokken
bağlantı açılmaz, boş SQLite dosyası oluşmaz; araç göç çalıştırmaz. Testler
dosya yok, dosya var ama göçsüz ve göç uygulanmış senaryolarını süreç içinde
ve stdio üzerinden ayrı ayrı sınar. Ürün verisi yazan araç henüz yoktur. Aşama 3'te kullanılan
geçici deneme araçları (`dosya_dene`, `deneme_baslat`, `deneme_durumu`)
kapı temizliğinde kaldırıldı; ne ölçtükleri "Cowork entegrasyonu"
bölümünde. Gelen dizini ayarı (`DEFTERIKI_GELEN_DIZINI`) kaldı: Aşama 4'te
belge alımı Cowork'un bu dizine bıraktığı dosyanın yoluyla yapılır.

Kurallar:

* stdout yalnız protokolündür. SDK'nın stdio taşıması sunucu çalışırken
  dosya tanımlayıcısı 1'i stderr'e çevirir; DEFTERIKI ayrıca hiç `print`
  kullanmaz. Test, stdout'un yalnız JSON-RPC satırları taşıdığını doğrular.
* Bütün tanı çıktısı teknik günlüğe gider. SDK'nın `mcp` günlüğü de aynı
  dosyaya bağlanır (olay sütunu `-`), stderr'e düşmez.
* Modül import edildiğinde sunucu kurulmaz, dosya oluşturulmaz.
* Her araç çağrısında günlüğe `mcp_el_sikisma` satırı düşer: istemci adı ve
  sürümü, müzakere edilen protokol sürümü, istemci yetenekleri. Aşama 3'ün
  ölçümü bu satırdan okunur.

Test (`tests/test_mcp_kapisi.py`) sunucuyu ayrı süreçte başlatır; ham
JSON-RPC ile `initialize`, `tools/list` ve `tools/call` yapar, her isteğin
yanıtını bekler, sonra stdin'i kapatır.

## Cowork entegrasyonu

Aşama 3'ün dört teslimi ve ölçümleri (aşama 2026-09-16'da kapandı). Geçici
deneme araçları `dosya_dene`, `deneme_baslat`, `deneme_durumu` ve testleri
kapı temizliğinde kaldırıldı; yalnız `sistem_durumu` kaldı. Aşağıdaki satırlar
o araçların ne ölçtüğünün kalıcı kaydıdır. Kalıcı çıkarımlar: SDK `mcp` 2.2.0
kilitli; protokol 2025-11-25, istemcide elicitation ve sampling yok; belge
alımı dosya yolu yöntemiyle (gelen dizini), parça yükleme gerekmez; kullanıcı
kararı bekleyen işler için "BEKLIYOR + talep kimliği, istemci tekrar sorar"
yöntemi Cowork'la çalışır, talep durumu veritabanında tutulur.

| Teslim | Konu | Sonuç |
|---|---|---|
| 3.1 | MCP SDK ve sunucu iskeleti | Bitti. `mcp` 2.2.0 `uv.lock` ile kilitli. SDK 2.x'te `FastMCP` adı `MCPServer` oldu (`mcp.server.mcpserver`); 1.x örnekleri doğrudan çalışmaz. Araç dönüş tipi `slots=True` dataclass olamaz, SDK şemayı düşürüyor. Yerel istemciyle protokol sürümü `2025-06-18` müzakere edildi. |
| 3.2 | Gerçek Cowork bağlantısı | Bitti (2026-09-15). Ayar: Claude masaüstü `claude_desktop_config.json` → `mcpServers`, komut `uv.exe run --directory C:/dev/DefterIki defteriki-mcp`, ortam değişkeni yok, veri `%LOCALAPPDATA%/DEFTERIKI/gelistirme`. Ölçüm (`mcp_el_sikisma`): istemci `local-agent-mode-defteriki 1.0.0`; müzakere edilen protokol sürümü **2025-11-25** (sunucunun en yükseği 2026-07-28, istemci daha eskisini seçti); istemci yetenekleri `roots.listChanged=true` ve `io.modelcontextprotocol/ui` uzantısı (`text/html;profile=mcp-app`); sampling ve elicitation bildirilmedi. Uygulama açılışta sunucuyu üç kez başlatıyor: biri 10 ms içinde kapanan yoklama, ikisi kalıcı (Cowork ve Claude Code). Zaman aşımı gözlenmedi: başlatmadan araç yanıtına kadar sorun yok, uygulama kapanınca sunucular EOF ile temiz çıktı. Uygulamanın kendi MCP günlüğü boş; ölçüm sunucu günlüğünden alındı. |
| 3.3 | Dosya erişim denemesi | **Bitti (2026-09-15): dosya yolu yöntemi çalıştı, parça yükleme gerekmez.** Araç `dosya_dene` yazıldı ve testlendi (izinli dosya, boş dosya, alt dizin, dizin dışı, `..`, göreli yol, olmayan dosya, dizin, okuma hatası, stdio üzerinden okuma ve red; simgesel bağlantı testleri Windows'ta bağlantı yetkisi yoksa atlanır). Cowork ayarı: `mcpServers.defteriki.env` → `DEFTERIKI_GELEN_DIZINI=C:/dev/DefterIki-gelen`; uygulama yeniden başlayınca dizin kendiliğinden oluştu. Deneme ~402 KB'lik gerçek bir hesap özeti PDF'iyle iki senaryoda yapıldı: (a) dosya elle gelen dizinine kopyalandı, Cowork'a yol söylendi → `sonuc=okundu`; (b) PDF Cowork'a yüklendi, gelen dizinine bırakması istendi → Cowork dosyayı dizine yazdı ve `dosya_dene` ile okuttu → `sonuc=okundu`. İki dosyanın SHA-256 özeti birebir aynı; Cowork dosyayı bozmadan aktarıyor. Günlükte iki `mcp_dosya_deneme` satırı, red ya da hata yok. Aşama 4 belge alımı bu yöntemle kurulacak: Cowork dosyayı gelen dizinine bırakır, yolu MCP aracına verir. |
| 3.4 | Çok adımlı protokol denemesi | **Bitti (2026-09-16): Cowork BEKLIYOR döngüsünü kendi başına, sadakatle yürüttü.** Araç çifti `deneme_baslat` / `deneme_durumu` yazıldı ve testlendi (süreç içi sahte saatle bekle→tamamla geçişi, aynı anahtar aynı kimlik, boş anahtar reddi, bilinmeyen kimlik, yanıt ve günlükte anahtar yok; stdio üzerinden başlat→durum→bilinmeyen→tekrar başlat döngüsü). Cowork'a tek cümle verildi: "bir deneme işi başlat; bekliyor dönerse aynı anahtarla durumu sor, tamamlanınca bildir." Günlük (`mcp_deneme`): `deneme_baslat` → BEKLIYOR, talep kimliği verildi; `deneme_durumu` üç kez soruldu: 3,1 s (BEKLIYOR), 17,4 s (BEKLIYOR), 42,5 s (TAMAMLANDI). Sorgu aralıkları yaklaşık 3 s, 14 s, 25 s; Cowork bekleme süresini kendi uzattı, vazgeçmedi, kimliği doğru taşıdı, anahtarı değiştirmedi, aynı işi yeniden başlatmadı. Hiçbir çağrı açık kalmadı; durum sorguları anında döndü. Dört çağrı da aynı sunucu sürecinden (`surec` eşit) geldi: Claude masaüstü sunucuyu yine iki kalıcı süreç olarak başlattı ama tek sohbetin bütün çağrıları tek sürece gitti; BILINMIYOR görülmedi. Aşama 5 için çıkarım: BEKLIYOR + talep kimliği + istemcinin tekrar sorması çalışan bir yöntem; talep durumu yine de belleğe değil veritabanına yazılır, çünkü sohbetler ve uygulama yeniden başlatmaları arası süreç garantisi yok. |

## Teknik hata günlüğü

Günlük yalnızca ayarlardaki log dizinine yazar: `<log dizini>/defteriki.log`
(varsayılan `<veri kökü>/<ortam>/logs/defteriki.log`). Standart kütüphanenin
`logging` modülü kullanılır; ek bağımlılık yoktur.

Her satır `zaman | seviye | olay | mesaj` biçimindedir; olay türleri
şimdilik `baslangic`, `baslangic_hatasi`, `mcp_baslangic`, `mcp_el_sikisma`,
`mcp_kapanis`, `mcp_hatasi`. Dosya günlüğüne bağlanan dış kütüphane
kayıtlarında olay `-` olur.

Saklama sınırı: dosya 1.000.000 baytı aşınca döndürülür, en fazla 5 eski
dosya (`defteriki.log.1` ... `.5`) tutulur; toplam en çok ~6 MB. Kurulum
tekrar çağrılırsa önceki handler kapatılıp kaldırılır, aynı olay birden
fazla yazılmaz.

Gizlilik: belge içeriği, finansal kayıt içeriği, IBAN, kimlik bilgileri,
sırlar ve ortam değişkenleri günlüğe yazılmaz. Hatalar yalnızca türüyle
(`builtins.ValueError` gibi) kaydedilir; ham hata mesajı ve traceback dosyaya
dökülmez. Kullanıcıya gösterilen hata metni stderr'e gider, dosyaya değil.
Aynı kural dosyaya bağlanan dış kütüphane günlüğü (MCP SDK) için de geçerlidir
(2026-09-18). Sarmalayıcı handler kütüphane kaydını üç kuralla indirger:

* İstisna taşıyan kayıt (`logger.exception`; SDK'da beklenmeyen araç hatası)
  yalnız `hata türü: ...` olarak yazılır; mesaj, `exc_info` ve yığın izi
  düşmez.
* Parametreli kayıt (SDK'nın beklenen `ToolError` yolu:
  `logger.info("Tool %r failed: %r", ad, str(exc))`) yalnız sabit şablonuyla
  yazılır, değerler yerine türleri not edilir:
  `Tool %r failed: %r [parametreler gizlendi: str, str]`. Araç adı ve hata
  metni dosyaya geçmez; şablon kütüphanenin kendi sabit metnidir.
* Mesajı metin olmayan kayıt (`logger.warning(exc)`) yalnız mesaj nesnesinin
  türüyle yazılır.

Parametresiz, istisnasız sabit kayıtlar olduğu gibi yazılır; hiçbir seviye
toptan kapatılmaz. Sarmalayıcı kaydın kopyası üzerinde çalışır, aynı logger'a
bağlı başka handler'ların gördüğü kayıt değişmez. SDK'nın kurulu dosyalarına
dokunulmaz. Testler (`tests/test_mcp_kapisi.py`) gerçek stdio çağrısında araç
gövdesini sentetik hassas içerikli hatayla değiştirir: beklenmeyen hata için
dosyada yalnız `hata türü: ...UnexpectedToolError`, beklenen `ToolError` için
yalnız şablon kalır; araç `isError` sonucu döndürür. Bilinen sınır: kütüphane
metni f-string ile önceden biçimlendirip parametresiz gönderirse değerler
ayırt edilemez; SDK 2.2.0'ın sunucu yolunda istemci verisi taşıyan kayıtlar
`%` biçimlidir, f-string'li kayıtları kayıt anındaki sunucu tarafı adlardır
(araç, kaynak, istem adı). Not: SDK araç hatasının metnini istemciye `isError`
yanıtı içinde döndürür; bu MCP katmanının işidir ve araçlar geldiğinde ele
alınır.

## Kalite kontrolü

Biçim kontrolü, statik kontrol, tip kontrolü ve testler tek komutla:

```bash
uv run python scripts/kontrol.py
```

Betik sırayla `ruff format --check`, `ruff check`, `pyright` ve `pytest`
çalıştırır. Bir adım düşse de diğerleri çalışır; sonunda toplu sonuç verir ve
herhangi bir adım başarısızsa sıfırdan farklı çıkış kodu döner. Kaynak
dosyalarını değiştirmez.

Yalnızca testler:

```bash
uv run pytest
```

Aynı kontrol her `git commit` öncesinde pre-commit kancasıyla otomatik
çalışır (`.pre-commit-config.yaml`, tek kanca: `scripts/kontrol.py`);
bir adım düşerse commit yapılmaz. Kanca kaynak dosyalarını değiştirmez.

## Ayarlar

Bütün yollar `defteriki.ayarlar` modülünden gelir; uygulamanın nereden
başlatıldığı yolları değiştirmez.

```python
from defteriki.ayarlar import ayarlari_yukle, dizinleri_hazirla

ayarlar = ayarlari_yukle()  # ortam değişkenlerini okur, diske yazmaz
dizinleri_hazirla(ayarlar)  # gerekli dizinleri açar, dosya oluşturmaz
```

Ortam değişkenleri (öncelik yukarıdan aşağıya):

| Değişken | Anlamı |
|---|---|
| `DEFTERIKI_VERITABANI_YOLU` | Veritabanı dosyası; türetilmiş yolun yerine geçer |
| `DEFTERIKI_BELGE_DIZINI` | Belge arşivi dizini; türetilmiş yolun yerine geçer |
| `DEFTERIKI_LOG_DIZINI` | Log dizini; türetilmiş yolun yerine geçer |
| `DEFTERIKI_GELEN_DIZINI` | Gelen dizini: Cowork'un dosya bıraktığı, MCP araçlarının okumaya izinli olduğu tek dizin; türetilmiş yolun yerine geçer |
| `DEFTERIKI_VERI_KOKU` | Ortamların ortak üst dizini; ortam adı altına eklenir |
| `DEFTERIKI_ORTAM` | `gelistirme` (varsayılan), `test`, `gercek` |

Varsayılan veri kökü Windows'ta `%LOCALAPPDATA%\DEFTERIKI\<ortam>`, Linux'ta
`$XDG_DATA_HOME/DEFTERIKI/<ortam>` (yoksa `~/.local/share/...`), macOS'ta
`~/Library/Application Support/DEFTERIKI/<ortam>`. Bu kökten
`defteriki.sqlite3`, `belgeler/`, `logs/` ve `gelen/` türetilir.

Kurallar:

* Yollar mutlak olmalı; boş veya göreli değer hata verir.
* Bilinmeyen ortam adı hata verir.
* `test` ortamı `DEFTERIKI_VERI_KOKU` ister ve tekil yolların bu kökün dışına
  çıkmasına izin vermez. Sınır yolun yazılı biçimine değil fiziksel
  karşılığına bakar (2026-09-18, `Path.resolve`): kök içindeki bir simgesel
  bağlantı ya da junction dışarıyı gösteriyorsa yol reddedilir ve hiçbir dizin
  oluşturulmaz; hata mesajı fiziksel karşılığı da söyler. Kabul edilen yol
  verildiği biçimde saklanır. Bu sınır yalnız `test` ortamınındır; geliştirme
  ve gerçek ortamların yol politikası değişmedi. Testler: normal yol, `..` ile
  kaçış, simgesel bağlantıyla kaçış (Windows'ta yetki yoksa atlanır), junction
  ile kaçış (yalnız Windows), kök içini gösteren bağlantı.
* Tekil yol değişkenleri diğer ortamlarda ortam ayrımını geçersiz kılabilir.

### Defter3 yerel kurulumu (2026-09-18)

Bu hattın yerel verisi eski hattan ayrıdır. Claude masaüstü
`claude_desktop_config.json` içindeki `mcpServers.defteriki` girdisi bu
depoyu (`uv run --directory C:\dev\DefterIki defteriki-mcp`) şu ortam
değişkenleriyle çalıştırır:

| Değişken | Değer |
|---|---|
| `DEFTERIKI_VERI_KOKU` | `C:\dev\Defter3-veri` |
| `DEFTERIKI_GELEN_DIZINI` | `C:\dev\Defter3-gelen` |

Türetilen yollar: `C:\dev\Defter3-veri\gelistirme\defteriki.sqlite3`,
`...\belgeler`, `...\logs`; gelen dizini `C:\dev\Defter3-gelen`. Bu dosya
Git'e girmez; kurulum yalnız bu makinede geçerlidir. Paket ve komut adları
(`defteriki`, `defteriki-mcp`) değişmedi; ayrım yalnız veri kökündedir.

Düzeltme (2026-09-19): bu bölüm 2026-09-18'de MCP girdisinin Defter3
köklerine çevrildiğini yazıyordu, ama dosya gerçekte değiştirilmemişti ve
girdi eski `C:\dev\DefterIki-veri` / `C:\dev\DefterIki-gelen` köklerini
gösteriyordu; Claude masaüstü her açılışta MCP sunucusunu başlatınca sunucu
eski klasörleri yeniden oluşturuyordu. 2026-09-19'da girdi gerçekten
düzeltildi (yedek `claude_desktop_config.json.yedek-2026-09-19`), kullanıcı
düzeyindeki `setx` değişkenleri de aynı köklere çevrildi ve eski hattın
`C:\dev\DefterIki-veri` / `C:\dev\DefterIki-gelen` klasörleri silindi
(içlerinde veritabanı yoktu). Artık terminal ve Cowork aynı kökleri kullanır.

## Dizin düzeni

```
src/defteriki/    uygulama paketi
  ayarlar.py      merkezi ayarlar (ortam, yollar)
  baslangic.py    uv run defteriki giriş noktası; ortak hazırlık (ortami_hazirla)
  gunluk.py       teknik hata günlüğü
  mcp_kapisi.py   uv run defteriki-mcp; MCP sunucusu ve araçları
  cekirdek/       genel çekirdek; finansı tanımaz
    veritabani.py   SQLite bağlantı politikası, TabloTabani, işlem sınırı
    gocler.py       Alembic şema sürümü ve süreç içi göç
    tanim_tablolari.py  tanım paketi/sürüm/nesne türü/özellik/ilişki/kayıt türü/kayıt alanı tabloları
    tanim_sorgulari.py  tanım okuma: kimlikle getirme, listeleme, TanimHatasi / TanimBulunamadi
    tanim_islemleri.py  tanım yazma, hata modeli, ekleme-yalnız sürüm kilidi (okuma adlarını yeniden dışa aktarır)
    nesne_tablolari.py  nesne, nesne özelliği, nesne ilişkisi tabloları
    nesne_islemleri.py  nesne motoru: oluşturma, özellik doğrulama, ilişki, hiyerarşi, yaşam durumu
    arsiv.py            gelen dizini sınırı, akışla SHA-256, içerik adresli atomik arşiv, bütünlük, tarama
    belge_tablolari.py  arşiv dosyası, belge, okuma, kaynak tabloları
    belge_islemleri.py  belge alma, okuma sürümleri, kaynak izi, dosya/DB uzlaştırma
    deger_kodlama.py    özellik değeri kanonik metin kodlaması (kesin ve aday özellik ortak)
    taslak_tablolari.py işlem paketi, aday nesne / özellik / ilişki / kayıt, kayıt-nesne bağı tabloları
    taslak_islemleri.py işlem paketi yaşam döngüsü, taslak yazma / silme / sorgulama
    mukerrerlik_tablolari.py mükerrerlik şartı, karar talebi, aday çözümlemesi, nesne birleşimi
    mukerrerlik_islemleri.py şart seçimi, şüphe taraması, karar, birleştirme, zincirleme denetim
    denetim_tablolari.py aktörlü iş denetim izi tablosu (teknik günlükten ayrı)
    denetim_islemleri.py denetim olayı yazma ve okuma
  finans/         finansal domain; çekirdeği kullanabilir (henüz boş)
alembic.ini       Alembic yapılandırması (veritabanı adresi yok)
alembic/          env.py (yol merkezi ayarlardan), versions/ (0001 boş, 0002 tanım tabloları, 0003 sürüm no kısıtı, 0004 nesne motoru, 0005 kendine dönüş serbest, 0006 belge zinciri, 0007 işlem paketi ve taslak)
tests/            pytest testleri (test_mimari_sinir.py: çekirdek → finans yasağı, finansal ad denetimi, taslak / kesin ayrımı; test_nesne_motoru.py: ENVANTER dünyası; test_arsiv.py ve test_belge_zinciri.py: belge zinciri; test_islem_paketi.py: işlem paketi ve taslak)
scripts/          geliştirme betikleri (kontrol.py)
.pre-commit-config.yaml  commit öncesi kanca; kontrol.py'yi çalıştırır
kavramlar_sozlugu.md   ortak kavram tanımları; ekleme ve değişiklik yalnız Abdüllatif'in onayıyla
```

## Teknoloji

Bu projede kullanılacak teknoloji. Mutlak değil; ihtiyaç duyulması halinde değişebilir.

* Python 3.13 — ana dil
* uv — paket ve sanal ortam yönetimi
* pyproject.toml — proje/bağımlılık tanımı
* uv.lock — bağımlılık kilidi
* SQLite — ilişkisel veritabanı
* WAL — SQLite çalışma/journal modu; ayrı bir teknoloji değil
* SQLAlchemy 2.x — ORM / veritabanı erişimi
* Alembic — migration
* Pydantic 2.x — MCP giriş/çıkış ve veri doğrulama
* MCP Python SDK 2.x (`mcp`, `MCPServer`) — Cowork ↔ DEFTERIKI kapısı
* PySide6 — masaüstü GUI için
* pytest — test
* Hypothesis — property-based test
* Ruff — lint + format
* Pyright strict — statik type checking
* pre-commit — commit öncesi kalite kontrolleri
* Git — sürüm kontrolü
* `.gitignore` — DB, WAL/SHM, kişisel veri, cache, secret vb. dışlama
* `.gitattributes` — LF/CRLF standardizasyonu
