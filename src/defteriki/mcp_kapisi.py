"""DEFTERIKI MCP kapısı.

Cowork'un DEFTERIKI'ye ulaştığı tek kapı. ``uv run defteriki-mcp`` bu modülün
``main`` fonksiyonunu çalıştırır; sunucu stdio taşımasıyla konuşur.

Aşama 3 kapsamı: kalıcı araç ``sistem_durumu`` ve geçici deneme araçları
``dosya_dene`` (Teslim 3.3) ile ``deneme_baslat`` / ``deneme_durumu``
(Teslim 3.4); geçici araçlar aşama sonunda kaldırılır. Ürün verisi
yazılmaz, veritabanı açılmaz.

``dosya_dene`` Cowork'un dosyayı gelen dizinine bırakıp yolunu doğru
aktarabildiğini ölçer: yol izinli gelen dizininin altında olmalı, simgesel
bağlantı ve üst dizin parçası (``..``) reddedilir; dosya akışla okunup
SHA-256 ve boyut döndürülür, içerik döndürülmez. İzinli dizin dışına çıkma
denemesi günlüğe uyarı olarak düşer.

``deneme_baslat`` / ``deneme_durumu`` çok adımlı protokolün provasıdır:
Cowork'ta elicitation olmadığından kullanıcı kararı bekleyen bir iş çağrıyı
açık tutamaz; araç ``BEKLIYOR`` ve bir talep kimliği döner, Cowork daha sonra
aynı kimlikle durumu sorar. Provada kullanıcı onayının yerine sabit bir süre
vardır: başlangıçtan ``DENEME_TAMAMLANMA_SANIYE`` geçince ``TAMAMLANDI``.
Aynı işlem anahtarıyla tekrar başlatma aynı talep kimliğini verir (yeni iş
açılmaz). Talep kayıtları süreç belleğindedir; istemci birden fazla sunucu
süreci çalıştırıyorsa ikinci süreç kimliği tanımaz ve ``BILINMIYOR`` döner.
Bu bilerek ölçülür: günlükteki ``surec`` alanı hangi süreçten yanıt
geldiğini gösterir.

Kurallar:

* stdout yalnız protokole aittir; bu modül stdout'a hiçbir şey yazmaz.
  SDK'nın stdio taşıması sunucu çalışırken dosya tanımlayıcısı 1'i stderr'e
  çevirir, yine de bütün tanı çıktısı teknik günlüğe gider: SDK'nın ``mcp``
  günlüğü de aynı dosyaya bağlanır.
* Araç yanıtlarında yol, anahtar ya da ortam değişkeni dökümü yoktur.
* Her araç çağrısında el sıkışma özeti (istemci adı ve sürümü, protokol
  sürümü, istemci yetenekleri) günlüğe yazılır; Aşama 3'ün ölçümü budur.
* Modül import edildiğinde sunucu kurulmaz, dosya oluşturulmaz.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Context, MCPServer

from defteriki import gunluk
from defteriki.ayarlar import Ayarlar
from defteriki.baslangic import (
    CIKIS_BASARILI,
    CIKIS_HATALI,
    BaslangicHatasi,
    ortami_hazirla,
)

SUNUCU_ADI = "defteriki"
PAKET_ADI = "defteriki"
KUTUPHANE_GUNLUK_ADI = "mcp"

ARAC_SISTEM_DURUMU = "sistem_durumu"
ARAC_DOSYA_DENE = "dosya_dene"
ARAC_DENEME_BASLAT = "deneme_baslat"
ARAC_DENEME_DURUMU = "deneme_durumu"
ARACLAR = [
    ARAC_SISTEM_DURUMU,
    ARAC_DOSYA_DENE,
    ARAC_DENEME_BASLAT,
    ARAC_DENEME_DURUMU,
]
SEMA_SURUMU_YOK = "yok"
SURUM_BILINMIYOR = "bilinmiyor"

OLAY_MCP_BASLANGIC = "mcp_baslangic"
OLAY_MCP_KAPANIS = "mcp_kapanis"
OLAY_MCP_HATASI = "mcp_hatasi"
OLAY_MCP_EL_SIKISMA = "mcp_el_sikisma"
OLAY_MCP_DOSYA_DENEME = "mcp_dosya_deneme"
OLAY_MCP_DENEME = "mcp_deneme"
ISTEMCI_BILINMIYOR = "bilinmiyor"

SONUC_OKUNDU = "okundu"
SONUC_REDDEDILDI = "reddedildi"
GEREKCE_YOK = ""
GEREKCE_MUTLAK_DEGIL = "yol mutlak değil"
GEREKCE_UST_DIZIN = "yolda üst dizin parçası (..) var"
GEREKCE_BULUNAMADI = "dosya bulunamadı"
GEREKCE_DIZIN_DISI = "izinli gelen dizininin dışında"
GEREKCE_BAGLANTI = "simgesel bağlantı ya da takma yol"
GEREKCE_DOSYA_DEGIL = "sıradan bir dosya değil"
GEREKCE_OKUNAMADI = "dosya okunamadı"
OKUMA_PARCA_BOYUTU = 1024 * 1024
"""Bayt; dosya bu parçalarla akışla okunur, bütünü belleğe alınmaz."""

DURUM_BEKLIYOR = "BEKLIYOR"
DURUM_TAMAMLANDI = "TAMAMLANDI"
DURUM_BILINMIYOR = "BILINMIYOR"
DURUM_REDDEDILDI = "REDDEDILDI"
DENEME_TAMAMLANMA_SANIYE = 20.0
"""Prova süresi: kullanıcı onayının yerine geçer; başlangıçtan bu kadar
saniye sonra talep TAMAMLANDI olur. Yalnız Teslim 3.4 için, ürüne girmez."""
TALEP_KIMLIGI_BAYT = 6
"""Talep kimliği rastgele bu kadar bayt, hex olarak 12 karakter."""
SONRAKI_ADIM_BEKLE = (
    "İş henüz bitmedi. Bir süre sonra aynı talep_id ile deneme_durumu aracını "
    "tekrar çağır."
)
SONRAKI_ADIM_BITTI = "İş tamamlandı; kullanıcıya bildir."
SONRAKI_ADIM_BILINMIYOR = (
    "Bu talep_id bu sunucuda bilinmiyor. Aynı islem_anahtari ile deneme_baslat "
    "aracını yeniden çağır; aynı anahtar aynı işi verir."
)
SONRAKI_ADIM_ANAHTAR_BOS = "islem_anahtari boş olamaz; anlamlı bir anahtar ver."

SUNUCU_TALIMATI = (
    "DEFTERIKI kişisel finans kayıt sisteminin MCP kapısı. Bu sürümde "
    "sistem_durumu ve deneme amaçlı dosya_dene, deneme_baslat, deneme_durumu "
    "araçları vardır; finansal kayıt yazılmaz. Bir araç durum=BEKLIYOR dönerse "
    "iş bitmemiştir: bir süre sonra aynı talep_id ile durumu tekrar sor."
)
ARAC_SISTEM_DURUMU_ACIKLAMASI = (
    "DEFTERIKI'nin durumunu döndürür: uygulama sürümü, çalışma ortamı, şema "
    "sürümü ve bu sunucunun yetenek listesi. Yol, anahtar ya da ortam "
    "değişkeni içermez."
)
ARAC_DENEME_BASLAT_ACIKLAMASI = (
    "Çok adımlı protokol denemesi, adım 1. islem_anahtari ile bir deneme işi "
    "başlatır; hemen durum=BEKLIYOR ve bir talep_id döner, çağrı açık kalmaz. "
    "Aynı islem_anahtari ile tekrar çağrılırsa yeni iş açmaz, aynı talep_id'yi "
    "verir. Sonucu öğrenmek için talep_id ile deneme_durumu aracını çağır."
)
ARAC_DENEME_DURUMU_ACIKLAMASI = (
    "Çok adımlı protokol denemesi, adım 2. deneme_baslat'ın verdiği talep_id ile "
    "işin durumunu sorar: BEKLIYOR ise bir süre sonra tekrar sor; TAMAMLANDI ise "
    "iş bitti; BILINMIYOR ise talep bu sunucuda yok, deneme_baslat ile aynı "
    "islem_anahtari kullanarak yeniden başlat. Yanıttaki sonraki_adim alanı ne "
    "yapılacağını söyler."
)
ARAC_DOSYA_DENE_ACIKLAMASI = (
    "Dosya erişim denemesi. Verilen mutlak yoldaki dosyayı DEFTERIKI'nin izinli "
    "gelen dizininde arar, akışla okur ve SHA-256 özeti ile bayt boyutunu "
    "döndürür; içerik döndürmez. Gelen dizininin dışındaki yollar, simgesel "
    "bağlantılar ve '..' içeren yollar reddedilir; red durumunda sonuc "
    "'reddedildi' ve gerekce dolu döner."
)


@dataclass(frozen=True)
class SistemDurumu:
    """Aracın yapılandırılmış yanıtı.

    ``slots=True`` bilerek yok: SDK dataclass'tan JSON şeması üretirken slot
    tanımlayıcılarını varsayılan değer sanıp şemayı düşürüyor.
    """

    uygulama_surumu: str
    ortam: str
    sema_surumu: str
    """Veritabanı şema sürümü; henüz veritabanı olmadığından ``yok``."""
    yetenekler: list[str]
    """Bu sunucunun sunduğu araç adları."""


@dataclass(frozen=True)
class DosyaDenemesi:
    """``dosya_dene`` aracının yapılandırılmış yanıtı; yol içermez."""

    sonuc: str
    """``okundu`` ya da ``reddedildi``."""
    gerekce: str
    """Red gerekçesi; okunduysa boş."""
    sha256: str
    """Dosyanın SHA-256 özeti (hex); reddedildiyse boş."""
    boyut_bayt: int
    """Okunan bayt sayısı; reddedildiyse 0."""


@dataclass(frozen=True)
class DenemeYaniti:
    """``deneme_baslat`` ve ``deneme_durumu`` araçlarının ortak yanıtı."""

    durum: str
    """``BEKLIYOR``, ``TAMAMLANDI``, ``BILINMIYOR`` ya da ``REDDEDILDI``."""
    talep_id: str
    """Talep kimliği; reddedildiyse boş."""
    gecen_saniye: float
    """Talebin başlangıcından bu yana geçen süre; bilinmiyorsa 0."""
    sonraki_adim: str
    """İstemciye ne yapacağını söyleyen kısa metin."""


@dataclass(frozen=True, slots=True)
class _Talep:
    talep_id: str
    baslangic: float


class DenemeTakibi:
    """Deneme taleplerini süreç belleğinde tutar.

    ``saat`` tekdüze artan bir saniye sayacıdır (varsayılan
    ``time.monotonic``); testler sahte saat verir. ``tamamlanma_saniye``
    kullanıcı onayının yerine geçen prova süresidir.
    """

    def __init__(
        self,
        tamamlanma_saniye: float = DENEME_TAMAMLANMA_SANIYE,
        saat: Callable[[], float] = time.monotonic,
    ) -> None:
        self._tamamlanma_saniye = tamamlanma_saniye
        self._saat = saat
        self._anahtara_gore: dict[str, _Talep] = {}
        self._kimlige_gore: dict[str, _Talep] = {}

    def baslat(self, islem_anahtari: str) -> DenemeYaniti:
        """Anahtar yeniyse talep açar; değilse aynı talebi döndürür."""
        anahtar = islem_anahtari.strip()
        if not anahtar:
            self._kaydet(ARAC_DENEME_BASLAT, DURUM_REDDEDILDI, "-", 0.0, "anahtar_bos")
            return DenemeYaniti(DURUM_REDDEDILDI, "", 0.0, SONRAKI_ADIM_ANAHTAR_BOS)

        talep = self._anahtara_gore.get(anahtar)
        yeni = talep is None
        if talep is None:
            talep = _Talep(secrets.token_hex(TALEP_KIMLIGI_BAYT), self._saat())
            self._anahtara_gore[anahtar] = talep
            self._kimlige_gore[talep.talep_id] = talep
        gecen = self._saat() - talep.baslangic
        self._kaydet(
            ARAC_DENEME_BASLAT,
            DURUM_BEKLIYOR,
            talep.talep_id,
            gecen,
            "yeni" if yeni else "tekrar",
        )
        return DenemeYaniti(DURUM_BEKLIYOR, talep.talep_id, gecen, SONRAKI_ADIM_BEKLE)

    def durum(self, talep_id: str) -> DenemeYaniti:
        """Talebin durumunu döndürür; süre dolduysa TAMAMLANDI."""
        talep = self._kimlige_gore.get(talep_id.strip())
        if talep is None:
            self._kaydet(ARAC_DENEME_DURUMU, DURUM_BILINMIYOR, "-", 0.0)
            return DenemeYaniti(DURUM_BILINMIYOR, "", 0.0, SONRAKI_ADIM_BILINMIYOR)
        gecen = self._saat() - talep.baslangic
        if gecen >= self._tamamlanma_saniye:
            self._kaydet(ARAC_DENEME_DURUMU, DURUM_TAMAMLANDI, talep.talep_id, gecen)
            return DenemeYaniti(
                DURUM_TAMAMLANDI, talep.talep_id, gecen, SONRAKI_ADIM_BITTI
            )
        self._kaydet(ARAC_DENEME_DURUMU, DURUM_BEKLIYOR, talep.talep_id, gecen)
        return DenemeYaniti(DURUM_BEKLIYOR, talep.talep_id, gecen, SONRAKI_ADIM_BEKLE)

    @staticmethod
    def _kaydet(
        arac: str, durum: str, talep_id: str, gecen: float, not_: str = ""
    ) -> None:
        ek = f" not={not_}" if not_ else ""
        gunluk.olay_kaydet(
            OLAY_MCP_DENEME,
            f"arac={arac} durum={durum} talep={talep_id} gecen={gecen:.1f} "
            f"surec={os.getpid()}{ek}",
        )


def uygulama_surumu() -> str:
    """Kurulu paketin sürümü; paket bulunamazsa ``bilinmiyor``."""
    try:
        return version(PAKET_ADI)
    except PackageNotFoundError:
        return SURUM_BILINMIYOR


def sistem_durumu(ayarlar: Ayarlar) -> SistemDurumu:
    """Uygulamanın durumunu döndürür; yol ya da sır içermez."""
    return SistemDurumu(
        uygulama_surumu=uygulama_surumu(),
        ortam=ayarlar.ortam.value,
        sema_surumu=SEMA_SURUMU_YOK,
        yetenekler=list(ARACLAR),
    )


def dosya_dene(yol_metni: str, gelen_dizini: Path) -> DosyaDenemesi:
    """Yolu denetler, izinliyse dosyayı akışla okuyup özetini döndürür.

    Sıra: mutlak yol → ``..`` yok → gerçek yol çözülür ve izinli dizinin
    gerçek yolunun altında mı bakılır → simgesel bağlantı yok → sıradan dosya
    → akışla SHA-256. Her çağrı günlüğe ``mcp_dosya_deneme`` olayı yazar;
    izinli dizin dışına çıkma denemesi uyarı seviyesindedir. Günlüğe tam yol
    yazılmaz, yalnız gelen dizinine göre göreli ad.
    """
    yol = Path(yol_metni)
    if not yol_metni.strip() or not yol.is_absolute():
        return _red(GEREKCE_MUTLAK_DEGIL)
    if ".." in yol.parts:
        return _red(GEREKCE_UST_DIZIN)

    gelen_gercek = gelen_dizini.resolve()
    try:
        hedef = yol.resolve(strict=True)
    except FileNotFoundError:
        return _red(GEREKCE_BULUNAMADI)
    except (OSError, RuntimeError):
        return _red(GEREKCE_OKUNAMADI)

    if not hedef.is_relative_to(gelen_gercek):
        return _red(GEREKCE_DIZIN_DISI, seviye=logging.WARNING)
    goreli = hedef.relative_to(gelen_gercek).as_posix()

    if yol.is_symlink() or _takma_yol_mu(yol, hedef):
        return _red(GEREKCE_BAGLANTI, goreli)
    if not hedef.is_file():
        return _red(GEREKCE_DOSYA_DEGIL, goreli)

    try:
        ozet, boyut = _akisla_ozetle(hedef)
    except OSError:
        return _red(GEREKCE_OKUNAMADI, goreli)

    gunluk.olay_kaydet(
        OLAY_MCP_DOSYA_DENEME, f"sonuc={SONUC_OKUNDU} dosya={goreli} boyut={boyut}"
    )
    return DosyaDenemesi(
        sonuc=SONUC_OKUNDU, gerekce=GEREKCE_YOK, sha256=ozet, boyut_bayt=boyut
    )


def _takma_yol_mu(verilen: Path, gercek: Path) -> bool:
    """Verilen yol sözlüksel sadeleştirmeden sonra gerçek yoldan farklı mı?

    Fark varsa arada simgesel bağlantı, kavşak (junction) ya da başka bir
    takma yol vardır. Büyük/küçük harf farkı platform kuralına göre sayılmaz.
    """
    sade = os.path.normcase(os.path.normpath(str(verilen)))
    return sade != os.path.normcase(str(gercek))


def _akisla_ozetle(dosya: Path) -> tuple[str, int]:
    ozet = hashlib.sha256()
    boyut = 0
    with dosya.open("rb") as akis:
        while parca := akis.read(OKUMA_PARCA_BOYUTU):
            ozet.update(parca)
            boyut += len(parca)
    return ozet.hexdigest(), boyut


def _red(
    gerekce: str, goreli: str | None = None, seviye: int = logging.INFO
) -> DosyaDenemesi:
    dosya = f" dosya={goreli}" if goreli is not None else ""
    gunluk.olay_kaydet(
        OLAY_MCP_DOSYA_DENEME,
        f"sonuc={SONUC_REDDEDILDI} gerekce={gerekce}{dosya}",
        seviye,
    )
    return DosyaDenemesi(
        sonuc=SONUC_REDDEDILDI, gerekce=gerekce, sha256="", boyut_bayt=0
    )


def el_sikisma_ozeti(baglam: Context[Any, Any]) -> str:
    """Bağlantının el sıkışma bilgisini tek satırda özetler.

    İstemcinin ``initialize`` ile bildirdiği ad ve sürüm, müzakere edilen
    protokol sürümü ve istemci yetenekleri. Yol, anahtar ya da kişisel veri
    içermez; günlüğe yazılmak içindir.
    """
    oturum = baglam.session
    parametreler = oturum.client_params
    if parametreler is None:
        istemci = ISTEMCI_BILINMIYOR
    else:
        istemci = f"{parametreler.client_info.name} {parametreler.client_info.version}"
    yetenekler = oturum.client_capabilities
    yetenek_metni = (
        json.dumps(
            yetenekler.model_dump(mode="json", by_alias=True, exclude_none=True),
            ensure_ascii=False,
            sort_keys=True,
        )
        if yetenekler is not None
        else "yok"
    )
    return (
        f"istemci={istemci} protokol={oturum.protocol_version} "
        f"yetenekler={yetenek_metni}"
    )


def sunucu_kur(ayarlar: Ayarlar, takip: DenemeTakibi | None = None) -> MCPServer[None]:
    """MCP sunucusunu ve araçlarını kurar; henüz çalıştırmaz.

    ``takip`` verilmezse sunucu ömrü boyunca yaşayan bir ``DenemeTakibi``
    kurulur.
    """
    deneme_takibi = takip if takip is not None else DenemeTakibi()
    sunucu: MCPServer[None] = MCPServer(
        name=SUNUCU_ADI,
        version=uygulama_surumu(),
        instructions=SUNUCU_TALIMATI,
    )

    @sunucu.tool(name=ARAC_SISTEM_DURUMU, description=ARAC_SISTEM_DURUMU_ACIKLAMASI)
    def sistem_durumu_araci(baglam: Context[Any, Any]) -> SistemDurumu:
        gunluk.olay_kaydet(OLAY_MCP_EL_SIKISMA, el_sikisma_ozeti(baglam))
        return sistem_durumu(ayarlar)

    @sunucu.tool(name=ARAC_DOSYA_DENE, description=ARAC_DOSYA_DENE_ACIKLAMASI)
    def dosya_dene_araci(yol: str, baglam: Context[Any, Any]) -> DosyaDenemesi:
        gunluk.olay_kaydet(OLAY_MCP_EL_SIKISMA, el_sikisma_ozeti(baglam))
        return dosya_dene(yol, ayarlar.gelen_dizini)

    @sunucu.tool(name=ARAC_DENEME_BASLAT, description=ARAC_DENEME_BASLAT_ACIKLAMASI)
    def deneme_baslat_araci(
        islem_anahtari: str, baglam: Context[Any, Any]
    ) -> DenemeYaniti:
        gunluk.olay_kaydet(OLAY_MCP_EL_SIKISMA, el_sikisma_ozeti(baglam))
        return deneme_takibi.baslat(islem_anahtari)

    @sunucu.tool(name=ARAC_DENEME_DURUMU, description=ARAC_DENEME_DURUMU_ACIKLAMASI)
    def deneme_durumu_araci(talep_id: str, baglam: Context[Any, Any]) -> DenemeYaniti:
        gunluk.olay_kaydet(OLAY_MCP_EL_SIKISMA, el_sikisma_ozeti(baglam))
        return deneme_takibi.durum(talep_id)

    return sunucu


def main() -> int:
    """MCP kapısını stdio üzerinde çalıştırır; çıkış kodunu döndürür."""
    try:
        ayarlar, _ = ortami_hazirla()
    except BaslangicHatasi as hata:
        _hata_yaz(str(hata))
        return CIKIS_HATALI

    try:
        gunluk.kutuphane_gunlugunu_yonlendir(KUTUPHANE_GUNLUK_ADI)
        sunucu = sunucu_kur(ayarlar)
        gunluk.olay_kaydet(
            OLAY_MCP_BASLANGIC,
            f"ortam={ayarlar.ortam.value} surum={uygulama_surumu()} tasima=stdio",
        )
        sunucu.run(transport="stdio")
    except Exception as hata:
        gunluk.hata_kaydet(OLAY_MCP_HATASI, hata)
        _hata_yaz(f"Beklenmeyen hata ({type(hata).__name__}): {hata}")
        return CIKIS_HATALI

    gunluk.olay_kaydet(OLAY_MCP_KAPANIS, "istemci bağlantıyı kapattı")
    return CIKIS_BASARILI


def _hata_yaz(mesaj: str) -> None:
    print(f"DEFTERIKI MCP kapısı başlatılamadı. {mesaj}", file=sys.stderr, flush=True)
