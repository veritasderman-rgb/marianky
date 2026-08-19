"""Rozbor zápisů z komisí — kdo byl u toho a co komise navrhla.

CO Z TOHO JE ZAJÍMAVÉ
--------------------
Zápis z komise má pravidelnou stavbu a nese tři věci, které jinde nejsou:

1. **Doporučení radě.** „Usnesení: Komise kultury doporučuje Radě města
   podpořit žádost o dotaci na pořízení nového projektoru pro Kino Slavia."
   Tohle je návrh PŘED tím, než o něm rada hlasuje — a rada už v projektu
   sledovaná je. Dá se tak vidět, kde se rozhodnutí vzalo.
2. **Hosté.** Zápis jmenuje, kdo na jednání přišel zvenčí, včetně firmy
   v závorce. Když se táž firma později objeví v registru smluv, je to
   stopa, kterou z usnesení vyčíst nejde.
3. **Účast členů.** Přítomen / omluven / neomluven, jednání po jednání.

CO TENHLE MODUL DĚLÁ A CO NE
----------------------------
Rozebírá pravidelný formát: hlavičku, číslované body, bloky „Usnesení"
a hlasování. To je práce pro kód — je to tvar, ne význam.

NEVYKLÁDÁ, co doporučení znamená, a NETVRDÍ, že se jím rada řídila.
Spojení doporučení s pozdějším usnesením rady je odhad a jako odhad se
i ukládá (`jistota`), stejně jako u řetězu usnesení → smlouva.

MĚŘÍ SE ÚSPĚŠNOST ROZBORU. Zápis, který se nepodařilo rozebrat, se počítá
a je vidět v datech. Bez toho by se dalo tvrdit, že komise nic nenavrhly,
ačkoliv se to jen nepovedlo přečíst.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import DATA, Log, nacti, slug, uloz  # noqa: E402

# ── hlavička ────────────────────────────────────────────────────────────
_SEKCE_HLAVICKY = [
    ("pritomni", r"P[řr][ií]tomn[ií][^:\n]*:"),
    ("omluveni", r"Omluven[ií][^:\n]*:"),
    ("neomluveni", r"Neomluven[ií][^:\n]*:"),
    ("hoste", r"Host[éeí][^:\n]*:"),
    ("zapisovatel", r"Zapisovatel[ka]*[^:\n]*:"),
]

_VSECHNY_HLAVICKY = re.compile(
    r"(?m)^\s*(" + "|".join(v for _, v in _SEKCE_HLAVICKY) + r"|\d+\.\s)",
)

# ── body a usnesení ─────────────────────────────────────────────────────
# Číslování bodů není jednotné: novější zápisy píšou „1. ", starší „1) ".
# První verze uměla jen tečku a 98 ze 278 zápisů proto vyšlo jako
# nerozebraných — vypadalo to, že v nich komise nic neprojednala.
_BOD = re.compile(r"(?m)^\s*(\d{1,2})[.)]\s+(?P<nazev>\S[^\n]{2,160})\s*$")

# „Usnesení" bývá na vlastní řádce, ale i rovnou s textem za dvojtečkou.
_USNESENI = re.compile(
    r"(?m)^[ \t]*(?:Usnesen[ií]|Doporu[čc]en[ií]|N[áa]vrh\s+usnesen[ií])\s*:?[ \t]*",
)
_HLASOVANI = re.compile(
    r"Pro\s*:?\s*(\d+)\s*(?:\n|\s)+Proti\s*:?\s*(\d+)\s*(?:\n|\s)+Zdr[žz]el[ai]?\s*se\s*:?\s*(\d+)",
    re.IGNORECASE,
)

# Jestli návrh prošel. Zápis to říká až za hlasováním („PRO: 4 PROTI: 2 …
# Navržené usnesení nebylo přijato."), takže se hledá i kus za koncem
# bloku. Bez toho by se nepřijatý návrh četl jako doporučení komise —
# tvrdil by pravý opak toho, co komise rozhodla.
#
# OKNO MUSÍ SKONČIT NA HRANICI BODU. První verze brala pevných 250 znaků
# a přetekla do dalšího bodu: u zápisu Komise sociální a zdravotní
# z 1. 11. 2023 stálo nad usnesením „K tomuto bodu bylo přijato usnesení"
# a hlasování 4–0–0, ale o dva body dál „K tomuto bodu nebylo přijato
# žádné usnesení" — a přijaté doporučení kvůli tomu vyšlo jako zamítnuté.
_NEPRIJATO = re.compile(
    r"(?i)(usnesen[ií]\s+neb\w*\s+p[řr]ijat|nebylo\s+p[řr]ijato\s+[žz][áa]dn|"
    r"n[áa]vrh\w*\s+usnesen\w*\s+neb\w*\s+p[řr]ijat|nebyl[oa]?\s+p[řr]ijat)"
)
# Opačný doklad: zápis říká, že usnesení přijato BYLO. Zápor je vyloučený
# pohledem zpět — „nebylo přijato" obsahuje „bylo přijato".
_PRIJATO = re.compile(r"(?i)(?<!ne)\bbyl[oa]?\s+p[řr]ijat|p[řr]ijat[oa]?\s+usnesen")

# Začátek dalšího bodu. Okno pro hledání výsledku hlasování končí tady,
# ať se stav jednoho bodu nepřilepí k usnesení bodu předchozího.
_DALSI_BOD = re.compile(
    r"(?im)^[ \t]*(?:K\s+tomuto\s+bodu\b|Usnesen[ií]\s*:|Ad\s*\d|\d{1,2}[.)]\s+\S)|\*{5,}"
)

# Zbytek sloupce s hlasováním, který zůstal viset na konci textu.
# pdftotext bez -layout míchá sloupce a věta pak končí „…pro použití. Pro:".
_ZBYTEK_HLASOVANI = re.compile(r"(?i)\s*(pro|proti|zdr[žz]el(\s+se)?)\s*:?\s*\d*\s*$")


# Komise doporučuje / nedoporučuje / žádá / ukládá — sloveso nese směr.
#
# POŘADÍ JE SOUČÁST VÝZNAMU. Záporný tvar musí stát PŘED kladným, jinak ho
# kladný vzor spolkne: „nesouhlasí" obsahuje „souhlasí" a vyšlo by z toho
# opačné tvrzení, než co komise řekla.
#
# HRANICE SLOVA TAKY. První verze hledala „zad[áa]" bez hranic a trefila se
# do slova „Zadávací" — třináct usnesení tak vyšlo jako „komise žádá",
# přestože komise souhlasila se zadávací dokumentací.
_SMER = [
    ("nedoporucuje", r"nedoporu[čc]uj"),
    ("doporucuje", r"doporu[čc]uj"),
    ("zada", r"\b[žz][áa]d[áa](?:j[íi]|me|te)?\b"),
    ("uklada", r"\bukl[áa]d[áa](?:j[íi]|me)?\b"),
    # „Navrhuje" je návrh jako každý jiný — „KK navrhuje RM zabývat se
    # vytvořením koncepce kultury". Vzor pro věty ho hledal odjakživa,
    # ale směr mu nikdo nepřiřadil, takže takové návrhy vypadly z řetězu
    # na radu i ze seznamu těch, ke kterým se nic nenašlo.
    ("navrhuje", r"navrhuj"),
    ("bere_na_vedomi", r"bere\s+na\s+v[ěe]dom[ií]"),
    ("nesouhlasi", r"nesouhlas[ií]"),
    ("souhlasi", r"souhlas[ií]"),
]

# Nejdelší text usnesení, který se ještě bere celý. Delší bývá slepenec
# usnesení a následující diskuze — vypíše se zkrácený a je to poznat.
PSANY_STROP = 700

# Firma v závorce za jménem hosta: „Petra Němcová (AV-ELZO s.r.o.)".
_HOST_S_FIRMOU = re.compile(r"([^,()]{3,60}?)\s*\(([^)]{2,80})\)")

_PRAVNI_FORMA = re.compile(
    r"\b(s\.?\s?r\.?\s?o\.?|a\.?\s?s\.?|z\.?\s?s\.?|o\.?p\.?s\.?|s\.?p\.?|"
    r"p\.?\s?o\.?|spol\.?\s+s\s+r\.?\s?o\.?)\s*$",
    re.IGNORECASE,
)


def _bez_diakritiky(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn"
    ).lower()


def _jmena(blok: str) -> list[str]:
    """Rozseká seznam jmen oddělený čárkami na jednotlivá jména.

    Závorky se nechávají u jména — „(odešla v 15:30)" i „(AV-ELZO s.r.o.)"
    jsou údaj ze zdroje a zahodit je by znamenalo ztratit informaci.
    """
    text = re.sub(r"\s+", " ", blok).strip(" ,;")
    if not text:
        return []
    # Čárka uvnitř závorky neodděluje jméno.
    kusy, hloubka, akt = [], 0, ""
    for ch in text:
        if ch == "(":
            hloubka += 1
        elif ch == ")":
            hloubka = max(0, hloubka - 1)
        if ch == "," and hloubka == 0:
            kusy.append(akt)
            akt = ""
        else:
            akt += ch
    kusy.append(akt)
    return [k.strip() for k in kusy if k.strip() and len(k.strip()) > 2]


def _hlavicka(text: str) -> dict:
    """Přítomní, omluvení, neomluvení, hosté a zapisovatel."""
    ven: dict[str, list[str] | str | None] = {k: [] for k, _ in _SEKCE_HLAVICKY}
    for klic, vzor in _SEKCE_HLAVICKY:
        m = re.search(r"(?m)^\s*" + vzor, text)
        if not m:
            # Chybějící sekce zůstává prázdná se stavem `null` níže —
            # „nikdo nebyl omluven" a „zápis to neuvádí" nejsou totéž.
            ven[klic] = None
            continue
        zbytek = text[m.end():]
        dalsi = _VSECHNY_HLAVICKY.search(zbytek)
        blok = zbytek[: dalsi.start()] if dalsi else zbytek[:600]
        ven[klic] = _jmena(blok)
    zap = ven.get("zapisovatel")
    ven["zapisovatel"] = (zap[0] if isinstance(zap, list) and zap else None)
    return ven


def _organizace_hosta(host: str, rejstrik: dict[str, dict]) -> str | None:
    """Firma uvedená u hosta v závorce.

    Do závorky si zápisy dávají leccos — „(dále jen „Pravidla“)“,
    „(přítomno 6, omluveni 2)“, poznámky o odchodu. První verze brala
    všechno a mezi „hosty z firem“ se dostalo osm výskytů slova
    „Pravidla“. Bereme proto jen to, co vypadá jako firma: buď má právní
    formu v názvu, nebo se přesně shoduje s rejstříkem firem ve městě.

    Zkratky útvarů úřadu (OKLCRU, MÚML, OÚP) firmy nejsou a vypadnou taky.
    """
    m = _HOST_S_FIRMOU.search(host)
    if not m:
        return None
    org = re.sub(r"\s+", " ", m.group(2)).strip(" .,;")
    if not org or len(org) > 70:
        return None
    if _PRAVNI_FORMA.search(org):
        return org
    if _bez_diakritiky(org) in rejstrik:
        return org
    return None


# Jak daleko za koncem bloku se ještě smí hledat výsledek hlasování.
OKNO_VYSLEDKU = 250


def _konec_okoli(zbytek: str, od: int) -> int:
    """Konec okna, ve kterém se hledá hlasování a výsledek.

    Okno začíná na konci bloku usnesení a končí na nejbližší hranici
    dalšího bodu, nejdál po `OKNO_VYSLEDKU` znacích. Pevné okno bez téhle
    hranice přetéká do dalšího bodu a přenáší na usnesení cizí výsledek.
    """
    strop = od + OKNO_VYSLEDKU
    dalsi = _DALSI_BOD.search(zbytek, od)
    return min(strop, dalsi.start()) if dalsi else strop


# Stavová věta nad usnesením: „K tomuto bodu bylo přijato usnesení."
# Není to návrh, je to hlavička bodu — a zápisy Komise sociální a zdravotní
# ji mají nad každým usnesením, takže tentýž návrh vyjde jednou s ní
# a jednou bez ní.
_STAVOVA_VETA = re.compile(
    r"(?i)^\s*K\s+tomuto\s+bodu\b[^.]{0,90}\.?\s*(?:Usnesen[ií]\s*:)?[\s•·*–—-]*$"
)


# Blok, který začíná stavem bodu — ať už celou větou („K tomuto bodu…"),
# nebo holým výsledkem hlasování („bylo přijato"). Za ním už neběží
# usnesení, ale vyprávění o dalším bodu.
_ZACATEK_STAVU = re.compile(r"(?i)^\s*(?:K\s+tomuto\s+bodu\b|(?:ne)?byl[oa]?\s+p[řr]ijat)")

# Stav bodu napsaný NAD usnesením („K tomuto bodu bylo přijato usnesení.
# Usnesení: Komise doporučuje…"). Zápisy Komise sociální a zdravotní to
# tak píšou vždycky. Hledá se jen těsně před značkou usnesení a jen jako
# celá stavová věta na konci — dál zpátky už by to byl stav bodu jiného.
_STAV_PRED = re.compile(r"(?i)K\s+tomuto\s+bodu\b[^.]{0,90}\.\s*$")
DOSAH_STAVU_PRED = 160


def _slouc_duplicity(usneseni: list[dict]) -> list[dict]:
    """Sloučí usnesení zachycené v zápisu dvakrát — se stavovou větou a bez ní.

    Slučuje se jen tehdy, když je delší text přesně stavová věta + kratší
    text. Kdyby stačilo prosté „jeden je koncem druhého", zahodily by se
    i případy, kdy blok spolkl dvě RŮZNÁ usnesení a to druhé žije jen
    uvnitř toho delšího.

    Zůstává kratší, čistý text; příznaky (přijetí, hlasování) se z delšího
    přenesou, protože tam je stavová věta a s ní i doklad o výsledku.
    """
    dle_textu = {u["text"]: u for u in usneseni}
    zahodit: set[str] = set()
    for u in usneseni:
        for v in usneseni:
            if u is v or len(v["text"]) >= len(u["text"]):
                continue
            if not u["text"].endswith(v["text"]):
                continue
            if not _STAVOVA_VETA.match(u["text"][: len(u["text"]) - len(v["text"])]):
                continue
            cil = dle_textu[v["text"]]
            if cil.get("prijato") is None:
                cil["prijato"] = u.get("prijato")
            if cil.get("hlasovani") is None:
                cil["hlasovani"] = u.get("hlasovani")
            zahodit.add(u["text"])
            break
    return [u for u in usneseni if u["text"] not in zahodit]


def _prijato(okoli: str) -> bool | None:
    """Prošel návrh? `None` = zápis o tom mlčí.

    Zápor má přednost: „nebylo přijato žádné usnesení" je jednoznačné
    tvrzení, kdežto slovo „přijato" se v okolí najde i v jiných větách.
    Z počtu hlasů se přijetí NEDOPOČÍTÁVÁ — kvórum komisí odsud vidět
    není a dohad by tu vypadal jako údaj ze zápisu.
    """
    if _NEPRIJATO.search(okoli):
        return False
    if _PRIJATO.search(okoli):
        return True
    return None


def _usneseni_z_textu(text: str) -> list[dict]:
    """Bloky „Usnesení" s doporučením a hlasováním.

    Blok začíná nadpisem a končí hlasováním nebo dalším bodem. Když
    hlasování chybí, doporučení se uloží bez něj — mnoho komisí hlasuje
    jen o části bodů a dopisovat nulu by lhalo.
    """
    ven: list[dict] = []
    for m in _USNESENI.finditer(text):
        zbytek = text[m.end():]
        # Konec bloku je NEJBLIŽŠÍ z: prázdný řádek, další číslovaný bod,
        # nadpis hlasování. Původně se bralo až po další bod, a když bod
        # nenásledoval, spolklo usnesení půl stránky textu — jedno mělo
        # 1 200 znaků a končilo uprostřed slova.
        # Řádek hvězdiček je v zápisech Komise školství oddělovač bodů. Bez
        # něj usnesení pokračovalo přes hvězdičky do dalšího bodu a vznikaly
        # slepence typu „trvá. - vyjádření RM - NE ***** Komise školství…".
        hranice = [len(zbytek[:PSANY_STROP])]
        # „PRO:" je začátek hlasování i tam, kde nadpis „Hlasování" chybí.
        # KLCR za ním jmenuje, kdo jak hlasoval; bez téhle hranice se roll
        # call slepil s usnesením a jména členů pak vypadala jako jeho téma.
        for vzor in (r"\n[ \t]*\n", r"(?m)^\s*\d{1,2}[.)]\s+\S", r"Hlasov[áa]n[ií]",
                     r"\*{5,}", r"(?i)\bPRO\s*:"):
            k = re.search(vzor, zbytek)
            if k:
                hranice.append(k.start())
        blok = zbytek[: min(hranice)]

        okoli = zbytek[: _konec_okoli(zbytek, min(hranice))]
        pred = _STAV_PRED.search(text[max(0, m.start() - DOSAH_STAVU_PRED): m.start()])
        h = _HLASOVANI.search(okoli)
        veta = re.sub(r"\s+", " ", blok).strip(" *–—-\t")
        # Nadpis hlasování patří k hlasování, ne k usnesení.
        veta = re.sub(r"\s*Hlasov[áa]n[ií]\s*:?\s*$", "", veta).strip()
        while True:
            oriznute = _ZBYTEK_HLASOVANI.sub("", veta).strip(" .,;")
            if oriznute == veta:
                break
            veta = oriznute
        # Blok začínající stavem bodu končí tím stavem. Za ním už běží
        # vyprávění o dalším bodu — a když v něm padne slovo „doporučuje",
        # vydával se cizí odstavec za usnesení, o kterém zápis přitom říká,
        # že přijato nebylo. Ořez musí přijít PŘED kontrolou délky, jinak
        # se do dat dostane usnesení s prázdným textem.
        if _ZACATEK_STAVU.match(veta):
            # Bez tečky za stavem není co zachránit — zbytek je text
            # dalšího bodu, který se sem přilepil.
            tecka = veta.find(".")
            veta = veta[: tecka + 1] if tecka > 0 else ""
        # Blok, ve kterém zbyla jen hlavička bodu, žádný návrh nenese.
        # Ukládat ho jako „usnesení komise" by nafouklo počty o body,
        # na kterých se komise právě že neusnesla.
        if len(veta) < 12 or _STAVOVA_VETA.match(veta):
            continue

        smer = None
        for klic, vzor in _SMER:
            if re.search(vzor, _bez_diakritiky(veta) if klic != "bere_na_vedomi" else veta, re.I):
                smer = klic
                break

        zkraceno = len(veta) >= PSANY_STROP
        ven.append({
            "text": (veta[:PSANY_STROP].rstrip() + "…") if zkraceno else veta,
            # Zkrácený text se musí poznat, aby se necitoval jako celý.
            "zkraceno": zkraceno,
            # Sloveso určuje, co komise chce. „nedoporučuje" se musí poznat
            # od „doporučuje" — je to opačné tvrzení.
            "smer": smer,
            # Formální usnesení, ne věta z textu. Rozdíl je podstatný:
            # o usnesení se hlasovalo, věta může být převyprávění.
            "zdroj": "usneseni",
            # Zdroj říká, že návrh neprošel. `None` = zdroj mlčí; „přijato"
            # se nedopočítává z hlasování, kvórum komisí odsud nevidíme.
            # Stav bodu bývá pod usnesením i nad ním; bere se ten, který
            # se najde, a zápor má přednost.
            "prijato": _prijato(okoli + " " + (pred.group(0) if pred else "")),
            "hlasovani": (
                {"pro": int(h.group(1)), "proti": int(h.group(2)), "zdrzel": int(h.group(3))}
                if h else None
            ),
        })
    return ven


# Starší zápisy (a Komise sportu vůbec) žádné bloky „Usnesení" nemají —
# návrh je normální věta v textu: „Komise sportu jednohlasně odsouhlasila
# Systémovou podporu ve výši 350.000,-- Kč." Takové věty se hledají zvlášť
# a NESLÉVAJÍ se s formálními usneseními: `zdroj` u každého říká, odkud je.
_VETA_KOMISE = re.compile(
    r"(?:^|[.\n])\s*((?:Komise|V[ýy]bor)\b[^.\n]{0,200}?\b"
    r"(?:doporu[čc]uje|nedoporu[čc]uje|navrhuje|nesouhlas[ií]|souhlas[ií]|"
    r"[žz][áa]d[áa]|ukl[áa]d[áa]|odsouhlasil[aoy]?|schv[áa]lil[aoy]?)"
    r"[^.\n]{0,300}\.)",
    re.IGNORECASE,
)


def _vety_komise(text: str, uz_mame: list[dict]) -> list[dict]:
    """Návrhy zapsané jako běžná věta, ne jako blok „Usnesení".

    Bere jen věty, které začínají orgánem („Komise…", „Výbor…") a nesou
    sloveso vůle. Nechytá tím převyprávění diskuze — to je záměr: raději
    nenajít návrh, než vydávat za návrh cizí názor.
    """
    videne = {re.sub(r"\s+", " ", u["text"])[:80] for u in uz_mame}
    ven: list[dict] = []
    for m in _VETA_KOMISE.finditer(text):
        veta = re.sub(r"\s+", " ", m.group(1)).strip()
        okoli = text[m.start(): m.end() + _konec_okoli(text[m.end():], 0)]
        if len(veta) < 25:
            continue
        klic = veta[:80]
        if klic in videne:
            continue
        videne.add(klic)

        smer = None
        for k, vzor in _SMER:
            if re.search(vzor, _bez_diakritiky(veta) if k != "bere_na_vedomi" else veta, re.I):
                smer = k
                break
        zkraceno = len(veta) >= PSANY_STROP
        ven.append({
            "text": (veta[:PSANY_STROP].rstrip() + "…") if zkraceno else veta,
            "zkraceno": zkraceno,
            "smer": smer,
            "hlasovani": None,
            "zdroj": "veta",
            "prijato": _prijato(okoli),
        })
    return ven


def _body(text: str) -> list[str]:
    """Názvy číslovaných bodů programu."""
    videne: list[str] = []
    for m in _BOD.finditer(text):
        nazev = re.sub(r"\s+", " ", m.group("nazev")).strip(" –-—")
        # Řádky typu „5. 1. 2026" jsou datum, ne bod programu.
        if re.fullmatch(r"[\d.\s]+", nazev):
            continue
        if nazev and nazev not in videne:
            videne.append(nazev)
    return videne


def _komise_a_archiv(nazev: str | None) -> tuple[str | None, bool]:
    """Rozdělí „Komise sportu > Archiv" na komisi a příznak archivu.

    Rejstřík na webu má archivy jako podsekce. Kdyby se braly jako
    samostatné komise, vyšlo by jich patnáct místo osmi a počty by se
    rozpadly na dvě hromádky.
    """
    if not nazev:
        return None, False
    kusy = [k.strip() for k in nazev.split(">")]
    return kusy[0] or None, len(kusy) > 1


def rozeber(zapis: dict, rejstrik_firem: dict[str, dict] | None = None) -> dict:
    rejstrik_firem = rejstrik_firem or {}
    text = zapis.get("text") or ""
    hlavicka = _hlavicka(text)
    usneseni = _usneseni_z_textu(text)
    usneseni += _vety_komise(text, usneseni)
    usneseni = _slouc_duplicity(usneseni)
    body = _body(text)

    hoste = hlavicka.get("hoste") or []
    organizace = []
    for h in hoste if isinstance(hoste, list) else []:
        org = _organizace_hosta(h, rejstrik_firem)
        if org:
            organizace.append({"host": h, "organizace": org})

    komise, z_archivu = _komise_a_archiv(zapis.get("komise"))
    return {
        "id": slug(f"{komise or 'komise'}-{zapis.get('datum') or ''}-{zapis.get('cislo_jednani') or ''}"),
        "komise": komise,
        "z_archivu": z_archivu,
        "datum": zapis.get("datum"),
        "cislo_jednani": zapis.get("cislo_jednani"),
        "url": zapis.get("url"),
        "soubor": zapis.get("soubor"),
        "stazeno": zapis.get("stazeno"),
        "stran": zapis.get("stran"),
        **hlavicka,
        "hoste_s_organizaci": organizace,
        "body": body,
        "usneseni": usneseni,
        # Zápis, ze kterého se nepodařilo vytáhnout ani body, ani usnesení,
        # je podezřelý — buď má jiný formát, nebo je to sken.
        "rozebrano": bool(body or usneseni),
    }


def _firmy_podle_nazvu() -> dict[str, dict]:
    """Rejstřík firem ve městě podle normalizovaného názvu."""
    s = nacti("firmy/subjekty.json") or {}
    rejstrik: dict[str, dict] = {}
    for f in s.get("subjekty") or []:
        nazev = (f.get("nazev") or "").strip()
        if not nazev:
            continue
        rejstrik.setdefault(_bez_diakritiky(re.sub(r"\s+", " ", nazev)), f)
    return rejstrik


def main() -> None:
    log = Log("komise_prehled")

    koren = DATA / "komise" / "texty"
    if not koren.exists():
        log.chyba("data/komise/texty neexistuje — nejdřív musí proběhnout scrapers/komise.py")
        log.uzavri()
        return

    zapisy = []
    for soubor in sorted(koren.glob("*.json")):
        try:
            zapisy.append(json.loads(soubor.read_text(encoding="utf-8")))
        except Exception as e:  # noqa: BLE001
            log.chyba(f"{soubor.name}: {e}")

    firmy = _firmy_podle_nazvu()
    rozebrane = [rozeber(z, firmy) for z in zapisy]
    rozebrane.sort(key=lambda r: (r["datum"] or "", r["komise"] or ""), reverse=True)

    # ── Hosté z firem ────────────────────────────────────────────────────
    # Shoda názvu s rejstříkem firem je ODHAD. Firma se stejným názvem může
    # sídlit jinde a zkratka v závorce nemusí být firma vůbec.
    stopy: list[dict] = []
    for r in rozebrane:
        for h in r["hoste_s_organizaci"]:
            klic = _bez_diakritiky(re.sub(r"\s+", " ", h["organizace"]))
            nalez = firmy.get(klic)
            stopy.append({
                "datum": r["datum"],
                "komise": r["komise"],
                "host": h["host"],
                "organizace": h["organizace"],
                "ico": (nalez or {}).get("ico"),
                "jistota": "nazev-sedi" if nalez else "nedohledano",
                "url": r["url"],
            })

    # ── Souhrn ───────────────────────────────────────────────────────────
    po_komisich: Counter[str] = Counter()
    usneseni_celkem = 0
    doporuceni = 0
    neprijato = 0
    z_bloku = 0
    for r in rozebrane:
        po_komisich[r["komise"] or "neurčeno"] += 1
        usneseni_celkem += len(r["usneseni"])
        z_bloku += sum(1 for u in r["usneseni"] if u.get("zdroj") == "usneseni")
        # Nepřijatý návrh se do doporučení NEPOČÍTÁ. „Komise doporučuje…
        # PRO: 4 PROTI: 2 … Navržené usnesení nebylo přijato" je zápis
        # o tom, že komise návrh zamítla, ne o tom, že ho doporučila.
        doporuceni += sum(1 for u in r["usneseni"]
                          if u["smer"] in {"doporucuje", "nedoporucuje"}
                          and u.get("prijato") is not False)
        neprijato += sum(1 for u in r["usneseni"] if u.get("prijato") is False)

    nerozebrano = [r for r in rozebrane if not r["rozebrano"]]

    uloz("komise/prehled.json", {
        "metodika": {
            "co_to_je": (
                "Rozbor zápisů z jednání komisí rady a výborů zastupitelstva. "
                "Vytahuje účast, body programu a bloky „Usnesení“ s hlasováním."
            ),
            "zdroj_navrhu": (
                "`usneseni` = formální blok „Usnesení“, o kterém se hlasovalo. "
                "`veta` = běžná věta v textu („Komise sportu odsouhlasila…“). "
                "Starší zápisy bloky nemají a bez tohohle rozlišení by vypadaly "
                "jako jednání, na kterých komise nic nenavrhla."
            ),
            "co_to_neni": (
                "Nevykládá, co doporučení znamená, a netvrdí, že se jím rada řídila. "
                "Spojení s pozdějším usnesením rady dělá až pipeline/retez_komise.py "
                "a ukládá ho jako odhad."
            ),
            "prijato": (
                "Co o osudu návrhu říká zápis. `false` = „Navržené usnesení nebylo "
                "přijato“, `true` = „K tomuto bodu bylo přijato usnesení“, `null` = "
                "zápis o přijetí mlčí. Z počtu hlasů se to NEDOPOČÍTÁVÁ — kvórum "
                "komisí odsud vidět není. Výsledek se hledá jen v okolí téhož bodu; "
                "pevné okno přetékalo do dalšího bodu a přijaté doporučení kvůli "
                "tomu vycházelo jako zamítnuté. Nepřijatý návrh se nepočítá mezi "
                "doporučení."
            ),
            "duplicity": (
                "Zápis, který nad usnesením uvádí stavovou větu, zachytí tentýž "
                "návrh dvakrát — s ní a bez ní. Slučuje se jen tehdy, když je delší "
                "text přesně stavová věta plus ten kratší; jinak by se zahodil "
                "případ, kdy blok spolkl dvě různá usnesení."
            ),
            "prazdno": (
                "Chybějící sekce hlavičky je `null`, ne prázdný seznam: „nikdo nebyl "
                "omluven“ a „zápis to neuvádí“ jsou dvě různá tvrzení."
            ),
            "hoste": (
                "Organizace hosta se bere jen ze závorky v zápisu. Shoda s rejstříkem "
                "firem je odhad — stejný název může mít firma jinde."
            ),
            "uspesnost": (
                "Zápis, ze kterého nešlo vytáhnout ani bod, ani usnesení, je v `nerozebrane`. "
                "Bez toho by se dalo číst, že komise nic nenavrhly."
            ),
        },
        "souhrn": {
            "zapisu": len(rozebrane),
            "rozebranych": len(rozebrane) - len(nerozebrano),
            "nerozebranych": len(nerozebrano),
            "usneseni": usneseni_celkem,
            "z_formalnich_usneseni": z_bloku,
            "z_vet_v_textu": usneseni_celkem - z_bloku,
            "doporuceni_rade": doporuceni,
            "neprijatych_navrhu": neprijato,
            "hostu_s_organizaci": len(stopy),
            "po_komisich": dict(po_komisich.most_common()),
        },
        "nerozebrane": [
            {"komise": r["komise"], "datum": r["datum"], "url": r["url"]} for r in nerozebrano
        ],
        "zapisy": rozebrane,
    })

    uloz("komise/hoste.json", {
        "metodika": {
            "co_to_je": (
                "Hosté jednání komisí, u kterých zápis uvádí organizaci. Slouží jako "
                "stopa: firma, která přijde na komisi a později uzavře smlouvu s městem, "
                "je vidět na obou místech."
            ),
            "jistota": (
                "`nazev-sedi` znamená jen shodu názvu s rejstříkem firem ve městě, "
                "ne ověřenou totožnost. `nedohledano` znamená, že se název nenašel — "
                "často jde o útvar úřadu nebo firmu odjinud."
            ),
            "co_z_toho_neplyne": (
                "Účast na komisi není nic nepatřičného; jednání jsou veřejná a hosté "
                "bývají zváni. Přehled z toho nevyvozuje žádný závěr."
            ),
        },
        "celkem": len(stopy),
        "stopy": sorted(stopy, key=lambda s: (s["datum"] or ""), reverse=True),
    })

    log.pricti(len(rozebrane))
    log.info("zápisů rozebráno", pocet=len(rozebrane) - len(nerozebrano))
    log.info("usnesení komisí", pocet=usneseni_celkem)
    log.info("z toho doporučení radě", pocet=doporuceni)
    if nerozebrano:
        log.info("zápisů se nepodařilo rozebrat", pocet=len(nerozebrano))
    log.uzavri()


if __name__ == "__main__":
    main()
