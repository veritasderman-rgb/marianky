#!/usr/bin/env python3
"""Sbírka listin obchodního rejstříku — závěrky městských společností.

Obchodní společnosti města (TDS, Lázeňské lesy, Infocentrum…) nejsou
vybrané účetní jednotky, takže v Monitoru státní pokladny nemají rozvahu
ani výsledovku — jejich hospodaření je vidět jen ve sbírce listin
obchodního rejstříku (`or.justice.cz`), kam mají ze zákona ukládat účetní
závěrky.

Co tenhle sběrač dělá — a co záměrně NE:

* **Dělá:** pro každou společnost stáhne seznam listin ve sbírce a rozebere
  ho na typy a roky („účetní závěrka [2023]", „výroční zpráva [2023]"…).
  Výstupem je matice „firma × rok: závěrka založena / chybí" — tedy
  odpověď na otázku, ZDA firma hospodaření zveřejňuje a za které roky.
* **Nedělá:** nečte čísla z PDF závěrek. Závěrky jsou skeny i strojová
  PDF v tuctu různých šablon; deterministicky se z nich čísla vytáhnout
  nedají a model je parsovat nesmí (zásada „scraping dělá kód"). Odkaz na
  listinu ve výstupu je, čtenář se k číslům prokliká.

Jak se hledá subjekt: `rejstrik-$firma?ico=…` vrátí výsledky s odkazem
`vypis-sl-firma?subjektId=…`. Ověřuje se, že stránka sbírky listin nese
IČO z konfigurace — kdyby vyhledávání vrátilo jiný subjekt, sběr spadne,
místo aby tiše přiřadil cizí listiny.

Spuštění:
    python3 scrapers/zaverky.py
"""
from __future__ import annotations

import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from selectolax.parser import HTMLParser

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import UA, Log, ZdrojSelhal, sledovane_subjekty, uloz  # noqa: E402

ZAKLAD = "https://or.justice.cz/ias/ui"
VYSTUP = "zaverky"

# Druhy listin, které vypovídají o hospodaření. Ostatní (společenská
# smlouva, podpisové vzory…) se počítají jen do celkového počtu.
DRUHY_HOSPODARENI = (
    "účetní závěrka",
    "výroční zpráva",
    "zpráva auditora",
    "zpráva o vztazích",
)


def _get(url: str, pokusu: int = 4) -> str:
    posledni: Exception | None = None
    for pokus in range(pokusu):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
            r.raise_for_status()
            return r.text
        except Exception as e:  # noqa: BLE001
            posledni = e
            time.sleep(2 ** pokus)
    raise ZdrojSelhal(f"{url}: {posledni}")


def najdi_subjekt(ico: str) -> int:
    """IČO → subjektId v aplikaci rejstříku."""
    html = _get(f"{ZAKLAD}/rejstrik-$firma?ico={ico}&jenPlatne=VSECHNY")
    m = re.search(r"vypis-sl-firma\?subjektId=(\d+)", html)
    if not m:
        raise ZdrojSelhal(f"IČO {ico}: rejstřík nevrátil odkaz na sbírku listin")
    return int(m.group(1))


def _text(uzel) -> str:
    return re.sub(r"\s+", " ", uzel.text(separator=" ")).strip()


def _typy_listiny(bunka) -> list[dict]:
    """„účetní závěrka [2023], zpráva auditora [2023]“ → strukturovaně.

    Rok v hranatých závorkách je rok, KE KTERÉMU se listina vztahuje —
    ne rok založení. Rozsah „[2010-2012]“ se rozepíše na jednotlivé roky.

    Závorka s rokem NEMUSÍ stát na konci: soudy zapisují i „účetní
    závěrka [2023] Rozvaha []“ (část závěrky, prázdná závorka na konci).
    Druh je proto text PŘED první závorkou a roky se sbírají ze VŠECH
    závorek v kusu — kdo by chytal jen závorku na konci, přišel by
    o většinu závěrek TDS.
    """
    out: list[dict] = []
    text = _text(bunka)
    for kus in re.split(r",\s*", text):
        kus = kus.strip()
        if not kus:
            continue
        pred = re.match(r"(.+?)\s*\[", kus)
        druh = (pred.group(1) if pred else kus).strip().lower()
        roky: list[int] = []
        for zavorka in re.findall(r"\[([0-9,\s\-–]*)\]", kus):
            for cast in re.split(r"[,\s]+", zavorka):
                r2 = re.match(r"(\d{4})[\-–](\d{4})$", cast)
                if r2:
                    roky.extend(range(int(r2.group(1)), int(r2.group(2)) + 1))
                elif re.match(r"\d{4}$", cast):
                    roky.append(int(cast))
        out.append({"druh": druh, "roky": sorted(set(roky))})
    return out


def listiny_subjektu(subjekt_id: int, ico: str) -> list[dict]:
    html = _get(f"{ZAKLAD}/vypis-sl-firma?subjektId={subjekt_id}")
    strom = HTMLParser(html)

    # Ověření identity: stránka nese IČO subjektu po trojicích („252 13 261“).
    bez_mezer = re.sub(r"[\s ]+", "", strom.body.text())
    if ico not in bez_mezer:
        raise ZdrojSelhal(
            f"sbírka listin subjektu {subjekt_id} nenese IČO {ico} — "
            "vyhledávání vrátilo jiný subjekt")

    out: list[dict] = []
    for radek in strom.css("tr"):
        bunky = radek.css("td")
        if len(bunky) < 6:
            continue
        cislo = _text(bunky[0])
        # Řádky listin poznáme podle čísla ve tvaru „C 9012/SL111/KSPL“.
        if "/SL" not in cislo:
            continue
        odkaz = radek.css_first("a[href*='vypis-sl-detail']")
        out.append({
            "cislo": cislo,
            "typy": _typy_listiny(bunky[1]),
            "vznik": _text(bunky[2]) or None,
            "doslo_na_soud": _text(bunky[3]) or None,
            "zalozeno": _text(bunky[4]) or None,
            "stranek": int(_text(bunky[5])) if _text(bunky[5]).isdigit() else None,
            "url": (f"{ZAKLAD}/" + odkaz.attributes.get("href", "").lstrip("./")
                    .replace("&amp;", "&")) if odkaz else None,
        })
    return out


def roky_zaverek(listiny: list[dict]) -> dict[str, list[int]]:
    """Za které roky jsou ve sbírce listiny o hospodaření."""
    out: dict[str, set[int]] = {}
    for listina in listiny:
        for typ in listina["typy"]:
            # Prefixem, ne rovností: druh bývá „účetní závěrka“ i s dovětkem
            # části („účetní závěrka [2023] Rozvaha“ → druh „účetní závěrka“).
            zaklad = next((d for d in DRUHY_HOSPODARENI
                           if typ["druh"].startswith(d)), None)
            if zaklad:
                out.setdefault(zaklad, set()).update(typ["roky"])
    return {druh: sorted(roky) for druh, roky in sorted(out.items())}


def main() -> int:
    log = Log("zaverky")
    subjekty = [s for s in sledovane_subjekty()
                if s.get("typ") in ("obchodni_spolecnost", "ops")]
    if not subjekty:
        log.chyba("v config/subjekty.json není žádná obchodní společnost")
        log.uzavri()
        return 1

    firmy = []
    selhani = 0
    for s in subjekty:
        try:
            subjekt_id = najdi_subjekt(s["ico"])
            listiny = listiny_subjektu(subjekt_id, s["ico"])
            zaverky = roky_zaverek(listiny)
            roky_ucetni = zaverky.get("účetní závěrka", [])
            firmy.append({
                "ico": s["ico"],
                "nazev": s["nazev"],
                "typ": s.get("typ"),
                "vlastnictvi": s.get("vlastnictvi"),
                "subjekt_id": subjekt_id,
                "sbirka_listin_url": f"{ZAKLAD}/vypis-sl-firma?subjektId={subjekt_id}",
                "listin_celkem": len(listiny),
                "roky_s_ucetni_zaverkou": roky_ucetni,
                "posledni_zaverka": roky_ucetni[-1] if roky_ucetni else None,
                "roky_podle_druhu": zaverky,
                "listiny": listiny,
            })
            log.pricti()
            log.info(f"{s['nazev']}: {len(listiny)} listin, "
                     f"závěrky {roky_ucetni[0] if roky_ucetni else '—'}"
                     f"–{roky_ucetni[-1] if roky_ucetni else '—'}")
        except ZdrojSelhal as e:
            selhani += 1
            log.chyba(f"{s['nazev']}: {e}")
            firmy.append({
                "ico": s["ico"], "nazev": s["nazev"], "typ": s.get("typ"),
                "vlastnictvi": s.get("vlastnictvi"),
                "stav": "chybi", "duvod": str(e),
            })
        time.sleep(2)  # ohleduplné tempo vůči or.justice.cz

    uloz(f"{VYSTUP}/listiny.json", {
        "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "zdroj": "sbírka listin obchodního rejstříku, or.justice.cz",
        "metodika": [
            "Rok v hranaté závorce u listiny je rok, KE KTERÉMU se závěrka "
            "vztahuje, ne rok založení do sbírky.",
            "Sleduje se, ZDA je závěrka založena — čísla z PDF se nečtou: "
            "závěrky jsou skeny i strojová PDF v mnoha šablonách a "
            "deterministický parser na ně neexistuje. Odkaz na listinu je "
            "u každé firmy, čtenář se k číslům prokliká.",
            "Chybějící rok znamená, že závěrka za něj ve sbírce NENÍ — "
            "povinnost ji uložit přitom firmám ukládá zákon o účetnictví.",
            "Nemocnice Mariánské Lázně s.r.o. už městu nepatří; je tu pro "
            "kontext a nese `vlastnictvi: mimo_mesto`.",
        ],
        "firem": len(firmy),
        "selhani": selhani,
        "firmy": firmy,
    })

    vysledek = log.uzavri()
    return 0 if vysledek["uspech"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
