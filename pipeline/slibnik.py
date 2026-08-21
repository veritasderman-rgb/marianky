#!/usr/bin/env python3
"""Slibník — co si rada a zastupitelstvo uložily a co s tím je.

Usnesení často zní „rada ukládá odboru X do 30. 6. předložit…". Tenhle modul
takové úkoly vytahuje z textů usnesení a hlídá jim termíny.

Co se tvrdí a co se NEtvrdí
---------------------------
* **Tvrdí se:** že úkol byl uložen (citace z usnesení), komu, s jakým
  termínem, a která pozdější usnesení se na něj VÝSLOVNĚ odkazují číslem
  (např. „usnesení č. RM/145/24"). Odkaz číslem je doložená návaznost.
* **NEtvrdí se, že úkol nebyl splněn.** Rada plnění kontroluje („Kontrola
  plnění usnesení…"), ale výsledek je vždy jen v příloze, kterou město
  nezveřejňuje — z veřejných dat splnění doložit ani vyvrátit nejde.
  Stav `termin_uplynul` znamená právě jen to: termín je pryč a veřejná
  stopa o výsledku neexistuje. To zjištění je samo o sobě obsah.

Jak se páruje návaznost
-----------------------
Body usnesení nesou `cislo_usneseni` (např. „145/24") a texty na sebe
odkazují tvarem „RM/145/24" (rada) nebo „ZM/12/23" (zastupitelstvo).
Párování je deterministické — hledá se přesné číslo, nic se nedohaduje.
Stejné číslo se v jednom roce nemůže opakovat v rámci orgánu.

Vstup:  data/usneseni/{organ}/{rok}/*.json
Výstup: data/slibnik/ukoly.json

Spuštění:
    python3 -m pipeline.slibnik
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import DATA, Log, uloz  # noqa: E402

VYSTUP = "slibnik/ukoly.json"

# „ukládá" v textu bodu. Vylučuje se „neukládá" a „zákon ukládá" — první
# není úkol, druhé je citace povinnosti, ne rozhodnutí rady.
VZOR_UKLADA = re.compile(r"(?<![a-zá-ž])uklád[áa]\b", re.IGNORECASE)
VZOR_NE_UKOL = re.compile(r"(?:ne|zákon\s+|zákoník\s+|vyhláška\s+)uklád[áa]", re.IGNORECASE)

# Plné datum v českém zápisu: 30. 6. 2024, 30.6.2024, 30. června 2024.
MESICE_SLOVY = {
    "ledna": 1, "února": 2, "března": 3, "dubna": 4, "května": 5,
    "června": 6, "července": 7, "srpna": 8, "září": 9, "října": 10,
    "listopadu": 11, "prosince": 12,
}
VZOR_DATUM = re.compile(
    r"(\d{1,2})\.\s*(?:(\d{1,2})\.|(" + "|".join(MESICE_SLOVY) + r"))\s*(\d{4})")

# Termín se hledá jen v okolí slov, která ho ohlašují — datum jinde v textu
# (den podpisu smlouvy, konec nájmu, datum jednání) není termín úkolu.
# Silný vzor: výslovné slovo „termín" / „nejpozději". Slabý vzor: holé
# „do DATUM" — to je termín jen blízko za „ukládá" a jen když před ním
# nestojí slova o platnosti či době („na dobu do", „s platností do"…).
VZOR_TERMIN_SILNY = re.compile(
    r"(?:termín(?:em)?\s*:?\s*(?:do\s+)?|nejpozději\s+(?:do\s+)?|s\s+termínem\s+do\s+)"
    r"(\d{1,2}\.\s*(?:\d{1,2}\.|(?:" + "|".join(MESICE_SLOVY) + r"))\s*\d{4})",
    re.IGNORECASE)
VZOR_TERMIN_SLABY = re.compile(
    r"do\s+(\d{1,2}\.\s*(?:\d{1,2}\.|(?:" + "|".join(MESICE_SLOVY) + r"))\s*\d{4})",
    re.IGNORECASE)
VZOR_NENI_TERMIN_PRED = re.compile(
    r"(?:dobu|doby|platnost[íi]?|období|výpůjčk\w*|nájm\w*|pronájm\w*|"
    r"účinnost[íi]?|splatnost[íi]?|ode?\s+dne[\s\S]{0,20})\s*$", re.IGNORECASE)

# Komu se ukládá. Zachytává se krátká fráze za „ukládá"; typ se pozná
# podle prvního slova. Nezachycený adresát je „neurčeno", ne dohad.
TYPY_ADRESATU = [
    ("odbor", re.compile(r"^odbor", re.I)),
    ("oddělení", re.compile(r"^odděl", re.I)),
    ("tajemník", re.compile(r"^tajemn", re.I)),
    ("starosta/místostarosta", re.compile(r"^(?:místo)?starost", re.I)),
    ("ředitel organizace", re.compile(r"^ředitel", re.I)),
    ("jednatel společnosti", re.compile(r"^jednatel", re.I)),
    ("komise/výbor", re.compile(r"^(?:komisi|výboru)", re.I)),
    ("rada", re.compile(r"^radě", re.I)),
]

VZOR_ODKAZ = re.compile(r"\b(RM|ZM)\s*/\s*(\d{1,4}/\d{2})\b")

PREFIX_ORGANU = {"rada": "RM", "zastupitelstvo": "ZM"}


def _datum_iso(shoda: re.Match) -> str | None:
    den = int(shoda.group(1))
    mesic = int(shoda.group(2)) if shoda.group(2) else MESICE_SLOVY[shoda.group(3)]
    rok = int(shoda.group(4))
    try:
        return date(rok, mesic, den).isoformat()
    except ValueError:
        return None


def _adresat(text_za: str) -> tuple[str | None, str]:
    """Krátká fráze za „ukládá" a její typ."""
    # Fráze končí čárkou, spojkou s infinitivem, nebo po ~8 slovech.
    kus = re.split(r"[,;\n]| aby | a to ", text_za, maxsplit=1)[0]
    slova = kus.strip().split()
    if not slova:
        return None, "neurčeno"
    fraze = " ".join(slova[:8]).strip(" .")
    for typ, vzor in TYPY_ADRESATU:
        if vzor.search(fraze):
            return fraze, typ
    return fraze, "jiný/neurčeno"


def _ukol_z_bodu(jednani: dict, bod: dict, dnes: str) -> dict | None:
    text = (bod.get("text") or "").strip()
    if not text or not VZOR_UKLADA.search(text):
        return None
    m = VZOR_UKLADA.search(text)
    if VZOR_NE_UKOL.search(text[max(0, m.start() - 12):m.end()]):
        return None

    za = text[m.end():]
    adresat, adresat_typ = _adresat(za)

    termin_iso = None
    termin_text = None
    mt = VZOR_TERMIN_SILNY.search(text)
    if not mt:
        # Slabý vzor jen do 250 znaků za „ukládá" a bez slov o platnosti
        # těsně před ním — jinak by termínem bylo kdejaké datum smlouvy.
        for kandidat in VZOR_TERMIN_SLABY.finditer(text, m.end(), m.end() + 250):
            if not VZOR_NENI_TERMIN_PRED.search(text[max(0, kandidat.start() - 30):kandidat.start()]):
                mt = kandidat
                break
    if mt:
        md = VZOR_DATUM.search(mt.group(1))
        if md:
            termin_iso = _datum_iso(md)
            termin_text = mt.group(0).strip()
    # Termín před dnem uložení je nesmysl — datum z textu patřilo něčemu
    # jinému. Radši žádný termín než vymyšlený.
    if termin_iso and termin_iso < (jednani.get("datum") or ""):
        termin_iso = termin_text = None

    if termin_iso is None:
        stav = "bez_terminu"
    elif termin_iso >= dnes:
        stav = "bezi"
    else:
        # POZOR: neznamená „nesplněno". Znamená: termín je pryč a veřejná
        # data o výsledku mlčí — kontrola plnění je jen v příloze.
        stav = "termin_uplynul"

    # Citace úkolu: věta od „ukládá" dál, oříznutá.
    citace = ("…" + text[m.start():m.start() + 320]).strip()
    if len(text) - m.start() > 320:
        citace += "…"

    return {
        "organ": jednani.get("organ"),
        "datum_ulozeni": jednani.get("datum"),
        "cislo_bodu": bod.get("cislo"),
        "cislo_usneseni": bod.get("cislo_usneseni"),
        "nazev": bod.get("nazev"),
        "url": bod.get("url"),
        "tagy": bod.get("tagy") or [],
        "adresat": adresat,
        "adresat_typ": adresat_typ,
        "termin": termin_iso,
        "termin_text": termin_text,
        "stav": stav,
        "citace": citace,
        "navazujici": [],  # doplní se párováním níž
    }


def main() -> int:
    log = Log("slibnik")
    dnes = date.today().isoformat()

    jednani_vse: list[dict] = []
    for cesta in sorted((DATA / "usneseni").glob("*/*/*.json")):
        try:
            jednani_vse.append(json.loads(cesta.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            log.chyba(f"nečitelný soubor {cesta}")
    if not jednani_vse:
        log.chyba("data/usneseni je prázdné — nejdřív musí proběhnout sběr usnesení")
        log.uzavri()
        return 1

    ukoly: list[dict] = []
    # Index odkazů: (prefix, cislo_usneseni, rok_jednani) není potřeba —
    # číslo usnesení nese rok v sobě („145/24“), takže klíč je (prefix, číslo).
    odkazy: dict[tuple[str, str], list[dict]] = {}

    for j in jednani_vse:
        for b in j.get("body") or []:
            u = _ukol_z_bodu(j, b, dnes)
            if u:
                ukoly.append(u)
            for pref, cislo in VZOR_ODKAZ.findall(b.get("text") or ""):
                odkazy.setdefault((pref, cislo), []).append({
                    "datum": j.get("datum"),
                    "organ": j.get("organ"),
                    "cislo_usneseni": b.get("cislo_usneseni"),
                    "nazev": b.get("nazev"),
                    "url": b.get("url"),
                })

    # Doložené návaznosti: pozdější bod se výslovně odkazuje číslem úkolu.
    s_navaznosti = 0
    for u in ukoly:
        pref = PREFIX_ORGANU.get(u["organ"] or "")
        cislo = u["cislo_usneseni"]
        if not (pref and cislo):
            continue
        nav = [o for o in odkazy.get((pref, cislo), [])
               if (o["datum"] or "") > (u["datum_ulozeni"] or "")]
        if nav:
            u["navazujici"] = sorted(nav, key=lambda o: o["datum"] or "")[:10]
            s_navaznosti += 1

    ukoly.sort(key=lambda u: (u["datum_ulozeni"] or "", u["cislo_bodu"] or ""),
               reverse=True)

    stavy = Counter(u["stav"] for u in ukoly)
    po_letech = Counter((u["datum_ulozeni"] or "????")[:4] for u in ukoly)
    adresati = Counter(u["adresat_typ"] for u in ukoly)

    uloz(VYSTUP, {
        "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "hodnoceno_k": dnes,
        "zdroj": "texty usnesení rady a zastupitelstva (usneseni.muml.cz)",
        "metodika": [
            "Úkol je bod usnesení, jehož text obsahuje „ukládá“. Adresát a "
            "termín se čtou z textu; kde termín není plným datem, úkol nese "
            "`bez_terminu` — nic se nedomýšlí.",
            "`termin_uplynul` NEZNAMENÁ „nesplněno“. Rada plnění kontroluje, "
            "ale výsledek kontroly je vždy jen v příloze usnesení, kterou "
            "město nezveřejňuje — splnění z veřejných dat doložit ani "
            "vyvrátit nejde. Že to nejde, je zjištění samo o sobě.",
            "`navazujici` jsou pozdější usnesení, která se na úkol VÝSLOVNĚ "
            "odkazují jeho číslem (např. „RM/145/24“). Je to doložená "
            "návaznost; úkoly, na které nic nenavazuje číslem, mohly být "
            "vyřízeny beze stopy v textech.",
            "Zachycení je textové a konzervativní: „neukládá“ a citace "
            "zákonných povinností se vynechávají; přesto může ojedinělý "
            "bod proklouznout nebo chybět — u každého úkolu je citace "
            "a odkaz na originál.",
        ],
        "souhrn": {
            "ukolu": len(ukoly),
            "s_terminem": sum(1 for u in ukoly if u["termin"]),
            "bezi": stavy.get("bezi", 0),
            "termin_uplynul": stavy.get("termin_uplynul", 0),
            "bez_terminu": stavy.get("bez_terminu", 0),
            "s_navaznosti": s_navaznosti,
            "po_letech": dict(sorted(po_letech.items())),
            "podle_adresata": dict(adresati.most_common()),
        },
        "ukoly": ukoly,
    })
    log.pricti(len(ukoly))
    log.info(f"úkolů {len(ukoly)}: běží {stavy.get('bezi', 0)}, "
             f"termín uplynul {stavy.get('termin_uplynul', 0)}, "
             f"bez termínu {stavy.get('bez_terminu', 0)}, "
             f"s doloženou návazností {s_navaznosti}")
    vysledek = log.uzavri()
    return 0 if vysledek["uspech"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
