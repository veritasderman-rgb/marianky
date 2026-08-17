#!/usr/bin/env python3
"""Rozpočet města a hospodaření holdingu — přehledy z dat Monitoru.

Vstup: `data/rozpocet/{fin212m,rozvaha,vyzz}/*.json` a číselníky, které
stáhl `scrapers/monitor.py`. Výstup: `data/rozpocet/prehled/`.

Co se tu počítá
---------------
* **po_letech.json** — příjmy a výdaje města v čase, plán i skutečnost
* **vydaje_struktura.json** — kam peníze jdou podle paragrafů rozpočtové
  skladby (školství, doprava, kultura…)
* **plan_vs_skutecnost.json** — kde se plán a realita rozešly nejvíc
* **majetek_zadluzenost.json** — rozvaha města, úvěry, peníze na účtech
* **organizace.json** — účetní výkazy příspěvkových organizací
* **kryti_smlouvami.json** — kolik z výdajů má protějšek v registru smluv
* **souhrn.json** — čísla pro titulní stranu

Pět věcí, na kterých se dá tenhle přehled rozbít
------------------------------------------------
1. **Konsolidace se do schváleného rozpočtu nerozpočtuje.** Vnitřní převody
   mezi fondy města se ve skutečnosti odečítají (řádky 4060 a 4250), ale
   v plánu jsou nulové. V roce 2025 to dělá 1,09 mld. Kč — víc, než je celý
   rozpočet města. Kdo porovná plán „před konsolidací" se skutečností
   „po konsolidaci", dostane nesmysl. Tady se porovnává **výhradně
   po konsolidaci** (4200 / 4430), kde plán ani skutečnost nemají co odečítat.
   Ze stejného důvodu nese členění po třídách celý rozklad až k číslu
   po konsolidaci — samo se totiž na celek nesečte.

2. **Součet paragrafů není rozpočet.** Členění po paragrafech je před
   konsolidací, takže obsahuje i převody vlastním fondům (paragraf 6330).
   Každá položka proto vedle `skutecnost` nese i `skutecnost_bez_prevodu`;
   graf „kam jdou peníze" musí kreslit to druhé. Jinak vyjde, že největší
   kapitolou města jsou „finanční operace" se 65 % rozpočtu — a je to jen
   přesouvání peněz mezi jeho vlastními účty.

3. **Chybějící řádek je null, ne nula.** Když výkaz řádek nemá, neznamená
   to, že je nulový — a naopak, `0.00` ve zdroji je vykázaná nula a ta se
   zachovává. Procenta plnění se nepočítají, když je jmenovatel null nebo 0.
   Stejně tak řádek „C." výkazu zisku a ztráty je jen nadpis s nulou:
   skutečný hospodářský výsledek je až v C.1. a C.2.

4. **Od roku 2026 vypadá výkaz jinak.** FIN 2-12 M přešel z kódu 051 na 063,
   příjmy i výdaje sloučil do jedné tabulky a souhrnnou tabulku úplně
   zrušil. Součty za běžící rok si proto počítáme sami — a `kontrola_dopoctu`
   při každém běhu prožene stejný výpočet šestnácti ročníky, kde souhrn ve
   zdroji je, a porovná ho s ním.

5. **Registr smluv se rozpočtu nerovná.** Smlouva má hodnotu za celou dobu
   plnění, ne za rok podpisu; smlouvy do 50 tis. Kč se nezveřejňují;
   registr běží od 1. 7. 2016. Poměr „kryto smlouvami" je proto orientační
   ukazatel, ne míra transparentnosti — a nese to s sebou v datech.

Kontrola jednotek
-----------------
`overeni_proti_usnesenim` porovnává schválený rozpočet výdajů s částkou,
kterou u bodu „Rozpočet města na rok N" uvádí usnesení zastupitelstva.
Jedenáct ročníků sedí do koruny. Je to nezávislá pojistka proti tomu, aby
se rozpočet ve stovkách milionů někdy zobrazil jako stovky tisíc.

Spuštění:
    python3 -m pipeline.rozpocet
    python3 -m pipeline.rozpocet --rok 2025      # jen kontrolní výpis
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import DATA, Log, ZdrojSelhal, nacti, sledovane_subjekty, uloz  # noqa: E402

VSTUP = DATA / "rozpocet"
VYSTUP = "rozpocet/prehled"
MESTO = "00254061"

# Rekapitulace FIN 2-12 M, tabulka 000400. Klíčové řádky, na kterých stojí
# celá časová osa. Názvy jsou v číselníku, tady je jen náš překlad.
REKAP = {
    "danove": "4010",
    "nedanove": "4020",
    "kapitalove_prijmy": "4030",
    "transfery": "4040",
    "prijmy_pred_konsolidaci": "4050",
    "konsolidace_prijmu": "4060",
    "prijmy": "4200",            # Příjmy celkem po konsolidaci
    "bezne_vydaje": "4210",
    "kapitalove_vydaje": "4220",
    "vydaje_pred_konsolidaci": "4240",
    "konsolidace_vydaju": "4250",
    "vydaje": "4430",            # Výdaje celkem po konsolidaci
    "saldo": "4440",
    "financovani": "4450",
}

# Paragraf 6330 jsou převody vlastním fondům — přesně to, co konsolidace
# odečítá. Ve struktuře výdajů se drží zvlášť, jinak by z něj vyšla
# největší „kapitola" města.
PARAGRAF_PREVODY = "6330"

# Rozvaha (výkaz 001, tabulka 000100) a výkaz zisku a ztráty (002/000100).
ROZVAHA = {
    "aktiva": "AKTIVA",
    "stala_aktiva": "A.",
    "dlouhodoby_hmotny_majetek": "A.II.",
    "dlouhodoby_financni_majetek": "A.III.",
    "obezna_aktiva": "B.",
    "vlastni_kapital": "C.",
    "cizi_zdroje": "D.",
    "dlouhodobe_zavazky": "D.II.",
    "dlouhodobe_uvery": "D.II.1.",
    "kratkodobe_zavazky": "D.III.",
    "kratkodobe_uvery": "D.III.1.",
    "dodavatele": "D.III.5.",
}
# Řádek „C." je ve výkazu jen nadpis a vozí nulu — skutečné výsledky jsou
# až v C.1. a C.2. Kdo by sáhl na „C.", dostal by nulový hospodářský
# výsledek u všech organizací ve všech letech, a vypadalo by to jako fakt.
VYZZ = {
    "naklady": "A.",
    "vynosy": "B.",
    "vysledek_pred_zdanenim": "C.1.",
    "vysledek_po_zdaneni": "C.2.",
}

# Financování, tabulka 000300 — odsud se pozná zadlužování a splácení.
FINANCOVANI = {
    "celkem": "8000",
    "kratkodobe_pujcky_prijate": "8113",
    "kratkodobe_pujcky_splaceno": "8114",
    "zmena_stavu_uctu": "8115",
    "dlouhodobe_pujcky_prijate": "8123",
    "dlouhodobe_pujcky_splaceno": "8124",
}


# --------------------------------------------------------------------------
# Načítání
# --------------------------------------------------------------------------

def _obdobi(vykaz: str) -> list[dict]:
    """Načte všechna období daného výkazu, seřazená."""
    slozka = VSTUP / vykaz
    if not slozka.exists():
        raise ZdrojSelhal(
            f"chybí {slozka} — nejdřív spusť `python3 scrapers/monitor.py`")
    obsah = []
    for p in sorted(slozka.glob("*.json")):
        obsah.append(json.loads(p.read_text(encoding="utf-8")))
    if not obsah:
        raise ZdrojSelhal(f"{slozka} je prázdná")
    return sorted(obsah, key=lambda d: (d["rok"], d["mesic"]))


def _ciselnik(nazev: str) -> dict:
    d = nacti(f"rozpocet/ciselniky/{nazev}.json")
    if not d:
        raise ZdrojSelhal(f"chybí číselník {nazev}")
    return d["polozky"]


def _radky(obd: dict, oddil: str, ico: str) -> list[dict]:
    return [r for r in obd["oddily"].get(oddil, []) if r["ico"] == ico]


# Konsolidační položky. Ověřeno na všech šestnácti uzavřených ročnících:
# součet příjmových položek 413x se do haléře rovná řádku 4060 (konsolidace
# příjmů) a součet výdajů na paragrafu 6330 řádku 4250 (konsolidace výdajů).
# Díky tomu jde konsolidaci dopočítat i pro běžící rok, kde souhrnná tabulka
# ve výkazu chybí — není to odhad, je to pravidlo ověřené proti zdroji.
KONSOLIDACNI_PRIJMY = {"4133", "4134", "4135", "4136", "4137", "4138", "4139"}

# Tabulka financování ve výkazu 051 nese vedle jednotlivých položek i hotový
# součet za celou třídu 8 (řádek 8000). Kdo ho nechá v součtu, dostane
# financování přesně dvojnásobné — a s ním falešný dojem, že si město
# půjčuje dvakrát víc, než si půjčuje.
SOUHRNNE_POLOZKY_FINANCOVANI = {"8000"}


def _rozdel(obd: dict, ico: str) -> dict:
    """Sjednotí obě podoby výkazu FIN 2-12 M do jednoho tvaru.

    Do roku 2025 nese výkaz kód 051 a příjmy, výdaje, financování
    i souhrnnou rekapitulaci má v samostatných tabulkách. Od roku 2026 nese
    kód 063, všechno je v jedné tabulce rozlišené třídou rozpočtové skladby
    a **souhrnná tabulka v extraktu není vůbec**. Tady se obojí převede na
    stejný tvar, aby to zbytek modulu nemusel řešit.
    """
    if "rozpocet" in obd["oddily"]:
        radky = _radky(obd, "rozpocet", ico)
        prijmy = [r for r in radky if (r.get("polozka") or " ")[0] in "1234"]
        vydaje = [r for r in radky if (r.get("polozka") or " ")[0] in "56"]
        financovani = [r for r in radky if (r.get("polozka") or " ")[0] == "8"]
        rekapitulace = None
    else:
        prijmy = _radky(obd, "prijmy", ico)
        vydaje = _radky(obd, "vydaje", ico)
        financovani = _radky(obd, "financovani", ico)
        rekapitulace = _podle_klice(
            _radky(obd, "rekapitulace", ico), "polozka_vykazu") or None
    return {
        "prijmy": prijmy,
        "vydaje": vydaje,
        "financovani": financovani,
        "rekapitulace": rekapitulace,
        "bankovni_ucty": _radky(obd, "bankovni_ucty", ico),
    }


def _soucet_sloupcu(radky: list[dict]) -> dict:
    """Sečte trojici schválený/upravený/skutečnost.

    Sčítá se jen to, co je uvedené; když sloupec nemá ani jeden údaj,
    výsledek je null, ne nula.
    """
    out = {}
    for sloupec in ("schvaleny", "upraveny", "skutecnost"):
        znama = [r[sloupec] for r in radky if r.get(sloupec) is not None]
        out[sloupec] = round(sum(znama), 2) if znama else None
    return out


def _rozdil(a: dict, b: dict) -> dict:
    """Rozdíl dvou trojic. Kde chybí kterákoliv strana, je null."""
    return {k: (round(a[k] - b[k], 2) if None not in (a.get(k), b.get(k)) else None)
            for k in ("schvaleny", "upraveny", "skutecnost")}


def _podle_klice(radky: list[dict], klic: str) -> dict[str, dict]:
    return {r[klic]: r for r in radky if klic in r}


def _trojice(zaznam: dict | None) -> dict:
    """Schválený / upravený / skutečnost. Chybí-li řádek, jsou všechny null.

    Null tu znamená „výkaz to neuvádí", ne nulu. Bez toho rozdílu by graf
    kreslil propad na nulu tam, kde jen nemáme údaj.
    """
    if zaznam is None:
        return {"schvaleny": None, "upraveny": None, "skutecnost": None}
    return {
        "schvaleny": zaznam.get("schvaleny"),
        "upraveny": zaznam.get("upraveny"),
        "skutecnost": zaznam.get("skutecnost"),
    }


def _plneni(t: dict, zaklad: str = "upraveny") -> float | None:
    """Plnění v procentech proti plánu. Nulový nebo chybějící plán → null."""
    p, s = t.get(zaklad), t.get("skutecnost")
    if p is None or s is None or p == 0:
        return None
    return round(s / p * 100, 1)


# --------------------------------------------------------------------------
# 1. Příjmy a výdaje po letech
# --------------------------------------------------------------------------

def _z_rekapitulace(rek: dict) -> dict:
    return {nas: _trojice(rek.get(kod)) for nas, kod in REKAP.items()}


def _dopoctem(cast: dict) -> dict:
    """Sestaví rekapitulaci z jednotlivých položek.

    Použije se u běžícího roku od 2026, kde souhrnná tabulka ve výkazu není.
    Pravidlo pro konsolidaci je ověřené na šestnácti uzavřených ročnících
    (viz KONSOLIDACNI_PRIJMY) — nedopočítává se tu nic, co by zdroj jinde
    nepotvrdil.
    """
    def podle_tridy(radky, tridy):
        return _soucet_sloupcu([r for r in radky
                                if (r.get("polozka") or " ")[0] in tridy])

    p = {
        "danove": podle_tridy(cast["prijmy"], "1"),
        "nedanove": podle_tridy(cast["prijmy"], "2"),
        "kapitalove_prijmy": podle_tridy(cast["prijmy"], "3"),
        "transfery": podle_tridy(cast["prijmy"], "4"),
        "bezne_vydaje": podle_tridy(cast["vydaje"], "5"),
        "kapitalove_vydaje": podle_tridy(cast["vydaje"], "6"),
        "prijmy_pred_konsolidaci": _soucet_sloupcu(cast["prijmy"]),
        "vydaje_pred_konsolidaci": _soucet_sloupcu(cast["vydaje"]),
        "financovani": _soucet_sloupcu(
            [r for r in cast["financovani"]
             if r.get("polozka_vykazu") not in SOUHRNNE_POLOZKY_FINANCOVANI]),
        "konsolidace_prijmu": _soucet_sloupcu(
            [r for r in cast["prijmy"] if r.get("polozka") in KONSOLIDACNI_PRIJMY]),
        "konsolidace_vydaju": _soucet_sloupcu(
            [r for r in cast["vydaje"] if (r.get("paragraf") or "") == PARAGRAF_PREVODY]),
    }
    p["prijmy"] = _rozdil(p["prijmy_pred_konsolidaci"], p["konsolidace_prijmu"])
    p["vydaje"] = _rozdil(p["vydaje_pred_konsolidaci"], p["konsolidace_vydaju"])
    p["saldo"] = _rozdil(p["prijmy"], p["vydaje"])
    return p


KONTROLOVANE_UKAZATELE = (
    "prijmy", "vydaje", "saldo", "financovani", "danove", "nedanove",
    "kapitalove_prijmy", "transfery", "bezne_vydaje", "kapitalove_vydaje",
    "konsolidace_prijmu", "konsolidace_vydaju",
)


def kontrola_dopoctu(fin: list[dict]) -> dict:
    """Ověří dopočet proti souhrnům, které vozí sám výkaz.

    Od roku 2026 souhrnná tabulka v extraktu není a součty si musíme udělat
    sami. Aby to nebylo „věřte nám", pustí se stejný výpočet na všech
    ročnících, kde souhrn ve zdroji **je**, a porovná se s ním. Výsledek se
    ukládá k datům: kdyby se pravidlo někdy rozešlo se zdrojem, je to vidět
    v datech, ne až v grafu.
    """
    porovnano = neshody = 0
    rozdily = []
    for obd in fin:
        cast = _rozdel(obd, MESTO)
        if not cast["rekapitulace"]:
            continue
        zdroj, nas = _z_rekapitulace(cast["rekapitulace"]), _dopoctem(cast)
        for u in KONTROLOVANE_UKAZATELE:
            for sloupec in ("schvaleny", "upraveny", "skutecnost"):
                a, b = zdroj[u][sloupec], nas[u][sloupec]
                if a is None and b is None:
                    continue
                porovnano += 1
                if a is None or b is None or abs(a - b) > 0.5:
                    neshody += 1
                    rozdily.append({"obdobi": obd["obdobi"], "ukazatel": u,
                                    "sloupec": sloupec, "vykaz": a, "dopocet": b})
    return {
        "porovnanych_hodnot": porovnano,
        "neshod": neshody,
        "obdobi_se_souhrnem": sum(1 for o in fin if _rozdel(o, MESTO)["rekapitulace"]),
        "rozdily": rozdily[:20],
        "zaver": ("dopočet se shoduje se souhrny výkazu ve všech porovnaných "
                  "hodnotách" if not neshody else
                  "POZOR: dopočet se v některých hodnotách rozchází se zdrojem"),
    }


def overeni_proti_usnesenim(osa: dict) -> dict:
    """Porovná schválený rozpočet výdajů s částkou z usnesení zastupitelstva.

    Nezávislá kontrola jednotek. Monitor vede částky v celých korunách,
    ale kdyby je někdy začal vozit v tisících, tenhle test to chytne dřív,
    než se rozpočet ve stovkách milionů zobrazí jako stovky tisíc — což se
    v tomhle projektu už jednou stalo.

    Zastupitelstvo schvaluje rozpočet na příští rok, takže se usnesení
    z prosince roku N páruje s rozpočtem roku N+1. Body, kde je výše jen
    v příloze a v textu zůstala jiná částka (Fond z pobytu), test poznají
    podle řádového rozdílu a hlásí je jako `neporovnano`, ne jako neshodu.
    """
    # Schválený rozpočet se během roku nemění, takže na tenhle test stačí
    # i běžící období — jinak by poslední schválený rozpočet zůstal
    # neověřený celý rok, právě když je nejčerstvější.
    podle_roku = {}
    for r in osa["roky"]:
        if r["rok"] not in podle_roku or r["koncove"]:
            podle_roku[r["rok"]] = r
    sedi = neshody = neporovnano = 0
    polozky = []

    for cesta in sorted((DATA / "usneseni").glob("*/*/*.json")):
        jednani = json.loads(cesta.read_text(encoding="utf-8"))
        for bod in jednani.get("body") or []:
            nazev = bod.get("nazev") or ""
            castka = bod.get("castka_czk")
            m = re.search(r"Rozpočet města.*na rok (\d{4})", nazev)
            if not (m and castka):
                continue
            rok = int(m.group(1))
            r = podle_roku.get(rok)
            plan = (r or {}).get("vydaje", {}).get("schvaleny")
            if plan is None:
                stav = "rok_neni_v_datech"
                neporovnano += 1
            elif abs(castka - plan) < 1:
                stav = "sedi"
                sedi += 1
            elif castka < plan / 5:
                # Řádově menší číslo — v usnesení je odkaz na přílohu
                # a vyparsovaná částka patří jinému bodu (typicky Fondu
                # z pobytu). Není to rozpor v datech Monitoru.
                stav = "usneseni_uvadi_jinou_castku"
                neporovnano += 1
            else:
                stav = "neshoda"
                neshody += 1
            polozky.append({
                "rok": rok,
                "datum_usneseni": jednani.get("datum"),
                "castka_v_usneseni": castka,
                "schvalene_vydaje_monitor": plan,
                "stav": stav,
            })

    return {
        "popis": ("Schválený rozpočet výdajů podle Monitoru proti částce "
                  "v usnesení zastupitelstva. Kontrola jednotek — Monitor "
                  "vede částky v celých korunách."),
        "sedi": sedi,
        "neshod": neshody,
        "neporovnano": neporovnano,
        "polozky": sorted(polozky, key=lambda z: z["rok"]),
        "zaver": ("schválený rozpočet z Monitoru se do koruny shoduje "
                  f"s {sedi} usneseními zastupitelstva" if not neshody else
                  "POZOR: Monitor se rozchází s usnesením zastupitelstva"),
    }


def po_letech(fin: list[dict], log: Log) -> dict:
    roky = []
    for obd in fin:
        cast = _rozdel(obd, MESTO)
        if not (cast["prijmy"] or cast["vydaje"]):
            log.info(f"{obd['obdobi']}: město ve výkazu není, přeskakuji")
            continue
        if cast["rekapitulace"]:
            polozky, zdroj_souctu = _z_rekapitulace(cast["rekapitulace"]), "rekapitulace"
        else:
            polozky, zdroj_souctu = _dopoctem(cast), "dopocet_z_polozek"
            log.info(f"{obd['obdobi']}: výkaz nemá souhrnnou tabulku, "
                     "součty dopočítány z položek")

        roky.append({
            "rok": obd["rok"],
            "obdobi": obd["obdobi"],
            "koncove": obd["koncove"],
            "zdroj_souctu": zdroj_souctu,
            "prijmy": polozky["prijmy"],
            "vydaje": polozky["vydaje"],
            "saldo": polozky["saldo"],
            "financovani": polozky["financovani"],
            "plneni_prijmu_pct": _plneni(polozky["prijmy"]),
            "plneni_vydaju_pct": _plneni(polozky["vydaje"]),
            # Členění po třídách rozpočtové skladby je vždycky PŘED
            # konsolidací — v roce 2025 je v přijatých transferech 1,17 mld.,
            # z toho 1,09 mld. jsou převody z vlastních fondů města. Aby se
            # nedalo omylem sečíst členění a porovnat ho s celkem, nese si
            # každé členění celý rozklad až k číslu po konsolidaci.
            "prijmy_struktura": {
                "pred_konsolidaci": True,
                **{k: polozky[k] for k in
                   ("danove", "nedanove", "kapitalove_prijmy", "transfery")},
                "soucet_pred_konsolidaci": polozky["prijmy_pred_konsolidaci"],
                "minus_konsolidace": polozky["konsolidace_prijmu"],
                "po_konsolidaci": polozky["prijmy"],
            },
            "vydaje_struktura": {
                "pred_konsolidaci": True,
                **{k: polozky[k] for k in ("bezne_vydaje", "kapitalove_vydaje")},
                "soucet_pred_konsolidaci": polozky["vydaje_pred_konsolidaci"],
                "minus_konsolidace": polozky["konsolidace_vydaju"],
                "po_konsolidaci": polozky["vydaje"],
            },
            "konsolidace": {
                "prijmy": polozky["konsolidace_prijmu"],
                "vydaje": polozky["konsolidace_vydaju"],
            },
        })

    hotove = [r["rok"] for r in roky if r["koncove"]]
    mezery = ([r for r in range(min(hotove), max(hotove) + 1) if r not in hotove]
              if hotove else [])
    return {
        "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "jednotka": "CZK",
        "subjekt": {"ico": MESTO, "nazev": "Město Mariánské Lázně"},
        "zdroj": "FIN 2-12 M, tabulka IV (rekapitulace), Monitor státní pokladny",
        "metodika": [
            "Příjmy i výdaje jsou uvedené PO KONSOLIDACI (řádky 4200 a 4430) — "
            "bez vnitřních převodů mezi fondy města.",
            "Konsolidace se do schváleného ani upraveného rozpočtu nerozpočtuje, "
            "proto je plán před konsolidací a po konsolidaci shodný. Porovnávat "
            "plán se skutečností jde jen na téhle úrovni.",
            "Chybějící hodnota je null, ne nula. `0` znamená, že výkaz nulu "
            "skutečně uvádí.",
            "Období s `koncove: false` je stav k danému měsíci, ne celý rok — "
            "do meziročního srovnání nepatří.",
            "`prijmy_struktura` a `vydaje_struktura` jsou členění po TŘÍDÁCH "
            "rozpočtové skladby, a ta jsou PŘED konsolidací. Nesečtou se proto "
            "na `prijmy` / `vydaje` — rozklad až k číslu po konsolidaci nese "
            "každé členění v sobě (`soucet_pred_konsolidaci` − "
            "`minus_konsolidace` = `po_konsolidaci`).",
            "`zdroj_souctu: rekapitulace` znamená, že součty přebíráme ze "
            "souhrnné tabulky výkazu. `dopocet_z_polozek` znamená, že souhrnná "
            "tabulka v extraktu není (od roku 2026) a součet je náš — včetně "
            "konsolidace, jejíž pravidlo se do haléře shoduje se souhrny všech "
            "šestnácti uzavřených ročníků.",
        ],
        "kontrola_dopoctu": kontrola_dopoctu(fin),
        "overeni_proti_usnesenim": None,   # doplní se níž, potřebuje hotovou osu
        "roky": roky,
        "roky_bez_dat": mezery,
    }


# --------------------------------------------------------------------------
# 2. Struktura výdajů podle paragrafů
# --------------------------------------------------------------------------

def _nazev_paragrafu(kod: str, cis: dict) -> str | None:
    z = cis.get(kod)
    return z["nazev"] if z else None


def vydaje_struktura(fin: list[dict], cis_par: dict, log: Log) -> dict:
    roky = []
    for obd in fin:
        radky = _rozdel(obd, MESTO)["vydaje"]
        if not radky:
            continue

        po_paragrafu: dict[str, dict] = {}
        po_oddilu: dict[str, dict] = {}
        po_skupine: dict[str, dict] = {}
        celkem = {"schvaleny": 0.0, "upraveny": 0.0, "skutecnost": 0.0}
        bez_prevodu = {"schvaleny": 0.0, "upraveny": 0.0, "skutecnost": 0.0}
        prevody = {"schvaleny": 0.0, "upraveny": 0.0, "skutecnost": 0.0}

        for r in radky:
            par = r.get("paragraf") or ""
            je_prevod = par == PARAGRAF_PREVODY
            hodnoty = {k: (r.get(k) or 0.0) for k in celkem}
            for k in celkem:
                celkem[k] += hodnoty[k]
            cil = prevody if je_prevod else bez_prevodu
            for k in cil:
                cil[k] += hodnoty[k]

            for kos, kod in ((po_paragrafu, par), (po_oddilu, par[:2]),
                             (po_skupine, par[:1])):
                z = kos.setdefault(kod, {
                    "schvaleny": 0.0, "upraveny": 0.0, "skutecnost": 0.0,
                    "schvaleny_bez_prevodu": 0.0, "upraveny_bez_prevodu": 0.0,
                    "skutecnost_bez_prevodu": 0.0, "obsahuje_prevody": False})
                for k in ("schvaleny", "upraveny", "skutecnost"):
                    z[k] += hodnoty[k]
                # Převody vlastním fondům sedí na paragrafu 6330, takže se
                # schovají i do nadřazeného oddílu 63 a skupiny 6. Bez téhle
                # druhé řady by z „finančních operací" vyšla dvoutřetinová
                # největší kapitola města — a byly by to jen přesuny mezi
                # vlastními účty.
                if je_prevod:
                    z["obsahuje_prevody"] = True
                else:
                    for k in ("schvaleny", "upraveny", "skutecnost"):
                        z[f"{k}_bez_prevodu"] += hodnoty[k]

        def _sez(kos: dict, uroven: str) -> list[dict]:
            out = []
            for kod, v in kos.items():
                out.append({
                    "kod": kod,
                    "nazev": _nazev_paragrafu(kod, cis_par),
                    "uroven": uroven,
                    "obsahuje_prevody_vlastnim_fondum": v["obsahuje_prevody"],
                    **{k: round(v[k], 2) for k in
                       ("schvaleny", "upraveny", "skutecnost",
                        "schvaleny_bez_prevodu", "upraveny_bez_prevodu",
                        "skutecnost_bez_prevodu")},
                    "podil_pct": None,
                    "podil_bez_prevodu_pct": None,
                })
            zaklad = celkem["skutecnost"]
            zaklad_bez = bez_prevodu["skutecnost"]
            for z in out:
                if zaklad:
                    z["podil_pct"] = round(z["skutecnost"] / zaklad * 100, 2)
                if zaklad_bez:
                    z["podil_bez_prevodu_pct"] = round(
                        z["skutecnost_bez_prevodu"] / zaklad_bez * 100, 2)
            return sorted(out, key=lambda z: -z["skutecnost_bez_prevodu"])

        roky.append({
            "rok": obd["rok"],
            "obdobi": obd["obdobi"],
            "koncove": obd["koncove"],
            "celkem": {k: round(v, 2) for k, v in celkem.items()},
            "bez_prevodu_vlastnim_fondum": {k: round(v, 2) for k, v in bez_prevodu.items()},
            "prevody_vlastnim_fondum": {k: round(v, 2) for k, v in prevody.items()},
            "skupiny": _sez(po_skupine, "skupina"),
            "oddily": _sez(po_oddilu, "oddil"),
            "paragrafy": _sez(po_paragrafu, "paragraf"),
        })

    return {
        "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "jednotka": "CZK",
        "subjekt": {"ico": MESTO, "nazev": "Město Mariánské Lázně"},
        "zdroj": "FIN 2-12 M, tabulka II (výdaje po paragrafech a položkách)",
        "metodika": [
            "Členění po paragrafech je PŘED konsolidací, takže součet paragrafů "
            "je vyšší než výdaje po konsolidaci z `po_letech.json`.",
            "Paragraf 6330 jsou převody vlastním fondům — vnitřní přesuny peněz "
            "města. Do grafu „kam jdou peníze\" patří "
            "`skutecnost_bez_prevodu` a `podil_bez_prevodu_pct`, ne `skutecnost`. "
            "V roce 2025 by jinak vyšlo, že 65 % rozpočtu města jde na "
            "„finanční operace\" — přitom jde o přesuny mezi jeho vlastními účty.",
            "`podil_pct` počítá podíl na skutečnosti VČETNĚ převodů, "
            "`podil_bez_prevodu_pct` bez nich. Každá řada se sečte na 100 % "
            "ve své vlastní základně; nemíchat je v jednom grafu.",
            "`obsahuje_prevody_vlastnim_fondum` označuje oddíl nebo skupinu, "
            "do které paragraf 6330 spadá (oddíl 63, skupina 6).",
            "Řazení je podle `skutecnost_bez_prevodu`.",
            "Úrovně: skupina (1 číslice), oddíl (2), paragraf (4) — hierarchie "
            "rozpočtové skladby. Nesčítat napříč úrovněmi.",
        ],
        "roky": roky,
    }


# --------------------------------------------------------------------------
# 3. Plán proti skutečnosti
# --------------------------------------------------------------------------

def plan_vs_skutecnost(osa: dict, struktura: dict) -> dict:
    podle_roku = {r["rok"]: r for r in struktura["roky"]}
    roky = []

    for r in osa["roky"]:
        prijmy, vydaje = r["prijmy"], r["vydaje"]
        s = podle_roku.get(r["rok"])

        rozchody = []
        if s:
            # Záměrně se pracuje s hodnotami BEZ převodů vlastním fondům.
            # Ty se do plánu nerozpočtují, takže by u oddílu 63 vyšel rozchod
            # v řádu miliardy — a byl by to jen účetní přesun, ne minutý plán.
            for p in s["oddily"]:
                sch, upr = p["schvaleny_bez_prevodu"], p["upraveny_bez_prevodu"]
                sku = p["skutecnost_bez_prevodu"]
                rozchody.append({
                    "kod": p["kod"],
                    "nazev": p["nazev"],
                    "schvaleny": sch,
                    "upraveny": upr,
                    "skutecnost": sku,
                    "rozdil_proti_schvalenemu": round(sku - sch, 2),
                    "rozdil_proti_upravenemu": round(sku - upr, 2),
                    "plneni_pct": round(sku / upr * 100, 1) if upr else None,
                })
            rozchody.sort(key=lambda z: -abs(z["rozdil_proti_schvalenemu"]))

        def _delta(t: dict) -> dict:
            sch, upr, sku = t["schvaleny"], t["upraveny"], t["skutecnost"]
            return {
                "navyseni_rozpoctu": (round(upr - sch, 2)
                                      if None not in (upr, sch) else None),
                "navyseni_rozpoctu_pct": (round((upr - sch) / sch * 100, 1)
                                          if sch else None),
                "odchylka_od_planu": (round(sku - upr, 2)
                                      if None not in (sku, upr) else None),
                "odchylka_od_schvaleneho": (round(sku - sch, 2)
                                            if None not in (sku, sch) else None),
            }

        roky.append({
            "rok": r["rok"],
            "obdobi": r["obdobi"],
            "koncove": r["koncove"],
            "prijmy": {**prijmy, "plneni_pct": r["plneni_prijmu_pct"], **_delta(prijmy)},
            "vydaje": {**vydaje, "plneni_pct": r["plneni_vydaju_pct"], **_delta(vydaje)},
            "saldo_planovane": r["saldo"]["schvaleny"],
            "saldo_skutecne": r["saldo"]["skutecnost"],
            "nejvetsi_rozchody_oddilu": rozchody[:10],
        })

    return {
        "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "jednotka": "CZK",
        "subjekt": {"ico": MESTO, "nazev": "Město Mariánské Lázně"},
        "metodika": [
            "`navyseni_rozpoctu` je rozdíl upraveného a schváleného rozpočtu — "
            "o kolik zastupitelstvo v průběhu roku plán změnilo.",
            "`odchylka_od_planu` je rozdíl skutečnosti proti upravenému rozpočtu, "
            "tedy o kolik minulo plnění i ten opravený plán.",
            "`plneni_pct` se počítá proti UPRAVENÉMU rozpočtu; proti schválenému "
            "by měřilo hlavně to, kolikrát se rozpočet během roku měnil.",
            "Rozchody podle oddílů se počítají BEZ převodů vlastním fondům "
            "(paragraf 6330). Ty se do plánu nerozpočtují, takže by u oddílu 63 "
            "vyšel rozchod v řádu miliardy — což by byl přesun mezi vlastními "
            "účty města, ne minutý plán.",
        ],
        "roky": roky,
    }


# --------------------------------------------------------------------------
# 4. Majetek a zadluženost města
# --------------------------------------------------------------------------

def _vykaz_hodnoty(radky: list[dict], mapa: dict, pole: str) -> dict:
    podle = _podle_klice(radky, "polozka_vykazu")
    out = {}
    for nas, kod in mapa.items():
        z = podle.get(kod)
        out[nas] = z.get(pole) if z else None
    return out


def majetek_zadluzenost(rozv: list[dict], fin: list[dict], cis_polvyk: dict) -> dict:
    financ_podle_roku = {}
    ucty_podle_roku = {}
    for obd in fin:
        cast = _rozdel(obd, MESTO)
        # Do roku 2025 má financování vlastní tabulku s položkami výkazu,
        # od 2026 jsou to prostě položky třídy 8 v hlavní tabulce. Klíč se
        # proto bere z toho, co řádek nese.
        f = {(r.get("polozka_vykazu") or r.get("polozka")): r
             for r in cast["financovani"]}
        financ_podle_roku[obd["obdobi"]] = {
            nas: (f[kod].get("skutecnost") if kod in f else None)
            for nas, kod in FINANCOVANI.items()
        }
        # Účty se ve výkazu 051 značí kódy 6010–6060 a je mezi nimi hotový
        # součet (6030 = běžné účty celkem); ve výkazu 063 se značí 1–8
        # a součtový řádek v něm není. Ukládá se jmenný rozpis a k němu
        # součet s příznakem, odkud se vzal.
        kod_vykazu = (obd.get("kody_vykazu") or ["051"])[0]
        ucty = []
        for r in cast["bankovni_ucty"]:
            kod = r.get("ucet") or r.get("polozka_vykazu")
            ucty.append({
                "kod": kod,
                "nazev": (cis_polvyk.get(f"{kod_vykazu}/000600/{kod}")
                          or cis_polvyk.get(f"{kod_vykazu}/000200/{kod}")
                          or {}).get("nazev"),
                "pocatecni_stav": r.get("pocatecni_stav"),
                "koncovy_stav": r.get("koncovy_stav"),
                "zmena": r.get("zmena"),
            })
        soucet = next((u for u in ucty if u["kod"] == "6030"), None)
        ucty_podle_roku[obd["obdobi"]] = {
            "ucty": ucty,
            "bezne_ucty_celkem": {
                "pocatecni_stav": (soucet or {}).get("pocatecni_stav"),
                "koncovy_stav": (soucet or {}).get("koncovy_stav"),
                "zdroj": "vykaz" if soucet else "neuvedeno",
            },
        }

    roky = []
    for obd in rozv:
        radky = _radky(obd, "rozvaha", MESTO)
        if not radky:
            continue
        r = _vykaz_hodnoty(radky, ROZVAHA, "netto")
        dluh = [r["dlouhodobe_uvery"], r["kratkodobe_uvery"]]
        roky.append({
            "rok": obd["rok"],
            "obdobi": obd["obdobi"],
            "koncove": obd["koncove"],
            "rozvaha": r,
            "uvery_celkem": (round(sum(x for x in dluh if x is not None), 2)
                             if any(x is not None for x in dluh) else None),
            "financovani": financ_podle_roku.get(obd["obdobi"]),
            "bankovni_ucty": ucty_podle_roku.get(obd["obdobi"]),
        })

    return {
        "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "jednotka": "CZK",
        "subjekt": {"ico": MESTO, "nazev": "Město Mariánské Lázně"},
        "zdroj": "Rozvaha (netto, běžné období) + FIN 2-12 M tabulky III a VI",
        "metodika": [
            "Rozvahové hodnoty jsou NETTO za běžné období, tedy po odečtení oprávek.",
            "`uvery_celkem` je součet dlouhodobých (D.II.1.) a krátkodobých "
            "(D.III.1.) úvěrů. Když výkaz řádek nemá, je null — to není nula, "
            "ale „neuvedeno\".",
            "Cizí zdroje (D.) obsahují i běžné závazky vůči dodavatelům, "
            "takže se nerovnají dluhu. Zadluženost je `uvery_celkem`.",
            "`financovani` je třída 8 rozpočtu: kladné číslo znamená, že město "
            "peníze do rozpočtu doplnilo (úvěrem nebo z účtů), záporné, že "
            "přebytek odložilo nebo splatilo dluh.",
            "`bezne_ucty_celkem.zdroj` říká, jestli součet běžných účtů vozí "
            "sám výkaz (`vykaz`), nebo v něm součtový řádek není (`neuvedeno`) "
            "— od roku 2026 tam není. Rozpis jednotlivých účtů je vždy.",
        ],
        "roky": roky,
    }


# --------------------------------------------------------------------------
# 5. Účetní výkazy organizací holdingu
# --------------------------------------------------------------------------

def organizace(rozv: list[dict], vyzz: list[dict], subjekty: dict) -> dict:
    data: dict[str, dict] = {}
    for obd in rozv:
        for ico, radky in _seskup(obd, "rozvaha").items():
            rok = data.setdefault(ico, {}).setdefault(obd["obdobi"], {})
            rok["rok"] = obd["rok"]
            rok["koncove"] = obd["koncove"]
            rok["rozvaha"] = _vykaz_hodnoty(radky, ROZVAHA, "netto")
    for obd in vyzz:
        for ico, radky in _seskup(obd, "vyzz").items():
            rok = data.setdefault(ico, {}).setdefault(obd["obdobi"], {})
            rok["rok"] = obd["rok"]
            rok["koncove"] = obd["koncove"]
            hlavni = _vykaz_hodnoty(radky, VYZZ, "hlavni_cinnost")
            hosp = _vykaz_hodnoty(radky, VYZZ, "hospodarska_cinnost")
            naklady = _soucet(hlavni["naklady"], hosp["naklady"])
            vynosy = _soucet(hlavni["vynosy"], hosp["vynosy"])
            vysledek = _soucet(hlavni["vysledek_po_zdaneni"],
                               hosp["vysledek_po_zdaneni"])
            # Výkazy za roky 2010 a 2011 řádek s výsledkem hospodaření vůbec
            # nemají. Dopočítá se rozdílem výnosů a nákladů a nese to napsané
            # v `vysledek_zdroj`, aby se pak nedalo tvrdit, že to říká výkaz.
            zdroj_vysledku = "vykaz"
            if vysledek is None and None not in (naklady, vynosy):
                vysledek, zdroj_vysledku = round(vynosy - naklady, 2), "dopocet"
            rok["vyzz"] = {
                "hlavni_cinnost": hlavni,
                "hospodarska_cinnost": hosp,
                "naklady_celkem": naklady,
                "vynosy_celkem": vynosy,
                "vysledek_hospodareni_celkem": vysledek,
                "vysledek_zdroj": zdroj_vysledku,
            }

    out = []
    for ico in sorted(data, key=lambda i: subjekty.get(i, {}).get("nazev", i)):
        s = subjekty.get(ico, {})
        obdobi = [{"obdobi": o, **v} for o, v in sorted(data[ico].items())]
        out.append({
            "ico": ico,
            "nazev": s.get("nazev"),
            "typ": s.get("typ"),
            "vlastnictvi": s.get("vlastnictvi"),
            "obdobi": obdobi,
        })

    chybi = [{"ico": i, "nazev": s["nazev"], "typ": s.get("typ")}
             for i, s in sorted(subjekty.items()) if i not in data]
    return {
        "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "jednotka": "CZK",
        "zdroj": "Rozvaha a Výkaz zisku a ztráty, Monitor státní pokladny",
        "metodika": [
            "Rozvahové hodnoty jsou netto za běžné období.",
            "Výkaz zisku a ztráty se vede zvlášť za hlavní a hospodářskou "
            "činnost; součty obou činností jsou dopočítané, ne převzaté ze zdroje.",
            "`vysledek_hospodareni_celkem` je výsledek PO zdanění (řádek C.2.). "
            "`vysledek_zdroj: dopocet` značí roky 2010 a 2011, kde výkaz řádek "
            "s výsledkem nemá a počítá se z rozdílu výnosů a nákladů.",
            "Obchodní společnosti města (TDS, Lázeňské lesy…) v CSÚIS nejsou — "
            "nejsou to vybrané účetní jednotky. Jejich závěrky vede sbírka "
            "listin obchodního rejstříku, ne Monitor.",
        ],
        "organizace": out,
        "subjekty_bez_vykazu": chybi,
    }


def _seskup(obd: dict, oddil: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in obd["oddily"].get(oddil, []):
        out[r["ico"]].append(r)
    return out


def _soucet(*hodnoty) -> float | None:
    """Součet, ve kterém null není nula. Když chybí všechno, vrací null."""
    znama = [h for h in hodnoty if h is not None]
    return round(sum(znama), 2) if znama else None


# --------------------------------------------------------------------------
# 6. Propojení na registr smluv
# --------------------------------------------------------------------------

def kryti_smlouvami(osa: dict, subjekty: dict) -> dict:
    vnitrni_ica = {i for i, s in subjekty.items()
                   if i != MESTO and s.get("vlastnictvi", "").startswith("mesto")}

    smlouvy = nacti(f"penize/smlouvy/{MESTO}.json")
    if not smlouvy:
        return {
            "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "stav": "chybi",
            "duvod": f"data/penize/smlouvy/{MESTO}.json neexistuje — "
                     "modul A3 (peníze) ještě neproběhl",
            "roky": [],
        }

    po_letech_smluv: dict[int, dict] = {}
    for s in smlouvy["smlouvy"]:
        if s.get("smer") != "vydaj":
            continue
        datum = s.get("datum")
        if not datum:
            continue
        rok = int(datum[:4])
        z = po_letech_smluv.setdefault(rok, {
            "castka": 0.0, "smluv": 0, "bez_ceny": 0,
            "vnitrni_castka": 0.0, "vnitrni_smluv": 0,
        })
        z["smluv"] += 1
        castka = s.get("castka_czk")
        if castka is None:
            # Smlouva bez uvedené ceny. Nepočítat ji jako nulu — jinak by
            # vyšlo, že město za ni nic neplatí.
            z["bez_ceny"] += 1
            continue
        z["castka"] += castka
        if s.get("protistrana_ico") in vnitrni_ica:
            z["vnitrni_castka"] += castka
            z["vnitrni_smluv"] += 1

    roky = []
    for r in osa["roky"]:
        rok = r["rok"]
        vyd = r["vydaje"]["skutecnost"]
        z = po_letech_smluv.get(rok)
        # Registr smluv běží od 1. 7. 2016; rok 2016 je jen půlrok.
        stav = ("mimo_registr" if rok < 2016
                else "castecny_rok" if rok == 2016 else "ok")
        podil = None
        if z and vyd:
            podil = round(z["castka"] / vyd * 100, 1)
        roky.append({
            "rok": rok,
            "koncove": r["koncove"],
            "vydaje_skutecnost": vyd,
            "smlouvy_hodnota": round(z["castka"], 2) if z else None,
            "smluv": z["smluv"] if z else None,
            "smluv_bez_ceny": z["bez_ceny"] if z else None,
            "z_toho_vnitrni_holding": round(z["vnitrni_castka"], 2) if z else None,
            "vnitrnich_smluv": z["vnitrni_smluv"] if z else None,
            "podil_smluv_na_vydajich_pct": podil,
            "stav_registru": stav,
        })

    return {
        "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "jednotka": "CZK",
        "subjekt": {"ico": MESTO, "nazev": "Město Mariánské Lázně"},
        "zdroj": "FIN 2-12 M (výdaje) + registr smluv přes Hlídač státu",
        "metodika": [
            "TOHLE NENÍ MÍRA TRANSPARENTNOSTI. Hodnota smlouvy je za celou dobu "
            "plnění, ne za rok podpisu, takže se s ročními výdaji nekryje.",
            "Registr smluv běží od 1. 7. 2016 — roky do 2015 mají "
            "`stav_registru: mimo_registr` a nulový počet smluv o ničem nevypovídá.",
            "Smlouvy do 50 tis. Kč se nezveřejňují, takže drobné výdaje "
            "v registru chybí ze zákona.",
            "Smlouvy bez uvedené ceny se nepočítají jako nula — jsou zvlášť "
            "v `smluv_bez_ceny`.",
            "`z_toho_vnitrni_holding` jsou smlouvy s vlastními organizacemi "
            "města (TDS a spol.). Je to vnitřní převod, ne plnění cizímu "
            "dodavateli — jedna in-house smlouva na 724,5 mil. z 12/2025 sama "
            "přebije roční rozpočet.",
        ],
        "roky": roky,
    }


# --------------------------------------------------------------------------
# 7. Souhrn
# --------------------------------------------------------------------------

def souhrn(osa: dict, struktura: dict, majetek: dict, orgs: dict) -> dict:
    koncove = [r for r in osa["roky"] if r["koncove"]]
    posledni = koncove[-1] if koncove else None
    bezici = next((r for r in reversed(osa["roky"]) if not r["koncove"]), None)

    top = []
    if posledni:
        s = next((x for x in struktura["roky"] if x["rok"] == posledni["rok"]), None)
        if s:
            top = [o for o in s["oddily"]
                   if o["skutecnost_bez_prevodu"] > 0][:8]

    maj = next((m for m in reversed(majetek["roky"]) if m["koncove"]), None)

    return {
        "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "jednotka": "CZK",
        "subjekt": {"ico": MESTO, "nazev": "Město Mariánské Lázně"},
        "rozsah_dat": {
            "prvni_rok": koncove[0]["rok"] if koncove else None,
            "posledni_uzavreny_rok": posledni["rok"] if posledni else None,
            "bezici_obdobi": bezici["obdobi"] if bezici else None,
        },
        "posledni_uzavreny_rok": posledni,
        "bezici_obdobi": bezici,
        "nejvetsi_oddily_vydaju": top,
        "majetek": (maj["rozvaha"] if maj else None),
        "uvery_celkem": (maj["uvery_celkem"] if maj else None),
        "organizaci_s_vykazy": len(orgs["organizace"]),
        "subjektu_bez_vykazu": len(orgs["subjekty_bez_vykazu"]),
        "overeni": {
            "dopocet_proti_souhrnum_vykazu": {
                k: osa["kontrola_dopoctu"][k]
                for k in ("porovnanych_hodnot", "neshod", "zaver")
            },
            "schvaleny_rozpocet_proti_usnesenim": {
                k: osa["overeni_proti_usnesenim"][k]
                for k in ("sedi", "neshod", "neporovnano", "zaver")
            },
        },
    }


# --------------------------------------------------------------------------

def kontrolni_vypis(osa: dict, rok: int) -> None:
    r = next((x for x in osa["roky"] if x["rok"] == rok and x["koncove"]), None)
    if not r:
        print(f"rok {rok} v datech není")
        return
    print(f"\n=== Mariánské Lázně, rozpočet {rok} (v Kč) ===")
    for nazev, t in (("Příjmy", r["prijmy"]), ("Výdaje", r["vydaje"]),
                     ("Saldo", r["saldo"]), ("Financování", r["financovani"])):
        print(f"{nazev:14s} schválený {_f(t['schvaleny'])}  "
              f"upravený {_f(t['upraveny'])}  skutečnost {_f(t['skutecnost'])}")


def _f(v) -> str:
    return "        neuvedeno" if v is None else f"{v:>17,.0f}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Přehledy rozpočtu z dat Monitoru")
    ap.add_argument("--rok", type=int, help="vypsat kontrolní součty za rok")
    args = ap.parse_args()

    log = Log("rozpocet")
    try:
        fin = _obdobi("fin212m")
        rozv = _obdobi("rozvaha")
        vyzz = _obdobi("vyzz")
        cis_par = _ciselnik("paragrafy")
        subjekty = {s["ico"]: s for s in sledovane_subjekty()}
        log.info(f"načteno: fin212m {len(fin)}, rozvaha {len(rozv)}, "
                 f"vyzz {len(vyzz)} období")

        osa = po_letech(fin, log)
        osa["overeni_proti_usnesenim"] = overeni_proti_usnesenim(osa)
        uloz(f"{VYSTUP}/po_letech.json", osa)
        log.info(f"po_letech: {len(osa['roky'])} období, "
                 f"mezery {osa['roky_bez_dat'] or 'žádné'}")
        kd = osa["kontrola_dopoctu"]
        log.info(f"kontrola dopočtu: {kd['porovnanych_hodnot']} hodnot proti "
                 f"souhrnům výkazu, neshod {kd['neshod']}")
        if kd["neshod"]:
            log.chyba(kd["zaver"])

        ku = osa["overeni_proti_usnesenim"]
        log.info(f"ověření proti usnesením: sedí {ku['sedi']}, "
                 f"neshod {ku['neshod']}, neporovnáno {ku['neporovnano']}")
        if ku["neshod"]:
            log.chyba(ku["zaver"])

        struktura = vydaje_struktura(fin, cis_par, log)
        uloz(f"{VYSTUP}/vydaje_struktura.json", struktura)

        plan = plan_vs_skutecnost(osa, struktura)
        uloz(f"{VYSTUP}/plan_vs_skutecnost.json", plan)

        majetek = majetek_zadluzenost(rozv, fin, _ciselnik("polozky_vykazu"))
        uloz(f"{VYSTUP}/majetek_zadluzenost.json", majetek)

        orgs = organizace(rozv, vyzz, subjekty)
        uloz(f"{VYSTUP}/organizace.json", orgs)
        log.info(f"organizace: {len(orgs['organizace'])} s výkazy, "
                 f"{len(orgs['subjekty_bez_vykazu'])} bez")

        kryti = kryti_smlouvami(osa, subjekty)
        uloz(f"{VYSTUP}/kryti_smlouvami.json", kryti)

        uloz(f"{VYSTUP}/souhrn.json", souhrn(osa, struktura, majetek, orgs))
        log.pricti(7)

        if args.rok:
            kontrolni_vypis(osa, args.rok)
    except ZdrojSelhal as e:
        log.chyba(str(e))
        log.uzavri()
        return 1

    vysledek = log.uzavri()
    return 0 if vysledek["uspech"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
