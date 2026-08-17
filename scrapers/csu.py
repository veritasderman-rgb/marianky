#!/usr/bin/env python3
"""O1 — statistika města z otevřených dat ČSÚ.

Zdroj: katalog otevřených dat ČSÚ, `https://vdb.czso.cz/pll/eweb/lkod_ld.seznam`
(seznam datových sad v CSV) → popis sady ve formátu DCAT-AP-CZ → adresa
souboru ke stažení. Nesaháme na adresy souborů natvrdo: ČSÚ je při každé
aktualizaci mění (v názvu mají datum vydání), zatímco **identifikátor sady
je stálý**. Proto se v konfiguraci drží identifikátor a adresa se dohledá.

Datové sady jsou celorepublikové a v „dlouhém" tvaru — jeden řádek je
jedna hodnota jednoho ukazatele za jedno území a období. Sbírá se z nich
jen obec 554642, a to **proudově**: rozbalený soubor s obyvatelstvem má
226 MB, do paměti se nevejde a na disk ho rozbalovat nemá smysl.

Tři věci, které nejsou samozřejmé
--------------------------------
1. **`csu.gov.cz` velké soubory usekává.** Opakovaně: z 20,7 MB dorazí
   jednou 1,3 MB, podruhé 5,2 MB, pokaždé s HTTP 200. Není to výpadek —
   je to náš síťový průchod. Řeší to `_stahni()`: ptá se na
   `Content-Length` a dotahuje zbytek přes hlavičku `Range`, dokud soubor
   nesedí na velikost. Bez toho by ZIP nešel otevřít a data by chyběla
   „bez příčiny".

2. **Prázdná hodnota není nula.** ČSÚ u ubytovacích kapacit v malých
   kategoriích hodnotu neuvádí a označí ji `duvernost=duverny` — je to
   *utajený* údaj, ne nula. Ukládá se `hodnota: null` a `duverne: true`,
   aby graf nemohl nakreslit propad tam, kde jen nesmíme vidět číslo.

3. **Rezidenti a nerezidenti mají číselníkové kódy, ne názvy.** V sadě
   návštěvnosti je `uzemiz_kod` 203 (Česko = rezidenti), 17 (zahraničí =
   nerezidenti) a prázdno (celkem). Ověřeno porovnáním lázeňských měst
   s vnitrozemskými (viz `ZEME`).

Spuštění:
    python3 scrapers/csu.py                 # vše
    python3 scrapers/csu.py --sada obyvatelstvo
    python3 scrapers/csu.py --prehled       # jen co katalog nabízí
"""
from __future__ import annotations

import argparse
import csv
import hashlib
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
    DATA,
    UA,
    Log,
    ZdrojSelhal,
    fetch,
    uloz,
)
# Odstup mezi požadavky na stejný server drží jádro přes soubor se značkou.
# `_stahni()` níž nemůže použít `core.fetch()` (neumí navazovat přerušené
# stahování), ale tempo držet musí — proto si bere tenhle pomocník.
from lib.core import _pockej_na_rade  # noqa: E402

OBEC = "554642"
OBEC_NAZEV = "Mariánské Lázně"
OKRES = "CZ0411"
KRAJ = "CZ041"

KATALOG = "https://vdb.czso.cz/pll/eweb/lkod_ld.seznam"
POPIS_SADY = "https://vdb.czso.cz/pll/eweb/lkod_ld.datova_sada?nazev={}"
VYSTUP = "opendata/csu"
STAHOVANE = CACHE / "csu"

# Kódy území v sadě návštěvnosti ubytovacích zařízení. Sada je nemá popsané
# textem, takže se překládají tady. Ověřeno srovnáním: v Mariánských Lázních
# a Karlových Varech převažuje 17, ve Zlíně, Pardubicích a Havířově 203 —
# což odpovídá tomu, že 17 jsou zahraniční hosté.
ZEME = {"203": "rezidenti", "17": "nerezidenti", "": "celkem"}


# --------------------------------------------------------------------------
# Konfigurace sad
# --------------------------------------------------------------------------

@dataclass
class Sada:
    kod: str                        # náš kód, podle něj se jmenuje výstup
    nazev: str
    vzor_id: str                    # regulární výraz na dataset_id v katalogu
    perioda: str                    # 'rok' | 'mesic' | 'scitani'
    popis: str = ""
    # Ukazatele, které se propíšou do plochých časových řad k vykreslení.
    # {kód naší řady: (název ukazatele ve zdroji, filtr členění)}
    rady: dict[str, tuple[str, dict]] = field(default_factory=dict)
    # Některé sady vozí jen číselný kód ukazatele (`stapro_kod`) bez textu —
    # sada 130149 má sloupec `stapro_txt` úplně vynechaný. Pak se název bere
    # odsud. Je to překlad číselníku ČSÚ, ne domýšlení dat.
    kody_ukazatelu: dict[str, str] = field(default_factory=dict)


SADY: list[Sada] = [
    Sada(
        kod="obyvatelstvo",
        nazev="Obyvatelstvo podle pohlaví a základních věkových skupin",
        vzor_id=r"^130149$",
        perioda="rok",
        popis="Stav obyvatel k 31. 12. od roku 2000, v členění na pohlaví "
              "a věkové skupiny 0–14 / 15–64 / 65 a více.",
        kody_ukazatelu={"2406": "Počet obyvatel k 31. 12."},
        rady={
            "obyvatel_celkem": ("Počet obyvatel k 31. 12.", {"pohlavi": None, "vek": None}),
            "obyvatel_muzi": ("Počet obyvatel k 31. 12.", {"pohlavi": "muž", "vek": None}),
            "obyvatel_zeny": ("Počet obyvatel k 31. 12.", {"pohlavi": "žena", "vek": None}),
            "obyvatel_0_14": ("Počet obyvatel k 31. 12.", {"pohlavi": None, "vek": "0 až 14"}),
            "obyvatel_15_64": ("Počet obyvatel k 31. 12.", {"pohlavi": None, "vek": "15 až 64"}),
            "obyvatel_65_vic": ("Počet obyvatel k 31. 12.", {"pohlavi": None, "vek": "65 a více"}),
        },
    ),
    Sada(
        kod="pohyb_obyvatel",
        nazev="Pohyb obyvatel",
        vzor_id=r"^130141(r\d+)?$",
        perioda="rok",
        popis="Narození, zemřelí, stěhování, sňatky a rozvody. Katalog ČSÚ "
              "vede tuhle sadu po ročnících a nejstarší zveřejněný je 2014 — "
              "starší roky v otevřených datech nejsou.",
        rady={
            "narozeni": ("Živě narození", {}),
            "zemreli": ("Zemřelí", {}),
            "pristehovali": ("Přistěhovalí", {}),
            "vystehovali": ("Vystěhovalí", {}),
            "prirozeny_prirustek": ("Přirozený přírůstek", {}),
            "migracni_saldo": ("Migrační saldo", {}),
            "celkovy_prirustek": ("Celkový přírůstek", {}),
            "snatky": ("Sňatky", {}),
            "rozvody": ("Rozvody", {}),
            "stredni_stav": ("Střední stav obyvatel", {}),
        },
    ),
    Sada(
        kod="nezamestnanost",
        nazev="Uchazeči o zaměstnání a podíl nezaměstnaných osob",
        vzor_id=r"^250169(r\d+)?$",
        perioda="mesic",
        popis="Měsíční řada podle obcí. Zdrojem čísel je Úřad práce, ČSÚ je "
              "publikuje.",
        rady={
            "podil_nezamestnanych": ("Podíl nezaměstnaných osob", {}),
            "podil_nezamestnanych_zeny": ("Podíl nezaměstnaných osob - ženy", {}),
            "uchazeci": ("Uchazeči o zaměstnání", {}),
            "uchazeci_dosazitelni": ("Uchazeči o zaměstnání dosažitelní", {}),
            "uchazecky_dosazitelne": ("Uchazeči o zaměstnání dosažitelní - ženy", {}),
        },
    ),
    Sada(
        kod="cestovni_ruch",
        nazev="Návštěvnost hromadných ubytovacích zařízení",
        vzor_id=r"^020050$",
        perioda="rok",
        popis="Hosté a přenocování od roku 2012, zvlášť za rezidenty "
              "a zahraniční hosty. U lázeňského města je to hlavní ukazatel "
              "jeho hlavního odvětví.",
        rady={
            "hoste_celkem": ("Počet turistů", {"zeme": "celkem"}),
            "hoste_rezidenti": ("Počet turistů", {"zeme": "rezidenti"}),
            "hoste_nerezidenti": ("Počet turistů", {"zeme": "nerezidenti"}),
            "prenocovani_celkem": ("Počet přenocování turistů", {"zeme": "celkem"}),
            "prenocovani_rezidenti": ("Počet přenocování turistů", {"zeme": "rezidenti"}),
            "prenocovani_nerezidenti": ("Počet přenocování turistů", {"zeme": "nerezidenti"}),
        },
    ),
    Sada(
        kod="ubytovaci_kapacity",
        nazev="Kapacity hromadných ubytovacích zařízení",
        vzor_id=r"^020055$",
        perioda="rok",
        popis="Počet zařízení, pokojů a lůžek podle kategorie ubytování. "
              "U menších kategorií ČSÚ hodnotu tají (`duverne: true`).",
        rady={
            "ubytovacich_zarizeni": ("Počet ubytovacích zařízení",
                                     {"kategorie": "Hromadná ubytovací zařízení"}),
            "pokoju_prumer": ("Průměrný počet pokojů v ubytovacím zařízení k dispozici",
                              {"kategorie": "Hromadná ubytovací zařízení"}),
            "luzek_prumer": ("Průměrný počet lůžek v ubytovacím zařízení k dispozici",
                             {"kategorie": "Hromadná ubytovací zařízení"}),
        },
    ),
    Sada(
        kod="dokoncene_byty",
        nazev="Dokončené byty v obcích",
        vzor_id=r"^200068$",
        perioda="rok",
        popis="Kolik bytů se ve městě ročně dostavělo, od roku 1997.",
        rady={
            "byty_celkem": ("Počet dokončených bytů", {"typ": None}),
            "byty_rodinne_domy": ("Počet dokončených bytů", {"typ": "Rodinný dům"}),
            "byty_bytove_domy": ("Počet dokončených bytů", {"typ": "Bytový dům"}),
        },
    ),
    Sada(
        kod="scitani",
        nazev="Obyvatelstvo a domy v obcích podle výsledků sčítání od roku 1869",
        vzor_id=r"^170240-17$",
        perioda="scitani",
        popis="Nejdelší řada, jakou o městě máme: obyvatelé a domy při každém "
              "sčítání od roku 1869. Body jsou nepravidelné — sčítání se "
              "nekonala po stejných odstupech a graf to musí přiznat.",
        rady={
            "obyvatel_scitani": ("Počet obyvatel s trvalým nebo dlouhodobým pobytem", {}),
            "domu_scitani": ("Počet domů", {}),
        },
    ),
    Sada(
        kod="domy_byty_2021",
        nazev="Sčítání 2021 — domy a byty",
        vzor_id=r"^sldb2021_(domy_obydlen_druh|byty_obydlenost)$",
        perioda="scitani",
        popis="Kolik má město domů a bytů a kolik z nich je obydlených. "
              "Doplňuje řadu ze sčítání od roku 1869, která končí rokem 2011. "
              "Podíl neobydlených bytů je u lázeňského města samostatné téma.",
        rady={
            "domy_2021": ("Počet domů", {"obydlen": None, "druh_domu": None}),
            "domy_obydlene_2021": ("Počet domů",
                                   {"obydlen": "Obvykle obydlen", "druh_domu": None}),
            "domy_neobydlene_2021": ("Počet domů",
                                     {"obydlen": "Obvykle neobydlen", "druh_domu": None}),
            "byty_2021": ("Počet bytů", {"obydlenost": None}),
            "byty_obydlene_2021": ("Počet bytů", {"obydlenost": "obvykle obydlen"}),
            "byty_neobydlene_2021": ("Počet bytů", {"obydlenost": "obvykle neobydlen"}),
        },
    ),
    Sada(
        kod="socialni_sluzby",
        nazev="Zařízení sociálních služeb podle obcí",
        vzor_id=r"^190037$",
        perioda="rok",
        popis="Počet zařízení a míst v nich, po druzích služby.",
    ),
]


# --------------------------------------------------------------------------
# Stahování, které přežije usekané spojení
# --------------------------------------------------------------------------

def _hlavicky(extra: dict | None = None) -> dict[str, str]:
    h = {"User-Agent": UA, "Accept-Language": "cs,en;q=0.8"}
    if extra:
        h.update(extra)
    return h


def _ocekavana_velikost(url: str) -> int:
    """Kolik bajtů má soubor mít.

    Nejdřív se ptáme metodou HEAD. Část adres ČSÚ (nezabalená CSV) na HEAD
    délku neposílá, ale na GET ano — tak se pošle GET a odpověď se po
    přečtení hlaviček zavře, aniž by se tělo stahovalo. Bez znalosti
    velikosti by nešlo poznat useknutý přenos od hotového a už stažený
    soubor by se navazoval donekonečna.
    """
    for pokus in range(8):
        metoda = "HEAD" if pokus % 2 == 0 else "GET"
        req = urllib.request.Request(url, headers=_hlavicky(), method=metoda)
        _pockej_na_rade(urlparse(url).netloc)
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                delka = int(r.headers.get("Content-Length") or 0)
        except Exception:  # noqa: BLE001 — zkoušíme dál, síť sem tam vypadne
            delka = 0
        if delka:
            return delka
        time.sleep(min(2 ** (pokus // 2), 8))
    return 0


def _stahni(url: str, jmeno: str, log: Log, pokusu: int = 60) -> Path:
    """Stáhne velký soubor a **dotáhne ho, i když spojení spadne uprostřed**.

    `csu.gov.cz` přes náš síťový průchod pravidelně ukončí přenos dřív, a to
    s návratovým kódem 200 — takže se to netváří jako chyba (z 20,7MB ZIPu
    dorazilo v jednom pokusu 1,3 MB, v druhém 5,2 MB). Jediná obrana je
    porovnat velikost s `Content-Length` a chybějící část si vyžádat
    hlavičkou `Range`. Když se soubor nepodaří dotáhnout, letí `ZdrojSelhal`
    — nedostažený soubor se nikdy nepředstírá jako hotový.
    """
    STAHOVANE.mkdir(parents=True, exist_ok=True)
    cil = STAHOVANE / jmeno
    celkem = _ocekavana_velikost(url)
    if not celkem:
        raise ZdrojSelhal(f"{url}: server neuvedl velikost, nelze ověřit úplnost stažení")
    if cil.exists() and cil.stat().st_size >= celkem:
        return cil

    hlaseno = naprazdno = 0
    for _ in range(pokusu):
        mam = cil.stat().st_size if cil.exists() else 0
        if mam >= celkem:
            return cil
        if mam and not hlaseno:
            log.info(f"{jmeno}: spojení useknuto na {mam}/{celkem} B, navazuji")
            hlaseno = 1
        req = urllib.request.Request(
            url, headers=_hlavicky({"Range": f"bytes={mam}-"} if mam else None))
        try:
            _pockej_na_rade(urlparse(url).netloc)
            # Krátký časový limit schválně: spojení sem tam neskončí, jen
            # umlkne. Čekat na něj tři minuty je dražší než začít znovu —
            # rozdělaný soubor se stejně jen doplní.
            with urllib.request.urlopen(req, timeout=45) as r:
                rezim = "ab" if (mam and r.status == 206) else "wb"
                with open(cil, rezim) as f:
                    while True:
                        blok = r.read(1 << 20)
                        if not blok:
                            break
                        f.write(blok)
        except Exception:  # noqa: BLE001 — opakujeme na čemkoliv síťovém
            pass
        # Čeká se, jen když pokus nepřinesl ani bajt. Useknuté spojení není
        # zahlcený server — couvat před ním by stahování jen protahovalo.
        pote = cil.stat().st_size if cil.exists() else 0
        naprazdno = naprazdno + 1 if pote <= mam else 0
        if naprazdno:
            time.sleep(min(2 ** naprazdno, 15))
    mam = cil.stat().st_size if cil.exists() else 0
    if mam < celkem:
        raise ZdrojSelhal(f"{url}: stáhlo se jen {mam} z {celkem} B ani na {pokusu} pokusů")
    return cil


def _cti_proud(fh):
    """Přečte otevřený textový proud jako CSV a sám pozná oddělovač.

    Většina souborů ČSÚ má čárku, ale ne všechny — sada nezaměstnanosti za
    rok 2015 je se středníkem. Bez rozpoznání by se celý řádek načetl jako
    jeden sloupec, obec by se nenašla a rok 2015 by z řady tiše vypadl.
    """
    prvni = fh.readline()
    if not prvni:
        return
    oddelovac = ";" if prvni.count(";") > prvni.count(",") else ","
    hlavicka = next(csv.reader([prvni], delimiter=oddelovac))
    yield from csv.DictReader(fh, fieldnames=hlavicka, delimiter=oddelovac)


def _radky_csv(cesta: Path):
    """Projde CSV (i zabalené v ZIPu) proudově, řádek po řádku.

    Rozbalený soubor s obyvatelstvem má 226 MB — načítat ho celý by bylo
    plýtvání i tehdy, kdyby se to vešlo.
    """
    if cesta.suffix.lower() == ".zip":
        z = zipfile.ZipFile(cesta)
        jmena = [i.filename for i in z.infolist() if i.filename.lower().endswith(".csv")]
        if not jmena:
            raise ZdrojSelhal(f"{cesta.name}: v archivu není žádné CSV")
        for jmeno in jmena:
            with z.open(jmeno) as fh:
                yield from _cti_proud(io.TextIOWrapper(fh, encoding="utf-8-sig"))
    else:
        with open(cesta, encoding="utf-8-sig", newline="") as fh:
            yield from _cti_proud(fh)


# --------------------------------------------------------------------------
# Katalog
# --------------------------------------------------------------------------

def katalog(log: Log) -> list[dict]:
    text = fetch(KATALOG, max_age=7 * 86_400)
    assert isinstance(text, str)
    radky = list(csv.DictReader(io.StringIO(text)))
    log.info(f"katalog ČSÚ nabízí {len(radky)} datových sad")
    return radky


def distribuce(zaznam: dict) -> list[dict]:
    """Adresy souborů ke stažení pro jednu datovou sadu (DCAT-AP-CZ)."""
    popis = fetch(zaznam["dataset_iri"], max_age=7 * 86_400)
    assert isinstance(popis, str)
    try:
        dcat = json.loads(popis)
    except json.JSONDecodeError as e:
        raise ZdrojSelhal(f"{zaznam['dataset_id']}: popis sady není JSON ({e})")
    out = []
    for d in dcat.get("distribuce", []):
        url = d.get("soubor_ke_stažení") or d.get("přístupové_url")
        if not url:
            continue
        out.append({
            "nazev": (d.get("název") or {}).get("cs"),
            "url": url,
        })
    return out


def sady_z_katalogu(sada: Sada, radky: list[dict]) -> list[dict]:
    vzor = re.compile(sada.vzor_id)
    return sorted((r for r in radky if vzor.match(r["dataset_id"])),
                  key=lambda r: r["dataset_id"])


# --------------------------------------------------------------------------
# Převod dlouhého tvaru ČSÚ na naše záznamy
# --------------------------------------------------------------------------

# Názvy sloupců se mezi sadami ČSÚ liší; sjednocují se až tady.
SLOUPCE_UZEMI = ("uzemi_kod", "vuzemi_kod", "obec_kod")
SLOUPCE_UKAZATELE = ("stapro_txt", "vuk_text", "ukaz_txt")
CLENENI = {
    "pohlavi": "pohlavi_txt",
    "vek": "vek_txt",
    "kategorie": "kat_txt",
    "typ": "tb_txt",
    "druh": "dsz_txt",              # druh sociální služby
    "obydlenost": "obydlenost_txt",  # sčítání 2021 — byty
    "obydlen": "obydlen_txt",        # sčítání 2021 — domy
    "druh_domu": "druh_txt",
}


def _je_nase_obec(r: dict) -> bool:
    return any((r.get(s) or "").strip() == OBEC for s in SLOUPCE_UZEMI)


def _nazev_ukazatele(text: str) -> tuple[str, str | None]:
    """Sjednotí zápis názvu ukazatele a oddělí jednotku.

    ČSÚ mezi ročníky téže sady mění drobnosti: „Uchazeči o zaměstnání
    dosažitelní" má v jednom roce dvě mezery, „Podíl nezaměstnaných osob"
    má v jednom roce na konci „(%)" a v jiném ne. Bez sjednocení by se
    z jedné časové řady staly dvě, každá s jinou částí let — a graf by
    ukázal přerušený vývoj tam, kde se jen přepsala hlavička.
    """
    t = " ".join((text or "").split())
    jednotka = None
    m = re.search(r"\s*\((%|tis\.[^)]*|mil\.[^)]*)\)$", t)
    if m:
        jednotka = m.group(1)
        t = t[: m.start()].strip()
    return t, jednotka


def _hodnota(r: dict) -> tuple[float | int | None, bool]:
    """Vrátí (hodnota, je_důvěrná). Prázdno je None, nikdy nula."""
    syrova = (r.get("hodnota") or "").strip()
    duverne = (r.get("duvernost") or "").strip().lower() == "duverny"
    if syrova == "":
        return None, duverne
    try:
        if re.fullmatch(r"-?\d+", syrova):
            return int(syrova), duverne
        return float(syrova.replace(",", ".")), duverne
    except ValueError:
        return None, duverne


def _obdobi(r: dict, perioda: str) -> str | None:
    if perioda == "mesic":
        rok, mesic = (r.get("rok") or "").strip(), (r.get("mesic") or "").strip()
        if rok and mesic:
            return f"{rok}-{int(mesic):02d}"
        obd = (r.get("obdobi") or "").strip()
        return f"{obd[:4]}-{obd[4:6]}" if len(obd) >= 6 else None
    if perioda == "scitani":
        for s in ("datum", "sldb_datum", "rok", "sldb_rok"):
            v = (r.get(s) or "").strip()
            if v:
                return v
        return None
    rok = (r.get("rok") or "").strip()
    if rok:
        return rok
    for s in ("obdobi", "casref_do", "casref_od"):
        v = (r.get(s) or "").strip()
        if len(v) >= 4 and v[:4].isdigit():
            return v[:4]
    return None


def zaznamy(cesta: Path, sada: Sada) -> list[dict]:
    """Přefiltruje celorepublikový soubor na naši obec a převede na záznamy."""
    out: list[dict] = []
    for r in _radky_csv(cesta):
        if not _je_nase_obec(r):
            continue
        ukazatel = next(((r.get(s) or "").strip() for s in SLOUPCE_UKAZATELE
                         if (r.get(s) or "").strip()), "")
        if not ukazatel:
            kod = (r.get("stapro_kod") or r.get("vuk") or "").strip()
            ukazatel = sada.kody_ukazatelu.get(kod) or (f"ukazatel {kod}" if kod else "")
        ukazatel, jednotka = _nazev_ukazatele(ukazatel)
        hod, duverne = _hodnota(r)
        zaznam = {
            "obdobi": _obdobi(r, sada.perioda),
            "ukazatel": ukazatel,
            "jednotka": jednotka,
            "hodnota": hod,
            "duverne": duverne,
        }
        for nas, jejich in CLENENI.items():
            v = (r.get(jejich) or "").strip()
            if v:
                zaznam[nas] = v
        if "uzemiz_kod" in r:
            zaznam["zeme"] = ZEME.get((r.get("uzemiz_kod") or "").strip(),
                                      (r.get("uzemiz_kod") or "").strip())
        if (r.get("rok") or "").strip() and sada.perioda == "scitani":
            zaznam["rok"] = int(r["rok"])
        out.append(zaznam)
    out.sort(key=lambda z: (z["obdobi"] or "", z["ukazatel"], json.dumps(z, sort_keys=True)))
    return out


def _sedi(z: dict, filtr: dict) -> bool:
    """Odpovídá záznam filtru řady? `None` znamená „bez tohohle členění"."""
    for klic, chtene in filtr.items():
        mam = z.get(klic)
        if chtene is None:
            if mam is not None:
                return False
        elif mam != chtene:
            return False
    return True


def rady_ze_zaznamu(sada: Sada, zaz: list[dict]) -> list[dict]:
    """Ploché časové řady k vykreslení."""
    out = []
    for kod, (ukazatel, filtr) in sada.rady.items():
        body = [z for z in zaz if z["ukazatel"] == ukazatel and _sedi(z, filtr)]
        if not body:
            continue
        # Jedno období musí mít jednu hodnotu; kdyby jich bylo víc, filtr
        # není dost úzký a raději se to nahlásí, než aby se tiše sečetly.
        podle_obdobi: dict[str, list[dict]] = {}
        for b in body:
            podle_obdobi.setdefault(b["obdobi"], []).append(b)
        dvojznacne = sorted(o for o, v in podle_obdobi.items() if len(v) > 1)
        out.append({
            "kod": kod,
            "nazev": ukazatel,
            "jednotka": next((b.get("jednotka") for b in body if b.get("jednotka")), None),
            "clenění": {k: v for k, v in filtr.items() if v is not None} or None,
            "perioda": sada.perioda,
            "sada": sada.kod,
            "od": min(podle_obdobi),
            "do": max(podle_obdobi),
            "bodu": len(podle_obdobi),
            "dvojznacna_obdobi": dvojznacne or None,
            "body": [{"obdobi": o,
                      "hodnota": podle_obdobi[o][0]["hodnota"],
                      "duverne": podle_obdobi[o][0]["duverne"]}
                     for o in sorted(podle_obdobi)],
        })
    return out


# Součtové kontroly: {kód sady: [(celek, [části])]}. Když se rozpad nesečte
# na celek, je něco špatně v tom, jak čteme zdroj — a je lepší se to dozvědět
# hned než z grafu, který nikdo nepřepočítá.
KONTROLY: dict[str, list[tuple[str, list[str]]]] = {
    "obyvatelstvo": [
        ("obyvatel_celkem", ["obyvatel_muzi", "obyvatel_zeny"]),
        ("obyvatel_celkem", ["obyvatel_0_14", "obyvatel_15_64", "obyvatel_65_vic"]),
    ],
    "cestovni_ruch": [
        ("hoste_celkem", ["hoste_rezidenti", "hoste_nerezidenti"]),
        ("prenocovani_celkem", ["prenocovani_rezidenti", "prenocovani_nerezidenti"]),
    ],
    "dokoncene_byty": [
        # Schválně jen jako informace: kromě rodinných a bytových domů se
        # byty dokončují i v nástavbách a nebytových budovách, takže se
        # tyhle dvě položky na celek sečíst NEMUSÍ.
    ],
    "domy_byty_2021": [
        ("domy_2021", ["domy_obydlene_2021", "domy_neobydlene_2021"]),
        ("byty_2021", ["byty_obydlene_2021", "byty_neobydlene_2021"]),
    ],
}


def zkontroluj(sada: Sada, rady: list[dict]) -> list[str]:
    """Ověří součtové vztahy. Prázdný seznam znamená, že data sedí.

    Neznámá hodnota se do součtu nepočítá a kontrola se pro dané období
    přeskočí — sečíst „neznámo" jako nulu by z kontroly udělalo generátor
    falešných poplachů.
    """
    podle_kodu = {r["kod"]: {b["obdobi"]: b["hodnota"] for b in r["body"]} for r in rady}
    potize = []
    for celek, casti in KONTROLY.get(sada.kod, []):
        if celek not in podle_kodu or any(c not in podle_kodu for c in casti):
            continue
        for obdobi, hodnota in sorted(podle_kodu[celek].items()):
            dilci = [podle_kodu[c].get(obdobi) for c in casti]
            if hodnota is None or any(d is None for d in dilci):
                continue  # neznámo se nesčítá
            if abs(sum(dilci) - hodnota) > 0.5:
                potize.append(f"{sada.kod}/{obdobi}: {' + '.join(casti)} = "
                              f"{sum(dilci)} != {celek} = {hodnota}")
    return potize


def mezery(rada: dict) -> list[str]:
    """Chybějící období uvnitř řady.

    Díra v řadě je zjištění, ne detail: graf, který ji přeskočí, nakreslí
    plynulý vývoj tam, kde ve skutečnosti chybí měření. U sčítání se mezery
    nepočítají — ta se konají v nepravidelných odstupech schválně.
    """
    mam = {b["obdobi"] for b in rada["body"]}
    if rada["perioda"] == "rok":
        roky = sorted(int(o) for o in mam if o.isdigit())
        if not roky:
            return []
        return [str(r) for r in range(roky[0], roky[-1] + 1) if str(r) not in mam]
    if rada["perioda"] == "mesic":
        mesice = sorted(o for o in mam if re.fullmatch(r"\d{4}-\d{2}", o))
        if not mesice:
            return []
        zac = int(mesice[0][:4]) * 12 + int(mesice[0][5:]) - 1
        kon = int(mesice[-1][:4]) * 12 + int(mesice[-1][5:]) - 1
        vse = [f"{n // 12:04d}-{n % 12 + 1:02d}" for n in range(zac, kon + 1)]
        return [o for o in vse if o not in mam]
    return []


# --------------------------------------------------------------------------
# Sběr
# --------------------------------------------------------------------------

def zpracuj_sadu(sada: Sada, katalog_radky: list[dict], log: Log) -> dict:
    zdroje = sady_z_katalogu(sada, katalog_radky)
    if not zdroje:
        raise ZdrojSelhal(f"{sada.kod}: katalog nezná sadu podle vzoru {sada.vzor_id}")

    vsechny: list[dict] = []
    pouzite = []
    for z in zdroje:
        try:
            dists = distribuce(z)
        except ZdrojSelhal as e:
            log.chyba(f"{sada.kod}/{z['dataset_id']}: {e}")
            pouzite.append({"dataset_id": z["dataset_id"], "stav": "chybi", "duvod": str(e)})
            continue
        for d in dists:
            pripona = ".zip" if ".zip" in d["url"].lower() else ".csv"
            # Otisk adresy musí být stálý mezi běhy, jinak by se cache míjela
            # a stahovalo by se pořád dokola — vestavěný `hash()` je u řetězců
            # per proces náhodný, proto sha256.
            otisk = hashlib.sha256(d["url"].encode()).hexdigest()[:10]
            jmeno = f"{sada.kod}-{z['dataset_id']}-{otisk}{pripona}"
            try:
                cesta = _stahni(d["url"], jmeno, log)
                cast = zaznamy(cesta, sada)
            except (ZdrojSelhal, zipfile.BadZipFile) as e:
                log.chyba(f"{sada.kod}/{z['dataset_id']}: {e}")
                pouzite.append({"dataset_id": z["dataset_id"], "url": d["url"],
                                "stav": "chybi", "duvod": str(e)})
                continue
            vsechny += cast
            pouzite.append({
                "dataset_id": z["dataset_id"],
                "nazev": z["title"],
                "distribuce": d["nazev"],
                "url": d["url"],
                "dokumentace": z.get("page") or None,
                "zaznamu_pro_obec": len(cast),
                # "prazdno" = sada se stáhla, ale o naší obci v ní nic není.
                # To je jiné tvrzení než "nestáhlo se".
                "stav": "ok" if cast else "prazdno",
            })

    zaz = sorted(vsechny, key=lambda z: (z["obdobi"] or "", z["ukazatel"]))
    rady = rady_ze_zaznamu(sada, zaz)
    for r in rady:
        r["chybejici_obdobi"] = mezery(r) or None
    potize = zkontroluj(sada, rady)
    for p in potize:
        log.chyba(p)

    ukazatele = sorted({z["ukazatel"] for z in zaz})
    obdobi = sorted({z["obdobi"] for z in zaz if z["obdobi"]})
    vysledek = {
        "kod": sada.kod,
        "nazev": sada.nazev,
        "popis": sada.popis,
        "perioda": sada.perioda,
        "obec": {"kod": OBEC, "nazev": OBEC_NAZEV, "okres": OKRES, "kraj": KRAJ},
        "zdroj_katalog": KATALOG,
        "zdroje": pouzite,
        "stav": "ok" if zaz else ("prazdno" if pouzite else "chybi"),
        "od": obdobi[0] if obdobi else None,
        "do": obdobi[-1] if obdobi else None,
        "ukazatele": ukazatele,
        "zaznamu": len(zaz),
        "kontrola": {"nesrovnalosti": potize},
        "zaznamy": zaz,
        "rady": rady,
    }
    log.info(f"{sada.kod}: {len(zaz)} záznamů, {len(ukazatele)} ukazatelů, "
             f"{vysledek['od']}–{vysledek['do']}, řad {len(rady)}")
    return vysledek


def sber(vybrane: list[Sada], log: Log) -> dict:
    radky = katalog(log)
    hotove: list[dict] = []
    for sada in vybrane:
        try:
            v = zpracuj_sadu(sada, radky, log)
        except ZdrojSelhal as e:
            log.chyba(f"{sada.kod}: {e}")
            continue
        uloz(f"{VYSTUP}/sady/{sada.kod}.json", v)
        hotove.append(v)
        log.pricti(v["zaznamu"])

    # Sady z dřívějších běhů se přiberou, aby dílčí běh nezahodil zbytek.
    znam = {v["kod"] for v in hotove}
    for p in sorted((DATA / VYSTUP / "sady").glob("*.json")):
        if p.stem not in znam:
            hotove.append(json.loads(p.read_text(encoding="utf-8")))
    hotove.sort(key=lambda v: v["kod"])

    vsechny_rady = [r for v in hotove for r in v["rady"]]
    uloz(f"{VYSTUP}/casove_rady.json", {
        "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "obec": {"kod": OBEC, "nazev": OBEC_NAZEV, "okres": OKRES, "kraj": KRAJ},
        "zdroj": KATALOG,
        "poznamka": (
            "Chybějící hodnota je `null`. Když ji ČSÚ tají kvůli malému počtu "
            "subjektů, je navíc `duverne: true` — to je neznámo, ne nula. "
            "Pole `chybejici_obdobi` vyjmenovává roky, které v řadě nejsou."
        ),
        "rady": sorted(vsechny_rady, key=lambda r: (r["sada"], r["kod"])),
    })

    prehled = {
        "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "obec": {"kod": OBEC, "nazev": OBEC_NAZEV, "okres": OKRES, "kraj": KRAJ},
        "zdroj": KATALOG,
        "licence": "https://www.czso.cz/csu/czso/podminky_pro_vyuzivani_a_dalsi_zverejnovani_statistickych_udaju_csu",
        "sady": [{
            "kod": v["kod"], "nazev": v["nazev"], "stav": v["stav"],
            "perioda": v["perioda"], "od": v["od"], "do": v["do"],
            "zaznamu": v["zaznamu"], "ukazatelu": len(v["ukazatele"]),
            "rad": len(v["rady"]),
            "zdroju_chybi": sum(1 for z in v["zdroje"] if z["stav"] == "chybi"),
            "nesrovnalosti": len(v.get("kontrola", {}).get("nesrovnalosti", [])),
        } for v in hotove],
    }
    uloz(f"{VYSTUP}/prehled.json", prehled)
    return prehled


def vypis_prehled(vybrane: list[Sada], log: Log) -> None:
    radky = katalog(log)
    for sada in vybrane:
        zdroje = sady_z_katalogu(sada, radky)
        print(f"{sada.kod:20} {sada.perioda:8} {len(zdroje):2} sad v katalogu")
        for z in zdroje:
            print(f"    {z['dataset_id']:12} {z['title'][:70]}")


def hlavni() -> int:
    ap = argparse.ArgumentParser(description="O1 — statistika Mariánských Lázní z ČSÚ")
    ap.add_argument("--sada", action="append", help="jen tahle sada (lze opakovat)")
    ap.add_argument("--prehled", action="store_true",
                    help="jen vypíše, co katalog ČSÚ nabízí")
    args = ap.parse_args()

    vybrane = SADY
    if args.sada:
        podle_kodu = {s.kod: s for s in SADY}
        nezname = [k for k in args.sada if k not in podle_kodu]
        if nezname:
            ap.error(f"neznámé sady: {', '.join(nezname)}; znám: "
                     f"{', '.join(podle_kodu)}")
        vybrane = [podle_kodu[k] for k in args.sada]

    log = Log("csu")
    try:
        if args.prehled:
            vypis_prehled(vybrane, log)
        else:
            sber(vybrane, log)
    except ZdrojSelhal as e:
        log.chyba(str(e))
        log.uzavri()
        return 1
    vysledek = log.uzavri()
    return 0 if vysledek["uspech"] else 1


if __name__ == "__main__":
    raise SystemExit(hlavni())
