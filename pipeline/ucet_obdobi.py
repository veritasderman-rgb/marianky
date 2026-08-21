#!/usr/bin/env python3
"""Účet volebního období — co zastupitelstvo skutečně dělalo od voleb 2022.

Před komunálními volbami je tohle otázka, kterou si klade volič i kandidát:
jak kdo hlasoval, kdo chodil, kdo drží s klubem. Modul počítá tvrdá čísla
z jmenovitých hlasování zastupitelstva za běžící volební období.

NEJVĚTŠÍ PAST ZDROJE, kterou musí nést každý výstup: portál města
zveřejňuje **jen schválená hlasování** (ověřeno: všech 2 548 hlasování
zastupitelstva v datech má výsledek `schvaleno`). Neschválené návrhy —
tedy přesně ty nejspornější — ve veřejných datech NEJSOU. „Klíčová
hlasování" proto znamenají „nejtěsněji SCHVÁLENÁ", nikoliv „nejspornější
vůbec", a stránka to musí říkat na začátku, ne pod čarou.

Co se počítá
------------
* **Klíčová hlasování** — schválená s nejvíce hlasy proti + zdržel se,
  s rozpisem, jak hlasovaly kluby.
* **Účast** — podíl hlasování, u kterých byl zastupitel přítomen.
* **Hlasování s klubem** — jen z hlasování, kde se klub sám rozdělil
  (kde je klub jednotný, je shoda definičně 100 % a nic neměří).

Vstup:  data/hlasovani/zastupitelstvo/*/*.json, data/usneseni (odkazy)
Výstup: data/obdobi/ucet.json

Spuštění:
    python3 -m pipeline.ucet_obdobi
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import DATA, Log, uloz  # noqa: E402

VYSTUP = "obdobi/ucet.json"

# Komunální volby 23.–24. 9. 2022; ustavující zasedání v říjnu. Období
# běží dodnes — konec se nedopisuje, dokud nejsou další volby v datech.
OBDOBI_OD = "2022-10-01"
VOLBY = "2022"

# Hlas, který znamená přítomnost v sále (nehlasoval = přítomen, nehlasoval).
PRITOMNOST = {"pro", "proti", "zdrzel", "nehlasoval"}
# Hlas, který vstupuje do počítání shody s klubem.
VECNY_HLAS = {"pro", "proti", "zdrzel"}

KLICOVYCH = 30
MIN_PROTIHLASU = 3


def main() -> int:
    log = Log("ucet_obdobi")

    jednani = []
    for cesta in sorted((DATA / "hlasovani" / "zastupitelstvo").glob("*/*.json")):
        try:
            j = json.loads(cesta.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            log.chyba(f"nečitelný soubor {cesta}")
            continue
        if (j.get("datum") or "") >= OBDOBI_OD:
            jednani.append(j)
    jednani.sort(key=lambda j: j.get("datum") or "")
    if not jednani:
        log.chyba(f"žádné jednání zastupitelstva od {OBDOBI_OD}")
        log.uzavri()
        return 1

    # Odkazy na body usnesení podle hlasovani_id — kvůli URL a částce.
    body_podle_hlasovani: dict[str, dict] = {}
    for cesta in sorted((DATA / "usneseni").glob("zastupitelstvo/*/*.json")):
        try:
            u = json.loads(cesta.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for b in u.get("body") or []:
            hid = b.get("hlasovani_id")
            if hid:
                body_podle_hlasovani[hid] = b

    hlasovani_vse: list[tuple[dict, dict]] = [
        (j, h) for j in jednani for h in j.get("hlasovani") or []
    ]

    # ── Klíčová (nejtěsněji schválená) hlasování ──────────────────────────
    def protihlasy(h: dict) -> int:
        return (h.get("proti") or 0) + (h.get("zdrzel") or 0)

    sporna = [(j, h) for j, h in hlasovani_vse if protihlasy(h) >= MIN_PROTIHLASU]
    sporna.sort(key=lambda x: (-protihlasy(x[1]), x[0].get("datum") or ""))

    klicova = []
    for j, h in sporna[:KLICOVYCH]:
        kluby: dict[str, Counter] = defaultdict(Counter)
        for jm in h.get("jmenovite") or []:
            if jm.get("hlas") in VECNY_HLAS:
                kluby[(jm.get("strana") or "bez uskupení").strip()][jm["hlas"]] += 1
        bod = body_podle_hlasovani.get(h.get("id") or "", {})
        klicova.append({
            "id": h.get("id"),
            "datum": j.get("datum"),
            "nazev": h.get("nazev"),
            "tagy": h.get("tagy") or [],
            "pro": h.get("pro"),
            "proti": h.get("proti"),
            "zdrzel": h.get("zdrzel"),
            "nepritomen": h.get("nepritomen"),
            "castka_czk": bod.get("castka_czk"),
            "url": bod.get("url"),
            "kluby": {k: dict(v) for k, v in sorted(kluby.items())},
        })

    # ── Zastupitelé: účast a hlasování s klubem ──────────────────────────
    osoby: dict[str, dict] = {}
    for j, h in hlasovani_vse:
        jmenovite = h.get("jmenovite") or []
        # Rozdělení klubů v tomhle hlasování (jen věcné hlasy).
        hlasy_klubu: dict[str, Counter] = defaultdict(Counter)
        for jm in jmenovite:
            if jm.get("hlas") in VECNY_HLAS:
                hlasy_klubu[(jm.get("strana") or "bez uskupení").strip()][jm["hlas"]] += 1

        for jm in jmenovite:
            oid = jm.get("osoba_id")
            if not oid:
                continue
            o = osoby.setdefault(oid, {
                "osoba_id": oid,
                "jmeno": jm.get("jmeno"),
                "strany": Counter(),
                "hlasovani": 0,
                "pritomen": 0,
                "klub_delene": 0,
                "s_klubem": 0,
            })
            o["hlasovani"] += 1
            o["strany"][(jm.get("strana") or "bez uskupení").strip()] += 1
            hlas = jm.get("hlas")
            if hlas in PRITOMNOST:
                o["pritomen"] += 1
            # Shoda s klubem: jen kde se klub sám rozdělil a kde jsou v něm
            # aspoň 3 věcné hlasy — dvojice „rozdělená 1:1“ nemá většinu.
            if hlas in VECNY_HLAS:
                klub = (jm.get("strana") or "bez uskupení").strip()
                hk = hlasy_klubu.get(klub) or Counter()
                if sum(hk.values()) >= 3 and len(hk) >= 2:
                    nej = hk.most_common(2)
                    if nej[0][1] > nej[1][1]:  # jednoznačná většina klubu
                        o["klub_delene"] += 1
                        if hlas == nej[0][0]:
                            o["s_klubem"] += 1

    zastupitele = []
    for o in osoby.values():
        strana = o["strany"].most_common(1)[0][0]
        zastupitele.append({
            "osoba_id": o["osoba_id"],
            "jmeno": o["jmeno"],
            "strana": strana,
            "zmena_strany": len(o["strany"]) > 1,
            "hlasovani": o["hlasovani"],
            "pritomen": o["pritomen"],
            "ucast_pct": round(o["pritomen"] / o["hlasovani"] * 100, 1) if o["hlasovani"] else None,
            "klub_delene": o["klub_delene"],
            "s_klubem": o["s_klubem"],
            # Míň než 10 dělených hlasování → procento by bylo šum, radši null.
            "s_klubem_pct": (round(o["s_klubem"] / o["klub_delene"] * 100, 1)
                             if o["klub_delene"] >= 10 else None),
        })
    zastupitele.sort(key=lambda z: (-(z["ucast_pct"] or 0), z["jmeno"] or ""))

    # ── Kluby ────────────────────────────────────────────────────────────
    kluby_souhrn: dict[str, dict] = {}
    for z in zastupitele:
        k = kluby_souhrn.setdefault(z["strana"], {"clenove": 0, "delene": 0, "s_klubem": 0})
        k["clenove"] += 1
        k["delene"] += z["klub_delene"]
        k["s_klubem"] += z["s_klubem"]
    kluby = [{
        "strana": s,
        "clenove": v["clenove"],
        "soudrznost_pct": (round(v["s_klubem"] / v["delene"] * 100, 1)
                           if v["delene"] >= 20 else None),
        "delenych_hlasu": v["delene"],
    } for s, v in sorted(kluby_souhrn.items(), key=lambda kv: -kv[1]["clenove"])]

    ne_zcela = sum(1 for _, h in hlasovani_vse if protihlasy(h) >= 1)

    po_letech: dict[str, dict] = {}
    for j, h in hlasovani_vse:
        rok = (j.get("datum") or "????")[:4]
        z = po_letech.setdefault(rok, {"hlasovani": 0, "ne_zcela_jednomyslnych": 0})
        z["hlasovani"] += 1
        if protihlasy(h) >= 1:
            z["ne_zcela_jednomyslnych"] += 1

    uloz(VYSTUP, {
        "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "obdobi": {"volby": VOLBY, "od": OBDOBI_OD, "do": None,
                   "prvni_jednani": jednani[0].get("datum"),
                   "posledni_jednani": jednani[-1].get("datum")},
        "zdroj": "jmenovitá hlasování zastupitelstva (usneseni.muml.cz)",
        "metodika": [
            "ZÁSADNÍ OMEZENÍ ZDROJE: portál města zveřejňuje JEN SCHVÁLENÁ "
            "hlasování. Návrhy, které neprošly, ve veřejných datech nejsou — "
            "„klíčová hlasování“ tu proto znamenají NEJTĚSNĚJI SCHVÁLENÁ, "
            "ne nejspornější vůbec.",
            "Účast je podíl hlasování, u kterých je zastupitel zapsán jinak "
            "než „nepřítomen“. Omluvy zdroj značí jen u novějších zápisů, "
            "proto se omluvená a neomluvená absence nerozlišuje.",
            "„Hlasování s klubem“ se počítá VÝHRADNĚ z hlasování, kde se "
            "klub sám rozdělil a měl jednoznačnou většinu (aspoň 3 věcné "
            "hlasy). Kde je klub jednotný, je shoda definičně 100 % a nic "
            "neměří. Méně než 10 takových hlasování → procento se neuvádí.",
            "Klubem se rozumí uskupení, pod kterým je hlas ve zdroji zapsán "
            "u daného hlasování; při změně klubu během období nese zastupitel "
            "příznak `zmena_strany`.",
            "Hlasy „nehlasoval“ se počítají jako přítomnost, ale ne jako "
            "věcný hlas.",
        ],
        "souhrn": {
            "jednani": len(jednani),
            "hlasovani": len(hlasovani_vse),
            "ne_zcela_jednomyslnych": ne_zcela,
            "s_protihlasy_3plus": len(sporna),
            "zastupitelu": len(zastupitele),
            "po_letech": dict(sorted(po_letech.items())),
        },
        "klicova_hlasovani": klicova,
        "zastupitele": zastupitele,
        "kluby": kluby,
    })
    log.pricti(len(zastupitele))
    log.info(f"období od {OBDOBI_OD}: {len(jednani)} jednání, "
             f"{len(hlasovani_vse)} hlasování, klíčových {len(klicova)}, "
             f"zastupitelů {len(zastupitele)}")
    vysledek = log.uzavri()
    return 0 if vysledek["uspech"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
