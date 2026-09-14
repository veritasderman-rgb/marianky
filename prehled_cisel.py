"""Spočítá tabulku „Co je v datech" pro README z hotových dat.

Proč skript a ne ruční tabulka: úvodní stránka webu si tatáž čísla počítá
živě a má u toho napsané, proč — „napsat ta čísla do textu ručně by
znamenalo, že za měsíc lžou". U README to platí stejně a lhalo to: před
během 14. 9. 2026 tam stálo 692 jednání (bylo 693), 12 908 bodů usnesení
(12 914), 12 367 hlasování (12 373) a 16 týdenních vydání (17).

Pozor na opačnou chybu: **číslo, které se dá vzít z hotové agregace, se
nikdy nepočítá znovu z podkladů.** První verze tohohle skriptu sečetla
smlouvy přes soubory v `data/penize/smlouvy/`, vyšlo jí 6 996 místo 6 684
a chystala se README „opravit" na nadsazené číslo. Kde agregace nebo
`souhrn` existuje, čte se odtud.

Pouští se po týdenním běhu a jeho výstup se vloží do README místo tabulky:

    python3 prehled_cisel.py            # markdown tabulka na stdout
    python3 prehled_cisel.py --json     # tytéž údaje strojově

Čte JEN hotová data v `data/` a číselníky v `config/`. Když soubor chybí,
řádek se vynechá a napíše se o tom na stderr — chybějící číslo je lepší
než vymyšlené.
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

KOREN = Path(__file__).resolve().parent


def nacti(cesta: str):
    """Načte JSON z kořene projektu; None, když soubor není."""
    p = KOREN / cesta
    if not p.exists():
        print(f"  … chybí {cesta}, řádek vynechán", file=sys.stderr)
        return None
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def cislo(n: int) -> str:
    """12936 → „12 936" — mezera po tisícovkách, stejná jako dosud v README."""
    return f"{n:,}".replace(",", " ")


def spocitej() -> dict:
    u: dict = {}

    # ---- usnesení: jednání, body, otagované body -------------------------
    # Jeden soubor = jedno jednání, `body` = body programu s usnesením.
    jednani = sorted(glob.glob(str(KOREN / "data/usneseni/*/*/*.json")))
    if jednani:
        datumy, bodu, otagovanych = [], 0, 0
        for f in jednani:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
            body = d.get("body") or []
            bodu += len(body)
            otagovanych += sum(1 for b in body if b.get("tagy"))
            if d.get("datum"):
                datumy.append(d["datum"])
        u["jednani"] = len(jednani)
        u["jednani_od"] = min(datumy)[:4]
        u["jednani_do"] = max(datumy)[:4]
        u["bodu_usneseni"] = bodu
        u["bodu_otagovanych"] = otagovanych

    tagy = nacti("config/tagy.json")
    if tagy is not None:
        u["tagu"] = len(tagy.get("tagy", tagy) or [])

    # ---- hlasování a jmenovité hlasy ------------------------------------
    soubory = glob.glob(str(KOREN / "data/hlasovani/*/*/*.json"))
    if soubory:
        hlasovani = jmenovitych = 0
        for f in soubory:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
            for h in d.get("hlasovani") or []:
                hlasovani += 1
                jmenovitych += len(h.get("jmenovite") or [])
        u["hlasovani"] = hlasovani
        u["jmenovitych_hlasu"] = jmenovitych

    if (d := nacti("data/slibnik/ukoly.json")) is not None:
        u["ukolu"] = d["souhrn"]["ukolu"]
        u["ukolu_s_terminem"] = d["souhrn"]["s_terminem"]

    if (d := nacti("data/obdobi/ucet.json")) is not None:
        u["hlasovani_v_uctu"] = d["souhrn"]["hlasovani"]

    if (d := nacti("data/komise/prehled.json")) is not None:
        u["zapisu_komisi"] = d["souhrn"]["zapisu"]
        u["doporuceni_rade"] = d["souhrn"]["doporuceni_rade"]

    if (d := nacti("data/informace106/prehled.json")) is not None:
        u["zadosti_rozebranych"] = d["souhrn"]["rozebranych"]
        u["zadosti_v_rejstriku"] = d["souhrn"]["v_rejstriku"]

    # ---- smlouvy: JEN z hotové agregace, nikdy součtem řádků ------------
    # Sečíst `smlouvy` přes soubory v `data/penize/smlouvy/` dá 6 996, a to je
    # o 312 víc, než kolik má město s holdingem smluv. Dvě různé příčiny:
    #
    #  - **33 smluv je nemocnice**, která už městu nepatří (`vlastnictvi:
    #    "mimo_mesto"`). Sleduje se dál kvůli významu pro město, ale do
    #    součtů holdingu nevstupuje.
    #  - **279 smluv leží ve dvou souborech naráz.** Smlouva mezi dvěma členy
    #    holdingu je u obou, takže součet řádků ji počítá dvakrát.
    #
    # `agregace_penez` obojí řeší a publikuje jediný správný počet; brát ho
    # odjinud znamená nadsazené číslo. Tohle je taky důvod, proč se počet
    # subjektů bere odtud a ne z `config/subjekty.json`: konfigurace vede
    # nemocnici mezi subjekty, holding v agregaci ji správně nemá.
    if (d := nacti("data/penize/agregace/souhrn.json")) is not None:
        u["smluv"] = d["celkem"]["smluv"]
        u["subjektu_holdingu"] = len(d["holding"])

    if (d := nacti("data/penize/agregace/protistrany.json")) is not None:
        protistrany = d["protistrany"]
        u["protistran"] = len(protistrany)
        roky = [r for p in protistrany for r in (p.get("po_letech") or {}) if str(r).isdigit()]
        if roky:
            u["protistrany_od"], u["protistrany_do"] = min(roky), max(roky)

    if (d := nacti("data/rozpocet/prehled/po_letech.json")) is not None:
        roky = [str(r["rok"]) for r in d.get("roky") or [] if r.get("rok")]
        if roky:
            u["rozpocet_od"], u["rozpocet_do"] = min(roky), max(roky)

    if (d := nacti("data/vysvedceni/audit.json")) is not None:
        u["projektu"] = d["souhrn"]["projektu"]
        u["slibu"] = d["souhrn"]["slibu"]

    if (d := nacti("data/firmy/subjekty.json")) is not None:
        u["firem_ares"] = len(d["subjekty"])

    if (d := nacti("data/zpravodaj/cisla.json")) is not None:
        u["cisel_zpravodaje"] = len(d)
        klice = sorted((c["rok"], int(c["mesic"])) for c in d if c.get("rok") and c.get("mesic"))
        if klice:
            u["zpravodaj_od"] = f"{klice[0][1]:02d}/{klice[0][0]}"
            u["zpravodaj_do"] = f"{klice[-1][1]:02d}/{klice[-1][0]}"
        # Jeden soubor = jeden článek, adresář = jedno číslo.
        u["clanku_zpravodaje"] = len(glob.glob(str(KOREN / "data/zpravodaj/clanky/*/*.json")))

    if (d := nacti("data/lide/osobnosti.json")) is not None:
        u["osobnosti"] = len(d)
        u["kategorii_osobnosti"] = len({o["kategorie"] for o in d if o.get("kategorie")})

    if (d := nacti("data/media/clanky.json")) is not None:
        u["medialnich_clanku"] = len(d)
        roky = sorted(c["datum"][:4] for c in d if c.get("datum"))
        if roky:
            u["media_od"], u["media_do"] = roky[0], roky[-1]

    if (d := nacti("data/retez/retezy.json")) is not None:
        u["retezu"] = d["statistika"]["retezu"]

    cykly = KOREN / "data/opendata/volby/cykly"
    if cykly.is_dir():
        u["volebnich_cyklu"] = len(list(cykly.glob("*")))

    if (d := nacti("data/diagramy/index.json")) is not None:
        u["diagramu"] = d["diagramu"]

    if (d := nacti("data/vydani/index.json")) is not None:
        u["vydani"] = len(d)

    return u


def tabulka(u: dict) -> str:
    """Markdown tabulka pro README. Řádek se vypíše jen s daty, která jsou."""
    radky: list[tuple[str, str]] = []

    def pridej(popis: str, *klice: str, sablona: str = "") -> None:
        if any(k not in u for k in klice):
            return
        radky.append((popis, sablona.format(*[
            cislo(u[k]) if isinstance(u[k], int) else u[k] for k in klice])))

    pridej("jednání rady a zastupitelstva", "jednani", "jednani_od", "jednani_do",
           sablona="**{0}** ({1}–{2})")
    # Dokud je otagované všechno, čte se to jako dosud. Kdyby tagování část
    # bodů minulo, věta to řekne — jinak by README tvrdilo, že jsou otagované
    # všechny, a to je právě ten druh tichého nepřesna, kterému se tu vyhýbáme.
    if u.get("bodu_usneseni") == u.get("bodu_otagovanych"):
        pridej("bodů usnesení", "bodu_usneseni", "tagu",
               sablona="**{0}**, otagovaných podle {1} témat")
    else:
        pridej("bodů usnesení", "bodu_usneseni", "bodu_otagovanych", "tagu",
               sablona="**{0}**, z toho {1} otagovaných podle {2} témat")
    pridej("hlasování", "hlasovani", "jmenovitych_hlasu",
           sablona="**{0}**, z toho **{1} jmenovitých hlasů**")
    pridej("uložených úkolů ve slibníku", "ukolu", "ukolu_s_terminem",
           sablona="**{0}**, z toho {1} s termínem")
    pridej("hlasování od voleb 2022 na účtu období", "hlasovani_v_uctu", sablona="**{0}**")
    pridej("zápisů z komisí a výborů", "zapisu_komisi", "doporuceni_rade",
           sablona="**{0}**, z nich {1} doporučení radě")
    pridej("žádostí o informace podle stovky šestky", "zadosti_rozebranych",
           "zadosti_v_rejstriku", sablona="**{0}** rozebraných ze {1} v rejstříku")
    pridej("smluv v registru", "smluv", "subjektu_holdingu",
           sablona="**{0}** za {1} subjektů městského holdingu")
    pridej("protistran města", "protistran", "protistrany_od", "protistrany_do",
           sablona="**{0}**, roky {1}–{2}")
    pridej("rozpočet z Monitoru státní pokladny", "rozpocet_od", "rozpocet_do",
           sablona="roky **{0}–{1}**, po konsolidaci")
    pridej("prověřených projektů ve vysvědčení koalici", "projektu", "slibu",
           sablona="**{0}** a {1} slibů z programového prohlášení")
    pridej("firem se sídlem ve městě (ARES)", "firem_ares", sablona="**{0}**")
    pridej("čísel zpravodaje", "cisel_zpravodaje", "zpravodaj_od", "zpravodaj_do",
           "clanku_zpravodaje",
           sablona="**{0}** ({1}–{2}), rozebraných na **{3} článků**")
    pridej("osobností", "osobnosti", "kategorii_osobnosti",
           sablona="**{0}** v {1} kategoriích")
    pridej("mediálních článků", "medialnich_clanku", "media_od", "media_do",
           sablona="**{0}** ({1}–{2})")
    pridej("spojení usnesení → smlouva → peníze", "retezu", sablona="**{0}**")
    pridej("volebních cyklů po okrscích", "volebnich_cyklu", sablona="**{0}**")
    pridej("schémat vykreslených z dat", "diagramu", sablona="**{0}**")
    pridej("týdenních vydání", "vydani", sablona="**{0}** včetně zpětného archivu")

    return "\n".join(["| | |", "|---|---|", *(f"| {p} | {v} |" for p, v in radky)])


def main() -> int:
    p = argparse.ArgumentParser(description="Čísla pro tabulku „Co je v datech“ v README")
    p.add_argument("--json", action="store_true", help="vypsat strojově místo tabulky")
    args = p.parse_args()

    u = spocitej()
    if args.json:
        print(json.dumps(u, ensure_ascii=False, indent=2))
    else:
        print(tabulka(u))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
