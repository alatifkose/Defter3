"""DEFTERUC MCP kapısı.

Cowork'un DEFTERUC'e ulaştığı tek kapı. ``uv run defteruc-mcp`` bu modülün
``main`` fonksiyonunu çalıştırır; sunucu stdio taşımasıyla konuşur.

Kapsam: tek araç ``sistem_durumu``. Ürün verisi yazılmaz; veritabanına
dokunulmaz.

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

import json
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
    """Aracın yapılandırılmış yanıtı.

    ``slots=True`` bilerek yok: SDK dataclass'tan JSON şeması üretirken slot
    tanımlayıcılarını varsayılan değer sanıp şemayı düşürüyor.
    """

    uygulama_surumu: str
    ortam: str
    yetenekler: list[str]
    """Bu sunucunun sunduğu araç adları."""


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
        yetenekler=[ARAC_SISTEM_DURUMU],
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
    print(f"DEFTERUC MCP kapısı başlatılamadı. {mesaj}", file=sys.stderr, flush=True)
