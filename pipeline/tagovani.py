"""Tagování bodů usnesení podle pevného číselníku `config/tagy.json`.

ZÁSADA: tagy se VYBÍRAJÍ z číselníku, nikdy nevymýšlejí. Kdyby si každý běh
vymyslel vlastní názvy, filtrování na webu by přestalo dávat smysl.

Proto je tenhle modul čistě deterministický — žádný jazykový model, jen
klíčová slova a váhy. Stejný vstup dá vždy stejný výstup a rozdíly mezi
běhy jdou vysvětlit změnou pravidel, ne náladou modelu.

Použití:
  * `navrhni_tagy(nazev, text)` volá sběrač usnesení při zápisu,
  * `main()` přetáguje už uložený archiv a propíše tagy na hlasování.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import core  # noqa: E402

# Kolik tagů nejvýš na jeden bod. PLAN.md říká 1–3.
MAX_TAGU = 3

# Minimální skóre, aby se tag vůbec uvažoval. Pod ním je shoda tak slabá,
# že je poctivější přiznat "ruzne" než tvrdit téma, které tam není.
PRAH = 3


# --------------------------------------------------------------------------
# Pravidla
# --------------------------------------------------------------------------
# Klíč je `id` tagu z config/tagy.json — na startu se to kontroluje.
# Hodnota je seznam (regulární výraz nad textem BEZ diakritiky, váha).
#
# Váhy: 5 = jednoznačný marker tématu, 3 = silná indicie, 1 = slabá.
# Shoda v názvu bodu se počítá trojnásobně — název je psaný úředníkem jako
# shrnutí a je mnohem popisnější než tělo usnesení plné právních formulí.
PRAVIDLA: dict[str, list[tuple[str, int]]] = {
    "majetek-prodej": [
        (r"\bprodej", 5), (r"\bodprodej", 5), (r"\bprodat\b", 5),
        (r"zamer\s+prodeje", 5), (r"\bprodeji\b", 4),
        (r"kupni\s+smlouv", 3), (r"\bprodava", 3),
    ],
    "majetek-nakup": [
        (r"\bnakup", 4), (r"\bkoupe\b", 4), (r"\bodkup", 4), (r"\bvykup", 4),
        (r"nabyti\s+(nemovit|pozemk|majetk)", 5),
        (r"bezuplatn\w*\s+prevod", 4), (r"\bprevod\w*\s+do\s+vlastnictvi\s+mesta", 5),
        (r"prijeti\s+daru\s+(nemovit|pozemk)", 5), (r"darovaci\s+smlouv", 3),
    ],
    "majetek-pronajem": [
        (r"\bpronajem", 5), (r"\bpronajm", 5), (r"\bnajemni\s+smlouv", 5),
        (r"\bnajmu\b", 4), (r"\bpodnajem", 4), (r"\bpodnajm", 4),
        (r"\bpacht", 5), (r"\bvypujc", 4),
        (r"sluzebnost", 5), (r"vecn\w*\s+bremen", 5), (r"vecneho\s+prava", 4),
        (r"\bnebytov\w*\s+prostor", 5), (r"\bnp\b", 4), (r"\bzabor\b", 3),
    ],
    "bydleni": [
        (r"\bbytov\w*\s+jednotk", 4), (r"\bbytovy\s+fond", 5),
        (r"prideleni\s+bytu", 5), (r"\bnajemne\b", 4),
        (r"\bbytu\b", 3), (r"\bbyty\b", 3), (r"\bbytova\s+komise", 4),
        (r"\bbytov\w*\s+dum", 3), (r"socialni\s+byt", 4), (r"\bbj\s+c\.", 4),
        (r"\bbytova\s+jednotka", 5),
    ],
    "rozpocet": [
        (r"rozpoc\w*\s+opatreni", 5), (r"\brozpocet\b", 5), (r"\brozpoctu\b", 4),
        (r"\bodpis\w*\b", 3), (r"rezervni\w*\s+fond", 4), (r"investicni\w*\s+fond", 4),
        (r"zaverecny\s+ucet", 5), (r"rozpoctov\w*\s+vyhled", 5),
        (r"rozpoctov\w*\s+provizorium", 5), (r"\brozpoctova\s+zmena", 5),
        (r"\bstrednedoby\s+vyhled", 4), (r"volnych\s+financnich\s+prostredk", 5),
        (r"\bzhodnoceni\s+(volnych\s+)?financnich", 4), (r"\bucetni\s+zaverk", 4),
    ],
    "dotace-poskytnute": [
        (r"poskytnuti\s+dotac", 5), (r"poskytnuti\s+(financniho\s+)?daru", 4),
        (r"individualni\s+dotac", 5), (r"\bfondu?\s+(sportu|kultury|zivotniho)", 4),
        (r"dotac\w*\s+z\s+fondu", 5), (r"neinvesticni\s+prispevek", 4),
        (r"verejnopravni\s+smlouv", 4), (r"\bprogramov\w*\s+dotac", 4),
        (r"financni\s+prispev", 5), (r"\bzadost\w*\s+o\s+prispev", 5),
        (r"\bprisp\.?\s*na\b", 4), (r"poskytnuti\s+prispev", 5),
        (r"schvaleni\s+dotac", 5), (r"\bz\s+fs\b", 4), (r"\bfondu\s+rozvoje", 4),
    ],
    "dotace-prijate": [
        (r"zapojeni\s+dotac", 5), (r"prijeti\s+dotac", 5),
        (r"dotac\w*\s+z\s+rozpoctu\s+karlovarskeho\s+kraje", 5),
        (r"podani\s+zadosti\s+o\s+dotac", 5), (r"zadost\w*\s+o\s+dotac", 4),
        (r"\bdotacni\s+titul", 4), (r"\birop\b", 4), (r"operacni\s+program", 4),
        (r"ministerstv\w*\s+pro\s+mistni\s+rozvoj", 3), (r"\bstatni\s+fond\b", 3),
        (r"prijeti\s+ucelove\s+dotace", 5), (r"zapojeni\s+daru", 5),
        (r"\bprijeti\s+financniho\s+daru", 5), (r"zapojeni\s+financnich\s+prostredk", 4),
        (r"zapojeni\s+(neinv\w*\.?\s*)?ucel", 5), (r"\bucel\.?\s*dotac", 5),
        (r"\bneinv\.?\s*ucelov", 5),
    ],
    "verejna-zakazka": [
        (r"verejn\w*\s+zakazk", 5), (r"zadavaci\s+dokumentac", 5),
        (r"zadavaci\s+rizeni", 5), (r"vyber\s+dodavatele", 5),
        (r"vyzv\w*\s+k\s+podani\s+nabid", 5), (r"hodnoceni\s+nabidek", 5),
        (r"vyberov\w*\s+rizeni", 4), (r"\bhodnotici\s+komis", 4),
        (r"\bzruseni\s+zadavaciho", 4),
    ],
    "smlouvy": [
        (r"\bsmlouv", 2), (r"\bdodatek\b", 3), (r"\bdodatku\b", 3),
        (r"\bmemorandum", 4), (r"ukonceni\s+smlouvy", 4), (r"\bpujck", 4), (r"\bzapujck", 4),
        (r"\bsmlouva\s+o\s+dilo", 4),
    ],
    "investice": [
        (r"\brekonstrukc", 5), (r"\bvystavb", 5), (r"investicni\s+akc", 5),
        (r"stavebni\s+uprav", 5), (r"projektov\w*\s+dokumentac", 4),
        (r"\brevitalizac", 5), (r"\bmodernizac", 4), (r"\boprava\b", 3),
        (r"\bopravy\b", 3), (r"smlouva\s+o\s+dilo", 3), (r"\betapa\b", 2),
        (r"\bstavebni\s+povoleni", 4), (r"\bzhotovitel", 3),
    ],
    "uzemni-plan": [
        (r"uzemni\w*\s+plan", 5), (r"uzemniho\s+planu", 5),
        (r"regulacni\s+plan", 5), (r"uzemni\s+studie", 5),
        (r"zastavovaci\s+studie", 4), (r"uzemne\s+analyticke", 4),
        (r"\bzmena\s+c\.?\s*\d+\s+uzemniho", 5),
    ],
    "pamatky": [
        (r"\bpamatk", 5), (r"\bpamatkov", 5), (r"\bvila\s+lil\b", 5),
        (r"\brestaurovani", 4), (r"kulturni\s+pamatk", 5),
        (r"pamatkov\w*\s+zon", 5), (r"\bobnova\s+historick", 4),
        (r"\bmpr\b", 4), (r"program\w*\s+regenerace", 5),
    ],
    "unesco": [
        (r"\bunesco\b", 5), (r"slavn\w*\s+lazn\w*\s+evropy", 5),
        (r"svetov\w*\s+dedictvi", 5), (r"great\s+spa\s+towns", 5),
    ],
    "lazenstvi": [
        (r"\bkolonad", 5), (r"lazensk\w*\s+zdroj", 5), (r"lazensky\s+statut", 5),
        (r"\bzridel", 5), (r"mineraln\w*\s+pramen", 5), (r"\bpramen", 4),
        (r"vnitrni\s+lazensk", 4), (r"\blazenstvi\b", 5),
        (r"lazensk\w*\s+mist", 4),
    ],
    "cestovni-ruch": [
        (r"cestovni\w*\s+ruch", 5), (r"\binfocentrum", 5),
        (r"propagac\w*\s+mesta", 4), (r"\bturistick", 4),
        (r"destinacni\s+(agentur|management)", 5), (r"\bmarketing\w*\s+mesta", 3),
    ],
    "doprava": [
        (r"\bmhd\b", 5), (r"mestsk\w*\s+doprav", 5), (r"\bdopravni\s+", 4),
        (r"\bkomunikac", 4), (r"\bchodnik", 4), (r"\bsilnic", 4),
        (r"\bautobus", 4), (r"\buzavirk", 4), (r"\bzeleznic", 4),
        (r"\bcyklostezk", 4), (r"dopravni\s+obsluznost", 5), (r"\blanov\w*\s+drah", 4),
    ],
    "parkovani": [
        (r"\bparkov", 5), (r"\bparking\b", 5), (r"\bparkoviste", 5),
        (r"stani\s+vozidel", 4), (r"parkovaci\s+zon", 5), (r"vyhrazen\w*\s+stani", 5),
    ],
    "zivotni-prostredi": [
        (r"zivotni\w*\s+prostredi", 5), (r"\bovzdusi", 5), (r"\bvodni\s+tok", 4),
        (r"\brenaturac", 5), (r"\bkanalizac", 4), (r"\bvodovod", 4),
        (r"\bcistirn\w*\s+odpadnich", 5), (r"ochran\w*\s+prirody", 5),
        (r"\bpovodnov", 3), (r"\bprotipovodnov", 4), (r"\brozptylov\w*\s+studi", 5),
        (r"\bchko\b", 4), (r"\bemis", 4), (r"odneti\s+zemedelsk", 5),
    ],
    "zelen": [
        (r"\bzelene\b", 4), (r"\bzelen\b", 4), (r"\bstrom", 4), (r"\bkaceni", 5),
        (r"lazensk\w*\s+lesy", 5), (r"\bmestsk\w*\s+lesy", 5), (r"\blesni\s+hospodar", 4),
        (r"\bsadov\w*\s+uprav", 4), (r"\bpark\b", 3), (r"\bparku\b", 3),
        (r"\bvysadb", 5), (r"\bdrevin", 5), (r"\bzahradn", 3),
    ],
    "odpady": [
        (r"\bodpad", 5), (r"\bsvoz\b", 4), (r"\btrideni\s+odpad", 5),
        (r"\bskladk", 4), (r"sberny\s+dvur", 5), (r"\bpopelnic", 4),
        (r"\bpoh\b", 4), (r"odpadov\w*\s+hospodar", 5),
    ],
    "energetika": [
        (r"\bteplarn", 5), (r"\bteplo\b", 4), (r"dodavk\w*\s+tepla", 5),
        (r"\bplynu\b", 4), (r"\belektrick\w*\s+energi", 5), (r"\bfotovolt", 5),
        (r"verejn\w*\s+osvetlen", 5), (r"uspor\w*\s+energi", 5),
        (r"\benergetick", 4), (r"\benergi", 3), (r"\btepeln\w*\s+cerpadl", 5),
        (r"\bteplovod", 5), (r"\bczt\b", 5),
    ],
    "skolstvi": [
        (r"\bzakladni\s+skol", 5), (r"\bmatersk\w*\s+skol", 5), (r"\bskolk", 4),
        (r"\bzus\b", 5), (r"zakladni\s+umeleck", 5), (r"\bdum\s+deti", 5),
        (r"\bskolsk", 4), (r"\bskoly\b", 3), (r"\bskole\b", 3), (r"\bskolni\s+jideln", 4),
        (r"\bskolstvi\b", 5), (r"\bzs\s+", 4), (r"\bms\s+", 3),
        (r"detsk\w*\s+skupin", 5), (r"\bjesle\b", 4),
    ],
    "socialni": [
        (r"\bsocialni", 4), (r"domov\w*\s+pro\s+seniory", 5), (r"\bpecovatelsk", 5),
        (r"\bseniory\b", 4), (r"\bseniorum\b", 4), (r"\bazylov", 5),
        (r"komunitni\s+plan", 4), (r"socialni\s+sluzb", 5),
        (r"hmotn\w*\s+nouz", 5), (r"\bprotidrog", 5), (r"\bhandicap", 4),
    ],
    "zdravotnictvi": [
        (r"\bnemocnic", 5), (r"\bzdravotn", 4), (r"\blekarsk", 4),
        (r"\bordinac", 4), (r"\blekarn", 4), (r"\bzachrann\w*\s+sluzb", 4),
    ],
    "kultura": [
        (r"\bdivadl", 5), (r"\bmuzeum\b", 5), (r"\bmuzea\b", 5), (r"\bknihovn", 5),
        (r"\borchestr", 5), (r"\bfestival", 5), (r"\bkoncert", 4), (r"\bgalerie\b", 4),
        (r"\bkulturn", 4), (r"\bkultury\b", 4), (r"\bchopin", 4),
        (r"\bkronik", 4), (r"\bpublikac", 3), (r"\breedic", 4),
    ],
    "sport": [
        (r"\bsportov", 5), (r"\bsportu\b", 5), (r"\bstadion", 5), (r"\bhriste\b", 4),
        (r"\bbazen", 4), (r"\btelocvicn", 4), (r"\bfotbal", 4), (r"\bhokej", 4),
        (r"\bgolf", 3), (r"\bzimni\s+stadion", 5),
    ],
    "bezpecnost": [
        (r"mestsk\w*\s+polici", 5), (r"\bkrizov", 4), (r"\bhasic", 5),
        (r"\bsbor\s+dobrovolnych", 5), (r"\bkamerov\w*\s+system", 5),
        (r"\bbezpecnosti\s+ve\s+meste", 4), (r"\bverejneho\s+poradku", 4),
    ],
    "personalni": [
        (r"\bjmenovani\b", 4), (r"\bodvolani\b", 4), (r"\bkonkurz", 5),
        (r"\bodmen\w*\s+(reditel|jednatel|clenu|neuvolnen)", 5), (r"\bodmen", 3),
        (r"\bplat\w*\s+reditel", 5),
        (r"\bmzdov", 4), (r"\bpracovni\s+pomer", 5), (r"\bvedouci\s+odboru", 5),
        (r"\btajemnik", 4), (r"\bpocet\s+zamestnanc", 5), (r"\bvyplaceni\s+odmen", 5),
    ],
    "organizacni": [
        (r"organizacni\w*\s+rad", 5), (r"\bvnitrni\s+predpis", 5), (r"\bsmernic", 4),
        (r"\bjednaci\s+rad", 5), (r"\bpravidla\s+pro\b", 4), (r"\bstatut\b", 4),
        (r"\bspisovy\s+rad", 5), (r"\borganizacni\s+struktur", 5),
        (r"\bprogram\s+\d+\.", 5), (r"program\w*\s+jednani", 5),
        (r"organizacni\s+opatreni", 5), (r"\bzpravodaj\s+mesta", 5),
        (r"program\w*\s+rozvoje\s+mesta", 5), (r"\bvolba\s+overovatel", 5),
        (r"\brevokac", 5), (r"strategick\w*\s+plan", 4),
        (r"\bnavrhov\w*\s+komis", 4), (r"\bkontrola\s+plneni\s+usneseni", 5),
    ],
    "komise-vybory": [
        (r"\bkomise\b", 4), (r"\bkomisi\b", 4), (r"\bvybor\b", 4), (r"\bvyboru\b", 4),
        (r"financni\s+vybor", 5), (r"kontrolni\s+vybor", 5), (r"osadni\s+vybor", 5),
        (r"\bclenu\s+komis", 5), (r"\bzrizeni\s+komis", 5),
    ],
    "mestske-firmy": [
        (r"valn\w*\s+hromad", 5), (r"\bjednatel", 5), (r"\bdozorci\s+rad", 5),
        (r"\bspol\.?\s*s\s*r\.?\s*o", 3), (r"\bs\.\s*r\.\s*o", 2),
        (r"\btds\b", 5), (r"lazenske\s+lesy\s+spol", 5),
        (r"\bdevelop\s+centrum", 5), (r"\bprispevkov\w*\s+organizac", 4),
        (r"\bzakladatelsk\w*\s+listin", 5), (r"\bvh\b", 4), (r"\ba\.\s*s\.", 3),
        (r"spravni\s+rad", 4), (r"\bpredstavenstv", 5), (r"\bdelegovani\s+zastupce", 5),
        (r"\bdso\b", 4), (r"dobrovoln\w*\s+svazek\s+obci", 5),
    ],
    "vyhlasky": [
        (r"obecne\s+zavazn\w*\s+vyhlask", 5), (r"\bozv\b", 5),
        (r"\bnarizeni\s+mesta", 5), (r"\btrzni\s+rad", 4),
    ],
    # "ruzne" nemá pravidla — je to výslovné přiznání, že si nejsme jistí.
    "ruzne": [],
}

# Když skóre vyjde nastejno, rozhodne pořadí tady: konkrétní téma přebíjí
# obecné. Bez toho by "smlouvy" požíraly polovinu archivu.
PRIORITA = [
    "unesco", "pamatky", "lazenstvi", "uzemni-plan",
    "majetek-prodej", "majetek-nakup", "majetek-pronajem", "bydleni",
    "verejna-zakazka", "dotace-prijate", "dotace-poskytnute", "rozpocet",
    "parkovani", "odpady", "energetika", "zelen", "zivotni-prostredi", "doprava",
    "skolstvi", "socialni", "zdravotnictvi", "kultura", "sport", "bezpecnost",
    "cestovni-ruch", "investice",
    "vyhlasky", "komise-vybory", "mestske-firmy", "personalni", "organizacni",
    "smlouvy", "ruzne",
]


class TagovaniSelhalo(Exception):
    """Nekonzistence mezi pravidly a číselníkem. Radši spadnout než tiše tagovat blbě."""


def _zkontroluj_pravidla() -> None:
    """Pravidla musí odkazovat výhradně na existující tagy z číselníku."""
    platne = core.platne_tagy()
    navic = set(PRAVIDLA) - platne
    if navic:
        raise TagovaniSelhalo(f"pravidla odkazují na neexistující tagy: {sorted(navic)}")
    chybi = platne - set(PRAVIDLA)
    if chybi:
        raise TagovaniSelhalo(f"číselník má tagy bez pravidel: {sorted(chybi)}")
    if set(PRIORITA) != platne:
        raise TagovaniSelhalo("PRIORITA neodpovídá číselníku")


_ZKOMPILOVANO: dict[str, list[tuple[re.Pattern, int]]] = {}


def _priprav() -> None:
    if _ZKOMPILOVANO:
        return
    _zkontroluj_pravidla()
    for tag, pravidla in PRAVIDLA.items():
        _ZKOMPILOVANO[tag] = [(re.compile(vzor), vaha) for vzor, vaha in pravidla]


def _norm(text: str) -> str:
    """Bez diakritiky, malá písmena, sjednocené mezery.

    Úředníci píšou jednou 'Mariánské Lázně' a jindy 'Marianske Lazne';
    pravidla se pak píšou jen v jedné podobě.
    """
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", t)


def skore(nazev: str, text: str) -> dict[str, int]:
    """Vrátí skóre všech tagů. Vystaveno kvůli ladění pravidel."""
    _priprav()
    n_nazev = _norm(nazev)
    n_text = _norm(text)[:6000]  # delší usnesení jsou přílohy a jen ředí signál
    body: dict[str, int] = {}
    for tag, vzory in _ZKOMPILOVANO.items():
        s = 0
        for vzor, vaha in vzory:
            if vzor.search(n_nazev):
                s += vaha * 3  # název je shrnutí bodu, váží nejvíc
            elif vzor.search(n_text):
                s += vaha
        if s:
            body[tag] = s
    return body


def navrhni_tagy(nazev: str, text: str) -> list[str]:
    """Vrátí 1–3 tagy z číselníku. Když si nejsme jistí, vrátí ["ruzne"].

    Deterministické — stejný vstup dá vždy stejný výstup.
    """
    body = {t: s for t, s in skore(nazev, text).items() if s >= PRAH}
    if not body:
        return ["ruzne"]

    poradi = {t: i for i, t in enumerate(PRIORITA)}
    vybrane = sorted(body, key=lambda t: (-body[t], poradi[t]))[:MAX_TAGU]

    # "ruzne" nikdy nejde dohromady s konkrétním tagem — buď víme, nebo nevíme.
    vybrane = [t for t in vybrane if t != "ruzne"] or ["ruzne"]

    platne = core.platne_tagy()
    neplatne = [t for t in vybrane if t not in platne]
    if neplatne:
        raise TagovaniSelhalo(f"vygenerovány tagy mimo číselník: {neplatne}")
    return vybrane


# --------------------------------------------------------------------------
# Přetagování už uloženého archivu + propsání na hlasování
# --------------------------------------------------------------------------

def _soubory(podadresar: str) -> list[Path]:
    koren = core.DATA / podadresar
    return sorted(koren.rglob("*.json")) if koren.exists() else []


def main() -> dict:
    """Přetáguje uložená usnesení a propíše tagy na odpovídající hlasování.

    Sběrač usnesení tuhle funkci volá už při zápisu, takže tenhle krok je
    hlavně opravný: po změně pravidel projede archiv znovu bez stahování.
    """
    log = core.Log("tagovani")
    _priprav()

    rozlozeni: Counter = Counter()
    tagy_bodu: dict[str, list[str]] = {}   # hlasovani_id -> tagy
    zmeneno = 0
    bodu = 0

    for soubor in _soubory("usneseni"):
        zaznam = core.nacti(soubor)
        if not isinstance(zaznam, dict) or "body" not in zaznam:
            log.chyba(f"{soubor} nevypadá jako záznam usnesení")
            continue
        zmena = False
        for bod in zaznam["body"]:
            bodu += 1
            nove = navrhni_tagy(bod.get("nazev", ""), bod.get("text", ""))
            if bod.get("tagy") != nove:
                bod["tagy"] = nove
                zmena = True
            rozlozeni.update(nove)
            if bod.get("hlasovani_id"):
                tagy_bodu[bod["hlasovani_id"]] = nove
        if zmena:
            core.uloz(soubor, zaznam)
            zmeneno += 1

    # Tagy na hlasování se KOPÍRUJÍ z bodu usnesení — aby šlo filtrovat
    # hlasování podle tématu. Vlastní tagování hlasování by se rozešlo.
    propsano = 0
    for soubor in _soubory("hlasovani"):
        zaznam = core.nacti(soubor)
        if not isinstance(zaznam, dict) or "hlasovani" not in zaznam:
            continue
        zmena = False
        for h in zaznam["hlasovani"]:
            nove = tagy_bodu.get(h.get("id"))
            if nove is None:
                continue
            if h.get("tagy") != nove:
                h["tagy"] = nove
                zmena = True
            propsano += 1
        if zmena:
            core.uloz(soubor, zaznam)

    log.info("přetagováno", bodu=bodu, zmenenych_souboru=zmeneno, hlasovani_s_tagy=propsano)
    for tag, kolik in rozlozeni.most_common():
        log.info(f"  {tag}", pocet=kolik, podil=f"{100 * kolik / max(bodu, 1):.1f} %")
    log.pricti(bodu)
    return log.uzavri()


if __name__ == "__main__":
    main()
