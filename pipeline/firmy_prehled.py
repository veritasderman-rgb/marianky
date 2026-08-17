"""Přehled firem ve městě — co z 4 177 subjektů stojí za pozornost.

Modul O2, navazuje na `scrapers/firmy.py`.

CO TENHLE PŘEHLED DĚLÁ A CO NEDĚLÁ
----------------------------------
Nedělá pořadí důležitosti. Obrat ani počet zaměstnanců ARES nezveřejňuje,
takže "největší firma ve městě" je údaj, který z dostupných dat prostě
nejde postavit — a odhadovat ho podle právní formy nebo stáří by byl
dohad vydávaný za zjištění.

Místo toho staví ŽEBŘÍČKY PODLE DOLOŽITELNÝCH KRITÉRIÍ. Každé kritérium má
jeden zdroj a jednu měřitelnou hodnotu:

  obchoduje_s_mestem  registr smluv — kolik korun a v kolika smlouvách
                      (data/penize/agregace/protistrany.json)
  mestsky_holding     město v subjektu drží podíl (config/subjekty.json)
  velikost            kategorie počtu pracovníků z registru ekonomických
                      subjektů — pásmo, ne číslo
  stari               datum vzniku z ARES
  obor                převažující činnost CZ-NACE z registru ekonomických
                      subjektů

U každé firmy v přehledu je uvedeno, které kritérium ji tam dostalo a
s jakou hodnotou. "Největší příjemce peněz od města" je fakt a smí se
napsat. Cokoliv o tom, jestli je to dobře, do dat nepatří.

KRITÉRIUM "OBOR" JE VÝBĚR, NE MĚŘENÍ
------------------------------------
Seznam oborů, které se u lázeňského města sledují zvlášť (ubytování,
stravování, zdravotní péče, lázeňství, doprava), je náš výběr. Je proto
vypsaný v `OBORY_LAZENSKEHO_MESTA` a v metodice výstupu, aby bylo vidět,
co se do něj počítá a co ne. Firma se do žebříčku nedostane za to, že
"působí v lázeňství" — dostane se tam za konkrétní kód CZ-NACE.

ČASOVÁ OSA MĚŘÍ NĚCO JINÉHO, NEŽ SE ZDÁ
---------------------------------------
"Vzniky po letech" NEJSOU "kolik firem v tom roce vzniklo". Jsou to
"kolik DNES EXISTUJÍCÍCH subjektů v tom roce vzniklo" — adresní index ARES
zaniklé firmy nevede, takže starší roky jsou tím osekané tím víc, čím jsou
starší. Výstup to nese v poli `mereni` u každé osy, aby si to nikdo
nespletl s demografií firem.
"""
from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import Log, ZdrojSelhal, nacti, nacti_config, uloz  # noqa: E402
from scrapers.firmy import nace_sekce  # noqa: E402

# Kategorie počtu pracovníků z RES. Kódy jsou vzestupné podle velikosti,
# takže se dají porovnávat — 230 ("25 - 49") je víc než 210 ("10 - 19").
PRAH_ZAMESTNAVATELE = "210"   # od 10 zaměstnanců výš
PRAH_VELKY = "310"            # od 100 zaměstnanců výš

# Rok, do kterého se firma počítá jako pamětník. Sametová revoluce +
# první porevoluční vlna: co vzniklo do konce roku 1995 a dodnes funguje,
# přežilo ve městě třicet let.
ROK_PAMETNIKA = 1995

# Obory, které se u lázeňského města sledují zvlášť. Kódy CZ-NACE, ne
# slovní popis — aby šlo zpětně ověřit, co se do skupiny počítá.
OBORY_LAZENSKEHO_MESTA: dict[str, str] = {
    "55": "ubytování",
    "56": "stravování a pohostinství",
    "86": "zdravotní péče (včetně lázeňské)",
    "96": "ostatní osobní služby (lázně, wellness)",
    "49": "pozemní doprava",
    "79": "cestovní agentury a kanceláře",
    "93": "sportovní, zábavní a rekreační činnosti",
}

# Právní formy, které znamenají zapsanou právnickou osobu s rejstříkem,
# ne podnikající fyzickou osobu. Kódy z číselníku ARES.
FORMY_FYZICKYCH_OSOB = {"100", "101", "102", "105", "107", "424", "425"}

# Formy s povinným základním kapitálem a plným zveřejněním v obchodním
# rejstříku. Nejsou "důležitější" — jen o nich existuje víc doložených dat.
FORMY_S_KAPITALEM = {"121": "akciová společnost", "205": "družstvo",
                     "922": "evropská společnost"}

# Formy, které ze své podstaty nepodnikají. Ve statistice oborů dělají
# zmatek: 396 společenství vlastníků jednotek má v CZ-NACE "činnosti v
# oblasti nemovitostí", takže by z bytových domů vyšlo, že hlavní obor
# Mariánských Lázní je realitní byznys. Nevyhazují se — dostávají vlastní
# pohled, aby šlo obojí porovnat.
FORMY_NEPODNIKATELSKE = {
    "145": "společenství vlastníků jednotek",
    "706": "spolek",
    "736": "pobočný spolek",
    "707": "odborová organizace",
    "722": "evidovaná církevní právnická osoba",
    "761": "honební společenstvo",
    "117": "nadace",
    "118": "nadační fond",
    "422": "organizační složka zahraničního nadačního fondu",
    "751": "zájmové sdružení právnických osob",
}

# Kritéria, která firmu do přehledu dostanou sama o sobě. Ostatní jsou
# doplňující: říkají o firmě něco doloženého, ale platí pro tak široký
# okruh subjektů, že by z přehledu udělaly seznam všech firem ve městě.
KRITERIA_SILNA = {"mestsky_holding", "sledovany_subjekt", "obchoduje_s_mestem",
                  "zamestnavatel", "pametnik", "dotace"}


# --------------------------------------------------------------------------
# Pomocníci
# --------------------------------------------------------------------------

def _rok(datum: str | None) -> int | None:
    if not datum or len(datum) < 4 or not datum[:4].isdigit():
        return None
    return int(datum[:4])


def _oddil(kod: str | None) -> str | None:
    """Dvoumístný oddíl CZ-NACE. Kratší kódy oddíl neurčují."""
    if not kod:
        return None
    cislice = "".join(c for c in kod if c.isdigit())
    return cislice[:2] if len(cislice) >= 2 else None


def _je_fyzicka_osoba(f: dict) -> bool:
    return f.get("pravni_forma") in FORMY_FYZICKYCH_OSOB


def _rada_let(roky: list[int]) -> list[int]:
    """Souvislá řada let. Chybějící rok je nula, ne díra.

    PLAN.md to říká u peněz a platí to tady stejně: přeskočený rok v časové
    ose je tvrzení, že se nic nestalo, vykreslené jako by tam nebyl.
    """
    if not roky:
        return []
    return list(range(min(roky), max(roky) + 1))


# --------------------------------------------------------------------------
# Načtení vstupů
# --------------------------------------------------------------------------

def nacti_dotace(log: Log) -> dict[str, dict]:
    """Dotace podle příjemce z už sklizených dat modulu peněz.

    POZOR NA VÝKLAD: `data/penize/dotace/` obsahuje dotace jen pro subjekty
    městského holdingu — pro ně je sklidil modul A3. O dotacích ostatních
    firem ve městě projekt data NEMÁ. Kritérium "dotace" tedy u firmy mimo
    holding neznamená "nedostává dotace", ale "nevíme". Proto se nikde
    neukládá jako false a v metodice výstupu je to napsané.
    """
    from lib.core import DATA  # lokálně, ať je vidět, že sáháme na cizí data

    slozka = DATA / "penize" / "dotace"
    if not slozka.exists():
        log.info("dotace nejsou sklizené, kritérium se nepoužije")
        return {}

    podle_ica: dict[str, dict] = {}
    for soubor in sorted(slozka.glob("*.json")):
        obsah = nacti(soubor)
        if not obsah or not obsah.get("ico"):
            continue
        polozky = obsah.get("dotace") or []
        if not polozky:
            continue
        podle_ica[obsah["ico"]] = {
            "pocet": len(polozky),
            # Dotace bez uvedené částky se počítá do `pocet`, do součtu ne —
            # stejně jako smlouva bez ceny v modulu peněz.
            "celkem_czk": round(sum(d.get("castka_czk") or 0 for d in polozky), 2),
            "poskytovatele": sorted({d.get("poskytovatel") for d in polozky
                                     if d.get("poskytovatel")}),
        }
    log.info("dotace načteny", prijemcu=len(podle_ica))
    return podle_ica


def nacti_vstupy(log: Log) -> tuple[dict, dict[str, dict], dict[str, dict], dict[str, dict]]:
    data = nacti("firmy/subjekty.json")
    if not data or not data.get("subjekty"):
        raise ZdrojSelhal(
            "Chybí data/firmy/subjekty.json. Spusť nejdřív `python3 scrapers/firmy.py`."
        )
    log.info("načteno subjektů", pocet=len(data["subjekty"]),
             ares_hlasi=data.get("uplnost", {}).get("ares_hlasi"))

    # Protistrany města z registru smluv. Klíč je IČO, takže se firmy
    # spárují přesně; protistrany bez IČO (klic_dle: "nazev") se párovat
    # nedají a do propojení nevstupují — párovat je podle názvu by
    # vyrábělo shody, které nikdo neověřil.
    agregace = nacti("penize/agregace/protistrany.json") or {}
    protistrany = {
        p["ico"]: p for p in agregace.get("protistrany", [])
        if p.get("klic_dle") == "ico" and p.get("ico")
    }
    bez_ica = sum(1 for p in agregace.get("protistrany", []) if p.get("klic_dle") != "ico")
    log.info("protistrany města z registru smluv", s_icem=len(protistrany), bez_ica=bez_ica)

    holding = {s["ico"]: s for s in nacti_config("subjekty.json")["subjekty"] if s.get("ico")}

    # Ruční doplňky z Hlídače státu (obrat, počet zaměstnanců, vazby osob).
    # Nepovinné — bez nich přehled funguje, jen bez těchhle údajů.
    doplnky_soubor = nacti("firmy/hlidac_doplnky.json") or {}
    doplnky = {d["ico"]: d for d in doplnky_soubor.get("subjekty", []) if d.get("ico")}
    if doplnky:
        log.info("doplňky z Hlídače státu", subjektu=len(doplnky))

    return data, protistrany, holding, doplnky


# --------------------------------------------------------------------------
# Kritéria
# --------------------------------------------------------------------------

def kriteria_firmy(f: dict, protistrany: dict[str, dict], holding: dict[str, dict],
                   kategorie: dict[str, str], dotace: dict[str, dict]) -> list[dict]:
    """Doložitelné důvody, proč firma v přehledu je. Každý s hodnotou i zdrojem."""
    duvody: list[dict] = []
    ico = f.get("ico")

    if ico and ico in holding:
        h = holding[ico]
        # Nemocnice už městu nepatří (PROVOZ.md). Projekt ji sleduje dál, ale
        # napsat u ní "město drží podíl" by byla nepravda — vlastnictví se
        # proto čte z configu, ne z toho, že subjekt je na seznamu.
        mimo = h.get("vlastnictvi") == "mimo_mesto"
        duvody.append({
            "kod": "sledovany_subjekt" if mimo else "mestsky_holding",
            "popis": ("město v subjektu podíl nedrží; projekt ho sleduje kvůli "
                      "významu pro město"
                      if mimo else "město v subjektu drží podíl"),
            "hodnota": h.get("vlastnictvi"),
            "zdroj": "config/subjekty.json",
        })

    d = dotace.get(ico or "")
    if d:
        duvody.append({
            "kod": "dotace",
            "popis": "dotace evidované Hlídačem státu",
            "hodnota": d["celkem_czk"],
            "jednotka": "Kč",
            "dotaci": d["pocet"],
            "poskytovatelu": len(d["poskytovatele"]),
            "zdroj": "Hlídač státu — dotace",
        })

    if ico and ico in protistrany:
        p = protistrany[ico]
        duvody.append({
            "kod": "obchoduje_s_mestem",
            "popis": ("město subjektu platí" if p.get("smer") == "vydaj"
                      else "město od subjektu inkasuje"),
            "hodnota": p.get("celkem_czk"),
            "jednotka": "Kč",
            "smluv": p.get("smluv"),
            "smluv_bez_ceny": p.get("bez_ceny"),
            "prvni_rok": p.get("prvni_rok"),
            "posledni_rok": p.get("posledni_rok"),
            "vnitromestsky_prevod": p.get("interni"),
            "zdroj": "registr smluv přes Hlídač státu",
        })

    kat = f.get("zamestnancu_kategorie")
    if kat and kat >= PRAH_ZAMESTNAVATELE:
        duvody.append({
            "kod": "zamestnavatel",
            "popis": "kategorie počtu pracovníků podle registru ekonomických subjektů",
            "hodnota": kategorie.get(kat, kat),
            "kod_kategorie": kat,
            "zdroj": "ARES / registr ekonomických subjektů",
        })

    rok = _rok(f.get("datum_vzniku"))
    # Jen právnické osoby. Živnostenských listů vydaných po roce 1990 a dodnes
    # nezrušených je ve městě 700+ a stáří o nich neříká skoro nic — u zapsané
    # firmy, která ve městě funguje třicet let, ano.
    if (rok and rok <= ROK_PAMETNIKA and f.get("stav") == "aktivni"
            and not _je_fyzicka_osoba(f)):
        duvody.append({
            "kod": "pametnik",
            "popis": f"právnická osoba vzniklá do konce roku {ROK_PAMETNIKA}, stále aktivní",
            "hodnota": f.get("datum_vzniku"),
            "zdroj": "ARES",
        })

    oddil = _oddil(f.get("nace_prevazujici"))
    if oddil in OBORY_LAZENSKEHO_MESTA and not _je_fyzicka_osoba(f):
        duvody.append({
            "kod": "obor_lazenskeho_mesta",
            "popis": f"převažující činnost: {OBORY_LAZENSKEHO_MESTA[oddil]}",
            "hodnota": f.get("nace_prevazujici"),
            "nazev_cinnosti": f.get("nace_prevazujici_nazev"),
            "zdroj": "ARES / registr ekonomických subjektů",
        })

    forma = f.get("pravni_forma")
    if forma in FORMY_S_KAPITALEM:
        duvody.append({
            "kod": "forma_s_kapitalem",
            "popis": f"{FORMY_S_KAPITALEM[forma]} — povinný základní kapitál "
                     "a plné zveřejnění v obchodním rejstříku",
            "hodnota": f.get("pravni_forma_nazev"),
            "zdroj": "ARES",
        })

    return duvody


def _radici_klic(zaznam: dict) -> tuple:
    """Řazení přehledu. Pravidlo je vypsané v metodice výstupu.

    Nejdřív doložená velikost (kategorie pracovníků), pak objem obchodu
    s městem, pak stáří. Není to škála důležitosti — je to pořadí sloupců,
    podle kterých se řadí, aby výstup nebyl náhodný.
    """
    kat = zaznam.get("zamestnancu_kategorie") or "000"
    penize = 0.0
    for k in zaznam["kriteria"]:
        if k["kod"] == "obchoduje_s_mestem" and isinstance(k.get("hodnota"), (int, float)):
            penize = float(k["hodnota"])
    rok = _rok(zaznam.get("datum_vzniku")) or 9999
    return (kat, penize, -rok)


# --------------------------------------------------------------------------
# Výstupy
# --------------------------------------------------------------------------

def prehled_dulezitych(firmy: list[dict], protistrany: dict[str, dict],
                       holding: dict[str, dict], kategorie: dict[str, str],
                       doplnky: dict[str, dict], dotace: dict[str, dict],
                       log: Log) -> dict:
    vybrane: list[dict] = []
    for f in firmy:
        duvody = kriteria_firmy(f, protistrany, holding, kategorie, dotace)
        if not any(d["kod"] in KRITERIA_SILNA for d in duvody):
            continue
        zaznam = {
            "ico": f.get("ico"),
            "nazev": f.get("nazev"),
            "pravni_forma_nazev": f.get("pravni_forma_nazev"),
            "stav": f.get("stav"),
            "datum_vzniku": f.get("datum_vzniku"),
            "datum_zaniku": f.get("datum_zaniku"),
            "adresa": f.get("adresa"),
            "sidlo_v_obci": f.get("sidlo_v_obci"),
            "obor": f.get("nace_prevazujici_nazev"),
            "obor_kod": f.get("nace_prevazujici"),
            "obor_sekce": f.get("nace_sekce_nazev"),
            "zamestnancu_kategorie": f.get("zamestnancu_kategorie"),
            "zamestnancu_rozsah": f.get("zamestnancu_rozsah"),
            "kriteria": duvody,
            "kriterii": len(duvody),
        }
        d = doplnky.get(f.get("ico") or "")
        if d:
            # Údaje z Hlídače státu jsou pásma, ne čísla, a mají vlastní
            # datum sběru — drží se odděleně od dat z ARES.
            zaznam["hlidac_statu"] = {
                "obrat_pasmo": d.get("obrat_pasmo"),
                "zamestnancu_pasmo": d.get("zamestnancu_pasmo"),
                "obor": d.get("obor"),
                "platce_dph": d.get("platce_dph"),
                "osob_ve_vedeni": d.get("osob_ve_vedeni"),
                "osoby_s_vazbou_na_politiku": d.get("osoby_s_vazbou_na_politiku"),
                "dcerine_spolecnosti": d.get("dcerine_spolecnosti"),
                "odkaz": d.get("odkaz"),
            }
        vybrane.append(zaznam)

    vybrane.sort(key=_radici_klic, reverse=True)
    log.info("firem splnilo alespoň jedno silné kritérium", pocet=len(vybrane))

    podle_kriteria = Counter()
    for z in vybrane:
        for k in z["kriteria"]:
            podle_kriteria[k["kod"]] += 1

    return {
        "generovano": time.strftime("%Y-%m-%d"),
        "metodika": {
            "vyber": (
                "V přehledu je subjekt, který splnil aspoň jedno ze silných "
                "kritérií: městský holding, obchod s městem, doložený počet "
                "zaměstnanců, dotace, nebo právnická osoba starší roku "
                f"{ROK_PAMETNIKA}. Obor a právní forma se u firmy zapisují, "
                "ale samy do přehledu nikoho nedostanou — platí pro tak "
                "široký okruh, že by z přehledu byl seznam všech firem."
            ),
            "silna_kriteria": sorted(KRITERIA_SILNA),
            "razeni": (
                "kategorie počtu pracovníků, pak objem obchodu s městem, pak "
                "stáří firmy. Není to škála důležitosti — jen pořadí sloupců."
            ),
            "obrat": (
                "ARES obrat nezveřejňuje. Pásmo obratu je jen u firem "
                "doplněných z Hlídače státu a je to pásmo, ne číslo."
            ),
            "dotace": (
                "Dotace projekt sklidil jen pro subjekty městského holdingu. "
                "U ostatních firem chybějící kritérium 'dotace' znamená "
                "NEVÍME, ne 'dotace nedostává'."
            ),
            "obor_lazenskeho_mesta": OBORY_LAZENSKEHO_MESTA,
            "prah_zamestnavatele": PRAH_ZAMESTNAVATELE,
            "rok_pametnika": ROK_PAMETNIKA,
        },
        "pocty_podle_kriteria": dict(podle_kriteria.most_common()),
        "zebricky": zebricky(vybrane),
        "firmy": vybrane,
    }


def zebricky(vybrane: list[dict]) -> dict:
    """Pořadí podle jednotlivých kritérií, každé zvlášť.

    Míchat je do jednoho čísla důležitosti by znamenalo tvrdit, že se dá
    porovnat "sto zaměstnanců" s "osmdesát milionů od města". Nedá.
    """
    def _penize(z: dict) -> float:
        for k in z["kriteria"]:
            if k["kod"] == "obchoduje_s_mestem" and isinstance(k.get("hodnota"), (int, float)):
                return float(k["hodnota"])
        return 0.0

    def _strucne(z: dict, extra: dict) -> dict:
        return {"ico": z["ico"], "nazev": z["nazev"], "obor": z["obor"], **extra}

    zamestnavatele = [z for z in vybrane if z.get("zamestnancu_kategorie")]
    zamestnavatele.sort(key=lambda z: z["zamestnancu_kategorie"], reverse=True)

    protistrany = [z for z in vybrane if _penize(z) > 0]
    protistrany.sort(key=_penize, reverse=True)

    stare = [z for z in vybrane
             if any(k["kod"] == "pametnik" for k in z["kriteria"])]
    stare.sort(key=lambda z: z["datum_vzniku"] or "9999")

    lazenske = [z for z in vybrane
                if any(k["kod"] == "obor_lazenskeho_mesta" for k in z["kriteria"])]
    lazenske.sort(key=lambda z: (z.get("zamestnancu_kategorie") or "000"), reverse=True)

    return {
        "nejvetsi_zamestnavatele": [
            _strucne(z, {"zamestnancu_rozsah": z["zamestnancu_rozsah"]})
            for z in zamestnavatele[:40]
        ],
        "nejvetsi_protistrany_mesta": [
            _strucne(z, {"od_mesta_czk": _penize(z),
                         "zamestnancu_rozsah": z["zamestnancu_rozsah"]})
            for z in protistrany[:40]
        ],
        "nejdele_pusobici": [
            _strucne(z, {"datum_vzniku": z["datum_vzniku"]}) for z in stare[:40]
        ],
        "lazenstvi_a_cestovni_ruch": [
            _strucne(z, {"zamestnancu_rozsah": z["zamestnancu_rozsah"],
                         "datum_vzniku": z["datum_vzniku"]})
            for z in lazenske[:40]
        ],
    }


def prehled_oboru(firmy: list[dict], nace_nazvy: dict[str, str], log: Log) -> dict:
    """Čím se město živí — rozložení podle převažující činnosti."""
    sekce_vse = Counter()
    sekce_pravnicke = Counter()
    sekce_podnikatelske = Counter()
    oddily = Counter()
    oddily_podnikatelske = Counter()
    bez_oboru = 0
    bez_oboru_pravnicke = 0

    for f in firmy:
        kod = f.get("nace_prevazujici")
        pravnicka = not _je_fyzicka_osoba(f)
        podnika = f.get("pravni_forma") not in FORMY_NEPODNIKATELSKE
        if not kod:
            bez_oboru += 1
            if pravnicka:
                bez_oboru_pravnicke += 1
            continue
        sekce, nazev = nace_sekce(kod)
        if sekce:
            sekce_vse[(sekce, nazev)] += 1
            if pravnicka:
                sekce_pravnicke[(sekce, nazev)] += 1
            if podnika:
                sekce_podnikatelske[(sekce, nazev)] += 1
        oddil = _oddil(kod)
        if oddil:
            oddily[oddil] += 1
            if podnika:
                oddily_podnikatelske[oddil] += 1

    def _seznam(citac: Counter) -> list[dict]:
        return [{"sekce": s, "nazev": n, "subjektu": p}
                for (s, n), p in citac.most_common()]

    def _oddily(citac: Counter) -> list[dict]:
        return [{"oddil": o, "nazev": nace_nazvy.get(o), "subjektu": p}
                for o, p in citac.most_common(30)]

    log.info("obory spočteny", sekci=len(sekce_vse), bez_oboru=bez_oboru)

    return {
        "generovano": time.strftime("%Y-%m-%d"),
        "mereni": (
            "Počty subjektů podle PŘEVAŽUJÍCÍ činnosti z registru "
            "ekonomických subjektů. Ne podle obratu, tržeb ani zaměstnanců — "
            "ty údaje ARES nemá. Živnostník s nulovým obratem váží v tomhle "
            "grafu stejně jako lázeňská akciová společnost."
        ),
        "ktery_pohled_cist": (
            "Pro otázku 'čím se město živí' je nejblíž pravdě pohled "
            "sekce_podnikatelske_subjekty. Ostatní dva pohledy jsou v sekci L "
            "(nemovitosti) nafouknuté o 396 společenství vlastníků jednotek — "
            "bytové domy, ne realitní firmy."
        ),
        "vyrazene_formy_v_podnikatelskem_pohledu": FORMY_NEPODNIKATELSKE,
        "bez_urceneho_oboru": {
            "vsechny_subjekty": bez_oboru,
            "pravnicke_osoby": bez_oboru_pravnicke,
            "poznamka": (
                "Převažující činnost u nich RES neuvádí, nebo má jen kód 00 "
                "(volná živnost), což obor neurčuje. Není to nula, je to "
                "chybějící údaj."
            ),
        },
        "sekce_podnikatelske_subjekty": _seznam(sekce_podnikatelske),
        "sekce_vsechny_subjekty": _seznam(sekce_vse),
        "sekce_pravnicke_osoby": _seznam(sekce_pravnicke),
        "oddily_podnikatelske_subjekty": _oddily(oddily_podnikatelske),
        "oddily": _oddily(oddily),
    }


def casova_osa(firmy: list[dict], log: Log) -> dict:
    vzniky = Counter()
    zaniky = Counter()
    vzniky_pravnicke = Counter()
    bez_data_vzniku = 0

    for f in firmy:
        rok = _rok(f.get("datum_vzniku"))
        if rok is None:
            bez_data_vzniku += 1
        else:
            vzniky[rok] += 1
            if not _je_fyzicka_osoba(f):
                vzniky_pravnicke[rok] += 1
        rok_z = _rok(f.get("datum_zaniku"))
        if rok_z is not None:
            zaniky[rok_z] += 1

    roky = _rada_let(sorted(vzniky))
    log.info("časová osa vzniků", od=roky[0] if roky else None,
             do=roky[-1] if roky else None, bez_data=bez_data_vzniku)

    bezi = 0
    kumulativne = {}
    for r in roky:
        bezi += vzniky.get(r, 0)
        kumulativne[str(r)] = bezi

    return {
        "generovano": time.strftime("%Y-%m-%d"),
        "vzniky": {
            "mereni": (
                "Kolik DNES EXISTUJÍCÍCH subjektů vzniklo v daném roce. "
                "NENÍ to počet firem založených v tom roce: adresní index "
                "ARES zaniklé subjekty nevede, takže čím starší rok, tím víc "
                "je osekaný o firmy, které mezitím skončily."
            ),
            "po_letech": {str(r): vzniky.get(r, 0) for r in roky},
            "po_letech_pravnicke_osoby": {str(r): vzniky_pravnicke.get(r, 0) for r in roky},
            "kumulativne": kumulativne,
            "bez_data_vzniku": bez_data_vzniku,
            "chybejici_rok": "Chybějící rok v řadě je nula. Graf ho musí vykreslit, ne přeskočit.",
        },
        "zaniky": {
            "stav": "neuplne",
            "mereni": (
                "Datum výmazu má jen obchodní rejstřík a dotahuje se pouze "
                "u subjektů, které ARES vede jako zaniklé. Firmy vymazané "
                "dávno v adresním indexu ARES vůbec nejsou, takže tuhle osu "
                "NELZE číst jako 'kolik firem ve městě zaniklo'."
            ),
            "po_letech": {str(r): zaniky[r] for r in sorted(zaniky)},
            "dohledano_celkem": sum(zaniky.values()),
        },
    }


def propojeni_s_mestem(firmy: list[dict], protistrany: dict[str, dict],
                       holding: dict[str, dict], log: Log) -> dict:
    """Které firmy ve městě figurují v registru smluv města — párováno podle IČO."""
    ve_meste = {f["ico"]: f for f in firmy if f.get("ico")}
    napojene = []
    for ico, p in protistrany.items():
        f = ve_meste.get(ico)
        if f is None:
            continue
        napojene.append({
            "ico": ico,
            "nazev_ares": f.get("nazev"),
            "nazev_v_registru": p.get("nazev"),
            "smer": p.get("smer"),
            "celkem_czk": p.get("celkem_czk"),
            "smluv": p.get("smluv"),
            "smluv_bez_ceny": p.get("bez_ceny"),
            "prvni_rok": p.get("prvni_rok"),
            "posledni_rok": p.get("posledni_rok"),
            "aktivni_v_poslednim_roce": p.get("aktivni"),
            "vnitromestsky_prevod": p.get("interni"),
            "mestsky_holding": ico in holding,
            "po_letech": p.get("po_letech"),
            "obor": f.get("nace_prevazujici_nazev"),
            "stav": f.get("stav"),
            "adresa": f.get("adresa"),
        })

    napojene.sort(key=lambda z: z.get("celkem_czk") or 0, reverse=True)
    mimo_mesto = len(protistrany) - len(napojene)
    objem_ve_meste = sum(z["celkem_czk"] or 0 for z in napojene)
    objem_celkem = sum(p.get("celkem_czk") or 0 for p in protistrany.values())

    log.info("firem ve městě napojených na registr smluv", pocet=len(napojene),
             protistran_celkem=len(protistrany))

    return {
        "generovano": time.strftime("%Y-%m-%d"),
        "metodika": {
            "parovani": (
                "Výhradně podle IČO. Protistrany, které registr smluv vede "
                "bez IČO, se nepárují — shoda podle názvu by vyráběla vazby, "
                "které nikdo neověřil."
            ),
            "smer": (
                "vydaj = město platí (protistrana je dodavatel), prijem = "
                "město inkasuje. Přebírá se ze zdroje a nepřepisuje se."
            ),
            "vnitromestsky_prevod": (
                "true = protistrana je sama subjektem městského holdingu, "
                "takže jde o přesun peněz uvnitř města, ne o platbu ven."
            ),
        },
        "souhrn": {
            "protistran_mesta_s_icem": len(protistrany),
            "z_toho_se_sidlem_ve_meste": len(napojene),
            "z_toho_mimo_mesto": mimo_mesto,
            "objem_protistran_ve_meste_czk": round(objem_ve_meste, 2),
            "objem_vsech_protistran_czk": round(objem_celkem, 2),
        },
        "firmy": napojene,
    }


def souhrn(data: dict, firmy: list[dict], dulezite: dict, obory: dict,
           propojeni: dict, osa: dict) -> dict:
    stavy = Counter(f.get("stav") or "neznamy" for f in firmy)
    formy = Counter(f.get("pravni_forma_nazev") or "neuvedena" for f in firmy)
    fyzicke = sum(1 for f in firmy if _je_fyzicka_osoba(f))
    mimo_obec = sum(1 for f in firmy if f.get("sidlo_v_obci") is False)
    s_velikosti = sum(1 for f in firmy if f.get("zamestnancu_kategorie"))
    zamestnavatele = sum(1 for f in firmy
                         if (f.get("zamestnancu_kategorie") or "000") >= PRAH_ZAMESTNAVATELE)
    velci = sum(1 for f in firmy
                if (f.get("zamestnancu_kategorie") or "000") >= PRAH_VELKY)

    return {
        "generovano": time.strftime("%Y-%m-%d"),
        "zdroj": data.get("zdroj"),
        "obec": data.get("obec"),
        "uplnost": data.get("uplnost"),
        "subjektu_celkem": len(firmy),
        "podle_stavu": dict(stavy.most_common()),
        "pravnickych_osob": len(firmy) - fyzicke,
        "podnikajicich_fyzickych_osob": fyzicke,
        "sidlo_dnes_mimo_obec": {
            "pocet": mimo_obec,
            "poznamka": (
                "ARES je k městu váže historickou adresou. Dnes sídlí jinde."
            ),
        },
        "velikost": {
            "s_udajem_o_poctu_pracovniku": s_velikosti,
            "bez_udaje": len(firmy) - s_velikosti,
            "od_10_zamestnancu": zamestnavatele,
            "od_100_zamestnancu": velci,
            "poznamka": (
                "Registr ekonomických subjektů vede pásmo, ne číslo, a u "
                "většiny subjektů ho nevede vůbec. Chybějící údaj není nula."
            ),
        },
        "nejcastejsi_pravni_formy": dict(formy.most_common(8)),
        "nejcastejsi_obory": obory["sekce_vsechny_subjekty"][:8],
        "v_prehledu_dulezitych": len(dulezite["firmy"]),
        "napojenych_na_registr_smluv_mesta": propojeni["souhrn"]["z_toho_se_sidlem_ve_meste"],
        "vzniky_rozsah": {
            "od": min((int(r) for r in osa["vzniky"]["po_letech"]), default=None),
            "do": max((int(r) for r in osa["vzniky"]["po_letech"]), default=None),
        },
    }


# --------------------------------------------------------------------------
# Běh
# --------------------------------------------------------------------------

def main() -> None:
    log = Log("firmy_prehled")
    data, protistrany, holding, doplnky = nacti_vstupy(log)
    firmy = data["subjekty"]
    kategorie = (data.get("ciselniky") or {}).get("kategorie_pracovniku") or {}

    # Názvy oborů z číselníku, který uložil scraper. Doplňkově i z toho, co
    # je u jednotlivých subjektů — starší běhy scraperu číselník neukládaly.
    nace_nazvy: dict[str, str] = dict((data.get("ciselniky") or {}).get("cz_nace") or {})
    for f in firmy:
        for kod, nazev in zip(f.get("nace_vse") or [], f.get("nace_vse_nazvy") or []):
            if nazev:
                nace_nazvy.setdefault(kod, nazev)
        if f.get("nace_prevazujici") and f.get("nace_prevazujici_nazev"):
            nace_nazvy.setdefault(f["nace_prevazujici"], f["nace_prevazujici_nazev"])

    dotace = nacti_dotace(log)
    obory = prehled_oboru(firmy, nace_nazvy, log)
    osa = casova_osa(firmy, log)
    propojeni = propojeni_s_mestem(firmy, protistrany, holding, log)
    dulezite = prehled_dulezitych(firmy, protistrany, holding, kategorie,
                                  doplnky, dotace, log)
    prehled = souhrn(data, firmy, dulezite, obory, propojeni, osa)

    uloz("firmy/prehled/obory.json", obory)
    uloz("firmy/prehled/casova_osa.json", osa)
    uloz("firmy/prehled/mesto_a_firmy.json", propojeni)
    uloz("firmy/prehled/dulezite.json", dulezite)
    uloz("firmy/prehled/souhrn.json", prehled)

    log.pricti(len(firmy))
    log.uzavri()


if __name__ == "__main__":
    main()
