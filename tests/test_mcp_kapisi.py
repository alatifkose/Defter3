"""MCP kapısı testleri.

Sunucu ayrı bir süreçte, ``test`` ortamında ve geçici veri köküyle başlatılır.
İstemci taklidi yoktur: JSON-RPC mesajları ham satırlar olarak stdin'e
yazılır, her isteğin yanıtı stdout'tan okunduktan sonra sıradakine geçilir;
stdin en sonda kapatılır. Böylece stdout'un protokol dışında hiçbir şey
taşımadığı da sınanır.
"""

import copy
import dataclasses
import json
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest

from defteruc import ayarlar as ay
from defteruc import gunluk, mcp_kapisi

DEFTERUC_DEGISKENLERI = (
    ay.ORTAM_DEGISKENI,
    ay.VERI_KOKU_DEGISKENI,
    ay.VERITABANI_YOLU_DEGISKENI,
    ay.BELGE_DIZINI_DEGISKENI,
    ay.LOG_DIZINI_DEGISKENI,
    ay.GELEN_DIZINI_DEGISKENI,
)

ISTEMCI_PROTOKOL_SURUMU = "2025-06-18"

ILK_ISTEKLER: tuple[dict[str, Any], ...] = (
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": ISTEMCI_PROTOKOL_SURUMU,
            "capabilities": {},
            "clientInfo": {"name": "defteruc-test", "version": "0"},
        },
    },
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": mcp_kapisi.ARAC_SISTEM_DURUMU, "arguments": {}},
    },
)


@pytest.fixture(autouse=True)
def temiz_cevre_ve_gunluk(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for degisken in DEFTERUC_DEGISKENLERI:
        monkeypatch.delenv(degisken, raising=False)
    gunluk.gunlugu_kapat()
    yield
    gunluk.gunlugu_kapat()


@pytest.fixture
def test_koku(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    kok = tmp_path / "kok"
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(kok))
    return kok / "test"


# --- süreç içi -------------------------------------------------------------


def test_sistem_durumu_beklenen_alanlari_tasir(test_koku: Path) -> None:
    durum = mcp_kapisi.sistem_durumu(ay.ayarlari_yukle())

    assert durum.ortam == "test"
    assert durum.yetenekler == [mcp_kapisi.ARAC_SISTEM_DURUMU]
    assert durum.uygulama_surumu not in ("", mcp_kapisi.SURUM_BILINMIYOR)


def test_sistem_durumu_veritabani_yokken_dosya_olusturmaz(test_koku: Path) -> None:
    ayarlar = ay.ayarlari_yukle()
    ay.dizinleri_hazirla(ayarlar)

    mcp_kapisi.sistem_durumu(ayarlar)

    assert not ayarlar.veritabani_yolu.exists()
    assert list(ayarlar.veritabani_yolu.parent.glob("*.sqlite3*")) == []


def test_sistem_durumu_yol_ve_ortam_degiskeni_icermez(test_koku: Path) -> None:
    durum = mcp_kapisi.sistem_durumu(ay.ayarlari_yukle())

    metin = json.dumps(dataclasses.asdict(durum), ensure_ascii=False)

    assert str(test_koku) not in metin
    assert str(test_koku.parent) not in metin
    assert "DEFTERUC_" not in metin


def test_sunucu_yalniz_sistem_durumu_aracini_sunar(test_koku: Path) -> None:
    sunucu = mcp_kapisi.sunucu_kur(ay.ayarlari_yukle())

    araclar = anyio.run(sunucu.list_tools)

    assert [arac.name for arac in araclar] == [mcp_kapisi.ARAC_SISTEM_DURUMU]
    assert sunucu.name == mcp_kapisi.SUNUCU_ADI
    (arac,) = araclar
    assert arac.output_schema is not None
    assert set(arac.output_schema["required"]) == {
        "uygulama_surumu",
        "ortam",
        "yetenekler",
    }


def test_import_sunucu_kurmaz_ve_dosya_olusturmaz(tmp_path: Path) -> None:
    assert not gunluk.kurulu()
    assert list(tmp_path.iterdir()) == []


# --- ayrı süreçte stdio ----------------------------------------------------

SUNUCU_KOMUTU = "import sys; from defteruc.mcp_kapisi import main; sys.exit(main())"
BEKLEME_SANIYE = 60


def _cevre(cevre: dict[str, str]) -> dict[str, str]:
    temiz = {k: v for k, v in os.environ.items() if not k.startswith("DEFTERUC_")}
    temiz.update(cevre)
    temiz["PYTHONUTF8"] = "1"
    return temiz


@dataclasses.dataclass(frozen=True, slots=True)
class Konusma:
    stdout_satirlari: list[str]
    stderr: str
    cikis_kodu: int

    @property
    def yanitlar(self) -> dict[int, dict[str, Any]]:
        """stdout'taki her satırı JSON-RPC mesajı olarak çözer; kimliğe göre verir."""
        yanitlar: dict[int, dict[str, Any]] = {}
        for satir in self.stdout_satirlari:
            mesaj: dict[str, Any] = json.loads(satir)
            assert mesaj["jsonrpc"] == "2.0", satir
            if "id" in mesaj:
                yanitlar[int(mesaj["id"])] = mesaj
        return yanitlar


def _sunucuyla_konus(
    cwd: Path,
    cevre: dict[str, str],
    mesajlar: tuple[dict[str, Any], ...],
    komut: str = SUNUCU_KOMUTU,
) -> Konusma:
    """Mesajları sırayla gönderir; istek olanların yanıtını bekler, sonra kapatır."""
    surec = subprocess.Popen(
        [sys.executable, "-c", komut],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=_cevre(cevre),
        text=True,
        encoding="utf-8",
    )
    assert surec.stdin is not None and surec.stdout is not None
    bekci = threading.Timer(BEKLEME_SANIYE, surec.kill)
    bekci.start()
    satirlar: list[str] = []
    try:
        for mesaj in mesajlar:
            surec.stdin.write(json.dumps(mesaj) + "\n")
            surec.stdin.flush()
            if "id" not in mesaj:
                continue
            while True:
                satir = surec.stdout.readline()
                assert satir, f"sunucu {mesaj['id']} yanıtından önce stdout'u kapattı"
                satirlar.append(satir.rstrip("\n"))
                if json.loads(satir).get("id") == mesaj["id"]:
                    break
        surec.stdin.close()
        kalan, stderr = surec.communicate(timeout=BEKLEME_SANIYE)
        satirlar.extend(s for s in kalan.splitlines() if s.strip())
    finally:
        bekci.cancel()
        if surec.poll() is None:
            surec.kill()
            surec.wait()
    return Konusma(satirlar, stderr, surec.returncode)


def _sunucuyu_calistir(
    cwd: Path, cevre: dict[str, str], mesajlar: tuple[dict[str, Any], ...]
) -> subprocess.CompletedProcess[str]:
    """Bütün girdiyi tek seferde verir; yanıt beklemez. Başarısız başlangıç için."""
    girdi = "".join(json.dumps(mesaj) + "\n" for mesaj in mesajlar)
    return subprocess.run(
        [sys.executable, "-c", SUNUCU_KOMUTU],
        input=girdi,
        cwd=cwd,
        env=_cevre(cevre),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=BEKLEME_SANIYE,
        check=False,
    )


def test_stdio_uzerinden_baslatma_arac_listesi_ve_cagri(
    tmp_path: Path, test_koku: Path
) -> None:
    calisma = tmp_path / "baska_yer"
    calisma.mkdir()

    sonuc = _sunucuyla_konus(calisma, dict(os.environ), ILK_ISTEKLER)

    assert sonuc.cikis_kodu == 0, sonuc.stderr
    assert "Traceback" not in sonuc.stderr
    yanitlar = sonuc.yanitlar
    assert set(yanitlar) == {1, 2, 3}

    baslangic = yanitlar[1]["result"]
    assert baslangic["serverInfo"]["name"] == mcp_kapisi.SUNUCU_ADI
    assert baslangic["protocolVersion"]

    araclar = yanitlar[2]["result"]["tools"]
    assert [arac["name"] for arac in araclar] == [mcp_kapisi.ARAC_SISTEM_DURUMU]
    assert araclar[0]["inputSchema"]["properties"] == {}

    cagri = yanitlar[3]["result"]
    assert not cagri.get("isError", False)
    assert cagri["structuredContent"] == {
        "uygulama_surumu": mcp_kapisi.uygulama_surumu(),
        "ortam": "test",
        "yetenekler": [mcp_kapisi.ARAC_SISTEM_DURUMU],
    }
    assert all(str(test_koku) not in satir for satir in sonuc.stdout_satirlari)
    assert not any(calisma.iterdir())
    assert not (test_koku / ay.VERITABANI_DOSYA_ADI).exists()  # araç dosya açmadı


def test_stdio_sunucusu_gunluge_yazar_stdout_a_yazmaz(
    tmp_path: Path, test_koku: Path
) -> None:
    sonuc = _sunucuyla_konus(tmp_path, dict(os.environ), ILK_ISTEKLER)

    assert sonuc.cikis_kodu == 0, sonuc.stderr
    icerik = (test_koku / ay.LOG_DIZIN_ADI / gunluk.GUNLUK_DOSYA_ADI).read_text(
        encoding="utf-8"
    )
    assert f"| INFO | {mcp_kapisi.OLAY_MCP_BASLANGIC} | ortam=test" in icerik
    assert (
        f"| INFO | {mcp_kapisi.OLAY_MCP_EL_SIKISMA} | istemci=defteruc-test 0 "
        f"protokol={ISTEMCI_PROTOKOL_SURUMU} yetenekler=[]"
    ) in icerik
    assert f"| INFO | {mcp_kapisi.OLAY_MCP_KAPANIS} |" in icerik
    for satir in sonuc.stdout_satirlari:
        assert satir.startswith("{"), satir


GIZLI_METIN = "SENTETIK-GIZLI IBAN TR00 0000 0000 0000 0000 00"
HATALI_SUNUCU_KOMUTU = (
    "import sys\n"
    "from defteruc import mcp_kapisi\n"
    "def patlat(ayarlar):\n"
    f"    raise ValueError({GIZLI_METIN!r})\n"
    "mcp_kapisi.sistem_durumu = patlat\n"
    "sys.exit(mcp_kapisi.main())\n"
)
"""Gerçek sunucu, araç gövdesi sentetik hassas içerikli hatayla değiştirilmiş."""

BEKLENEN_HATALI_SUNUCU_KOMUTU = (
    "import sys\n"
    "from defteruc import mcp_kapisi\n"
    "from mcp.server.mcpserver.exceptions import ToolError\n"
    "def patlat(ayarlar):\n"
    f"    raise ToolError({GIZLI_METIN!r})\n"
    "mcp_kapisi.sistem_durumu = patlat\n"
    "sys.exit(mcp_kapisi.main())\n"
)
"""Aynı sunucu, beklenen ToolError: SDK istisnasız INFO kaydıyla hata metnini loglar."""


def test_stdio_beklenen_arac_hatasi_metni_gunluge_gecmez(
    tmp_path: Path, test_koku: Path
) -> None:
    sonuc = _sunucuyla_konus(
        tmp_path, dict(os.environ), ILK_ISTEKLER, komut=BEKLENEN_HATALI_SUNUCU_KOMUTU
    )

    assert sonuc.cikis_kodu == 0, sonuc.stderr
    assert sonuc.yanitlar[3]["result"]["isError"] is True
    icerik = (test_koku / ay.LOG_DIZIN_ADI / gunluk.GUNLUK_DOSYA_ADI).read_text(
        encoding="utf-8"
    )
    # SDK: logger.info("Tool %r failed: %r", ad, str(exc)); yalnız şablon kalır.
    assert "| INFO | - | Tool %r failed: %r [parametreler gizlendi: str, str]" in icerik
    assert GIZLI_METIN not in icerik
    assert "Traceback" not in icerik
    assert "hata türü" not in icerik  # istisna kaydı yok, beklenen hata yolu
    assert GIZLI_METIN not in sonuc.stderr
    assert f"| INFO | {mcp_kapisi.OLAY_MCP_KAPANIS} |" in icerik


def test_stdio_arac_hatasi_gunluge_yalniz_turuyle_gecer(
    tmp_path: Path, test_koku: Path
) -> None:
    sonuc = _sunucuyla_konus(
        tmp_path, dict(os.environ), ILK_ISTEKLER, komut=HATALI_SUNUCU_KOMUTU
    )

    assert sonuc.cikis_kodu == 0, sonuc.stderr
    assert sonuc.yanitlar[3]["result"]["isError"] is True
    icerik = (test_koku / ay.LOG_DIZIN_ADI / gunluk.GUNLUK_DOSYA_ADI).read_text(
        encoding="utf-8"
    )
    # SDK araç istisnasını kendi türüyle sarar; dosyaya yalnız o tür düşer.
    assert (
        f"| ERROR | {gunluk.OLAY_YOKSA} | hata türü: "
        "mcp.server.mcpserver.exceptions.UnexpectedToolError"
    ) in icerik
    assert "ValueError" not in icerik
    assert GIZLI_METIN not in icerik
    assert "Traceback" not in icerik
    assert GIZLI_METIN not in sonuc.stderr
    assert "Traceback" not in sonuc.stderr
    assert f"| INFO | {mcp_kapisi.OLAY_MCP_KAPANIS} |" in icerik


def test_ayar_hatasinda_stdout_bos_stderr_aciklayici(tmp_path: Path) -> None:
    # Veri kökü verilmedi; test ortamı bunu zorunlu tutar.
    sonuc = _sunucuyu_calistir(tmp_path, {ay.ORTAM_DEGISKENI: "test"}, ILK_ISTEKLER)

    assert sonuc.returncode == 1
    assert sonuc.stdout == ""
    assert "DEFTERUC MCP kapısı başlatılamadı" in sonuc.stderr
    assert "Ayar hatası" in sonuc.stderr
    assert ay.VERI_KOKU_DEGISKENI in sonuc.stderr


# --- dördüncü inceleme (2026-09-24): el sıkışma günlüğü süzülür ----------------------


def test_stdio_istemci_metni_ve_yetenek_icerigi_gunluge_suzulerek_gecer(
    tmp_path: Path, test_koku: Path
) -> None:
    """İstemci adındaki satır sonu günlük satırı bozuyordu; deneysel yetenek
    içeriği aynen loga giriyordu. Gerçek stdio ile: kontrol karakteri '?'
    olur, uzunluk sınırlanır, yeteneklerin yalnız adları yazılır."""
    istekler = copy.deepcopy(ILK_ISTEKLER)
    istekler[0]["params"]["clientInfo"]["name"] = "client\nFORGED_LOG_LINE"
    istekler[0]["params"]["clientInfo"]["version"] = "1.0 " + "x" * 300
    istekler[0]["params"]["capabilities"] = {
        "experimental": {"custom": {"secret_test_marker": "CONFIDENTIAL_TEST_VALUE"}},
        "roots": {"listChanged": True},
    }

    sonuc = _sunucuyla_konus(tmp_path, dict(os.environ), istekler)

    assert sonuc.cikis_kodu == 0, sonuc.stderr
    icerik = (test_koku / ay.LOG_DIZIN_ADI / gunluk.GUNLUK_DOSYA_ADI).read_text(
        encoding="utf-8"
    )
    assert "\nFORGED_LOG_LINE" not in icerik
    assert "CONFIDENTIAL_TEST_VALUE" not in icerik
    assert "secret_test_marker" not in icerik
    satir = next(s for s in icerik.splitlines() if mcp_kapisi.OLAY_MCP_EL_SIKISMA in s)
    assert "istemci=client?FORGED_LOG_LINE 1.0 xxx" in satir
    assert "x" * 100 not in satir  # kısaltıldı
    assert "yetenekler=[experimental, roots]" in satir


@pytest.mark.parametrize(
    ("metin", "beklenen"),
    [
        ("defteruc-test", "defteruc-test"),
        ("a\nb\tc\x00d", "a?b?c?d"),
        ("x" * 70, "x" * 64 + "…"),
        ("", ""),
    ],
)
def test_gunluk_icin_suzme(metin: str, beklenen: str) -> None:
    assert mcp_kapisi.gunluk_icin_suz(metin) == beklenen
