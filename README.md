# DEFTERUC

Kişisel finans kayıt sistemi. Belgeler Cowork tarafından okunur, MCP kapısından
DEFTERUC'e yazılır; uygulama kayıtları tutar, denetler ve gösterir.

## Durum

**Yön değişikliği (2026-09-24, karar: Abdüllatif).** Çekirdek yeniden
tasarlanıyor. Veritabanında **hazır kalıp tablo yoktur**; tablo tasarlama işi
geliştiriciden alınıp uygulama çalışırken kullanılan bir **motora** verilir.

Akış: **Belge → Tablo (= Nesne) → Kayıt.**

1. Cowork belgeyi okur; sistemin henüz tanımadığı bir yapı görürse onu tarif
   eder (özellikleri, değerleri, başka yapılarla bağlantısı).
2. Cowork motoru kullanarak tablo oluşturur, tabloya sütun ekler, sütunun
   özelliklerini belirler. Yeni bir nesne oluşturmak, veritabanında yeni bir
   tablo oluşturmaktır.
3. Kayıt, tabloya satır eklemektir.

Roller:

| Kim | Ne yapar |
|---|---|
| Cowork | Belgeyi okur, ne gerektiğine karar verir, motoru kullanır. |
| Motor | Yalnız araçtır: tablo oluşturur, sütun ekler, sütun özelliği belirler. Hafızası yoktur, bir şey göstermez, mevcut yapıyı okumaz, kural koymaz ve reddetmez; onaylananı yapar. |
| Uygulama | Kullanıcı onayını alır (Cowork değil). |

Onay kuralı: **yapıyı değiştiren her şey kullanıcı onayına bağlıdır** (tablo,
sütun ekleme, sütun özelliği ve ileride gelecek her yapı işlemi). Nesne için
ayrıca onay yoktur (nesne = tablo). Kayıt (satır ekleme) onaysız yazılır.

Mükerrerlik modülü olacak, ama eski haliyle değil; tasarımı ayrıca
konuşulacak.

Bu karar üzerine eski çekirdek (Aşama 4.2–4.7: tanım sistemi, nesne motoru,
belge zinciri tabloları, işlem paketi ve taslak, onay ve mükerrerlik, denetim
izi, kesin kayıt) ile Alembic göç zinciri (`0001`–`0014`) kaldırıldı; hepsi
Git geçmişinde durur (son hâli `e77a222`). Kalanlar:

* uv ile paket iskeleti (`src/defteruc`), merkezi ayarlar (`ayarlar.py`),
  başlangıç akışı (`uv run defteruc`), teknik hata günlüğü (`gunluk.py`)
* Test altyapısı (pytest + Hypothesis) ve tek komutluk kalite kontrolü (Ruff,
  Pyright strict, pytest)
* `.gitignore` / `.gitattributes`; kritik dışlama kuralları testle doğrulanır
* MCP kapısı: `uv run defteruc-mcp`, tek araç `sistem_durumu`
* Veritabanı altyapısı (`cekirdek/veritabani.py`): bağlantı politikası ve
  işlem sınırı; tablo içermez
* Arşiv (`cekirdek/arsiv.py`): gelen dizini sınırı, akışla SHA-256, içerik
  adresli atomik arşiv, bütünlük doğrulama; veritabanına dokunmaz
* Mimari sınır: `cekirdek/` ve `finans/` paketleri, bağımlılık yönünü ve
  çekirdekte finansal ad yasağını koruyan AST testi

* **Birinci motor** (`cekirdek/motor.py`, 2026-09-24): tablo oluşturur, sütun
  ekler. Sütun özelliği ekleme isteğinin içinde gider ve **koda gömülü
  değildir**: istekte ne geldiyse (`Sutun.ozellikler`) sütun adından sonra
  olduğu gibi yazılır, geçerliliğini SQLite belirler. Görünen ad, sütun
  tanımının motor tarafından yönetilen özelliğidir; motor onu tek bir sütun
  tanımları tablosunda (`sutun_tanimlari`: tablo_adi, sutun_adi, gorunen_ad)
  kalıcı saklar, arayüz oradan okur. Tablo/sütun adları sade ve Türkçe
  karaktersizdir (`AD_BICIMI`). Motor yapıyı okumaz, onay almaz (onayı
  uygulama alır, motoru onaydan sonra çağırır); bir iş = bir transaction.

İkinci motor (mevcut sütunun özelliğini değiştirme; SQLite kısıtı gereği
tabloyu yedek alıp yalnız iş anında okuyarak baştan kurar) henüz yok.

Henüz yok: ikinci motor, uygulamanın onay penceresi, motoru Cowork'e açan MCP
araçları, yeni mükerrerlik tasarımı.

## Veritabanı

Aşama 4.1 (2026-09-18). Güvenilir persistence temeli. Hazır uygulama tablosu
yoktur ("Durum"); tablolar çalışma anında motorla, kullanıcı onayıyla oluşur.

**Bağlantı (`src/defteruc/cekirdek/veritabani.py`).** SQLite dosyasının yolu
tek kaynaktan gelir: `Ayarlar.veritabani_yolu`. Çekirdek bu yolu çağırandan
`Path` olarak alır; `defteruc.ayarlar`ı import etmez, çalışma dizinine
bakmaz. Adres metin birleştirilerek değil SQLAlchemy `URL.create` ile üretilir
(`sqlite+pysqlite`, Windows yolu olduğu gibi); göreli yol reddedilir. Engine
modül importunda değil `motor_olustur(yol)` ile açıkça kurulur ve kurulmak
diske dokunmaz; dosya ilk bağlantıda oluşur. Bağlantı politikası tek yerde,
her yeni bağlantıda uygulanır: `PRAGMA foreign_keys=ON` (bağlantı başına
zorunlu) ve `PRAGMA journal_mode=WAL`. `TabloTabani` bütün tabloların ortak
tabanıdır; tek `metadata`, isimli kısıt kalıbı.

**Transaction kontrolü.** Bağlantılar `sqlite3` modülünün Python 3.12+
`autocommit=False` kipiyle açılır (`connect_args`). Eski kipte `sqlite3`
yalnız DML öncesi örtük `BEGIN` açar; `CREATE TABLE` gibi DDL transaction
dışında kalır ve geri alınamaz. Yeni kipte bağlantı ertelenmiş bir transaction ile gelir ve her
`commit`/`rollback` sonrası yenisi başlar; DDL dahil her şey içinde kalır.
PRAGMA'lar transaction içinde çalışmadığından (`journal_mode` değiştirilemez,
`foreign_keys` sessizce yok sayılır) bağlantı olayında `autocommit` geçici
olarak açılır, PRAGMA'lar uygulanır, sonra kapatılır. Motor için önemli
sonuç: yarıda düşen bir yapı değişikliği de tamamen geri alınır.

**İşlem sınırı.** `Veritabani(yol).islem()` bağlam yöneticisi: bir iş = bir
kısa ömürlü oturum = bir transaction. Normal çıkışta `commit`, istisnada
`rollback` ve istisna yeniden yükselir, her durumda oturum kapanır. Model ya
da ileride gelecek depo kodu kendi başına `commit` etmez; sahip bu bağlam
yöneticisidir. `kapat()` havuzu boşaltır (Windows'ta dosya kilidi için).

**Testler** (`tests/test_cekirdek_veritabani.py`): gerçek SQLite dosyalarıyla,
`test` ortamı ve `tmp_path` altında kök; `:memory:` yok. Kanıtlananlar: import
ve engine kurulumu dosya oluşturmaz; adres verilen mutlak yoldan üretilir,
göreli yol reddedilir, çalışma dizini etkisizdir; her bağlantıda
`foreign_keys=1` ve `journal_mode=wal`; bağlantı `autocommit=False`
kipindedir; hatalı dış anahtar yazımı reddedilir; başarılı işlem commit olur,
hata alan işlem tamamen rollback olur; işlem içindeki DDL de geri alınır
(`CREATE TABLE` + hata → tablo yok); test veritabanı ve WAL dosyası yalnız
test kökünde oluşur.

## Arşiv

`src/defteruc/cekirdek/arsiv.py` (Aşama 4.4'ten kalan, 2026-09-24'te korundu).
Cowork dosyayı gelen dizinine bırakır; arşiv dosyayı denetler, akışla
kopyalar, SHA-256 parmak izini ve boyutunu gerçek baytlardan hesaplar,
içerik adresli kalıcı yola (`<ilk iki hex>/<sha256>`) atomik taşır. Aynı
içerik hangi adla gelirse gelsin tek fiziksel dosyadır. Veritabanına dokunmaz;
ayrıntılı kurallar modülün docstring'indedir, testler `tests/test_arsiv.py`.

## Mimari sınır: çekirdek ve finans

Karar (2026-09-18, Abdüllatif). Önceki geliştirme hattında genel mekanik ile
finansal domain birbirine karıştı: para birimi, kuruş, eksen (VARLIK / BORC /
GIDER), yön (ARTTIR / AZALT), HESAP_HAREKETI, bakiye ve ekstre mutabakatı
ortak katmana girdi. Yeniden inşada finans bilgisi yok edilmez; yeri
belirlenir.

* DEFTERUC iki kavramsal katmana ayrılır: genel **çekirdek**
  (`defteruc.cekirdek`) ve finansal **domain** (`defteruc.finans`).
* `finans → çekirdek` bağımlılığına izin vardır: finans çekirdeği kullanabilir.
* `çekirdek → finans` bağımlılığı yasaktır: çekirdek `defteruc.finans`
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

Test (`tests/test_mimari_sinir.py`) `src/defteruc/cekirdek/**/*.py`
dosyalarını Python AST ile okur; `defteruc.finans` bağımlılığı bulursa dosya
ve satırla, dolaylı bağımlılık bulursa modül zinciriyle düşer. Kapsam:

* `import defteruc.finans[.x]` (`as` ile de), `from defteruc.finans[.x]
  import y`, `from defteruc import finans`;
* göreli import: `from .. import finans`, `from ..finans import x`, derin
  paketlerde `...`;
* metin hedefli dinamik import: `importlib.import_module(...)` ve
  `__import__(...)`; hedef ilk konumsal argüman ya da `name=`; `package=` ile
  ya da dosyanın kendi paketine göre çözülen göreli hedef (`".finans"`);
  `import importlib as il` ve `from importlib import import_module as im`
  takma adları;
* fonksiyon gövdesi içindeki importlar;
* dolaylı bağımlılık: çekirdek modülünün `defteruc` içindeki statik import
  grafiği üzerinden (aynı biçimlerle) finansa ulaşması, örneğin çekirdek →
  `defteruc.yardimci` → `defteruc.finans`. Python bir alt modülü yüklerken
  üst paketlerin `__init__.py` dosyalarını da çalıştırdığından bunlar grafiğe
  dahildir: `from defteruc.yardimci.alt import veri` yazan bir çekirdek
  modülü, `alt.py` temiz olsa bile `yardimci/__init__.py` finansı yüklüyorsa
  ihlaldir; başlangıç modülünün kendi üst paketleri de (`defteruc/__init__`,
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
ikinci denetim `src/defteruc/cekirdek/**/*.py` dosyalarını AST ile okur; tanımlayıcıları (değişken, sınıf, fonksiyon,
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

Aşama 4.0'da iki paket de boş açıldı. 2026-09-24'ten beri `cekirdek/`
`veritabani.py` ve `arsiv.py` modüllerini içerir; `finans/` boştur
(`__init__.py` yalnız docstring taşır). Dinamik tablo yönünde finans
paketinin yeri henüz konuşulmadı.

## Bilinen teknik borç

2026-09-19 incelemesinde tespit edildi; kararla ertelendi. Bu bölüm borç
kapanınca silinir.

**1. Eşzamanlı yazma eşlemesi yok.** SQLite iki bağlantı aynı anda yazmaya
kalkınca birini durdurur; bu ham hata (`database is locked` / `busy`) bugün
anlamlı bir hataya çevrilmez. Tek kullanıcılı masaüstünde kabul edilir. Çok
istemci (uygulama açıkken Cowork yazıyor) gündeme gelince motor ve kayıt
yazımı bir yazma sınırı ve yeniden deneme noktasıyla korunur. SQLite'a özgü
SQL veritabanı katmanında kalır.

**2. Uzak kalite kapısı (CI) yok; engel GitHub hesabının kilidi.** Kontrol
(`scripts/kontrol.py`) yalnız bu makinede, commit öncesi kancayla çalışır.
Depoya dışarıdan bakan biri — örneğin bağımsız bir denetçi — testlerin
geçtiğini göremez; kaynağı ve testleri okuyarak denetlemek zorunda kalır.

Eksik olan yapılandırma değil. İş akışı dosyası iki kez yazıldı ve ikisinde de
aynı yerde durdu:

* 2026-09-18, commit `5bfe105` — koşu düştü, aynı gün `7a2b3e8` ile geri alındı;
* 2026-09-20, commit `2c5cdb7` — koşu yine düştü, bu commit'le geri alındı.

GitHub'ın verdiği sebep: *"The job was not started because your account is
locked due to a billing issue."* Yani iş hiç başlamıyor. İki depo da public,
dolayısıyla dakika ücreti söz konusu değil; engel hesap düzeyindeki kilit.
Kilit çözülmeden üçüncü kez denemek anlamsız: çalışmayan bir kontrol, hiç
olmamasından kötüdür — her push'ta kırmızı görünür ve depoya bakan herkese
proje bozukmuş izlenimi verir.

Kilit çözülünce geri koyulacak dosya küçüktür: `windows-latest`,
`actions/setup-python` + `pip install uv`, `uv sync --frozen`, ardından
`uv run python scripts/kontrol.py`. Ürün hedefi Windows masaüstü olduğu için
koşu orada; Linux koşusu gerekirse matrise eklenir. Bu maddeyi kapatan şey
kod değil, ödeme tarafının düzelmesidir.

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
uv run defteruc
```

Komut sırayla ayarları ortam değişkenlerinden yükler, seçilen ortamın
dizinlerini (veritabanı dizini, `belgeler/`, `logs/`) açar, teknik günlüğü
kurar ve başlangıç olayını günlüğe yazar. Başarılıysa tek satırlık bir mesaj
(ortam, veri kökü, günlük dosyası) basar ve `0` ile çıkar. Henüz veritabanı
oluşturmaz; finansal iş yapmaz.

Herhangi bir adım başarısızsa (`DEFTERUC_ORTAM` bilinmeyen değer, test
ortamında veri kökü verilmemiş, dizin yerine dosya var, log dosyası
açılamıyor...) anlaşılır bir hata stderr'e yazılır ve çıkış kodu `1` olur.
Günlük kurulamadıysa başarılı başlangıç mesajı verilmez. Yollar
uygulamanın hangi dizinden başlatıldığına bağlı değildir; modüller import
edildiğinde dizin ya da dosya oluşturulmaz.

## MCP kapısı

Cowork'un DEFTERUC'e ulaştığı tek kapı. stdio taşımasıyla çalışır:

```bash
uv run defteruc-mcp
```

Komut `uv run defteruc` ile aynı hazırlığı yapar (ayarlar, dizinler, günlük),
ardından MCP sunucusunu stdin/stdout üzerinde çalıştırır. İstemci bağlantıyı
kapatınca `0` ile çıkar. Hazırlık düşerse hata stderr'e yazılır, çıkış kodu
`1` olur; stdout'a hiçbir şey yazılmaz.

Bu sürümde tek araç var: `sistem_durumu`. Uygulama sürümü, ortam adı ve
yetenek listesini döndürür; yol, anahtar ya da ortam değişkeni içermez,
veritabanına dokunmaz. Şema sürümü alanı 2026-09-24'te göç zinciriyle
birlikte kaldırıldı. Motorun araçları henüz yoktur. Aşama 3'te kullanılan
geçici deneme araçları (`dosya_dene`, `deneme_baslat`, `deneme_durumu`) kapı
temizliğinde kaldırıldı; ne ölçtükleri "Cowork entegrasyonu" bölümünde.
Gelen dizini ayarı (`DEFTERUC_GELEN_DIZINI`) kaldı: belge Cowork'ün bu dizine
bıraktığı dosyanın yoluyla alınır.

Kurallar:

* stdout yalnız protokolündür. SDK'nın stdio taşıması sunucu çalışırken
  dosya tanımlayıcısı 1'i stderr'e çevirir; DEFTERUC ayrıca hiç `print`
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
| 3.2 | Gerçek Cowork bağlantısı | Bitti (2026-09-15). Ayar: Claude masaüstü `claude_desktop_config.json` → `mcpServers`, komut `uv.exe run --directory <proje dizini> defteruc-mcp`, ortam değişkeni yok, veri `%LOCALAPPDATA%/DEFTERUC/gelistirme`. Ölçüm (`mcp_el_sikisma`): istemci `local-agent-mode-defteruc 1.0.0`; müzakere edilen protokol sürümü **2025-11-25** (sunucunun en yükseği 2026-07-28, istemci daha eskisini seçti); istemci yetenekleri `roots.listChanged=true` ve `io.modelcontextprotocol/ui` uzantısı (`text/html;profile=mcp-app`); sampling ve elicitation bildirilmedi. Uygulama açılışta sunucuyu üç kez başlatıyor: biri 10 ms içinde kapanan yoklama, ikisi kalıcı (Cowork ve Claude Code). Zaman aşımı gözlenmedi: başlatmadan araç yanıtına kadar sorun yok, uygulama kapanınca sunucular EOF ile temiz çıktı. Uygulamanın kendi MCP günlüğü boş; ölçüm sunucu günlüğünden alındı. |
| 3.3 | Dosya erişim denemesi | **Bitti (2026-09-15): dosya yolu yöntemi çalıştı, parça yükleme gerekmez.** Araç `dosya_dene` yazıldı ve testlendi (izinli dosya, boş dosya, alt dizin, dizin dışı, `..`, göreli yol, olmayan dosya, dizin, okuma hatası, stdio üzerinden okuma ve red; simgesel bağlantı testleri Windows'ta bağlantı yetkisi yoksa atlanır). Cowork ayarı: `mcpServers.defteruc.env` → `DEFTERUC_GELEN_DIZINI=<gelen dizini>`; uygulama yeniden başlayınca dizin kendiliğinden oluştu. Deneme ~402 KB'lik gerçek bir hesap özeti PDF'iyle iki senaryoda yapıldı: (a) dosya elle gelen dizinine kopyalandı, Cowork'a yol söylendi → `sonuc=okundu`; (b) PDF Cowork'a yüklendi, gelen dizinine bırakması istendi → Cowork dosyayı dizine yazdı ve `dosya_dene` ile okuttu → `sonuc=okundu`. İki dosyanın SHA-256 özeti birebir aynı; Cowork dosyayı bozmadan aktarıyor. Günlükte iki `mcp_dosya_deneme` satırı, red ya da hata yok. Aşama 4 belge alımı bu yöntemle kurulacak: Cowork dosyayı gelen dizinine bırakır, yolu MCP aracına verir. |
| 3.4 | Çok adımlı protokol denemesi | **Bitti (2026-09-16): Cowork BEKLIYOR döngüsünü kendi başına, sadakatle yürüttü.** Araç çifti `deneme_baslat` / `deneme_durumu` yazıldı ve testlendi (süreç içi sahte saatle bekle→tamamla geçişi, aynı anahtar aynı kimlik, boş anahtar reddi, bilinmeyen kimlik, yanıt ve günlükte anahtar yok; stdio üzerinden başlat→durum→bilinmeyen→tekrar başlat döngüsü). Cowork'a tek cümle verildi: "bir deneme işi başlat; bekliyor dönerse aynı anahtarla durumu sor, tamamlanınca bildir." Günlük (`mcp_deneme`): `deneme_baslat` → BEKLIYOR, talep kimliği verildi; `deneme_durumu` üç kez soruldu: 3,1 s (BEKLIYOR), 17,4 s (BEKLIYOR), 42,5 s (TAMAMLANDI). Sorgu aralıkları yaklaşık 3 s, 14 s, 25 s; Cowork bekleme süresini kendi uzattı, vazgeçmedi, kimliği doğru taşıdı, anahtarı değiştirmedi, aynı işi yeniden başlatmadı. Hiçbir çağrı açık kalmadı; durum sorguları anında döndü. Dört çağrı da aynı sunucu sürecinden (`surec` eşit) geldi: Claude masaüstü sunucuyu yine iki kalıcı süreç olarak başlattı ama tek sohbetin bütün çağrıları tek sürece gitti; BILINMIYOR görülmedi. Aşama 5 için çıkarım: BEKLIYOR + talep kimliği + istemcinin tekrar sorması çalışan bir yöntem; talep durumu yine de belleğe değil veritabanına yazılır, çünkü sohbetler ve uygulama yeniden başlatmaları arası süreç garantisi yok. |

## Teknik hata günlüğü

Günlük yalnızca ayarlardaki log dizinine yazar: `<log dizini>/defteruc.log`
(varsayılan `<veri kökü>/<ortam>/logs/defteruc.log`). Standart kütüphanenin
`logging` modülü kullanılır; ek bağımlılık yoktur.

Her satır `zaman | seviye | olay | mesaj` biçimindedir; olay türleri
şimdilik `baslangic`, `baslangic_hatasi`, `mcp_baslangic`, `mcp_el_sikisma`,
`mcp_kapanis`, `mcp_hatasi`. Dosya günlüğüne bağlanan dış kütüphane
kayıtlarında olay `-` olur.

Saklama sınırı: dosya 1.000.000 baytı aşınca döndürülür, en fazla 5 eski
dosya (`defteruc.log.1` ... `.5`) tutulur; toplam en çok ~6 MB. Kurulum
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

**Uzak kalite kapısı (CI) yoktur** ve bunun sebebi yapılandırma değildir; bkz.
"Bilinen teknik borç", madde 3. Kontrol yalnız bu makinede, commit öncesinde
çalışır; depoya dışarıdan bakan biri testlerin geçtiğini göremez, kaynağı
okuyarak denetlemek zorundadır.

## Ayarlar

Bütün yollar `defteruc.ayarlar` modülünden gelir; uygulamanın nereden
başlatıldığı yolları değiştirmez.

```python
from defteruc.ayarlar import ayarlari_yukle, dizinleri_hazirla

ayarlar = ayarlari_yukle()  # ortam değişkenlerini okur, diske yazmaz
dizinleri_hazirla(ayarlar)  # gerekli dizinleri açar, dosya oluşturmaz
```

Ortam değişkenleri (öncelik yukarıdan aşağıya):

| Değişken | Anlamı |
|---|---|
| `DEFTERUC_VERITABANI_YOLU` | Veritabanı dosyası; türetilmiş yolun yerine geçer |
| `DEFTERUC_BELGE_DIZINI` | Belge arşivi dizini; türetilmiş yolun yerine geçer |
| `DEFTERUC_LOG_DIZINI` | Log dizini; türetilmiş yolun yerine geçer |
| `DEFTERUC_GELEN_DIZINI` | Gelen dizini: Cowork'un dosya bıraktığı, MCP araçlarının okumaya izinli olduğu tek dizin; türetilmiş yolun yerine geçer |
| `DEFTERUC_VERI_KOKU` | Ortamların ortak üst dizini; ortam adı altına eklenir |
| `DEFTERUC_ORTAM` | `gelistirme` (varsayılan), `test`, `gercek` |

Varsayılan veri kökü Windows'ta `%LOCALAPPDATA%\DEFTERUC\<ortam>`, Linux'ta
`$XDG_DATA_HOME/DEFTERUC/<ortam>` (yoksa `~/.local/share/...`), macOS'ta
`~/Library/Application Support/DEFTERUC/<ortam>`. Bu kökten
`defteruc.sqlite3`, `belgeler/`, `logs/` ve `gelen/` türetilir.

Kurallar:

* Yollar mutlak olmalı; boş veya göreli değer hata verir.
* Bilinmeyen ortam adı hata verir.
* `test` ortamı `DEFTERUC_VERI_KOKU` ister ve tekil yolların bu kökün dışına
  çıkmasına izin vermez. Sınır yolun yazılı biçimine değil fiziksel
  karşılığına bakar (2026-09-18, `Path.resolve`): kök içindeki bir simgesel
  bağlantı ya da junction dışarıyı gösteriyorsa yol reddedilir ve hiçbir dizin
  oluşturulmaz; hata mesajı fiziksel karşılığı da söyler. Kabul edilen yol
  verildiği biçimde saklanır. Bu sınır yalnız `test` ortamınındır; geliştirme
  ve gerçek ortamların yol politikası değişmedi. Testler: normal yol, `..` ile
  kaçış, simgesel bağlantıyla kaçış (Windows'ta yetki yoksa atlanır), junction
  ile kaçış (yalnız Windows), kök içini gösteren bağlantı.
* Tekil yol değişkenleri diğer ortamlarda ortam ayrımını geçersiz kılabilir.

### Yerel kurulum

Proje ve yerel verisi tek üst klasörde durur:

```
C:\dev\Defter\
  DefterUc\   proje (bu depo)
  veri\       veri kökü: veritabanı, belge arşivi, günlükler
  gelen\      gelen dizini: Cowork'ün okuyacağı belgeler
```

Claude masaüstü `claude_desktop_config.json` içindeki `mcpServers.defteruc`
girdisi sunucuyu (`uv run --directory C:\dev\Defter\DefterUc defteruc-mcp`)
şu ortam değişkenleriyle çalıştırır; kullanıcı düzeyi ortam değişkenleri de
aynı değerleri taşır, böylece terminal ve Cowork aynı kökü kullanır:

| Değişken | Değer |
|---|---|
| `DEFTERUC_VERI_KOKU` | `C:\dev\Defter\veri` |
| `DEFTERUC_GELEN_DIZINI` | `C:\dev\Defter\gelen` |

Türetilen yollar: `C:\dev\Defter\veri\gelistirme\defteruc.sqlite3`,
`...\belgeler`, `...\logs`. Bu kurulum Git'e girmez; yalnız bu makinede
geçerlidir.

## Dizin düzeni

```
src/defteruc/    uygulama paketi
  ayarlar.py      merkezi ayarlar (ortam, yollar)
  baslangic.py    uv run defteruc giriş noktası; ortak hazırlık (ortami_hazirla)
  gunluk.py       teknik hata günlüğü
  mcp_kapisi.py   uv run defteruc-mcp; MCP sunucusu ve araçları
  cekirdek/       genel çekirdek; finansı tanımaz
    veritabani.py   SQLite bağlantı politikası, TabloTabani, işlem sınırı
    arsiv.py        gelen dizini sınırı, akışla SHA-256, içerik adresli atomik arşiv, bütünlük
  finans/         finansal domain; çekirdeği kullanabilir (boş)
tests/            pytest testleri (test_mimari_sinir.py: çekirdek → finans yasağı ve finansal ad denetimi; test_arsiv.py: arşiv)
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
* Pydantic 2.x — MCP giriş/çıkış ve veri doğrulama
* MCP Python SDK 2.x (`mcp`, `MCPServer`) — Cowork ↔ DEFTERUC kapısı
* PySide6 — masaüstü GUI için
* pytest — test
* Hypothesis — property-based test
* Ruff — lint + format
* Pyright strict — statik type checking
* pre-commit — commit öncesi kalite kontrolleri
* Git — sürüm kontrolü
* `.gitignore` — DB, WAL/SHM, kişisel veri, cache, secret vb. dışlama
* `.gitattributes` — LF/CRLF standardizasyonu
