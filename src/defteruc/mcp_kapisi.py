from __future__ import annotations

import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from mcp.server.mcpserver import Context, MCPServer

from defteruc import gunluk
from defteruc.ayarlar import Ayarlar
from defteruc.baslangic import (
    CIKIS_BASARILI,
    CIKIS_HATALI,
    BaslangicHatasi,
    ortami_hazirla,
)

SUNUCU_ADI = "defteruc"
PAKET_ADI = "defteruc"
KUTUPHANE_GUNLUK_ADI = "mcp"

ARAC_SISTEM_DURUMU = "sistem_durumu"
SURUM_BILINMIYOR = "bilinmiyor"

OLAY_MCP_BASLANGIC = "mcp_baslangic"
OLAY_MCP_KAPANIS = "mcp_kapanis"
OLAY_MCP_HATASI = "mcp_hatasi"
OLAY_MCP_EL_SIKISMA = "mcp_el_sikisma"
ISTEMCI_BILINMIYOR = "bilinmiyor"

SUNUCU_TALIMATI = (
    "DEFTERUC kişisel finans kayıt sisteminin MCP kapısı. Bu sürümde yalnız "
    "sistem_durumu aracı vardır; finansal kayıt yazılmaz."
)
ARAC_SISTEM_DURUMU_ACIKLAMASI = (
    "DEFTERUC'ün durumunu döndürür: uygulama sürümü, çalışma ortamı ve bu "
    "sunucunun yetenek listesi. Yol, anahtar ya da ortam "
    "değişkeni içermez."
)


@dataclass(frozen=True)
class SistemDurumu:
    uygulama_surumu: str
    ortam: str
    yetenekler: list[str]


def uygulama_surumu() -> str:
    try:
        return version(PAKET_ADI)
    except PackageNotFoundError:
        return SURUM_BILINMIYOR


def sistem_durumu(ayarlar: Ayarlar) -> SistemDurumu:
    return SistemDurumu(
        uygulama_surumu=uygulama_surumu(),
        ortam=ayarlar.ortam.value,
        yetenekler=[ARAC_SISTEM_DURUMU],
    )


GUNLUK_METIN_AZAMI = 64

GUNLUK_YETENEK_AZAMI = 8


def gunluk_icin_suz(metin: str, azami: int = GUNLUK_METIN_AZAMI) -> str:
    suzulmus = "".join(c if c.isprintable() else "?" for c in metin)
    return suzulmus if len(suzulmus) <= azami else suzulmus[:azami] + "…"


def el_sikisma_ozeti(baglam: Context[Any, Any]) -> str:
    oturum = baglam.session
    parametreler = oturum.client_params
    if parametreler is None:
        istemci = ISTEMCI_BILINMIYOR
    else:
        bilgi = parametreler.client_info
        istemci = f"{gunluk_icin_suz(bilgi.name)} {gunluk_icin_suz(bilgi.version)}"
    yetenekler = oturum.client_capabilities
    if yetenekler is None:
        yetenek_metni = "yok"
    else:
        adlar = sorted(
            yetenekler.model_dump(mode="json", by_alias=True, exclude_none=True)
        )
        gorunen = [gunluk_icin_suz(ad, 32) for ad in adlar[:GUNLUK_YETENEK_AZAMI]]
        if len(adlar) > GUNLUK_YETENEK_AZAMI:
            gorunen.append("…")
        yetenek_metni = "[" + ", ".join(gorunen) + "]"
    protokol = gunluk_icin_suz(str(oturum.protocol_version))
    return f"istemci={istemci} protokol={protokol} yetenekler={yetenek_metni}"


def sunucu_kur(ayarlar: Ayarlar) -> MCPServer[None]:
    sunucu: MCPServer[None] = MCPServer(
        name=SUNUCU_ADI,
        version=uygulama_surumu(),
        instructions=SUNUCU_TALIMATI,
    )

    @sunucu.tool(name=ARAC_SISTEM_DURUMU, description=ARAC_SISTEM_DURUMU_ACIKLAMASI)
    def sistem_durumu_araci(baglam: Context[Any, Any]) -> SistemDurumu:
        gunluk.olay_kaydet(OLAY_MCP_EL_SIKISMA, el_sikisma_ozeti(baglam))
        return sistem_durumu(ayarlar)

    return sunucu


def main() -> int:
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
    print(f"DEFTERUC MCP kapısı başlatılamadı. {mesaj}", file=sys.stderr, flush=True)
