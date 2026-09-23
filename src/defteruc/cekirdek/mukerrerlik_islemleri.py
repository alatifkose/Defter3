"""Mükerrerlik protokolü ve kullanıcı karar talebi servisleri (Aşama 4.6).

**Mükerrerlik bir benzersizlik kısıtı değildir.** Eşleşme "bunlar kesinlikle
aynı nesnedir" demek değildir; yalnız kalıcı bir **şüphe** ve ona bağlı bir
**kullanıcı karar talebi** doğurur. Otomatik birleştirme yoktur. Çekirdek
burada da domain bilmez: şart olarak seçilen özelliklerin anlamını, hangi
türün ne olduğunu bilmez; yalnız ``ozellik_tanimi`` kimliklerini ve
``deger_kodlama`` ile üretilmiş kanonik metinleri **birebir** karşılaştırır.
Küçük harfe indirme, boşluk kırpma, yaklaşık eşleşme, regex, güven puanı ya da
ad tahmini yoktur; tanım verisinde böyle bir kural yoksa çekirdek değeri kendi
kafasına göre değiştirmez.

**Şart seçimi.** Kullanıcı bir kesin nesne ya da aday nesne için sıfır, bir ya
da birden fazla özelliği mükerrerlik şartı seçer (``nesne_sarti_ekle`` /
``aday_sarti_ekle``; seçim eklenir, geri alma işlevi yoktur). Birden fazla
şart **VEYA** mantığındadır: herhangi biri eşleşirse şüphe doğar. Seçilmemiş
bir özelliğin eşitliği şüphe üretmez. Başka türün özelliği şart seçilemez
(servis ve bileşik dış anahtar). Şart yalnız **kanonik** kesin nesneye
seçilir (``NesneBirlesmis``); aday şartı aday veridir ve yalnız ``calisiyor``
pakette seçilir (``taslak_islemleri.yazilabilir_paket``).

**İki yönlü tarama.** Karşılaştırma tek yönlü değildir: taranan ucun kendi
şartları karşı ucun aynı özelliğindeki değerle, karşı ucun şartları da taranan
ucun değeriyle karşılaştırılır. Böylece şart seçmemiş yeni bir nesne, şart
seçmiş mevcut bir nesnenin korumasından kaçamaz. Hiçbir uçta şart yoksa
karşılaştırma yapılmaz. Karşılaştırma aynı nesne türü içindedir: özellik
tanımı bir türe aittir, dolayısıyla farklı türler eşleşmez.

**Şüphe → talep → BEKLIYOR.** Şüphe ``KararTalebi`` satırı olarak kalıcı
yazılır; satırın kimliği Aşama 3.4'te doğrulanan ``BEKLIYOR + talep kimliği``
protokolündeki kalıcı kimliktir. Paket, açık talebi varken ``BEKLIYOR``
olur; bütün açık talepleri çözülünce ``CALISIYOR``a döner (ilk karar tek
başına paketi canlandırmaz). Bir talep ``KararTalebiPaketi`` üzerinden birden
fazla paketi bekletebilir. ``IPTAL`` terminaldir: paket diriltilmez; açık
talep ancak onu bekleyen başka etkin paket kalmadığında ``GECERSIZ`` olur
(``taslak_islemleri.paketi_iptal_et``). Ortak soruya kalan paket adına karar
verilebilir; açılış paketi tarihsel bilgi olarak değişmez.
``GECERSIZ`` bir ``AYRI`` kararı değildir — ``karar`` boş kalır, satır
geçmişte durur — ama açık talep sayılmaz: aynı çift başka bir pakette yeniden
değerlendirilebilir, yoksa iptal edilen bir paket o çifti sonsuza kadar
kilitlerdi. Aynı durum ikinci bir nedenle daha kullanılır: bir birleşmeden
sonra uçları kanonik olmaktan çıkan açık kesin çift talepleri de hükümsüz
kalır ve soru kanonik uçlarla yeniden sorulur (bkz. "Kanonik kimlik ve
tarihsel kimlik"). Bekleyen karar yalnız ilgili paketi ve şüpheli ucu
durdurur; sistem genelinde kilit yoktur.

**Kararı yalnız kullanıcı verir.** ``karar_ver`` aktörü ``KULLANICI``
olmayan çağrıyı ``KararKaynagiGecersiz`` ile reddeder ve hiçbir şey yazmaz;
veritabanında da ``karar_aktor_turu`` yalnız ``kullanici`` olabilir. Ajan ve
sistem tarama yapar, şüphe açar, denetim olayı üretir; kullanıcı yerine karar
veremez. Güvenli otomatik karar motoru (Aşama 4.9) henüz yoktur.

**Karar.** ``AYRI`` şüpheyi kapatır ve bu karar kimlikler sonraki
birleşmelerle değişse de korunur. ``AYNI`` çözümlemeyi / birleştirmeyi
uygular. ``karar_ver``in bütün yazmaları **tek bir dış SAVEPOINT**
içindedir: bir adım düşerse çağrının hiçbir değişikliği kalmaz, çağıran
hatayı yakalayıp dış transaction'ı commit etse bile. ``KARARSIZ`` şüpheyi
çözmez: talep açık kalır,
paket ``BEKLIYOR`` kalır, karar yalnız denetim izine yazılır. Aynı talebe
ikinci kez karar uygulanmaz: kapatma koşullu güncellemedir (``UPDATE ...
WHERE durum = 'acik'``), iki bağlantı aynı anda cevaplarsa yalnız biri
kazanır, diğeri ``KararTalebiKapali`` alır.

**Aday → mevcut nesne çözümlemesi.** ``AYNI`` kararında aday nesne kesin
tabloya taşınmaz; ``AdayNesneCozumlemesi`` satırı "bu aday şu kesin nesne
olarak çözüldü" bilgisini kalıcı ve ilişkisel tutar. Aşama 4.8 paketi
kesinleştirirken bunu tahmin etmez, buradan okur. Adayın özellikleri, aday
ilişkileri ve aday kayıt bağları olduğu gibi korunur (provenance bozulmaz);
onları kesin dünyaya yazmak 4.8'in işidir. ``AYRI`` kararında aday aday
kalır ve 4.8'de yeni kesin nesneye dönüşebilir. Bir aday **birden fazla**
kesin nesneyle eşleşebilir; ikisine de ``AYNI`` denirse aday için ikinci
çözümleme satırı yazılmaz, mantıksal sonuç (``X = Y``) iki kesin nesnenin
birleştirilmesi olarak uygulanır. O çift için daha önce ``AYRI`` denmişse
çelişki sessizce çözülmez: ``KararCelismesi`` yükselir, işlem geri alınır,
talep açık kalır.

**İki kesin nesnenin birleştirilmesi.** Hedef korunur (çift her zaman
``kaynak > hedef`` sırasına normalleştirilir: önce oluşturulan korunur).
İlişkiler ``nesne_islemleri.iliskileri_devret`` ile taşınır; ikinci bir
ilişki motoru yoktur, bütün 4.3 doğrulamaları (tür, sürüm, mükerrer ilişki,
üst yaşam durumu, en çok / en az üst, çevrim) çalışır ve ihlalde **her şey**
geri alınır. Kaynağın şartları hedefe **kopyalanır** (kaynaktan silinmez).
Kaynak silinmez: yaşam durumu ``kapali`` olur ve ``NesneBirlesimi`` satırı onu
kalıcı olarak hedefe bağlar; geçmiş kaybolmaz. Kaynağın özellik değerleri
kaynakta kalır — hangi değerin doğru güncel değer olduğu bir domain yorumudur,
çekirdek karar vermez.

**Kanonik kimlik ve tarihsel kimlik.** Bir gerçek nesnenin sistemdeki karşılığı
tek bir **kanonik** kesin nesnedir; ``kanonik_nesneyi_bul`` onu **tek
sıçramada** verir, ``adayin_kesin_nesnesi`` aynı şeyi aday için yapar. Buna iki
kural hizmet eder:

* *Geçmiş ``AYRI`` kararı aşılmaz.* Birleşmeden önce iki kanonik kümenin
  bütün üyeleri (önceki birleşmelerle katılanlar dahil) karşılaştırılır;
  herhangi iki üye arasında kullanıcının verdiği bir ``AYRI`` varsa birleşme
  ``KararCelismesi`` ile reddedilir ve hiçbir kalıcı değişiklik kalmaz. Eski
  karar silinmez, değiştirilmez; çelişkiyi çekirdek çözmez. Çözümlenmiş
  adayların AYRI kararları da iki kümenin karşılaştırmasına katılır; adayın
  ilk çözümlemesi ayrıca kendi tarihsel AYRI kararlarıyla denetlenir.
* *Bayat talep kalmaz.* Birleşen nesneyi gösteren açık kesin çift talepleri
  terminal ``GECERSIZ`` olur ve soru, hâlâ geçerliyse, aynı işlem içinde
  zincirleme denetimle kanonik uçlarla yeniden açılır: ne kalıcı bekleme, ne
  mükerrer karar, ne benzersizlik ihlali. İki ucu aynı kanonik nesneye düşen
  talep yeniden sorulmaz. Eski talebin bütün etkin paket bağları yeni tek
  soruya taşınır. Aday zaten talebin kanonik hedefine çözümlüyse aday talebi
  de GECERSIZ olur; kullanıcı adına yeni karar üretilmez.
* *Birleşim zinciri kurulmaz.* ``nesne_birlesimi.hedef_nesne_id`` kullanıcının
  o günkü kararıdır ve değişmez; ``kanonik_nesne_id`` ise bugünkü kanonik
  nesnedir. Hedef sonradan başka bir nesneye birleşirse eski satırların
  ``kanonik_nesne_id``si yeni kanonik nesneye bağlanır (denetim izine
  ``birlesim_yeniden_baglandi``). Hiçbir satır birleşmiş bir nesneyi kanonik
  göstermez; karar geçmişi ve ``karar_talebi_id`` bağları kaybolmaz.
* *Tarihsel kimlik düşmez.* Mükerrerlik taraması kanonik nesnenin değerleri
  olarak ona birleşmiş kaynakların değerlerini de sayar; birleşmiş bir nesne
  eşleşme sonucunda kendi başına görünmez, kanonik nesnesine eşlenir ve karar
  talebi kanonik nesneyi gösterir. Kaynağın değerleri hedefin özelliği
  **yapılmaz**: aynı özellikte iki farklı değer varsa hangisinin doğru olduğu
  bir domain yorumudur. Normal özellik okuması (``nesne_islemleri``) bundan
  etkilenmez; geçmiş yalnız mükerrerlik motorunda kullanılır.

**Zincirleme mükerrerlik.** Birleşimden sonra hedefin altındaki çocuklar
yeniden denetlenir; yeni eşleşme yeni talep açar ve paket bütün talepler
çözülene kadar ``BEKLIYOR`` kalır. Döngü olamaz: aynı çift için ikinci talep
açılmaz (açık talep kısmi benzersiz indeksle, çözülmüş talep servis
denetimiyle engellenir; "ayrı" kararı verilmiş çift aynı kanıtla yeniden
durdurulmaz). ``gecersiz`` talep bu denetimde sayılmaz. Burada doğan sorular
kararın verildiği sorunun **bağımsız kökenini devralır**: paketten bağımsız
bir sorunun çocuğu da paket iptaliyle cevapsız kapanmaz
(``_zincirleme_denetle``).

**İşlem sınırı ve eşzamanlılık.** Her servis açık bir ``Session`` alır;
çağıran ``Veritabani.islem`` transaction'ının sahibidir, burada ``commit`` ya
da dış ``rollback`` yoktur. Her yazma kendi SAVEPOINT'inde çalışır ve dar hata
eşlemesinden geçer (``_yazma_siniri``): kilit / anlık görüntü çakışması
``MukerrerlikYazmaCakismasi``, aynı çift için eşzamanlı ikinci açık talep
``SupheZatenAcik``; başka veritabanı hataları olduğu gibi yükselir. Yeniden
deneme çağıranındır, serviste retry döngüsü yoktur.

**Kapsam dışı (bilinçli).** Güvenli karar motoru, güven puanı, LLM değeri ya
da gizli sezgisel kural yoktur; karar kaynağı yalnız kullanıcıdır (Aşama 4.9
yeni bir karar kaynağı ekleyebilir). İki aday nesnenin birbiriyle mükerrerliği
bu aşamada aranmaz (paket içi çözüm 4.8'in işidir). Kesin kayıt (4.7) ve
kesinleştirme (4.8) burada yoktur.
"""

from __future__ import annotations

from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field

from sqlalchemy import Select, and_, func, or_, select, tuple_, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from defteruc.cekirdek.denetim_islemleri import AZAMI_GEREKCE_UZUNLUGU, olay_yaz
from defteruc.cekirdek.denetim_tablolari import Aktor, AktorTuru, DenetimOlayi
from defteruc.cekirdek.kayit_islemleri import kayit_baglarini_devret
from defteruc.cekirdek.mukerrerlik_tablolari import (
    KARAR_TALEBI,
    NESNE_BIRLESIMI,
    AdayNesneCozumlemesi,
    AdayNesneMukerrerlikSarti,
    Karar,
    KararTalebi,
    KararTalebiPaketi,
    NesneBirlesimi,
    NesneMukerrerlikSarti,
    TalepDurumu,
)
from defteruc.cekirdek.nesne_islemleri import (
    DevirOzeti,
    iliskileri_devret,
    nesne_getir,
    yasam_durumunu_degistir,
)
from defteruc.cekirdek.nesne_tablolari import Nesne, NesneIliskisi, NesneOzelligi
from defteruc.cekirdek.tanim_tablolari import (
    HiyerarsiKurali,
    OzellikTanimi,
    YasamDurumu,
    simdi_utc,
)
from defteruc.cekirdek.taslak_islemleri import (
    PaketDurumuGecersiz,
    aday_nesne_getir,
    benzersizlik_ihlali_mi,
    kilit_cakismasi_mi,
    paket_getir,
    paketi_beklet,
    paketi_devam_et,
    yazilabilir_paket,
)
from defteruc.cekirdek.taslak_tablolari import (
    AdayNesne,
    AdayNesneOzelligi,
    IslemPaketi,
    PaketDurumu,
)


class MukerrerlikHatasi(Exception):
    """Mükerrerlik ve karar talebi servis hatalarının ortak tabanı."""


class KararTalebiBulunamadi(MukerrerlikHatasi, LookupError):
    """Verilen kimlikle karar talebi yok."""


class KararTalebiKapali(MukerrerlikHatasi):
    """Talep zaten çözülmüş; ikinci karar uygulanmaz (eşzamanlı yarış dahil)."""


class GecersizSart(MukerrerlikHatasi, ValueError):
    """Nesnenin türünde böyle özellik yok ya da şart listesi geçersiz."""


class NesneBirlesmis(MukerrerlikHatasi):
    """Nesne başka bir nesneye birleşmiş; şart yalnız kanonik nesneye seçilir."""


class SartKaynagiGecersiz(MukerrerlikHatasi):
    """Mükerrerlik şartını kullanıcı dışında bir aktör seçmeye çalıştı."""


class BirlestirmeGecersiz(MukerrerlikHatasi, ValueError):
    """Birleştirme bu uçlar için uygulanamaz."""


class SupheZatenAcik(MukerrerlikHatasi):
    """Aynı çift için açık bir karar talebi zaten var (eşzamanlı açma dahil)."""


class MukerrerlikYazmaCakismasi(MukerrerlikHatasi):
    """Eşzamanlı yazma çatışması; işlemi geri alıp yeni işlemde yeniden deneyin."""


class KararKaynagiGecersiz(MukerrerlikHatasi):
    """Mükerrerlik kararını kullanıcı dışında bir aktör vermeye çalıştı."""


class KararCelismesi(MukerrerlikHatasi):
    """Karar, kullanıcının daha önce verdiği bir kararla çelişiyor; çelişkiyi
    çekirdek kendi başına çözmez."""


@dataclass(frozen=True, slots=True)
class KararSonucu:
    """``karar_ver`` sonucunun tamamı."""

    talep: KararTalebi
    cozuldu: bool
    """``KARARSIZ`` kararında ``False``: talep açık kalır."""
    paket_durumu: PaketDurumu | None
    cozumleme: AdayNesneCozumlemesi | None = None
    birlesim: NesneBirlesimi | None = None
    devir: DevirOzeti | None = None
    yeni_talepler: tuple[KararTalebi, ...] = field(default_factory=tuple)
    """Zincirleme denetimin açtığı veya kanonik uzlaştırmanın bağladığı talepler."""
    gecersiz_kalan_talepler: tuple[KararTalebi, ...] = field(default_factory=tuple)
    """Birleşme yüzünden uçları kanonik olmaktan çıktığı için hükümsüz kalan
    açık talepler; karar taşımazlar, geçmişte dururlar."""


@dataclass(frozen=True, slots=True)
class _TaramaSonucu:
    """``_nesneyi_tara`` çıktısı: bu çağrının açtığı ve dokunduğu açık talepler.

    ``dokunulan`` zaten açık olan, bu taramanın yeniden sorduğu talepleri
    taşır. Köken devri ikisini birden kapsar (2026-09-20 altıncı tur): soruyu
    bu tarama açmış olmasa da, bağımsız bir kararın yeniden sorduğu soru artık
    yalnız bir paket tarafından ayakta tutulmuyordur.
    """

    acilan: tuple[KararTalebi, ...]
    dokunulan: tuple[KararTalebi, ...]


@dataclass(frozen=True, slots=True)
class _Birlestirme:
    """``_nesneleri_birlestir`` çıktısı."""

    birlesim: NesneBirlesimi
    devir: DevirOzeti
    gecersiz_talepler: tuple[KararTalebi, ...]


# --- yazma sınırı ---------------------------------------------------------------------


@contextmanager
def _yazma_siniri(
    oturum: Session,
    tablo: str | None = None,
    benzersizlik_hatasi: type[MukerrerlikHatasi] = SupheZatenAcik,
    benzersizlik_mesaji: str = "",
) -> Generator[None, None, None]:
    """SAVEPOINT + dar hata eşlemesi (4.5 kalıbı)."""
    try:
        with oturum.begin_nested():
            yield
    except IntegrityError as hata:
        if tablo is not None and benzersizlik_ihlali_mi(hata, tablo):
            raise benzersizlik_hatasi(benzersizlik_mesaji) from None
        raise
    except OperationalError as hata:
        if kilit_cakismasi_mi(hata):
            raise MukerrerlikYazmaCakismasi(
                "eşzamanlı yazma çatışması: başka bir bağlantı aynı anda yazdı; "
                "işlemi geri alıp yeni işlemde yeniden deneyin."
            ) from None
        raise


# --- getirme --------------------------------------------------------------------------


def karar_talebi_getir(oturum: Session, karar_talebi_id: int) -> KararTalebi:
    talep = oturum.get(KararTalebi, karar_talebi_id)
    if talep is None:
        raise KararTalebiBulunamadi(
            f"karar talebi bulunamadı: kimlik {karar_talebi_id}"
        )
    return talep


def talepleri_listele(
    oturum: Session,
    *,
    islem_paketi_id: int | None = None,
    durum: TalepDurumu | None = None,
) -> list[KararTalebi]:
    """Karar talepleri, kimlik sırasıyla (deterministik)."""
    sorgu = select(KararTalebi).order_by(KararTalebi.id)
    if islem_paketi_id is not None:
        sorgu = sorgu.where(
            or_(
                KararTalebi.islem_paketi_id == islem_paketi_id,
                KararTalebi.id.in_(
                    select(KararTalebiPaketi.karar_talebi_id).where(
                        KararTalebiPaketi.islem_paketi_id == islem_paketi_id
                    )
                ),
            )
        )
    if durum is not None:
        sorgu = sorgu.where(KararTalebi.durum == TalepDurumu(durum).value)
    return list(oturum.execute(sorgu).scalars())


def aday_cozumlemesi_bul(
    oturum: Session, aday_nesne_id: int
) -> AdayNesneCozumlemesi | None:
    """Adayın çözümlendiği kesin nesne kaydı; yoksa ``None`` (4.8 buradan okur)."""
    return oturum.execute(
        select(AdayNesneCozumlemesi).where(
            AdayNesneCozumlemesi.aday_nesne_id == aday_nesne_id
        )
    ).scalar_one_or_none()


def nesne_birlesimini_bul(oturum: Session, nesne_id: int) -> NesneBirlesimi | None:
    """Nesne başka bir nesneye birleştirildiyse birleşim kaydı; yoksa ``None``."""
    return oturum.execute(
        select(NesneBirlesimi).where(NesneBirlesimi.kaynak_nesne_id == nesne_id)
    ).scalar_one_or_none()


def kanonik_nesneyi_bul(oturum: Session, nesne_id: int) -> int:
    """Nesnenin bugünkü kanonik karşılığı; birleşmemişse kendisi.

    **Tek sıçrama yeter**: ``nesne_birlesimi.kanonik_nesne_id`` hiçbir zaman
    kendisi birleşmiş bir nesneyi göstermez (birleşim zinciri kurulmaz, eski
    satırlar yeni kanonik nesneye bağlanır), dolayısıyla burada döngü ya da
    ardışık arama yoktur.
    """
    birlesim = nesne_birlesimini_bul(oturum, nesne_id)
    return nesne_id if birlesim is None else birlesim.kanonik_nesne_id


def adayin_kesin_nesnesi(oturum: Session, aday_nesne_id: int) -> int | None:
    """Adayın çözümlendiği **güncel** kesin nesne; çözümlenmemişse ``None``.

    Çözümleme satırı kararın verildiği andaki nesneyi saklar ve değişmez; o
    nesne sonradan birleşmiş olabilir. Aşama 4.8 hedefi tahmin etmesin diye
    kanonik karşılık burada tek adımda verilir.
    """
    cozumleme = aday_cozumlemesi_bul(oturum, aday_nesne_id)
    if cozumleme is None:
        return None
    return kanonik_nesneyi_bul(oturum, cozumleme.nesne_id)


def _kanonik_esleme(oturum: Session, nesne_idleri: set[int]) -> dict[int, int]:
    """Verilen nesnelerin kanonik karşılıkları (tek sorgu, tek sıçrama)."""
    if not nesne_idleri:
        return {}
    kanonikler = {
        kaynak: kanonik
        for kaynak, kanonik in oturum.execute(
            select(
                NesneBirlesimi.kaynak_nesne_id, NesneBirlesimi.kanonik_nesne_id
            ).where(NesneBirlesimi.kaynak_nesne_id.in_(sorted(nesne_idleri)))
        ).all()
    }
    return {n: kanonikler.get(n, n) for n in nesne_idleri}


def _kimlik_gecmisi_idleri(oturum: Session, nesne_id: int) -> list[int]:
    """Nesnenin kendisi ve ona birleşmiş bütün kaynaklar.

    Birleşen nesnenin özellik değerleri kaynakta kalır (hangi değerin doğru
    güncel değer olduğu bir domain yorumudur, çekirdek karar vermez); ama o
    değerler mükerrerlik açısından kanonik nesnenin **tarihsel kimliğidir** ve
    korumadan düşmez (2026-09-20 incelemesi, bulgu 5).
    """
    birlesenler = oturum.execute(
        select(NesneBirlesimi.kaynak_nesne_id).where(
            NesneBirlesimi.kanonik_nesne_id == nesne_id
        )
    ).scalars()
    return [nesne_id, *sorted(birlesenler)]


def _paketin_acik_talepleri(paket_id: int) -> Select[tuple[int]]:
    """Bir paketin açık taleplerinin kimlikleri: açılış paketi ya da bağlanan."""
    return (
        select(KararTalebi.id)
        .where(
            or_(
                KararTalebi.islem_paketi_id == paket_id,
                KararTalebi.id.in_(
                    select(KararTalebiPaketi.karar_talebi_id).where(
                        KararTalebiPaketi.islem_paketi_id == paket_id
                    )
                ),
            ),
            KararTalebi.durum == TalepDurumu.ACIK.value,
        )
        .order_by(KararTalebi.id)
    )


def _acik_talep_sayisi(oturum: Session, islem_paketi_id: int) -> int:
    return int(
        oturum.execute(
            select(func.count()).select_from(
                _paketin_acik_talepleri(islem_paketi_id).order_by(None).subquery()
            )
        ).scalar_one()
    )


# --- şart seçimi ----------------------------------------------------------------------


def _sart_kaynagini_dogrula(aktor: Aktor) -> None:
    """Şartı yalnız kullanıcı seçer (2026-09-20 altıncı tur).

    Kavramlar sözlüğü ("Mükerrerlik protokolü", 1. madde, Abdüllatif'in
    onayıyla 2026-09-11) ve bu modülün açıklaması şartı **kullanıcının**
    seçtiğini söylüyordu; kod ise aktör türüne bakmıyordu, ajan ve sistem de
    kalıcı şart ekleyebiliyordu. Şart geri alınamadığı için yanlış seçim
    kalıcı bir yanlış şüphe kaynağı olurdu. Kapı ``karar_ver``inkiyle aynı
    yerdedir: en başta, hiçbir şey okunmadan ve yazılmadan.

    Ajan ve sistem tarama yapar, şüphe açar, denetim olayı üretir; neyin
    kimlik sayılacağına karar veremez. ``karar_aktor_turu`` gibi bir
    veritabanı kısıtı burada yoktur: şart satırı aktör taşımaz, aktör yalnız
    denetim izine yazılır. Kısıt gerekirse şart tablolarına aktör sütunu
    eklemek gerekir; bugün servis kapısı yeterli sayıldı.
    """
    if aktor.tur is not AktorTuru.KULLANICI:
        raise SartKaynagiGecersiz(
            f"mükerrerlik şartını yalnız kullanıcı seçer; {aktor.tur.value!r} "
            "aktörü tarama yapabilir ve şüphe açabilir ama şart ekleyemez."
        )


def _ozellik_tanimlari(
    oturum: Session, nesne_turu_id: int, kodlar: Sequence[str]
) -> list[OzellikTanimi]:
    if not kodlar:
        raise GecersizSart("en az bir özellik kodu verilmeli.")
    benzersiz = list(dict.fromkeys(kodlar))
    tanimlar = list(
        oturum.execute(
            select(OzellikTanimi)
            .where(
                OzellikTanimi.nesne_turu_id == nesne_turu_id,
                OzellikTanimi.kod.in_(benzersiz),
            )
            .order_by(OzellikTanimi.id)
        ).scalars()
    )
    bulunan = {t.kod for t in tanimlar}
    eksik = [k for k in benzersiz if k not in bulunan]
    if eksik:
        raise GecersizSart(
            f"nesne türü {nesne_turu_id} için şu özellik tanımı yok: "
            f"{', '.join(eksik)}; başka türün özelliği şart seçilemez."
        )
    return tanimlar


def nesne_sarti_ekle(
    oturum: Session, nesne_id: int, ozellik_kodlari: Sequence[str], aktor: Aktor
) -> list[NesneMukerrerlikSarti]:
    """Kesin nesneye mükerrerlik şartı ekler; zaten seçili kod sessizce geçilir.

    Şart kaldırma işlevi yoktur (koruma zayıflatılamaz). Şartların anlamını
    çekirdek bilmez.

    **Nesne kanonik olmalı** (2026-09-20 beşinci inceleme turu). Birleşmiş bir
    nesneye şart eklemek koruma sağlamıyor, tek yönlü bir tarama bırakıyordu:
    taranan uç kendi kimlik geçmişinin şartlarını kullanır
    (``_kimlik_sartlari``), ama karşı ucun şartı ``_eslesen_nesneler`` içinde
    **kanonik** nesne üzerinden aranır. Şart birleşmiş nesnede kalırsa kanonik
    nesne tarandığında şüphe doğar, yeni gelen nesne tarandığında doğmaz —
    yani modülün "iki yönlü tarama" sözü tutulmaz. Birleşme sırasında kaynağın
    şartları hedefe kopyalandığı için birleşmeden **önce** seçilen şartlar bu
    durumdan etkilenmez; sorun yalnız birleşmeden sonra eklemekti. Çağıran
    kanonik nesneyi ``kanonik_nesneyi_bul`` ile bulup şartı oraya ekler;
    çekirdek hedefi kendiliğinden değiştirmez.
    """
    _sart_kaynagini_dogrula(aktor)
    nesne = nesne_getir(oturum, nesne_id)
    if (kanonik := kanonik_nesneyi_bul(oturum, nesne.id)) != nesne.id:
        raise NesneBirlesmis(
            f"nesne {nesne.id} kanonik nesne {kanonik} ile birleşmiş; mükerrerlik "
            f"şartı yalnız kanonik nesneye seçilir. Şartı {kanonik} için ekleyin."
        )
    tanimlar = _ozellik_tanimlari(oturum, nesne.nesne_turu_id, ozellik_kodlari)
    mevcut = {s.ozellik_tanimi_id for s in nesne_sartlarini_listele(oturum, nesne.id)}
    eklenen: list[NesneMukerrerlikSarti] = []
    with _yazma_siniri(oturum):
        for tanim in tanimlar:
            if tanim.id in mevcut:
                continue
            satir = NesneMukerrerlikSarti(
                nesne_id=nesne.id,
                nesne_turu_id=nesne.nesne_turu_id,
                ozellik_tanimi_id=tanim.id,
            )
            oturum.add(satir)
            eklenen.append(satir)
        oturum.flush()
        for satir in eklenen:
            olay_yaz(
                oturum,
                DenetimOlayi.MUKERRERLIK_SARTI_BELIRLENDI,
                aktor,
                nesne_id=nesne.id,
                ozellik_tanimi_id=satir.ozellik_tanimi_id,
            )
    return eklenen


def aday_sarti_ekle(
    oturum: Session, aday_nesne_id: int, ozellik_kodlari: Sequence[str], aktor: Aktor
) -> list[AdayNesneMukerrerlikSarti]:
    """Aday nesneye mükerrerlik şartı ekler (kesin nesneyle aynı kurallar).

    Aday şartı **aday veridir**: aday nesneyle birlikte silinir. Bu yüzden
    taslak yazma kuralına tabidir ve paket ``taslak_islemleri.yazilabilir_paket``
    ile denetlenir: yalnız ``calisiyor`` pakette şart seçilir (2026-09-20 beşinci
    inceleme turu). Önceden bu denetim yoktu ve ``bekliyor`` ya da terminal
    ``iptal`` pakete kalıcı şart satırı yazılabiliyordu; şart kaldırma işlevi de
    olmadığından satır orada kalırdı.
    """
    _sart_kaynagini_dogrula(aktor)
    aday = aday_nesne_getir(oturum, aday_nesne_id)
    yazilabilir_paket(oturum, aday.islem_paketi_id)
    tanimlar = _ozellik_tanimlari(oturum, aday.nesne_turu_id, ozellik_kodlari)
    mevcut = {s.ozellik_tanimi_id for s in aday_sartlarini_listele(oturum, aday.id)}
    eklenen: list[AdayNesneMukerrerlikSarti] = []
    with _yazma_siniri(oturum):
        for tanim in tanimlar:
            if tanim.id in mevcut:
                continue
            satir = AdayNesneMukerrerlikSarti(
                aday_nesne_id=aday.id,
                nesne_turu_id=aday.nesne_turu_id,
                ozellik_tanimi_id=tanim.id,
            )
            oturum.add(satir)
            eklenen.append(satir)
        oturum.flush()
        for satir in eklenen:
            olay_yaz(
                oturum,
                DenetimOlayi.MUKERRERLIK_SARTI_BELIRLENDI,
                aktor,
                islem_paketi_id=aday.islem_paketi_id,
                aday_nesne_id=aday.id,
                ozellik_tanimi_id=satir.ozellik_tanimi_id,
            )
    return eklenen


def nesne_sartlarini_listele(
    oturum: Session, nesne_id: int
) -> list[NesneMukerrerlikSarti]:
    return list(
        oturum.execute(
            select(NesneMukerrerlikSarti)
            .where(NesneMukerrerlikSarti.nesne_id == nesne_id)
            .order_by(NesneMukerrerlikSarti.ozellik_tanimi_id)
        ).scalars()
    )


def aday_sartlarini_listele(
    oturum: Session, aday_nesne_id: int
) -> list[AdayNesneMukerrerlikSarti]:
    return list(
        oturum.execute(
            select(AdayNesneMukerrerlikSarti)
            .where(AdayNesneMukerrerlikSarti.aday_nesne_id == aday_nesne_id)
            .order_by(AdayNesneMukerrerlikSarti.ozellik_tanimi_id)
        ).scalars()
    )


# --- eşleşme taraması -----------------------------------------------------------------


def _kimlik_degerleri(
    oturum: Session, kimlik_idleri: Sequence[int]
) -> set[tuple[int, str]]:
    """Kanonik nesnenin ve ona birleşmiş kaynakların ``(özellik, değer)`` çiftleri.

    Aynı özellik için birden fazla tarihsel değer olabilir (kaynakta bir,
    hedefte başka bir değer); ikisi de kimlik kanıtıdır, hiçbiri diğerini
    ezmez. Bu küme yalnız mükerrerlik taramasında kullanılır; nesnenin normal
    özellik okuması (``nesne_islemleri``) değişmez.
    """
    idler = list(kimlik_idleri)
    return {
        (tanim_id, deger)
        for tanim_id, deger in oturum.execute(
            select(NesneOzelligi.ozellik_tanimi_id, NesneOzelligi.deger).where(
                NesneOzelligi.nesne_id.in_(idler)
            )
        ).all()
    }


def _kimlik_sartlari(oturum: Session, kimlik_idleri: Sequence[int]) -> set[int]:
    """Kanonik nesnenin ve ona birleşmiş kaynakların şart özellikleri."""
    idler = list(kimlik_idleri)
    return set(
        oturum.execute(
            select(NesneMukerrerlikSarti.ozellik_tanimi_id).where(
                NesneMukerrerlikSarti.nesne_id.in_(idler)
            )
        ).scalars()
    )


def _aday_degerleri(oturum: Session, aday_nesne_id: int) -> set[tuple[int, str]]:
    return {
        (tanim_id, deger)
        for tanim_id, deger in oturum.execute(
            select(AdayNesneOzelligi.ozellik_tanimi_id, AdayNesneOzelligi.deger).where(
                AdayNesneOzelligi.aday_nesne_id == aday_nesne_id
            )
        ).all()
    }


def _eslesen_nesneler(
    oturum: Session,
    nesne_turu_id: int,
    degerler: set[tuple[int, str]],
    sart_kimlikleri: set[int],
    haric: set[int],
) -> dict[int, int]:
    """Şüphe doğuran **kanonik** nesneler: ``nesne kimliği → eşleşen özellik``.

    İki yön birlikte taranır: taranan ucun şartları (birinci sorgu) ve karşı
    ucun şartları (ikinci sorgu). Karşılaştırma kanonik metnin birebir
    eşitliğidir. Bir nesne için birden çok özellik eşleşirse kanıt olarak en
    küçük özellik tanımı kimliği tutulur (deterministik).

    Birleşmiş bir nesne sonuçtan **atılmaz**, kanonik nesnesine eşlenir: eski
    kimlik değerleri korumadan düşmez, ama karar talebi her zaman kanonik
    nesneyi gösterir (2026-09-20 incelemesi, bulgu 5). Karşı ucun şartı da
    kanonik nesne üzerinden aranır: birleşen kaynağın değeri, kanonik nesnenin
    şartıyla korunur (şartlar birleşimde kanonik nesnede toplanır).
    """
    if not degerler:
        return {}
    tum_ciftler = sorted(degerler)
    kendi_ciftleri = sorted(
        (tanim_id, deger) for tanim_id, deger in degerler if tanim_id in sart_kimlikleri
    )
    kanonik_sahip = func.coalesce(
        NesneBirlesimi.kanonik_nesne_id, NesneOzelligi.nesne_id
    )
    sorgular = [
        select(NesneOzelligi.nesne_id, NesneOzelligi.ozellik_tanimi_id)
        .join(
            NesneBirlesimi,
            NesneBirlesimi.kaynak_nesne_id == NesneOzelligi.nesne_id,
            isouter=True,
        )
        .join(
            NesneMukerrerlikSarti,
            and_(
                NesneMukerrerlikSarti.nesne_id == kanonik_sahip,
                NesneMukerrerlikSarti.ozellik_tanimi_id
                == NesneOzelligi.ozellik_tanimi_id,
            ),
        )
        .where(
            NesneOzelligi.nesne_turu_id == nesne_turu_id,
            tuple_(NesneOzelligi.ozellik_tanimi_id, NesneOzelligi.deger).in_(
                tum_ciftler
            ),
        )
    ]
    if kendi_ciftleri:
        sorgular.append(
            select(NesneOzelligi.nesne_id, NesneOzelligi.ozellik_tanimi_id).where(
                NesneOzelligi.nesne_turu_id == nesne_turu_id,
                tuple_(NesneOzelligi.ozellik_tanimi_id, NesneOzelligi.deger).in_(
                    kendi_ciftleri
                ),
            )
        )
    ham: dict[int, int] = {}
    for sorgu in sorgular:
        for nesne_id, tanim_id in oturum.execute(sorgu).all():
            onceki = ham.get(nesne_id)
            if onceki is None or tanim_id < onceki:
                ham[nesne_id] = tanim_id
    if not ham:
        return {}
    kanonikler = _kanonik_esleme(oturum, set(ham))
    eslesmeler: dict[int, int] = {}
    for nesne_id, tanim_id in ham.items():
        kanonik = kanonikler[nesne_id]
        if kanonik in haric:
            continue
        onceki = eslesmeler.get(kanonik)
        if onceki is None or tanim_id < onceki:
            eslesmeler[kanonik] = tanim_id
    return eslesmeler


def talebin_paketleri(oturum: Session, talep: KararTalebi) -> set[int]:
    """Bu soruyu bekleyen paketler: açılış paketi ve sonradan bağlananlar.

    İptal edilen paketin bağı silinmez; hangilerinin hâlâ etkin olduğunu
    çağıran ``taslak_islemleri.paket_getir`` ile bakar.
    """
    paketler = set(
        oturum.scalars(
            select(KararTalebiPaketi.islem_paketi_id).where(
                KararTalebiPaketi.karar_talebi_id == talep.id
            )
        )
    )
    if talep.islem_paketi_id is not None:
        paketler.add(talep.islem_paketi_id)
    return paketler


def _talebi_pakete_bagla(
    oturum: Session, talep: KararTalebi, paket_id: int, aktor: Aktor
) -> None:
    paket = paket_getir(oturum, paket_id)
    if paket.durum == PaketDurumu.IPTAL.value:
        return
    if oturum.get(KararTalebiPaketi, (talep.id, paket_id)) is not None:
        return
    with _yazma_siniri(oturum):
        oturum.add(
            KararTalebiPaketi(karar_talebi_id=talep.id, islem_paketi_id=paket_id)
        )
        oturum.flush()
        olay_yaz(
            oturum,
            DenetimOlayi.KARAR_TALEBI_PAKETE_BAGLANDI,
            aktor,
            islem_paketi_id=paket_id,
            karar_talebi_id=talep.id,
            gerekce="mevcut ortak karar talebine paket bağlandı",
        )


def _cift_talebi(
    oturum: Session,
    *,
    hedef_nesne_id: int,
    aday_nesne_id: int | None = None,
    kaynak_nesne_id: int | None = None,
) -> KararTalebi | None:
    """Bu çift için (açık ya da çözülmüş) talep var mı? Çözülmüş "ayrı" kararı
    aynı çifti yeniden durdurmaz; açık talep ikinci kez açılmaz.

    ``gecersiz`` talepler sayılmaz: paketi iptal edildiği için hükümsüz kalan
    bir talep kullanıcı kararı taşımaz, dolayısıyla aynı çiftin başka bir
    pakette değerlendirilmesini engelleyemez.
    """
    hedefler = _kimlik_gecmisi_idleri(oturum, hedef_nesne_id)
    sorgu = select(KararTalebi).where(
        KararTalebi.durum != TalepDurumu.GECERSIZ.value,
    )
    if aday_nesne_id is not None:
        sorgu = sorgu.where(
            KararTalebi.aday_nesne_id == aday_nesne_id,
            KararTalebi.hedef_nesne_id.in_(hedefler),
        )
    else:
        assert kaynak_nesne_id is not None
        sorgu = sorgu.where(
            KararTalebi.hedef_nesne_id == hedef_nesne_id,
            KararTalebi.kaynak_nesne_id == kaynak_nesne_id,
        )
    return oturum.scalars(
        sorgu.order_by(
            (KararTalebi.durum == TalepDurumu.ACIK.value).desc(), KararTalebi.id
        )
    ).first()


def _talep_ac(
    oturum: Session,
    aktor: Aktor,
    *,
    islem_paketi_id: int | None,
    nesne_turu_id: int,
    hedef_nesne_id: int,
    eslesen_ozellik_tanimi_id: int,
    aday_nesne_id: int | None = None,
    kaynak_nesne_id: int | None = None,
) -> KararTalebi:
    with _yazma_siniri(
        oturum,
        KARAR_TALEBI,
        SupheZatenAcik,
        f"nesne {hedef_nesne_id} için aynı çiftte açık karar talebi zaten var.",
    ):
        talep = KararTalebi(
            durum=TalepDurumu.ACIK.value,
            islem_paketi_id=islem_paketi_id,
            nesne_turu_id=nesne_turu_id,
            aday_nesne_id=aday_nesne_id,
            kaynak_nesne_id=kaynak_nesne_id,
            hedef_nesne_id=hedef_nesne_id,
            eslesen_ozellik_tanimi_id=eslesen_ozellik_tanimi_id,
            olusturma_zamani=simdi_utc(),
            acan_aktor_turu=aktor.tur.value,
            acan_aktor_kimligi=aktor.kimlik.strip(),
            bagimsiz_koken=islem_paketi_id is None,
        )
        oturum.add(talep)
        oturum.flush()
        if islem_paketi_id is not None:
            oturum.add(
                KararTalebiPaketi(
                    karar_talebi_id=talep.id, islem_paketi_id=islem_paketi_id
                )
            )
            oturum.flush()
        for olay in (
            DenetimOlayi.MUKERRERLIK_SUPHESI_ACILDI,
            DenetimOlayi.KARAR_TALEBI_ACILDI,
        ):
            olay_yaz(
                oturum,
                olay,
                aktor,
                islem_paketi_id=islem_paketi_id,
                karar_talebi_id=talep.id,
                nesne_id=hedef_nesne_id,
                ikincil_nesne_id=kaynak_nesne_id,
                aday_nesne_id=aday_nesne_id,
                ozellik_tanimi_id=eslesen_ozellik_tanimi_id,
            )
    return talep


def adayi_denetle(
    oturum: Session, aday_nesne_id: int, aktor: Aktor
) -> list[KararTalebi]:
    """Aday nesneyi mevcut kesin nesnelere karşı mükerrerlik denetimine sokar.

    Eşleşme otomatik birleştirme değildir: her eşleşme için kalıcı karar
    talebi açılır ve paket ``BEKLIYOR``a geçer. Şart hiçbir uçta yoksa hiçbir
    şey olmaz.

    Taramanın bütün yazmaları **tek bir dış SAVEPOINT** içindedir (2026-09-20
    üçüncü turu, bulgu 2): talepler, denetim izleri ve paket durumu aynı
    atomiklik sınırındadır. Paket bekletme adımı düşerse açılan talep de
    kalmaz; "açık talebi var ama paket ``calisiyor``" gibi yarım bir durum
    çağıran hatayı yutup commit etse bile oluşmaz.
    """
    aday = aday_nesne_getir(oturum, aday_nesne_id)
    paket = paket_getir(oturum, aday.islem_paketi_id)
    if paket.durum == PaketDurumu.IPTAL.value:
        raise PaketDurumuGecersiz(
            f"işlem paketi {paket.id} iptal; mükerrerlik denetimi yapılmaz."
        )
    with _yazma_siniri(oturum):  # dış SAVEPOINT: ya hepsi ya hiçbiri
        eslesmeler = _eslesen_nesneler(
            oturum,
            aday.nesne_turu_id,
            _aday_degerleri(oturum, aday.id),
            {s.ozellik_tanimi_id for s in aday_sartlarini_listele(oturum, aday.id)},
            haric={cozum}
            if (cozum := adayin_kesin_nesnesi(oturum, aday.id))
            else set(),
        )
        talepler = [
            _talep_ac(
                oturum,
                aktor,
                islem_paketi_id=paket.id,
                nesne_turu_id=aday.nesne_turu_id,
                hedef_nesne_id=nesne_id,
                eslesen_ozellik_tanimi_id=eslesmeler[nesne_id],
                aday_nesne_id=aday.id,
            )
            for nesne_id in sorted(eslesmeler)
            if _cift_talebi(oturum, hedef_nesne_id=nesne_id, aday_nesne_id=aday.id)
            is None
        ]
        _paket_durumunu_esitle(oturum, paket.id, aktor)
    return talepler


def nesneyi_denetle(
    oturum: Session,
    nesne_id: int,
    aktor: Aktor,
    islem_paketi_id: int | None = None,
) -> list[KararTalebi]:
    """Kesin nesneyi diğer kesin nesnelere karşı denetler; **açılan** talepler.

    Çift normalleştirilir: küçük kimlikli (önce oluşturulan) nesne hedeftir ve
    ``AYNI`` kararında korunur. Birleştirilmiş nesneler taramaya girmez.

    Taramanın bütün yazmaları **tek bir dış SAVEPOINT** içindedir (2026-09-20
    üçüncü turu, bulgu 2): yeni talepler, mevcut ortak soruya eklenen paket
    bağları, denetim izleri ve paket durumu aynı atomiklik sınırındadır. Paket
    bekletme adımı düşerse ne talep ne bağ kalır; açık sorusu olan bir pakete
    ``calisiyor`` sanılıp yeni aday yazılamaz. ``karar_ver`` bu işlevi kendi
    dış SAVEPOINT'i içinden çağırır; iç içe SAVEPOINT olağan davranıştır.

    Dönen liste yalnız bu çağrının **açtığı** talepleri taşır; zaten açık olan
    bir soruya yalnız paket bağı eklenir. Kökeni de ilgilendiren çağıran
    (``_zincirleme_denetle``) ikisini birden ``_nesneyi_tara`` ile alır.
    """
    return list(_nesneyi_tara(oturum, nesne_id, aktor, islem_paketi_id).acilan)


def _nesneyi_tara(
    oturum: Session,
    nesne_id: int,
    aktor: Aktor,
    islem_paketi_id: int | None = None,
) -> _TaramaSonucu:
    """``nesneyi_denetle``in gövdesi; açılan **ve** dokunulan açık talepler."""
    nesne = nesne_getir(oturum, nesne_id)
    if islem_paketi_id is not None:
        paket = paket_getir(oturum, islem_paketi_id)
        if paket.durum == PaketDurumu.IPTAL.value:
            raise PaketDurumuGecersiz(f"işlem paketi {paket.id} iptal; taranamaz.")
    if nesne_birlesimini_bul(oturum, nesne.id) is not None:
        return _TaramaSonucu((), ())
    acilan: list[KararTalebi] = []
    dokunulan: list[KararTalebi] = []
    with _yazma_siniri(oturum):  # dış SAVEPOINT: ya hepsi ya hiçbiri
        kimlik_idleri = _kimlik_gecmisi_idleri(oturum, nesne.id)
        eslesmeler = _eslesen_nesneler(
            oturum,
            nesne.nesne_turu_id,
            _kimlik_degerleri(oturum, kimlik_idleri),
            _kimlik_sartlari(oturum, kimlik_idleri),
            haric={nesne.id},
        )
        for karsi_id in sorted(eslesmeler):
            hedef_id, kaynak_id = min(nesne.id, karsi_id), max(nesne.id, karsi_id)
            mevcut = _cift_talebi(
                oturum, hedef_nesne_id=hedef_id, kaynak_nesne_id=kaynak_id
            )
            if mevcut is not None:
                if mevcut.durum == TalepDurumu.ACIK.value:
                    dokunulan.append(mevcut)
                    if islem_paketi_id is not None:
                        _talebi_pakete_bagla(oturum, mevcut, islem_paketi_id, aktor)
                continue
            acilan.append(
                _talep_ac(
                    oturum,
                    aktor,
                    islem_paketi_id=islem_paketi_id,
                    nesne_turu_id=nesne.nesne_turu_id,
                    hedef_nesne_id=hedef_id,
                    kaynak_nesne_id=kaynak_id,
                    eslesen_ozellik_tanimi_id=eslesmeler[karsi_id],
                )
            )
        if islem_paketi_id is not None:
            _paket_durumunu_esitle(oturum, islem_paketi_id, aktor)
    return _TaramaSonucu(tuple(acilan), tuple(dokunulan))


# --- paket durumu ---------------------------------------------------------------------


def _paket_durumunu_esitle(
    oturum: Session, islem_paketi_id: int, aktor: Aktor
) -> PaketDurumu:
    """Paket durumunu açık talep sayısına eşitler; ``IPTAL`` terminaldir.

    Açık talep varsa ``BEKLIYOR``, hiç kalmadıysa ``CALISIYOR``. İlk kararın
    tek başına paketi canlandırmaması bu kuraldan gelir. Tekrar çağrılabilir.
    """
    paket = paket_getir(oturum, islem_paketi_id)
    if paket.durum == PaketDurumu.IPTAL.value:
        return PaketDurumu.IPTAL
    acik = _acik_talep_sayisi(oturum, paket.id)
    if acik > 0 and paket.durum == PaketDurumu.CALISIYOR.value:
        paketi_beklet(oturum, paket.id)
        olay_yaz(
            oturum,
            DenetimOlayi.PAKET_BEKLEMEYE_GECTI,
            aktor,
            islem_paketi_id=paket.id,
            gerekce=f"açık karar talebi: {acik}",
        )
        return PaketDurumu.BEKLIYOR
    if acik == 0 and paket.durum == PaketDurumu.BEKLIYOR.value:
        paketi_devam_et(oturum, paket.id)
        olay_yaz(
            oturum,
            DenetimOlayi.PAKET_YENIDEN_CALISIYOR,
            aktor,
            islem_paketi_id=paket.id,
            gerekce="açık karar talebi kalmadı",
        )
        return PaketDurumu.CALISIYOR
    return PaketDurumu(paket.durum)


# --- karar ----------------------------------------------------------------------------


def karar_ver(
    oturum: Session,
    karar_talebi_id: int,
    karar: Karar,
    aktor: Aktor,
    gerekce: str | None = None,
) -> KararSonucu:
    """Açık karar talebine kullanıcı kararını uygular.

    ``AYRI`` talebi kapatır. ``AYNI`` çözümlemeyi (aday → kesin nesne) ya da
    birleştirmeyi (kesin → kesin) uygular. ``KARARSIZ`` talebi açık bırakır.
    Kapalı talebe ikinci karar ``KararTalebiKapali`` verir; iki bağlantı aynı
    anda cevaplarsa yalnız biri kazanır.

    **Bütün yazmalar tek bir dış SAVEPOINT içindedir** (2026-09-20 ikinci
    incelemesi, bulgu 2). Talebin kapatılması, denetim olayları, çözümleme,
    birleştirme, kanonik yeniden bağlama, açık talep uzlaştırması ve paket
    durumu aynı atomiklik sınırındadır: herhangi bir adım düşerse bu çağrının
    yaptığı **hiçbir** değişiklik kalmaz — çağıran hatayı yakalayıp dış
    transaction'ı commit etse bile. Eskiden talebi kapatan SAVEPOINT kendi
    başına tamamlandığı için "talep ``cozuldu/ayni`` ama birleşim yok" gibi
    yarım bir durum kalıcı olabiliyordu. Servis dış transaction'a dokunmaz:
    çağıranın bu çağrıdan **önce** yaptığı bağımsız değişiklikler korunur.
    """
    karar = Karar(karar)
    _karar_kaynagini_dogrula(aktor)
    _gerekceyi_dogrula(karar, gerekce)
    talep = karar_talebi_getir(oturum, karar_talebi_id)
    if talep.durum == TalepDurumu.GECERSIZ.value:
        raise KararTalebiKapali(
            f"karar talebi {talep.id} geçersiz: hükümsüz kaldı (paketi iptal "
            "edildi ya da bir ucu birleşme sonucu kanonik olmaktan çıktı). "
            "Geçersizlik bir kullanıcı kararı değildir ve talep yeniden karara "
            "açılmaz; soru hâlâ geçerliyse kanonik uçlarla yeniden sorulur."
        )
    if talep.durum != TalepDurumu.ACIK.value:
        raise KararTalebiKapali(
            f"karar talebi {talep.id} {talep.durum}; ikinci karar uygulanmaz."
        )
    paket_id = talep.islem_paketi_id
    if paket_id is not None:
        paket = paket_getir(oturum, paket_id)
        if paket.durum == PaketDurumu.IPTAL.value:
            etkinler = sorted(
                p
                for p in talebin_paketleri(oturum, talep)
                if paket_getir(oturum, p).durum != PaketDurumu.IPTAL.value
            )
            if etkinler:
                paket_id = etkinler[0]
            elif talep.bagimsiz_koken:
                # Soruyu ayakta tutan şey bir paket değil: hiçbir paket
                # dirilmeden cevaplanır (2026-09-20 üçüncü turu, bulgu 1).
                paket_id = None
            else:
                raise PaketDurumuGecersiz(
                    f"işlem paketi {paket.id} iptal (terminal); talebine karar "
                    "verilmez ve paket diriltilmez."
                )
    with _yazma_siniri(oturum):  # dış SAVEPOINT: ya hepsi ya hiçbiri
        return _karari_uygula(oturum, talep, karar, aktor, gerekce, paket_id)


def _karari_uygula(
    oturum: Session,
    talep: KararTalebi,
    karar: Karar,
    aktor: Aktor,
    gerekce: str | None,
    paket_id: int | None,
) -> KararSonucu:
    """``karar_ver``in yazan gövdesi; çağıranın açtığı dış SAVEPOINT içinde
    çalışır ve kendi başına işlem sınırı açmaz."""
    if karar is Karar.KARARSIZ:
        olay_yaz(
            oturum,
            DenetimOlayi.KULLANICI_KARARI_VERILDI,
            aktor,
            islem_paketi_id=paket_id,
            karar_talebi_id=talep.id,
            gerekce=_karar_gerekcesi(karar, gerekce),
        )
        durum = (
            None
            if paket_id is None
            else _paket_durumunu_esitle(oturum, paket_id, aktor)
        )
        return KararSonucu(talep=talep, cozuldu=False, paket_durumu=durum)

    if karar is Karar.AYRI and talep.aday_nesne_id is not None:
        if adayin_kesin_nesnesi(oturum, talep.aday_nesne_id) == kanonik_nesneyi_bul(
            oturum, talep.hedef_nesne_id
        ):
            raise KararCelismesi("Aday zaten bu kanonik nesneye çözümlü; ayrı olamaz.")
    _talebi_kapat(oturum, talep, karar, aktor, gerekce)
    olay_yaz(
        oturum,
        DenetimOlayi.KULLANICI_KARARI_VERILDI,
        aktor,
        islem_paketi_id=paket_id,
        karar_talebi_id=talep.id,
        gerekce=_karar_gerekcesi(karar, gerekce),
    )

    cozumleme: AdayNesneCozumlemesi | None = None
    birlestirme: _Birlestirme | None = None
    yeni_talepler: tuple[KararTalebi, ...] = ()
    if karar is Karar.AYRI:
        olay_yaz(
            oturum,
            DenetimOlayi.NESNE_AYRI_KABUL_EDILDI,
            aktor,
            islem_paketi_id=paket_id,
            karar_talebi_id=talep.id,
            nesne_id=talep.hedef_nesne_id,
            ikincil_nesne_id=talep.kaynak_nesne_id,
            aday_nesne_id=talep.aday_nesne_id,
        )
    elif talep.aday_nesne_id is not None:
        cozumleme, birlestirme = _adayi_cozumle(oturum, talep, aktor)
        if birlestirme is not None:
            yeni_talepler = tuple(
                _zincirleme_denetle(
                    oturum, birlestirme.birlesim.hedef_nesne_id, paket_id, talep, aktor
                )
            )
    else:
        kaynak_id = talep.kaynak_nesne_id
        assert kaynak_id is not None  # kontrol kısıtı: uçlardan tam biri dolu
        birlestirme = _nesneleri_birlestir(
            oturum, talep, kaynak_id, talep.hedef_nesne_id, aktor
        )
        yeni_talepler = tuple(
            _zincirleme_denetle(oturum, talep.hedef_nesne_id, paket_id, talep, aktor)
        )

    gecersiz = list(() if birlestirme is None else birlestirme.gecersiz_talepler)
    if karar is Karar.AYNI:
        gecersiz.extend(_aday_talepleri_uzlastir(oturum, talep, aktor))
    etkilenen = talebin_paketleri(oturum, talep)
    if birlestirme is not None:
        for p in sorted(etkilenen - {paket_id}):
            if paket_getir(oturum, p).durum != PaketDurumu.IPTAL.value:
                yeni_talepler += tuple(
                    _zincirleme_denetle(
                        oturum, birlestirme.birlesim.hedef_nesne_id, p, talep, aktor
                    )
                )
    for eski in gecersiz:
        paketler = talebin_paketleri(oturum, eski)
        etkilenen.update(paketler)
        if eski.kaynak_nesne_id is not None:
            yeni = _kanonik_soruyu_koru(oturum, eski, aktor)
            if yeni is not None:
                if yeni.id not in {t.id for t in yeni_talepler}:
                    yeni_talepler += (yeni,)
                for p in sorted(paketler):
                    _talebi_pakete_bagla(oturum, yeni, p, aktor)
    for diger_paket_id in sorted(etkilenen - {paket_id}):
        _paket_durumunu_esitle(oturum, diger_paket_id, aktor)
    durum = (
        None if paket_id is None else _paket_durumunu_esitle(oturum, paket_id, aktor)
    )
    return KararSonucu(
        talep=talep,
        cozuldu=True,
        paket_durumu=durum,
        cozumleme=cozumleme,
        birlesim=None if birlestirme is None else birlestirme.birlesim,
        devir=None if birlestirme is None else birlestirme.devir,
        yeni_talepler=yeni_talepler,
        gecersiz_kalan_talepler=tuple(gecersiz),
    )


def _karar_kaynagini_dogrula(aktor: Aktor) -> None:
    """Kararı yalnız kullanıcı verir (Aşama 4.6 sözleşmesi).

    Ajan ve sistem tarama yapabilir, şüphe açabilir, denetim olayı üretebilir;
    kullanıcı yerine ``AYNI`` / ``AYRI`` / ``KARARSIZ`` diyemez. Denetim en
    başta yapılır: reddedilen çağrı talebi değiştirmez, denetim izine yazmaz,
    paket durumuna dokunmaz. Güvenli otomatik karar motoru (Aşama 4.9) yoktur;
    geldiğinde bu kapı ve ``karar_aktor_turu`` kısıtı birlikte genişletilir.
    """
    if aktor.tur is not AktorTuru.KULLANICI:
        raise KararKaynagiGecersiz(
            f"mükerrerlik kararını yalnız kullanıcı verir; {aktor.tur.value!r} "
            "aktörü tarama yapabilir ve şüphe açabilir ama karar veremez."
        )


def _karar_gerekcesi(karar: Karar, gerekce: str | None) -> str:
    return karar.value if gerekce is None else f"{karar.value}: {gerekce}"


def _gerekceyi_dogrula(karar: Karar, gerekce: str | None) -> None:
    """Sınır kararın en başında denetlenir: talep kapandıktan sonra düşen bir
    denetim yazımı yerine çağırana doğrudan anlamlı hata verilir."""
    if gerekce is not None and len(_karar_gerekcesi(karar, gerekce)) > (
        AZAMI_GEREKCE_UZUNLUGU
    ):
        raise GecersizSart(
            f"gerekçe {AZAMI_GEREKCE_UZUNLUGU} karakter sınırını aşıyor; karar "
            "talebi bir içerik deposu değildir."
        )


def _talebi_kapat(
    oturum: Session, talep: KararTalebi, karar: Karar, aktor: Aktor, gerekce: str | None
) -> None:
    """Koşullu güncelleme: yalnız açık talep kapanır, yarışta tek kazanan olur."""
    with _yazma_siniri(oturum):
        guncellenen = oturum.execute(
            update(KararTalebi)
            .where(
                KararTalebi.id == talep.id,
                KararTalebi.durum == TalepDurumu.ACIK.value,
            )
            .values(
                durum=TalepDurumu.COZULDU.value,
                karar=karar.value,
                karar_zamani=simdi_utc(),
                karar_aktor_turu=aktor.tur.value,
                karar_aktor_kimligi=aktor.kimlik.strip(),
                gerekce=gerekce,
            )
            .returning(KararTalebi.id)
        ).scalar_one_or_none()
        if guncellenen is None:
            raise KararTalebiKapali(
                f"karar talebi {talep.id} eşzamanlı olarak cevaplandı; "
                "ikinci karar uygulanmadı."
            )
    oturum.refresh(talep)


def _ayri_karari(
    oturum: Session, kume: Sequence[int], karsi_kume: Sequence[int]
) -> KararTalebi | None:
    """İki kanonik kümenin **herhangi iki üyesi** arasındaki ``AYRI`` kararı.

    Kümeler ``_kimlik_gecmisi_idleri`` ile bulunur: kanonik nesnenin kendisi ve
    ona daha önce birleşmiş bütün nesneler. Kimlikler birleşmelerle değiştiği
    için doğrudan çifte bakmak yetmez (2026-09-20 ikinci incelemesi, bulgu 1):
    kullanıcı ``N1 ≠ N3`` demişse ve ``N3`` sonradan ``N2``ye birleşmişse
    ``N1 = N2`` kararı eski kararı aşar. Zincir ne kadar uzun olursa olsun
    düzleştirme sayesinde küme tek sorguda bulunur.

    Karar satırının yönü sonucu değiştirmez: kesin çift ``kaynak > hedef``
    sırasına normalleştirildiğinden AYRI kararı hangi kümenin üyesini hedef
    yazdıysa o yazılmıştır, iki yön de aranır.
    """
    bu, karsi = sorted(set(kume)), sorted(set(karsi_kume))
    # Adayın kesin çözümlemesi de kimliğin parçasıdır. AYRI satırındaki
    # kaynak NULL olsa bile adayın çözümlendiği nesne karşı ucu temsil eder.
    kaynak = func.coalesce(KararTalebi.kaynak_nesne_id, AdayNesneCozumlemesi.nesne_id)
    return (
        oturum.execute(
            select(KararTalebi)
            .outerjoin(
                AdayNesneCozumlemesi,
                AdayNesneCozumlemesi.aday_nesne_id == KararTalebi.aday_nesne_id,
            )
            .where(
                KararTalebi.karar == Karar.AYRI.value,
                or_(
                    and_(
                        KararTalebi.hedef_nesne_id.in_(bu),
                        kaynak.in_(karsi),
                    ),
                    and_(
                        KararTalebi.hedef_nesne_id.in_(karsi),
                        kaynak.in_(bu),
                    ),
                ),
            )
            .order_by(KararTalebi.id)
        )
        .scalars()
        .first()
    )


def _adayi_cozumle(
    oturum: Session, talep: KararTalebi, aktor: Aktor
) -> tuple[AdayNesneCozumlemesi, _Birlestirme | None]:
    """Aday nesneyi mevcut kesin nesneye kalıcı olarak çözümler.

    Aday satır kesin tabloya taşınmaz; adayın özellikleri, ilişkileri ve kayıt
    bağları olduğu gibi kalır. Kesinleştirme 4.8'in işidir ve bu satırı okur.
    Satıra yazılan nesne, kararın verildiği andaki **kanonik** nesnedir.

    **Aynı aday birden fazla kesin nesneyle eşleşebilir** (biri bir kimlikten,
    öteki başka bir kimlikten). Kullanıcı ikisine de ``AYNI`` derse mantıksal
    sonuç ``X = Y``dir; aday için ikinci bir çözümleme satırı yazılmaz (ham
    benzersizlik hatası da sızmaz), problem iki kesin nesnenin birleştirilmesi
    problemine dönüşür ve bu talep birleşimin karar kaynağı olarak kaydedilir.
    İkisi aynı kanonik nesneye çıkıyorsa yapılacak yeni bir şey yoktur; karar
    yine denetim izine yazılır.

    Kullanıcı o iki kesin nesnenin (ya da onlara birleşmiş eski kimliklerin)
    herhangi bir çifti için daha önce ``AYRI`` demişse çelişki sessizce
    çözülmez: ``_nesneleri_birlestir`` ``KararCelismesi`` yükseltir, işlem
    tamamen geri alınır, talep açık kalır. Eski kullanıcı kararını ezmek de
    yeni kullanıcı kararını yok saymak da çekirdeğin işi değildir; kullanıcı
    ya bu talebe ``AYRI`` der ya da iki kesin nesneyi kendisi ele alır.
    """
    aday_id = talep.aday_nesne_id
    assert aday_id is not None  # kontrol kısıtı: uçlardan tam biri dolu
    hedef_id = kanonik_nesneyi_bul(oturum, talep.hedef_nesne_id)
    ayri = oturum.scalars(
        select(KararTalebi)
        .where(
            KararTalebi.aday_nesne_id == aday_id,
            KararTalebi.karar == Karar.AYRI.value,
            KararTalebi.hedef_nesne_id.in_(_kimlik_gecmisi_idleri(oturum, hedef_id)),
        )
        .order_by(KararTalebi.id)
    ).first()
    if ayri is not None:
        raise KararCelismesi(
            f"aday {aday_id}, karar talebi {ayri.id} ile bu kimlikten "
            "ayrı kabul edildi."
        )
    mevcut = aday_cozumlemesi_bul(oturum, aday_id)
    if mevcut is None:
        with _yazma_siniri(oturum):
            cozumleme = AdayNesneCozumlemesi(
                aday_nesne_id=aday_id,
                nesne_turu_id=talep.nesne_turu_id,
                nesne_id=hedef_id,
                karar_talebi_id=talep.id,
                olusturma_zamani=simdi_utc(),
                aktor_turu=aktor.tur.value,
                aktor_kimligi=aktor.kimlik.strip(),
            )
            oturum.add(cozumleme)
            oturum.flush()
            olay_yaz(
                oturum,
                DenetimOlayi.ADAY_NESNEYE_COZUMLENDI,
                aktor,
                islem_paketi_id=talep.islem_paketi_id,
                karar_talebi_id=talep.id,
                nesne_id=hedef_id,
                aday_nesne_id=aday_id,
            )
        return cozumleme, None

    onceki_id = kanonik_nesneyi_bul(oturum, mevcut.nesne_id)
    if onceki_id == hedef_id:
        olay_yaz(
            oturum,
            DenetimOlayi.ADAY_NESNEYE_COZUMLENDI,
            aktor,
            islem_paketi_id=talep.islem_paketi_id,
            karar_talebi_id=talep.id,
            nesne_id=hedef_id,
            aday_nesne_id=aday_id,
            gerekce=f"aday zaten kanonik nesne {hedef_id} olarak çözümlü",
        )
        return mevcut, None

    yeni_hedef_id, kaynak_id = min(onceki_id, hedef_id), max(onceki_id, hedef_id)
    birlestirme = _nesneleri_birlestir(oturum, talep, kaynak_id, yeni_hedef_id, aktor)
    olay_yaz(
        oturum,
        DenetimOlayi.ADAY_NESNEYE_COZUMLENDI,
        aktor,
        islem_paketi_id=talep.islem_paketi_id,
        karar_talebi_id=talep.id,
        nesne_id=yeni_hedef_id,
        aday_nesne_id=aday_id,
        gerekce=(
            f"aday {onceki_id} nesnesine çözümlüydü; bu karar {kaynak_id} "
            f"nesnesini {yeni_hedef_id} ile birleştirdi"
        ),
    )
    return mevcut, birlestirme


def _sartlari_hedefe_kopyala(oturum: Session, kaynak: Nesne, hedef: Nesne) -> None:
    """Birleşen nesnenin şartlarını hedefe **kopyalar**; hedefte olan tekrar
    edilmez.

    Kaynağın şart satırları silinmez (2026-09-20 incelemesi, bulgu 5): şart
    kaldırma işlevi zaten yoktur (koruma zayıflatılamaz) ve kaynakta kalan
    ``(şart, değer)`` çifti, kanonik nesnenin tarihsel kimliğini korur.
    """
    hedef_sartlari = {
        s.ozellik_tanimi_id for s in nesne_sartlarini_listele(oturum, hedef.id)
    }
    for sart in nesne_sartlarini_listele(oturum, kaynak.id):
        if sart.ozellik_tanimi_id not in hedef_sartlari:
            oturum.add(
                NesneMukerrerlikSarti(
                    nesne_id=hedef.id,
                    nesne_turu_id=hedef.nesne_turu_id,
                    ozellik_tanimi_id=sart.ozellik_tanimi_id,
                )
            )
    oturum.flush()


def _birlesimleri_kanonige_bagla(
    oturum: Session,
    eski_kanonik_id: int,
    yeni_kanonik_id: int,
    talep: KararTalebi,
    aktor: Aktor,
) -> list[int]:
    """Eski kanonik nesneye bağlı birleşimleri yeni kanonik nesneye bağlar.

    ``N3 → N2`` varken ``N2 → N1`` birleşimi olursa tablo zincire dönerdi.
    Zincir kurulmaz: eski satırların ``kanonik_nesne_id``si ``N1`` yapılır,
    ``hedef_nesne_id`` (kullanıcının o günkü kararı) ve ``karar_talebi_id``
    olduğu gibi kalır; her yeniden bağlama denetim izine bu kararın kimliğiyle
    yazılır. Sonuç: kanonik nesne her zaman tek sıçramada bulunur, karar
    geçmişi kaybolmaz.
    """
    with _yazma_siniri(oturum):
        satirlar = list(
            oturum.execute(
                select(NesneBirlesimi)
                .where(NesneBirlesimi.kanonik_nesne_id == eski_kanonik_id)
                .order_by(NesneBirlesimi.id)
            ).scalars()
        )
        for satir in satirlar:
            satir.kanonik_nesne_id = yeni_kanonik_id
        oturum.flush()
        for satir in satirlar:
            olay_yaz(
                oturum,
                DenetimOlayi.BIRLESIM_YENIDEN_BAGLANDI,
                aktor,
                islem_paketi_id=talep.islem_paketi_id,
                karar_talebi_id=talep.id,
                nesne_id=yeni_kanonik_id,
                ikincil_nesne_id=satir.kaynak_nesne_id,
                gerekce=(
                    f"kanonik nesne {eski_kanonik_id} → {yeni_kanonik_id}; "
                    f"karar hedefi {satir.hedef_nesne_id} değişmedi"
                ),
            )
    return [satir.kaynak_nesne_id for satir in satirlar]


def _acik_talepleri_uzlastir(
    oturum: Session, birlesen_nesne_id: int, talep: KararTalebi, aktor: Aktor
) -> list[KararTalebi]:
    """Birleşen nesneyi gösteren açık **kesin çift** taleplerini hükümsüz kılar.

    Birleşmeden sonra o talepler artık kanonik olmayan bir kimliği anlatır:
    ``N1 ?= N3`` talebi ``N3 → N2`` olduktan sonra fiilen ``N1 ?= N2``dir. Açık
    bırakılırsa üç şey olur: ``AYNI`` cevabı ``BirlestirmeGecersiz`` ile
    reddedilir (kalıcı bekleme), zincirleme denetimin kanonik uçlarla açtığı
    talep aynı soruyu ikinci kez sorar (mükerrer karar) ve iki açık talep aynı
    kanonik çifte düşerse kısmi benzersiz indeks ihlal edilebilir.

    Bu yüzden eski talep terminal ``GECERSIZ`` duruma geçer — ``AYRI`` kararı
    **değildir**, ``karar`` boş kalır ve satır geçmişte durur — ve soru,
    doğruysa, birleşmenin hemen ardından çalışan zincirleme denetimle kanonik
    uçlarla yeniden açılır. İki ucu aynı kanonik nesneye düşen talep yeniden
    açılmaz: tarama nesneyi kendisiyle karşılaştırmaz.

    Yeni bir durum ya da şema gerekmedi: ``GECERSIZ`` zaten "karar verilmeden
    hükümsüz kalan talep" demektir (paket iptalinden beri), burada hükümsüzlük
    nedeni farklıdır ve denetim izinin gerekçesinde yazar.

    Paket bağları çağıranın ``_kanonik_soruyu_koru`` adımıyla korunur.
    Çözümlenmiş adayların gereksiz talepleri ayrı olarak
    ``_cozulmus_aday_taleplerini_kapat`` ile hükümsüz kılınır; çözümlenmemiş
    adayın kesin ucu karar anında kanonik nesneye çevrilir.
    """
    with _yazma_siniri(oturum):
        satirlar = list(
            oturum.execute(
                select(KararTalebi)
                .where(
                    KararTalebi.durum == TalepDurumu.ACIK.value,
                    KararTalebi.kaynak_nesne_id.is_not(None),
                    or_(
                        KararTalebi.kaynak_nesne_id == birlesen_nesne_id,
                        KararTalebi.hedef_nesne_id == birlesen_nesne_id,
                    ),
                )
                .order_by(KararTalebi.id)
            ).scalars()
        )
        simdi = simdi_utc()
        for satir in satirlar:
            satir.durum = TalepDurumu.GECERSIZ.value
            satir.gecersizlik_zamani = simdi
        oturum.flush()
        for satir in satirlar:
            olay_yaz(
                oturum,
                DenetimOlayi.KARAR_TALEBI_GECERSIZ_KALDI,
                aktor,
                islem_paketi_id=satir.islem_paketi_id,
                karar_talebi_id=satir.id,
                gerekce=(
                    f"nesne {birlesen_nesne_id} karar talebi {talep.id} ile "
                    "birleşti; bu talebin ucu artık kanonik değil"
                ),
            )
    return satirlar


def _kokeni_devret(
    oturum: Session, eski: KararTalebi, yeni: KararTalebi, aktor: Aktor
) -> None:
    """Bağımsız kökeni kanonik halefe taşır (2026-09-20 üçüncü turu, bulgu 1).

    Paket kimliklerini aktarmak yetmez: paketten bağımsız doğmuş soruyu ayakta
    tutan şey bir paket değildir, dolayısıyla bütün paketleri iptal edilse de
    düşmemelidir. Halefin **tarihsel açılış paketi değiştirilmez** (geçmiş
    bozulmaz); devredilen yalnız ``bagimsiz_koken`` niteliğidir.
    """
    if not eski.bagimsiz_koken or yeni.bagimsiz_koken:
        return
    with _yazma_siniri(oturum):
        yeni.bagimsiz_koken = True
        oturum.flush()
        olay_yaz(
            oturum,
            DenetimOlayi.KARAR_TALEBI_KOKENI_DEVREDILDI,
            aktor,
            islem_paketi_id=yeni.islem_paketi_id,
            karar_talebi_id=yeni.id,
            gerekce=(
                f"karar talebi {eski.id} paketten bağımsız doğmuştu; köken "
                "kanonik soruya devredildi"
            ),
        )


def _kanonik_soruyu_koru(
    oturum: Session, eski: KararTalebi, aktor: Aktor
) -> KararTalebi | None:
    """Bayat soruyu, eşleşme şartları sonradan değişse bile, cevapsız düşürme.

    Halef zaten açıksa ona bağlanılır; her iki durumda da bağımsız köken
    korunur (``_kokeni_devret``).
    """
    assert eski.kaynak_nesne_id is not None
    kaynak = kanonik_nesneyi_bul(oturum, eski.kaynak_nesne_id)
    hedef = kanonik_nesneyi_bul(oturum, eski.hedef_nesne_id)
    if kaynak == hedef:
        return None
    hedef, kaynak = min(kaynak, hedef), max(kaynak, hedef)
    mevcut = _cift_talebi(oturum, hedef_nesne_id=hedef, kaynak_nesne_id=kaynak)
    if mevcut is not None:
        if mevcut.durum != TalepDurumu.ACIK.value:
            return None  # çift için kullanıcı kararı zaten var
        _kokeni_devret(oturum, eski, mevcut, aktor)
        return mevcut
    yeni = _talep_ac(
        oturum,
        aktor,
        islem_paketi_id=eski.islem_paketi_id,
        nesne_turu_id=eski.nesne_turu_id,
        hedef_nesne_id=hedef,
        kaynak_nesne_id=kaynak,
        eslesen_ozellik_tanimi_id=eski.eslesen_ozellik_tanimi_id,
    )
    _kokeni_devret(oturum, eski, yeni, aktor)
    return yeni


def _aday_kanonik_karari(
    oturum: Session, aday_nesne_id: int, kanonik_id: int
) -> KararTalebi | None:
    """Bu aday ve bu kanonik nesne için kullanıcının verdiği karar; yoksa ``None``."""
    for cozulmus in oturum.scalars(
        select(KararTalebi)
        .where(
            KararTalebi.aday_nesne_id == aday_nesne_id,
            KararTalebi.durum == TalepDurumu.COZULDU.value,
        )
        .order_by(KararTalebi.id)
    ):
        if kanonik_nesneyi_bul(oturum, cozulmus.hedef_nesne_id) == kanonik_id:
            return cozulmus
    return None


def _aday_talepleri_uzlastir(
    oturum: Session, karar_talebi: KararTalebi, aktor: Aktor
) -> list[KararTalebi]:
    """Aynı ``(aday, güncel kanonik hedef)`` için tek açık soru bırakır.

    Birleşmeler adayın iki ayrı sorusunu aynı kanonik nesneye düşürebilir;
    ikisini de açık bırakmak kullanıcıdan gereksiz ikinci bir karar ister ve
    paketi boşuna bekletir (2026-09-20 üçüncü turu, bulgu 3). Üç durumda soru
    gereksizdir:

    * aday zaten o kanonik nesneye çözümlenmiştir,
    * o kanonik nesne için kullanıcının verdiği bir karar (``AYNI`` ya da
      ``AYRI``) zaten vardır — tarihsel kimlik üzerinden verilmiş olsa bile,
    * aynı çift için daha eski bir açık soru vardır.

    Gereksiz soru gerekçeli ``GECERSIZ`` olur; kullanıcı adına ``AYNI`` /
    ``AYRI`` **yazılmaz**. Uzlaştırma çözümlenmiş adaylarla sınırlı değildir.

    Paket bağı taşımaya gerek yoktur: aday sorusu adayın kendi paketine aittir
    ve o paket her iki soruda da aynıdır (paket bağı yalnız kesin çift
    sorularında paylaşılır, ``nesneyi_denetle`` ve ``_kanonik_soruyu_koru``).
    Aday sorusu ileride paylaşılabilir olursa düşen sorunun bağları korunana
    aktarılmalıdır.
    """
    acik = list(
        oturum.scalars(
            select(KararTalebi)
            .where(
                KararTalebi.durum == TalepDurumu.ACIK.value,
                KararTalebi.aday_nesne_id.is_not(None),
            )
            .order_by(KararTalebi.id)
        )
    )
    korunan: dict[tuple[int, int], KararTalebi] = {}
    gecersiz: list[KararTalebi] = []
    for talep in acik:
        aday_id = talep.aday_nesne_id
        assert aday_id is not None
        kanonik = kanonik_nesneyi_bul(oturum, talep.hedef_nesne_id)
        onceki = korunan.get((aday_id, kanonik))
        if adayin_kesin_nesnesi(oturum, aday_id) == kanonik:
            neden = "aday zaten aynı kanonik nesneye çözümlü"
        elif (karar := _aday_kanonik_karari(oturum, aday_id, kanonik)) is not None:
            neden = f"karar talebi {karar.id} aynı kanonik nesne için cevaplanmış"
        elif onceki is not None:
            neden = f"karar talebi {onceki.id} aynı kanonik nesneyi soruyor"
        else:
            korunan[(aday_id, kanonik)] = talep
            continue
        with _yazma_siniri(oturum):
            talep.durum = TalepDurumu.GECERSIZ.value
            talep.gecersizlik_zamani = simdi_utc()
            oturum.flush()
            olay_yaz(
                oturum,
                DenetimOlayi.KARAR_TALEBI_GECERSIZ_KALDI,
                aktor,
                islem_paketi_id=talep.islem_paketi_id,
                karar_talebi_id=talep.id,
                aday_nesne_id=aday_id,
                gerekce=f"karar talebi {karar_talebi.id}: {neden}",
            )
        gecersiz.append(talep)
    return gecersiz


def _nesneleri_birlestir(
    oturum: Session,
    talep: KararTalebi,
    kaynak_nesne_id: int,
    hedef_nesne_id: int,
    aktor: Aktor,
) -> _Birlestirme:
    """İki kesin nesneyi birleştirir: ilişkiler hedefe taşınır, şartlar hedefe
    kopyalanır, kaynak ``kapali`` olur ve kalıcı birleşim kaydı yazılır.

    Uçlar çağırandan gelir: kesin çift talebinde talebin kendi uçlarıdır, aday
    talebinde ise ``Z = X`` ve ``Z = Y`` kararlarının doğurduğu ``X = Y``
    çiftidir. İkisi de kanonik nesne olmalıdır; birleşmiş bir nesne ne kaynak
    ne hedef olabilir.

    **Geçmiş ``AYRI`` kararları korunur.** Birleşecek iki kanonik kümenin
    herhangi iki üyesi (önceki birleşmelerle kümeye katılanlar dahil) arasında
    kullanıcının verdiği bir ``AYRI`` kararı varsa birleşme ``KararCelismesi``
    ile reddedilir. Eski karar silinmez, değiştirilmez, bağlantısı kopmaz;
    reddedilen işlem hiçbir kalıcı değişiklik bırakmaz.

    Bütün adımlar çağıranın transaction'ı içindedir; ilişki devrinde bir
    hiyerarşi ya da çevrim ihlali çıkarsa hiçbiri uygulanmaz.
    """
    kaynak = nesne_getir(oturum, kaynak_nesne_id)
    hedef = nesne_getir(oturum, hedef_nesne_id)
    for nesne in (kaynak, hedef):
        if nesne_birlesimini_bul(oturum, nesne.id) is not None:
            raise BirlestirmeGecersiz(
                f"nesne {nesne.id} zaten başka bir nesneye birleştirilmiş; "
                "birleşim zinciri kurulmaz."
            )
    kaynak_kimlikleri = _kimlik_gecmisi_idleri(oturum, kaynak.id)
    hedef_kimlikleri = _kimlik_gecmisi_idleri(oturum, hedef.id)
    celisen = _ayri_karari(oturum, kaynak_kimlikleri, hedef_kimlikleri)
    if celisen is not None:
        raise KararCelismesi(
            f"nesne {kaynak.id} ile {hedef.id} birleştirilemez: karar talebi "
            f"{celisen.id} ile {celisen.hedef_nesne_id} ve "
            f"{celisen.kaynak_nesne_id} için 'ayrı' denmişti ve bu nesneler "
            f"bugün {hedef.id} ile {kaynak.id} kimliklerinin geçmişinde. "
            "Çelişkiyi çekirdek çözmez: kullanıcı kararı silinmez ya da "
            "ezilmez; bu talebe 'ayrı' deyin ya da eski kararı önce kendiniz "
            "ele alın."
        )
    devir = iliskileri_devret(oturum, kaynak.id, hedef.id)
    kayit_devri = kayit_baglarini_devret(
        oturum, kaynak.id, hedef.id, aktor, islem_paketi_id=talep.islem_paketi_id
    )
    with _yazma_siniri(oturum):
        _sartlari_hedefe_kopyala(oturum, kaynak, hedef)
    yasam_durumunu_degistir(oturum, kaynak.id, YasamDurumu.KAPALI)
    with _yazma_siniri(
        oturum,
        NESNE_BIRLESIMI,
        BirlestirmeGecersiz,
        f"nesne {kaynak.id} için birleşim kaydı zaten var.",
    ):
        birlesim = NesneBirlesimi(
            kaynak_nesne_id=kaynak.id,
            hedef_nesne_id=hedef.id,
            kanonik_nesne_id=hedef.id,
            nesne_turu_id=talep.nesne_turu_id,
            karar_talebi_id=talep.id,
            olusturma_zamani=simdi_utc(),
            aktor_turu=aktor.tur.value,
            aktor_kimligi=aktor.kimlik.strip(),
        )
        oturum.add(birlesim)
        oturum.flush()
        olay_yaz(
            oturum,
            DenetimOlayi.NESNE_BIRLESTIRILDI,
            aktor,
            islem_paketi_id=talep.islem_paketi_id,
            karar_talebi_id=talep.id,
            nesne_id=hedef.id,
            ikincil_nesne_id=kaynak.id,
            gerekce=(
                f"taşınan {devir.tasinan}, birleşen {devir.birlesen}, "
                f"düşen {devir.dusen}; kayıt bağı taşınan "
                f"{kayit_devri.tasinan}, birleşen {kayit_devri.birlesen}"
            ),
        )
    _birlesimleri_kanonige_bagla(oturum, kaynak.id, hedef.id, talep, aktor)
    gecersiz = _acik_talepleri_uzlastir(oturum, kaynak.id, talep, aktor)
    return _Birlestirme(birlesim, devir, tuple(gecersiz))


def _zincirleme_denetle(
    oturum: Session,
    hedef_nesne_id: int,
    islem_paketi_id: int | None,
    karar_talebi: KararTalebi,
    aktor: Aktor,
) -> list[KararTalebi]:
    """Birleşimden sonra hedefin hiyerarşik çocuklarını yeniden denetler.

    Birleşim alt seviyede yeni eşleşme doğurabilir (iki üst aynıysa altlarındaki
    aynı kimlikli nesneler artık yan yanadır). Hedefin kendisi de yeniden
    taranır: kaynağın şartlarını devraldığından artık başka bir nesneyle
    eşleşebilir. Döngü olamaz: yeni talep yalnız daha önce talebi olmayan çift
    için açılır ve bu adım birleştirme yapmaz.

    **Bağımsız köken bir kuşak sonra düşmez** (2026-09-20 beşinci inceleme
    turu). Burada sorulan sorular ``karar_talebi``nin kararından doğar; o soru
    paketten bağımsızsa çocukları da bağımsızdır. Devir olmadan sonuç paketin
    ne zaman iptal edildiğine bağlı kalıyordu: karardan **sonra** iptal
    edilirse çocuk soru pakete ait sayılıp cevapsız ``gecersiz`` oluyor,
    karardan **önce** iptal edilirse (``karar_ver`` paketsiz karara düşer)
    bağımsız doğup açık kalıyordu. Aynı soru, aynı karar, farklı sonuç.

    Devir **açılan ve dokunulan** açık taleplerin ikisini de kapsar (2026-09-20
    altıncı tur). Beşinci turda yalnız yeni açılan talepler devralıyordu; alt
    soru başka bir paket tarafından daha önce açılmışsa tarama onu yeniden
    soruyor ama kökenini almıyordu, paketler iptal edilince soru cevapsız
    ``gecersiz`` oluyordu. Bu, ``_kanonik_soruyu_koru``nun kuralıyla da
    çelişiyordu: orada köken mevcut açık halefe zaten devrediliyor. Halefin
    tarihsel açılış paketi her iki yolda da korunur (``_kokeni_devret``).
    """
    cocuk_idleri = list(
        oturum.execute(
            select(NesneIliskisi.kaynak_nesne_id)
            .join(
                HiyerarsiKurali,
                HiyerarsiKurali.iliski_tanimi_id == NesneIliskisi.iliski_tanimi_id,
            )
            .where(NesneIliskisi.hedef_nesne_id == hedef_nesne_id)
            .distinct()
            .order_by(NesneIliskisi.kaynak_nesne_id)
        ).scalars()
    )
    taramalar = [_nesneyi_tara(oturum, hedef_nesne_id, aktor, islem_paketi_id)]
    taramalar.extend(
        _nesneyi_tara(oturum, cocuk_id, aktor, islem_paketi_id)
        for cocuk_id in cocuk_idleri
    )
    yeni: list[KararTalebi] = [t for tarama in taramalar for t in tarama.acilan]
    for tarama in taramalar:
        for soru in (*tarama.acilan, *tarama.dokunulan):
            _kokeni_devret(oturum, karar_talebi, soru, aktor)
    return yeni


def paketin_adaylarini_denetle(
    oturum: Session, islem_paketi_id: int, aktor: Aktor
) -> list[KararTalebi]:
    """Paketteki bütün aday nesneleri sırayla denetler.

    Bütün adayların yazmaları **tek bir dış SAVEPOINT** içindedir (2026-09-20
    beşinci inceleme turu). Tekil ``adayi_denetle`` üçüncü turda bu sınıra
    alınmıştı ama onu çağıran bu işlev alınmamıştı: ikinci aday taranırken hata
    çıkarsa ilk adayın açtığı talepler, denetim izleri ve paketin ``bekliyor``
    durumu, çağıran hatayı yakalayıp dış transaction'ı commit ettiğinde kalıcı
    oluyordu. Artık ya bütün adaylar taranır ya hiçbiri.

    İptal paket **baştan** reddedilir (2026-09-20 altıncı tur). Önceden durum
    denetimi yoktu: paketin adayı varsa ilk ``adayi_denetle`` çağrısı
    ``PaketDurumuGecersiz`` veriyor, adayı yoksa döngü hiç dönmediği için
    sessizce ``[]`` dönüyordu. Aynı geçersiz durum iki farklı davranış
    üretmesin diye denetim ``adayi_denetle`` ile aynı mesaja bağlandı.
    """
    paket = paket_getir(oturum, islem_paketi_id)
    if paket.durum == PaketDurumu.IPTAL.value:
        raise PaketDurumuGecersiz(
            f"işlem paketi {paket.id} iptal; mükerrerlik denetimi yapılmaz."
        )
    aday_idleri = list(
        oturum.execute(
            select(AdayNesne.id)
            .where(AdayNesne.islem_paketi_id == paket.id)
            .order_by(AdayNesne.id)
        ).scalars()
    )
    talepler: list[KararTalebi] = []
    with _yazma_siniri(oturum):  # dış SAVEPOINT: ya hepsi ya hiçbiri
        for aday_id in aday_idleri:
            talepler.extend(adayi_denetle(oturum, aday_id, aktor))
    return talepler


def bekleyen_paketler(oturum: Session) -> list[IslemPaketi]:
    """Açık karar talebi yüzünden bekleyen paketler, kimlik sırasıyla.

    Açık soru şartı gerçekten aranır (2026-09-20 altıncı tur). Önceden yalnız
    ``durum == bekliyor`` bakılıyordu; ``taslak_islemleri.paketi_beklet`` açık
    soru olmadan da çağrılabildiği için elle duraklatılmış paketler de bu
    listeye giriyor, işlev adının ve açıklamasının verdiği sözü tutmuyordu.
    Elle duraklatılmış paket bu listede yoktur; ``paketleri_listele`` ile
    duruma göre sorgulanır.
    """
    acilis_paketi = select(KararTalebi.islem_paketi_id).where(
        KararTalebi.durum == TalepDurumu.ACIK.value,
        KararTalebi.islem_paketi_id.is_not(None),
    )
    baglanan_paket = (
        select(KararTalebiPaketi.islem_paketi_id)
        .join(KararTalebi, KararTalebi.id == KararTalebiPaketi.karar_talebi_id)
        .where(KararTalebi.durum == TalepDurumu.ACIK.value)
    )
    return list(
        oturum.execute(
            select(IslemPaketi)
            .where(
                IslemPaketi.durum == PaketDurumu.BEKLIYOR.value,
                or_(
                    IslemPaketi.id.in_(acilis_paketi),
                    IslemPaketi.id.in_(baglanan_paket),
                ),
            )
            .order_by(IslemPaketi.id)
        ).scalars()
    )
