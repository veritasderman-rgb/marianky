"""Týdenní běh — spouští se v neděli ráno.

Orchestruje sběrače a vypíše souhrn. Běh je inkrementální: sběrače berou
jen to, co přibylo od minule, a využívají diskovou cache.

Zásada, kvůli které to celé stojí za to: když zdroj selže, běh to NAHLÁSÍ
a vydání to uvede. Rozdíl mezi "tento týden se nic nedělo" a "nepodařilo
se načíst" je to jediné, co dělá takový přehled důvěryhodným.
"""
from __future__ import annotations

import argparse
import importlib
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.core import uloz  # noqa: E402

# (modul, popis, povinný)
# Povinný krok, který selže, shodí běh na nenulový návratový kód —
# vydání bez usnesení nemá smysl vydávat. Nepovinný jen chybí.
KROKY: list[tuple[str, str, bool]] = [
    ("scrapers.usneseni",  "Usnesení rady a zastupitelstva", True),
    ("scrapers.hlasovani", "Jmenovitá hlasování",            True),
    ("scrapers.muml",      "Web města, deska, akce",         True),
    ("scrapers.snapshoty", "Hlídání změn na webu města",     False),
    ("scrapers.hlidac",    "Registr smluv, dotace, zakázky", True),
    ("scrapers.zpravodaj", "Nové číslo zpravodaje",          False),
    ("scrapers.media",     "Mediální monitoring",            False),
    ("scrapers.lide",      "Aktualizace osobností",          False),
    ("scrapers.zaznamy",   "Záznamy zastupitelstva",         False),
    ("scrapers.volby",     "Výsledky voleb po okrscích",     False),
    ("scrapers.csu",       "Statistiky ČSÚ o městě",         False),
    ("scrapers.firmy",     "Firmy se sídlem ve městě",       False),
    ("scrapers.podnikatele", "Podnikatelé z rejstříku",      False),
    # Pořadí je závazné: památky používají hranici obce z geodat
    # k dohledání chráněných území. Bez ní proběhnou taky, jen se omezí
    # na to, co uvádí katalog, a napíšou to do logu.
    ("scrapers.geodata",   "Geodata a volební okrsky",       False),
    ("scrapers.pamatky",   "Kulturní památky",               False),
    ("scrapers.uzemni_plan", "Územní plánování",             False),
    ("scrapers.monitor",   "Rozpočet z Monitoru st. pokladny", False),
    # Komise jsou místo, kde návrh vzniká dřív, než o něm hlasuje rada.
    # Sběr je pomalý (stovky PDF s tempem šetrným k webu města), proto
    # není povinný — když se nedoběhne, zbytek běhu tím netrpí.
    ("scrapers.komise",    "Komise, výbory a zápisy z jednání", False),
    # Poskytnuté informace podle stovky šestky. Jediný zdroj, kde je vidět
    # POPTÁVKA po informacích, ne jen to, co úřad zveřejnit chtěl.
    ("scrapers.informace106", "Žádosti podle zákona 106/1999", False),
]

# Pořadí je závazné: propojení a řetěz čtou výstup agregace peněz,
# vydání čte úplně všechno, takže musí být poslední.
NAVAZNE: list[tuple[str, str, bool]] = [
    ("pipeline.tagovani",       "Otagování usnesení",           True),
    ("pipeline.clanky",         "Rozbor článků zpravodaje",     False),
    ("pipeline.agregace_penez", "Agregace peněz po letech",     True),
    ("pipeline.propojeni",      "Propojení lidí, firem a peněz", False),
    ("pipeline.profily",        "Hlasovací profily",            False),
    ("pipeline.retez",          "Řetěz usnesení → smlouva → peníze", False),
    ("pipeline.prepis",         "Přepisy jednání",              False),
    # Osa čte výstup řetězu i propojení, proto stojí až za nimi.
    ("pipeline.casova_osa",     "Jednotná časová osa",          False),
    ("pipeline.firmy_prehled",  "Přehled firem ve městě",       False),
    ("pipeline.podnikatele_prehled", "Přehled podnikatelů",     False),
    ("pipeline.vydani",         "Sestavení týdenního vydání",   True),
    # Schémata čtou hotové výstupy ostatních modulů i seznam kroků z tohohle
    # souboru. Nejsou povinná: bez nich web funguje, jen stránka /diagramy
    # napíše, že se je nepodařilo spočítat.
    ("pipeline.komise_prehled", "Rozbor zápisů z komisí",       False),
    ("pipeline.informace106_prehled", "Rozbor žádostí o informace", False),
    ("pipeline.retez_komise",   "Řetěz komise → rada",          False),
    ("pipeline.diagramy",       "Schémata projektu a města",    False),
    # Znaky sekcí čtou hotové výstupy VŠECH ostatních modulů — včetně
    # přehledu komisí, žádostí a rejstříku schémat — takže stojí úplně
    # poslední. (Dřív běžely dřív a znaky těch sekcí byly o týden pozadu.)
    # Jediný háček: diagram „zdroje“ si ze znaků bere popisky sekcí, čte je
    # tedy z minulého běhu; je to jen doprovodný text uzlu a chybějící
    # popisek diagram snese. Nejsou povinné: web bez nich funguje, jen
    # dlaždice rozcestníku nemají obrázek dat.
    ("pipeline.znaky_sekci",    "Znaky sekcí pro rozcestník",   False),
]


def spust_krok(modul: str, popis: str, povinny: bool) -> dict:
    print(f"\n▸ {popis}  ({modul})", flush=True)
    vysledek = {"modul": modul, "popis": popis, "povinny": povinny}
    try:
        m = importlib.import_module(modul)
    except ModuleNotFoundError:
        print(f"  … modul {modul} zatím neexistuje, přeskakuji", flush=True)
        return {**vysledek, "stav": "chybi_modul"}

    if not hasattr(m, "main"):
        return {**vysledek, "stav": "chybi_main"}

    # Moduly si samy parsují argumenty přes argparse, tedy čtou sys.argv.
    # Bez téhle výměny by `run_tyden.py --bez-sberu` spadlo uvnitř modulu na
    # "unrecognized arguments: --bez-sberu" — přepínač patří rutině, ne jemu.
    puvodni_argv = sys.argv
    sys.argv = [modul.replace(".", "/") + ".py"]
    try:
        m.main()
        return {**vysledek, "stav": "ok"}
    except SystemExit as e:
        if e.code:
            print(f"  … skončil s kódem {e.code}", flush=True)
            return {**vysledek, "stav": "selhal", "chyba": f"SystemExit {e.code}"}
        return {**vysledek, "stav": "ok"}
    except Exception as e:  # noqa: BLE001
        print(f"  CHYBA: {e}", flush=True)
        traceback.print_exc(limit=3)
        return {**vysledek, "stav": "selhal", "chyba": str(e)[:300]}
    finally:
        sys.argv = puvodni_argv


def main() -> int:
    p = argparse.ArgumentParser(description="Týdenní běh projektu Naše Mariánky v přehledech")
    p.add_argument("--jen", nargs="*", help="Spustit jen vyjmenované moduly")
    p.add_argument("--bez-sberu", action="store_true", help="Přeskočit sběr, jen přepočítat")
    args = p.parse_args()

    zacatek = datetime.now(timezone.utc)
    dnes = zacatek.date()
    obdobi_od = dnes - timedelta(days=7)

    print("=" * 64)
    print("  NAŠE MARIÁNKY V PŘEHLEDECH — týdenní běh")
    print(f"  období {obdobi_od.strftime('%-d. %-m.')} – {dnes.strftime('%-d. %-m. %Y')}")
    print("=" * 64)

    vysledky = []
    plan = ([] if args.bez_sberu else KROKY) + NAVAZNE
    if args.jen:
        plan = [k for k in plan if any(j in k[0] for j in args.jen)]

    for modul, popis, povinny in plan:
        vysledky.append(spust_krok(modul, popis, povinny))

    # ---- souhrn ----
    ok = [v for v in vysledky if v["stav"] == "ok"]
    selhalo = [v for v in vysledky if v["stav"] == "selhal"]
    chybi = [v for v in vysledky if v["stav"] == "chybi_modul"]
    kriticke = [v for v in selhalo if v["povinny"]]

    print("\n" + "=" * 64)
    print(f"  hotovo: {len(ok)}   selhalo: {len(selhalo)}   chybí modul: {len(chybi)}")
    for v in selhalo:
        znacka = "!!" if v["povinny"] else " ·"
        print(f"  {znacka} {v['popis']}: {v.get('chyba', '')[:90]}")
    if kriticke:
        print("\n  POZOR: selhal povinný zdroj. Vydání musí u dotčené sekce")
        print("  explicitně uvést, že data chybí — nesmí vypadat, že se nic nedělo.")
    print("=" * 64)

    souhrn = {
        "datum": dnes.isoformat(),
        "obdobi_od": obdobi_od.isoformat(),
        "obdobi_do": dnes.isoformat(),
        "trvani_s": round((datetime.now(timezone.utc) - zacatek).total_seconds(), 1),
        "kroky": vysledky,
        "uspech": not kriticke,
    }
    uloz(f"logy/{dnes.isoformat()}/beh.json", souhrn)

    return 1 if kriticke else 0


if __name__ == "__main__":
    raise SystemExit(main())
