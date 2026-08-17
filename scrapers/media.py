#!/usr/bin/env python3
"""B3 — mediální monitoring Mariánských Lázní.

Sbírá ZMÍNKY o městě v regionálních médiích. Ukládá výhradně titulek, zdroj,
datum, URL a vlastní dvouvětné shrnutí. **Plný text cizího článku se nikdy
neukládá do `data/`** — perex původního autora slouží jen jako pracovní
podklad pro sepsání shrnutí a zůstává v `.cache/` (mimo git).

Jak to je rozdělené (v duchu zásady projektu "scraping dělá kód, porozumění
dělá Claude"):

    1. KÓD (tenhle soubor) posbírá ověřitelná metadata — titulek, datum, URL.
       Nic si nedomýšlí. Když datum na stránce není, uloží `null`.
    2. CLAUDE si přes `--podklady` vytáhne čistá data + perex, přečte je,
       napíše vlastní shrnutí a vybere tagy z číselníku.
    3. `--doplnit` shrnutí zpátky zaválcuje do `clanky.json` a přitom
       ZVALIDUJE tagy proti `config/tagy.json`. Neplatný tag = chyba.

Dokud shrnutí neexistuje, je v záznamu `shrnuti: null` a `stav: "k-shrnuti"`.
Nikdy se nevymýšlí náhražka — prázdno se pozná od hotového.

--------------------------------------------------------------------------
ROBOTS.TXT — ověřeno 17. 8. 2026
--------------------------------------------------------------------------
Deníkový holding (`denik.cz` včetně `chebsky.denik.cz`) má v robots.txt
sekci "AI bots protection" a v ní `User-agent: ClaudeBot` / `Claude-Web` /
`anthropic-ai` s `Disallow: /`. Zdroj je proto v `ZDROJE` označený
`povoleno=False` a sběrač ho NIKDY nestahuje. Není to opomenutí, je to
respektování zákazu — schválně to není řešené přepnutím User-Agenta.
Odkaz na Deník se dá do přehledu doplnit ručně, obsah se nescrapuje.

`vary.rozhlas.cz` má `Crawl-delay: 10`. Dodržujeme ho doslova, proto dávka
přes rozhlas trvá desítky minut. Není to chyba, je to slušnost.

Spuštění:
    python3 scrapers/media.py --historie              # dávka, co nejhlouběji
    python3 scrapers/media.py --historie --zdroj cro  # jen jeden zdroj
    python3 scrapers/media.py --tyden                 # inkrement od minula
    python3 scrapers/media.py --hloubka               # jen průzkum archivů
    python3 scrapers/media.py --podklady > /tmp/p.json   # co čeká na shrnutí
    python3 scrapers/media.py --doplnit /tmp/hotovo.json # zaválcovat shrnutí
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from selectolax.parser import HTMLParser

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import (  # noqa: E402
    CACHE,
    Log,
    ZdrojSelhal,
    cistit,
    fetch,
    nacti,
    platne_tagy,
    slug,
    uloz,
)

CLANKY = "media/clanky.json"
ZDROJE_STAV = "media/zdroje.json"
STAV = "media/stav.json"

# Perexy cizích autorů drží jen cache — do data/ se nikdy nedostanou.
PODKLADY = CACHE / "media" / "podklady"

# Identity, pod kterými nás web může chtít zakázat. Když robots.txt zakáže
# kteroukoliv z nich, zdroj nestahujeme — i když bychom se "prošli" pod
# běžnou prohlížečovou hlavičkou. Obcházet zákaz přejmenováním je podvod.
NASE_IDENTITY = ("claudebot", "claude-web", "anthropic-ai", "claude-user")


# --------------------------------------------------------------------------
# Co hlídáme
# --------------------------------------------------------------------------

# Podoba ve slugu URL (bez diakritiky). Slouží k předfiltru sitemapy — je
# schválně široká, přesnost dodá až kontrola textu níž.
SLUG_VZORY = [
    "marianske-lazne", "marianskych-lazni", "marianskych-laznich",
    "marianskym-laznim", "marianskymi-laznemi", "marianskym-laznim",
    "marianske-lazni", "marianskolazensk", "marianek", "mariankach",
    "marianky-", "-marianky",
    "hurajcik", "zabolotny", "miloslav-pelc",
    "vila-lil", "vily-lil", "vile-lil", "vilu-lil",
    "boheminium", "lazenske-lesy", "lazenskych-lesu",
    "infocentrum-marianske", "develop-centrum",
    "mestska-doprava-marianske", "nemocnice-marianske",
    "nemocnice-v-marianskych", "zapadocesky-symfonicky",
]

# Podoba v textu (titulek + perex), s diakritikou. Tohle je ta ostrá kontrola:
# článek se uloží, jen když se opravdu týká Mariánských Lázní.
#
# Schválně tu NENÍ obecné "lázeňské lesy". Karlovy Vary mají vlastní
# "Lázeňské lesy a parky Karlovy Vary" a ten výraz do dat pustil sedm
# článků o karlovarské firmě, které s Mariánskými Lázněmi nemají nic
# společného. Ve slugu ho jako předfiltr necháváme — ale projít smí
# jen článek, který Mariánské Lázně opravdu jmenuje.
TEXT_VZORY = [
    re.compile(r"mari[áa]nsk\w*\s+l[áa]zn\w*", re.I),
    re.compile(r"mari[áa]nskol[áa]ze[ňn]sk\w*", re.I),
    re.compile(r"\bmari[áa]nk[yáách]\w*", re.I),
    re.compile(r"vil[ayeu]\s+lil\b", re.I),
    re.compile(r"boheminium", re.I),
    re.compile(r"hurajč[íi]k", re.I),
    re.compile(r"zabolotn[ýy]", re.I),
]

# Jména, která umíme ve zmínce rozpoznat → slug `prijmeni-jmeno`,
# aby šel článek spárovat s databází osobností (modul B1).
# Detekce je doslovná: jméno v textu opravdu stojí, nic se nedovozuje.
OSOBY_VZORY: list[tuple[re.Pattern, str]] = [
    (re.compile(r"Hurajč[íi]k", re.I), "hurajcik-martin"),
    (re.compile(r"Miloslav\w*\s+Pelc|Pelc\w*\s*\(?Zm[ěe]na", re.I), "pelc-miloslav"),
    (re.compile(r"Zabolotn[ýyáéu]\w*", re.I), "zabolotny-samuel"),
    (re.compile(r"Vojt[ěe]ch\w*\s+Frant[ay]|Frant[ay]\s*\(?Pir[áa]t", re.I), "franta-vojtech"),
    (re.compile(r"Lubo[šs]\w*\s+Bork[ay]", re.I), "borka-lubos"),
    (re.compile(r"Jan\w*\s+Budk[ay]", re.I), "budka-jan"),
    (re.compile(r"Roman\w*\s+Dubnick[ýyéu]", re.I), "dubnicky-roman"),
    (re.compile(r"Du[šs]an\w*\s+Drexler\w*", re.I), "drexler-dusan"),
    (re.compile(r"Petr\w*\s+H[áa]l[ay]\b", re.I), "hala-petr"),
    (re.compile(r"Alen[ay]\s+H[áa]lov[áa]", re.I), "halova-alena"),
    (re.compile(r"Martin\w*\s+Hlad[íi]k\w*", re.I), "hladik-martin"),
    (re.compile(r"Miloslav\w*\s+Chadim\w*", re.I), "chadim-miloslav"),
    (re.compile(r"Vladim[íi]r\w*\s+Kafk[ay]", re.I), "kafka-vladimir"),
    (re.compile(r"Martin\w*\s+Kalin[ay]", re.I), "kalina-martin"),
    (re.compile(r"Zden[ěe]k\w*\s+Kr[áa]l\w*\b", re.I), "kral-zdenek"),
    (re.compile(r"Ludmil[ay]\s+M[íi]kov[áa]", re.I), "mikova-ludmila"),
    (re.compile(r"Ivan[ay]\s+Mottlov[áa]", re.I), "mottlova-ivana"),
    (re.compile(r"Josef\w*\s+Pavlovic\w*", re.I), "pavlovic-josef"),
    (re.compile(r"Jan[ay]\s+Roubalov[áa]", re.I), "roubalova-jana"),
    (re.compile(r"[ŠS]t[ěe]p[áa]n\w*\s+Str[áa]n[íi]k\w*", re.I), "stranik-stepan"),
    (re.compile(r"Kamil\w*\s+[ŠS]pindler\w*", re.I), "spindler-kamil"),
]


# --------------------------------------------------------------------------
# Zdroje
# --------------------------------------------------------------------------

@dataclass
class Zdroj:
    kod: str
    nazev: str
    domena: str
    # Odkud vezmeme seznam URL. `sitemap` = XML sitemapa (i vnořená),
    # `wp_hledani` = stránkované vyhledávání WordPressu.
    sitemapy: list[str] = field(default_factory=list)
    hledani: str | None = None          # šablona s {q} a {p}
    prodleva: float = 2.0               # sekundy mezi síťovými požadavky
    povoleno: bool = True
    duvod_zakazu: str | None = None
    # Jak u tohohle webu vypadá URL ZPRÁVY. Sitemapa míchá články
    # s rozcestníky (kraj má v ní i stránky svých příspěvkovek a úřední
    # desku) a ty do mediálního monitoringu nepatří — nemají datum vydání
    # ani autora, jsou to adresáře. Bez tohohle filtru se stahují zbytečně.
    vzor_clanku: re.Pattern | None = None


ZDROJE: dict[str, Zdroj] = {
    "cro": Zdroj(
        kod="cro",
        nazev="Český rozhlas Karlovy Vary",
        domena="vary.rozhlas.cz",
        sitemapy=["https://vary.rozhlas.cz/sitemap.xml"],
        # robots.txt: Crawl-delay: 10 — dodržujeme doslova.
        prodleva=10.0,
        # Zpráva má na konci slugu číslo uzlu Drupalu (…-6820288).
        vzor_clanku=re.compile(r"-\d{6,}$"),
    ),
    "zk": Zdroj(
        kod="zk",
        nazev="Zprávy Karlovarsko",
        domena="zpravykarlovarsko.cz",
        sitemapy=["https://zpravykarlovarsko.cz/sitemap_index.xml"],
        # WordPress bez REST API (wp-json vrací 404), ale ?s= hledání funguje
        # a stránkuje. Chytá i zmínky, které nejsou vidět ve slugu.
        hledani="https://zpravykarlovarsko.cz/page/{p}/?s={q}",
        prodleva=2.0,
        vzor_clanku=re.compile(r"^https://zpravykarlovarsko\.cz/[a-z0-9-]+/$"),
    ),
    "kkr": Zdroj(
        kod="kkr",
        nazev="Karlovarský kraj",
        domena="www.kr-karlovarsky.cz",
        sitemapy=["https://www.kr-karlovarsky.cz/sitemap.xml"],
        prodleva=2.0,
        # Tiskové zprávy kraje žijí pod /aktuality/. Zbytek sitemapy jsou
        # rozcestníky obcí, příspěvkovek a úřední deska (ta navíc vrací 403).
        vzor_clanku=re.compile(r"/aktuality/"),
    ),
    "drbna": Zdroj(
        kod="drbna",
        nazev="Karlovarská Drbna",
        domena="karlovarska.drbna.cz",
        sitemapy=["https://karlovarska.drbna.cz/sitemap.xml"],
        prodleva=2.0,
        vzor_clanku=re.compile(r"/\d+-[a-z0-9-]+\.html$"),
    ),
    "denik": Zdroj(
        kod="denik",
        nazev="Chebský deník / Deník.cz",
        domena="chebsky.denik.cz",
        povoleno=False,
        duvod_zakazu=(
            "robots.txt Deníku má sekci 'AI bots protection' s "
            "'User-agent: ClaudeBot / Claude-Web / anthropic-ai' a "
            "'Disallow: /'. Automatický sběr je tím zakázaný na celé doméně "
            "i poddoménách. Nescrapujeme."
        ),
    ),
}

# Dotazy do stránkovaného hledání (jen zdroje s `hledani`).
HLEDANE_DOTAZY = [
    "Mariánské Lázně",
    "mariánskolázeňský",
    "Hurajčík",
    "vila LIL",
]


# --------------------------------------------------------------------------
# Slušné stahování
# --------------------------------------------------------------------------

_posledni_pozadavek: dict[str, float] = {}


def _v_cache(url: str, max_age: int) -> bool:
    """Je URL v diskové cache jádra a dost čerstvá? Kopíruje klíč z core.fetch.

    Potřebujeme to vědět dopředu: prodlevu má smysl držet jen před skutečným
    síťovým požadavkem, ne před čtením z disku. Jinak by opakovaný běh přes
    rozhlas (prodleva 10 s) trval hodinu i bez jediného spojení.
    """
    key = hashlib.sha256(url.encode()).hexdigest()[:24]
    p = CACHE / "txt" / f"{key}.txt"
    return p.exists() and (time.time() - p.stat().st_mtime) < max_age


def stahni(url: str, z: Zdroj, *, max_age: int = 30 * 86_400) -> str:
    """Stáhne stránku a přitom drží prodlevu danou zdrojem."""
    if not z.povoleno:
        raise ZdrojSelhal(f"{z.nazev}: sběr zakázán — {z.duvod_zakazu}")
    if not _v_cache(url, max_age):
        posl = _posledni_pozadavek.get(z.kod, 0.0)
        cekat = z.prodleva - (time.time() - posl)
        if cekat > 0:
            time.sleep(cekat)
        _posledni_pozadavek[z.kod] = time.time()
    return fetch(url, max_age=max_age)  # type: ignore[return-value]


def robots_zakazuje(z: Zdroj) -> str | None:
    """Vrátí důvod zákazu, nebo None. Kontroluje i pravidla pro AI boty.

    Schválně se neptáme, co robots.txt dovoluje prohlížečové hlavičce —
    ptáme se, co dovoluje NÁM. Když je kdekoliv 'ClaudeBot: Disallow: /',
    je to zákaz a tečka.
    """
    try:
        txt = fetch(f"https://{z.domena}/robots.txt", max_age=7 * 86_400)
    except ZdrojSelhal:
        return None  # robots.txt nedostupný — nebereme jako zákaz, ale ani jako svolení navíc
    assert isinstance(txt, str)

    # Skupinu tvoří několik po sobě jdoucích 'User-agent:' řádků; první
    # direktiva pod nimi ten výčet uzavře. Prázdný řádek nic neznamená,
    # proto se skupina resetuje až dalším 'User-agent:' po direktivě —
    # jinak by se zákaz z jedné skupiny přelil do následující.
    skupina: list[str] = []
    predchozi_ua = False
    nase_skupina = False
    for radek in txt.splitlines():
        radek = radek.split("#")[0].strip()
        if not radek or ":" not in radek:
            continue
        klic, _, hod = radek.partition(":")
        klic, hod = klic.strip().lower(), hod.strip()
        if klic == "user-agent":
            if not predchozi_ua:
                skupina = []
            skupina.append(hod.lower())
            predchozi_ua = True
            nase_skupina = any(u in NASE_IDENTITY for u in skupina)
        else:
            predchozi_ua = False
            if klic == "disallow" and nase_skupina and hod == "/":
                nase = [u for u in skupina if u in NASE_IDENTITY]
                return (f"robots.txt zakazuje '{', '.join(nase)}' "
                        f"na celé doméně (Disallow: /)")
    return None


# --------------------------------------------------------------------------
# Index URL
# --------------------------------------------------------------------------

def _locs(xml: str) -> list[tuple[str, str | None]]:
    out = []
    for blok in re.findall(r"<url>(.*?)</url>|<sitemap>(.*?)</sitemap>", xml, re.S):
        kus = blok[0] or blok[1]
        m = re.search(r"<loc>(.*?)</loc>", kus, re.S)
        if not m:
            continue
        lm = re.search(r"<lastmod>(.*?)</lastmod>", kus, re.S)
        out.append((m.group(1).strip(), lm.group(1).strip() if lm else None))
    return out


def sitemap_urls(z: Zdroj, log: Log) -> list[tuple[str, str | None]]:
    """Rozbalí sitemapu včetně vnořených indexů. Vrací (url, lastmod)."""
    fronta = list(z.sitemapy)
    videno: set[str] = set()
    vysledek: list[tuple[str, str | None]] = []
    while fronta:
        sm = fronta.pop(0)
        if sm in videno:
            continue
        videno.add(sm)
        xml = stahni(sm, z, max_age=86_400)
        polozky = _locs(xml)
        je_index = "<sitemapindex" in xml[:400]
        if je_index:
            fronta += [u for u, _ in polozky]
        else:
            vysledek += polozky
    log.info(f"{z.nazev}: sitemapa dala {len(vysledek)} URL z {len(videno)} souborů")
    if not vysledek:
        raise ZdrojSelhal(f"{z.nazev}: sitemapa neobsahuje žádné URL")
    return vysledek


def je_clanek(z: Zdroj, url: str) -> bool:
    """Je to URL zprávy, nebo rozcestník? Odděleno od `zajimave` schválně:
    ve vyhledávání chceme JEN tuhle podmínku — tam je smysl v tom najít
    články, které mají město až v textu, a slug o něm mlčí."""
    return not z.vzor_clanku or bool(z.vzor_clanku.search(url))


def zajimave(url: str, z: Zdroj | None = None) -> bool:
    """Předfiltr sitemapy — levný, bez jediného síťového požadavku.
    Musí platit obojí: je to zpráva a už ze slugu je vidět Mariánky.
    """
    if z is not None and not je_clanek(z, url):
        return False
    return any(v in url.lower() for v in SLUG_VZORY)


def hledani_urls(z: Zdroj, log: Log, max_stran: int = 25) -> list[str]:
    """Projde stránkované vyhledávání. Chytá zmínky mimo titulek."""
    if not z.hledani:
        return []
    nalez: set[str] = set()
    for dotaz in HLEDANE_DOTAZY:
        q = dotaz.replace(" ", "+")
        predchozi: set[str] = set()
        for p in range(1, max_stran + 1):
            url = z.hledani.format(p=p, q=q)
            try:
                html = stahni(url, z, max_age=3 * 86_400)
            except ZdrojSelhal:
                break
            # Tady se ML nefiltruje — to je celý smysl hledání. Ořízne se
            # jen tvar URL, ať nelezeme na rubriky a rozcestníky.
            odkazy = {u for u in re.findall(
                rf"https?://{re.escape(z.domena)}/[a-z0-9][a-z0-9\-]{{12,}}/", html)
                if je_clanek(z, u)}
            # Poslední stránka se opakuje nebo je prázdná — dál nemá smysl jít.
            if not odkazy or odkazy == predchozi:
                break
            predchozi = odkazy
            nalez |= odkazy
    log.info(f"{z.nazev}: hledání dalo {len(nalez)} URL")
    return sorted(nalez)


# --------------------------------------------------------------------------
# Detail článku
# --------------------------------------------------------------------------

def _metatabulka(doc: HTMLParser) -> dict[str, str]:
    """Posbírá <meta> do slovníku {property|name: content}.

    Schválně přes selectolax, ne přes regulární výraz. Původní verze
    hledala meta tagy vzorem s `.*?` a `re.DOTALL`; na 130 kB stránce
    kraje spotřeboval JEDEN nenalezený klíč 2,4 sekundy čistého CPU
    katastrofickým backtrackingem a dávka se kvůli tomu vlekla.
    Parser projde dokument jednou a je to.
    """
    tab: dict[str, str] = {}
    for tag in doc.css("meta"):
        a = tag.attributes
        klic = a.get("property") or a.get("name")
        obsah = a.get("content")
        if klic and obsah and klic.lower() not in tab:
            tab[klic.lower()] = obsah
    return tab


def _meta(tab: dict[str, str], *klice: str) -> str | None:
    for k in klice:
        v = tab.get(k.lower())
        if v and v.strip():
            return cistit(v)
    return None


def _datum(doc: HTMLParser, tab: dict[str, str], html: str) -> str | None:
    """Datum vydání ze stránky. Když ho nenajdeme, vrací None — nehádá se.

    POZOR: `lastmod` ze sitemapy je u všech tří zdrojů razítko poslední
    migrace CMS, ne datum vydání (ověřeno: článek rozhlasu se sitemap
    lastmod 2014 má article:published_time 2011-05-16, článek kraje
    s lastmod 2024 má <time datetime="2012-04-23">). Autoritativní je
    jedině metadatum na stránce.
    """
    kandidati = [
        _meta(tab, "article:published_time", "article:published", "datePublished"),
    ]
    # JSON-LD: `[^"]+` je omezená třída, backtracking tu nehrozí.
    m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
    if m:
        kandidati.append(m.group(1))
    for t in doc.css("time"):
        dt = t.attributes.get("datetime")
        if dt:
            kandidati.append(dt)
            break
    for k in kandidati:
        if not k:
            continue
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", k.strip())
        if m:
            try:
                return datetime(*(int(g) for g in m.groups())).strftime("%Y-%m-%d")  # type: ignore[arg-type]
            except ValueError:
                continue
    return None


def _titulek(doc: HTMLParser, tab: dict[str, str]) -> str | None:
    t = _meta(tab, "og:title")
    if not t:
        uzel = doc.css_first("title")
        t = cistit(uzel.text()) if uzel else None
    if not t:
        return None
    # Weby si za titulek lepí název redakce — pryč s tím.
    for ocasek in (" | Karlovy Vary", " | KV Kraj", " – Karlovarská Drbna",
                   " - Karlovarská Drbna", " | Zprávy Karlovarsko"):
        if t.endswith(ocasek):
            t = t[: -len(ocasek)]
    return t.strip(" |–-") or None


def clanek_id(z: Zdroj, url: str) -> str:
    cesta = re.sub(rf"^https?://{re.escape(z.domena)}/", "", url).strip("/")
    cesta = re.sub(r"\.html?$", "", cesta)
    return f"{z.kod}-{slug(cesta, 70)}"


def nacti_clanek(z: Zdroj, url: str) -> dict | None:
    """Stáhne článek a vrátí ověřená metadata + perex jako pracovní podklad.

    Vrací None, když se město ve skutečnosti nezmiňuje (předfiltr slugu je
    široký schválně) nebo když stránka nemá titulek.
    """
    html = stahni(url, z)
    doc = HTMLParser(html)
    tab = _metatabulka(doc)
    titulek = _titulek(doc, tab)
    if not titulek:
        return None
    perex = _meta(tab, "og:description", "description") or ""
    if not any(v.search(f"{titulek} {perex}") for v in TEXT_VZORY):
        return None
    return {
        "id": clanek_id(z, url),
        "titulek": titulek,
        "zdroj": z.nazev,
        "datum": _datum(doc, tab, html),
        "url": url,
        "shrnuti": None,
        "osoby": sorted({s for v, s in OSOBY_VZORY if v.search(f"{titulek} {perex}")}),
        "tagy": [],
        "stav": "k-shrnuti",
        "_perex": perex,  # odstraní se před uložením do data/
    }


# --------------------------------------------------------------------------
# Ukládání
# --------------------------------------------------------------------------

def uloz_clanky(clanky: list[dict]) -> None:
    """Uloží články BEZ perexu. Autorský text cizí redakce do data/ nepatří."""
    cisto = []
    for c in sorted(clanky, key=lambda x: (x.get("datum") or "0000", x["id"]), reverse=True):
        cisto.append({k: v for k, v in c.items() if not k.startswith("_")})
    uloz(CLANKY, cisto)


_PODLE_NAZVU = {z.nazev: z for z in ZDROJE.values()}


def uklid(log: Log) -> int:
    """Vyhodí ze `clanky.json` záznamy, které nejsou zprávy.

    Filtr tvaru URL přibyl až poté, co první dávka stáhla i rozcestníky
    kraje (stránky příspěvkových organizací, přehled obce). Ty nemají
    datum vydání ani autora a v mediálním monitoringu nemají co dělat.
    Maže se hlasitě — vypíše se, co odchází a proč.
    """
    clanky = nacti(CLANKY) or []
    drzet, pryc = [], []
    for c in clanky:
        z = _PODLE_NAZVU.get(c["zdroj"])
        duvod = None
        if z and not je_clanek(z, c["url"]):
            duvod = "není zpráva, je to rozcestník"
        else:
            # Přeověření tématu z uloženého podkladu — bez jediného
            # síťového požadavku. Když se zpřísní TEXT_VZORY, tohle
            # z dat vymete, co dřív prošlo omylem.
            p = PODKLADY / f"{c['id']}.json"
            if p.exists():
                perex = json.loads(p.read_text(encoding="utf-8")).get("perex", "")
                if not any(v.search(f"{c['titulek']} {perex}") for v in TEXT_VZORY):
                    duvod = "netýká se Mariánských Lázní"
        if duvod:
            c["_duvod"] = duvod
            pryc.append(c)
        else:
            drzet.append(c)
    for c in pryc:
        log.info(f"úklid: {c['_duvod']} — {c['titulek'][:58]}")
    if pryc:
        uloz_clanky(drzet)
    log.info(f"úklid: ponecháno {len(drzet)}, smazáno {len(pryc)}")
    return len(pryc)


def uloz_podklad(c: dict) -> None:
    """Perex do cache (mimo git) — pracovní materiál pro sepsání shrnutí."""
    PODKLADY.mkdir(parents=True, exist_ok=True)
    (PODKLADY / f"{c['id']}.json").write_text(
        json.dumps(
            {"id": c["id"], "titulek": c["titulek"], "zdroj": c["zdroj"],
             "datum": c["datum"], "url": c["url"], "perex": c.get("_perex", "")},
            ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------
# Průzkum hloubky archivu
# --------------------------------------------------------------------------

def zmer_hloubku(log: Log, vzorek: int = 6) -> list[dict]:
    """Zjistí, jak hluboko každý zdroj reálně sahá.

    Neptá se, co si o archivu myslíme — sáhne na nejstarší kandidáty a
    přečte jim datum vydání ze stránky.
    """
    zprava = []
    for z in ZDROJE.values():
        rec: dict = {"kod": z.kod, "nazev": z.nazev, "domena": z.domena,
                     "povoleno": z.povoleno, "prodleva_s": z.prodleva}
        zakaz = z.duvod_zakazu or (robots_zakazuje(z) if z.povoleno else None)
        if zakaz:
            rec.update({"povoleno": False, "duvod_zakazu": zakaz,
                        "urls_celkem": 0, "urls_ml": 0,
                        "nejstarsi_datum": None, "nejnovejsi_datum": None})
            log.info(f"{z.nazev}: ZAKÁZÁNO — {zakaz}")
            zprava.append(rec)
            continue
        try:
            vsechny = sitemap_urls(z, log)
        except ZdrojSelhal as e:
            log.chyba(str(e))
            rec["chyba"] = str(e)
            zprava.append(rec)
            continue
        ml = [(u, m) for u, m in vsechny if zajimave(u, z)]
        rec["urls_celkem"] = len(vsechny)
        rec["urls_ml"] = len(ml)
        # Nejstarší podle lastmod jsou nejlepší kandidáti na dno archivu,
        # ale skutečné datum přečteme až na stránce.
        s_lastmod = sorted([x for x in ml if x[1]], key=lambda x: x[1])
        data = []
        for u, _ in s_lastmod[:vzorek] + s_lastmod[-2:]:
            try:
                html = stahni(u, z)
            except ZdrojSelhal:
                continue
            doc = HTMLParser(html)
            d = _datum(doc, _metatabulka(doc), html)
            if d:
                data.append(d)
        # Pozor na čtení těchhle dvou: jsou z VZORKU, ne z celého archivu.
        # `nejstarsi_overene` je proto dolní odhad hloubky — archiv může
        # sahat ještě dál, rozhodně ne míň.
        rec["nejstarsi_overene"] = min(data) if data else None
        rec["nejnovejsi_ve_vzorku"] = max(data) if data else None
        rec["velikost_vzorku"] = len(data)
        rec["lastmod_rozsah"] = (
            [min(m for _, m in ml if m)[:10], max(m for _, m in ml if m)[:10]]
            if any(m for _, m in ml) else None
        )
        log.info(
            f"{z.nazev}: {len(vsechny)} URL, z toho {len(ml)} o ML, "
            f"nejstarší ověřené vydání {rec['nejstarsi_datum']}"
        )
        zprava.append(rec)
    uloz(ZDROJE_STAV, {"overeno": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                       "zdroje": zprava})
    return zprava


# --------------------------------------------------------------------------
# Sběr
# --------------------------------------------------------------------------

def sber(zdroje: list[Zdroj], log: Log, *, od: str | None = None,
         limit: int | None = None, s_hledanim: bool = True) -> int:
    """Projde zdroje a doplní nové články.

    `od` (RRRR-MM-DD) zapíná inkrementální režim: kandidáti se ořežou už
    podle `lastmod` ze sitemapy, tedy dřív, než se cokoliv stáhne.
    Co se jednou stáhne, to se uloží — nic se po stažení nezahazuje.

    Vrací počet nově přidaných.
    """
    existuji = {c["id"]: c for c in (nacti(CLANKY) or [])}
    novych = 0

    for z in zdroje:
        if not z.povoleno:
            log.info(f"{z.nazev}: přeskočeno — {z.duvod_zakazu}")
            continue
        zakaz = robots_zakazuje(z)
        if zakaz:
            log.info(f"{z.nazev}: přeskočeno — {zakaz}")
            continue

        try:
            polozky = [(u, m) for u, m in sitemap_urls(z, log) if zajimave(u, z)]
        except ZdrojSelhal as e:
            log.chyba(f"{z.nazev}: {e}")
            continue

        # Týdenní inkrement filtruje PŘED stažením, podle lastmod ze sitemapy.
        # Pro historii je lastmod bezcenný (razítko migrace CMS), ale u
        # čerstvě vydaného článku odpovídá skutečnosti — a hlavně: ořezat
        # se musí předem. Kdybychom filtrovali až podle data na stažené
        # stránce, starý článek by se stáhl, zahodil, neuložil — a příští
        # týden by se stáhl znovu, protože by pořád nebyl mezi známými.
        if od:
            pred = len(polozky)
            polozky = [(u, m) for u, m in polozky if not m or m[:10] >= od]
            log.info(f"{z.nazev}: podle lastmod zbylo {len(polozky)} z {pred}")
        kandidati = [u for u, _ in polozky]
        if s_hledanim and z.hledani:
            try:
                kandidati += hledani_urls(z, log)
            except ZdrojSelhal as e:
                log.chyba(f"{z.nazev} (hledání): {e}")

        # Už uložené přeskočíme — inkrement se tím stává levným.
        kandidati = sorted({u for u in kandidati if clanek_id(z, u) not in existuji})
        if limit:
            kandidati = kandidati[:limit]
        log.info(f"{z.nazev}: {len(kandidati)} nových kandidátů ke stažení")

        pridano = mimo = 0
        for i, u in enumerate(kandidati, 1):
            try:
                c = nacti_clanek(z, u)
            except ZdrojSelhal as e:
                log.chyba(f"{u}: {e}")
                c = None
            if c is None:
                mimo += 1
            else:
                existuji[c["id"]] = c
                uloz_podklad(c)
                pridano += 1
                novych += 1
            # Průběžné uložení a hlášení postupu patří KAŽDÉ pětadvacáté
            # položce, ne jen té, která prošla filtrem. U hledání na
            # Karlovarsku je většina kandidátů mimo téma, takže dřív se
            # hlášení skoro neozvalo a běh vypadal jako zaseknutý.
            if i % 25 == 0 or i == len(kandidati):
                uloz_clanky(list(existuji.values()))
                log.info(f"{z.nazev}: {i}/{len(kandidati)}, "
                         f"uloženo {pridano}, mimo téma {mimo}")
        log.info(f"{z.nazev}: přidáno {pridano}, mimo téma {mimo}")
        log.pricti(pridano)

    uloz_clanky(list(existuji.values()))
    stav = nacti(STAV) or {}
    for z in zdroje:
        if z.povoleno:
            stav[z.kod] = {"posledni_beh": datetime.now(timezone.utc).isoformat()}
    uloz(STAV, stav)
    return novych


# --------------------------------------------------------------------------
# Shrnutí — most mezi kódem a modelem
# --------------------------------------------------------------------------

def podklady(limit: int | None = None) -> list[dict]:
    """Články čekající na shrnutí, včetně perexu z cache jako podkladu."""
    out = []
    for c in nacti(CLANKY) or []:
        if c.get("shrnuti"):
            continue
        p = PODKLADY / f"{c['id']}.json"
        perex = json.loads(p.read_text(encoding="utf-8"))["perex"] if p.exists() else ""
        out.append({"id": c["id"], "titulek": c["titulek"], "zdroj": c["zdroj"],
                    "datum": c["datum"], "url": c["url"], "perex_zdroje": perex})
        if limit and len(out) >= limit:
            break
    return out


def pridat_rucne(cesta: Path, log: Log) -> int:
    """Přidá záznamy, které sběrač sám dosáhnout nemůže.

    Dvě situace, na které to je:
      * celostátní média — nemají společnou sitemapu, dohledávají se
        webovým vyhledáváním a záznam sem přinese člověk (nebo Claude),
      * zdroje se zákazem sběru (Deník) — ruční přečtení a odkaz je něco
        jiného než automatický scraping, ale i tak se ukládá jen odkaz
        a vlastní shrnutí, nikdy převzatý text.

    Vstup: [{"titulek", "zdroj", "datum"|null, "url", "shrnuti",
             "tagy": [...], "osoby": [...]}]
    """
    vstup = json.loads(cesta.read_text(encoding="utf-8"))
    clanky = {c["id"]: c for c in (nacti(CLANKY) or [])}
    platne = platne_tagy()
    chyby, pridano = [], 0

    for v in vstup:
        url = (v.get("url") or "").strip()
        if not url.startswith("http"):
            chyby.append(f"chybí nebo vadné url: {v.get('titulek', '?')}")
            continue
        if not v.get("titulek") or not v.get("zdroj"):
            chyby.append(f"{url}: chybí titulek nebo zdroj")
            continue
        spatne = [t for t in v.get("tagy", []) if t not in platne]
        if spatne:
            chyby.append(f"{url}: tagy mimo číselník: {spatne}")
            continue
        datum = v.get("datum")
        if datum and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", datum):
            chyby.append(f"{url}: datum není ve tvaru RRRR-MM-DD: {datum}")
            continue
        domena = re.sub(r"^https?://", "", url).split("/")[0]
        ident = f"rucne-{slug(domena + '-' + url.split(domena)[-1], 70)}"
        if ident in clanky:
            continue
        clanky[ident] = {
            "id": ident,
            "titulek": cistit(v["titulek"]),
            "zdroj": v["zdroj"],
            "datum": datum,          # None, když se datum nedohledalo — nehádá se
            "url": url,
            "shrnuti": cistit(v["shrnuti"]) if v.get("shrnuti") else None,
            "osoby": sorted(set(v.get("osoby", []))),
            "tagy": v.get("tagy", [])[:3],
            "stav": "hotovo" if v.get("shrnuti") else "k-shrnuti",
            "puvod": "rucne",
        }
        pridano += 1

    if chyby:
        for ch in chyby:
            log.chyba(ch)
        raise ZdrojSelhal(f"ruční vstup zamítnut, {len(chyby)} vadných záznamů")

    uloz_clanky(list(clanky.values()))
    log.info(f"ručně přidáno {pridano} záznamů")
    log.pricti(pridano)
    return pridano


def doplnit(cesta: Path, log: Log) -> int:
    """Zaválcuje hotová shrnutí. Tagy VALIDUJE proti číselníku.

    Vstup: [{"id": ..., "shrnuti": "dvě věty", "tagy": [...], "osoby": [...]}]
    Neplatný tag nebo neznámé id shodí běh — tichá tolerance by do dat
    pustila nesmysl, který by pak nikdo nenašel.
    """
    vstup = json.loads(cesta.read_text(encoding="utf-8"))
    clanky = {c["id"]: c for c in (nacti(CLANKY) or [])}
    platne = platne_tagy()
    chyby = []

    for v in vstup:
        if v["id"] not in clanky:
            chyby.append(f"neznámé id: {v['id']}")
            continue
        spatne = [t for t in v.get("tagy", []) if t not in platne]
        if spatne:
            chyby.append(f"{v['id']}: tagy mimo číselník: {spatne}")
            continue
        if not v.get("shrnuti") or len(v["shrnuti"].split()) < 8:
            chyby.append(f"{v['id']}: prázdné nebo příliš krátké shrnutí")
            continue
        c = clanky[v["id"]]
        c["shrnuti"] = cistit(v["shrnuti"])
        if v.get("tagy"):
            c["tagy"] = v["tagy"][:3]
        if v.get("osoby"):
            c["osoby"] = sorted(set(c.get("osoby", [])) | set(v["osoby"]))
        c["stav"] = "hotovo"

    if chyby:
        for ch in chyby:
            log.chyba(ch)
        raise ZdrojSelhal(f"doplnění zamítnuto, {len(chyby)} vadných záznamů")

    uloz_clanky(list(clanky.values()))
    log.info(f"doplněno {len(vstup)} shrnutí")
    return len(vstup)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def hlavni() -> int:
    ap = argparse.ArgumentParser(description="B3 — mediální monitoring")
    ap.add_argument("--historie", action="store_true",
                    help="dávkové natažení archivu, co nejhlouběji")
    ap.add_argument("--tyden", action="store_true",
                    help="inkrement — jen články za posledních 8 dní")
    ap.add_argument("--hloubka", action="store_true",
                    help="jen průzkum: jak hluboko který archiv sahá")
    ap.add_argument("--podklady", action="store_true",
                    help="vypíše na stdout články čekající na shrnutí")
    ap.add_argument("--doplnit", metavar="SOUBOR",
                    help="zaválcuje hotová shrnutí ze souboru")
    ap.add_argument("--rucne", metavar="SOUBOR",
                    help="přidá ručně dohledané záznamy (celostátní média)")
    ap.add_argument("--zdroj", help="omezí na jeden zdroj (kód)")
    ap.add_argument("--limit", type=int, help="max. kandidátů na zdroj")
    ap.add_argument("--bez-hledani", action="store_true",
                    help="vynechá stránkované hledání, jen sitemapy")
    ap.add_argument("--uklid", action="store_true",
                    help="vyhodí z dat záznamy, které nejsou zprávy")
    args = ap.parse_args()

    log = Log("media")

    if args.podklady:
        print(json.dumps(podklady(args.limit), ensure_ascii=False, indent=2))
        return 0

    if args.doplnit or args.rucne:
        try:
            if args.doplnit:
                doplnit(Path(args.doplnit), log)
            if args.rucne:
                pridat_rucne(Path(args.rucne), log)
        except ZdrojSelhal as e:
            log.chyba(str(e))
            log.uzavri()
            return 1
        log.uzavri()
        return 0

    if args.uklid:
        uklid(log)
        log.uzavri()
        return 0

    if args.hloubka:
        zmer_hloubku(log)
        log.uzavri()
        return 0

    if not (args.historie or args.tyden):
        ap.error("vyber režim: --historie, --tyden, --hloubka, --uklid, "
                 "--podklady, --rucne nebo --doplnit")

    vyber = [ZDROJE[args.zdroj]] if args.zdroj else list(ZDROJE.values())
    if args.zdroj and args.zdroj not in ZDROJE:
        ap.error(f"neznámý zdroj {args.zdroj}, znám: {', '.join(ZDROJE)}")

    od = None
    if args.tyden:
        od = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%d")
        log.info(f"inkrementální režim, beru články od {od}")

    novych = sber(vyber, log, od=od, limit=args.limit,
                  s_hledanim=not args.bez_hledani)
    log.info(f"celkem nových článků: {novych}")
    vysledek = log.uzavri()
    return 0 if vysledek["uspech"] else 1


if __name__ == "__main__":
    raise SystemExit(hlavni())
