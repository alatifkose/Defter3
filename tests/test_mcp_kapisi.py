"""MCP kapısı testleri.

Sunucu ayrı bir süreçte, ``test`` ortamında ve geçici veri köküyle başlatılır.
İstemci taklidi yoktur: JSON-RPC mesajları ham satırlar olarak stdin'e
yazılır, her isteğin yanıtı stdout'tan okunduktan sonra sıradakine geçilir;
stdin en sonda kapatılır. Böylece stdout'un protokol dışında hiçbir şey
taşımadığı da sınanır.
"""

import dataclasses
import hashlib
import json
import logging
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest

from defteriki import ayarlar as ay
from defteriki import gunluk, mcp_kapisi

DEFTERIKI_DEGISKENLERI = (
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
            "clientInfo": {"name": "defteriki-test", "version": "0"},
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
    for degisken in DEFTERIKI_DEGISKENLERI:
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
    assert durum.sema_surumu == mcp_kapisi.SEMA_SURUMU_YOK
    assert durum.yetenekler == mcp_kapisi.ARACLAR
    assert durum.uygulama_surumu not in ("", mcp_kapisi.SURUM_BILINMIYOR)


def test_sistem_durumu_yol_ve_ortam_degiskeni_icermez(test_koku: Path) -> None:
    durum = mcp_kapisi.sistem_durumu(ay.ayarlari_yukle())

    metin = json.dumps(dataclasses.asdict(durum), ensure_ascii=False)

    assert str(test_koku) not in metin
    assert str(test_koku.parent) not in metin
    assert "DEFTERIKI_" not in metin


def test_sunucu_iki_araci_sunar(test_koku: Path) -> None:
    sunucu = mcp_kapisi.sunucu_kur(ay.ayarlari_yukle())

    araclar = anyio.run(sunucu.list_tools)

    assert [arac.name for arac in araclar] == mcp_kapisi.ARACLAR
    assert sunucu.name == mcp_kapisi.SUNUCU_ADI
    durum, dene = araclar
    assert durum.output_schema is not None
    assert set(durum.output_schema["required"]) == {
        "uygulama_surumu",
        "ortam",
        "sema_surumu",
        "yetenekler",
    }
    assert dene.input_schema["required"] == ["yol"]
    assert dene.output_schema is not None
    assert set(dene.output_schema["required"]) == {
        "sonuc",
        "gerekce",
        "sha256",
        "boyut_bayt",
    }


def test_import_sunucu_kurmaz_ve_dosya_olusturmaz(tmp_path: Path) -> None:
    assert not gunluk.kurulu()
    assert list(tmp_path.iterdir()) == []


# --- dosya_dene (süreç içi) ------------------------------------------------


@pytest.fixture
def gelen(test_koku: Path) -> Path:
    dizin = test_koku / ay.GELEN_DIZIN_ADI
    dizin.mkdir(parents=True)
    return dizin


def _yaz(dosya: Path, icerik: bytes) -> Path:
    dosya.parent.mkdir(parents=True, exist_ok=True)
    dosya.write_bytes(icerik)
    return dosya


def test_dosya_dene_izinli_dosyayi_akisla_ozetler(gelen: Path) -> None:
    icerik = bytes(range(256)) * 5000  # 1,28 MB: birden fazla okuma parçası
    dosya = _yaz(gelen / "ekstre.pdf", icerik)

    sonuc = mcp_kapisi.dosya_dene(str(dosya), gelen)

    assert sonuc == mcp_kapisi.DosyaDenemesi(
        sonuc=mcp_kapisi.SONUC_OKUNDU,
        gerekce=mcp_kapisi.GEREKCE_YOK,
        sha256=hashlib.sha256(icerik).hexdigest(),
        boyut_bayt=len(icerik),
    )


def test_dosya_dene_alt_dizindeki_bos_dosyayi_okur(gelen: Path) -> None:
    dosya = _yaz(gelen / "2026" / "bos.txt", b"")

    sonuc = mcp_kapisi.dosya_dene(str(dosya), gelen)

    assert sonuc.sonuc == mcp_kapisi.SONUC_OKUNDU
    assert sonuc.sha256 == hashlib.sha256(b"").hexdigest()
    assert sonuc.boyut_bayt == 0


def test_dosya_dene_yaniti_yol_icermez(gelen: Path) -> None:
    dosya = _yaz(gelen / "gizli.pdf", b"x")

    sonuc = mcp_kapisi.dosya_dene(str(dosya), gelen)

    metin = json.dumps(dataclasses.asdict(sonuc), ensure_ascii=False)
    assert "gizli" not in metin
    assert str(gelen) not in metin


def test_dosya_dene_dizin_disini_reddeder_ve_uyari_yazar(
    tmp_path: Path, gelen: Path, caplog: pytest.LogCaptureFixture
) -> None:
    disari = _yaz(tmp_path / "disari" / "sir.txt", b"gizli")
    caplog.set_level(logging.INFO, logger=gunluk.GUNLUK_ADI)

    sonuc = mcp_kapisi.dosya_dene(str(disari), gelen)

    assert sonuc == mcp_kapisi.DosyaDenemesi(
        sonuc=mcp_kapisi.SONUC_REDDEDILDI,
        gerekce=mcp_kapisi.GEREKCE_DIZIN_DISI,
        sha256="",
        boyut_bayt=0,
    )
    (kayit,) = caplog.records
    assert kayit.levelno == logging.WARNING
    assert kayit.__dict__["olay"] == mcp_kapisi.OLAY_MCP_DOSYA_DENEME
    assert "sir" not in kayit.getMessage()
    assert str(tmp_path) not in kayit.getMessage()


def test_dosya_dene_ust_dizin_parcasini_reddeder(tmp_path: Path, gelen: Path) -> None:
    _yaz(tmp_path / "disari" / "sir.txt", b"gizli")
    kacan = gelen / ".." / "disari" / "sir.txt"

    sonuc = mcp_kapisi.dosya_dene(str(kacan), gelen)

    assert sonuc.sonuc == mcp_kapisi.SONUC_REDDEDILDI
    assert sonuc.gerekce == mcp_kapisi.GEREKCE_UST_DIZIN


@pytest.mark.parametrize("yol", ["", "   ", "ekstre.pdf", "./ekstre.pdf"])
def test_dosya_dene_goreli_yolu_reddeder(gelen: Path, yol: str) -> None:
    _yaz(gelen / "ekstre.pdf", b"x")

    sonuc = mcp_kapisi.dosya_dene(yol, gelen)

    assert sonuc.gerekce == mcp_kapisi.GEREKCE_MUTLAK_DEGIL


def test_dosya_dene_olmayan_dosyayi_reddeder(gelen: Path) -> None:
    sonuc = mcp_kapisi.dosya_dene(str(gelen / "yok.pdf"), gelen)

    assert sonuc.gerekce == mcp_kapisi.GEREKCE_BULUNAMADI


def test_dosya_dene_dizini_reddeder(gelen: Path) -> None:
    (gelen / "klasor").mkdir()

    sonuc = mcp_kapisi.dosya_dene(str(gelen / "klasor"), gelen)

    assert sonuc.gerekce == mcp_kapisi.GEREKCE_DOSYA_DEGIL


def test_dosya_dene_okuma_hatasini_bildirir(
    gelen: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dosya = _yaz(gelen / "kilitli.pdf", b"x")

    def acilamaz(self: Path, *args: object, **kwargs: object) -> None:
        raise PermissionError(13, "Erişim reddedildi")

    monkeypatch.setattr(Path, "open", acilamaz)

    sonuc = mcp_kapisi.dosya_dene(str(dosya), gelen)

    assert sonuc.gerekce == mcp_kapisi.GEREKCE_OKUNAMADI


def _baglanti_kur(baglanti: Path, hedef: Path) -> None:
    try:
        baglanti.symlink_to(hedef)
    except (OSError, NotImplementedError) as hata:
        pytest.skip(f"simgesel bağlantı oluşturulamadı: {type(hata).__name__}")


def test_dosya_dene_disariya_giden_baglantiyi_reddeder(
    tmp_path: Path, gelen: Path
) -> None:
    hedef = _yaz(tmp_path / "disari" / "sir.txt", b"gizli")
    baglanti = gelen / "masum.txt"
    _baglanti_kur(baglanti, hedef)

    sonuc = mcp_kapisi.dosya_dene(str(baglanti), gelen)

    assert sonuc.sonuc == mcp_kapisi.SONUC_REDDEDILDI
    assert sonuc.gerekce == mcp_kapisi.GEREKCE_DIZIN_DISI


def test_dosya_dene_icerideki_baglantiyi_da_reddeder(gelen: Path) -> None:
    hedef = _yaz(gelen / "gercek.txt", b"icerik")
    baglanti = gelen / "kisayol.txt"
    _baglanti_kur(baglanti, hedef)

    sonuc = mcp_kapisi.dosya_dene(str(baglanti), gelen)

    assert sonuc.gerekce == mcp_kapisi.GEREKCE_BAGLANTI


def test_dosya_dene_okumayi_gunluge_goreli_adla_yazar(
    gelen: Path, caplog: pytest.LogCaptureFixture
) -> None:
    dosya = _yaz(gelen / "2026" / "ekstre.pdf", b"abc")
    caplog.set_level(logging.INFO, logger=gunluk.GUNLUK_ADI)

    mcp_kapisi.dosya_dene(str(dosya), gelen)

    (kayit,) = caplog.records
    assert kayit.levelno == logging.INFO
    assert kayit.getMessage() == "sonuc=okundu dosya=2026/ekstre.pdf boyut=3"


# --- ayrı süreçte stdio ----------------------------------------------------

SUNUCU_KOMUTU = "import sys; from defteriki.mcp_kapisi import main; sys.exit(main())"
BEKLEME_SANIYE = 60


def _cevre(cevre: dict[str, str]) -> dict[str, str]:
    temiz = {k: v for k, v in os.environ.items() if not k.startswith("DEFTERIKI_")}
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
    cwd: Path, cevre: dict[str, str], mesajlar: tuple[dict[str, Any], ...]
) -> Konusma:
    """Mesajları sırayla gönderir; istek olanların yanıtını bekler, sonra kapatır."""
    surec = subprocess.Popen(
        [sys.executable, "-c", SUNUCU_KOMUTU],
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
    assert [arac["name"] for arac in araclar] == mcp_kapisi.ARACLAR
    assert araclar[0]["inputSchema"]["properties"] == {}
    assert list(araclar[1]["inputSchema"]["properties"]) == ["yol"]

    cagri = yanitlar[3]["result"]
    assert not cagri.get("isError", False)
    assert cagri["structuredContent"] == {
        "uygulama_surumu": mcp_kapisi.uygulama_surumu(),
        "ortam": "test",
        "sema_surumu": mcp_kapisi.SEMA_SURUMU_YOK,
        "yetenekler": mcp_kapisi.ARACLAR,
    }
    assert all(str(test_koku) not in satir for satir in sonuc.stdout_satirlari)
    assert not any(calisma.iterdir())


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
        f"| INFO | {mcp_kapisi.OLAY_MCP_EL_SIKISMA} | istemci=defteriki-test 0 "
        f"protokol={ISTEMCI_PROTOKOL_SURUMU} yetenekler={{}}"
    ) in icerik
    assert f"| INFO | {mcp_kapisi.OLAY_MCP_KAPANIS} |" in icerik
    for satir in sonuc.stdout_satirlari:
        assert satir.startswith("{"), satir


def test_stdio_uzerinden_dosya_dene_okur_ve_reddeder(
    tmp_path: Path, test_koku: Path
) -> None:
    icerik = b"%PDF-1.4 sentetik deneme"
    dosya = _yaz(test_koku / ay.GELEN_DIZIN_ADI / "deneme.pdf", icerik)
    disari = _yaz(tmp_path / "disari" / "sir.pdf", b"gizli")
    istekler = ILK_ISTEKLER[:2] + (
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": mcp_kapisi.ARAC_DOSYA_DENE,
                "arguments": {"yol": str(dosya)},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": mcp_kapisi.ARAC_DOSYA_DENE,
                "arguments": {"yol": str(disari)},
            },
        },
    )

    sonuc = _sunucuyla_konus(tmp_path, dict(os.environ), istekler)

    assert sonuc.cikis_kodu == 0, sonuc.stderr
    yanitlar = sonuc.yanitlar
    okunan = yanitlar[4]["result"]
    assert not okunan.get("isError", False)
    assert okunan["structuredContent"] == {
        "sonuc": mcp_kapisi.SONUC_OKUNDU,
        "gerekce": "",
        "sha256": hashlib.sha256(icerik).hexdigest(),
        "boyut_bayt": len(icerik),
    }
    reddedilen = yanitlar[5]["result"]
    assert not reddedilen.get("isError", False)
    assert reddedilen["structuredContent"]["sonuc"] == mcp_kapisi.SONUC_REDDEDILDI
    assert reddedilen["structuredContent"]["gerekce"] == mcp_kapisi.GEREKCE_DIZIN_DISI
    for satir in sonuc.stdout_satirlari:
        assert "gizli" not in satir and "sentetik" not in satir

    icerik_gunluk = (test_koku / ay.LOG_DIZIN_ADI / gunluk.GUNLUK_DOSYA_ADI).read_text(
        encoding="utf-8"
    )
    assert (
        f"| INFO | {mcp_kapisi.OLAY_MCP_DOSYA_DENEME} | sonuc=okundu "
        f"dosya=deneme.pdf boyut={len(icerik)}"
    ) in icerik_gunluk
    assert (
        f"| WARNING | {mcp_kapisi.OLAY_MCP_DOSYA_DENEME} | sonuc=reddedildi "
        f"gerekce={mcp_kapisi.GEREKCE_DIZIN_DISI}"
    ) in icerik_gunluk
    assert str(tmp_path) not in icerik_gunluk


def test_ayar_hatasinda_stdout_bos_stderr_aciklayici(tmp_path: Path) -> None:
    # Veri kökü verilmedi; test ortamı bunu zorunlu tutar.
    sonuc = _sunucuyu_calistir(tmp_path, {ay.ORTAM_DEGISKENI: "test"}, ILK_ISTEKLER)

    assert sonuc.returncode == 1
    assert sonuc.stdout == ""
    assert "DEFTERIKI MCP kapısı başlatılamadı" in sonuc.stderr
    assert "Ayar hatası" in sonuc.stderr
    assert ay.VERI_KOKU_DEGISKENI in sonuc.stderr
