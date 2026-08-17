"""Jednotná časová osa — jeden formát pro všechno, co má v projektu datum.

Vstup:  prakticky všechna datovaná data projektu (výčet níže)
Výstup: `data/casova_osa/` — souhrn, osa města, osy po letech a osy entit

--------------------------------------------------------------------------
K čemu to je
--------------------------------------------------------------------------
Každý modul si vede vlastní formát: usnesení mají body a čísla jednání,
smlouvy mají částky a protistrany, zpravodaj má čísla a strany, historie má
období. Web ale potřebuje u každé entity — u tématu, u člověka, u firmy —
ukázat **jednu osu**, na které je vidět vývoj v čase napříč zdroji.

Tenhle modul proto zdroje nepřepisuje. Čte je a skládá z nich **jeden
plochý typ záznamu** (níže „událost"), ke kterému si vždycky pamatuje, ze
kterého souboru a kterého klíče pochází. Osa nikdy není zdroj pravdy —
je to rejstřík ukazující zpátky do dat.

--------------------------------------------------------------------------
!!! JISTOTY SE NESMÍ SMÍCHAT !!!
--------------------------------------------------------------------------
Do osy vstupují dva zásadně různé druhy záznamů:

* **doložené záznamy** — usnesení bylo přijato, smlouva byla podepsána,
  článek vyšel. Ty nesou `jistota: "fakt"`.
* **odhady** — spojení usnesení → smlouva z `data/retez/retezy.json` nemá
  v datech žádný společný identifikátor a je složené z nepřímých indicií.
  Ty nesou `jistota` `vysoka` / `stredni` / `nizka` **beze změny z řetězu**
  a k tomu `jistota_duvod` s původním odůvodněním.

Řetěz s nízkou jistotou se v ose **nesmí** tvářit jako fakt: tvrdil by, že
konkrétní zastupitelé rozhodli o konkrétní zakázce, což je vážné obvinění.
Proto se `jistota` nikde nezahazuje, nepřepočítává ani nesjednocuje a web ji
MUSÍ u události zobrazit. Do souhrnů se odhady počítají zvlášť
(`pocty.dle_jistoty`), aby nešlo omylem sečíst fakta s domněnkami.

Historické události mají navíc hodnotu `sporne` — prameny se v údaji
rozcházejí a rozpor je popsaný v `poznamka`.

--------------------------------------------------------------------------
Formát události
--------------------------------------------------------------------------
```json
{
  "id": "hlasovani:rada-2026-108-2",
  "datum": "2026-01-06",        // ISO v přesnosti, jakou zdroj má
  "datum_do": null,             // konec intervalu (funkce, období), jinak null
  "presnost": "den",            // den | mesic | rok | obdobi
  "razeni": "2026-01-06",       // doplněné na celé datum, jen pro řazení
  "rok": 2026,
  "datum_podezrele": false,     // true = zdroj má zjevně zkomolený rok
  "typ": "hlasovani",           // viz TYPY
  "nadpis": "Dodatek č.1 k pojistné smlouvě …",
  "popis": "Rada města, bod 108/2. Pro 6, proti 0, zdrželo se 0.",
  "castka_czk": null,           // null = zdroj částku neuvádí, NIKDY ne nula
  "jistota": "fakt",            // fakt | vysoka | stredni | nizka
  "jistota_duvod": null,        // vyplněné jen u odhadů a nejistých údajů
  "osoby": ["hurajcik-martin"], // id z data/lide/osobnosti.json
  "firmy": ["25213261"],        // IČO
  "tagy": ["smlouvy"],          // id z config/tagy.json
  "organy": ["rada"],           // rada | zastupitelstvo | mesto
  "zdroj": "hlasovani",         // modul, ze kterého záznam pochází
  "zdroj_soubor": "data/hlasovani/rada/2026/108.json",
  "zdroj_klic": "rada-2026-108-2",
  "url": "https://usneseni.muml.cz/…",
  "detail": { … doplňky podle typu … }
}
```

Vazby na entity jsou **ploché** (`osoby`, `firmy`, `tagy`, `organy`), ne
zanořené pod jedním klíčem — takhle je čte web a takhle se nad nimi dá
filtrovat bez rozbalování.

`castka_czk` je `null`, když zdroj částku nemá. Nula znamená nulu, ne
„nevíme" — stejná zásada jako v `data/penize`.

--------------------------------------------------------------------------
Typy událostí (`typ`)
--------------------------------------------------------------------------
| typ         | odkud                                   | jistota          |
|-------------|-----------------------------------------|------------------|
| `historie`  | `data/historie/udalosti.json`           | fakt / sporne    |
| `funkce`    | `data/lide/osobnosti.json` → `funkce[]`  | fakt             |
| `usneseni`  | `data/usneseni/**`                       | fakt             |
| `hlasovani` | `data/hlasovani/**`                      | fakt             |
| `smlouva`   | `data/penize/smlouvy/*.json`             | fakt             |
| `retez`     | `data/retez/retezy.json`                 | vysoka/stredni/nizka |
| `zpravodaj` | `data/zpravodaj/clanky/**`               | fakt             |
| `media`     | `data/media/clanky.json`                 | fakt             |
| `volby`     | `data/opendata/volby/**` (volitelné)     | fakt             |
| `firma`     | `data/firmy/**` (volitelné)              | fakt             |

`volby` a `firmy` vznikají v jiných modulech souběžně. Když adresář
neexistuje, modul to **nepovažuje za chybu**, jen si to poznamená do
souhrnu jako `stav: "chybi"` — aby prázdná osa nevypadala jako stav světa.

--------------------------------------------------------------------------
Výstupní soubory
--------------------------------------------------------------------------
| soubor                            | co v něm je |
|-----------------------------------|-------------|
| `casova_osa/souhrn.json`          | metodika, stav zdrojů, počty, rozsah let, rejstřík entit |
| `casova_osa/roky/{rok}.json`      | **všechny** události daného roku, plné záznamy |
| `casova_osa/roky/nezarazene.json` | události se zkomoleným datem ze zdroje |
| `osy/mesto.json`                  | osa města — historické milníky, volby a roční agregáty |
| `osy/osoby/{osoba_id}.json`       | osa jedné osoby |
| `osy/firmy/{ico}.json`            | osa jedné firmy (podle IČO) |
| `osy/tagy/{tag}.json`             | osa jednoho tématu (podle tagu z číselníku) |

**Proč dva adresáře.** `data/casova_osa/` je úplná sada událostí, každá
v ní leží **právě jednou**. Web ji čte rekurzivně a skládá z ní celou osu;
kdyby ve stejném adresáři ležely i osy entit, přečetl by tutéž událost
pětkrát — jednou v ročníku, pak v ose osoby, firmy a každého jejího tématu.
Předpočítané osy entit proto bydlí v `data/osy/`.

Osy entit nesou **položky osy**: zkrácený tvar, který stačí k vykreslení
řádku (datum, přesnost, typ, nadpis, částka, jistota, odkaz) a nese `id`,
kterým se v `casova_osa/roky/{rok}.json` dohledá úplný záznam. Kdyby nesly
plné události, výstup by měl stovky megabajtů.

Osa firmy se zakládá od `--min-udalosti-firmy` událostí (výchozí 2): firma,
o které je v datech jediný záznam (typicky jen datum vzniku z rejstříku),
nemá co ukazovat v čase. Kolik firem se našlo a kolik dostalo osu, je
v `souhrn.json` → `entity`.

--------------------------------------------------------------------------
Hlasování v ose osoby: proč tam nejsou všechna
--------------------------------------------------------------------------
Ve jmenovitých hlasováních je 121 935 záznamů; u nejaktivnějšího zastupitele
skoro deset tisíc. Osa s deseti tisíci položkami „hlasoval pro" není osa,
je to výpis. V ose osoby jsou proto jednotlivě jen hlasování, která se něčím
liší, podle **objektivního** kritéria (žádné redakční vybírání):

* hlas byl `proti`, `zdrzel` nebo `nehlasoval` (neúčast ne — ta je jen
  v ročním souhrnu),
* bod neprošel (proti ≥ pro),
* nebo hlasování vede `data/propojeni/hlasovani_vazby.json` jako hlasování
  o firmě, ve které má hlasující angažmá.

Zbytek se **nezahazuje** — je sečtený v `hlasovani_po_letech` a celkový počet
sedí (`pocty.hlasovani_celkem`). Souhrn po letech uvádí jen **souhrnnou
neúčast** (`nepritomen`) a nerozpadá ji na omluvenou a neomluvenou: příznak
„omluven" ve starších datech neexistuje (zastupitelstvo od 2019, rada od 2023)
a rozpad by z jednoho člověka udělal stovky neomluvených absencí — což je
tvrzení o zdroji, ne o člověku.

--------------------------------------------------------------------------
Co osa ze své podstaty neumí
--------------------------------------------------------------------------
1. **Předkladatel bodu usnesení se z dat vytáhnout nedá.** Řetězec
   „Předkládá:" je v textu jen u bodů typu „Program 108. RM", které vypisují
   celý pořad jednání; mimo ně není ani jednou (ověřeno na všech 12 890
   bodech). Osoba se tedy k usnesení váže přes jmenovité hlasování, ne přes
   předkladatelství.
2. **Články zpravodaje odkazují na osoby, které nejsou mezi osobnostmi.**
   Slugů je v článcích výrazně víc než 199 záznamů v `osobnosti.json`. Osy se
   zakládají jen pro známé osobnosti; neznámé slugy zůstávají v události
   a jejich přehled je v `souhrn.json` → `nezname_osoby`, aby modul B1 věděl,
   koho případně doplnit.
3. **Zpravodaj je datovaný na měsíc, ne na den.** Události z článků mají
   `presnost: "mesic"` a v ose se řadí na první den měsíce.
4. **Registr smluv běží od 1. 7. 2016.** Prázdno před tímhle datem
   v ose firmy neznamená, že firma s městem neobchodovala.
5. **Jedna smlouva mezi dvěma sledovanými subjekty je v `data/penize`
   dvakrát** — jednou u každé strany. Do osy jde jako **jedna** událost
   se dvěma pohledy v `detail.dle_subjektu`; jinak by se její částka
   v ročních součtech započítala dvakrát.
6. **Část zdrojů má zkomolené datum** (v registru smluv se objevují roky
   jako 2, 25 nebo 26 — useknuté tisíciletí). Takový záznam se
   **neopravuje**: nese `datum_podezrele: true`, jde do
   `roky/nezarazene.json`, nevstupuje do výpočtu rozsahu a je vypsaný
   v `souhrn.json` → `podezrela_data`. Opravit ho musí modul, který
   data sbírá.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import DATA, Log, nacti, platne_tagy, uloz  # noqa: E402

# Dva adresáře se dvěma různými úkoly:
#   data/casova_osa/ = úplná sada událostí, každá právě jednou (roky/ + souhrn)
#   data/osy/        = předpočítané osy entit; nesou POLOŽKY, ne události
# Oddělení není kosmetika. Web čte data/casova_osa/ rekurzivně a skládá z něj
# celou osu; kdyby v témž adresáři ležely i osy entit, přečetl by tutéž
# událost pětkrát (jednou v roce, pak v ose osoby, firmy a každého tématu).
VYSTUP = "casova_osa"
VYSTUP_OSY = "osy"

TYPY = ("historie", "funkce", "usneseni", "hlasovani", "smlouva",
        "retez", "zpravodaj", "media", "volby", "firma")

# Jistoty. Fakt a sporne popisují doložený záznam, zbytek jsou odhady
# přebrané z řetězu usnesení → smlouva. Nikdy se nemíchají do jednoho součtu.
JISTOTY_FAKT = ("fakt", "sporne")
JISTOTY_ODHAD = ("vysoka", "stredni", "nizka")

# IČO v textu usnesení. Zdroj píše „IČ 12345678" i „IČO: 12345678".
RE_ICO = re.compile(r"I[ČC]O?[:\s]{0,3}(\d{8})")

# Rok mimo tohle okno je zjevně zkomolený (v registru smluv jsou datumy
# jako 0002-11-14 nebo 0026-06-02 — useknutá tisíciletí). Záznam se
# NEOPRAVUJE, jen se označí `datum_podezrele` a vypadne z výpočtu rozsahu,
# aby osa města nezačínala rokem 2. Oprava patří modulu, který data sbírá.
ROK_NEJDRIV = 1000
ROK_NEJPOZDEJI = date.today().year + 5


# --------------------------------------------------------------------------
# Datum
# --------------------------------------------------------------------------

def presnost_data(datum: str | None) -> str | None:
    """Podle délky ISO řetězce určí, jak přesně je záznam datovaný."""
    if not datum:
        return None
    d = str(datum).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        return "den"
    if re.fullmatch(r"\d{4}-\d{2}", d):
        return "mesic"
    if re.fullmatch(r"\d{4}", d):
        return "rok"
    return None


def razeni(datum: str) -> str:
    """Doplní částečné datum na celé, jen kvůli řazení.

    Doplněné hodnoty se nikam neukládají jako údaj — `datum` a `presnost`
    zůstávají takové, jaké je má zdroj, aby web nepředstíral přesnost,
    kterou data nemají.
    """
    d = str(datum).strip()
    if len(d) == 4:
        return d + "-01-01"
    if len(d) == 7:
        return d + "-01"
    return d[:10]


def rok_z(datum: str) -> int:
    return int(str(datum)[:4])


# --------------------------------------------------------------------------
# Stavba události
# --------------------------------------------------------------------------

def udalost(
    *,
    id: str,
    datum: str,
    typ: str,
    nadpis: str,
    popis: str,
    modul: str,
    soubor: str,
    klic: str | None = None,
    url: str | None = None,
    datum_do: str | None = None,
    presnost: str | None = None,
    castka_czk: float | int | None = None,
    jistota: str = "fakt",
    jistota_duvod: str | None = None,
    osoby: list[str] | None = None,
    firmy: list[str] | None = None,
    tagy: list[str] | None = None,
    organy: list[str] | None = None,
    detail: dict | None = None,
) -> dict:
    p = presnost or presnost_data(datum) or "rok"
    rok = rok_z(datum)
    return {
        "id": id,
        "datum": datum,
        "datum_do": datum_do,
        "presnost": p,
        "razeni": razeni(datum),
        "rok": rok,
        "datum_podezrele": not (ROK_NEJDRIV <= rok <= ROK_NEJPOZDEJI),
        "typ": typ,
        "nadpis": (nadpis or "").strip(),
        "popis": (popis or "").strip(),
        "castka_czk": castka_czk,
        "jistota": jistota,
        "jistota_duvod": jistota_duvod,
        # Vazby na entity jsou ploché, ne zanořené: web je čte jako
        # osoby / firmy / tagy přímo na záznamu.
        "osoby": sorted(set(osoby or [])),
        "firmy": sorted(set(firmy or [])),
        "tagy": sorted(set(tagy or [])),
        "organy": sorted(set(organy or [])),
        "zdroj": modul,
        "zdroj_soubor": soubor,
        "zdroj_klic": klic,
        "url": url,
        "detail": detail or {},
    }


def _rel(cesta: Path) -> str:
    """Cesta k souboru tak, jak ji zapisujeme do zdroj.soubor."""
    return "data/" + str(cesta.relative_to(DATA)).replace("\\", "/")


# Záznamy, které se do osy nedostaly, protože je nešlo umístit v čase.
# Nezahazují se tiše — jejich počet jde do souhrnu.
PRESKOCENO: Counter = Counter()


# --------------------------------------------------------------------------
# Zdroje
# --------------------------------------------------------------------------

def z_historie(log: Log) -> tuple[list[dict], str]:
    data = nacti("historie/udalosti.json")
    if not data:
        log.info("historie: soubor chybí")
        return [], "chybi"
    ven = []
    for e in data.get("udalosti", []):
        # Historie má vlastní slovník jistoty: dolozeno / nejiste. Do osy se
        # překládá na společný — a „nejiste" (prameny se rozcházejí) musí
        # skončit jako `nizka`, ne jako fakt. Původní hodnota se neztrácí,
        # zůstává v detail.jistota_zdroje.
        jz = e.get("jistota") or "dolozeno"
        jistota = {"dolozeno": "fakt", "nejiste": "nizka"}.get(jz, "nizka")
        ven.append(udalost(
            id=f"historie:{e['id']}",
            datum=e["datum"],
            datum_do=e.get("datum_do"),
            presnost=e.get("presnost"),
            typ="historie",
            nadpis=e["nazev"],
            popis=e["popis"],
            modul="historie",
            soubor="data/historie/udalosti.json",
            klic=e["id"],
            url=e.get("odkaz"),
            jistota=jistota,
            jistota_duvod=e.get("poznamka"),
            osoby=e.get("osoby"),
            tagy=e.get("tagy"),
            organy=["mesto"],
            detail={"kategorie": e.get("kategorie"),
                    "obdobi": e.get("obdobi"),
                    "jistota_zdroje": jz,
                    "zdroje": e.get("zdroje", [])},
        ))
    log.info("historie", udalosti=len(ven))
    return ven, "ok" if ven else "prazdno"


def z_funkci(log: Log, osobnosti: list[dict]) -> tuple[list[dict], str, int]:
    """Funkce osob jako intervalové události (od–do).

    Funkce bez data `od` se do osy nedostane — nedá se umístit. Kolik jich
    je, jde do souhrnu; není to chyba, zdroj to prostě neuvádí.
    """
    ven, bez_data = [], 0
    for o in osobnosti:
        for i, f in enumerate(o.get("funkce") or []):
            od = f.get("od")
            if not od:
                bez_data += 1
                PRESKOCENO["funkce_bez_data"] += 1
                continue
            do = f.get("do")
            p = presnost_data(od) or "rok"
            konec = "dosud" if not do else do
            ven.append(udalost(
                id=f"funkce:{o['id']}:{i}",
                datum=od,
                datum_do=do,
                presnost="obdobi" if do or f.get("do") is None else p,
                typ="funkce",
                nadpis=f"{o['jmeno']} — {f.get('nazev') or 'funkce'}",
                popis=f"{f.get('nazev') or 'funkce'} ({od} – {konec}).",
                modul="lide",
                soubor="data/lide/osobnosti.json",
                klic=f"{o['id']}#funkce[{i}]",
                osoby=[o["id"]],
                organy=["mesto"],
                detail={"funkce": f.get("nazev"), "strana": o.get("strana"),
                        "kategorie": o.get("kategorie"), "do": do},
            ))
    log.info("funkce", udalosti=len(ven), bez_data=bez_data)
    return ven, ("ok" if ven else "prazdno"), bez_data


def z_usneseni(log: Log) -> tuple[list[dict], str]:
    soubory = sorted((DATA / "usneseni").rglob("*.json"))
    if not soubory:
        log.info("usnesení: adresář chybí")
        return [], "chybi"
    ven = []
    for cesta in soubory:
        d = json.loads(cesta.read_text(encoding="utf-8"))
        organ, datum = d.get("organ"), d.get("datum")
        if not datum:
            PRESKOCENO["usneseni_bez_data"] += len(d.get("body", []))
            continue
        for b in d.get("body", []):
            icos = sorted(set(RE_ICO.findall(b.get("text") or "")))
            castka = b.get("castka_czk")
            vysl = b.get("vysledek")
            popis = f"{'Rada' if organ == 'rada' else 'Zastupitelstvo'} města, bod {b.get('cislo')}"
            if b.get("cislo_usneseni"):
                popis += f", usnesení {b['cislo_usneseni']}"
            popis += f". {vysl.capitalize()}." if vysl else "."
            ven.append(udalost(
                id=f"usneseni:{organ}-{rok_z(datum)}-{d.get('cj')}-{b.get('cislo')}",
                datum=datum,
                typ="usneseni",
                nadpis=b.get("nazev") or "(bez názvu)",
                popis=popis,
                modul="usneseni",
                soubor=_rel(cesta),
                klic=b.get("cislo"),
                url=b.get("url") or d.get("url"),
                castka_czk=castka,
                tagy=b.get("tagy"),
                firmy=icos,
                organy=[organ] if organ else [],
                detail={"cj": d.get("cj"), "cislo_usneseni": b.get("cislo_usneseni"),
                        "vysledek": vysl, "hlasovani_id": b.get("hlasovani_id"),
                        "obdobi": d.get("obdobi")},
            ))
    log.info("usnesení", udalosti=len(ven), souboru=len(soubory))
    return ven, "ok"


def z_hlasovani(log: Log, vazby_dle_hlasovani: dict) -> tuple[list[dict], str]:
    soubory = sorted((DATA / "hlasovani").rglob("*/*/*.json"))
    if not soubory:
        log.info("hlasování: adresář chybí")
        return [], "chybi"
    ven = []
    for cesta in soubory:
        d = json.loads(cesta.read_text(encoding="utf-8"))
        organ, datum = d.get("organ"), d.get("datum")
        if not datum:
            PRESKOCENO["hlasovani_bez_data"] += len(d.get("hlasovani", []))
            continue
        for h in d.get("hlasovani", []):
            hlasy = {j["osoba_id"]: j.get("hlas")
                     for j in (h.get("jmenovite") or []) if j.get("osoba_id")}
            hlasy_skupiny: dict[str, list[str]] = {}
            for _oid, _hlas in hlasy.items():
                hlasy_skupiny.setdefault(_hlas or "neznamy", []).append(_oid)
            pro, proti = h.get("pro") or 0, h.get("proti") or 0
            # Portál vede všechna hlasování jako „schváleno", včetně těch,
            # kde je proti víc hlasů než pro. Pole `vysledek` proto není
            # spolehlivé a výsledek se odvozuje z počtů hlasů.
            proslo = pro > proti
            vazba = vazby_dle_hlasovani.get(h.get("id"))
            popis = (f"{'Rada' if organ == 'rada' else 'Zastupitelstvo'} města, "
                     f"bod {h.get('bod')}. Pro {pro}, proti {proti}, "
                     f"zdrželo se {h.get('zdrzel') or 0}, "
                     f"nepřítomno {h.get('nepritomen') or 0}.")
            ven.append(udalost(
                id=f"hlasovani:{h.get('id')}",
                datum=datum,
                typ="hlasovani",
                nadpis=h.get("nazev") or "(bez názvu)",
                popis=popis,
                modul="hlasovani",
                soubor=_rel(cesta),
                klic=h.get("id"),
                tagy=h.get("tagy"),
                osoby=list(hlasy),
                firmy=[v["ico"] for v in vazba] if vazba else [],
                organy=[organ] if organ else [],
                detail={
                    "bod": h.get("bod"),
                    "cj": d.get("cj"),
                    "pro": pro, "proti": proti,
                    "zdrzel": h.get("zdrzel") or 0,
                    "nehlasoval": h.get("nehlasoval") or 0,
                    "nepritomen": h.get("nepritomen") or 0,
                    "proslo": proslo,
                    "vysledek_zdroje": h.get("vysledek"),
                    # Jmenovité hlasy po skupinách, ne mapa osoba→hlas:
                    # stejná informace v menším zápisu a rovnou je vidět,
                    # kdo byl proti.
                    "hlasy_dle_hlasu": hlasy_skupiny,
                    "vazba_na_firmu": vazba or None,
                },
            ))
    log.info("hlasování", udalosti=len(ven))
    return ven, "ok"


def z_smluv(log: Log) -> tuple[list[dict], str]:
    soubory = sorted((DATA / "penize" / "smlouvy").glob("*.json"))
    if not soubory:
        log.info("smlouvy: adresář chybí")
        return [], "chybi"
    ven: list[dict] = []
    # id smlouvy → už vyrobená událost. Registr smluv vede jednu smlouvu
    # u obou stran, a když jsou sledované obě, přišla by do osy dvakrát.
    dle_id: dict[str, dict] = {}
    dvojich = 0
    for cesta in soubory:
        d = json.loads(cesta.read_text(encoding="utf-8"))
        subjekt_ico, subjekt = d.get("ico"), d.get("nazev")
        for s in d.get("smlouvy", []):
            datum = s.get("datum")
            if not datum:
                PRESKOCENO["smlouvy_bez_data"] += 1
                continue
            # Zdroj u části smluv místo protistrany uvádí zveřejňující
            # subjekt. Taková „protistrana" nic neříká a do vazeb nepatří.
            pico = s.get("protistrana_ico")
            protistrana_urcena = bool(pico) and pico != subjekt_ico
            firmy = [subjekt_ico] + ([pico] if protistrana_urcena else [])
            smer = s.get("smer")
            popis = (f"{subjekt} — "
                     f"{'výdaj' if smer == 'vydaj' else 'příjem' if smer == 'prijem' else 'smlouva'}"
                     + (f", protistrana {s.get('protistrana')}" if protistrana_urcena else "")
                     + ".")
            pohled = {"subjekt_ico": subjekt_ico, "subjekt": subjekt,
                      "smer": smer, "soubor": _rel(cesta)}
            drive = dle_id.get(s.get("id"))
            if drive is not None:
                # Táž smlouva podruhé: obě strany jsou sledované subjekty
                # (např. město a Infocentrum, domov pro seniory a nemocnice).
                # Je to jedna listina, ne dvě — jinak by se její částka
                # v součtech započítala dvakrát. Druhý pohled se přidá.
                drive["firmy"] = sorted(
                    set(drive["firmy"]) | {f for f in firmy if f})
                drive["detail"]["dle_subjektu"].append(pohled)
                drive["detail"]["vice_subjektu"] = True
                if (drive["castka_czk"] or 0) != (s.get("castka_czk") or 0):
                    drive["detail"]["castka_se_lisi_dle_subjektu"] = True
                dvojich += 1
                continue

            u = udalost(
                id=f"smlouva:{s.get('id')}",
                datum=datum,
                typ="smlouva",
                nadpis=s.get("predmet") or "(bez předmětu)",
                popis=popis,
                modul="penize",
                soubor=_rel(cesta),
                klic=str(s.get("id")),
                url=s.get("url"),
                castka_czk=s.get("castka_czk"),
                firmy=[f for f in firmy if f],
                organy=["mesto"],
                detail={
                    "subjekt_ico": subjekt_ico, "subjekt": subjekt,
                    "protistrana_ico": pico if protistrana_urcena else None,
                    "protistrana": s.get("protistrana"),
                    "protistrana_neurcena": not protistrana_urcena,
                    "smer": smer, "vada": s.get("vada"),
                    "bez_ceny": s.get("bez_ceny"),
                    "kategorie": s.get("kategorie"),
                    "dle_subjektu": [pohled],
                    "vice_subjektu": False,
                },
            )
            dle_id[s.get("id")] = u
            ven.append(u)
    if dvojich:
        log.info("smlouvy uvnitř holdingu vedené u obou stran se sloučily "
                 "do jedné události", sloucenych=dvojich)
    log.info("smlouvy", udalosti=len(ven))
    return ven, "ok"


def z_retezu(log: Log) -> tuple[list[dict], str]:
    """Spojení usnesení → smlouva. POZOR: odhad, ne doklad.

    `jistota` a `duvod` se přebírají beze změny. Záznamy z pole
    `podpis_pred_usnesenim` do osy nevstupují — metodika řetězu je
    výslovně označuje za varování, ne za shodu.
    """
    d = nacti("retez/retezy.json")
    if not d:
        log.info("řetěz: soubor chybí")
        return [], "chybi"
    ven = []
    for r in d.get("retezy", []):
        us, sml = r.get("usneseni") or {}, r.get("smlouva") or {}
        datum = sml.get("datum") or us.get("datum")
        if not datum:
            PRESKOCENO["retezy_bez_data"] += 1
            continue
        firmy = [x for x in (sml.get("protistrana_ico"), sml.get("subjekt_ico")) if x]
        ven.append(udalost(
            id=f"retez:{r.get('id')}",
            datum=datum,
            typ="retez",
            nadpis=sml.get("predmet") or "smlouva",
            popis=(f"Odhadované spojení smlouvy z {sml.get('datum')} s bodem "
                   f"{us.get('bod')} z {us.get('datum')} "
                   f"({us.get('nazev') or 'usnesení'}). Jistota {r.get('jistota')}."),
            modul="retez",
            soubor="data/retez/retezy.json",
            klic=r.get("id"),
            url=sml.get("url"),
            castka_czk=sml.get("castka_czk"),
            jistota=r.get("jistota") or "nizka",
            jistota_duvod=r.get("duvod"),
            tagy=us.get("tagy"),
            firmy=firmy,
            organy=[us.get("organ")] if us.get("organ") else [],
            detail={
                "skore": r.get("skore"), "signaly": r.get("signaly"),
                "odstup_dni": r.get("odstup_dni"),
                "kandidatu_usneseni": r.get("kandidatu_usneseni"),
                "kandidatu_smluv": r.get("kandidatu_smluv"),
                "usneseni_datum": us.get("datum"), "usneseni_bod": us.get("bod"),
                "usneseni_url": us.get("url"),
                "smlouva_id": sml.get("id"), "protistrana": sml.get("protistrana"),
            },
        ))
    log.info("řetěz (odhady)", udalosti=len(ven),
             dle_jistoty=dict(Counter(u["jistota"] for u in ven)))
    return ven, "ok"


def z_zpravodaje(log: Log) -> tuple[list[dict], str]:
    korenove = DATA / "zpravodaj" / "clanky"
    soubory = sorted(korenove.glob("*/*.json"))
    if not soubory:
        log.info("zpravodaj: adresář chybí")
        return [], "chybi"
    cisla = {c["id"]: c for c in (nacti("zpravodaj/cisla.json") or [])}
    ven = []
    for cesta in soubory:
        a = json.loads(cesta.read_text(encoding="utf-8"))
        cislo = a.get("cislo") or cesta.parent.name
        c = cisla.get(cislo) or {}
        rok, mesic = c.get("rok"), c.get("mesic")
        if rok and mesic:
            datum = f"{rok:04d}-{mesic:02d}"
        elif re.fullmatch(r"\d{4}-\d{2}", str(cislo)):
            datum = str(cislo)
        else:
            PRESKOCENO["clanky_zpravodaje_bez_data"] += 1
            continue
        ven.append(udalost(
            id=f"zpravodaj:{a.get('id')}",
            datum=datum,
            presnost="mesic",
            typ="zpravodaj",
            nadpis=a.get("nadpis") or "(bez nadpisu)",
            popis=(a.get("perex") or "").strip().replace("\n", " ")[:300],
            modul="zpravodaj",
            soubor=_rel(cesta),
            klic=a.get("id"),
            url=a.get("pdf_odkaz"),
            osoby=a.get("osoby"),
            tagy=a.get("tagy"),
            organy=["mesto"],
            detail={"cislo": cislo, "strana": a.get("strana"),
                    "rubrika": a.get("rubrika"),
                    "nazev_cisla": c.get("nazev")},
        ))
    log.info("zpravodaj", udalosti=len(ven))
    return ven, "ok"


def z_medii(log: Log) -> tuple[list[dict], str]:
    clanky = nacti("media/clanky.json")
    if clanky is None:
        log.info("média: soubor chybí")
        return [], "chybi"
    ven = []
    for a in clanky:
        datum = a.get("datum")
        if not datum:
            PRESKOCENO["medialni_clanky_bez_data"] += 1
            continue
        ven.append(udalost(
            id=f"media:{a.get('id')}",
            datum=datum,
            typ="media",
            nadpis=a.get("titulek") or "(bez titulku)",
            popis=(a.get("shrnuti") or "").strip().replace("\n", " ")[:400],
            modul="media",
            soubor="data/media/clanky.json",
            klic=a.get("id"),
            url=a.get("url"),
            osoby=a.get("osoby"),
            tagy=a.get("tagy"),
            organy=["mesto"],
            detail={"zdroj_media": a.get("zdroj"), "stav": a.get("stav")},
        ))
    log.info("média", udalosti=len(ven))
    return ven, "ok"


def z_voleb(log: Log) -> tuple[list[dict], str]:
    """Volby z `data/opendata/volby/` (vzniká souběžně v jiném modulu).

    Čtou se dva soubory se známým tvarem:
      * `cykly/{cyklus}.json` → jedno kolo voleb = jedna událost
      * `zastupitele.json`    → jeden zvolený zastupitel = jedna událost

    Ostatní soubory adresáře (okrsky, geometrie, vlastní osa modulu) se
    záměrně nečtou — nejsou datované události. Když adresář existuje, ale
    ani jeden ze známých souborů v něm není, je to `neznamy_format`;
    nic se nehádá.
    """
    koren = DATA / "opendata" / "volby"
    if not koren.exists():
        log.info("volby: adresář data/opendata/volby zatím neexistuje")
        return [], "chybi"

    ven: list[dict] = []
    cykly = sorted((koren / "cykly").glob("*.json"))
    for cesta in cykly:
        try:
            c = json.loads(cesta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.chyba(f"volby: {cesta.name} není platný JSON")
            continue
        rok, nazev = c.get("rok"), c.get("nazev") or "Volby"
        for i, v in enumerate(c.get("volby") or []):
            datum = v.get("datum") or (str(rok) if rok else None)
            if not datum or not presnost_data(str(datum)):
                PRESKOCENO["volby_bez_data"] += 1
                continue
            ucast = v.get("ucast") or {}
            strany = sorted((v.get("strany") or []),
                            key=lambda s: s.get("hlasy") or 0, reverse=True)
            vitez = strany[0] if strany else None
            kolo = v.get("kolo")
            popis = nazev + (f", {kolo}. kolo" if kolo else "") + "."
            if ucast.get("ucast_proc") is not None:
                popis += f" Účast {ucast['ucast_proc']} %."
            if vitez:
                popis += (f" Nejvíc hlasů: {vitez.get('nazev')} "
                          f"({vitez.get('hlasy_proc')} %).")
            ven.append(udalost(
                id=f"volby:{c.get('cyklus')}-{i}",
                datum=str(datum),
                presnost="rok" if not v.get("datum") else None,
                typ="volby",
                nadpis=f"{nazev} {rok}" if rok else nazev,
                popis=popis,
                modul="opendata",
                soubor=_rel(cesta),
                klic=c.get("cyklus"),
                url=c.get("zdroj"),
                organy=["mesto"],
                detail={
                    "cyklus": c.get("cyklus"), "druh": c.get("druh"),
                    "kolo": kolo, "stav": c.get("stav"),
                    "ucast": ucast, "mandatu": v.get("mandatu"),
                    "poradi_stran": [
                        {"nazev": s.get("nazev"), "hlasy": s.get("hlasy"),
                         "hlasy_proc": s.get("hlasy_proc"),
                         "mandaty": s.get("mandaty")}
                        for s in strany[:10]
                    ],
                },
            ))

    zastupitele = nacti("opendata/volby/zastupitele.json") or []
    for z in zastupitele:
        datum = z.get("datum") or (str(z["rok"]) if z.get("rok") else None)
        if not datum or not presnost_data(str(datum)):
            PRESKOCENO["zvoleni_zastupitele_bez_data"] += 1
            continue
        ven.append(udalost(
            id=f"volby:zvolen:{z.get('cyklus')}:{z.get('osoba_id')}",
            datum=str(datum),
            typ="volby",
            nadpis=f"{z.get('jmeno')} zvolen(a) do zastupitelstva města",
            popis=(f"Zvolen(a) za {z.get('strana')} s {z.get('hlasy')} hlasy "
                   f"({z.get('hlasy_proc')} %), {z.get('poradi_mandatu')}. mandát."),
            modul="opendata",
            soubor="data/opendata/volby/zastupitele.json",
            klic=f"{z.get('cyklus')}:{z.get('osoba_id')}",
            osoby=[z["osoba_id"]] if z.get("osoba_id") else [],
            organy=["zastupitelstvo"],
            detail={"cyklus": z.get("cyklus"), "strana": z.get("strana"),
                    "hlasy": z.get("hlasy"), "hlasy_proc": z.get("hlasy_proc"),
                    "poradi_na_listine": z.get("poradi_na_listine"),
                    "poradi_mandatu": z.get("poradi_mandatu"),
                    "povolani": z.get("povolani")},
        ))

    if not cykly and not zastupitele:
        log.chyba("volby: adresář existuje, ale nemá cykly/*.json ani "
                  "zastupitele.json — formát se změnil, osa je nečte")
        return [], "neznamy_format"
    log.info("volby", udalosti=len(ven), cyklu=len(cykly),
             zvolenych=len(zastupitele))
    return ven, ("ok" if ven else "prazdno")


def z_firem(log: Log) -> tuple[list[dict], str]:
    """Rejstříkové události firem z `data/firmy/subjekty.json` (modul vzniká souběžně).

    Z registru se berou dvě data, která tam skutečně jsou: vznik a zánik
    subjektu. Nic dalšího se nedopočítává — ostatní soubory adresáře jsou
    agregáty, ne datované události.

    POZOR na výklad: adresní index ARES nevede zaniklé subjekty, takže
    „vzniků v roce X" ubývá do minulosti tím víc, čím je rok starší. Osa
    firmy tím netrpí (jde o konkrétní subjekt), ale součet vzniků po letech
    ano — proto se tu žádný takový součet nedělá.
    """
    koren = DATA / "firmy"
    if not koren.exists():
        log.info("firmy: adresář data/firmy zatím neexistuje")
        return [], "chybi"
    reg = nacti("firmy/subjekty.json")
    if not reg or not reg.get("subjekty"):
        log.info("firmy: data/firmy/subjekty.json chybí nebo je prázdný")
        return [], "prazdno" if reg else "neznamy_format"

    ven = []
    for f in reg["subjekty"]:
        ico = str(f.get("ico") or "").strip()
        if not ico:
            PRESKOCENO["firmy_bez_ica"] += 1
            continue
        nazev = f.get("nazev") or ico
        for pole, popisek, kategorie in (
            ("datum_vzniku", "Vznik subjektu", "vznik"),
            ("datum_zaniku", "Zánik subjektu", "zanik"),
        ):
            datum = f.get(pole)
            if not datum:
                if pole == "datum_vzniku":
                    PRESKOCENO["firmy_bez_data_vzniku"] += 1
                continue
            if not presnost_data(str(datum)):
                PRESKOCENO["firmy_nesrozumitelne_datum"] += 1
                continue
            ven.append(udalost(
                id=f"firma:{ico}:{kategorie}",
                datum=str(datum),
                typ="firma",
                nadpis=f"{popisek} — {nazev}",
                popis=(f"{popisek} {nazev} (IČO {ico}), "
                       f"{f.get('pravni_forma_nazev') or 'právní forma neuvedena'}"
                       + (f", obor: {f['nace_prevazujici_nazev']}"
                          if f.get("nace_prevazujici_nazev") else "") + "."),
                modul="firmy",
                soubor="data/firmy/subjekty.json",
                klic=ico,
                firmy=[ico],
                detail={
                    "kategorie": kategorie,
                    "nazev": nazev,
                    "stav": f.get("stav"),
                    "pravni_forma": f.get("pravni_forma_nazev"),
                    "adresa": f.get("adresa"),
                    "sidlo_v_obci": f.get("sidlo_v_obci"),
                    "obor": f.get("nace_prevazujici_nazev"),
                    "zamestnancu_rozsah": f.get("zamestnancu_rozsah"),
                },
            ))
    log.info("firmy", udalosti=len(ven), subjektu=len(reg["subjekty"]))
    return ven, ("ok" if ven else "prazdno")


# --------------------------------------------------------------------------
# Osy entit
# --------------------------------------------------------------------------

def polozka(u: dict, role: dict | None = None) -> dict:
    """Zkrácený tvar události pro osu entity — „položka osy".

    Osy entit nesou položky, ne plné události. Položka má všechno, co je
    potřeba k vykreslení řádku osy (datum, přesnost, typ, nadpis, částka,
    jistota, odkaz), a `id`, kterým se v `casova_osa/roky/{rok}.json`
    dohledá úplný záznam se vším detailem.

    Kdyby osy entit nesly plné události, výstup by měl stovky megabajtů:
    jedna událost se objevuje až ve třech osách tagů, v ose firmy
    i v ose každého hlasujícího.
    """
    p = {
        "id": u["id"],
        "datum": u["datum"],
        "datum_do": u["datum_do"],
        "presnost": u["presnost"],
        "razeni": u["razeni"],
        "rok": u["rok"],
        "typ": u["typ"],
        "nadpis": u["nadpis"],
        "popis": u["popis"][:160],
        "castka_czk": u["castka_czk"],
        "jistota": u["jistota"],
        # Odůvodnění se nese jen tam, kde na něm záleží — u odhadů.
        # U doložených záznamů je vždycky prázdné a jen by nafukovalo soubor.
        "jistota_duvod": (u["jistota_duvod"] or "")[:200] if u["jistota"] != "fakt" else None,
        "url": u["url"],
        "zdroj": u["zdroj"],
        "zdroj_soubor": u["zdroj_soubor"],
    }
    if u["datum_podezrele"]:
        p["datum_podezrele"] = True
    if role:
        p["role"] = role
    return p


def osa_osoby(osoba: dict, udalosti: list[dict]) -> dict:
    """Sestaví osu jedné osoby. Rutinní hlasování se agreguje po letech."""
    ven, po_letech = [], defaultdict(Counter)
    hlasovani_celkem = vynechano = 0

    for u in udalosti:
        if u["typ"] == "hlasovani":
            hlasovani_celkem += 1
            d = u["detail"]
            hlas = next((h for h, ids in (d.get("hlasy_dle_hlasu") or {}).items()
                         if osoba["id"] in ids), None)
            po = po_letech[u["rok"]]
            po["celkem"] += 1
            po[hlas or "neznamy"] += 1
            vazba = [v for v in (d.get("vazba_na_firmu") or [])
                     if v.get("osoba_id") == osoba["id"]]
            # Neúčast se do osy jednotlivě NEDÁVÁ. Je to nepřítomnost, ne
            # projev vůle, a stovky řádků „nepřítomen" na ose člověka by
            # z ní udělaly výčet absencí — přesně to, před čím varuje
            # docs/PROVOZ.md. Neúčast je jen v souhrnu po letech.
            zajimave = (hlas in ("proti", "zdrzel", "nehlasoval")
                        or not d.get("proslo") or bool(vazba))
            if not zajimave:
                vynechano += 1
                continue
            ven.append(polozka(u, {"vztah": "hlasoval", "hlas": hlas,
                                   "proslo": d.get("proslo"),
                                   "vazba_na_firmu": vazba or None}))
            continue

        vztah = {
            "funkce": "funkce",
            "zpravodaj": "zminen_v_clanku",
            "media": "zminen_v_clanku",
            "historie": "historicka_udalost",
            "volby": "zvolen",
            "firma": "angazma",
        }.get(u["typ"], "zminen")
        ven.append(polozka(u, {"vztah": vztah}))

    ven.sort(key=lambda u: (u["razeni"], u["id"]))
    roky = [{"rok": r, **dict(po_letech[r])} for r in sorted(po_letech)]
    return {
        "entita": {
            "typ": "osoba",
            "id": osoba["id"],
            "jmeno": osoba.get("jmeno"),
            "role": osoba.get("role") or [],
            "kategorie": osoba.get("kategorie"),
            "strana": osoba.get("strana"),
            "zijici": osoba.get("zijici"),
        },
        "metodika": METODIKA_OSOBA,
        "rozsah": _rozsah(ven),
        "pocty": _pocty(ven, hlasovani_celkem=hlasovani_celkem,
                        hlasovani_v_ose=hlasovani_celkem - vynechano,
                        hlasovani_v_souhrnu=vynechano),
        "hlasovani_po_letech": roky,
        "udalosti": ven,
    }


def osa_firmy(ico: str, nazev: str | None, udalosti: list[dict]) -> dict:
    ven = []
    for u in udalosti:
        d = u["detail"]
        if u["typ"] == "smlouva":
            vztah = "protistrana" if d.get("protistrana_ico") == ico else "subjekt"
        elif u["typ"] == "usneseni":
            vztah = "zminena_v_usneseni"
        elif u["typ"] == "hlasovani":
            vztah = "hlasovani_s_vazbou"
        elif u["typ"] == "retez":
            vztah = "odhadovane_spojeni"
        else:
            vztah = "zminena"
        ven.append(polozka(u, {"vztah": vztah}))
    ven.sort(key=lambda u: (u["razeni"], u["id"]))
    return {
        "entita": {"typ": "firma", "ico": ico, "nazev": nazev},
        "metodika": METODIKA_FIRMA,
        "rozsah": _rozsah(ven),
        "pocty": _pocty(ven),
        "udalosti": ven,
    }


def osa_tagu(tag: str, nazev: str | None, udalosti: list[dict]) -> dict:
    ven = sorted((polozka(u, {"vztah": "tema"}) for u in udalosti),
                 key=lambda u: (u["razeni"], u["id"]))
    return {
        "entita": {"typ": "tag", "id": tag, "nazev": nazev},
        "metodika": METODIKA_TAG,
        "rozsah": _rozsah(ven),
        "pocty": _pocty(ven),
        "udalosti": ven,
    }


def _rozsah(udalosti: list[dict]) -> dict:
    """Rozsah osy. Záznamy se zkomoleným datem se do něj nepočítají —
    zůstávají v ose s příznakem `datum_podezrele`, ale nesmí posunout
    začátek osy města do starověku."""
    dobre = [u for u in udalosti if not u.get("datum_podezrele")]
    podezrelych = len(udalosti) - len(dobre)
    if not dobre:
        return {"od": None, "do": None, "prvni_rok": None, "posledni_rok": None,
                "podezrelych_dat": podezrelych}
    razene = sorted(dobre, key=lambda u: u["razeni"])
    return {
        "od": razene[0]["datum"],
        "do": razene[-1]["datum"],
        "prvni_rok": razene[0]["rok"],
        "posledni_rok": razene[-1]["rok"],
        "podezrelych_dat": podezrelych,
    }


def uklid(zaklad: str, podadresar: str, ponechat: set[str]) -> int:
    """Smaže osy, které tenhle běh už nevyrobil.

    Bez toho by po odstranění osobnosti nebo firmy ze zdrojových dat zůstal
    její soubor navěky a web by ukazoval osu entity, která v datech není.
    """
    koren = DATA / zaklad / podadresar
    if not koren.exists():
        return 0
    smazano = 0
    for cesta in koren.glob("*.json"):
        if cesta.stem not in ponechat:
            cesta.unlink()
            smazano += 1
    return smazano


def _pocty(udalosti: list[dict], **extra) -> dict:
    """Počty. Fakta a odhady se zásadně počítají odděleně."""
    dle_typu = Counter(u["typ"] for u in udalosti)
    dle_jistoty = Counter(u["jistota"] for u in udalosti)
    return {
        "celkem": len(udalosti),
        "dolozenych": sum(v for k, v in dle_jistoty.items() if k in JISTOTY_FAKT),
        "odhadu": sum(v for k, v in dle_jistoty.items() if k in JISTOTY_ODHAD),
        "dle_typu": dict(dle_typu),
        "dle_jistoty": dict(dle_jistoty),
        **extra,
    }


METODIKA_OBECNA = {
    "co_to_je": (
        "Jednotná časová osa. Sesbírané datované záznamy ze všech zdrojů projektu "
        "v jednom formátu. Osa není zdroj pravdy — každá událost nese zdroj.soubor "
        "a zdroj.klic, kterými se dohledá původní záznam."
    ),
    "jistota": (
        "fakt = doložený záznam (usnesení, smlouva, článek). sporne = historický údaj, "
        "ve kterém se prameny rozcházejí (rozpor je v jistota_duvod). "
        "vysoka / stredni / nizka = ODHAD spojení usnesení → smlouva, převzatý beze změny "
        "z data/retez/retezy.json. Odhad se nesmí zobrazovat jako fakt a v součtech "
        "je oddělený (pocty.dolozenych vs. pocty.odhadu)."
    ),
    "castka": "castka_czk je null, když zdroj částku neuvádí. Nula znamená nulu.",
    "presnost": (
        "presnost říká, jak přesně je záznam datovaný (den / mesic / rok / obdobi). "
        "Pole razeni je datum doplněné na celý den JEN kvůli řazení — není to údaj "
        "ze zdroje a nesmí se zobrazovat."
    ),
    "chybejici_zdroj": (
        "Zdroj, který v datech není, má v souhrnu stav chybi. To není totéž jako prazdno. "
        "Prázdná osa kvůli chybějícímu zdroji nesmí vypadat jako „nic se nedělo“."
    ),
    "rozlozeni": (
        "data/casova_osa/roky/{rok}.json je úplná sada událostí, každá právě jednou — "
        "kdo čte celý adresář, dostane celou osu bez duplicit. Předpočítané osy entit "
        "jsou v data/osy/ (mesto.json, osoby/, firmy/, tagy/) a nesou POLOŽKY, "
        "které se přes id dohledají v roky/. Kdyby ležely ve stejném adresáři, "
        "přečetl by se každý záznam několikrát."
    ),
}

# Osy entit nesou jen svá specifika a odkaz na obecnou metodiku v souhrnu —
# kopírovat celý blok do 1 700 souborů firem by výstup zbytečně nafouklo.
METODIKA_ODKAZ = "obecná pravidla viz data/casova_osa/souhrn.json → metodika"

METODIKA_OSOBA = {
    "viz": METODIKA_ODKAZ,
    "polozky": ("Osa nese položky, ne plné události. Úplný záznam je pod stejným "
                "id v data/casova_osa/roky/{rok}.json."),
    "hlasovani": (
        "V ose jsou jednotlivě jen hlasování, kde osoba hlasovala proti, zdržela se "
        "nebo nehlasovala, kde bod neprošel (proti ≥ pro), nebo kde "
        "propojeni/hlasovani_vazby.json vede vazbu na firmu. Ostatní hlasování se "
        "nezahazují — jsou sečtená v hlasovani_po_letech a celkový počet je "
        "v pocty.hlasovani_celkem."
    ),
    "neucast_neni_polozka": (
        "Neúčast (nepritomen) se do osy jednotlivě nedává. Je to nepřítomnost, "
        "ne projev vůle; jednotlivé řádky by z osy udělaly výčet absencí. "
        "Neúčast je jen v souhrnu po letech."
    ),
    "vysledek": (
        "Portál vede všechna hlasování jako „schváleno“, včetně těch, kde je proti víc "
        "hlasů než pro. Pole detail.proslo se proto počítá z hlasů, ne z pole vysledek; "
        "původní hodnota zdroje zůstává v detail.vysledek_zdroje."
    ),
    "neucast": (
        "hlasovani_po_letech uvádí souhrnnou neúčast (nepritomen) a NEROZPADÁ ji na "
        "omluvenou a neomluvenou. Příznak „omluven“ ve starších datech neexistuje "
        "(zastupitelstvo od 2019, rada od 2023) a rozpad by byl tvrzením o zdroji, "
        "ne o člověku."
    ),
    "predkladatel": (
        "Předkladatel bodu usnesení se z dat vytáhnout nedá — řetězec „Předkládá:“ je "
        "jen v bodech typu „Program 108. RM“. Osoba se k usnesení váže přes jmenovité "
        "hlasování."
    ),
}

METODIKA_FIRMA = {
    "viz": METODIKA_ODKAZ,
    "polozky": ("Osa nese položky, ne plné události. Úplný záznam je pod stejným "
                "id v data/casova_osa/roky/{rok}.json."),
    "identita": "Firmy se vedou podle IČO. Bez IČO se vazba nezakládá.",
    "usneseni": (
        "Vazba usnesení → firma vzniká, jen když je IČO uvedené přímo v textu bodu. "
        "Shoda podle názvu se tu nepoužívá."
    ),
    "registr_od": (
        "Registr smluv běží od 1. 7. 2016. Prázdno před tímto datem neznamená, "
        "že firma s městem neobchodovala."
    ),
    "protistrana_neurcena": (
        "U části smluv zdroj místo protistrany uvádí zveřejňující subjekt. Taková "
        "smlouva má detail.protistrana_neurcena = true a do vazby na protistranu nevstupuje."
    ),
}

METODIKA_TAG = {
    "viz": METODIKA_ODKAZ,
    "polozky": ("Osa nese položky, ne plné události. Úplný záznam je pod stejným "
                "id v data/casova_osa/roky/{rok}.json."),
    "tagy": "Tagy jsou výhradně z config/tagy.json. Nové se nevymýšlejí.",
    "prenos": (
        "Hlasování přebírá tagy z odpovídajícího bodu usnesení, takže se v ose tématu "
        "objeví jak rozhodnutí, tak hlasování o něm."
    ),
}


# --------------------------------------------------------------------------
# Běh
# --------------------------------------------------------------------------

def nacti_vazby() -> dict:
    """hlasovani_id → seznam vazeb osoba/firma z modulu propojení."""
    d = nacti("propojeni/hlasovani_vazby.json") or {}
    ven = defaultdict(list)
    for v in d.get("vazby", []):
        if v.get("hlasovani_id"):
            ven[v["hlasovani_id"]].append({
                "osoba_id": v.get("osoba_id"),
                "jmeno": v.get("jmeno"),
                "ico": v.get("ico"),
                "firma": v.get("firma") or v.get("nazev"),
                "role": v.get("role"),
                "hlas": v.get("hlas"),
            })
    return ven


def nazvy_firem(udalosti: list[dict]) -> dict[str, str]:
    """Název k IČO. Bere se z nejnovější smlouvy — firma se jmenuje tak,
    jak se jmenuje dnes (stejná zásada jako v agregaci peněz)."""
    ven: dict[str, tuple[str, str]] = {}
    for u in udalosti:
        if u["typ"] != "smlouva":
            continue
        d = u["detail"]
        for ico, nazev in ((d.get("subjekt_ico"), d.get("subjekt")),
                           (d.get("protistrana_ico"), d.get("protistrana"))):
            if not ico or not nazev:
                continue
            stary = ven.get(ico)
            if stary is None or u["razeni"] > stary[0]:
                ven[ico] = (u["razeni"], nazev)
    return {ico: nazev for ico, (_, nazev) in ven.items()}


def sesbirej(log: Log) -> tuple[list[dict], dict, dict]:
    PRESKOCENO.clear()
    osobnosti = nacti("lide/osobnosti.json") or []
    vazby = nacti_vazby()

    stav: dict[str, str] = {}
    vse: list[dict] = []
    extra: dict = {}

    for jmeno, vysledek in (
        ("historie", z_historie(log)),
        ("usneseni", z_usneseni(log)),
        ("hlasovani", z_hlasovani(log, vazby)),
        ("smlouvy", z_smluv(log)),
        ("retez", z_retezu(log)),
        ("zpravodaj", z_zpravodaje(log)),
        ("media", z_medii(log)),
        ("volby", z_voleb(log)),
        ("firmy", z_firem(log)),
    ):
        udalosti, s = vysledek
        vse.extend(udalosti)
        stav[jmeno] = s

    fu, s, _ = z_funkci(log, osobnosti)
    vse.extend(fu)
    stav["funkce"] = s

    extra["preskoceno"] = {
        "co_to_je": ("Záznamy, které zdroj sice má, ale nešly umístit v čase "
                     "(chybí datum). Nezahazují se tiše — patří do modulu, "
                     "který je sbírá."),
        "pocty": dict(PRESKOCENO),
    }
    podezrela = [u for u in vse if u["datum_podezrele"]]
    extra["podezrela_data"] = {
        "co_to_je": (f"Záznamy s rokem mimo {ROK_NEJDRIV}–{ROK_NEJPOZDEJI}. "
                     "Zdroj má zjevně zkomolené datum (useknuté tisíciletí). "
                     "V ose zůstávají s příznakem datum_podezrele a nevstupují "
                     "do výpočtu rozsahu. Opravit je musí modul, který je sbírá."),
        "pocet": len(podezrela),
        "zaznamy": [{"id": u["id"], "datum": u["datum"], "typ": u["typ"],
                     "soubor": u["zdroj_soubor"], "nadpis": u["nadpis"]}
                    for u in podezrela],
    }
    if podezrela:
        log.info("zkomolená data ve zdroji (neopravují se, jen se přiznávají)",
                 pocet=len(podezrela))
    if PRESKOCENO:
        log.info("nedatované záznamy se do osy nedostaly", **dict(PRESKOCENO))

    vse.sort(key=lambda u: (u["razeni"], u["typ"], u["id"]))
    return vse, stav, extra


def zapis(log: Log, vse: list[dict], stav: dict, extra: dict, *,
          min_udalosti_firmy: int = 2) -> dict:
    osobnosti = {o["id"]: o for o in (nacti("lide/osobnosti.json") or [])}
    tagy_cfg = {t["id"]: t.get("nazev") for t in
                (nacti_cfg_tagy() or [])}
    platne = platne_tagy()
    nazvy = nazvy_firem(vse)

    dle_roku = defaultdict(list)
    dle_osoby = defaultdict(list)
    dle_firmy = defaultdict(list)
    dle_tagu = defaultdict(list)
    nezname_osoby = Counter()
    neplatne_tagy = Counter()

    for u in vse:
        # Záznam se zkomoleným datem nedostane vlastní ročník — jinak by
        # v roky/ přibyly soubory 2.json nebo 25.json. Jde do zvláštního
        # oddílu a je vypsaný v souhrn.json → podezrela_data.
        dle_roku["nezarazene" if u["datum_podezrele"] else u["rok"]].append(u)
        for oid in u["osoby"]:
            if oid in osobnosti:
                dle_osoby[oid].append(u)
            else:
                nezname_osoby[oid] += 1
        for ico in u["firmy"]:
            dle_firmy[ico].append(u)
        for t in u["tagy"]:
            if t in platne:
                dle_tagu[t].append(u)
            else:
                neplatne_tagy[t] += 1

    # roky — jediné úplné uložiště
    for rok, ud in dle_roku.items():
        uloz(f"{VYSTUP}/roky/{rok}.json", {
            "rok": rok if isinstance(rok, int) else None,
            "nezarazene": not isinstance(rok, int),
            "metodika": METODIKA_OBECNA,
            "pocty": _pocty(ud),
            "udalosti": ud,
        })

    # osoby
    for oid, ud in dle_osoby.items():
        uloz(f"{VYSTUP_OSY}/osoby/{oid}.json", osa_osoby(osobnosti[oid], ud))

    # firmy
    zapsanych_firem = 0
    for ico, ud in dle_firmy.items():
        if len(ud) < min_udalosti_firmy:
            continue
        uloz(f"{VYSTUP_OSY}/firmy/{ico}.json", osa_firmy(ico, nazvy.get(ico), ud))
        zapsanych_firem += 1

    # tagy
    for t, ud in dle_tagu.items():
        uloz(f"{VYSTUP_OSY}/tagy/{t}.json", osa_tagu(t, tagy_cfg.get(t), ud))

    # osa města
    mesto = osa_mesta(vse, dle_roku)
    uloz(f"{VYSTUP_OSY}/mesto.json", mesto)

    # úklid po předchozích bězích — osa entity, která už v datech není,
    # nesmí na webu přežívat
    smazano = {
        "roky": uklid(VYSTUP, "roky", {str(r) for r in dle_roku}),
        "osoby": uklid(VYSTUP_OSY, "osoby", set(dle_osoby)),
        "firmy": uklid(VYSTUP_OSY, "firmy", {i for i, ud in dle_firmy.items()
                                             if len(ud) >= min_udalosti_firmy}),
        "tagy": uklid(VYSTUP_OSY, "tagy", set(dle_tagu)),
    }
    if any(smazano.values()):
        log.info("smazány zastaralé osy", **{k: v for k, v in smazano.items() if v})

    souhrn = {
        "generovano": date.today().isoformat(),
        "metodika": METODIKA_OBECNA,
        "stav_zdroju": stav,
        "vysvetlivky_stavu": {
            "ok": "zdroj se načetl a něco v něm je",
            "prazdno": "zdroj se načetl a nic v něm není",
            "chybi": "zdroj v datech není — o období nevíme nic",
        },
        "pocty": _pocty(vse),
        "preskoceno": extra.get("preskoceno"),
        "podezrela_data": extra.get("podezrela_data"),
        "rozsah": _rozsah(vse),
        "po_letech": [{"rok": r, "udalosti": len(dle_roku[r])}
                      for r in sorted(k for k in dle_roku if isinstance(k, int))],
        "entity": {
            "osob": len(dle_osoby),
            "firem": zapsanych_firem,
            "firem_nalezeno": len(dle_firmy),
            "tagu": len(dle_tagu),
            "roku": len(dle_roku),
        },
        "rejstrik": {
            "osoby": sorted(dle_osoby),
            "tagy": sorted(dle_tagu),
            "roky": sorted(k for k in dle_roku if isinstance(k, int)),
        },
        "nezname_osoby": {
            "co_to_je": ("Slugy osob, které se objevují v článcích, ale nejsou "
                         "v data/lide/osobnosti.json. Osa se pro ně nezakládá. "
                         "Podnět pro modul B1, ne chyba."),
            "pocet": len(nezname_osoby),
            "nejcastejsi": nezname_osoby.most_common(30),
        },
        "neplatne_tagy": dict(neplatne_tagy),
        "smazano_zastaralych": smazano,
    }
    uloz(f"{VYSTUP}/souhrn.json", souhrn)
    log.info("zapsáno", roku=len(dle_roku), osob=len(dle_osoby),
             firem=zapsanych_firem, tagu=len(dle_tagu))
    return souhrn


def nacti_cfg_tagy():
    from lib.core import nacti_config
    try:
        return nacti_config("tagy.json").get("tagy", [])
    except Exception:  # noqa: BLE001 — číselník je volitelný pro popisky
        return []


def osa_mesta(vse: list[dict], dle_roku: dict) -> dict:
    """Souhrnná osa města.

    Milníky (historie, volby) v plném znění, provozní záznamy jen jako
    roční agregát — jinak by osa města měla desítky tisíc položek.
    Součty částek jdou zvlášť za doložené záznamy a zvlášť za odhady,
    aby nešlo sečíst smlouvu s domněnkou.
    """
    milniky = [u for u in vse if u["typ"] in ("historie", "volby")]
    roky = []
    for rok in sorted(k for k in dle_roku if isinstance(k, int)):
        ud = dle_roku[rok]
        castky = [u["castka_czk"] for u in ud
                  if u["typ"] == "smlouva" and isinstance(u["castka_czk"], (int, float))]
        roky.append({
            "rok": rok,
            "udalosti": len(ud),
            "dle_typu": dict(Counter(u["typ"] for u in ud)),
            "smluv": len(castky),
            "smlouvy_czk": round(sum(castky), 2) if castky else None,
        })
    return {
        "entita": {"typ": "mesto", "id": "marianske-lazne",
                   "nazev": "Mariánské Lázně"},
        "metodika": {
            **METODIKA_OBECNA,
            "milniky": ("V udalosti jsou jen historické milníky a volby. Provozní "
                        "záznamy (usnesení, hlasování, smlouvy, články) jsou v ročním "
                        "agregátu po_letech a v plném znění v casova_osa/roky/{rok}.json."),
            "chybejici_rok": ("Rok, který v po_letech není, znamená, že v datech není "
                              "žádná událost — ne nutně, že se nic nedělo."),
        },
        "rozsah": _rozsah(vse),
        # pocty = to, co je v tomhle souboru (milníky)
        # pocty_vse = celá osa města napříč roky/, aby šlo obojí porovnat
        "pocty": _pocty(milniky),
        "pocty_vse": _pocty(vse),
        "po_letech": roky,
        "udalosti": milniky,
    }


def vypis_osu(cesta: str, limit: int) -> int:
    """Kontrolní výpis jedné osy na stdout."""
    d = nacti(cesta)
    if d is None:
        print(f"osa {cesta} neexistuje")
        return 1
    e = d["entita"]
    print(f"\n=== {e.get('nazev') or e.get('jmeno') or e.get('id')} "
          f"({e['typ']}) ===")
    print(f"rozsah: {d['rozsah']['od']} → {d['rozsah']['do']}")
    print(f"počty:  {json.dumps(d['pocty'], ensure_ascii=False)}")
    for u in d["udalosti"][:limit]:
        jist = "" if u["jistota"] == "fakt" else f"  [jistota: {u['jistota']}]"
        r = u.get("role") or {}
        role = r.get("vztah", "")
        if r.get("hlas"):
            role = f"{role}: {r['hlas']}"
        if r.get("proslo") is False:
            role += " (neprošlo)"
        castka = f"  {u['castka_czk']:,.0f} Kč".replace(",", " ") if u["castka_czk"] else ""
        print(f"  {u['datum']:<10} {u['typ']:<10} {role:<20} {u['nadpis'][:60]}{castka}{jist}")
    if len(d["udalosti"]) > limit:
        print(f"  … a dalších {len(d['udalosti']) - limit}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Jednotná časová osa")
    ap.add_argument("--osoba", help="jen vypsat osu osoby (id z osobnosti.json)")
    ap.add_argument("--firma", help="jen vypsat osu firmy (IČO)")
    ap.add_argument("--tag", help="jen vypsat osu tématu (id z config/tagy.json)")
    ap.add_argument("--mesto", action="store_true", help="jen vypsat osu města")
    ap.add_argument("--limit", type=int, default=25, help="kolik událostí vypsat")
    ap.add_argument("--bez-zapisu", action="store_true",
                    help="jen spočítat, nic neukládat")
    ap.add_argument("--min-udalosti-firmy", type=int, default=2,
                    help="firma s méně událostmi nedostane vlastní soubor "
                         "(výchozí 2: firma, o které je v datech jediný záznam, "
                         "nemá co ukazovat v čase; --min-udalosti-firmy 1 vypíše všechny)")
    args = ap.parse_args()

    if args.osoba:
        return vypis_osu(f"{VYSTUP_OSY}/osoby/{args.osoba}.json", args.limit)
    if args.firma:
        return vypis_osu(f"{VYSTUP_OSY}/firmy/{args.firma}.json", args.limit)
    if args.tag:
        return vypis_osu(f"{VYSTUP_OSY}/tagy/{args.tag}.json", args.limit)
    if args.mesto:
        return vypis_osu(f"{VYSTUP_OSY}/mesto.json", args.limit)

    log = Log("casova_osa")
    vse, stav, extra = sesbirej(log)
    if not vse:
        log.chyba("nesesbírala se ani jedna událost — zkontroluj data/")
        log.uzavri()
        return 1

    chybi = [k for k, v in stav.items() if v == "chybi"]
    if chybi:
        log.info("zdroje, které v datech nejsou (není to chyba)", chybi=chybi)

    if args.bez_zapisu:
        r = _rozsah(vse)
        log.info("běh bez zápisu", udalosti=len(vse),
                 rozsah=f"{r['od']} → {r['do']}")
        log.uzavri()
        return 0

    souhrn = zapis(log, vse, stav, extra,
                   min_udalosti_firmy=args.min_udalosti_firmy)
    log.pricti(souhrn["pocty"]["celkem"])
    log.uzavri()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
