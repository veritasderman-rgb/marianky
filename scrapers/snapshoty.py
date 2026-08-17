"""Hlídání změn na webu města — otisky stránek a strukturovaný diff.

PROČ TO EXISTUJE: muml.cz nemá RSS (ověřeno, /rss i /rss.xml vracejí 404).
Dokumenty z úřední desky navíc umí zmizet nebo se tiše přepsat, aniž by se
kdekoliv objevila zmínka. Jediná obrana je pravidelně brát otisk sledovaných
stránek a porovnávat ho s tím minulým.

CO DĚLÁ NAVÍC PROTI OBYČEJNÉMU DIFFU:

1. **Normalizuje před hashováním.** Bílé znaky, pořadí položek a cache-busting
   parametry v URL (``?gcm_date=1475683145``, ``?kshow=15``) se vyhazují, takže
   se hlídač nespustí pokaždé, když web přegeneruje odkazy.

2. **Diffuje položky, ne řetězce.** Výsledek neříká „něco se změnilo", ale
   *co* přibylo, *co* zmizelo a *u čeho* se změnil název nebo datum sejmutí.

3. **Rozlišuje plánované sejmutí od tichého zmizení.** Dokument, kterému
   vypršelo „Datum sejmutí", odchází z úřední desky podle zákona — to není
   zpráva. Dokument, který zmizel dřív (nebo bez uvedeného data sejmutí),
   zpráva je a hlásí se zvlášť jako ``zmizelo_predcasne``.

Použití:

    python3 scrapers/snapshoty.py                # zkontroluje vše a uloží
    python3 scrapers/snapshoty.py uredni-deska   # jen jednu stránku
    python3 scrapers/snapshoty.py --neukladat    # jen ukáže rozdíl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from selectolax.parser import HTMLParser

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import core  # noqa: E402
from lib.core import ZdrojSelhal  # noqa: E402

BASE = "https://www.muml.cz"
SNAPSHOTY = "mesto/snapshots"
ZMENY_LOG = f"{SNAPSHOTY}/_zmeny.json"

# Parametry, které nenesou identitu dokumentu — jen stav prohlížení nebo
# obcházení cache. Do klíče položky se nepočítají.
SMETNI_PARAMY = {
    "gcm_date", "kshow", "show", "archiv_rok", "page", "hl_text", "pismeno",
    "filtr", "_", "t", "v", "rnd", "cache", "ts",
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "fbclid",
}


# Stránky, které hlídáme. `nazev` se propisuje do hlášek pro čtenáře.
SLEDOVANE: dict[str, dict] = {
    # Živá deska je ta důležitá — právě odsud dokumenty mizí.
    "uredni-deska": {
        "url": f"{BASE}/urad/uredni-deska/",
        "nazev": "Úřední deska",
        "uredni_deska": True,
    },
    # Archiv složek drží dokumenty vyvěšené trvale; když odsud něco zmizí,
    # je to taky zpráva, jen jiného druhu.
    "uredni-deska-archiv": {
        "url": f"{BASE}/urad/uredni-deska-archiv/",
        "nazev": "Archiv složek úřední desky",
        "uredni_deska": True,
    },
    "novinky": {
        "url": f"{BASE}/aktualne/novinky/",
        "nazev": "Novinky města",
    },
    "kalendar-akci": {
        "url": f"{BASE}/aktualne/kalendar-akci/",
        "nazev": "Kalendář akcí (rozcestník)",
    },
    "zpravodaj-mesta": {
        "url": f"{BASE}/aktualne/zpravodaj-mesta/",
        "nazev": "Archiv zpravodaje",
    },
    "zastupitele": {
        "url": f"{BASE}/samosprava/zastupitelstvo/clenove-1/",
        "nazev": "Členové zastupitelstva",
    },
    "terminy-zasedani": {
        "url": f"{BASE}/samosprava/zastupitelstvo/terminy-zasedani/",
        "nazev": "Termíny zasedání zastupitelstva",
    },
    "online-prenos": {
        "url": f"{BASE}/samosprava/zastupitelstvo/online-prenos-jednani/",
        "nazev": "Online přenos jednání",
    },
    "vedeni-mesta": {
        "url": f"{BASE}/samosprava/vedeni-mesta/",
        "nazev": "Vedení města",
    },
    "obchodni-spolecnosti": {
        "url": f"{BASE}/urad/povinne-informace/subjekt-obchodni-spolecnosti-81.html",
        "nazev": "Obchodní společnosti města",
    },
    "povinne-informace": {
        "url": f"{BASE}/urad/povinne-informace/",
        "nazev": "Povinně zveřejňované informace",
    },
    "telefonni-seznam": {
        "url": f"{BASE}/kontakty/telefonni-seznam/",
        "nazev": "Telefonní seznam úřadu",
    },
    "volna-mista": {
        "url": f"{BASE}/urad/volna-mista/",
        "nazev": "Volná místa na úřadu",
    },
    "strategicke-dokumenty": {
        "url": f"{BASE}/urad/dokumenty/strategicke-dokumenty/",
        "nazev": "Strategické dokumenty",
    },
    "dokumenty": {
        "url": f"{BASE}/urad/dokumenty/",
        "nazev": "Dokumenty úřadu",
    },
}


# --------------------------------------------------------------------------
# Normalizace
# --------------------------------------------------------------------------

def normalizuj_url(url: str | None, base: str = BASE) -> str | None:
    """Zbaví URL cache-busting a zobrazovacích parametrů a kotvy.

    Bez toho by se hlídač spouštěl pokaždé, když web přegeneruje ``?gcm_date=``
    nebo když se tentýž dokument objeví pod jinou kategorií (``?kshow=``).
    """
    if not url:
        return None
    u = urlparse(urljoin(base + "/", url))
    q = [(k, v) for k, v in parse_qsl(u.query) if k not in SMETNI_PARAMY]
    q.sort()
    return urlunparse((u.scheme, u.netloc, u.path.rstrip("/") or "/", "", urlencode(q), ""))


def normalizuj_text(node) -> str:
    """Text obsahové části: jednotné bílé znaky, prázdné řádky pryč.

    Cíl je, aby se hash změnil jen tehdy, když se změnil *obsah*, ne když
    šablona přesunula mezeru nebo přidala odřádkování.
    """
    text = (node.text() or "").replace("\xa0", " ").replace("​", "")
    radky = [re.sub(r"\s+", " ", r).strip() for r in text.split("\n")]
    return "\n".join(r for r in radky if r)


def _hlavni(html: str, url: str):
    p = HTMLParser(html)
    for t in p.css("script, style, noscript, form, .pagination, .social-share, .breadcrumb"):
        t.decompose()
    node = p.css_first(".gcm-main") or p.css_first("main")
    if node is None:
        raise ZdrojSelhal(f"Na {url} chybí obsahový blok — změnila se šablona webu?")
    return node


def _cistit(t: str | None) -> str | None:
    if not t:
        return None
    return re.sub(r"\s+", " ", t.replace("\xa0", " ")).strip() or None


# --------------------------------------------------------------------------
# Rozpad stránky na položky
# --------------------------------------------------------------------------

def _polozka(klic: str, nazev: str | None, url: str | None, **detail) -> dict:
    return {
        "klic": klic,
        "nazev": nazev,
        "url": url,
        "detail": {k: v for k, v in detail.items() if v is not None},
    }


def polozky_stranky(node) -> list[dict]:
    """Rozloží stránku na porovnatelné položky.

    Každý typ výpisu na webu města má vlastní rozpoznávač; když nesedí ani
    jeden, spadne se na obecný seznam odkazů v obsahu. Díky tomu umí diff
    říct „zmizel dokument X", ne jen „stránka se změnila".
    """
    out: list[dict] = []

    # 1) Úřední deska
    for kat in node.css(".official-desk-list .category"):
        kat_nazev = _cistit(kat.css_first(".category-name a").text()) if kat.css_first(".category-name a") else None
        for it in kat.css(".item"):
            a = it.css_first(".item-href")
            if a is None:
                continue
            odkaz = normalizuj_url(a.attributes.get("href"))
            out.append(_polozka(
                odkaz or _cistit(a.text()) or "?",
                _cistit(a.text()),
                odkaz,
                kategorie=kat_nazev,
                vyveseno_od=core.parse_datum(_cistit(it.css_first(".item-date-from").text()) or "")
                if it.css_first(".item-date-from") else None,
                vyveseno_do=core.parse_datum(_cistit(it.css_first(".item-date-to").text()) or "")
                if it.css_first(".item-date-to") else None,
            ))
    if out:
        return out

    # 2) Novinky a další výpisy událostí
    for a in node.css("a.event-link"):
        ev = a.css_first(".event")
        odkaz = normalizuj_url(a.attributes.get("href"))
        nazev = _cistit(ev.css_first(".event-name").text()) if ev is not None and ev.css_first(".event-name") else None
        datum = None
        if ev is not None and ev.css_first(".event-info-value.event-date"):
            datum = core.parse_datum(ev.css_first(".event-info-value.event-date").text() or "")
        out.append(_polozka(odkaz or nazev or "?", nazev, odkaz, datum=datum))
    if out:
        return out

    # 3) Osoby (zastupitelé, telefonní seznam, firmy)
    for p in node.css(".person"):
        h = p.css_first("h2") or p.css_first("h3")
        if h is None:
            continue
        jmeno = _cistit(h.text())
        if not jmeno:
            continue
        a = h.css_first("a[href]") or p.css_first("a[href*='/osoba-']")
        odkaz = normalizuj_url(a.attributes.get("href")) if a is not None else None
        funkce = _cistit(p.css_first(".function").text()) if p.css_first(".function") else None
        if funkce is None:
            subjekt = p.css_first("a[href*='/subjekt-']")
            if subjekt is not None:
                celek = _cistit(p.text()) or ""
                funkce = _cistit(celek.replace(jmeno, "", 1).split(" - ")[0]) if celek else None
        mail = p.css_first("a[href^=mailto]")
        out.append(_polozka(
            odkaz or jmeno, jmeno, odkaz,
            funkce=funkce,
            email=_cistit(mail.text()) if mail is not None else None,
        ))
    if out:
        return out

    # 4) Vedení města — widgety „funkce → jméno"
    for w in node.css(".contentbox .widget"):
        funkce = _cistit(w.css_first("h2.title").text()) if w.css_first("h2.title") else None
        jmeno = _cistit(w.css_first(".content h3").text()) if w.css_first(".content h3") else None
        if funkce and jmeno:
            out.append(_polozka(core.slug(funkce), funkce, None, jmeno=jmeno))
    if out:
        return out

    # 5) Strom podřízených subjektů
    for a in node.css(".contats-subject-tree a[href]"):
        nazev = _cistit(a.text())
        odkaz = normalizuj_url(a.attributes.get("href"))
        if nazev:
            out.append(_polozka(odkaz or nazev, nazev, odkaz))
    if out:
        return out

    # 6) Obecný zbytek: odkazy a soubory v obsahu, plus položky seznamů
    for a in node.css("a[href]"):
        nazev = _cistit(a.text())
        odkaz = normalizuj_url(a.attributes.get("href"))
        if nazev and odkaz:
            out.append(_polozka(odkaz, nazev, odkaz))
    for li in node.css("li"):
        if li.css_first("a"):
            continue
        t = _cistit(li.text())
        if t:
            out.append(_polozka("li:" + core.slug(t, 120), t, None))
    return out


def _otisk_hash(text: str, polozky: list[dict]) -> str:
    """Hash nad normalizovaným obsahem — na pořadí položek nezáleží."""
    kanon = json.dumps(
        {
            "text": text,
            "polozky": sorted(
                ({"klic": p["klic"], "nazev": p["nazev"], "detail": p["detail"]} for p in polozky),
                key=lambda p: p["klic"] or "",
            ),
        },
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(kanon.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Otisk a porovnání
# --------------------------------------------------------------------------

def otisk(slug: str, *, max_age: int = 0) -> dict:
    """Stáhne sledovanou stránku a udělá z ní normalizovaný otisk."""
    if slug not in SLEDOVANE:
        raise ZdrojSelhal(f"Neznámá sledovaná stránka '{slug}'")
    cfg = SLEDOVANE[slug]
    html = core.fetch(cfg["url"], max_age=max_age)
    if not isinstance(html, str):  # pragma: no cover
        html = html.decode("utf-8", errors="replace")

    node = _hlavni(html, cfg["url"])
    text = normalizuj_text(node)
    polozky = polozky_stranky(node)
    if not text:
        raise ZdrojSelhal(f"Otisk {slug} je prázdný — {cfg['url']} nejspíš vrátil chybovou stránku")

    return {
        "slug": slug,
        "nazev": cfg["nazev"],
        "url": cfg["url"],
        "cas": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hash": _otisk_hash(text, polozky),
        "polozek": len(polozky),
        "znaku": len(text),
        "polozky": polozky,
        "text": text,
    }


def nacti_otisk(slug: str) -> dict | None:
    return core.nacti(f"{SNAPSHOTY}/{slug}.json")


def uloz_otisk(o: dict) -> Path:
    return core.uloz(f"{SNAPSHOTY}/{o['slug']}.json", o)


def _index(polozky: list[dict]) -> dict[str, dict]:
    return {p["klic"]: p for p in polozky if p.get("klic")}


def _radky(text: str) -> set[str]:
    return set(text.split("\n"))


def porovnej(stary: dict | None, novy: dict, *, dnes: str | None = None) -> dict:
    """Strukturovaný rozdíl dvou otisků.

    Vrací, co přibylo, co zmizelo a co se změnilo — u úřední desky navíc
    odděluje plánované sejmutí od tichého zmizení.
    """
    dnes = dnes or date.today().isoformat()
    uredni = bool(SLEDOVANE.get(novy["slug"], {}).get("uredni_deska"))

    # Když se pod stejným jménem začne hlídat jiná adresa, není to změna webu,
    # ale změna konfigurace. Porovnávat staré s novým by vyrobilo falešnou
    # zprávu „zmizelo všechno" — bereme to jako první otisk.
    if stary is not None and stary.get("url") != novy["url"]:
        stary = None

    if stary is None:
        return {
            "slug": novy["slug"],
            "nazev": novy["nazev"],
            "url": novy["url"],
            "prvni_otisk": True,
            "zmena": False,
            "cas_stary": None,
            "cas_novy": novy["cas"],
            "hash_stary": None,
            "hash_novy": novy["hash"],
            "pribylo": [],
            "zmizelo": [],
            "zmizelo_predcasne": [],
            "zmenilo": [],
            "radku_pribylo": 0,
            "radku_zmizelo": 0,
            "zpravy": [f"{novy['nazev']}: pořízen první otisk ({novy['polozek']} položek), není s čím porovnávat."],
        }

    a, b = _index(stary.get("polozky", [])), _index(novy.get("polozky", []))
    pribylo = [b[k] for k in b if k not in a]
    zmizelo = [a[k] for k in a if k not in b]

    zmenilo = []
    for k in a.keys() & b.keys():
        pole = []
        if (a[k].get("nazev") or "") != (b[k].get("nazev") or ""):
            pole.append("nazev")
        for d in set(a[k].get("detail", {})) | set(b[k].get("detail", {})):
            if a[k].get("detail", {}).get(d) != b[k].get("detail", {}).get(d):
                pole.append(d)
        if pole:
            zmenilo.append({
                "klic": k,
                "nazev": b[k].get("nazev") or a[k].get("nazev"),
                "url": b[k].get("url"),
                "pole": sorted(pole),
                "pred": {"nazev": a[k].get("nazev"), **a[k].get("detail", {})},
                "po": {"nazev": b[k].get("nazev"), **b[k].get("detail", {})},
            })

    zmenilo.sort(key=lambda z: z["klic"] or "")  # ať je výstup mezi běhy stabilní

    # Zmizelý dokument z úřední desky: rozlišit řádné sejmutí od tichého zmizení.
    predcasne = []
    if uredni:
        zbyle = []
        for z in zmizelo:
            do = z.get("detail", {}).get("vyveseno_do")
            if do and do <= dnes:
                z = {**z, "duvod": "vypršelo datum sejmutí"}
                zbyle.append(z)
            else:
                z = {**z, "duvod": "zmizel bez uplynutí data sejmutí" if do else "zmizel, datum sejmutí nebylo uvedeno"}
                predcasne.append(z)
                zbyle.append(z)
        zmizelo = zbyle

    stare_r, nove_r = _radky(stary.get("text", "")), _radky(novy.get("text", ""))

    diff = {
        "slug": novy["slug"],
        "nazev": novy["nazev"],
        "url": novy["url"],
        "prvni_otisk": False,
        "zmena": stary.get("hash") != novy["hash"],
        "cas_stary": stary.get("cas"),
        "cas_novy": novy["cas"],
        "hash_stary": stary.get("hash"),
        "hash_novy": novy["hash"],
        "pribylo": pribylo,
        "zmizelo": zmizelo,
        "zmizelo_predcasne": predcasne,
        "zmenilo": zmenilo,
        "radku_pribylo": len(nove_r - stare_r),
        "radku_zmizelo": len(stare_r - nove_r),
    }
    diff["zpravy"] = _zpravy(diff)
    return diff


def _sklonuj(n: int, jeden: str, dva: str, pet: str) -> str:
    """1 dokument / 2 dokumenty / 5 dokumentů — ať hlášky nedrhnou."""
    if n == 1:
        return f"{n} {jeden}"
    if 2 <= n <= 4:
        return f"{n} {dva}"
    return f"{n} {pet}"


def _zpravy(diff: dict) -> list[str]:
    """Rozdíl přeložený do vět, které jde rovnou dát do týdenního přehledu."""
    n = diff["nazev"]
    out: list[str] = []

    def _jmeno(p: dict) -> str:
        return p.get("nazev") or p.get("url") or p.get("klic") or "bez názvu"

    for p in diff["pribylo"]:
        kdy = p.get("detail", {}).get("vyveseno_od") or p.get("detail", {}).get("datum")
        out.append(f"{n}: přibylo „{_jmeno(p)}“" + (f" ({kdy})" if kdy else ""))
    for p in diff["zmizelo_predcasne"]:
        do = p.get("detail", {}).get("vyveseno_do")
        out.append(
            f"{n}: ZMIZEL dokument „{_jmeno(p)}“ — {p.get('duvod')}"
            + (f", uvedené datum sejmutí bylo {do}" if do else "")
        )
    planovane = [p for p in diff["zmizelo"] if p not in diff["zmizelo_predcasne"]]
    if planovane:
        out.append(
            f"{n}: řádně sejmut "
            f"{_sklonuj(len(planovane), 'dokument', 'dokumenty', 'dokumentů')} "
            "(vypršelo datum sejmutí)"
        )
    for p in diff["zmenilo"]:
        out.append(f"{n}: změna u „{_jmeno(p)}“ — {', '.join(p['pole'])}")
    if not out and diff["zmena"]:
        out.append(
            f"{n}: změnil se text stránky "
            f"(+{diff['radku_pribylo']} / −{diff['radku_zmizelo']} řádků), seznam položek beze změny"
        )
    return out


# --------------------------------------------------------------------------
# Běh
# --------------------------------------------------------------------------

def zkontroluj(slug: str, *, ulozit: bool = True, log: core.Log | None = None) -> dict:
    """Vezme nový otisk, porovná ho s uloženým a případně ho uloží."""
    novy = otisk(slug)
    stary = nacti_otisk(slug)
    diff = porovnej(stary, novy)
    if ulozit:
        uloz_otisk(novy)
    if log is not None:
        if diff["prvni_otisk"]:
            log.info("první otisk", stranka=slug, polozek=novy["polozek"])
        elif diff["zmena"]:
            log.info(
                "ZMĚNA", stranka=slug,
                pribylo=len(diff["pribylo"]),
                zmizelo=len(diff["zmizelo"]),
                predcasne=len(diff["zmizelo_predcasne"]),
                zmenilo=len(diff["zmenilo"]),
            )
        else:
            log.info("beze změny", stranka=slug, polozek=novy["polozek"])
    return diff


def zkontroluj_vse(*, ulozit: bool = True, slugy: list[str] | None = None) -> list[dict]:
    """Projde všechny sledované stránky. Zapíše souhrn změn do historie."""
    log = core.Log("muml-snapshoty")
    vysledky: list[dict] = []
    for slug in (slugy or list(SLEDOVANE)):
        try:
            vysledky.append(zkontroluj(slug, ulozit=ulozit, log=log))
        except ZdrojSelhal as e:
            log.chyba(f"{slug}: {e}")

    zmeny = [d for d in vysledky if d["zmena"]]
    if zmeny and ulozit:
        historie = core.nacti(ZMENY_LOG, []) or []
        historie.append({
            "cas": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "zmenenych_stranek": len(zmeny),
            "zmeny": zmeny,
        })
        core.uloz(ZMENY_LOG, historie[-200:])  # držíme rozumně krátkou historii

    log.pricti(sum(len(d["pribylo"]) for d in vysledky))
    log.info(
        "souhrn",
        stranek=len(vysledky),
        zmenenych=len(zmeny),
        predcasne_zmizelo=sum(len(d["zmizelo_predcasne"]) for d in vysledky),
    )
    log.uzavri()
    return vysledky


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Hlídání změn na webu města")
    ap.add_argument("slugy", nargs="*", default=[], metavar="STRANKA",
                    help=f"které stránky zkontrolovat (výchozí: všechny). Volby: {', '.join(SLEDOVANE)}")
    ap.add_argument("--neukladat", action="store_true",
                    help="jen ukázat rozdíl, neaktualizovat uložené otisky")
    ap.add_argument("--seznam", action="store_true", help="vypsat sledované stránky")
    args = ap.parse_args(argv)

    nezname = [s for s in args.slugy if s not in SLEDOVANE]
    if nezname:
        ap.error(f"neznámé stránky: {', '.join(nezname)}. Volby: {', '.join(SLEDOVANE)}")

    if args.seznam:
        for slug, cfg in SLEDOVANE.items():
            print(f"{slug:24} {cfg['nazev']:38} {cfg['url']}")
        return 0

    vysledky = zkontroluj_vse(ulozit=not args.neukladat, slugy=args.slugy or None)
    for d in vysledky:
        for z in d["zpravy"]:
            print("  •", z, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
