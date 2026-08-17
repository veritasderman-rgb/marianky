"""Sběrač B1 — Kdo je kdo.

Natáhne z webu města to, co jde získat automaticky — zastupitelstvo, radu,
vedení města, vedoucí odborů úřadu, ředitele a jednatele městských organizací
a členy dozorčích rad městských firem — a sloučí to do
`data/lide/osobnosti.json`.

Zbytek databáze (historické osobnosti, kultura, sport, věda, podnikání) je
doplněn ručně a sběrač se ho nedotýká.

ZÁSADY (drží se docs/PLAN.md):

* **Slučuje se podle `id`, ručně doplněné údaje se nikdy nepřepisují.** Sběrač
  umí doplnit jen to, co sám vidí — jméno, stranu, roli a funkci. Pole `popis`,
  `kategorie`, `zdroje`, `zijici`, `narozen`, `zemrel` patří člověku a sběrač
  do nich sahá jen tehdy, jsou-li prázdná.
* **Funkce se ukládají s platností od–do, ne jako aktuální stav.** Sběrač vidí
  jen dnešek, takže nově nalezené funkci nechává `do: null`. Funkci, která ze
  zdroje zmizela, sám NEUZAVÍRÁ — jen na ni upozorní v logu. Zmizet totiž může
  i kvůli chybě na webu města a tiše přepsaná historie je horší než chybějící
  údaj.
* **U úředníků se sbírá jen jméno a funkce.** Telefony, mobily a e-maily z
  telefonního seznamu se záměrně NEUKLÁDAJÍ — do přehledu osobností nepatří.
* Zdroj buď uspěje, nebo vyhodí `ZdrojSelhal`. Kontrolní počty níže
  (`MIN_ZASTUPITELU` atd.) hlídají, že se nezměnila struktura stránky a sběrač
  nesmazal půlku zastupitelstva jako „nic nenalezeno".

Spouštění: `python3 scrapers/lide.py`
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from selectolax.parser import HTMLParser

from lib.core import Log, ZdrojSelhal, cistit, fetch, nacti, slug, uloz

SOUBOR = "lide/osobnosti.json"
WEB = "https://www.muml.cz"

# Volební období 2022–2026. Ustavující zasedání zastupitelstva proběhlo v
# říjnu 2022 po komunálních volbách 23.–24. 9. 2022.
OBDOBI_OD = "2022-10"

# Web města sneseme jen v rozumné dávce — modulů, které ho čtou, je víc.
# Hodinová cache znamená, že opakované spuštění během ladění nesahá na server
# znovu, denní běh přesto dostane čerstvá data.
CACHE_S = 3600

# Kontrolní minima — když se jich nedosáhne, zdroj se nejspíš rozbil.
MIN_ZASTUPITELU = 15
MIN_ODBORU = 8
MIN_ORGANIZACI = 12
MIN_DOZORCICH_RAD = 4

STRANKY = {
    "zastupitelstvo": f"{WEB}/samosprava/zastupitelstvo/clenove-1/",
    "rada": f"{WEB}/samosprava/rada/",
    "vedeni": f"{WEB}/samosprava/vedeni-mesta/",
    "seznam": f"{WEB}/kontakty/telefonni-seznam/",
}

# Odbory, oddělení a útvary městského úřadu — stránky telefonního seznamu.
ODBORY = [
    "odbor-dopravy-silnicniho-hospodarstvi-a-spravnich-agend-66",
    "odbor-financni-20",
    "odbor-kultury-lazenstvi-cestovniho-ruchu-a-unesco-76",
    "odbor-legislativy-spravnich-agend-a-zivnostensky-urad-31",
    "odbor-rozvoje-mesta-investic-a-dotaci-24",
    "odbor-socialnich-veci-29",
    "odbor-spravy-majetku-mesta-69",
    "odbor-stavebniho-uradu-26",
    "odbor-skolstvi-30",
    "odbor-vnitrnich-veci-a-spravnich-agend-17",
    "odbor-zivotniho-prostredi-28",
    "oddeleni-mistnich-poplatku-70",
    "oddeleni-pohledavek-68",
    "oddeleni-prestupku-67",
    "oddeleni-uzemniho-planovani-62",
    "utvar-kancelar-starosty-99",
    "utvar-kancelar-tajemnika-14",
]

# Městské příspěvkové organizace, školy a obchodní společnosti.
ORGANIZACE = [
    "zakladni-skola-usovice-39",
    "zakladni-skola-jih-40",
    "zakladni-skola-vitezstvi-41",
    "zakladni-umelecka-skola-fchopina-42",
    "mestsky-dum-deti-a-mladeze-43",
    "materska-skola-vora-44",
    "materska-skola-krizikova-45",
    "materska-skola-hlavni-46",
    "materska-skola-usovice-47",
    "materska-skola-tresnovka-48",
    "domov-pro-seniory-a-dum-s-pecovatelskou-sluzbou-34",
    "sprava-mestskych-sportovist-35",
    "mestska-knihovna-36",
    "mestske-muzeum-37",
    "mestske-divadlo-marianske-lazne-100",
    "infocentrum-marianske-lazne-sro-49",
    "tds-spol-s-ro-50",
    "lazenske-lesy-spol-s-ro-51",
    "develop-centrum-marianske-lazne-sro-84",
    "nemocnice-marianske-lazne-sro-86",
]

# Dozorčí rady společností, do kterých město nominuje své zástupce. Sedí v nich
# i zastupitelé, takže je to jedno z mála míst, kde je vidět propojení
# samosprávy s firmami — pro přehled „kdo je kdo" klíčové.
DOZORCI_RADY = [
    "chevak-cheb-as-vodarenska-spolecnost-91",
    "mestska-doprava-marianske-lazne-92",
    "infocentrum-marianske-lazne-sro-93",
    "technicky-a-dopravni-servis-sro-94",
    "develop-centrum-marianske-lazne-sro-95",
    "nemocnice-marianske-lazne-96",
]

# Funkce úřadu, které do přehledu patří — vedení odborů a veřejně vystupující
# role. Řadový referent do přehledu osobností nepatří.
URAD_FUNKCE = ("vedouc", "tajemn", "pověřen", "mluvč", "site manager", "velitel")

# Funkce v organizacích, které do přehledu patří.
FIRMY_FUNKCE = ("ředitel", "reditel", "jednatel", "vedouc")

# Web města píše u TDS „dozorní rada" i „dozorčí rada" — obojí musí projít.
DOZORCI_FUNKCE = ("dozorčí rad", "dozorní rad")

# --------------------------------------------------------------------------
# Jména
# --------------------------------------------------------------------------

# Akademické tituly a hodnosti před jménem i za ním.
TITULY = {
    "bc", "bca", "mgr", "mga", "ing", "arch", "judr", "mudr", "mvdr", "rndr",
    "phdr", "paeddr", "thdr", "thlic", "dr", "prof", "doc", "csc", "drsc",
    "ph", "d", "mba", "dba", "dis", "llm", "ll", "m", "et", "mba.", "phd",
}

# Jména, u kterých obecný algoritmus (příjmení = poslední slovo) selhává.
# Klíč je jméno tak, jak ho vypisuje web města.
VYJIMKY: dict[str, tuple[str, str]] = {
    # Telefonní seznam uvádí u ředitele ZUŠ příjmení jako první.
    "Tománek David, DiS.": ("tomanek-david", "David Tománek"),
}


def _bez_titulu(jmeno: str) -> str:
    """Odstraní akademické tituly před jménem i za ním."""
    j = cistit(jmeno).replace("\xa0", " ")
    j = j.split(",")[0]  # „Novák Jan, DiS." → „Novák Jan"
    slova = [s for s in j.split() if s]
    ocistena = []
    for s in slova:
        holy = re.sub(r"[.\s]", "", s).lower()
        holy = "".join(c for c in holy if c.isalpha())
        # „Ing.arch." se v seznamu píše i bez mezery
        casti = [c for c in re.split(r"[.\s]", s.lower()) if c]
        if holy in TITULY or (casti and all(c in TITULY for c in casti)):
            continue
        ocistena.append(s)
    return " ".join(ocistena)


def rozloz_jmeno(jmeno: str) -> tuple[str, str]:
    """Vrátí (id, čisté jméno) — id je slug `prijmeni-jmeno` podle PLAN.md.

    `id` MUSÍ odpovídat `osoba_id` v hlasování a v článcích zpravodaje,
    proto se počítá z jména bez titulů a bez diakritiky.

    Pravidlo je **příjmení + jedno křestní jméno**, nikdy víc. „Johann Wolfgang
    von Goethe" je `goethe-johann`, ne `goethe-johann-wolfgang` — jinak by se
    tentýž člověk v článcích zpravodaje a tady rozešel na dva různé lidi.
    Výjimky (predikáty typu „von Heilborn", panovnická jména jako „Eduard VII.")
    se v `data/lide/osobnosti.json` udržují ručně; sběrač na ně na webu města
    nenarazí.
    """
    if jmeno.strip() in VYJIMKY:
        return VYJIMKY[jmeno.strip()]
    ciste = _bez_titulu(jmeno)
    casti = ciste.split()
    if not casti:
        raise ZdrojSelhal(f"Z {jmeno!r} nezbylo po odstranění titulů žádné jméno")
    if len(casti) == 1:
        return slug(casti[0]), casti[0]
    prijmeni = casti[-1]
    krestni = casti[0]
    return f"{slug(prijmeni)}-{slug(krestni)}", ciste


# --------------------------------------------------------------------------
# Sjednocení názvů
# --------------------------------------------------------------------------

# Web města píše tutéž funkci na různých stránkách různě. Bez sjednocení by
# vznikaly dvojí záznamy („starosta" a „starosta města").
NAZVY_FUNKCI = {
    "starosta města": "starosta",
    "starostka města": "starostka",
    "místostarosta města": "místostarosta",
    "1. místostarosta města": "1. místostarosta",
    "2. místostarosta města": "2. místostarosta",
    "člen zastupitelstva města": "člen zastupitelstva",
    "člen rady": "člen rady města",
}


# Web města píše tutéž kandidátku různě — u jedné zastupitelky „ZpML",
# u ostatních „Změna pro ML". Bez sjednocení by se rozpadlo filtrování
# podle uskupení.
NAZVY_STRAN = {
    "zpml": "Změna pro ML",
    "změna pro ml": "Změna pro ML",
    "změna pro mariánské lázně": "Změna pro ML",
    "ano": "ANO 2011",
    "ano 2011": "ANO 2011",
    "piráti": "Piráti",
    "ods plus": "ODS Plus",
    "stan": "STAN",
    "spd": "SPD",
    "město sobě": "Město sobě",
}


def normalizuj_stranu(nazev: str | None) -> str | None:
    if not nazev:
        return None
    n = cistit(nazev).replace("\xa0", " ")
    return NAZVY_STRAN.get(n.lower(), n)


def normalizuj_funkci(nazev: str) -> str:
    n = cistit(nazev)
    if not n:
        return n
    # „Ředitelka — Městská knihovna" → „ředitelka — Městská knihovna"
    n = n[0].lower() + n[1:]
    return NAZVY_FUNKCI.get(n.lower(), n)


# --------------------------------------------------------------------------
# Parsování stránek
# --------------------------------------------------------------------------

def _osoby_na_strance(html: str) -> list[dict]:
    """Vytáhne bloky `div.person` — jméno, politická příslušnost, funkce.

    Kontakty (telefon, mobil, e-mail) se záměrně ignorují.
    """
    strom = HTMLParser(html)
    out = []
    for blok in strom.css("div.person"):
        nadpis = blok.css_first("h3")
        if not nadpis:
            continue
        jmeno = cistit(nadpis.text())
        if not jmeno:
            continue
        funkce = blok.css_first("div.function")
        strana = None
        for span in blok.css("span"):
            t = cistit(span.text())
            if t.lower().startswith("politická příslušnost"):
                strana = t.split(":", 1)[1].strip() or None
        out.append({
            "jmeno_raw": jmeno,
            "funkce": cistit(funkce.text()) if funkce else None,
            "strana": strana,
        })
    return out


def _nazev_stranky(html: str) -> str:
    h1 = HTMLParser(html).css_first("div.gcm-main h1")
    return cistit(h1.text()) if h1 else ""


def _zaznam(jmeno_raw: str, *, kategorie: str, role: str,
            funkce: list[dict], strana: str | None, zdroj: str) -> dict:
    ident, jmeno = rozloz_jmeno(jmeno_raw)
    return {
        "id": ident,
        "jmeno": jmeno,
        "role": [role],
        "kategorie": kategorie,
        "strana": normalizuj_stranu(strana),
        "funkce": [{**f, "nazev": normalizuj_funkci(f["nazev"])} for f in funkce],
        "popis": None,
        "zdroje": [zdroj],
        "zijici": True,
        "narozen": None,
        "zemrel": None,
    }


def sber_zastupitele(log: Log) -> list[dict]:
    url = STRANKY["zastupitelstvo"]
    osoby = _osoby_na_strance(fetch(url, max_age=CACHE_S))
    if len(osoby) < MIN_ZASTUPITELU:
        raise ZdrojSelhal(
            f"Seznam zastupitelů vrátil jen {len(osoby)} osob (min. {MIN_ZASTUPITELU}) — "
            f"struktura {url} se nejspíš změnila"
        )
    out = []
    for o in osoby:
        f = [{"nazev": "člen zastupitelstva", "od": OBDOBI_OD, "do": None}]
        # Starosta a místostarostové jsou na stránce uvedeni svou funkcí.
        if o["funkce"] and "člen" not in o["funkce"].lower():
            f.append({"nazev": o["funkce"].lower(), "od": None, "do": None})
        out.append(_zaznam(o["jmeno_raw"], kategorie="politika", role="zastupitel",
                           funkce=f, strana=o["strana"], zdroj=url))
    log.info("zastupitelé", pocet=len(out))
    return out


def sber_rada(log: Log) -> list[dict]:
    url = STRANKY["rada"]
    osoby = _osoby_na_strance(fetch(url, max_age=CACHE_S))
    if not osoby:
        raise ZdrojSelhal(f"Na {url} nebyl nalezen žádný člen rady")
    out = []
    for o in osoby:
        f = [{"nazev": "člen rady města", "od": None, "do": None}]
        if o["funkce"] and "člen rady" not in o["funkce"].lower():
            f.append({"nazev": o["funkce"].lower(), "od": None, "do": None})
        out.append(_zaznam(o["jmeno_raw"], kategorie="politika", role="radní",
                           funkce=f, strana=o["strana"], zdroj=url))
    log.info("rada města", pocet=len(out))
    return out


def sber_vedeni(log: Log) -> list[dict]:
    """Vedení města.

    Tahle stránka NEPOUŽÍVÁ `div.person` jako zbytek webu — je poskládaná
    z widgetů `div.editor.widget`, kde je funkce v `h2.title`, jméno v `h3`
    a stranické zázemí v první položce seznamu pod ním.
    """
    url = STRANKY["vedeni"]
    strom = HTMLParser(fetch(url, max_age=CACHE_S))
    hlavni = strom.css_first("div.gcm-main")
    if hlavni is None:
        raise ZdrojSelhal(f"Na {url} chybí blok div.gcm-main")
    videno: dict[str, dict] = {}
    for karta in hlavni.css("div.editor"):
        nadpis = karta.css_first("h2.title")
        jmeno_uzel = karta.css_first("div.content h3")
        if not nadpis or not jmeno_uzel:
            continue
        funkce = cistit(nadpis.text()).lower()
        jmeno = cistit(jmeno_uzel.text())
        if not jmeno or not funkce:
            continue
        strana = None
        polozky = [cistit(li.text()) for li in karta.css("div.content ul li")]
        polozky = [p for p in polozky if p and "podrobnosti" not in p.lower()]
        if polozky:
            strana = polozky[0]
        z = _zaznam(jmeno, kategorie="politika", role="vedení města",
                    funkce=[{"nazev": funkce, "od": None, "do": None}],
                    strana=strana, zdroj=url)
        videno.setdefault(z["id"], z)
    if not videno:
        raise ZdrojSelhal(f"Na {url} nebyl nalezen nikdo z vedení města")
    log.info("vedení města", pocet=len(videno))
    return list(videno.values())


def _sber_subjektu(log: Log, kody: list[str], *, kategorie: str, role: str,
                   klice: tuple[str, ...], minimum: int, popis: str,
                   chybi: str = "bez uvedeného vedoucího") -> list[dict]:
    """Projde stránky subjektů telefonního seznamu a vybere z nich jen ty osoby,
    jejichž funkce odpovídá některému z `klice`.

    `minimum` je pojistka: když se osoba nenajde u dost subjektů, není to
    „nikdo tam není", ale nejspíš změna struktury zdroje — a to je chyba.
    """
    out = []
    nalezeno_subjektu = 0
    for kod in kody:
        url = f"{WEB}/kontakty/telefonni-seznam/subjekt-{kod}.html"
        html = fetch(url, max_age=CACHE_S)
        nazev = _nazev_stranky(html)
        mel_nekoho = False
        for o in _osoby_na_strance(html):
            f = (o["funkce"] or "").lower()
            if not any(k in f for k in klice):
                continue
            mel_nekoho = True
            out.append(_zaznam(
                o["jmeno_raw"], kategorie=kategorie, role=role,
                funkce=[{"nazev": f"{o['funkce']} — {nazev}" if nazev else o["funkce"],
                         "od": None, "do": None}],
                strana=None, zdroj=url))
        if mel_nekoho:
            nalezeno_subjektu += 1
        else:
            log.info(f"{popis}: {chybi}", subjekt=nazev or kod)
    if nalezeno_subjektu < minimum:
        raise ZdrojSelhal(
            f"{popis}: vedoucí nalezen jen u {nalezeno_subjektu} z {len(kody)} subjektů "
            f"(min. {minimum}) — struktura telefonního seznamu se nejspíš změnila"
        )
    log.info(popis, osob=len(out), subjektu=nalezeno_subjektu)
    return out


def sber_urad(log: Log) -> list[dict]:
    """Vedoucí odborů a tajemník. Ukládá se JEN jméno a funkce."""
    return _sber_subjektu(log, ODBORY, kategorie="urad", role="úředník",
                          klice=URAD_FUNKCE, minimum=MIN_ODBORU, popis="městský úřad")


def sber_organizace(log: Log) -> list[dict]:
    """Ředitelé příspěvkových organizací a škol, jednatelé městských firem."""
    return _sber_subjektu(log, ORGANIZACE, kategorie="mestske-firmy", role="statutár",
                          klice=FIRMY_FUNKCE, minimum=MIN_ORGANIZACI,
                          popis="městské organizace")


def sber_dozorci_rady(log: Log) -> list[dict]:
    """Zástupci města v dozorčích radách městských a spoluvlastněných firem."""
    return _sber_subjektu(log, DOZORCI_RADY, kategorie="mestske-firmy",
                          role="člen dozorčí rady", klice=DOZORCI_FUNKCE,
                          minimum=MIN_DOZORCICH_RAD, popis="dozorčí rady",
                          chybi="bez uvedeného člena dozorčí rady")


# --------------------------------------------------------------------------
# Slučování
# --------------------------------------------------------------------------

# Pole, do kterých sběrač NIKDY nesahá, pokud už mají hodnotu — patří člověku.
RUCNI_POLE = ("popis", "kategorie", "zijici", "narozen", "zemrel")

PORADI_KATEGORII = ["politika", "urad", "mestske-firmy", "kultura", "sport",
                    "veda", "podnikani", "historie"]

# Web (modul B2) čte pevnou sadu polí. Každý záznam je musí mít všechna
# a ve stejném pořadí, i když je zrovna prázdné.
POLE = ["id", "jmeno", "role", "kategorie", "strana", "funkce", "popis",
        "zdroje", "zijici", "narozen", "zemrel"]


def _sjednot_pole(z: dict) -> dict:
    return {k: z.get(k) for k in POLE}


def _stejna_funkce(a: dict, b: dict) -> bool:
    """Funkce se považují za shodné, když mají stejný název.

    Sběrač neví, odkdy funkce platí, a posílá `od: null`. Kdyby se porovnávalo
    i podle `od`, ručně doplněný začátek funkce by způsobil, že se při každém
    běhu přidá duplicitní záznam s prázdným datem.
    """
    return a["nazev"].strip().lower() == b["nazev"].strip().lower()


def slouc(stare: list[dict], nove: list[dict], log: Log) -> list[dict]:
    """Sloučí čerstvě sebrané záznamy do stávající databáze podle `id`."""
    podle_id: dict[str, dict] = {z["id"]: z for z in stare}
    pridano = 0

    for n in nove:
        s = podle_id.get(n["id"])
        if s is None:
            podle_id[n["id"]] = n
            pridano += 1
            log.info("nová osoba", id=n["id"], jmeno=n["jmeno"])
            continue

        # jméno — doplní se jen, když chybí; ručně upřesněný tvar má přednost
        if not s.get("jmeno"):
            s["jmeno"] = n["jmeno"]
        # role — sjednocení, pořadí zachováno
        role = list(s.get("role") or [])
        for r in n["role"]:
            if r not in role:
                role.append(r)
        s["role"] = role
        # strana — jen když chybí
        if not s.get("strana") and n.get("strana"):
            s["strana"] = n["strana"]
        # funkce — přidají se jen ty, které tam ještě nejsou
        funkce = list(s.get("funkce") or [])
        for f in n["funkce"]:
            if not any(_stejna_funkce(f, g) for g in funkce):
                funkce.append(f)
                log.info("nová funkce", id=s["id"], funkce=f["nazev"])
        s["funkce"] = funkce
        # zdroje — sjednocení
        zdroje = list(s.get("zdroje") or [])
        for z in n["zdroje"]:
            if z not in zdroje:
                zdroje.append(z)
        s["zdroje"] = zdroje
        # ručně vyplněná pole zůstávají nedotčena
        for pole in RUCNI_POLE:
            if s.get(pole) in (None, "", []) and n.get(pole) not in (None, "", []):
                s[pole] = n[pole]

    log.pricti(pridano)

    # Upozornění na funkce, které ze zdroje zmizely. Sběrač je NEUZAVÍRÁ sám —
    # zdroj mohl jen zakolísat a tiše přepsaná historie je horší než chybějící údaj.
    #
    # Porovnávají se jen názvy funkcí, které sběrač v tomhle běhu vůbec umí
    # vyprodukovat. Bez toho by hlásil i ručně doplněné funkce mimo web města
    # (poslanec Evropského parlamentu, náměstek hejtmana), které tam nikdy nebyly.
    aktualni = {(n["id"], f["nazev"].strip().lower()) for n in nove for f in n["funkce"]}
    sberatelne = {nazev for _, nazev in aktualni}
    drive_videne = {(z["id"], f["nazev"].strip().lower())
                    for z in stare if z.get("kategorie") in ("politika", "urad", "mestske-firmy")
                    for f in (z.get("funkce") or [])
                    if f.get("do") is None and f["nazev"].strip().lower() in sberatelne}
    for ident, nazev in sorted(drive_videne - aktualni):
        log.info("POZOR: otevřená funkce už není ve zdroji, zkontroluj ručně",
                 id=ident, funkce=nazev)

    poradi = {k: i for i, k in enumerate(PORADI_KATEGORII)}
    serazene = sorted(podle_id.values(),
                      key=lambda z: (poradi.get(z.get("kategorie"), 99), z["id"]))
    return [_sjednot_pole(z) for z in serazene]


# --------------------------------------------------------------------------

def main() -> dict:
    log = Log("lide")
    stare = nacti(SOUBOR, default=[])
    log.info("stávající databáze", osob=len(stare))

    nove: list[dict] = []
    try:
        nove += sber_zastupitele(log)
        nove += sber_rada(log)
        nove += sber_vedeni(log)
        nove += sber_urad(log)
        nove += sber_organizace(log)
        nove += sber_dozorci_rady(log)
    except ZdrojSelhal as e:
        # Selhání se zapíše do logu běhu a pak bublá dál. Databáze zůstává
        # netknutá — polovičatý sběr by z ní smazal víc, než by přinesl.
        log.chyba(str(e))
        log.uzavri()
        raise

    vysledek = slouc(stare, nove, log)
    uloz(SOUBOR, vysledek)
    log.info("uloženo", osob=len(vysledek), soubor=SOUBOR)

    podle_kat: dict[str, int] = {}
    for z in vysledek:
        podle_kat[z.get("kategorie") or "?"] = podle_kat.get(z.get("kategorie") or "?", 0) + 1
    log.info("podle kategorií", **podle_kat)
    return log.uzavri()


if __name__ == "__main__":
    vysl = main()
    sys.exit(0 if vysl["uspech"] else 1)
