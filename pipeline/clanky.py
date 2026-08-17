#!/usr/bin/env python3
"""A2 — rozklad PDF Městského zpravodaje na jednotlivé články.

Postup je dvoufázový, jak popisuje docs/PLAN.md:

1. `pdftotext -bbox-layout` dá souřadnice každého slova. Z rozměrů boxu
   se odvodí velikost písma → kandidáti na nadpisy, z xMin příslušnost
   ke sloupci. Velikost se nebere z výšky boxu, ale ze šířky slova na
   jeden znak — viz `_mira_slova()`, kde je vysvětlené proč.
2. Nad geometrií běží heuristika, která z bloků poskládá pořadí čtení
   (rekurzivní XY-řez) a rozseká stránku na články.

Proč vlastní pořadí čtení a ne prostý výstup `pdftotext`: ve starší
sazbě (ročníky 2016–2017) stojí vedle sebe dva nezávislé články se
stejně vysokými nadpisy a poppler je ve výchozím režimu prokládá
po vodorovných pásech — z textu pak vznikne nesmysl. XY-řez najde
nejdřív mezisloupcovou mezeru a čte sloupec po sloupci; naopak tam,
kde nadpis přetéká přes oba sloupce (sazba od 2024), najde nejdřív
vodorovnou mezeru pod nadpisem. Běžný textový výstup `pdf_na_text()`
slouží jako kontrola výtěžnosti a jako záloha pro stránky, ze kterých
geometrie nic nedá.

Rubriky se neberou z pevného seznamu: nasbírají se ze záhlaví stránek
daného čísla ("Dění ve městě", "RADNICE", "INZERCE" …) a stejné popisky
se pak hledají i uprostřed stránky, kde rubrika přechází v jinou.

Inzerce se zahazuje, viz PLAN.md.

Spuštění:
    python3 pipeline/clanky.py                 # celý archiv
    python3 pipeline/clanky.py --cislo 2026-08 # jedno číslo
    python3 pipeline/clanky.py --od 2024       # jen novější ročníky
"""
from __future__ import annotations

import argparse
import re
import statistics
import subprocess
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from selectolax.parser import HTMLParser

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import (  # noqa: E402
    DATA,
    Log,
    ZdrojSelhal,
    cistit,
    nacti,
    platne_tagy,
    slug,
    uloz,
)

PDF_DIR = DATA / "zpravodaj" / "pdf"
TEXT_DIR = DATA / "zpravodaj" / "text"
CLANKY_DIR = DATA / "zpravodaj" / "clanky"
INDEX = "zpravodaj/cisla.json"

# Nadpis pozná pipeline podle toho, že je vysázený nápadně větším písmem
# než běžný text čísla. Naměřeno napříč ročníky: masthead a upoutávky
# z titulky mají 1,3–1,5×, skutečné nadpisy 1,65× až 3,8×.
PRAH_NADPISU = 1.60
MAX_SLOV_NADPISU = 26
MIN_DELKA_CLANKU = 260  # kratší útvary jsou popisky fotek a řádky programu

# XY-řez: mezera menší než tohle se nebere jako hranice.
MIN_MEZERA_X = 8.0
MIN_MEZERA_Y = 6.0


# --------------------------------------------------------------------------
# Geometrie z pdftotext -bbox-layout
# --------------------------------------------------------------------------

@dataclass
class Blok:
    x0: float
    y0: float
    x1: float
    y1: float
    mira: float           # zástupné měřítko velikosti písma, viz _mira_slova()
    text: str
    slov: int
    strana: int
    rubrika: str | None = None
    je_nadpis: bool = False

    @property
    def stred_x(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class Stranka:
    cislo: int
    sirka: float
    vyska: float
    bloky: list[Blok] = field(default_factory=list)      # obsah
    zahlavi: list[Blok] = field(default_factory=list)    # pásmo záhlaví/zápatí


def _mira_slova(w) -> float | None:
    """Velikost písma odhadnutá z šířky slova na jeden znak.

    Nabízí se brát výšku boxu (yMax - yMin), jenže ta závisí na tom, jaký
    FontBBox má písmo zapsaný — v čísle 3/2020 vychází běžný text na 30 pt
    a nadpisy na 28 pt, protože tělo je sázené písmem s obřím deklarovaným
    boxem. Šířka na znak je proti tomu napříč ročníky konzistentní:
    nadpisy vycházejí 1,65× až 3,8× nad běžným textem.

    Krátká slova se vynechávají — u dvou písmen převáží postranní mezery.
    """
    text = (w.text() or "").strip()
    znaku = len(text.replace(" ", ""))
    if znaku < 3:
        return None
    a = w.attributes
    return (float(a["xmax"]) - float(a["xmin"])) / znaku


def _text_bloku(blok_node) -> tuple[str, int, float]:
    """Poskládá text bloku z řádků a spojí slova rozdělená na konci řádku.

    `-bbox-layout` na rozdíl od výchozího režimu dělená slova nespojuje,
    takže "Communi-" + "cations" musíme slepit sami. Spojujeme jen tehdy,
    když další řádek začíná malým písmenem — jinak by utrpěly spojovníky
    ve složeninách typu "stavebně-technického".
    """
    radky: list[str] = []
    miry: list[float] = []
    slov = 0
    for radek in blok_node.css("line"):
        slova = []
        for w in radek.css("word"):
            t = (w.text() or "").strip()
            if not t:
                continue
            slova.append(t)
            m = _mira_slova(w)
            if m:
                miry.append(m)
        if slova:
            radky.append(" ".join(slova))
            slov += len(slova)

    text = ""
    for r in radky:
        if text.endswith("-") and r[:1].islower():
            text = text[:-1] + r
        elif text:
            text += " " + r
        else:
            text = r

    return _cistit_znaky(text), slov, statistics.median(miry) if miry else 0.0


_RIDICI = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _cistit_znaky(t: str) -> str:
    """Vyhodí řídicí znaky, které do PDF občas propadnou (viděno \\x08)."""
    return _RIDICI.sub("", t).replace("�", "").strip()


def nacti_geometrii(pdf: Path) -> list[Stranka]:
    """Načte stránky a bloky z `pdftotext -bbox-layout`.

    Parsuje se selectolaxem, ne XML parserem: výstup popplera občas
    obsahuje řídicí znak uvnitř textu a XML parser na něm spadne.
    """
    r = subprocess.run(
        ["pdftotext", "-bbox-layout", "-enc", "UTF-8", str(pdf), "-"],
        capture_output=True,
        timeout=1800,
    )
    if r.returncode != 0:
        raise ZdrojSelhal(f"pdftotext -bbox-layout selhal na {pdf.name}: {r.stderr.decode()[:200]}")

    dom = HTMLParser(r.stdout.decode("utf-8", errors="replace"))
    stranky: list[Stranka] = []
    for i, pg in enumerate(dom.css("page"), 1):
        st = Stranka(cislo=i, sirka=float(pg.attributes["width"]), vyska=float(pg.attributes["height"]))
        for bl in pg.css("block"):
            slova = bl.css("word")
            if not slova:
                continue
            text, n, mira = _text_bloku(bl)
            if not text or n == 0:
                continue
            xs0 = [float(w.attributes["xmin"]) for w in slova]
            ys0 = [float(w.attributes["ymin"]) for w in slova]
            xs1 = [float(w.attributes["xmax"]) for w in slova]
            ys1 = [float(w.attributes["ymax"]) for w in slova]
            st.bloky.append(Blok(min(xs0), min(ys0), max(xs1), max(ys1), mira, text, n, i))
        stranky.append(st)
    return stranky


def mira_tela(stranky: list[Stranka]) -> float:
    """Medián velikosti písma běžného textu — měřítko pro všechny prahy.

    Počítá se jen z dlouhých bloků, aby měřítko neurčily popisky fotek
    ani nadpisy.
    """
    dlouhe = [b.mira for st in stranky for b in st.bloky if b.slov >= 12 and b.mira > 0]
    if not dlouhe:
        dlouhe = [b.mira for st in stranky for b in st.bloky if b.mira > 0]
    return statistics.median(dlouhe) if dlouhe else 4.5


_CISLO_STRANY = re.compile(r"^(str\.?|strana|page)?\s*\d{1,3}\s*$", re.I)
_TIRAZ = re.compile(r"(zpravodaj|zpravy z marianskych|rocnik|www\.|muml\.cz)")


def roztrid_bloky(stranky: list[Stranka], telo: float) -> None:
    """Oddělí od obsahu tiráž stránky: masthead, rubriku v záhlaví, číslování.

    Pozor na velikost písma: nadpis článku často začíná hned pod záhlavím
    (y ≈ 54 na A4) a podle samotné souřadnice by spadl do tiráže. Rozhoduje
    proto kombinace — v pásmu záhlaví, krátký a buď menším písmem než nadpis,
    nebo rozpoznatelný jako masthead ("ZPRAVODAJ MĚSTA … • BŘEZEN 2020",
    který je vysázený dost velkým písmem, aby prahem prošel).
    """
    for st in stranky:
        obsah, zahlavi = [], []
        for b in st.bloky:
            v_zahlavi = b.y0 < st.vyska * 0.075
            v_zapati = b.y0 > st.vyska * 0.945
            n = _norm(b.text)
            tiraz = bool(_TIRAZ.search(n)) or bool(_MESIC_ROK.match(n))
            if v_zahlavi and b.slov <= 8 and (b.mira < telo * PRAH_NADPISU or tiraz):
                zahlavi.append(b)
            elif (v_zahlavi or v_zapati) and _CISLO_STRANY.match(b.text):
                pass  # číslo strany do článku nepatří
            else:
                obsah.append(b)
        st.bloky, st.zahlavi = obsah, zahlavi


# --------------------------------------------------------------------------
# Pořadí čtení — rekurzivní XY-řez
# --------------------------------------------------------------------------

def _nejvetsi_mezera(intervaly: list[tuple[float, float]]) -> tuple[float, float]:
    """Najde největší prázdné místo v projekci intervalů na osu.

    Vrací (šířka mezery, souřadnice řezu).
    """
    if len(intervaly) < 2:
        return 0.0, 0.0
    setrideno = sorted(intervaly)
    konec = setrideno[0][1]
    nej, kde = 0.0, 0.0
    for zac, kon in setrideno[1:]:
        if zac - konec > nej:
            nej, kde = zac - konec, (zac + konec) / 2
        konec = max(konec, kon)
    return nej, kde


def poradi_cteni(bloky: list[Blok], hloubka: int = 0) -> list[Blok]:
    """Seřadí bloky do pořadí čtení rekurzivním XY-řezem.

    V každém kroku se hledá největší souvislá mezera vodorovně i svisle
    a řeže se tou širší: svislá mezera (mezisloupcová) dá pořadí
    "nejdřív levý sloupec, pak pravý", vodorovná dá "nejdřív horní pás".

    Mezery se měří JEN na běžných blocích, nadpisy se z měření vynechávají.
    Nadpis totiž zabírá několik sloupců naráz, takže přes něj mezisloupcová
    mezera nevede — a když se počítá s ním, čtyřsloupcová sazba ročníků
    2018–2021 se rozsype a text článku začne uprostřed věty. Nadpis se
    pak do poloviny zařadí tam, kam patří čtenářsky: při svislém řezu
    podle levého okraje (patří k prvnímu sloupci, který zahajuje),
    při vodorovném podle spodního okraje (patří k textu POD sebou).
    """
    if len(bloky) <= 1 or hloubka > 20:
        return sorted(bloky, key=lambda b: (b.y0, b.x0))

    bezne = [b for b in bloky if not b.je_nadpis] or bloky
    mx, rez_x = _nejvetsi_mezera([(b.x0, b.x1) for b in bezne])
    my, rez_y = _nejvetsi_mezera([(b.y0, b.y1) for b in bezne])

    def svisle() -> list[Blok] | None:
        levy = [b for b in bloky if b.x0 < rez_x]
        pravy = [b for b in bloky if b.x0 >= rez_x]
        if not levy or not pravy:
            return None
        return poradi_cteni(levy, hloubka + 1) + poradi_cteni(pravy, hloubka + 1)

    def vodorovne() -> list[Blok] | None:
        horni = [b for b in bezne if b.y1 <= rez_y]
        dolni = [b for b in bezne if b.y1 > rez_y]
        if not horni or not dolni:
            return None
        # Nadpis patří k textu, který pod ním následuje. Bere se nejbližší
        # běžný blok pod nadpisem se společným rozsahem x — nadpis totiž
        # bývá oddělený od svého článku fotkou přes půl stránky a podle
        # vlastní souřadnice by skončil u článku nad sebou.
        for h in (b for b in bloky if b.je_nadpis):
            pod = [b for b in bezne if b.y0 >= h.y1 - 4 and b.x0 < h.x1 and h.x0 < b.x1]
            nasleduje = min(pod, key=lambda b: b.y0) if pod else None
            v_hornim = nasleduje.y1 <= rez_y if nasleduje is not None else h.y1 <= rez_y
            (horni if v_hornim else dolni).append(h)
        return poradi_cteni(horni, hloubka + 1) + poradi_cteni(dolni, hloubka + 1)

    if mx >= MIN_MEZERA_X and mx >= my:
        out = svisle()
        if out:
            return out
    if my >= MIN_MEZERA_Y:
        out = vodorovne()
        if out:
            return out
    if mx >= MIN_MEZERA_X:
        out = svisle()
        if out:
            return out

    return sorted(bloky, key=lambda b: (b.y0, b.x0))


# --------------------------------------------------------------------------
# Rubriky
# --------------------------------------------------------------------------

# Popisky, které se v záhlaví tváří jako rubrika, ale nejsou jí.
_NENI_RUBRIKA = re.compile(
    r"(zpravodaj|marianske lazne|rocnik|www|muml|^str\b|^strana\b|^\d+$)",
)

_MESICE_TVARY = (
    "leden|ledna|unor|unora|brezen|brezna|duben|dubna|kveten|kvetna|cerven|cervna|"
    "cervenec|cervence|srpen|srpna|zari|rijen|rijna|listopad|listopadu|prosinec|prosince"
)
_MESIC_ROK = re.compile(rf"^({_MESICE_TVARY})\s*\d{{4}}$")

# Rubriky, které přežily napříč ročníky — slouží jako semínko pro čísla,
# kde se v záhlaví žádný popisek neopakuje.
SEMINKO_RUBRIK = {
    "inzerce", "radnice", "obcane", "kultura", "skola", "skoly", "sport",
    "policie", "historie", "rozhovor", "deni ve meste", "prevence", "lazenstvi",
}

# Rubrika, pod kterou článek do archivu nepatří. Kromě holého "INZERCE"
# sem spadne i "Ceník placené inzerce" a podobné popisky reklamních stran.
ZAHOZENA_RUBRIKA = re.compile(r"inzer(ce|at|ci|tni)")


def _norm(t: str) -> str:
    """Malá písmena bez diakritiky a bez interpunkce, mezery sjednocené."""
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _je_kandidat_rubriky(b: Blok) -> bool:
    if b.slov > 5 or len(b.text) > 42 or len(b.text) < 3:
        return False
    n = _norm(b.text)
    if not n or _NENI_RUBRIKA.search(n) or _MESIC_ROK.match(n):
        return False
    return bool(re.search(r"[a-z]", n))


def _je_verzalkami(text: str) -> bool:
    pismena = [c for c in text if c.isalpha()]
    if len(pismena) < 4:
        return False
    return sum(1 for c in pismena if c.isupper()) / len(pismena) > 0.85


def slovnik_rubrik(stranky: list[Stranka], telo: float) -> set[str]:
    """Rubriky daného čísla: krátké popisky ze záhlaví stránek.

    Bere se výhradně pásmo záhlaví — v zápatí sedí podpis autora článku
    ("Václava Simeonová") a ten by se jinak proměnil v rubriku a smazal
    by z článků každý svůj výskyt.

    Ročníky 2016–2017 rubriku v záhlaví nemají vůbec, zato mají uprostřed
    sazby mezititulky verzálkami ("ZPRÁVY Z RADNICE"). Poznají se podle
    toho, že v takovém čísle jsou nadpisy jinak psané normálně — a že se
    stejný popisek opakuje. Když je verzálkami většina nadpisů (sazba 2017–2023),
    tohle pravidlo se neuplatní, protože by sežralo skutečné nadpisy.
    """
    slovnik = {
        _norm(b.text)
        for st in stranky
        for b in st.zahlavi
        if _je_kandidat_rubriky(b)
    }
    slovnik.discard("")

    kandidati = [b for st in stranky for b in st.bloky if _je_nadpis(b, telo)]
    verzalkami = [b for b in kandidati if _je_verzalkami(b.text)]
    if kandidati and len(verzalkami) / len(kandidati) < 0.45:
        pocty: dict[str, int] = {}
        for b in verzalkami:
            if _je_kandidat_rubriky(b):
                pocty[_norm(b.text)] = pocty.get(_norm(b.text), 0) + 1
        slovnik |= {n for n, c in pocty.items() if c >= 2}

    return slovnik


def _uprav_rubriku(t: str) -> str:
    """'OBČANÉ' -> 'Občané', 'kultura' -> 'Kultura', 'Dění ve městě' zůstane.

    Sjednocení velikosti písmen je nutné: stejná rubrika je v archivu
    sázená verzálkami, minuskami i smíšeně a bez tohohle by se na webu
    rozpadla do tří různých filtrů.
    """
    t = re.sub(r"\s+", " ", (t or "").strip(" .:-•"))
    if t.isupper():
        t = t.capitalize()
    return t[:1].upper() + t[1:] if t else t


def priraz_rubriky(stranky: list[Stranka], slovnik: set[str]) -> None:
    """Doplní každému bloku rubriku a vyhodí bloky, které rubriku jen ohlašují.

    Rubrika se hledá ve třech krocích: popisek uvnitř stránky (platí pro
    vše pod ním), popisek v záhlaví nejblíž vodorovně (stránka bývá
    rozdělená napůl na dvě rubriky) a nakonec doběh z předchozí stránky.
    """
    predchozi: str | None = None
    for st in stranky:
        zahlavi_rubriky = [b for b in st.zahlavi if _norm(b.text) in slovnik]
        znacky = [b for b in st.bloky if _je_kandidat_rubriky(b) and _norm(b.text) in slovnik]
        st.bloky = [b for b in st.bloky if b not in znacky]

        for b in st.bloky:
            aktualni: str | None = None
            nad_blokem = [z for z in znacky if z.y0 <= b.y0 + 4 and z.stred_x - 140 <= b.stred_x <= z.stred_x + 140]
            if nad_blokem:
                aktualni = max(nad_blokem, key=lambda z: z.y0).text
            elif zahlavi_rubriky:
                aktualni = min(zahlavi_rubriky, key=lambda z: abs(z.stred_x - b.stred_x)).text
            elif predchozi:
                aktualni = predchozi
            b.rubrika = _uprav_rubriku(aktualni) if aktualni else None

        posledni = [b.rubrika for b in st.bloky if b.rubrika]
        if posledni:
            predchozi = posledni[-1]
        elif zahlavi_rubriky:
            predchozi = _uprav_rubriku(zahlavi_rubriky[-1].text)


# --------------------------------------------------------------------------
# Osoby
# --------------------------------------------------------------------------

MUZSKA_JMENA = {
    "adam", "ales", "alexandr", "alois", "andrej", "antonin", "arnost", "bedrich",
    "bohumil", "bohuslav", "boris", "bretislav", "cyril", "ctirad", "dalibor",
    "daniel", "david", "denis", "dominik", "dusan", "eduard", "emil", "erik",
    "evzen", "filip", "frantisek", "gustav", "hynek", "igor", "ivan", "ivo",
    "jachym", "jakub", "jan", "jaromir", "jaroslav", "jindrich", "jiri", "jonas",
    "josef", "jozef", "julius", "kamil", "karel", "kristian", "ladislav", "leos",
    "libor", "lubomir", "ludek", "ludvik", "lukas", "marcel", "marek", "marian",
    "martin", "matej", "matous", "matyas", "michal", "milan", "milos", "miloslav",
    "miroslav", "mojmir", "norbert", "oldrich", "ondrej", "otakar", "oto", "otto",
    "patrik", "pavel", "petr", "premysl", "prokop", "radek", "radim", "radovan",
    "rene", "richard", "robert", "roman", "rostislav", "rudolf", "samuel",
    "sebastian", "silvestr", "simon", "slavomir", "stanislav", "stepan", "svatopluk",
    "sarl", "tadeas", "tibor", "tomas", "vaclav", "valentin", "vilem", "viktor",
    "vit", "vitezslav", "vladimir", "vladislav", "vlastimil", "vojtech", "vratislav",
    "zbynek", "zdenek", "alexander", "hubert", "kryspin", "maxmilian", "leopold",
    "ferdinand", "gabriel", "gregor", "herman", "hugo", "jerome", "johann", "joachim",
}

ZENSKA_JMENA = {
    "adela", "alena", "alexandra", "alzbeta", "andrea", "aneta", "anezka", "anna",
    "barbora", "blanka", "blazena", "bohumila", "bozena", "brigita", "dagmar",
    "dana", "daniela", "danuse", "denisa", "dominika", "drahomira", "edita", "ela",
    "eliska", "ema", "emilie", "eva", "gabriela", "hana", "hedvika", "helena",
    "ida", "irena", "irma", "iva", "ivana", "iveta", "ivona", "jana", "jarmila",
    "jaroslava", "jindriska", "jitka", "jolana", "julie", "kamila", "karolina",
    "katerina", "klara", "kristina", "kristyna", "lada", "lenka", "libuse", "lucie",
    "ludmila", "magdalena", "marcela", "marie", "marketa", "marta", "martina",
    "michaela", "milada", "milena", "miloslava", "miluse", "miroslava", "monika",
    "nadezda", "natalie", "nela", "nikola", "olga", "otylie", "pavla", "pavlina",
    "petra", "radka", "renata", "romana", "ruzena", "sabina", "sarka", "silvie",
    "simona", "sona", "stanislava", "stepanka", "svatava", "svetlana", "sylva",
    "tereza", "vaclava", "vendula", "vera", "veronika", "viktorie", "vlasta",
    "yveta", "zdenka", "zuzana", "zaneta", "lubica", "miluska", "nikol", "elena",
}

# Slova, která za křestním jménem vypadají jako příjmení, ale nejsou.
NENI_PRIJMENI = {
    "lazne", "lazni", "laznich", "lazen", "laznim", "lazenske", "lazenska",
    "kraj", "kraje", "kraji", "krajem", "mesto", "mesta", "meste", "mestu",
    "namesti", "ulice", "ulici", "hotel", "hotelu", "park", "parku", "les",
    "lesa", "pramen", "pramene", "divadlo", "divadla", "muzeum", "muzea",
    "kostel", "kostela", "skola", "skoly", "sport", "klub", "klubu", "cechy",
    "cech", "praha", "prahy", "praze", "brno", "brna", "plzen", "plzne",
    "cheb", "chebu", "kladska", "kladske", "unesco", "evropa", "evropy",
    "vary", "varech", "republika", "republiky", "republice", "sever", "jih",
    "kolonada", "kolonady", "naucna", "naucne", "pramen", "prameny", "cesta",
    "cesty", "sady", "sadu", "hory", "hora", "les", "lesy", "rok", "roku",
    "kraje", "spolek", "spolku", "cirkev", "vila", "vily", "galerie", "kino",
    "gymnazium", "univerzita", "univerzity", "fakulta", "fakulty", "nemocnice",
}

_JMENO_RE = re.compile(
    r"(?<![\wÀ-ž])"
    r"(?:(?:Ing|Mgr|MgA|Bc|BcA|MUDr|MVDr|PhDr|JUDr|RNDr|PaedDr|ThDr|doc|prof|plk|pplk|npor|kpt|por)\.\s*)*"
    r"([A-ZÁ-Ža-zá-ž]?[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-zá-žčďěňřšťůýž]{2,})"
    r"\s+"
    r"([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-zá-žčďěňřšťůýž]{2,}(?:\s+[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-zá-žčďěňřšťůýž]{2,})?)"
    r"(?![\wÀ-ž])"
)

# Pádové koncovky křestních jmen -> jak se z nich dostat k 1. pádu.
_PADY_MUZ = [("", ""), ("ovi", ""), ("em", ""), ("a", ""), ("e", ""), ("u", "")]
_PADY_ZENA = [("", ""), ("y", "a"), ("e", "a"), ("ě", "a"), ("u", "a"), ("ou", "a")]


_PRECHYLENE = ("ová", "ové", "ovou", "ovu", "ovy")


def _rozpoznej(jmeno_raw: str, prijmeni_raw: str) -> tuple[str, str] | None:
    """Dvojici slov převede na (jméno, příjmení) v 1. pádě, nebo vrátí None.

    Rod se určuje nejdřív podle příjmení: přechýlené "-ová" je jistota,
    zatímco křestní jméno samo o sobě klame — "Miroslava" je jednak ženské
    jméno, jednak 2. pád Miroslava a "Martina" totéž. Bez téhle přednosti
    by ze "Miroslava Trýzny" vyšla neexistující "Miroslava Trýzny".
    """
    n_jmeno = _norm(jmeno_raw)
    n_prijmeni = _norm(prijmeni_raw)
    if n_prijmeni in NENI_PRIJMENI or len(prijmeni_raw) < 3:
        return None
    # Příjmení, které je samo křestním jménem, bývá ve skutečnosti dvojice
    # jmen z výčtu ("Josef, Jan a Marie") — raději zahodit.
    if n_prijmeni in MUZSKA_JMENA or n_prijmeni in ZENSKA_JMENA:
        return None

    prechylene = prijmeni_raw.endswith(_PRECHYLENE)

    if prechylene:
        jmeno = _do_nominativu(jmeno_raw, ZENSKA_JMENA, _PADY_ZENA)
        if not jmeno:
            return None
        prijmeni = prijmeni_raw
        for konc in ("ové", "ovou", "ovu", "ovy"):
            if prijmeni.endswith(konc):
                prijmeni = prijmeni[: -len(konc)] + "ová"
                break
        return jmeno, prijmeni

    # Nepřechýlené příjmení: zkusíme mužský výklad, pak ženský.
    if n_jmeno in MUZSKA_JMENA:
        return jmeno_raw, prijmeni_raw
    for konc, nahrada in _PADY_MUZ[1:]:
        if n_jmeno.endswith(konc) and (n_jmeno[: -len(konc)] + nahrada) in MUZSKA_JMENA:
            jmeno = jmeno_raw[: len(jmeno_raw) - len(konc)] + nahrada
            return jmeno, _odsklonuj_muzske(prijmeni_raw)
    if n_jmeno in ZENSKA_JMENA:
        return jmeno_raw, prijmeni_raw
    return None


def _do_nominativu(slovo: str, slovnik: set[str], pady: list[tuple[str, str]]) -> str | None:
    n = _norm(slovo)
    if n in slovnik:
        return slovo
    for konc, nahrada in pady[1:]:
        if n.endswith(konc) and (n[: -len(konc)] + nahrada) in slovnik:
            return slovo[: len(slovo) - len(konc)] + nahrada
    return None


def _odsklonuj_muzske(p: str) -> str:
    """'Bischofa' -> 'Bischof', 'Trýzny' -> 'Trýzna', 'Petrusovi' -> 'Petrus'."""
    for konc in ("ovi", "em"):
        if p.endswith(konc) and len(p) - len(konc) >= 3:
            return p[: -len(konc)]
    if p.endswith("y") and len(p) > 3:
        return p[:-1] + "a"
    for konc in ("a", "e", "u"):
        if p.endswith(konc) and len(p) > 4:
            return p[:-1]
    return p


def najdi_osoby(text: str, limit: int = 12) -> list[str]:
    """Vytáhne z textu jména osob jako slug 'prijmeni-jmeno'.

    Kotva je křestní jméno ze slovníku — bez ní by regulární výraz nabral
    každé "Mariánské Lázně". Skloňované tvary se vracejí do 1. pádu,
    aby ze "Zuzany Stejskalové" a "Zuzana Stejskalová" vyšel jeden slug.
    Nejde o dokonalý rozbor češtiny, ale o použitelný rejstřík jmen.
    """
    nalezene: dict[str, int] = {}
    for m in _JMENO_RE.finditer(text or ""):
        # U dvouslovného příjmení bereme poslední slovo.
        dvojice = _rozpoznej(m.group(1), m.group(2).split()[-1])
        if not dvojice:
            continue
        jmeno, prijmeni = dvojice
        s = f"{slug(prijmeni)}-{slug(jmeno)}"
        if len(s) < 7 or s.count("-") != 1:
            continue
        nalezene[s] = nalezene.get(s, 0) + 1
    return [s for s, _ in sorted(nalezene.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]


# --------------------------------------------------------------------------
# Tagy — výhradně z číselníku config/tagy.json
# --------------------------------------------------------------------------

# Klíčová slova jsou KMENY bez diakritiky — vyhledávají se s libovolnou
# koncovkou ("strazn" chytí strážník i strážníci), ale na hranici slova,
# aby "les" nechytal "leštění". Víceslovné výrazy váží víc, protože jsou
# specifičtější.
KLICOVA_SLOVA: dict[str, list[str]] = {
    "majetek-prodej": ["prodej pozemk", "prodeji pozemk", "prodej nemovitost", "prodej byt", "odprodej", "kupni smlouv", "zamer prodat", "drazb", "prodalo pozemek"],
    "majetek-nakup": ["vykup pozemk", "koupe pozemk", "nabyti nemovitost", "mesto koupilo", "odkoupilo", "odkup"],
    "majetek-pronajem": ["pronaj", "najemni smlouv", "pacht", "vypujck", "vecne bremen", "propachtov"],
    "bydleni": ["mestsk byt", "mestske byt", "bytov fond", "prideleni byt", "najemne", "startovaci byt", "ubytovn", "bytov dum", "bytovka", "socialni bydlen"],
    "rozpocet": ["rozpoct", "rozpocet", "zaverecn ucet", "hospodareni mest", "audit hospodaren", "prijmy mesta", "vydaje mesta", "financni plan"],
    "dotace-poskytnute": ["dotacni program", "fond kultur", "fond sport", "prispevek spolk", "dotace spolk", "grantov", "poskytlo dotaci", "poskytnuti dotace", "prispevky organizac"],
    "dotace-prijate": ["ziskalo dotaci", "ziskaly dotaci", "ziskalo prispevek", "dotace od kraj", "operacni program", "evropsk dotac", "dotacni titul", "narodni plan obnovy", "dotaci na", "podporeno z fondu"],
    "verejna-zakazka": ["verejn zakazk", "vyberov rizeni", "vysoutez", "zadavaci rizeni", "nabidkova cena", "zadavaci dokumentac", "vitez souteze"],
    "smlouvy": ["smlouva o dilo", "memorandum", "dodatek smlouv", "uzavreni smlouv", "smlouv o spolupraci", "darovaci smlouv", "podepsali smlouv"],
    "investice": ["rekonstrukc", "vystavb", "investicni ak", "stavebni prac", "oprava komunikac", "modernizac", "revitalizac", "prestavb", "zahajeni stavb", "stavebni firm", "novostavb", "opravy budov"],
    "uzemni-plan": ["uzemni plan", "uzemniho planu", "regulacni plan", "uzemni studi", "zastavovaci studi", "uzemni rizeni", "uzemniho rizeni"],
    "pamatky": ["pamatk", "pamatkov", "vila lil", "obnova historick", "kulturni dedictv", "historick objekt", "chraneny objekt"],
    "unesco": ["unesco", "svetov dedictv", "slavne lazne evropy", "great spa towns", "site manaz"],
    "lazenstvi": ["lazensk", "lazenstv", "mineralni pramen", "kolonad", "zridl", "pitna kura", "balneo", "lecebne lazn", "lazenska lecb", "prameny"],
    "cestovni-ruch": ["cestovni ruch", "cestovniho ruchu", "infocentrum", "turistick", "navstevnost mest", "propagace mest", "turist", "destinacn"],
    "doprava": ["doprav", "silnic", "mhd", "autobus", "uzavirk", "chodnik", "krizovatk", "cyklostezk", "zeleznic", "objizdk", "dopravni znacen"],
    "parkovani": ["parkovan", "parkovist", "parkovaci zon", "parkovaci kart", "rezidentni kart", "parkovaci automat", "zaparkov"],
    "zivotni-prostredi": ["zivotni prostred", "ovzdus", "znecisten", "ochrana prirod", "vodni zdroj", "povodn", "ekologick", "emis", "klimatick"],
    "zelen": ["zelen", "kacen", "vysadb", "stromy", "stromu", "lesy", "lesni hospodarstv", "pamatny strom", "travnik", "zahon", "lesnik"],
    "odpady": ["odpad", "trideni odpad", "svoz", "kontejner", "sberny dvur", "popelnic", "bioodpad", "skladk"],
    "energetika": ["teplarn", "vytapen", "fotovoltaik", "uspory energi", "tepelne hospodarstv", "cena tepla", "energetick", "kotelna"],
    "skolstvi": ["skol", "materska skol", "zakladni skol", "gymnazium", "zus", "zaci", "zaku", "student", "ucitel", "dum deti a mladez", "skolni rok", "univerzit", "fakult", "vzdelavan", "druzin"],
    "socialni": ["socialni sluzb", "domov pro senior", "pecovatelsk", "senior", "azylov", "socialni odbor", "handicap", "charit", "socialne slab", "krizova pomoc"],
    "zdravotnictvi": ["nemocnic", "lekar", "zdravotn", "ordinac", "zubn", "zachrann sluzb", "pohotovost", "ockovan", "covid", "lekarn", "pacient"],
    "kultura": ["divadl", "koncert", "vystav", "muzeum", "muzea", "knihovn", "orchestr", "festival", "kulturni ak", "galeri", "kino", "hudebn", "vernisaz", "chopin", "vernisaz", "spisovatel", "vystoup"],
    "sport": ["sport", "fotbal", "hokej", "turnaj", "zavod", "stadion", "tenis", "plaveck", "bazen", "atletik", "golf", "mistrovstv", "medail", "trenink", "trener", "zavodnic"],
    "bezpecnost": ["mestska polic", "strazn", "policist", "policie cr", "hasic", "krizov rizeni", "prevence kriminalit", "bezpecnostni situac", "kamerov system", "integrovan zachrann", "prestupk"],
    "personalni": ["jmenovan", "odvolan", "konkurz", "odmen", "novym reditel", "novy reditel", "tajemnik urad", "nastoupil do funkce", "ve funkci", "novy vedouc"],
    "organizacni": ["organizacni rad", "vnitrni predpis", "uredni hodin", "odbor mestskeho urad", "matrik", "obcansk prukaz", "czech point", "mestsky urad", "radnic"],
    "komise-vybory": ["komise rady", "vybor zastupitelstv", "financni vybor", "kontrolni vybor", "clenove komise", "zrizeni komise", "osadni vybor", "komise mesta"],
    "mestske-firmy": ["spolecnost mesta", "mestska spolecnost", "valna hromad", "dozorci rad", "jednatel", "prispevkova organizac", "technicke sluzb", "spolecnosti mesta"],
    "vyhlasky": ["obecne zavazn vyhlask", "narizeni mest", "vyhlaska mest", "trzni rad", "mistni poplat"],
    "ruzne": [],
}


_VZORY: dict[str, list[re.Pattern]] = {
    tag: [re.compile(rf"(?<![a-z0-9]){re.escape(kw)}[a-z]*(?![a-z])") for kw in slova]
    for tag, slova in KLICOVA_SLOVA.items()
}

MIN_SKORE_TAGU = 4


def vyber_tagy(text: str, nadpis: str = "", rubrika: str | None = None, max_tagu: int = 3) -> list[str]:
    """Vybere 1–3 tagy z číselníku `config/tagy.json`. Nikdy nevymýšlí nové.

    Klíčová slova se hledají na hranici slova s povolenou koncovkou — jinak
    by "park" chytal každé "parkoviště" a "les" každé "leštění".
    Když nic nedosáhne prahu, článek dostane jediný tag `ruzne`; radši
    přiznaná neurčitost než vymyšlené zařazení.
    """
    povolene = platne_tagy()
    # Nadpis váží dvojnásob — bývá o tématu vypovídavější než tělo článku.
    n_text = _norm(f"{nadpis} {nadpis} {rubrika or ''} {text}")
    skore: dict[str, int] = {}
    for tag, vzory in _VZORY.items():
        if tag not in povolene:
            continue
        for vzor in vzory:
            pocet = len(vzor.findall(n_text))
            if pocet:
                # víceslovné (specifičtější) klíčové slovo váží víc
                skore[tag] = skore.get(tag, 0) + pocet * (3 if " " in vzor.pattern else 1)

    poradi = sorted(skore.items(), key=lambda kv: (-kv[1], kv[0]))
    vybrane = [t for t, s in poradi if s >= MIN_SKORE_TAGU][:max_tagu]
    if not vybrane and poradi and poradi[0][1] >= 2:
        vybrane = [poradi[0][0]]
    if not vybrane:
        vybrane = ["ruzne"]
    return [t for t in vybrane if t in povolene]


# --------------------------------------------------------------------------
# Skládání článků
# --------------------------------------------------------------------------

_SAMOHLASKY = set("aeiouyáéěíóúůýAEIOUYÁÉĚÍÓÚŮÝ")


def je_smeti(text: str) -> bool:
    """Pozná text z fontu bez použitelného mapování na Unicode.

    Inzerátní bloky občas vyjdou jako "4VSREģI^EQÝWXRERGIZŀH]" — jsou to
    písmena, ale nedávají smysl. Poznáme je podle slov bez samohlásek.
    """
    slova = [s for s in re.findall(r"\S+", text) if len(s) >= 4]
    if len(slova) < 5:
        return False
    bez = sum(1 for s in slova if not (_SAMOHLASKY & set(s)))
    return bez / len(slova) > 0.25


def _je_nadpis(b: Blok, telo: float) -> bool:
    """Nadpis = nápadně větší písmo v krátkém bloku."""
    if b.slov > MAX_SLOV_NADPISU or not (8 <= len(b.text) <= 190):
        return False
    return b.mira >= telo * PRAH_NADPISU


def _perex(text: str, prvni_blok: str | None, maximum: int = 420) -> str:
    if prvni_blok and 60 <= len(prvni_blok) <= 900:
        return prvni_blok.strip()
    vety = re.split(r"(?<=[.!?…])\s+", text.strip())
    out = ""
    for v in vety:
        if out and len(out) + len(v) > maximum:
            break
        out = (out + " " + v).strip()
        if len(out) >= 160:
            break
    return out[:900]


def _spoj(casti: list[str]) -> str:
    """Slepí bloky do souvislého textu; hlídá slova dělená přes sloupec."""
    out = ""
    for c in casti:
        c = c.strip()
        if not c:
            continue
        if out.endswith("-") and c[:1].islower():
            out = out[:-1] + c
        elif out:
            out += "\n\n" + c
        else:
            out = c
    return cistit(out)


def clanky_z_cisla(zaznam: dict, log: Log) -> list[dict]:
    """Rozebere jedno číslo na články. Vrací seznam ve formátu z PLAN.md."""
    pdf = PDF_DIR / f"{zaznam['id']}.pdf"
    if not pdf.exists():
        raise ZdrojSelhal(f"chybí PDF {pdf}")

    stranky = nacti_geometrii(pdf)
    if not stranky:
        raise ZdrojSelhal(f"{zaznam['id']}: pdftotext nevrátil ani jednu stránku")

    telo = mira_tela(stranky)
    roztrid_bloky(stranky, telo)
    for st in stranky:
        for b in st.bloky:
            b.je_nadpis = _je_nadpis(b, telo)
    slovnik = slovnik_rubrik(stranky, telo)
    priraz_rubriky(stranky, slovnik)

    # ------ průchod celým číslem v pořadí čtení ------
    clanky: list[dict] = []
    akt: dict | None = None

    for st in stranky:
        serazene = poradi_cteni(st.bloky)
        for b in serazene:
            if b.je_nadpis:
                akt = {
                    "strana": b.strana,
                    "rubrika": b.rubrika,
                    "nadpis": re.sub(r"\s+", " ", b.text).strip(" .:-–"),
                    "casti": [],
                    "miry": [],
                }
                clanky.append(akt)
            elif akt is not None:
                # Pokračování přes stránku beze změny rubriky bereme jako totéž.
                akt["casti"].append(b.text)
                akt["miry"].append(b.mira)
                if akt["rubrika"] is None and b.rubrika:
                    akt["rubrika"] = b.rubrika

    # ------ dočištění a převod do výstupního formátu ------
    hotove: list[dict] = []
    poradi = 0
    for c in clanky:
        if not c["nadpis"] or not c["casti"]:
            continue
        if ZAHOZENA_RUBRIKA.search(_norm(c["rubrika"] or "")):
            continue

        text = _spoj(c["casti"])
        if len(text) < MIN_DELKA_CLANKU or je_smeti(text) or je_smeti(c["nadpis"]):
            continue

        # Perex: první blok, když je vysázený větším písmem než tělo (lead),
        # jinak úvodní věty článku.
        prvni = c["casti"][0].strip() if c["casti"] else ""
        je_lead = bool(c["miry"]) and c["miry"][0] >= telo * 1.10
        perex = _perex(text, prvni if je_lead else None)

        poradi += 1
        hotove.append({
            "id": f"{zaznam['id']}-{poradi:03d}",
            "cislo": zaznam["id"],
            "strana": c["strana"],
            "rubrika": c["rubrika"],
            "nadpis": c["nadpis"],
            "perex": perex,
            "text": text,
            "osoby": najdi_osoby(f"{c['nadpis']}\n{text}"),
            "tagy": vyber_tagy(text, c["nadpis"], c["rubrika"]),
            "pdf_odkaz": f"{zaznam['url']}#page={c['strana']}",
        })

    return hotove


def uloz_clanky(cislo: str, clanky: list[dict]) -> int:
    adresar = CLANKY_DIR / cislo
    if adresar.exists():
        for stary in adresar.glob("*.json"):
            stary.unlink()
    for i, c in enumerate(clanky, 1):
        uloz(f"zpravodaj/clanky/{cislo}/{i:03d}.json", c)
    return len(clanky)


# --------------------------------------------------------------------------
# Hlavní běh
# --------------------------------------------------------------------------

def hlavni(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Rozebere zpravodaj na články")
    ap.add_argument("--cislo", action="append", help="jen konkrétní číslo, např. 2026-08")
    ap.add_argument("--od", type=int, default=0, help="jen ročníky >= tomuto roku")
    ap.add_argument("--do", type=int, default=0, help="jen ročníky <= tomuto roku")
    ap.add_argument("--limit", type=int, default=0, help="jen N čísel")
    ap.add_argument("--prepsat", action="store_true", help="přepsat i už rozebraná čísla")
    args = ap.parse_args(argv)

    log = Log("clanky")
    index = nacti(INDEX)
    if not index:
        log.chyba("chybí data/zpravodaj/cisla.json — spusť nejdřív scrapers/zpravodaj.py")
        log.uzavri()
        return 1

    vyber = [z for z in index if not z.get("ocr")]
    if args.cislo:
        vyber = [z for z in vyber if z["id"] in set(args.cislo)]
    if args.od:
        vyber = [z for z in vyber if z["rok"] >= args.od]
    if args.do:
        vyber = [z for z in vyber if z["rok"] <= args.do]
    vyber.sort(key=lambda z: z["id"], reverse=True)
    if args.limit:
        vyber = vyber[: args.limit]

    celkem = 0
    zpracovano = 0
    for i, z in enumerate(vyber, 1):
        adresar = CLANKY_DIR / z["id"]
        if adresar.exists() and any(adresar.glob("*.json")) and not args.prepsat:
            celkem += len(list(adresar.glob("*.json")))
            zpracovano += 1
            continue
        if not (PDF_DIR / f"{z['id']}.pdf").exists():
            log.chyba(f"{z['id']}: PDF není stažené, přeskakuji")
            continue
        try:
            clanky = clanky_z_cisla(z, log)
        except Exception as e:  # noqa: BLE001 — jedno rozbité číslo nesmí zabít dávku
            log.chyba(f"{z['id']}: rozklad selhal ({type(e).__name__}: {e})")
            continue
        if not clanky:
            log.chyba(f"{z['id']}: nevznikl ani jeden článek")
            continue
        n = uloz_clanky(z["id"], clanky)
        celkem += n
        zpracovano += 1
        log.pricti(n)
        prum = sum(len(c["text"]) for c in clanky) // max(n, 1)
        log.info(f"[{i}/{len(vyber)}] {z['id']}: {n} článků, průměr {prum} znaků")

    log.info(f"hotovo: {zpracovano}/{len(vyber)} čísel, {celkem} článků")
    log.uzavri()
    return 0


if __name__ == "__main__":
    raise SystemExit(hlavni())
