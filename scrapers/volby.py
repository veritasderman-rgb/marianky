#!/usr/bin/env python3
"""O1 — volební výsledky Mariánských Lázní z otevřených dat ČSÚ.

Zdroj: https://volby.gov.cz/opendata/  (volby.cz na tuhle adresu přesměrovává)

Co sbírá a proč zrovna takhle
-----------------------------
ČSÚ zveřejňuje ke každému volebnímu cyklu tři ZIPy s CSV:

  * **data**      — okrsková data (jeden řádek na okrsek, druhý soubor na
                    stranu v okrsku). Tohle je jádro: bez něj není heatmapa.
  * **registry**  — kdo kandidoval, kdo dostal mandát, jak se strana jmenuje.
  * **číselníky** — kódy obcí, okresů, politických stran.

Soubory jsou celorepublikové (6–14 MB zabalené), takže se stahují celé do
`.cache/` a **filtrují se až při čtení** na obec 554642. Do `data/` jde jen
Mariánské Lázně.

Čtyři věci, které nejsou samozřejmé
----------------------------------
1. **Kódování.** Adresář `csv/` v ZIPu je "excelovská" varianta ve
   windows-1250 se středníkem, adresář `csv_od/` je varianta pro otevřená
   data v UTF-8 s čárkou. Jenže ne vždycky — registr kandidátů na prezidenta
   2023 je v `csv_od/` taky ve windows-1250. Proto se kódování **nehádá podle
   adresáře, ale zkouší** (`_dekoduj`), jinak by v datech byl mojibake.

2. **Okrsky se v čase mění.** Jejich počet i hranice. Kód proto ukládá
   `okrsky.json`, kde je u každé dvojice po sobě jdoucích voleb napsané, co
   o srovnatelnosti VÍME (počet a čísla okrsků, ta jsou přímo v datech)
   a co NEVÍME (hranice). Hranice zná jen samostatná geografická vrstva
   k roku 2022 a 2024 — pro starší volby je zdroj nemá a **nedomýšlíme je**.
   Mariánské Lázně mají shodou okolností všech 36 sledovaných voleb 17
   okrsků číslovaných 1–17, ale i tak platí: shodné číslo ≠ shodné území.

3. **Rozcestník otevřených dat neuvádí všechny cykly.** Chybí na něm
   `ps2017`, `prez2023`, `se2014` a `se2018`, přestože ty adresy existují
   a data mají. Seznam cyklů se proto skládá z rozcestníku PLUS ručně
   doplněných, ověřených adres (`CYKLY_NAVIC`).

4. **Starší senátní cykly nemají CSV vůbec** — jen XML a Excel. Datový
   balík se proto vybírá podle formátu: CSV má přednost, XML je záchrana
   (`_cti_xml`). Bez toho by ze senátních voleb chyběly roky 2008–2017.

Spuštění:
    python3 scrapers/volby.py                    # vše
    python3 scrapers/volby.py --typ kv           # jen komunální
    python3 scrapers/volby.py --cyklus kv2022    # jeden cyklus
    python3 scrapers/volby.py --prehled          # jen zjistí, co je k dispozici
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from xml.etree import ElementTree

from selectolax.parser import HTMLParser

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import (  # noqa: E402
    DATA,
    Log,
    ZdrojSelhal,
    fetch,
    slug,
    uloz,
)

# --------------------------------------------------------------------------
# Co sledujeme
# --------------------------------------------------------------------------

OBEC = "554642"
OBEC_NAZEV = "Mariánské Lázně"
OKRES = "4101"          # NUMNUTS okresu Cheb (CZ0411)
KRAJ = "4100"           # NUMNUTS Karlovarského kraje (CZ041)

KOREN = "https://volby.gov.cz/opendata"
VYSTUP = "opendata/volby"

# Druhy voleb. Klíč je předpona kódu cyklu (kv2022 → "kv").
DRUHY: dict[str, dict[str, str]] = {
    "kv": {"typ": "komunalni", "nazev": "Volby do zastupitelstva obce"},
    "ps": {"typ": "snemovni", "nazev": "Volby do Poslanecké sněmovny"},
    "kz": {"typ": "krajske", "nazev": "Volby do zastupitelstva kraje"},
    "ep": {"typ": "evropske", "nazev": "Volby do Evropského parlamentu"},
    "prez": {"typ": "prezidentske", "nazev": "Volba prezidenta republiky"},
    "se": {"typ": "senatni", "nazev": "Volby do Senátu"},
}

# Cykly, které na rozcestníku /opendata/opendata.htm nejsou, ale existují.
# Ověřeno 17. 8. 2026 — všechny adresy vracejí HTTP 200 a mají kompletní ZIPy.
# Senátní volby 2018 jsou pro Mariánské Lázně ty podstatné: město leží
# ve volebním obvodu č. 2 (Sokolov), který volí v letech …2012, 2018, 2024.
CYKLY_NAVIC = ["ps2017", "prez2023", "se2014", "se2018"]

# Rozcestník míchá i věci, které nejsou jeden volební cyklus (kumulovaný
# přehled Senátu 1996–2025 nemá okrsková data v obvyklé struktuře).
CYKLY_MIMO = {"senat_vse"}

# Geometrie volebních okrsků. ČSÚ ji publikuje jen u některých cyklů a vždy
# k roku, ne k volbám — proto se bere z nejnovějšího dostupného zdroje a
# ukládá se s poznámkou, ke kterému roku platí.
GEO_ZDROJE = [
    ("2024", f"{KOREN}/kz2024/geo/vol_okrsky_2024g100.geojson"),
    ("2022", f"{KOREN}/kv2022/geo/vol_okrsky_2022g100.geojson"),
]


# --------------------------------------------------------------------------
# Čtení ZIPů s CSV
# --------------------------------------------------------------------------

def _dekoduj(raw: bytes) -> str:
    """Vrátí text CSV se správnou češtinou.

    Nejde odvodit z názvu adresáře: `csv/` bývá windows-1250 a `csv_od/`
    UTF-8, ale registr kandidátů na prezidenta 2023 je i v `csv_od/`
    ve windows-1250. Zkoušíme proto UTF-8 přísně a teprve když neprojde,
    sáhneme po windows-1250, ve které jsou české statistické soubory jinak.
    """
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("windows-1250")


def _cti_csv(raw: bytes) -> list[dict]:
    text = _dekoduj(raw)
    hlavicka = text.split("\n", 1)[0]
    oddelovac = ";" if hlavicka.count(";") > hlavicka.count(",") else ","
    return list(csv.DictReader(io.StringIO(text), delimiter=oddelovac))


def _stahni_zip(url: str, log: Log) -> zipfile.ZipFile:
    """Stáhne ZIP a otevře ho. Poškozený archiv se stáhne znovu bez cache.

    Nekompletní stažení se pozná právě až tady — ZIP bez centrálního
    adresáře se neotevře. Tiše vrátit prázdno by znamenalo tvrdit, že
    v obci nikdo nevolil.
    """
    for cerstve in (False, True):
        data = fetch(url, binary=True, max_age=0 if cerstve else 30 * 86_400)
        assert isinstance(data, bytes)
        try:
            return zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            if cerstve:
                raise ZdrojSelhal(f"{url}: stažený soubor není platný ZIP")
            log.info(f"poškozený ZIP v cache, stahuji znovu: {url}")
    raise ZdrojSelhal(url)  # nedosažitelné, ale ať to má návratovou cestu


def _cti_xml(raw: bytes) -> list[dict]:
    """Ploché XML ČSÚ na řádky.

    Starší senátní cykly (se2008–se2017) CSV variantu vůbec nemají, jen XML
    a Excel. Struktura je ale plochá — `<SE_T5_ROW><OBEC>…</OBEC>…</>` — takže
    se přečte stejně snadno jako CSV a nikam se kvůli tomu netahá nová
    závislost.
    """
    korenovy = ElementTree.fromstring(raw)
    out: list[dict] = []
    for radek in list(korenovy):
        zaznam = {}
        for pole in radek:
            jmeno = pole.tag.rsplit("}", 1)[-1]
            zaznam[jmeno] = (pole.text or "").strip()
        if zaznam:
            out.append(zaznam)
    return out


def _tabulky(z: zipfile.ZipFile) -> dict[str, list[dict]]:
    """Rozbalí ZIP na {jméno souboru bez přípony: řádky}.

    Když je stejná tabulka v `csv_od/` i v `csv/`, vyhrává `csv_od/` —
    je to varianta určená pro otevřená data (čárka, obvykle UTF-8).
    CSV vždycky přebíjí XML; XML se čte, jen když CSV varianta chybí.
    """
    podle_jmena: dict[str, str] = {}
    for i in z.infolist():
        pripona = Path(i.filename).suffix.lower()
        if pripona not in (".csv", ".xml"):
            continue
        jmeno = Path(i.filename).stem.lower()
        stavajici = podle_jmena.get(jmeno)
        lepsi = (
            stavajici is None
            or (pripona == ".csv" and stavajici.lower().endswith(".xml"))
            or (i.filename.startswith("csv_od/") and not stavajici.startswith("csv_od/"))
        )
        if lepsi:
            podle_jmena[jmeno] = i.filename
    out = {}
    for jmeno, cesta in podle_jmena.items():
        raw = z.read(cesta)
        out[jmeno] = _cti_xml(raw) if cesta.lower().endswith(".xml") else _cti_csv(raw)
    return out


def _obec_radky(radky: list[dict], sloupec: str = "OBEC") -> list[dict]:
    return [r for r in radky if (r.get(sloupec) or "").strip() == OBEC]


def _i(r: dict, klic: str) -> int | None:
    """Celé číslo, nebo None. Prázdno je neznámo, ne nula."""
    v = (r.get(klic) or "").strip()
    if v == "":
        return None
    try:
        return int(float(v.replace(",", ".")))
    except ValueError:
        return None


def _f(r: dict, klic: str) -> float | None:
    v = (r.get(klic) or "").strip()
    if v == "":
        return None
    try:
        return float(v.replace(",", "."))
    except ValueError:
        return None


def _procenta(cast: int | None, celek: int | None) -> float | None:
    if cast is None or not celek:
        return None
    return round(100.0 * cast / celek, 2)


def _datum(rrrrmmdd: str | None) -> str | None:
    if not rrrrmmdd or len(rrrrmmdd) != 8 or not rrrrmmdd.isdigit():
        return None
    return f"{rrrrmmdd[:4]}-{rrrrmmdd[4:6]}-{rrrrmmdd[6:]}"


def osoba_id(jmeno: str, prijmeni: str) -> str:
    """Slug `prijmeni-jmeno` — musí sedět s data/lide/osobnosti.json."""
    return f"{slug(prijmeni)}-{slug(jmeno)}"


def _cele_jmeno(r: dict) -> str:
    casti = [r.get("TITULPRED", ""), r.get("JMENO", ""), r.get("PRIJMENI", ""), r.get("TITULZA", "")]
    return " ".join(c.strip() for c in casti if c and c.strip())


# --------------------------------------------------------------------------
# Rozcestník cyklů
# --------------------------------------------------------------------------

def seznam_cyklu(log: Log) -> list[str]:
    """Kódy volebních cyklů z rozcestníku plus ručně ověřené dodatky."""
    html = fetch(f"{KOREN}/opendata.htm", max_age=7 * 86_400)
    assert isinstance(html, str)
    nalez: list[str] = []
    for a in HTMLParser(html).css("a"):
        m = re.search(r"/opendata/([a-z0-9]+)/\1_opendata\.htm", a.attributes.get("href") or "")
        if m and m.group(1) not in nalez:
            nalez.append(m.group(1))
    pred = len(nalez)
    for k in CYKLY_NAVIC:
        if k not in nalez:
            nalez.append(k)
    nalez = [k for k in nalez if k not in CYKLY_MIMO and druh_cyklu(k)]
    log.info(f"rozcestník nabídl {pred} cyklů, po doplnění {len(nalez)}")
    return sorted(nalez)


def druh_cyklu(kod: str) -> str | None:
    for predpona in sorted(DRUHY, key=len, reverse=True):
        if kod.startswith(predpona):
            return predpona
    return None


def rok_cyklu(kod: str) -> int | None:
    m = re.search(r"(\d{4})", kod)
    return int(m.group(1)) if m else None


def datum_z_rozcestniku(kod: str) -> str | None:
    """První den voleb z nadpisu rozcestníku, nebo None.

    Nadpis ho uvádí jen u některých cyklů ("konané dne 8.10. - 9.10.2021").
    Komunální volby ho mají přímo v datech (DATUMVOLEB), u sněmovních,
    krajských a evropských voleb ho zdroj v otevřených datech nemá vůbec —
    tam zůstane `null`. Datum se **nedomýšlí**; časová osa se řadí podle
    roku, který je z kódu cyklu jistý.
    """
    try:
        html = fetch(f"{KOREN}/{kod}/{kod}_opendata.htm", max_age=7 * 86_400)
    except ZdrojSelhal:
        return None
    assert isinstance(html, str)
    h1 = HTMLParser(html).css_first("h1")
    if not h1:
        return None
    text = " ".join(h1.text().split())
    m = re.search(r"kona[nl]\w*\s+(?:dne|ve\s+dnech)\s+(\d{1,2})\s*\.\s*(\d{1,2})\s*\."
                  r"(?:\s*(\d{4}))?", text)
    if not m:
        return None
    den, mesic, rok = m.group(1), m.group(2), m.group(3)
    if not rok:
        m2 = re.search(r"(\d{4})\s*$", text)
        rok = m2.group(1) if m2 else str(rok_cyklu(kod) or "")
    if not rok:
        return None
    try:
        return datetime(int(rok), int(mesic), int(den)).strftime("%Y-%m-%d")
    except ValueError:
        return None


def odkazy_cyklu(kod: str) -> dict[str, str]:
    """Najde v rozcestníku cyklu odkazy na CSV balíky (data / registry / číselníky).

    Pojmenování se mezi ročníky liší (`KV2018_data_20230224_csv.zip`,
    `KV2022_data_20260328_csv.zip`, `PS2025data20251005_csv.zip`,
    `PREZ2023_data_20230128_csv_kolo2.zip`), takže se hledá podle obsahu
    názvu, ne podle přesného tvaru.
    """
    url = f"{KOREN}/{kod}/{kod}_opendata.htm"
    html = fetch(url, max_age=7 * 86_400)
    assert isinstance(html, str)
    # Nejdřív se posbírají kandidáti podle role, pak se z nich vybere
    # nejlepší formát. CSV má přednost; XML je záchrana pro cykly, které
    # CSV nemají vůbec (senátní volby 2008–2017).
    kandidati: dict[str, dict[str, str]] = {"data": {}, "reg": {}, "cisel": {}}
    for a in HTMLParser(html).css("a"):
        h = (a.attributes.get("href") or "").strip()
        if not h.lower().endswith(".zip"):
            continue
        n = h.rsplit("/", 1)[-1].lower()
        if "xsd" in n or "popis" in n or "xlsx" in n or "_json" in n:
            continue
        format_ = "csv" if "csv" in n else "xml"
        role = "data" if "data" in n else ("reg" if "reg" in n else
                                           ("cisel" if "cisel" in n else None))
        if role is None or format_ in kandidati[role]:
            continue
        kandidati[role][format_] = h if h.startswith("http") else f"{KOREN}/{kod}/{h.lstrip('/')}"
    return {role: v["csv"] if "csv" in v else v["xml"]
            for role, v in kandidati.items() if v}


# --------------------------------------------------------------------------
# Komunální volby
# --------------------------------------------------------------------------

def zpracuj_kv(kod: str, tab_data: dict, tab_reg: dict, log: Log) -> list[dict]:
    """Rozparsuje komunální volby. Vrací seznam „voleb" (obvykle jedny).

    Jeden cyklus může obsahovat i navazující (opakované, dodatečné) volby
    s jiným datem — proto se seskupuje podle DATUMVOLEB, ne slepě sčítá.
    """
    t3 = _obec_radky(tab_data.get("kvt3", []))
    hl = _obec_radky(tab_data.get("kvhl", []))
    ros = _obec_radky(tab_reg.get("kvros", []), "KODZASTUP")
    rk = _obec_radky(tab_reg.get("kvrk", []), "KODZASTUP")
    zast = _obec_radky(tab_reg.get("kvrzcoco", []))
    if not t3:
        return []

    volby = []
    for datumvoleb in sorted({r.get("DATUMVOLEB") or "" for r in t3}):
        okrsky_syrove = [r for r in t3 if (r.get("DATUMVOLEB") or "") == datumvoleb]
        hl_v = [r for r in hl if (r.get("DATUMVOLEB") or "") == datumvoleb]
        ros_v = [r for r in ros if (r.get("DATUMVOLEB") or "") == datumvoleb] or ros
        rk_v = [r for r in rk if (r.get("DATUMVOLEB") or "") == datumvoleb] or rk
        zast_v = next((r for r in zast if (r.get("DATUMVOLEB") or "") == datumvoleb),
                      zast[0] if zast else {})

        # Strany podle pořadí na hlasovacím lístku.
        strany = []
        for r in sorted(ros_v, key=lambda x: int(x.get("POR_STR_HL") or 0)):
            strany.append({
                "poradi": _i(r, "POR_STR_HL"),
                "vstrana": (r.get("VSTRANA") or "").strip() or None,
                "nazev": (r.get("NAZEVCELK") or "").strip() or None,
                "zkratka": (r.get("ZKRATKAO8") or "").strip() or None,
                "hlasy": _i(r, "HLASY_STR"),
                "hlasy_proc": _f(r, "PROCHLSTR"),
                "mandaty": _i(r, "MAND_STR"),
                "slozeni": (r.get("SLOZENI") or "").strip() or None,
            })
        podle_poradi = {s["poradi"]: s for s in strany}

        # Okrsky + hlasy pro strany v okrsku.
        hlasy_okrsku: dict[int, dict[str, int]] = defaultdict(dict)
        for r in hl_v:
            okr = _i(r, "OKRSEK")
            por = _i(r, "POR_STR_HL")
            poc = _i(r, "POC_HLASU")
            if okr is None or por is None or poc is None:
                continue
            hlasy_okrsku[okr][str(por)] = poc

        okrsky = []
        for r in sorted(okrsky_syrove, key=lambda x: int(x.get("OKRSEK") or 0)):
            cislo = _i(r, "OKRSEK")
            okrsky.append({
                "cislo": cislo,
                "volicu_v_seznamu": _i(r, "VOL_SEZNAM"),
                "vydane_obalky": _i(r, "VYD_OBALKY"),
                "odevzdane_obalky": _i(r, "ODEVZ_OBAL"),
                "platne_hlasy": _i(r, "PL_HL_CELK"),
                "ucast_proc": _procenta(_i(r, "VYD_OBALKY"), _i(r, "VOL_SEZNAM")),
                "hlasy_stran": hlasy_okrsku.get(cislo, {}),
            })

        # Kandidáti a zvolení zastupitelé.
        kandidati = []
        for r in sorted(rk_v, key=lambda x: (int(x.get("POR_STR_HL") or 0),
                                             int(x.get("PORCISLO") or 0))):
            por = _i(r, "POR_STR_HL")
            strana = podle_poradi.get(por, {})
            kandidati.append({
                "osoba_id": osoba_id(r.get("JMENO", ""), r.get("PRIJMENI", "")),
                "jmeno": (r.get("JMENO") or "").strip(),
                "prijmeni": (r.get("PRIJMENI") or "").strip(),
                "cele_jmeno": _cele_jmeno(r),
                "strana_poradi": por,
                "strana": strana.get("nazev"),
                "poradi_na_listine": _i(r, "PORCISLO"),
                "vek": _i(r, "VEK"),
                "povolani": (r.get("POVOLANI") or "").strip() or None,
                "politicka_prislusnost": (r.get("PSTRANA") or "").strip() or None,
                "navrhujici_strana": (r.get("NSTRANA") or "").strip() or None,
                "hlasy": _i(r, "POCHLASU"),
                "hlasy_proc": _f(r, "POCPROCVSE"),
                "mandat": (r.get("MANDAT") or "").strip().upper() == "A",
                "poradi_mandatu": _i(r, "PORADIMAND"),
                "poradi_nahradnika": _i(r, "PORADINAHR"),
            })

        celkem_v_seznamu = sum(o["volicu_v_seznamu"] or 0 for o in okrsky)
        celkem_obalky = sum(o["vydane_obalky"] or 0 for o in okrsky)
        volby.append({
            "datum": _datum(datumvoleb),
            "datum_puvod": "okrsková data",
            "kolo": None,
            "mandatu": _i(zast_v, "MANDATY"),
            "obyvatel_dle_zdroje": _i(zast_v, "POCOBYV"),
            "ucast": {
                "okrsku": len(okrsky),
                "volicu_v_seznamu": celkem_v_seznamu,
                "vydane_obalky": celkem_obalky,
                "odevzdane_obalky": sum(o["odevzdane_obalky"] or 0 for o in okrsky),
                "platne_hlasy": sum(o["platne_hlasy"] or 0 for o in okrsky),
                "ucast_proc": _procenta(celkem_obalky, celkem_v_seznamu),
            },
            "strany": strany,
            "okrsky": okrsky,
            "kandidati": kandidati,
            "zvoleni": [k for k in kandidati if k["mandat"]],
        })
    return volby


# --------------------------------------------------------------------------
# Celostátní volby (sněmovna, kraj, EP, prezident, Senát)
# --------------------------------------------------------------------------

# Kde v registrech hledat název strany / jméno kandidáta.
KLIC_STRANY = {"ps": "KSTRANA", "kz": "KSTRANA", "ep": "ESTRANA"}
REG_STRAN = {"ps": "psrkl", "kz": "kzrkl", "ep": "eprkl"}
REG_KANDIDATU = {"prez": "perk", "se": "serk"}


def _souhrn_a_strany(tab_data: dict) -> tuple[list[dict], list[dict]]:
    """Najde v datovém balíku souhrnnou a stranickou tabulku podle sloupců.

    Názvy souborů se mezi druhy voleb liší (pst4/pst4p, kzt6/kzt6p,
    ept2/ept2p, pet1, set5), ale sloupce ne: souhrn má VOL_SEZNAM,
    stranická tabulka POC_HLASU. Poznáváme je proto podle obsahu.
    """
    souhrn: list[dict] = []
    strany: list[dict] = []
    for radky in tab_data.values():
        if not radky:
            continue
        sloupce = set(radky[0])
        if "POC_HLASU" in sloupce:
            strany = radky
        elif "VOL_SEZNAM" in sloupce:
            souhrn = radky
    return souhrn, strany


def _nazvy_stran(predpona: str, tab_reg: dict) -> dict[str, dict]:
    """Mapa kód strany → {nazev, zkratka, vstrana}."""
    tabulka = tab_reg.get(REG_STRAN.get(predpona, ""), [])
    klic = KLIC_STRANY.get(predpona, "KSTRANA")
    out: dict[str, dict] = {}
    for r in tabulka:
        k = (r.get(klic) or "").strip()
        if not k or k in out:
            continue
        out[k] = {
            "nazev": (r.get("NAZEVCELK") or r.get("NAZEVPLNY") or "").strip() or None,
            "zkratka": (r.get("ZKRATKAK8") or r.get("ZKRATKAE8") or "").strip() or None,
            "vstrana": (r.get("VSTRANA") or "").strip() or None,
        }
    return out


def _kandidati_na_poradi(predpona: str, tab_reg: dict, obvod: str | None) -> dict[int, dict]:
    """Prezidentští a senátní kandidáti — sloupce HLASY_01..NN jdou po jejich pořadí."""
    tabulka = tab_reg.get(REG_KANDIDATU.get(predpona, ""), [])
    out: dict[int, dict] = {}
    for r in tabulka:
        if obvod is not None and (r.get("OBVOD") or "").strip() != obvod:
            continue
        c = _i(r, "CKAND")
        if c is None:
            continue
        out[c] = {
            "poradi": c,
            "jmeno": (r.get("JMENO") or "").strip(),
            "prijmeni": (r.get("PRIJMENI") or "").strip(),
            "cele_jmeno": _cele_jmeno(r),
            "osoba_id": osoba_id(r.get("JMENO", ""), r.get("PRIJMENI", "")),
            "navrhujici_strana": (r.get("NSTRANA") or "").strip() or None,
            "politicka_prislusnost": (r.get("PSTRANA") or "").strip() or None,
        }
    return out


def zpracuj_celostatni(predpona: str, tab_data: dict, tab_reg: dict, log: Log) -> list[dict]:
    souhrn_vse, strany_vse = _souhrn_a_strany(tab_data)
    souhrn = _obec_radky(souhrn_vse)
    if not souhrn:
        return []
    strany_obec = _obec_radky(strany_vse)

    # Prezidentské a senátní volby mají kola; ostatní jedno "kolo" None.
    kola = sorted({(r.get("KOLO") or "").strip() for r in souhrn}) or [""]
    obvod = next((r.get("OBVOD") or "").strip() for r in souhrn) if souhrn and "OBVOD" in souhrn[0] else None

    nazvy = _nazvy_stran(predpona, tab_reg)
    kandidati = _kandidati_na_poradi(predpona, tab_reg, obvod)
    klic = KLIC_STRANY.get(predpona, "KSTRANA")

    volby = []
    for kolo in kola:
        okrsky_syrove = [r for r in souhrn if (r.get("KOLO") or "").strip() == kolo]
        strany_kola = [r for r in strany_obec if (r.get("KOLO") or "").strip() == kolo] or strany_obec

        # Hlasy po okrscích — buď ze stranické tabulky, nebo ze sloupců
        # HLASY_NN v souhrnu (prezident, Senát: kandidáti, ne strany).
        hlasy: dict[int, dict[str, int]] = defaultdict(dict)
        celkem: dict[str, int] = defaultdict(int)
        if strany_kola:
            for r in strany_kola:
                okr, poc = _i(r, "OKRSEK"), _i(r, "POC_HLASU")
                k = (r.get(klic) or "").strip()
                if okr is None or poc is None or not k:
                    continue
                hlasy[okr][k] = poc
                celkem[k] += poc
        else:
            for r in okrsky_syrove:
                okr = _i(r, "OKRSEK")
                if okr is None:
                    continue
                for sl in r:
                    m = re.fullmatch(r"HLASY_(\d+)", sl)
                    if not m:
                        continue
                    poc = _i(r, sl)
                    if not poc:
                        continue
                    k = str(int(m.group(1)))
                    hlasy[okr][k] = poc
                    celkem[k] += poc

        platne_celkem = sum(_i(r, "PL_HL_CELK") or 0 for r in okrsky_syrove)
        polozky = []
        for k, poc in sorted(celkem.items(), key=lambda x: -x[1]):
            zaznam = {
                "kod": k,
                "hlasy": poc,
                "hlasy_proc": _procenta(poc, platne_celkem),
            }
            if predpona in REG_KANDIDATU:
                kand = kandidati.get(int(k), {})
                zaznam["nazev"] = kand.get("cele_jmeno") or f"kandidát č. {k}"
                zaznam["osoba_id"] = kand.get("osoba_id")
                zaznam["navrhujici_strana"] = kand.get("navrhujici_strana")
            else:
                info = nazvy.get(k, {})
                zaznam["nazev"] = info.get("nazev") or f"strana č. {k}"
                zaznam["zkratka"] = info.get("zkratka")
                zaznam["vstrana"] = info.get("vstrana")
            polozky.append(zaznam)

        okrsky = []
        for r in sorted(okrsky_syrove, key=lambda x: int(x.get("OKRSEK") or 0)):
            c = _i(r, "OKRSEK")
            okrsky.append({
                "cislo": c,
                "volicu_v_seznamu": _i(r, "VOL_SEZNAM"),
                "vydane_obalky": _i(r, "VYD_OBALKY"),
                "odevzdane_obalky": _i(r, "ODEVZ_OBAL"),
                "platne_hlasy": _i(r, "PL_HL_CELK"),
                "ucast_proc": _procenta(_i(r, "VYD_OBALKY"), _i(r, "VOL_SEZNAM")),
                "hlasy_stran": hlasy.get(c, {}),
            })

        v_seznamu = sum(o["volicu_v_seznamu"] or 0 for o in okrsky)
        obalky = sum(o["vydane_obalky"] or 0 for o in okrsky)
        volby.append({
            "datum": _datum(next((r.get("DATUMVOLEB") for r in okrsky_syrove
                                  if r.get("DATUMVOLEB")), None)),
            "datum_puvod": "okrsková data",
            "kolo": int(kolo) if kolo.isdigit() else None,
            "senatni_obvod": obvod,
            "ucast": {
                "okrsku": len(okrsky),
                "volicu_v_seznamu": v_seznamu,
                "vydane_obalky": obalky,
                "odevzdane_obalky": sum(o["odevzdane_obalky"] or 0 for o in okrsky),
                "platne_hlasy": platne_celkem,
                "ucast_proc": _procenta(obalky, v_seznamu),
            },
            "strany": polozky,
            "okrsky": okrsky,
        })
    return volby


# --------------------------------------------------------------------------
# Kontroly — data se nesmí uložit, aniž by se ověřilo, že sedí
# --------------------------------------------------------------------------

def zkontroluj(kod: str, v: dict, log: Log) -> list[str]:
    """Vrátí seznam nesrovnalostí. Prázdný seznam = data sedí."""
    potize = []
    u = v["ucast"]
    if u["volicu_v_seznamu"] and u["vydane_obalky"]:
        ucast = 100.0 * u["vydane_obalky"] / u["volicu_v_seznamu"]
        if not 5.0 <= ucast <= 100.0:
            potize.append(f"{kod}: účast {ucast:.1f} % mimo rozumné rozmezí")
    soucet_stran = sum(s["hlasy"] or 0 for s in v["strany"])
    if u["platne_hlasy"] and soucet_stran and soucet_stran != u["platne_hlasy"]:
        potize.append(
            f"{kod}: součet hlasů stran {soucet_stran} != platné hlasy {u['platne_hlasy']}")
    # Součet hlasů po okrscích musí dát celkový výsledek strany.
    po_okrscich: dict[str, int] = defaultdict(int)
    for o in v["okrsky"]:
        for k, poc in o["hlasy_stran"].items():
            po_okrscich[k] += poc
    for s in v["strany"]:
        klic = str(s.get("poradi") if "poradi" in s else s.get("kod"))
        if s.get("hlasy") is not None and klic in po_okrscich:
            if po_okrscich[klic] != s["hlasy"]:
                potize.append(f"{kod}: strana {klic} — okrsky {po_okrscich[klic]} "
                              f"!= celkem {s['hlasy']}")
    for o in v["okrsky"]:
        if o["volicu_v_seznamu"] and o["vydane_obalky"]:
            if o["vydane_obalky"] > o["volicu_v_seznamu"]:
                potize.append(f"{kod}: okrsek {o['cislo']} — víc obálek než voličů")
    return potize


# --------------------------------------------------------------------------
# Jeden cyklus
# --------------------------------------------------------------------------

def zpracuj_cyklus(kod: str, log: Log) -> dict:
    predpona = druh_cyklu(kod)
    if not predpona:
        raise ZdrojSelhal(f"neznámý druh voleb: {kod}")
    druh = DRUHY[predpona]
    zaznam: dict = {
        "cyklus": kod,
        "druh": druh["typ"],
        "nazev": druh["nazev"],
        "rok": rok_cyklu(kod),
        "obec": {"kod": OBEC, "nazev": OBEC_NAZEV, "okres": OKRES, "kraj": KRAJ},
        "zdroj": f"{KOREN}/{kod}/{kod}_opendata.htm",
        "stav": "chybi",
        "volby": [],
    }

    odkazy = odkazy_cyklu(kod)
    if "data" not in odkazy:
        raise ZdrojSelhal(f"{kod}: rozcestník nenabízí CSV s okrskovými daty")
    zaznam["zdroj_data"] = odkazy["data"]
    zaznam["zdroj_registry"] = odkazy.get("reg")

    tab_data = _tabulky(_stahni_zip(odkazy["data"], log))
    tab_reg = _tabulky(_stahni_zip(odkazy["reg"], log)) if odkazy.get("reg") else {}

    if predpona == "kv":
        volby = zpracuj_kv(kod, tab_data, tab_reg, log)
    else:
        volby = zpracuj_celostatni(predpona, tab_data, tab_reg, log)

    if not volby:
        # Není to chyba: v senátních volbách se hlasuje jen ve třetině
        # obvodů, takže Mariánské Lázně v datech legitimně nejsou.
        zaznam["stav"] = "neucastnila_se"
        log.info(f"{kod}: Mariánské Lázně v datech nejsou (volby se tu nekonaly)")
        return zaznam

    # Sněmovní, krajské a evropské volby nemají datum ani v datech, ani
    # v registrech. Když ho uvádí aspoň nadpis rozcestníku, doplní se odtud
    # a je to u záznamu vidět. Jinak zůstane null.
    z_nadpisu = datum_z_rozcestniku(kod)
    for v in volby:
        if not v.get("datum"):
            v["datum"] = z_nadpisu
            v["datum_puvod"] = "nadpis rozcestníku" if z_nadpisu else None

    potize = []
    for v in volby:
        potize += zkontroluj(kod, v, log)
    for p in potize:
        log.chyba(p)
    zaznam["volby"] = volby
    zaznam["stav"] = "ok"
    zaznam["kontrola"] = {"nesrovnalosti": potize}
    ucasti = ", ".join(
        (f"kolo {v['kolo']}: " if v.get("kolo") else "") + f"{v['ucast']['ucast_proc']} %"
        for v in volby)
    log.info(f"{kod}: {volby[0]['ucast']['okrsku']} okrsků, účast {ucasti}")
    return zaznam


# --------------------------------------------------------------------------
# Odvozené přehledy
# --------------------------------------------------------------------------

def _klic_strany(s: dict) -> str:
    """Klíč pro sledování strany napříč cykly.

    Kód volební strany (VSTRANA) je celostátní číselník a mezi cykly se
    nemění — je to jediné, co drží identitu strany. Když chybí (prezident,
    Senát), padáme na slug názvu, což je slabší a je to tak označené.
    """
    if s.get("vstrana"):
        return f"vstrana:{s['vstrana']}"
    if s.get("osoba_id"):
        return f"osoba:{s['osoba_id']}"
    return f"nazev:{slug(s.get('nazev') or '')}"


def casova_osa(cykly: list[dict]) -> dict:
    """Jak se ve městě volilo v čase, strana po straně."""
    podle_druhu: dict[str, dict] = {}
    for c in cykly:
        if c["stav"] != "ok":
            continue
        d = podle_druhu.setdefault(c["druh"], {
            "nazev": c["nazev"], "volby": [], "strany": {},
        })
        for v in c["volby"]:
            oznaceni = c["cyklus"] + (f"-kolo{v['kolo']}" if v.get("kolo") else "")
            d["volby"].append({
                "id": oznaceni,
                "cyklus": c["cyklus"],
                "rok": c["rok"],
                "datum": v["datum"],
                "kolo": v.get("kolo"),
                "okrsku": v["ucast"]["okrsku"],
                "volicu_v_seznamu": v["ucast"]["volicu_v_seznamu"],
                "ucast_proc": v["ucast"]["ucast_proc"],
                "platne_hlasy": v["ucast"]["platne_hlasy"],
                "mandatu": v.get("mandatu"),
            })
            for s in v["strany"]:
                k = _klic_strany(s)
                z = d["strany"].setdefault(k, {
                    "klic": k,
                    "nazvy": [],
                    "identita": "vstrana" if s.get("vstrana") else (
                        "osoba" if s.get("osoba_id") else "nazev"),
                    "vysledky": {},
                })
                if s.get("nazev") and s["nazev"] not in z["nazvy"]:
                    z["nazvy"].append(s["nazev"])
                z["vysledky"][oznaceni] = {
                    "hlasy": s.get("hlasy"),
                    "hlasy_proc": s.get("hlasy_proc"),
                    "mandaty": s.get("mandaty"),
                }
    # Řadí se podle roku, ne podle data: rok je z kódu cyklu jistý, kdežto
    # datum u sněmovních, krajských a evropských voleb zdroj neuvádí.
    for d in podle_druhu.values():
        d["volby"].sort(key=lambda x: (x["rok"] or 0, x["kolo"] or 0))
        d["strany"] = sorted(
            d["strany"].values(),
            key=lambda z: -max((v["hlasy_proc"] or 0) for v in z["vysledky"].values()),
        )
    return {
        "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "poznamka": (
            "Identita strany se drží přes kód volební strany (VSTRANA) z celostátního "
            "číselníku ČSÚ. Kde chybí, je klíč odvozený z názvu a shoda napříč cykly "
            "je jen pravděpodobná — pole `identita` říká, o který případ jde."
        ),
        "druhy": podle_druhu,
    }


def prehled_okrsku(cykly: list[dict], vrstvy: list[dict]) -> dict:
    """Co o okrscích víme a co ne.

    Zdroj neříká, jestli okrsek č. 3 z roku 2002 leží tam, co okrsek č. 3
    z roku 2022. Umíme porovnat počet a čísla okrsků — a to je taky všechno,
    co se sem smí napsat.
    """
    podle_voleb: dict[str, dict] = {}
    for c in cykly:
        if c["stav"] != "ok":
            continue
        for v in c["volby"]:
            oznaceni = c["cyklus"] + (f"-kolo{v['kolo']}" if v.get("kolo") else "")
            cisla = sorted(o["cislo"] for o in v["okrsky"] if o["cislo"] is not None)
            podle_voleb[oznaceni] = {
                "druh": c["druh"],
                "rok": c["rok"],
                "datum": v["datum"],
                "pocet": len(cisla),
                "cisla": cisla,
                "volicu_v_seznamu": v["ucast"]["volicu_v_seznamu"],
            }
    poradi = sorted(podle_voleb, key=lambda k: (podle_voleb[k]["rok"] or 0,
                                                podle_voleb[k]["datum"] or ""))
    srovnani = []
    for a, b in zip(poradi, poradi[1:]):
        A, B = podle_voleb[a], podle_voleb[b]
        srovnani.append({
            "od": a, "do": b,
            "stejny_pocet": A["pocet"] == B["pocet"],
            "stejna_cisla": A["cisla"] == B["cisla"],
            "pribylo": sorted(set(B["cisla"]) - set(A["cisla"])),
            "ubylo": sorted(set(A["cisla"]) - set(B["cisla"])),
        })
    # Co o hranicích říká sám zdroj: u každého polygonu je datum, odkdy platí.
    hranice = []
    for v in vrstvy:
        for f in v["features"]:
            p = f["properties"]
            hranice.append({"vrstva": v["plati_k"], "okrsek": p["okrsek"],
                            "plati_od": p["plati_od"], "plati_do": p["plati_do"]})
    zmeny = sorted({h["plati_od"] for h in hranice if h["plati_od"]})

    return {
        "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "poznamka": (
            "Shodné číslo okrsku ve dvou volbách NEZNAMENÁ shodné území. ČSÚ v otevřených "
            "datech hranice okrsků k jednotlivým volbám nepublikuje — geometrie existuje "
            "jen jako samostatná vrstva k roku (viz okrsky_geo/). Porovnávat výsledky "
            "okrsek po okrsku mezi vzdálenými roky jde proto jen s touhle výhradou."
        ),
        "co_vime": (
            "Počet a čísla okrsků, protože jsou přímo v okrskových datech ke každým volbám."
        ),
        "co_nevime": (
            "Zda okrsek téhož čísla pokrývá v různých letech totéž území. Pro roky bez "
            "geometrie to zdroj neříká a nedopočítáváme to."
        ),
        "volby": podle_voleb,
        "srovnani_po_sobe": srovnani,
        "hranice_dle_zdroje": {
            "vrstvy": [v["plati_k"] for v in vrstvy],
            "data_zmen": zmeny,
            "okrsky": sorted(hranice, key=lambda h: (h["vrstva"], h["okrsek"] or 0)),
        },
    }


def zastupitele(cykly: list[dict]) -> list[dict]:
    """Zvolení zastupitelé ze všech komunálních cyklů, k propojení s osobnostmi."""
    out = []
    for c in cykly:
        if c["druh"] != "komunalni" or c["stav"] != "ok":
            continue
        for v in c["volby"]:
            for z in v.get("zvoleni", []):
                out.append({
                    "cyklus": c["cyklus"],
                    "rok": c["rok"],
                    "datum": v["datum"],
                    "osoba_id": z["osoba_id"],
                    "jmeno": f"{z['jmeno']} {z['prijmeni']}".strip(),
                    "cele_jmeno": z["cele_jmeno"],
                    "strana": z["strana"],
                    "politicka_prislusnost": z["politicka_prislusnost"],
                    "poradi_na_listine": z["poradi_na_listine"],
                    "poradi_mandatu": z["poradi_mandatu"],
                    "hlasy": z["hlasy"],
                    "hlasy_proc": z["hlasy_proc"],
                    "vek_v_dobe_voleb": z["vek"],
                    "povolani": z["povolani"],
                })
    return sorted(out, key=lambda z: (z["rok"] or 0, z["strana"] or "",
                                      z["poradi_mandatu"] or 0))


def geometrie_okrsku(log: Log) -> list[dict]:
    """Hranice volebních okrsků Mariánských Lázní jako GeoJSON, po ročnících.

    Celorepublikový soubor má 8 MB a 14 733 okrsků; do dat jde jen 17
    polygonů obce. Vrstva je vedená k roku, ne k volbám, a **hranice se
    mezi ročníky liší** — proto se ukládají všechny dostupné ročníky vedle
    sebe a u každého okrsku zůstává `PLATIOD` ze zdroje, tedy datum, od
    kterého ta hranice podle ČSÚ platí. Vybírat vrstvu k volbám je věc
    zobrazení, ne sběru.
    """
    vrstvy = []
    for rok, url in GEO_ZDROJE:
        try:
            syrove = fetch(url, binary=True, max_age=30 * 86_400)
        except ZdrojSelhal as e:
            log.info(f"geometrie {rok}: {e}")
            continue
        assert isinstance(syrove, bytes)
        gj = json.loads(syrove.decode("utf-8"))
        prvky = [f for f in gj.get("features", [])
                 if str(f.get("properties", {}).get("OBEC")) == OBEC]
        if not prvky:
            log.info(f"geometrie {rok}: obec {OBEC} ve vrstvě není")
            continue
        for f in prvky:
            p = f["properties"]
            p["okrsek"] = int(p["CISLO"]) if str(p.get("CISLO", "")).isdigit() else None
            p["plati_od"] = _datum(p.get("PLATIOD"))
            p["plati_do"] = _datum(p.get("PLATIDO")) or None
        prvky.sort(key=lambda f: f["properties"]["okrsek"] or 0)
        zmeny = sorted({f["properties"]["plati_od"] for f in prvky if f["properties"]["plati_od"]})
        log.info(f"geometrie okrsků {rok}: {len(prvky)} polygonů, "
                 f"hranice platné od {zmeny[0]} do {zmeny[-1]}")
        vrstvy.append({
            "type": "FeatureCollection",
            "plati_k": rok,
            "zdroj": url,
            "souradnice": "WGS 84 (EPSG:4326)",
            "poznamka": (
                f"Hranice volebních okrsků ve stavu, v jakém je ČSÚ vydal k roku {rok}. "
                "Pro starší volby zdroj geometrii nezveřejňuje a tahle vrstva pro ně "
                "NEPLATÍ. Datum `plati_od` u každého okrsku je tvrzení zdroje o tom, "
                "odkdy ta hranice platí."
            ),
            "features": prvky,
        })
    return vrstvy


# --------------------------------------------------------------------------
# Běh
# --------------------------------------------------------------------------

def sber(kody: list[str], log: Log) -> dict:
    hotove: list[dict] = []
    for kod in kody:
        try:
            z = zpracuj_cyklus(kod, log)
        except ZdrojSelhal as e:
            log.chyba(f"{kod}: {e}")
            continue
        uloz(f"{VYSTUP}/cykly/{kod}.json", z)
        hotove.append(z)
        if z["stav"] == "ok":
            log.pricti(sum(len(v["okrsky"]) for v in z["volby"]))

    # Cykly z dřívějších běhů, které teď nebyly na řadě, se přiberou —
    # jinak by dílčí běh (--typ kv) vymazal časovou osu ostatních voleb.
    znam = {z["cyklus"] for z in hotove}
    for p in sorted((DATA / VYSTUP / "cykly").glob("*.json")):
        if p.stem not in znam:
            hotove.append(json.loads(p.read_text(encoding="utf-8")))

    hotove.sort(key=lambda z: (z["druh"], z["rok"] or 0))
    vrstvy = geometrie_okrsku(log)
    for v in vrstvy:
        uloz(f"{VYSTUP}/okrsky_geo/{v['plati_k']}.json", v)

    uloz(f"{VYSTUP}/casova_osa.json", casova_osa(hotove))
    uloz(f"{VYSTUP}/okrsky.json", prehled_okrsku(hotove, vrstvy))
    zast = zastupitele(hotove)
    uloz(f"{VYSTUP}/zastupitele.json", zast)
    log.info(f"zvolených zastupitelů celkem: {len(zast)}")

    prehled = {
        "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "obec": {"kod": OBEC, "nazev": OBEC_NAZEV, "okres": OKRES, "kraj": KRAJ},
        "zdroj": f"{KOREN}/opendata.htm",
        "licence": "https://www.czso.cz/csu/czso/podminky_pro_vyuzivani_a_dalsi_zverejnovani_statistickych_udaju_csu",
        "geometrie_okrsku": [{
            "plati_k": v["plati_k"],
            "soubor": f"data/{VYSTUP}/okrsky_geo/{v['plati_k']}.json",
            "okrsku": len(v["features"]),
        } for v in vrstvy],
        "cykly": [{
            "cyklus": z["cyklus"], "druh": z["druh"], "nazev": z["nazev"],
            "rok": z["rok"], "stav": z["stav"],
            "voleb": len(z["volby"]),
            "okrsku": z["volby"][0]["ucast"]["okrsku"] if z["volby"] else None,
            # Účast prvního kola — u dvoukolových voleb je to ta srovnatelná.
            "ucast_proc": z["volby"][0]["ucast"]["ucast_proc"] if z["volby"] else None,
            "ucast_po_kolech": [
                {"kolo": v.get("kolo"), "ucast_proc": v["ucast"]["ucast_proc"]}
                for v in z["volby"]] if len(z["volby"]) > 1 else None,
            "nesrovnalosti": len(z.get("kontrola", {}).get("nesrovnalosti", [])),
        } for z in hotove],
    }
    uloz(f"{VYSTUP}/prehled.json", prehled)
    return prehled


def hlavni() -> int:
    ap = argparse.ArgumentParser(description="O1 — volební výsledky Mariánských Lázní")
    ap.add_argument("--typ", help="jen jeden druh voleb (kv, ps, kz, ep, prez, se)")
    ap.add_argument("--cyklus", action="append", help="jen tenhle cyklus (lze opakovat)")
    ap.add_argument("--prehled", action="store_true",
                    help="jen vypíše, jaké cykly a soubory zdroj nabízí")
    args = ap.parse_args()

    log = Log("volby")
    try:
        kody = args.cyklus or seznam_cyklu(log)
    except ZdrojSelhal as e:
        log.chyba(str(e))
        log.uzavri()
        return 1
    if args.typ:
        kody = [k for k in kody if druh_cyklu(k) == args.typ]
        if not kody:
            log.chyba(f"pro druh {args.typ} nemám žádný cyklus")
            log.uzavri()
            return 1

    if args.prehled:
        for k in kody:
            try:
                o = odkazy_cyklu(k)
            except ZdrojSelhal as e:
                print(f"{k:14} CHYBA {e}")
                continue
            print(f"{k:14} {DRUHY[druh_cyklu(k)]['typ']:14} {', '.join(sorted(o))}")
        log.uzavri()
        return 0

    log.info(f"zpracovávám {len(kody)} cyklů: {', '.join(kody)}")
    sber(kody, log)
    vysledek = log.uzavri()
    return 0 if vysledek["uspech"] else 1


if __name__ == "__main__":
    raise SystemExit(hlavni())
