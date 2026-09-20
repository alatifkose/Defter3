"""İşlem paketi ve taslak (aday) verinin servisleri (Aşama 4.5).

**Yazmak ≠ kaydetmek.** Dış okuyucunun belgeden çıkarıp sisteme yazdığı
bilgi bir *işlem paketi* altında *taslak* olarak yaşar: aday nesne, aday
özellik, aday ilişki, aday kayıt ve kayıt ↔ nesne bağı. Bunlar kesin dünyaya
(``nesne``, ``nesne_ozelligi``, ``nesne_iliskisi``; ileride kesin kayıt) hiç
girmez; tablolar fiziksel olarak ayrıdır (``taslak_tablolari``) ve bu modül
kesin nesne tablolarını import etmez. Kesin kaydetme (paketi kesinleştirme,
tamlık kapısı, atomik finalizasyon) Aşama 4.8'in işidir; burada yoktur.

**Paket yaşam döngüsü** (``PaketDurumu``)::

    CALISIYOR → BEKLIYOR → CALISIYOR      (beklet / devam et)
    CALISIYOR → IPTAL,  BEKLIYOR → IPTAL  (iptal; terminal)

Paket yalnız ``tamamlandi`` durumundaki okumadan oluşturulur (``basladi``
okuma için ``OkumaDurumuGecersiz``). Paket durumu yazma yetkisini belirler:
aday veriyi değiştiren her servis paketi merkezi ``_yazilabilir_paket`` ile
denetler; yalnız ``calisiyor`` pakette yazılır. ``bekliyor`` paket
sorgulanır, okunur, devam ettirilir ya da iptal edilir ama içeriği
değişmez; ``iptal`` paket sorgulanır ve okunur, değiştirilemez, devam
ettirilemez. Devam edildiğinde aynı paket aynı taslaklarla sürer; yeni paket
açılıp içerik kopyalanmaz. İptal fiziksel silme değildir: hiçbir aday satır,
kaynak, okuma, belge ya da arşiv dosyası silinmez; paket ve içeriği
sorgulanabilir kalır. Durum geçişi koşullu güncellemedir (``UPDATE ... WHERE
durum = eski``): aynı bağlantıda araya giren başka bir değişiklik satır
etkilemez ve ``PaketDurumuGecersiz`` verir.

**Eşzamanlı yazma sözleşmesi** (2026-09-19 incelemesi; iki bağlantılı gerçek
yarış testleriyle kanıtlanır). Bu servisler önce okur (SQLite WAL anlık
görüntüsü), sonra yazar. İki bağımsız bağlantı aynı satırı ya da aynı paketi
aynı anda değiştirmeye kalkarsa SQLite tam olarak birini yazdırır; diğeri
yazma anında kilit / anlık görüntü çakışması (``database is locked`` /
``busy``; ``SQLITE_BUSY_SNAPSHOT`` için busy handler çağrılmaz) ya da
yarışan ilk yazımda benzersizlik ihlali alır. Bu ham hatalar servis
sözleşmesi değildir; her yazma tek bir sınırdan geçer (``_yazma_siniri``) ve
**dar** eşlenir:

* kilit / anlık görüntü çakışması (``OperationalError``, metinde ``locked``
  ya da ``busy``) → ``TaslakYazmaCakismasi``;
* işlemin kendi tablosundaki benzersizlik ihlali (``IntegrityError``,
  ``UNIQUE constraint failed: <tablo>.``) → işlemin anlamına göre: aday
  ilişki ve kayıt-nesne bağı için ``MukerrerAday`` (satır zaten var), aday
  özelliğin ilk yazımı için ``TaslakYazmaCakismasi`` (yarışan iki ilk yazım;
  "son yazan kazanır" icat edilmez);
* başka her veritabanı hatası (dış anahtar, kontrol kısıtı, başka tablonun
  benzersizliği, disk / dosya hataları) olduğu gibi yükselir.

``TaslakYazmaCakismasi`` alan çağıranın işlemi artık yazamaz (anlık görüntü
eskidir): işlemi geri alır ve **yeni işlemde** yeniden dener; yeniden
denemede ön denetim güncel veriyi görür ve olağan sonucu verir (mükerrer ise
``MukerrerAday``, paket artık ``calisiyor`` değilse ``PaketDurumuGecersiz``,
değilse yazma başarılı). Yeniden deneme çağıranındır; serviste retry döngüsü
yoktur. Paket durum geçişi ile taslak yazımı yarışırsa da tam biri yazar:
ya taslak önce yazılır sonra durum değişir, ya durum önce değişir ve taslak
yazımı ``TaslakYazmaCakismasi`` (yeniden denemede ``PaketDurumuGecersiz``)
alır; yarım satır ve terminal / bekleyen pakete sessiz yazma yoktur.

**Taslak eksik olabilir, yapısal olarak anlamsız olamaz.** Aday nesne zorunlu
özelliği ya da zorunlu üst bağlantısı olmadan var olabilir; aday kayıt
içeriği eksik, kayıt-nesne bağı henüz kurulmamış olabilir. Buna karşılık
olmayan tanıma referans, başka türün özelliği, yanlış veri tipi, ilişki
tanımına uymayan kaynak/hedef türü ya da sürüm, başka paketin adayını
bağlamak ve başka okumanın kaynağını bağlamak reddedilir (servis sözleşmesi;
aynı ihlaller ``taslak_tablolari`` bileşik dış anahtarları ve
benzersizlikleriyle ham SQL'e karşı da reddedilir). Hiyerarşi sayımları,
çevrim, mükerrer nesne arama, zorunlu özellik tamlığı ve kayıt alanı
doğrulaması bu aşamada aranmaz. Aday nesne oluşturmak tanım sürümünü
kilitlemez; kilit kesin nesneyle (4.3) ve kesinleştirmeyle (4.8) ilgilidir.

**Provenance.** Paket ``okuma_id`` taşır; belge ``okuma → belge`` zincirinden
bulunur (``paket_belgesi``). Aday nesne ve aday kayıt isteğe bağlı bir
``Kaynak`` satırına bağlanabilir; kaynak paketin okumasına ait olmak zorundadır
(``PaketUyusmazligi``; veritabanında ``(kaynak_id, okuma_id)`` bileşik dış
anahtar). Kaynak kimliği JSON içine değil gerçek dış anahtara yazılır. Aday
özellik ve aday ilişki bu aşamada ayrı kaynak taşımaz; provenance nesne /
kayıt düzeyinde ve en azından paket (okuma) düzeyindedir.

**Taslak silme.** Çalışan pakette aday nesne, ilişki, kayıt ve bağ
kaldırılabilir. Aday nesnenin kendi özellikleri onun parçasıdır ve nesneyle
birlikte silinir; aday nesne bir aday ilişkide ya da kayıt-nesne bağında
kullanılıyorsa silme açıkça reddedilir (``AdayKullanimda``), sessiz cascade
yoktur. Aday kaydın kendi kayıt-nesne bağları kaydın ekidir ve kayıtla
birlikte silinir; bağlı aday nesneler kalır. Aday özellik, zorunlu olsa da,
silinebilir (tamlık 4.8'de aranır).

**İşlem sınırı ve hata atomikliği** 4.1 / 4.3 kuralıdır: her servis açık bir
``Session`` alır, çağıran ``Veritabani.islem`` transaction'ının sahibidir,
burada ``commit`` / dış ``rollback`` yoktur; ``paket_olustur`` dahil hiçbir
servis kendi işlemini açmaz. Her yazma işlevi önce doğrular, sonra kendi
SAVEPOINT'i içinde yazar (``Session.begin_nested``); başarısız çağrı hatası
aynı dış işlemde yakalansa bile kendi kısmi değişikliğini bırakmaz.

**Sorgu yüzeyi.** ``paket_getir``, ``paketleri_listele`` (isteğe bağlı
duruma göre), ``paket_belgesi``, ``paket_ayrinti`` (bütün çalışma alanı tek
``PaketAyrintisi`` içinde, her liste kimlik sırasıyla, deterministik),
``aday_ozellikleri_oku``, ``aday_kayit_icerigi``. Listeler veritabanının
tesadüfi satır sırasına bırakılmaz. ``PaketAyrintisi`` yalnız mekanik
bilgi verir (kaç aday nesne, kaç aday kayıt, durum); "kaydedilebilir mi"
sorusu 4.8'in işidir ve burada yoktur.

Hata modeli (``IslemPaketiHatasi`` altında): ``PaketBulunamadi``,
``AdayBulunamadi`` (``LookupError``); ``PaketDurumuGecersiz`` (yazma için
``calisiyor`` gerekli, geçiş izinli değil, eşzamanlı geçiş);
``PaketUyusmazligi`` (başka paketin adayı, başka okumanın kaynağı);
``GecersizAdayOzellik``, ``GecersizAdayIliski``, ``GecersizTaslakIcerik``
(``ValueError``); ``MukerrerAday`` (aynı aday ilişki ya da bağ);
``AdayKullanimda`` (silme reddi); ``TaslakYazmaCakismasi`` (eşzamanlı yazma
çatışması; yeni işlemde yeniden denenir). Tanım hataları
(``TanimBulunamadi``) ve belge zinciri hataları (``OkumaBulunamadi``,
``OkumaDurumuGecersiz``, ``KaynakBulunamadi``) kendi modüllerinden olduğu
gibi gelir. Ham ``IntegrityError`` / ``OperationalError`` yalnız yukarıdaki
dar eşlemeyle çevrilir, kalanı olduğu gibi yükselir. Mesajlarda aday kayıt
içeriği yoktur; bu modül hiçbir şeyi günlüğe yazmaz.
"""

from __future__ import annotations

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from defteriki.cekirdek.belge_islemleri import (
    OkumaDurumuGecersiz,
    belge_getir,
    json_coz,
    json_kodla,
    kaynak_getir,
    okuma_getir,
)
from defteriki.cekirdek.belge_tablolari import Belge, Kaynak, OkumaDurumu
from defteriki.cekirdek.deger_kodlama import (
    DegerKodlamaHatasi,
    degeri_coz,
    degeri_kodla,
)
from defteriki.cekirdek.tanim_sorgulari import (
    iliski_tanimi_getir,
    kayit_turu_getir,
    nesne_turu_getir,
)
from defteriki.cekirdek.tanim_tablolari import (
    IliskiTanimi,
    NesneTuru,
    OzellikTanimi,
    simdi_utc,
)
from defteriki.cekirdek.taslak_tablolari import (
    ADAY_KAYIT_NESNE,
    ADAY_NESNE_ILISKISI,
    ADAY_NESNE_OZELLIGI,
    AdayKayit,
    AdayKayitNesne,
    AdayNesne,
    AdayNesneIliskisi,
    AdayNesneOzelligi,
    IslemPaketi,
    PaketDurumu,
)

AZAMI_ADAY_KAYIT_ICERIGI_BOYUTU = 64 * 1024
"""Aday kayıt içeriğinin kanonik JSON metni için UTF-8 bayt sınırı; teknik
sınır, domain kuralı değil (okuma içeriğinin 4 MiB sınırından küçük: tek bir
aday kayıt okumanın tamamı değildir)."""

IZINLI_GECISLER: Mapping[PaketDurumu, frozenset[PaketDurumu]] = {
    PaketDurumu.CALISIYOR: frozenset({PaketDurumu.BEKLIYOR, PaketDurumu.IPTAL}),
    PaketDurumu.BEKLIYOR: frozenset({PaketDurumu.CALISIYOR, PaketDurumu.IPTAL}),
    PaketDurumu.IPTAL: frozenset(),
}
"""Paket yaşam döngüsü; ``iptal`` terminaldir."""


class IslemPaketiHatasi(Exception):
    """İşlem paketi ve taslak servis hatalarının ortak tabanı."""


class PaketBulunamadi(IslemPaketiHatasi, LookupError):
    """Verilen kimlikle işlem paketi yok."""


class AdayBulunamadi(IslemPaketiHatasi, LookupError):
    """Verilen kimlikle aday nesne, aday ilişki, aday kayıt ya da bağ yok."""


class PaketDurumuGecersiz(IslemPaketiHatasi):
    """Paket bu işlem için uygun durumda değil ya da geçiş izinli değil."""


class PaketUyusmazligi(IslemPaketiHatasi):
    """Aday öğe başka pakete, kaynak başka okumaya ait."""


class GecersizAdayOzellik(IslemPaketiHatasi, ValueError):
    """Aday nesnenin türünde böyle özellik yok ya da değer türe uymuyor."""


class GecersizAdayIliski(IslemPaketiHatasi, ValueError):
    """İlişki tanımına uymayan kaynak / hedef türü ya da sürüm."""


class GecersizTaslakIcerik(IslemPaketiHatasi, ValueError):
    """Aday kayıt içeriği JSON nesnesi değil, çevrilemiyor ya da sınırı aşıyor."""


class MukerrerAday(IslemPaketiHatasi):
    """Aynı aday ilişki ya da aynı kayıt-nesne bağı zaten var."""


class AdayKullanimda(IslemPaketiHatasi):
    """Aday nesne bir aday ilişkide ya da kayıt-nesne bağında kullanılıyor;
    silme reddedildi."""


class TaslakYazmaCakismasi(IslemPaketiHatasi):
    """Eşzamanlı yazma çatışması: başka bir bağlantı aynı anda yazdı (SQLite
    kilit / anlık görüntü çakışması ya da yarışan ilk yazımda benzersizlik
    ihlali). Bu işlem artık yazamaz; çağıran işlemi geri alır ve yeni işlemde
    yeniden dener."""


@dataclass(frozen=True, slots=True)
class PaketAyrintisi:
    """Paketin bütün çalışma alanı; her liste kimlik sırasıyla (deterministik)."""

    paket: IslemPaketi
    aday_nesneler: tuple[AdayNesne, ...]
    aday_ozellikler: tuple[AdayNesneOzelligi, ...]
    aday_iliskiler: tuple[AdayNesneIliskisi, ...]
    aday_kayitlar: tuple[AdayKayit, ...]
    kayit_nesne_baglari: tuple[AdayKayitNesne, ...]

    @property
    def durum(self) -> PaketDurumu:
        return PaketDurumu(self.paket.durum)

    @property
    def aday_nesne_sayisi(self) -> int:
        return len(self.aday_nesneler)

    @property
    def aday_kayit_sayisi(self) -> int:
        return len(self.aday_kayitlar)


# --- getirme --------------------------------------------------------------------------


def paket_getir(oturum: Session, paket_id: int) -> IslemPaketi:
    paket = oturum.get(IslemPaketi, paket_id)
    if paket is None:
        raise PaketBulunamadi(f"işlem paketi bulunamadı: kimlik {paket_id}")
    return paket


def paketleri_listele(
    oturum: Session, durum: PaketDurumu | None = None
) -> list[IslemPaketi]:
    """Paketler kimlik sırasıyla; ``durum`` verilirse yalnız o durumdakiler."""
    sorgu = select(IslemPaketi).order_by(IslemPaketi.id)
    if durum is not None:
        sorgu = sorgu.where(IslemPaketi.durum == PaketDurumu(durum).value)
    return list(oturum.execute(sorgu).scalars())


def paket_belgesi(oturum: Session, paket_id: int) -> Belge:
    """Paketin belgesi, ``paket → okuma → belge`` zincirinden."""
    paket = paket_getir(oturum, paket_id)
    return belge_getir(oturum, okuma_getir(oturum, paket.okuma_id).belge_id)


def aday_nesne_getir(oturum: Session, aday_nesne_id: int) -> AdayNesne:
    aday = oturum.get(AdayNesne, aday_nesne_id)
    if aday is None:
        raise AdayBulunamadi(f"aday nesne bulunamadı: kimlik {aday_nesne_id}")
    return aday


def aday_kayit_getir(oturum: Session, aday_kayit_id: int) -> AdayKayit:
    aday = oturum.get(AdayKayit, aday_kayit_id)
    if aday is None:
        raise AdayBulunamadi(f"aday kayıt bulunamadı: kimlik {aday_kayit_id}")
    return aday


def _aday_iliski_getir(oturum: Session, aday_iliski_id: int) -> AdayNesneIliskisi:
    satir = oturum.get(AdayNesneIliskisi, aday_iliski_id)
    if satir is None:
        raise AdayBulunamadi(f"aday ilişki bulunamadı: kimlik {aday_iliski_id}")
    return satir


def paket_ayrinti(oturum: Session, paket_id: int) -> PaketAyrintisi:
    """Paketin bütün taslak içeriği; her liste kimlik sırasıyla. Durumdan
    bağımsız okunur (bekleyen ve iptal paket dahil)."""
    paket = paket_getir(oturum, paket_id)
    nesneler = tuple(
        oturum.execute(
            select(AdayNesne)
            .where(AdayNesne.islem_paketi_id == paket.id)
            .order_by(AdayNesne.id)
        ).scalars()
    )
    ozellikler = tuple(
        oturum.execute(
            select(AdayNesneOzelligi)
            .join(AdayNesne, AdayNesne.id == AdayNesneOzelligi.aday_nesne_id)
            .where(AdayNesne.islem_paketi_id == paket.id)
            .order_by(AdayNesneOzelligi.id)
        ).scalars()
    )
    iliskiler = tuple(
        oturum.execute(
            select(AdayNesneIliskisi)
            .where(AdayNesneIliskisi.islem_paketi_id == paket.id)
            .order_by(AdayNesneIliskisi.id)
        ).scalars()
    )
    kayitlar = tuple(
        oturum.execute(
            select(AdayKayit)
            .where(AdayKayit.islem_paketi_id == paket.id)
            .order_by(AdayKayit.id)
        ).scalars()
    )
    baglar = tuple(
        oturum.execute(
            select(AdayKayitNesne)
            .where(AdayKayitNesne.islem_paketi_id == paket.id)
            .order_by(AdayKayitNesne.id)
        ).scalars()
    )
    return PaketAyrintisi(paket, nesneler, ozellikler, iliskiler, kayitlar, baglar)


# --- yazma sınırı (merkezi) ----------------------------------------------------------


def kilit_cakismasi_mi(hata: OperationalError) -> bool:
    """SQLite kilit ya da anlık görüntü çakışması (``database is locked`` /
    ``busy``); başka ``OperationalError`` (disk, dosya, sözdizimi) değildir."""
    metin = str(hata.orig).lower()
    return "locked" in metin or "busy" in metin


def benzersizlik_ihlali_mi(hata: IntegrityError, tablo: str) -> bool:
    """Yalnız ``tablo`` üzerindeki benzersizlik ihlali; dış anahtar, kontrol
    kısıtı ve başka tabloların benzersizliği değildir."""
    return str(hata.orig).startswith(f"UNIQUE constraint failed: {tablo}.")


@contextmanager
def _yazma_siniri(
    oturum: Session,
    tablo: str | None = None,
    benzersizlik_hatasi: type[IslemPaketiHatasi] = TaslakYazmaCakismasi,
    benzersizlik_mesaji: str = "",
) -> Generator[None, None, None]:
    """Her yazma işlevinin tek kapısı: SAVEPOINT (``begin_nested``) + dar hata
    eşleme. Kilit / anlık görüntü çakışması ``TaslakYazmaCakismasi``;
    ``tablo`` verilmişse o tablonun benzersizlik ihlali ``benzersizlik_hatasi``;
    başka veritabanı hataları olduğu gibi yükselir."""
    try:
        with oturum.begin_nested():
            yield
    except IntegrityError as hata:
        if tablo is not None and benzersizlik_ihlali_mi(hata, tablo):
            raise benzersizlik_hatasi(benzersizlik_mesaji) from None
        raise
    except OperationalError as hata:
        if kilit_cakismasi_mi(hata):
            raise TaslakYazmaCakismasi(
                "eşzamanlı yazma çatışması: başka bir bağlantı aynı anda yazdı; "
                "işlemi geri alıp yeni işlemde yeniden deneyin."
            ) from None
        raise


# --- paket durumu (merkezi) -----------------------------------------------------------


def _yazilabilir_paket(oturum: Session, paket_id: int) -> IslemPaketi:
    """Aday veriyi değiştiren her servisin tek kapısı: paket var ve ``calisiyor``."""
    paket = paket_getir(oturum, paket_id)
    if paket.durum != PaketDurumu.CALISIYOR.value:
        raise PaketDurumuGecersiz(
            f"işlem paketi {paket.id} {paket.durum} durumunda; taslak yalnız "
            f"{PaketDurumu.CALISIYOR.value} pakette değiştirilir."
        )
    return paket


def _durumu_degistir(oturum: Session, paket_id: int, yeni: PaketDurumu) -> IslemPaketi:
    """İzinli geçişi koşullu güncellemeyle uygular; eşzamanlı ikinci geçişte
    satır etkilenmez ve ``PaketDurumuGecersiz`` yükselir."""
    paket = paket_getir(oturum, paket_id)
    eski = PaketDurumu(paket.durum)
    if yeni not in IZINLI_GECISLER[eski]:
        raise PaketDurumuGecersiz(
            f"işlem paketi {paket.id}: {eski.value} → {yeni.value} geçişi izinli "
            f"değil{' (iptal terminaldir)' if eski is PaketDurumu.IPTAL else ''}."
        )
    with _yazma_siniri(oturum):
        guncellenen = oturum.execute(
            update(IslemPaketi)
            .where(IslemPaketi.id == paket.id, IslemPaketi.durum == eski.value)
            .values(durum=yeni.value, durum_zamani=simdi_utc())
            .returning(IslemPaketi.id)
        ).scalar_one_or_none()
        if guncellenen is None:
            raise PaketDurumuGecersiz(
                f"işlem paketi {paket.id}: durum eşzamanlı değişti; "
                f"{eski.value} → {yeni.value} uygulanmadı."
            )
    oturum.refresh(paket)
    return paket


# --- paket ----------------------------------------------------------------------------


def paket_olustur(oturum: Session, okuma_id: int) -> IslemPaketi:
    """Tamamlanmış okumadan yeni, ``calisiyor`` durumunda işlem paketi.
    ``basladi`` okuma için ``OkumaDurumuGecersiz``; olmayan okuma için
    ``OkumaBulunamadi``. Kendi işlemini açmaz."""
    okuma = okuma_getir(oturum, okuma_id)
    if okuma.durum != OkumaDurumu.TAMAMLANDI.value:
        raise OkumaDurumuGecersiz(
            f"okuma {okuma.id} {okuma.durum} durumunda; işlem paketi yalnız "
            f"{OkumaDurumu.TAMAMLANDI.value} okumadan oluşturulur."
        )
    with _yazma_siniri(oturum):
        simdi = simdi_utc()
        paket = IslemPaketi(
            okuma_id=okuma.id,
            durum=PaketDurumu.CALISIYOR.value,
            olusturma_zamani=simdi,
            durum_zamani=simdi,
        )
        oturum.add(paket)
        oturum.flush()
    return paket


def paketi_beklet(oturum: Session, paket_id: int) -> IslemPaketi:
    """``calisiyor → bekliyor``: taslak korunur, yazma durur."""
    return _durumu_degistir(oturum, paket_id, PaketDurumu.BEKLIYOR)


def paketi_devam_et(oturum: Session, paket_id: int) -> IslemPaketi:
    """``bekliyor → calisiyor``: aynı paket, aynı taslaklarla sürer.
    ``iptal`` paket yeniden açılamaz."""
    return _durumu_degistir(oturum, paket_id, PaketDurumu.CALISIYOR)


def paketi_iptal_et(oturum: Session, paket_id: int) -> IslemPaketi:
    """``calisiyor`` ya da ``bekliyor`` → ``iptal`` (terminal). Hiçbir satır
    silinmez; paket ve taslak içeriği sorgulanabilir kalır."""
    return _durumu_degistir(oturum, paket_id, PaketDurumu.IPTAL)


# --- kaynak / provenance --------------------------------------------------------------


def _kaynagi_dogrula(oturum: Session, paket: IslemPaketi, kaynak_id: int) -> Kaynak:
    """Kaynak var ve paketin okumasına ait; değilse ``PaketUyusmazligi``."""
    kaynak = kaynak_getir(oturum, kaynak_id)
    if kaynak.okuma_id != paket.okuma_id:
        raise PaketUyusmazligi(
            f"kaynak {kaynak.id} okuma {kaynak.okuma_id}'e ait; işlem paketi "
            f"{paket.id} okuma {paket.okuma_id} üzerinde çalışıyor."
        )
    return kaynak


# --- aday nesne -----------------------------------------------------------------------


def _tur_tanimlari(oturum: Session, nesne_turu_id: int) -> dict[str, OzellikTanimi]:
    return {
        t.kod: t
        for t in oturum.execute(
            select(OzellikTanimi)
            .where(OzellikTanimi.nesne_turu_id == nesne_turu_id)
            .order_by(OzellikTanimi.id)
        ).scalars()
    }


def _degeri_kodla(tur: NesneTuru, tanim: OzellikTanimi, deger: object) -> str:
    try:
        return degeri_kodla(tanim.deger_turu, tanim.kod, deger)
    except DegerKodlamaHatasi as hata:
        raise GecersizAdayOzellik(f"nesne türü {tur.kod!r}: {hata}") from None


def _ozellik_tanimi_bul(oturum: Session, tur: NesneTuru, kod: str) -> OzellikTanimi:
    tanim = oturum.execute(
        select(OzellikTanimi).where(
            OzellikTanimi.nesne_turu_id == tur.id, OzellikTanimi.kod == kod
        )
    ).scalar_one_or_none()
    if tanim is None:
        raise GecersizAdayOzellik(
            f"nesne türü {tur.kod!r} için {kod!r} adlı özellik tanımı yok."
        )
    return tanim


def aday_nesne_ekle(
    oturum: Session,
    paket_id: int,
    nesne_turu_id: int,
    ozellikler: Mapping[str, object] | None = None,
    kaynak_id: int | None = None,
) -> AdayNesne:
    """Çalışan pakete türün tanımıyla aday nesne; başlangıç özellikleri isteğe
    bağlı ve eksik olabilir (zorunlu özellik aranmaz). Kesin ``nesne`` satırı
    oluşmaz, tanım sürümü kilitlenmez. Doğrulama yazmadan önce, yazma
    SAVEPOINT içinde."""
    paket = _yazilabilir_paket(oturum, paket_id)
    tur = nesne_turu_getir(oturum, nesne_turu_id)
    tanimlar = _tur_tanimlari(oturum, tur.id)
    kodlanmis: dict[str, str] = {}
    for kod, deger in dict(ozellikler or {}).items():
        if kod not in tanimlar:
            raise GecersizAdayOzellik(
                f"nesne türü {tur.kod!r} için {kod!r} adlı özellik tanımı yok."
            )
        kodlanmis[kod] = _degeri_kodla(tur, tanimlar[kod], deger)
    if kaynak_id is not None:
        _kaynagi_dogrula(oturum, paket, kaynak_id)
    with _yazma_siniri(oturum):
        aday = AdayNesne(
            islem_paketi_id=paket.id,
            okuma_id=paket.okuma_id,
            nesne_turu_id=tur.id,
            tanim_surumu_id=tur.tanim_surumu_id,
            kaynak_id=kaynak_id,
            olusturma_zamani=simdi_utc(),
        )
        oturum.add(aday)
        oturum.flush()
        for kod, metin in kodlanmis.items():
            oturum.add(
                AdayNesneOzelligi(
                    aday_nesne_id=aday.id,
                    nesne_turu_id=tur.id,
                    ozellik_tanimi_id=tanimlar[kod].id,
                    deger=metin,
                )
            )
        oturum.flush()
    return aday


def aday_nesne_sil(oturum: Session, aday_nesne_id: int) -> None:
    """Aday nesneyi kendi özellikleriyle birlikte kaldırır. Bir aday ilişkide
    ya da kayıt-nesne bağında kullanılıyorsa ``AdayKullanimda``; sessiz
    cascade yoktur."""
    aday = aday_nesne_getir(oturum, aday_nesne_id)
    _yazilabilir_paket(oturum, aday.islem_paketi_id)
    iliski = oturum.execute(
        select(AdayNesneIliskisi.id).where(
            (AdayNesneIliskisi.kaynak_aday_nesne_id == aday.id)
            | (AdayNesneIliskisi.hedef_aday_nesne_id == aday.id)
        )
    ).first()
    if iliski is not None:
        raise AdayKullanimda(
            f"aday nesne {aday.id} aday ilişkide kullanılıyor; önce ilişki kaldırılır."
        )
    bag = oturum.execute(
        select(AdayKayitNesne.id).where(AdayKayitNesne.aday_nesne_id == aday.id)
    ).first()
    if bag is not None:
        raise AdayKullanimda(
            f"aday nesne {aday.id} aday kayda bağlı; önce bağ çözülür."
        )
    with _yazma_siniri(oturum):
        for ozellik in oturum.execute(
            select(AdayNesneOzelligi).where(AdayNesneOzelligi.aday_nesne_id == aday.id)
        ).scalars():
            oturum.delete(ozellik)
        oturum.flush()
        oturum.delete(aday)
        oturum.flush()


# --- aday özellik ---------------------------------------------------------------------


def aday_ozellik_yaz(
    oturum: Session, aday_nesne_id: int, kod: str, deger: object
) -> AdayNesneOzelligi:
    """Aday nesnenin türündeki ``kod`` özelliğini yazar; varsa değeri günceller
    (aynı özellik iki satır olmaz). Tür ve değer türü kesin özellikle aynı
    kuralla doğrulanır."""
    aday = aday_nesne_getir(oturum, aday_nesne_id)
    _yazilabilir_paket(oturum, aday.islem_paketi_id)
    tur = nesne_turu_getir(oturum, aday.nesne_turu_id)
    tanim = _ozellik_tanimi_bul(oturum, tur, kod)
    metin = _degeri_kodla(tur, tanim, deger)
    satir = oturum.execute(
        select(AdayNesneOzelligi).where(
            AdayNesneOzelligi.aday_nesne_id == aday.id,
            AdayNesneOzelligi.ozellik_tanimi_id == tanim.id,
        )
    ).scalar_one_or_none()
    with _yazma_siniri(
        oturum,
        ADAY_NESNE_OZELLIGI,
        TaslakYazmaCakismasi,
        f"aday nesne {aday.id} üzerinde {kod!r} özelliği başka bir bağlantı "
        "tarafından aynı anda yazıldı; yeni işlemde yeniden deneyin.",
    ):
        if satir is None:
            satir = AdayNesneOzelligi(
                aday_nesne_id=aday.id,
                nesne_turu_id=aday.nesne_turu_id,
                ozellik_tanimi_id=tanim.id,
                deger=metin,
            )
            oturum.add(satir)
        else:
            satir.deger = metin
        oturum.flush()
    return satir


def aday_ozellik_sil(oturum: Session, aday_nesne_id: int, kod: str) -> None:
    """Yazılı aday özelliği kaldırır (zorunlu olsa da; tamlık 4.8'de aranır).
    Yazılmamış özellik için ``GecersizAdayOzellik``."""
    aday = aday_nesne_getir(oturum, aday_nesne_id)
    _yazilabilir_paket(oturum, aday.islem_paketi_id)
    tur = nesne_turu_getir(oturum, aday.nesne_turu_id)
    tanim = _ozellik_tanimi_bul(oturum, tur, kod)
    satir = oturum.execute(
        select(AdayNesneOzelligi).where(
            AdayNesneOzelligi.aday_nesne_id == aday.id,
            AdayNesneOzelligi.ozellik_tanimi_id == tanim.id,
        )
    ).scalar_one_or_none()
    if satir is None:
        raise GecersizAdayOzellik(
            f"aday nesne {aday.id} üzerinde {kod!r} özelliği yazılı değil."
        )
    with _yazma_siniri(oturum):
        oturum.delete(satir)
        oturum.flush()


def aday_ozellikleri_oku(oturum: Session, aday_nesne_id: int) -> dict[str, object]:
    """Aday nesnenin yazılı özellikleri: kod → türüne çözülmüş Python değeri;
    tanım sırasıyla. Durumdan bağımsız okunur."""
    aday = aday_nesne_getir(oturum, aday_nesne_id)
    satirlar = oturum.execute(
        select(OzellikTanimi.kod, OzellikTanimi.deger_turu, AdayNesneOzelligi.deger)
        .join(
            AdayNesneOzelligi,
            AdayNesneOzelligi.ozellik_tanimi_id == OzellikTanimi.id,
        )
        .where(AdayNesneOzelligi.aday_nesne_id == aday.id)
        .order_by(OzellikTanimi.id)
    ).all()
    return {kod: degeri_coz(deger_turu, deger) for kod, deger_turu, deger in satirlar}


# --- aday ilişki ----------------------------------------------------------------------


def aday_iliski_ekle(
    oturum: Session,
    iliski_tanimi_id: int,
    kaynak_aday_nesne_id: int,
    hedef_aday_nesne_id: int,
) -> AdayNesneIliskisi:
    """İki aday nesne arasında ilişki tanımıyla aday ilişki. Paket iki
    adayın ortak paketidir (farklıysa ``PaketUyusmazligi``); kaynak adayın
    türü tanımın kaynak türü, hedefinki hedef türü, üçü aynı sürümde olmalı
    (``GecersizAdayIliski``); aynı ilişki ikinci kez ``MukerrerAday``.
    Hiyerarşi sayımı ve çevrim aranmaz."""
    iliski = iliski_tanimi_getir(oturum, iliski_tanimi_id)
    kaynak = aday_nesne_getir(oturum, kaynak_aday_nesne_id)
    hedef = aday_nesne_getir(oturum, hedef_aday_nesne_id)
    if kaynak.islem_paketi_id != hedef.islem_paketi_id:
        raise PaketUyusmazligi(
            f"aday nesne {kaynak.id} paket {kaynak.islem_paketi_id}, aday nesne "
            f"{hedef.id} paket {hedef.islem_paketi_id} içinde; aday ilişki tek "
            "paket içinde kurulur."
        )
    paket = _yazilabilir_paket(oturum, kaynak.islem_paketi_id)
    _iliski_turlerini_dogrula(iliski, kaynak, hedef)
    var = oturum.execute(
        select(AdayNesneIliskisi.id).where(
            AdayNesneIliskisi.iliski_tanimi_id == iliski.id,
            AdayNesneIliskisi.kaynak_aday_nesne_id == kaynak.id,
            AdayNesneIliskisi.hedef_aday_nesne_id == hedef.id,
        )
    ).first()
    if var is not None:
        raise MukerrerAday(
            f"aday ilişki {iliski.kod!r} aday nesne {kaynak.id} → {hedef.id} zaten var."
        )
    with _yazma_siniri(
        oturum,
        ADAY_NESNE_ILISKISI,
        MukerrerAday,
        f"aday ilişki {iliski.kod!r} aday nesne {kaynak.id} → {hedef.id} zaten var.",
    ):
        satir = AdayNesneIliskisi(
            islem_paketi_id=paket.id,
            iliski_tanimi_id=iliski.id,
            tanim_surumu_id=iliski.tanim_surumu_id,
            kaynak_nesne_turu_id=iliski.kaynak_nesne_turu_id,
            hedef_nesne_turu_id=iliski.hedef_nesne_turu_id,
            kaynak_aday_nesne_id=kaynak.id,
            hedef_aday_nesne_id=hedef.id,
        )
        oturum.add(satir)
        oturum.flush()
    return satir


def _iliski_turlerini_dogrula(
    iliski: IliskiTanimi, kaynak: AdayNesne, hedef: AdayNesne
) -> None:
    if kaynak.nesne_turu_id != iliski.kaynak_nesne_turu_id:
        raise GecersizAdayIliski(
            f"ilişki {iliski.kod!r}: kaynak aday nesne {kaynak.id} türü "
            f"{kaynak.nesne_turu_id}, tanım {iliski.kaynak_nesne_turu_id} bekler."
        )
    if hedef.nesne_turu_id != iliski.hedef_nesne_turu_id:
        raise GecersizAdayIliski(
            f"ilişki {iliski.kod!r}: hedef aday nesne {hedef.id} türü "
            f"{hedef.nesne_turu_id}, tanım {iliski.hedef_nesne_turu_id} bekler."
        )
    if not (kaynak.tanim_surumu_id == hedef.tanim_surumu_id == iliski.tanim_surumu_id):
        raise GecersizAdayIliski(
            f"ilişki {iliski.kod!r}: aday nesneler ve tanım aynı tanım sürümünde "
            f"değil ({kaynak.tanim_surumu_id}, {hedef.tanim_surumu_id}, "
            f"{iliski.tanim_surumu_id})."
        )


def aday_iliski_kaldir(oturum: Session, aday_iliski_id: int) -> None:
    """Aday ilişkiyi kaldırır; en az üst kuralı aranmaz (taslak eksik olabilir)."""
    satir = _aday_iliski_getir(oturum, aday_iliski_id)
    _yazilabilir_paket(oturum, satir.islem_paketi_id)
    with _yazma_siniri(oturum):
        oturum.delete(satir)
        oturum.flush()


# --- aday kayıt -----------------------------------------------------------------------


def _icerigi_kodla(icerik: Mapping[str, Any]) -> str:
    return json_kodla(
        icerik,
        AZAMI_ADAY_KAYIT_ICERIGI_BOYUTU,
        GecersizTaslakIcerik,
        "aday kayıt içeriği",
    )


def aday_kayit_ekle(
    oturum: Session,
    paket_id: int,
    kayit_turu_id: int,
    icerik: Mapping[str, Any],
    kaynak_id: int | None = None,
) -> AdayKayit:
    """Çalışan pakete genel kayıt türüne bağlı aday kayıt. İçerik domain
    bağımsız JSON nesnesidir (``{}`` dahil; eksik olabilir), kanonik metin
    olarak saklanır; kesin kayıt alanı değildir ve kesin ``kayit`` satırı
    oluşmaz. Kaynak isteğe bağlı, paketin okumasına ait olmalı."""
    paket = _yazilabilir_paket(oturum, paket_id)
    tur = kayit_turu_getir(oturum, kayit_turu_id)
    metin = _icerigi_kodla(icerik)
    if kaynak_id is not None:
        _kaynagi_dogrula(oturum, paket, kaynak_id)
    with _yazma_siniri(oturum):
        aday = AdayKayit(
            islem_paketi_id=paket.id,
            okuma_id=paket.okuma_id,
            kayit_turu_id=tur.id,
            kaynak_id=kaynak_id,
            icerik=metin,
            olusturma_zamani=simdi_utc(),
        )
        oturum.add(aday)
        oturum.flush()
    return aday


def aday_kayit_icerigini_degistir(
    oturum: Session, aday_kayit_id: int, icerik: Mapping[str, Any]
) -> AdayKayit:
    """Aday kaydın içeriğini yeni JSON nesnesiyle değiştirir (taslak düzeltilebilir)."""
    aday = aday_kayit_getir(oturum, aday_kayit_id)
    _yazilabilir_paket(oturum, aday.islem_paketi_id)
    metin = _icerigi_kodla(icerik)
    with _yazma_siniri(oturum):
        aday.icerik = metin
        oturum.flush()
    return aday


def aday_kayit_icerigi(oturum: Session, aday_kayit_id: int) -> dict[str, Any]:
    """Aday kaydın içeriği (JSON çözülmüş); durumdan bağımsız okunur."""
    return json_coz(aday_kayit_getir(oturum, aday_kayit_id).icerik)


def aday_kayit_sil(oturum: Session, aday_kayit_id: int) -> None:
    """Aday kaydı kendi kayıt-nesne bağlarıyla birlikte kaldırır; bağlı aday
    nesneler kalır."""
    aday = aday_kayit_getir(oturum, aday_kayit_id)
    _yazilabilir_paket(oturum, aday.islem_paketi_id)
    with _yazma_siniri(oturum):
        for bag in oturum.execute(
            select(AdayKayitNesne).where(AdayKayitNesne.aday_kayit_id == aday.id)
        ).scalars():
            oturum.delete(bag)
        oturum.flush()
        oturum.delete(aday)
        oturum.flush()


# --- aday kayıt ↔ aday nesne ----------------------------------------------------------


def aday_kayit_nesne_bagla(
    oturum: Session, aday_kayit_id: int, aday_nesne_id: int
) -> AdayKayitNesne:
    """Aday kaydı aday nesneye bağlar (çoktan çoğa, rolsüz). İki taraf aynı
    pakette olmalı (``PaketUyusmazligi``); aynı bağ ikinci kez ``MukerrerAday``."""
    kayit = aday_kayit_getir(oturum, aday_kayit_id)
    nesne = aday_nesne_getir(oturum, aday_nesne_id)
    if kayit.islem_paketi_id != nesne.islem_paketi_id:
        raise PaketUyusmazligi(
            f"aday kayıt {kayit.id} paket {kayit.islem_paketi_id}, aday nesne "
            f"{nesne.id} paket {nesne.islem_paketi_id} içinde; bağ tek paket "
            "içinde kurulur."
        )
    paket = _yazilabilir_paket(oturum, kayit.islem_paketi_id)
    var = oturum.execute(
        select(AdayKayitNesne.id).where(
            AdayKayitNesne.aday_kayit_id == kayit.id,
            AdayKayitNesne.aday_nesne_id == nesne.id,
        )
    ).first()
    if var is not None:
        raise MukerrerAday(
            f"aday kayıt {kayit.id} ↔ aday nesne {nesne.id} bağı zaten var."
        )
    with _yazma_siniri(
        oturum,
        ADAY_KAYIT_NESNE,
        MukerrerAday,
        f"aday kayıt {kayit.id} ↔ aday nesne {nesne.id} bağı zaten var.",
    ):
        bag = AdayKayitNesne(
            islem_paketi_id=paket.id, aday_kayit_id=kayit.id, aday_nesne_id=nesne.id
        )
        oturum.add(bag)
        oturum.flush()
    return bag


def aday_kayit_nesne_coz(
    oturum: Session, aday_kayit_id: int, aday_nesne_id: int
) -> None:
    """Kayıt-nesne bağını kaldırır; yoksa ``AdayBulunamadi``."""
    kayit = aday_kayit_getir(oturum, aday_kayit_id)
    _yazilabilir_paket(oturum, kayit.islem_paketi_id)
    bag = oturum.execute(
        select(AdayKayitNesne).where(
            AdayKayitNesne.aday_kayit_id == kayit.id,
            AdayKayitNesne.aday_nesne_id == aday_nesne_id,
        )
    ).scalar_one_or_none()
    if bag is None:
        raise AdayBulunamadi(
            f"aday kayıt {kayit.id} ↔ aday nesne {aday_nesne_id} bağı yok."
        )
    with _yazma_siniri(oturum):
        oturum.delete(bag)
        oturum.flush()
