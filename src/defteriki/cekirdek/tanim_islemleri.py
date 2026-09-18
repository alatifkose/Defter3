"""Tanım sisteminin yazma ve okuma işlevleri (Aşama 4.2).

Tanım tablolarına (``tanim_tablolari``) tek giriş noktası. Her işlev açık bir
``Session`` alır ve ``Veritabani.islem`` bağlamı içinde çağrılır; kendi başına
``commit`` etmez, ``rollback`` etmez. Yazma işlevleri satırı ekleyip ``flush``
eder, böylece kimlik atanır ve olası veritabanı hatası çağıranın işlem
sınırında yükselir; işlem bağlamı rollback ile her şeyi geri alır.

Hata modeli (hepsi ``TanimHatasi`` altında; domain bağımsız):

* ``GecersizTanim`` — kod ``KOD_BICIMI``'ne uymuyor, gösterim adı boş, sürüm
  numarası pozitif değil.
* ``TanimBulunamadi`` — verilen paket, sürüm, nesne türü ya da kayıt türü
  kimliği yok. Olmayan üst kayda bağlanmak sessizce geçmez; listeleme de
  olmayan üst kayıt için boş liste yerine bu hatayı verir.
* ``MukerrerTanim`` — aynı kapsamda aynı kod (paket: bütün paketler; sürüm:
  aynı paket içinde sürüm numarası; nesne türü, ilişki, kayıt türü: aynı
  sürüm; özellik: aynı nesne türü; kayıt alanı: aynı kayıt türü).
* ``TanimSurumuUyusmuyor`` — ilişkinin kaynak ya da hedef türü ilişkinin
  sürümünde değil.

Bu denetimler uygulama sözleşmesidir; veritabanındaki benzersizlik, dış
anahtar ve bileşik dış anahtar kısıtları son savunmadır ve aynı durumları
ham ``IntegrityError`` ile de reddeder. Uygulama denetiminden geçen bir
yazma yalnız eşzamanlı yazma yarışında veritabanı hatası alır.

Çekirdek burada da domain bilmez: kodların anlamı, hangi türlerin var olacağı,
hangi ilişkilerin kurulacağı çağıranın (tanım paketinin) verisidir. Bu modül
``TEST_KISI`` ile ``BANKA`` arasında fark görmez.
"""

from __future__ import annotations

import re

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from defteriki.cekirdek.tanim_tablolari import (
    IliskiTanimi,
    KayitAlaniTanimi,
    KayitTuru,
    NesneTuru,
    OzellikTanimi,
    TanimPaketi,
    TanimSurumu,
    simdi_utc,
)

KOD_BICIMI = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
"""Makine kimliği biçimi: ASCII harfle başlar, harf / rakam / alt çizgi ile
sürer; büyük-küçük harf ayrımı vardır, kod verildiği gibi saklanır ve
karşılaştırılır (``Demo`` ile ``DEMO`` farklı kodlardır)."""


class TanimHatasi(Exception):
    """Tanım sistemi hatalarının ortak tabanı."""


class GecersizTanim(TanimHatasi, ValueError):
    """Kod biçimi, gösterim adı ya da sürüm numarası geçersiz."""


class TanimBulunamadi(TanimHatasi, LookupError):
    """Verilen kimlikle paket, sürüm, nesne türü ya da kayıt türü yok."""


class MukerrerTanim(TanimHatasi):
    """Aynı kapsamda aynı kod (ya da aynı sürüm numarası) zaten tanımlı."""


class TanimSurumuUyusmuyor(TanimHatasi):
    """İlişkinin kaynak ya da hedef türü ilişkinin sürümünde değil."""


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


def _mukerrer_denetle(oturum: Session, sorgu: Select[tuple[int]], mesaj: str) -> None:
    if oturum.execute(sorgu).first() is not None:
        raise MukerrerTanim(mesaj)


def _paket_getir(oturum: Session, tanim_paketi_id: int) -> TanimPaketi:
    paket = oturum.get(TanimPaketi, tanim_paketi_id)
    if paket is None:
        raise TanimBulunamadi(f"tanım paketi bulunamadı: kimlik {tanim_paketi_id}")
    return paket


def _surum_getir(oturum: Session, tanim_surumu_id: int) -> TanimSurumu:
    surum = oturum.get(TanimSurumu, tanim_surumu_id)
    if surum is None:
        raise TanimBulunamadi(f"tanım sürümü bulunamadı: kimlik {tanim_surumu_id}")
    return surum


def _nesne_turu_getir(oturum: Session, nesne_turu_id: int) -> NesneTuru:
    tur = oturum.get(NesneTuru, nesne_turu_id)
    if tur is None:
        raise TanimBulunamadi(f"nesne türü bulunamadı: kimlik {nesne_turu_id}")
    return tur


def _kayit_turu_getir(oturum: Session, kayit_turu_id: int) -> KayitTuru:
    tur = oturum.get(KayitTuru, kayit_turu_id)
    if tur is None:
        raise TanimBulunamadi(f"kayıt türü bulunamadı: kimlik {kayit_turu_id}")
    return tur


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
    """Paketin yeni sürümü; ``surum_no`` pozitif ve paket içinde benzersiz."""
    if surum_no <= 0:
        raise GecersizTanim(f"sürüm numarası pozitif olmalı: {surum_no}")
    paket = _paket_getir(oturum, tanim_paketi_id)
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
    """Sürüme yeni nesne türü; ``kod`` sürüm içinde benzersiz."""
    _kodu_dogrula(kod, "nesne türü")
    _gosterim_adini_dogrula(gosterim_adi, "nesne türü")
    surum = _surum_getir(oturum, tanim_surumu_id)
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
    aciklama: str | None = None,
) -> OzellikTanimi:
    """Nesne türüne yeni özellik tanımı; ``kod`` tür içinde benzersiz."""
    _kodu_dogrula(kod, "özellik")
    _gosterim_adini_dogrula(gosterim_adi, "özellik")
    tur = _nesne_turu_getir(oturum, nesne_turu_id)
    _mukerrer_denetle(
        oturum,
        select(OzellikTanimi.id).where(
            OzellikTanimi.nesne_turu_id == tur.id, OzellikTanimi.kod == kod
        ),
        f"özellik {kod!r} nesne türü {tur.kod!r} için zaten var.",
    )
    ozellik = OzellikTanimi(
        nesne_turu_id=tur.id, kod=kod, gosterim_adi=gosterim_adi, aciklama=aciklama
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
    benzersiz; iki tür de bu sürümde olmalı. Kaynak ile hedef aynı tür olabilir."""
    _kodu_dogrula(kod, "ilişki")
    _gosterim_adini_dogrula(gosterim_adi, "ilişki")
    surum = _surum_getir(oturum, tanim_surumu_id)
    kaynak = _nesne_turu_getir(oturum, kaynak_nesne_turu_id)
    hedef = _nesne_turu_getir(oturum, hedef_nesne_turu_id)
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


def kayit_turu_tanimla(
    oturum: Session,
    tanim_surumu_id: int,
    kod: str,
    gosterim_adi: str,
    aciklama: str | None = None,
) -> KayitTuru:
    """Sürüme yeni kayıt türü; ``kod`` sürüm içinde benzersiz."""
    _kodu_dogrula(kod, "kayıt türü")
    _gosterim_adini_dogrula(gosterim_adi, "kayıt türü")
    surum = _surum_getir(oturum, tanim_surumu_id)
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
    aciklama: str | None = None,
) -> KayitAlaniTanimi:
    """Kayıt türüne yeni alan tanımı; ``kod`` tür içinde benzersiz."""
    _kodu_dogrula(kod, "kayıt alanı")
    _gosterim_adini_dogrula(gosterim_adi, "kayıt alanı")
    tur = _kayit_turu_getir(oturum, kayit_turu_id)
    _mukerrer_denetle(
        oturum,
        select(KayitAlaniTanimi.id).where(
            KayitAlaniTanimi.kayit_turu_id == tur.id, KayitAlaniTanimi.kod == kod
        ),
        f"kayıt alanı {kod!r} kayıt türü {tur.kod!r} için zaten var.",
    )
    alan = KayitAlaniTanimi(
        kayit_turu_id=tur.id, kod=kod, gosterim_adi=gosterim_adi, aciklama=aciklama
    )
    oturum.add(alan)
    oturum.flush()
    return alan


# --- okuma -----------------------------------------------------------------------


def paket_bul(oturum: Session, kod: str) -> TanimPaketi | None:
    """Koduyla paket; yoksa ``None`` (arama sonucu, hata değil)."""
    return oturum.execute(
        select(TanimPaketi).where(TanimPaketi.kod == kod)
    ).scalar_one_or_none()


def paketleri_listele(oturum: Session) -> list[TanimPaketi]:
    return list(oturum.execute(select(TanimPaketi).order_by(TanimPaketi.kod)).scalars())


def surumleri_listele(oturum: Session, tanim_paketi_id: int) -> list[TanimSurumu]:
    """Paketin sürümleri, numaraya göre artan; paket yoksa ``TanimBulunamadi``."""
    paket = _paket_getir(oturum, tanim_paketi_id)
    return list(
        oturum.execute(
            select(TanimSurumu)
            .where(TanimSurumu.tanim_paketi_id == paket.id)
            .order_by(TanimSurumu.surum_no)
        ).scalars()
    )


def nesne_turlerini_listele(oturum: Session, tanim_surumu_id: int) -> list[NesneTuru]:
    surum = _surum_getir(oturum, tanim_surumu_id)
    return list(
        oturum.execute(
            select(NesneTuru)
            .where(NesneTuru.tanim_surumu_id == surum.id)
            .order_by(NesneTuru.kod)
        ).scalars()
    )


def ozellik_tanimlarini_listele(
    oturum: Session, nesne_turu_id: int
) -> list[OzellikTanimi]:
    """Türün özellikleri, tanımlanma sırasıyla."""
    tur = _nesne_turu_getir(oturum, nesne_turu_id)
    return list(
        oturum.execute(
            select(OzellikTanimi)
            .where(OzellikTanimi.nesne_turu_id == tur.id)
            .order_by(OzellikTanimi.id)
        ).scalars()
    )


def iliski_tanimlarini_listele(
    oturum: Session, tanim_surumu_id: int
) -> list[IliskiTanimi]:
    surum = _surum_getir(oturum, tanim_surumu_id)
    return list(
        oturum.execute(
            select(IliskiTanimi)
            .where(IliskiTanimi.tanim_surumu_id == surum.id)
            .order_by(IliskiTanimi.kod)
        ).scalars()
    )


def kayit_turlerini_listele(oturum: Session, tanim_surumu_id: int) -> list[KayitTuru]:
    surum = _surum_getir(oturum, tanim_surumu_id)
    return list(
        oturum.execute(
            select(KayitTuru)
            .where(KayitTuru.tanim_surumu_id == surum.id)
            .order_by(KayitTuru.kod)
        ).scalars()
    )


def kayit_alani_tanimlarini_listele(
    oturum: Session, kayit_turu_id: int
) -> list[KayitAlaniTanimi]:
    """Kayıt türünün alanları, tanımlanma sırasıyla."""
    tur = _kayit_turu_getir(oturum, kayit_turu_id)
    return list(
        oturum.execute(
            select(KayitAlaniTanimi)
            .where(KayitAlaniTanimi.kayit_turu_id == tur.id)
            .order_by(KayitAlaniTanimi.id)
        ).scalars()
    )
