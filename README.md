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
veritabanı altyapısı) ve Aşama 4.2 (tanım sistemi) 2026-09-18'de bitti;
Aşama 4.3 (nesne motoru) sırada.
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
* Mimari sınır: `src/defteriki/cekirdek/` ve `src/defteriki/finans/`
  paketleri (henüz boş) ve bağımlılık yönünü koruyan AST testi
  (`tests/test_mimari_sinir.py`)
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
  (göç `0002`), `defteriki.cekirdek.tanim_tablolari` ve
  `defteriki.cekirdek.tanim_islemleri`; çekirdek hangi türlerin var olduğunu
  bilmez, testler nötr sahte paketlerle çalışır ("Tanım sistemi" bölümü)

Henüz yok: nesne ve kayıt verisi (tanımların örnekleri; Aşama 4.3 ve 4.7),
finans tanım paketi (`finans/` boş), GUI, ürün verisi yazan MCP aracı.

## Veritabanı

Aşama 4.1 (2026-09-18; Yeniden İnşa Teknik Planı madde 26). Güvenilir
persistence temeli; uygulama tabloları yalnız Aşama 4.2'nin tanım tablolarıdır
("Tanım sistemi" bölümü). Finansal tablo yoktur, `finans/` boştur.

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
tablosunu ekler (zincirin başı bugün `0002`). `alembic/env.py` tanım tablo
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
(sürüm ilerlememiştir), ardından gerçek zincir aynı dosyada `0001`e çıkar ve
`integrity_check` temizdir. Gerçek `0001_genel_altyapi` göçüne dokunulmaz.
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
gün aynı komutla uygulandı, dosya `0002` sürümünde.

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
veritabanından `upgrade head` `0002`ye çıkar ve tablolar `alembic_version` +
yedi tanım tablosudur; iki sıfır veritabanı aynı şemayı üretir; tekrar
`upgrade` şemayı değiştirmez; `head → 0001 → head` döngüsünde tanım tabloları
ve indeksleri gider, geri gelir ve `sqlite_master` birebir aynıdır,
`integrity_check` temizdir; elle yazılan `0002` göçünün ürettiği şema ORM
metadata'sıyla Alembic karşılaştırmasında farksızdır; her tanım tablosunun
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
| `tanim_surumu` | paketin sürümü; `surum_no > 0` (kontrol kısıtı) | `(tanim_paketi_id, surum_no)` |
| `nesne_turu` | sürümdeki nesne türü | `(tanim_surumu_id, kod)`; ayrıca `(id, tanim_surumu_id)` bileşik dış anahtar hedefi |
| `ozellik_tanimi` | nesne türünün özelliği | `(nesne_turu_id, kod)` |
| `iliski_tanimi` | iki nesne türü arasında yönlü ilişki (kaynak → hedef) | `(tanim_surumu_id, kod)`; kaynak ve hedef için `ix_` indeksleri |
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
türetmez, sıralama zorunluluğu yoktur.

**İşlevler (`src/defteriki/cekirdek/tanim_islemleri.py`).** Tanım tablolarına
tek giriş noktası; her işlev açık bir `Session` alır ve
`Veritabani.islem()` içinde çağrılır, kendi başına commit etmez. Yazma:
`paket_tanimla`, `surum_tanimla`, `nesne_turu_tanimla`, `ozellik_tanimla`,
`iliski_tanimla`, `kayit_turu_tanimla`, `kayit_alani_tanimla` (satırı ekler,
`flush` eder, kimlik atanmış ORM nesnesini döndürür). Okuma: `paket_bul`,
`paketleri_listele`, `surumleri_listele`, `nesne_turlerini_listele`,
`ozellik_tanimlarini_listele`, `iliski_tanimlarini_listele`,
`kayit_turlerini_listele`, `kayit_alani_tanimlarini_listele`. Üst kaydı
olmayan listeleme boş liste değil hata verir; boş liste ile "üst kayıt yok"
karışmaz. Silme ve güncelleme işlevi bu aşamada yoktur.

**Hata modeli.** Hepsi `TanimHatasi` altında, domain bağımsız:
`GecersizTanim` (kod biçimi, boş gösterim adı, pozitif olmayan sürüm no;
`ValueError`), `TanimBulunamadi` (verilen paket/sürüm/tür kimliği yok;
`LookupError`), `MukerrerTanim` (aynı kapsamda aynı kod ya da sürüm no),
`TanimSurumuUyusmuyor` (ilişkinin kaynak/hedef türü başka sürümde). Bu
denetimler uygulama sözleşmesidir; veritabanı kısıtları son savunmadır ve
aynı durumları ham `IntegrityError` ile de reddeder (testte iki düzey ayrı
ayrı sınanır). Herhangi bir hata `islem()` bağlamında yükselir ve aynı
işlemdeki bütün yazmalar geri alınır.

**Testler** (`tests/test_tanim_sistemi.py`, gerçek SQLite, göç zinciriyle
kurulmuş şema): paket tanımlanır ve okunur; aynı kodla ikinci paket hem
uygulama hem veritabanı düzeyinde reddedilir; büyük-küçük harf ayrımı;
geçersiz kod biçimleri (boş, boşluklu, rakamla ya da alt çizgiyle başlayan,
Türkçe harfli, noktalama) ve boş gösterim adı reddedilir; sürüm tanımlanır ve
numaraya göre listelenir, aynı pakette aynı numara reddedilir, farklı
paketlerde serbesttir, `0`/`-1` reddedilir, kontrol/benzersizlik/dış anahtar
kısıtları ham SQL ile de çalışır; nesne türü tanımlanır, aynı sürümde aynı
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

**Bilinçli sınırlar (Aşama 4.2'de yok, sonraki aşamaların kararı):** özellik
ve kayıt alanı için veri tipi / zorunluluk bilgisi (plan bu aşama için tip
sistemi tanımlamaz; 4.3 "özellik doğrulama" için gerekince yeni göçle
eklenir); ilişki için çokluk (cardinality), zorunluluk ve hiyerarşi kısıtları
(plan madde 8, Aşama 4.3); sürümün kilitlenmesi / değişmezliği (nesneler
sürüme bağlanınca gerekecek); nesne ve kayıt örnekleri; tanım silme ve
güncelleme; finans tanım paketi (Aşama 4.10).

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
("Tanım sistemi" bölümü). `finans/` hâlâ boştur (`__init__.py` yalnız
docstring taşır). Eski hattan modül taşınmamış, iş modeli yazılmamıştır.

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
Alembic'in `alembic_version` tablosundaki sürüm (bugün `0002`; zincirin
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
`...\belgeler`, `...\logs`; gelen dizini `C:\dev\Defter3-gelen`. Eski hattın
kökü `C:\dev\DefterIki-veri` (şema 0002 veritabanı, arşiv, günlükler) ve gelen
dizini `C:\dev\DefterIki-gelen` olduğu gibi durur; taşınmaz, kopyalanmaz,
silinmez. Bu dosya Git'e girmez; kurulum yalnız bu makinede geçerlidir. Paket
ve komut adları (`defteriki`, `defteriki-mcp`) değişmedi; ayrım yalnız veri
kökündedir. Dikkat: kullanıcı düzeyinde `setx` ile tanımlı
`DEFTERIKI_VERI_KOKU` hâlâ eski kökü gösteriyorsa, terminalden doğrudan
`uv run defteriki` eski kökü kullanır; MCP girdisindeki `env` bunu yalnız
Cowork'un başlattığı sunucu için geçersiz kılar.

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
    tanim_islemleri.py  tanım yazma ve okuma işlevleri, tanım hata modeli
  finans/         finansal domain; çekirdeği kullanabilir (henüz boş)
alembic.ini       Alembic yapılandırması (veritabanı adresi yok)
alembic/          env.py (yol merkezi ayarlardan), versions/ (0001 boş, 0002 tanım tabloları)
tests/            pytest testleri (test_mimari_sinir.py: çekirdek → finans yasağı ve finansal ad denetimi)
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
