"""Sběrač dat z Hlídače státu — registr smluv, dotace, veřejné zakázky, K-index.

ZÁSADA PROJEKTU: scraping dělá kód, porozumění dělá Claude.
Tenhle modul je ta "kódová" půlka — jenom normalizuje a počítá. Nic nedopočítává,
nic nehádá. Když částka ve zdroji chybí, je `null`.

--------------------------------------------------------------------------
JAK SE SEM DATA DOSTÁVAJÍ  (přečti dřív, než budeš modul měnit)
--------------------------------------------------------------------------
Hlídač státu **nemá volně dostupné REST API**. Ověřeno 17. 8. 2026:

    GET https://api.hlidacstatu.cz/api/v2/smlouvy/hledat?...
        → HTTP 302 na /Identity/Account/Login   (vyžaduje osobní API token)
    GET https://www.hlidacstatu.cz/api/v1/...   → HTTP 404
    https://data.hlidacstatu.cz/                → nedostupné

Data jsou dostupná **jako MCP server** (`mcp__hlidac_statu__*`), tedy nástroji,
které volá jazykový model, ne Python. `core.fetch()` se sem proto nedá použít.

Sběr tedy probíhá ve dvou krocích:

  1. **Sklizeň (model)** — model stránkuje `search_contracts` / `search_subsidies` /
     `search_public_tenders` (max 50 na stránku) a zapisuje odpovědi do
     `.cache/hlidac/*.psv`. Plochý textový formát, protože je to nejúspornější
     věrný přepis odpovědi API — sloupce odpovídají 1:1 polím, která API vrací.
  2. **Normalizace (tenhle modul)** — přečte sklizeň a vyrobí z ní JSON ve formátu
     podle `docs/PLAN.md`.

Kdyby projekt někdy získal API token, stačí doplnit funkci, která `.psv` vyrobí
přímo z REST API — zbytek modulu zůstane beze změny.

Sklizené soubory (`.cache/hlidac/`, oddělovač **svislítko `|`**, bez hlavičky, UTF-8).
Svislítko, ne tabulátor — přepis dělá model a tabulátory se při přepisu ztrácejí;
`|` se v názvech českých firem ani v předmětech smluv prakticky nevyskytuje.

  smlouvy.psv   id | datum | castka | kategorie | platce_ico | platce_nazev |
                prijemci | predmet
                - `datum`        = signed_On (YYYY-MM-DD)
                - `castka`       = amount_Received; prázdné nebo 0 = cena NEUVEDENA
                - `kategorie`    = kód z KATEGORIE níže, prázdné = neurčeno
                - `platce_nazev` = prázdné u sledovaných subjektů (název je v configu)
                - `prijemci`     = `ICO:název` oddělené `;` (smlouva jich může mít víc);
                                   prázdné IČO se zapisuje jako `:název`
                - `predmet`      = contract_Name

  vady.psv      id | uroven      -- `Z` = zásadní nedostatek (with_serious_issues_only)
  dotace.psv    id | rok | castka | prijemce_ico | poskytovatel_ico |
                poskytovatel_nazev | kategorie | program | nazev
  zakazky.psv   id | zadavatel_ico | zverejneno | podepsano | odhad_bez_dph |
                konecna_bez_dph | stav | dodavatele | nazev
  subjekty.psv  ico | smluv | objem_czk | bez_ceny | vadnych
                -- souhrnná čísla, která API hlásí samo; slouží ke kontrole,
                   jestli nám ve sklizni něco nechybí
  statistiky.json  -- výřez z `get_business_with_government` (K-index, souhrny)

POZNÁMKA K ROZSAHU PŘEPISU: sloupec `predmet` (a u části smluv i `kategorie`)
zůstává v první sklizni prázdný — přepis 6 503 předmětů smluv je řádově dražší
než všechno ostatní dohromady a agregace protistran, kvůli které data sbíráme,
ho nepotřebuje. Prázdný předmět proto neznamená „ve zdroji chybí", ale
„zatím nesklizeno"; ve výstupu je `null` a v `souhrn.json` → `metodika` je to
přiznané. Doplnění je mechanické — formát se nemění, jen se dopíše sloupec.

--------------------------------------------------------------------------
SMĚR PENĚZ (`smer`) — na tomhle stojí celý graf
--------------------------------------------------------------------------
Registr smluv rozlišuje strany jako **plátce** (`platce`, v hledání
`contract_Provider`) a **příjemce** (`prijemce`, v hledání `contract_Recipients`).
Z toho plyne:

  * sledovaný subjekt je **plátce**   → `smer = "vydaj"`  (město platí, protistrana je dodavatel)
  * sledovaný subjekt je **příjemce** → `smer = "prijem"` (město inkasuje, protistrana je plátce)

Ověřeno na reálných datech: u smlouvy 5299472 je plátcem Karlovarský kraj
a příjemcem město (dar 66 mil. Kč) → `prijem`; u smlouvy 39134862 je plátcem
město a příjemcem Zahradní a parková s.r.o. → `vydaj`.

POZOR — známá vada zdroje, nedá se z dat opravit: u pronájmů a prodejů
zveřejňovatelé běžně zapíšou sami sebe do kolonky plátce, i když peníze
naopak inkasují (např. smlouva 39141538 — nájem nebytového prostoru, město
je vedeno jako plátce, ačkoliv nájemné dostává). Směr proto **kopírujeme
ze zdroje** a nepřepisujeme ho podle klíčových slov v předmětu — to by
znamenalo vyrábět čísla, která v registru nejsou. Ve výstupu se to projeví
tak, že kategorie „Nákup, prodej a pronájem nemovitosti" je mezi výdaji
nadhodnocená. Uvedeno i v `souhrn.json` → `metodika`.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import (  # noqa: E402
    CACHE,
    Log,
    ZdrojSelhal,
    nacti,
    sledovane_subjekty,
    uloz,
)

SUROVE = CACHE / "hlidac"

DETAIL_SMLOUVY = "https://www.hlidacstatu.cz/Detail/{}"
DETAIL_DOTACE = "https://www.hlidacstatu.cz/Dotace/Detail/{}"
DETAIL_ZAKAZKY = "https://www.hlidacstatu.cz/verejnezakazky/zakazka/{}"

# Kódy kategorií smluv → český název, jak ho Hlídač zobrazuje.
# Zdroj: nástroj `list_contract_categories` (staženo 17. 8. 2026). Ve sklizni
# se píše krátký kód, ať se ve sklizni neopakuje dvacetiznakový název u každé smlouvy.
KATEGORIE: dict[str, str] = {
    "ostatni": "Ostatní",
    "it": "IT",
    "it_hw": "IT Hardware",
    "it_sw": "IT Software",
    "it_site_opravy": "Opravy, údržba a počítačové sítě",
    "it_vyvoj": "IT Vývoj",
    "it_konzultace": "Konzultace a poradenství",
    "it_sluzby_servery": "Internetové služby, servery, cloud, certifikáty",
    "it_bezpecnost": "IT Bezpečnost",
    "stav": "Stavebnictví",
    "stav_konstr": "Konstrukční a stavební práce",
    "stav_vedeni": "Stavební práce pro potrubní, telekomunikační a elektrické vedení",
    "stav_silnice": "Výstavba, zakládání a povrchové práce pro silnice",
    "stav_zeleznice": "Stavební úpravy pro železnici",
    "stav_voda": "Výstavba vodních děl",
    "stav_dokonceni": "Práce při dokončování budov",
    "stav_sluzby": "Stavební služby",
    "doprava": "Doprava a poštovní služby",
    "doprava_osobni": "Osobní vozidla",
    "doprava_special": "Nákladní nebo speciální vozidla",
    "doprava_lidi": "Hromadná autobusová a vlaková doprava",
    "doprava_udrzba": "Vozidla silniční údržby a příslušenství",
    "doprava_pohotovost": "Sanitní a zdravotnická vozidla",
    "doprava_koleje": "Železniční a tramvajové lokomotivy a vozidla",
    "doprava_opravy": "Servis a oprava vozidel včetně náhradních dílů a příslušenství",
    "doprava_posta": "Poštovní a kurýrní služby",
    "doprava_letadla": "Letecká přeprava",
    "stroje": "Stroje a zařízení",
    "stroje_elektricke": "Elektrické stroje",
    "stroje_laborator": "Laboratorní přístroje a zařízení",
    "stroje_prumysl": "Průmyslové stroje",
    "telco": "Telco",
    "telco_site": "Sítě a přenos dat",
    "telco_sluzby": "Telekomunikační služby",
    "zdrav": "Zdravotnictví",
    "zdrav_pristroje": "Zdravotnické přístroje",
    "zdrav_leciva": "Léčiva",
    "zdrav_kosmetika": "Kosmetika",
    "zdrav_opravy": "Opravy a údržba zdravotnických přístrojů",
    "zdrav_material": "Zdravotnický materiál",
    "zdrav_hygiena": "Zdravotnický hygienický materiál",
    "jidlo": "Voda a potraviny",
    "jidlo_potrava": "Potraviny",
    "jidlo_voda": "Pitná voda, nápoje, tabák atd.",
    "bezpecnost": "Bezpečnostní a ochranné vybavení a údržba",
    "bezpecnost_kamery": "Kamerové systémy",
    "bezpecnost_hasici": "Hasičské vybavení, požární ochrana",
    "bezpecnost_zbrane": "Zbraně",
    "bezpecnost_ostraha": "Ostraha objektů",
    "prirodnizdroj": "Přírodní zdroje",
    "prirodnizdroj_pisky": "Písky a jíly",
    "prirodnizdroj_chemie": "Chemické výrobky",
    "energie": "Energie",
    "energie_paliva": "Paliva a oleje",
    "energie_elektrina": "Elektrická energie",
    "energie_jina": "Jiná energie",
    "energie_sluzby": "Veřejné služby pro energie",
    "energie_voda": "Voda",
    "agro": "Zemědělství",
    "agro_les": "Lesnictví a těžba dřeva",
    "agro_zahrada": "Zahradnické služby",
    "kancelar": "Kancelář",
    "kancelar_tisk": "Tisk",
    "kancelar_potreby": "Kancelářské potřeby",
    "kancelar_nabytek": "Nábytek",
    "kancelar_spotrebice": "Kancelářské a domácí spotřebiče",
    "kancelar_cisteni": "Čisticí výrobky",
    "kancelar_nabor": "Nábor zaměstnanců",
    "kancelar_smart": "Mobily, smart zařízení",
    "kancelar_literatura": "Knihy, časopisy, literatura",
    "remeslo": "Řemesla",
    "remeslo_odevy": "Oděvy",
    "remeslo_textil": "Textilie",
    "remeslo_hudba": "Hudební nástroje",
    "remeslo_sport": "Sport a sportoviště",
    "social": "Sociální služby",
    "social_zdravotni": "Zdravotní péče",
    "social_pece": "Sociální péče",
    "social_kultura": "Rekreační, kulturní akce",
    "social_knihovny": "Knihovny, archivy, muzea a jiné",
    "finance": "Finance",
    "finance_pojisteni": "Pojišťovací služby",
    "finance_ucetni": "Účetní, revizní a peněžní služby",
    "finance_poradenstvi": "Podnikatelské a manažerské poradenství a související služby",
    "finance_bankovni": "Bankovní služby a poplatky",
    "finance_repo": "Spoření a repo operace",
    "finance_formality": "Bankovní formality, ceníky, VOP",
    "legal": "Právní a realitní služby",
    "legal_reality": "Realitní služby",
    "legal_pravni": "Právní služby",
    "legal_nemovitosti": "Nákup, prodej a pronájem nemovitosti (bytové i nebytové)",
    "techsluzby": "Technické služby",
    "techsluzby_odpady": "Odpady",
    "techsluzby_cisteni": "Čistící a hygienické služby",
    "techsluzby_uklid": "Úklidové služby",
    "vyzkum": "Věda, výzkum a vzdělávání",
    "vyzkum_skoleni": "Školení a kurzy",
    "marketing": "Reklamní a marketingové služby",
    "jine": "Jiné služby",
    "jine_pohostinstvi": "Pohostinství a ubytovací služby a maloobchodní služby",
    "jine_jidelny": "Služby závodních jídelen",
    "jine_admin": "Administrativní služby, stravenky",
    "jine_verejnost": "Zajišťování služeb pro veřejnost",
    "jine_pruzkum": "Průzkum veřejného mínění a statistiky",
    "jine_opravy": "Opravy, údržba, záruční i pozáruční servis",
    "jine_preklady": "Překladatelské a tlumočnické služby",
    "dary": "Dary a dotace",
    "dary_spoluprace": "Smlouvy o spolupráci",
    "zvirata": "Zvířata",
}

# `legal_Risk_Level` v odpovědi API. Za "vážně vadnou" (PLAN.md: `vada: true`)
# považujeme jen zásadní nedostatek — přesně to, co filtruje
# `with_serious_issues_only=true`, podle čeho Hlídač počítá svoje statistiky.
VADA_ZASADNI = "Zásadní nedostatek s vlivem na platnost smlouvy"


# --------------------------------------------------------------------------
# Čtení sklizně
# --------------------------------------------------------------------------

def _psv(jmeno: str, sloupcu: int) -> list[list[str]]:
    """Načte sklizený soubor oddělený `|`. Když chybí nebo je prázdný, vyhodí ZdrojSelhal.

    Řádky s jiným počtem sloupců neignorujeme potichu — to by znamenalo tiše
    zahodit smlouvu. Doplníme prázdné sloupce jen zprava (chybějící koncová
    pole), cokoliv delšího je chyba sklizně.
    """
    path = SUROVE / jmeno
    if not path.exists():
        raise ZdrojSelhal(
            f"Chybí sklizený soubor {path}. Data z Hlídače se stahují přes MCP "
            f"nástroje (viz docstring modulu), ne přímo tímhle skriptem."
        )
    radky: list[list[str]] = []
    for i, radek in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not radek.strip():
            continue
        pole = radek.split("|")
        if len(pole) > sloupcu:
            raise ZdrojSelhal(f"{jmeno}:{i} má {len(pole)} sloupců, čeká se {sloupcu}")
        pole += [""] * (sloupcu - len(pole))
        radky.append([p.strip() for p in pole])
    if not radky:
        raise ZdrojSelhal(f"{path} je prázdný — sklizeň nic nepřinesla")
    return radky


def _castka(txt: str) -> float | None:
    """Částka ze sklizně.

    Hlídač u smluv bez uvedené (nebo skryté) ceny vrací `amount_Received = 0`.
    Ověřeno: `with_hidden_value_only=true` vrací u města 258 smluv a všechny
    mají nulu. Nula proto znamená „cena neuvedena" → `None`, ne nulovou smlouvu.
    Nikdy ji nedopočítáváme.
    """
    txt = txt.strip()
    if not txt:
        return None
    hodnota = float(txt)
    return None if hodnota == 0 else hodnota


def _strany(txt: str) -> list[dict]:
    """Rozparsuje sloupec `ICO:název;ICO:název`. Prázdné IČO je povolené."""
    out = []
    for kus in txt.split(";"):
        kus = kus.strip()
        if not kus:
            continue
        ico, _, nazev = kus.partition(":")
        out.append({"ico": ico.strip() or None, "nazev": nazev.strip() or None})
    return out


def _rok(datum: str) -> int | None:
    return int(datum[:4]) if datum[:4].isdigit() else None


# --------------------------------------------------------------------------
# Smlouvy
# --------------------------------------------------------------------------

def zpracuj_smlouvy(log: Log) -> dict[str, int]:
    """Ze sklizně vyrobí `data/penize/smlouvy/{ico}.json` pro každý sledovaný subjekt.

    Smlouva mezi dvěma sledovanými subjekty se objeví v obou souborech —
    u plátce jako `vydaj`, u příjemce jako `prijem`. Agregace to musí
    deduplikovat podle `id` (viz `pipeline/agregace_penez.py`).
    """
    subjekty = {s["ico"]: s["nazev"] for s in sledovane_subjekty()}
    vady = {r[0] for r in _psv("vady.psv", 2) if r[1] == "Z"}
    log.info("vadných smluv ve sklizni", pocet=len(vady))

    def dopln_nazev(strana: dict) -> dict:
        """U sledovaných subjektů se název ve sklizni vynechává — je v configu
        a opakovat ho u tisíců řádků by TSV zbytečně nafouklo."""
        if not strana["nazev"] and strana["ico"] in subjekty:
            strana["nazev"] = subjekty[strana["ico"]]
        return strana

    podle_subjektu: dict[str, list[dict]] = {ico: [] for ico in subjekty}
    videno: set[str] = set()
    bez_strany = 0

    for r in _psv("smlouvy.psv", 8):
        sid, datum, castka, kat, platce_ico, platce_nazev, prijemci, predmet = r
        videno.add(sid)
        platce = dopln_nazev({"ico": platce_ico or None, "nazev": platce_nazev or None})
        strany = [dopln_nazev(p) for p in _strany(prijemci)]

        zaklad = {
            "id": sid,
            "datum": datum or None,
            "castka_czk": _castka(castka),
            "predmet": predmet or None,
            "kategorie": KATEGORIE.get(kat) if kat else None,
            "vada": sid in vady,
            "url": DETAIL_SMLOUVY.format(sid),
        }

        zapsano = False

        # Sledovaný subjekt v roli plátce → město platí → protistranou je příjemce.
        if platce_ico in subjekty:
            protistrany = [p for p in strany if p["ico"] != platce_ico] or strany
            hlavni = protistrany[0] if protistrany else {"ico": None, "nazev": None}
            zaznam = dict(zaklad)
            zaznam.update({
                "protistrana_ico": hlavni["ico"],
                "protistrana": hlavni["nazev"],
                "smer": "vydaj",
            })
            if len(protistrany) > 1:
                # Částka se mezi protistrany NEDĚLÍ — registr smluv rozpad neuvádí
                # a vymýšlet si poměr by znamenalo vyrábět čísla. Připíše se celá
                # první protistraně a zbytek se jen vyjmenuje.
                zaznam["dalsi_protistrany"] = protistrany[1:]
            podle_subjektu[platce_ico].append(zaznam)
            zapsano = True

        # Sledovaný subjekt v roli příjemce → město inkasuje → protistranou je plátce.
        for p in strany:
            if p["ico"] in subjekty:
                podle_subjektu[p["ico"]].append({
                    **zaklad,
                    "protistrana_ico": platce["ico"],
                    "protistrana": platce["nazev"],
                    "smer": "prijem",
                })
                zapsano = True

        if not zapsano:
            bez_strany += 1

    if bez_strany:
        log.chyba(
            f"{bez_strany} smluv nemá na žádné straně sledovaný subjekt — "
            f"sklizeň zřejmě zachytila i cizí smlouvy"
        )

    pocty: dict[str, int] = {}
    for ico, nazev in subjekty.items():
        smlouvy = sorted(podle_subjektu[ico], key=lambda s: (s["datum"] or "", s["id"]))
        uloz(f"penize/smlouvy/{ico}.json", {
            "ico": ico,
            "nazev": nazev,
            "aktualizovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "smlouvy": smlouvy,
        })
        pocty[ico] = len(smlouvy)
        log.pricti(len(smlouvy))

    log.info("smluv ve sklizni", unikatnich=len(videno), zapsano=sum(pocty.values()))
    return pocty


# --------------------------------------------------------------------------
# Dotace
# --------------------------------------------------------------------------

def zpracuj_dotace(log: Log) -> dict[str, int]:
    """`data/penize/dotace/{ico}.json` — dotace přijaté sledovanými subjekty."""
    subjekty = {s["ico"]: s["nazev"] for s in sledovane_subjekty()}
    podle_subjektu: dict[str, list[dict]] = {ico: [] for ico in subjekty}
    cizich = 0

    for r in _psv("dotace.psv", 9):
        did, rok, castka, prijemce_ico, posk_ico, posk_nazev, kat, program, nazev = r
        if prijemce_ico not in subjekty:
            cizich += 1
            continue
        podle_subjektu[prijemce_ico].append({
            "id": did,
            "rok": int(rok) if rok.isdigit() else None,
            "castka_czk": _castka(castka),
            "poskytovatel_ico": posk_ico or None,
            "poskytovatel": posk_nazev or None,
            "kategorie": kat or None,
            "program": program or None,
            "nazev": nazev or None,
            "url": DETAIL_DOTACE.format(did),
        })

    if cizich:
        log.info("dotací mimo sledované subjekty (přeskočeno)", pocet=cizich)

    pocty = {}
    for ico, nazev in subjekty.items():
        dotace = sorted(podle_subjektu[ico], key=lambda d: (d["rok"] or 0, d["id"]))
        uloz(f"penize/dotace/{ico}.json", {"ico": ico, "nazev": nazev, "dotace": dotace})
        pocty[ico] = len(dotace)
    log.info("dotací zapsáno", pocet=sum(pocty.values()))
    return pocty


# --------------------------------------------------------------------------
# Veřejné zakázky
# --------------------------------------------------------------------------

def zpracuj_zakazky(log: Log) -> dict[str, int]:
    """`data/penize/zakazky/{ico}.json` — veřejné zakázky, kde je subjekt zadavatelem."""
    subjekty = {s["ico"]: s["nazev"] for s in sledovane_subjekty()}
    podle_subjektu: dict[str, list[dict]] = {ico: [] for ico in subjekty}
    cizich = 0

    for r in _psv("zakazky.psv", 9):
        zid, zadavatel, zverejneno, podepsano, odhad, konecna, stav, dodavatele, nazev = r
        if zadavatel not in subjekty:
            cizich += 1
            continue
        podle_subjektu[zadavatel].append({
            "id": zid,
            "nazev": nazev or None,
            "zverejneno": zverejneno or None,
            "smlouva_podepsana": podepsano or None,
            "odhad_bez_dph_czk": _castka(odhad),
            "konecna_bez_dph_czk": _castka(konecna),
            "stav": stav or None,
            "dodavatele": _strany(dodavatele),
            "url": DETAIL_ZAKAZKY.format(zid),
        })

    if cizich:
        log.info("zakázek mimo sledované subjekty (přeskočeno)", pocet=cizich)

    pocty = {}
    for ico, nazev in subjekty.items():
        zakazky = sorted(podle_subjektu[ico], key=lambda z: (z["zverejneno"] or "", z["id"]))
        uloz(f"penize/zakazky/{ico}.json", {"ico": ico, "nazev": nazev, "zakazky": zakazky})
        pocty[ico] = len(zakazky)
    log.info("zakázek zapsáno", pocet=sum(pocty.values()))
    return pocty


# --------------------------------------------------------------------------
# Statistiky a K-index
# --------------------------------------------------------------------------

def zpracuj_statistiky(log: Log) -> dict:
    """Přenese souhrnná čísla Hlídače do `data/penize/statistiky.json`.

    Tahle čísla si Hlídač počítá sám. Nepřepisujeme je vlastními součty —
    slouží naopak jako kontrola, jestli nám ve sklizni něco nechybí.
    """
    path = SUROVE / "statistiky.json"
    if not path.exists():
        raise ZdrojSelhal(f"Chybí {path} — sklizeň `get_business_with_government` neproběhla")
    import json

    stat = json.loads(path.read_text(encoding="utf-8"))

    per_subjekt = []
    for r in _psv("subjekty.psv", 5):
        per_subjekt.append({
            "ico": r[0],
            "smluv": int(r[1]) if r[1] else None,
            "objem_czk": _castka(r[2]),
            "bez_ceny": int(r[3]) if r[3] else 0,
            "vadnych": int(r[4]) if r[4] else 0,
        })

    vysledek = {
        "zdroj": "Hlídač státu, get_business_with_government + search_contracts",
        "staženo": stat.get("staženo"),
        "mesto": stat.get("mesto"),
        "holding_dle_hlidace": stat.get("holding_dle_hlidace"),
        "kindex": stat.get("kindex", []),
        "po_letech_mesto": stat.get("po_letech_mesto", []),
        "po_letech_holding": stat.get("po_letech_holding", []),
        "dotace_po_letech_mesto": stat.get("dotace_po_letech_mesto", []),
        "dotace_po_letech_holding": stat.get("dotace_po_letech_holding", []),
        "v_registru": stat.get("sklizen_smluv_po_letech_zverejneni", {}),
        # Bez pokrytí by se dílčí sklizeň dala číst jako úplná data. Propisuje
        # se dál do souhrn.json, aby to viděl i web, ne jen tenhle soubor.
        "pokryti": stat.get("pokryti", {}),
        "subjekty": per_subjekt,
    }
    uloz("penize/statistiky.json", vysledek)
    log.info("statistiky uloženy", subjektu=len(per_subjekt), kindex_let=len(vysledek["kindex"]))
    return vysledek


# --------------------------------------------------------------------------

def main() -> None:
    log = Log("hlidac")
    try:
        zpracuj_statistiky(log)
        zpracuj_smlouvy(log)
        zpracuj_dotace(log)
        zpracuj_zakazky(log)
    except ZdrojSelhal as e:
        log.chyba(str(e))
        log.uzavri()
        raise
    log.uzavri()


if __name__ == "__main__":
    main()
