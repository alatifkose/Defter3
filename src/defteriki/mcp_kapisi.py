"""DEFTERIKI MCP kapısı.

Cowork'un DEFTERIKI'ye ulaştığı tek kapı. ``uv run defteriki-mcp`` bu modülün
``main`` fonksiyonunu çalıştırır; sunucu stdio taşımasıyla konuşur.

Aşama 3 kapsamı: tek araç ``sistem_durumu``. Ürün verisi yazılmaz, veritabanı
açılmaz.

Kurallar:

* stdout yalnız protokole aittir; bu modül stdout'a hiçbir şey yazmaz.
  SDK'nın stdio taşıması sunucu çalışırken dosya tanımlayıcısı 1'i stderr'e
  çevirir, yine de bütün tanı çıktısı teknik günlüğe gider: SDK'nın ``mcp``
  günlüğü de aynı dosyaya bağlanır.
* Araç yanıtlarında yol, anahtar ya da ortam değişkeni dökümü yoktur.
* Modül import edildiğinde sunucu kurulmaz, dosya oluşturulmaz.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

from mcp.server.mcpserver import MCPServer

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
SEMA_SURUMU_YOK = "yok"
SURUM_BILINMIYOR = "bilinmiyor"

OLAY_MCP_BASLANGIC = "mcp_baslangic"
OLAY_MCP_KAPANIS = "mcp_kapanis"
OLAY_MCP_HATASI = "mcp_hatasi"

SUNUCU_TALIMATI = (
    "DEFTERIKI kişisel finans kayıt sisteminin MCP kapısı. Bu sürümde yalnız "
    "sistem_durumu aracı vardır; finansal kayıt yazılmaz."
)
ARAC_SISTEM_DURUMU_ACIKLAMASI = (
    "DEFTERIKI'nin durumunu döndürür: uygulama sürümü, çalışma ortamı, şema "
    "sürümü ve bu sunucunun yetenek listesi. Yol, anahtar ya da ortam "
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
    sema_surumu: str
    """Veritabanı şema sürümü; henüz veritabanı olmadığından ``yok``."""
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
        sema_surumu=SEMA_SURUMU_YOK,
        yetenekler=[ARAC_SISTEM_DURUMU],
    )


def sunucu_kur(ayarlar: Ayarlar) -> MCPServer[None]:
    """MCP sunucusunu ve araçlarını kurar; henüz çalıştırmaz."""
    sunucu: MCPServer[None] = MCPServer(
        name=SUNUCU_ADI,
        version=uygulama_surumu(),
        instructions=SUNUCU_TALIMATI,
    )

    @sunucu.tool(name=ARAC_SISTEM_DURUMU, description=ARAC_SISTEM_DURUMU_ACIKLAMASI)
    def sistem_durumu_araci() -> SistemDurumu:
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
    print(f"DEFTERIKI MCP kapısı başlatılamadı. {mesaj}", file=sys.stderr, flush=True)
