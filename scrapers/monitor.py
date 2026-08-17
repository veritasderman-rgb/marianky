#!/usr/bin/env python3
"""Monitor státní pokladny — rozpočet města a účetní výkazy holdingu.

Zdroj: **lokální katalog otevřených dat Ministerstva financí** na
`https://monitor.statnipokladna.gov.cz/api/opendata/monitor`. Vrací JSON-LD
podle otevřené formální normy „rozhraní katalogů otevřených dat" a obsahuje
803 datových sad — celostátní extrakty CSÚIS plus číselníky.

Jak se to našlo (ať to nikdo nemusí hledat znovu)
-------------------------------------------------
Samotná aplikace `monitor.statnipokladna.gov.cz` je Angular a na **jakoukoliv
neznámou cestu vrací svou úvodní stránku**, takže hádání adres nefunguje —
`/api/...` i `/otevrena-data` vypadaly jako 404 nebo jako prázdná skořápka.
Adresa katalogu je ale zaregistrovaná v Národním katalogu otevřených dat:

    SPARQL na https://data.gov.cz/sparql, dataset
    https://data.gov.cz/zdroj/datové-sady/00006947/c40985841e83510d2044b5d37d1f3849
    → dct:identifier = https://monitor.statnipokladna.gov.cz/api/opendata/monitor/MONITOR

O úroveň výš (`/api/opendata/monitor`, bez `/MONITOR`) sedí celý katalog.
NKOD tedy sloužil jen jako rozcestník; data se pak berou přímo od MF.

Čtyři věci, které nejsou samozřejmé
-----------------------------------
1. **Adresy souborů se NESMÍ skládat z názvu sady.** Skupina v katalogu se
   jmenuje jinak než složka v úložišti: sada `.../monitor/Zisk-a-ztraty/...`
   leží na `.../extrakty/csv/ZiskZtraty/...`. Odvozená adresa vrátí 404.
   Proto se u každé sady čte `distribuce[].soubor_ke_stažení`.
   (Výpis adresáře `/data/extrakty/csv/` je zakázaný — 403 —, ale konkrétní
   soubor se stáhne bez problémů.)

2. **Částky jsou v celých korunách, ne v tisících.** Ověřeno proti usnesení
   zastupitelstva: schválený rozpočet výdajů města na rok 2019 vychází ze
   sady na 397 951 000 Kč, což přesně odpovídá „397 mil." z usnesení.
   Do každého souboru se proto zapisuje `jednotka: "CZK"`.

3. **IČO má ve starších extraktech deset míst.** Do roku 2012 je zleva
   vycpané nulami (`0000254061`), pak osm (`00254061`). Bez normalizace by
   se starší roky tvářily jako „subjekt nenalezen", tedy jako by město
   neexistovalo — což je tichá díra v časové ose, ne chyba dat.

4. **Od roku 2026 je FIN 2-12 M jiný výkaz.** Kód se změnil z `051` na
   `063`, příjmy i výdaje se slily do jedné tabulky rozlišené sloupcem
   `0CI_TYPE` a **souhrnná tabulka (rekapitulace) v extraktu zmizela**.
   Číslo tabulky proto samo o sobě nic neznamená: `000200` je v `051`
   tabulka výdajů, ale v `063` tabulka bankovních účtů. Mapuje se dvojicí
   (výkaz, tabulka) a kódy výkazů se zapisují k datům, aby navazující
   zpracování poznalo, se kterou podobou má co do činění.

Co se odsud NEDÁ získat
-----------------------
FIN 2-12 M podávají jen územní samosprávné celky, takže **rozpočet má
v datech pouze město**. Příspěvkové organizace (školy, muzeum, knihovna…)
se v extraktech objevují jen účetními výkazy — rozvahou a výkazem zisku
a ztráty. Není to mezera ve sběru, je to rozsah povinnosti výkaznictví.

Spuštění:
    python3 scrapers/monitor.py                  # roční data, všechny výkazy
    python3 scrapers/monitor.py --katalog        # jen vypsat, co katalog nabízí
    python3 scrapers/monitor.py --vykaz fin212m  # jen jeden výkaz
    python3 scrapers/monitor.py --vse-obdobi     # i mezitímní čtvrtletí
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import (  # noqa: E402
    CACHE,
    UA,
    Log,
    ZdrojSelhal,
    fetch,
    sledovane_subjekty,
    uloz,
)
# Tempo mezi požadavky na stejný server drží jádro přes soubor se značkou.
# `_stahni()` níž nemůže použít `core.fetch()` (neumí navazovat přerušené
# stahování velkých souborů), ale tempo držet musí — proto tenhle pomocník.
from lib.core import _pockej_na_rade  # noqa: E402

KATALOG = "https://monitor.statnipokladna.gov.cz/api/opendata/monitor"
VYSTUP = "rozpocet"
STAHOVANE = CACHE / "monitor"

# Číselníky. Adresy jsou v katalogu u sad `ciselnik-*`; drží se tu jejich
# identifikátory, ne adresy souborů — viz poznámka 1 v hlavičce.
CISELNIKY = {
    "paragrafy": ("ciselnik-paragraf", "CSV"),
    "polozky": ("ciselnik-rozpoctova-polozka", "CSV"),
    "polozky_vykazu": ("ciselnik-polozka-vykazu", "CSV"),
}


# --------------------------------------------------------------------------
# Které výkazy sbíráme
# --------------------------------------------------------------------------

@dataclass
class Vykaz:
    """Jeden druh výkazu napříč obdobími.

    `vzor` se pouští na název sady (`2019_12_Data_CSUIS_FINM`). Musí být
    ukotvený na konec, jinak by `FINM` chytil i `FINMMC` (městské části
    Prahy) a `ROZV` i `ROZV_KONS` — jiné výkazy s jinými sloupci.
    """
    kod: str
    nazev: str
    popis: str
    vzor: re.Pattern
    # {kód sloupce ve zdroji: náš název} — sloupce se hledají podle hlavičky,
    # ne podle pořadí. Hlavička se mezi ročníky mění (2010 nemá popisky,
    # 2025 je má a některé kódy má s prefixem /BIC/), pořadí sloupců ne.
    klice: dict[str, str] = field(default_factory=dict)
    hodnoty: dict[str, str] = field(default_factory=dict)
    # Tabulky, které nás zajímají: {(kód výkazu, kód tabulky): náš oddíl}.
    # Klíčem musí být dvojice, ne samotná tabulka — od roku 2026 nese FIN
    # 2-12 M kód výkazu 063 místo 051 a tabulka `000200` v něm znamená něco
    # úplně jiného než dřív (bankovní účty místo výdajů). Kdo by mapoval jen
    # podle čísla tabulky, uložil by si stavy účtů jako výdaje města.
    tabulky: dict[tuple[str, str], str] = field(default_factory=dict)


VYKAZY: dict[str, Vykaz] = {
    "fin212m": Vykaz(
        kod="fin212m",
        nazev="FIN 2-12 M — Výkaz pro hodnocení plnění rozpočtu ÚSC",
        popis=(
            "Plnění rozpočtu územního samosprávného celku po paragrafech "
            "a položkách rozpočtové skladby. Podávají jen ÚSC, nikoliv "
            "příspěvkové organizace."
        ),
        # `(\d{4})?` na konci pokrývá sady běžícího roku (`..._FINM2026`).
        vzor=re.compile(r"^(\d{4})_(\d{2})_Data_CSUIS_FINM(\d{4})?$"),
        klice={
            "0CI_TYPE": "typ_kod",
            "0FUNC_AREA": "paragraf",
            "ZCMMT_ITM": "polozka",
            "ZC_POLVYK": "polozka_vykazu",
            "ZC_BUCE": "ucet",
        },
        hodnoty={
            "ZU_ROZSCH": "schvaleny",
            "ZU_ROZPZM": "upraveny",
            "ZU_ROZKZ": "skutecnost",
            # Tabulka bankovních účtů má jinou trojici sloupců; sloupec se
            # změnou stavu se od roku 2026 jmenuje ZU_ZMSTAV místo ZU_ZMEST.
            "ZU_PZ": "pocatecni_stav",
            "ZU_AKTZ": "koncovy_stav",
            "ZU_ZMEST": "zmena",
            "ZU_ZMSTAV": "zmena",
        },
        tabulky={
            # Výkaz 051 — podoba platná do roku 2025 včetně.
            ("051", "000100"): "prijmy",
            ("051", "000200"): "vydaje",
            ("051", "000300"): "financovani",
            ("051", "000400"): "rekapitulace",
            ("051", "000600"): "bankovni_ucty",
            # Výkaz 063 — od roku 2026. Příjmy i výdaje jsou v jedné tabulce
            # a rozlišuje je sloupec 0CI_TYPE (2 = příjmy, 3 = výdaje);
            # souhrnná tabulka (rekapitulace) v extraktu úplně chybí.
            ("063", "000100"): "rozpocet",
            ("063", "000200"): "bankovni_ucty",
        },
    ),
    "rozvaha": Vykaz(
        kod="rozvaha",
        nazev="Rozvaha",
        popis="Účetní výkaz: aktiva a pasiva k rozvahovému dni.",
        vzor=re.compile(r"^(\d{4})_(\d{2})_Data_CSUIS_ROZV$"),
        klice={"ZC_POLVYK": "polozka_vykazu", "ZC_SYNUC": "synteticky_ucet"},
        hodnoty={
            "ZU_AOBTTO": "brutto",
            "ZU_AOKORR": "korekce",
            "ZU_AONET": "netto",
            "ZU_MONET": "netto_minule",
        },
        tabulky={("001", "000100"): "rozvaha"},
    ),
    "vyzz": Vykaz(
        kod="vyzz",
        nazev="Výkaz zisku a ztráty",
        popis="Účetní výkaz: náklady a výnosy za hlavní a hospodářskou činnost.",
        vzor=re.compile(r"^(\d{4})_(\d{2})_Data_CSUIS_VYKZZ$"),
        klice={"ZC_POLVYK": "polozka_vykazu", "ZC_SYNUC": "synteticky_ucet"},
        hodnoty={
            "ZU_HLCIBO": "hlavni_cinnost",
            "ZU_HCINBO": "hospodarska_cinnost",
            "ZU_HLCIN": "hlavni_cinnost_minule",
            "ZU_HOSCIN": "hospodarska_cinnost_minule",
        },
        tabulky={("002", "000100"): "vyzz"},
    ),
}


# --------------------------------------------------------------------------
# Katalog
# --------------------------------------------------------------------------

def _json(url: str, max_age: int = 43_200) -> dict:
    txt = fetch(url, max_age=max_age)
    try:
        return json.loads(txt)
    except json.JSONDecodeError as e:
        # Aplikace vrací na neznámé cesty vlastní HTML úvodní stránku
        # s kódem 200. Bez téhle kontroly by se HTML tvářilo jako prázdná data.
        raise ZdrojSelhal(f"{url} nevrátilo JSON (nejspíš HTML skořápka aplikace): {e}")


def nacti_katalog() -> list[str]:
    """Seznam IRI všech datových sad v katalogu MF."""
    kat = _json(KATALOG)
    sady = kat.get("datová_sada") or []
    if not sady:
        raise ZdrojSelhal(f"{KATALOG}: katalog nevrátil žádné datové sady")
    return sady


def _nazev_sady(iri: str) -> str:
    from urllib.parse import unquote
    return unquote(iri).rsplit("/", 1)[-1]


def popis_sady(iri: str) -> dict:
    """Detail jedné sady včetně adres ke stažení."""
    return _json(iri)


def soubor_ke_stazeni(detail: dict, format_kod: str = "CSV") -> str | None:
    """Vytáhne z detailu sady adresu souboru v požadovaném formátu.

    Adresa se **nikdy neskládá z názvu sady** — složka v úložišti se jmenuje
    jinak než skupina v katalogu (`Zisk-a-ztraty` → `ZiskZtraty`).
    """
    for dist in detail.get("distribuce") or []:
        url = dist.get("soubor_ke_stažení")
        if not url:
            continue
        fmt = (dist.get("formát") or "").rsplit("/", 1)[-1].upper()
        if fmt == format_kod.upper():
            return url
    return None


def sady_vykazu(katalog: list[str], vykaz: Vykaz) -> list[tuple[int, int, str]]:
    """Sady daného výkazu jako (rok, měsíc, IRI), seřazené."""
    out = []
    for iri in katalog:
        m = vykaz.vzor.match(_nazev_sady(iri))
        if m:
            out.append((int(m.group(1)), int(m.group(2)), iri))
    return sorted(out)


def vyber_obdobi(sady: list[tuple[int, int, str]], vse: bool) -> list[tuple[int, int, str]]:
    """Vybere období ke stažení.

    Ve výchozím stavu jen **prosincové** sady — to jsou konečná roční data,
    ze kterých se staví časová osa. Běžící rok prosinec ještě nemá, takže se
    k nim přidá jeho nejnovější mezitímní období; nese příznak `koncove:
    false`, aby graf neporovnával půl roku s celými roky.
    """
    if vse:
        return sady
    rocni = [s for s in sady if s[1] == 12]
    hotove_roky = {s[0] for s in rocni}
    rozpracovane = [s for s in sady if s[0] not in hotove_roky]
    posledni = {}
    for rok, mesic, iri in rozpracovane:
        if rok not in posledni or mesic > posledni[rok][1]:
            posledni[rok] = (rok, mesic, iri)
    return sorted(rocni + list(posledni.values()))


# --------------------------------------------------------------------------
# Stahování velkých souborů
# --------------------------------------------------------------------------

def _hlavicky(extra: dict | None = None) -> dict:
    h = {"User-Agent": UA, "Accept-Language": "cs,en;q=0.8"}
    if extra:
        h.update(extra)
    return h


def _ocekavana_velikost(url: str) -> int:
    req = urllib.request.Request(url, headers=_hlavicky(), method="HEAD")
    try:
        _pockej_na_rade(urlparse(url).netloc)
        with urllib.request.urlopen(req, timeout=45) as r:
            return int(r.headers.get("Content-Length") or 0)
    except Exception:  # noqa: BLE001 — bez velikosti se prostě neověří úplnost
        return 0


def _stahni(url: str, jmeno: str, log: Log, pokusu: int = 40) -> Path:
    """Stáhne ZIP a dotáhne ho, i kdyby spojení spadlo uprostřed.

    Velikost se porovnává s `Content-Length` a chybějící část se dožádá
    hlavičkou `Range`. Nedostažený soubor se **nikdy nevydává za hotový** —
    letí `ZdrojSelhal`, protože useknutý ZIP by jinak vypadal jako
    „subjekt v tom roce nic nevykázal".
    """
    STAHOVANE.mkdir(parents=True, exist_ok=True)
    cil = STAHOVANE / jmeno
    celkem = _ocekavana_velikost(url)
    if cil.exists() and celkem and cil.stat().st_size >= celkem:
        return cil
    if cil.exists() and not celkem and zipfile.is_zipfile(cil):
        return cil

    hlaseno = naprazdno = 0
    for _ in range(pokusu):
        mam = cil.stat().st_size if cil.exists() else 0
        if celkem and mam >= celkem:
            break
        if mam and not hlaseno:
            log.info(f"{jmeno}: spojení useknuto na {mam}/{celkem} B, navazuji")
            hlaseno = 1
        req = urllib.request.Request(
            url, headers=_hlavicky({"Range": f"bytes={mam}-"} if mam else None))
        try:
            _pockej_na_rade(urlparse(url).netloc)
            with urllib.request.urlopen(req, timeout=90) as r:
                rezim = "ab" if (mam and r.status == 206) else "wb"
                with open(cil, rezim) as f:
                    while True:
                        blok = r.read(1 << 20)
                        if not blok:
                            break
                        f.write(blok)
        except Exception:  # noqa: BLE001 — opakujeme na čemkoliv síťovém
            pass
        pote = cil.stat().st_size if cil.exists() else 0
        naprazdno = naprazdno + 1 if pote <= mam else 0
        if naprazdno:
            time.sleep(min(2 ** naprazdno, 15))

    mam = cil.stat().st_size if cil.exists() else 0
    if celkem and mam < celkem:
        raise ZdrojSelhal(f"{url}: stáhlo se jen {mam} z {celkem} B ani na {pokusu} pokusů")
    if not zipfile.is_zipfile(cil):
        raise ZdrojSelhal(f"{url}: stažený soubor není platný ZIP ({mam} B)")
    return cil


# --------------------------------------------------------------------------
# Čtení extraktů
# --------------------------------------------------------------------------

def normalizuj_ico(s: str) -> str:
    """Sjednotí IČO na osm míst.

    Extrakty do roku 2012 vozí IČO na deset míst vycpané nulami. Bez tohohle
    by starší roky vypadaly, jako by v nich město neexistovalo.
    """
    s = (s or "").strip().strip('"')
    if not s:
        return ""
    return s.lstrip("0").zfill(8)


def cislo(s: str) -> float | None:
    """Převede částku ze SAP formátu. Prázdno je None, ne nula.

    Záporné hodnoty mají minus **za** číslem (`1551157.54-`), jak je v SAP
    zvykem. Kdo to přehlédne, dostane všechny schodky jako přebytky.
    """
    s = (s or "").strip().strip('"')
    if not s:
        return None
    zaporne = s.endswith("-")
    if zaporne:
        s = s[:-1].strip()
    try:
        v = float(s.replace(",", "."))
    except ValueError:
        return None
    return -v if zaporne else v


def _kody_sloupcu(hlavicka: str) -> list[str]:
    """Z hlavičky extraktu vytáhne kódy sloupců.

    Sloupec se ve starších ročnících jmenuje `ZC_ICO:ZC_ICO`, v novějších
    před kód přibyl uvozovkami obalený český popisek a prefix `/BIC/`. Kód
    je vždy až za poslední dvojtečkou; popisky se mezi lety mění a **nesmí
    se na ně vázat** (v roce 2010 tam nejsou vůbec).
    """
    return [c.rsplit(":", 1)[-1].strip().strip('"') for c in hlavicka.split(";")]


def cti_extrakt(zip_path: Path, vykaz: Vykaz, ica: set[str],
                log: Log) -> tuple[dict[str, list[dict]], dict]:
    """Projde ZIP a vybere řádky sledovaných subjektů.

    Čte **proudově** — největší soubor (FINM201) má rozbalený 126 MB
    a v paměti nemá co dělat.

    Vrací dvojici (oddíly, popis toho, co se v extraktu potkalo). Druhá
    část se ukládá k datům, aby bylo vidět, které tabulky se vynechaly —
    mlčky zahozený řádek se od neexistujícího řádku jinak nepozná.
    """
    vysledek: dict[str, list[dict]] = {}
    nezname_tabulky: set[str] = set()
    kody_vykazu: set[str] = set()

    with zipfile.ZipFile(zip_path) as z:
        for clen in z.namelist():
            if not clen.lower().endswith(".csv"):
                continue
            with z.open(clen) as raw:
                proud = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
                cteni = csv.reader(proud, delimiter=";")
                try:
                    hlavicka = next(cteni)
                except StopIteration:
                    continue
                kody = _kody_sloupcu(";".join(hlavicka))
                try:
                    i_ico = kody.index("ZC_ICO")
                    i_tab = kody.index("ZC_VTAB")
                    i_vyk = kody.index("ZC_VYKAZ")
                except ValueError:
                    # Extrakt od roku 2026 vozí i souhrny za kraj a za celou
                    # republiku — ty IČO nemají a nás nezajímají.
                    log.info(f"{zip_path.name}/{clen}: hlavička bez IČO nebo výkazu, "
                             "přeskakuji (nejspíš celostátní souhrn)")
                    continue

                # Předpočítat pozice sloupců, ať se to nedělá pro každý řádek.
                pozice_klice = [(kody.index(k), n) for k, n in vykaz.klice.items() if k in kody]
                pozice_hodnot = [(kody.index(k), n) for k, n in vykaz.hodnoty.items() if k in kody]

                for radek in cteni:
                    if len(radek) <= i_ico:
                        continue
                    ico = normalizuj_ico(radek[i_ico])
                    if ico not in ica:
                        continue
                    tab = (radek[i_tab] or "").strip()
                    kod_vykazu = (radek[i_vyk] or "").strip()
                    kody_vykazu.add(kod_vykazu)
                    oddil = vykaz.tabulky.get((kod_vykazu, tab))
                    if oddil is None:
                        nezname_tabulky.add(f"{kod_vykazu}/{tab}")
                        continue
                    zaznam = {"ico": ico}
                    for i, jmeno in pozice_klice:
                        if i < len(radek):
                            hodnota = (radek[i] or "").strip()
                            if hodnota:
                                zaznam[jmeno] = hodnota
                    for i, jmeno in pozice_hodnot:
                        if i < len(radek):
                            zaznam[jmeno] = cislo(radek[i])
                    vysledek.setdefault(oddil, []).append(zaznam)

    if nezname_tabulky:
        # Není to chyba — extrakt vozí i tabulky, které nesbíráme (účelové
        # znaky, EDS/SMVS…). Zapisuje se, ať je vidět, co se vynechalo.
        log.info(f"{zip_path.name}: nesbírané tabulky {sorted(nezname_tabulky)}")
    return vysledek, {
        "kody_vykazu": sorted(kody_vykazu),
        "nesbirane_tabulky": sorted(nezname_tabulky),
    }


# --------------------------------------------------------------------------
# Číselníky
# --------------------------------------------------------------------------

def _cti_ciselnik(url: str) -> list[dict]:
    txt = fetch(url, max_age=604_800)
    cteni = csv.reader(io.StringIO(txt), delimiter=";")
    hlavicka = next(cteni)
    # Sloupce se jmenují `/BIC/ZC_TRIDA Třída` — kód je první slovo.
    kody = [h.strip().strip('"').split(" ", 1)[0].rsplit("/", 1)[-1] for h in hlavicka]
    return [dict(zip(kody, r)) for r in cteni if r]


def stahni_ciselniky(katalog: list[str], log: Log) -> dict:
    """Stáhne číselníky a uloží z nich jen platné názvy kódů.

    Číselníky vozí historii platnosti (`DATEFROM`/`DATETO`). Ukládá se
    poslední platné znění a k němu rozsah platnosti, aby šlo poznat, že
    kód `1111` se v roce 2025 přejmenoval — a nevypadalo to jako chyba.
    """
    podle_nazvu = {_nazev_sady(i): i for i in katalog}
    hotovo = {}

    for nas_kod, (sada, fmt) in CISELNIKY.items():
        iri = podle_nazvu.get(sada)
        if not iri:
            raise ZdrojSelhal(f"číselník {sada} v katalogu MF není")
        url = soubor_ke_stazeni(popis_sady(iri), fmt)
        if not url:
            raise ZdrojSelhal(f"číselník {sada}: v katalogu chybí soubor formátu {fmt}")
        radky = _cti_ciselnik(url)

        if nas_kod == "paragrafy":
            polozky = _sbal(radky, "FUNC_AREA", ["ZC_SKUP", "ZC_ODD", "ZC_PODODD"])
        elif nas_kod == "polozky":
            polozky = _sbal(radky, "ZCMMT_ITM", ["ZC_TRIDA", "ZC_SES", "ZC_PODSES"])
        else:
            polozky = _sbal_polvyk(radky)

        hotovo[nas_kod] = {
            "zdroj": url,
            "sada": iri,
            "polozek": len(polozky),
            "polozky": polozky,
        }
        log.info(f"číselník {nas_kod}: {len(polozky)} kódů")

    for nas_kod, obsah in hotovo.items():
        uloz(f"{VYSTUP}/ciselniky/{nas_kod}.json", obsah)
    return hotovo


def _sbal(radky: list[dict], klic: str, doplnky: list[str]) -> dict:
    """Z číselníku s historií udělá {kód: {nazev, platnost_od, platnost_do}}."""
    out: dict[str, dict] = {}
    for r in radky:
        kod = (r.get(klic) or "").strip()
        if not kod:
            continue
        od, do = (r.get("DATEFROM") or "").strip(), (r.get("DATETO") or "").strip()
        stavajici = out.get(kod)
        if stavajici and stavajici["platnost_do"] >= do:
            continue
        zaznam = {
            "nazev": (r.get("TXTXL") or "").strip(),
            "platnost_od": od,
            "platnost_do": do,
        }
        for d in doplnky:
            hodnota = (r.get(d) or "").strip()
            zaznam[d.lower().replace("zc_", "")] = hodnota or None
        out[kod] = zaznam
    return out


def _sbal_polvyk(radky: list[dict]) -> dict:
    """Položky výkazu jsou jednoznačné až trojicí výkaz + tabulka + položka."""
    out: dict[str, dict] = {}
    for r in radky:
        vykaz = (r.get("ZC_VYKAZ") or "").strip()
        tab = (r.get("ZC_VTAB") or "").strip()
        pol = (r.get("ZC_POLVYK") or "").strip()
        if not (vykaz and tab and pol):
            continue
        kod = f"{vykaz}/{tab}/{pol}"
        do = (r.get("DATETO") or "").strip()
        if kod in out and out[kod]["platnost_do"] >= do:
            continue
        out[kod] = {
            "nazev": (r.get("TXTXL") or "").strip(),
            "cislo_polozky": (r.get("ZC_CISPOL") or "").strip() or None,
            "platnost_od": (r.get("DATEFROM") or "").strip(),
            "platnost_do": do,
        }
    return out


# --------------------------------------------------------------------------
# Hlavní běh
# --------------------------------------------------------------------------

def zpracuj_vykaz(vykaz: Vykaz, katalog: list[str], subjekty: dict[str, dict],
                  log: Log, vse_obdobi: bool) -> list[dict]:
    sady = sady_vykazu(katalog, vykaz)
    if not sady:
        raise ZdrojSelhal(f"v katalogu MF nejsou žádné sady výkazu {vykaz.kod}")
    vybrane = vyber_obdobi(sady, vse_obdobi)
    log.info(f"{vykaz.kod}: v katalogu {len(sady)} období, beru {len(vybrane)}")

    ica = set(subjekty)
    prehled = []

    for rok, mesic, iri in vybrane:
        nazev_sady = _nazev_sady(iri)
        detail = popis_sady(iri)
        url = soubor_ke_stazeni(detail, "CSV")
        if not url:
            log.chyba(f"{nazev_sady}: v katalogu není CSV distribuce")
            continue

        cesta = _stahni(url, f"{nazev_sady}.zip", log)
        oddily, meta = cti_extrakt(cesta, vykaz, ica, log)

        nalezene = {z["ico"] for radky in oddily.values() for z in radky}
        nalezena_ica = sorted(nalezene)
        radku = sum(len(v) for v in oddily.values())

        obsah = {
            "vykaz": vykaz.kod,
            "nazev_vykazu": vykaz.nazev,
            "popis": vykaz.popis,
            "rok": rok,
            "mesic": mesic,
            "obdobi": f"{rok}-{mesic:02d}",
            # Prosinec je konečné roční číslo; cokoliv jiného je stav
            # k danému měsíci a do roční osy patří jen s tímhle příznakem.
            "koncove": mesic == 12,
            "jednotka": "CZK",
            "poznamka_jednotka": (
                "Částky jsou v celých korunách. Ověřeno proti usnesení "
                "zastupitelstva: schválené výdaje města 2019 = 397 951 000 Kč."
            ),
            "zdroj": {
                "sada": iri,
                "nazev_sady": (detail.get("název") or {}).get("cs"),
                "soubor": url,
                "katalog": KATALOG,
                "staženo": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            },
            "subjekty_v_datech": [
                {"ico": i, "nazev": subjekty[i]["nazev"]} for i in nalezena_ica
            ],
            # Subjekty, které výkaz nepodávají. Prázdno není totéž co neznámo:
            # tohle je ověřená nepřítomnost ve zdroji, ne chyba stahování.
            "subjekty_bez_dat": [
                {"ico": i, "nazev": s["nazev"]}
                for i, s in sorted(subjekty.items()) if i not in nalezene
            ],
            "radku": radku,
            # Kód výkazu ve zdroji. Od roku 2026 se u FIN 2-12 M změnil
            # z 051 na 063 a s ním i členění tabulek — přehledy podle toho
            # musí poznat, že souhrnná tabulka v novějších datech není.
            "kody_vykazu": meta["kody_vykazu"],
            "nesbirane_tabulky": meta["nesbirane_tabulky"],
            "oddily": oddily,
        }
        uloz(f"{VYSTUP}/{vykaz.kod}/{rok}-{mesic:02d}.json", obsah)
        log.pricti()
        log.info(f"{vykaz.kod} {rok}-{mesic:02d}: {radku} řádků, "
                 f"{len(nalezena_ica)} subjektů")
        prehled.append({
            "rok": rok, "mesic": mesic, "koncove": mesic == 12,
            "radku": radku, "subjektu": len(nalezena_ica),
            "soubor": f"{VYSTUP}/{vykaz.kod}/{rok}-{mesic:02d}.json",
            "zdroj": url,
        })

    return prehled


def bez_dat_upozorneni(prehled: dict) -> list[str]:
    """Poznámky o tom, co ve zdroji chybí — ať se to nemusí dohadovat z dat."""
    poznamky = []
    if "fin212m" in prehled:
        poznamky.append(
            "FIN 2-12 M podávají jen územní samosprávné celky, takže rozpočet "
            "v datech má pouze město (00254061). Chybějící rozpočty "
            "příspěvkových organizací nejsou mezera ve sběru — ty se "
            "vykazují rozvahou a výkazem zisku a ztráty."
        )
    return poznamky


def main() -> int:
    ap = argparse.ArgumentParser(description="Monitor státní pokladny — rozpočet a výkazy")
    ap.add_argument("--katalog", action="store_true",
                    help="jen vypsat, co katalog MF nabízí, nic nestahovat")
    ap.add_argument("--vykaz", choices=sorted(VYKAZY), action="append",
                    help="zpracovat jen vybraný výkaz (lze opakovat)")
    ap.add_argument("--vse-obdobi", action="store_true",
                    help="stáhnout i mezitímní čtvrtletí, ne jen roční závěrky")
    ap.add_argument("--bez-ciselniku", action="store_true",
                    help="přeskočit stahování číselníků")
    args = ap.parse_args()

    log = Log("monitor")
    try:
        katalog = nacti_katalog()
        log.info(f"katalog MF: {len(katalog)} datových sad")

        if args.katalog:
            for kod, v in VYKAZY.items():
                sady = sady_vykazu(katalog, v)
                obdobi = [f"{r}-{m:02d}" for r, m, _ in sady]
                print(f"\n{kod}: {v.nazev}")
                print(f"  období ({len(obdobi)}): {', '.join(obdobi)}")
            return 0

        subjekty = {s["ico"]: s for s in sledovane_subjekty()}
        log.info(f"sledovaných subjektů: {len(subjekty)}")

        ciselniky = {} if args.bez_ciselniku else stahni_ciselniky(katalog, log)

        vybrane = args.vykaz or list(VYKAZY)
        prehled = {}
        for kod in vybrane:
            prehled[kod] = zpracuj_vykaz(VYKAZY[kod], katalog, subjekty, log,
                                         args.vse_obdobi)

        uloz(f"{VYSTUP}/zdroje.json", {
            "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "zdroj": {
                "nazev": "MONITOR státní pokladny (Ministerstvo financí)",
                "katalog": KATALOG,
                "aplikace": "https://monitor.statnipokladna.gov.cz/",
                "nkod": "https://data.gov.cz/datová-sada?iri=https%3A%2F%2Fdata.gov.cz"
                        "%2Fzdroj%2Fdatové-sady%2F00006947%2Fc40985841e83510d2044b5d37d1f3849",
                "licence": "https://monitor.statnipokladna.gov.cz/datovy-katalog/licence",
            },
            "jednotka": "CZK",
            "poznamka_jednotka": (
                "Všechny částky jsou v celých korunách, NE v tisících. "
                "Ověřeno proti usnesení zastupitelstva (schválené výdaje "
                "města 2019 = 397 951 000 Kč)."
            ),
            "sledovanych_subjektu": len(subjekty),
            "vykazy": {
                kod: {
                    "nazev": VYKAZY[kod].nazev,
                    "popis": VYKAZY[kod].popis,
                    "obdobi": p,
                } for kod, p in prehled.items()
            },
            "ciselniky": {k: {"zdroj": v["zdroj"], "polozek": v["polozek"]}
                          for k, v in ciselniky.items()},
            "poznamky": bez_dat_upozorneni(prehled),
        })
    except ZdrojSelhal as e:
        log.chyba(str(e))
        log.uzavri()
        return 1

    vysledek = log.uzavri()
    return 0 if vysledek["uspech"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
