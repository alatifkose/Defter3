"""Genel nesne motoru: nesne, özellik, ilişki, hiyerarşi, yaşam durumu (Aşama 4.3).

Çekirdek bir nesnenin ne olduğunu bilmez; yalnız tanım verisinin (nesne türü,
özellik tanımı, ilişki tanımı, hiyerarşi kuralı) söylediğini uygular. Aynı kod
envanter, kütüphane ya da başka bir alan için değişmeden çalışır.

İşlem sınırı 4.1 kuralıdır: her işlev açık bir ``Session`` alır, çağıran
``Veritabani.islem`` transaction'ının sahibidir; burada ``commit`` yoktur.
Nesne oluşturma tek işte nesneyi, özelliklerini, üst bağlantılarını ve tanım
sürümü kilidini yazar; herhangi bir adım düşerse çağıranın rollback'i hepsini
geri alır.

Sözleşmeler:

* **Nesne oluşturma** başlangıç özelliklerini ve üst bağlantılarını birlikte
  alır; başarılı dönüşte nesne türünün zorunlu özelliklerini taşır ve türünün
  bütün hiyerarşi kurallarını sağlar. "Önce boş nesne, sonra belki özellik"
  yolu yoktur; taslak mekanizması Aşama 4.5'in işidir.
* **Tanım sürümü kilidi**: nesne oluşturulurken kullanılan sürüm aynı işlem
  içinde ``kilitli`` yapılır; işlem rollback olursa kilit de kalkar. Kilitli
  sürüme ``tanim_islemleri`` yeni tanım eklemez.
* **Özellik değeri** tanımın ``deger_turu``'ne göre doğrulanır ve kanonik
  metin olarak saklanır: metin olduğu gibi; tam sayı ``str(int)`` (``bool``
  reddedilir); mantıksal ``"1"`` / ``"0"``; ondalık ``str(Decimal)`` (sonlu
  ``Decimal``; ``float`` reddedilir, ölçek varsayımı yoktur). Okuma aynı
  kuralla Python değerine döner. Nesneye yalnız kendi türünün özellikleri
  yazılır; ``ozellik_yaz`` var olan değeri günceller (aynı özellik iki satır
  olmaz), ``ozellik_sil`` zorunlu özelliği silmez.
* **İlişki** ``kaynak nesne → ilişki tanımı → hedef nesne``; kaynak nesnenin
  türü tanımın kaynak türü, hedefinki hedef türü, üçü aynı tanım sürümünde
  olmalı. Aynı tanımla aynı iki nesne arasında ikinci ilişki yazılmaz.
* **Hiyerarşi**: kuralı olan ilişki üst bağlantısıdır (kaynak çocuk, hedef
  üst). Her zaman korunan kural: etkin çocuğun, gerekli durumdaki üst sayısı
  ``en_az_ust``'ten az olamaz; toplam üst bağlantısı ``en_cok_ust``'ü aşamaz;
  bağlantı kurulurken üst gerekli yaşam durumunda olmalı. Bu, nesne
  oluştururken, bağlantı kurarken ve kaldırırken, çocuğun ya da üstün yaşam
  durumu değişirken yeniden doğrulanır. Kapalı çocuk için en az üst kuralı
  aranmaz (bir alt ağaç önce çocuklardan başlayarak kapatılabilir); etkin
  yapılırken yeniden aranır.
* **Yaşam durumu**: ``etkin`` / ``kapali``; geçiş yalnız
  ``yasam_durumunu_degistir`` ile ve hiyerarşi kurallarını bozamaz.

Hata modeli (``NesneHatasi`` altında; tanım hataları ``tanim_islemleri``'nden
olduğu gibi gelir):

* ``NesneBulunamadi`` — nesne ya da nesne ilişkisi kimliği yok.
* ``GecersizOzellik`` — nesnenin türünde böyle özellik yok (başka türün
  özelliği de buraya girer), zorunlu özellik silinmek isteniyor;
  ``OzellikTuruUyusmuyor`` — değer tanımın türüne uymuyor;
  ``ZorunluOzellikEksik`` — nesne oluşturulurken zorunlu özellik verilmemiş.
* ``GecersizIliski`` — tür ya da sürüm uyuşmuyor, nesne kendisiyle;
  ``MukerrerIliski`` — aynı ilişki zaten var.
* ``HiyerarsiIhlali`` — en az / en çok üst ya da üstün gerekli durumu.
* ``YasamDurumuIhlali`` — geçersiz durum değeri.

Veritabanı kısıtları (``nesne_tablolari``) tür/sürüm uyumunu, başka türün
özelliğini, mükerrer özelliği ve mükerrer ilişkiyi ham SQL'e karşı da korur;
sayım kuralları yalnız burada doğrulanır.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from defteriki.cekirdek.nesne_tablolari import Nesne, NesneIliskisi, NesneOzelligi
from defteriki.cekirdek.tanim_islemleri import (
    TanimBulunamadi,
    iliski_tanimi_getir,
    nesne_turu_getir,
)
from defteriki.cekirdek.tanim_tablolari import (
    DegerTuru,
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
    """Tür ya da sürüm uyuşmuyor, nesne kendisiyle ilişkilendiriliyor."""


class MukerrerIliski(GecersizIliski):
    """Aynı ilişki tanımıyla aynı iki nesne arasında ilişki zaten var."""


class HiyerarsiIhlali(NesneHatasi):
    """En az / en çok üst sayısı ya da üstün gerekli yaşam durumu sağlanmıyor."""


class YasamDurumuIhlali(NesneHatasi, ValueError):
    """Geçersiz yaşam durumu değeri."""


@dataclass(frozen=True, slots=True)
class UstBaglanti:
    """Nesne oluşturulurken verilen üst (ya da genel hedef) bağlantısı."""

    iliski_tanimi_id: int
    hedef_nesne_id: int


# --- değer kodlama --------------------------------------------------------------------


def _degeri_kodla(tanim: OzellikTanimi, deger: object) -> str:
    """Python değerini tanımın türüne göre doğrular, kanonik metne çevirir."""
    tur = DegerTuru(tanim.deger_turu)
    hata = OzellikTuruUyusmuyor(
        f"özellik {tanim.kod!r} {tur.value} bekler, {type(deger).__name__} verildi."
    )
    if tur is DegerTuru.METIN:
        if not isinstance(deger, str):
            raise hata
        return deger
    if tur is DegerTuru.TAM_SAYI:
        if type(deger) is not int:
            raise hata
        return str(deger)
    if tur is DegerTuru.MANTIKSAL:
        if type(deger) is not bool:
            raise hata
        return "1" if deger else "0"
    if not isinstance(deger, Decimal) or not deger.is_finite():
        raise hata
    return str(deger)


def _degeri_coz(deger_turu: str, metin: str) -> object:
    """Saklanan kanonik metni Python değerine çevirir."""
    tur = DegerTuru(deger_turu)
    if tur is DegerTuru.METIN:
        return metin
    if tur is DegerTuru.TAM_SAYI:
        return int(metin)
    if tur is DegerTuru.MANTIKSAL:
        return metin == "1"
    return Decimal(metin)


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


def _ust_durumlari(oturum: Session, cocuk: Nesne, iliski: IliskiTanimi) -> list[str]:
    """Çocuğun bu ilişkiyle bağlı üstlerinin yaşam durumları."""
    return list(
        oturum.execute(
            select(Nesne.yasam_durumu)
            .join(NesneIliskisi, NesneIliskisi.hedef_nesne_id == Nesne.id)
            .where(
                NesneIliskisi.iliski_tanimi_id == iliski.id,
                NesneIliskisi.kaynak_nesne_id == cocuk.id,
            )
        ).scalars()
    )


def _kurali_dogrula(
    oturum: Session,
    cocuk: Nesne,
    kural: HiyerarsiKurali,
    iliski: IliskiTanimi,
    yalniz_en_cok: bool = False,
) -> None:
    """Tek kural: toplam üst ≤ en çok; etkin çocuk için gerekli durumdaki üst
    ≥ en az. ``yalniz_en_cok`` bağlantı yazılırken kullanılır: en az kuralı iş
    bitince (bütün bağlantılar yazılınca) aranır."""
    durumlar = _ust_durumlari(oturum, cocuk, iliski)
    if kural.en_cok_ust is not None and len(durumlar) > kural.en_cok_ust:
        raise HiyerarsiIhlali(
            f"nesne {cocuk.id}: ilişki {iliski.kod!r} için en çok {kural.en_cok_ust} "
            f"üst olabilir, {len(durumlar)} var."
        )
    if yalniz_en_cok or cocuk.yasam_durumu != YasamDurumu.ETKIN.value:
        return
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
            f"nesne {cocuk.id}: ilişki {iliski.kod!r} için en az {kural.en_az_ust} "
            f"üst{gerek} gerekli, {len(gecerli)} var."
        )


def _cocugu_dogrula(oturum: Session, cocuk: Nesne) -> None:
    for kural, iliski in _cocuk_kurallari(oturum, cocuk.nesne_turu_id):
        _kurali_dogrula(oturum, cocuk, kural, iliski)


def _cocuklari_dogrula(oturum: Session, ust: Nesne) -> None:
    """Üstün durumu değişince, ondan durum isteyen kuralların çocuklarını yeniden
    doğrular (yalnız etkin çocuklar aranır; ``_kurali_dogrula`` bunu bilir)."""
    for kural, iliski in _ust_kurallari(oturum, ust.nesne_turu_id):
        cocuklar = oturum.execute(
            select(Nesne)
            .join(NesneIliskisi, NesneIliskisi.kaynak_nesne_id == Nesne.id)
            .where(
                NesneIliskisi.iliski_tanimi_id == iliski.id,
                NesneIliskisi.hedef_nesne_id == ust.id,
            )
        ).scalars()
        for cocuk in cocuklar:
            _kurali_dogrula(oturum, cocuk, kural, iliski)


# --- ilişki (iç) ----------------------------------------------------------------------


def _iliski_yaz(
    oturum: Session, iliski: IliskiTanimi, kaynak: Nesne, hedef: Nesne
) -> NesneIliskisi:
    """Doğrulanmış ilişki satırı; hiyerarşi kuralını (üst durumu, en çok) uygular.
    En az üst kuralı çağıranın işi bitince ``_cocugu_dogrula`` ile aranır."""
    if kaynak.id == hedef.id:
        raise GecersizIliski(f"nesne {kaynak.id} kendisiyle ilişkilendirilemez.")
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
    if (
        kural is not None
        and kural.ust_yasam_durumu is not None
        and hedef.yasam_durumu != kural.ust_yasam_durumu
    ):
        raise HiyerarsiIhlali(
            f"ilişki {iliski.kod!r}: üst nesne {hedef.id} {kural.ust_yasam_durumu} "
            f"durumda olmalı, {hedef.yasam_durumu}."
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
    if kural is not None:
        _kurali_dogrula(oturum, kaynak, kural, iliski, yalniz_en_cok=True)
    return satir


# --- nesne ----------------------------------------------------------------------------


def nesne_olustur(
    oturum: Session,
    nesne_turu_id: int,
    ozellikler: Mapping[str, object] | None = None,
    ust_baglantilar: Sequence[UstBaglanti] = (),
) -> Nesne:
    """Türün tanımıyla yeni, etkin nesne; özellikler ve üst bağlantılar tek işte.

    Sıra: nesne satırı → özellikler (tanımsız kod, tür uyuşmazlığı, eksik
    zorunlu özellik reddedilir) → bağlantılar (nesne kaynak, verilen nesne
    hedef) → türün bütün hiyerarşi kuralları → tanım sürümü kilidi. Herhangi
    bir hata çağıranın işlem sınırında yükselir; hiçbir parça kalmaz.
    """
    tur = nesne_turu_getir(oturum, nesne_turu_id)
    surum = oturum.get(TanimSurumu, tur.tanim_surumu_id)
    if surum is None:  # dış anahtar bunu engeller; sözleşme için
        raise TanimBulunamadi(f"tanım sürümü bulunamadı: kimlik {tur.tanim_surumu_id}")
    nesne = Nesne(
        nesne_turu_id=tur.id,
        tanim_surumu_id=tur.tanim_surumu_id,
        yasam_durumu=YasamDurumu.ETKIN.value,
        olusturma_zamani=simdi_utc(),
    )
    oturum.add(nesne)
    oturum.flush()

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
    for kod, deger in verilen.items():
        tanim = tanimlar[kod]
        oturum.add(
            NesneOzelligi(
                nesne_id=nesne.id,
                nesne_turu_id=tur.id,
                ozellik_tanimi_id=tanim.id,
                deger=_degeri_kodla(tanim, deger),
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

    Etkin yapılırken nesnenin kendi üst kuralları, herhangi bir değişimde
    ondan durum isteyen kuralların (etkin) çocukları yeniden doğrulanır.
    """
    try:
        yeni_durum = YasamDurumu(yeni_durum)
    except ValueError:
        raise YasamDurumuIhlali(f"geçersiz yaşam durumu: {yeni_durum!r}") from None
    nesne = nesne_getir(oturum, nesne_id)
    if nesne.yasam_durumu == yeni_durum.value:
        return nesne
    nesne.yasam_durumu = yeni_durum.value
    oturum.flush()
    if yeni_durum is YasamDurumu.ETKIN:
        _cocugu_dogrula(oturum, nesne)
    _cocuklari_dogrula(oturum, nesne)
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
    return {kod: _degeri_coz(deger_turu, deger) for kod, deger_turu, deger in satirlar}


# --- ilişki ---------------------------------------------------------------------------


def iliski_kur(
    oturum: Session, iliski_tanimi_id: int, kaynak_nesne_id: int, hedef_nesne_id: int
) -> NesneIliskisi:
    """İki var olan nesne arasında ilişki; hiyerarşikse kuralı uygular."""
    iliski = iliski_tanimi_getir(oturum, iliski_tanimi_id)
    kaynak = nesne_getir(oturum, kaynak_nesne_id)
    hedef = nesne_getir(oturum, hedef_nesne_id)
    return _iliski_yaz(oturum, iliski, kaynak, hedef)


def iliski_kaldir(oturum: Session, nesne_iliskisi_id: int) -> None:
    """İlişkiyi kaldırır; hiyerarşikse çocuğun en az üst kuralı bozulamaz."""
    satir = _iliski_getir(oturum, nesne_iliskisi_id)
    kaynak = nesne_getir(oturum, satir.kaynak_nesne_id)
    iliski = iliski_tanimi_getir(oturum, satir.iliski_tanimi_id)
    kural = _kural_bul(oturum, iliski.id)
    oturum.delete(satir)
    oturum.flush()
    if kural is not None:
        _kurali_dogrula(oturum, kaynak, kural, iliski)


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
