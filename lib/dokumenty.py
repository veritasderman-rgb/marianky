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
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urljoin

from lib.core import (  # noqa: E402
    CACHE,
    Log,
    ZdrojSelhal,
    docx_na_text,
    fetch,
    parse_datum,
    pdf_na_text,
    potrebuje_ocr,
)

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


# ── archivy ZIP ─────────────────────────────────────────────────────────
#
# Část zápisů z komisí město nezveřejňuje jako PDF, ale jako ZIP se
# zápisem a přílohami. Sběrač je stahoval a `pdftotext` na nich padal,
# takže 66 jednání z rejstříku nebylo v datech vůbec — a přitom je
# v archivech 200 souborů.

# Jména v ZIPu bez příznaku UTF-8 leží v DOS kódování. Python je dekóduje
# jako CP437 a česká písmena z toho vyjdou jako „ƒ" a „²"; skutečné
# kódování je CP852. Bez převodu by v datech stálo „Zápis z jednání
# ƒ.24_KLCR" místo „č.24".
_PRIZNAK_UTF8 = 0x800


def jmeno_v_archivu(info: zipfile.ZipInfo) -> str:
    if info.flag_bits & _PRIZNAK_UTF8:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp852")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


def je_archiv(cesta: Path) -> bool:
    """Je to ZIP? Podle obsahu, ne podle přípony.

    Sběrač ukládá všechno stažené pod jménem `.pdf`, takže přípona
    o typu souboru neříká nic.
    """
    try:
        with cesta.open("rb") as f:
            return f.read(2) == b"PK"
    except OSError:
        return False


def je_docx(cesta: Path) -> bool:
    """Je ten „archiv" ve skutečnosti dokument Wordu?

    Formáty Office jsou ZIP; rejstřík je někdy vede jako .zip. Pozná se
    to podle `word/document.xml` uvnitř.
    """
    try:
        with zipfile.ZipFile(cesta) as z:
            return "word/document.xml" in z.namelist()
    except (zipfile.BadZipFile, OSError):
        return False


def obsah_archivu(cesta: Path) -> list[dict]:
    """Soubory v archivu: jméno, velikost, přípona. Adresáře se vynechají."""
    try:
        with zipfile.ZipFile(cesta) as z:
            return [
                {
                    "jmeno": jmeno_v_archivu(i),
                    "bajtu": i.file_size,
                    "typ": (re.search(r"\.(\w{1,5})$", jmeno_v_archivu(i).lower())
                            or [None, ""])[1],
                    "_klic": i.filename,
                }
                for i in z.infolist()
                if not i.is_dir() and i.file_size > 0
            ]
    except (zipfile.BadZipFile, OSError) as e:
        raise ZdrojSelhal(f"archiv {cesta.name} nejde otevřít: {e}") from e


# Co v archivu je zápis a co příloha. Rozhoduje JMÉNO souboru, ne
# velikost: příloha bývá naskenovaná a tím pádem mnohem větší než zápis.
# První verze brala z „zápisových" souborů ten největší a vybrala tak
# „Zapis_07.KS_25.09.2019 - příloha č. 1.pdf" místo samotného zápisu.
_JE_ZAPIS = re.compile(r"(?i)z[áa]pis")
_JE_PRILOHA = re.compile(
    r"(?i)p[řr][íi]loh|prezen[čc]n[íi]\s*listin|pozv[áa]nk|prezentac|tabulk|"
    r"[žz][áa]dost|rozpo[čc]et"
)
CITELNE_TYPY = ("pdf", "docx")


def poradi_kandidatu(polozky: list[dict]) -> list[tuple[dict, str]]:
    """Čitelné dokumenty od nejpravděpodobnějšího zápisu, s důvodem výběru.

    Vrací se celé pořadí, ne jen vítěz: když je vybraný soubor sken bez
    textové vrstvy, má smysl zkusit další v řadě — ale JEN v rámci téže
    třídy. Sáhnout na přílohu a uložit ji jako zápis by znamenalo číst
    žádost o dotaci jako jednání komise.
    """
    citelne = [p for p in polozky if p["typ"] in CITELNE_TYPY]
    zapisy = [p for p in citelne if _JE_ZAPIS.search(p["jmeno"])
              and not _JE_PRILOHA.search(p["jmeno"])]
    jine = [p for p in citelne
            if p not in zapisy and not _JE_PRILOHA.search(p["jmeno"])]
    poradi: list[tuple[dict, str]] = []
    poradi += [(p, "jmeno-souboru") for p in sorted(zapisy, key=lambda p: -p["bajtu"])]
    poradi += [(p, "jediny-neprilohovy") for p in sorted(jine, key=lambda p: -p["bajtu"])]
    return poradi


def hlavni_dokument(polozky: list[dict]) -> tuple[dict | None, str]:
    """(zápis, podle čeho se vybral). `None` = v archivu není nic čitelného."""
    poradi = poradi_kandidatu(polozky)
    return poradi[0] if poradi else (None, "nic-citelneho")


def text_z_archivu(cesta: Path) -> dict:
    """Text zápisu z archivu ZIP a soupis toho, co v něm ještě je.

    Vrací `text`, vybraný `zapis`, podle čeho se vybral, a `prilohy`.
    Přílohy se NEČTOU — jsou to rozpočty, žádosti o dotace a prezentace,
    tedy podklady jednání, ne zápis. Jejich seznam ale stojí za uložení:
    co měla komise na stole, je samo o sobě údaj.
    """
    # Soubor .docx je taky ZIP. Rejstřík ho někdy vede jako .zip a bez
    # téhle výjimky by vyšel jako „archiv bez čitelného dokumentu".
    if je_docx(cesta):
        text = docx_na_text(cesta)
        return {
            "text": text, "stran": None,
            "zapis": {"jmeno": cesta.name, "bajtu": cesta.stat().st_size, "typ": "docx"},
            "vybrano_podle": "sam-je-docx", "prilohy": [],
        }

    polozky = obsah_archivu(cesta)
    poradi = poradi_kandidatu(polozky)
    if not poradi:
        raise ZdrojSelhal(
            f"archiv {cesta.name} nemá čitelný dokument "
            f"(je v něm: {', '.join(sorted({p['typ'] or 'bez přípony' for p in polozky}))})"
        )

    chyby: list[str] = []
    with zipfile.ZipFile(cesta) as z:
        for hlavni, podle in poradi:
            data = z.read(hlavni["_klic"])
            if hlavni["typ"] == "docx":
                text, stran = docx_na_text(data), None
            else:
                # pdftotext umí jen soubor na disku, ne proud.
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(data)
                    docasny = Path(tmp.name)
                try:
                    text = pdf_na_text(docasny)
                except ZdrojSelhal as e:
                    chyby.append(f"{hlavni['jmeno']}: {e}")
                    continue
                finally:
                    docasny.unlink(missing_ok=True)
                stran = text.count("\f") + 1
                # Sken. Zkusí se další kandidát — ale jen zápis, nikdy
                # příloha; ta by se uložila jako jednání komise.
                if potrebuje_ocr(text, stran):
                    chyby.append(f"{hlavni['jmeno']}: nemá textovou vrstvu")
                    continue
            return {
                "text": text,
                "stran": stran,
                "zapis": {k: v for k, v in hlavni.items() if k != "_klic"},
                "vybrano_podle": podle,
                "prilohy": [
                    {k: v for k, v in p.items() if k != "_klic"}
                    for p in polozky if p["_klic"] != hlavni["_klic"]
                ],
            }

    raise ZdrojSelhal(
        f"v archivu {cesta.name} není čitelný zápis ({'; '.join(chyby[:3])})"
    )


def cesta_ke_stazenemu(polozka: dict, podadresar: str) -> Path:
    return CACHE / podadresar / f"{klic_dokumentu(polozka)}.pdf"
