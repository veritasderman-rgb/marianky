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
    # „Nepřítomni" MUSÍ být zvlášť. Bez toho seznam přítomných pokračoval
    # přes nadpis dál a z „Vladimír Kafka Nepřítomni: Patricie Irlveková"
    # vzniklo jedno jméno — přítomný člen slepený s nepřítomným. Přisoudit
    # někomu cizí absenci je horší než účast neuvádět vůbec.
    ("nepritomni", r"Nep[řr][ií]tomn[ií][^:\n]*:"),
    ("omluveni", r"Omluven[ií][^:\n]*:"),
    ("neomluveni", r"Neomluven[ií][^:\n]*:"),
    ("hoste", r"Host[éeí][^:\n]*:"),
    ("zapisovatel", r"Zapisovatel[ka]*[^:\n]*:"),
]

# Kde seznam jmen končí. Kromě dalších hlaviček i řádky, kterými začíná
# vlastní jednání — jinak se do „přítomných" dostal celý program.
_KONEC_SEZNAMU = [
    r"Po[čc]et\s+p[řr][ií]tomn",
    r"Program\s*(?:jedn[áa]n[íi])?\s*:",
    r"Ad\s*\d",
    r"Komise\s+je\s+usn[áa][šs]en",
    r"\d{1,2}[.)]\s",
    r"\*{5,}",
]

# Case-insensitive schválně: Komise lázeňství píše hlavičky verzálkami
# („PŘÍTOMNI:", „NEPŘÍTOMNI:"). Bez toho vypadlo z docházky 83 z jejích
# 87 zápisů — a přitom je to nejaktivnější komise ve městě.
_VSECHNY_HLAVICKY = re.compile(
    r"(?im)^\s*(?:"
    + "|".join(v for _, v in _SEKCE_HLAVICKY)
    + "|" + "|".join(_KONEC_SEZNAMU)
    + r")",
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


# Jak vypadá jméno. Používá se jen k tomu, aby se do účasti nedostal
# slepenec typu „Mgr. Vladimír Kafka Mgr. Miloslav Pelc – 2.mst" nebo
# kus programu jednání. Co neprojde, se zahodí a zápis se označí jako
# nespolehlivý — počítat docházku z rozsypaného seznamu nemá cenu.
# Titul musí být SAMOSTATNÉ slovo — proto hranice na obou stranách. Bez
# té druhé sežral vzor „p" první písmeno z „Petr" a „Dr" z „Drexler",
# takže se z členů komise stali „etr" a „exler" a docházka jim nesedla.
_TITUL = re.compile(
    r"(?i)\b(?:Mgr|Bc|Ing|MUDr|MVDr|JUDr|PhDr|PaedDr|RNDr|MDDr|Dr|prof|doc|arch|"
    r"Ph\.?D|MBA|LL\.?M|DiS|pí|pan|paní|p)\b\.?\s*"
)
_ZAVORKA = re.compile(r"\([^)]*\)")


# Zbytek nadpisu, který zůstal viset na prvním jméně: „KŠ: hosté: Alena
# Hálová". Zkratka orgánu s dvojtečkou není součást jména.
_ZBYTEK_NADPISU = re.compile(r"(?i)^\s*[A-ZŠČŘŽÁÉÍÓÚŮĎŤŇ]{1,6}\s*:\s*(?:host[éeí]\s*:\s*)?")


def _ocisti_jmeno(jmeno: str) -> str:
    """Jméno bez titulů a poznámek v závorce, na porovnávání i do součtů."""
    bez_zavorky = _ZAVORKA.sub(" ", jmeno or "")
    bez_nadpisu = _ZBYTEK_NADPISU.sub("", bez_zavorky)
    return re.sub(r"\s+", " ", _TITUL.sub("", bez_nadpisu)).strip(" ,;–—-[]()")


def _je_jmeno(jmeno: str) -> bool:
    ocistene = _ocisti_jmeno(jmeno)
    if not 3 <= len(ocistene) <= 45 or any(c.isdigit() for c in ocistene):
        return False
    slova = ocistene.split()
    if not 1 <= len(slova) <= 4:
        return False
    # Každé slovo jména začíná velkým písmenem. „hosté", „viz prezenční
    # listina" ani „člen RM" tím neprojdou.
    return all(w[:1].isupper() for w in slova)


def _je_slepecky_tvar(jmeno: str) -> bool:
    """Slepenec dvou jmen, ne prostě neuvedený údaj.

    Pozná se podle toho, že v něm stojí víc velkými písmeny začínajících
    slov, než se do jednoho jména vejde. „viz prezenční listina" tím
    neprojde — to je chybějící údaj, ne poškozený.
    """
    ocistene = _ocisti_jmeno(jmeno)
    velka = sum(1 for w in ocistene.split() if w[:1].isupper())
    return velka >= 4 or len(ocistene) > 45


_je_slepenec = _je_slepecky_tvar


def _hlavicka(text: str) -> dict:
    """Přítomní, omluvení, neomluvení, hosté a zapisovatel."""
    ven: dict[str, list[str] | str | None] = {k: [] for k, _ in _SEKCE_HLAVICKY}
    for klic, vzor in _SEKCE_HLAVICKY:
        m = re.search(r"(?im)^\s*" + vzor, text)
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

    # Co neprojde kontrolou jména, se zahodí. Rozlišují se přitom dvě věci:
    #
    #   „viz prezenční listina", „člen RM"  — zdroj jména neuvádí. Seznam
    #       se pak nesmí uložit jako prázdný: „nikdo nebyl přítomen" a
    #       „zápis to neříká" jsou dvě různá tvrzení.
    #   „Vladimír Kafka Miloslav Pelc – 2.mst" — slepenec dvou jmen. To je
    #       poškozená hlavička a zápis se z docházky vyřadí celý.
    poskozeno = False
    for klic in ("pritomni", "nepritomni", "omluveni", "neomluveni"):
        # Hosté se nefiltrují — nejsou to členové a mívají u sebe firmu
        # v závorce, kterou by kontrola jména zahodila i se stopou.
        jmena = ven.get(klic)
        if not isinstance(jmena, list) or not jmena:
            continue
        cista = [j for j in jmena if _je_jmeno(j)]
        if any(_je_slepenec(j) for j in jmena if not _je_jmeno(j)):
            poskozeno = True
        ven[klic] = cista if cista else None
    ven["hlavicka_poskozena"] = poskozeno
    return ven


# Město samo. Jako „organizace hosta" nenese žádnou informaci — úředník
# města je na komisi města doma, ne stopa. Stejná zásada jako u řetězu na
# smlouvy, kde se IČO města jako identita nepoužívá.
ICO_MESTA = "00254061"
_MESTO_SAMO = {"mesto marianske lazne", "marianske lazne", "mestsky urad marianske lazne",
               "mesto", "muml"}


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
    if _bez_diakritiky(org) in _MESTO_SAMO:
        return None  # město na vlastní komisi není stopa
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


# Pod tolik znaků je dokument prakticky bez textové vrstvy — sken, ze
# kterého pdftotext vytáhl leda hlavičku úřadu.
PRAH_BEZ_TEXTU = 400

# Nadpis bodu, který není číslovaný: „Ad 3) Různé", „Hlavní bod jednání —
# …", „Program jednání Komise sportu:". Slouží jen k rozlišení, PROČ se
# zápis nepodařilo rozebrat; body se z toho nedělají.
_NADPIS_BODU = re.compile(
    r"(?im)^\s*(?:Ad\s*\d|Bod\s*\d|Hlavn[íi]\s+bod|Program\s+jedn[áa]n[íi])"
)
_SLOVESO_VULE = re.compile(
    r"(?i)(doporu[čc]uj|nedoporu[čc]uj|navrhuj|odsouhlasil|schv[áa]lil|"
    r"[žz][áa]d[áa]|ukl[áa]d[áa])"
)


def _duvod_nerozebrani(text: str) -> str:
    """Proč se ze zápisu nepodařilo vytáhnout ani bod, ani usnesení.

    NENÍ TO OCR. Všech 364 stažených zápisů má textovou vrstvu — nejkratší
    má 450 znaků. Dřív se tu psalo, že jsou to skeny; nejsou. Selhává
    struktura: jednání je zapsané jako souvislé vyprávění bez číslovaných
    bodů a bez bloku „Usnesení".

    Rozlišuje se to proto, že „nepodařilo se to přečíst" je bez důvodu
    jen omluva. S důvodem je z toho měřitelný stav zdroje.
    """
    if len(text or "") < PRAH_BEZ_TEXTU:
        return "bez-textove-vrstvy"
    ma_nadpis = bool(_NADPIS_BODU.search(text))
    ma_sloveso = bool(_SLOVESO_VULE.search(text))
    if ma_nadpis and ma_sloveso:
        # Zápis o návrzích mluví, ale ne větou, kterou by šlo vzít celou.
        return "navrh-jen-ve-vypraveni"
    if ma_nadpis:
        return "body-nejsou-cislovane"
    return "souvisly-text-bez-struktury"


POPIS_DUVODU = {
    "bez-textove-vrstvy": "dokument nemá text, je to sken",
    "navrh-jen-ve-vypraveni": (
        "zápis o návrzích mluví, ale ne větou, kterou by šlo vzít celou "
        "— chybí blok „Usnesení“ i věta začínající orgánem"
    ),
    "body-nejsou-cislovane": "body programu nejsou číslované a zápis nemá blok „Usnesení“",
    "souvisly-text-bez-struktury": "souvislé vyprávění bez bodů i bez usnesení",
}


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
        # Zápis, ze kterého se nepodařilo vytáhnout ani body, ani usnesení.
        "rozebrano": bool(body or usneseni),
        # A hlavně PROČ. Bez důvodu je „nepodařilo se" jen omluva.
        "duvod_nerozebrani": None if (body or usneseni) else _duvod_nerozebrani(text),
    }


# ── párování komisí mezi dvěma zdroji ───────────────────────────────────
# Rozcestník samosprávy a rejstřík zápisů píšou tytéž komise jinak:
#   „Komise lázeňství, CR a UNESCO"  ×  „Komise lázeňství, cestovního ruchu a UNESCO"
# Spojení přes přesnou shodu názvu proto u té nejaktivnější komise tvrdilo
# „žádný zápis nezveřejněn", ačkoliv jich má 87. Páruje se na významových
# slovech; zkratky („CR") se do porovnání nepočítají, protože v druhém
# zdroji stojí rozepsané.
_BEZ_VYZNAMU = {"komise", "komisi", "vybor", "vyboru", "mesta", "a", "pro", "ve", "na"}


def _klicova_slova(nazev: str) -> set[str]:
    return {
        w for w in re.sub(r"[^a-z0-9]+", " ", _bez_diakritiky(nazev)).split()
        if len(w) >= 4 and w not in _BEZ_VYZNAMU
    }


def _sparuj_organy(organy: list[dict], komise_v_zapisech: set[str]) -> dict[str, str]:
    """Název komise ze zápisů → název orgánu v rozcestníku samosprávy.

    Páruje se jen tehdy, když je vítěz jednoznačný. Dvojznačnou shodu je
    lepší nechat nespárovanou a přiznat to než ji přiřadit napůl náhodně —
    stejná zásada jako u řetězů.
    """
    kandidati = [(o.get("nazev") or "", _klicova_slova(o.get("nazev") or "")) for o in organy]
    # Shoda na celý název je jistota, ne odhad, a musí se zkusit dřív než
    # překryv slov. Kdyby město zřídilo „Komisi sportu a mládeže", měla by
    # stávající „Komise sportu" s oběma překryv jednoho slova, remíza by
    # párování zamítla a komise by přišla o všech 82 zápisů — přestože se
    # její název shoduje přesně.
    dle_nazvu = {_bez_diakritiky(o.get("nazev") or "").strip(): (o.get("nazev") or "")
                 for o in organy}
    parovani: dict[str, str] = {}
    for komise in komise_v_zapisech:
        presna = dle_nazvu.get(_bez_diakritiky(komise).strip())
        if presna:
            parovani[komise] = presna
            continue
        slova = _klicova_slova(komise)
        if not slova:
            continue
        skore = sorted(
            ((len(slova & k), nazev) for nazev, k in kandidati if slova & k),
            reverse=True,
        )
        if not skore:
            continue
        if len(skore) > 1 and skore[0][0] == skore[1][0]:
            continue  # dvě stejně dobré shody — hádat se tu nemá co
        parovani[komise] = skore[0][1]
    return parovani


def _jmeno_hosta(host: str) -> str | None:
    """Jméno hosta z textu před závorkou.

    Zápisy sem dávají celé věty: „přizvané hosty a předal slovo
    p. Hulákovi (Basketbalový klub…)". Bere se poslední souvislý úsek
    slov začínajících velkým písmenem — to je jméno. Když žádný není,
    vrací se `None`; vypsat půl věty jako jméno hosta je horší než
    nevypsat nic.
    """
    pred = _ocisti_jmeno((host or "").split("(")[0])
    slova = pred.split()
    konec = len(slova)
    while konec > 0 and slova[konec - 1][:1].isupper():
        konec -= 1
    jmeno = " ".join(slova[konec:][:4]).strip(" ,;-")
    return jmeno or None


def _protistrany_registru() -> tuple[dict[str, dict], dict[str, dict]]:
    """(podle IČO, podle normalizovaného názvu) z agregace registru smluv.

    Slouží k jediné otázce: obchoduje organizace, která přišla na komisi,
    taky s městem? Odpověď je ukazatel k dohledání — účast na veřejném
    jednání není nic nepatřičného a přehled z ní žádný závěr nedělá.
    """
    agr = nacti("penize/agregace/protistrany.json") or {}
    dle_ica: dict[str, dict] = {}
    dle_nazvu: dict[str, dict] = {}
    for p in agr.get("protistrany") or []:
        if p.get("ico") == ICO_MESTA:
            continue
        # Jedna firma má v agregaci až tři záznamy (výdaj, příjem, neurčen).
        # Sčítají se — čtenáře zajímá objem, ne členění podle směru.
        for klic, kam in ((p.get("ico"), dle_ica),
                          (_bez_diakritiky(p.get("nazev") or ""), dle_nazvu)):
            if not klic:
                continue
            stav = kam.setdefault(klic, {"nazev": p.get("nazev"), "ico": p.get("ico"),
                                         "celkem_czk": 0.0, "smluv": 0,
                                         "prvni_rok": None, "posledni_rok": None})
            stav["celkem_czk"] += float(p.get("celkem_czk") or 0)
            stav["smluv"] += int(p.get("smluv") or 0)
            for pole, vyber in (("prvni_rok", min), ("posledni_rok", max)):
                if p.get(pole):
                    stav[pole] = p[pole] if stav[pole] is None else vyber(stav[pole], p[pole])
    return dle_ica, dle_nazvu


# Zápis píše do závorky i roli hosta: „(ředitel SPRÁVY MĚSTSKÝCH SPORTOVIŠŤ,
# p. o.)", „(investor Madruzzo s.r.o.)". Role není součást názvu firmy a při
# hledání v registru překáží. V uloženém poli `organizace` ale zůstává —
# je to citace ze zápisu a přepisovat ji by znamenalo měnit zdroj.
_ROLE_PRED_NAZVEM = re.compile(
    r"(?i)^\s*(?:[řr]editel(?:ka)?|jednatel(?:ka)?|investor(?:ka)?|z[áa]stupce|"
    r"z[áa]stupkyn[ěe]|p[řr]edseda|p[řr]edsedkyn[ěe]|majitel(?:ka)?|za)\s+"
)


def _obchod_s_mestem(ico: str | None, organizace: str,
                     dle_ica: dict[str, dict], dle_nazvu: dict[str, dict]) -> dict | None:
    """Má organizace hosta smlouvy s městem? `None` = žádné jsme nenašli.

    Shoda podle IČO je doklad, shoda podle názvu odhad — firma téhož
    jména může sídlit jinde. Rozdíl se nese ven, ať ho web ukáže.
    """
    if ico and ico in dle_ica:
        return {**dle_ica[ico], "shoda": "ico"}
    cisty = _ROLE_PRED_NAZVEM.sub("", organizace).strip()
    for varianta in (organizace, cisty):
        nalez = dle_nazvu.get(_bez_diakritiky(varianta))
        if nalez:
            return {**nalez, "shoda": "nazev"}
    # Právní forma se v zápisu a v registru píše různě: „AV-ELZO s.r.o"
    # × „AV-ELZO s.r.o.". Porovnává se proto jádro názvu bez ní.
    jadro = _bez_diakritiky(_PRAVNI_FORMA.sub("", cisty).strip(" ,."))
    if len(jadro) < 5:
        return None
    # Registr píše tutéž firmu několika způsoby („MADRUZZO a.s." ×
    # „MADRUZZO a. s., Robert Vaněk"), někdy s IČO a někdy bez. Vybrat
    # jeden záznam by objem podstřelilo, proto se sčítají všechny — a nese
    # se ven, kolik jich bylo a jak se jmenují, ať je to vidět.
    shody = [h for k, h in dle_nazvu.items() if k.startswith(jadro)]
    if not shody:
        return None
    roky = [r for h in shody for r in (h["prvni_rok"], h["posledni_rok"]) if r]
    return {
        "nazev": shody[0]["nazev"],
        "ico": next((h["ico"] for h in shody if h["ico"]), None),
        "celkem_czk": sum(h["celkem_czk"] for h in shody),
        "smluv": sum(h["smluv"] for h in shody),
        "prvni_rok": min(roky) if roky else None,
        "posledni_rok": max(roky) if roky else None,
        "shoda": "nazev-bez-formy",
        "zaznamu_v_registru": len(shody),
        "nazvy_v_registru": sorted({h["nazev"] for h in shody if h["nazev"]}),
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


# ── docházka ────────────────────────────────────────────────────────────

def _klic_jmena(jmeno: str) -> str:
    return _bez_diakritiky(_ocisti_jmeno(jmeno))


def _spoj_prijmeni(jmena: set[str]) -> dict[str, str]:
    """Zkrácený tvar jména → celé jméno, když je v komisi jednoznačné.

    Zápisy střídají „Roman Kořán", „p. Kořán" a „R. Šnajdr". Bez spojení
    by z jednoho člena vyšli dva až tři a docházka by seděla každému
    kousek. Spojuje se JEN při jediném kandidátovi — dvě řádky jsou lepší
    než splynutí dvou různých lidí.
    """
    def cele(j: str) -> bool:
        # Zkratka s tečkou je iniciála, i když má dvě písmena („Vl."),
        # a celé jméno z ní nedělá ani to, že vypadá jako slovo.
        def plne_slovo(c: str) -> bool:
            return len(c.rstrip(".")) >= 3 or not c.endswith(".")
        casti = j.split()
        return len(casti) >= 2 and all(plne_slovo(c) for c in casti)

    cela = {j for j in jmena if cele(j)}
    mapa: dict[str, str] = {}
    for kratke in jmena - cela:
        casti = kratke.split()
        prijmeni = casti[-1]
        # „Kořán" i „R. Šnajdr" — u iniciály musí sedět i první písmeno.
        iniciala = casti[0].rstrip(".") if len(casti) == 2 else None
        sedici = [
            c for c in cela
            if c.split()[-1] == prijmeni
            and (iniciala is None or c.split()[0].startswith(iniciala))
        ]
        if len(sedici) == 1:
            mapa[kratke] = sedici[0]
    return mapa


def dochazka(zapisy: list[dict], log: Log) -> dict:
    """Kdo na komisi chodil, počítáno jen z jednání, kde je vůbec jmenován.

    ZÁSADNÍ MEZ: složení komisí se v čase mění a rozcestník samosprávy
    uvádí jen to dnešní. Kdyby se za absenci brala každá schůze, na které
    člen není v přítomných, vyšlo by členovi jmenovanému loni sto absencí
    z let, kdy v komisi vůbec nebyl. Jmenovatel je proto počet jednání,
    na kterých ho hlavička uvádí — přítomného, nepřítomného či omluveného.

    Do počítání jdou jen zápisy s čitelnou hlavičkou. Zápis, kde se jména
    slila dohromady, by přisoudil cizí absenci.
    """
    pouzitelne = [
        z for z in zapisy
        if z.get("pritomni") and not z.get("hlavicka_poskozena")
    ]
    dle_komise: dict[str, dict[str, dict]] = {}
    for z in pouzitelne:
        komise = z.get("komise") or "neurčeno"
        stav = dle_komise.setdefault(komise, {})
        skupiny = (
            ("pritomen", z.get("pritomni") or []),
            ("omluven", z.get("omluveni") or []),
            ("neomluven", z.get("neomluveni") or []),
            # „Nepřítomen" bez důvodu — zápis nerozlišuje omluvu.
            ("nepritomen", z.get("nepritomni") or []),
        )
        for druh, jmena in skupiny:
            for j in jmena:
                klic = _klic_jmena(j)
                if not klic:
                    continue
                osoba = stav.setdefault(klic, {
                    "jmeno": _ocisti_jmeno(j), "pritomen": 0, "omluven": 0,
                    "neomluven": 0, "nepritomen": 0,
                })
                osoba[druh] += 1

    # Sloučení „Kořán" a „Roman Kořán" uvnitř jedné komise.
    vysledek: dict[str, list[dict]] = {}
    for komise, lide in dle_komise.items():
        mapa = _spoj_prijmeni(set(lide))
        slouceno: dict[str, dict] = {}
        for klic, osoba in lide.items():
            cil = mapa.get(klic, klic)
            stav = slouceno.setdefault(cil, {"jmeno": osoba["jmeno"], "pritomen": 0,
                                             "omluven": 0, "neomluven": 0,
                                             "nepritomen": 0})
            # Delší tvar jména je ten úplnější, ten se nechá k zobrazení.
            if len(osoba["jmeno"]) > len(stav["jmeno"]):
                stav["jmeno"] = osoba["jmeno"]
            for k in ("pritomen", "omluven", "neomluven", "nepritomen"):
                stav[k] += osoba[k]
        radky = []
        for osoba in slouceno.values():
            jmenovan = sum(osoba[k] for k in
                           ("pritomen", "omluven", "neomluven", "nepritomen"))
            radky.append({**osoba, "jmenovan_na": jmenovan})
        radky.sort(key=lambda r: (-r["jmenovan_na"], r["jmeno"]))
        vysledek[komise] = radky

    log.info("docházka spočítána", zapisu=len(pouzitelne),
             komisi=len(vysledek), osob=sum(len(v) for v in vysledek.values()))
    return {
        "metodika": {
            "co_to_je": (
                "Kdo na jednání komise chodil. Počítá se jen z jednání, kde ho "
                "hlavička zápisu jmenuje — přítomného, nepřítomného nebo omluveného."
            ),
            "jmenovatel": (
                "`jmenovan_na` je počet jednání, na kterých se jméno v hlavičce "
                "objevuje. NENÍ to počet všech jednání komise: složení se v čase mění "
                "a člen jmenovaný letos by jinak měl absence z let, kdy v komisi nebyl."
            ),
            "nepritomen_vs_omluven": (
                "„Nepřítomen“ je stav, který zápis uvádí bez důvodu. Omluvu od "
                "neomluvené absence rozliší jen část zápisů, proto se to nesčítá "
                "dohromady — dopočítat důvod by byl dohad."
            ),
            "co_chybi": (
                f"Do počítání jde {len(pouzitelne)} zápisů z {len(zapisy)}. Zbytek buď "
                "hlavičku s přítomnými nemá, nebo se v ní jména slila dohromady; "
                "takový zápis by přisoudil cizí absenci a vynechává se celý."
            ),
            "prijmeni": (
                "„p. Kořán“ a „Roman Kořán“ se spojí, jen když příjmení v té komisi "
                "sedí na jediného člena. Jinak zůstávají zvlášť — dvě řádky jsou lepší "
                "než splynutí dvou lidí."
            ),
        },
        "zapisu_pouzito": len(pouzitelne),
        "zapisu_celkem": len(zapisy),
        "po_komisich": vysledek,
    }


# ── členství: propojení komisí s rejstříkem osobností ───────────────────

def _tokeny_jmena(jmeno: str) -> frozenset[str]:
    """Jméno jako množina slov — pořadí se v zápisech liší.

    Komise lázeňství píše „Richter Jiří", ostatní „Jiří Richter". Kdyby
    se porovnával řetězec, byli by to dva různí lidé.
    """
    return frozenset(
        w for w in _bez_diakritiky(_ocisti_jmeno(jmeno)).split() if len(w) >= 2
    )


def _rejstrik_osobnosti() -> dict[frozenset[str], dict]:
    """Množina slov jména → osobnost. Nejednoznačná jména se vynechají."""
    osobnosti = nacti("lide/osobnosti.json") or []
    dle_tokenu: dict[frozenset[str], list[dict]] = {}
    for o in osobnosti if isinstance(osobnosti, list) else []:
        klic = _tokeny_jmena(o.get("jmeno") or "")
        if len(klic) >= 2:
            dle_tokenu.setdefault(klic, []).append(o)
    # Dva lidé téhož jména se spojit nesmí; radši ani jednoho.
    return {k: v[0] for k, v in dle_tokenu.items() if len(v) == 1}


def clenstvi(ucast: dict, parovani: dict[str, str], log: Log) -> dict:
    """Kdo v komisích sedí a jak tam chodí, po osobách.

    Skládá se ze dvou zdrojů: rozcestník samosprávy říká DNEŠNÍ složení
    a roli, zápisy říkají docházku za celou dobu. Člověk může mít
    docházku a v dnešním složení nebýt — komise se obměňují a to je
    samo o sobě údaj, ne chyba.
    """
    organy = (nacti("komise/organy.json") or {}).get("organy") or []
    rejstrik = _rejstrik_osobnosti()

    # Docházka podle (název komise v ZÁPISECH, tokeny jména). Komise se
    # v rozcestníku a v rejstříku zápisů jmenuje jinak, proto se tu jede
    # přes už spočítané párování — a jen přes ně. První verze hledala jen
    # podle jména a přiřadila docházku z Komise kultury i Finančnímu
    # výboru, který žádné zápisy nemá.
    dle_organu = {organ: komise for komise, organ in parovani.items()}
    dochazka_dle: dict[tuple[str, frozenset[str]], dict] = {}
    for komise, radky in (ucast.get("po_komisich") or {}).items():
        for r in radky:
            dochazka_dle[(komise, _tokeny_jmena(r["jmeno"]))] = r

    dle_osoby: dict[str, list[dict]] = {}
    bez_osobnosti: list[str] = []
    for o in organy:
        komise = o.get("nazev") or ""
        for clen in o.get("osoby") or []:
            tokeny = _tokeny_jmena(clen.get("jmeno") or "")
            osobnost = rejstrik.get(tokeny)
            if osobnost is None:
                bez_osobnosti.append(clen.get("jmeno") or "")
                continue
            # Docházka se bere JEN z té komise, o kterou jde. Orgán, který
            # zápisy nezveřejňuje, docházku prostě nemá.
            komise_v_zapisech = dle_organu.get(komise)
            zaznam = (dochazka_dle.get((komise_v_zapisech, tokeny))
                      if komise_v_zapisech else None)
            dle_osoby.setdefault(osobnost["id"], []).append({
                "komise": komise,
                "role": clen.get("role"),
                "url_komise": o.get("url"),
                "dochazka": (
                    {k: zaznam[k] for k in
                     ("jmenovan_na", "pritomen", "omluven", "neomluven", "nepritomen")}
                    if zaznam else None
                ),
            })
    for seznam in dle_osoby.values():
        seznam.sort(key=lambda x: x["komise"])

    log.info("členství v komisích spárováno", osob=len(dle_osoby),
             bez_osobnosti=len(bez_osobnosti))
    return {
        "metodika": {
            "co_to_je": (
                "V jakých komisích člověk sedí a jak tam chodí. Složení a role jsou "
                "z rozcestníku samosprávy, docházka ze zápisů."
            ),
            "dnesni_slozeni": (
                "Rozcestník uvádí jen DNEŠNÍ složení. Kdo v komisi byl dřív, tu není, "
                "i když má v zápisech docházku — komise se obměňují."
            ),
            "parovani": (
                "Osoba se s rejstříkem osobností páruje podle množiny slov jména, ne "
                "podle pořadí: zápisy Komise lázeňství píšou „Richter Jiří“, ostatní "
                "„Jiří Richter“. Jméno, které sedí na dvě osobnosti, se nespáruje."
            ),
            "chybejici": (
                f"{len(bez_osobnosti)} členů komisí nemá v rejstříku osobností záznam. "
                "Nejsou to veřejně činné osoby sledované projektem a profil nemají."
            ),
            "dochazka_null": (
                "`dochazka: null` znamená, že se ke členovi nenašel ani jeden zápis "
                "s čitelnou hlavičkou. Není to nulová účast."
            ),
        },
        "osob": len(dle_osoby),
        "clenu_bez_osobnosti": len(bez_osobnosti),
        "dle_osoby": dle_osoby,
    }


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
    dle_ica, dle_nazvu = _protistrany_registru()
    stopy: list[dict] = []
    for r in rozebrane:
        for h in r["hoste_s_organizaci"]:
            klic = _bez_diakritiky(re.sub(r"\s+", " ", h["organizace"]))
            nalez = firmy.get(klic)
            ico = (nalez or {}).get("ico")
            stopy.append({
                "datum": r["datum"],
                "komise": r["komise"],
                # Citace ze zápisu tak, jak tam stojí.
                "host": h["host"],
                # A z ní jen jméno, když se dá poznat. Web ukazuje tohle.
                "host_jmeno": _jmeno_hosta(h["host"]),
                "organizace": h["organizace"],
                "ico": ico,
                "jistota": "nazev-sedi" if nalez else "nedohledano",
                # Druhý konec stopy: obchoduje ta organizace s městem?
                # Prázdno znamená „nenašli jsme", ne „neobchoduje".
                "obchod_s_mestem": _obchod_s_mestem(ico, h["organizace"], dle_ica, dle_nazvu),
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

    # Zápisy přiřazené k orgánům z rozcestníku samosprávy. Web tím plní
    # sloupec „Zápisů" v tabulce komisí; bez párování by u komise, kterou
    # zdroje pojmenovávají různě, stálo „žádný nezveřejněn".
    organy = (nacti("komise/organy.json") or {}).get("organy") or []
    parovani = _sparuj_organy(organy, {k for k in po_komisich if k != "neurčeno"})
    po_organech: Counter[str] = Counter()
    for komise, pocet in po_komisich.items():
        cil = parovani.get(komise)
        if cil:
            po_organech[cil] += pocet
    nesparovane = sorted(k for k in po_komisich if k != "neurčeno" and k not in parovani)
    if nesparovane:
        log.info("komise ze zápisů bez orgánu v rozcestníku", komise=nesparovane)

    # Rejstřík je širší než to, z čeho máme text — a je poctivé vědět o kolik.
    rejstrik = nacti("komise/zapisy.json") or {}
    polozky = rejstrik.get("zapisy") or []
    rejstrik_celkem = len(polozky)
    dle_typu: Counter[str] = Counter(
        (re.search(r"\.(\w{2,4})$", (p.get("soubor") or "").lower()) or [None, "bez přípony"])[1]
        for p in polozky
    )

    nerozebrano = [r for r in rozebrane if not r["rozebrano"]]
    duvody_nerozebrani: Counter[str] = Counter(
        r["duvod_nerozebrani"] for r in nerozebrano if r["duvod_nerozebrani"]
    )

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
            "parovani_organu": (
                "Rozcestník samosprávy a rejstřík zápisů píšou tytéž komise jinak "
                "(„Komise lázeňství, CR a UNESCO“ × „…cestovního ruchu…“). Páruje se "
                "na významových slovech názvu a jen při jednoznačném vítězi; co se "
                "nespárovalo, je v `komise_bez_organu`."
            ),
            "nerozebrane_nejsou_skeny": (
                "Zápis v `nerozebrane` NENÍ sken. Všechny stažené zápisy textovou vrstvu "
                "mají; nejkratší má 450 znaků. Co chybí, je struktura — číslované body "
                "a blok „Usnesení“. Důvod nese u každého pole `duvod`; „nepodařilo se to "
                "přečíst“ bez důvodu je jen omluva."
            ),
            "rejstrik_vs_text": (
                "Rejstřík je širší než to, z čeho máme text, a chybí to ze tří různých "
                "důvodů: archivy ZIP se neotvírají vůbec, u části PDF nevrátí pdftotext "
                "nic (to jsou skutečné skeny a tam by OCR pomohlo) a zbytek text má. "
                "Počty jsou v `souhrn.rejstrik_dle_typu` a `souhrn.s_textem`."
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
            # Klíčem je název orgánu tak, jak ho uvádí rozcestník samosprávy
            # (data/komise/organy.json) — web podle něj plní tabulku komisí.
            "po_organech": dict(po_organech.most_common()),
            # Komise, které mají zápisy, ale v rozcestníku se nenašly.
            # Prázdný seznam znamená, že sedí všechny.
            "komise_bez_organu": nesparovane,
            "duvody_nerozebrani": dict(duvody_nerozebrani.most_common()),
            # Co je v rejstříku proti tomu, z čeho máme text. Rozdíl není
            # jedna věc: ZIP se neotvírá vůbec, u části PDF pdftotext nic
            # nevrátí (to jsou skutečné skeny). Držet to zvlášť brání
            # tvrzení „nerozebrané zápisy jsou skeny" — nejsou.
            "v_rejstriku": rejstrik_celkem,
            "rejstrik_dle_typu": dict(dle_typu.most_common()),
            "s_textem": len(rozebrane),
        },
        "nerozebrane": [
            {"komise": r["komise"], "datum": r["datum"], "url": r["url"],
             "duvod": r["duvod_nerozebrani"],
             "popis": POPIS_DUVODU.get(r["duvod_nerozebrani"] or "", "neurčeno")}
            for r in nerozebrano
        ],
        "zapisy": rozebrane,
    })

    ucast = dochazka(rozebrane, log)
    uloz("komise/ucast.json", ucast)
    uloz("komise/clenstvi.json", clenstvi(ucast, parovani, log))

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
            "obchod_s_mestem": (
                "Dohledání organizace hosta v registru smluv. `shoda: ico` je doklad, "
                "`nazev` a `nazev-bez-formy` jsou odhad — firma téhož jména může sídlit "
                "jinde. Prázdno znamená „v registru jsme ji nenašli“, ne „s městem "
                "neobchoduje“; skloňovaný název ze zápisu („ředitel SPRÁVY městských "
                "sportovišť“) se s prvním pádem v registru nepotká. Když registr píše "
                "firmu víc způsoby, částky se sečtou a `zaznamu_v_registru` říká, přes "
                "kolik zápisů."
            ),
            "mesto_neni_host": (
                "Úředník uvedený v závorce jako „(město Mariánské Lázně)“ se mezi stopy "
                "nepočítá. Město na vlastní komisi není stopa — stejná zásada jako "
                "u řetězu na smlouvy, kde se IČO města jako identita nepoužívá."
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
