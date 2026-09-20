"""Genel nesne motoru: nesne, özellik, ilişki, hiyerarşi, yaşam durumu (Aşama 4.3).

Çekirdek bir nesnenin ne olduğunu bilmez; yalnız tanım verisinin (nesne türü,
özellik tanımı, ilişki tanımı, hiyerarşi kuralı) söylediğini uygular. Aynı kod
envanter, kütüphane ya da başka bir alan için değişmeden çalışır.

İşlem sınırı 4.1 kuralıdır: her işlev açık bir ``Session`` alır, çağıran
``Veritabani.islem`` transaction'ının sahibidir; burada ``commit`` ve dış
``rollback`` yoktur. **Servis hata atomikliği:** her yazma işlevi önce
doğrular, sonra yazar; yine de yazma sonrası doğrulama gereken yerler (nesne
oluşturmada bütün bağlantılar yazıldıktan sonra en az üst kuralı) ve
veritabanı kısıt hataları için her yazma işlevi kendi SAVEPOINT'i içinde
çalışır (``Session.begin_nested``). Başarısız bir çağrı, hatası çağıran
tarafından aynı işlem içinde yakalansa bile kendi yarattığı hiçbir değişikliği
bırakmaz; dış işlem kullanılabilir kalır ve sonraki geçerli iş commit edilebilir.

Sözleşmeler:

* **Nesne oluşturma** başlangıç özelliklerini ve üst bağlantılarını birlikte
  alır; başarılı dönüşte nesne türünün zorunlu özelliklerini taşır ve türünün
  bütün hiyerarşi kurallarını sağlar. "Önce boş nesne, sonra belki özellik"
  yolu yoktur; taslak mekanizması Aşama 4.5'in işidir.
* **Tanım sürümü kilidi**: nesne oluşturulurken kullanılan sürüm aynı işlem
  içinde ``kilitli`` yapılır; işlem rollback olursa kilit de kalkar. Kilitli
  sürüme ``tanim_islemleri`` yalnız mevcut kesin veriyi bozmayan tanım ekler
  (ekleme-yalnız kilit: zorunlu özellik ve zorunlu üst şartı yalnız
  kullanılmamış türe).
* **Özellik değeri** tanımın ``deger_turu``'ne göre doğrulanır ve kanonik
  metin olarak saklanır (kural ``deger_kodlama`` modülünde, 4.5'te aday
  özellikle ortak): metin olduğu gibi; tam sayı ``str(int)`` (``bool``
  reddedilir); mantıksal ``"1"`` / ``"0"``; ondalık sayısal kanonik biçim
  (``12.50`` → ``125e-1``; sonlu ``Decimal``, ``float`` reddedilir, ölçek
  varsayımı yoktur). Okuma aynı
  kuralla Python değerine döner. Nesneye yalnız kendi türünün özellikleri
  yazılır; ``ozellik_yaz`` var olan değeri günceller (aynı özellik iki satır
  olmaz), ``ozellik_sil`` zorunlu özelliği silmez.
* **İlişki** ``kaynak nesne → ilişki tanımı → hedef nesne``; kaynak nesnenin
  türü tanımın kaynak türü, hedefinki hedef türü, üçü aynı tanım sürümünde
  olmalı. Aynı tanımla aynı iki nesne arasında ikinci ilişki yazılmaz.
  Hiyerarşik olmayan ilişkide nesnenin kendisine dönmesine çekirdek karışmaz
  (``A → A`` geçerlidir); geçerli olup olmadığı domain'in işidir.
* **Hiyerarşi**: kuralı olan ilişki üst bağlantısıdır (kaynak çocuk, hedef
  üst). Kural yaşam durumundan bağımsız, her zaman korunur: çocuğun gerekli
  durumdaki üst sayısı ``en_az_ust``'ten az olamaz, toplam üst bağlantısı
  ``en_cok_ust``'ü aşamaz, bağlantı kurulurken üst gerekli yaşam durumunda
  olmalı. Nesne oluştururken, bağlantı kurarken ve kaldırırken, üstün yaşam
  durumu değişirken yeniden doğrulanır; çocuğun kapalı olması kuralı
  gevşetmez (böyle bir esneklik istenirse tanım verisi kararıdır, kodda
  değildir). Hiyerarşik grafikte çevrim yoktur: nesne kendi üstü olamaz ve
  ``A → B → … → A`` oluşamaz; denetim bütün hiyerarşik ilişki tanımları
  üzerinden, üst bağlantılarını izleyerek yapılır.
* **Yaşam durumu**: ``etkin`` / ``kapali``; geçiş yalnız
  ``yasam_durumunu_degistir`` ile ve hiyerarşi kurallarını bozamaz.

Hata modeli (``NesneHatasi`` altında; tanım hataları ``tanim_sorgulari``'ndan
olduğu gibi gelir):

* ``NesneBulunamadi`` — nesne ya da nesne ilişkisi kimliği yok.
* ``GecersizOzellik`` — nesnenin türünde böyle özellik yok (başka türün
  özelliği de buraya girer), zorunlu özellik silinmek isteniyor;
  ``OzellikTuruUyusmuyor`` — değer tanımın türüne uymuyor;
  ``ZorunluOzellikEksik`` — nesne oluşturulurken zorunlu özellik verilmemiş.
* ``GecersizIliski`` — tür ya da sürüm uyuşmuyor;
  ``MukerrerIliski`` — aynı ilişki zaten var.
* ``HiyerarsiIhlali`` — en az / en çok üst, üstün gerekli durumu ya da çevrim.
* ``YasamDurumuIhlali`` — geçersiz durum değeri.

Veritabanı kısıtları (``nesne_tablolari``) tür/sürüm uyumunu, başka türün
özelliğini, mükerrer özelliği ve mükerrer ilişkiyi ham SQL'e karşı da korur;
sayım ve çevrim kuralları yalnız burada doğrulanır.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from defteriki.cekirdek.deger_kodlama import (
    DegerKodlamaHatasi,
    degeri_coz,
    degeri_kodla,
)
from defteriki.cekirdek.nesne_tablolari import Nesne, NesneIliskisi, NesneOzelligi
from defteriki.cekirdek.tanim_sorgulari import (
    TanimBulunamadi,
    iliski_tanimi_getir,
    nesne_turu_getir,
)
from defteriki.cekirdek.tanim_tablolari import (
    HiyerarsiKurali,
    IliskiTanimi,
    OzellikTanimi,
    TanimSurumu,
    YasamDurumu,
    simdi_utc,
)


class NesneHatasi(Exception):
    """Nesne motoru hatalarının ortak tabanı."""


class NesneBulunamadi(NesneHatasi, LookupError):
    """Verilen kimlikle nesne ya da nesne ilişkisi yok."""


class GecersizOzellik(NesneHatasi, ValueError):
    """Nesnenin türünde böyle özellik yok ya da özellik bu işleme uygun değil."""


class OzellikTuruUyusmuyor(GecersizOzellik):
    """Değer, özellik tanımının değer türüne uymuyor."""


class ZorunluOzellikEksik(GecersizOzellik):
    """Nesne oluşturulurken zorunlu özellik verilmedi."""


class GecersizIliski(NesneHatasi, ValueError):
    """Tür ya da sürüm uyuşmuyor."""


class MukerrerIliski(GecersizIliski):
    """Aynı ilişki tanımıyla aynı iki nesne arasında ilişki zaten var."""


class HiyerarsiIhlali(NesneHatasi):
    """En az / en çok üst, üstün gerekli yaşam durumu ya da çevrim."""


class YasamDurumuIhlali(NesneHatasi, ValueError):
    """Geçersiz yaşam durumu değeri."""


@dataclass(frozen=True, slots=True)
class UstBaglanti:
    """Nesne oluşturulurken verilen üst (ya da genel hedef) bağlantısı."""

    iliski_tanimi_id: int
    hedef_nesne_id: int


# --- değer kodlama --------------------------------------------------------------------


def _degeri_kodla(tanim: OzellikTanimi, deger: object) -> str:
    """Python değerini tanımın türüne göre doğrular, kanonik metne çevirir
    (ortak kural ``deger_kodlama``; hata bu modülün hata modeline sarılır)."""
    try:
        return degeri_kodla(tanim.deger_turu, tanim.kod, deger)
    except DegerKodlamaHatasi as hata:
        raise OzellikTuruUyusmuyor(str(hata)) from None


# --- getirme --------------------------------------------------------------------------


def nesne_getir(oturum: Session, nesne_id: int) -> Nesne:
    nesne = oturum.get(Nesne, nesne_id)
    if nesne is None:
        raise NesneBulunamadi(f"nesne bulunamadı: kimlik {nesne_id}")
    return nesne


def _iliski_getir(oturum: Session, nesne_iliskisi_id: int) -> NesneIliskisi:
    iliski = oturum.get(NesneIliskisi, nesne_iliskisi_id)
    if iliski is None:
        raise NesneBulunamadi(f"nesne ilişkisi bulunamadı: kimlik {nesne_iliskisi_id}")
    return iliski


def _ozellik_tanimi_bul(oturum: Session, nesne: Nesne, kod: str) -> OzellikTanimi:
    tanim = oturum.execute(
        select(OzellikTanimi).where(
            OzellikTanimi.nesne_turu_id == nesne.nesne_turu_id,
            OzellikTanimi.kod == kod,
        )
    ).scalar_one_or_none()
    if tanim is None:
        raise GecersizOzellik(
            f"nesne {nesne.id} türünde {kod!r} adlı özellik tanımı yok."
        )
    return tanim


def _tur_tanimlari(oturum: Session, nesne_turu_id: int) -> list[OzellikTanimi]:
    return list(
        oturum.execute(
            select(OzellikTanimi)
            .where(OzellikTanimi.nesne_turu_id == nesne_turu_id)
            .order_by(OzellikTanimi.id)
        ).scalars()
    )


# --- hiyerarşi doğrulama --------------------------------------------------------------


def _cocuk_kurallari(
    oturum: Session, nesne_turu_id: int
) -> list[tuple[HiyerarsiKurali, IliskiTanimi]]:
    """Türün çocuk olduğu (kaynak) hiyerarşik ilişkilerin kuralları."""
    return [
        (kural, iliski)
        for kural, iliski in oturum.execute(
            select(HiyerarsiKurali, IliskiTanimi)
            .join(IliskiTanimi, IliskiTanimi.id == HiyerarsiKurali.iliski_tanimi_id)
            .where(IliskiTanimi.kaynak_nesne_turu_id == nesne_turu_id)
            .order_by(IliskiTanimi.kod)
        ).all()
    ]


def _ust_kurallari(
    oturum: Session, nesne_turu_id: int
) -> list[tuple[HiyerarsiKurali, IliskiTanimi]]:
    """Türün üst olduğu (hedef) ve üstten yaşam durumu isteyen kurallar."""
    return [
        (kural, iliski)
        for kural, iliski in oturum.execute(
            select(HiyerarsiKurali, IliskiTanimi)
            .join(IliskiTanimi, IliskiTanimi.id == HiyerarsiKurali.iliski_tanimi_id)
            .where(
                IliskiTanimi.hedef_nesne_turu_id == nesne_turu_id,
                HiyerarsiKurali.ust_yasam_durumu.is_not(None),
            )
            .order_by(IliskiTanimi.kod)
        ).all()
    ]


def _kural_bul(oturum: Session, iliski_tanimi_id: int) -> HiyerarsiKurali | None:
    return oturum.execute(
        select(HiyerarsiKurali).where(
            HiyerarsiKurali.iliski_tanimi_id == iliski_tanimi_id
        )
    ).scalar_one_or_none()


def _ust_durumlari(
    oturum: Session,
    cocuk_id: int,
    iliski_tanimi_id: int,
    haric_baglanti_id: int | None = None,
    durum_yerine: tuple[int, str] | None = None,
) -> list[str]:
    """Çocuğun bu ilişkiyle bağlı üstlerinin yaşam durumları.

    ``haric_baglanti_id`` kaldırılmak istenen bağlantıyı saymaz;
    ``durum_yerine`` (üst kimliği, aday durum) bir üstün durumu değişecekmiş
    gibi hesaplar. İkisi de mutasyondan önce doğrulama içindir.
    """
    satirlar = oturum.execute(
        select(NesneIliskisi.id, NesneIliskisi.hedef_nesne_id, Nesne.yasam_durumu)
        .join(Nesne, Nesne.id == NesneIliskisi.hedef_nesne_id)
        .where(
            NesneIliskisi.iliski_tanimi_id == iliski_tanimi_id,
            NesneIliskisi.kaynak_nesne_id == cocuk_id,
        )
    ).all()
    durumlar: list[str] = []
    for baglanti_id, ust_id, durum in satirlar:
        if baglanti_id == haric_baglanti_id:
            continue
        if durum_yerine is not None and ust_id == durum_yerine[0]:
            durum = durum_yerine[1]
        durumlar.append(durum)
    return durumlar


def _sayimlari_dogrula(
    cocuk_id: int, kural: HiyerarsiKurali, iliski: IliskiTanimi, durumlar: list[str]
) -> None:
    """Tek kural, verilen üst durumları için: toplam ≤ en çok; gerekli
    durumdaki üst ≥ en az. Çocuğun yaşam durumu kuralı değiştirmez."""
    if kural.en_cok_ust is not None and len(durumlar) > kural.en_cok_ust:
        raise HiyerarsiIhlali(
            f"nesne {cocuk_id}: ilişki {iliski.kod!r} için en çok {kural.en_cok_ust} "
            f"üst olabilir, {len(durumlar)} olurdu."
        )
    gecerli = [
        d
        for d in durumlar
        if kural.ust_yasam_durumu is None or d == kural.ust_yasam_durumu
    ]
    if len(gecerli) < kural.en_az_ust:
        gerek = (
            f" ({kural.ust_yasam_durumu} durumda)"
            if kural.ust_yasam_durumu is not None
            else ""
        )
        raise HiyerarsiIhlali(
            f"nesne {cocuk_id}: ilişki {iliski.kod!r} için en az {kural.en_az_ust} "
            f"üst{gerek} gerekli, {len(gecerli)} olurdu."
        )


def _cocugu_dogrula(oturum: Session, cocuk: Nesne) -> None:
    for kural, iliski in _cocuk_kurallari(oturum, cocuk.nesne_turu_id):
        _sayimlari_dogrula(
            cocuk.id, kural, iliski, _ust_durumlari(oturum, cocuk.id, iliski.id)
        )


def _cocuklari_dogrula(oturum: Session, ust: Nesne, aday_durum: str) -> None:
    """Üstün durumu ``aday_durum`` olsaydı, ondan durum isteyen kuralların
    çocukları hâlâ geçerli olur muydu? Mutasyondan önce çağrılır."""
    for kural, iliski in _ust_kurallari(oturum, ust.nesne_turu_id):
        cocuk_idleri = oturum.execute(
            select(NesneIliskisi.kaynak_nesne_id).where(
                NesneIliskisi.iliski_tanimi_id == iliski.id,
                NesneIliskisi.hedef_nesne_id == ust.id,
            )
        ).scalars()
        for cocuk_id in cocuk_idleri:
            _sayimlari_dogrula(
                cocuk_id,
                kural,
                iliski,
                _ust_durumlari(
                    oturum, cocuk_id, iliski.id, durum_yerine=(ust.id, aday_durum)
                ),
            )


def _cevrim_olusturur_mu(oturum: Session, cocuk_id: int, ust_id: int) -> bool:
    """``cocuk → ust`` üst bağlantısı hiyerarşik grafikte çevrim yapar mı?

    Çevrim, çocuğun zaten üstün (dolaylı) üstü olmasıdır: üstten başlayıp
    bütün hiyerarşik ilişki tanımlarının üst bağlantılarını yukarı doğru
    izleyerek çocuğa ulaşılıyorsa evet. ``cocuk == ust`` doğrudan çevrimdir.
    Genişlik öncelikli tarama; her nesne bir kez ziyaret edilir.
    """
    if cocuk_id == ust_id:
        return True
    gorulen = {ust_id}
    kuyruk: deque[int] = deque([ust_id])
    while kuyruk:
        simdiki = kuyruk.popleft()
        ustler = oturum.execute(
            select(NesneIliskisi.hedef_nesne_id)
            .join(
                HiyerarsiKurali,
                HiyerarsiKurali.iliski_tanimi_id == NesneIliskisi.iliski_tanimi_id,
            )
            .where(NesneIliskisi.kaynak_nesne_id == simdiki)
        ).scalars()
        for ust in ustler:
            if ust == cocuk_id:
                return True
            if ust not in gorulen:
                gorulen.add(ust)
                kuyruk.append(ust)
    return False


# --- ilişki (iç) --------------------------------------------------------------------


def _iliski_yaz(
    oturum: Session, iliski: IliskiTanimi, kaynak: Nesne, hedef: Nesne
) -> NesneIliskisi:
    """Bütün doğrulamalar yazmadan önce: tür, sürüm, mükerrerlik; hiyerarşikse
    üst durumu, en çok üst ve çevrim. En az üst kuralı bağlantı eklerken
    bozulamaz; nesne oluşturmada iş bitince ``_cocugu_dogrula`` arar."""
    if kaynak.nesne_turu_id != iliski.kaynak_nesne_turu_id:
        raise GecersizIliski(
            f"ilişki {iliski.kod!r}: kaynak nesne {kaynak.id} türü "
            f"{kaynak.nesne_turu_id}, tanım {iliski.kaynak_nesne_turu_id} bekler."
        )
    if hedef.nesne_turu_id != iliski.hedef_nesne_turu_id:
        raise GecersizIliski(
            f"ilişki {iliski.kod!r}: hedef nesne {hedef.id} türü "
            f"{hedef.nesne_turu_id}, tanım {iliski.hedef_nesne_turu_id} bekler."
        )
    if not (kaynak.tanim_surumu_id == hedef.tanim_surumu_id == iliski.tanim_surumu_id):
        raise GecersizIliski(
            f"ilişki {iliski.kod!r}: nesneler ve tanım aynı tanım sürümünde değil "
            f"({kaynak.tanim_surumu_id}, {hedef.tanim_surumu_id}, "
            f"{iliski.tanim_surumu_id})."
        )
    var = oturum.execute(
        select(NesneIliskisi.id).where(
            NesneIliskisi.iliski_tanimi_id == iliski.id,
            NesneIliskisi.kaynak_nesne_id == kaynak.id,
            NesneIliskisi.hedef_nesne_id == hedef.id,
        )
    ).first()
    if var is not None:
        raise MukerrerIliski(
            f"ilişki {iliski.kod!r} nesne {kaynak.id} → {hedef.id} zaten var."
        )
    kural = _kural_bul(oturum, iliski.id)
    if kural is not None:
        if (
            kural.ust_yasam_durumu is not None
            and hedef.yasam_durumu != kural.ust_yasam_durumu
        ):
            raise HiyerarsiIhlali(
                f"ilişki {iliski.kod!r}: üst nesne {hedef.id} "
                f"{kural.ust_yasam_durumu} durumda olmalı, {hedef.yasam_durumu}."
            )
        mevcut = _ust_durumlari(oturum, kaynak.id, iliski.id)
        if kural.en_cok_ust is not None and len(mevcut) + 1 > kural.en_cok_ust:
            raise HiyerarsiIhlali(
                f"nesne {kaynak.id}: ilişki {iliski.kod!r} için en çok "
                f"{kural.en_cok_ust} üst olabilir, {len(mevcut) + 1} olurdu."
            )
        if _cevrim_olusturur_mu(oturum, kaynak.id, hedef.id):
            raise HiyerarsiIhlali(
                f"ilişki {iliski.kod!r}: nesne {kaynak.id} → {hedef.id} hiyerarşide "
                "çevrim oluşturur; nesne kendi (dolaylı) üstü olamaz."
            )
    satir = NesneIliskisi(
        iliski_tanimi_id=iliski.id,
        tanim_surumu_id=iliski.tanim_surumu_id,
        kaynak_nesne_turu_id=iliski.kaynak_nesne_turu_id,
        hedef_nesne_turu_id=iliski.hedef_nesne_turu_id,
        kaynak_nesne_id=kaynak.id,
        hedef_nesne_id=hedef.id,
    )
    oturum.add(satir)
    oturum.flush()
    return satir


# --- nesne ----------------------------------------------------------------------------


def nesne_olustur(
    oturum: Session,
    nesne_turu_id: int,
    ozellikler: Mapping[str, object] | None = None,
    ust_baglantilar: Sequence[UstBaglanti] = (),
) -> Nesne:
    """Türün tanımıyla yeni, etkin nesne; özellikler ve üst bağlantılar tek işte.

    Sıra: özellikler yazmadan doğrulanır (tanımsız kod, tür uyuşmazlığı, eksik
    zorunlu özellik) → SAVEPOINT içinde nesne satırı, özellik satırları,
    bağlantılar (her biri yazmadan doğrulanır) → türün bütün hiyerarşi
    kuralları (en az üst) → tanım sürümü kilidi. Herhangi bir hata SAVEPOINT'i
    geri alır ve yükselir; çağıran yakalasa da hiçbir parça kalmaz.
    """
    tur = nesne_turu_getir(oturum, nesne_turu_id)
    surum = oturum.get(TanimSurumu, tur.tanim_surumu_id)
    if surum is None:  # dış anahtar bunu engeller; sözleşme için
        raise TanimBulunamadi(f"tanım sürümü bulunamadı: kimlik {tur.tanim_surumu_id}")

    verilen = dict(ozellikler or {})
    tanimlar = {t.kod: t for t in _tur_tanimlari(oturum, tur.id)}
    for kod in verilen:
        if kod not in tanimlar:
            raise GecersizOzellik(
                f"nesne türü {tur.kod!r} için {kod!r} adlı özellik tanımı yok."
            )
    eksik = [t.kod for t in tanimlar.values() if t.zorunlu and t.kod not in verilen]
    if eksik:
        raise ZorunluOzellikEksik(
            f"nesne türü {tur.kod!r}: zorunlu özellik eksik: {', '.join(eksik)}."
        )
    kodlanmis = {
        kod: _degeri_kodla(tanimlar[kod], deger) for kod, deger in verilen.items()
    }

    with oturum.begin_nested():
        nesne = Nesne(
            nesne_turu_id=tur.id,
            tanim_surumu_id=tur.tanim_surumu_id,
            yasam_durumu=YasamDurumu.ETKIN.value,
            olusturma_zamani=simdi_utc(),
        )
        oturum.add(nesne)
        oturum.flush()
        for kod, metin in kodlanmis.items():
            oturum.add(
                NesneOzelligi(
                    nesne_id=nesne.id,
                    nesne_turu_id=tur.id,
                    ozellik_tanimi_id=tanimlar[kod].id,
                    deger=metin,
                )
            )
        oturum.flush()
        for baglanti in ust_baglantilar:
            iliski = iliski_tanimi_getir(oturum, baglanti.iliski_tanimi_id)
            hedef = nesne_getir(oturum, baglanti.hedef_nesne_id)
            _iliski_yaz(oturum, iliski, nesne, hedef)
        _cocugu_dogrula(oturum, nesne)
        if not surum.kilitli:
            surum.kilitli = True
            oturum.flush()
    return nesne


def nesneleri_listele(oturum: Session, nesne_turu_id: int) -> list[Nesne]:
    """Türün nesneleri, kimlik sırasıyla; tür yoksa ``TanimBulunamadi``."""
    tur = nesne_turu_getir(oturum, nesne_turu_id)
    return list(
        oturum.execute(
            select(Nesne).where(Nesne.nesne_turu_id == tur.id).order_by(Nesne.id)
        ).scalars()
    )


def yasam_durumunu_degistir(
    oturum: Session, nesne_id: int, yeni_durum: YasamDurumu
) -> Nesne:
    """Nesnenin yaşam durumunu değiştirir; hiyerarşi kurallarını bozamaz.

    Ondan durum isteyen kuralların çocukları, aday durumla yazmadan önce
    doğrulanır; ihlal varsa durum değişmez.
    """
    try:
        yeni_durum = YasamDurumu(yeni_durum)
    except ValueError:
        raise YasamDurumuIhlali(f"geçersiz yaşam durumu: {yeni_durum!r}") from None
    nesne = nesne_getir(oturum, nesne_id)
    if nesne.yasam_durumu == yeni_durum.value:
        return nesne
    _cocuklari_dogrula(oturum, nesne, yeni_durum.value)
    with oturum.begin_nested():
        nesne.yasam_durumu = yeni_durum.value
        oturum.flush()
    return nesne


# --- özellik --------------------------------------------------------------------------


def ozellik_yaz(
    oturum: Session, nesne_id: int, kod: str, deger: object
) -> NesneOzelligi:
    """Nesnenin türündeki ``kod`` özelliğini yazar; varsa değeri günceller."""
    nesne = nesne_getir(oturum, nesne_id)
    tanim = _ozellik_tanimi_bul(oturum, nesne, kod)
    metin = _degeri_kodla(tanim, deger)
    satir = oturum.execute(
        select(NesneOzelligi).where(
            NesneOzelligi.nesne_id == nesne.id,
            NesneOzelligi.ozellik_tanimi_id == tanim.id,
        )
    ).scalar_one_or_none()
    with oturum.begin_nested():
        if satir is None:
            satir = NesneOzelligi(
                nesne_id=nesne.id,
                nesne_turu_id=nesne.nesne_turu_id,
                ozellik_tanimi_id=tanim.id,
                deger=metin,
            )
            oturum.add(satir)
        else:
            satir.deger = metin
        oturum.flush()
    return satir


def ozellik_sil(oturum: Session, nesne_id: int, kod: str) -> None:
    """İsteğe bağlı özelliği kaldırır; zorunlu özellik ya da yazılmamış özellik
    için ``GecersizOzellik``."""
    nesne = nesne_getir(oturum, nesne_id)
    tanim = _ozellik_tanimi_bul(oturum, nesne, kod)
    if tanim.zorunlu:
        raise GecersizOzellik(
            f"özellik {kod!r} zorunlu; nesne {nesne.id}'den silinemez."
        )
    satir = oturum.execute(
        select(NesneOzelligi).where(
            NesneOzelligi.nesne_id == nesne.id,
            NesneOzelligi.ozellik_tanimi_id == tanim.id,
        )
    ).scalar_one_or_none()
    if satir is None:
        raise GecersizOzellik(
            f"nesne {nesne.id} üzerinde {kod!r} özelliği yazılı değil."
        )
    with oturum.begin_nested():
        oturum.delete(satir)
        oturum.flush()


def ozellikleri_oku(oturum: Session, nesne_id: int) -> dict[str, object]:
    """Nesnenin yazılı özellikleri: kod → türüne çözülmüş Python değeri."""
    nesne = nesne_getir(oturum, nesne_id)
    satirlar = oturum.execute(
        select(OzellikTanimi.kod, OzellikTanimi.deger_turu, NesneOzelligi.deger)
        .join(NesneOzelligi, NesneOzelligi.ozellik_tanimi_id == OzellikTanimi.id)
        .where(NesneOzelligi.nesne_id == nesne.id)
        .order_by(OzellikTanimi.id)
    ).all()
    return {kod: degeri_coz(deger_turu, deger) for kod, deger_turu, deger in satirlar}


# --- ilişki ---------------------------------------------------------------------------


def iliski_kur(
    oturum: Session, iliski_tanimi_id: int, kaynak_nesne_id: int, hedef_nesne_id: int
) -> NesneIliskisi:
    """İki var olan nesne arasında ilişki; hiyerarşikse kuralı ve çevrimi denetler."""
    iliski = iliski_tanimi_getir(oturum, iliski_tanimi_id)
    kaynak = nesne_getir(oturum, kaynak_nesne_id)
    hedef = nesne_getir(oturum, hedef_nesne_id)
    with oturum.begin_nested():
        return _iliski_yaz(oturum, iliski, kaynak, hedef)


def iliski_kaldir(oturum: Session, nesne_iliskisi_id: int) -> None:
    """İlişkiyi kaldırır; hiyerarşikse çocuğun en az üst kuralı bozulamaz
    (silmeden önce, bu bağlantı sayılmadan doğrulanır)."""
    satir = _iliski_getir(oturum, nesne_iliskisi_id)
    iliski = iliski_tanimi_getir(oturum, satir.iliski_tanimi_id)
    kural = _kural_bul(oturum, iliski.id)
    if kural is not None:
        _sayimlari_dogrula(
            satir.kaynak_nesne_id,
            kural,
            iliski,
            _ust_durumlari(
                oturum, satir.kaynak_nesne_id, iliski.id, haric_baglanti_id=satir.id
            ),
        )
    with oturum.begin_nested():
        oturum.delete(satir)
        oturum.flush()


def iliskileri_listele(oturum: Session, nesne_id: int) -> list[NesneIliskisi]:
    """Nesnenin kaynak ya da hedef olduğu ilişkiler, kimlik sırasıyla."""
    nesne = nesne_getir(oturum, nesne_id)
    return list(
        oturum.execute(
            select(NesneIliskisi)
            .where(
                (NesneIliskisi.kaynak_nesne_id == nesne.id)
                | (NesneIliskisi.hedef_nesne_id == nesne.id)
            )
            .order_by(NesneIliskisi.id)
        ).scalars()
    )
