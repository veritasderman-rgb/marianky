"""Územní plánování Mariánských Lázní.

Územní plán rozhoduje o tom, co se kde ve městě smí postavit. U města
zapsaného na seznamu UNESCO je to jedna z mála věcí, které občana zajímají
dřív, než se postaví — proto tenhle modul.

ZDROJE (ověřeno 17. 8. 2026)

| stránka | co z ní bereme |
|---|---|
| `/urad/uzemni-planovani/uzemne-planovaci-dokumentace-a-studie/` | rozcestník — seznam obcí ORP a popisky s daty účinnosti |
| `…/uzemne-planovaci-dokumentace-a-studie/marianske-lazne/` | vlastní dokumentace ML, po kategoriích |
| `/urad/uzemni-planovani/novy-uzemni-plan-marianske-lazne/` | průběh pořizování nového ÚP — datované kroky |
| `/urad/uzemni-planovani/uzemne-analyticke-podklady/` | ÚAP ORP Mariánské Lázně |
| `/urad/uzemni-planovani/urad-uzemniho-planovani/` | „na čem zrovna pracujeme“ — rozpracované věci |
| `data/usneseni/**` | usnesení s tagem `uzemni-plan` (číselník `config/tagy.json`) |

Mariánské Lázně jsou obec s rozšířenou působností a vedou úřad územního
plánování i pro okolní obce. **Prioritou jsou Mariánské Lázně**; ostatní
obce se jen zaznamenají (název, odkaz, počet dokumentů), jejich
dokumentace se nestahuje.

ČTYŘI VĚCI, KTERÉ JE POTŘEBA VĚDĚT PŘEDEM

1. **Kořenový výpis obce nesedí s kategoriemi.** Stránka obce bez
   `?kateg=` vypíše všech 234 dokumentů ML, ale nadpis kategorie
   neopakuje při každé změně — dokumenty za koncem kategorie tak
   vizuálně spadnou pod cizí nadpis (kategorie 100493 má 11 dokumentů,
   v kořenovém výpisu jich pod ní vyšlo 20). Autoritativní je proto
   procházení **po kategoriích** ze `<select>` na stránce obce.
   Přepínač `--overit` obojí porovná; ověřeno, že množina souborů je
   shodná (234 = 234), liší se jen přiřazení kategorie.

2. **„Vloženo“ není datum vydání.** U souboru je datum nahrání do
   úložiště webu (celý archiv změn ÚP má 25. 4. 2018 — den migrace webu).
   Datum vydání a účinnosti se bere odjinud a vždy je u něj vidět odkud:
   `datum_zdroj` je `rozcestnik` (popisek kategorie) nebo `usneseni`
   („Vydání změny č. 27 …“). Údaje odvozené z názvu souboru jsou
   označené zvlášť — `zmena_odvozena` u čísla změny, `rok_odvozen_z_oop`
   u roku z čísla opatření obecné povahy.

3. **Oznámení o vydání OOP jsou skeny.** Právě ty dokumenty, které nesou
   datum nabytí účinnosti, nemají textovou vrstvu — všech 10 skenů mezi
   vytěženými PDF jsou přesně ony. Datum se proto nedomýšlí: dokument
   dostane `sken: true` a datum zůstane `null`, dokud ho nedoloží
   usnesení. Vydání změn 1–19 se tak doložit nedá vůbec, protože archiv
   usnesení začíná rokem 2012. Hledání „nabylo účinnosti dne …“ v textu
   běží jen v dokumentech, které o vydání samy jsou — v textové části
   územního plánu se totiž tatáž věta vyskytuje u cizích předpisů
   (zásady územního rozvoje kraje) a dala by datum, které s dokumentem
   nesouvisí.

4. **Starší PDF mají rozbité kódování diakritiky.** V textových částech
   změn z roku 2012 vychází „Zm ny .23“ místo „Změny č.23“; od roku 2014
   je to v pořádku. Je to vlastnost zdrojových PDF, ne chyba extrakce —
   text se ukládá tak, jak vyjde, a soubor nese `diakritika_poskozena`.

VÝSTUPY do `data/uzemni_plan/`

| soubor | co v něm je |
|---|---|
| `dokumentace.json` | platná i rozpracovaná ÚPD Mariánských Lázní, dokument po dokumentu |
| `zmeny.json` | 27 změn platného ÚP shrnutých z dokumentů a usnesení |
| `novy_plan.json` | proces pořizování nového ÚP — fáze, kroky, dokumenty |
| `osa.json` | časová osa procesu: web + usnesení + vydané dokumenty |
| `uap.json` | územně analytické podklady ORP |
| `obce.json` | přehled obcí ve správním obvodu (bez jejich dokumentů) |
| `usneseni.json` | všechna usnesení s tagem `uzemni-plan` |
| `souhrn.json` | počty, stav a upozornění pro web |
| `text/{id}.txt` | vytěžený text u dokumentů, kde dává smysl |

TEMPO: web města má sdílený strop a už jednou projekt na 90 minut
odstřihl. Všechno jde přes `core.fetch()`, která drží odstup 1,5 s na
`muml.cz` sdílený přes soubor mezi procesy. Nezrychlovat.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from selectolax.parser import HTMLParser  # noqa: E402

from lib.core import (CACHE, DATA, Log, ZdrojSelhal, cistit, fetch,  # noqa: E402
                      pdf_na_text, pdf_pocet_stran, platne_tagy,
                      potrebuje_ocr, uloz)

CIL = "uzemni_plan"
BASE = "https://www.muml.cz"

ROZCESTNIK = BASE + "/urad/uzemni-planovani/uzemne-planovaci-dokumentace-a-studie/"
NOVY_PLAN = BASE + "/urad/uzemni-planovani/novy-uzemni-plan-marianske-lazne/"
UAP = BASE + "/urad/uzemni-planovani/uzemne-analyticke-podklady/"
URAD_UP = BASE + "/urad/uzemni-planovani/urad-uzemniho-planovani/"
# Tatáž stránka jako rozcestník, jen pod jinou adresou v sekci „město“.
ZRCADLO = BASE + "/mesto/investice-a-rozvoj/uzemni-planovani/"

OBEC_ML = "marianske-lazne"
TAG = "uzemni-plan"          # id z config/tagy.json, nové se nevymýšlejí

# Stránky se mění řádově jednou za měsíce; denní cache stačí a šetří zdroj.
CACHE_STRANKA = 6 * 3600
CACHE_SOUBOR = 30 * 86_400

# Text se vytěžuje jen z PDF do téhle velikosti. Výkresy územního plánu
# mají desítky MB a text v nich stejně není — jsou to mapy.
LIMIT_TEXTU_B = 40 * 1024 * 1024


# ==========================================================================
# HTML pomocníci
# ==========================================================================

def _stranka(url: str, *, max_age: int = CACHE_STRANKA) -> HTMLParser:
    """Stáhne stránku webu města a vrátí její obsahovou část."""
    html = fetch(url, max_age=max_age)
    if not isinstance(html, str):  # pragma: no cover — binary=False vrací str
        html = html.decode("utf-8", errors="replace")
    p = HTMLParser(html)
    for t in p.css("script, style, noscript"):
        t.decompose()
    node = p.css_first(".gcm-main") or p.css_first("main")
    if node is None:
        raise ZdrojSelhal(f"Na {url} chybí obsahový blok .gcm-main — změnila se šablona?")
    return node


def _txt(node) -> str:
    if node is None:
        return ""
    return re.sub(r"\s+", " ", (node.text() or "").replace("\xa0", " ")).strip()


def _abs(href: str | None) -> str | None:
    if not href:
        return None
    return urljoin(BASE + "/", href.replace("&amp;", "&"))


# ==========================================================================
# Datum: rozpoznání a přesnost
# ==========================================================================

MESICE = {}
for _c, _tvary in {
    1: "leden ledna lednu", 2: "únor února únoru", 3: "březen března březnu",
    4: "duben dubna dubnu", 5: "květen května květnu", 6: "červen června červnu",
    7: "červenec července červenci", 8: "srpen srpna srpnu", 9: "září",
    10: "říjen října říjnu", 11: "listopad listopadu", 12: "prosinec prosince prosinci",
}.items():
    for _t in _tvary.split():
        MESICE[_t] = _c
_MES_RE = "|".join(sorted(MESICE, key=len, reverse=True))

# Datum na den: 8.10.2020 i 25. 4. 2018 i 10.února 2016
RE_DEN = re.compile(r"(\d{1,2})\s*\.\s*(\d{1,2})\s*\.\s*(\d{4})")
RE_DEN_SLOVY = re.compile(rf"(\d{{1,2}})\s*\.\s*({_MES_RE})\s+(\d{{4}})", re.I)
# Měsíc a rok: 09_2018, 10/2019, únor 2026, v lednu 2018
RE_MESIC_CISLEM = re.compile(r"\b(\d{1,2})[_/](\d{4})\b")
RE_MESIC_SLOVY = re.compile(rf"\b({_MES_RE})\s+(\d{{4}})\b", re.I)
RE_ROK = re.compile(r"\b(19\d{2}|20\d{2})\b")


def _iso(rok: int, mesic: int = 1, den: int = 1) -> str | None:
    try:
        return datetime(rok, mesic, den).strftime("%Y-%m-%d")
    except ValueError:
        return None


def datum_z_textu(text: str) -> tuple[str | None, str | None, str | None]:
    """Vrátí (ISO datum, přesnost, doslovný zápis) prvního data v textu.

    Přesnost je `den`, `mesic` nebo `rok` — bez ní by se z „(2002)“ stalo
    1. ledna 2002 a graf by tvrdil něco, co ve zdroji není.
    """
    t = (text or "").replace("\xa0", " ")
    m = RE_DEN.search(t)
    if m:
        d, mo, y = (int(g) for g in m.groups())
        iso = _iso(y, mo, d)
        if iso:
            return iso, "den", m.group(0).strip()
    m = RE_DEN_SLOVY.search(t)
    if m:
        iso = _iso(int(m.group(3)), MESICE[m.group(2).lower()], int(m.group(1)))
        if iso:
            return iso, "den", m.group(0).strip()
    m = RE_MESIC_CISLEM.search(t)
    if m and 1 <= int(m.group(1)) <= 12:
        iso = _iso(int(m.group(2)), int(m.group(1)))
        if iso:
            return iso, "mesic", m.group(0).strip()
    m = RE_MESIC_SLOVY.search(t)
    if m:
        iso = _iso(int(m.group(2)), MESICE[m.group(1).lower()])
        if iso:
            return iso, "mesic", m.group(0).strip()
    m = RE_ROK.search(t)
    if m:
        return _iso(int(m.group(1))), "rok", m.group(0)
    return None, None, None


def _razeni(iso: str | None) -> str:
    """Datum doplněné na celý den JEN kvůli řazení. Není to údaj ze zdroje."""
    return iso or "9999-12-31"


# ==========================================================================
# Rozcestník — obce ORP a popisky kategorií
# ==========================================================================

def _popisek(a) -> str:
    """Celý popisek odkazu i s tím, co za odkaz vyteklo mimo `<a>`.

    Editor webu odkazy uzavírá nedbale: „…po změnách 1-2</a>7“ nebo
    „…náves (2022</a>)“. Kdo by četl jen text `<a>`, přišel by o číslo
    poslední změny i o závorku s rokem.
    """
    casti = [a.text() or ""]
    sourozenec = a.next
    while sourozenec is not None and sourozenec.tag in ("-text", "i", "b", "strong", "span", "em"):
        casti.append(sourozenec.text() or "")
        if len(" ".join(casti)) > 300:
            break
        sourozenec = sourozenec.next
    return re.sub(r"\s+", " ", "".join(casti).replace("\xa0", " ")).strip()


def rozcestnik(log: Log) -> tuple[dict[str, dict], dict[str, dict]]:
    """Přečte rozcestník: obce ORP a popisky kategorií s daty.

    Vrací (obce podle slugu, popisky podle id kategorie).
    """
    node = _stranka(ROZCESTNIK)
    cesta = urlparse(ROZCESTNIK).path

    obce: dict[str, dict] = {}
    # Klikací mapa ORP nese názvy obcí ve správné podobě včetně diakritiky.
    for area in node.css("area[href]"):
        href = area.attributes.get("href", "")
        if not href.startswith(cesta):
            continue
        slug = href[len(cesta):].split("/")[0].split("?")[0]
        if slug:
            obce.setdefault(slug, {"slug": slug, "nazev": area.attributes.get("title") or slug,
                                   "url": _abs(href),
                                   "kategorii_na_rozcestniku": 0})

    popisky: dict[str, dict] = {}
    for a in node.css("a[href]"):
        href = a.attributes.get("href", "").replace("&amp;", "&")
        if not href.startswith(cesta):
            continue
        slug = href[len(cesta):].split("/")[0].split("?")[0]
        if not slug:
            continue
        obce.setdefault(slug, {"slug": slug, "nazev": slug, "url": _abs(href),
                               "kategorii_na_rozcestniku": 0})
        kateg = parse_qs(urlparse(href).query).get("kateg", [None])[0]
        if not kateg:
            continue
        text = _popisek(a)
        iso, presnost, doslova = datum_z_textu(text)
        popisky[kateg] = {
            "kateg": kateg, "obec": slug, "popisek": text,
            "datum": iso, "presnost": presnost, "datum_doslova": doslova,
        }
        obce[slug]["kategorii_na_rozcestniku"] += 1

    if len(obce) < 10:
        raise ZdrojSelhal(f"Rozcestník vrátil jen {len(obce)} obcí — změnila se stránka?")
    log.info("rozcestník přečten", obci=len(obce), popisku_kategorii=len(popisky))
    return obce, popisky


# ==========================================================================
# Výpis dokumentů obce
# ==========================================================================

RE_TYP_VELIKOST = re.compile(r"Typ souboru:\s*([A-Za-z0-9]+)\s*,\s*Velikost:\s*([\d ,.]+\s*[kKMG]?B)")
RE_STAZENO = re.compile(r"Staženo:\s*([\d ,.]+)\s*×")
JEDNOTKY = {"b": 1, "kb": 1000, "mb": 1000 ** 2, "gb": 1000 ** 3}


def _velikost_b(text: str | None) -> int | None:
    """„29,64 MB“ → bajty. Web sází desetinnou čárku a mezerový tisíc."""
    if not text:
        return None
    m = re.match(r"\s*([\d .,]+?)\s*([kKMG]?B)\s*$", text)
    if not m:
        return None
    cislo = m.group(1).replace(" ", "").replace("\xa0", "").replace(",", ".")
    try:
        return int(round(float(cislo) * JEDNOTKY[m.group(2).lower()]))
    except (ValueError, KeyError):
        return None


def _kategorie_obce(node) -> list[dict]:
    """Strom kategorií ze `<select>` na stránce obce.

    Odsazení `&nbsp;` drží úroveň zanoření, `disabled` znamená skupinu bez
    vlastních dokumentů. Strom je úplnější než rozcestník — regulační plán
    ML je v něm, na rozcestníku na něj odkaz chybí.
    """
    out: list[dict] = []
    nadrazene: dict[int, str] = {}
    for o in node.css("select option"):
        hodnota = (o.attributes.get("value") or "").strip()
        if not hodnota or hodnota == "0":
            continue
        surovy = (o.text() or "").replace("\xa0", " ")
        uroven = (len(surovy) - len(surovy.lstrip(" "))) // 3
        nazev = surovy.strip()
        nadrazene[uroven] = nazev
        cesta = [nadrazene[u] for u in sorted(nadrazene) if u < uroven and nadrazene.get(u)]
        out.append({
            "kateg": hodnota,
            "nazev": nazev,
            "uroven": uroven,
            "cesta": cesta + [nazev],
            "skupina": "disabled" in o.attributes,   # nadpis bez dokumentů
        })
    return out


def _dokumenty_ze_stranky(node) -> list[dict]:
    """Vytáhne řádky souborů z výpisu dokumentů."""
    out = []
    for radek in node.css("div.file-row"):
        a = radek.css_first("h3 a[href]")
        if a is None:
            continue
        url = _abs(a.attributes.get("href"))
        soubor = a.attributes.get("download") or (
            _txt(radek.css_first(".file-name")) or None)
        detail = _txt(radek)
        m = RE_TYP_VELIKOST.search(detail)
        velikost = m.group(2).strip() if m else None
        stazeno = RE_STAZENO.search(detail)
        vlozeno = radek.css_first(".date")
        iso_vlozeno, _, _ = datum_z_textu(_txt(vlozeno)) if vlozeno is not None else (None, None, None)
        q = parse_qs(urlparse(url or "").query)
        klic = (q.get("file", [""])[0] or "").split("|")[-1] or None
        out.append({
            "id_souboru": klic,
            "nazev": _txt(a),
            "soubor": soubor,
            "pripona": (Path(soubor).suffix.lstrip(".").lower() or None) if soubor else (
                m.group(1).lower() if m else None),
            "velikost": velikost,
            "velikost_b": _velikost_b(velikost),
            "vlozeno": iso_vlozeno,
            "stazeno": int(re.sub(r"[^\d]", "", stazeno.group(1))) if stazeno else None,
            "url": url,
        })
    return out


def _posledni_strana(node) -> int:
    posledni = 1
    for a in node.css(".pagination a[href]"):
        m = re.search(r"page=(\d+)", a.attributes.get("href") or "")
        if m:
            posledni = max(posledni, int(m.group(1)))
    return posledni


def vypis(url: str, *, max_stran: int = 40) -> list[dict]:
    """Projde stránkovaný výpis dokumentů a vrátí všechny řádky."""
    oddelovac = "&" if "?" in url else "?"
    node = _stranka(url)
    dokumenty = _dokumenty_ze_stranky(node)
    posledni = _posledni_strana(node)
    for strana in range(2, min(posledni, max_stran) + 1):
        dalsi = _stranka(f"{url}{oddelovac}page={strana}")
        dokumenty += _dokumenty_ze_stranky(dalsi)
    return dokumenty


# ==========================================================================
# Druh dokumentace a čísla změn
# ==========================================================================

# Pořadí rozhoduje — první shoda v cestě kategorie vyhrává.
DRUHY = [
    ("regulační plán", "regulacni-plan", "Regulační plán"),
    ("územní studie", "uzemni-studie", "Územní studie"),
    ("rybízovna", "uzemni-studie", "Územní studie"),
    ("změny úp", "zmena-up", "Změna územního plánu"),
    ("soutěž", "urbanisticka-soutez", "Urbanistická soutěž o návrh"),
    ("zadání", "zadani", "Zadání územního plánu"),
    ("doplňující průzkumy", "pruzkumy-rozbory", "Doplňující průzkumy a rozbory"),
    ("úprava pro veřejné projednání", "navrh-verejne-projednani",
     "Návrh ÚP pro veřejné projednání"),
    ("pro společné jednání", "navrh-spolecne-jednani", "Návrh ÚP pro společné jednání"),
    ("úplné znění", "uzemni-plan-uplne-zneni", "Územní plán — úplné znění po změnách"),
    ("před změnami", "uzemni-plan-puvodni", "Územní plán — původní znění"),
    ("úp města ml", "uzemni-plan-puvodni", "Územní plán — původní znění"),
    ("platné", "uzemni-plan-platny", "Platný územní plán"),
    ("rozpracované", "uzemni-plan-navrh", "Rozpracovaný územní plán"),
]


def druh_kategorie(cesta: list[str]) -> tuple[str, str]:
    """Z cesty kategorie určí druh dokumentace. Od nejpodrobnějšího."""
    for uroven in reversed(cesta):
        nizky = uroven.lower()
        for klic, druh, nazev in DRUHY:
            if klic in nizky:
                return druh, nazev
    return "jine", "Ostatní"


RE_ZMENA = re.compile(r"Změn[ay]?\s*č\.\s*([0-9]{1,2}(?:\s*[-,/]\s*[0-9]{1,2})*)", re.I)
RE_OOP = re.compile(r"OOP\s*č\.\s*(\d+)\s*/\s*ÚP\s*/\s*(\d{4})", re.I)


def cisla_zmen(text: str) -> list[int]:
    """„Změna č. 08-11“ → [8,9,10,11], „Změna č. 20,22“ → [20,22].

    Rozsah `N-M` se rozvíjí, `N/M` je podvarianta jedné změny (03/3 = 3).
    Odvozeno z názvu dokumentu — proto to výstup označuje `odvozeno`.
    """
    m = RE_ZMENA.search(text or "")
    if not m:
        return []
    out: set[int] = set()
    for cast in m.group(1).split(","):
        cast = cast.strip()
        if "/" in cast:
            out.add(int(cast.split("/")[0]))
        elif "-" in cast:
            od, do = (int(x) for x in cast.split("-", 1))
            if od <= do <= od + 20:
                out.update(range(od, do + 1))
            else:
                out.update({od, do})
        elif cast.isdigit():
            out.add(int(cast))
    return sorted(out)


# ==========================================================================
# Dokumentace Mariánských Lázní
# ==========================================================================

def dokumentace_ml(popisky: dict[str, dict], log: Log, overit: bool = False) -> dict:
    """Stáhne veškerou ÚPD Mariánských Lázní, kategorii po kategorii."""
    url_obce = ROZCESTNIK + OBEC_ML + "/"
    node = _stranka(url_obce)
    kategorie = _kategorie_obce(node)
    if not kategorie:
        raise ZdrojSelhal(f"Na {url_obce} není strom kategorií — změnila se stránka?")

    dokumenty: list[dict] = []
    kat_out: list[dict] = []
    for k in kategorie:
        popis = popisky.get(k["kateg"], {})
        druh, druh_nazev = druh_kategorie(k["cesta"])
        zaznam = {
            "kateg": k["kateg"],
            "nazev": k["nazev"],
            "cesta": " > ".join(k["cesta"]),
            "druh": druh,
            "druh_nazev": druh_nazev,
            "skupina": k["skupina"],
            "url": f"{url_obce}?search=&kateg={k['kateg']}",
            # Popisek z rozcestníku nese datum vydání či účinnosti.
            "popisek_rozcestnik": popis.get("popisek"),
            "datum": popis.get("datum"),
            "datum_presnost": popis.get("presnost"),
            "datum_doslova": popis.get("datum_doslova"),
            "datum_zdroj": "rozcestnik" if popis.get("datum") else None,
            "dokumentu": 0,
        }
        if k["skupina"]:
            # Nadpis skupiny — vlastní dokumenty nemá, výpis by byl prázdný.
            kat_out.append(zaznam)
            continue

        radky = vypis(zaznam["url"])
        for r in radky:
            zmeny = cisla_zmen(r["nazev"]) or cisla_zmen(r["soubor"] or "")
            oop = RE_OOP.search(r["nazev"] or "")
            dokumenty.append({
                "id": f"ml-{r['id_souboru']}" if r["id_souboru"] else None,
                "obec": OBEC_ML,
                "kateg": k["kateg"],
                "kategorie": zaznam["cesta"],
                "druh": druh,
                "druh_nazev": druh_nazev,
                **{p: r[p] for p in ("nazev", "soubor", "pripona", "velikost",
                                     "velikost_b", "vlozeno", "stazeno", "url")},
                "zmena_c": zmeny or None,
                "zmena_odvozena": bool(zmeny),
                "oop_cislo": f"{oop.group(1)}/ÚP/{oop.group(2)}" if oop else None,
                "oop_rok": int(oop.group(2)) if oop else None,
                # Datum kategorie je datum dokumentace, ne jednotlivého souboru.
                "datum_dokumentace": zaznam["datum"],
                "datum_presnost": zaznam["datum_presnost"],
                "datum_zdroj": zaznam["datum_zdroj"],
                "text_soubor": None,
                "stran": None,
                "sken": None,
            })
        zaznam["dokumentu"] = len(radky)
        kat_out.append(zaznam)
        log.info("kategorie", kateg=k["kateg"], nazev=k["nazev"][:48], dokumentu=len(radky))

    if not dokumenty:
        raise ZdrojSelhal("Mariánské Lázně nemají ani jeden dokument — zdroj je rozbitý")

    kontrola = None
    if overit:
        kontrola = _overit_proti_korenu(url_obce, dokumenty, log)

    return {"kategorie": kat_out, "dokumenty": dokumenty, "kontrola": kontrola}


def _overit_proti_korenu(url_obce: str, dokumenty: list[dict], log: Log) -> dict:
    """Porovná dokumenty posbírané po kategoriích s kořenovým výpisem obce.

    Kořenový výpis přiřazuje kategorie špatně (viz hlavička modulu), ale
    množina souborů v něm je úplná — je to tedy dobrá kontrola, jestli
    procházení po kategoriích o nějaký dokument nepřišlo.
    """
    koren = {d["url"] for d in vypis(url_obce)}
    mam = {d["url"] for d in dokumenty}
    chybi = sorted(koren - mam)
    navic = sorted(mam - koren)
    if chybi:
        log.chyba(f"{len(chybi)} dokumentů je v kořenovém výpisu, ale ne v žádné kategorii")
    log.info("kontrola proti kořenovému výpisu", koren=len(koren), kategorie=len(mam),
             chybi=len(chybi), navic=len(navic))
    return {"v_korenovem_vypisu": len(koren), "po_kategoriich": len(mam),
            "chybi_v_kategoriich": chybi, "navic_v_kategoriich": navic}


# ==========================================================================
# Usnesení k územnímu plánu
# ==========================================================================

# Klasifikace usnesení podle názvu bodu. Pořadí rozhoduje — první shoda vyhrává.
#
# Město rozlišuje dva plány názvem a drží se toho důsledně:
#   „Územní plán města Mariánské Lázně“ = platný plán z roku 2002
#   „Územní plán Mariánské Lázně“       = nový, pořizovaný od roku 2015
# Rozlišit je podle názvu proto jde, ale spolehlivější jsou návěští jako
# „právní stav“ nebo „úplné znění“, která se u nového plánu nevyskytují.
PROCESY = [
    (re.compile(r"vydání\s+změn|změn\w*\s*(č\.)?\s*\d+.{0,30}(ÚP|územní|úz\.)|"
                r"ÚPD\s+změn|změny\s+ÚP|změn\w*\s+\d+\s*(a\s*\d+\s*)?ÚP", re.I),
     "zmeny-stavajiciho-up"),
    (re.compile(r"regulační\s+plán", re.I), "regulacni-plan"),
    (re.compile(r"územní(ch)?\s+stud|zastav\w*\s+studi|urbanistické\s+řešení", re.I),
     "uzemni-studie"),
    (re.compile(r"právní\s+stav|úplné\s+znění|stávajícího\s+územního\s+plánu|"
                r"vyhotovení\s+stávajícího", re.I), "stavajici-up"),
    (re.compile(r"nov[ýéáou]\w*\s+(územní|ÚP)|urbanistick\w+\s+soutěž|soutěž\w*\s+o\s+návrh|"
                r"soutěžní\w*\s+podmín|ideov\w+\s+návrh|"
                r"zadání\s+(pro\s+)?územní|návrh\s+zadání|návrh\w*\s+územního\s+plánu|"
                r"úprav\w*\s+(návrhu\s+)?územního\s+plánu|standardizace\s+územního\s+plánu|"
                r"zpracování\s+(nového\s+)?[Úú]zemního\s+plánu|"
                r"územní\w*\s+plán\w*\s+(mariánsk|ML\b)|ÚP\s*ML\b|"
                r"na\s+územní\s+plán", re.I),
     "novy-up"),
    (re.compile(r"pořizování\s+územně\s+plánovací\s+dokumentace|určený\s+zastupitel|"
                r"určení\s+člena\s+zastupitelstva.{0,40}územní", re.I), "porizovani-obecne"),
]
RE_VYDANI_ZMENY = re.compile(r"[Vv]ydání\s+změn[ay]?\s*č\.?\s*([\d,\s.a]+)")


def _proces(nazev: str) -> str:
    for vzor, proces in PROCESY:
        if vzor.search(nazev or ""):
            return proces
    return "jine"


def _vydane_zmeny(nazev: str) -> list[int]:
    """Z „Vydání změn č.23, 24, 25, 26 ÚP …“ vytáhne čísla vydaných změn."""
    m = RE_VYDANI_ZMENY.search(nazev or "")
    if not m:
        return []
    return sorted({int(x) for x in re.findall(r"\d+", m.group(1))})


def usneseni(log: Log) -> list[dict]:
    """Usnesení s tagem `uzemni-plan`. Tag je z číselníku, nový se nevymýšlí."""
    if TAG not in platne_tagy():
        raise ZdrojSelhal(f"Tag {TAG} není v config/tagy.json — číselník se změnil")

    soubory = sorted(glob.glob(str(DATA / "usneseni" / "*" / "*" / "*.json")))
    if not soubory:
        log.chyba("data/usneseni/ je prázdné — časová osa přijde o usnesení")
        return []

    out: list[dict] = []
    for cesta in soubory:
        jednani = json.loads(Path(cesta).read_text(encoding="utf-8"))
        for bod in jednani.get("body", []):
            if TAG not in (bod.get("tagy") or []):
                continue
            proces = _proces(bod.get("nazev", ""))
            out.append({
                "id": f"{jednani['organ']}-{jednani['datum'][:4]}-{jednani['cj']}-{bod['cislo'].split('/')[-1]}",
                "organ": jednani["organ"],
                "datum": jednani["datum"],
                "cj": jednani["cj"],
                "bod": bod["cislo"],
                "cislo_usneseni": bod.get("cislo_usneseni"),
                "nazev": bod.get("nazev"),
                "tagy": bod.get("tagy"),
                "castka_czk": bod.get("castka_czk"),
                "proces": proces,
                "vydane_zmeny": _vydane_zmeny(bod.get("nazev", "")) or None,
                "url": bod.get("url") or jednani.get("url"),
                "zdroj_soubor": str(Path(cesta).relative_to(DATA.parent)),
            })
    out.sort(key=lambda u: (u["datum"], u["organ"], u["bod"]))
    log.info("usnesení s tagem uzemni-plan", celkem=len(out),
             novy_up=sum(1 for u in out if u["proces"] == "novy-up"),
             zmeny=sum(1 for u in out if u["proces"] == "zmeny-stavajiciho-up"))
    return out


# ==========================================================================
# Změny platného územního plánu
# ==========================================================================

def zmeny_up(dokumenty: list[dict], usn: list[dict], log: Log) -> dict:
    """Shrne změny platného ÚP: kolik jich je, čím jsou doložené a kdy vyšly.

    Datum vydání se bere z usnesení zastupitelstva („Vydání změny č. …“),
    protože oznámení o vydání OOP jsou skeny bez textové vrstvy. Kde
    usnesení není (archiv usnesení sahá k roku 2012, změny 1–19 jsou
    starší), zůstává datum `null` a je uvedený jen rok z čísla OOP —
    ten je označený jako odvozený.
    """
    zmeny: dict[int, dict] = {}
    for d in dokumenty:
        for c in (d.get("zmena_c") or []):
            z = zmeny.setdefault(c, {
                "cislo": c, "dokumentu": 0, "soubory": [], "oop_cislo": None,
                "oop_rok": None, "rok_odvozen_z_oop": False,
                "datum_vydani": None, "datum_zdroj": None, "usneseni": [],
            })
            z["dokumentu"] += 1
            z["soubory"].append({"nazev": d["nazev"], "url": d["url"],
                                 "pripona": d["pripona"], "velikost": d["velikost"]})
            if d.get("oop_cislo") and not z["oop_cislo"]:
                z["oop_cislo"] = d["oop_cislo"]
                z["oop_rok"] = d["oop_rok"]
                z["rok_odvozen_z_oop"] = True

    for u in usn:
        for c in (u.get("vydane_zmeny") or []):
            z = zmeny.setdefault(c, {
                "cislo": c, "dokumentu": 0, "soubory": [], "oop_cislo": None,
                "oop_rok": None, "rok_odvozen_z_oop": False,
                "datum_vydani": None, "datum_zdroj": None, "usneseni": [],
            })
            z["usneseni"].append({"id": u["id"], "datum": u["datum"],
                                  "bod": u["bod"], "nazev": u["nazev"], "url": u["url"]})
            if z["datum_vydani"] is None or u["datum"] < z["datum_vydani"]:
                z["datum_vydani"] = u["datum"]
                z["datum_zdroj"] = "usneseni"

    radky = [zmeny[c] for c in sorted(zmeny)]
    s_datem = sum(1 for z in radky if z["datum_vydani"])
    log.info("změny platného ÚP", celkem=len(radky), s_datem_vydani=s_datem)
    return {
        "vysvetlivky": {
            "cislo": "Číslo změny odvozené z názvu dokumentu (např. „Změna č. 08-11“).",
            "datum_vydani": "Datum jednání zastupitelstva, které změnu vydalo. "
                            "null znamená, že usnesení nemáme — archiv usnesení "
                            "sahá k roku 2012, změny 1–19 jsou starší.",
            "oop_rok": "Rok z čísla opatření obecné povahy v názvu dokumentu. "
                       "Je to odvození z názvu, ne datum ze zdroje.",
        },
        "pocty": {"zmen": len(radky), "s_datem_vydani": s_datem,
                  "bez_data_vydani": len(radky) - s_datem},
        "zmeny": radky,
    }


# ==========================================================================
# Nový územní plán — proces
# ==========================================================================

RE_ODDELOVAC = re.compile(r"^_{5,}$")

# Etapy pořizování územního plánu podle stavebního zákona. Přiřazují se
# podle klíčových slov v textu kroku; pořadí rozhoduje o tom, co vyhraje.
#
# Na pořadí záleží víc, než je vidět: „před společným jednáním“ obsahuje
# „společným jednáním“ a „zadáním veřejné zakázky“ obsahuje „zadání“.
# Kdo by řadil od obecnějšího, zařadil by besedu před společným jednáním
# do společného jednání a vyhlášení urbanistické soutěže do zadání.
ETAPY = [
    ("schvaleni-stavajiciho-up", "Schválení platného územního plánu (2002)",
     re.compile(r"stávající\s+územní\s+plán|schválen\w*\s+zastupitelstvem\s+města\s+dne", re.I)),
    ("verejne-projednani", "Veřejné projednání",
     re.compile(r"veřejné\w*\s+projednání|opakovan\w+\s+veřejn", re.I)),
    ("uprava-po-spolecnem-jednani", "Úprava návrhu po společném jednání",
     re.compile(r"pokyny\s+k\s+úpravě|úprav\w*\s+(návrhu|po\s+společném)|"
                r"vyhodnocení\s+projednané\s+etapy|vyhodnocení\s+stanovisek|"
                r"stanovisk\w+|dohodování", re.I)),
    ("navrh-pred-spolecnym-jednanim", "Pracovní návrh před společným jednáním",
     re.compile(r"před\s+společným\s+jednáním|beseda\s+s\s+veřejností|"
                r"diskuze\s+nad\s+návrhem|dotazník|vlastní\s+podnět", re.I)),
    ("spolecne-jednani", "Společné jednání o návrhu",
     re.compile(r"společn\w+\s+jednání|společném\s+projednání|připomínkovat", re.I)),
    ("vydani-noveho-up", "Vydání nového územního plánu",
     re.compile(r"vydání\s+(nového\s+)?[Úú]zemního\s+plánu", re.I)),
    ("urbanisticka-soutez", "Urbanistická soutěž o návrh",
     re.compile(r"urbanistick\w+\s+soutěž|soutěž\w*\s+o\s+návrh|soutěžní|ideov\w+\s+návrh", re.I)),
    # Web má v nadpisu překlep „průzlumy“ — zdroj se opravuje, ne obchází.
    ("pruzkumy-rozbory", "Doplňující průzkumy a rozbory",
     re.compile(r"pr[uů]z[kl]um\w*\s+a\s+rozbor|veřejné\s+setkání", re.I)),
    ("zadani", "Zadání územního plánu",
     re.compile(r"zadání", re.I)),
    ("zahajeni-porizovani", "Rozhodnutí pořídit nový územní plán",
     re.compile(r"záměr\w*\s+pořídit|pořídit\s+nový|rozhodnutí\s+o\s+pořízení", re.I)),
    ("vyber-zpracovatele", "Výběr zpracovatele a smlouva o dílo",
     re.compile(r"zadávací\w*\s+(řízení|dokumentac|podmínk)|výběr\s+dodavatele|"
                r"veřejn\w+\s+zakázk|smlouv\w+\s+o\s+dílo|postoupení\s+smluv", re.I)),
    ("financovani", "Financování pořizování",
     re.compile(r"dotac|zapojení\s+(dotace|finančních)|rozpočtové\s+opatření|"
                r"finanční\w*\s+prostředk", re.I)),
    ("porizovatel-a-zastupitel", "Pořizovatel a určený zastupitel",
     re.compile(r"určený\s+zastupitel|určení\s+člena\s+zastupitelstva|"
                r"pořizování\s+územně\s+plánovací\s+dokumentace", re.I)),
]


def _etapa(text: str, zaloha: str = "") -> tuple[str, str]:
    """Zařadí text do etapy pořizování. Vlastní text kroku má přednost.

    Kdyby rozhodoval text celého bloku, přebila by jedna zmínka o
    průzkumech a rozborech všechny kroky v něm — na stránce nového ÚP
    stojí zpráva o soutěži z roku 2016 ve stejném bloku jako zpráva
    o průzkumech z roku 2017, protože je úřad neoddělil.
    """
    for text_kandidat in (text, zaloha):
        if not text_kandidat:
            continue
        for kod, nazev, vzor in ETAPY:
            if vzor.search(text_kandidat):
                return kod, nazev
    return "prubeh", "Průběh pořizování"


def _soubory_v_uzlu(node) -> list[dict]:
    """Přílohy v běžném textu. Web je servíruje dvěma různými skripty."""
    out, videno = [], set()
    for a in node.css("a[href]"):
        href = (a.attributes.get("href") or "").replace("&amp;", "&")
        if "e_download.php" not in href and "file_storage/download.php" not in href:
            continue
        url = _abs(href)
        if url in videno:
            continue
        videno.add(url)
        title = (a.attributes.get("title") or "").replace("\xa0", " ")
        m = re.search(r"Soubor ke\s*stáhnutí:\s*(.+?),\s*Typ:\s*(\S+).*?Velikost:\s*([\d ,.]+\s*[kKMG]?B)",
                      title)
        q = parse_qs(urlparse(href).query)
        nazev_souboru = (m.group(1).strip() if m else None) or (
            q.get("original", [""])[0] or Path(q.get("file", [""])[0]).name) or None
        velikost = m.group(3).strip() if m else None
        out.append({
            "popis": _txt(a) or nazev_souboru,
            "soubor": nazev_souboru,
            "pripona": (Path(nazev_souboru).suffix.lstrip(".").lower() or None) if nazev_souboru else None,
            "velikost": velikost,
            "velikost_b": _velikost_b(velikost),
            "url": url,
        })
    return out


def _odkazy_na_kategorie(node) -> list[str]:
    """Odkazy do výpisu dokumentace (…/marianske-lazne/?kateg=…)."""
    out = []
    for a in node.css("a[href]"):
        href = (a.attributes.get("href") or "").replace("&amp;", "&")
        kateg = parse_qs(urlparse(href).query).get("kateg", [None])[0]
        if kateg and kateg not in out:
            out.append(kateg)
    return out


HRANICE_VETY = (". ", "! ", "? ", ": ", "; ", "\n", ":")


def _zacatek_vety(text: str, pozice: int, nejdrive: int) -> int:
    """Najde začátek věty, ve které leží datum na dané pozici."""
    zac = nejdrive
    for hranice in HRANICE_VETY:
        i = text.rfind(hranice, nejdrive, pozice)
        if i != -1:
            zac = max(zac, i + len(hranice))
    return zac


def _kroky_z_odstavce(text: str) -> list[dict]:
    """Rozseká odstavec na kroky podle dat v něm.

    Úřad píše do jednoho odstavce celý řetěz jednání:
    „dne 22.4.2024 - zahájeno jednání …, 16.7.2024 - jednání …,
    31.7.2024 - rozeslán zápis …“. Každé datum tak začíná vlastní krok;
    text kroku sahá k dalšímu datu. Bez tohohle řezu by z pěti kroků byl
    jeden a osa by lhala o tom, kdy se co dělo.

    Popis kroku začíná na začátku věty, ve které datum stojí — jinak by
    z „Projednání návrhu Zadání proběhlo v termínu od 16. 5. 2018 do“
    zbylo jen „od 16. 5. 2018 do“ a nebylo by poznat, o co šlo.
    """
    if not text:
        return []
    nalezy = [(m.start(), m.end(), m.group(0)) for m in RE_DEN.finditer(text)]
    nalezy += [(m.start(), m.end(), m.group(0)) for m in RE_DEN_SLOVY.finditer(text)]
    # Část kroků je datovaná jen měsícem („Na začátku července 2025 byly
    # odeslány pokyny k úpravě návrhu“). Bez nich by z osy vypadl krok,
    # kterým začala celá etapa před veřejným projednáním. Bere se jen
    # slovní tvar měsíce — číselný by spolkl čísla zákonů (183/2006).
    obsazeno = [(z, k) for z, k, _ in nalezy]
    for m in RE_MESIC_SLOVY.finditer(text):
        if not any(z <= m.start() < k for z, k in obsazeno):
            nalezy.append((m.start(), m.end(), m.group(0)))
    nalezy.sort()
    if not nalezy:
        return []
    # Odstavec, který cituje paragraf zákona, nepopisuje krok pořizování,
    # ale právní rámec — a data v něm jsou lhůty, ne události.
    pravni = "§" in text
    out = []
    for i, (zac, konec, doslova) in enumerate(nalezy):
        iso, presnost, _ = datum_z_textu(doslova)
        if not iso:
            continue
        dalsi = nalezy[i + 1][0] if i + 1 < len(nalezy) else len(text)
        zacatek = _zacatek_vety(text, zac, nalezy[i - 1][1] if i else 0)
        popis = re.sub(r"\s+", " ", text[zacatek:dalsi]).strip(" ,.;-–—")
        out.append({"datum": iso, "presnost": presnost, "popis": popis,
                    "pravni_odkaz": pravni,
                    # Jak daleko od začátku věty datum stojí. Věta, která
                    # datem začíná, o něm mluví; věta, kde je až na konci,
                    # ho většinou jen zmiňuje mimochodem.
                    "odsazeni": zac - zacatek})
    return out


def _druh_kroku(krok: dict) -> str:
    """Krok, lhůta, nebo odkaz na předpis?

    Bez tohohle rozlišení by se stav pořizování určil podle 31. 12. 2028 —
    což není krok, který proběhl, ale zákonný termín, do kterého starý
    územní plán pozbude platnosti.
    """
    if krok.get("pravni_odkaz"):
        return "pravni-ramec"
    if krok["datum"] > datetime.now(timezone.utc).strftime("%Y-%m-%d"):
        return "lhuta"
    return "krok"


def _lepsi_popis(a: dict, b: dict) -> dict:
    """Ze dvou popisů téže události vybere ten, který o ní opravdu mluví.

    Rozhoduje, jak brzy ve větě datum stojí: „Beseda proběhla 24.6.2019
    v muzeu“ je o tom dni, kdežto „Dotazník slouží jako podklad … veřejnosti
    bude představena 24.6.2019“ ho jen zmiňuje. Při shodě vyhraje delší.
    """
    if a["odsazeni"] != b["odsazeni"]:
        return a if a["odsazeni"] < b["odsazeni"] else b
    return a if len(a["popis"]) >= len(b["popis"]) else b


def _bez_duplicit(kroky: list[dict]) -> list[dict]:
    """Jedno datum uvnitř zprávy = jeden krok.

    Úřad tutéž událost v jedné zprávě zmíní víckrát (v textu a znovu
    v názvu přiloženého zápisu z jednání). Na ose by z toho byly dvě.
    """
    nejlepsi: dict[str, dict] = {}
    for k in kroky:
        stavajici = nejlepsi.get(k["datum"])
        nejlepsi[k["datum"]] = k if stavajici is None else _lepsi_popis(stavajici, k)
    return sorted(nejlepsi.values(), key=lambda k: k["datum"])


def novy_plan(popisky: dict[str, dict], log: Log) -> dict:
    """Přečte stránku nového územního plánu jako sled datovaných kroků.

    Stránka je psaná odshora dolů od nejnovějšího a jednotlivé zprávy jsou
    oddělené řádkou podtržítek. Blok = jedna zpráva úřadu, krok = jedno
    datum v ní.
    """
    node = _stranka(NOVY_PLAN)
    obsahy = node.css("div.editor_content.readable")
    if not obsahy:
        raise ZdrojSelhal(f"Na {NOVY_PLAN} chybí blok editor_content — změnila se šablona?")
    obsah = obsahy[-1]

    bloky: list[dict] = []
    aktualni: list = []
    for uzel in obsah.iter():
        if uzel.tag == "p" and RE_ODDELOVAC.match(_txt(uzel).replace(" ", "")):
            bloky.append(aktualni)
            aktualni = []
            continue
        aktualni.append(uzel)
    bloky.append(aktualni)

    zpravy: list[dict] = []
    for poradi, blok in enumerate(b for b in bloky if b):
        odstavce = [_txt(u) for u in blok]
        text = cistit("\n".join(o for o in odstavce if o))
        if not text:
            continue
        kroky: list[dict] = []
        for u in blok:
            odstavec = _txt(u)
            for krok in _kroky_z_odstavce(odstavec):
                kod, nazev = _etapa(krok["popis"], text[:400])
                kroky.append({
                    **krok,
                    "etapa": kod if not krok["pravni_odkaz"] else "pravni-ramec",
                    "etapa_nazev": nazev if not krok["pravni_odkaz"] else "Právní rámec",
                    "druh": _druh_kroku(krok),
                    "kontext": odstavec[:600],
                })
        kroky = _bez_duplicit(kroky)
        soubory = []
        for u in blok:
            soubory += [s for s in _soubory_v_uzlu(u)
                        if s["url"] not in {x["url"] for x in soubory}]
        kod, nazev = _etapa(text)
        zpravy.append({
            "poradi": poradi,
            "nadpis": odstavce[0][:160] if odstavce else None,
            "text": text,
            "etapa": kod,
            "etapa_nazev": nazev,
            "kroky": kroky,
            "soubory": soubory,
            "kategorie_dokumentace": _odkazy_na_kategorie(
                HTMLParser("".join(u.html or "" for u in blok))),
        })

    kroky = [k for z in zpravy for k in z["kroky"]]
    if not kroky:
        raise ZdrojSelhal("Na stránce nového ÚP se nenašel ani jeden datovaný krok")

    # Etapy z popisků kategorií na rozcestníku — dávají měsíční přesnost
    # tam, kde stránka procesu mluví jen obecně („v roce 2016“).
    milniky = []
    for p in popisky.values():
        if p["obec"] != OBEC_ML or not p["datum"]:
            continue
        kod, nazev = _etapa(p["popisek"])
        druh, druh_nazev = druh_kategorie([p["popisek"]])
        milniky.append({"datum": p["datum"], "presnost": p["presnost"],
                        "popis": p["popisek"], "etapa": kod, "etapa_nazev": nazev,
                        "druh": druh, "druh_nazev": druh_nazev,
                        "kateg": p["kateg"], "datum_doslova": p["datum_doslova"]})
    milniky.sort(key=lambda m: _razeni(m["datum"]))

    kontakt = None
    cely_text = re.sub(r"\s+", " ", obsah.text().replace("\xa0", " "))
    m = re.search(r"kontaktní osoba:\s*([^,]+?),\s*([\d ]{9,}?),\s*(\S+@[\w.]+)", cely_text, re.I)
    if m:
        kontakt = {"jmeno": m.group(1).strip(), "telefon": m.group(2).strip(),
                   "email": m.group(3).strip().rstrip(".")}

    probehle = [k for k in kroky if k["druh"] == "krok"]
    lhuty = sorted((k for k in kroky if k["druh"] in ("lhuta", "pravni-ramec")
                    and k["datum"] > datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                   key=lambda k: k["datum"])
    posledni = max(probehle or kroky, key=lambda k: _razeni(k["datum"]))
    stav = {
        # Poslední krok, který podle stránky opravdu proběhl. Budoucí termíny
        # a citace zákona se sem nepočítají, jinak by fáze vyšla z roku 2028.
        "posledni_krok": posledni,
        "etapa": posledni["etapa"],
        "etapa_nazev": posledni["etapa_nazev"],
        "nejblizsi_lhuta": lhuty[0] if lhuty else None,
        # Nejnovější zpráva na stránce je to, co úřad sám uvádí jako stav.
        "text_nahore": zpravy[0]["text"] if zpravy else None,
        "zjisteno": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    log.info("nový územní plán", zprav=len(zpravy), kroku=len(kroky),
             milniku=len(milniky), etapa=stav["etapa"],
             posledni=posledni["datum"])
    return {
        "url": NOVY_PLAN,
        "vysvetlivky": {
            "zprava": "Jedna zpráva úřadu na stránce procesu; stránka je řazená "
                      "od nejnovější a zprávy odděluje řádka podtržítek.",
            "krok": "Jedno datum uvnitř zprávy i s textem, který u něj stojí. "
                    "Úřad píše do jednoho odstavce celý řetěz jednání, proto se "
                    "odstavec řeže na každém datu.",
            "etapa": "Etapa pořizování ÚP odvozená z klíčových slov v textu kroku. "
                     "Je to zařazení, ne údaj ze zdroje.",
            "stav": "Stav není tvrzení úřadu o fázi, ale poslední datovaný krok, "
                    "který na stránce je, plus doslovné znění nejnovější zprávy.",
        },
        "stav": stav,
        "kontakt": kontakt,
        "milniky_dokumentace": milniky,
        "zpravy": zpravy,
    }


# ==========================================================================
# Územně analytické podklady
# ==========================================================================

def uap(log: Log) -> dict:
    """ÚAP ORP Mariánské Lázně — výkresy, textová část a co k nim web říká."""
    node = _stranka(UAP)
    obsahy = node.css("div.editor_content.readable")
    if not obsahy:
        raise ZdrojSelhal(f"Na {UAP} chybí blok editor_content")
    obsah = obsahy[-1]

    # Stránka je členěná dvakrát: h2/h3 drží aktualizaci („6. úplná
    # aktualizace 2024“), h4/h5 druh výkresu. Bez obojího by u souboru
    # nebylo poznat, ke které aktualizaci patří.
    dokumenty, sekce, aktualizace_sekce = [], None, None
    for uzel in obsah.iter():
        if uzel.tag in ("h1", "h2", "h3"):
            nadpis = _txt(uzel)
            if nadpis:
                aktualizace_sekce = nadpis
                sekce = None
        elif uzel.tag in ("h4", "h5", "h6"):
            nadpis = _txt(uzel)
            if nadpis:
                sekce = nadpis
        for s in _soubory_v_uzlu(uzel):
            if s["url"] in {d["url"] for d in dokumenty}:
                continue
            rok = re.search(r"(20\d{2})", aktualizace_sekce or "")
            dokumenty.append({**s, "sekce": sekce, "aktualizace": aktualizace_sekce,
                              "rok_aktualizace": int(rok.group(1)) if rok else None})

    text = cistit(obsah.text())
    if not dokumenty:
        raise ZdrojSelhal("Na stránce ÚAP není ani jeden dokument")

    # Nadpis „6. úplná aktualizace 2024“ je strukturovaný údaj, prózu pod ním
    # nerozebíráme — ukládá se doslova, ať si ji přečte člověk.
    aktualizace: dict[int, dict] = {}
    for m in re.finditer(r"(\d+)\.\s*úplná aktualizace\s*(\d{4})?", text, re.I):
        poradi, rok = int(m.group(1)), int(m.group(2)) if m.group(2) else None
        stavajici = aktualizace.get(poradi)
        if stavajici is None or (rok and not stavajici["rok"]):
            aktualizace[poradi] = {"poradi": poradi, "rok": rok,
                                   "doslova": m.group(0).strip(),
                                   "dokumentu": sum(1 for d in dokumenty
                                                    if d["rok_aktualizace"] == rok) if rok else 0}
    aktualizace_list = [aktualizace[k] for k in sorted(aktualizace)]
    porizovatel = None
    m = re.search(r"Pořizovatel:\s*(.+?)(?:\s{2,}|Územně analytické)", text)
    if m:
        porizovatel = m.group(1).strip()

    log.info("ÚAP", dokumentu=len(dokumenty), aktualizaci=len(aktualizace_list))
    return {
        "url": UAP,
        "nazev": "Územně analytické podklady ORP Mariánské Lázně",
        "porizovatel": porizovatel,
        "aktualizace": aktualizace_list,
        "vysvetlivky": {
            "aktualizace": "Pořadí a rok úplné aktualizace ÚAP. Vytaženo z nadpisů "
                           "a z textu stránky; prózu o historii ÚAP modul nerozebírá "
                           "a nechává ji v text_stranky tak, jak ji město napsalo.",
            "rok_aktualizace": "Rok z nadpisu sekce, pod kterou soubor na stránce leží.",
        },
        "text_stranky": text,
        "dokumenty": dokumenty,
        "pocty": {"dokumentu": len(dokumenty)},
    }


# ==========================================================================
# Obce správního obvodu
# ==========================================================================

def obce_orp(obce: dict[str, dict], log: Log) -> dict:
    """Spočítá dokumenty u ostatních obcí ORP. Jejich dokumentaci nestahuje.

    Počet se čte z kořenového výpisu obce: poslední stránka × 20 plus to,
    co je na ní. Kořenový výpis přiřazuje kategorie špatně, ale množinu
    souborů má úplnou (ověřeno na ML: 234 = 234), a pro počet to stačí.
    """
    prace = _rozpracovane(log)
    out = []
    for slug, obec in sorted(obce.items()):
        zaznam = {**obec, "je_marianske_lazne": slug == OBEC_ML,
                  "dokumentu": None, "dokumentace_stazena": slug == OBEC_ML}
        node = _stranka(obec["url"])
        posledni = _posledni_strana(node)
        pocet = len(_dokumenty_ze_stranky(node))
        if posledni > 1:
            konec = _stranka(f"{obec['url']}?page={posledni}")
            pocet = (posledni - 1) * 20 + len(_dokumenty_ze_stranky(konec))
        zaznam["dokumentu"] = pocet
        zaznam["stran_vypisu"] = posledni
        zaznam["rozpracovano"] = [p for p in prace if p["obec_hadana"] == slug] or None
        out.append(zaznam)
        log.info("obec ORP", obec=slug, dokumentu=pocet)

    return {
        "vysvetlivky": {
            "rozsah": "Mariánské Lázně jsou obec s rozšířenou působností a vedou "
                      "úřad územního plánování i pro okolní obce. Stahuje se jen "
                      "dokumentace Mariánských Lázní; u ostatních obcí je vidět, "
                      "že existují a kolik dokumentů mají.",
            "dokumentu": "Počet souborů v kořenovém výpisu obce, ne počet "
                         "územních plánů. Jeden územní plán je desítky výkresů.",
            "kategorii_na_rozcestniku": "Kolik odkazů na kategorie vede z rozcestníku. "
                                        "Není to úplný počet kategorií — u Mariánských "
                                        "Lázní jich rozcestník uvádí 10, ale strom "
                                        "kategorií na stránce obce jich má 16 "
                                        "(regulační plán na rozcestníku chybí).",
            "rozpracovano": "Věty ze stránky úřadu územního plánování „na čem "
                            "zrovna pracujeme“. Obec je k nim přiřazená podle "
                            "názvu v textu — je to odhad, ne údaj ze zdroje.",
        },
        "obci": len(out),
        "obce": out,
    }


def _rozpracovane(log: Log) -> list[dict]:
    """Ze stránky úřadu ÚP vytáhne, co se právě projednává."""
    try:
        node = _stranka(URAD_UP)
    except ZdrojSelhal as e:
        log.chyba(f"stránka úřadu územního plánování nedostupná: {e}")
        return []
    obsahy = node.css("div.editor_content.readable")
    if not obsahy:
        return []
    obsah = obsahy[-1]

    NAZVY = {
        "marianské lázně": OBEC_ML, "mariánské lázně": OBEC_ML, "ml": OBEC_ML,
        "drmoul": "drmoul", "lázně kynžvart": "lazne-kynzvart", "mnichov": "mnichov",
        "ovesné kladruby": "ovesne-kladruby", "prameny": "prameny",
        "stará voda": "stara-voda", "teplá": "tepla", "tři sekery": "tri-sekery",
        "trstěnice": "trstenice", "valy": "valy", "velká hleďsebe": "velka-hledsebe",
        "vlkovice": "vlkovice", "zádub": "zadub-zavisin", "zádub - závišín": "zadub-zavisin",
    }
    out = []
    for uzel in obsah.iter():
        text = _txt(uzel)
        if len(text) < 15:
            continue
        nizky = text.lower()
        obec = next((slug for nazev, slug in NAZVY.items() if nazev in nizky and len(nazev) > 2), None)
        if obec is None:
            continue
        iso, presnost, _ = datum_z_textu(text)
        out.append({"text": text, "obec_hadana": obec, "datum": iso,
                    "datum_presnost": presnost, "zdroj": URAD_UP})
    return out


# ==========================================================================
# Vytěžení textu z dokumentů
# ==========================================================================

# Dokumenty, u kterých text dává smysl. Výkresy jsou mapy — v těch není nic.
RE_TEXTOVY = re.compile(
    r"textov[áa]\s*část|výrok|odůvodn|zadání|opatření obecné povahy|"
    r"oznámení\s*(o\s*)?vydání|OOP|zpráva o uplatňování|údaje o vydané|OZV", re.I)
# Datum nabytí účinnosti se hledá VÝHRADNĚ v dokumentech, které o vydání
# změny samy jsou. V textové části územního plánu se totiž „nabylo
# účinnosti dne …“ vyskytuje taky — jenže u cizích předpisů (zásady
# územního rozvoje kraje, stavební zákon). První shoda v takovém
# dokumentu dá datum, které s ním nemá nic společného.
RE_O_VYDANI = re.compile(r"oznámení\s*(o\s*)?vydání|údaje\s+o\s+vydané|opatření\s+obecné\s+povahy", re.I)
RE_UCINNOST = re.compile(r"nab\w+\s+účinnosti\s+(?:dne\s+)?(\d{1,2}\s*\.\s*\d{1,2}\s*\.\s*\d{4})", re.I)
# Poškozené kódování: v PDF z roku 2012 vypadnou háčky a z „Změny“ je
# „Zm ny“. Zdravý český text má háčkovaných písmen kolem 4 %, poškozený
# přesně nula — práh 1 % je proto bezpečný.
HACKY = "ěščřžĚŠČŘŽ"


def vytez_texty(dokumenty: list[dict], log: Log, limit: int | None = None) -> dict:
    """Stáhne vybraná PDF do `.cache/` a uloží z nich text do `data/`.

    Do `data/` jde text a metadata, nikdy binární obsah — výkresy mají
    desítky MB. `core.pdf_na_text()` běží záměrně bez `-layout`.
    """
    vybrane = [d for d in dokumenty
               if d["pripona"] == "pdf" and RE_TEXTOVY.search(d["nazev"] or "")
               and (d["velikost_b"] or 0) <= LIMIT_TEXTU_B]
    vybrane.sort(key=lambda d: d["velikost_b"] or 0)
    if limit:
        vybrane = vybrane[:limit]

    cil = DATA / CIL / "text"
    cil.mkdir(parents=True, exist_ok=True)
    hotovo, skeny, ucinnosti = 0, 0, []
    for d in vybrane:
        # PDF zůstává v .cache/, do data/ jde jen text a metadata. Když už
        # v cache leží, na server se vůbec nesahá — je sdílený a má strop.
        docasny = CACHE / "uzemni_plan" / f"{d['id']}.pdf"
        docasny.parent.mkdir(parents=True, exist_ok=True)
        if not docasny.exists():
            try:
                data = fetch(d["url"], binary=True, max_age=CACHE_SOUBOR, retries=2)
            except ZdrojSelhal as e:
                log.chyba(f"nestáhl se {d['nazev']}: {e}")
                continue
            if not isinstance(data, bytes) or not data.startswith(b"%PDF"):
                log.chyba(f"{d['nazev']} není PDF, přeskakuji")
                continue
            docasny.write_bytes(data)
        try:
            stran = pdf_pocet_stran(docasny)
            text = pdf_na_text(docasny)
        except ZdrojSelhal as e:
            log.chyba(f"pdftotext selhal na {d['nazev']}: {e}")
            continue
        d["stran"] = stran
        d["velikost_stazena_b"] = docasny.stat().st_size
        if potrebuje_ocr(text, stran):
            # Oznámení o vydání OOP jsou skeny. Nedomýšlíme, co v nich je.
            d["sken"] = True
            skeny += 1
            continue
        d["sken"] = False
        d["diakritika_poskozena"] = (
            sum(text.count(c) for c in HACKY) / max(len(text), 1)) < 0.01
        soubor = cil / f"{d['id']}.txt"
        soubor.write_text(text, encoding="utf-8")
        d["text_soubor"] = str(soubor.relative_to(DATA.parent))
        d["znaku_textu"] = len(text)
        hotovo += 1
        if not RE_O_VYDANI.search(d["nazev"] or ""):
            continue
        m = RE_UCINNOST.search(text)
        if m:
            iso, _, doslova = datum_z_textu(m.group(1))
            if iso:
                d["ucinnost"] = iso
                d["ucinnost_zdroj"] = "text-dokumentu"
                ucinnosti.append({"id": d["id"], "nazev": d["nazev"],
                                  "ucinnost": iso, "doslova": doslova})

    log.info("vytěžení textu", vybranych=len(vybrane), s_textem=hotovo,
             skenu=skeny, s_ucinnosti=len(ucinnosti))
    return {"vybranych": len(vybrane), "s_textem": hotovo, "skenu": skeny,
            "ucinnosti": ucinnosti}


# ==========================================================================
# Časová osa procesu
# ==========================================================================

def osa(plan: dict, usn: list[dict], zmeny: dict) -> dict:
    """Sestaví časovou osu pořizování nového územního plánu.

    Formát událostí drží tvar `data/casova_osa/` (id, datum, presnost,
    razeni, typ, nadpis, popis, jistota, zdroj), aby šlo osy slučovat.
    """
    udalosti: list[dict] = []

    # Tutéž událost úřad zmiňuje v několika zprávách pod sebou (beseda
    # 24. 6. 2019 je na stránce třikrát). Na ose má být jednou, s tím
    # nejpodrobnějším popisem, jaký o ní web má.
    z_webu: dict[str, dict] = {}
    for zprava in plan["zpravy"]:
        for krok in zprava["kroky"]:
            stavajici = z_webu.get(krok["datum"])
            if stavajici and _lepsi_popis(stavajici["_krok"], krok) is stavajici["_krok"]:
                stavajici["zmineno_krat"] += 1
                continue
            z_webu[krok["datum"]] = {
                "_krok": krok,
                "id": f"uzemni-plan:web:{krok['datum']}",
                "datum": krok["datum"],
                "presnost": krok["presnost"],
                "razeni": _razeni(krok["datum"]),
                "rok": int(krok["datum"][:4]),
                "typ": "uzemni-plan",
                "nadpis": krok["popis"],
                "popis": krok.get("kontext"),
                "etapa": krok["etapa"],
                "etapa_nazev": krok["etapa_nazev"],
                "druh": krok["druh"],
                "zmineno_krat": (stavajici or {}).get("zmineno_krat", 0) + 1,
                "jistota": "fakt",
                "jistota_duvod": None,
                "castka_czk": None,
                "url": NOVY_PLAN,
                "zdroj": "web-mesta",
                "zdroj_soubor": f"data/{CIL}/novy_plan.json",
            }
    for u in z_webu.values():
        u.pop("_krok", None)
    udalosti += list(z_webu.values())

    for m in plan["milniky_dokumentace"]:
        udalosti.append({
            "id": f"uzemni-plan:dokumentace:{m['kateg']}",
            "datum": m["datum"], "presnost": m["presnost"], "razeni": _razeni(m["datum"]),
            "rok": int(m["datum"][:4]), "typ": "uzemni-plan",
            "nadpis": m["popis"][:180],
            "popis": f"{m['druh_nazev']} na webu města, datováno „{m['datum_doslova']}“.",
            "etapa": m["etapa"], "etapa_nazev": m["etapa_nazev"],
            "druh": "dokumentace", "dokumentace_druh": m["druh"],
            "jistota": "fakt", "jistota_duvod": None, "castka_czk": None,
            "url": ROZCESTNIK + OBEC_ML + f"/?search=&kateg={m['kateg']}",
            "zdroj": "web-mesta", "zdroj_soubor": f"data/{CIL}/dokumentace.json",
        })

    for u in usn:
        if u["proces"] not in ("novy-up", "porizovani-obecne"):
            continue
        etapa, etapa_nazev = _etapa(u["nazev"] or "")
        udalosti.append({
            "id": f"uzemni-plan:usneseni:{u['id']}",
            "datum": u["datum"], "presnost": "den", "razeni": u["datum"],
            "rok": int(u["datum"][:4]), "typ": "usneseni",
            "nadpis": u["nazev"],
            "popis": f"{'Zastupitelstvo' if u['organ'] == 'zastupitelstvo' else 'Rada'} města, bod {u['bod']}.",
            "etapa": etapa, "etapa_nazev": etapa_nazev,
            "druh": "usneseni",
            "jistota": "fakt", "jistota_duvod": None, "castka_czk": u["castka_czk"],
            "url": u["url"], "zdroj": "usneseni", "zdroj_soubor": u["zdroj_soubor"],
            "vazba": "primy" if u["proces"] == "novy-up" else "organizacni",
        })

    for z in zmeny["zmeny"]:
        if not z["datum_vydani"]:
            continue
        udalosti.append({
            "id": f"uzemni-plan:zmena:{z['cislo']}",
            "datum": z["datum_vydani"], "presnost": "den", "razeni": z["datum_vydani"],
            "rok": int(z["datum_vydani"][:4]), "typ": "uzemni-plan",
            "nadpis": f"Vydána změna č. {z['cislo']} územního plánu města",
            "popis": f"Doloženo usnesením zastupitelstva. Dokumentů ve výpisu: {z['dokumentu']}."
                     + (f" Opatření obecné povahy č. {z['oop_cislo']}." if z["oop_cislo"] else ""),
            "etapa": "zmena-stavajiciho-up", "etapa_nazev": "Změna platného územního plánu",
            "druh": "zmena",
            "jistota": "fakt", "jistota_duvod": None, "castka_czk": None,
            "url": z["usneseni"][0]["url"] if z["usneseni"] else None,
            "zdroj": "usneseni", "zdroj_soubor": f"data/{CIL}/zmeny.json",
        })

    udalosti.sort(key=lambda u: (u["razeni"], u["id"]))
    podle_typu: dict[str, int] = {}
    podle_etapy: dict[str, int] = {}
    podle_druhu: dict[str, int] = {}
    for u in udalosti:
        podle_typu[u["zdroj"]] = podle_typu.get(u["zdroj"], 0) + 1
        podle_etapy[u["etapa"]] = podle_etapy.get(u["etapa"], 0) + 1
        podle_druhu[u["druh"]] = podle_druhu.get(u["druh"], 0) + 1

    return {
        "entita": {"typ": "tema", "id": "uzemni-plan", "nazev": "Územní plánování Mariánské Lázně"},
        "metodika": {
            "co_to_je": "Časová osa pořizování územního plánu Mariánských Lázní. "
                        "Sesbírané datované záznamy z webu města, z usnesení "
                        "zastupitelstva a rady a z vydaných změn platného ÚP.",
            "presnost": "presnost říká, jak přesně je záznam datovaný (den / mesic / "
                        "rok). Pole razeni je datum doplněné na celý den JEN kvůli "
                        "řazení — není to údaj ze zdroje a nesmí se zobrazovat.",
            "etapa": "Etapa pořizování odvozená z klíčových slov v textu. Je to "
                     "zařazení pro filtrování, ne údaj ze zdroje.",
            "druh": "krok = událost, která proběhla. lhuta = termín v budoucnu. "
                    "pravni-ramec = datum z citace stavebního zákona, ne krok "
                    "pořizování (například 31. 12. 2028, kdy platný plán pozbude "
                    "platnosti). usneseni / zmena / dokumentace = původ záznamu. "
                    "Fáze pořizování se určuje jen z druhu krok.",
            "usneseni": "Zařazená jsou usnesení s tagem uzemni-plan, jejichž název "
                        "mluví o novém územním plánu (vazba primy) nebo o pořizování "
                        "ÚPD obecně (vazba organizacni). Usnesení o změnách platného "
                        "ÚP, územních studiích a jednotlivých pozemcích jsou celá "
                        "v usneseni.json.",
            "cislovani": "Web města cituje usnesení jako „ZM/753/18“, portál usnesení "
                         "jako bod 39/4 z 11. 9. 2018. Je to totéž jednání, ale jiné "
                         "číslování — páruje se datum a téma, ne číslo.",
        },
        "rozsah": {"od": udalosti[0]["datum"] if udalosti else None,
                   "do": udalosti[-1]["datum"] if udalosti else None},
        "pocty": {"celkem": len(udalosti), "dle_zdroje": podle_typu,
                  "dle_etapy": podle_etapy, "dle_druhu": podle_druhu},
        "udalosti": udalosti,
    }


# ==========================================================================
# Běh
# ==========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Územní plánování Mariánských Lázní")
    parser.add_argument("--overit", action="store_true",
                        help="porovnat dokumenty po kategoriích s kořenovým výpisem obce")
    parser.add_argument("--bez-textu", action="store_true",
                        help="nestahovat PDF a nevytěžovat z nich text")
    parser.add_argument("--limit-textu", type=int, default=None,
                        help="vytěžit text jen z N nejmenších dokumentů")
    args = parser.parse_args()

    log = Log("uzemni_plan")

    obce, popisky = rozcestnik(log)
    usn = usneseni(log)
    dokumentace = dokumentace_ml(popisky, log, overit=args.overit)
    zmeny = zmeny_up(dokumentace["dokumenty"], usn, log)
    plan = novy_plan(popisky, log)
    podklady = uap(log)
    prehled_obci = obce_orp(obce, log)

    texty = {"vybranych": 0, "s_textem": 0, "skenu": 0, "ucinnosti": []}
    if not args.bez_textu:
        texty = vytez_texty(dokumentace["dokumenty"], log, limit=args.limit_textu)

    cesta = osa(plan, usn, zmeny)

    ml = dokumentace["dokumenty"]
    uloz(f"{CIL}/dokumentace.json", {
        "obec": {"slug": OBEC_ML, "nazev": "Mariánské Lázně"},
        "url": ROZCESTNIK + OBEC_ML + "/",
        "vysvetlivky": {
            "vlozeno": "Datum nahrání souboru na web, NE datum vydání dokumentace. "
                       "Celý archiv změn ÚP má 25. 4. 2018 — den migrace webu.",
            "datum_dokumentace": "Datum vydání či účinnosti podle popisku kategorie "
                                 "na rozcestníku. datum_zdroj říká, odkud je.",
            "zmena_c": "Číslo změny odvozené z názvu dokumentu (zmena_odvozena=true).",
            "sken": "true = PDF nemá textovou vrstvu, text z něj nejde vytěžit bez OCR.",
        },
        "pocty": {
            "dokumentu": len(ml),
            "kategorii": len([k for k in dokumentace["kategorie"] if not k["skupina"]]),
            "dle_druhu": {d: sum(1 for x in ml if x["druh"] == d)
                          for d in sorted({x["druh"] for x in ml})},
            "velikost_celkem_b": sum(x["velikost_b"] or 0 for x in ml),
        },
        "kontrola": dokumentace["kontrola"],
        "kategorie": dokumentace["kategorie"],
        "dokumenty": ml,
    })
    uloz(f"{CIL}/zmeny.json", zmeny)
    uloz(f"{CIL}/novy_plan.json", plan)
    uloz(f"{CIL}/osa.json", cesta)
    uloz(f"{CIL}/uap.json", podklady)
    uloz(f"{CIL}/obce.json", prehled_obci)
    uloz(f"{CIL}/usneseni.json", {
        "tag": TAG,
        "vysvetlivky": {
            "proces": "Zařazení podle názvu bodu: novy-up, zmeny-stavajiciho-up, "
                      "uzemni-studie, regulacni-plan, porizovani-obecne, jine. "
                      "Je to zařazení kódem, ne údaj ze zdroje.",
            "vydane_zmeny": "Čísla změn ÚP z názvu usnesení „Vydání změny č. …“.",
        },
        "pocty": {"celkem": len(usn),
                  "dle_procesu": {p: sum(1 for u in usn if u["proces"] == p)
                                  for p in sorted({u["proces"] for u in usn})}},
        "usneseni": usn,
    })

    souhrn = {
        "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "zdroje": {"rozcestnik": ROZCESTNIK, "novy_plan": NOVY_PLAN, "uap": UAP,
                   "urad": URAD_UP, "zrcadlo": ZRCADLO},
        "marianske_lazne": {
            "dokumentu": len(ml),
            "kategorii": len([k for k in dokumentace["kategorie"] if not k["skupina"]]),
            "zmen_platneho_up": zmeny["pocty"]["zmen"],
            "s_datem_vydani": zmeny["pocty"]["s_datem_vydani"],
            "textu_vytezeno": texty["s_textem"],
            "skenu": texty["skenu"],
        },
        "novy_plan": {
            "etapa": plan["stav"]["etapa"],
            "etapa_nazev": plan["stav"]["etapa_nazev"],
            "posledni_krok": plan["stav"]["posledni_krok"]["datum"],
            "kroku": sum(len(z["kroky"]) for z in plan["zpravy"]),
            "udalosti_na_ose": cesta["pocty"]["celkem"],
            "od": cesta["rozsah"]["od"],
            "do": cesta["rozsah"]["do"],
        },
        "uap": podklady["pocty"],
        "obce_orp": {"obci": prehled_obci["obci"],
                     "dokumentu_celkem": sum(o["dokumentu"] or 0 for o in prehled_obci["obce"])},
        "usneseni": {"celkem": len(usn),
                     "na_ose": sum(1 for u in cesta["udalosti"] if u["zdroj"] == "usneseni")},
        "upozorneni": [
            "Datum „Vloženo“ u souboru je datum nahrání na web, ne datum vydání.",
            "Oznámení o vydání opatření obecné povahy jsou skeny bez textové vrstvy; "
            "data vydání změn 1–19 proto nemáme — archiv usnesení sahá k roku 2012.",
            "Ostatní obce ORP se jen evidují, jejich dokumentace se nestahuje.",
        ],
    }
    uloz(f"{CIL}/souhrn.json", souhrn)
    log.pricti(len(ml) + len(usn) + cesta["pocty"]["celkem"])
    log.uzavri()


if __name__ == "__main__":
    main()
