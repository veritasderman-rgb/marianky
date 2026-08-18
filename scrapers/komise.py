"""Komise rady a výbory zastupitelstva — složení a zápisy z jednání.

PROČ TO STOJÍ ZA SBĚR
---------------------
Komise jsou místo, kde návrh vzniká dřív, než se o něm hlasuje v radě.
Zápis obsahuje větu typu „Komise kultury doporučuje Radě města podpořit
žádost o dotaci na pořízení nového projektoru pro Kino Slavia" — a týž
záměr se pak objeví v usnesení rady, které projekt už sbírá. Bez zápisů
je vidět rozhodnutí, ale ne to, kde se vzalo.

Zápisy navíc uvádějí HOSTY. Když na jednání komise přijde zástupce firmy,
která pak s městem uzavře smlouvu, je to stopa, kterou jinde nedohledáte.

CO SE SBÍRÁ
-----------
1. Struktura: 8 komisí rady a 2 výbory zastupitelstva — název, čím se
   zabývají, členové a jejich role.
2. Zápisy: rejstřík dokumentů na /urad/dokumenty/zapisy-z-komisi/
   (24 stránek po 20 položkách) a k nim PDF převedená na text.

Rozbor textu na účast, body a doporučení dělá `pipeline/komise_prehled.py`.
Tenhle modul jen stahuje a nic si nedomýšlí.

ZÁSADA: prázdno není nula. Komise, u které web neuvádí členy, dostane
prázdný seznam a poznámku — ne tvrzení, že členy nemá.
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import (  # noqa: E402
    CACHE,
    Log,
    ZdrojSelhal,
    fetch,
    parse_datum,
    pdf_na_text,
    potrebuje_ocr,
    slug,
    uloz,
)

ZAKLAD = "https://www.muml.cz"
ROZCESTNIK = f"{ZAKLAD}/samosprava/"
REJSTRIK_ZAPISU = f"{ZAKLAD}/urad/dokumenty/zapisy-z-komisi/"

# Strop stránkování. Rejstřík hlásí 24 stránek; strop je pojistka proti
# nekonečné smyčce, kdyby se odkaz „poslední stránka" rozbil.
MAX_STRANEK = 60


def _text(s: str) -> str:
    """HTML na čitelný text. Nic chytrého — jen tagy pryč a mezery srovnat."""
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</p>|</li>|</h[1-6]>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"[ \t\xa0]+", " ", html.unescape(s)).strip()


def _telo(stranka: str) -> str:
    """Obsah stránky bez hlavičky a navigace.

    Web města má v každé stránce kompletní menu (asi 6 000 znaků), ve kterém
    se jménem komise trefíte i tam, kde o ní nic není. Bereme proto až text
    za `<h1>`.
    """
    i = stranka.lower().find("<h1")
    return stranka[i:] if i > 0 else stranka


# ═════════════════════════  1. Struktura orgánů  ══════════════════════════

# Role, které web u osob uvádí. Cokoliv mimo seznam se uloží tak, jak je —
# vymýšlet si škatulku by znamenalo přepsat zdroj.
_ROLE = re.compile(
    r"^(předseda|předsedkyně|místopředseda|místopředsedkyně|člen komise|"
    r"členka komise|člen výboru|členka výboru|tajemník|tajemnice|zapisovatel|zapisovatelka)",
    re.IGNORECASE,
)


def _orgány_z_rozcestníku(log: Log) -> list[dict]:
    """Najde adresy všech komisí a výborů. Neopisujeme je ručně —
    komise vznikají a zanikají a ruční seznam by zastaral."""
    stranka = fetch(ROZCESTNIK, cache_key="samosprava-rozcestnik", max_age=3600)
    assert isinstance(stranka, str)

    nalezene: dict[str, dict] = {}
    for m in re.finditer(
        r'href="(/samosprava/(komise-rady|vybory-zastupitelstva)/([^"/#?]+)/)"[^>]*>\s*'
        r"(?:<[^>]+>\s*)*([^<]{2,80})",
        stranka,
    ):
        cesta, druh, klic, nazev = m.groups()
        nazev = html.unescape(nazev).strip()
        if not nazev or klic in {"", "index"}:
            continue
        nalezene.setdefault(cesta, {
            "id": klic,
            "nazev": nazev,
            "druh": "komise-rady" if druh == "komise-rady" else "vybor-zastupitelstva",
            "url": urljoin(ZAKLAD, cesta),
        })

    if not nalezene:
        raise ZdrojSelhal(
            "Na /samosprava/ nejsou žádné odkazy na komise ani výbory. "
            "Web města nejspíš změnil strukturu — sběrač se musí opravit, "
            "ne tiše vrátit prázdno."
        )
    log.info("nalezeno orgánů", pocet=len(nalezene))
    return sorted(nalezene.values(), key=lambda o: (o["druh"], o["nazev"]))


def _osoby_z_stranky(telo: str) -> list[dict]:
    """Členové orgánu.

    Web sází osobu jako odkaz do telefonního seznamu a hned za ním roli.
    Bereme dvojici odkaz + následující text; kdo v seznamu není odkazem,
    do výpisu nespadne a je to lepší než hádat podle formátování.
    """
    osoby: list[dict] = []
    for m in re.finditer(
        r'href="(/kontakty/telefonni-seznam/[^"]+)"[^>]*>\s*(?:<[^>]+>\s*)*([^<]{3,80})</a>(.{0,400})',
        telo,
        re.S,
    ):
        odkaz, jmeno, za = m.groups()
        jmeno = html.unescape(jmeno).strip()
        popis = _text(za)
        role_m = _ROLE.search(popis.lstrip())
        osoby.append({
            "jmeno": jmeno,
            "id": slug(jmeno),
            # Role, kterou web neuvádí, zůstává `null`. „Člen" by byl dohad.
            "role": role_m.group(0).lower() if role_m else None,
            "url": urljoin(ZAKLAD, odkaz),
        })
    return osoby


def _cinnost(telo: str) -> str | None:
    """Čím se orgán zabývá. Komise má nadpis „Činnost", výbor „Kontroluje"."""
    m = re.search(
        r"<h[23][^>]*>\s*(?:Činnost|Kontroluje|Náplň\s+činnosti)\s*</h[23]>(.{0,1500}?)<h[23]",
        telo,
        re.S | re.I,
    )
    if not m:
        return None
    t = _text(m.group(1))
    t = re.sub(r"\s*\n\s*", " ", t).strip()
    return t or None


def sklid_organy(log: Log) -> list[dict]:
    organy = _orgány_z_rozcestníku(log)
    ven: list[dict] = []
    for o in organy:
        try:
            stranka = fetch(o["url"], cache_key=f"organ-{o['id']}", max_age=3600)
        except ZdrojSelhal as e:
            log.chyba(f"{o['nazev']}: {e}")
            # Orgán zůstane v seznamu s prázdnem a poznámkou — vynechat ho
            # by vypadalo, jako by neexistoval.
            ven.append({**o, "cinnost": None, "osoby": [], "stav": "nedostupne"})
            continue
        assert isinstance(stranka, str)
        telo = _telo(stranka)
        osoby = _osoby_z_stranky(telo)
        ven.append({
            **o,
            "cinnost": _cinnost(telo),
            "osoby": osoby,
            "stav": "ok" if osoby else "bez-osob",
        })
        log.info(o["nazev"], pocet=len(osoby))
    return ven


# ═══════════════════════════  2. Rejstřík zápisů  ═════════════════════════

# Rejstřík je členěný na sekce podle komise:
#   <h2 class="gcm-category-name-anchor"><a id="category-100098">Komise kultury</a></h2>
#   <div class="file-row ..."><h3><a class="link-small" href="...">Zápis 18.05.2026 - jednání č. 30</a></h3>
#     <div class="not_readable file-name">Zapis_30_KK_18052026.pdf</div>
#     Staženo: 61×   Vloženo: 25. 5. 2026
#
# Sekce je podstatná: bez ní by 469 zápisů leželo na hromadě a nešlo by
# říct, která komise co projednávala. Zkoušel jsem to odvodit z názvu
# souboru („KK" = komise kultury), ale zkratky nejsou jednotné.
_SEKCE = re.compile(
    r'<h2[^>]*class="[^"]*gcm-category-name-anchor[^"]*"[^>]*>\s*'
    r'<a[^>]*id="category-(?P<kateg>\d+)"[^>]*>(?P<nazev>.*?)</a>',
    re.S,
)

_RADEK = re.compile(
    r'<div[^>]*class="[^"]*file-row[^"]*"[^>]*>(?P<blok>.*?)(?=<div[^>]*class="[^"]*file-row|'
    r'<h2[^>]*class="[^"]*gcm-category-name-anchor|</div>\s*</div>\s*</div>)',
    re.S,
)

_ODKAZ = re.compile(
    r'<a[^>]*class="[^"]*link-small[^"]*"[^>]*href="(?P<odkaz>[^"]+)"[^>]*>(?P<nadpis>.*?)</a>',
    re.S,
)
_NAZEV_SOUBORU = re.compile(r'class="[^"]*file-name[^"]*"[^>]*>\s*([^<]+)', re.I)
_STAZENO = re.compile(r'Staženo:\s*(\d+)')
_VLOZENO = re.compile(r'Vloženo:\s*(?:<[^>]+>\s*)*([\d.\s]+\d{4})')

_DATUM_V_NAZVU = re.compile(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})")
_CISLO_JEDNANI = re.compile(r"jednán[íi]\s*č\.?\s*(\d+)", re.IGNORECASE)


def _polozky_stranky(telo: str) -> list[dict]:
    """Rozebere jednu stránku rejstříku na jednotlivé zápisy.

    Jede se podle skutečných tříd v HTML (`gcm-category-name-anchor`,
    `file-row`, `link-small`, `file-name`), ne podle textu okolo odkazu.
    První pokus bral text před odkazem a vytáhl z něj `class="link-small"` —
    všech 469 zápisů pak mělo tentýž „nadpis“ a slouply se do jednoho
    souboru. Křehké to zůstává, proto sběrač hlásí prázdnou stránku.
    """
    # Hranice sekcí: od které pozice platí která komise.
    sekce: list[tuple[int, str, str]] = [
        (m.start(), m.group("kateg"), _text(m.group("nazev")))
        for m in _SEKCE.finditer(telo)
    ]

    def komise_pro(pozice: int) -> tuple[str | None, str | None]:
        posledni: tuple[str | None, str | None] = (None, None)
        for zacatek, kateg, nazev in sekce:
            if zacatek <= pozice:
                posledni = (kateg, nazev)
            else:
                break
        return posledni

    polozky: list[dict] = []
    for r in _RADEK.finditer(telo):
        blok = r.group("blok")
        a = _ODKAZ.search(blok)
        if not a:
            continue
        nadpis = _text(a.group("nadpis"))
        odkaz = html.unescape(a.group("odkaz"))
        kateg, komise = komise_pro(r.start())

        soubor_m = _NAZEV_SOUBORU.search(blok)
        stazeno_m = _STAZENO.search(blok)
        vlozeno_m = _VLOZENO.search(blok)

        d = _DATUM_V_NAZVU.search(nadpis)
        datum = f"{d.group(3)}-{int(d.group(2)):02d}-{int(d.group(1)):02d}" if d else None
        cj = _CISLO_JEDNANI.search(nadpis)

        polozky.append({
            "nadpis": nadpis,
            "komise": komise,
            "kategorie": kateg,
            "datum": datum,
            "cislo_jednani": int(cj.group(1)) if cj else None,
            "soubor": soubor_m.group(1).strip() if soubor_m else None,
            "url": urljoin(ZAKLAD, odkaz),
            "vlozeno": parse_datum(vlozeno_m.group(1)) if vlozeno_m else None,
            # Kolikrát si zápis někdo stáhl. Údaj o zájmu veřejnosti, který
            # jinde není k mání.
            "stazeno": int(stazeno_m.group(1)) if stazeno_m else None,
        })
    return polozky


def sklid_rejstrik(log: Log) -> list[dict]:
    vse: dict[str, dict] = {}
    stranka_c = 1
    while stranka_c <= MAX_STRANEK:
        url = REJSTRIK_ZAPISU if stranka_c == 1 else f"{REJSTRIK_ZAPISU}?page={stranka_c}"
        stranka = fetch(url, cache_key=f"zapisy-rejstrik-{stranka_c}", max_age=3600)
        assert isinstance(stranka, str)
        telo = _telo(stranka)
        polozky = _polozky_stranky(telo)

        if not polozky:
            if stranka_c == 1:
                raise ZdrojSelhal(
                    "Rejstřík zápisů z komisí nevrátil ani jednu položku. "
                    "Buď se změnila struktura stránky, nebo web neodpovídá — "
                    "prázdno se tu nesmí uložit jako „žádné zápisy nejsou“."
                )
            break

        nove = 0
        for p in polozky:
            if p["url"] not in vse:
                vse[p["url"]] = p
                nove += 1
        # Když stránka nepřinesla nic nového, stránkování se zacyklilo.
        if nove == 0:
            break
        stranka_c += 1

    log.info("zápisů v rejstříku", pocet=len(vse))
    return sorted(vse.values(), key=lambda z: (z["datum"] or "", z["nadpis"]), reverse=True)


# ═══════════════════════════  3. Texty zápisů  ════════════════════════════

def _klic(zapis: dict) -> str:
    """Jednoznačný klíč zápisu. Odvozený z URL, protože ta je unikátní."""
    return re.sub(r"[^0-9a-zA-Z]+", "-", zapis["url"].split("file=")[-1]).strip("-")[:48]


def _cesta_pdf(zapis: dict) -> Path:
    return CACHE / "komise" / f"{_klic(zapis)}.pdf"


def stahni_texty(zapisy: list[dict], log: Log, strop: int | None = None) -> int:
    """Stáhne PDF a uloží text. Vrací počet nově zpracovaných."""
    novych = 0
    for z in zapisy if strop is None else zapisy[:strop]:
        # Jméno souboru je odvozené z URL, ne z nadpisu. Nadpisy se opakují
        # („Zápis 5. 1. 2026“ má víc komisí) a při shodě by se zápisy
        # přepisovaly navzájem.
        cil = Path("komise/texty") / f"{_klic(z)}.json"
        hotovo = (Path(__file__).resolve().parent.parent / "data" / cil).exists()
        if hotovo:
            continue

        pdf = _cesta_pdf(z)
        try:
            if not pdf.exists():
                data = fetch(z["url"], cache_key=f"komise-{pdf.stem}", max_age=0, binary=True)
                assert isinstance(data, bytes)
                pdf.parent.mkdir(parents=True, exist_ok=True)
                pdf.write_bytes(data)
            text = pdf_na_text(pdf)
        except ZdrojSelhal as e:
            log.chyba(f"{z['nadpis']}: {e}")
            continue

        stran = text.count("\f") + 1
        if potrebuje_ocr(text, stran):
            # Sken bez textové vrstvy. Neukládá se prázdný text, který by
            # vypadal jako zápis bez obsahu.
            log.chyba(f"{z['nadpis']}: PDF nemá textovou vrstvu (potřeboval by OCR)")
            continue

        uloz(cil, {**z, "stran": stran, "text": text})
        novych += 1
    return novych


def main() -> None:
    log = Log("komise")

    organy = sklid_organy(log)
    uloz("komise/organy.json", {
        "zdroj": [ROZCESTNIK],
        "metodika": {
            "co_to_je": (
                "Komise rady a výbory zastupitelstva: čím se zabývají a kdo v nich sedí. "
                "Seznam orgánů se čte z rozcestníku samosprávy, ne z ručního seznamu — "
                "komise vznikají a zanikají."
            ),
            "role": (
                "Role se přebírá tak, jak ji web uvádí. Kde chybí, zůstává `null`; "
                "doplnit „člen“ by byl dohad."
            ),
            "jednani_verejna": (
                "Jednání komisí jsou podle usnesení rady č. RM/555/16 veřejná."
            ),
        },
        "celkem": len(organy),
        "organy": organy,
    })

    zapisy = sklid_rejstrik(log)
    uloz("komise/zapisy.json", {
        "zdroj": [REJSTRIK_ZAPISU],
        "metodika": {
            "co_to_je": "Rejstřík zápisů z jednání komisí, jak je zveřejňuje web města.",
            "stazeno": "Počet stažení uvádí web města. Je to údaj o zájmu, ne o obsahu.",
            "prazdno": (
                "Prázdný rejstřík se neuloží. Když stránka nevrátí ani jednu položku, "
                "sběrač spadne — „žádné zápisy nejsou“ je jiné tvrzení než „nepodařilo se “."
            ),
        },
        "celkem": len(zapisy),
        "zapisy": zapisy,
    })

    novych = stahni_texty(zapisy, log)
    log.pricti(novych)
    log.info("zápisů s novým textem", pocet=novych)
    log.uzavri()


if __name__ == "__main__":
    main()
