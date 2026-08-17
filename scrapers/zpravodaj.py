#!/usr/bin/env python3
"""A2 — sběrač archivu Městského zpravodaje Mariánských Lázní.

Archiv na muml.cz je stránkovaný výpis souborů (7 stránek po 20 položkách,
celkem 122 čísel od 02/2016 do 08/2026). Odkaz na PDF má tvar

    /modules/file_storage/download.php?file=HASH%7CID

kde HASH (8 hex znaků) ani ID nejde odvodit — seznam se musí vždy sesbírat
ze stránky výpisu.

Autoritativní pro rok a měsíc je NADPIS položky ("Zpravodaj města 08/2026").
Název souboru se v archivu občas plete (číslo 02/2021 je nahrané jako
"ml zpravodaj - 2020 - unor.pdf"), takže slouží jen jako záloha.

Prázdninová dvojčísla ("07-08/2019") dostanou id podle prvního měsíce
a v indexu navíc pole `mesic_do`.

Spuštění:
    python3 scrapers/zpravodaj.py            # vše, s cache (hotová PDF přeskočí)
    python3 scrapers/zpravodaj.py --limit 5  # jen prvních 5 čísel (vývoj)
    python3 scrapers/zpravodaj.py --jen-index  # nestahuje PDF, jen výpis
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
from pathlib import Path

import requests
from selectolax.parser import HTMLParser

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import (  # noqa: E402
    DATA,
    UA,
    Log,
    ZdrojSelhal,
    fetch,
    pdf_na_text,
    pdf_pocet_stran,
    potrebuje_ocr,
    uloz,
)

ZAKLAD = "https://www.muml.cz"
ARCHIV = ZAKLAD + "/aktualne/zpravodaj-mesta/"

PDF_DIR = DATA / "zpravodaj" / "pdf"
TEXT_DIR = DATA / "zpravodaj" / "text"
INDEX = "zpravodaj/cisla.json"

# Kolik místa na disku si necháváme jako rezervu, než začneme stahovat další PDF.
# Největší čísla mají přes 100 MB, celý archiv je zhruba 1,7 GB.
REZERVA_B = 3 * 1024**3

MAX_STRANEK = 40  # pojistka proti nekonečné smyčce, reálně jich je 7


# --------------------------------------------------------------------------
# Výpis archivu
# --------------------------------------------------------------------------

def _cisla_z_nadpisu(nadpis: str) -> tuple[int, int, int | None] | None:
    """'Zpravodaj města 07-08/2019' -> (2019, 7, 8); '08/2026' -> (2026, 8, None)."""
    m = re.search(r"(\d{1,2})\s*(?:-\s*(\d{1,2}))?\s*/\s*(\d{4})", nadpis or "")
    if not m:
        return None
    od = int(m.group(1))
    do = int(m.group(2)) if m.group(2) else None
    rok = int(m.group(3))
    if not (1 <= od <= 12) or not (2000 <= rok <= 2100):
        return None
    return rok, od, do


def _parsuj_stranku(html: str) -> list[dict]:
    """Vytáhne z jedné stránky výpisu položky se souborem."""
    out: list[dict] = []
    for row in HTMLParser(html).css("div.files-list div.file-row"):
        a = row.css_first("h2 a")
        if a is None:
            continue
        href = (a.attributes.get("href") or "").strip()
        if "download.php" not in href:
            continue
        nadpis = a.text(strip=True)
        cisla = _cisla_z_nadpisu(nadpis)
        if cisla is None:
            continue  # do archivu se občas připlete jiný soubor než číslo zpravodaje
        rok, mesic, mesic_do = cisla

        jmeno = (a.attributes.get("download") or "").strip()
        detail = row.css_first("div.file-details")
        velikost = None
        if detail is not None:
            mv = re.search(r"Velikost:\s*([\d, ]+)\s*(MB|kB|B)", detail.text())
            if mv:
                hodnota = float(mv.group(1).replace(" ", "").replace(",", "."))
                velikost = int(hodnota * {"MB": 1024**2, "kB": 1024, "B": 1}[mv.group(2)])

        out.append({
            "id": f"{rok}-{mesic:02d}",
            "rok": rok,
            "mesic": mesic,
            "mesic_do": mesic_do,
            "nazev": nadpis,
            "url": ZAKLAD + href if href.startswith("/") else href,
            "soubor": f"data/zpravodaj/pdf/{rok}-{mesic:02d}.pdf",
            "pdf_nazev": jmeno,
            "velikost_b": velikost,
        })
    return out


def sesbirej_odkazy(log: Log, max_age: int = 3600) -> list[dict]:
    """Projde stránkovaný archiv a vrátí všechna čísla.

    Server na `?page=N` za posledním číslem vrací pořád tu samou poslední
    stránku, takže se končí ve chvíli, kdy stránka nepřinese nic nového.
    """
    nalezene: dict[str, dict] = {}
    for stranka in range(1, MAX_STRANEK + 1):
        url = f"{ARCHIV}?page={stranka}"
        polozky = _parsuj_stranku(fetch(url, cache_key=f"zpravodaj-vypis-{stranka}", max_age=max_age))
        if not polozky:
            break
        nove = [p for p in polozky if p["id"] not in nalezene]
        if not nove:
            break  # opakující se stránka = jsme za koncem výpisu
        for p in nove:
            nalezene[p["id"]] = p
        log.info(f"výpis strana {stranka}: {len(polozky)} položek, {len(nove)} nových")

    if not nalezene:
        raise ZdrojSelhal("Archiv zpravodaje nevrátil ani jedno číslo — změnila se struktura stránky?")

    return sorted(nalezene.values(), key=lambda z: (z["rok"], z["mesic"]), reverse=True)


# --------------------------------------------------------------------------
# Stahování PDF
# --------------------------------------------------------------------------

def volne_misto() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(str(DATA)).free


def stahni_pdf(zaznam: dict, log: Log, *, prepsat: bool = False) -> Path | None:
    """Stáhne jedno číslo do data/zpravodaj/pdf/. Vrací cestu, nebo None při selhání.

    Stahuje se proudově po blocích — některá čísla mají přes 100 MB a nemá
    smysl je držet celá v paměti ani v cache `fetch()` (ta by je zdvojila).
    """
    cil = PDF_DIR / f"{zaznam['id']}.pdf"
    cekana = zaznam.get("velikost_b")

    if cil.exists() and not prepsat:
        mam = cil.stat().st_size
        # Výpis uvádí velikost zaokrouhlenou na 2 desetinná místa, tolerance 2 %.
        if mam > 10_000 and (cekana is None or abs(mam - cekana) <= max(cekana * 0.02, 50_000)):
            return cil
        log.info(f"{zaznam['id']}: soubor na disku je useknutý ({mam} B), stahuji znovu")

    rezerva = REZERVA_B + (cekana or 120 * 1024**2)
    if volne_misto() < rezerva:
        raise ZdrojSelhal(
            f"Došlo místo na disku ({volne_misto() // 1024**2} MB volných) — "
            f"zpracuj a smaž stažená PDF, teprve pak pokračuj."
        )

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    tmp = cil.with_suffix(".pdf.tmp")
    hlavicky = {"User-Agent": UA, "Accept-Language": "cs,en;q=0.8", "Referer": ARCHIV}

    posledni: Exception | None = None
    for pokus in range(4):
        try:
            with requests.get(zaznam["url"], headers=hlavicky, timeout=300, stream=True) as r:
                if r.status_code == 429 or 500 <= r.status_code < 600:
                    raise ZdrojSelhal(f"HTTP {r.status_code}")
                r.raise_for_status()
                with tmp.open("wb") as f:
                    for blok in r.iter_content(chunk_size=1024 * 256):
                        f.write(blok)
            if tmp.stat().st_size < 10_000:
                raise ZdrojSelhal(f"stažený soubor má jen {tmp.stat().st_size} B")
            tmp.replace(cil)
            return cil
        except Exception as e:  # noqa: BLE001 — opakujeme na čemkoliv síťovém
            posledni = e
            tmp.unlink(missing_ok=True)
            if pokus < 3:
                time.sleep(2 ** (pokus + 1))

    log.chyba(f"{zaznam['id']}: stažení selhalo ({posledni})")
    return None


def popis_pdf(zaznam: dict, pdf: Path, log: Log) -> None:
    """Doplní do záznamu počet stran, hustotu textu a příznak OCR.

    Text se rovnou ukládá do data/zpravodaj/text/{id}.txt — pipeline pak
    nemusí PDF otevírat znovu a archiv přežije i smazání PDF kvůli místu.
    """
    zaznam["stran"] = pdf_pocet_stran(pdf)
    zaznam["velikost_b"] = pdf.stat().st_size
    try:
        text = pdf_na_text(pdf)
    except ZdrojSelhal as e:
        log.chyba(f"{zaznam['id']}: {e}")
        zaznam["stran"] = zaznam.get("stran", 0)
        zaznam["znaku"] = 0
        zaznam["ocr"] = True
        return

    zaznam["znaku"] = len(text)
    zaznam["ocr"] = potrebuje_ocr(text, zaznam["stran"])
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    (TEXT_DIR / f"{zaznam['id']}.txt").write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------
# Hlavní běh
# --------------------------------------------------------------------------

def hlavni(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Stáhne archiv Městského zpravodaje")
    ap.add_argument("--limit", type=int, default=0, help="zpracovat jen N nejnovějších čísel")
    ap.add_argument("--jen-index", action="store_true", help="jen sesbírat výpis, nestahovat PDF")
    ap.add_argument("--od", type=int, default=0, help="jen ročníky >= tomuto roku")
    ap.add_argument("--prepsat", action="store_true", help="stáhnout znovu i hotová PDF")
    args = ap.parse_args(argv)

    log = Log("zpravodaj")
    try:
        cisla = sesbirej_odkazy(log)
    except ZdrojSelhal as e:
        log.chyba(str(e))
        log.uzavri()
        return 1

    log.info(f"archiv obsahuje {len(cisla)} čísel", od=cisla[-1]["id"], do=cisla[0]["id"])

    # Předchozí běh: co už máme popsané, nemusíme dělat znovu.
    stary = {z["id"]: z for z in (nacti_index() or [])}

    vyber = [z for z in cisla if not args.od or z["rok"] >= args.od]
    if args.limit:
        vyber = vyber[: args.limit]

    for z in cisla:
        if z["id"] in stary:
            for klic in ("stran", "znaku", "ocr"):
                if klic in stary[z["id"]]:
                    z[klic] = stary[z["id"]][klic]

    if args.jen_index:
        uloz(INDEX, cisla)
        log.info(f"uložen index bez stahování: {len(cisla)} čísel")
        log.uzavri()
        return 0

    hotovo = 0
    for i, z in enumerate(vyber, 1):
        hotovy = z.get("stran") and (TEXT_DIR / f"{z['id']}.txt").exists()
        if hotovy and not args.prepsat:
            hotovo += 1
            continue
        try:
            pdf = stahni_pdf(z, log, prepsat=args.prepsat)
        except ZdrojSelhal as e:
            log.chyba(str(e))
            break  # došlo místo — dál nemá smysl pokračovat
        if pdf is None:
            continue
        popis_pdf(z, pdf, log)
        hotovo += 1
        log.pricti()
        log.info(
            f"[{i}/{len(vyber)}] {z['id']}: {z['stran']} stran, "
            f"{z['velikost_b'] // 1024**2} MB, {z['znaku']} znaků"
            + (" — SKEN, potřebuje OCR" if z["ocr"] else "")
        )
        # Průběžné ukládání indexu: dávka běží dlouho, práce se nesmí ztratit.
        if i % 5 == 0 or i == len(vyber):
            uloz(INDEX, cisla)
        time.sleep(0.5)  # šetrné tempo vůči serveru města

    uloz(INDEX, cisla)
    skenu = sum(1 for z in cisla if z.get("ocr"))
    log.info(f"hotovo {hotovo}/{len(vyber)} čísel, skenů bez textové vrstvy: {skenu}")
    log.uzavri()
    return 0


def nacti_index() -> list[dict] | None:
    from lib.core import nacti
    return nacti(INDEX)


if __name__ == "__main__":
    raise SystemExit(hlavni())
