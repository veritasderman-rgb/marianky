"""Hlasovací profily zastupitelů a radních.

Vstup:  `data/hlasovani/{organ}/{rok}/{cj}.json`  (vyrábí `scrapers/hlasovani.py`)
        `data/usneseni/{organ}/{rok}/{cj}.json`   (kvůli `castka_czk` a `obdobi`)
        `data/lide/osobnosti.json`                (jen ke čtení — vlastní modul B1)
        `data/hlasovani/clenove.json`             (rejstřík hlasujících, kontrolní součty)
Výstup: `data/lide/profily.json`

--------------------------------------------------------------------------
!!! TENHLE SOUBOR OBSAHUJE ČÍSLA, NE HODNOCENÍ !!!
--------------------------------------------------------------------------
Nikde tu není „loajální", „rebel" ani „absentér" a nikdy tu být nesmí.
Ukládá se počet a podíl; co si o tom čtenář myslí, je jeho věc. Zvlášť
platí u účasti: nízká účast může znamenat nemoc nebo práci a data o důvodu
nevědí nic. Web smí zobrazit číslo, ne známku.

--------------------------------------------------------------------------
Šest stavů, ne tři
--------------------------------------------------------------------------
Zdroj kóduje nepřítomnost dvěma poli naráz: `hlas: "nepritomen"` plus
volitelný příznak `omluven: true`. Slévat to by zkreslovalo — omluvená
neúčast, neomluvená neúčast a „byl v sále, ale nehlasoval" jsou tři různé
věci. Profily proto pracují se šesti stavy:

    pro | proti | zdrzel | nehlasoval | omluven | nepritomen

kde `nepritomen` znamená **neomluvenou** neúčast (v datech 11 090 případů)
a `omluven` tu omluvenou (4 550 případů). Součet všech šesti = počet
příležitostí. Odvozené skupiny:

    hlasoval = pro + proti + zdrzel          (odevzdal hlas)
    pritomen = hlasoval + nehlasoval          (byl u toho)
    neucast  = omluven + nepritomen           (nebyl u toho)

--------------------------------------------------------------------------
!!! PŘÍZNAK OMLUVY VE STARŠÍCH DATECH NENÍ !!!
--------------------------------------------------------------------------
Zdroj začal omluvy zapisovat až u zastupitelstva od roku 2019 a u rady od
roku 2023 — ve starších zápisech je **každá** neúčast vedená jako
`nepritomen` bez příznaku. Není to tím, že by se dřív nikdo neomlouval;
zdroj to prostě neuvádí.

Číst z toho, že někdo „má 793 neomluvených absencí", by proto byla lež
o zdroji, ne údaj o člověku. Kde je to spolehlivé, říká top-level blok
`dostupnost_omluv` (podle orgánu a roku, včetně `spolehlive_od`) a u každého
profilu `rozliseni_omluv`. **Mimo spolehlivé období smí web zobrazit jen
souhrnné `neucast`, nikdy rozpad na omluven/nepritomen.**

--------------------------------------------------------------------------
Proč se procenta počítají z vlastních příležitostí
--------------------------------------------------------------------------
`prilezitosti` je počet hlasování, ve kterých se člověk **objevil na
jmenovité listině** — ne počet všech hlasování orgánu. Kdo nastoupil v půli
volebního období nebo sedí jen v zastupitelstvu a ne v radě, má jmenovku
u méně hlasování a počítat mu docházku z celku by z něj udělalo absentéra,
kterým není. Kolik z období člověk zabral, říká zvlášť pole
`podil_obdobi` v `po_obdobich` — tam je vidět neúplné období jako fakt,
ne jako propad docházky.

--------------------------------------------------------------------------
Malý vzorek
--------------------------------------------------------------------------
U řezů pod PRAH_MALY_VZOREK hlasování je procento zavádějící (jedno
hlasování z pěti dělá rovných 20 %). Každý řez proto nese vedle podílu
i absolutní počet a příznak `maly_vzorek`. Frontend má u `maly_vzorek:
true` zobrazit počet, ne procento.
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import DATA, Log, ZdrojSelhal, nacti, nacti_config, uloz  # noqa: E402

# Šest stavů, v pořadí, ve kterém se zobrazují.
STAVY = ("pro", "proti", "zdrzel", "nehlasoval", "omluven", "nepritomen")
ODEVZDANE = ("pro", "proti", "zdrzel")          # hlasoval
PRITOMNE = ("pro", "proti", "zdrzel", "nehlasoval")  # byl v sále

# Pod tímhle počtem hlasování se procento neinterpretuje.
PRAH_MALY_VZOREK = 20

# „Velká částka" u bodu usnesení. Milion je hranice, kterou zadává projekt.
PRAH_VELKA_CASTKA = 1_000_000

# Nad tímhle stropem je částka u bodu usnesení nedůvěryhodná — v datech jsou
# hodnoty typu 51 612 190 000 Kč u „Příspěvku do Fondu sportu", což je zjevně
# slepený letopočet s číslem. Částky vyrábí modul A1, my je neopravujeme; jen
# spočítáme, kolik jich je nad stropem, a hlásíme to ve výstupu. Objemy v Kč
# se proto v profilech vůbec nesčítají, publikují se jen počty hlasování.
STROP_ROZUMNE_CASTKY = 1_000_000_000

# Od jakého podílu omluvených neúčastí se bere, že zdroj omluvy v daném roce
# opravdu zapisuje. Nižší podíl znamená pár ojedinělých záznamů (rada 2015 má
# 7 omluv z 783 neúčastí) — z toho se rozpad omluven/nepritomen číst nedá.
PRAH_DOSTUPNOSTI_OMLUV = 0.5


# --------------------------------------------------------------------------
# Načtení a normalizace
# --------------------------------------------------------------------------

def _stav(zaznam: dict) -> str:
    """Převede zdrojový zápis hlasu na jeden ze šesti stavů.

    Zdroj nemá stav „omluven" jako hodnotu `hlas` — nese ho příznakem
    `omluven: true` u hlasu `nepritomen`. Bez tohohle rozpletení by omluvená
    a neomluvená neúčast splynuly.
    """
    hlas = zaznam.get("hlas")
    if hlas == "nepritomen" and zaznam.get("omluven"):
        return "omluven"
    return hlas


def _nacti_hlasovani(log: Log) -> list[dict]:
    """Načte všechna hlasování a zploští je na jeden seznam.

    Prázdný výsledek je chyba, ne prázdno — bez hlasování nemá profil smysl.
    """
    zaznamy: list[dict] = []
    neznamy_stav: Counter = Counter()
    for cesta in sorted((DATA / "hlasovani").glob("*/*/*.json")):
        soubor = nacti(cesta)
        if not isinstance(soubor, dict) or "hlasovani" not in soubor:
            raise ZdrojSelhal(f"{cesta} nemá očekávanou strukturu hlasování")
        organ, datum = soubor["organ"], soubor["datum"]
        for h in soubor["hlasovani"]:
            jmenovite = h.get("jmenovite") or []
            if not jmenovite:
                # Hlasování bez jmenovité listiny do profilů nepatří — nikomu
                # bychom ho nemohli připsat. Hlásíme, ať se to nezamlčí.
                log.chyba(f"hlasování {h.get('id')} nemá jmenovité hlasy")
                continue
            hlasy = []
            for j in jmenovite:
                stav = _stav(j)
                if stav not in STAVY:
                    neznamy_stav[stav] += 1
                    continue
                hlasy.append((j["osoba_id"], j.get("strana"), stav, j.get("jmeno")))
            zaznamy.append({
                "id": h["id"],
                "organ": organ,
                "datum": datum,
                "rok": datum[:4],
                "tagy": h.get("tagy") or [],
                "hlasy": hlasy,
            })
    if not zaznamy:
        raise ZdrojSelhal("v data/hlasovani nejsou žádná hlasování")
    if neznamy_stav:
        log.chyba(f"neznámé hodnoty hlasu: {dict(neznamy_stav)}")
    log.info("načteno hlasování", pocet=len(zaznamy))
    return zaznamy


def _nacti_usneseni(log: Log) -> tuple[dict[str, int | None], dict[str, str]]:
    """Z usnesení vytáhne částku a volební období pro každé hlasování.

    Klíčem je `hlasovani_id`; body bez něj se přeskočí (u nich se hlasování
    nedohledalo, viz PLAN.md).
    """
    castky: dict[str, int | None] = {}
    obdobi: dict[str, str] = {}
    nad_stropem = 0
    for cesta in sorted((DATA / "usneseni").glob("*/*/*.json")):
        soubor = nacti(cesta)
        if not isinstance(soubor, dict) or "body" not in soubor:
            raise ZdrojSelhal(f"{cesta} nemá očekávanou strukturu usnesení")
        for b in soubor["body"]:
            hid = b.get("hlasovani_id")
            if not hid:
                continue
            castka = b.get("castka_czk")
            castky[hid] = castka
            if castka is not None and castka > STROP_ROZUMNE_CASTKY:
                nad_stropem += 1
            if soubor.get("obdobi"):
                obdobi[hid] = soubor["obdobi"]
    if not castky:
        raise ZdrojSelhal("v data/usneseni nejsou žádné body s hlasovani_id")
    log.info("napojena usnesení", bodu=len(castky), nad_stropem_castky=nad_stropem)
    return castky, obdobi


# --------------------------------------------------------------------------
# Většina
# --------------------------------------------------------------------------

def _vetsina(hlasy: list[tuple]) -> str | None:
    """Nejčastější odevzdaný hlas. Při remíze vrací None.

    Počítá se z odevzdaných hlasů (pro/proti/zdrzel), ne z výsledku usnesení:
    v datech je `vysledek` u všech 12 349 hlasování „schvaleno", takže shoda
    s výsledkem by nic neměřila. Většina spočítaná ze skutečných hlasů
    aspoň odliší, kdo hlasoval jinak než sál.
    """
    c = Counter(s for _, _, s, _ in hlasy if s in ODEVZDANE)
    if not c:
        return None
    poradi = c.most_common()
    if len(poradi) > 1 and poradi[0][1] == poradi[1][1]:
        return None
    return poradi[0][0]


def _vetsina_ostatnich(hlasy_skupiny: list[str], vlastni_index: int) -> str | None:
    """Většina skupiny BEZ zkoumaného člověka. Při remíze nebo prázdnu None.

    Vlastní hlas se ze srovnávací základny vyjímá schválně — jinak by u
    dvoučlenného klubu vycházela shoda vždycky a u jednočlenného by se
    člověk porovnával sám se sebou.
    """
    c = Counter(h for i, h in enumerate(hlasy_skupiny) if i != vlastni_index)
    if not c:
        return None
    poradi = c.most_common()
    if len(poradi) > 1 and poradi[0][1] == poradi[1][1]:
        return None
    return poradi[0][0]


# --------------------------------------------------------------------------
# Souhrny
# --------------------------------------------------------------------------

def _podil(cast: int, celek: int) -> float | None:
    """Podíl, nebo None když není z čeho dělit. Nikdy nedělí nulou."""
    return round(cast / celek, 4) if celek else None


def _dostupnost_omluv(neucasti: dict[tuple[str, str], Counter]) -> dict:
    """Zjistí, od kdy zdroj u kterého orgánu vůbec zapisuje omluvy.

    `spolehlive_od` je nejstarší rok, od kterého už podíl omluvených neúčastí
    v žádném dalším roce neklesne pod práh. Před ním se rozpad
    omluven/nepritomen nesmí zobrazovat — chybí ve zdroji, ne v realitě.
    """
    dle_organu: dict[str, dict[str, dict]] = defaultdict(dict)
    for (organ, rok), c in neucasti.items():
        celkem_neucasti = c["omluven"] + c["nepritomen"]
        dle_organu[organ][rok] = {
            "neucasti": celkem_neucasti,
            "omluvenych": c["omluven"],
            "podil_omluvenych": _podil(c["omluven"], celkem_neucasti),
        }
    out = {}
    for organ, roky in dle_organu.items():
        serazene = sorted(roky)
        spolehlive_od = None
        # zprava doleva: jakmile rok propadne pod práh, spolehlivá řada končí
        for rok in reversed(serazene):
            if (roky[rok]["podil_omluvenych"] or 0) < PRAH_DOSTUPNOSTI_OMLUV:
                break
            spolehlive_od = rok
        for rok in serazene:
            roky[rok]["spolehlive"] = spolehlive_od is not None and rok >= spolehlive_od
        out[organ] = {
            "spolehlive_od": spolehlive_od,
            "po_letech": {r: roky[r] for r in serazene},
        }
    return out


def _souhrn(c: Counter) -> dict:
    """Jeden řez profilu: počty šesti stavů plus odvozené podíly."""
    prilezitosti = sum(c[s] for s in STAVY)
    hlasoval = sum(c[s] for s in ODEVZDANE)
    pritomen = sum(c[s] for s in PRITOMNE)
    return {
        "prilezitosti": prilezitosti,
        **{s: c[s] for s in STAVY},
        "pritomen": pritomen,
        "hlasoval": hlasoval,
        # Souhrnná neúčast je jediné číslo o absenci, které platí ve všech
        # letech — rozpad na omluven/nepritomen zdroj u starších zápisů nemá.
        "neucast": c["omluven"] + c["nepritomen"],
        "podil_pritomen": _podil(pritomen, prilezitosti),
        "podil_hlasoval": _podil(hlasoval, prilezitosti),
        # Rozložení se počítá z odevzdaných hlasů, ne z příležitostí —
        # jinak by neúčast tlačila „pro" dolů a vypadalo by to jako nesouhlas.
        "rozlozeni": {s: _podil(c[s], hlasoval) for s in ODEVZDANE} if hlasoval else None,
        "maly_vzorek": prilezitosti < PRAH_MALY_VZOREK,
    }


def _pomer(cast: int, celek: int, klic_celek: str, klic_cast: str) -> dict:
    """Dvojice počet/celek s podílem a příznakem malého vzorku."""
    return {
        klic_celek: celek,
        klic_cast: cast,
        "podil": _podil(cast, celek),
        "maly_vzorek": celek < PRAH_MALY_VZOREK,
    }


# --------------------------------------------------------------------------
# Hlavní agregace
# --------------------------------------------------------------------------

def spocti_profily(log: Log) -> dict:
    zaznamy = _nacti_hlasovani(log)
    castky, obdobi_dle_id = _nacti_usneseni(log)

    osobnosti = {o["id"]: o for o in (nacti("lide/osobnosti.json") or [])}
    clenove = {c["id"]: c for c in (nacti("hlasovani/clenove.json") or [])}
    tagy_nazvy = {t["id"]: t["nazev"] for t in nacti_config("tagy.json")["tagy"]}

    # --- akumulátory ---------------------------------------------------
    meta: dict[str, dict] = defaultdict(lambda: {
        "jmena": Counter(), "strany": Counter(), "organy": Counter(),
        "obdobi": Counter(), "prvni": None, "posledni": None,
        "strana_dle_roku": {},
    })
    celkem: dict[str, Counter] = defaultdict(Counter)
    po_letech: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    po_organech: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    po_obdobich: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    po_tagu: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    velke: dict[str, Counter] = defaultdict(Counter)

    # [základna, shodných] — základna jsou hlasování, kde člověk odevzdal hlas
    # a zároveň existovala jednoznačná většina.
    vetsina_celkem: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    vetsina_velke: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    vetsina_rok: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    vetsina_tag: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    jediny_odlisny: Counter = Counter()

    # [porovnatelných, odchylek] proti většině vlastního uskupení
    strana_celkem: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    strana_rok: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    strana_tag: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))

    # dvojice -> {"spolecnych", "shodnych", organ: [spolecnych, shodnych]}
    pary: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"spolecnych": 0, "shodnych": 0, "organy": defaultdict(lambda: [0, 0])})

    # kolik hlasování měl orgán v období celkem — základna pro `podil_obdobi`
    hlasovani_v_obdobi: Counter = Counter()
    # (organ, rok) -> stavy neúčasti, kvůli zjištění dostupnosti omluv
    neucasti: dict[tuple[str, str], Counter] = defaultdict(Counter)
    # osoba -> (organ, rok) -> příležitosti, kvůli `rozliseni_omluv`
    po_organ_rok: dict[str, Counter] = defaultdict(Counter)
    omluven_organ_rok: dict[str, Counter] = defaultdict(Counter)
    velkych_hlasovani = 0
    bez_vetsiny = 0

    # --- průchod hlasováními -------------------------------------------
    for z in zaznamy:
        organ, rok, hid = z["organ"], z["rok"], z["id"]
        obdobi = obdobi_dle_id.get(hid)
        castka = castky.get(hid)
        velke_hlasovani = castka is not None and castka > PRAH_VELKA_CASTKA
        if velke_hlasovani:
            velkych_hlasovani += 1
        if obdobi:
            hlasovani_v_obdobi[(organ, obdobi)] += 1

        vetsina = _vetsina(z["hlasy"])
        if vetsina is None:
            bez_vetsiny += 1

        # kdo se od většiny odchýlil (kvůli „byl jediný odlišný")
        odchylni = [o for o, _, s, _ in z["hlasy"]
                    if vetsina and s in ODEVZDANE and s != vetsina]
        if len(odchylni) == 1:
            jediny_odlisny[odchylni[0]] += 1

        # rozdělení podle uskupení — label strany je vždy ten zapsaný u
        # konkrétního hlasování, takže přejmenování klubu v čase nevadí
        # (ověřeno: „Město sobě" a SNK „MĚSTO SOBĚ" se v jednom hlasování
        # nikdy nepotkají, jde o tentýž klub ve dvou obdobích).
        skupiny: dict[str, list[tuple[str, str]]] = defaultdict(list)

        for osoba_id, strana, stav, jmeno in z["hlasy"]:
            m = meta[osoba_id]
            if jmeno:
                m["jmena"][jmeno] += 1
            if strana:
                m["strany"][strana] += 1
                m["strana_dle_roku"][rok] = strana
            m["organy"][organ] += 1
            if obdobi:
                m["obdobi"][obdobi] += 1
            if m["prvni"] is None or z["datum"] < m["prvni"]:
                m["prvni"] = z["datum"]
            if m["posledni"] is None or z["datum"] > m["posledni"]:
                m["posledni"] = z["datum"]

            celkem[osoba_id][stav] += 1
            po_letech[osoba_id][rok][stav] += 1
            po_organech[osoba_id][organ][stav] += 1
            po_organ_rok[osoba_id][(organ, rok)] += 1
            if stav in ("omluven", "nepritomen"):
                neucasti[(organ, rok)][stav] += 1
                if stav == "omluven":
                    omluven_organ_rok[osoba_id][(organ, rok)] += 1
            if obdobi:
                po_obdobich[osoba_id][obdobi][stav] += 1
            for t in z["tagy"]:
                po_tagu[osoba_id][t][stav] += 1
            if velke_hlasovani:
                velke[osoba_id][stav] += 1

            if stav in ODEVZDANE:
                if strana:
                    skupiny[strana].append((osoba_id, stav))
                if vetsina:
                    shoda = 1 if stav == vetsina else 0
                    vetsina_celkem[osoba_id][0] += 1
                    vetsina_celkem[osoba_id][1] += shoda
                    vetsina_rok[osoba_id][rok][0] += 1
                    vetsina_rok[osoba_id][rok][1] += shoda
                    for t in z["tagy"]:
                        vetsina_tag[osoba_id][t][0] += 1
                        vetsina_tag[osoba_id][t][1] += shoda
                    if velke_hlasovani:
                        vetsina_velke[osoba_id][0] += 1
                        vetsina_velke[osoba_id][1] += shoda

        # --- odchylky od vlastního uskupení ---
        for strana, clenove_skupiny in skupiny.items():
            if len(clenove_skupiny) < 2:
                continue  # sám za sebe se od sebe odchýlit nemůže
            stavy_skupiny = [s for _, s in clenove_skupiny]
            for i, (osoba_id, stav) in enumerate(clenove_skupiny):
                vetsina_klubu = _vetsina_ostatnich(stavy_skupiny, i)
                if vetsina_klubu is None:
                    continue
                odchylka = 1 if stav != vetsina_klubu else 0
                strana_celkem[osoba_id][0] += 1
                strana_celkem[osoba_id][1] += odchylka
                strana_rok[osoba_id][rok][0] += 1
                strana_rok[osoba_id][rok][1] += odchylka
                for t in z["tagy"]:
                    strana_tag[osoba_id][t][0] += 1
                    strana_tag[osoba_id][t][1] += odchylka

        # --- matice shody ---
        # Porovnávají se jen dvojice, kde OBA odevzdali hlas. Kdo chyběl,
        # s nikým nesouhlasil ani nesouhlasil — počítat neúčast jako neshodu
        # by z nemocného udělalo opozičníka.
        odevzdali = [(o, s) for o, _, s, _ in z["hlasy"] if s in ODEVZDANE]
        for i in range(len(odevzdali)):
            a_id, a_stav = odevzdali[i]
            for j in range(i + 1, len(odevzdali)):
                b_id, b_stav = odevzdali[j]
                klic = (a_id, b_id) if a_id < b_id else (b_id, a_id)
                p = pary[klic]
                shoda = 1 if a_stav == b_stav else 0
                p["spolecnych"] += 1
                p["shodnych"] += shoda
                p["organy"][organ][0] += 1
                p["organy"][organ][1] += shoda

    dostupnost = _dostupnost_omluv(neucasti)
    log.info("agregováno", osob=len(celkem), dvojic=len(pary),
             velkych_hlasovani=velkych_hlasovani, bez_jednoznacne_vetsiny=bez_vetsiny)
    log.info("omluvy zdroj zapisuje od",
             **{o: (v["spolehlive_od"] or "nikdy") for o, v in dostupnost.items()})

    # --- sousedé v matici pro rychlý přístup z profilu ------------------
    sousede: dict[str, list[dict]] = defaultdict(list)
    for (a, b), p in pary.items():
        for x, y in ((a, b), (b, a)):
            sousede[x].append({
                "id": y,
                "spolecnych": p["spolecnych"],
                "shodnych": p["shodnych"],
                "podil": _podil(p["shodnych"], p["spolecnych"]),
                "maly_vzorek": p["spolecnych"] < PRAH_MALY_VZOREK,
            })

    # --- sestavení profilů ---------------------------------------------
    profily = []
    for osoba_id in sorted(celkem):
        m = meta[osoba_id]
        c = celkem[osoba_id]
        osobnost = osobnosti.get(osoba_id)
        clen = clenove.get(osoba_id)

        # Jméno: nejdřív rejstřík osobností (B1), pak rejstřík hlasujících,
        # nakonec nejčastější podoba ze samotných hlasování.
        jmeno = ((osobnost or {}).get("jmeno")
                 or (clen or {}).get("jmeno")
                 or (m["jmena"].most_common(1)[0][0] if m["jmena"] else osoba_id))

        # sousedé: k nejbližším/nejvzdálenějším se berou jen dvojice s dost
        # společnými hlasováními, jinak by žebříček vedly náhody z pár schůzí
        blizci = sorted((s for s in sousede[osoba_id] if not s["maly_vzorek"]),
                        key=lambda s: (-s["podil"], -s["spolecnych"], s["id"]))
        for s in blizci:
            s["jmeno"] = (osobnosti.get(s["id"]) or clenove.get(s["id"]) or {}).get("jmeno", s["id"])
        _kolik = min(10, len(blizci) // 2)

        # kolik z příležitostí (a omluv) spadá do doby, kdy zdroj omluvy vede
        def _je_spolehlivy(organ_rok: tuple[str, str]) -> bool:
            od = dostupnost.get(organ_rok[0], {}).get("spolehlive_od")
            return od is not None and organ_rok[1] >= od

        _spolehlive = sum(n for kl, n in po_organ_rok[osoba_id].items()
                          if _je_spolehlivy(kl))
        _mimo = sum(n for kl, n in omluven_organ_rok[osoba_id].items()
                    if not _je_spolehlivy(kl))

        # kontrolní součet proti rejstříku hlasujících
        kontrola = None
        if clen and clen.get("hlasu"):
            nase = {o: sum(v[s] for s in STAVY) for o, v in po_organech[osoba_id].items()}
            kontrola = {"zdroj_hlasu": clen["hlasu"], "nase_prilezitosti": nase,
                        "sedi": nase == {k: v for k, v in clen["hlasu"].items() if v}}

        profil = {
            "id": osoba_id,
            "jmeno": jmeno,
            # Modul B1 vlastní osobnosti.json; když tam člověk ještě není,
            # profil se přesto postaví a jen to přizná.
            "v_osobnostech": osobnost is not None,
            "role": (osobnost or {}).get("role") or [],
            "strana_posledni": (m["strana_dle_roku"].get(max(m["strana_dle_roku"]))
                                if m["strana_dle_roku"] else None),
            "strany": [s for s, _ in m["strany"].most_common()],
            "organy": [o for o, _ in m["organy"].most_common()],
            "obdobi": sorted(m["obdobi"]),
            "prvni_hlasovani": m["prvni"],
            "posledni_hlasovani": m["posledni"],

            # Jak velká část záznamu spadá do doby, kdy zdroj omluvy zapisuje.
            # Kde je `podil` nízký, nesmí web rozpad omluven/nepritomen ukazovat.
            "rozliseni_omluv": {
                **_pomer(_spolehlive, sum(po_organ_rok[osoba_id].values()),
                         "prilezitosti", "s_rozlisenim"),
                # Zdroj sem tam omluvu zapíše i v ročníku, kde je jinak
                # nevede (rada 2015 a 2022). Je to pár záznamů a nedělá
                # to z ročníku spolehlivý — přiznáváme je číslem.
                "omluv_mimo_spolehlive_obdobi": _mimo,
            },

            "ucast": _souhrn(c),
            "po_letech": {r: _souhrn(po_letech[osoba_id][r])
                          for r in sorted(po_letech[osoba_id])},
            "po_organech": {o: _souhrn(po_organech[osoba_id][o])
                            for o in sorted(po_organech[osoba_id])},
            "po_obdobich": {},

            "shoda_s_vetsinou": {
                **_pomer(vetsina_celkem[osoba_id][1], vetsina_celkem[osoba_id][0],
                         "z_hlasovani", "shodnych"),
                "odlisnych": vetsina_celkem[osoba_id][0] - vetsina_celkem[osoba_id][1],
                "jediny_odlisny": jediny_odlisny.get(osoba_id, 0),
                "po_letech": {
                    r: _pomer(v[1], v[0], "z_hlasovani", "shodnych")
                    for r, v in sorted(vetsina_rok[osoba_id].items())
                },
            },

            "odchylky_od_strany": {
                **_pomer(strana_celkem[osoba_id][1], strana_celkem[osoba_id][0],
                         "porovnatelnych", "odchylek"),
                "po_letech": {
                    r: _pomer(v[1], v[0], "porovnatelnych", "odchylek")
                    for r, v in sorted(strana_rok[osoba_id].items())
                },
            },

            "podle_tagu": [],
            "velke_castky": {
                "prah_czk": PRAH_VELKA_CASTKA,
                **_souhrn(velke[osoba_id]),
                "shoda_s_vetsinou": _pomer(vetsina_velke[osoba_id][1],
                                           vetsina_velke[osoba_id][0],
                                           "z_hlasovani", "shodnych"),
            },

            # Oba žebříčky se krájí z téhož seřazeného seznamu, takže u lidí
            # s málo protějšky by se překryly a tentýž člověk by figuroval
            # jako nejshodnější i nejodlišnější. Krájí se proto nejvýš půlka.
            "nejcasteji_shodne": blizci[:_kolik],
            "nejcasteji_odlisne": list(reversed(blizci[len(blizci) - _kolik:])) if _kolik else [],
            "kontrola": kontrola,
        }

        # období s údajem, jak velkou část období člověk zabral — bez toho
        # by kratší působení vypadalo jako slabá docházka
        for obd in sorted(po_obdobich[osoba_id]):
            s = _souhrn(po_obdobich[osoba_id][obd])
            v_obdobi = {o: hlasovani_v_obdobi.get((o, obd), 0)
                        for o in po_organech[osoba_id]}
            s["hlasovani_v_obdobi"] = v_obdobi
            s["podil_obdobi"] = _podil(s["prilezitosti"], sum(v_obdobi.values()))
            profil["po_obdobich"][obd] = s

        # témata: kde hlasuje nejčastěji a kde se nejčastěji liší
        for tag, tc in po_tagu[osoba_id].items():
            s = _souhrn(tc)
            vt = vetsina_tag[osoba_id].get(tag, [0, 0])
            st = strana_tag[osoba_id].get(tag, [0, 0])
            profil["podle_tagu"].append({
                "tag": tag,
                "nazev": tagy_nazvy.get(tag, tag),
                **s,
                "shoda_s_vetsinou": {**_pomer(vt[1], vt[0], "z_hlasovani", "shodnych"),
                                     "odlisnych": vt[0] - vt[1]},
                "odchylky_od_strany": _pomer(st[1], st[0], "porovnatelnych", "odchylek"),
            })
        profil["podle_tagu"].sort(key=lambda t: (-t["prilezitosti"], t["tag"]))

        profily.append(profil)

    # --- matice shody ---------------------------------------------------
    jmena = {p["id"]: p["jmeno"] for p in profily}
    matice = []
    for (a, b), p in sorted(pary.items()):
        matice.append({
            "a": a, "a_jmeno": jmena.get(a, a),
            "b": b, "b_jmeno": jmena.get(b, b),
            "spolecnych": p["spolecnych"],
            "shodnych": p["shodnych"],
            "podil": _podil(p["shodnych"], p["spolecnych"]),
            "maly_vzorek": p["spolecnych"] < PRAH_MALY_VZOREK,
            "po_organech": {o: {"spolecnych": v[0], "shodnych": v[1],
                                "podil": _podil(v[1], v[0]),
                                "maly_vzorek": v[0] < PRAH_MALY_VZOREK}
                            for o, v in sorted(p["organy"].items())},
        })

    vysledek = {
        "generovano": date.today().isoformat(),
        "zdroj": {
            "hlasovani": len(zaznamy),
            "jmenovitych_hlasu": sum(len(z["hlasy"]) for z in zaznamy),
            "osob": len(profily),
            "osob_v_osobnostech": sum(1 for p in profily if p["v_osobnostech"]),
            "dvojic": len(matice),
            "rozsah": [min(z["datum"] for z in zaznamy), max(z["datum"] for z in zaznamy)],
            "hlasovani_bez_jednoznacne_vetsiny": bez_vetsiny,
            "hlasovani_nad_prahem_castky": velkych_hlasovani,
            "neucasti_celkem": sum(sum(c.values()) for c in neucasti.values()),
            "omluvenych_celkem": sum(c["omluven"] for c in neucasti.values()),
            "omluv_mimo_spolehlive_obdobi": sum(
                p["rozliseni_omluv"]["omluv_mimo_spolehlive_obdobi"] for p in profily),
            "castek_nad_stropem_duveryhodnosti": sum(
                1 for c in castky.values()
                if c is not None and c > STROP_ROZUMNE_CASTKY),
        },
        "metodika": {
            "stavy": list(STAVY),
            "omluven": "Zdroj kóduje omluvenou neúčast jako hlas 'nepritomen' "
                       "s příznakem 'omluven: true'. Profily je rozdělují: "
                       "'omluven' = omluvená neúčast, 'nepritomen' = neomluvená.",
            "hlasoval": "pro + proti + zdrzel",
            "pritomen": "pro + proti + zdrzel + nehlasoval",
            "neucast": "omluven + nepritomen",
            "dostupnost_omluv": "Zdroj příznak omluvy u starších zápisů vůbec "
                                "nemá — zastupitelstvo ho zapisuje od roku 2019, "
                                "rada od roku 2023. Před tím je každá neúčast "
                                "vedená jako 'nepritomen', ačkoliv se lidé "
                                "samozřejmě omlouvali. Mimo spolehlivé období "
                                "(viz blok 'dostupnost_omluv' a u profilu "
                                "'rozliseni_omluv') se smí zobrazovat jen "
                                "souhrnné 'neucast', nikdy rozpad na omluvené "
                                "a neomluvené.",
            "prilezitosti": "Počet hlasování, u kterých je člověk na jmenovité "
                            "listině. Všechna procenta se počítají z tohoto čísla, "
                            "ne z počtu všech hlasování orgánu — jinak by neúplné "
                            "funkční období vypadalo jako nízká docházka.",
            "vetsina": "Nejčastější odevzdaný hlas daného hlasování; při remíze "
                       "se hlasování do shody nepočítá. Pole 'vysledek' se "
                       "nepoužívá — v datech je u všech hlasování 'schvaleno', "
                       "takže by shoda s výsledkem nic neměřila.",
            "odchylky_od_strany": "Většina ostatních členů téhož uskupení v témže "
                                  "hlasování (vlastní hlas se ze základny vyjímá). "
                                  "Uskupení se bere podle labelu zapsaného u daného "
                                  "hlasování, takže přejmenování klubu nevadí. "
                                  "Klub o jednom přítomném a remízy se nepočítají.",
            "matice_shody": "Dvojice se porovnává jen v hlasováních, kde OBA "
                            "odevzdali hlas. Neúčast se nepočítá jako neshoda.",
            "maly_vzorek": f"true, když je základna pod {PRAH_MALY_VZOREK} hlasování. "
                           "Frontend má u takového řezu zobrazit počet, ne procento.",
            "castky": f"Hranice velké částky je {PRAH_VELKA_CASTKA:,} Kč a bere se "
                      "z 'castka_czk' bodu usnesení. Objemy v Kč se v profilech "
                      "nesčítají — část částek ve zdroji je zjevně chybně "
                      "vyparsovaná (viz 'castek_nad_stropem_duveryhodnosti'), "
                      "takže by součet lhal. Publikují se jen počty hlasování.",
            "bez_hodnoceni": "Soubor obsahuje počty a podíly, žádné hodnocení. "
                             "Nízká účast nemá v datech uvedený důvod a nesmí se "
                             "prezentovat jako selhání.",
        },
        "dostupnost_omluv": dostupnost,
        "profily": profily,
        "matice_shody": matice,
    }
    return vysledek


# --------------------------------------------------------------------------
# Kontrola výstupu
# --------------------------------------------------------------------------

def zkontroluj(vysledek: dict, log: Log) -> None:
    """Ověří, že součty v profilech sedí. Nesrovnalost je chyba, ne poznámka."""
    for p in vysledek["profily"]:
        u = p["ucast"]
        soucet = sum(u[s] for s in STAVY)
        if soucet != u["prilezitosti"]:
            log.chyba(f"{p['id']}: součet stavů {soucet} != příležitostí {u['prilezitosti']}")
        if u["pritomen"] + u["neucast"] != u["prilezitosti"]:
            log.chyba(f"{p['id']}: přítomen + neúčast != příležitostí")
        if u["omluven"] + u["nepritomen"] != u["neucast"]:
            log.chyba(f"{p['id']}: omluven + nepřítomen != neúčasti")
        if p["rozliseni_omluv"]["prilezitosti"] != u["prilezitosti"]:
            log.chyba(f"{p['id']}: základna rozlišení omluv != příležitostí")
        ro = p["rozliseni_omluv"]
        if u["omluven"] - ro["omluv_mimo_spolehlive_obdobi"] > ro["s_rozlisenim"]:
            log.chyba(f"{p['id']}: víc omluv než příležitostí s rozlišením omluv")
        po_letech = sum(r["prilezitosti"] for r in p["po_letech"].values())
        if po_letech != u["prilezitosti"]:
            log.chyba(f"{p['id']}: po letech {po_letech} != celkem {u['prilezitosti']}")
        po_organech = sum(r["prilezitosti"] for r in p["po_organech"].values())
        if po_organech != u["prilezitosti"]:
            log.chyba(f"{p['id']}: po orgánech {po_organech} != celkem {u['prilezitosti']}")
        sv = p["shoda_s_vetsinou"]
        if sv["shodnych"] > sv["z_hlasovani"]:
            log.chyba(f"{p['id']}: shodných > základny u shody s většinou")
        if sv["z_hlasovani"] > u["hlasoval"]:
            log.chyba(f"{p['id']}: základna shody s většinou > počtu odevzdaných hlasů")
        od = p["odchylky_od_strany"]
        if od["odchylek"] > od["porovnatelnych"]:
            log.chyba(f"{p['id']}: odchylek > porovnatelných")
        if p["kontrola"] and not p["kontrola"]["sedi"]:
            log.chyba(f"{p['id']}: příležitosti nesedí s rejstříkem hlasujících "
                      f"{p['kontrola']}")
    for d in vysledek["matice_shody"]:
        if d["shodnych"] > d["spolecnych"]:
            log.chyba(f"dvojice {d['a']}/{d['b']}: shodných > společných")
        po_organech = sum(v["spolecnych"] for v in d["po_organech"].values())
        if po_organech != d["spolecnych"]:
            log.chyba(f"dvojice {d['a']}/{d['b']}: součet po orgánech nesedí")
    log.info("kontrola hotova", profilu=len(vysledek["profily"]),
             dvojic=len(vysledek["matice_shody"]))


def main() -> None:
    log = Log("profily")
    try:
        vysledek = spocti_profily(log)
        zkontroluj(vysledek, log)
    except ZdrojSelhal as e:
        log.chyba(str(e))
        log.uzavri()
        raise
    cesta = uloz("lide/profily.json", vysledek)
    log.pricti(len(vysledek["profily"]))
    log.info("uloženo", soubor=str(cesta),
             kb=round(cesta.stat().st_size / 1024))
    log.uzavri()


if __name__ == "__main__":
    main()
