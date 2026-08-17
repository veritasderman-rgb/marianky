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
usnesení smlouvu povolilo. Každé spojení v `retezy.json` je proto **domněnka
složená z nepřímých indicií** — shody IČO, názvu, částky a času.

Každý řetěz proto nese `jistota` a `duvod`. Web MUSÍ jistotu zobrazit;
řetěz s `jistota: "nizka"` se nesmí prezentovat jako fakt. Falešné spojení
„usnesení → smlouva" je horší než žádné: tvrdilo by, že se konkrétní
politici usnesli na konkrétní zakázce, což je vážné obvinění.

Zásada: **bez identitní shody se spojení neukládá.** Samotná shoda částky
a data je náhoda, kterou nelze odůvodnit — a co nedokážeme odůvodnit,
to neuložíme.

--------------------------------------------------------------------------
Co data ze své podstaty neumí
--------------------------------------------------------------------------
1. **Registr smluv začal 1. 7. 2016.** Usnesení máme od roku 2012. Pro
   usnesení starší než polovina roku 2016 tedy „nenalezená smlouva"
   neznamená vůbec nic — smlouva v registru prostě být nemůže. Do seznamu
   schválených částek bez smlouvy proto vstupují jen usnesení od 2016-07-01.
2. **Do registru se nezveřejňují smlouvy do 50 000 Kč.** Malé schválené
   částky bez smlouvy nejsou podezřelé, jen mimo dosah zdroje.
3. **Jména fyzických osob jsou v usneseních anonymizovaná** (`*****`).
   Smlouvy s fyzickými osobami tedy podle jména spárovat nelze; zbývá
   jen IČO, které u nich zdroj často nemá.
4. **U 687 smluv zdroj neuvedl protistranu** — v datech je místo ní
   samotný zveřejňující subjekt. Takovou smlouvu nelze párovat podle
   identity vůbec; je to označeno v `nespojene.json` polem
   `protistrana_neurcena`.
5. **Město samo se jako protistrana pro párování nepoužívá.** Řetězec
   „Rada města Mariánské Lázně schvaluje…" je v každém usnesení, takže
   jméno ani IČO města nenesou žádnou informaci o tom, které usnesení
   ke smlouvě patří.

--------------------------------------------------------------------------
Smlouva podepsaná PŘED usnesením
--------------------------------------------------------------------------
Není to shoda, je to varovný signál — a proto je v `retezy.json` zvlášť,
v poli `podpis_pred_usnesenim`. Může jít o dodatečné schválení, o dodatek
ke starší smlouvě, nebo jen o špatné datum ve zdroji. Ukládá se fakt
(identita sedí, částka sedí, podpis je dřív), výklad se nechává na čtenáři.
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

# Registr smluv běží od 1. 7. 2016. Starší usnesení se do „schváleno,
# ale smlouva nenalezena" nepočítají — nebylo by co najít.
REGISTR_OD = "2016-07-01"

# „Velká" smlouva / „velká" schválená částka pro soubor nespojených.
# 1 mil. Kč = zhruba horní desetina obou rozdělení (799 z 5 626 smluv
# s uvedenou cenou, 449 z 3 877 bodů usnesení od poloviny roku 2016).
PRAH_VELKE_CZK = 1_000_000

# Město samo — jako protistrana nenese identitní informaci.
ICO_MESTA = "00254061"

# Časová okna mezi usnesením a podpisem smlouvy (ve dnech).
OKNO_TESNE = 120       # typický průběh: schválí se a do čtvrt roku podepíše
OKNO_BEZNE = 365
OKNO_SIROKE = 730      # dál už čas nic nedokazuje
OKNO_PRED = 545        # jak daleko zpět hledat podpis PŘED usnesením

# Sazby DPH: bod usnesení běžně schvaluje cenu bez DPH, registr uvádí
# částku včetně. Zkouší se i opačný směr (usnesení s DPH, registr bez).
SAZBY_DPH = {"1.21": 1.21, "1.15": 1.15, "1.12": 1.12}

# Minimum bodů, pod kterým se spojení neukládá vůbec.
PRAH_ULOZIT = 62
PRAH_STREDNI = 78
PRAH_VYSOKA = 96

# Kolik nejlepších usnesení si u jedné smlouvy necháme. Když je shoda
# nerozhodná (rámcová smlouva + dodatky), je poctivější nabídnout několik
# kandidátů než jednoho vylosovat.
MAX_KANDIDATU = 3

# Bezobsažná slova — do překryvu předmětu smlouvy a názvu bodu nevstupují.
STOPSLOVA = {
    "mesto", "mestem", "mesta", "marianske", "lazne", "lazni", "lazenske",
    "smlouva", "smlouvy", "smlouve", "smlouvou", "dodatek", "dodatku",
    "uzavreni", "uzavrenie", "schvaluje", "souhlas", "souhlasu", "navrh",
    "rada", "rady", "zastupitelstvo", "zastupitelstva", "poskytnuti",
    "verejne", "verejneho", "verejnou", "cast", "casti", "roku", "rok",
    "pro", "por", "the", "ktere", "ktery", "ostatni", "dalsi", "mezi",
    "spolecnost", "spolecnosti", "firma", "sro", "ceske", "republiky",
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


# Právní formy — „SLEPIČKA s.r.o." se v usnesení může psát jako
# „Slepička, spol. s r. o." i „firma Slepička". Jádro je „slepicka".
_PRAVNI_FORMY = re.compile(
    r"\b(s r o|spol s r o|spol|a s|akciova spolecnost|"
    r"z s|z u|o p s|o s|k s|v o s|se|s e|p o|"
    r"prispevkova organizace|spolecnost s rucenim omezenym|"
    r"ustav|zapsany spolek|zapsany ustav|"
    r"vienna insurance group|v likvidaci|"
    r"sro|as)\b"
)

# Názvy, které jako identitní signál nefungují: buď je to město samo,
# nebo zdroj místo protistrany uvedl zástupný text.
_NEPOUZITELNE_JADRO = {
    "mesto marianske lazne",
    "marianske lazne",
    "udaj neni verejny na zaklade 5 odst 6 zakona c 340 2015 sb o registru smluv",
    "fyzicka osoba",
    "neuvedeno",
    "neuvedena",
}


def _jadro_nazvu(nazev: str) -> str:
    """Jádro názvu protistrany bez právní formy — to se hledá v usnesení."""
    x = _normalizuj(nazev)
    x = _PRAVNI_FORMY.sub(" ", x)
    x = re.sub(r"\s+", " ", x).strip()
    return x


# IČO v textu usnesení: „IČO: 47116617", „IČ 024 25 491", „IČO:47116617".
# Číslice se v zápisech oddělují mezerami, proto se mezery uvnitř povolují
# a až potom vyhodí.
_ICO_RE = re.compile(r"I[ČC]O?\s*[:.]?\s*(\d[\d ]{4,10}\d)", re.IGNORECASE)


def _ica_z_textu(text: str) -> set[str]:
    """Vytáhne z textu IČO. Doplňuje vedoucí nuly, delší číslo než 8 zahodí."""
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
    korene = sorted((DATA / "usneseni").glob("*/*/*.json"))
    if not korene:
        raise ZdrojSelhal(
            "Nenalezena žádná data/usneseni/**/*.json — nejdřív spusť scrapers/usneseni.py"
        )
    body: list[dict] = []
    for cesta in korene:
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
    log.info("načteno bodů usnesení", pocet=len(body), zapisu=len(korene))
    return body


def nacti_smlouvy(log: Log) -> list[dict]:
    """Všechny smlouvy všech sledovaných subjektů jako plochý seznam."""
    soubory = sorted((DATA / "penize" / "smlouvy").glob("*.json"))
    if not soubory:
        raise ZdrojSelhal(
            "Nenalezena žádná data/penize/smlouvy/*.json — nejdřív spusť scrapers/hlidac.py"
        )
    smlouvy: list[dict] = []
    for cesta in soubory:
        obsah = nacti(cesta)
        subjekt_ico = obsah.get("ico") or cesta.stem
        subjekt_nazev = obsah.get("nazev") or ""
        for s in obsah.get("smlouvy", []):
            protistrana_ico = (s.get("protistrana_ico") or "").strip()
            # Zdroj u části smluv místo protistrany zopakoval sám subjekt —
            # protistrana je tím pádem neznámá, ne že by to bylo město.
            neurcena = (protistrana_ico == subjekt_ico)
            smlouvy.append({
                **s,
                "subjekt_ico": subjekt_ico,
                "subjekt": subjekt_nazev,
                "_den": _den(s.get("datum") or ""),
                "_ico": "" if neurcena else protistrana_ico,
                "_jadro": "" if neurcena else _jadro_nazvu(s.get("protistrana") or ""),
                "_protistrana_neurcena": neurcena,
                "_cisla": _cisla_smlouvy(s.get("predmet") or ""),
                "_slova": _obsahova_slova(s.get("predmet") or ""),
            })
    log.info("načteno smluv", pocet=len(smlouvy), subjektu=len(soubory))
    return smlouvy


def nacti_penize() -> dict[str, dict]:
    """Agregace protistran — klíč IČO, jinak slug názvu. Konec řetězu: peníze."""
    agr = nacti("penize/agregace/protistrany.json")
    if not agr:
        raise ZdrojSelhal(
            "Chybí data/penize/agregace/protistrany.json — nejdřív spusť pipeline/agregace_penez.py"
        )
    out: dict[str, dict] = {}
    for p in agr.get("protistrany", []):
        klic = p["ico"] if p.get("klic_dle") == "ico" else f"nazev:{p['ico']}"
        out[klic] = p
    return out


# --------------------------------------------------------------------------
# Rejstříky pro rychlé hledání kandidátů
# --------------------------------------------------------------------------

def _rejstriky(body: list[dict]) -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    """Vrací (IČO → indexy bodů, slovo → indexy bodů)."""
    dle_ica: dict[str, list[int]] = defaultdict(list)
    dle_slova: dict[str, list[int]] = defaultdict(list)
    for i, b in enumerate(body):
        for ico in b["_ica"]:
            dle_ica[ico].append(i)
        for slovo in set(b["_norm"].split()):
            if len(slovo) >= 3:
                dle_slova[slovo].append(i)
    return dle_ica, dle_slova


def _body_dle_jadra(jadro: str, body: list[dict], dle_slova: dict[str, list[int]]) -> list[int]:
    """Indexy bodů, jejichž text obsahuje celé jádro názvu protistrany."""
    tokeny = [t for t in jadro.split() if len(t) >= 3]
    if not tokeny:
        return []
    # Průnik přes nejvzácnější token — ušetří procházení celého korpusu.
    tokeny.sort(key=lambda t: len(dle_slova.get(t, ())))
    kandidati = set(dle_slova.get(tokeny[0], ()))
    for t in tokeny[1:]:
        kandidati &= set(dle_slova.get(t, ()))
        if not kandidati:
            return []
    # Tokeny mohou být v textu roztroušené — ověř, že jde o souvislý název.
    return [i for i in kandidati if jadro in body[i]["_norm"]]


# --------------------------------------------------------------------------
# Jednotlivé signály
# --------------------------------------------------------------------------

def _shoda_castky(castka_bodu, castka_smlouvy) -> tuple[str, str] | None:
    """Shoda částek. Vrací (kód, lidský popis), nebo None."""
    if not castka_bodu or not castka_smlouvy:
        return None
    a, b = float(castka_bodu), float(castka_smlouvy)
    if a <= 0 or b <= 0:
        return None

    def sedi(x: float, y: float) -> bool:
        return abs(x - y) <= max(1.0, 0.004 * max(x, y))

    if sedi(a, b):
        return ("castka_presna", "částka bodu a smlouvy sedí přesně")
    for popis, sazba in SAZBY_DPH.items():
        if sedi(a * sazba, b):
            procent = round((sazba - 1) * 100)
            return (f"castka_dph_{procent}",
                    f"částka bodu odpovídá částce smlouvy po připočtení {procent} % DPH")
        if sedi(a, b * sazba):
            procent = round((sazba - 1) * 100)
            return (f"castka_dph_obraceně_{procent}",
                    f"částka bodu odpovídá částce smlouvy s {procent} % DPH navíc "
                    f"(bod uvedl cenu včetně daně)")
    return None


def _body_za_castku(castka: float | int) -> int:
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


def _ohodnot(bod: dict, smlouva: dict, distinktivni: bool) -> dict | None:
    """Sečte indicie pro jednu dvojici. None = nedá se odůvodnit."""
    if bod["den"] is None or smlouva["_den"] is None:
        return None
    odstup = (smlouva["_den"] - bod["den"]).days

    signaly: list[str] = []
    duvody: list[str] = []
    skore = 0

    # --- identita (bez ní se neukládá nic) ---
    if smlouva["_ico"] and smlouva["_ico"] in bod["_ica"]:
        skore += 50
        signaly.append("ico")
        duvody.append(f"IČO {smlouva['_ico']} je uvedeno v textu usnesení")
    if smlouva["_jadro"] and smlouva["_jadro"] in bod["_norm"]:
        if "ico" in signaly:
            skore += 12
            signaly.append("nazev")
            duvody.append("v textu usnesení je i název protistrany")
        else:
            skore += 38 if distinktivni else 24
            signaly.append("nazev")
            duvody.append(f"název protistrany „{smlouva.get('protistrana')}" "
                          f"je uveden v textu usnesení")
    if not signaly:
        return None

    # --- číslo smlouvy ---
    for cislo in smlouva["_cisla"]:
        if cislo in bod["_norm"] or re.sub(r"\D", "", cislo) in bod["_norm"]:
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
        if odstup <= OKNO_TESNE:
            signaly.append("cas_tesne")
        elif odstup <= OKNO_BEZNE:
            signaly.append("cas_bezne")
        elif odstup <= OKNO_SIROKE:
            signaly.append("cas_siroke")
        else:
            signaly.append("cas_mimo")
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


def _jistota(hodnoceni: dict) -> str:
    """Převod skóre a signálů na tři stupně, které web ukazuje čtenáři."""
    s, sig = hodnoceni["skore"], set(hodnoceni["signaly"])
    ma_castku = any(x.startswith("castka_") for x in sig)
    ma_identitu_tvrdou = "ico" in sig or "cislo_smlouvy" in sig
    v_case = bool({"cas_tesne", "cas_bezne", "cas_siroke"} & sig)

    if s >= PRAH_VYSOKA and v_case and ma_identitu_tvrdou and (ma_castku or "cislo_smlouvy" in sig):
        return "vysoka"
    if s >= PRAH_STREDNI and v_case:
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


def _vystup_penez(s: dict, penize: dict[str, dict]) -> dict | None:
    """Konec řetězu: co ta protistrana od města dostala celkem."""
    p = penize.get(s["_ico"]) if s["_ico"] else None
    if p is None and s["_jadro"]:
        klic = slug(s.get("protistrana") or "")
        p = penize.get(f"nazev:{klic}")
    if p is None:
        return None
    return {
        "protistrana_celkem_czk": p.get("celkem_czk"),
        "protistrana_smluv": p.get("smluv"),
        "prvni_rok": p.get("prvni_rok"), "posledni_rok": p.get("posledni_rok"),
        "aktivni": p.get("aktivni"), "interni": p.get("interni"),
    }


def spoj(log: Log, body: list[dict], smlouvy: list[dict], penize: dict[str, dict]) -> tuple[list, list]:
    dle_ica, dle_slova = _rejstriky(body)

    # Jak často se které jádro názvu v usneseních vyskytuje. Název, který je
    # skoro všude („karlovarsky kraj"), o konkrétní smlouvě neříká nic.
    cache_jadra: dict[str, list[int]] = {}

    def kandidati_dle_jmena(jadro: str) -> list[int]:
        if jadro not in cache_jadra:
            cache_jadra[jadro] = _body_dle_jadra(jadro, body, dle_slova)
        return cache_jadra[jadro]

    retezy: list[dict] = []
    pred: list[dict] = []
    preskoceno_bez_identity = 0

    for s in smlouvy:
        if s["_den"] is None:
            continue
        # Město jako protistrana není identita — je to v každém usnesení.
        if s["_ico"] == ICO_MESTA or s["_jadro"] in _NEPOUZITELNE_JADRO:
            s["_ico"], s["_jadro"] = "", ""
        if not s["_ico"] and not s["_jadro"]:
            preskoceno_bez_identity += 1
            continue

        idx: set[int] = set()
        if s["_ico"]:
            idx |= set(dle_ica.get(s["_ico"], ()))
        vyskyty_jmena = 0
        if s["_jadro"] and len(s["_jadro"]) >= 5:
            nalezene = kandidati_dle_jmena(s["_jadro"])
            vyskyty_jmena = len(nalezene)
            idx |= set(nalezene)
        if not idx:
            continue

        # Jméno, které je v usneseních rozeseté po stovkách bodů, je slabší
        # identita než jméno, které padne na hrstku bodů.
        distinktivni = 0 < vyskyty_jmena <= 60

        hodnoceni: list[tuple[dict, dict]] = []
        for i in idx:
            b = body[i]
            if b["den"] is None:
                continue
            odstup = (s["_den"] - b["den"]).days
            if odstup > OKNO_SIROKE or odstup < -OKNO_PRED:
                continue
            h = _ohodnot(b, s, distinktivni)
            if h:
                hodnoceni.append((b, h))
        if not hodnoceni:
            continue

        hodnoceni.sort(key=lambda x: (-x[1]["skore"], abs(x[1]["odstup_dni"])))

        # --- podpis před usnesením: samostatná hromádka, ne shoda ---
        zpetne = [(b, h) for b, h in hodnoceni
                  if h["odstup_dni"] < 0
                  and (any(x.startswith("castka_") for x in h["signaly"])
                       or "cislo_smlouvy" in h["signaly"])]
        for b, h in zpetne[:1]:
            pred.append(_retez(b, s, h, penize, jistota_override="varovani"))

        dopredne = [(b, h) for b, h in hodnoceni if h["odstup_dni"] >= 0]
        if not dopredne:
            continue
        nejlepsi = dopredne[0][1]["skore"]
        if nejlepsi < PRAH_ULOZIT:
            continue
        for b, h in dopredne[:MAX_KANDIDATU]:
            if h["skore"] < PRAH_ULOZIT or h["skore"] < nejlepsi - 12:
                break
            retezy.append(_retez(b, s, h, penize))

    log.info("smluv bez použitelné identity protistrany", pocet=preskoceno_bez_identity)
    retezy.sort(key=lambda r: (r["smlouva"]["datum"] or "", r["smlouva"]["id"] or ""))
    pred.sort(key=lambda r: (r["smlouva"]["datum"] or "", r["smlouva"]["id"] or ""))
    return retezy, pred


def _retez(bod: dict, smlouva: dict, h: dict, penize: dict[str, dict],
           jistota_override: str | None = None) -> dict:
    jistota = jistota_override or _jistota(h)
    return {
        "id": f"{bod['organ']}-{bod['datum'][:4]}-{bod['bod']}__{smlouva.get('id')}",
        "jistota": jistota,
        "skore": h["skore"],
        "signaly": h["signaly"],
        "duvod": "; ".join(h["duvody"]),
        "odstup_dni": h["odstup_dni"],
        "usneseni": _vystup_bodu(bod),
        "smlouva": _vystup_smlouvy(smlouva),
        "penize": _vystup_penez(smlouva, penize),
    }


# --------------------------------------------------------------------------
# Nespojené — stejně cenný výstup jako spojené
# --------------------------------------------------------------------------

def nespojene(log: Log, body: list[dict], smlouvy: list[dict],
              retezy: list[dict], pred: list[dict]) -> dict:
    """Velké smlouvy bez nalezeného usnesení a velké schválené částky bez smlouvy.

    Nepíše se, co to znamená. Chybějící usnesení může být chyba tohoto
    párování stejně dobře jako smlouva, o které se nehlasovalo.
    """
    spojene_smlouvy = {r["smlouva"]["id"] for r in retezy} | {r["smlouva"]["id"] for r in pred}
    spojene_body = {(r["usneseni"]["organ"], r["usneseni"]["bod"]) for r in retezy}

    smlouvy_bez: list[dict] = []
    for s in smlouvy:
        c = s.get("castka_czk") or 0
        if c < PRAH_VELKE_CZK or s.get("id") in spojene_smlouvy:
            continue
        smlouvy_bez.append({
            **_vystup_smlouvy(s),
            "protistrana_neurcena": s["_protistrana_neurcena"],
            "poznamka": ("zdroj u této smlouvy neuvedl protistranu, párovat podle identity nelze"
                         if s["_protistrana_neurcena"] else
                         "protistrana je uvedena, ale v žádném usnesení se nenašla"),
        })

    usneseni_bez: list[dict] = []
    for b in body:
        c = b.get("castka_czk") or 0
        if c < PRAH_VELKE_CZK:
            continue
        if b["datum"] < REGISTR_OD:
            continue  # smlouva by v registru nebyla, tady by to nic neznamenalo
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
        "identifikátor neexistuje, spojení se skládá z nepřímých indicií."
    ),
    "identita_povinna": (
        "Spojení se uloží jen tehdy, když je v textu usnesení IČO nebo název "
        "protistrany. Samotná shoda částky a data je náhoda, ne důvod."
    ),
    "jistota": {
        "vysoka": ("v usnesení je IČO protistrany nebo číslo smlouvy, sedí částka "
                   "(i po přepočtu DPH) a smlouva je podepsaná po usnesení"),
        "stredni": "identita a čas sedí, ale chybí jedna z tvrdých indicií",
        "nizka": ("identita sedí, zbytek ne — web to MUSÍ označit jako "
                  "nepotvrzenou domněnku"),
    },
    "dph": ("Bod usnesení běžně schvaluje cenu bez DPH, registr uvádí částku "
            f"včetně. Zkouší se sazby {', '.join(SAZBY_DPH)} v obou směrech."),
    "cas": (f"Hledá se podpis do {OKNO_SIROKE} dní po usnesení. Podpis PŘED "
            "usnesením není shoda — je v poli podpis_pred_usnesenim."),
    "vice_kandidatu": (f"U jedné smlouvy se ukládá až {MAX_KANDIDATU} bodů, když mají "
                       "srovnatelné skóre. Rámcová smlouva a její dodatky se "
                       "schvalují opakovaně a vybrat jeden bod by bylo hádání."),
    "mesto_neni_identita": ("Název ani IČO města se jako identitní signál nepoužívá — "
                            "je v každém usnesení."),
    "registr_od": (f"Registr smluv běží od {REGISTR_OD}. Usnesení starší než toto "
                   "datum se do seznamu „schváleno, smlouva nenalezena" nepočítají."),
    "prah_velke": f"Za velkou se považuje částka od {PRAH_VELKE_CZK} Kč.",
    "nespojene": ("Chybějící usnesení u velké smlouvy může znamenat chybu tohoto "
                  "párování i to, že se o smlouvě nehlasovalo. Ukládá se fakt, "
                  "výklad se nechává na čtenáři."),
}


def main() -> int:
    log = Log("retez")
    try:
        body = nacti_body(log)
        smlouvy = nacti_smlouvy(log)
        penize = nacti_penize()

        retezy, pred = spoj(log, body, smlouvy, penize)
        stat = _statistika(retezy, pred, body, smlouvy)
        log.info("řetězů", **stat["dle_jistoty"], celkem=stat["retezu"],
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
                "smlouvy": METODIKA["nespojene"],
                "usneseni": METODIKA["registr_od"],
                "limit_registru": ("Smlouvy do 50 000 Kč se do registru nezveřejňují, "
                                   "proto se sleduje jen hranice od "
                                   f"{PRAH_VELKE_CZK} Kč."),
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
