"""Dodatky ke smlouvám — spojit je s původní smlouvou, aby se nesčítaly dvakrát.

--------------------------------------------------------------------------
PROČ TENHLE MODUL VŮBEC JE
--------------------------------------------------------------------------
Dodatek ke smlouvě se v registru zveřejňuje jako **samostatný záznam**
a uvádí **novou celkovou cenu díla, ne přírůstek**. Ověřeno na datech:

    Rekonstrukce ul. Palackého  smlouva     24 184 616
                                dodatek č.1 24 182 800
                                dodatek č.2 26 118 056

Skutečná cena je 26,1 mil. Prostý součet dá 74,5 mil, tedy skoro trojnásobek.
Totéž u dotace ZSO 2024: 15 + 15 + 16,5 + 18,8 = 65,3 mil místo 18,8 mil.

Napříč sledovanými subjekty je v dodatcích 14 % objemu. Bez tohohle modulu
web nadhodnocuje, kolik město komu zaplatilo — a to je přesně ten druh čísla,
kvůli kterému lidé na takový přehled chodí.

--------------------------------------------------------------------------
JE TO ODHAD, NE ÚDAJ ZE ZDROJE
--------------------------------------------------------------------------
**Registr smluv vazbu dodatku na původní smlouvu neuvádí.** Ověřeno přes API
Hlídače na všech 82 smlouvách ZSO: `navazanyZaznam` i `souvisejiciSmlouvy`
jsou prázdné u všech a `cisloSmlouvy` dostane dodatek vlastní (dodatek
S488/24 k původní S580/23). Spojení se proto **počítá z předmětu smlouvy**
a je to odhad se vším všudy: ukládá se míra jistoty a měří se, jak často
sedí (`config/vzorek_dodatky.json`, přepínač `--overit`).

Zásada zbytku projektu platí i tady: co je dohad, se jako dohad označí.
Nesloučený dodatek se **nezahazuje** — jde do `nesparovane` a jeho objem
se přizná, aby se dílčí výsledek nedal číst jako úplný.

Vstup:  `data/penize/smlouvy/{ico}.json`
Výstup: `data/penize/dodatky.json`
"""
from __future__ import annotations

import argparse
import math
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import DATA, Log, nacti, nacti_config, uloz  # noqa: E402

VYSTUP = "penize/dodatky.json"
VZOREK = "vzorek_dodatky.json"

# Předmět, který o sobě říká, že je dodatek.
#
# Hranice slova ZA kmenem tu být nesmí: v datech je „Dodatekč.10 ke smlouvě
# o převzetí odpadu" (bez mezery) a `\b` po „dodatek" na „č" nesedne, takže
# se takový záznam tvářil jako originál a jiné dodatky se na něj vázaly.
#
# Kmen „dodat(ek|k)" naopak nechytá „dodatečný" ani sloveso „dodat" —
# po „dodat" tam následuje „eč", ne „ek" ani „k".
JE_DODATEK = re.compile(r"\bdodat(?:ek|k)", re.I)

# Úvodní fráze dodatku, která nenese nic o tom, čeho se týká. Odstraní se,
# aby zbyl jen předmět původního díla („rekonstrukce zpívající fontány").
PREFIX = re.compile(
    r"^\s*dodatek\s*(č\.?\s*\d+)?\s*"
    r"(ke?\s+)?(smlouv\w+|sod|sml\.?|so\s?d)?\s*"
    r"(o\s+dílo|o\s+poskytnutí)?\s*",
    re.I,
)

# Slova, která jsou ve smlouvách tak často, že o podobnosti nic neříkají.
STOPKY = {
    "smlouva", "smlouvy", "smlouve", "smlouvu", "smluvni", "dodatek", "dodatku",
    "mesta", "mesto", "mestem", "marianske", "lazne", "laznich", "marianskych",
    "poskytnuti", "poskytnutim", "dilo", "dila", "cislo", "kupni", "najemni",
    "verejnopravni", "uzavreni", "zmena", "zmene", "rozsah", "rozsahu", "ceny",
    "cena", "sod", "roku", "rok",
}

# Kolik měsíců zpátky se hledá původní smlouva. Stavební zakázka se
# dodatkuje i po dvou letech; delší okno už dělá víc škody než užitku.
OKNO_MESICU = 36

PRAH_VYSOKA = 0.55
PRAH_STREDNI = 0.30
PRAH_NIZKA = 0.15


def _bez_diakritiky(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def tokeny(predmet: str) -> set[str]:
    """Významová slova předmětu — bez diakritiky, bez stopek, od 4 znaků."""
    text = _bez_diakritiky(PREFIX.sub("", predmet or "")).lower()
    slova = re.findall(r"[a-z0-9]{3,}", text)
    return {s for s in slova if s not in STOPKY and (len(s) >= 4 or s.isdigit())}


def _mesice(a: str, b: str) -> int:
    """Rozdíl v měsících mezi dvěma „YYYY-MM-DD"; `9999` když datum chybí."""
    try:
        ra, ma = int(a[:4]), int(a[5:7])
        rb, mb = int(b[:4]), int(b[5:7])
    except (ValueError, IndexError):
        return 9999
    return abs((ra - rb) * 12 + (ma - mb))


def idf(vsechny: list[dict]) -> dict[str, float]:
    """Váha slova podle vzácnosti. „fontany" musí vážit víc než „oprava"."""
    n = max(1, len(vsechny))
    cetnost: Counter[str] = Counter()
    for s in vsechny:
        for t in tokeny(s.get("predmet") or ""):
            cetnost[t] += 1
    return {t: math.log(n / c) for t, c in cetnost.items()}


def podobnost(a: set[str], b: set[str], vahy: dict[str, float]) -> float:
    """Vážený Jaccard. Bez vah by „oprava chodníku" sedla na cokoliv."""
    if not a or not b:
        return 0.0
    prunik = sum(vahy.get(t, 1.0) for t in a & b)
    sjednoceni = sum(vahy.get(t, 1.0) for t in a | b)
    return prunik / sjednoceni if sjednoceni else 0.0


def jistota(skore: float) -> str | None:
    if skore >= PRAH_VYSOKA:
        return "vysoka"
    if skore >= PRAH_STREDNI:
        return "stredni"
    if skore >= PRAH_NIZKA:
        return "nizka"
    return None


def _cislo_dodatku(predmet: str) -> int | None:
    m = re.search(r"dodat\w*\s*(?:č\.?|c\.?|cislo)?\s*(\d{1,2})\b", predmet or "", re.I)
    return int(m.group(1)) if m else None


def nacti_smlouvy() -> list[dict]:
    """Všechny smlouvy sledovaných subjektů, každá právě jednou.

    DEDUPLIKACE JE NUTNÁ. Smlouva uvnitř holdingu (např. město ↔ TDS) leží
    v souboru obou stran, takže se načte dvakrát. Ze 6 521 řádků je jen
    6 264 různých smluv — 257 duplicit. Bez deduplikace se týž dodatek
    dostane do řetězu dvakrát a nafoukne počty i naivní součet, tedy přesně
    tu chybu, kterou má tenhle modul odstraňovat.
    """
    ven: list[dict] = []
    videne: set[str] = set()
    adr = DATA / "penize" / "smlouvy"
    for f in sorted(adr.glob("*.json")):
        d = nacti(f"penize/smlouvy/{f.name}", {}) or {}
        for s in d.get("smlouvy") or []:
            klic = str(s.get("id"))
            if klic in videne:
                continue
            videne.add(klic)
            ven.append({**s, "subjekt_ico": d.get("ico"), "subjekt": d.get("nazev")})
    return ven


def sparuj(smlouvy: list[dict], log: Log) -> dict:
    """Přiřadí každému dodatku původní smlouvu téže protistrany."""
    vahy = idf(smlouvy)

    # Klíč je DVOJICE STRAN, ne jen protistrana. Kdyby stačila protistrana,
    # slily by se do jednoho koše všechny smlouvy, kde je druhou stranou
    # město — a dotace KIS 2024 by posbírala dodatky k dotaci ZSO, protože
    # obojí je „Smlouva o poskytnutí neinvestiční dotace" od města. Přesně
    # to se stalo v první verzi.
    #
    # Množina, ne dvojice: smlouva uvnitř holdingu je vedená u obou stran
    # a směr se mezi jejich soubory obrací.
    def _klic(s: dict) -> frozenset:
        a = s.get("subjekt_ico") or "?"
        b = s.get("protistrana_ico") or ("nazev:" + (s.get("protistrana") or "?"))
        return frozenset({a, b})

    podle_protistrany: dict[frozenset, list[dict]] = defaultdict(list)
    for s in smlouvy:
        podle_protistrany[_klic(s)].append(s)

    retezy: list[dict] = []
    nesparovane: list[dict] = []
    # Dodatek se páruje na ORIGINÁL, ne na předchozí dodatek — jinak by
    # řetěz o třech dodatcích vznikl třikrát a součty by se zase rozjely.
    for klic, sm in podle_protistrany.items():
        sm.sort(key=lambda x: x.get("datum") or "")
        originaly = [x for x in sm if not JE_DODATEK.search(x.get("predmet") or "")]
        dodatky = [x for x in sm if JE_DODATEK.search(x.get("predmet") or "")]
        if not dodatky:
            continue

        pripojene: dict[str, list[dict]] = defaultdict(list)
        for d in dodatky:
            td = tokeny(d.get("predmet") or "")
            nejlepsi, nejskore = None, 0.0
            for o in originaly:
                if not o.get("datum") or not d.get("datum"):
                    continue
                if o["datum"] > d["datum"]:
                    continue
                if _mesice(o["datum"], d["datum"]) > OKNO_MESICU:
                    continue
                sk = podobnost(td, tokeny(o.get("predmet") or ""), vahy)
                if sk > nejskore:
                    nejlepsi, nejskore = o, sk

            j = jistota(nejskore) if nejlepsi else None
            if nejlepsi is None or j is None:
                nesparovane.append({
                    "id": d.get("id"),
                    "datum": d.get("datum"),
                    "castka_czk": d.get("castka_czk"),
                    "predmet": d.get("predmet"),
                    "protistrana": d.get("protistrana"),
                    "protistrana_ico": d.get("protistrana_ico"),
                    "subjekt_ico": d.get("subjekt_ico"),
                    "url": d.get("url"),
                    "duvod": "žádná dřívější smlouva téže protistrany dost podobná",
                })
                continue
            pripojene[nejlepsi["id"]].append({**d, "_skore": nejskore, "_jistota": j})

        for oid, ds in pripojene.items():
            o = next(x for x in originaly if x["id"] == oid)
            ds.sort(key=lambda x: (x.get("datum") or "", _cislo_dodatku(x.get("predmet") or "") or 0))
            # Nejnižší jistota v řetězu určuje jistotu celku — řetěz není
            # spolehlivější než jeho nejslabší článek.
            poradi = {"vysoka": 3, "stredni": 2, "nizka": 1}
            j_celku = min((d["_jistota"] for d in ds), key=lambda x: poradi[x])
            castky = [x.get("castka_czk") for x in [o, *ds] if x.get("castka_czk") is not None]
            retezy.append({
                "protistrana": o.get("protistrana"),
                "protistrana_ico": o.get("protistrana_ico"),
                "subjekt_ico": o.get("subjekt_ico"),
                "jistota": j_celku,
                "puvodni": {
                    "id": o.get("id"), "datum": o.get("datum"),
                    "castka_czk": o.get("castka_czk"), "predmet": o.get("predmet"),
                    "url": o.get("url"),
                },
                "dodatky": [{
                    "id": d.get("id"), "datum": d.get("datum"),
                    "castka_czk": d.get("castka_czk"), "predmet": d.get("predmet"),
                    "url": d.get("url"), "skore": round(d["_skore"], 3),
                    "jistota": d["_jistota"],
                } for d in ds],
                # Platná částka = NEJVYŠŠÍ uvedená částka v řetězu, ne
                # poslední. Ta úvaha stála za pokus a byla špatně: dodatky
                # v jednom řetězu MÍCHAJÍ dvě různé věci — přepsanou
                # celkovou cenu (fontána, dodatek č. 7 = 45,0 mil) i pouhý
                # přírůstek (tentýž řetěz, dodatky 1–5 po stovkách tisíc).
                # A dodatek umí mít částku 0, když cenu neuvádí: u smlouvy
                # IN HOUSE s TDS má originál 724,5 mil a dodatek č. 1 nulu,
                # takže „poslední článek" by z účtů smazal tři čtvrtě
                # miliardy.
                #
                # Maximum na všech ověřených řetězech vychází správně a
                # hlavně selhává bezpečným směrem: nikdy nesmaže originál.
                # PRAVDA LEŽÍ MEZI `castka_platna_czk` A NAIVNÍM SOUČTEM —
                # z registru se přesně určit nedá a web to musí říct.
                "castka_platna_czk": max(castky) if castky else None,
                "castka_naivni_soucet_czk": sum(castky) if castky else None,
            })

    retezy.sort(key=lambda r: -(r.get("castka_naivni_soucet_czk") or 0))

    dvojite = sum(
        (r["castka_naivni_soucet_czk"] or 0) - (r["castka_platna_czk"] or 0)
        for r in retezy
        if r.get("castka_platna_czk") is not None
    )
    log.info(
        "dodatky",
        retezu=len(retezy),
        dodatku_v_retezech=sum(len(r["dodatky"]) for r in retezy),
        nesparovanych=len(nesparovane),
        dle_jistoty=dict(Counter(r["jistota"] for r in retezy)),
        dvojite_zapocteno_mil=round(dvojite / 1e6, 1),
    )
    return {"retezy": retezy, "nesparovane": nesparovane, "dvojite_zapocteno_czk": dvojite}


def overeni(retezy: list[dict]) -> dict | None:
    """Změří, jak často odhad sedí, proti ručně rozsouzenému vzorku."""
    if not (Path(DATA).parent / "config" / VZOREK).exists():
        return None            # vzorek ještě není rozsouzený, není co měřit
    vzorek = nacti_config(VZOREK)
    if not vzorek:
        return None
    podle_id = {}
    for r in retezy:
        for d in r["dodatky"]:
            podle_id[str(d["id"])] = r["puvodni"]["id"]
    trefy: Counter[str] = Counter()
    celkem: Counter[str] = Counter()
    for p in vzorek.get("pripady") or []:
        j = p.get("jistota_ocekavana") or "celkem"
        celkem[j] += 1
        celkem["celkem"] += 1
        if podle_id.get(str(p.get("dodatek_id"))) == p.get("spravny_original_id"):
            trefy[j] += 1
            trefy["celkem"] += 1
    return {
        "zdroj": f"config/{VZOREK}",
        "presnost": {k: f"{trefy[k]}/{celkem[k]}" for k in sorted(celkem)},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Spojení dodatků s původní smlouvou")
    ap.add_argument("--overit", action="store_true",
                    help="změřit přesnost proti config/vzorek_dodatky.json")
    args = ap.parse_args()

    log = Log("dodatky")
    smlouvy = nacti_smlouvy()
    if not smlouvy:
        log.chyba("žádné smlouvy — spustit nejdřív sběr")
        log.uzavri()
        return 1

    vysledek = sparuj(smlouvy, log)
    objem_nesparovanych = sum(d.get("castka_czk") or 0 for d in vysledek["nesparovane"])

    vystup = {
        "metodika": (
            "Dodatek ke smlouvě se v registru zveřejňuje jako samostatný záznam "
            "a uvádí novou CELKOVOU cenu, ne přírůstek — prostý součet proto "
            "objem nadhodnocuje. Registr vazbu dodatku na původní smlouvu "
            "neuvádí (`navazanyZaznam` i `souvisejiciSmlouvy` jsou prázdné), "
            "takže se spojení POČÍTÁ z předmětu a je to odhad. Platná částka "
            "řetězu je NEJVYŠŠÍ uvedená částka v řetězu, ne poslední: dodatky "
            "míchají přepsanou celkovou cenu s pouhým přírůstkem a umí mít "
            "i nulu. Skutečná hodnota leží mezi `castka_platna_czk` "
            "a `castka_naivni_soucet_czk` a z registru se přesně určit nedá."
        ),
        "souhrn": {
            "retezu": len(vysledek["retezy"]),
            "dodatku_v_retezech": sum(len(r["dodatky"]) for r in vysledek["retezy"]),
            "nesparovanych": len(vysledek["nesparovane"]),
            "objem_nesparovanych_czk": objem_nesparovanych,
            "dvojite_zapocteno_czk": vysledek["dvojite_zapocteno_czk"],
            "dle_jistoty": dict(Counter(r["jistota"] for r in vysledek["retezy"])),
        },
        "overeni": overeni(vysledek["retezy"]),
        "retezy": vysledek["retezy"],
        "nesparovane": vysledek["nesparovane"],
    }
    uloz(VYSTUP, vystup)
    log.pricti(len(vysledek["retezy"]))
    log.uzavri()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
