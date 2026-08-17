"""Ekonomické subjekty se sídlem v Mariánských Lázních — sběr z ARES.

Modul O2. Projekt dosud sledoval jen 25 subjektů městského holdingu
(`config/subjekty.json`). Tenhle sběrač bere všechny subjekty se sídlem ve
městě — tedy i lázeňské společnosti, hotely, dopravce a živnostníky, kteří
s městem nemusí mít nic společného, ale ve městě reálně působí.

ZDROJ: ARES, https://ares.gov.cz/ekonomicke-subjekty-v-be/rest
Kód obce Mariánské Lázně: 554642.

PROČ SE DOTAZ MUSÍ ŘEZAT
------------------------
ARES odmítne každý dotaz, který by vrátil přes 1 000 výsledků, a odmítne
ho hned — ne až na tisící stránce. Subjektů ve městě je 4 177, takže se
dotaz musí rozdělit na kousky pod strop. Řezy jdou v tomhle pořadí a každý
další se nasazuje jen tam, kde předchozí nestačil:

  1. právní forma   — 151 kódů z číselníku ARES. Ověřeno 17. 8. 2026:
     součet přes všechny formy dá přesně 4 177, je to úplný rozklad.
  2. část obce      — potřeba jen u formy 101 (živnostníci, 2 353 subjektů)
  3. ulice          — Mariánské Lázně (1 099) a Úšovice (1 062) jsou přes
     strop i po rozdělení na části
  4. číslo domovní  — dobírá adresy bez názvu ulice; jen v části Mariánské
     Lázně jich je 173 a bez tohohle kroku by pár subjektů vypadlo

KONTROLA ÚPLNOSTI
-----------------
ARES u každého dotazu prozradí přesný počet výsledků: buď v `pocetCelkem`,
nebo — když je jich přes strop — přímo číslem v chybové hlášce. Sběrač si
ten počet u každého řezu pamatuje a porovná ho s počtem skutečně stažených
IČO. Když se čísla nesejdou, zapíše se rozdíl do `uplnost.mezery` a běh se
označí za neúspěšný. Nikdy se nedopočítá a nikdy se nezamlčí.

CO TENHLE ZDROJ NEDÁVÁ — A PROTO ZŮSTÁVÁ NULL
---------------------------------------------
1. `datumZaniku` ve vyhledávání ani v detailu subjektu NENÍ, to pole tam
   vůbec neexistuje. Datum výmazu má až obchodní rejstřík
   (`/ekonomicke-subjekty-vr/{ico}`), a ten se proto dotahuje jen pro
   subjekty, které mají v `seznamRegistraci` stav ZANIKLY.
2. Adresní index ARES vede převážně žijící subjekty. Firmy zaniklé před
   lety v něm nejsou vůbec — nemají v datech ani řádek. Časová osa zániků
   je tedy ze své podstaty NEÚPLNÁ; `datum_zaniku: null` znamená "nevíme",
   ne "firma trvá". Časová osa vzniků takovou vadu nemá, ale i ta ukazuje
   jen firmy, které dodnes existují — ne kolik jich v daném roce vzniklo.
3. Obrat ani přesný počet zaměstnanců ARES nezveřejňuje. Registr
   ekonomických subjektů (RES) dává jen KATEGORII počtu pracovníků
   ("50 - 99 zaměstnanců"), a i ta u většiny subjektů chybí.

DOTAHOVANÁ DATA
---------------
Vyhledávání vrací jméno, sídlo, právní formu, seznam CZ-NACE a datum
vzniku. Registr ekonomických subjektů umí ke stovce IČO naráz vrátit navíc
`czNacePrevazujici` (převažující činnost — ARES ji vede sám, takže se
nemusí hádat, který obor je hlavní) a kategorii počtu pracovníků. Proto se
dotahuje pro všechny subjekty; 4 177 IČO je 42 dotazů.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import core  # noqa: E402
from lib.core import CACHE, Log, ZdrojSelhal, uloz  # noqa: E402

ARES = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest"
ARES_HOST = "ares.gov.cz"
KOD_OBCE = 554642
NAZEV_OBCE = "Mariánské Lázně"

STROP_ARES = 1000   # nad tolik výsledků ARES dotaz odmítne
NA_STRANKU = 200    # maximum, které vrátí na jednu stránku
DAVKA_ICO = 100     # maximum IČO na jeden dotaz do RES

# Dokud řez podle ulic nedojde na úplný počet, dobírá se po číslech
# domovních. Nejvyšší číslo domovní nalezené v Mariánských Lázních je 2 407
# (evidenční číslo v Kladské), obytná zástavba končí kolem 900. Strop je
# tady jako pojistka proti nekonečnému běhu — když ani on nestačí, chybějící
# kus se zapíše do `uplnost.mezery` a je vidět.
MAX_CISLO_DOMOVNI = 1500

CACHE_ARES = CACHE / "ares"


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

class PrilisMnoho(Exception):
    """ARES odmítl dotaz kvůli stropu. Nese počet, který sám nahlásil."""

    def __init__(self, pocet: int):
        super().__init__(f"dotaz vrací {pocet} výsledků, strop je {STROP_ARES}")
        self.pocet = pocet


_SESSION: requests.Session | None = None


def _session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
    return _SESSION


def _post(cesta: str, telo: dict, *, max_age: int = 7 * 86_400, retries: int = 4) -> tuple[int, dict]:
    """POST na ARES s diskovou cache a tempem.

    `core.fetch()` umí jen GET, ARES chce POST s JSON tělem. Tempo se drží
    stejným mechanismem jako u ostatních sběračů — přes značku sdílenou mezi
    procesy, aby na cizí API netlačilo víc modulů naráz.

    Do cache jde i odmítnutí kvůli stropu (HTTP 400). Je to platná odpověď
    zdroje, ne výpadek, a řezání dotazů se na ni opakovaně ptá.
    """
    otisk = hashlib.sha256(
        (cesta + json.dumps(telo, sort_keys=True, ensure_ascii=False)).encode()
    ).hexdigest()[:24]
    soubor = CACHE_ARES / f"{otisk}.json"

    if max_age and soubor.exists() and (time.time() - soubor.stat().st_mtime) < max_age:
        ulozene = json.loads(soubor.read_text(encoding="utf-8"))
        return ulozene["status"], ulozene["telo"]

    hlavicky = {
        "User-Agent": core.UA,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Accept-Language": "cs",
    }
    posledni: Exception | None = None
    for pokus in range(retries):
        try:
            core._pockej_na_rade(ARES_HOST)  # sdílené tempo projektu
            r = _session().post(f"{ARES}/{cesta}", json=telo, headers=hlavicky, timeout=90)
            if r.status_code == 429 or 500 <= r.status_code < 600:
                raise ZdrojSelhal(f"HTTP {r.status_code} u {cesta}")
            odpoved = r.json()
            soubor.parent.mkdir(parents=True, exist_ok=True)
            soubor.write_text(
                json.dumps({"status": r.status_code, "telo": odpoved}, ensure_ascii=False),
                encoding="utf-8",
            )
            return r.status_code, odpoved
        except Exception as e:  # noqa: BLE001 — opakujeme na čemkoliv síťovém
            posledni = e
            if pokus < retries - 1:
                time.sleep(2 ** (pokus + 1))

    raise ZdrojSelhal(f"ARES {cesta} selhal na {retries} pokusů: {posledni}")


def _get(cesta: str, *, max_age: int = 7 * 86_400, retries: int = 3) -> tuple[int, dict]:
    otisk = hashlib.sha256(("GET:" + cesta).encode()).hexdigest()[:24]
    soubor = CACHE_ARES / f"{otisk}.json"
    if max_age and soubor.exists() and (time.time() - soubor.stat().st_mtime) < max_age:
        ulozene = json.loads(soubor.read_text(encoding="utf-8"))
        return ulozene["status"], ulozene["telo"]

    hlavicky = {"User-Agent": core.UA, "Accept": "application/json", "Accept-Language": "cs"}
    posledni: Exception | None = None
    for pokus in range(retries):
        try:
            core._pockej_na_rade(ARES_HOST)
            r = _session().get(f"{ARES}/{cesta}", headers=hlavicky, timeout=90)
            if r.status_code == 429 or 500 <= r.status_code < 600:
                raise ZdrojSelhal(f"HTTP {r.status_code} u {cesta}")
            odpoved = r.json() if r.content else {}
            soubor.parent.mkdir(parents=True, exist_ok=True)
            soubor.write_text(
                json.dumps({"status": r.status_code, "telo": odpoved}, ensure_ascii=False),
                encoding="utf-8",
            )
            return r.status_code, odpoved
        except Exception as e:  # noqa: BLE001
            posledni = e
            if pokus < retries - 1:
                time.sleep(2 ** (pokus + 1))
    raise ZdrojSelhal(f"ARES {cesta} selhal na {retries} pokusů: {posledni}")


def _pocet_z_hlasky(telo: dict) -> int:
    """Vytáhne počet výsledků z hlášky o překročení stropu.

    Hláška zní: "Zadaný dotaz vrací příliš mnoho výsledků (4 177)."
    Číslo je oddělené mezerami po tisících, a to i nezlomitelnými.
    """
    m = re.search(r"\(([\d\s  ]+)\)", telo.get("popis") or "")
    if not m:
        raise ZdrojSelhal(f"ARES odmítl dotaz, ale nesdělil počet: {telo}")
    return int(re.sub(r"\D", "", m.group(1)))


# --------------------------------------------------------------------------
# Číselníky
# --------------------------------------------------------------------------

def _oprav_nazev(text: str) -> str:
    """Opraví rozbité HTML entity v názvech z číselníku ARES.

    Dvanáct položek CZ-NACE má místo středníku řetězec `&#59^` — zdroj si
    escapoval středník a pak ho zkomolil. Opravuje se JEN tenhle přesný
    řetězec, aby oprava nemohla potichu změnit nic jiného. Je to vada
    zobrazení názvu oboru, ne údaj o subjektu.
    """
    return html.unescape(text.replace("&#59^", ";"))


def _ciselnik(kod: str, zdroj: str | None = None) -> dict[str, str]:
    telo: dict[str, Any] = {"kodCiselniku": kod}
    if zdroj:
        telo["zdrojCiselniku"] = zdroj
    status, odpoved = _post("ciselniky-nazevniky/vyhledat", telo, max_age=30 * 86_400)
    if status != 200:
        raise ZdrojSelhal(f"číselník {kod} se nenačetl: {odpoved}")

    # Endpoint vrací několik číselníků stejného jména (různé verze zdroje).
    # Bereme sjednocení — první výskyt kódu vyhrává, kódy se mezi verzemi
    # nepřepisují na jiný význam, jen přibývají.
    polozky: dict[str, str] = {}
    for c in odpoved.get("ciselniky") or []:
        for p in c.get("polozkyCiselniku") or []:
            nazvy = [n["nazev"] for n in p.get("nazev") or [] if n.get("kodJazyka") == "cs"]
            if p.get("kod") not in polozky:
                polozky[p["kod"]] = _oprav_nazev(nazvy[0] if nazvy else p["kod"])
    if not polozky:
        raise ZdrojSelhal(f"číselník {kod} přišel prázdný")
    return polozky


# CZ-NACE sekce podle oddílů. Rozsahy jsou dané klasifikací CZ-NACE, ne
# odhadem — sekce se z oddílu odvozuje jednoznačně.
SEKCE_NACE: list[tuple[int, int, str, str]] = [
    (1, 3, "A", "Zemědělství, lesnictví a rybářství"),
    (5, 9, "B", "Těžba a dobývání"),
    (10, 33, "C", "Zpracovatelský průmysl"),
    (35, 35, "D", "Výroba a rozvod elektřiny, plynu, tepla"),
    (36, 39, "E", "Zásobování vodou, odpady a sanace"),
    (41, 43, "F", "Stavebnictví"),
    (45, 47, "G", "Velkoobchod, maloobchod, opravy vozidel"),
    (49, 53, "H", "Doprava a skladování"),
    (55, 56, "I", "Ubytování, stravování a pohostinství"),
    (58, 63, "J", "Informační a komunikační činnosti"),
    (64, 66, "K", "Peněžnictví a pojišťovnictví"),
    (68, 68, "L", "Činnosti v oblasti nemovitostí"),
    (69, 75, "M", "Profesní, vědecké a technické činnosti"),
    (77, 82, "N", "Administrativní a podpůrné činnosti"),
    (84, 84, "O", "Veřejná správa a obrana"),
    (85, 85, "P", "Vzdělávání"),
    (86, 88, "Q", "Zdravotní a sociální péče"),
    (90, 93, "R", "Kulturní, zábavní a rekreační činnosti"),
    (94, 96, "S", "Ostatní činnosti"),
    (97, 98, "T", "Činnosti domácností"),
    (99, 99, "U", "Činnosti exteritoriálních organizací"),
]


def nace_sekce(kod: str | None) -> tuple[str | None, str | None]:
    """Sekce CZ-NACE pro kód činnosti. Nezná-li se, vrací (None, None).

    Kód "00" je v ARES zástupka pro "výroba, obchod a služby neuvedené
    v přílohách živnostenského zákona" — není to obor, je to *chybějící*
    obor. Vrací se proto jako neznámo, ne jako vlastní kategorie.
    """
    if not kod or kod == "00":
        return None, None
    if kod.isalpha() and len(kod) == 1:
        for _, _, pismeno, nazev in SEKCE_NACE:
            if pismeno == kod.upper():
                return pismeno, nazev
        return None, None
    cislice = re.sub(r"\D", "", kod)
    if len(cislice) < 2:
        return None, None
    oddil = int(cislice[:2])
    for od, do, pismeno, nazev in SEKCE_NACE:
        if od <= oddil <= do:
            return pismeno, nazev
    return None, None


# --------------------------------------------------------------------------
# Kontext řezání
# --------------------------------------------------------------------------

class Kontext:
    """Co sběrač o obci ví — a co z toho plyne pro řezání dotazů.

    Kódy částí obce, ulic a čísel domovních se sbírají ze VŠECH adres, které
    ARES u subjektu vede, tedy i z historických záznamů v `dalsiUdaje`.
    Vyhledávání totiž porovnává i je: mezi subjekty "se sídlem v Mariánských
    Lázních" jsou i takové, které dnes sídlí jinde a na město je váže jen
    starší adresa. Kdyby se kandidáti brali jen z aktuálního sídla, tyhle
    subjekty by při řezání podle ulice vypadly.
    """

    def __init__(self, log: Log):
        self.log = log
        self.casti: set[int] = set()
        self.ulice_v_casti: dict[int | None, set[int]] = {}
        self.cisla_v_casti: dict[int | None, set[int]] = {}
        self.vsechny_ulice: set[int] = set()
        self.mezery: list[dict] = []
        self._adresy_casti: dict[int, tuple[set[int], set[int]]] = {}

    # -- sběr znalostí -----------------------------------------------------

    def zaznamenej(self, subjekt: dict) -> None:
        for adresa in self._adresy(subjekt):
            if adresa.get("kodObce") != KOD_OBCE:
                continue
            cast = adresa.get("kodCastiObce")
            if cast:
                self.casti.add(cast)
            if adresa.get("kodUlice"):
                self.ulice_v_casti.setdefault(cast, set()).add(adresa["kodUlice"])
                self.vsechny_ulice.add(adresa["kodUlice"])
            if adresa.get("cisloDomovni"):
                self.cisla_v_casti.setdefault(cast, set()).add(adresa["cisloDomovni"])

    @staticmethod
    def _adresy(subjekt: dict) -> Iterable[dict]:
        if subjekt.get("sidlo"):
            yield subjekt["sidlo"]
        for udaj in subjekt.get("dalsiUdaje") or []:
            for polozka in udaj.get("sidlo") or []:
                if polozka.get("sidlo"):
                    yield polozka["sidlo"]

    # -- adresní registr ---------------------------------------------------

    def adresy_casti(self, cast: int) -> tuple[set[int], set[int]]:
        """Ulice a čísla domovní bez ulice v dané části obce, z RÚIAN.

        Adresní rejstřík má stejný strop 1 000. Části, které se přes něj
        nevejdou (Úšovice mají 1 318 adres), vrací prázdno — kandidáti se
        pak berou jen ze subjektů. Je to horší vstup, ne tichá ztráta:
        úplnost hlídá kontrola počtů o úroveň výš.
        """
        if cast in self._adresy_casti:
            return self._adresy_casti[cast]

        ulice: set[int] = set()
        bez_ulice: set[int] = set()
        start = 0
        while True:
            status, telo = _post("standardizovane-adresy/vyhledat", {
                "kodObce": KOD_OBCE,
                "kodCastiObce": cast,
                "typStandardizaceAdresy": "VYHOVUJICI_ADRESY",
                "pocet": NA_STRANKU,
                "start": start,
            }, max_age=30 * 86_400)
            if status != 200:
                self.log.info("adresní rejstřík části je nad stropem, kandidáti jen ze subjektů",
                              cast=cast)
                break
            adresy = telo.get("standardizovaneAdresy") or []
            if not adresy:
                break
            for a in adresy:
                if a.get("kodUlice"):
                    ulice.add(a["kodUlice"])
                elif a.get("cisloDomovni"):
                    bez_ulice.add(a["cisloDomovni"])
            start += NA_STRANKU
            if start >= (telo.get("pocetCelkem") or 0):
                break

        self._adresy_casti[cast] = (ulice, bez_ulice)
        return ulice, bez_ulice

    # -- kandidáti na řezy -------------------------------------------------

    def hodnoty_casti(self, _filtr: dict) -> list[int]:
        return sorted(self.casti)

    def hodnoty_ulic(self, filtr: dict) -> list[int]:
        cast = (filtr.get("sidlo") or {}).get("kodCastiObce")
        z_registru, _ = self.adresy_casti(cast) if cast else (set(), set())
        blizke = z_registru | self.ulice_v_casti.get(cast, set())
        # Ulice z jiných částí jdou na konec: kód ulice je v RÚIAN jedinečný
        # přes celou obec a části se o ně někdy dělí. Řezání se zastaví, jak
        # jen je řez úplný, takže se ocas obvykle vůbec neprojde.
        return sorted(blizke) + sorted(self.vsechny_ulice - blizke)

    def hodnoty_cisel(self, filtr: dict) -> list[int]:
        """Čísla domovní jako poslední záchrana. Nejdřív ta, o kterých víme.

        Pořadí je od nejpravděpodobnějšího k nejdražšímu:
          1. adresy bez názvu ulice — právě ty řez podle ulic minul
          2. čísla domovní viděná u subjektů v téže části obce
          3. celý rozsah 1 až MAX_CISLO_DOMOVNI

        Třetí krok je hrubý, ale jediný úplný: subjekt, který se k městu váže
        historickou adresou, má dnešní sídlo jinde, takže jeho mariánské číslo
        domovní není odkud vzít. Ověřeno na Úšovicích — bez slepého dojezdu
        chybělo 7 subjektů, s ním sedí 1 062 z 1 062 a řez skončí u čísla 903.
        Řezání se zastaví, jakmile počet sedí, takže se rozsah obvykle projde
        jen zčásti.
        """
        cast = (filtr.get("sidlo") or {}).get("kodCastiObce")
        _, bez_ulice = self.adresy_casti(cast) if cast else (set(), set())
        znama = self.cisla_v_casti.get(cast, set())
        poradi = sorted(bez_ulice) + sorted(znama - bez_ulice)
        vyzkousena = set(poradi)
        return poradi + [c for c in range(1, MAX_CISLO_DOMOVNI + 1)
                         if c not in vyzkousena]

    def mezera(self, filtr: dict, ocekavano: int, ziskano: int) -> None:
        self.mezery.append({
            "filtr": filtr,
            "ares_hlasi": ocekavano,
            "staženo": ziskano,
            "chybi": ocekavano - ziskano,
        })


# --------------------------------------------------------------------------
# Řezání a stahování
# --------------------------------------------------------------------------

# Pořadí řezů pod úrovní právní formy. Ke každé dimenzi patří zdroj hodnot.
DIMENZE: list[tuple[str, str]] = [
    ("kodCastiObce", "hodnoty_casti"),
    ("kodUlice", "hodnoty_ulic"),
    ("cisloDomovni", "hodnoty_cisel"),
]


def _s_dimenzi(filtr: dict, jmeno: str, hodnota: Any) -> dict:
    novy = json.loads(json.dumps(filtr))  # hluboká kopie, filtry se vnořují
    novy.setdefault("sidlo", {})[jmeno] = hodnota
    return novy


def _klic(subjekt: dict) -> str:
    """Klíč subjektu. IČO, a když chybí, interní ARES id.

    Pár subjektů v RŽP nemá v odpovědi `ico` vůbec — mají jen `icoId` typu
    "ARES_00361728". Číslo v něm vypadá jako IČO, ale detail subjektu pod
    ním vrací 404, takže IČO to není. Neodvozujeme ho: takový subjekt má
    `ico: null` a klíčuje se pod svým interním id.
    """
    return subjekt.get("ico") or f"bez-ico:{subjekt.get('icoId')}"


def _stranka(filtr: dict, start: int) -> tuple[int, list[dict]]:
    status, telo = _post("ekonomicke-subjekty/vyhledat",
                         dict(filtr, pocet=NA_STRANKU, start=start))
    if status == 200:
        return telo.get("pocetCelkem") or 0, telo.get("ekonomickeSubjekty") or []
    if telo.get("subKod") == "VYSTUP_PRILIS_MNOHO_VYSLEDKU":
        raise PrilisMnoho(_pocet_z_hlasky(telo))
    raise ZdrojSelhal(f"ARES odmítl dotaz {filtr}: {telo}")


def _sklid(filtr: dict, uroven: int, ctx: Kontext, log: Log) -> dict[str, dict]:
    """Stáhne jeden řez. Když je nad stropem, rozřeže ho dál."""
    try:
        celkem, prvni = _stranka(filtr, 0)
    except PrilisMnoho as e:
        return _rozdel(filtr, uroven, e.pocet, ctx, log)

    zisk: dict[str, dict] = {}
    for davka in _dalsi_stranky(filtr, celkem, prvni):
        for s in davka:
            zisk[_klic(s)] = s
            ctx.zaznamenej(s)

    if len(zisk) < celkem:
        # Uvnitř jednoho řezu jsou IČO jedinečná, takže menší počet znamená
        # neúplné stránkování, ne duplicity.
        ctx.mezera(filtr, celkem, len(zisk))
        log.chyba(f"řez {filtr} vrátil {len(zisk)} z {celkem} hlášených subjektů")
    return zisk


def _dalsi_stranky(filtr: dict, celkem: int, prvni: list[dict]) -> Iterable[list[dict]]:
    yield prvni
    start = NA_STRANKU
    while start < celkem:
        _, dalsi = _stranka(filtr, start)
        if not dalsi:
            return
        yield dalsi
        start += NA_STRANKU


def _rozdel(filtr: dict, uroven: int, celkem: int, ctx: Kontext, log: Log) -> dict[str, dict]:
    """Rozřeže dotaz nad stropem na menší podle další dimenze v pořadí.

    Dimenze se přidávají, dokud se počet stažených subjektů nesrovná s tím,
    co ARES hlásí. Sjednocení přes několik dimenzí je v pořádku — subjekty
    se klíčují podle IČO, takže překryv se sám sléhne.
    """
    zisk: dict[str, dict] = {}
    for i in range(uroven, len(DIMENZE)):
        jmeno, zdroj = DIMENZE[i]
        hodnoty = getattr(ctx, zdroj)(filtr)
        if not hodnoty:
            continue
        log.info(f"řežu podle {jmeno}", hodnot=len(hodnoty), ares_hlasi=celkem,
                 zatim=len(zisk))
        for hodnota in hodnoty:
            zisk.update(_sklid(_s_dimenzi(filtr, jmeno, hodnota), i + 1, ctx, log))
            if len(zisk) >= celkem:
                break
        if len(zisk) >= celkem:
            break

    if len(zisk) < celkem:
        ctx.mezera(filtr, celkem, len(zisk))
        log.chyba(f"řez {filtr}: ARES hlásí {celkem}, dohledáno {len(zisk)}")
    return zisk


# --------------------------------------------------------------------------
# Převod na náš formát
# --------------------------------------------------------------------------

STAVY_REGISTRU = {
    "stavZdrojeVr": "obchodni_rejstrik",
    "stavZdrojeRes": "registr_ekonomickych_subjektu",
    "stavZdrojeRzp": "zivnostensky_rejstrik",
    "stavZdrojeRos": "registr_osob",
    "stavZdrojeNrpzs": "poskytovatele_zdravotnich_sluzeb",
    "stavZdrojeRpsh": "politicke_strany",
    "stavZdrojeRcns": "cirkve",
    "stavZdrojeSzr": "zemedelsky_registr",
    "stavZdrojeDph": "platce_dph",
    "stavZdrojeIr": "insolvencni_rejstrik",
    "stavZdrojeSd": "spotrebni_dan",
    "stavZdrojeCeu": "centralni_evidence_uctu",
    "stavZdrojeRs": "registr_smluv",
    "stavZdrojeRed": "registr_ekonomickych_dat",
    "stavZdrojeMonitor": "monitor_statni_pokladny",
}


def stav_subjektu(surovy: dict, datum_zaniku: str | None) -> str | None:
    """Stav subjektu z toho, co registry hlásí. Když nevíme, vrací None.

    Pořadí je dané: doložený výmaz přebíjí všechno, "v likvidaci" je součást
    zapsaného obchodního jména (registr ho tam sám doplňuje) a je to tedy
    údaj ze zdroje, ne náš odhad.
    """
    if datum_zaniku:
        return "zanikla"
    stavy = {v for k, v in (surovy.get("seznamRegistraci") or {}).items()
             if k in STAVY_REGISTRU and v and v != "NEEXISTUJICI"}
    if stavy and stavy <= {"ZANIKLY", "HISTORICKY"}:
        return "zanikla"
    if "likvidaci" in (surovy.get("obchodniJmeno") or "").lower():
        return "v_likvidaci"
    if "AKTIVNI" in stavy:
        return "aktivni"
    return None


def prevedi(surovy: dict, formy: dict[str, str], nace_nazvy: dict[str, str]) -> dict:
    sidlo = surovy.get("sidlo") or {}
    forma = surovy.get("pravniForma")
    nace_vse = [k for k in (surovy.get("czNace") or []) if k != "00"]

    return {
        "ico": surovy.get("ico"),
        "ares_id": surovy.get("icoId"),
        "nazev": surovy.get("obchodniJmeno"),
        "pravni_forma": forma,
        "pravni_forma_nazev": formy.get(forma) if forma else None,
        "adresa": sidlo.get("textovaAdresa"),
        "cast_obce": sidlo.get("nazevCastiObce"),
        # Vyhledávání porovnává i historické adresy, takže mezi výsledky jsou
        # i subjekty, které dnes sídlí jinde. Nezahazujeme je — vazbu na
        # město mají doloženou — ale musí být poznat.
        "sidlo_v_obci": sidlo.get("kodObce") == KOD_OBCE if sidlo.get("kodObce") else None,
        "datum_vzniku": surovy.get("datumVzniku"),
        "datum_zaniku": None,      # doplní se z obchodního rejstříku, viz doplň_zaniky
        "stav": None,              # dopočítá se až po datu zániku
        "nace_prevazujici": None,  # doplní se z RES, viz doplň_res
        "nace_prevazujici_nazev": None,
        "nace_sekce": None,
        "nace_sekce_nazev": None,
        "nace_vse": nace_vse,
        # Názvy drží pořadí kódů 1:1 — kód bez názvu v číselníku má None,
        # aby se dvojice nerozjely a název nesedl na cizí kód.
        "nace_vse_nazvy": [nace_nazvy.get(k) for k in nace_vse],
        "zamestnancu_kategorie": None,
        "zamestnancu_rozsah": None,
        "datum_aktualizace": surovy.get("datumAktualizace"),
        "registrace": {
            STAVY_REGISTRU[k]: v
            for k, v in (surovy.get("seznamRegistraci") or {}).items()
            if k in STAVY_REGISTRU and v and v != "NEEXISTUJICI"
        },
    }


# --------------------------------------------------------------------------
# Dotažení RES a zániků
# --------------------------------------------------------------------------

def dopln_res(subjekty: dict[str, dict], nace_nazvy: dict[str, str],
              pracovnici: dict[str, str], log: Log) -> int:
    """Doplní převažující obor a kategorii počtu pracovníků z RES.

    Vyhledávání v registru ekonomických subjektů bere až sto IČO na dotaz,
    takže celé město je 42 dotazů. `czNacePrevazujici` je zásadní: seznam
    `czNace` u subjektu má klidně deset položek a který obor je hlavní,
    z něj poznat nejde. RES to vede sám, takže se nemusí hádat.
    """
    icos = [i for i in subjekty if not i.startswith("bez-ico:")]
    doplneno = 0
    for davka in core.davky(icos, DAVKA_ICO):
        status, telo = _post("ekonomicke-subjekty-res/vyhledat",
                             {"ico": list(davka), "pocet": DAVKA_ICO, "start": 0})
        if status != 200:
            log.chyba(f"RES odmítl dávku {len(davka)} IČO: {telo}")
            continue
        for obal in telo.get("ekonomickeSubjekty") or []:
            zaznamy = obal.get("zaznamy") or []
            if not zaznamy:
                continue
            z = next((r for r in zaznamy if r.get("primarniZaznam")), zaznamy[0])
            cil = subjekty.get(z.get("ico") or obal.get("icoId"))
            if cil is None:
                continue
            prevazujici = z.get("czNacePrevazujici")
            if prevazujici and prevazujici != "00":
                sekce, sekce_nazev = nace_sekce(prevazujici)
                cil["nace_prevazujici"] = prevazujici
                cil["nace_prevazujici_nazev"] = nace_nazvy.get(prevazujici)
                cil["nace_sekce"] = sekce
                cil["nace_sekce_nazev"] = sekce_nazev
            kat = (z.get("statistickeUdaje") or {}).get("kategoriePoctuPracovniku")
            # "000" je v číselníku RES doslova "Neuvedeno" — chybějící údaj,
            # ne kategorie "nula zaměstnanců". Ta má vlastní kód 110.
            if kat and kat != "000":
                cil["zamestnancu_kategorie"] = kat
                cil["zamestnancu_rozsah"] = pracovnici.get(kat)
            doplneno += 1
    return doplneno


def dopln_zaniky(subjekty: dict[str, dict], log: Log) -> int:
    """Dotáhne datum výmazu u subjektů, které registry vedou jako zaniklé.

    Vyhledávání ani detail subjektu pole `datumZaniku` nemají vůbec — má ho
    až obchodní rejstřík. Dotahuje se proto jen pro subjekty se stavem
    ZANIKLY, kterých jsou jednotky, ne pro celé město.
    """
    kandidati = [
        s for s in subjekty.values()
        if "ZANIKLY" in set((s.get("registrace") or {}).values())
    ]
    log.info("dotahuji datum výmazu z obchodního rejstříku", kandidatu=len(kandidati))
    nalezeno = 0
    for s in kandidati:
        if not s.get("ico"):
            continue
        status, telo = _get(f"ekonomicke-subjekty-vr/{s['ico']}")
        if status != 200:
            continue
        for z in telo.get("zaznamy") or []:
            if z.get("datumVymazu"):
                s["datum_zaniku"] = z["datumVymazu"][:10]
                nalezeno += 1
                break
    return nalezeno


# --------------------------------------------------------------------------
# Běh
# --------------------------------------------------------------------------

def sklid_mesto(log: Log) -> tuple[dict[str, dict], Kontext, dict[str, str], dict[str, str], dict[str, str]]:
    formy = _ciselnik("PravniForma")
    nace_nazvy = _ciselnik("CzNace", zdroj="res")
    pracovnici = _ciselnik("KategoriePoctuPracovniku", zdroj="res")
    log.info("číselníky načteny", pravnich_forem=len(formy), nace=len(nace_nazvy))

    ctx = Kontext(log)
    zaklad = {"sidlo": {"kodObce": KOD_OBCE}}
    surove: dict[str, dict] = {}
    nad_stropem: list[str] = []

    # První průchod: formy, které se pod strop vejdou. Zároveň se tím naplní
    # kontext (části obce, ulice, čísla domovní), který velké formy potřebují
    # k řezání — proto se velké nechávají až nakonec.
    for kod in sorted(formy):
        filtr = dict(zaklad, pravniForma=[kod])
        try:
            celkem, prvni = _stranka(filtr, 0)
        except PrilisMnoho as e:
            nad_stropem.append(kod)
            log.info("právní forma je nad stropem, řeže se později",
                     forma=kod, subjektu=e.pocet)
            continue
        if celkem == 0:
            continue
        for davka in _dalsi_stranky(filtr, celkem, prvni):
            for s in davka:
                surove[_klic(s)] = s
                ctx.zaznamenej(s)
        log.info("právní forma stažena", forma=kod, subjektu=celkem,
                 nazev=formy.get(kod, "")[:40])

    for kod in nad_stropem:
        pred = len(surove)
        surove.update(_sklid(dict(zaklad, pravniForma=[kod]), 0, ctx, log))
        log.info("velká právní forma dořezána", forma=kod, novych=len(surove) - pred)

    return surove, ctx, formy, nace_nazvy, pracovnici


def main() -> None:
    log = Log("firmy")

    # Kolik subjektů má obec celkem. ARES to sdělí i tím, že dotaz odmítne —
    # a je to nezávislá kontrola proti součtu přes právní formy.
    try:
        celkem_obec, _ = _stranka({"sidlo": {"kodObce": KOD_OBCE}}, 0)
    except PrilisMnoho as e:
        celkem_obec = e.pocet
    log.info("ARES hlásí subjektů v obci", pocet=celkem_obec)

    surove, ctx, formy, nace_nazvy, pracovnici = sklid_mesto(log)
    log.info("staženo subjektů", pocet=len(surove), ares_hlasi=celkem_obec)

    subjekty = {k: prevedi(v, formy, nace_nazvy) for k, v in surove.items()}
    doplneno = dopln_res(subjekty, nace_nazvy, pracovnici, log)
    log.info("doplněno z registru ekonomických subjektů", subjektu=doplneno)

    zaniku = dopln_zaniky(subjekty, log)
    log.info("dohledáno dat výmazu", pocet=zaniku)

    for klic, s in subjekty.items():
        s["stav"] = stav_subjektu(surove[klic], s["datum_zaniku"])

    chybi = celkem_obec - len(subjekty)
    if chybi > 0:
        log.chyba(f"ARES hlásí {celkem_obec} subjektů, staženo {len(subjekty)} — chybí {chybi}")

    uloz("firmy/subjekty.json", {
        "generovano": time.strftime("%Y-%m-%d"),
        "zdroj": "ares.gov.cz/ekonomicke-subjekty-v-be/rest",
        "obec": {"nazev": NAZEV_OBCE, "kod": KOD_OBCE},
        "uplnost": {
            "ares_hlasi": celkem_obec,
            "stazeno": len(subjekty),
            "chybi": chybi,
            "mezery": ctx.mezery,
        },
        "metodika": {
            "vyber": "všechny ekonomické subjekty, které ARES váže na kód obce 554642",
            "sidlo_v_obci": (
                "ARES porovnává i historické adresy. Subjekty s "
                "sidlo_v_obci=false dnes sídlí jinde a na město je váže jen "
                "dřívější adresa."
            ),
            "datum_zaniku": (
                "Vyhledávání ARES pole datumZaniku nemá. Doplňuje se z "
                "obchodního rejstříku jen u subjektů se stavem ZANIKLY. "
                "Adresní index navíc vede převážně žijící subjekty, takže "
                "firmy zaniklé dávno v datech nejsou vůbec — časová osa "
                "zániků je neúplná a null znamená 'nevíme', ne 'trvá'."
            ),
            "zamestnanci": (
                "Přesné počty ARES nezveřejňuje, jen kategorii z registru "
                "ekonomických subjektů. Kód 000 = 'Neuvedeno' se ukládá jako "
                "null, ne jako nula zaměstnanců."
            ),
            "nace": (
                "nace_prevazujici je převažující činnost podle RES, ne náš "
                "výběr ze seznamu. Kód 00 ('volná živnost') není obor a "
                "vyřazuje se."
            ),
            "obrat": "ARES obrat nezveřejňuje — v datech není a nedopočítává se.",
        },
        "ciselniky": {
            "pravni_formy": formy,
            "kategorie_pracovniku": pracovnici,
            # Celý číselník CZ-NACE, ať si navazující přehled nemusí názvy
            # oborů skládat z toho, co náhodou vidí u subjektů — oddíl, který
            # nikdo nemá jako vedlejší činnost, by jinak zůstal bez názvu.
            "cz_nace": nace_nazvy,
        },
        "subjekty": sorted(subjekty.values(),
                           key=lambda s: (s["nazev"] or "").lower()),
    })

    log.pricti(len(subjekty))
    log.uzavri()


if __name__ == "__main__":
    main()
