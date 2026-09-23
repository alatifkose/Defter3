"""Tanım sisteminin yazma işlevleri ve tam yüzeyi (Aşama 4.2; kilit ve hiyerarşi 4.3).

Tanım tablolarına (``tanim_tablolari``) yazan tek modül. Okuma işlevleri ve
``TanimHatasi`` / ``TanimBulunamadi`` ``tanim_sorgulari`` içindedir ve buradan
yeniden dışa aktarılır: tanım sistemini bütün olarak kullanan çağıran yalnız
bu modülü import eder; yalnız okuyan modüller (``nesne_islemleri``,
``taslak_islemleri``) ``tanim_sorgulari`` kullanır, çünkü bu modül ekleme-yalnız
kilit için kesin nesne tablolarını (``nesne_tablolari``) import eder ve taslak
modülleri kesin nesne dünyasına ulaşamaz (``tests/test_mimari_sinir.py``).

Her işlev açık bir ``Session`` alır ve ``Veritabani.islem`` bağlamı içinde
çağrılır; kendi başına ``commit`` etmez, ``rollback`` etmez. Yazma işlevleri
satırı ekleyip ``flush`` eder, böylece kimlik atanır ve olası veritabanı
hatası çağıranın işlem sınırında yükselir; işlem bağlamı rollback ile her
şeyi geri alır.

Hata modeli (hepsi ``TanimHatasi`` altında; domain bağımsız):

* ``GecersizTanim`` — kod ``KOD_BICIMI``'ne uymuyor, gösterim adı boş, sürüm
  numarası pozitif tam sayı değil (``bool``, ``float``, metin de reddedilir),
  hiyerarşi kuralı sayıları tutarsız.
* ``TanimBulunamadi`` — verilen paket, sürüm, nesne türü, ilişki ya da kayıt
  türü kimliği yok (``tanim_sorgulari``). Olmayan üst kayda bağlanmak sessizce
  geçmez; listeleme de olmayan üst kayıt için boş liste yerine bu hatayı verir.
* ``MukerrerTanim`` — aynı kapsamda aynı kod (paket: bütün paketler; sürüm:
  aynı paket içinde sürüm numarası; nesne türü, ilişki, kayıt türü: aynı
  sürüm; özellik: aynı nesne türü; kayıt alanı: aynı kayıt türü; hiyerarşi
  kuralı: aynı ilişki tanımı).
* ``TanimSurumuUyusmuyor`` — ilişkinin kaynak ya da hedef türü ilişkinin
  sürümünde değil.
* ``TanimSurumuKilitli`` — ekleme, sürüm altındaki mevcut kesin veriyi geriye
  dönük bozardı (aşağıdaki ekleme-yalnız kilit).

**Ekleme-yalnız kilit (karar 2026-09-19).** Sürüm altında ilk kesin nesne
üretilince ``kilitli`` olur; bu "hiçbir şey eklenemez" değil, "mevcut kesin
verinin anlamını ya da geçerliliğini bozan ekleme yapılamaz" demektir.
Denetim sürüm bayrağına değil yerel veriye bakar (bayrak yalnız hızlı ön
kontroldür: kilitsiz sürümün altında kesin nesne olamaz):

* yeni nesne türü, yeni ilişki, yeni kayıt türü, yeni kayıt alanı her zaman
  serbest (yeni tanımın altında veri yoktur);
* yeni isteğe bağlı özellik her zaman serbest (eski nesnede yalnız
  "yazılmamış" sayılır);
* yeni **zorunlu** özellik yalnız o nesne türünün altında kesin nesne yoksa
  (kilitten sonra eklenen, henüz kullanılmamış tür zorunlu özellik alabilir);
* hiyerarşi kuralı yalnız o ilişkiyle kurulmuş kesin bağlantı yoksa (mevcut
  bağlantılar ``en_cok_ust`` sınırını ya da çevrim yasağını ihlal ediyor
  olabilir) **ve** ``en_az_ust > 0`` ise kaynak türün altında kesin nesne
  yoksa (aksi hâlde üstsüz mevcut nesneler bir anda kurala aykırı olurdu);
* tanım değiştirme ve silme işlevi yoktur (API düzeyinde koruma; oturuma
  doğrudan erişen kod ORM alanını değiştirebilir, bu kapsam dışı ve bilinçli
  sınırdır: MCP ve GUI oturuma değil işlevlere erişir).

Aday (taslak) nesneler sayılmaz; kapalı nesne sayılır. Bozan değişiklik
gerçekten gerekirse yeni sürüm açılır; ama sürümler arası nesne bağlantısı
ve taşıma yoktur (``nesne_islemleri``), yani pratikte tek sürüm ekleme-yalnız
büyür.

Bu denetimler uygulama sözleşmesidir; veritabanındaki benzersizlik, dış
anahtar ve bileşik dış anahtar kısıtları son savunmadır ve aynı durumları
ham ``IntegrityError`` ile de reddeder. Kilit yalnız uygulama düzeyindedir
(SQLite'ta tetikleyicisiz ifade edilemez; bilinçli sınır).

Çekirdek burada da domain bilmez: kodların anlamı, hangi türlerin var olacağı,
hangi ilişkilerin kurulacağı çağıranın (tanım paketinin) verisidir. Bu modül
``TEST_KISI`` ile ``BANKA`` arasında fark görmez.
"""

from __future__ import annotations

import re

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from defteruc.cekirdek.nesne_tablolari import Nesne, NesneIliskisi
from defteruc.cekirdek.tanim_sorgulari import TanimBulunamadi as TanimBulunamadi
from defteruc.cekirdek.tanim_sorgulari import TanimHatasi as TanimHatasi
from defteruc.cekirdek.tanim_sorgulari import (
    hiyerarsi_kurallarini_listele as hiyerarsi_kurallarini_listele,
)
from defteruc.cekirdek.tanim_sorgulari import (
    iliski_tanimi_getir as iliski_tanimi_getir,
)
from defteruc.cekirdek.tanim_sorgulari import (
    iliski_tanimlarini_listele as iliski_tanimlarini_listele,
)
from defteruc.cekirdek.tanim_sorgulari import (
    kayit_alani_tanimlarini_listele as kayit_alani_tanimlarini_listele,
)
from defteruc.cekirdek.tanim_sorgulari import (
    kayit_turlerini_listele as kayit_turlerini_listele,
)
from defteruc.cekirdek.tanim_sorgulari import kayit_turu_getir as kayit_turu_getir
from defteruc.cekirdek.tanim_sorgulari import (
    nesne_turlerini_listele as nesne_turlerini_listele,
)
from defteruc.cekirdek.tanim_sorgulari import nesne_turu_getir as nesne_turu_getir
from defteruc.cekirdek.tanim_sorgulari import (
    ozellik_tanimlarini_listele as ozellik_tanimlarini_listele,
)
from defteruc.cekirdek.tanim_sorgulari import paket_bul as paket_bul
from defteruc.cekirdek.tanim_sorgulari import paket_getir as paket_getir
from defteruc.cekirdek.tanim_sorgulari import paketleri_listele as paketleri_listele
from defteruc.cekirdek.tanim_sorgulari import surum_getir as surum_getir
from defteruc.cekirdek.tanim_sorgulari import surum_kilitli_mi as surum_kilitli_mi
from defteruc.cekirdek.tanim_sorgulari import surumleri_listele as surumleri_listele
from defteruc.cekirdek.tanim_tablolari import (
    DegerTuru,
    HiyerarsiKurali,
    IliskiTanimi,
    KayitAlaniTanimi,
    KayitTuru,
    NesneTuru,
    OzellikTanimi,
    TanimPaketi,
    TanimSurumu,
    YasamDurumu,
    simdi_utc,
)

KOD_BICIMI = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
"""Makine kimliği biçimi: ASCII harfle başlar, harf / rakam / alt çizgi ile
sürer; büyük-küçük harf ayrımı vardır, kod verildiği gibi saklanır ve
karşılaştırılır (``Demo`` ile ``DEMO`` farklı kodlardır)."""


class GecersizTanim(TanimHatasi, ValueError):
    """Kod biçimi, gösterim adı, sürüm numarası ya da kural sayıları geçersiz."""


class MukerrerTanim(TanimHatasi):
    """Aynı kapsamda aynı kod (ya da aynı sürüm numarası / ilişki) zaten tanımlı."""


class TanimSurumuUyusmuyor(TanimHatasi):
    """İlişkinin kaynak ya da hedef türü ilişkinin sürümünde değil."""


class TanimSurumuKilitli(TanimHatasi):
    """Ekleme, sürüm altındaki mevcut kesin veriyi geriye dönük bozardı."""


# --- doğrulama -------------------------------------------------------------------


def _kodu_dogrula(kod: str, ne: str) -> str:
    if not KOD_BICIMI.fullmatch(kod):
        raise GecersizTanim(
            f"{ne} kodu {kod!r} geçersiz: harfle başlamalı, yalnız ASCII harf, "
            "rakam ve alt çizgi içermeli."
        )
    return kod


def _gosterim_adini_dogrula(gosterim_adi: str, ne: str) -> str:
    if not gosterim_adi.strip():
        raise GecersizTanim(f"{ne} gösterim adı boş olamaz.")
    return gosterim_adi


def _deger_turunu_dogrula(deger_turu: DegerTuru, kod: str, ne: str) -> DegerTuru:
    """Tip ipucu çalışma zamanında denetlemez: ``DegerTuru`` dışında bir değer
    gelirse tanım geçersizdir."""
    try:
        return DegerTuru(deger_turu)
    except ValueError:
        raise GecersizTanim(
            f"{ne} {kod!r}: değer türü geçersiz: {deger_turu!r}"
        ) from None


def _zorunlulugu_dogrula(zorunlu: bool, kod: str, ne: str) -> bool:
    if type(zorunlu) is not bool:
        raise GecersizTanim(f"{ne} {kod!r}: zorunlu bilgisi mantıksal olmalı.")
    return zorunlu


def _tam_sayi_dogrula(deger: object, ne: str) -> int:
    """Yalnız gerçek ``int``: tip ipucu çalışma zamanında denetlemez; ``1.5``,
    ``"1"`` ve ``True`` sayı değildir (``bool`` ``int`` alt sınıfı olduğundan
    ayrıca dışlanır)."""
    if type(deger) is not int:
        raise GecersizTanim(f"{ne} tam sayı olmalı: {deger!r} ({type(deger).__name__})")
    return deger


def _surum_noyu_dogrula(surum_no: object) -> int:
    deger = _tam_sayi_dogrula(surum_no, "sürüm numarası")
    if deger <= 0:
        raise GecersizTanim(f"sürüm numarası pozitif olmalı: {deger}")
    return deger


def _mukerrer_denetle(oturum: Session, sorgu: Select[tuple[int]], mesaj: str) -> None:
    if oturum.execute(sorgu).first() is not None:
        raise MukerrerTanim(mesaj)


# --- ekleme-yalnız kilit: mevcut kesin veri ------------------------------------------


def _turde_kesin_nesne_var_mi(oturum: Session, tur: NesneTuru) -> bool:
    """Türün altında kesin nesne var mı (etkin ya da kapalı; aday sayılmaz).
    Kilitsiz sürümün altında nesne olamaz; bayrak hızlı ön kontroldür."""
    if not surum_getir(oturum, tur.tanim_surumu_id).kilitli:
        return False
    sorgu = select(Nesne.id).where(Nesne.nesne_turu_id == tur.id).limit(1)
    return oturum.execute(sorgu).first() is not None


def _iliskide_kesin_baglanti_var_mi(oturum: Session, iliski: IliskiTanimi) -> bool:
    """İlişki tanımıyla kurulmuş kesin nesne ilişkisi var mı."""
    if not surum_getir(oturum, iliski.tanim_surumu_id).kilitli:
        return False
    sorgu = (
        select(NesneIliskisi.id)
        .where(NesneIliskisi.iliski_tanimi_id == iliski.id)
        .limit(1)
    )
    return oturum.execute(sorgu).first() is not None


# --- yazma -----------------------------------------------------------------------


def paket_tanimla(
    oturum: Session, kod: str, gosterim_adi: str, aciklama: str | None = None
) -> TanimPaketi:
    """Yeni tanım paketi; ``kod`` bütün paketler arasında benzersiz."""
    _kodu_dogrula(kod, "tanım paketi")
    _gosterim_adini_dogrula(gosterim_adi, "tanım paketi")
    _mukerrer_denetle(
        oturum,
        select(TanimPaketi.id).where(TanimPaketi.kod == kod),
        f"tanım paketi {kod!r} zaten var.",
    )
    paket = TanimPaketi(
        kod=kod,
        gosterim_adi=gosterim_adi,
        aciklama=aciklama,
        olusturma_zamani=simdi_utc(),
    )
    oturum.add(paket)
    oturum.flush()
    return paket


def surum_tanimla(
    oturum: Session,
    tanim_paketi_id: int,
    surum_no: int,
    aciklama: str | None = None,
) -> TanimSurumu:
    """Paketin yeni sürümü; ``surum_no`` pozitif tam sayı (``int``; ``bool``,
    ``float`` ve metin reddedilir) ve paket içinde benzersiz. Yeni sürüm açmak
    her zaman serbesttir; kilit sürüm başınadır."""
    _surum_noyu_dogrula(surum_no)
    paket = paket_getir(oturum, tanim_paketi_id)
    _mukerrer_denetle(
        oturum,
        select(TanimSurumu.id).where(
            TanimSurumu.tanim_paketi_id == paket.id,
            TanimSurumu.surum_no == surum_no,
        ),
        f"tanım paketi {paket.kod!r} için sürüm {surum_no} zaten var.",
    )
    surum = TanimSurumu(
        tanim_paketi_id=paket.id,
        surum_no=surum_no,
        aciklama=aciklama,
        olusturma_zamani=simdi_utc(),
        kilitli=False,
    )
    oturum.add(surum)
    oturum.flush()
    return surum


def nesne_turu_tanimla(
    oturum: Session,
    tanim_surumu_id: int,
    kod: str,
    gosterim_adi: str,
    aciklama: str | None = None,
) -> NesneTuru:
    """Sürüme yeni nesne türü; ``kod`` sürüm içinde benzersiz. Kilitli sürümde
    de serbest: yeni türün altında veri yoktur."""
    _kodu_dogrula(kod, "nesne türü")
    _gosterim_adini_dogrula(gosterim_adi, "nesne türü")
    surum = surum_getir(oturum, tanim_surumu_id)
    _mukerrer_denetle(
        oturum,
        select(NesneTuru.id).where(
            NesneTuru.tanim_surumu_id == surum.id, NesneTuru.kod == kod
        ),
        f"nesne türü {kod!r} bu sürümde zaten var.",
    )
    tur = NesneTuru(
        tanim_surumu_id=surum.id, kod=kod, gosterim_adi=gosterim_adi, aciklama=aciklama
    )
    oturum.add(tur)
    oturum.flush()
    return tur


def ozellik_tanimla(
    oturum: Session,
    nesne_turu_id: int,
    kod: str,
    gosterim_adi: str,
    deger_turu: DegerTuru,
    zorunlu: bool = False,
    aciklama: str | None = None,
) -> OzellikTanimi:
    """Nesne türüne yeni özellik tanımı; ``kod`` tür içinde benzersiz.
    ``deger_turu`` teknik değer türü, ``zorunlu`` nesnenin bu özellik olmadan
    var olamayacağı anlamına gelir. İsteğe bağlı özellik her zaman eklenir;
    zorunlu özellik yalnız türün altında kesin nesne yoksa (ekleme-yalnız
    kilit), aksi hâlde ``TanimSurumuKilitli``."""
    _kodu_dogrula(kod, "özellik")
    _gosterim_adini_dogrula(gosterim_adi, "özellik")
    deger_turu = _deger_turunu_dogrula(deger_turu, kod, "özellik")
    _zorunlulugu_dogrula(zorunlu, kod, "özellik")
    tur = nesne_turu_getir(oturum, nesne_turu_id)
    _mukerrer_denetle(
        oturum,
        select(OzellikTanimi.id).where(
            OzellikTanimi.nesne_turu_id == tur.id, OzellikTanimi.kod == kod
        ),
        f"özellik {kod!r} nesne türü {tur.kod!r} için zaten var.",
    )
    # Mükerrerlik kilitten önce: var olan özellik ikinci kez verilirse sebep
    # "zaten var"dır, "kilitli" değil (2026-09-20 incelemesi).
    if zorunlu and _turde_kesin_nesne_var_mi(oturum, tur):
        raise TanimSurumuKilitli(
            f"nesne türü {tur.kod!r} altında kesin nesne var; zorunlu özellik "
            f"{kod!r} eklenemez (mevcut nesneleri geçersiz kılardı), yalnız isteğe "
            "bağlı özellik eklenebilir."
        )
    ozellik = OzellikTanimi(
        nesne_turu_id=tur.id,
        kod=kod,
        gosterim_adi=gosterim_adi,
        aciklama=aciklama,
        deger_turu=deger_turu.value,
        zorunlu=zorunlu,
    )
    oturum.add(ozellik)
    oturum.flush()
    return ozellik


def iliski_tanimla(
    oturum: Session,
    tanim_surumu_id: int,
    kod: str,
    gosterim_adi: str,
    kaynak_nesne_turu_id: int,
    hedef_nesne_turu_id: int,
    aciklama: str | None = None,
) -> IliskiTanimi:
    """Sürüme yönlü ilişki tanımı (kaynak → hedef); ``kod`` sürüm içinde
    benzersiz; iki tür de bu sürümde olmalı. Kaynak ile hedef aynı tür
    olabilir. Kilitli sürümde de serbest: yeni ilişkinin bağlantısı yoktur."""
    _kodu_dogrula(kod, "ilişki")
    _gosterim_adini_dogrula(gosterim_adi, "ilişki")
    surum = surum_getir(oturum, tanim_surumu_id)
    kaynak = nesne_turu_getir(oturum, kaynak_nesne_turu_id)
    hedef = nesne_turu_getir(oturum, hedef_nesne_turu_id)
    for rol, tur in (("kaynak", kaynak), ("hedef", hedef)):
        if tur.tanim_surumu_id != surum.id:
            raise TanimSurumuUyusmuyor(
                f"ilişki {kod!r}: {rol} türü {tur.kod!r} sürüm {tur.tanim_surumu_id} "
                f"içinde, ilişki sürüm {surum.id} içinde tanımlanıyor."
            )
    _mukerrer_denetle(
        oturum,
        select(IliskiTanimi.id).where(
            IliskiTanimi.tanim_surumu_id == surum.id, IliskiTanimi.kod == kod
        ),
        f"ilişki {kod!r} bu sürümde zaten var.",
    )
    iliski = IliskiTanimi(
        tanim_surumu_id=surum.id,
        kod=kod,
        gosterim_adi=gosterim_adi,
        aciklama=aciklama,
        kaynak_nesne_turu_id=kaynak.id,
        hedef_nesne_turu_id=hedef.id,
    )
    oturum.add(iliski)
    oturum.flush()
    return iliski


def hiyerarsi_kurali_tanimla(
    oturum: Session,
    iliski_tanimi_id: int,
    en_az_ust: int,
    en_cok_ust: int | None,
    ust_yasam_durumu: YasamDurumu | None = None,
) -> HiyerarsiKurali:
    """İlişki tanımını hiyerarşik yapar: kaynak tür çocuk, hedef tür üsttür.

    ``en_az_ust`` ≥ 0 (0: isteğe bağlı üst), ``en_cok_ust`` ≥ 1 ve ≥ ``en_az_ust``
    ya da ``None`` (sınırsız), ``ust_yasam_durumu`` üstün olması gereken durum
    ya da ``None`` (fark etmez). Bir ilişkinin en çok bir kuralı olur.
    Ekleme-yalnız kilit: ilişkiyle kurulmuş kesin bağlantı varsa kural
    eklenemez; ``en_az_ust > 0`` ise kaynak türün altında kesin nesne de
    olmamalı (``TanimSurumuKilitli``)."""
    iliski = iliski_tanimi_getir(oturum, iliski_tanimi_id)
    if _tam_sayi_dogrula(en_az_ust, "en az üst sayısı") < 0:
        raise GecersizTanim(f"en az üst sayısı negatif olamaz: {en_az_ust}")
    if en_cok_ust is not None:
        _tam_sayi_dogrula(en_cok_ust, "en çok üst sayısı")
        if en_cok_ust < 1 or en_cok_ust < en_az_ust:
            raise GecersizTanim(
                f"en çok üst sayısı en az 1 ve en az üst sayısından ({en_az_ust}) "
                f"küçük olmamalı: {en_cok_ust}"
            )
    if ust_yasam_durumu is not None:
        try:
            ust_yasam_durumu = YasamDurumu(ust_yasam_durumu)
        except ValueError:
            raise GecersizTanim(
                f"üst yaşam durumu geçersiz: {ust_yasam_durumu!r}"
            ) from None
    _mukerrer_denetle(
        oturum,
        select(HiyerarsiKurali.id).where(HiyerarsiKurali.iliski_tanimi_id == iliski.id),
        f"ilişki {iliski.kod!r} için hiyerarşi kuralı zaten var.",
    )
    if _iliskide_kesin_baglanti_var_mi(oturum, iliski):
        raise TanimSurumuKilitli(
            f"ilişki {iliski.kod!r} ile kurulmuş kesin bağlantı var; hiyerarşi "
            "kuralı eklenemez (mevcut bağlantılar kurala aykırı olabilir)."
        )
    if en_az_ust > 0 and _turde_kesin_nesne_var_mi(
        oturum, nesne_turu_getir(oturum, iliski.kaynak_nesne_turu_id)
    ):
        raise TanimSurumuKilitli(
            f"ilişki {iliski.kod!r}: kaynak tür altında kesin nesne var; en az "
            f"{en_az_ust} üst şartı eklenemez (mevcut nesneleri geçersiz kılardı)."
        )
    kural = HiyerarsiKurali(
        iliski_tanimi_id=iliski.id,
        en_az_ust=en_az_ust,
        en_cok_ust=en_cok_ust,
        ust_yasam_durumu=None if ust_yasam_durumu is None else ust_yasam_durumu.value,
    )
    oturum.add(kural)
    oturum.flush()
    return kural


def kayit_turu_tanimla(
    oturum: Session,
    tanim_surumu_id: int,
    kod: str,
    gosterim_adi: str,
    aciklama: str | None = None,
) -> KayitTuru:
    """Sürüme yeni kayıt türü; ``kod`` sürüm içinde benzersiz; kilitli sürümde
    de serbest."""
    _kodu_dogrula(kod, "kayıt türü")
    _gosterim_adini_dogrula(gosterim_adi, "kayıt türü")
    surum = surum_getir(oturum, tanim_surumu_id)
    _mukerrer_denetle(
        oturum,
        select(KayitTuru.id).where(
            KayitTuru.tanim_surumu_id == surum.id, KayitTuru.kod == kod
        ),
        f"kayıt türü {kod!r} bu sürümde zaten var.",
    )
    tur = KayitTuru(
        tanim_surumu_id=surum.id, kod=kod, gosterim_adi=gosterim_adi, aciklama=aciklama
    )
    oturum.add(tur)
    oturum.flush()
    return tur


def kayit_alani_tanimla(
    oturum: Session,
    kayit_turu_id: int,
    kod: str,
    gosterim_adi: str,
    deger_turu: DegerTuru,
    zorunlu: bool = False,
    aciklama: str | None = None,
) -> KayitAlaniTanimi:
    """Kayıt türüne yeni alan tanımı; ``kod`` tür içinde benzersiz.
    ``deger_turu`` teknik değer türü, ``zorunlu`` kaydın bu alan olmadan var
    olamayacağı anlamına gelir; kilitli sürümde de serbest."""
    _kodu_dogrula(kod, "kayıt alanı")
    _gosterim_adini_dogrula(gosterim_adi, "kayıt alanı")
    deger_turu = _deger_turunu_dogrula(deger_turu, kod, "kayıt alanı")
    _zorunlulugu_dogrula(zorunlu, kod, "kayıt alanı")
    tur = kayit_turu_getir(oturum, kayit_turu_id)
    _mukerrer_denetle(
        oturum,
        select(KayitAlaniTanimi.id).where(
            KayitAlaniTanimi.kayit_turu_id == tur.id, KayitAlaniTanimi.kod == kod
        ),
        f"kayıt alanı {kod!r} kayıt türü {tur.kod!r} için zaten var.",
    )
    alan = KayitAlaniTanimi(
        kayit_turu_id=tur.id,
        kod=kod,
        gosterim_adi=gosterim_adi,
        aciklama=aciklama,
        deger_turu=deger_turu.value,
        zorunlu=zorunlu,
    )
    oturum.add(alan)
    oturum.flush()
    return alan
