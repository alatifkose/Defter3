from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

PROJE_KOKU = Path(__file__).resolve().parent.parent

type Calistirici = Callable[[Sequence[str], Path], int]


@dataclass(frozen=True, slots=True)
class Adim:
    ad: str
    komut: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AdimSonucu:
    adim: Adim
    cikis_kodu: int | None
    aciklama: str = ""

    @property
    def basarili(self) -> bool:
        return self.cikis_kodu == 0


def adimlar(python: str = sys.executable) -> tuple[Adim, ...]:
    return (
        Adim("Ruff biçim kontrolü", (python, "-m", "ruff", "format", "--check", ".")),
        Adim("Ruff statik kontrolü", (python, "-m", "ruff", "check", ".")),
        Adim("Pyright", (python, "-m", "pyright")),
        Adim("pytest", (python, "-m", "pytest")),
    )


def alt_sureci_calistir(komut: Sequence[str], kok: Path) -> int:
    return subprocess.run(list(komut), cwd=kok, check=False).returncode


def adimi_calistir(adim: Adim, kok: Path, calistirici: Calistirici) -> AdimSonucu:
    print(f"\n=== {adim.ad} ===", flush=True)
    print("$ " + " ".join(adim.komut), flush=True)
    try:
        kod = calistirici(adim.komut, kok)
    except (FileNotFoundError, PermissionError) as hata:
        sonuc = AdimSonucu(adim, None, f"araç başlatılamadı: {hata}")
    else:
        sonuc = AdimSonucu(adim, kod)
    print(f"--- {adim.ad}: {_etiket(sonuc)}", flush=True)
    return sonuc


def hepsini_calistir(
    adimlar_: Sequence[Adim],
    kok: Path,
    calistirici: Calistirici = alt_sureci_calistir,
) -> int:
    sonuclar = [adimi_calistir(adim, kok, calistirici) for adim in adimlar_]

    print("\n=== Toplu sonuç ===", flush=True)
    for sonuc in sonuclar:
        print(f"{_etiket(sonuc):<6} {sonuc.adim.ad}", flush=True)

    basarisiz = [s for s in sonuclar if not s.basarili]
    if basarisiz:
        print(f"\n{len(basarisiz)}/{len(sonuclar)} kontrol başarısız.", flush=True)
        return 1
    print(f"\n{len(sonuclar)}/{len(sonuclar)} kontrol başarılı.", flush=True)
    return 0


def _etiket(sonuc: AdimSonucu) -> str:
    if sonuc.basarili:
        return "[OK]"
    if sonuc.cikis_kodu is None:
        return f"[YOK] {sonuc.aciklama}"
    return f"[HATA] çıkış kodu {sonuc.cikis_kodu}"


def main() -> int:
    print(f"Proje kökü: {PROJE_KOKU}", flush=True)
    return hepsini_calistir(adimlar(), PROJE_KOKU)


if __name__ == "__main__":
    sys.exit(main())
