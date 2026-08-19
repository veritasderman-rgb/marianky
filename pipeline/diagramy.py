"""Diagramy — schémata projektu a města, počítaná ze skutečných dat.

PROČ TENHLE MODUL
-----------------
Osm diagramů, které vysvětlují to, co z tabulky vidět není: jak je poskládaný
městský holding, kudy tečou data týdenním během, kolik usnesení se podařilo
spojit se smlouvou, kdo sedí v jakých firmách.

Vznikají tady, ne v kreslicím nástroji, ze tří důvodů:
  – **přepočítají se s daty.** Když do holdingu přibude firma, přibude
    v diagramu uzel. Obrázek nakreslený jednou by za měsíc lhal.
  – **umí tmavý motiv.** Web je kreslí jako SVG s barvami z tokenů.
  – **nic se nenačítá z cizího serveru.** Web to má napsané v patičce.

CO JE ZJIŠTĚNÉ A CO TVRZENÉ
---------------------------
Šest diagramů je celé z dat. Dva stojí na `config/diagramy.json`, protože
mapu „který zdroj plní kterou sekci“ a datový model projektu nelze ze sběru
odvodit — to je znalost o projektu, ne údaj o městě. Každý diagram nese pole
`zdroj`, kde je napsané, odkud pochází.

VÝSTUP
------
data/diagramy/{id}.json — jeden soubor na diagram, plus `index.json`.

Typy, které web umí vykreslit (web/src/lib/diagramy.ts):
    strom  — kořen, skupiny v řadě, potomci ve sloupci pod skupinou
    tok    — vrstvy zleva doprava, hrany s čísly
    sit    — dva sloupce uzlů a hrany mezi nimi
    mysl   — kořen, větve, listy (myšlenková mapa)
    erd    — entity s poli a vztahy mezi nimi
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import DATA, Log, nacti, nacti_config, uloz  # noqa: E402


def _cely(x) -> int | None:
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _mezerou(n: int | None) -> str:
    return "—" if n is None else f"{n:,}".replace(",", " ")


def _chybi(diagram_id: str, nazev: str, duvod: str, zdroj: str) -> dict:
    """Diagram, který nejde nakreslit.

    Nekreslí se prázdné schéma. Prázdné schéma by tvrdilo, že struktura je
    prázdná — přitom jen chybí data.
    """
    return {
        "id": diagram_id,
        "nazev": nazev,
        "typ": "chybi",
        "popis": duvod,
        "zdroj": zdroj,
        "stav": "chybi",
    }


# ═════════════════════════  1. Vlastnická struktura  ══════════════════════

# Jak se jmenují typy subjektů v souhrnu, česky a v pořadí, ve kterém patří
# do diagramu. Pořadí je od „nejvíc obchodní“ po „nejvíc služba“.
SKUPINY_HOLDINGU = [
    ("obchodni_spolecnost", "Obchodní společnosti", "Město drží podíl. Hospodaří samostatně."),
    ("prispevkova_organizace", "Příspěvkové organizace", "Zřízené městem, financované z rozpočtu."),
    ("ops", "Obecně prospěšné společnosti", "Zřízené městem, samostatná právní forma."),
    ("skola", "Školy a školky", "Zřizovatelem je město."),
    ("jine", "Ostatní", "Subjekty, které nespadají do žádné skupiny výše."),
]


def diagram_holding() -> dict:
    souhrn = nacti("penize/agregace/souhrn.json")
    if not souhrn:
        return _chybi("holding", "Vlastnická struktura města",
                      "Souhrn registru smluv zatím není spočítaný.",
                      "data/penize/agregace/souhrn.json")

    holding = souhrn.get("holding") or []
    mesto = next((h for h in holding if h.get("typ") == "mesto"), None)
    if not mesto:
        return _chybi("holding", "Vlastnická struktura města",
                      "V souhrnu není uvedené samotné město.",
                      "data/penize/agregace/souhrn.json")

    def popisek(h: dict) -> str:
        smluv = _cely(h.get("smluv"))
        # Nula smluv je zjištěná nula (subjekt v registru je a nemá nic),
        # ne neznámo — proto se píše, ne vynechává.
        return f"{_mezerou(smluv)} smluv" if smluv is not None else "počet smluv neznáme"

    skupiny = []
    for typ, nazev, popis in SKUPINY_HOLDINGU:
        deti = [h for h in holding if h.get("typ") == typ]
        if not deti:
            continue
        skupiny.append({
            "id": typ,
            "nazev": nazev,
            "popis": popis,
            "pocet": len(deti),
            "deti": [
                {"id": d.get("ico"), "nazev": d.get("nazev"), "popisek": popisek(d),
                 "hodnota": _cely(d.get("smluv"))}
                for d in sorted(deti, key=lambda x: -(_cely(x.get("smluv")) or 0))
            ],
        })

    # Nemocnice a spol.: v dashboardu jsou, do holdingu NEPATŘÍ. Kreslí se
    # stranou a přerušovaně, aby se nedaly přečíst jako městská firma.
    mimo = [
        {"id": m.get("ico"), "nazev": m.get("nazev"), "popisek": "vlastnicky mimo město",
         "poznamka": m.get("duvod")}
        for m in (souhrn.get("mimo_holding") or [])
    ]

    vsech = sum(s["pocet"] for s in skupiny)
    return {
        "id": "holding",
        "nazev": "Vlastnická struktura města",
        "typ": "strom",
        "popis": (
            f"Město a {_mezerou(vsech)} subjektů, které zřizuje nebo v nich drží podíl. "
            "Číslo u subjektu je počet jeho smluv v registru."
        ),
        "koren": {
            "id": mesto.get("ico"),
            "nazev": mesto.get("nazev"),
            "popisek": popisek(mesto),
        },
        "skupiny": skupiny,
        "stranou": mimo,
        "metodika": [
            "Skupiny odpovídají právní formě, ne velikosti. Příspěvková organizace "
            "hospodaří s rozpočtem města, obchodní společnost samostatně — je to "
            "rozdíl v tom, kdo za dluhy ručí.",
            "Nemocnice Mariánské Lázně s.r.o. tu stojí stranou a přerušovaně: "
            "vlastnicky už městu nepatří. Sleduje se kvůli významu pro město, "
            "ale do součtů holdingu nevstupuje.",
            "Platby uvnitř holdingu jsou vnitřní převody, ne výdaj města ven. "
            "U TDS (IČO 25213261) to platí obzvlášť — je to firma města.",
        ],
        "zdroj": "data/penize/agregace/souhrn.json",
        "stav": "ok",
    }


# ═══════════════════════════  2. Datový tok běhu  ═════════════════════════


def diagram_beh() -> dict:
    """Co spouští týdenní běh a v jakém pořadí.

    Seznam modulů se ČTE z `run_tyden.py`, ne opisuje. Opsaný seznam by se
    rozešel při prvním přidaném sběrači a diagram by tvrdil něco jiného,
    než co se v neděli spustí.
    """
    try:
        import run_tyden  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        return _chybi("beh", "Datový tok týdenního běhu",
                      f"run_tyden.py se nepodařilo načíst: {e}", "run_tyden.py")

    def uzel(krok: tuple[str, str, bool]) -> dict:
        modul, popis, povinny = krok
        return {
            "id": modul,
            "nazev": popis,
            "popisek": modul,
            # Povinný krok, který selže, shodí celý běh. To je vlastnost
            # kroku, ne jeho důležitost — kreslí se plně, ostatní slabě.
            "duraz": "povinny" if povinny else "nepovinny",
        }

    sberace = [uzel(k) for k in getattr(run_tyden, "KROKY", [])]
    navazne = [uzel(k) for k in getattr(run_tyden, "NAVAZNE", [])]
    if not sberace:
        return _chybi("beh", "Datový tok týdenního běhu",
                      "run_tyden.py nemá seznam kroků.", "run_tyden.py")

    povinnych = sum(1 for u in sberace + navazne if u["duraz"] == "povinny")
    return {
        "id": "beh",
        "nazev": "Datový tok týdenního běhu",
        "typ": "tok",
        "popis": (
            f"{len(sberace)} sběračů, {len(navazne)} navazujících modulů, "
            f"z toho {povinnych} povinných. Nedělní běh jde zleva doprava."
        ),
        "vrstvy": [
            {"id": "zdroje", "nazev": "Vnější zdroje",
             "popis": "Weby a API mimo projekt. Když nejedou, běh to nahlásí.",
             "uzly": [
                 {"id": "z-urad", "nazev": "Portál usnesení, web města", "duraz": "zdroj"},
                 {"id": "z-stat", "nazev": "Hlídač, ARES, ČSÚ, volby, RÚIAN", "duraz": "zdroj"},
                 {"id": "z-media", "nazev": "Média a zpravodaj", "duraz": "zdroj"},
             ]},
            {"id": "sber", "nazev": "Sběrače",
             "popis": "Stahují a ukládají syrová data. Deterministické — když zdroj selže, křičí.",
             "uzly": sberace},
            {"id": "zpracovani", "nazev": "Zpracování",
             "popis": "Počítají z už stažených dat. Nechodí na síť.",
             "uzly": navazne},
            {"id": "vystup", "nazev": "Výstup",
             "popis": "Kontrola před publikací a statický build.",
             "uzly": [
                 {"id": "kontrola", "nazev": "kontrola.py — brána před publikací", "duraz": "povinny"},
                 {"id": "build", "nazev": "astro build + Pagefind", "duraz": "povinny"},
                 {"id": "vercel", "nazev": "Nasazení na Vercel", "duraz": "nepovinny"},
             ]},
        ],
        "metodika": [
            "Seznam modulů se čte přímo z run_tyden.py. Diagram se proto nemůže "
            "rozejít s tím, co se v neděli opravdu spustí.",
            "Povinný krok je vykreslený plně: když selže, běh skončí nenulovým "
            "návratovým kódem a vydání se nevydá. Nepovinný krok jen chybí a "
            "sekce to o sobě napíše.",
            "Pořadí uvnitř vrstvy je závazné. Řetěz a propojení čtou výstup "
            "agregace peněz, časová osa čte oboje, vydání čte úplně všechno.",
        ],
        "zdroj": "run_tyden.py",
        "stav": "ok",
    }


# ═══════════════════════  3. Řetěz usnesení → peníze  ═════════════════════


def diagram_retez() -> dict:
    retez = nacti("retez/retezy.json")
    if not retez:
        return _chybi("retez", "Od usnesení ke smlouvě",
                      "Řetězy zatím nejsou spočítané.", "data/retez/retezy.json")

    st = retez.get("statistika") or {}
    jistoty = st.get("dle_jistoty") or {}
    nespojene = nacti("retez/nespojene.json") or {}
    pocty = nespojene.get("pocty") or {}

    vsech_bodu = _cely(st.get("vsech_bodu"))
    spojenych_bodu = _cely(st.get("spojenych_bodu"))
    vsech_smluv = _cely(st.get("vsech_smluv"))
    spojenych_smluv = _cely(st.get("spojenych_smluv"))

    def zbytek(celek: int | None, cast: int | None) -> int | None:
        if celek is None or cast is None:
            return None
        return celek - cast

    return {
        "id": "retez",
        "nazev": "Od usnesení ke smlouvě",
        "typ": "tok",
        "popis": (
            f"Z {_mezerou(vsech_bodu)} bodů usnesení se podařilo spojit se smlouvou "
            f"{_mezerou(spojenych_bodu)}. Vazba je odhad, ne údaj ze zdroje."
        ),
        "vrstvy": [
            {"id": "vstup", "nazev": "Co se schválilo",
             "popis": "Body usnesení rady a zastupitelstva.",
             "uzly": [
                 {"id": "body-spojene", "nazev": "Body se smlouvou",
                  "hodnota": spojenych_bodu, "duraz": "povinny"},
                 {"id": "body-bez", "nazev": "Body bez nalezené smlouvy",
                  "hodnota": zbytek(vsech_bodu, spojenych_bodu), "duraz": "nepovinny"},
             ]},
            {"id": "vazba", "nazev": "Jak jistá je vazba",
             "popis": "Společný identifikátor neexistuje. Spojuje se přes IČO, název, částku a čas.",
             "uzly": [
                 {"id": "j-vysoka", "nazev": "Vysoká jistota",
                  "hodnota": _cely(jistoty.get("vysoka")), "duraz": "povinny"},
                 {"id": "j-stredni", "nazev": "Střední jistota",
                  "hodnota": _cely(jistoty.get("stredni")), "duraz": "nepovinny"},
                 {"id": "j-nizka", "nazev": "Nízká jistota",
                  "hodnota": _cely(jistoty.get("nizka")), "duraz": "slaby"},
             ]},
            {"id": "vystup", "nazev": "Co se podepsalo",
             "popis": "Smlouvy v registru smluv.",
             "uzly": [
                 {"id": "sml-spojene", "nazev": "Smlouvy s usnesením",
                  "hodnota": spojenych_smluv, "duraz": "povinny"},
                 {"id": "sml-bez", "nazev": "Smlouvy bez usnesení",
                  "hodnota": zbytek(vsech_smluv, spojenych_smluv), "duraz": "nepovinny"},
             ]},
            {"id": "varovani", "nazev": "Co stojí za pozornost",
             "popis": "Případy, které řetěz našel a které nemusí být v pořádku.",
             "uzly": [
                 {"id": "predbeh", "nazev": "Smlouva podepsaná před usnesením",
                  "hodnota": _cely(st.get("podpis_pred_usnesenim")), "duraz": "varovani"},
                 {"id": "velke-bez", "nazev": "Velké smlouvy bez usnesení",
                  "hodnota": _cely(pocty.get("smlouvy_bez_usneseni")), "duraz": "varovani"},
                 {"id": "usn-bez", "nazev": "Usnesení bez smlouvy",
                  "hodnota": _cely(pocty.get("usneseni_bez_smlouvy")), "duraz": "varovani"},
             ]},
        ],
        "metodika": [
            "Registr smluv a portál usnesení nemají společný identifikátor. "
            "Vazba se odhaduje ze čtyř signálů: IČO v textu usnesení, shoda názvu "
            "protistrany, shoda částky a časový odstup podpisu.",
            "Nízká jistota znamená, že sedí jen část signálů, nebo že stejně dobře "
            "sedí i jiné usnesení. Takový řetěz je vodítko, ne důkaz.",
            '„Smlouva podepsaná před usnesením“ nemusí být pochybení. Bývá to i '
            'chyba tohoto párování, nebo dodatek k dřívější smlouvě. Je to podnět '
            'k ověření u zdroje, ne závěr.',
        ],
        "zdroj": "data/retez/retezy.json, data/retez/nespojene.json",
        "stav": "ok",
    }


def diagram_komise_rada() -> dict:
    """Od doporučení komise k usnesení rady.

    Trychtýř, který schválně končí uzlem „nenašli jsme nic". Bez něj by
    diagram tvrdil, že komise navrhne a rada rozhodne — přitom u většiny
    doporučení pozdější usnesení nenajdeme a NEVÍME, jestli žádné není,
    nebo ho jen neumíme dohledat.
    """
    r = nacti("retez/komise_rada.json")
    if not r:
        return _chybi("komise-rada", "Od doporučení komise k usnesení rady",
                      "Návaznost zatím není spočítaná.", "data/retez/komise_rada.json")
    k = nacti("komise/prehled.json") or {}

    st = r.get("statistika") or {}
    souhrn = k.get("souhrn") or {}
    jistoty = st.get("dle_jistoty") or {}
    projednani = r.get("projednani") or []
    usnesenim = sum(1 for p in projednani if p.get("zpusob") == "usneseni")
    na_programu = len(projednani) - usnesenim
    odhad_silny = (_cely(jistoty.get("vysoka")) or 0) + (_cely(jistoty.get("stredni")) or 0)

    navrhu = _cely(st.get("navrhu_pro_radu"))
    s_odhadem = _cely(st.get("doporuceni_s_odhadem"))

    return {
        "id": "komise-rada",
        "nazev": "Od doporučení komise k usnesení rady",
        "typ": "tok",
        "popis": (
            f"Komise poslaly radě {_mezerou(navrhu)} doporučení. Pozdější usnesení "
            f"o téže věci se podařilo najít u {_mezerou(s_odhadem)} z nich — a i to "
            "je odhad, ne údaj ze zdroje."
        ),
        "vrstvy": [
            {"id": "zapisy", "nazev": "Zápisy z komisí",
             "popis": "Dokumenty, které město zveřejnilo v rejstříku zápisů.",
             "uzly": [
                 {"id": "z-rozebrane", "nazev": "Rozebraných zápisů",
                  "hodnota": _cely(souhrn.get("rozebranych")), "duraz": "povinny"},
                 {"id": "z-nerozebrane", "nazev": "Nešly přečíst",
                  "hodnota": _cely(souhrn.get("nerozebranych")), "duraz": "varovani"},
             ]},
            {"id": "navrhy", "nazev": "Co komise navrhly",
             "popis": "Věty, kterými se komise obrací na radu: doporučuje, žádá, ukládá.",
             "uzly": [
                 {"id": "n-rade", "nazev": "Doporučení pro radu",
                  "hodnota": navrhu, "duraz": "povinny"},
                 # Jen návrhy směřující na radu, které komise zamítla. Celkový
                 # počet nepřijatých usnesení v zápisech je vyšší (patří tam
                 # i body, které radu o nic nežádaly) a vedle „doporučení pro
                 # radu" by se četl jako jejich část.
                 {"id": "n-neprijate", "nazev": "Doporučení, která komise nepřijala",
                  "hodnota": _cely(st.get("neprijatych_navrhu")), "duraz": "nepovinny"},
             ]},
            {"id": "navaznost", "nazev": "Jak jistá je návaznost",
             "popis": ("Doložené = usnesení samo jmenuje komisi a datum jejího jednání. "
                       "Odhad = shoduje se jen téma."),
             "uzly": [
                 {"id": "d-usnesenim", "nazev": "Usnesení o zápisu komise",
                  "hodnota": usnesenim or None, "duraz": "povinny"},
                 {"id": "d-program", "nazev": "Zápis jen na programu jednání",
                  "hodnota": na_programu or None, "duraz": "nepovinny"},
                 {"id": "o-silny", "nazev": "Odhad, vysoká a střední jistota",
                  "hodnota": odhad_silny or None, "duraz": "nepovinny"},
                 {"id": "o-nizky", "nazev": "Odhad, nízká jistota",
                  "hodnota": _cely(jistoty.get("nizka")), "duraz": "slaby"},
             ]},
            {"id": "nenalezeno", "nazev": "Co jsme nenašli",
             "popis": "Doporučení, ke kterému se žádné usnesení nepodařilo dohledat.",
             "uzly": [
                 {"id": "bez-odezvy", "nazev": "Doporučení bez nalezeného usnesení",
                  "hodnota": _cely(st.get("bez_odezvy")), "duraz": "varovani"},
             ]},
        ],
        "metodika": [
            "Zápis komise a usnesení rady nemají žádné společné číslo. Část spojení "
            "jde přesto doložit: usnesení samo říká „bere na vědomí zápis z jednání "
            "Komise kultury ze dne 13. 03. 2023“ a ten zápis v datech je.",
            "Zbytek je odhad ze shody neobvyklých slov, částky a času. Nízká jistota "
            "znamená, že sedí jen téma — je to vodítko, ne doklad.",
            "„Doporučení bez nalezeného usnesení“ NENÍ seznam přehlížených návrhů. "
            "Rozhodnutí může být zapsané jinými slovy, může patřit stavebnímu úřadu "
            "místo radě, nebo ho tohle párování nenašlo.",
            "Diagram netvrdí kauzalitu. Že zápis ležel radě na stole, neznamená, že "
            "se jím řídila.",
        ],
        "zdroj": "data/retez/komise_rada.json, data/komise/prehled.json",
        "stav": "ok",
    }


# ══════════════════════  4. Osoba ↔ firma ↔ peníze  ═══════════════════════

# Kolik firem se u jedné osoby vypíše, než se zbytek shrne do jednoho uzlu.
# Bez stropu by jedna osoba se čtrnácti firmami roztáhla celý diagram.
FIREM_NA_OSOBU = 8


def diagram_propojeni() -> dict:
    p = nacti("propojeni/osoby_firmy.json")
    if not p:
        return _chybi("propojeni", "Kdo sedí v jakých firmách",
                      "Vazby zatím nejsou dohledané.", "data/propojeni/osoby_firmy.json")

    osoby_vstup = [o for o in (p.get("osoby") or []) if o.get("firmy")]
    if not osoby_vstup:
        return _chybi("propojeni", "Kdo sedí v jakých firmách",
                      "Žádná osoba nemá dohledanou firmu.", "data/propojeni/osoby_firmy.json")

    vlevo: list[dict] = []
    vpravo: dict[str, dict] = {}
    hrany: list[dict] = []
    zamlceno = 0

    for o in sorted(osoby_vstup, key=lambda x: -len(x.get("firmy") or [])):
        firmy = o.get("firmy") or []
        vlevo.append({
            "id": o.get("osoba_id"),
            "nazev": o.get("jmeno"),
            "popisek": ", ".join(o.get("role") or []) or (o.get("strana") or ""),
            "pocet": len(firmy),
            # Stav ověření identity. „nejednoznacne“ znamená, že jméno sedí na
            # víc lidí — vazba se ukazuje, ale nesmí se tvářit jako potvrzená.
            "jistota": ((o.get("overeni") or {}).get("stav") or "neznamo"),
        })
        for f in firmy[:FIREM_NA_OSOBU]:
            ico = f.get("ico")
            if not ico:
                continue
            if ico not in vpravo:
                vpravo[ico] = {
                    "id": ico,
                    "nazev": f.get("nazev"),
                    # Vztah firmy k městu rozhoduje o barvě: firma města,
                    # dodavatel města, nebo firma bez vazby na město.
                    "vztah": f.get("vztah_k_mestu") or "bez-vazby",
                }
            hrany.append({
                "od": o.get("osoba_id"),
                "do": ico,
                "popisek": f.get("funkce") or None,
                "jistota": ((o.get("overeni") or {}).get("stav") or "neznamo"),
            })
        zamlceno += max(0, len(firmy) - FIREM_NA_OSOBU)

    souhrn = p.get("souhrn") or {}
    poznamky = [
        "Rozsah jsou veřejně činné osoby: zastupitelé, radní, statutáři a členové "
        "dozorčích rad městských firem. Řadoví úředníci se nesledují.",
        "Firma bez vazby na město se ukazuje taky. Přiznat, kde je člověk aktivní, "
        f"patří k věci — takových firem je {_mezerou(_cely(souhrn.get('firem_bez_vazby_na_mesto')))}.",
        "Identita se dohledává přes jméno. Když sedí na víc lidí, je vazba označená "
        "jako nejednoznačná a nesmí se číst jako potvrzená. Sloučit dva lidi do "
        "jednoho záznamu je horší chyba než nechat je nespárované.",
    ]
    if zamlceno:
        poznamky.append(
            f"U osob s víc než {FIREM_NA_OSOBU} firmami se kreslí prvních "
            f"{FIREM_NA_OSOBU}; {_mezerou(zamlceno)} dalších vazeb je jen v tabulce pod diagramem."
        )

    return {
        "id": "propojeni",
        "nazev": "Kdo sedí v jakých firmách",
        "typ": "sit",
        "popis": (
            f"{_mezerou(len(vlevo))} veřejně činných osob a {_mezerou(len(vpravo))} firem. "
            f"Čára je doložené angažmá."
        ),
        "vlevo": {"nazev": "Osoby", "uzly": vlevo},
        "vpravo": {"nazev": "Firmy", "uzly": sorted(vpravo.values(), key=lambda x: x["nazev"] or "")},
        "hrany": hrany,
        # Klíče musí být tytéž, jaké nese `vztah_k_mestu` v datech — legenda
        # se podle nich obarvuje. Dřív tu stálo „dodavatel" a „bez-vazby",
        # což se s daty nepotkalo a vzorky vyšly bílé.
        "legenda": [
            {"klic": "mestsky-subjekt", "nazev": "firma nebo organizace města"},
            {"klic": "obchoduje-s-mestem", "nazev": "obchoduje s městem"},
            {"klic": "bez-vazby-na-mesto", "nazev": "bez vazby na město"},
        ],
        "metodika": poznamky,
        "zdroj": "data/propojeni/osoby_firmy.json",
        "stav": "ok",
    }


# ═══════════════════════════  5. Mapa zdrojů  ═════════════════════════════


def diagram_zdroje() -> dict:
    cfg = nacti_config("diagramy.json")
    zdroje = (cfg or {}).get("zdroje") or []
    if not zdroje:
        return _chybi("zdroje", "Který zdroj plní kterou sekci",
                      "config/diagramy.json nemá seznam zdrojů.", "config/diagramy.json")

    # Názvy sekcí se berou ze znaků, aby se diagram nerozešel s rozcestníkem.
    znaky = (nacti("znaky/sekce.json") or {}).get("znaky") or {}
    nazvy = {
        "vydani": "Týdenní přehled", "usneseni": "Usnesení", "hlasovani": "Hlasování",
        "penize": "Peníze města", "retez": "Od usnesení k penězům", "lide": "Lidé",
        "firmy": "Firmy", "propojeni": "Propojení", "volby": "Volby", "mapa": "Mapa",
        "statistika": "Čísla o městě", "zpravodaj": "Zpravodaj", "historie": "Historie",
    }

    sekce_poradi: list[str] = []
    hrany: list[dict] = []
    for z in zdroje:
        for s in z.get("plni") or []:
            if s not in sekce_poradi:
                sekce_poradi.append(s)
            hrany.append({"od": z["id"], "do": s, "popisek": None, "jistota": "potvrzeno"})

    stav_zdroju = ((nacti("casova_osa/souhrn.json") or {}).get("stav_zdroju") or {})

    return {
        "id": "zdroje",
        "nazev": "Který zdroj plní kterou sekci",
        "typ": "sit",
        "popis": (
            f"{len(zdroje)} veřejných zdrojů a {len(sekce_poradi)} sekcí webu. "
            "Čára znamená, že sekce z toho zdroje bere data."
        ),
        "vlevo": {"nazev": "Zdroje", "uzly": [
            {"id": z["id"], "nazev": z["nazev"], "popisek": z.get("url"),
             "pocet": len(z.get("plni") or []),
             # Druh zdroje nese barvu: úřad města / stát / média.
             "vztah": z.get("druh"),
             "jistota": "potvrzeno" if stav_zdroju.get(z["id"], "ok") == "ok" else "nejednoznacne"}
            for z in zdroje
        ]},
        "vpravo": {"nazev": "Sekce webu", "uzly": [
            {"id": s, "nazev": nazvy.get(s, s),
             "popisek": (znaky.get(s) or {}).get("hodnota"),
             "vztah": "sekce"}
            for s in sekce_poradi
        ]},
        "hrany": hrany,
        "legenda": [
            {"klic": "urad", "nazev": "úřad města"},
            {"klic": "stat", "nazev": "státní otevřená data"},
            {"klic": "media", "nazev": "média a záznamy"},
        ],
        "metodika": [
            "Tenhle diagram je AUTORSKÝ, ne zjištěný. Mapa „zdroj → sekce“ se ze "
            "sběru odvodit nedá, je napsaná v config/diagramy.json.",
            "Sekce, která bere z víc zdrojů, přežije výpadek jednoho z nich — jen "
            "o tom napíše. Sekce s jediným zdrojem při jeho výpadku neví nic.",
            "Nic se nenačítá z cizích serverů za běhu. Všechny zdroje se stahují "
            "v nedělním běhu a web se skládá už z uložených dat.",
        ],
        "zdroj": "config/diagramy.json",
        "stav": "ok",
    }


# ═══════════════════════════  6. Číselník tagů  ═══════════════════════════

def diagram_tagy() -> dict:
    cfg = nacti_config("tagy.json")
    tagy = (cfg or {}).get("tagy") or []
    if not tagy:
        return _chybi("tagy", "Číselník témat",
                      "config/tagy.json nemá žádné tagy.", "config/tagy.json")

    # Názvy skupin se berou z číselníku, ne z vlastní tabulky v tomhle
    # souboru. Ta se rozešla hned napoprvé: vymyslela klíče „sprava" a
    # „lide", které v číselníku nejsou, a skupina „radnice" pak v diagramu
    # zůstala jako holý klíč místo „Chod radnice".
    nazvy_skupin = {s.get("id"): s.get("nazev") for s in (cfg or {}).get("skupiny") or []}

    # Kolikrát se který tag opravdu použil. Tag, který nikdo nepoužil, je
    # v číselníku zbytečný a má být vidět, že je prázdný.
    pouziti: Counter[str] = Counter()
    for organ in ("rada", "zastupitelstvo"):
        koren = DATA / "usneseni" / organ
        if not koren.exists():
            continue
        for soubor in koren.rglob("*.json"):
            try:
                d = json.loads(soubor.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            for b in d.get("body") or []:
                for t in b.get("tagy") or []:
                    pouziti[t] += 1

    skupiny_map: dict[str, list[dict]] = defaultdict(list)
    for t in tagy:
        skupiny_map[t.get("skupina") or "bez-skupiny"].append({
            "id": t.get("id"),
            "nazev": t.get("nazev"),
            "popisek": t.get("popis"),
            # `None` znamená, že usnesení nejsou načtená — ne že se tag
            # nepoužil. Nula znamená, že se opravdu nepoužil ani jednou.
            "hodnota": pouziti.get(t.get("id"), 0) if pouziti else None,
        })

    vetve = []
    for klic, deti in skupiny_map.items():
        deti.sort(key=lambda d: -(d["hodnota"] or 0))
        vetve.append({
            "id": klic,
            "nazev": nazvy_skupin.get(klic, klic),
            "pocet": len(deti),
            "hodnota": sum(d["hodnota"] or 0 for d in deti) if pouziti else None,
            "deti": deti,
        })
    vetve.sort(key=lambda v: -(v["hodnota"] or 0))

    nepouzitych = sum(1 for v in vetve for d in v["deti"] if d["hodnota"] == 0) if pouziti else 0
    return {
        "id": "tagy",
        "nazev": "Číselník témat",
        "typ": "mysl",
        "popis": (
            f"{len(tagy)} pevných témat v {len(vetve)} skupinách. Číslo je počet "
            "bodů usnesení, které téma dostaly."
        ),
        "koren": {"id": "tagy", "nazev": "Témata usnesení", "popisek": f"{len(tagy)} tagů"},
        "vetve": vetve,
        "metodika": [
            "Číselník je PEVNÝ. Model témata nevymýšlí, jen vybírá z tohoto seznamu — "
            "jinak by každý běh vyrobil jiné názvy a filtrování by přestalo fungovat.",
            "Nový tag se přidává ručně do config/tagy.json, nikdy automaticky.",
            "Jeden bod usnesení může mít víc témat, součet přes skupiny je proto "
            "vyšší než počet bodů."
            + (f" {_mezerou(nepouzitych)} témat se zatím nepoužilo ani jednou."
               if nepouzitych else ""),
        ],
        "zdroj": "config/tagy.json + data/usneseni",
        "stav": "ok",
    }


# ═══════════════════════════  7. Datový model  ════════════════════════════


def diagram_model() -> dict:
    cfg = nacti_config("diagramy.json")
    model = (cfg or {}).get("model") or {}
    entity = model.get("entity") or []
    if not entity:
        return _chybi("model", "Jak jsou data poskládaná",
                      "config/diagramy.json nemá datový model.", "config/diagramy.json")

    # Kolik souborů každé entity na disku opravdu je. Diagram tak neříká jen
    # „tahle entita existuje“, ale i „a je jí tolik“.
    def spocitej(vzor: str) -> int | None:
        cast = vzor.replace("data/", "", 1)
        if "{" in cast:
            # Vzory s proměnnou částí (organ, rok) se počítají rekurzivně.
            zaklad = cast.split("{", 1)[0].rstrip("/")
            koren = DATA / zaklad
            return sum(1 for _ in koren.rglob("*.json")) if koren.exists() else None
        cesta = DATA / cast
        return 1 if cesta.exists() else None

    return {
        "id": "model",
        "nazev": "Jak jsou data poskládaná",
        "typ": "erd",
        "popis": (
            f"{len(entity)} entit a {len(model.get('vztahy') or [])} vztahů. "
            "Není to databáze — jsou to JSON soubory v data/."
        ),
        "entity": [
            {**e, "souboru": spocitej(e.get("soubor") or "")}
            for e in entity
        ],
        "vztahy": model.get("vztahy") or [],
        "metodika": [
            "Data nejsou v databázi. Jsou to JSON soubory a vztahy nedrží cizí "
            "klíč — drží je hodnota: IČO, slug osoby, číslo bodu usnesení.",
            "Vztah označený jako ODHAD nemá ve zdrojích oporu a spočítal ho tenhle "
            "projekt. Týká se to vazby usnesení → smlouva, která je nejcennější "
            "a zároveň nejméně jistá věc v celém přehledu.",
            "Vztah označený jako OVĚŘOVANÝ vzniká dohledáním jména v rejstříku. "
            "Nese vlastní stav ověření a nejednoznačná shoda se nesmí vydávat "
            "za potvrzenou.",
        ],
        "zdroj": "config/diagramy.json",
        "stav": "ok",
    }


# ═════════════════════════  8. Kdo řídí město  ════════════════════════════


def diagram_vedeni() -> dict:
    z = nacti("mesto/zastupitele.json")
    u = nacti("mesto/urad.json")
    if not z:
        return _chybi("vedeni", "Kdo řídí město",
                      "Seznam zastupitelů zatím není.", "data/mesto/zastupitele.json")

    zastupitele = z.get("zastupitele") or []
    poc: Counter[str] = Counter()
    for c in zastupitele:
        poc[(c.get("uskupeni") or "bez uskupení").strip()] += 1

    vedeni = (u or {}).get("vedeni_mesta") or []
    odbory = [o for o in ((u or {}).get("odbory") or []) if o.get("uroven") == 1]

    skupiny = [
        {
            "id": "zastupitelstvo",
            "nazev": f"Zastupitelstvo — {len(zastupitele)} členů",
            "popis": "Volí se v komunálních volbách. Schvaluje rozpočet a nakládání s majetkem.",
            # `pocet` = kolik uzlů se pod skupinou kreslí, ne kolik je členů.
            # Členů je 21, ale kreslí se sedm uskupení; kdyby tu stálo 21,
            # diagram by sliboval jednadvacet krabiček a nakreslil sedm.
            "pocet": len(poc),
            "deti": [
                {"id": f"u-{i}", "nazev": nazev, "popisek": f"{p} z {len(zastupitele)}",
                 "hodnota": p}
                for i, (nazev, p) in enumerate(sorted(poc.items(), key=lambda kv: (-kv[1], kv[0])))
            ],
        },
    ]
    if vedeni:
        skupiny.append({
            "id": "vedeni",
            "nazev": f"Vedení města — {len(vedeni)}",
            "popis": "Uvolnění i neuvolnění členové rady, jak je uvádí web města.",
            "pocet": len(vedeni),
            "deti": [
                {"id": v.get("id"), "nazev": v.get("jmeno"),
                 "popisek": f"{v.get('funkce')} · {v.get('uskupeni') or '—'}"}
                for v in vedeni
            ],
        })
    if odbory:
        skupiny.append({
            "id": "urad",
            "nazev": f"Městský úřad — {len(odbory)} odborů",
            "popis": f"Výkonná část. Web města uvádí {_mezerou(_cely((u or {}).get('osob_celkem')))} osob.",
            "pocet": len(odbory),
            "deti": [
                {"id": o.get("id"), "nazev": o.get("nazev"), "popisek": None}
                for o in odbory
            ],
        })

    return {
        "id": "vedeni",
        "nazev": "Kdo řídí město",
        "typ": "strom",
        "popis": (
            f"Zastupitelstvo ({len(zastupitele)}), vedení města ({len(vedeni)}) "
            f"a {len(odbory)} odborů úřadu."
        ),
        "koren": {
            "id": "mesto",
            "nazev": "Mariánské Lázně",
            "popisek": f"volební období {z.get('volebni_obdobi') or '—'}",
        },
        "skupiny": skupiny,
        "stranou": [],
        "metodika": [
            "Výbory zastupitelstva a komise rady tu NEJSOU. Web města je "
            "nezveřejňuje ve strojově čitelné podobě, takže o jejich složení "
            "projekt nic neví — a nedokreslují se dohadem.",
            "Zastupitelstvo je rozdělené podle volebního uskupení, ne podle klubu. "
            "Uskupení je to, se kterým kandidát prošel do zastupitelstva; klub se "
            "může lišit a web města ho neuvádí.",
            "Web města ukazuje jen aktuální funkci. Kdy funkce začala, se dopočítává "
            "porovnáním s předchozím během sběrače — u starších to znamená „nevíme“, "
            "ne „platí odjakživa“.",
        ],
        "zdroj": "data/mesto/zastupitele.json, data/mesto/urad.json",
        "stav": "ok",
    }


# ═══════════════════════════════  běh  ════════════════════════════════════

STAVITELE = [
    ("holding", diagram_holding),
    ("vedeni", diagram_vedeni),
    ("beh", diagram_beh),
    ("retez", diagram_retez),
    ("komise-rada", diagram_komise_rada),
    ("propojeni", diagram_propojeni),
    ("zdroje", diagram_zdroje),
    ("tagy", diagram_tagy),
    ("model", diagram_model),
]


def main() -> None:
    log = Log("diagramy")
    rejstrik = []

    for klic, stavitel in STAVITELE:
        try:
            d = stavitel()
        except Exception as e:  # noqa: BLE001
            # Jeden rozbitý diagram nesmí shodit ostatních sedm.
            log.chyba(f"diagram {klic}: {e}")
            d = _chybi(klic, klic, f"Diagram se nepodařilo sestavit: {e}", "—")
        uloz(f"diagramy/{klic}.json", d)
        rejstrik.append({
            "id": d.get("id", klic),
            "nazev": d.get("nazev", klic),
            "typ": d.get("typ"),
            "popis": d.get("popis"),
            "stav": d.get("stav", "chybi"),
            "zdroj": d.get("zdroj"),
        })
        log.pricti(1)

    chybejicich = sum(1 for r in rejstrik if r["stav"] != "ok")
    uloz("diagramy/index.json", {
        "metodika": {
            "co_to_je": (
                "Schémata projektu a města. Kreslí se při buildu jako SVG z těchhle "
                "souborů — proto se přepočítají s daty, umí tmavý motiv a nenačítá "
                "se k nim nic z cizího serveru."
            ),
            "zjistene_vs_tvrzene": (
                "Sedm diagramů je celé z dat. Mapa zdrojů a datový model stojí na "
                "config/diagramy.json, protože to je znalost o projektu, ne údaj "
                "o městě. Každý diagram to má napsané v poli `zdroj`."
            ),
            "prazdno": "Diagram bez dat se nekreslí prázdný — má stav `chybi` a napíše proč.",
        },
        "diagramu": len(rejstrik),
        "chybejicich": chybejicich,
        "diagramy": rejstrik,
    })

    log.info("diagramy sestaveny", pocet=len(rejstrik))
    if chybejicich:
        log.info("diagramů bez dat", pocet=chybejicich)
    log.uzavri()


if __name__ == "__main__":
    main()
