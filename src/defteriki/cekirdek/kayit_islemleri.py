"""Kesin kayıt servisi (Aşama 4.7/3): tek atomik oluşturma ve okuma.

Kesin kayıt tek bir kapıdan doğar: ``kayit_olustur``. Kayıt satırı, bütün alan
satırları ve nesne bağları **aynı** SAVEPOINT içinde yazılır; herhangi bir
hata hiçbir parça bırakmaz. Bunun sebebi ``kayit_tablolari``ndaki karardır:
kaydın taslak ya da kesinleşme durumu yoktur, satırın varlığı kesinliktir —
öyleyse yarım (alanı eksik, bağı eksik) bir kesin kayıt veritabanında
bulunamamalıdır.

Sıra sabittir ve **doğrulama mutasyondan önce** biter: paket ve okuma → kayıt
türü ve tanım sürümü → kaynak → alan tanımları (tanımsız ad, eksik zorunlu
alan, değer türü, kanonik kodlama) → nesneler (var mı, etkin mi, yinelenmiş
mi). Ancak hepsi geçerse yazma başlar.

Alan değeri yazmadan sonra değiştirilemez, silinemez; kayıt da silinemez. Bu
modülde öyle bir işlev yoktur: düzeltme ve geri alma yaşam döngüsü Aşama
4.14'ün işidir ve kendi semantiğiyle gelecektir.

**Sınır.** Bu modül tek bir kaydın bütünlüğünden sorumludur. Aday veriyi kesin
kayda dönüştürmek, paketi kesinleştirmek, belgeyi kayıtlı duruma geçirmek ve
bu dönüşümün orkestrasyonu Aşama 4.8'indir; 4.8 hazırladığı veriyi buradaki
servise verir, kendi kayıt satırını yazmaz.

Çekirdek burada da domain bilmez: hangi alanın ne anlama geldiği, hangi kayıt
türünün hangi nesneye bağlanabileceği tanım verisinin (ileride kural
sisteminin, Aşama 4.9) işidir. Sayısal değer ``deger_kodlama`` ile kanonik
metne çevrilir; ölçek ya da birim varsayımı yoktur.

Hata modeli (hepsi ``KayitHatasi`` altında): ``KayitBulunamadi``,
``KayitKokeniGecersiz``, ``TanimsizKayitAlani``, ``ZorunluKayitAlaniEksik``,
``KayitAlaniDegeriGecersiz``, ``KayitNesneBagiGecersiz``,
``KayitYazmaCakismasi``. Paketin kendisiyle ilgili hatalar taslak dünyasının
kapısından (``taslak_islemleri.yazilabilir_paket``) olduğu gibi gelir:
``PaketBulunamadi`` ve ``PaketDurumuGecersiz``.
"""

from __future__ import annotations

from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from defteriki.cekirdek.belge_islemleri import (
    arsiv_dosyasi_getir,
    belge_getir,
    okuma_getir,
)
from defteriki.cekirdek.belge_tablolari import ArsivDosyasi, Belge, Kaynak, Okuma
from defteriki.cekirdek.deger_kodlama import (
    DegerKodlamaHatasi,
    degeri_coz,
    degeri_kodla,
)
from defteriki.cekirdek.denetim_islemleri import olay_yaz
from defteriki.cekirdek.denetim_tablolari import Aktor, DenetimOlayi
from defteriki.cekirdek.kayit_tablolari import (
    KAYIT_ALANI,
    KAYIT_NESNE,
    Kayit,
    KayitAlani,
    KayitNesne,
)
from defteriki.cekirdek.nesne_tablolari import Nesne
from defteriki.cekirdek.tanim_sorgulari import (
    kayit_alani_tanimlarini_listele,
    kayit_turu_getir,
)
from defteriki.cekirdek.tanim_tablolari import (
    KayitAlaniTanimi,
    KayitTuru,
    YasamDurumu,
    simdi_utc,
)
from defteriki.cekirdek.taslak_islemleri import (
    benzersizlik_ihlali_mi,
    kilit_cakismasi_mi,
    yazilabilir_paket,
)
from defteriki.cekirdek.taslak_tablolari import IslemPaketi


class KayitHatasi(Exception):
    """Kesin kayıt hatalarının ortak tabanı."""


class KayitBulunamadi(KayitHatasi, LookupError):
    """Verilen kimlikte kesin kayıt yok."""


class KayitKokeniGecersiz(KayitHatasi):
    """Kaynak yok ya da kaydın paketinin okumasına ait değil."""


class TanimsizKayitAlani(KayitHatasi, ValueError):
    """Verilen alan adı bu kayıt türünde tanımlı değil."""


class ZorunluKayitAlaniEksik(KayitHatasi, ValueError):
    """Kayıt türünün zorunlu alanlarından biri verilmedi."""


class KayitAlaniDegeriGecersiz(KayitHatasi, ValueError):
    """Değer, alan tanımının değer türüne uymuyor."""


class KayitNesneBagiGecersiz(KayitHatasi, ValueError):
    """Nesne listesi boş, yinelenmiş kimlik taşıyor ya da nesne yok / kapalı."""


class KayitYazmaCakismasi(KayitHatasi):
    """Eşzamanlı yazma çatışması; çağıran yeni işlemde yeniden dener."""


@dataclass(frozen=True, slots=True)
class KayitKokeni:
    """Kaydın belgeye kadar giden kökeni; her halka kimlikle bulunur."""

    kayit: Kayit
    islem_paketi: IslemPaketi
    okuma: Okuma
    belge: Belge
    arsiv_dosyasi: ArsivDosyasi
    kaynak_id: int | None


@contextmanager
def _yazma_siniri(oturum: Session) -> Generator[None, None, None]:
    """Yazmanın tek kapısı: SAVEPOINT (``begin_nested``) + dar hata eşleme.

    Kilit / anlık görüntü çakışması ve kendi tablolarımızın benzersizlik
    ihlali ``KayitYazmaCakismasi``e döner (servis aynı ihlali önceden
    reddettiğine göre geriye yalnız eşzamanlı yazma kalır); başka veritabanı
    hataları olduğu gibi yükselir.
    """
    try:
        with oturum.begin_nested():
            yield
    except IntegrityError as hata:
        if benzersizlik_ihlali_mi(hata, KAYIT_ALANI) or benzersizlik_ihlali_mi(
            hata, KAYIT_NESNE
        ):
            raise KayitYazmaCakismasi(
                "eşzamanlı yazma çatışması: aynı alan ya da bağ başka bir "
                "bağlantı tarafından yazıldı; işlemi geri alıp yeniden deneyin."
            ) from None
        raise
    except OperationalError as hata:
        if kilit_cakismasi_mi(hata):
            raise KayitYazmaCakismasi(
                "eşzamanlı yazma çatışması: başka bir bağlantı aynı anda yazdı; "
                "işlemi geri alıp yeni işlemde yeniden deneyin."
            ) from None
        raise


# --- doğrulama (mutasyon yok) ---------------------------------------------------------


def _kaynagi_dogrula(oturum: Session, kaynak_id: int, okuma_id: int) -> None:
    """Kaynak var mı ve paketin okumasına mı ait (şema da reddeder; servis
    hatayı adıyla verir)."""
    kaynak = oturum.get(Kaynak, kaynak_id)
    if kaynak is None:
        raise KayitKokeniGecersiz(f"kaynak bulunamadı: kimlik {kaynak_id}")
    if kaynak.okuma_id != okuma_id:
        raise KayitKokeniGecersiz(
            f"kaynak {kaynak_id} kaydın okumasına ({okuma_id}) ait değil; kesin "
            "kayıt kendi belgesinden başka bir belgenin parçasına dayanamaz."
        )


def _alanlari_kodla(
    oturum: Session, tur: KayitTuru, alanlar: Mapping[str, object]
) -> list[tuple[KayitAlaniTanimi, str]]:
    """Alan adlarını, zorunlulukları ve değer türlerini doğrular; kanonik
    metinleri tanım sırasıyla döndürür. Hiçbir satır yazılmaz."""
    tanimlar = {t.kod: t for t in kayit_alani_tanimlarini_listele(oturum, tur.id)}
    for kod in alanlar:
        if kod not in tanimlar:
            raise TanimsizKayitAlani(
                f"kayıt türü {tur.kod!r} için {kod!r} adlı alan tanımı yok."
            )
    eksik = [t.kod for t in tanimlar.values() if t.zorunlu and t.kod not in alanlar]
    if eksik:
        raise ZorunluKayitAlaniEksik(
            f"kayıt türü {tur.kod!r}: zorunlu alan eksik: {', '.join(eksik)}."
        )
    kodlanmis: list[tuple[KayitAlaniTanimi, str]] = []
    for tanim in tanimlar.values():
        if tanim.kod not in alanlar:
            continue
        try:
            metin = degeri_kodla(tanim.deger_turu, tanim.kod, alanlar[tanim.kod])
        except DegerKodlamaHatasi as hata:
            raise KayitAlaniDegeriGecersiz(str(hata)) from None
        kodlanmis.append((tanim, metin))
    return kodlanmis


def _nesneleri_dogrula(oturum: Session, nesne_idleri: Sequence[int]) -> list[int]:
    """Nesne listesi doğrulanır: en az bir, yinelenmeyen, var olan ve etkin."""
    if not nesne_idleri:
        raise KayitNesneBagiGecersiz(
            "kesin kayıt en az bir nesneye bağlanmalı: kayıt, nesnelerle "
            "ilişkilendirilen olaydır."
        )
    if len(set(nesne_idleri)) != len(nesne_idleri):
        raise KayitNesneBagiGecersiz(
            "aynı nesne kimliği birden fazla kez verildi; bağ rolsüzdür ve bir "
            "kez yazılır."
        )
    for nesne_id in nesne_idleri:
        nesne = oturum.get(Nesne, nesne_id)
        if nesne is None:
            raise KayitNesneBagiGecersiz(f"nesne bulunamadı: kimlik {nesne_id}")
        if nesne.yasam_durumu != YasamDurumu.ETKIN.value:
            raise KayitNesneBagiGecersiz(
                f"nesne {nesne_id} {nesne.yasam_durumu}; kesin kayıt yalnız etkin "
                "nesneye bağlanır (birleşmiş nesnenin bağları kanonik nesnededir)."
            )
    return list(nesne_idleri)


# --- oluşturma ------------------------------------------------------------------------


def kayit_olustur(
    oturum: Session,
    islem_paketi_id: int,
    kayit_turu_id: int,
    alanlar: Mapping[str, object],
    nesne_idleri: Sequence[int],
    aktor: Aktor,
    *,
    kaynak_id: int | None = None,
) -> Kayit:
    """Kesin kaydı alanları ve nesne bağlarıyla birlikte tek işte oluşturur.

    ``islem_paketi_id`` zorunludur ve paket ``calisiyor`` olmalıdır; kaydın
    ``okuma_id``si paketten alınır, çağıran veremez. ``kaynak_id``
    verilirse aynı okumaya ait olmalıdır. ``alanlar`` kayıt türünün tanımlı
    alan adlarıyla verilir; zorunlu alanların hepsi bulunmalıdır. Değerler
    ``deger_kodlama`` ile kanonik metne çevrilir.

    Doğrulama mutasyondan önce biter; yazma tek SAVEPOINT içindedir. Herhangi
    bir hata hiçbir ``kayit`` / ``kayit_alani`` / ``kayit_nesne`` satırı
    bırakmaz (çağıran hatayı yutup işlemi commit etse bile).
    """
    paket = yazilabilir_paket(oturum, islem_paketi_id)
    tur = kayit_turu_getir(oturum, kayit_turu_id)
    if kaynak_id is not None:
        _kaynagi_dogrula(oturum, kaynak_id, paket.okuma_id)
    kodlanmis = _alanlari_kodla(oturum, tur, alanlar)
    baglanacak = _nesneleri_dogrula(oturum, nesne_idleri)

    with _yazma_siniri(oturum):
        kayit = Kayit(
            kayit_turu_id=tur.id,
            tanim_surumu_id=tur.tanim_surumu_id,
            islem_paketi_id=paket.id,
            okuma_id=paket.okuma_id,
            kaynak_id=kaynak_id,
            olusturma_zamani=simdi_utc(),
        )
        oturum.add(kayit)
        oturum.flush()
        for tanim, metin in kodlanmis:
            oturum.add(
                KayitAlani(
                    kayit_id=kayit.id,
                    kayit_turu_id=tur.id,
                    kayit_alani_tanimi_id=tanim.id,
                    deger=metin,
                )
            )
        for nesne_id in baglanacak:
            oturum.add(KayitNesne(kayit_id=kayit.id, nesne_id=nesne_id))
        oturum.flush()
        olay_yaz(
            oturum,
            DenetimOlayi.KAYIT_OLUSTURULDU,
            aktor,
            islem_paketi_id=paket.id,
            kayit_id=kayit.id,
        )
    return kayit


# --- okuma ----------------------------------------------------------------------------


def kayit_getir(oturum: Session, kayit_id: int) -> Kayit:
    """Kaydı kimliğiyle getirir; yoksa ``KayitBulunamadi``."""
    kayit = oturum.get(Kayit, kayit_id)
    if kayit is None:
        raise KayitBulunamadi(f"kesin kayıt bulunamadı: kimlik {kayit_id}")
    return kayit


def kayit_alanlarini_oku(oturum: Session, kayit_id: int) -> dict[str, object]:
    """Kaydın alanları ``{kod: değer}``; değerler türüne göre çözülür."""
    kayit = kayit_getir(oturum, kayit_id)
    satirlar = oturum.execute(
        select(KayitAlaniTanimi.kod, KayitAlaniTanimi.deger_turu, KayitAlani.deger)
        .join(KayitAlani, KayitAlani.kayit_alani_tanimi_id == KayitAlaniTanimi.id)
        .where(KayitAlani.kayit_id == kayit.id)
        .order_by(KayitAlaniTanimi.id)
    ).all()
    return {kod: degeri_coz(deger_turu, deger) for kod, deger_turu, deger in satirlar}


def kaydin_nesneleri(oturum: Session, kayit_id: int) -> list[int]:
    """Kayda bağlı nesne kimlikleri, kimlik sırasıyla (deterministik)."""
    kayit = kayit_getir(oturum, kayit_id)
    return list(
        oturum.scalars(
            select(KayitNesne.nesne_id)
            .where(KayitNesne.kayit_id == kayit.id)
            .order_by(KayitNesne.nesne_id)
        )
    )


def nesnenin_kayitlari(oturum: Session, nesne_id: int) -> list[Kayit]:
    """Nesneye bağlı kesin kayıtlar, kimlik sırasıyla."""
    return list(
        oturum.scalars(
            select(Kayit)
            .join(KayitNesne, KayitNesne.kayit_id == Kayit.id)
            .where(KayitNesne.nesne_id == nesne_id)
            .order_by(Kayit.id)
        )
    )


def paketin_kayitlari(oturum: Session, islem_paketi_id: int) -> list[Kayit]:
    """Paketten doğmuş kesin kayıtlar, kimlik sırasıyla."""
    return list(
        oturum.scalars(
            select(Kayit)
            .where(Kayit.islem_paketi_id == islem_paketi_id)
            .order_by(Kayit.id)
        )
    )


def kaydin_kokeni(oturum: Session, kayit_id: int) -> KayitKokeni:
    """Kayıt → paket → okuma → belge → arşiv dosyası; kaynak varsa kimliğiyle.

    Köken tahmin edilmez: her halka dış anahtarla bulunur.
    """
    kayit = kayit_getir(oturum, kayit_id)
    paket = oturum.get(IslemPaketi, kayit.islem_paketi_id)
    if paket is None:  # dış anahtar bunu engeller; sözleşme için
        raise KayitKokeniGecersiz(
            f"kaydın paketi bulunamadı: kimlik {kayit.islem_paketi_id}"
        )
    okuma = okuma_getir(oturum, kayit.okuma_id)
    belge = belge_getir(oturum, okuma.belge_id)
    dosya = arsiv_dosyasi_getir(oturum, belge.arsiv_dosyasi_id)
    return KayitKokeni(
        kayit=kayit,
        islem_paketi=paket,
        okuma=okuma,
        belge=belge,
        arsiv_dosyasi=dosya,
        kaynak_id=kayit.kaynak_id,
    )
