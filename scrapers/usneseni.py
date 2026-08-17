"""Sběrač usnesení rady a zastupitelstva z portálu usneseni.muml.cz.

Jak portál doopravdy funguje (ověřeno 17. 8. 2026):

* Stránky jsou serverové HTML, ale **výpisy tabulek jsou AJAX**. Tabulky
  DataTables tahají data z `/{organ}/ajax/list/...` a bez hlavičky
  `X-Requested-With: XMLHttpRequest` server vrátí 500. Proto si tenhle modul
  drží vlastní tenkého klienta `ajax()` — `core.fetch()` posílá jen
  User-Agent a umí GET, ne POST s vlastní hlavičkou.
* Odpověď na detail usnesení nese `Content-Type: text/html` **bez charset**,
  takže `requests` hádá ISO-8859-1 a čeština se rozsype. Stahujeme proto
  binárně a dekódujeme UTF-8 sami — `stahni()`.
* Seznam jednání je v `<select name="meeting_id">` na výpisu usnesení.
  Číslování č. j. se resetuje s volebním obdobím, takže samotné č. j. není
  klíč — období se dopočítává z detekce resetů, ne z natvrdo psané tabulky.

Výstup podle PLAN.md: `data/usneseni/{organ}/{rok}/{cj}.json`.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from selectolax.parser import HTMLParser

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import core  # noqa: E402
from pipeline.tagovani import navrhni_tagy  # noqa: E402

PORTAL = "https://usneseni.muml.cz"
ORGANY = ("rada", "zastupitelstvo")

# Kolik detailů usnesení tahat naráz. Portál je malý PHP web na openresty,
# takže spíš pomalu a jistě — plný archiv je 12 890 stránek a jede se jednou.
SOUBEZNE = 8
PAUZA = 0.05  # s, mezi požadavky jednoho vlákna

# Popisky ve vodorovné tabulce hlasování na detailu usnesení.
HLASY_MAPA = {
    "Pro": "pro",
    "Proti": "proti",
    "Zdržel se": "zdrzel",
    "Nehlasoval": "nehlasoval",
    "Omluven": "omluven",
    "Nepřítomen": "nepritomen",
}

# Portál používá jediný popisek výsledku; kdyby přibyl další, chceme o tom vědět.
VYSLEDKY_MAPA = {
    "schváleno": "schvaleno",
    "neschváleno": "neschvaleno",
    "staženo": "staženo",
    "odloženo": "odlozeno",
}

# Text, kterým portál nahrazuje kartu hlasování, když hlasy nejsou k dispozici.
BEZ_HLASOVANI = "Výsledky hlasování se zpracovávají"


# --------------------------------------------------------------------------
# HTTP klient portálu
# --------------------------------------------------------------------------

_mistni = threading.local()


def _sezeni() -> requests.Session:
    """Session na vlákno — keep-alive ušetří portálu tisíce TLS handshaků."""
    s = getattr(_mistni, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": core.UA, "Accept-Language": "cs,en;q=0.8"})
        _mistni.session = s
    return s


def stahni(url: str, *, max_age: int = 30 * 86_400) -> str:
    """Stáhne HTML stránku portálu s diskovou cache, jako `core.fetch`.

    Proč ne rovnou `core.fetch()`: ta otevírá pro každý požadavek nové spojení,
    což je na 12 890 detailech usnesení 12 890 TLS handshaků a zdržení 0,67 s
    na stránku místo 0,26 s. Tady se drží session na vlákno.

    Dekóduje se ručně z bajtů — portál posílá `Content-Type: text/html` bez
    charsetu a requests by češtinu přečetl jako ISO-8859-1.
    """
    klic = hashlib.sha256(url.encode()).hexdigest()[:24]
    soubor = core.CACHE / "portal" / f"{klic}.html"
    if max_age and soubor.exists() and (time.time() - soubor.stat().st_mtime) < max_age:
        return soubor.read_text(encoding="utf-8")

    posledni: Exception | None = None
    for pokus in range(4):
        try:
            r = _sezeni().get(url, timeout=60)
            if r.status_code == 429 or 500 <= r.status_code < 600:
                raise core.ZdrojSelhal(f"HTTP {r.status_code} u {url}")
            r.raise_for_status()
            html = r.content.decode("utf-8")
            soubor.parent.mkdir(parents=True, exist_ok=True)
            soubor.write_text(html, encoding="utf-8")
            return html
        except Exception as e:  # noqa: BLE001 — opakujeme na čemkoliv síťovém
            posledni = e
            if pokus < 3:
                time.sleep(2 ** (pokus + 1))
    raise core.ZdrojSelhal(f"Nepodařilo se stáhnout {url} ani na 4 pokusy: {posledni}")


def ajax(organ: str, cesta: str, *, filtr: dict | None = None, max_age: int = 6 * 3600) -> list[dict]:
    """Zavolá DataTables endpoint portálu a vrátí řádky.

    `recordsTotal` v odpovědi je při filtrování NEPRAVDIVÉ (portál ho nepřepočítá),
    takže se řídíme délkou pole `data` a nikdy tím číslem.
    """
    url = f"{PORTAL}/{organ}/ajax/list/{cesta}"
    data = {"start": 0, "length": 100_000}
    for k, v in (filtr or {}).items():
        data[f"filter[{k}]"] = v

    klic = hashlib.sha256(f"{url}|{sorted(data.items())}".encode()).hexdigest()[:24]
    soubor = core.CACHE / "ajax" / f"{klic}.json"
    if max_age and soubor.exists() and (time.time() - soubor.stat().st_mtime) < max_age:
        return json.loads(soubor.read_text(encoding="utf-8"))

    posledni: Exception | None = None
    for pokus in range(4):
        try:
            r = _sezeni().post(
                url, data=data, timeout=120,
                headers={"X-Requested-With": "XMLHttpRequest"},  # bez ní portál vrací 500
            )
            if r.status_code == 429 or 500 <= r.status_code < 600:
                raise core.ZdrojSelhal(f"HTTP {r.status_code} u {url}")
            r.raise_for_status()
            # Před JSONem umí PHP vypsat notice; bereme až od první složené závorky.
            telo = r.content.decode("utf-8", errors="replace")
            zacatek = telo.find('{"recordsTotal')
            if zacatek < 0:
                raise core.ZdrojSelhal(f"{url} nevrátil JSON DataTables: {telo[:200]!r}")
            radky = json.loads(telo[zacatek:])["data"]
            soubor.parent.mkdir(parents=True, exist_ok=True)
            soubor.write_text(json.dumps(radky, ensure_ascii=False), encoding="utf-8")
            return radky
        except Exception as e:  # noqa: BLE001 — opakujeme na čemkoliv síťovém
            posledni = e
            if pokus < 3:
                time.sleep(2 ** (pokus + 1))
    raise core.ZdrojSelhal(f"AJAX {url} selhal ani na 4 pokusy: {posledni}")


# --------------------------------------------------------------------------
# Jednání a volební období
# --------------------------------------------------------------------------

def jednani(organ: str) -> list[dict]:
    """Všechna jednání orgánu z rozbalovacího seznamu na výpisu usnesení.

    Vrací chronologicky vzestupně: {id, datum, cj, rok, obdobi}.
    """
    html = stahni(f"{PORTAL}/{organ}/usneseni", max_age=3600)
    strom = HTMLParser(html)
    vyber = strom.css_first("select[name=meeting_id]")
    if vyber is None:
        raise core.ZdrojSelhal(f"{organ}: na výpisu usnesení chybí seznam jednání")

    seznam: list[dict] = []
    for volba in vyber.css("option"):
        hodnota = volba.attributes.get("value")
        if not hodnota:
            continue  # "- vše -"
        popis = volba.text(strip=True)
        datum = core.parse_datum(popis)
        cislo = re.search(r"č\.\s*j\.\s*(\d+)", popis)
        if not datum or not cislo:
            raise core.ZdrojSelhal(f"{organ}: nečitelná položka jednání {popis!r}")
        seznam.append({"id": hodnota, "datum": datum, "cj": int(cislo.group(1)), "rok": int(datum[:4])})

    if not seznam:
        raise core.ZdrojSelhal(f"{organ}: seznam jednání je prázdný")

    seznam.sort(key=lambda j: (j["datum"], j["cj"]))
    _doplnit_obdobi(seznam)
    return seznam


def _doplnit_obdobi(seznam: list[dict]) -> None:
    """Přiřadí volební období podle skutečných resetů číslování č. j.

    Číslování se po komunálních volbách vrací na začátek, takže hranice období
    jde z dat vyčíst — a bude platit i po volbách 2026, aniž by se sem sahalo.
    Období pojmenováváme rokem prvního a posledního jednání v něm.
    """
    # Reset poznáme podle propadu z vysokého čísla na začátek řady. Pouhé
    # "menší než minule" nestačí: rada má 22. 11. 2022 mimořádné jednání
    # č. j. 0 zařazené až za č. j. 3, a to volební období nekončí.
    hranice = [0]
    for i in range(1, len(seznam)):
        if seznam[i - 1]["cj"] - seznam[i]["cj"] >= 10:
            hranice.append(i)
    hranice.append(len(seznam))

    for i, (a, b) in enumerate(zip(hranice, hranice[1:])):
        usek = seznam[a:b]
        # Konec období = rok, kdy začíná další úsek, tedy rok voleb.
        # U posledního (probíhajícího) období volby ještě nebyly, dopočítá se.
        do = seznam[b]["rok"] if b < len(seznam) else usek[0]["rok"] + 4
        # Začátek období = rok prvního jednání v úseku. Nejstarší úsek ale
        # archiv zachycuje až od jeho poloviny, tak se odvodí zpětně od voleb.
        od = do - 4 if i == 0 else usek[0]["rok"]
        for j in usek:
            j["obdobi"] = f"{od}-{do}"


# --------------------------------------------------------------------------
# Parsování detailu usnesení
# --------------------------------------------------------------------------

def _na_text(uzel) -> str:
    """Z buňky s <ul>/<li>/<br> udělá čitelný víceřádkový text.

    Bez tohohle by se odrážky usnesení slily do jedné věty a text by se
    nedal číst ani vyhledávat.
    """
    html = uzel.html or ""
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</li\s*>", "\n", html, flags=re.I)
    html = re.sub(r"<li[^>]*>", "• ", html, flags=re.I)
    html = re.sub(r"</p\s*>", "\n\n", html, flags=re.I)
    return core.cistit(HTMLParser(html).text())


def _karta(strom: HTMLParser, nadpis: str):
    for karta in strom.css("div.card"):
        hlavicka = karta.css_first("h4.card-header")
        if hlavicka and hlavicka.text(strip=True).strip() == nadpis:
            return karta.css_first(".card-body")
    return None


def _radky_tabulky(telo) -> dict[str, str]:
    """Dvousloupcová tabulka 'popisek -> hodnota' na jednoduchý slovník."""
    out: dict[str, str] = {}
    if telo is None:
        return out
    for radek in telo.css("tr"):
        bunky = radek.css("th, td")
        if len(bunky) != 2:
            continue
        popisek = re.sub(r"\s+", " ", bunky[0].text()).strip().rstrip(":").strip()
        if popisek:
            out[popisek] = re.sub(r"\s+", " ", bunky[1].text()).strip()
    return out


def parsuj_detail(html: str) -> dict:
    """Rozebere stránku jednoho usnesení.

    Vrací {nazev, text, meeting_id, cj, datum, vysledek, hlasy}. Když stránka
    nemá povinné části, vyhodí ZdrojSelhal — prázdné usnesení neukládáme.
    """
    strom = HTMLParser(html)

    podrobnosti = _karta(strom, "Podrobnosti usnesení")
    if podrobnosti is None:
        raise core.ZdrojSelhal("detail usnesení nemá kartu 'Podrobnosti usnesení'")

    nazev = text = None
    for radek in podrobnosti.css("tr"):
        bunky = radek.css("th, td")
        if len(bunky) != 2:
            continue
        popisek = bunky[0].text(strip=True).rstrip(":").strip()
        if popisek == "Ve věci":
            nazev = core.cistit(bunky[1].text())
        elif popisek == "Popis":
            text = _na_text(bunky[1])
    if not nazev:
        raise core.ZdrojSelhal("detail usnesení nemá název ('Ve věci')")

    jed = _radky_tabulky(_karta(strom, "Jednání"))
    cj = jed.get("Číslo")
    datum = core.parse_datum(jed.get("Datum", ""))
    odkaz = strom.css_first('a[href*="meeting_id="]')
    meeting_id = None
    if odkaz:
        m = re.search(r"meeting_id=(\d+)", odkaz.attributes.get("href", ""))
        meeting_id = m.group(1) if m else None

    vysledek, hlasy = None, {}
    telo = _karta(strom, "Hlasování")
    if telo is not None:
        cely = re.sub(r"\s+", " ", telo.text()).strip()
        if BEZ_HLASOVANI not in cely:
            for popisek, hodnota in _radky_tabulky(telo).items():
                if popisek == "Výsledek":
                    if hodnota not in VYSLEDKY_MAPA:
                        raise core.ZdrojSelhal(f"neznámý výsledek hlasování {hodnota!r}")
                    vysledek = VYSLEDKY_MAPA[hodnota]
                elif popisek in HLASY_MAPA and hodnota.isdigit():
                    hlasy[HLASY_MAPA[popisek]] = int(hodnota)

    return {
        "nazev": nazev,
        "text": text or "",
        "cj": int(cj) if cj and cj.isdigit() else None,
        "datum": datum,
        "meeting_id": meeting_id,
        "vysledek": vysledek,
        "hlasy": hlasy,
    }


# --------------------------------------------------------------------------
# Částky
# --------------------------------------------------------------------------

# "1 250 000 Kč", "1.250.000,- Kč", "250 000,00 Kč", "2,4 mil. Kč", "800 tis. Kč"
_CASTKA = re.compile(
    r"(\d[\d   .,]*?)\s*(mil\.?|mld\.?|tis\.?)?\s*(?:Kč|CZK)\b",
    re.IGNORECASE,
)


def _cislo(surove: str, nasobek: int) -> float | None:
    t = surove.replace(" ", "").replace(" ", "").replace(" ", "").rstrip(".,-")
    if not t or not t[0].isdigit():
        return None
    if nasobek > 1:
        # U "2,4 mil." je čárka desetinná; tečka taky ("1.5 mil.").
        t = t.replace(",", ".")
        if t.count(".") > 1:
            return None
        return float(t) * nasobek
    if "," in t:  # "250000,00" — čárka je desetinná, tečky jsou oddělovače tisíců
        t = t.replace(".", "").replace(",", ".")
    elif "." in t:
        if not re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
            return None  # "1.5" u koruny nedává smysl, radši nic než nesmysl
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None


def castka_z_textu(text: str) -> int | None:
    """Největší výslovně uvedená koruna v textu, jinak None.

    PLAN.md: nikdy nehádat. Když v usnesení částka není, vrací se `null`;
    tenhle kód nic nedopočítává, jen čte, co je napsané. Když je částek víc
    (typicky rozpis dotací), bere se nejvyšší — bývá to celková suma bodu.
    """
    nejvic = 0.0
    for surove, jednotka in _CASTKA.findall(text or ""):
        j = (jednotka or "").lower()
        nasobek = 1_000_000_000 if j.startswith("mld") else 1_000_000 if j.startswith("mil") else 1_000 if j.startswith("tis") else 1
        hodnota = _cislo(surove, nasobek)
        if hodnota is None or hodnota <= 0:
            continue
        if hodnota > 1e11:
            continue  # nad 100 mld. jde jistě o špatně přečtené číslo
        nejvic = max(nejvic, hodnota)
    return int(round(nejvic)) if nejvic else None


# --------------------------------------------------------------------------
# Sběr
# --------------------------------------------------------------------------

def hlasovani_id(organ: str, rok: int, cj: int, poradi: int) -> str:
    """Stabilní klíč hlasování. Musí sedět se sběračem hlasování — na tomhle
    stojí propojení bodu usnesení s tím, kdo jak hlasoval."""
    return f"{organ}-{rok}-{cj}-{poradi}"


def _stahni_detail(url: str) -> dict:
    html = stahni(url)
    time.sleep(PAUZA)
    return parsuj_detail(html)


_bazen: ThreadPoolExecutor | None = None


def _pracovnici() -> ThreadPoolExecutor:
    """Jeden bazén vláken na celý běh.

    Zásadní pro rychlost: vlákna si drží HTTP session, takže spojení k portálu
    zůstávají otevřená. Bazén zakládaný na každé jednání zvlášť je pokaždé
    zahodí a stahování spadne z 12 stránek za sekundu na 3.
    """
    global _bazen
    if _bazen is None:
        _bazen = ThreadPoolExecutor(SOUBEZNE)
    return _bazen


def zpracuj_jednani(organ: str, jed: dict, log: core.Log) -> dict | None:
    """Sestaví jeden záznam jednání se všemi body usnesení."""
    radky = ajax(organ, "decrees", filtr={"meeting_id": jed["id"]}, max_age=6 * 3600)
    if not radky:
        log.chyba(f"{organ} č. j. {jed['cj']} ({jed['datum']}): jednání nemá žádná usnesení")
        return None

    # Portál řadí od nejnovějšího; číslujeme v pořadí, v jakém se jednalo.
    radky.sort(key=lambda r: r.get("number_index") or 0)
    odkazy = [r["DT_RowAttr"]["data-link"] for r in radky]

    detaily = list(_pracovnici().map(_stahni_detail, odkazy))

    body = []
    for poradi, (radek, detail, url) in enumerate(zip(radky, detaily, odkazy), start=1):
        if detail["meeting_id"] and detail["meeting_id"] != jed["id"]:
            log.chyba(f"{url}: detail hlásí jiné jednání ({detail['meeting_id']} vs {jed['id']})")
            continue
        hid = hlasovani_id(organ, jed["rok"], jed["cj"], poradi)
        body.append({
            "cislo": f"{jed['cj']}/{poradi}",
            "cislo_usneseni": radek.get("number"),   # oficiální číslo, např. "1397/26"
            "nazev": detail["nazev"],
            "text": detail["text"],
            "tagy": navrhni_tagy(detail["nazev"], detail["text"]),
            "castka_czk": castka_z_textu(detail["text"]),
            # Výsledek hlasování je na portálu jen na detailu usnesení. Ukládá se
            # sem, aby ho sběrač hlasování nemusel dolovat znovu ze 12 349 stránek.
            "vysledek": detail["vysledek"],
            "hlasovani_id": hid if detail["vysledek"] else None,
            "url": url,
        })

    if not body:
        log.chyba(f"{organ} č. j. {jed['cj']} ({jed['datum']}): nepodařilo se rozparsovat ani jeden bod")
        return None

    return {
        "organ": organ,
        "cj": jed["cj"],
        "datum": jed["datum"],
        "obdobi": jed["obdobi"],
        "url": f"{PORTAL}/{organ}/usneseni#p:meeting_id={jed['id']}",
        "body": body,
    }


def cesta_jednani(organ: str, rok: int, cj: int) -> str:
    return f"usneseni/{organ}/{rok}/{cj}.json"


def main(od_roku: int | None = None, jen_nove: bool = True) -> dict:
    """Stáhne usnesení obou orgánů.

    `jen_nove=True` přeskočí jednání, která už na disku jsou — týdenní běh
    tak sáhne jen na to, co přibylo. Archiv se natáhne prvním během.
    """
    log = core.Log("usneseni")
    prehled = {}

    for organ in ORGANY:
        try:
            seznam = jednani(organ)
        except core.ZdrojSelhal as e:
            log.chyba(f"{organ}: {e}")
            continue

        if od_roku:
            seznam = [j for j in seznam if j["rok"] >= od_roku]
        log.info(f"{organ}: {len(seznam)} jednání ({seznam[0]['datum']} … {seznam[-1]['datum']})")

        hotovo = bodu = 0
        for j in reversed(seznam):  # od nejnovějšího — když se běh přeruší, máme aktuální
            cesta = cesta_jednani(organ, j["rok"], j["cj"])
            if jen_nove and (core.DATA / cesta).exists():
                hotovo += 1
                continue
            try:
                zaznam = zpracuj_jednani(organ, j, log)
            except core.ZdrojSelhal as e:
                log.chyba(f"{organ} č. j. {j['cj']} ({j['datum']}): {e}")
                continue
            if zaznam is None:
                continue
            core.uloz(cesta, zaznam)
            hotovo += 1
            bodu += len(zaznam["body"])
            log.pricti(len(zaznam["body"]))

        prehled[organ] = {"jednani": hotovo, "novych_bodu": bodu}
        log.info(f"{organ}: hotovo {hotovo} jednání, nových bodů {bodu}")

    if not prehled:
        raise core.ZdrojSelhal("nepodařilo se stáhnout usnesení ani jednoho orgánu")

    vysledek = log.uzavri()
    vysledek["prehled"] = prehled
    return vysledek


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Sběrač usnesení rady a zastupitelstva")
    p.add_argument("--od-roku", type=int, default=None, help="Stáhnout jen jednání od tohoto roku")
    p.add_argument("--vse", action="store_true", help="Přepsat i jednání, která už jsou uložená")
    a = p.parse_args()
    main(od_roku=a.od_roku, jen_nove=not a.vse)
