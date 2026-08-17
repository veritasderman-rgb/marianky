"""Záznamy jednání zastupitelstva z YouTube.

Město streamuje jednání na kanál @mestomarianskelazne a archivuje je
v playlistu. Ověřeno 17. 8. 2026: playlist obsahuje 94 záznamů, jednání
trvají 2 až 5 hodin a v názvu nesou pořadové číslo i datum — díky tomu
jdou spárovat s usneseními ze stejného dne.

POZOR NA PROSTŘEDÍ: YouTube omezuje sdílené IP adresy. Z kontejneru, ve
kterém tenhle projekt vznikal, vracelo stahování jednotlivých videí
HTTP 429, zatímco výpis playlistu procházel. Skript proto rozlišuje
"video nemá titulky" od "YouTube nás odmítl" — druhé je chyba prostředí,
ne vlastnost zdroje, a řeší se spuštěním z vlastní sítě, ne přepsáním kódu.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import DATA, Log, ZdrojSelhal, nacti, parse_datum, uloz  # noqa: E402

PLAYLIST = "https://www.youtube.com/playlist?list=PL7kw9cr29vwKjQdYoyE01iAVIXeM0iRcV"
KANAL = "https://www.youtube.com/@mestomarianskelazne"

# yt-dlp od jisté verze vyžaduje JS runtime; v prostředí je Node.
YTDLP_ZAKLAD = ["yt-dlp", "--js-runtimes", "node", "--no-warnings"]


class YoutubeOdmitl(ZdrojSelhal):
    """YouTube odmítl požadavek (429 / bot check). Chyba prostředí, ne zdroje."""


def _spust(args: list[str], timeout: int = 300) -> str:
    r = subprocess.run(YTDLP_ZAKLAD + args, capture_output=True, timeout=timeout)
    out = r.stdout.decode("utf-8", errors="replace")
    err = r.stderr.decode("utf-8", errors="replace")
    if "429" in err or "Too Many Requests" in err or "Sign in to confirm" in err:
        raise YoutubeOdmitl(
            "YouTube odmítl požadavek (429 / kontrola robota). "
            "Spusť z vlastní sítě, nebo předej cookies přes --cookies-from-browser."
        )
    if r.returncode != 0 and not out.strip():
        raise ZdrojSelhal(f"yt-dlp selhal: {err[:300]}")
    return out


def seznam_zaznamu() -> list[dict]:
    """Vypíše záznamy v playlistu. Tenhle endpoint prochází i tam, kde
    stahování jednotlivých videí naráží na 429."""
    out = _spust([
        "--flat-playlist",
        "--print", "%(id)s\t%(duration)s\t%(title)s",
        PLAYLIST,
    ])

    zaznamy = []
    for radek in out.strip().splitlines():
        casti = radek.split("\t")
        if len(casti) < 3:
            continue
        vid, trvani, nazev = casti[0], casti[1], casti[2]

        # "28. mimořádné jednání zastupitelstva města Mariánské Lázně (20.07.2026)"
        datum = parse_datum(nazev)
        m = re.match(r"\s*(\d+)\.\s", nazev)
        cj = int(m.group(1)) if m else None

        zaznamy.append({
            "video_id": vid,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "nazev": nazev,
            "datum": datum,
            "cj": cj,
            "mimoradne": "mimořádn" in nazev.lower(),
            "trvani_s": int(float(trvani)) if trvani and trvani != "NA" else None,
        })

    # Krátké klipy nejsou jednání — u 17. jednání je vedle 3,5h záznamu
    # i 25sekundový útržek. Filtrujeme, ale nezahazujeme tiše.
    dlouhe = [z for z in zaznamy if (z["trvani_s"] or 0) >= 600]
    kratke = [z for z in zaznamy if (z["trvani_s"] or 0) < 600]
    for z in kratke:
        print(f"  přeskočeno (kratší než 10 min): {z['nazev']}")

    return dlouhe


def stahni_titulky(video_id: str, cil: Path) -> dict:
    """Stáhne titulky. Nejdřív ruční, pak automatické.

    Automatické titulky jsou řádově levnější než přepis Whisperem: jsou
    hotové, stáhnou se za vteřinu a u 350 hodin záznamů je to rozdíl mezi
    odpolednem a týdnem strojového času. Whisper je záložní cesta.
    """
    cil.mkdir(parents=True, exist_ok=True)
    sablona = str(cil / f"{video_id}.%(ext)s")

    for rezim, prepinac in (("rucni", "--write-subs"), ("automaticke", "--write-auto-subs")):
        _spust([
            prepinac, "--skip-download",
            "--sub-langs", "cs,cs-CZ,cs-orig",
            "--sub-format", "vtt",
            "-o", sablona,
            f"https://www.youtube.com/watch?v={video_id}",
        ])
        soubory = sorted(cil.glob(f"{video_id}*.vtt"))
        if soubory:
            return {"zdroj": rezim, "soubor": str(soubory[0])}

    return {"zdroj": None, "soubor": None}


def main() -> None:
    log = Log("zaznamy")
    try:
        zaznamy = seznam_zaznamu()
    except YoutubeOdmitl as e:
        log.chyba(str(e))
        log.uzavri()
        raise SystemExit(2)

    log.info("nalezeno záznamů", pocet=len(zaznamy))

    # Spárování s usneseními zastupitelstva podle data jednání.
    sparovano = 0
    for z in zaznamy:
        if not z["datum"]:
            continue
        rok = z["datum"][:4]
        adresar = DATA / "usneseni" / "zastupitelstvo" / rok
        if adresar.exists():
            for soubor in adresar.glob("*.json"):
                data = nacti(soubor)
                if data and data.get("datum") == z["datum"]:
                    z["usneseni"] = str(soubor.relative_to(DATA))
                    sparovano += 1
                    break

    log.info("spárováno s usneseními", pocet=sparovano)
    uloz("zaznamy/index.json", zaznamy)
    log.pricti(len(zaznamy))
    log.uzavri()


if __name__ == "__main__":
    main()
