"""Sběrače oficiálního webu města — www.muml.cz.

ZÁSADA PROJEKTU: scraping dělá kód, porozumění dělá Claude.
Tady se jenom čte HTML a překlápí do strukturovaných JSONů. Žádné shrnování,
žádné hádání. Když se stránka nedá rozparsovat, letí ``ZdrojSelhal``.

Co modul umí (každá funkce zapisuje jeden soubor do ``data/mesto/``):

    uredni_deska()  → data/mesto/uredni-deska.json
    novinky()       → data/mesto/novinky.json
    akce()          → data/mesto/akce.json
    zastupitele()   → data/mesto/zastupitele.json
    urad()          → data/mesto/urad.json
    spolecnosti()   → data/mesto/spolecnosti.json

DŮLEŽITÉ ZJIŠTĚNÍ K AKCÍM: stránka ``muml.cz/aktualne/kalendar-akci/`` žádný
kalendář neobsahuje — je to jen rozcestník odkazující na turistický portál
``marianskelazne.cz/kalendar/``. Skutečná data o akcích se proto berou odtud.

RSS na muml.cz neexistuje (ověřeno — /rss, /rss.xml i /aktualne/novinky/rss
vracejí 404), takže se vše sbírá z HTML a hlídá přes ``scrapers/snapshoty.py``.
"""
from __future__ import annotations

import argparse
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlparse, urlunparse, unquote

from selectolax.parser import HTMLParser

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import core  # noqa: E402
from lib.core import ZdrojSelhal  # noqa: E402

BASE = "https://www.muml.cz"
# Kalendář akcí města fyzicky žije na turistickém portálu, ne na muml.cz.
KALENDAR = "https://www.marianskelazne.cz"

# Kolik souběžných stahování a jak dlouhá pauza po každém síťovém dotazu.
# Web města běží na malém serveru — držíme se pod ~3 dotazy za sekundu.
VLAKEN = 3
PRODLEVA_S = 0.35

# Cache: listingy se mění často, detaily dokumentů skoro nikdy.
CACHE_LISTING = 3_600
CACHE_DETAIL = 30 * 86_400

_lock = threading.Lock()


# --------------------------------------------------------------------------
# HTTP a HTML pomocníci
# --------------------------------------------------------------------------

def _stahni(url: str, *, max_age: int = CACHE_LISTING, pokusy: int = 4) -> str:
    """Stáhne stránku přes sdílenou cache a po *síťovém* dotazu chvíli počká.

    Pauza se dělá jen když se opravdu sahalo na server — poznáme to podle toho,
    že volání trvalo déle než pár milisekund. Opakovaný běh nad plnou cache tak
    není zbytečně pomalý.

    U hromadného stahování detailů se dává ``pokusy=2``: když je na druhém konci
    mrtvý odkaz nebo nás server odstřihl, nemá smysl u každé adresy odsedět
    plný exponenciální backoff.
    """
    t0 = time.monotonic()
    html = core.fetch(url, max_age=max_age, retries=pokusy)
    if time.monotonic() - t0 > 0.05:
        time.sleep(PRODLEVA_S)
    if not isinstance(html, str):  # pragma: no cover — binary=False vrací str
        html = html.decode("utf-8", errors="replace")
    return html


def _hlavni(html: str, url: str) -> HTMLParser:
    """Vrátí obsahovou část stránky. Bez ní by se v diffu propisovalo menu."""
    p = HTMLParser(html)
    for t in p.css("script, style, noscript"):
        t.decompose()
    node = p.css_first(".gcm-main") or p.css_first("main")
    if node is None:
        raise ZdrojSelhal(f"Na {url} chybí obsahový blok .gcm-main — změnila se šablona webu?")
    return node


def _txt(node) -> str:
    if node is None:
        return ""
    return core.cistit(node.text()).replace("\n", " ").strip()


def _abs(href: str | None, base: str = BASE) -> str | None:
    if not href:
        return None
    return urljoin(base + "/", href)


# Parametry, které jen říkají „jak se na stránku dívám", ne co na ní je.
ZOBRAZOVACI_PARAMY = {"show", "archiv_rok", "kshow", "page", "hledej", "sort", "order"}


def _ocisti_url(url: str | None) -> str | None:
    """Odstraní z odkazu zobrazovací parametry, ať je adresa dokumentu jedna.

    Tentýž dokument má v listingu různý query string podle toho, přes jakou
    kategorii a ročník se na něj člověk proklikl.
    """
    if not url:
        return None
    u = urlparse(url)
    q = [(k, v) for k, v in parse_qsl(u.query) if k not in ZOBRAZOVACI_PARAMY]
    return urlunparse((u.scheme, u.netloc, u.path, "", urlencode(q), ""))


def _cislo_z_url(url: str) -> str | None:
    """Z ``…/nazev-dokumentu-6790.html`` vytáhne ``6790``."""
    m = re.search(r"-(\d+)(?:cs)?\.html", urlparse(url).path)
    return m.group(1) if m else None


def _soubory(node, base: str = BASE) -> list[dict]:
    """Posbírá přílohy. Web města je servíruje dvěma různými skripty."""
    out: list[dict] = []
    videno: set[str] = set()
    for a in node.css("a[href]"):
        href = a.attributes.get("href", "")
        if "e_download.php" not in href and "file_storage/download.php" not in href:
            continue
        url = _abs(href, base)
        if url in videno:
            continue
        videno.add(url)
        q = parse_qs(urlparse(href.replace("&amp;", "&")).query)
        nazev_souboru = unquote(q.get("original", [""])[0]) or unquote(
            Path(unquote(q.get("file", [""])[0])).name
        )
        title = a.attributes.get("title", "")
        m = re.search(r"Velikost:\s*([\d.,]+\s*[kMG]?B)", title)
        popis = re.sub(r"\s*\([\d.,]+\s*[kMG]?B\)\s*$", "", _txt(a)).strip()
        out.append({
            "popis": popis or nazev_souboru or None,
            "soubor": nazev_souboru or None,
            "pripona": (Path(nazev_souboru).suffix.lstrip(".").lower() or None) if nazev_souboru else None,
            "velikost": m.group(1) if m else None,
            "url": url,
        })
    return out


class Nezdary:
    """Sbírá výpadky jednotlivých detailů a rozhoduje, kdy jde o selhání zdroje.

    Jeden mrtvý odkaz ze dvou set není rozbitý web — to se stává. Teprve když
    výpadků přeroste určitý podíl, je zdroj opravdu v háji a log to musí hlásit
    jako chybu. Bez toho by běh hlásil SELHALO donekonečna kvůli jedné mrtvé
    stránce a operátor by hlášení přestal číst.
    """

    def __init__(self, log: core.Log, co: str, celkem: int, prah: float = 0.1):
        self.log, self.co, self.celkem, self.prah = log, co, celkem, prah
        self.polozky: list[str] = []

    def zapis(self, url: str, duvod: str) -> None:
        with _lock:
            self.polozky.append(f"{url}: {duvod}")

    def vyhodnot(self) -> None:
        if not self.polozky:
            return
        self.log.info(
            f"{self.co} — nedostupné detaily",
            pocet=len(self.polozky), z=self.celkem, ukazky=self.polozky[:3],
        )
        if len(self.polozky) > self.prah * max(self.celkem, 1):
            self.log.chyba(
                f"{self.co}: nepodařilo se načíst {len(self.polozky)} z {self.celkem} detailů "
                f"(přes {self.prah:.0%}) — zdroj je nejspíš rozbitý"
            )


def _paralelne(polozky: list, prace) -> None:
    """Spustí ``prace(polozka)`` nad seznamem v omezeném počtu vláken."""
    if not polozky:
        return
    with ThreadPoolExecutor(max_workers=VLAKEN) as ex:
        list(ex.map(prace, polozky))


def _dnes() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _hlavicka(zdroj: str | list[str]) -> dict:
    return {
        "generovano": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "zdroj": zdroj,
    }


def _jmeno_bez_titulu(jmeno: str) -> tuple[str, str]:
    """Rozdělí „Ing. arch. Vojtěch Franta" na ('Vojtěch', 'Franta').

    Tituly poznáme podle tečky (`Mgr.`, `Ing.arch.`, `PaedDr.`), přípony za
    čárkou (`, DiS.`, `, Ph.D.`) se zahazují.
    """
    cisty = jmeno.split(",")[0]
    casti = [c for c in cisty.replace("\xa0", " ").split() if c and "." not in c]
    if len(casti) < 2:
        raise ZdrojSelhal(f"Ze jména '{jmeno}' nejde odvodit jméno a příjmení")
    return casti[0], casti[-1]


def osoba_id(jmeno: str) -> str:
    """Slug ``prijmeni-jmeno`` — klíč pro párování s hlasováním a osobnostmi."""
    krestni, prijmeni = _jmeno_bez_titulu(jmeno)
    return core.slug(f"{prijmeni}-{krestni}")


# Web u jednoho zastupitele píše zkratku „ZpML", jinde plný název téhož
# uskupení. Sjednocujeme, ať se strany daly agregovat. Původní zápis
# zůstává v poli `uskupeni_zdroj`.
USKUPENI_NAZVY = {
    "zpml": "Změna pro ML",
    "zmena pro ml": "Změna pro ML",
}


def _uskupeni(raw: str) -> str:
    return USKUPENI_NAZVY.get(core.slug(raw).replace("-", " "), raw)


# --------------------------------------------------------------------------
# 1. Úřední deska
# --------------------------------------------------------------------------

# POZOR, dvě různé stránky:
#  * /urad/uredni-deska/       — živá úřední deska, tady visí dokumenty v zákonné lhůtě
#  * /urad/uredni-deska-archiv/ — „Archiv složek dokumentů", kam se přesouvají po sejmutí
# Web sám to vysvětluje v úvodním textu archivu. Sbíráme obojí — živá deska je
# to, co se hlídá na zmizení, archiv je hloubka.
UD_ZIVA_URL = f"{BASE}/urad/uredni-deska/"
UD_URL = f"{BASE}/urad/uredni-deska-archiv/"


def _ud_klic(url: str) -> str:
    """Stabilní klíč dokumentu — bez parametrů ``kshow``/``show``.

    Tentýž dokument má v listingu různé query stringy podle toho, přes jakou
    kategorii se na něj člověk proklikl. Do klíče patří jen číslo z URL.
    """
    return _cislo_z_url(url) or core.slug(urlparse(url).path)


def _ud_listing(html: str, url: str, archiv_rok: int | None, deska: str) -> list[dict]:
    node = _hlavni(html, url)
    seznam = node.css_first(".official-desk-list")
    if seznam is None:
        raise ZdrojSelhal(f"Na {url} chybí .official-desk-list")

    out: list[dict] = []
    for kat in seznam.css(".category"):
        # Živá deska má název kategorie v <button>, archiv v <a>. Obojí nese id
        # ve tvaru `volna_mista-29`, ze kterého bereme číslo kategorie.
        kotva = kat.css_first(".category-name a") or kat.css_first(".category-name button")
        kat_nazev = _txt(kotva)
        kat_id = None
        if kotva is not None and kotva.attributes.get("id"):
            m = re.search(r"-(\d+)$", kotva.attributes["id"])
            kat_id = m.group(1) if m else None

        for it in kat.css(".item"):
            a = it.css_first(".item-href")
            if a is None:
                continue
            odkaz = _ocisti_url(_abs(a.attributes.get("href")))
            out.append({
                "id": _ud_klic(odkaz),
                "nazev": _txt(a),
                "kategorie": kat_nazev or None,
                "kategorie_id": kat_id,
                "vyveseno_od": core.parse_datum(_txt(it.css_first(".item-date-from"))),
                "vyveseno_do": core.parse_datum(_txt(it.css_first(".item-date-to"))),
                "deska": deska,
                "aktualni": archiv_rok is None,
                "archiv_rok": archiv_rok,
                "url": odkaz,
                "cislo_jednaci": None,
                "zodpovida": None,
                "text": None,
                "prilohy": None,
                "detail_nacten": False,
            })
    return out


def _ud_roky(log: core.Log) -> list[int]:
    html = _stahni(f"{UD_URL}?show=1")
    p = HTMLParser(html)
    roky = sorted(
        int(o.attributes["value"])
        for o in p.css("#ud_archivrok option")
        if (o.attributes.get("value") or "").isdigit()
    )
    if not roky:
        raise ZdrojSelhal("Na archivu úřední desky nejde načíst nabídka ročníků")
    log.info("archivní ročníky úřední desky", od=roky[0], do=roky[-1])
    return roky


def _ud_detail(z: dict, nezdary: Nezdary) -> None:
    try:
        node = _hlavni(_stahni(z["url"], max_age=CACHE_DETAIL), z["url"])
    except ZdrojSelhal as e:
        nezdary.zapis(z["url"], str(e)[:120])
        return
    d = node.css_first(".official-desk-detail")
    if d is None:
        nezdary.zapis(z["url"], "chybí .official-desk-detail")
        return
    obsah = d.css_first(".content")
    cj = d.css_first(".reference-number span")
    zod = d.css_first(".responsible-person span")
    z["cislo_jednaci"] = _txt(cj) or None
    z["zodpovida"] = _txt(zod) or None
    z["text"] = core.cistit(obsah.text()) if obsah is not None else None
    z["prilohy"] = _soubory(obsah if obsah is not None else d)
    z["detail_nacten"] = True


def uredni_deska(*, detaily_roky: int = 2, jen_aktualni: bool = False) -> dict:
    """Úřední deska — živá deska, trvalé složky i celý ročníkový archiv.

    ``detaily_roky`` říká, u kolika nejnovějších archivních ročníků se mají
    stáhnout i detaily (plný text a přílohy). Živá deska a trvalé složky se
    stahují vždy. Archiv má přes 6 600 dokumentů — stahovat detail ke každému
    by znamenalo několikahodinové bušení do serveru města, což se nedělá.
    """
    log = core.Log("muml-uredni-deska")
    vse: dict[str, dict] = {}

    ziva = _ud_listing(_stahni(UD_ZIVA_URL, max_age=0), UD_ZIVA_URL, None, "ziva")
    if not ziva:
        raise ZdrojSelhal("Živá úřední deska je prázdná — to je podezřelé, nezapisuji")
    log.info("živá úřední deska", polozek=len(ziva))
    for z in ziva:
        vse[z["id"]] = z

    slozky = _ud_listing(_stahni(UD_URL), UD_URL, None, "slozky")
    if not slozky:
        raise ZdrojSelhal("Archiv složek dokumentů je prázdný — to je podezřelé, nezapisuji")
    log.info("archiv složek (trvale vyvěšené)", polozek=len(slozky))
    for z in slozky:
        vse.setdefault(z["id"], z)

    roky = [] if jen_aktualni else _ud_roky(log)
    for rok in sorted(roky, reverse=True):
        url = f"{UD_URL}?show=1&archiv_rok={rok}"
        polozky = _ud_listing(_stahni(url), url, rok, "archiv")
        if not polozky:
            log.chyba(f"archivní ročník {rok} nevrátil žádné položky")
            continue
        log.info("archiv", rok=rok, polozek=len(polozky))
        for z in polozky:
            # Aktuálně vyvěšený dokument má přednost — nese příznak `aktualni`.
            if z["id"] not in vse:
                vse[z["id"]] = z

    polozky = list(vse.values())

    detailni_roky = set(sorted(roky, reverse=True)[:detaily_roky])
    k_detailu = [z for z in polozky if z["aktualni"] or z["archiv_rok"] in detailni_roky]
    log.info("stahuji detaily", dokumentu=len(k_detailu), rocniky=sorted(detailni_roky))
    nezdary = Nezdary(log, "úřední deska", len(k_detailu))
    _paralelne(k_detailu, lambda z: _ud_detail(z, nezdary))
    nezdary.vyhodnot()

    s_detailem = sum(1 for z in polozky if z["detail_nacten"])
    priloh = sum(len(z["prilohy"] or []) for z in polozky)
    polozky.sort(key=lambda z: (z["vyveseno_od"] or "0000-00-00"), reverse=True)

    vysledek = {
        **_hlavicka([UD_ZIVA_URL, UD_URL]),
        "poznamka": (
            "`deska` říká, odkud záznam pochází: `ziva` = právě vyvěšeno na úřední "
            "desce, `slozky` = trvalé složky v archivu dokumentů, `archiv` = sejmuto "
            "a odloženo do ročníku. Detaily (plný text + přílohy) se stahují u živé "
            f"desky, u složek a u {detaily_roky} nejnovějších archivních ročníků; "
            "jinde je `detail_nacten: false` a `text`/`prilohy` jsou null — to není "
            "prázdný dokument, ale nestažený detail."
        ),
        "celkem": len(polozky),
        "na_zive_desce": sum(1 for z in polozky if z["deska"] == "ziva"),
        "aktualnich": sum(1 for z in polozky if z["aktualni"]),
        "s_detailem": s_detailem,
        "priloh": priloh,
        "polozky": polozky,
    }
    core.uloz("mesto/uredni-deska.json", vysledek)
    log.pricti(len(polozky))
    log.uzavri()
    return vysledek


# --------------------------------------------------------------------------
# 2. Novinky
# --------------------------------------------------------------------------

NOVINKY_URL = f"{BASE}/aktualne/novinky/"


def _novinky_listing(html: str, url: str) -> list[dict]:
    node = _hlavni(html, url)
    out = []
    for a in node.css("a.event-link"):
        ev = a.css_first(".event")
        if ev is None:
            continue
        ident = (ev.attributes.get("id") or "").replace("event-", "")
        odkaz = _abs(a.attributes.get("href"))
        img = ev.css_first("img")
        out.append({
            "id": ident or _cislo_z_url(odkaz or ""),
            "titulek": _txt(ev.css_first(".event-name")),
            "datum": core.parse_datum(_txt(ev.css_first(".event-info-value.event-date"))),
            "perex": _txt(ev.css_first(".event-perex")) or None,
            "url": odkaz,
            "obrazek": _abs(img.attributes.get("src")) if img is not None else None,
            "text": None,
            "prilohy": None,
            "detail_nacten": False,
        })
    return out


def _novinky_pocet_stran(html: str) -> tuple[int, int]:
    p = HTMLParser(html)
    posledni = 1
    for a in p.css(".pagination a"):
        m = re.search(r"[?&]page=(\d+)", a.attributes.get("href", ""))
        if m:
            posledni = max(posledni, int(m.group(1)))
    pocet = 0
    cnt = p.css_first(".pagination-count")
    if cnt is not None:
        m = re.search(r"ze\s+([\d\s ]+)", _txt(cnt))
        if m:
            pocet = int(re.sub(r"\D", "", m.group(1)))
    return posledni, pocet


def _novinka_detail(z: dict, nezdary: Nezdary) -> None:
    try:
        node = _hlavni(_stahni(z["url"], max_age=CACHE_DETAIL), z["url"])
    except ZdrojSelhal as e:
        nezdary.zapis(z["url"], str(e)[:120])
        return
    d = node.css_first(".event-detail-content")
    if d is None:
        nezdary.zapis(z["url"], "chybí .event-detail-content")
        return
    text = d.css_first(".event-text")
    perex = d.css_first("#action-detail")
    z["text"] = core.cistit(text.text()) if text is not None else None
    if _txt(perex):
        z["perex"] = _txt(perex)
    z["prilohy"] = _soubory(d)
    z["detail_nacten"] = True


def novinky(*, max_stran: int | None = None, plny_text: bool = True) -> dict:
    """Novinky města včetně celého archivu (webem stránkovaný výpis)."""
    log = core.Log("muml-novinky")

    prvni = _stahni(NOVINKY_URL)
    stran, hlaseno = _novinky_pocet_stran(prvni)
    if max_stran:
        stran = min(stran, max_stran)
    log.info("stránkování novinek", stran=stran, hlasi_polozek=hlaseno)

    vse: dict[str, dict] = {}
    for z in _novinky_listing(prvni, NOVINKY_URL):
        vse[z["id"]] = z
    if not vse:
        raise ZdrojSelhal("První stránka novinek nevrátila žádnou položku")

    def _strana(n: int) -> None:
        url = f"{NOVINKY_URL}?page={n}"
        try:
            polozky = _novinky_listing(_stahni(url), url)
        except ZdrojSelhal as e:
            log.chyba(f"novinky — výpis {url}: {e}")
            return
        if not polozky:
            log.chyba(f"novinky — stránka {n} je prázdná")
            return
        with _lock:
            for z in polozky:
                vse.setdefault(z["id"], z)

    _paralelne(list(range(2, stran + 1)), _strana)
    polozky = list(vse.values())
    log.info("výpis hotov", polozek=len(polozky))

    if plny_text:
        log.info("stahuji plné texty", clanku=len(polozky))
        nezdary = Nezdary(log, "novinky", len(polozky))
        _paralelne(polozky, lambda z: _novinka_detail(z, nezdary))
        nezdary.vyhodnot()

    polozky.sort(key=lambda z: (z["datum"] or "0000-00-00", z["id"]), reverse=True)
    vysledek = {
        **_hlavicka(NOVINKY_URL),
        "celkem": len(polozky),
        "web_hlasi": hlaseno or None,
        "s_plnym_textem": sum(1 for z in polozky if z["text"]),
        "novinky": polozky,
    }
    core.uloz("mesto/novinky.json", vysledek)
    log.pricti(len(polozky))
    log.uzavri()
    return vysledek


# --------------------------------------------------------------------------
# 3. Kalendář akcí
# --------------------------------------------------------------------------

AKCE_ROZCESTNIK = f"{BASE}/aktualne/kalendar-akci/"
AKCE_URL = f"{KALENDAR}/kalendar/"

# Výpis kalendáře je „načítací" — ?page=N vrací kumulativně 13 + (N-1)*12 akcí.
AKCE_PRVNI_DAVKA = 13
AKCE_DAVKA = 12


def _akce_datumy(node) -> dict:
    """Z bloku s ikonou kalendáře vytáhne rozsah data a čas.

    Podoby: ``<b>17.8.2026</b> od 15:00`` nebo ``<b>27.6.2026</b><b> - 31.8.2026</b>``.
    """
    out = {"datum_od": None, "datum_do": None, "cas_od": None, "cas_do": None}
    bs = [_txt(b).strip(" -–") for b in node.css("b")]
    datumy = [core.parse_datum(b) for b in bs]
    datumy = [d for d in datumy if d]
    if datumy:
        out["datum_od"] = datumy[0]
        out["datum_do"] = datumy[1] if len(datumy) > 1 else datumy[0]
    casy = re.findall(r"\b(\d{1,2}:\d{2})\b", _txt(node))
    if casy:
        out["cas_od"] = casy[0]
        if len(casy) > 1:
            out["cas_do"] = casy[1]
    return out


def _akce_listing(html: str, url: str) -> tuple[list[dict], int]:
    p = HTMLParser(html)
    for t in p.css("script, style"):
        t.decompose()

    hlaseno = 0
    nadpis = p.css_first(".body-top .title")
    if nadpis is not None:
        m = re.search(r"(\d+)\s*akc", _txt(nadpis))
        if m:
            hlaseno = int(m.group(1))

    out: list[dict] = []
    for box in p.css(".part_item_calendar_box"):
        odkaz_node = box.css_first("a.content") or box.css_first("a[href]")
        odkaz = _abs(odkaz_node.attributes.get("href"), KALENDAR) if odkaz_node is not None else None
        if not odkaz:
            continue

        datumy = {"datum_od": None, "datum_do": None, "cas_od": None, "cas_do": None}
        misto = adresa = None
        for it in box.css(".content-info .info-item"):
            ikona = it.css_first("span[class*=icon-]")
            trida = ikona.attributes.get("class", "") if ikona is not None else ""
            if "icon-calendar" in trida:
                datumy = _akce_datumy(it)
            elif "icon-pin" in trida:
                b = it.css_first("b")
                misto = _txt(b) or None
                zbytek = _txt(it)
                if misto and zbytek.startswith(misto):
                    zbytek = zbytek[len(misto):]
                adresa = zbytek.strip(" ,") or None

        q = parse_qs(urlparse(odkaz).query)
        date_id = (q.get("dateId") or [None])[0]
        cesta = urlparse(odkaz).path.strip("/")
        out.append({
            "id": f"{core.slug(cesta)}-{date_id}" if date_id else core.slug(cesta),
            "nazev": _txt(box.css_first(".headline")),
            "typ": _txt(box.css_first(".content-title .title")) or None,
            "popis": _txt(box.css_first(".content-title .text")) or None,
            **datumy,
            "misto": misto,
            "adresa": adresa,
            "poradatel": None,
            "kontakt": None,
            "url": odkaz,
            "text": None,
            "detail_nacten": False,
        })
    return out, hlaseno


def _akce_detail(z: dict, nezdary: Nezdary) -> None:
    try:
        html = _stahni(z["url"], max_age=CACHE_DETAIL)
    except ZdrojSelhal as e:
        nezdary.zapis(z["url"], str(e)[:120])
        return
    p = HTMLParser(html)
    for t in p.css("script, style"):
        t.decompose()
    d = p.css_first(".comp_calendar_detail")
    if d is None:
        nezdary.zapis(z["url"], "chybí .comp_calendar_detail")
        return

    text = d.css_first(".body-text .wsw")
    if text is not None:
        z["text"] = core.cistit(text.text())

    for it in d.css(".aside-info .item"):
        ikona = it.css_first("span[class*=icon-]")
        trida = ikona.attributes.get("class", "") if ikona is not None else ""
        obsah = _txt(it)
        if "icon-agenda" in trida:
            # „ od: 17.8.2026 20:00  do: 17.8.2026 21:30"
            m_od = re.search(r"od:\s*([\d.\s]+\d{4})(?:\s+(\d{1,2}:\d{2}))?", obsah)
            m_do = re.search(r"do:\s*([\d.\s]+\d{4})(?:\s+(\d{1,2}:\d{2}))?", obsah)
            if m_od:
                z["datum_od"] = core.parse_datum(m_od.group(1)) or z["datum_od"]
                z["cas_od"] = m_od.group(2) or z["cas_od"]
            if m_do:
                z["datum_do"] = core.parse_datum(m_do.group(1)) or z["datum_do"]
                z["cas_do"] = m_do.group(2) or z["cas_do"]
        elif "icon-conference" in trida:
            spany = [_txt(s) for s in it.css("span") if _txt(s)]
            if spany:
                z["poradatel"] = spany[0]
            kontakt = [
                a.attributes.get("href", "").replace("mailto:", "").replace("tel:", "")
                for a in it.css("a[href^=mailto], a[href^=tel]")
            ]
            z["kontakt"] = kontakt or None
    z["detail_nacten"] = True


def akce(*, dni_dopredu: int = 730, dni_zpet: int = 30, detaily: bool = True) -> dict:
    """Akce ve městě — podklad pro sekci „Co se děje ve městě".

    POZOR: nečte se muml.cz. Tamní stránka kalendáře je jen rozcestník na
    turistický portál marianskelazne.cz, kde kalendář opravdu je.
    """
    log = core.Log("muml-akce")

    # Kontrola, že rozcestník na muml.cz pořád ukazuje tam, kam si myslíme.
    try:
        rozc = _hlavni(_stahni(AKCE_ROZCESTNIK), AKCE_ROZCESTNIK)
        odkazy = [a.attributes.get("href", "") for a in rozc.css("a[href]")]
        if not any("marianskelazne.cz/kalendar" in h for h in odkazy):
            log.chyba(
                "muml.cz/aktualne/kalendar-akci/ už neodkazuje na marianskelazne.cz/kalendar "
                "— zkontrolovat, jestli město nezavedlo vlastní kalendář"
            )
    except ZdrojSelhal as e:
        log.chyba(f"rozcestník kalendáře na muml.cz: {e}")

    od = (date.today() - timedelta(days=dni_zpet)).isoformat()
    do = (date.today() + timedelta(days=dni_dopredu)).isoformat()
    zaklad = f"{AKCE_URL}?filtr=Y&nameEvent=&fromEvent={od}&toEvent={do}"

    _, hlaseno = _akce_listing(_stahni(f"{zaklad}&page=1"), zaklad)
    if not hlaseno:
        raise ZdrojSelhal("Kalendář akcí nehlásí počet nalezených akcí — změnila se šablona?")
    stran = max(1, -(-(hlaseno - AKCE_PRVNI_DAVKA) // AKCE_DAVKA) + 1)
    log.info("kalendář", od=od, do=do, hlasi_akci=hlaseno, dotazu=stran)

    url = f"{zaklad}&page={stran}"
    polozky, _ = _akce_listing(_stahni(url), url)
    if not polozky:
        raise ZdrojSelhal(f"Kalendář akcí hlásí {hlaseno} akcí, ale výpis je prázdný")

    vse: dict[str, dict] = {}
    for z in polozky:
        vse.setdefault(z["id"], z)
    polozky = list(vse.values())
    log.info("výpis akcí", nacteno=len(polozky), hlaseno=hlaseno)

    if detaily:
        nezdary = Nezdary(log, "akce", len(polozky))
        _paralelne(polozky, lambda z: _akce_detail(z, nezdary))
        nezdary.vyhodnot()

    polozky.sort(key=lambda z: (z["datum_od"] or "9999-99-99", z["cas_od"] or "", z["nazev"]))
    dnes = date.today().isoformat()
    vysledek = {
        **_hlavicka([AKCE_ROZCESTNIK, AKCE_URL]),
        "poznamka": (
            "Data pocházejí z turistického portálu marianskelazne.cz — stránka "
            "kalendáře na muml.cz je pouze rozcestník a žádné akce neobsahuje."
        ),
        "obdobi": {"od": od, "do": do},
        "celkem": len(polozky),
        "web_hlasi": hlaseno,
        "nadchazejicich": sum(1 for z in polozky if (z["datum_do"] or z["datum_od"] or "") >= dnes),
        "akce": polozky,
    }
    core.uloz("mesto/akce.json", vysledek)
    log.pricti(len(polozky))
    log.uzavri()
    return vysledek


# --------------------------------------------------------------------------
# 4. Zastupitelé
# --------------------------------------------------------------------------

ZASTUPITELE_URL = f"{BASE}/samosprava/zastupitelstvo/clenove-1/"
TERMINY_URL = f"{BASE}/samosprava/zastupitelstvo/terminy-zasedani/"
VOLEBNI_OBDOBI = "2022-2026"

# Ověřené změny funkcí, které web už neukazuje (drží jen aktuální stav).
# Zdroj: docs/datove-zdroje.md, ověřeno 17. 8. 2026.
ZNAME_HISTORIE_FUNKCI: dict[str, list[dict]] = {
    "zabolotny-samuel": [{
        "nazev": "1. místostarosta",
        "od": None,
        "do": "2026-06",
        "zjisteno": None,
        "zdroj": "docs/datove-zdroje.md — rezignace v červnu 2026 (ověřeno 2026-08-17)",
    }],
}


def _kontakty(node) -> dict:
    """Rozebere blok ``.contacts`` na telefon / mobil / e-mail / web."""
    out: dict[str, str | None] = {"telefon": None, "mobil": None, "email": None, "web": None}
    if node is None:
        return out
    for cast in re.split(r"<br\s*/?>", node.html or ""):
        p = HTMLParser(cast)
        a = p.css_first("a[href]")
        if a is None:
            continue
        href = a.attributes.get("href", "")
        hodnota = _txt(a) or href.split(":", 1)[-1]
        popisek = core.slug(_txt(p.css_first("body")).split(":")[0])
        if href.startswith("mailto:") or "mail" in popisek:
            out["email"] = out["email"] or hodnota
        elif "mobil" in popisek:
            out["mobil"] = out["mobil"] or hodnota
        elif href.startswith("tel:") or "telefon" in popisek:
            out["telefon"] = out["telefon"] or hodnota
        elif href.startswith("http"):
            out["web"] = out["web"] or href
    return out


def _osoby_bloku(node) -> list[dict]:
    """Parsuje ``.contacts-block.persons .person`` (zastupitelé, firmy, odbory)."""
    out = []
    for p in node.css(".person"):
        h = p.css_first("h3") or p.css_first("h2")
        if h is None:
            continue
        jmeno = _txt(h)
        if not jmeno:
            continue
        a = h.css_first("a[href]") or p.css_first("a[href*='/osoba-']")
        prislusnost = None
        for s in p.css("span.d-block"):
            t = _txt(s)
            if "říslušnost" in t:
                prislusnost = t.split(":", 1)[-1].strip()
        out.append({
            "jmeno": jmeno,
            "id": osoba_id(jmeno),
            "funkce": _txt(p.css_first(".function")) or None,
            "uskupeni_zdroj": prislusnost,
            "url": _abs(a.attributes.get("href")) if a is not None else None,
            **_kontakty(p.css_first(".contacts")),
        })
    return out


def _terminy_zasedani(log: core.Log) -> list[dict]:
    node = _hlavni(_stahni(TERMINY_URL), TERMINY_URL)
    text = core.cistit(node.text())
    m = re.search(r"od\s+(\d{1,2}[.:]\d{2})", text)
    cas = m.group(1).replace(".", ":") if m else None
    out = []
    for li in node.css("li"):
        d = core.parse_datum(_txt(li))
        if d:
            out.append({"datum": d, "cas": cas, "zdroj": TERMINY_URL})
    if not out:
        log.chyba("termíny zasedání se nepodařilo rozparsovat")
    return sorted(out, key=lambda z: z["datum"])


def _slouc_funkce(stare: list[dict] | None, nova: str | None, dnes: str) -> list[dict]:
    """Udržuje historii funkcí — web ukazuje jen aktuální stav.

    Když se od minulého běhu funkce změnila, ta stará se uzavře dnešním dnem
    a otevře se nová. `od: null` znamená „začátek neznáme" (funkci jsme poprvé
    viděli až při prvním běhu sběrače), ne „od nepaměti".
    """
    hist = [dict(f) for f in (stare or [])]
    otevrene = [f for f in hist if f.get("do") is None]
    aktualni = otevrene[-1] if otevrene else None

    if nova is None:
        for f in otevrene:
            f["do"] = dnes
        return hist
    if aktualni is not None and aktualni.get("nazev") == nova:
        return hist
    for f in otevrene:
        f["do"] = dnes
    hist.append({
        "nazev": nova,
        "od": None if aktualni is None and not hist else dnes,
        "do": None,
        "zjisteno": dnes,
        "zdroj": ZASTUPITELE_URL,
    })
    return hist


def zastupitele() -> dict:
    """Zastupitelstvo města — jména, uskupení, kontakty a historie funkcí."""
    log = core.Log("muml-zastupitele")
    node = _hlavni(_stahni(ZASTUPITELE_URL), ZASTUPITELE_URL)
    blok = node.css_first(".contacts-block.persons")
    if blok is None:
        raise ZdrojSelhal(f"Na {ZASTUPITELE_URL} chybí blok s osobami")

    osoby = _osoby_bloku(blok)
    if not osoby:
        raise ZdrojSelhal("Seznam zastupitelů je prázdný")
    if len(osoby) != 21:
        log.chyba(f"zastupitelstvo má mít 21 členů, načteno {len(osoby)} — ověřit ručně")

    stare = {z["id"]: z for z in (core.nacti("mesto/zastupitele.json", {}) or {}).get("zastupitele", [])}
    dnes = _dnes()

    out = []
    for o in osoby:
        drivejsi = stare.get(o["id"], {})
        hist = _slouc_funkce(
            drivejsi.get("funkce_historie") or ZNAME_HISTORIE_FUNKCI.get(o["id"]),
            o["funkce"],
            dnes,
        )
        out.append({
            "id": o["id"],
            "jmeno": o["jmeno"],
            "uskupeni": _uskupeni(o["uskupeni_zdroj"] or ""),
            "uskupeni_zdroj": o["uskupeni_zdroj"],
            "funkce": o["funkce"],
            "funkce_historie": hist,
            "kontakt": {
                "telefon": o["telefon"],
                "mobil": o["mobil"],
                "email": o["email"],
            },
            "url": o["url"],
        })

    out.sort(key=lambda z: core.slug(z["id"]))
    terminy = _terminy_zasedani(log)
    log.info("zastupitelé", osob=len(out), terminu=len(terminy))

    vysledek = {
        **_hlavicka([ZASTUPITELE_URL, TERMINY_URL]),
        "volebni_obdobi": VOLEBNI_OBDOBI,
        "poznamka": (
            "Web ukazuje jen aktuální funkci. `funkce_historie` se dopočítává "
            "porovnáním s předchozím během sběrače; `od: null` znamená, že "
            "začátek platnosti neznáme, ne že platí odjakživa."
        ),
        "celkem": len(out),
        "zastupitele": out,
        "terminy_zasedani": terminy,
    }
    core.uloz("mesto/zastupitele.json", vysledek)
    log.pricti(len(out))
    log.uzavri()
    return vysledek


# --------------------------------------------------------------------------
# 5. Úřad — vedení města a vedoucí odborů
# --------------------------------------------------------------------------

VEDENI_URL = f"{BASE}/samosprava/vedeni-mesta/"
TELEFONNI_URL = f"{BASE}/kontakty/telefonni-seznam/"


def _vedeni(log: core.Log) -> list[dict]:
    node = _hlavni(_stahni(VEDENI_URL), VEDENI_URL)
    out = []
    for w in node.css(".contentbox .widget"):
        funkce = _txt(w.css_first("h2.title"))
        jmeno = _txt(w.css_first(".content h3"))
        if not funkce or not jmeno:
            continue
        strana = None
        li = w.css(".content ul li")
        if li:
            prvni = _txt(li[0])
            if "odrobnosti" not in prvni:
                strana = prvni
        detail = w.css_first(".content ul li a[href]")
        out.append({
            "funkce": funkce,
            "jmeno": jmeno,
            "id": osoba_id(jmeno),
            "uskupeni": _uskupeni(strana) if strana else None,
            "url": _abs(detail.attributes.get("href")) if detail is not None else None,
        })
    if not out:
        raise ZdrojSelhal(f"Na {VEDENI_URL} se nenašla žádná pozice vedení města")
    log.info("vedení města", pozic=len(out))
    return out


def _odbory(html: str) -> list[dict]:
    """Strom odborů z rozbalovátka telefonního seznamu (odsazení = úroveň)."""
    p = HTMLParser(html)
    sel = p.css_first("#kty_filtr")
    if sel is None:
        raise ZdrojSelhal("V telefonním seznamu chybí výběr organizace #kty_filtr")
    out = []
    for o in sel.css("option"):
        hodnota = o.attributes.get("value", "")
        raw = (o.text() or "").replace("\xa0", " ")
        nazev = raw.strip()
        if not hodnota or hodnota == "0" or not nazev or nazev.startswith("---"):
            continue
        uroven = (len(raw) - len(raw.lstrip(" "))) // 2
        out.append({"id": hodnota, "nazev": nazev, "uroven": uroven})
    return out


def _osoby_seznamu(html: str, url: str) -> list[dict]:
    """Parsuje jednu stránku telefonního seznamu úřadu."""
    node = _hlavni(html, url)
    out = []
    for p in node.css(".persons-list .person"):
        h = p.css_first("h2")
        if h is None:
            continue
        jmeno = _txt(h)
        odkaz = p.css_first("a[href*='/osoba-']")
        subjekt = p.css_first("a[href*='/subjekt-']")

        # Funkce stojí jako holý text mezi odkazem na osobu a odkazem na odbor.
        html_p = p.html or ""
        funkce = None
        if subjekt is not None:
            konec_jmena = html_p.find("</a>")
            zacatek_subjektu = html_p.find(subjekt.html or "")
            if konec_jmena >= 0 and zacatek_subjektu > konec_jmena:
                mezi = HTMLParser(html_p[konec_jmena + 4:zacatek_subjektu]).text()
                funkce = core.cistit(mezi).replace("\n", " ").strip(" -–,") or None

        adresa = None
        for s in p.css("span[data-no-translate]"):
            t = _txt(s)
            if t and not t.startswith("+") and "@" not in t:
                adresa = t
                break

        odbor_id = None
        if subjekt is not None:
            m = re.search(r"-(\d+)\.html", subjekt.attributes.get("href", ""))
            odbor_id = m.group(1) if m else None

        out.append({
            "jmeno": jmeno,
            "id": osoba_id(jmeno),
            "funkce": funkce,
            "odbor": _txt(subjekt) if subjekt is not None else None,
            "odbor_id": odbor_id,
            "adresa": adresa,
            "url": _abs(odkaz.attributes.get("href")) if odkaz is not None else None,
            **_kontakty(p.css_first(".contacts")),
        })
    return out


def urad() -> dict:
    """Vedení města + celý telefonní seznam úřadu s vyznačenými vedoucími."""
    log = core.Log("muml-urad")
    vedeni = _vedeni(log)

    prvni = _stahni(TELEFONNI_URL)
    odbory = _odbory(prvni)
    stran = 1
    for a in HTMLParser(prvni).css(".pagination a"):
        m = re.search(r"[?&]page=(\d+)", a.attributes.get("href", ""))
        if m:
            stran = max(stran, int(m.group(1)))
    log.info("telefonní seznam", stran=stran, odboru=len(odbory))

    osoby: dict[str, dict] = {}
    for o in _osoby_seznamu(prvni, TELEFONNI_URL):
        osoby.setdefault(o["url"] or o["id"], o)

    def _strana(n: int) -> None:
        url = f"{TELEFONNI_URL}?page={n}"
        try:
            polozky = _osoby_seznamu(_stahni(url), url)
        except ZdrojSelhal as e:
            log.chyba(f"telefonní seznam — {url}: {e}")
            return
        if not polozky:
            log.chyba(f"telefonní seznam — stránka {n} je prázdná")
            return
        with _lock:
            for o in polozky:
                osoby.setdefault(o["url"] or o["id"], o)

    _paralelne(list(range(2, stran + 1)), _strana)

    vsichni = sorted(osoby.values(), key=lambda o: core.slug(o["id"]))
    if not vsichni:
        raise ZdrojSelhal("Telefonní seznam úřadu je prázdný")

    def _je_vedouci(o: dict) -> bool:
        f = core.slug(o.get("funkce") or "")
        return f.startswith("vedouci") or "tajemnik" in f

    vedouci = [o for o in vsichni if _je_vedouci(o)]
    log.info("úřad", osob=len(vsichni), vedoucich=len(vedouci))

    vysledek = {
        **_hlavicka([VEDENI_URL, TELEFONNI_URL]),
        "vedeni_mesta": vedeni,
        "odbory": odbory,
        "vedouci_odboru": vedouci,
        "osob_celkem": len(vsichni),
        "osoby": vsichni,
    }
    core.uloz("mesto/urad.json", vysledek)
    log.pricti(len(vsichni))
    log.uzavri()
    return vysledek


# --------------------------------------------------------------------------
# 6. Obchodní společnosti města
# --------------------------------------------------------------------------

SPOLECNOSTI_URL = f"{BASE}/urad/povinne-informace/subjekt-obchodni-spolecnosti-81.html"


def _spolecnost_detail(z: dict, nezdary: Nezdary) -> None:
    try:
        node = _hlavni(_stahni(z["url"], max_age=CACHE_DETAIL), z["url"])
    except ZdrojSelhal as e:
        nezdary.zapis(z["url"], str(e)[:120])
        return

    adresa = node.css_first(".contacts-address")
    if adresa is not None:
        radky = [_txt(s) for s in adresa.css("span") if _txt(s)]
        z["adresa"] = ", ".join(radky) or None

    kont = node.css_first(".subject-contacts")
    if kont is not None:
        for s in kont.css("span.d-block"):
            popisek = core.slug(_txt(s.css_first(".font-weight-bold")))
            a = s.css_first("a[href]")
            hodnota = _txt(a) if a is not None else _txt(s).split(":", 1)[-1].strip()
            if popisek.startswith("ico"):
                z["ico"] = re.sub(r"\D", "", hodnota) or None
            elif popisek.startswith("telefon"):
                z["telefon"] = hodnota
            elif popisek.startswith("www"):
                z["web"] = a.attributes.get("href") if a is not None else hodnota
            elif popisek.startswith("e-mail") or popisek.startswith("email"):
                z["email"] = hodnota

    blok = node.css_first(".contacts-block.persons")
    z["osoby"] = _osoby_bloku(blok) if blok is not None else []
    z["detail_nacten"] = True


def spolecnosti() -> dict:
    """Obchodní společnosti města včetně IČO z detailních karet.

    IČO na přehledové stránce není — je až v detailu každé firmy. Tím se
    zaplňuje mezera, kterou docs/datove-zdroje.md označuje jako „dohledat".
    """
    log = core.Log("muml-spolecnosti")
    node = _hlavni(_stahni(SPOLECNOSTI_URL), SPOLECNOSTI_URL)
    strom = node.css_first(".contats-subject-tree")
    if strom is None:
        raise ZdrojSelhal(f"Na {SPOLECNOSTI_URL} chybí strom podřízených subjektů")

    out: list[dict] = []
    for skupina in strom.css("ul > li"):
        a_sk = skupina.css_first("a[href]")
        nazev_skupiny = _txt(a_sk.css_first("h3")) if a_sk is not None else None
        for li in skupina.css("ul li"):
            a = li.css_first("a[href]")
            if a is None:
                continue
            nazev = _txt(a.css_first("h3")) or _txt(a)
            if not nazev:
                continue
            out.append({
                "id": core.slug(nazev),
                "nazev": nazev,
                "skupina": nazev_skupiny,
                "ucast_mesta": "100 %" if "100" in (nazev_skupiny or "") else "částečná",
                "ico": None,
                "adresa": None,
                "telefon": None,
                "email": None,
                "web": None,
                "url": _abs(a.attributes.get("href")),
                "osoby": None,
                "detail_nacten": False,
            })

    if not out:
        raise ZdrojSelhal("Seznam obchodních společností je prázdný")
    nezdary = Nezdary(log, "obchodní společnosti", len(out))
    _paralelne(out, lambda z: _spolecnost_detail(z, nezdary))
    nezdary.vyhodnot()

    # Chybějící IČO není chyba sběrače — web ho u některých firem prostě neuvádí.
    # Hlásíme to jako mezeru v datech, ne jako selhání zdroje.
    bez_ico = [z["nazev"] for z in out if not z["ico"]]
    if bez_ico:
        log.info("IČO web neuvádí", firmy=bez_ico)
    log.info("obchodní společnosti", firem=len(out), s_ico=len(out) - len(bez_ico))

    vysledek = {
        **_hlavicka(SPOLECNOSTI_URL),
        "celkem": len(out),
        "spolecnosti": sorted(out, key=lambda z: z["nazev"]),
    }
    core.uloz("mesto/spolecnosti.json", vysledek)
    log.pricti(len(out))
    log.uzavri()
    return vysledek


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

SBERACE = {
    "uredni-deska": uredni_deska,
    "novinky": novinky,
    "akce": akce,
    "zastupitele": zastupitele,
    "urad": urad,
    "spolecnosti": spolecnosti,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sběrače webu města Mariánské Lázně")
    ap.add_argument("co", nargs="*", default=[], metavar="SBERAC",
                    help=f"které sběrače spustit (výchozí: vse). Volby: {', '.join(SBERACE)}, vse")
    ap.add_argument("--bez-detailu", action="store_true",
                    help="jen výpisy, nestahovat plné texty a přílohy")
    ap.add_argument("--ud-detaily-roky", type=int, default=2,
                    help="u kolika nejnovějších archivních ročníků úřední desky stáhnout detaily")
    ap.add_argument("--novinky-stran", type=int, default=None,
                    help="omezit počet stránek novinek (pro rychlý zkušební běh)")
    args = ap.parse_args(argv)

    co = args.co or ["vse"]
    nezname = [c for c in co if c not in SBERACE and c != "vse"]
    if nezname:
        ap.error(f"neznámé sběrače: {', '.join(nezname)}. Volby: {', '.join(SBERACE)}, vse")
    if "vse" in co:
        co = list(SBERACE)

    chyby = 0
    for jmeno in co:
        try:
            if jmeno == "uredni-deska":
                uredni_deska(detaily_roky=0 if args.bez_detailu else args.ud_detaily_roky)
            elif jmeno == "novinky":
                novinky(max_stran=args.novinky_stran, plny_text=not args.bez_detailu)
            elif jmeno == "akce":
                akce(detaily=not args.bez_detailu)
            else:
                SBERACE[jmeno]()
        except ZdrojSelhal as e:
            print(f"[{jmeno}] SELHALO: {e}", flush=True)
            chyby += 1
    return 1 if chyby else 0


if __name__ == "__main__":
    raise SystemExit(main())
