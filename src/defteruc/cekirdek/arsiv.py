"""İçerik adresli belge arşivi: dosya katmanı (Aşama 4.4).

Cowork dosyayı izinli **gelen dizinine** bırakır ve yolunu verir; bu modül
dosyayı denetler, akışla kopyalar, SHA-256 ve boyutu gerçek baytlardan
hesaplar, içerik adresli kalıcı yola atomik taşır. Veritabanına dokunmaz,
``defteruc.ayarlar`` okumaz: gelen dizini ve
arşiv dizini çağırandan ``Path`` olarak gelir. Import edildiğinde dizin ya da
dosya oluşturmaz, ortam değişkeni okumaz. Bu modül belgenin ne olduğunu
bilmez; bir PDF ile bir metin dosyası burada aynı muameleyi görür.

**Gelen dizini sınırı** (``gelen_dosyayi_dogrula``), sırayla: yol boş olamaz →
mutlak olmalı → ``..`` parçası olamaz → sözlüksel olarak gelen dizininin
altında olmalı → var olmalı → gelen dizininden dosyaya inen hiçbir parça
simgesel bağlantı ya da Windows junction olamaz → fiziksel çözülmüş yol
(``Path.resolve``) gelen dizininin fiziksel çözülmüş yolunun altında olmalı →
sıradan dosya olmalı. Gelen dizininin kendisi bağlantı olabilir (çağıranın
ayarıdır); altındaki bağlantılar reddedilir. Hata mesajları kategoriktir; yol
ya da dosya adı taşımaz.

**Arşive atomik yazma** (``dosyayi_arsivle``): kaynak akışla okunur (bütün
dosya belleğe alınmaz), ilk parçadan MIME belirlenir (boş dosya geçici dosya
açılmadan reddedilir), ``<arşiv>/gecici/<rastgele>.tmp`` adına yazılırken SHA-256 ve
boyut hesaplanır, ``AZAMI_DOSYA_BOYUTU`` aşılırsa dosya kesilmez, tamamı
reddedilir; ``flush`` + ``fsync``; hedef yol yalnız özetten türer
(``arsiv_goreli_yolu``: ``<ilk iki hex>/<sha256>``, uzantısız); üst dizin
oluşturulur; ``os.replace`` ile aynı dosya sistemi üzerinde atomik taşınır.
Hangi adım düşerse düşsün geçici dosya silinir; yarım arşiv dosyası kalmaz.

**Fiziksel kimlik yalnız SHA-256'dır.** Aynı baytlar hangi adla, hangi
uzantıyla ya da uzantısız gelirse gelsin tek fiziksel dosyaya karşılık gelir.
Hedef zaten varsa yalnız boyuta güvenilmez: mevcut dosya baştan sona
özetlenir; özet beklenenle aynıysa kopya atılır ve sonuç "diskte zaten vardı"
olur, değilse ``ArsivButunlukHatasi`` yükselir (bozuk hedef sessizce duplicate
sayılmaz). İki süreç aynı içeriği aynı anda getirirse ikisi de aynı baytları
aynı yola bırakır; ``os.replace`` atomiktir, sonuç tek geçerli dosyadır.
Windows'ta hedef o an açıkken taşıma reddedilirse hedef yine özetle doğrulanır.
Arşiv yolu dizin taramasıyla ya da "SHA ile başlayan dosya" aramasıyla değil,
doğrudan özetten hesaplanır.

**MIME** yalnız ilk baytlardaki imzadan belirlenir (PDF, PNG, JPEG); imza
bilinmiyorsa güvenli genel değer ``application/octet-stream`` kullanılır.
Dosyanın adı ve uzantısı güvenilir içerik bilgisi değildir (karar 2026-09-19):
uzantı yalnız metadata'dır, imzayla uyuşmaması arşivlemeye engel değildir;
``.pdf`` adlı imzasız dosya da, ``.png`` adlı PDF de arşive girer. Arşiv
baytları saklar, belgeyi çalıştırmaz. MIME, uzantı ve kaynak adı metadata'dır,
fiziksel kimliğe girmez.

Teknik sınırlar: ``AZAMI_DOSYA_BOYUTU`` (50 MiB) domain kuralı değil kaynak
sınırıdır. Bu modül hiçbir şeyi günlüğe yazmaz.
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

AZAMI_DOSYA_BOYUTU = 50 * 1024 * 1024
"""Bayt; aşılırsa dosya kesilmez, tamamı reddedilir. Teknik kaynak sınırı."""
OKUMA_PARCA_BOYUTU = 1024 * 1024
GECICI_DIZIN_ADI = "gecici"
GECICI_UZANTI = ".tmp"
AZAMI_UZANTI_UZUNLUGU = 10
VARSAYILAN_MIME = "application/octet-stream"

SHA256_BICIMI = re.compile(r"[0-9a-f]{64}")
GORELI_YOL_BICIMI = re.compile(r"([0-9a-f]{2})/([0-9a-f]{64})")

_IMZALAR: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)


class ArsivHatasi(Exception):
    """Arşiv dosya katmanı hatalarının ortak tabanı."""


class GelenDosyaGecersiz(ArsivHatasi, ValueError):
    """Yol gelen dizini kurallarına uymuyor ya da dosya belge olamaz (boş)."""


class DosyaOkunamadi(ArsivHatasi):
    """Kaynak dosya açılamadı ya da okunurken hata oldu."""


class DosyaCokBuyuk(ArsivHatasi):
    """Dosya ``AZAMI_DOSYA_BOYUTU`` sınırını aşıyor; kesilmez, reddedilir."""


class ArsivYazilamadi(ArsivHatasi):
    """Arşiv dizini hazırlanamadı, geçici dosya yazılamadı ya da taşınamadı."""


class ArsivDosyasiEksik(ArsivHatasi):
    """Beklenen arşiv yolunda dosya yok."""


class ArsivButunlukHatasi(ArsivHatasi):
    """Arşiv yolundaki dosya sıradan dosya değil, boyutu ya da özeti beklenenden
    farklı."""


@dataclass(frozen=True, slots=True)
class ArsivlenenDosya:
    """Arşive giren dosyanın kimliği ve metadata'sı; veritabanına henüz
    yazılmamıştır."""

    sha256: str
    boyut: int
    mime: str
    kaynak_uzantisi: str
    """Kaynak adındaki küçük harfli uzantı (``.pdf``); yoksa boş. Metadata."""
    kaynak_adi: str
    """Gelen dizinindeki dosya adı; arşiv yolunu etkilemez. Metadata."""
    goreli_yol: str
    """Arşiv dizinine göre POSIX yol: ``<ilk iki hex>/<sha256>``; uzantısız."""
    diskte_zaten_vardi: bool
    """Aynı içerik arşivde zaten vardı ve özetle doğrulandı; yeni dosya yazılmadı."""


@dataclass(frozen=True, slots=True)
class ArsivTaramasi:
    """Arşiv dizinindeki dosyaların sınıflaması (yalnız dosya sistemi)."""

    adresli: tuple[str, ...]
    """``<2hex>/<sha256>`` biçimine uyan göreli yollar (veritabanı bilinmez)."""
    yarim: tuple[str, ...]
    """``gecici/`` altında kalmış artıklar."""
    taninmayan: tuple[str, ...]
    """Arşiv düzenine uymayan başka dosyalar."""


# --- gelen dizini sınırı --------------------------------------------------------------


def gelen_dosyayi_dogrula(yol: str | Path, gelen_dizini: Path) -> Path:
    """Yolu gelen dizini kurallarıyla denetler; geçerse dosyanın sözlüksel
    (sadeleştirilmiş) yolunu döndürür. Her red ``GelenDosyaGecersiz`` ya da
    ``DosyaOkunamadi``; mesajda yol yoktur."""
    if not gelen_dizini.is_absolute():
        raise ValueError("gelen dizini mutlak bir yol olmalı.")
    metin = str(yol)
    if not metin.strip():
        raise GelenDosyaGecersiz("dosya yolu boş olamaz.")
    verilen = Path(metin)
    if not verilen.is_absolute():
        raise GelenDosyaGecersiz("dosya yolu mutlak olmalı; göreli yol kabul edilmez.")
    if ".." in verilen.parts:
        raise GelenDosyaGecersiz("dosya yolunda üst dizin parçası (..) olamaz.")

    sade = Path(os.path.normpath(verilen))
    gelen_sade = Path(os.path.normpath(gelen_dizini))
    if not _sozluksel_altinda(sade, gelen_sade):
        raise GelenDosyaGecersiz("dosya izinli gelen dizininin dışında.")

    try:
        os.lstat(sade)
    except FileNotFoundError:
        raise GelenDosyaGecersiz("dosya bulunamadı.") from None
    except OSError:
        raise DosyaOkunamadi("dosya yoluna erişilemedi.") from None

    for ara in _inen_parcalar(sade, gelen_sade):
        if ara.is_symlink() or os.path.isjunction(ara):
            raise GelenDosyaGecersiz(
                "gelen dizini altında simgesel bağlantı ya da junction kabul edilmez."
            )

    try:
        fiziksel = sade.resolve(strict=True)
    except FileNotFoundError:
        raise GelenDosyaGecersiz("dosya bulunamadı.") from None
    except (OSError, RuntimeError):
        raise DosyaOkunamadi("dosya yolu çözülemedi.") from None
    if not fiziksel.is_relative_to(gelen_sade.resolve()):
        raise GelenDosyaGecersiz("dosyanın fiziksel yolu gelen dizininin dışında.")
    if not fiziksel.is_file():
        raise GelenDosyaGecersiz("yol sıradan bir dosya değil.")
    return sade


def _sozluksel_altinda(yol: Path, dizin: Path) -> bool:
    """``yol`` sözlüksel olarak ``dizin``in (kendisi değil) altında mı; Windows'ta
    büyük-küçük harf ayrımı yapılmaz."""
    y = Path(os.path.normcase(str(yol)))
    d = Path(os.path.normcase(str(dizin)))
    return y != d and y.is_relative_to(d)


def _inen_parcalar(yol: Path, dizin: Path) -> Iterator[Path]:
    """``dizin``den ``yol``a inen ara yollar: ilk alt dizinden dosyanın kendisine."""
    parcalar = yol.parts[len(dizin.parts) :]
    simdiki = dizin
    for parca in parcalar:
        simdiki = simdiki / parca
        yield simdiki


# --- yol hesabı -----------------------------------------------------------------------


def arsiv_goreli_yolu(sha256: str) -> str:
    """İçerikten deterministik arşiv yolu: ``<ilk iki hex>/<sha256>``; uzantısız."""
    if not SHA256_BICIMI.fullmatch(sha256):
        raise ValueError("SHA-256 64 karakter küçük harf onaltılık olmalı.")
    return f"{sha256[:2]}/{sha256}"


def arsiv_yolu(arsiv_dizini: Path, goreli_yol: str) -> Path:
    """Arşiv dizini + göreli yol → fiziksel yol. Göreli yol arşiv biçiminde olmalı."""
    eslesme = GORELI_YOL_BICIMI.fullmatch(goreli_yol)
    if eslesme is None or eslesme.group(1) != eslesme.group(2)[:2]:
        raise ValueError("arşiv göreli yolu <2hex>/<sha256> biçiminde olmalı.")
    return arsiv_dizini / eslesme.group(1) / eslesme.group(2)


def gecici_dizin(arsiv_dizini: Path) -> Path:
    return arsiv_dizini / GECICI_DIZIN_ADI


# --- özet ve bütünlük -----------------------------------------------------------------


def _kaynagi_ac(yol: Path) -> BinaryIO:
    """Kaynak dosyayı okumak için açar (testlerde hata enjeksiyonu noktası)."""
    return yol.open("rb")


def _geciciyi_ac(yol: Path) -> BinaryIO:
    """Geçici dosyayı yazmak için açar (testlerde hata enjeksiyonu noktası)."""
    return yol.open("xb")


def _yerine_koy(gecici: Path, hedef: Path) -> None:
    """Atomik taşıma (testlerde hata enjeksiyonu noktası)."""
    os.replace(gecici, hedef)


def sha256_hesapla(yol: Path) -> tuple[str, int]:
    """Dosyayı akışla özetler; (sha256, boyut) döndürür. Açılamazsa
    ``DosyaOkunamadi``."""
    ozet = hashlib.sha256()
    boyut = 0
    try:
        with _kaynagi_ac(yol) as girdi:
            while parca := girdi.read(OKUMA_PARCA_BOYUTU):
                ozet.update(parca)
                boyut += len(parca)
    except OSError:
        raise DosyaOkunamadi("dosya okunamadı.") from None
    return ozet.hexdigest(), boyut


def arsiv_dosyasini_dogrula(
    arsiv_dizini: Path, goreli_yol: str, boyut: int, sha256: str | None = None
) -> Path:
    """Arşiv dosyası yerinde, sıradan dosya ve beklenen boyutta mı; ``sha256``
    verilmişse özeti de baştan sona doğrulanır. Geçerse fiziksel yolu döner;
    yoksa ``ArsivDosyasiEksik``, uymuyorsa ``ArsivButunlukHatasi``."""
    yol = arsiv_yolu(arsiv_dizini, goreli_yol)
    kisa = goreli_yol[3:15]
    try:
        bilgi = os.lstat(yol)
    except FileNotFoundError:
        raise ArsivDosyasiEksik(f"arşiv dosyası eksik: {kisa}…") from None
    except OSError:
        raise ArsivButunlukHatasi(f"arşiv dosyasına erişilemedi: {kisa}…") from None
    if not os.path.isfile(yol) or os.path.islink(yol) or os.path.isjunction(yol):
        raise ArsivButunlukHatasi(f"arşiv yolu sıradan dosya değil: {kisa}…")
    if bilgi.st_size != boyut:
        raise ArsivButunlukHatasi(
            f"arşiv dosyası boyutu beklenenden farklı: {kisa}… "
            f"({bilgi.st_size} ≠ {boyut})."
        )
    if sha256 is not None:
        try:
            gercek, gercek_boyut = sha256_hesapla(yol)
        except DosyaOkunamadi:
            raise ArsivButunlukHatasi(f"arşiv dosyası okunamadı: {kisa}…") from None
        if gercek != sha256 or gercek_boyut != boyut:
            raise ArsivButunlukHatasi(
                f"arşiv dosyası içeriği beklenen özeti taşımıyor: {kisa}…"
            )
    return yol


# --- arşivleme ------------------------------------------------------------------------


def dosyayi_arsivle(
    yol: str | Path,
    *,
    gelen_dizini: Path,
    arsiv_dizini: Path,
    azami_boyut: int = AZAMI_DOSYA_BOYUTU,
) -> ArsivlenenDosya:
    """Gelen dizinindeki dosyayı denetler ve içerik adresli yola atomik arşivler.

    Dönen değer veritabanına yazılmamıştır. Hata yollarının hiçbirinde geçici
    dosya ya da yarım hedef kalmaz.
    """
    kaynak = gelen_dosyayi_dogrula(yol, gelen_dizini)
    uzanti = _uzanti(kaynak.name)
    try:
        if kaynak.stat().st_size > azami_boyut:
            raise DosyaCokBuyuk(_boyut_mesaji(azami_boyut))
    except OSError:
        raise DosyaOkunamadi("dosya okunamadı.") from None

    gecici = _gecici_ad(arsiv_dizini)
    try:
        ozet, boyut, mime = _akisla_kopyala(kaynak, gecici, azami_boyut)
        goreli_yol = arsiv_goreli_yolu(ozet)
        hedef = arsiv_yolu(arsiv_dizini, goreli_yol)
        _dizini_hazirla(hedef.parent)
        zaten_vardi = _hedefe_tasi(gecici, arsiv_dizini, goreli_yol, ozet, boyut)
    finally:
        gecici.unlink(missing_ok=True)

    return ArsivlenenDosya(
        sha256=ozet,
        boyut=boyut,
        mime=mime,
        kaynak_uzantisi=uzanti,
        kaynak_adi=kaynak.name,
        goreli_yol=goreli_yol,
        diskte_zaten_vardi=zaten_vardi,
    )


def _gecici_ad(arsiv_dizini: Path) -> Path:
    dizin = gecici_dizin(arsiv_dizini)
    _dizini_hazirla(dizin)
    return dizin / f"{uuid.uuid4().hex}{GECICI_UZANTI}"


def _dizini_hazirla(dizin: Path) -> None:
    try:
        dizin.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise ArsivYazilamadi("arşiv dizini hazırlanamadı.") from None


def _akisla_kopyala(
    kaynak: Path, gecici: Path, azami_boyut: int
) -> tuple[str, int, str]:
    """Kaynağı geçici dosyaya akışla kopyalar; (sha256, boyut, mime) döndürür.

    İlk parça okunur okunmaz boş dosya reddedilir ve MIME imzadan belirlenir;
    geçici dosya ancak bundan sonra açılır. Sınır aşımında kopya durur ve hata
    yükselir.
    """
    ozet = hashlib.sha256()
    boyut = 0
    try:
        girdi = _kaynagi_ac(kaynak)
    except OSError:
        raise DosyaOkunamadi("dosya okunamadı.") from None
    with girdi:
        try:
            parca = girdi.read(OKUMA_PARCA_BOYUTU)
        except OSError:
            raise DosyaOkunamadi("dosya okunamadı.") from None
        if not parca:
            raise GelenDosyaGecersiz("boş dosya belge olamaz.")
        mime = _mime_belirle(parca)
        try:
            with _geciciyi_ac(gecici) as cikti:
                while parca:
                    boyut += len(parca)
                    if boyut > azami_boyut:
                        raise DosyaCokBuyuk(_boyut_mesaji(azami_boyut))
                    ozet.update(parca)
                    cikti.write(parca)
                    parca = girdi.read(OKUMA_PARCA_BOYUTU)
                cikti.flush()
                os.fsync(cikti.fileno())
        except DosyaCokBuyuk:
            raise
        except OSError:
            raise ArsivYazilamadi("geçici arşiv dosyası yazılamadı.") from None
    return ozet.hexdigest(), boyut, mime


def _hedefe_tasi(
    gecici: Path, arsiv_dizini: Path, goreli_yol: str, ozet: str, boyut: int
) -> bool:
    """Geçici dosyayı hedefe atomik taşır. Hedef zaten varsa özetle doğrulanır:
    aynıysa kopya atılır ve ``True`` (zaten vardı), değilse bütünlük hatası.
    Taşıma başarılıysa ``False``."""
    hedef = arsiv_yolu(arsiv_dizini, goreli_yol)
    if hedef.exists() or hedef.is_symlink():
        arsiv_dosyasini_dogrula(arsiv_dizini, goreli_yol, boyut, ozet)
        return True
    try:
        _yerine_koy(gecici, hedef)
    except (PermissionError, FileExistsError):
        if hedef.exists():
            arsiv_dosyasini_dogrula(arsiv_dizini, goreli_yol, boyut, ozet)
            return True
        raise ArsivYazilamadi("arşiv dosyası hedefe taşınamadı.") from None
    except OSError:
        raise ArsivYazilamadi("arşiv dosyası hedefe taşınamadı.") from None
    _dizini_esle(hedef.parent)
    return False


def _dizini_esle(dizin: Path) -> None:
    """Dizin girdisini diske eşler (POSIX); Windows'ta dizin açılamaz, atlanır.
    Desteklemeyen dosya sisteminde sessizce geçilir: en iyi çaba."""
    if os.name == "nt":
        return
    try:
        fd = os.open(dizin, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _boyut_mesaji(azami_boyut: int) -> str:
    return f"dosya {azami_boyut} bayt sınırını aşıyor; kesilmez, reddedilir."


def _uzanti(ad: str) -> str:
    uzanti = Path(ad).suffix.lower()
    govde = uzanti[1:]
    if not govde or len(govde) > AZAMI_UZANTI_UZUNLUGU or not govde.isalnum():
        return ""
    return uzanti


def _mime_belirle(bas: bytes) -> str:
    """MIME yalnız içerik imzasından; bilinmiyorsa güvenli genel değer."""
    for imza, mime in _IMZALAR:
        if bas.startswith(imza):
            return mime
    return VARSAYILAN_MIME


# --- tarama ---------------------------------------------------------------------------


def arsivi_tara(arsiv_dizini: Path) -> ArsivTaramasi:
    """Arşiv dizinindeki bütün dosyaları sınıflar; hiçbir şeyi silmez, değiştirmez.
    Dizin yoksa boş tarama döner."""
    adresli: list[str] = []
    yarim: list[str] = []
    taninmayan: list[str] = []
    if not arsiv_dizini.is_dir():
        return ArsivTaramasi((), (), ())
    for dosya in sorted(arsiv_dizini.rglob("*")):
        if not dosya.is_file() and not dosya.is_symlink():
            continue
        goreli = dosya.relative_to(arsiv_dizini).as_posix()
        if goreli.startswith(f"{GECICI_DIZIN_ADI}/"):
            yarim.append(goreli)
            continue
        eslesme = GORELI_YOL_BICIMI.fullmatch(goreli)
        if eslesme is not None and eslesme.group(1) == eslesme.group(2)[:2]:
            adresli.append(goreli)
        else:
            taninmayan.append(goreli)
    return ArsivTaramasi(tuple(adresli), tuple(yarim), tuple(taninmayan))
