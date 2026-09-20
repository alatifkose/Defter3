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
(servis ve bileşik dış anahtar).

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
başına paketi canlandırmaz). ``IPTAL`` terminaldir: iptal paketin talebine
karar verilmez, paket diriltilmez; paketin açık talepleri iptal anında
terminal ``GECERSIZ`` duruma geçer (``taslak_islemleri.paketi_iptal_et``).
``GECERSIZ`` bir ``AYRI`` kararı değildir — ``karar`` boş kalır, satır
geçmişte durur — ama açık talep sayılmaz: aynı çift başka bir pakette yeniden
değerlendirilebilir, yoksa iptal edilen bir paket o çifti sonsuza kadar
kilitlerdi. Bekleyen karar yalnız ilgili paketi ve şüpheli ucu durdurur;
sistem genelinde kilit yoktur.

**Kararı yalnız kullanıcı verir.** ``karar_ver`` aktörü ``KULLANICI``
olmayan çağrıyı ``KararKaynagiGecersiz`` ile reddeder ve hiçbir şey yazmaz;
veritabanında da ``karar_aktor_turu`` yalnız ``kullanici`` olabilir. Ajan ve
sistem tarama yapar, şüphe açar, denetim olayı üretir; kullanıcı yerine karar
veremez. Güvenli otomatik karar motoru (Aşama 4.9) henüz yoktur.

**Karar.** ``AYRI`` şüpheyi kapatır. ``AYNI`` çözümlemeyi / birleştirmeyi tek
transaction içinde uygular. ``KARARSIZ`` şüpheyi çözmez: talep açık kalır,
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
durdurulmaz). ``gecersiz`` talep bu denetimde sayılmaz.

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

from sqlalchemy import and_, func, select, tuple_, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from defteriki.cekirdek.denetim_islemleri import AZAMI_GEREKCE_UZUNLUGU, olay_yaz
from defteriki.cekirdek.denetim_tablolari import Aktor, AktorTuru, DenetimOlayi
from defteriki.cekirdek.mukerrerlik_tablolari import (
    KARAR_TALEBI,
    NESNE_BIRLESIMI,
    AdayNesneCozumlemesi,
    AdayNesneMukerrerlikSarti,
    Karar,
    KararTalebi,
    NesneBirlesimi,
    NesneMukerrerlikSarti,
    TalepDurumu,
)
from defteriki.cekirdek.nesne_islemleri import (
    DevirOzeti,
    iliskileri_devret,
    nesne_getir,
    yasam_durumunu_degistir,
)
from defteriki.cekirdek.nesne_tablolari import Nesne, NesneIliskisi, NesneOzelligi
from defteriki.cekirdek.tanim_tablolari import (
    HiyerarsiKurali,
    OzellikTanimi,
    YasamDurumu,
    simdi_utc,
)
from defteriki.cekirdek.taslak_islemleri import (
    PaketDurumuGecersiz,
    aday_nesne_getir,
    benzersizlik_ihlali_mi,
    kilit_cakismasi_mi,
    paket_getir,
    paketi_beklet,
    paketi_devam_et,
)
from defteriki.cekirdek.taslak_tablolari import (
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
    """Zincirleme denetimin açtığı yeni talepler."""


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
        sorgu = sorgu.where(KararTalebi.islem_paketi_id == islem_paketi_id)
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


def _acik_talep_sayisi(oturum: Session, islem_paketi_id: int) -> int:
    return int(
        oturum.execute(
            select(func.count())
            .select_from(KararTalebi)
            .where(
                KararTalebi.islem_paketi_id == islem_paketi_id,
                KararTalebi.durum == TalepDurumu.ACIK.value,
            )
        ).scalar_one()
    )


# --- şart seçimi ----------------------------------------------------------------------


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
    """
    nesne = nesne_getir(oturum, nesne_id)
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
    """Aday nesneye mükerrerlik şartı ekler (kesin nesneyle aynı kurallar)."""
    aday = aday_nesne_getir(oturum, aday_nesne_id)
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


def _talep_var_mi(
    oturum: Session,
    *,
    hedef_nesne_id: int,
    aday_nesne_id: int | None = None,
    kaynak_nesne_id: int | None = None,
) -> bool:
    """Bu çift için (açık ya da çözülmüş) talep var mı? Çözülmüş "ayrı" kararı
    aynı çifti yeniden durdurmaz; açık talep ikinci kez açılmaz.

    ``gecersiz`` talepler sayılmaz: paketi iptal edildiği için hükümsüz kalan
    bir talep kullanıcı kararı taşımaz, dolayısıyla aynı çiftin başka bir
    pakette değerlendirilmesini engelleyemez.
    """
    sorgu = select(KararTalebi.id).where(
        KararTalebi.hedef_nesne_id == hedef_nesne_id,
        KararTalebi.durum != TalepDurumu.GECERSIZ.value,
    )
    if aday_nesne_id is not None:
        sorgu = sorgu.where(KararTalebi.aday_nesne_id == aday_nesne_id)
    else:
        sorgu = sorgu.where(KararTalebi.kaynak_nesne_id == kaynak_nesne_id)
    return oturum.execute(sorgu).first() is not None


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
        )
        oturum.add(talep)
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
    """
    aday = aday_nesne_getir(oturum, aday_nesne_id)
    paket = paket_getir(oturum, aday.islem_paketi_id)
    if paket.durum == PaketDurumu.IPTAL.value:
        raise PaketDurumuGecersiz(
            f"işlem paketi {paket.id} iptal; mükerrerlik denetimi yapılmaz."
        )
    eslesmeler = _eslesen_nesneler(
        oturum,
        aday.nesne_turu_id,
        _aday_degerleri(oturum, aday.id),
        {s.ozellik_tanimi_id for s in aday_sartlarini_listele(oturum, aday.id)},
        haric=set(),
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
        if not _talep_var_mi(oturum, hedef_nesne_id=nesne_id, aday_nesne_id=aday.id)
    ]
    _paket_durumunu_esitle(oturum, paket.id, aktor)
    return talepler


def nesneyi_denetle(
    oturum: Session,
    nesne_id: int,
    aktor: Aktor,
    islem_paketi_id: int | None = None,
) -> list[KararTalebi]:
    """Kesin nesneyi diğer kesin nesnelere karşı denetler.

    Çift normalleştirilir: küçük kimlikli (önce oluşturulan) nesne hedeftir ve
    ``AYNI`` kararında korunur. Birleştirilmiş nesneler taramaya girmez.
    """
    nesne = nesne_getir(oturum, nesne_id)
    if nesne_birlesimini_bul(oturum, nesne.id) is not None:
        return []
    kimlik_idleri = _kimlik_gecmisi_idleri(oturum, nesne.id)
    eslesmeler = _eslesen_nesneler(
        oturum,
        nesne.nesne_turu_id,
        _kimlik_degerleri(oturum, kimlik_idleri),
        _kimlik_sartlari(oturum, kimlik_idleri),
        haric={nesne.id},
    )
    talepler: list[KararTalebi] = []
    for karsi_id in sorted(eslesmeler):
        hedef_id, kaynak_id = min(nesne.id, karsi_id), max(nesne.id, karsi_id)
        if _talep_var_mi(oturum, hedef_nesne_id=hedef_id, kaynak_nesne_id=kaynak_id):
            continue
        talepler.append(
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
    return talepler


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
    birleştirmeyi (kesin → kesin) aynı transaction içinde uygular; herhangi
    bir doğrulama düşerse hiçbiri kalmaz. ``KARARSIZ`` talebi açık bırakır.
    Kapalı talebe ikinci karar ``KararTalebiKapali`` verir; iki bağlantı aynı
    anda cevaplarsa yalnız biri kazanır.
    """
    karar = Karar(karar)
    _karar_kaynagini_dogrula(aktor)
    _gerekceyi_dogrula(karar, gerekce)
    talep = karar_talebi_getir(oturum, karar_talebi_id)
    if talep.durum == TalepDurumu.GECERSIZ.value:
        raise KararTalebiKapali(
            f"karar talebi {talep.id} geçersiz: paketi iptal edildiği için "
            "hükümsüz kaldı. Geçersizlik bir kullanıcı kararı değildir ve talep "
            "yeniden karara açılmaz; aynı çift yeni bir pakette değerlendirilir."
        )
    if talep.durum != TalepDurumu.ACIK.value:
        raise KararTalebiKapali(
            f"karar talebi {talep.id} {talep.durum}; ikinci karar uygulanmaz."
        )
    paket_id = talep.islem_paketi_id
    if paket_id is not None:
        paket = paket_getir(oturum, paket_id)
        if paket.durum == PaketDurumu.IPTAL.value:
            raise PaketDurumuGecersiz(
                f"işlem paketi {paket.id} iptal (terminal); talebine karar "
                "verilmez ve paket diriltilmez."
            )

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
    birlesim: NesneBirlesimi | None = None
    devir: DevirOzeti | None = None
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
        cozumleme, birlesim, devir = _adayi_cozumle(oturum, talep, aktor)
        if birlesim is not None:
            yeni_talepler = tuple(
                _zincirleme_denetle(oturum, birlesim.hedef_nesne_id, paket_id, aktor)
            )
    else:
        kaynak_id = talep.kaynak_nesne_id
        assert kaynak_id is not None  # kontrol kısıtı: uçlardan tam biri dolu
        birlesim, devir = _nesneleri_birlestir(
            oturum, talep, kaynak_id, talep.hedef_nesne_id, aktor
        )
        yeni_talepler = tuple(
            _zincirleme_denetle(oturum, talep.hedef_nesne_id, paket_id, aktor)
        )

    durum = (
        None if paket_id is None else _paket_durumunu_esitle(oturum, paket_id, aktor)
    )
    return KararSonucu(
        talep=talep,
        cozuldu=True,
        paket_durumu=durum,
        cozumleme=cozumleme,
        birlesim=birlesim,
        devir=devir,
        yeni_talepler=yeni_talepler,
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
    oturum: Session, hedef_nesne_id: int, kaynak_nesne_id: int
) -> KararTalebi | None:
    """Bu kesin çift için kullanıcının verdiği ``AYRI`` kararı; yoksa ``None``."""
    return (
        oturum.execute(
            select(KararTalebi)
            .where(
                KararTalebi.hedef_nesne_id == hedef_nesne_id,
                KararTalebi.kaynak_nesne_id == kaynak_nesne_id,
                KararTalebi.karar == Karar.AYRI.value,
            )
            .order_by(KararTalebi.id)
        )
        .scalars()
        .first()
    )


def _adayi_cozumle(
    oturum: Session, talep: KararTalebi, aktor: Aktor
) -> tuple[AdayNesneCozumlemesi, NesneBirlesimi | None, DevirOzeti | None]:
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

    Kullanıcı o iki kesin nesne için daha önce ``AYRI`` demişse çelişki
    sessizce çözülmez: ``KararCelismesi`` yükselir, işlem tamamen geri alınır,
    talep açık kalır. Eski kullanıcı kararını ezmek de yeni kullanıcı kararını
    yok saymak da çekirdeğin işi değildir; kullanıcı ya bu talebe ``AYRI`` der
    ya da iki kesin nesneyi kendisi ele alır.
    """
    aday_id = talep.aday_nesne_id
    assert aday_id is not None  # kontrol kısıtı: uçlardan tam biri dolu
    hedef_id = kanonik_nesneyi_bul(oturum, talep.hedef_nesne_id)
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
        return cozumleme, None, None

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
        return mevcut, None, None

    yeni_hedef_id, kaynak_id = min(onceki_id, hedef_id), max(onceki_id, hedef_id)
    celisen = _ayri_karari(oturum, yeni_hedef_id, kaynak_id)
    if celisen is not None:
        raise KararCelismesi(
            f"aday nesne {aday_id} hem {onceki_id} hem {hedef_id} kesin "
            f"nesnesi kabul edilirse bu iki nesne aynı olur; oysa karar talebi "
            f"{celisen.id} ile {yeni_hedef_id} ve {kaynak_id} için "
            "'ayrı' denmişti. Çelişkiyi çekirdek çözmez: bu talebe 'ayrı' deyin "
            "ya da iki kesin nesneyi önce kendiniz ele alın."
        )
    birlesim, devir = _nesneleri_birlestir(
        oturum, talep, kaynak_id, yeni_hedef_id, aktor
    )
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
    return mevcut, birlesim, devir


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


def _nesneleri_birlestir(
    oturum: Session,
    talep: KararTalebi,
    kaynak_nesne_id: int,
    hedef_nesne_id: int,
    aktor: Aktor,
) -> tuple[NesneBirlesimi, DevirOzeti]:
    """İki kesin nesneyi birleştirir: ilişkiler hedefe taşınır, şartlar hedefe
    kopyalanır, kaynak ``kapali`` olur ve kalıcı birleşim kaydı yazılır.

    Uçlar çağırandan gelir: kesin çift talebinde talebin kendi uçlarıdır, aday
    talebinde ise ``Z = X`` ve ``Z = Y`` kararlarının doğurduğu ``X = Y``
    çiftidir. İkisi de kanonik nesne olmalıdır; birleşmiş bir nesne ne kaynak
    ne hedef olabilir.

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
    devir = iliskileri_devret(oturum, kaynak.id, hedef.id)
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
                f"düşen {devir.dusen}"
            ),
        )
    _birlesimleri_kanonige_bagla(oturum, kaynak.id, hedef.id, talep, aktor)
    return birlesim, devir


def _zincirleme_denetle(
    oturum: Session, hedef_nesne_id: int, islem_paketi_id: int | None, aktor: Aktor
) -> list[KararTalebi]:
    """Birleşimden sonra hedefin hiyerarşik çocuklarını yeniden denetler.

    Birleşim alt seviyede yeni eşleşme doğurabilir (iki üst aynıysa altlarındaki
    aynı kimlikli nesneler artık yan yanadır). Hedefin kendisi de yeniden
    taranır: kaynağın şartlarını devraldığından artık başka bir nesneyle
    eşleşebilir. Döngü olamaz: yeni talep yalnız daha önce talebi olmayan çift
    için açılır ve bu adım birleştirme yapmaz.
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
    yeni: list[KararTalebi] = list(
        nesneyi_denetle(oturum, hedef_nesne_id, aktor, islem_paketi_id)
    )
    for cocuk_id in cocuk_idleri:
        yeni.extend(nesneyi_denetle(oturum, cocuk_id, aktor, islem_paketi_id))
    return yeni


def paketin_adaylarini_denetle(
    oturum: Session, islem_paketi_id: int, aktor: Aktor
) -> list[KararTalebi]:
    """Paketteki bütün aday nesneleri sırayla denetler (kolaylık işlevi)."""
    paket = paket_getir(oturum, islem_paketi_id)
    aday_idleri = list(
        oturum.execute(
            select(AdayNesne.id)
            .where(AdayNesne.islem_paketi_id == paket.id)
            .order_by(AdayNesne.id)
        ).scalars()
    )
    talepler: list[KararTalebi] = []
    for aday_id in aday_idleri:
        talepler.extend(adayi_denetle(oturum, aday_id, aktor))
    return talepler


def bekleyen_paketler(oturum: Session) -> list[IslemPaketi]:
    """Açık karar talebi yüzünden bekleyen paketler, kimlik sırasıyla."""
    return list(
        oturum.execute(
            select(IslemPaketi)
            .where(IslemPaketi.durum == PaketDurumu.BEKLIYOR.value)
            .order_by(IslemPaketi.id)
        ).scalars()
    )
