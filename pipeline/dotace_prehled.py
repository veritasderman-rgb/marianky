#!/usr/bin/env python3
"""Dotace pro město a jeho organizace — přehled ze dvou zdrojů Hlídače.

Vstupy (oba sbírá `scrapers/hlidac.py`):

* `data/penize/statistiky.json` — souhrnné řady `dotace_po_letech_*`
  ze statistik subjektu na Hlídači. Spolehlivé roční součty, ale jen
  za poslední roky (okno Hlídače, dnes od 2023).
* `data/penize/dotace/{ico}.json` — jednotlivé dotace (DotInfo/CEDR).
  Je to VÝBĚR velkých dotací, ne úplný registr — a u části záznamů chybí
  rok. Slouží jako rozpis „co konkrétně", ne jako základ součtů.

Ta dvojkolejnost je záměr: součty se berou z řady, která je úplná ve svém
okně, a jednotlivosti z rozpisu, který je neúplný, ale konkrétní. Sečíst
rozpis po letech by vyrobilo řadu, která je zároveň neúplná i bez oken —
tedy nejhorší z obojího.

Výstup: `data/penize/agregace/dotace.json`.

Spuštění:
    python3 -m pipeline.dotace_prehled
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import DATA, Log, nacti, sledovane_subjekty, uloz  # noqa: E402

VYSTUP = "penize/agregace/dotace.json"


def main() -> int:
    log = Log("dotace_prehled")
    subjekty = {s["ico"]: s for s in sledovane_subjekty()}

    stat = nacti("penize/statistiky.json") or {}
    po_letech_mesto = stat.get("dotace_po_letech_mesto") or []
    po_letech_holding = stat.get("dotace_po_letech_holding") or []

    slozka = DATA / "penize" / "dotace"
    polozky = []
    subjektu = 0
    if slozka.exists():
        for cesta in sorted(slozka.glob("*.json")):
            d = json.loads(cesta.read_text(encoding="utf-8"))
            dotace = d.get("dotace") or []
            if not dotace:
                continue
            subjektu += 1
            s = subjekty.get(d.get("ico"), {})
            for x in dotace:
                polozky.append({
                    **x,
                    "prijemce_ico": d.get("ico"),
                    "prijemce": d.get("nazev") or s.get("nazev"),
                    "prijemce_typ": s.get("typ"),
                })

    if not po_letech_mesto and not polozky:
        uloz(VYSTUP, {
            "stav": "chybi",
            "duvod": ("v datech nejsou ani souhrnné řady dotací, ani rozpis — "
                      "nejdřív musí proběhnout scrapers/hlidac.py"),
        })
        log.chyba("dotace: žádný vstup, zapsán stav chybi")
        log.uzavri()
        return 1

    # Rozpis řazený od největších; bez roku dozadu, ale NEZAHOZENÉ.
    polozky.sort(key=lambda x: -(x.get("castka_czk") or 0))
    bez_roku = sum(1 for x in polozky if not x.get("rok"))
    celkem_czk = sum(x.get("castka_czk") or 0 for x in polozky)

    uloz(VYSTUP, {
        "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "stav": "ok",
        "jednotka": "CZK",
        "zdroj": "Hlídač státu — statistiky subjektu a rozpis dotací (DotInfo/CEDR)",
        "metodika": [
            "Souhrnné řady `po_letech_*` jsou ze statistik Hlídače a pokrývají "
            "jen poslední roky — starší dotace v nich NEJSOU, protože je okno "
            "zdroje nenese. Není to tvrzení, že dřív město dotace nebralo.",
            "Rozpis jednotlivých dotací je výběr velkých dotací z DotInfo/CEDR, "
            "ne úplný registr; u části záznamů zdroj neuvádí rok. Proto se "
            "z rozpisu NIKDY nesčítají roční řady.",
            "Částka dotace platí zpravidla pro celý projekt (i víceletý) — "
            "s ročními transfery ve FIN 2-12 M se nekryje a nemá se s nimi "
            "sčítat ani porovnávat po letech.",
            "`po_letech_mesto` je jen město (IČO 00254061), "
            "`po_letech_holding` město plus jeho organizace.",
        ],
        "po_letech_mesto": po_letech_mesto,
        "po_letech_holding": po_letech_holding,
        "rozpis": {
            "subjektu": subjektu,
            "polozek": len(polozky),
            "bez_roku": bez_roku,
            "celkem_czk": round(celkem_czk, 2),
            "polozky": polozky,
        },
    })
    log.pricti()
    log.info(f"dotace: řady {len(po_letech_mesto)}/{len(po_letech_holding)} let, "
             f"rozpis {len(polozky)} položek za {subjektu} subjektů")
    vysledek = log.uzavri()
    return 0 if vysledek["uspech"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
