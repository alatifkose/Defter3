"""Belge zincirinin servisleri (Aşama 4.4): belge alma, okuma, kaynak, uzlaştırma.

Zincir bu aşamada ``DOSYA → ARŞİV → BELGE → OKUMA → KAYNAK`` ile biter. Aday
nesne, işlem paketi, onay, mükerrerlik ve kesin kayıt sonraki aşamalardır;
burada "okuma tamamlandı = deftere kaydedildi" semantiği yoktur. Çekirdek
belgeyi kendisi okumaz, LLM çağırmaz; okuma içeriği dış okuyucudan gelir ve
domain bağımsız JSON olarak saklanır. Bu modül ``defteriki.ayarlar`` okumaz;
arşiv dizini ve gelen dizini çağırandan gelir.

**İşlem sınırı** 4.1 kuralıdır: her servis açık bir ``Session`` alır, çağıran
``Veritabani.islem`` transaction'ının sahibidir; burada ``commit`` / dış
``rollback`` yoktur. **Servis hata atomikliği** (4.3 kuralı): her yazma
işlevi önce doğrular, sonra kendi SAVEPOINT'i içinde yazar
(``Session.begin_nested``); başarısız çağrı, hatası aynı dış işlem içinde
yakalansa bile kendi kısmi değişikliğini bırakmaz.

**Tek istisna: ``belge_al``.** Dosya sistemi ile SQLite aynı transaction'a
giremez; bu saklanmaz. ``belge_al`` önce dosyayı arşive güvenli biçimde
yazar (``arsiv.dosyayi_arsivle``), SHA-256 kesinleşir, sonra kendi kısa
``Veritabani.islem`` işleminde ``belge_tanimla`` çağırır. Sınırı dardır:
başka hiçbir servis kendi işlemini açmaz. Sonuç invariantı: veritabanındaki
belge hiçbir zaman arşive güvenli biçimde yazılmamış dosyaya dayanmaz
(``belge_tanimla`` yazmadan önce dosyanın yerinde ve beklenen boyutta
olduğunu bir daha denetler). Ters yönde, DB adımı düşerse arşivde **sahipsiz**
dosya kalabilir: bu yarım belge kaydı değil, dosya/DB atomik olmamasının
doğal sonucudur; aynı dosya yeniden geldiğinde arşiv onu özetle doğrulayıp
kullanır ve belge kaydı tamamlanır. Sahipsiz dosyalar ``arsivi_uzlastir`` ile
raporlanır, silinmez.

**Duplicate belge** (``belge_tanimla``): aynı SHA-256 ikinci kez gelirse
ikinci ``ArsivDosyasi``, ikinci fiziksel dosya ve ikinci ``Belge`` oluşmaz;
mevcut belge ``zaten_vardi=True`` ile döner. Bu belge seviyesindeki
mekanizmadır; işlem anahtarı (işlem seviyesi) ve mükerrer nesne (nesne
seviyesi) ayrı mekanizmalardır ve bu aşamada kurulmaz.

**Okuma**: ``okuma_baslat`` önce arşiv dosyasının var, sıradan, beklenen
boyutta ve beklenen SHA-256'da olduğunu doğrular (DB satırına kör
güvenilmez; kaynak eksik ya da bozuksa okuma açılmaz), sonra belge içinde
bir sonraki sürüm numarasıyla ``basladi`` durumunda satır açar. Aynı belge
birden çok kez okunabilir. ``okuma_tamamla`` yalnız ``basladi`` okumayı
kabul eder; içerik JSON nesnesi (``Mapping``) olmalı, JSON'a çevrilebilmeli
(``NaN`` / sonsuz reddedilir), ``AZAMI_OKUMA_ICERIGI_BOYUTU``'nu aşmamalı;
kanonik JSON metni olarak saklanır. Tamamlanan okuma değiştirilemez: ikinci
``okuma_tamamla`` ``OkumaDurumuGecersiz`` verir, içerik güncelleyen bir işlev
yoktur; yeni okuma gerekiyorsa yeni sürüm açılır.

**Kaynak**: ``kaynak_olustur`` okumadan başlar; ``belge_id`` okumadan alınır,
çağıran veremez (servis düzeyinde uyuşmazlık imkânsız; ham SQL'e karşı
bileşik dış anahtar). ``konum`` isteğe bağlı JSON nesnesidir, yalnız yer
bilgisi taşır, ``AZAMI_KAYNAK_KONUMU_BOYUTU`` ile sınırlıdır. Kaynak satırı
değişmez veridir: güncelleyen işlev yoktur; yanlışsa yeni kaynak üretilir.
``kaynak_zinciri`` kaynaktan okumaya, belgeye ve arşiv dosyasına deterministik
geri gider. Kaynağın okumanın hangi durumunda üretilebileceğine dair kısıt
yoktur (bu aşamada karar verilmedi; not edildi).

**Uzlaştırma** (``arsivi_uzlastir``): veritabanı satırları ile arşiv dizinini
karşılaştırır ve her şeyi sınıflar (temiz / eksik / bozuk / sahipsiz / yarım
artık / tanınmayan). Yalnız tespit eder ve raporlar; silmez, onarmaz.

Hata modeli (``BelgeHatasi`` altında; arşiv dosya katmanı hataları
``arsiv.ArsivHatasi`` altında olduğu gibi gelir): ``BelgeBulunamadi``,
``OkumaBulunamadi``, ``KaynakBulunamadi``, ``OkumaDurumuGecersiz``,
``OkumaIcerigiGecersiz``, ``KaynakKonumuGecersiz``. Mesajlarda belge içeriği
ve yerel yol yoktur. Bu modül hiçbir şeyi günlüğe yazmaz.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from defteriki.cekirdek import arsiv
from defteriki.cekirdek.belge_tablolari import (
    ArsivDosyasi,
    Belge,
    Kaynak,
    Okuma,
    OkumaDurumu,
)
from defteriki.cekirdek.tanim_tablolari import simdi_utc
from defteriki.cekirdek.veritabani import Veritabani

AZAMI_OKUMA_ICERIGI_BOYUTU = 4 * 1024 * 1024
"""Kanonik JSON metninin UTF-8 bayt sınırı; teknik sınır, domain kuralı değil."""
AZAMI_KAYNAK_KONUMU_BOYUTU = 4 * 1024
"""Konum küçük bir yer bilgisidir; belge içeriğinin kopyası olamaz."""


class BelgeHatasi(Exception):
    """Belge zinciri servis hatalarının ortak tabanı."""


class BelgeBulunamadi(BelgeHatasi, LookupError):
    """Verilen kimlikle belge ya da arşiv dosyası kaydı yok."""


class OkumaBulunamadi(BelgeHatasi, LookupError):
    """Verilen kimlikle okuma yok."""


class KaynakBulunamadi(BelgeHatasi, LookupError):
    """Verilen kimlikle kaynak yok."""


class OkumaDurumuGecersiz(BelgeHatasi):
    """Okuma bu işlem için uygun durumda değil (tamamlanan okuma değiştirilemez)."""


class OkumaIcerigiGecersiz(BelgeHatasi, ValueError):
    """İçerik JSON nesnesi değil, JSON'a çevrilemiyor ya da sınırı aşıyor."""


class KaynakKonumuGecersiz(BelgeHatasi, ValueError):
    """Konum JSON nesnesi değil, JSON'a çevrilemiyor ya da sınırı aşıyor."""


@dataclass(frozen=True, slots=True)
class BelgeSonucu:
    belge: Belge
    arsiv_dosyasi: ArsivDosyasi
    zaten_vardi: bool
    """Belge veritabanında zaten vardı; yeni satır yazılmadı."""
    dosya_zaten_vardi: bool
    """Fiziksel dosya arşivde zaten vardı ve özetle doğrulandı."""


@dataclass(frozen=True, slots=True)
class KaynakZinciri:
    """Kaynaktan geriye deterministik yol: okuma, belge, arşiv dosyası."""

    kaynak: Kaynak
    okuma: Okuma
    belge: Belge
    arsiv_dosyasi: ArsivDosyasi


@dataclass(frozen=True, slots=True)
class UzlastirmaRaporu:
    """Arşiv dizini ile veritabanının karşılaştırması; yalnız tespit."""

    temiz: tuple[int, ...]
    """DB satırı var, fiziksel dosya beklenen boyut ve özette (arşiv dosyası
    kimliği)."""
    eksik: tuple[int, ...]
    """DB satırı var, fiziksel dosya yok."""
    bozuk: tuple[int, ...]
    """DB satırı var, hedefte yanlış boyut ya da özet (ya da sıradan dosya değil)."""
    sahipsiz: tuple[str, ...]
    """İçerik adresli fiziksel dosya var, DB satırı yok (göreli yol). Silinmez:
    DB hatası sonrası yeniden deneme ya da eşzamanlı işlem olabilir."""
    yarim: tuple[str, ...]
    """``gecici/`` altında kalmış artıklar (göreli yol)."""
    taninmayan: tuple[str, ...]
    """Arşiv düzenine uymayan başka dosyalar (göreli yol)."""

    @property
    def temiz_mi(self) -> bool:
        return not (
            self.eksik or self.bozuk or self.sahipsiz or self.yarim or self.taninmayan
        )


# --- JSON -----------------------------------------------------------------------------


def _json_kodla(veri: object, azami: int, hata: type[BelgeHatasi], ne: str) -> str:
    """JSON nesnesini kanonik metne çevirir; nesne değilse, çevrilemiyorsa
    (``NaN`` / sonsuz dahil) ya da sınırı aşıyorsa ``hata`` yükselir."""
    if not isinstance(veri, Mapping):
        raise hata(f"{ne} JSON nesnesi (anahtar → değer) olmalı.")
    try:
        metin = json.dumps(
            dict(veri),  # type: ignore[arg-type]
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        raise hata(f"{ne} JSON'a çevrilemiyor.") from None
    boyut = len(metin.encode("utf-8"))
    if boyut > azami:
        raise hata(f"{ne} {azami} bayt sınırını aşıyor ({boyut}).")
    return metin


def _json_coz(metin: str) -> dict[str, Any]:
    veri: Any = json.loads(metin)
    if not isinstance(veri, dict):
        raise ValueError("saklanan JSON nesne değil.")
    return veri  # type: ignore[return-value]


# --- getirme --------------------------------------------------------------------------


def arsiv_dosyasi_getir(oturum: Session, arsiv_dosyasi_id: int) -> ArsivDosyasi:
    satir = oturum.get(ArsivDosyasi, arsiv_dosyasi_id)
    if satir is None:
        raise BelgeBulunamadi(f"arşiv dosyası bulunamadı: kimlik {arsiv_dosyasi_id}")
    return satir


def belge_getir(oturum: Session, belge_id: int) -> Belge:
    belge = oturum.get(Belge, belge_id)
    if belge is None:
        raise BelgeBulunamadi(f"belge bulunamadı: kimlik {belge_id}")
    return belge


def belge_bul(oturum: Session, sha256: str) -> Belge | None:
    """SHA-256 ile belge; yoksa ``None`` (arama sonucu, hata değil)."""
    return oturum.execute(
        select(Belge)
        .join(ArsivDosyasi, ArsivDosyasi.id == Belge.arsiv_dosyasi_id)
        .where(ArsivDosyasi.sha256 == sha256)
    ).scalar_one_or_none()


def belgeleri_listele(oturum: Session) -> list[Belge]:
    return list(oturum.execute(select(Belge).order_by(Belge.id)).scalars())


def okuma_getir(oturum: Session, okuma_id: int) -> Okuma:
    okuma = oturum.get(Okuma, okuma_id)
    if okuma is None:
        raise OkumaBulunamadi(f"okuma bulunamadı: kimlik {okuma_id}")
    return okuma


def okumalari_listele(oturum: Session, belge_id: int) -> list[Okuma]:
    """Belgenin okumaları, sürüm sırasıyla; belge yoksa ``BelgeBulunamadi``."""
    belge = belge_getir(oturum, belge_id)
    return list(
        oturum.execute(
            select(Okuma).where(Okuma.belge_id == belge.id).order_by(Okuma.surum_no)
        ).scalars()
    )


def okuma_icerigi(oturum: Session, okuma_id: int) -> dict[str, Any] | None:
    """Tamamlanan okumanın içeriği (JSON çözülmüş); tamamlanmamışsa ``None``."""
    okuma = okuma_getir(oturum, okuma_id)
    if okuma.icerik is None:
        return None
    return _json_coz(okuma.icerik)


def kaynak_getir(oturum: Session, kaynak_id: int) -> Kaynak:
    kaynak = oturum.get(Kaynak, kaynak_id)
    if kaynak is None:
        raise KaynakBulunamadi(f"kaynak bulunamadı: kimlik {kaynak_id}")
    return kaynak


def kaynaklari_listele(oturum: Session, okuma_id: int) -> list[Kaynak]:
    """Okumanın kaynakları, kimlik sırasıyla; okuma yoksa ``OkumaBulunamadi``."""
    okuma = okuma_getir(oturum, okuma_id)
    return list(
        oturum.execute(
            select(Kaynak).where(Kaynak.okuma_id == okuma.id).order_by(Kaynak.id)
        ).scalars()
    )


def kaynak_konumu(oturum: Session, kaynak_id: int) -> dict[str, Any] | None:
    """Kaynağın konumu (JSON çözülmüş); konumsuz kaynakta ``None``."""
    kaynak = kaynak_getir(oturum, kaynak_id)
    if kaynak.konum is None:
        return None
    return _json_coz(kaynak.konum)


def kaynak_zinciri(oturum: Session, kaynak_id: int) -> KaynakZinciri:
    """Kaynak → okuma → belge → arşiv dosyası; her halka kimlikle bulunur."""
    kaynak = kaynak_getir(oturum, kaynak_id)
    okuma = okuma_getir(oturum, kaynak.okuma_id)
    belge = belge_getir(oturum, okuma.belge_id)
    dosya = arsiv_dosyasi_getir(oturum, belge.arsiv_dosyasi_id)
    return KaynakZinciri(kaynak=kaynak, okuma=okuma, belge=belge, arsiv_dosyasi=dosya)


# --- belge ----------------------------------------------------------------------------


def belge_tanimla(
    oturum: Session, arsivlenen: arsiv.ArsivlenenDosya, arsiv_dizini: Path
) -> BelgeSonucu:
    """Arşive girmiş dosya için ``ArsivDosyasi`` + ``Belge`` tanımlar ya da aynı
    SHA-256'nın mevcut belgesini döndürür.

    Yazmadan önce fiziksel dosyanın yerinde ve beklenen boyutta olduğu denetlenir
    (DB'de dosyasız belge oluşmaz). Yazma SAVEPOINT içindedir.
    """
    arsiv.arsiv_dosyasini_dogrula(arsiv_dizini, arsivlenen.goreli_yol, arsivlenen.boyut)
    dosya = oturum.execute(
        select(ArsivDosyasi).where(ArsivDosyasi.sha256 == arsivlenen.sha256)
    ).scalar_one_or_none()
    if dosya is not None:
        belge = oturum.execute(
            select(Belge).where(Belge.arsiv_dosyasi_id == dosya.id)
        ).scalar_one_or_none()
        if belge is not None:
            return BelgeSonucu(belge, dosya, True, arsivlenen.diskte_zaten_vardi)
    with oturum.begin_nested():
        if dosya is None:
            dosya = _arsiv_dosyasi_yaz(oturum, arsivlenen)
        belge = Belge(arsiv_dosyasi_id=dosya.id, olusturma_zamani=simdi_utc())
        oturum.add(belge)
        oturum.flush()
    return BelgeSonucu(belge, dosya, False, arsivlenen.diskte_zaten_vardi)


def _arsiv_dosyasi_yaz(
    oturum: Session, arsivlenen: arsiv.ArsivlenenDosya
) -> ArsivDosyasi:
    dosya = ArsivDosyasi(
        sha256=arsivlenen.sha256,
        boyut=arsivlenen.boyut,
        mime=arsivlenen.mime,
        kaynak_uzantisi=arsivlenen.kaynak_uzantisi,
        kaynak_adi=arsivlenen.kaynak_adi,
        goreli_yol=arsivlenen.goreli_yol,
        olusturma_zamani=simdi_utc(),
    )
    oturum.add(dosya)
    oturum.flush()
    return dosya


def belge_al(
    veritabani: Veritabani,
    yol: str | Path,
    *,
    gelen_dizini: Path,
    arsiv_dizini: Path,
) -> BelgeSonucu:
    """Gelen dizinindeki dosyayı belge yapar: önce arşiv, sonra kısa DB işlemi.

    Bu modülde kendi işlemini açan tek servis (bkz. modül açıklaması). Arşiv
    adımı düşerse DB'ye dokunulmaz; DB adımı düşerse fiziksel dosya arşivde
    kalabilir, belge kaydı kalmaz.
    """
    arsivlenen = arsiv.dosyayi_arsivle(
        yol, gelen_dizini=gelen_dizini, arsiv_dizini=arsiv_dizini
    )
    with veritabani.islem() as oturum:
        return belge_tanimla(oturum, arsivlenen, arsiv_dizini)


# --- okuma ----------------------------------------------------------------------------


def okuma_baslat(oturum: Session, belge_id: int, arsiv_dizini: Path) -> Okuma:
    """Belge için yeni okuma sürümü (``basladi``). Önce arşiv dosyası doğrulanır
    (var, sıradan, boyut, SHA-256); eksik ya da bozuksa okuma açılmaz."""
    belge = belge_getir(oturum, belge_id)
    dosya = arsiv_dosyasi_getir(oturum, belge.arsiv_dosyasi_id)
    arsiv.arsiv_dosyasini_dogrula(
        arsiv_dizini, dosya.goreli_yol, dosya.boyut, dosya.sha256
    )
    with oturum.begin_nested():
        son = oturum.execute(
            select(func.max(Okuma.surum_no)).where(Okuma.belge_id == belge.id)
        ).scalar_one()
        okuma = Okuma(
            belge_id=belge.id,
            surum_no=(son or 0) + 1,
            durum=OkumaDurumu.BASLADI.value,
            icerik=None,
            olusturma_zamani=simdi_utc(),
            tamamlanma_zamani=None,
        )
        oturum.add(okuma)
        oturum.flush()
    return okuma


def okuma_tamamla(oturum: Session, okuma_id: int, icerik: Mapping[str, Any]) -> Okuma:
    """``basladi`` okumayı içerikle tamamlar; başka durumda
    ``OkumaDurumuGecersiz``. İçerik yazmadan önce doğrulanır."""
    okuma = okuma_getir(oturum, okuma_id)
    if okuma.durum != OkumaDurumu.BASLADI.value:
        raise OkumaDurumuGecersiz(
            f"okuma {okuma.id} {okuma.durum} durumunda; yalnız "
            f"{OkumaDurumu.BASLADI.value} okuma tamamlanır, tamamlanan okuma "
            "değiştirilmez (yeni sürüm açın)."
        )
    metin = _json_kodla(
        icerik, AZAMI_OKUMA_ICERIGI_BOYUTU, OkumaIcerigiGecersiz, "okuma içeriği"
    )
    with oturum.begin_nested():
        okuma.durum = OkumaDurumu.TAMAMLANDI.value
        okuma.icerik = metin
        okuma.tamamlanma_zamani = simdi_utc()
        oturum.flush()
    return okuma


# --- kaynak ---------------------------------------------------------------------------


def kaynak_olustur(
    oturum: Session, okuma_id: int, konum: Mapping[str, Any] | None = None
) -> Kaynak:
    """Okumaya bağlı kaynak; belge okumadan alınır. ``konum`` isteğe bağlı JSON
    nesnesi. Konum yazmadan önce doğrulanır."""
    okuma = okuma_getir(oturum, okuma_id)
    metin = (
        None
        if konum is None
        else _json_kodla(
            konum, AZAMI_KAYNAK_KONUMU_BOYUTU, KaynakKonumuGecersiz, "kaynak konumu"
        )
    )
    with oturum.begin_nested():
        kaynak = Kaynak(
            belge_id=okuma.belge_id,
            okuma_id=okuma.id,
            konum=metin,
            olusturma_zamani=simdi_utc(),
        )
        oturum.add(kaynak)
        oturum.flush()
    return kaynak


# --- uzlaştırma -----------------------------------------------------------------------


def arsivi_uzlastir(oturum: Session, arsiv_dizini: Path) -> UzlastirmaRaporu:
    """Veritabanı ile arşiv dizinini karşılaştırır; her DB satırı için dosya
    boyut ve özetle doğrulanır. Hiçbir şey silinmez, değiştirilmez."""
    temiz: list[int] = []
    eksik: list[int] = []
    bozuk: list[int] = []
    kayitli_yollar: set[str] = set()
    satirlar = oturum.execute(select(ArsivDosyasi).order_by(ArsivDosyasi.id)).scalars()
    for dosya in satirlar:
        kayitli_yollar.add(dosya.goreli_yol)
        try:
            arsiv.arsiv_dosyasini_dogrula(
                arsiv_dizini, dosya.goreli_yol, dosya.boyut, dosya.sha256
            )
        except arsiv.ArsivDosyasiEksik:
            eksik.append(dosya.id)
        except arsiv.ArsivButunlukHatasi:
            bozuk.append(dosya.id)
        else:
            temiz.append(dosya.id)
    tarama = arsiv.arsivi_tara(arsiv_dizini)
    sahipsiz = tuple(yol for yol in tarama.adresli if yol not in kayitli_yollar)
    return UzlastirmaRaporu(
        temiz=tuple(temiz),
        eksik=tuple(eksik),
        bozuk=tuple(bozuk),
        sahipsiz=sahipsiz,
        yarim=tarama.yarim,
        taninmayan=tarama.taninmayan,
    )
