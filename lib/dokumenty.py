"""Čtení dokumentových rejstříků na webu města.

Web města má několik úložišť dokumentů se stejnou stavbou:

    /urad/dokumenty/zapisy-z-komisi/
    /urad/dokumenty/poskytnute-informace-106-1999-sb/
    /urad/dokumenty/stret-zajmu/
    /urad/dokumenty/zapisy-rady-mesta/
    …

Každé je stránkované po dvaceti položkách, volitelně členěné na sekce
(u zápisů z komisí je sekcí komise) a u každého souboru uvádí název,
velikost, počet stažení a datum vložení.

Modul se dívá na HTML strukturu, ne na text okolo odkazu. První verze
sběrače komisí brala text před odkazem a vytáhla z něj `class="link-small"`;
všech 469 zápisů pak mělo tentýž nadpis a slouply se do jednoho souboru.
Proto se tady jede podle skutečných tříd, a když stránka nevrátí ani jednu
položku, vyhodí se výjimka — prázdno se nesmí uložit jako „žádné dokumenty“.
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from urllib.parse import urljoin

from lib.core import CACHE, Log, ZdrojSelhal, fetch, parse_datum

ZAKLAD = "https://www.muml.cz"

# Strop stránkování. Nejdelší rejstřík má 24 stránek; strop je pojistka
# proti nekonečné smyčce, kdyby se odkaz „poslední stránka“ rozbil.
MAX_STRANEK = 60


def text_z_html(s: str) -> str:
    """HTML na čitelný text. Nic chytrého — jen tagy pryč a mezery srovnat."""
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</p>|</li>|</h[1-6]>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"[ \t\xa0]+", " ", html.unescape(s)).strip()


def telo_stranky(stranka: str) -> str:
    """Obsah stránky bez hlavičky a navigace.

    Web města má v každé stránce kompletní menu (asi 6 000 znaků). Bez
    odříznutí by se hledané výrazy trefovaly i v odkazech na jiné sekce.
    """
    i = stranka.lower().find("<h1")
    return stranka[i:] if i > 0 else stranka


# Sekce rejstříku:
#   <h2 class="gcm-category-name-anchor"><a id="category-100098">Komise kultury</a></h2>
_SEKCE = re.compile(
    r'<h2[^>]*class="[^"]*gcm-category-name-anchor[^"]*"[^>]*>\s*'
    r'<a[^>]*id="category-(?P<kateg>\d+)"[^>]*>(?P<nazev>.*?)</a>',
    re.S,
)

# Jedna položka:
#   <div class="file-row ..."><h3><a class="link-small" href="…">Nadpis</a></h3>
#     <div class="not_readable file-name">soubor.pdf</div>
#     Staženo: 61×   Vloženo: 25. 5. 2026
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
_STAZENO = re.compile(r"Staženo:\s*(\d+)")
_VLOZENO = re.compile(r"Vloženo:\s*(?:<[^>]+>\s*)*([\d.\s]+\d{4})")


def polozky_stranky(telo: str) -> list[dict]:
    """Rozebere jednu stránku rejstříku na jednotlivé dokumenty."""
    sekce: list[tuple[int, str, str]] = [
        (m.start(), m.group("kateg"), text_z_html(m.group("nazev")))
        for m in _SEKCE.finditer(telo)
    ]

    def sekce_pro(pozice: int) -> tuple[str | None, str | None]:
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
        kateg, nazev_sekce = sekce_pro(r.start())
        soubor_m = _NAZEV_SOUBORU.search(blok)
        stazeno_m = _STAZENO.search(blok)
        vlozeno_m = _VLOZENO.search(blok)

        polozky.append({
            "nadpis": text_z_html(a.group("nadpis")),
            "sekce": nazev_sekce,
            "kategorie": kateg,
            "soubor": soubor_m.group(1).strip() if soubor_m else None,
            "url": urljoin(ZAKLAD, html.unescape(a.group("odkaz"))),
            "vlozeno": parse_datum(vlozeno_m.group(1)) if vlozeno_m else None,
            # Kolikrát si dokument někdo stáhl. Údaj o zájmu veřejnosti,
            # který jinde není k mání.
            "stazeno": int(stazeno_m.group(1)) if stazeno_m else None,
        })
    return polozky


def sklid_rejstrik(zakladni_url: str, klic: str, log: Log, max_age: int = 3600) -> list[dict]:
    """Projde všechny stránky rejstříku a vrátí položky bez duplicit."""
    vse: dict[str, dict] = {}
    stranka_c = 1
    while stranka_c <= MAX_STRANEK:
        url = zakladni_url if stranka_c == 1 else f"{zakladni_url}?page={stranka_c}"
        stranka = fetch(url, cache_key=f"{klic}-rejstrik-{stranka_c}", max_age=max_age)
        assert isinstance(stranka, str)
        polozky = polozky_stranky(telo_stranky(stranka))

        if not polozky:
            if stranka_c == 1:
                raise ZdrojSelhal(
                    f"Rejstřík {zakladni_url} nevrátil ani jednu položku. Buď se změnila "
                    "struktura stránky, nebo web neodpovídá — prázdno se tu nesmí uložit "
                    "jako „žádné dokumenty nejsou“."
                )
            break

        nove = sum(1 for p in polozky if p["url"] not in vse)
        for p in polozky:
            vse.setdefault(p["url"], p)
        # Když stránka nepřinesla nic nového, stránkování se zacyklilo.
        if nove == 0:
            break
        stranka_c += 1

    log.info(f"{klic}: dokumentů v rejstříku", pocet=len(vse))
    return list(vse.values())


def klic_dokumentu(polozka: dict) -> str:
    """Jednoznačný klíč. Z URL, protože nadpisy se opakují.

    „Zápis 5. 1. 2026“ má víc komisí a „Žádost podle § 106“ je skoro
    v každém názvu; při shodě by se dokumenty přepisovaly navzájem.
    """
    return re.sub(r"[^0-9a-zA-Z]+", "-", polozka["url"].split("file=")[-1]).strip("-")[:48]


def cesta_ke_stazenemu(polozka: dict, podadresar: str) -> Path:
    return CACHE / podadresar / f"{klic_dokumentu(polozka)}.pdf"
