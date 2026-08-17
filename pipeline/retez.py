"""Řetěz usnesení → smlouva → peníze.

Vstup:  `data/usneseni/{organ}/{rok}/{cj}.json`   (modul A1)
        `data/penize/smlouvy/{ico}.json`          (modul A3)
        `data/penize/agregace/protistrany.json`   (modul A3)
Výstup: `data/retez/retezy.json`     — nalezená spojení
        `data/retez/nespojene.json`  — velké smlouvy bez usnesení a naopak

--------------------------------------------------------------------------
!!! TOHLE JSOU ODHADY, NE ÚŘEDNÍ VAZBY !!!
--------------------------------------------------------------------------
Usnesení a registr smluv nemají žádný společný identifikátor. Zápis rady
neuvádí číslo smlouvy, kterou schvaluje, a registr smluv neuvádí, které
usnesení smlouvu povolilo. Každé spojení v `retezy.json` je proto
**domněnka složená z nepřímých indicií** — shody IČO, názvu, částky a času.

Každý řetěz nese `jistota` a `duvod`. Web MUSÍ jistotu zobrazit; řetěz
s `jistota: "nizka"` se nesmí prezentovat jako fakt. Falešné spojení
usnesení → smlouva je horší než žádné: tvrdilo by, že se konkrétní
politici usnesli na konkrétní zakázce, což je vážné obvinění.

Zásada: **bez identitní shody se spojení neukládá.** Samotná shoda částky
a data je náhoda, kterou nelze odůvodnit — a co nedokážeme odůvodnit,
to neuložíme.

--------------------------------------------------------------------------
Co data ze své podstaty neumí
--------------------------------------------------------------------------
1. **Registr smluv běží od 1. 7. 2016**, usnesení máme od roku 2012.
   U usnesení starších než polovina roku 2016 tedy „smlouva nenalezena“
   neznamená nic — v registru být nemůže. Do seznamu schválených částek
   bez smlouvy proto vstupují jen usnesení od `REGISTR_OD`.
2. **Smlouvy do 50 000 Kč se do registru nezveřejňují.** Malé schválené
   částky bez smlouvy nejsou podezřelé, jen mimo dosah zdroje.
3. **Jména fyzických osob jsou v usneseních anonymizovaná** (`*****`).
   Smlouvy s fyzickými osobami tedy podle jména spárovat nejde a IČO
   u nich zdroj většinou nemá.
4. **U části smluv zdroj neuvedl protistranu** — místo ní je v datech
   samotný zveřejňující subjekt. Taková smlouva se podle identity párovat
   nedá; v `nespojene.json` to přiznává pole `protistrana_neurcena`.
5. **Město samo se jako protistrana nepoužívá.** „Rada města Mariánské
   Lázně schvaluje…“ je v každém usnesení, takže jméno ani IČO města
   neříkají nic o tom, které usnesení ke smlouvě patří.
6. **Názvy se v usneseních skloňují** („s Kooperativou pojišťovnou“).
   Hledá se proto kmen slova, ne přesný řetězec — což je o kus měkčí
   shoda než IČO, a odráží se to v jistotě.

--------------------------------------------------------------------------
Smlouva podepsaná PŘED usnesením
--------------------------------------------------------------------------
Není to shoda, je to varovný signál — proto je v `retezy.json` zvlášť,
v poli `podpis_pred_usnesenim`. Může jít o dodatečné schválení, o dodatek
ke starší smlouvě, nebo o špatné datum ve zdroji. Ukládá se fakt
(identita sedí, částka sedí, podpis je dřív), výklad zůstává na čtenáři.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import DATA, Log, ZdrojSelhal, nacti, slug, uloz  # noqa: E402

# --------------------------------------------------------------------------
# Prahy a konstanty
# --------------------------------------------------------------------------

# Registr smluv běží od 1. 7. 2016. U starších usnesení by „smlouva
# nenalezena" nebyl nález, jen mez zdroje.
REGISTR_OD = "2016-07-01"

# „Velká" smlouva / „velká" schválená částka pro soubor nespojených.
# 1 mil. Kč je zhruba horní desetina obou rozdělení (799 z 5 626 smluv
# s cenou, 449 z 3 877 bodů usnesení od poloviny roku 2016).
PRAH_VELKE_CZK = 1_000_000

# Město samo — jako protistrana nenese identitní informaci.
ICO_MESTA = "00254061"

# Časová okna mezi usnesením a podpisem smlouvy, ve dnech.
OKNO_TESNE = 120       # typický průběh: schválí se a do čtvrt roku podepíše
OKNO_BEZNE = 365
OKNO_SIROKE = 730      # dál už čas nic nedokazuje
OKNO_PRED = 545        # jak daleko zpět se hledá podpis PŘED usnesením

# Sazby DPH: bod usnesení běžně schvaluje cenu bez DPH, registr uvádí
# částku včetně. Zkouší se i opačný směr (usnesení s DPH, registr bez).
SAZBY_DPH = (21, 15, 12)

# Usnesení uvádějí částky zaokrouhlené na tisíce („2 000,0 tis. Kč"),
# registr na koruny. Malý rozdíl proto shodu nevylučuje — ale nikdy se
# nevydává za shodu přesnou, rozdíl se vypíše do důvodu.
TOLERANCE_CASTKY = 0.002

# Bodové prahy. PRAH_ULOZIT je hranice, pod kterou se spojení neuloží —
# co se nedá odůvodnit, to se neukládá.
PRAH_ULOZIT = 62
PRAH_STREDNI = 80
PRAH_VYSOKA = 98

# Kolik nejlepších bodů usnesení si u jedné smlouvy necháme. Když je shoda
# nerozhodná (rámcová smlouva a její dodatky), je poctivější nabídnout
# několik kandidátů než jednoho vylosovat. Nad tenhle počet už se ale
# nelosuje vůbec — dvojice se bez tvrdé indicie zahodí.
MAX_KANDIDATU = 3

# O kolik bodů smí být kandidát horší než nejlepší, aby ještě „byl ve hře".
ROZDIL_KANDIDATU = 12

# Jméno rozeseté po stovkách usnesení je slabší identita než jméno, které
# padne na hrstku bodů — a jméno, které je shodou okolností i běžné české
# slovo („Střecha s.r.o."), je skoro bezcenné. Body za shodu názvu se proto
# odstupňují podle toho, na kolik bodů usnesení to jméno vůbec padlo.
# Hranice jsou odhad, ne měření.
NAZEV_DISTINKTIVNI = (60, 38)   # padne na hrstku bodů — silná identita
NAZEV_BEZNY = (300, 24)         # opakuje se, sám o sobě nestačí
NAZEV_VSUDYPRITOMNY = 14        # nad 300 bodů: bez další indicie neunese nic

# Bezobsažná slova — do překryvu předmětu smlouvy a názvu bodu nevstupují.
STOPSLOVA = {
    "mesto", "mestem", "mesta", "marianske", "lazne", "lazni", "lazenske",
    "smlouva", "smlouvy", "smlouve", "smlouvou", "smlouvy", "dodatek", "dodatku",
    "uzavreni", "schvaluje", "souhlas", "souhlasu", "navrh", "navrhu",
    "rada", "rady", "zastupitelstvo", "zastupitelstva", "poskytnuti",
    "verejne", "verejneho", "verejnou", "cast", "casti", "roku", "rok",
    "ktere", "ktery", "ostatni", "dalsi", "mezi", "podle", "dle",
    "spolecnost", "spolecnosti", "firma", "ceske", "republiky", "cislo",
}


# --------------------------------------------------------------------------
# Normalizace textu
# --------------------------------------------------------------------------

def _bez_diakritiky(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def _normalizuj(text: str) -> str:
    """Text na porovnávání: bez diakritiky, malá písmena, jen slova a číslice."""
    return re.sub(r"[^a-z0-9]+", " ", _bez_diakritiky(text)).strip()


# Právní forma v původním (nenormalizovaném) názvu. Jádro názvu je to,
# co stojí PŘED ní: „Kooperativa pojišťovna, a.s., Vienna Insurance Group"
# → „kooperativa pojistovna". Kdyby se forma jen mazala zevnitř, zbyl by
# název s dírou, který se v textu usnesení nedá najít vcelku.
_FORMA_RE = re.compile(
    r"[,\s]*\b(?:"
    r"spol\.|s\.\s*r\.\s*o\.?|a\.\s*s\.?|z\.\s*s\.?|z\.\s*[uú]\.?|"
    r"o\.\s*p\.\s*s\.?|o\.\s*s\.?|k\.\s*s\.?|v\.\s*o\.\s*s\.?|"
    r"s\.\s*e\.?|p\.\s*o\.?|v\s+likvidaci|"
    r"p[řr][íi]sp[ěe]vkov[áa]\s+organizace|akciov[áa]\s+spole[čc]nost|"
    r"spole[čc]nost\s+s\s+ru[čc]en[íi]m\s+omezen[ýy]m"
    r")",
    re.IGNORECASE,
)

# Zbytky právní formy na konci už normalizovaného jádra.
_FORMA_KONCOVKA = re.compile(r"\s+(?:sro|as|zs|ops|spol|se|po)$")

# Názvy, které jako identita nefungují: buď je to město samo, nebo zdroj
# místo protistrany uvedl zástupný text.
_NEPOUZITELNE_JADRO = {
    "mesto marianske lazne", "marianske lazne", "mesto", "obec",
    "fyzicka osoba", "neuvedeno", "neuvedena", "nezverejneno",
}
_NEPOUZITELNY_ZACATEK = ("udaj neni verejny", "neni verejny", "anonymizov")


def _jadro_nazvu(nazev: str) -> str:
    """Jádro názvu protistrany bez právní formy — to se hledá v usnesení."""
    puvodni = (nazev or "").strip()
    m = _FORMA_RE.search(puvodni)
    if m and m.start() > 0:
        puvodni = puvodni[:m.start()]
    x = _normalizuj(puvodni)
    while True:
        y = _FORMA_KONCOVKA.sub("", x)
        if y == x:
            break
        x = y
    return x.strip()


def _pouzitelne_jadro(jadro: str) -> bool:
    if len(jadro) < 5:
        return False
    if jadro in _NEPOUZITELNE_JADRO:
        return False
    return not jadro.startswith(_NEPOUZITELNY_ZACATEK)


# --------------------------------------------------------------------------
# Skloňování: hledá se kmen, ne přesný řetězec
# --------------------------------------------------------------------------

def _kmen(token: str) -> str:
    """Kmen slova — koncovka se v češtině mění, začátek slova ne."""
    if len(token) >= 7:
        return token[:-2]
    if len(token) >= 5:
        return token[:-1]
    return token


def _vzor_nazvu(jadro: str) -> re.Pattern | None:
    """Regulární výraz hledající jádro názvu i ve skloňované podobě.

    Tokeny musí v textu stát za sebou — rozeseté shody („Servis" na jednom
    místě, „Dopravní" na druhém) by nebyly zmínkou o firmě.
    """
    tokeny = jadro.split()
    if not tokeny:
        return None
    casti = [re.escape(_kmen(t)) + r"\w*" for t in tokeny]
    return re.compile(r"\b" + r"\s+".join(casti) + r"\b")


# IČO v textu usnesení: „IČO: 47116617", „IČ 024 25 491", „IČO:47116617".
# Číslice se v zápisech oddělují mezerami, proto se mezery uvnitř povolují
# a až potom vyhodí.
_ICO_RE = re.compile(r"I[ČC]O?\s*[:.]?\s*(\d[\d ]{4,10}\d)", re.IGNORECASE)


def _ica_z_textu(text: str) -> set[str]:
    """Vytáhne z textu IČO. Doplní vedoucí nuly, delší číslo než 8 zahodí."""
    out: set[str] = set()
    for m in _ICO_RE.finditer(text or ""):
        cislice = re.sub(r"\D", "", m.group(1))
        if 5 <= len(cislice) <= 8:
            out.add(cislice.zfill(8))
    return out


# Číslo smlouvy uvnitř předmětu — „Smlouva č. 5220300390 o poskytnutí…".
# Bere se jen delší číslo (6+ číslic), aby „Dodatek č. 1" nedělal shodu.
_CISLO_SMLOUVY_RE = re.compile(r"\b(\d[\d/\-]{5,24}\d)\b")


def _cisla_smlouvy(predmet: str) -> set[str]:
    out: set[str] = set()
    for m in _CISLO_SMLOUVY_RE.finditer(predmet or ""):
        s = m.group(1)
        if len(re.sub(r"\D", "", s)) >= 6:
            out.add(s)
    return out


def _obsahova_slova(text: str) -> set[str]:
    return {
        s for s in _normalizuj(text).split()
        if len(s) >= 4 and not s.isdigit() and s not in STOPSLOVA
    }


def _den(datum: str) -> date | None:
    try:
        return datetime.strptime((datum or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Načtení vstupů
# --------------------------------------------------------------------------

def nacti_body(log: Log) -> list[dict]:
    """Všechny body usnesení jako plochý seznam, připravené na porovnávání."""
    soubory = sorted((DATA / "usneseni").glob("*/*/*.json"))
    if not soubory:
        raise ZdrojSelhal(
            "Nenalezena žádná data/usneseni/**/*.json — nejdřív spusť scrapers/usneseni.py"
        )
    body: list[dict] = []
    for cesta in soubory:
        zapis = nacti(cesta)
        datum = zapis.get("datum") or ""
        den = _den(datum)
        for b in zapis.get("body", []):
            text = f"{b.get('nazev') or ''}\n{b.get('text') or ''}"
            body.append({
                "organ": zapis.get("organ"),
                "cj": zapis.get("cj"),
                "datum": datum,
                "den": den,
                "bod": b.get("cislo"),
                "cislo_usneseni": b.get("cislo_usneseni"),
                "nazev": b.get("nazev") or "",
                "tagy": b.get("tagy") or [],
                "castka_czk": b.get("castka_czk"),
                "vysledek": b.get("vysledek"),
                "hlasovani_id": b.get("hlasovani_id"),
                "url": b.get("url") or zapis.get("url"),
                "_norm": _normalizuj(text),
                "_ica": _ica_z_textu(text),
                "_slova": _obsahova_slova(b.get("nazev") or ""),
            })
    log.info("načteno bodů usnesení", pocet=len(body), zapisu=len(soubory))
    return body


def nacti_smlouvy(log: Log) -> list[dict]:
    """Všechny smlouvy všech sledovaných subjektů jako plochý seznam."""
    soubory = sorted((DATA / "penize" / "smlouvy").glob("*.json"))
    if not soubory:
        raise ZdrojSelhal(
            "Nenalezena žádná data/penize/smlouvy/*.json — nejdřív spusť scrapers/hlidac.py"
        )
    smlouvy: list[dict] = []
    videne: set[str] = set()
    duplicit = 0
    for cesta in soubory:
        obsah = nacti(cesta)
        subjekt_ico = obsah.get("ico") or cesta.stem
        subjekt_nazev = obsah.get("nazev") or ""
        for s in obsah.get("smlouvy", []):
            # Když jsou v registru sledované obě strany, tatáž smlouva je
            # v datech dvakrát. Bez tohoto by každý řetěz vznikl dvakrát
            # a součty by tvrdily dvojnásobek skutečnosti.
            if s.get("id") in videne:
                duplicit += 1
                continue
            videne.add(s.get("id"))
            protistrana_ico = (s.get("protistrana_ico") or "").strip()
            # Zdroj u části smluv místo protistrany zopakoval sám subjekt —
            # protistrana je tím pádem neznámá, ne že by jí bylo město.
            neurcena = protistrana_ico == subjekt_ico
            jadro = "" if neurcena else _jadro_nazvu(s.get("protistrana") or "")
            if not _pouzitelne_jadro(jadro):
                jadro = ""
            ico = "" if neurcena else protistrana_ico
            if ico == ICO_MESTA:
                ico = ""  # město je v každém usnesení, identitu nenese
            smlouvy.append({
                **s,
                "subjekt_ico": subjekt_ico,
                "subjekt": subjekt_nazev,
                "_den": _den(s.get("datum") or ""),
                "_ico": ico,
                "_jadro": jadro,
                "_protistrana_neurcena": neurcena,
                "_cisla": _cisla_smlouvy(s.get("predmet") or ""),
                "_slova": _obsahova_slova(s.get("predmet") or ""),
            })
    log.info("načteno smluv", pocet=len(smlouvy), subjektu=len(soubory),
             duplicit_mezi_subjekty=duplicit)
    return smlouvy


def nacti_penize(log: Log) -> dict[tuple[str, str], dict]:
    """Agregace protistran — konec řetězu: kolik ta firma od města dostala.

    Agregace vede každou protistranu zvlášť pro směr `vydaj` a `prijem`
    (a u subjektů bez IČO drží klíč v názvu, ne v poli `ico`), takže klíč
    tady musí být dvojice (směr, identita) — jinak se půlka záznamů
    navzájem přepíše.
    """
    agr = nacti("penize/agregace/protistrany.json")
    if not agr:
        raise ZdrojSelhal(
            "Chybí data/penize/agregace/protistrany.json — "
            "nejdřív spusť pipeline/agregace_penez.py"
        )
    out: dict[tuple[str, str], dict] = {}
    for p in agr.get("protistrany", []):
        identita = p["ico"] if p.get("klic_dle") == "ico" else "nazev:" + slug(p.get("nazev") or "")
        out[(p.get("smer") or "", identita)] = p
    log.info("načteno protistran", pocet=len(out))
    return out


# --------------------------------------------------------------------------
# Rejstříky pro rychlé hledání kandidátů
# --------------------------------------------------------------------------

def _rejstriky(body: list[dict]) -> tuple[dict[str, list[int]], dict[str, set[int]]]:
    """(IČO → indexy bodů, čtyřpísmenný začátek slova → indexy bodů).

    Hledá se podle začátku slova, protože koncovky se skloňováním mění.
    """
    dle_ica: dict[str, list[int]] = defaultdict(list)
    dle_zacatku: dict[str, set[int]] = defaultdict(set)
    for i, b in enumerate(body):
        for ico in b["_ica"]:
            dle_ica[ico].append(i)
        for slovo in set(b["_norm"].split()):
            if len(slovo) >= 4:
                dle_zacatku[slovo[:4]].add(i)
    return dle_ica, dle_zacatku


def _body_dle_jmena(jadro: str, body: list[dict],
                    dle_zacatku: dict[str, set[int]]) -> set[int]:
    """Indexy bodů, v jejichž textu stojí jádro názvu (i skloňované) vcelku."""
    vzor = _vzor_nazvu(jadro)
    if vzor is None:
        return set()
    kmeny = [_kmen(t)[:4] for t in jadro.split() if len(_kmen(t)) >= 4]
    if not kmeny:
        return set()  # samá krátká slova — příliš slabé na identitu
    kmeny.sort(key=lambda k: len(dle_zacatku.get(k, ())))
    kandidati = set(dle_zacatku.get(kmeny[0], ()))
    for k in kmeny[1:]:
        kandidati &= dle_zacatku.get(k, set())
        if not kandidati:
            return set()
    return {i for i in kandidati if vzor.search(body[i]["_norm"])}


# --------------------------------------------------------------------------
# Jednotlivé signály
# --------------------------------------------------------------------------

def _shoda_castky(castka_bodu, castka_smlouvy) -> tuple[str, str] | None:
    """Shoda částek. Vrací (kód signálu, lidský popis), nebo None."""
    if not castka_bodu or not castka_smlouvy:
        return None
    a, b = float(castka_bodu), float(castka_smlouvy)
    if a <= 0 or b <= 0:
        return None

    def rozdil(x: float, y: float) -> str:
        """Nikdy netvrdit „sedí přesně", když se částky liší. Usnesení
        zaokrouhlují na tisíce, registr uvádí korunu — rozdíl se přizná."""
        d = abs(x - y)
        return "shodná" if d < 0.5 else f"rozdíl {d:,.0f} Kč".replace(",", " ")

    def sedi(x: float, y: float) -> bool:
        return abs(x - y) <= max(1.0, TOLERANCE_CASTKY * max(x, y))

    if sedi(a, b):
        return "castka_presna", f"částka bodu a smlouvy si odpovídá ({rozdil(a, b)})"
    for sazba in SAZBY_DPH:
        koef = 1 + sazba / 100
        if sedi(a * koef, b):
            return (f"castka_dph_{sazba}",
                    f"částka smlouvy odpovídá částce bodu po připočtení {sazba} % DPH "
                    f"({rozdil(a * koef, b)})")
        if sedi(a, b * koef):
            return (f"castka_dph_opacne_{sazba}",
                    f"částka bodu odpovídá částce smlouvy zvýšené o {sazba} % DPH "
                    f"— bod uvedl cenu včetně daně ({rozdil(a, b * koef)})")
    return None


def _body_za_castku(castka: float) -> int:
    """Shoda malých částek je snadná náhoda, shoda velkých téměř ne."""
    c = float(castka)
    if c >= 1_000_000:
        return 34
    if c >= 100_000:
        return 28
    if c >= 20_000:
        return 20
    return 8


def _body_za_cas(odstup: int) -> tuple[int, str]:
    if odstup <= OKNO_TESNE:
        return 26, f"smlouva podepsána {odstup} dní po usnesení"
    if odstup <= OKNO_BEZNE:
        return 16, f"smlouva podepsána {odstup} dní po usnesení"
    if odstup <= OKNO_SIROKE:
        return 6, f"smlouva podepsána až {odstup} dní po usnesení"
    return 0, f"smlouva podepsána {odstup} dní po usnesení"


def _prekryv_predmetu(bod: dict, smlouva: dict) -> tuple[int, str | None]:
    spolecna = bod["_slova"] & smlouva["_slova"]
    if len(spolecna) >= 3:
        return 14, "název bodu a předmět smlouvy sdílí slova " + ", ".join(sorted(spolecna)[:4])
    if len(spolecna) == 2:
        return 8, "název bodu a předmět smlouvy sdílí slova " + ", ".join(sorted(spolecna))
    if len(spolecna) == 1:
        return 3, None
    return 0, None


def _sila_nazvu(vyskytu: int) -> tuple[int, str | None]:
    """Kolik váží shoda názvu podle toho, na kolik bodů usnesení jméno padlo."""
    mez_d, body_d = NAZEV_DISTINKTIVNI
    mez_b, body_b = NAZEV_BEZNY
    if vyskytu <= mez_d:
        return body_d, None
    if vyskytu <= mez_b:
        return body_b, f"název se ale objevuje v {vyskytu} bodech usnesení"
    return NAZEV_VSUDYPRITOMNY, (
        f"název se objevuje v {vyskytu} bodech usnesení, sám o sobě neurčuje nic"
    )


def _ohodnot(bod: dict, smlouva: dict, *, ma_ico: bool, ma_nazev: bool,
             vyskytu_jmena: int) -> dict | None:
    """Sečte indicie pro jednu dvojici. None = nedá se odůvodnit."""
    if bod["den"] is None or smlouva["_den"] is None:
        return None
    odstup = (smlouva["_den"] - bod["den"]).days

    signaly: list[str] = []
    duvody: list[str] = []
    skore = 0

    # --- identita (bez ní se neukládá nic) ---
    if ma_ico:
        skore += 50
        signaly.append("ico")
        duvody.append(f"IČO {smlouva['_ico']} je uvedeno v textu usnesení")
    if ma_nazev:
        signaly.append("nazev")
        if ma_ico:
            skore += 12
            duvody.append("v usnesení je i název protistrany")
        else:
            b, vyhrada = _sila_nazvu(vyskytu_jmena)
            skore += b
            duvody.append(f"název protistrany ({smlouva.get('protistrana')}) "
                          "je v textu usnesení")
            if vyhrada:
                duvody.append(vyhrada)
    if not signaly:
        return None

    # --- číslo smlouvy z předmětu ---
    for cislo in smlouva["_cisla"]:
        holé_cislo = re.sub(r"\D", "", cislo)
        if holé_cislo and holé_cislo in bod["_norm"]:
            skore += 40
            signaly.append("cislo_smlouvy")
            duvody.append(f"číslo {cislo} z předmětu smlouvy je i v usnesení")
            break

    # --- částka ---
    shoda = _shoda_castky(bod.get("castka_czk"), smlouva.get("castka_czk"))
    if shoda:
        kod, popis = shoda
        skore += _body_za_castku(smlouva["castka_czk"])
        signaly.append(kod)
        duvody.append(popis)

    # --- čas ---
    if odstup >= 0:
        b, popis = _body_za_cas(odstup)
        skore += b
        duvody.append(popis)
        signaly.append(
            "cas_tesne" if odstup <= OKNO_TESNE else
            "cas_bezne" if odstup <= OKNO_BEZNE else
            "cas_siroke" if odstup <= OKNO_SIROKE else "cas_mimo"
        )
    else:
        signaly.append("podpis_pred_usnesenim")
        duvody.append(f"POZOR: smlouva byla podepsána {abs(odstup)} dní PŘED usnesením")

    # --- předmět ---
    b, popis = _prekryv_predmetu(bod, smlouva)
    skore += b
    if popis:
        signaly.append("predmet")
        duvody.append(popis)

    return {"skore": skore, "signaly": signaly, "duvody": duvody, "odstup_dni": odstup}


def _jistota(h: dict, kandidatu_usneseni: int = 1, kandidatu_smluv: int = 1) -> str:
    """Skóre, signály a jednoznačnost na tři stupně, které web ukazuje čtenáři.

    Jednoznačnost je stejně důležitá jako skóre: dvojice, ke které existuje
    pět stejně dobrých alternativ, není jistá, ať má bodů kolik chce.
    """
    s, sig = h["skore"], set(h["signaly"])
    ma_castku = any(x.startswith("castka_") for x in sig)
    tvrda_identita = "ico" in sig or "cislo_smlouvy" in sig
    v_case = bool({"cas_tesne", "cas_bezne", "cas_siroke"} & sig)
    jedina = kandidatu_usneseni == 1 and kandidatu_smluv == 1

    if (s >= PRAH_VYSOKA and v_case and tvrda_identita and jedina
            and (ma_castku or "cislo_smlouvy" in sig)):
        return "vysoka"
    if s >= PRAH_STREDNI and v_case and (_tvrda_indicie(h) or jedina):
        return "stredni"
    return "nizka"


# --------------------------------------------------------------------------
# Sestavení řetězů
# --------------------------------------------------------------------------

def _vystup_bodu(b: dict) -> dict:
    return {
        "organ": b["organ"], "cj": b["cj"], "datum": b["datum"],
        "bod": b["bod"], "cislo_usneseni": b["cislo_usneseni"],
        "nazev": b["nazev"], "tagy": b["tagy"],
        "castka_czk": b["castka_czk"], "vysledek": b["vysledek"],
        "hlasovani_id": b["hlasovani_id"], "url": b["url"],
    }


def _vystup_smlouvy(s: dict) -> dict:
    return {
        "id": s.get("id"), "datum": s.get("datum"), "castka_czk": s.get("castka_czk"),
        "predmet": s.get("predmet"), "kategorie": s.get("kategorie"),
        "protistrana": s.get("protistrana"), "protistrana_ico": s.get("protistrana_ico"),
        "smer": s.get("smer"), "vada": s.get("vada"),
        "vazba_na_politiky": s.get("vazba_na_politiky"),
        "subjekt_ico": s.get("subjekt_ico"), "subjekt": s.get("subjekt"),
        "url": s.get("url"),
    }


def _vystup_penez(s: dict, penize: dict[tuple[str, str], dict]) -> dict | None:
    """Konec řetězu: co protistrana od města dostala (nebo městu zaplatila) celkem."""
    smer = s.get("smer") or ""
    ico = (s.get("protistrana_ico") or "").strip()
    p = penize.get((smer, ico)) if ico else None
    if p is None:
        p = penize.get((smer, "nazev:" + slug(s.get("protistrana") or "")))
    if p is None:
        return None
    return {
        "protistrana_celkem_czk": p.get("celkem_czk"),
        "protistrana_smluv": p.get("smluv"),
        "prvni_rok": p.get("prvni_rok"),
        "posledni_rok": p.get("posledni_rok"),
        "aktivni": p.get("aktivni"),
        "interni": p.get("interni"),
    }


def _retez(bod: dict, smlouva: dict, h: dict, penize: dict[tuple[str, str], dict],
           jistota: str | None = None,
           nejednoznacnost: tuple[int, int] = (1, 1)) -> dict:
    n_usn, n_sml = nejednoznacnost
    duvody = list(h["duvody"])
    if n_usn > 1:
        duvody.append(f"stejně dobře sedí i {n_usn - 1} další usnesení")
    if n_sml > 1:
        duvody.append(f"témuž usnesení odpovídá i {n_sml - 1} dalších smluv téže protistrany")
    return {
        "id": f"{bod['organ']}-{bod['datum'][:4]}-{bod['bod']}__{smlouva.get('id')}",
        "jistota": jistota or _jistota(h, n_usn, n_sml),
        "skore": h["skore"],
        "signaly": h["signaly"],
        "duvod": "; ".join(duvody),
        "odstup_dni": h["odstup_dni"],
        # Kolik jiných usnesení se hlásí k téže smlouvě a kolik jiných smluv
        # téže protistrany k témuž usnesení. Jednička v obou znamená, že
        # dvojice je v datech jediná svého druhu.
        "kandidatu_usneseni": n_usn,
        "kandidatu_smluv": n_sml,
        "usneseni": _vystup_bodu(bod),
        "smlouva": _vystup_smlouvy(smlouva),
        "penize": _vystup_penez(smlouva, penize),
    }


def _identita(s: dict) -> str:
    return s["_ico"] or s["_jadro"]


def _navrhy(log: Log, body: list[dict], smlouvy: list[dict]) -> tuple[list[dict], list[dict]]:
    """První průchod: ke každé smlouvě posbírá všechny odůvodnitelné dvojice.

    Rozhodovat se tady ještě nedá — jestli je dvojice věrohodná, závisí i na
    tom, kolik jiných dvojic se o totéž uchází. To ví až druhý průchod.
    """
    dle_ica, dle_zacatku = _rejstriky(body)
    cache_jmen: dict[str, set[int]] = {}
    dopredu: list[dict] = []
    zpetne: list[dict] = []
    bez_identity = 0
    bez_zminky = 0

    for si, s in enumerate(smlouvy):
        if s["_den"] is None:
            continue
        if not s["_ico"] and not s["_jadro"]:
            bez_identity += 1
            continue

        idx_ico = set(dle_ica.get(s["_ico"], ())) if s["_ico"] else set()
        if s["_jadro"]:
            if s["_jadro"] not in cache_jmen:
                cache_jmen[s["_jadro"]] = _body_dle_jmena(s["_jadro"], body, dle_zacatku)
            idx_nazev = cache_jmen[s["_jadro"]]
        else:
            idx_nazev = set()
        if not idx_ico and not idx_nazev:
            bez_zminky += 1
            continue

        nejlepsi_zpetny: dict | None = None
        for i in idx_ico | idx_nazev:
            b = body[i]
            if b["den"] is None:
                continue
            odstup = (s["_den"] - b["den"]).days
            if odstup > OKNO_SIROKE or odstup < -OKNO_PRED:
                continue
            h = _ohodnot(b, s, ma_ico=i in idx_ico, ma_nazev=i in idx_nazev,
                         vyskytu_jmena=len(idx_nazev))
            if not h:
                continue
            navrh = {"bod_i": i, "sml_i": si, "h": h}
            if odstup >= 0:
                dopredu.append(navrh)
            elif _tvrda_indicie(h) and (
                nejlepsi_zpetny is None or h["skore"] > nejlepsi_zpetny["h"]["skore"]
            ):
                # Podpis PŘED usnesením není shoda. Bereme jen ten nejlépe
                # doložený, a jen když ho drží částka nebo číslo smlouvy.
                nejlepsi_zpetny = navrh
        if nejlepsi_zpetny:
            zpetne.append(nejlepsi_zpetny)

    log.info("smlouvy nepárovatelné podle identity",
             bez_identity=bez_identity, identita_bez_zminky=bez_zminky)
    return dopredu, zpetne


def _pocty_kandidatu(navrhy: list[dict], smlouvy: list[dict]
                     ) -> tuple[dict[int, int], dict[tuple[int, str], int]]:
    """(smlouva → kolik bodů se o ni uchází, bod+firma → kolik jejích smluv)."""
    dle_smlouvy: dict[int, int] = defaultdict(int)
    dle_bodu: dict[tuple[int, str], int] = defaultdict(int)
    for n in navrhy:
        dle_smlouvy[n["sml_i"]] += 1
        dle_bodu[(n["bod_i"], _identita(smlouvy[n["sml_i"]]))] += 1
    return dle_smlouvy, dle_bodu


def _tvrda_indicie(h: dict) -> bool:
    """Částka nebo číslo smlouvy — jediné signály, které vážou konkrétní kus."""
    return "cislo_smlouvy" in h["signaly"] or any(
        x.startswith("castka_") for x in h["signaly"]
    )


def spoj(log: Log, body: list[dict], smlouvy: list[dict],
         penize: dict[tuple[str, str], dict]) -> tuple[list[dict], list[dict]]:
    dopredu, zpetne = _navrhy(log, body, smlouvy)

    # --- druhý průchod: jak moc je dvojice jednoznačná ---
    # Bez tvrdé indicie drží dvojici jen to, že firma je v usnesení zmíněná
    # a smlouva přišla brzy po něm. Když se ale o tutéž smlouvu uchází pět
    # usnesení, nebo když jedno usnesení o firmě sedí na padesát jejích
    # smluv, není to zjištění, je to losování — a ty se neukládají.
    nejlepsi_pro_smlouvu: dict[int, int] = {}
    for n in dopredu:
        si, sk = n["sml_i"], n["h"]["skore"]
        if sk > nejlepsi_pro_smlouvu.get(si, -1):
            nejlepsi_pro_smlouvu[si] = sk

    ve_hre = [n for n in dopredu
              if n["h"]["skore"] >= PRAH_ULOZIT
              and n["h"]["skore"] >= nejlepsi_pro_smlouvu[n["sml_i"]] - ROZDIL_KANDIDATU]

    # Konkurence se počítá ve stejné váhové kategorii. Dvojici drženou
    # shodou částky neshazuje to, že se k témuž usnesení volně hlásí
    # padesát dalších smluv téže firmy — ta shoda míří na konkrétní kus.
    pocty_vse = _pocty_kandidatu(ve_hre, smlouvy)
    pocty_tvrde = _pocty_kandidatu([n for n in ve_hre if _tvrda_indicie(n["h"])], smlouvy)

    ve_hre.sort(key=lambda n: (n["sml_i"], -n["h"]["skore"], abs(n["h"]["odstup_dni"])))

    retezy: list[dict] = []
    zahozeno_nejednoznacne = 0
    poradi: dict[int, int] = defaultdict(int)
    for n in ve_hre:
        s = smlouvy[n["sml_i"]]
        tvrde = _tvrda_indicie(n["h"])
        kandidatu_usneseni, kandidatu_smluv = pocty_tvrde if tvrde else pocty_vse
        n_usn = kandidatu_usneseni[n["sml_i"]]
        n_sml = kandidatu_smluv[(n["bod_i"], _identita(s))]
        if not tvrde and (n_usn > MAX_KANDIDATU or n_sml > MAX_KANDIDATU):
            zahozeno_nejednoznacne += 1
            continue
        poradi[n["sml_i"]] += 1
        if poradi[n["sml_i"]] > MAX_KANDIDATU:
            continue
        retezy.append(_retez(body[n["bod_i"]], s, n["h"], penize,
                             nejednoznacnost=(n_usn, n_sml)))

    pred = [_retez(body[n["bod_i"]], smlouvy[n["sml_i"]], n["h"], penize,
                   jistota="varovani") for n in zpetne]

    log.info("zahozeno jako nejednoznačné", pocet=zahozeno_nejednoznacne)
    retezy.sort(key=lambda r: (r["smlouva"]["datum"] or "", str(r["smlouva"]["id"])))
    pred.sort(key=lambda r: (r["smlouva"]["datum"] or "", str(r["smlouva"]["id"])))
    return retezy, pred


# --------------------------------------------------------------------------
# Nespojené — stejně cenný výstup jako spojené
# --------------------------------------------------------------------------

def nespojene(log: Log, body: list[dict], smlouvy: list[dict],
              retezy: list[dict], pred: list[dict]) -> dict:
    """Velké smlouvy bez nalezeného usnesení a velké schválené částky bez smlouvy.

    Nepíše se, co to znamená. Chybějící usnesení u velké smlouvy může být
    chyba tohoto párování stejně dobře jako smlouva, o které se nehlasovalo.
    """
    spojene_smlouvy = ({r["smlouva"]["id"] for r in retezy}
                       | {r["smlouva"]["id"] for r in pred})
    spojene_body = {(r["usneseni"]["organ"], r["usneseni"]["bod"]) for r in retezy}

    smlouvy_bez: list[dict] = []
    for s in smlouvy:
        if (s.get("castka_czk") or 0) < PRAH_VELKE_CZK or s.get("id") in spojene_smlouvy:
            continue
        smlouvy_bez.append({
            **_vystup_smlouvy(s),
            "protistrana_neurcena": s["_protistrana_neurcena"],
            "poznamka": (
                "zdroj u této smlouvy neuvedl protistranu, párovat podle identity nelze"
                if s["_protistrana_neurcena"] else
                "protistrana je známá, ale v žádném usnesení se nenašla"
            ),
        })

    usneseni_bez: list[dict] = []
    for b in body:
        if (b.get("castka_czk") or 0) < PRAH_VELKE_CZK:
            continue
        if b["datum"] < REGISTR_OD:
            continue  # v registru by smlouva nebyla, absence tu nic neznamená
        if (b["organ"], b["bod"]) in spojene_body:
            continue
        usneseni_bez.append(_vystup_bodu(b))

    smlouvy_bez.sort(key=lambda s: -(s["castka_czk"] or 0))
    usneseni_bez.sort(key=lambda b: -(b["castka_czk"] or 0))
    log.info("nespojeno", velkych_smluv=len(smlouvy_bez), velkych_usneseni=len(usneseni_bez))
    return {"smlouvy": smlouvy_bez, "usneseni": usneseni_bez}


# --------------------------------------------------------------------------
# Běh
# --------------------------------------------------------------------------

def _statistika(retezy: list[dict], pred: list[dict],
                body: list[dict], smlouvy: list[dict]) -> dict:
    dle_jistoty = {"vysoka": 0, "stredni": 0, "nizka": 0}
    for r in retezy:
        dle_jistoty[r["jistota"]] += 1
    return {
        "retezu": len(retezy),
        "dle_jistoty": dle_jistoty,
        "podpis_pred_usnesenim": len(pred),
        "spojenych_smluv": len({r["smlouva"]["id"] for r in retezy}),
        "spojenych_bodu": len({(r["usneseni"]["organ"], r["usneseni"]["bod"]) for r in retezy}),
        "vsech_bodu": len(body),
        "vsech_smluv": len(smlouvy),
    }


METODIKA = {
    "co_to_je": (
        "Odhad vazby mezi bodem usnesení a smlouvou v registru. Společný "
        "identifikátor neexistuje, spojení se skládá z nepřímých indicií. "
        "Není to úřední doklad o tom, že smlouva vznikla z toho usnesení."
    ),
    "identita_povinna": (
        "Spojení se uloží jen tehdy, když je v textu usnesení IČO nebo název "
        "protistrany. Samotná shoda částky a data je náhoda, ne důvod."
    ),
    "jistota": {
        "vysoka": ("v usnesení je IČO protistrany (nebo číslo smlouvy), sedí částka "
                   "— i po přepočtu DPH — a smlouva je podepsaná po usnesení"),
        "stredni": "identita a čas sedí, ale chybí jedna z tvrdých indicií",
        "nizka": ("identita sedí, zbytek ne. Web to MUSÍ označit jako "
                  "nepotvrzenou domněnku, ne jako zjištění."),
        "varovani": "jen v poli podpis_pred_usnesenim, není to shoda",
    },
    "dph": ("Bod usnesení běžně schvaluje cenu bez DPH, registr uvádí částku "
            "včetně. Zkouší se sazby " + ", ".join(f"{s} %" for s in SAZBY_DPH)
            + " v obou směrech."),
    "cas": (f"Hledá se podpis do {OKNO_SIROKE} dní po usnesení. Podpis PŘED "
            "usnesením není shoda — je v poli podpis_pred_usnesenim."),
    "sklonovani": ("Názvy se v usneseních skloňují, hledá se proto kmen slova. "
                   "Shoda podle názvu je tím měkčí než shoda podle IČO."),
    "vice_kandidatu": (f"U jedné smlouvy se ukládá až {MAX_KANDIDATU} bodů, když mají "
                       "srovnatelné skóre. Rámcová smlouva a její dodatky se "
                       "schvalují opakovaně a vybrat jeden bod by bylo hádání."),
    "mesto_neni_identita": ("Název ani IČO města se jako identitní signál nepoužívá — "
                            "je v každém usnesení."),
    "registr_od": (f"Registr smluv běží od {REGISTR_OD}. Starší usnesení do seznamu "
                   "schválených částek bez smlouvy nevstupují."),
    "prah_velke": f"Za velkou se považuje částka od {PRAH_VELKE_CZK} Kč.",
    "nespojene": ("Chybějící usnesení u velké smlouvy může znamenat chybu tohoto "
                  "párování i to, že se o smlouvě nehlasovalo. Ukládá se fakt, "
                  "výklad zůstává na čtenáři."),
}


def main() -> int:
    log = Log("retez")
    try:
        body = nacti_body(log)
        smlouvy = nacti_smlouvy(log)
        penize = nacti_penize(log)

        retezy, pred = spoj(log, body, smlouvy, penize)
        stat = _statistika(retezy, pred, body, smlouvy)
        log.info("řetězů", celkem=stat["retezu"], **stat["dle_jistoty"],
                 pred_usnesenim=stat["podpis_pred_usnesenim"])

        dnes = datetime.now(timezone.utc).date().isoformat()
        uloz("retez/retezy.json", {
            "generovano": dnes,
            "zdroj": "data/usneseni + data/penize/smlouvy (Hlídač státu — registr smluv)",
            "metodika": METODIKA,
            "statistika": stat,
            "retezy": retezy,
            "podpis_pred_usnesenim": pred,
        })

        nesp = nespojene(log, body, smlouvy, retezy, pred)
        uloz("retez/nespojene.json", {
            "generovano": dnes,
            "prah_czk": PRAH_VELKE_CZK,
            "metodika": {
                "smlouvy_bez_usneseni": METODIKA["nespojene"],
                "usneseni_bez_smlouvy": METODIKA["registr_od"],
                "limit_registru": ("Smlouvy do 50 000 Kč se do registru nezveřejňují. "
                                   "Sleduje se proto jen hranice od "
                                   f"{PRAH_VELKE_CZK} Kč."),
                "protistrana_neurcena": ("U těchto smluv zdroj neuvedl druhou stranu. "
                                         "Nespojení je vada dat, ne nález."),
            },
            "pocty": {
                "smlouvy_bez_usneseni": len(nesp["smlouvy"]),
                "usneseni_bez_smlouvy": len(nesp["usneseni"]),
            },
            "smlouvy_bez_usneseni": nesp["smlouvy"],
            "usneseni_bez_smlouvy": nesp["usneseni"],
        })
        log.pricti(len(retezy))
    except ZdrojSelhal as e:
        log.chyba(str(e))
        log.uzavri()
        return 1
    log.uzavri()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
