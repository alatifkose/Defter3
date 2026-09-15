"""DEFTERIKI MCP kapısı.

Cowork'un DEFTERIKI'ye ulaştığı tek kapı. ``uv run defteriki-mcp`` bu modülün
``main`` fonksiyonunu çalıştırır; sunucu stdio taşımasıyla konuşur.

Aşama 3 kapsamı: kalıcı araç ``sistem_durumu`` ve geçici deneme aracı
``dosya_dene`` (Teslim 3.3, aşama sonunda kaldırılır). Ürün verisi yazılmaz,
veritabanı açılmaz.

``dosya_dene`` Cowork'un dosyayı gelen dizinine bırakıp yolunu doğru
aktarabildiğini ölçer: yol izinli gelen dizininin altında olmalı, simgesel
bağlantı ve üst dizin parçası (``..``) reddedilir; dosya akışla okunup
SHA-256 ve boyut döndürülür, içerik döndürülmez. İzinli dizin dışına çıkma
denemesi günlüğe uyarı olarak düşer.

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
import sys
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
ARACLAR = [ARAC_SISTEM_DURUMU, ARAC_DOSYA_DENE]
SEMA_SURUMU_YOK = "yok"
SURUM_BILINMIYOR = "bilinmiyor"

OLAY_MCP_BASLANGIC = "mcp_baslangic"
OLAY_MCP_KAPANIS = "mcp_kapanis"
OLAY_MCP_HATASI = "mcp_hatasi"
OLAY_MCP_EL_SIKISMA = "mcp_el_sikisma"
OLAY_MCP_DOSYA_DENEME = "mcp_dosya_deneme"
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

SUNUCU_TALIMATI = (
    "DEFTERIKI kişisel finans kayıt sisteminin MCP kapısı. Bu sürümde iki araç "
    "vardır: sistem_durumu ve deneme amaçlı dosya_dene; finansal kayıt yazılmaz."
)
ARAC_SISTEM_DURUMU_ACIKLAMASI = (
    "DEFTERIKI'nin durumunu döndürür: uygulama sürümü, çalışma ortamı, şema "
    "sürümü ve bu sunucunun yetenek listesi. Yol, anahtar ya da ortam "
    "değişkeni içermez."
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


def sunucu_kur(ayarlar: Ayarlar) -> MCPServer[None]:
    """MCP sunucusunu ve araçlarını kurar; henüz çalıştırmaz."""
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
