# DEFTERUC — Kavramlar Sözlüğü

## Amaç

Bu sözlük, DEFTERUC projesinde geçen kavramların tek ve ortak tanımını tutar. Aynı kavramı proje sahibi (Abdüllatif), kodu yazan ajan (Claude Code) ve Cowork'un aynı anlamda kullanmasını sağlamak için vardır. Bir kavram burada nasıl tanımlandıysa kodda, dokümanlarda ve sohbetlerde o anlamda kullanılır; farklı bir anlam gerekiyorsa önce bu sözlük güncellenir.

**Kural:** Sözlüğe kavram ekleme, mevcut bir tanımı değiştirme veya silme yalnızca Abdüllatif'in onayıyla yapılır. Ajanlar (Claude Code, Cowork) onaysız ekleme yapamaz.

## Kavramlar

### Nesne

Dış dünyadaki bir varlığın yapılandırılarak DEFTERUC'e kaydedilmesiyle nesne olur. Yapılandırmaya uğramayan şeyler nesne değildir; belgenin kendisi (PDF, fotoğraf) nesne değildir. Finansal hareketler nesne değildir; bire bir işlenir ve nesnelere bağlı, kendi işlem kurallarıyla tutulan kayıtlardır.

Her nesnenin benzersiz kimliği ve Cowork'un belirlediği serbest özellikleri vardır. Nesneler seviyeli bir hiyerarşide durur: seviye 0 hiçbir üst nesneye bağlı değildir; diğer nesneler hemen önceki seviyedeki en az bir nesneye bağlıdır; seviye atlanamaz; bir nesne birden fazla üst nesneye bağlanabilir. Sistem nesnenin banka, hesap ya da fiş olduğunu yorumlamaz; bağlantıları ve seviye kurallarını denetler.

_(Abdüllatif'in onayıyla eklendi, 2026-09-11.)_

### Mükerrerlik protokolü

DEFTERUC'te aynı varlığı temsil etme ihtimali bulunan nesneleri tespit etmek, ilgili faaliyetleri durdurmak ve mükerrerliği çözmek için uygulanan kurallar bütünüdür.

1. **Şartın belirlenmesi:** Yeni nesne açılışında kullanıcı, nesnenin özelliklerinden birini veya birkaçını mükerrerlik şartı olarak seçer. Seçim o nesnede kalıcı olarak saklanır. Şart seçilmeyen nesne de olabilir; o nesne için protokol işletilmez. Üst nesnenin mükerrerliği yine altına eklenen nesnenin şartıyla ortaya çıkabilir.
2. **Şüphenin oluşması:** Seçilen özelliklerden herhangi birinin başka bir nesnenin karşılık gelen alanındaki değerle birebir eşleşmesi protokolü başlatır. Birden fazla özellik seçilmişse VEYA mantığı uygulanır. Eşleşme, tek başına kesin mükerrerlik kararı değildir.
3. **Faaliyetlerin durdurulması:** Eşleşen eski ve yeni nesne üzerindeki işlemler durdurulur; bağlı hiyerarşiler denetime alınır. Şüphe çözülene kadar AI yeni nesne tanımlayamaz. Şüphe kapsamı dışındaki mevcut nesnelerde işlem yapabilir. Defter, eşleşmenin nedenini AI'a bildirir.
4. **AI'ın mükerrerlik kararı:** AI nesnelerin mükerrer olduğuna karar verirse düzeltme otomatik uygulanır. İlk oluşturulan nesne korunur. Sonradan oluşturulan nesnenin bütün işlem kayıtları ve nesne bağlantıları ilk nesneye aktarılır; ardından mükerrer nesne silinir. İşlem kaydı bulunmasa da mevcut bağlantılar korunur. Aktarım ve silme, kopukluk veya kısmi sonuç bırakmadan bir bütün olarak gerçekleştirilir. Aktarılan bir nesne korunan nesnenin altındaki bir nesneyle eşleşirse protokol o nesne için yeniden başlar; süreç hiyerarşi boyunca aynı kurallarla iner.
5. **Kullanıcı kararı:** AI mükerrer olmadığını düşünürse veya karar veremezse Defter durumu ve gerekçeyi uygulama üzerinden kullanıcıya sunar. Kullanıcı onayı olmadan ilgili engeller kaldırılmaz.
6. **Sonuçlandırma:** Kararlar, gerekçeler ve yapılan düzeltmeler kaydedilir ve uygulamada gösterilir. Şüphe çözüldüğünde ilgili engeller kaldırılır. Mükerrerlik giderilmişse AI işlemlerine korunan nesne üzerinden devam eder.

_(Abdüllatif'in onayıyla eklendi, 2026-09-11.)_

### Yazmak (write) ve kayıt etmek (save)

Yazmak ve kayıt etmek farklı şeylerdir; DEFTERUC'te ayrı tutulur. İşlemleri deftere yazmak kayıt etmek değildir; kayıt etmek ayrı bir adımdır ve belge kaydının tanımlanmasıyla olur. İleriki sürümlerde bir ajan yazıp bir ajan kontrol edebilir; yazan ajan kontrol ajanının onayıyla kaydeder (ihtimal, karar değil).

_(Abdüllatif'in onayıyla eklendi, 2026-09-11.)_

### İşlemin yarım kalması

İşlemin yarım kalması, kaydedilememesidir. İşlemleri deftere yazmak kayıt etmek değildir; kayıt etmek ayrı bir şeydir (bkz. Yazmak ve kayıt etmek). Şüpheli işlemler bekletilirken belgedeki diğer işlemler deftere yazılır; şüphe giderildikten sonra belge kaydı tanımlanır. Belge kaydının geçersiz olduğuna karar verilirse (belge yanlışsa) o belgenin bütün işlemleri geri alınır, doğru belge işlenir.

_(Abdüllatif'in onayıyla eklendi, 2026-09-11.)_
