"""Řetěz komise → rada: co komise navrhla a co s tím rada udělala.

--------------------------------------------------------------------------
DVĚ RŮZNÉ VĚCI, KTERÉ SE NESMÍ SLÉVAT
--------------------------------------------------------------------------
1. **Projednání zápisu (doložené).** Usnesení rady doslova říká „bere na
   vědomí zápis z jednání Komise kultury ze dne 13. 03. 2023". Když ten
   zápis v datech máme a datum sedí, není to odhad — je to citace. Část
   těchto usnesení jde dál a přiznává i důvod: „na základě doporučení
   Komise smart city… Rada města zřizuje pracovní skupinu".

2. **Téma (odhad).** Komise něco doporučila, rada o pár týdnů později
   rozhodla o něčem, co zní stejně. Společný identifikátor mezi zápisem
   komise a usnesením rady NEEXISTUJE — spojení se skládá ze shody
   neobvyklých slov, případně částky a času. Je to domněnka.

Obojí je v jednom souboru, ale v jiném poli a s jinou `jistota`. Smíchat
je by znamenalo vydávat dohad za citaci.

--------------------------------------------------------------------------
CO SE NETVRDÍ
--------------------------------------------------------------------------
**Že rada rozhodla PROTOŽE komise doporučila.** I doložené projednání
říká jen tolik, že se o zápisu jednalo. Kauzalitu z těchhle dat vyčíst
nejde a modul se o ni nepokouší — stejná zásada jako u řetězu
usnesení → smlouva.

**Že komisi rada neposlechla.** Doporučení, ke kterému se nic nenašlo, je
v `bez_odezvy`. To NENÍ seznam ignorovaných návrhů: rozhodnutí může být
zapsané jinými slovy, může spadat pod jiný orgán, může být teprve před
námi, nebo ho tohle párování prostě nenašlo. Je to seznam k dohledání.

--------------------------------------------------------------------------
Meze zdroje
--------------------------------------------------------------------------
* Zápisy komisí máme od roku 2015, usnesení rady od roku 2012. U starších
  usnesení tedy „doporučení nenalezeno" neznamená nic.
* Část zápisů se nepodařilo rozebrat (skeny, jiný formát). Návrhy z nich
  v datech nejsou a chybí i tady; kolik jich je, počítá komise_prehled.
* Zápisy nemají všechny komise — dopravní a další v rejstříku zápisy
  nezveřejňují. Jejich doporučení tenhle přehled nevidí vůbec.
* Bod „Program 37. RM" je seznam programu jednání a obsahuje názvy všech
  ostatních bodů. Do porovnávání témat proto nevstupuje — trefil by se
  do čehokoliv.
"""
from __future__ import annotations

import glob
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import CONFIG, DATA, Log, ZdrojSelhal, nacti, uloz  # noqa: E402

# --------------------------------------------------------------------------
# Prahy a konstanty
# --------------------------------------------------------------------------

# Jak dlouho po jednání komise se ještě hledá usnesení rady. Rada zasedá
# zhruba po třech týdnech; půl roku je běžný průběh u věcí, které čekají
# na rozpočet, rok už nic nedokazuje.
OKNO_TESNE = 60
OKNO_BEZNE = 180
OKNO_SIROKE = 365

# Kolik usnesení si u jednoho doporučení necháme. Víc než tři kandidáti
# nejsou nález, ale výběr — stejná zásada jako u řetězu na smlouvy.
MAX_KANDIDATU = 3

# Nad tolik stejně dobrých kandidátů se dvojice bez tvrdé indicie zahodí.
STROP_KANDIDATU = 8

# Bod usnesení s víc než tolika významovými slovy je slepenec (dlouhý
# soupis, příloha přepsaná do textu) a trefí se do čehokoliv.
STROP_SLOV_BODU = 150

# Bodové prahy pro tři stupně jistoty odhadu.
PRAH_ULOZIT = 40
PRAH_STREDNI = 68
PRAH_VYSOKA = 88

# Směry, které jsou návrhem PRO RADU. „bere na vědomí" ani „souhlasí"
# radu o nic nežádají, do řetězu tedy nevstupují.
SMERY_NAVRHU = {"doporucuje", "nedoporucuje", "zada", "uklada", "navrhuje"}


# --------------------------------------------------------------------------
# Normalizace a kmeny
# --------------------------------------------------------------------------

def _bez_diakritiky(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn"
    ).lower()


def _normalizuj(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _bez_diakritiky(s)).strip()


def _kmen(t: str) -> str:
    """Kmen slova. Koncovka se v češtině mění, začátek slova ne."""
    if len(t) >= 7:
        return t[:-2]
    if len(t) >= 5:
        return t[:-1]
    return t


# Slova, která jsou v usneseních i v zápisech komisí prakticky vždy.
# Shoda na nich nic neznamená; kdyby vstupovala do porovnání, spojilo by
# se všechno se vším přes „město", „schvaluje" a „smlouva".
STOPSLOVA = {_kmen(w) for w in """
mesto mestem mesta marianske lazne lazni lazenske rada rady rade radou radu
zastupitelstvo zastupitelstva zastupitelstvu komise komisi vybor vyboru
doporucuje nedoporucuje doporuceni schvaluje schvalit schvaleni souhlasi souhlas
navrh navrhu navrhuje uklada zada zadost zadosti usneseni jednani jednat
bere vedomi ktere ktery ktera dalsi ostatni mezi podle roku rok roce
tim tom teto tohoto ceske republiky cislo proti zdrzel hlasovani priloha
vyse celkove celkem vysledek jako budou bude byla byly bylo take pouze
podal predlozil predlozeni verze uzavreni uzavrenim smlouvy smlouva smlouve
sidlem podminek podminky prilohy prilohou tykajici spolecnosti spolecnost
prostredku financnich vsech zapis zapisu zapisem clenove clenu clen
pana pani predseda predsedy predsedou material materialu bodu body
""".split()} | {
    # Zkratky komisí samotných. Nesou identitu orgánu, ne téma — a tu už
    # nese signál `jmenuje_komisi`. Kdyby vstupovaly do porovnání témat,
    # spojilo by se doporučení komise urbanistiky s kterýmkoliv usnesením,
    # ve kterém stojí „urbanistická studie".
    "kuad", "kuar", "klcr", "klcru", "ksva", "ksvaz", "urbanist",
}


def _kmeny(text: str) -> set[str]:
    """Významové kmeny slov v textu — to jediné se porovnává."""
    out: set[str] = set()
    for w in _normalizuj(text).split():
        if len(w) < 4 or w.isdigit():
            continue
        k = _kmen(w)
        if len(k) >= 4 and k not in STOPSLOVA:
            out.add(k)
    return out


def _slova_ke_kmenum(text: str) -> dict[str, str]:
    """Kmen → slovo, jak stojí v textu.

    Kmeny jsou vnitřní pomůcka: „udrzitelno" a „spolecens" nejsou česká
    slova a čtenáři by je web ukazovat neměl. Mapa vrací původní tvar
    včetně diakritiky, takže se dá napsat „udržitelnost, společenská"
    místo mrzačených kmenů.
    """
    mapa: dict[str, str] = {}
    for slovo in re.findall(r"\w+", text or "", flags=re.UNICODE):
        n = _bez_diakritiky(slovo)
        if len(n) < 4 or n.isdigit():
            continue
        k = _kmen(n)
        if len(k) >= 4 and k not in STOPSLOVA:
            mapa.setdefault(k, slovo)
    return mapa


def _den(s: str | None) -> date | None:
    try:
        return datetime.strptime((s or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _mnozne(n: int, jeden: str, dva: str, pet: str) -> str:
    if n == 1:
        return f"{n} {jeden}"
    return f"{n} {dva}" if 2 <= n <= 4 else f"{n} {pet}"


# Částka v textu doporučení: „100 000 Kč", „350.000,-- Kč", „20 tis. Kč".
_CASTKA = re.compile(
    r"(\d{1,3}(?:[\s .]\d{3})+|\d{4,9})(?:[,.]-*\d*)?\s*(tis\.?|mil\.?)?\s*K[čc]",
    re.IGNORECASE,
)


def _castky(text: str) -> set[int]:
    out: set[int] = set()
    for m in _CASTKA.finditer(text or ""):
        cifry = re.sub(r"\D", "", m.group(1))
        if not cifry:
            continue
        hodnota = int(cifry)
        nasobek = (m.group(2) or "").lower()
        if nasobek.startswith("tis"):
            hodnota *= 1_000
        elif nasobek.startswith("mil"):
            hodnota *= 1_000_000
        if 1_000 <= hodnota <= 2_000_000_000:
            out.add(hodnota)
    return out


# --------------------------------------------------------------------------
# Rozpoznání komise v textu usnesení
# --------------------------------------------------------------------------
#
# Usnesení komisi jmenuje po svém: „Školská komise" místo „Komise školství",
# „KLCR" místo celého názvu, „komise UaD" po staru. Zkratky jsou nejisté
# (KS je Komise sportu i Komise smart city), proto se doložené projednání
# uloží jen tehdy, když se kromě názvu trefí i DATUM konkrétního zápisu.
ALIASY: dict[str, list[str]] = {
    "Komise kultury": [r"komis\w*\s+kultur", r"kulturn\w*\s+komis", r"\bkk\b"],
    "Komise sportu": [r"komis\w*\s+sport", r"sportovn\w*\s+komis", r"\bks\b"],
    "Komise urbanistiky a architektury": [
        r"komis\w*\s+urbanist", r"urbanistick\w*\s+komis",
        r"komis\w*\s+ua[dr]\b", r"\bkua[dr]\b",
    ],
    "Komise lázeňství, cestovního ruchu a UNESCO": [
        r"komis\w*\s+lazenst", r"\bklcru?\b", r"komis\w*\s+cestovn",
        r"lazensk\w*\s+komis",
    ],
    "Komise sociální a zdravotní": [
        r"komis\w*\s+socialn", r"socialn\w*\s+komis", r"\bksvaz\b",
        r"komis\w*\s+zdravotn",
    ],
    "Komise školství": [r"skolsk\w*\s+komis", r"komis\w*\s+skolst", r"\bks\b"],
    "Komise smart city, Zdravých měst a MA21": [
        r"komis\w*\s+smart", r"smart\s+city[^.]{0,40}komis",
    ],
}
_ALIASY = {k: [re.compile(v) for v in vzory] for k, vzory in ALIASY.items()}

# Datum v textu usnesení: „ze dne 13. 03. 2023", „(15.2.2023)".
_DATUM = re.compile(r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})\b")

# Usnesení, které přiznává důvod: „na základě doporučení Komise…",
# „ukládá (v souladu s doporučením komise)…". Je to jediné místo, kde
# rada sama říká, odkud návrh vzala.
_NA_ZAKLADE = re.compile(
    r"(na\s+zaklade|v\s+souladu\s+s|dle|die)\s+doporuc\w*\s+(komis|vybor)"
)

# Bod „Program 37. RM" (a „Schválení programu jednání") je soupis programu
# jednání — obsahuje názvy všech ostatních bodů a v porovnávání témat by se
# trefil do čehokoliv. Vzor jede přes text bez diakritiky a schválně nechytá
# „Program regenerace MPZ" ani „Program rozvoje města" — to jsou věcné body.
_PROGRAM = re.compile(
    r"^\s*(schvaleni\s+programu\s+jednani|programu?\s+jednani|program\s+\d)"
)


def _komise_v_textu(norm_text: str) -> set[str]:
    return {k for k, vzory in _ALIASY.items() if any(v.search(norm_text) for v in vzory)}


def _data_v_textu(text: str) -> set[str]:
    out: set[str] = set()
    for m in _DATUM.finditer(text or ""):
        try:
            out.add(date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat())
        except ValueError:
            continue
    return out


# --------------------------------------------------------------------------
# Načtení vstupů
# --------------------------------------------------------------------------

def nacti_usneseni(log: Log) -> list[dict]:
    soubory = sorted(glob.glob(str(DATA / "usneseni" / "*" / "*" / "*.json")))
    if not soubory:
        raise ZdrojSelhal(
            "Nenalezena žádná data/usneseni/**/*.json — nejdřív spusť scrapers/usneseni.py"
        )
    body: list[dict] = []
    for cesta in soubory:
        zapis = nacti(Path(cesta))
        den = _den(zapis.get("datum"))
        for b in zapis.get("body", []):
            nazev = b.get("nazev") or ""
            text = b.get("text") or ""
            cely = f"{nazev}\n{text}"
            norm = _normalizuj(cely)
            body.append({
                "organ": zapis.get("organ"),
                "cj": zapis.get("cj"),
                "datum": zapis.get("datum"),
                "den": den,
                "bod": b.get("cislo"),
                "cislo_usneseni": b.get("cislo_usneseni"),
                "nazev": nazev,
                "tagy": b.get("tagy") or [],
                "castka_czk": b.get("castka_czk"),
                "url": b.get("url") or zapis.get("url"),
                "_kmeny": _kmeny(cely),
                "_komise": _komise_v_textu(norm),
                "_data": _data_v_textu(cely),
                "_na_zaklade": bool(_NA_ZAKLADE.search(norm)),
                # Program jednání je soupis, ne rozhodnutí.
                "_program": bool(_PROGRAM.match(_bez_diakritiky(nazev))),
            })
    log.info("načteno bodů usnesení", pocet=len(body), zapisu=len(soubory))
    return body


def nacti_komise(log: Log) -> tuple[list[dict], list[dict], int]:
    """(zápisy komisí, návrhy pro radu, kolik návrhů komise nepřijala)."""
    prehled = nacti("komise/prehled.json")
    if not prehled:
        raise ZdrojSelhal(
            "Chybí data/komise/prehled.json — nejdřív spusť pipeline/komise_prehled.py"
        )
    zapisy = prehled.get("zapisy") or []
    if not zapisy:
        raise ZdrojSelhal("data/komise/prehled.json nemá ani jeden zápis")

    navrhy: list[dict] = []
    neprijatych = [0]
    for z in zapisy:
        den = _den(z.get("datum"))
        for poradi, u in enumerate(z.get("usneseni") or []):
            if u.get("smer") not in SMERY_NAVRHU:
                continue
            # Návrh, který komise sama neschválila, není doporučení. Vést
            # ho v řetězu by tvrdilo pravý opak toho, co komise rozhodla.
            if u.get("prijato") is False:
                neprijatych[0] += 1
                continue
            navrhy.append({
                "id": f"{z['id']}-{poradi}",
                "zapis_id": z["id"],
                "komise": z.get("komise"),
                "datum": z.get("datum"),
                "den": den,
                "url": z.get("url"),
                "cislo_jednani": z.get("cislo_jednani"),
                "text": u.get("text"),
                "zkraceno": bool(u.get("zkraceno")),
                "smer": u.get("smer"),
                "zdroj": u.get("zdroj"),
                "hlasovani": u.get("hlasovani"),
                "_kmeny": _kmeny(u.get("text") or ""),
                "_slova": _slova_ke_kmenum(u.get("text") or ""),
                "_castky": _castky(u.get("text") or ""),
            })
    log.info("zápisů komisí", pocet=len(zapisy), navrhu_pro_radu=len(navrhy),
             vynechano_neprijatych=neprijatych[0])
    return zapisy, navrhy, neprijatych[0]


# --------------------------------------------------------------------------
# 1. Doložené projednání zápisu
# --------------------------------------------------------------------------

def projednani(log: Log, zapisy: list[dict], body: list[dict]) -> list[dict]:
    """Usnesení, které jmenuje komisi a datum jejího jednání.

    Není to odhad. Usnesení samo říká, o kterém zápisu jednalo, a ten
    zápis v datech máme. Dvojznačné případy (téhož dne jednaly dvě komise
    a usnesení nerozlišuje která) se zahazují — hádat se tu nemá co.
    """
    dle_data: dict[str, list[dict]] = defaultdict(list)
    for z in zapisy:
        if z.get("datum"):
            dle_data[z["datum"]].append(z)

    nalezy: dict[tuple[str, str], dict] = {}
    nejednoznacnych = 0
    for b in body:
        if not b["_komise"] or not b["_data"] or b["den"] is None:
            continue
        for iso in b["_data"]:
            sedici = [z for z in dle_data.get(iso, ()) if z.get("komise") in b["_komise"]]
            if not sedici:
                continue
            if len(sedici) > 1:
                nejednoznacnych += 1
                continue
            z = sedici[0]
            odstup = (b["den"] - _den(iso)).days if _den(iso) else None
            # Zápis musí být starší než jednání rady. Opačné pořadí by
            # znamenalo, že se datum v usnesení týká něčeho jiného.
            if odstup is None or odstup < 0 or odstup > OKNO_SIROKE:
                continue
            klic = (z["id"], f"{b['organ']}-{b['bod']}")
            if klic in nalezy:
                continue
            # Dva různě silné doklady. „Usnesení" je rozhodnutí o zápisu,
            # „program" je jen bod na programu jednání — zápis ležel na
            # stole, ale usnesení o něm zdroj nezveřejnil. Obojí je citace
            # ze zdroje, ne odhad; slévat je by ale znamenalo vydávat
            # účast na programu za rozhodnutí.
            zpusob = "program" if b["_program"] else "usneseni"
            nalezy[klic] = {
                "id": f"{z['id']}__{b['organ']}-{b['bod']}",
                "jistota": "dolozeno",
                "zpusob": zpusob,
                "duvod": (
                    (f"usnesení jmenuje {z['komise']} a datum jejího jednání "
                     f"({_datum_cesky(iso)}); zápis z toho dne v datech je")
                    if zpusob == "usneseni" else
                    (f"zápis {z['komise']} z {_datum_cesky(iso)} je uvedený "
                     "na programu jednání; samostatné usnesení o něm zdroj neuvádí")
                ),
                "na_zaklade_doporuceni": b["_na_zaklade"],
                "odstup_dni": odstup,
                "zapis": _vystup_zapisu(z),
                "usneseni": _vystup_bodu(b),
            }
    dle_zpusobu = Counter(n["zpusob"] for n in nalezy.values())
    log.info("doložených projednání zápisu", pocet=len(nalezy),
             usnesenim=dle_zpusobu["usneseni"], jen_na_programu=dle_zpusobu["program"],
             zahozeno_nejednoznacnych=nejednoznacnych)
    return sorted(nalezy.values(), key=lambda r: (r["usneseni"]["datum"] or "", r["id"]))


_MESICE = ["", "ledna", "února", "března", "dubna", "května", "června",
           "července", "srpna", "září", "října", "listopadu", "prosince"]


def _datum_cesky(iso: str) -> str:
    d = _den(iso)
    return f"{d.day}. {_MESICE[d.month]} {d.year}" if d else iso


# --------------------------------------------------------------------------
# 2. Odhad podle tématu
# --------------------------------------------------------------------------

def _vaha(cetnost: int) -> int:
    """Kolik váží shoda na jednom slově podle toho, jak je v usneseních vzácné.

    Slovo, které je ve všech usneseních („rekonstrukce"), neurčuje nic.
    Slovo, které je v pěti („Knižní lázně"), určuje skoro všechno.
    """
    if cetnost <= 5:
        return 26
    if cetnost <= 15:
        return 18
    if cetnost <= 45:
        return 11
    if cetnost <= 150:
        return 5
    return 0


VZACNE = 45      # do téhle četnosti se slovo počítá jako rozlišující
VELMI_VZACNE = 15


def _dost_shody(spolecne: list[tuple[int, str]], ma_castku: bool) -> bool:
    """Kdy je překryv slov dost silný, aby se z něj vůbec směl dělat odhad.

    Jedno sdílené slovo je náhoda: „fórum" je v zápisu školské komise
    (Zdravé školní fórum) i v usnesení o Heritage Forum Marienbad a
    společného nemají nic. Bez dvou rozlišujících slov — nebo jednoho
    velmi vzácného doplněného sedící částkou — se spojení neukládá.
    """
    vzacnych = sum(1 for c, _ in spolecne if c <= VZACNE)
    velmi = sum(1 for c, _ in spolecne if c <= VELMI_VZACNE)
    if velmi >= 2:
        return True
    if velmi >= 1 and (vzacnych >= 2 or ma_castku):
        return True
    # Tři rozlišující slova bez jediného opravdu vzácného. Slabší, ale
    # pořád to není náhoda; dvě taková slova ano — „vybudovat" a „režim"
    # spojily doporučení o parkovacích stáních s investicí do golfu.
    return vzacnych >= 3


def _ohodnot(navrh: dict, bod: dict, cetnost: Counter,
             tyz_zapis: bool) -> dict | None:
    if bod["den"] is None or navrh["den"] is None:
        return None
    odstup = (bod["den"] - navrh["den"]).days
    if odstup < 0 or odstup > OKNO_SIROKE:
        return None

    spolecne = sorted((cetnost[k], k) for k in navrh["_kmeny"] & bod["_kmeny"])
    ma_castku = bool(bod["castka_czk"] and bod["castka_czk"] in navrh["_castky"])
    if not _dost_shody(spolecne, ma_castku):
        return None

    # Do textu pro čtenáře jdou slova tak, jak stojí v doporučení —
    # kmen „udrzitelno" by vypadal jako překlep, ne jako doklad.
    citelna = [navrh["_slova"].get(k, k) for c, k in spolecne if c <= VZACNE]
    signaly = ["tema"]
    duvody = ["společná neobvyklá slova: " + ", ".join(citelna)]
    # Skóre za téma se stropuje — dlouhý bod usnesení má víc slov a bez
    # stropu by vyhrával jen proto, že je delší.
    skore = min(sum(_vaha(c) for c, _ in spolecne), 64)

    if odstup <= OKNO_TESNE:
        skore += 20
        signaly.append("cas_tesne")
    elif odstup <= OKNO_BEZNE:
        skore += 12
        signaly.append("cas_bezne")
    else:
        # Nad půl roku už čas nespojuje nic. Necháváme jen dvojice, které
        # drží samy o sobě — velmi vzácné slovo nebo sedící částka.
        if not (ma_castku or any(c <= VELMI_VZACNE for c, _ in spolecne)):
            return None
        skore += 4
        signaly.append("cas_siroke")
    duvody.append(f"rada rozhodla {_mnozne(odstup, 'den', 'dny', 'dní')} po jednání komise"
                  if odstup else "rada rozhodla týž den jako komise")

    if ma_castku:
        skore += 20
        signaly.append("castka")
        duvody.append(f"částka {bod['castka_czk']:,} Kč je i v doporučení komise"
                      .replace(",", " "))

    if navrh["komise"] in bod["_komise"]:
        skore += 16
        signaly.append("jmenuje_komisi")
        duvody.append("usnesení tuhle komisi jmenuje")
    if bod["_na_zaklade"]:
        skore += 14
        signaly.append("na_zaklade_doporuceni")
        duvody.append("usnesení se odvolává na doporučení komise")
    if tyz_zapis:
        skore += 24
        signaly.append("zapis_na_jednani")
        duvody.append("na témž jednání rady byl na stole zápis z tohoto jednání komise")

    return {"skore": skore, "signaly": signaly, "duvody": duvody, "odstup_dni": odstup,
            "spolecna_slova": citelna[:8]}


def _tvrda_indicie(h: dict) -> bool:
    """Signál, který míří na konkrétní věc, ne jen na téma."""
    return bool({"castka", "zapis_na_jednani", "na_zaklade_doporuceni"} & set(h["signaly"]))


def _jistota(h: dict, kandidatu: int) -> str:
    sig = set(h["signaly"])
    v_case = bool({"cas_tesne", "cas_bezne"} & sig)
    if (h["skore"] >= PRAH_VYSOKA and v_case and kandidatu <= 2
            and "zapis_na_jednani" in sig
            and ("castka" in sig or "na_zaklade_doporuceni" in sig)):
        return "vysoka"
    if h["skore"] >= PRAH_STREDNI and v_case and (_tvrda_indicie(h) or kandidatu == 1):
        return "stredni"
    return "nizka"


def odhady(log: Log, navrhy: list[dict], body: list[dict],
           projednane: list[dict]) -> list[dict]:
    """Doporučení komise → pozdější usnesení rady o téže věci. Odhad."""
    pouzitelne = [b for b in body
                  if not b["_program"] and len(b["_kmeny"]) <= STROP_SLOV_BODU]
    log.info("bodů usnesení v porovnávání témat", pocet=len(pouzitelne),
             vynechano_program=sum(1 for b in body if b["_program"]),
             vynechano_dlouhych=sum(1 for b in body
                                    if not b["_program"] and len(b["_kmeny"]) > STROP_SLOV_BODU))

    cetnost: Counter[str] = Counter()
    for b in pouzitelne:
        cetnost.update(b["_kmeny"])
    rejstrik: dict[str, list[int]] = defaultdict(list)
    for i, b in enumerate(pouzitelne):
        for k in b["_kmeny"]:
            rejstrik[k].append(i)

    # Na kterém JEDNÁNÍ rady ležel který zápis komise. Klíčem je jednání,
    # ne bod: zápis bývá na programu pod jedním číslem a rozhodnutí o věci
    # z něj padne pod jiným. Že obojí proběhlo na jedné schůzi, je fakt ze
    # zdroje a téma pak spojuje dvě věci z téhož stolu.
    zapis_jednani: dict[tuple[str, str, object], set[str]] = defaultdict(set)
    for p in projednane:
        u = p["usneseni"]
        zapis_jednani[(u["organ"], u["datum"], u["cj"])].add(p["zapis"]["id"])

    retezy: list[dict] = []
    bez_odezvy: list[dict] = []
    zahozeno = 0
    for n in navrhy:
        if n["den"] is None:
            continue
        kandidati: set[int] = set()
        for k in n["_kmeny"]:
            if _vaha(cetnost.get(k, 0)) > 0:
                kandidati.update(rejstrik.get(k, ()))

        ohodnocene: list[tuple[dict, dict]] = []
        for i in kandidati:
            b = pouzitelne[i]
            tyz = n["zapis_id"] in zapis_jednani.get((b["organ"], b["datum"], b["cj"]), ())
            h = _ohodnot(n, b, cetnost, tyz)
            if h and h["skore"] >= PRAH_ULOZIT:
                ohodnocene.append((h, b))
        ohodnocene.sort(key=lambda x: (-x[0]["skore"], x[0]["odstup_dni"]))

        if not ohodnocene:
            bez_odezvy.append(_vystup_navrhu(n))
            continue

        # Když se o jedno doporučení uchází přehršel stejně dobrých usnesení
        # a žádné z nich nedrží tvrdá indicie, není to nález, ale výběr.
        if len(ohodnocene) > STROP_KANDIDATU and not any(
            _tvrda_indicie(h) for h, _ in ohodnocene[:MAX_KANDIDATU]
        ):
            zahozeno += 1
            zaznam = _vystup_navrhu(n)
            zaznam["poznamka"] = (
                f"tématu odpovídá {len(ohodnocene)} usnesení a žádné z nich nedrží "
                "částka ani odkaz na komisi — vybrat jedno by bylo hádání"
            )
            bez_odezvy.append(zaznam)
            continue

        for h, b in ohodnocene[:MAX_KANDIDATU]:
            retezy.append(_retez(n, b, h, len(ohodnocene)))

    log.info("odhadnutých spojení", pocet=len(retezy),
             doporuceni_bez_odezvy=len(bez_odezvy), zahozeno_nejednoznacnych=zahozeno)
    retezy.sort(key=lambda r: (r["usneseni"]["datum"] or "", r["id"]))
    return retezy, bez_odezvy


# --------------------------------------------------------------------------
# Výstupní tvary
# --------------------------------------------------------------------------

def _vystup_zapisu(z: dict) -> dict:
    return {
        "id": z["id"], "komise": z.get("komise"), "datum": z.get("datum"),
        "cislo_jednani": z.get("cislo_jednani"), "url": z.get("url"),
        "navrhu_pro_radu": sum(1 for u in (z.get("usneseni") or [])
                               if u.get("smer") in SMERY_NAVRHU),
    }


def _vystup_bodu(b: dict) -> dict:
    return {
        "organ": b["organ"], "cj": b["cj"], "datum": b["datum"], "bod": b["bod"],
        "cislo_usneseni": b["cislo_usneseni"], "nazev": b["nazev"],
        "tagy": b["tagy"], "castka_czk": b["castka_czk"], "url": b["url"],
    }


def _vystup_navrhu(n: dict) -> dict:
    return {
        "id": n["id"], "zapis_id": n["zapis_id"], "komise": n["komise"],
        "datum": n["datum"], "cislo_jednani": n["cislo_jednani"],
        "text": n["text"], "zkraceno": n["zkraceno"], "smer": n["smer"],
        "zdroj": n["zdroj"], "hlasovani": n["hlasovani"], "url": n["url"],
    }


def _retez(n: dict, b: dict, h: dict, kandidatu: int) -> dict:
    duvody = list(h["duvody"])
    if kandidatu > 1:
        duvody.append("tématu odpovídá i "
                      + _mnozne(kandidatu - 1, "další usnesení", "další usnesení",
                                "dalších usnesení"))
    return {
        "id": f"{n['id']}__{b['organ']}-{b['bod']}",
        "jistota": _jistota(h, kandidatu),
        "skore": h["skore"],
        "signaly": h["signaly"],
        "spolecna_slova": h["spolecna_slova"],
        "duvod": "; ".join(duvody),
        "odstup_dni": h["odstup_dni"],
        "kandidatu_usneseni": kandidatu,
        "doporuceni": _vystup_navrhu(n),
        "usneseni": _vystup_bodu(b),
    }


# --------------------------------------------------------------------------
# Měření: jak často odhad sedí
# --------------------------------------------------------------------------

def overeni(retezy: list[dict], log: Log) -> dict:
    """Kolik spojení z ručně posouzeného vzorku skutečně sedí.

    Stupně jistoty jsou bez měření jen slova. `config/vzorek_retez_komise.json`
    drží lidský verdikt nad reprodukovatelným vzorkem — všechna spojení
    s vysokou a střední jistotou a každé čtvrté s nízkou.

    VZOREK ZASTARÁVÁ. Když se párování změní, část posouzených dvojic
    zmizí a měření přestane platit pro to, co web ukazuje. Kolik jich
    chybí, je proto ve výstupu a hlídá to `kontrola.py`.
    """
    cesta = CONFIG / "vzorek_retez_komise.json"
    if not cesta.exists():
        return {"stav": "neposouzeno",
                "poznamka": "config/vzorek_retez_komise.json chybí — přesnost se neměří"}
    try:
        vzorek = json.loads(cesta.read_text(encoding="utf-8")).get("posouzeno") or []
    except (json.JSONDecodeError, OSError) as e:  # noqa: BLE001
        log.chyba(f"vzorek nejde přečíst: {e}")
        return {"stav": "neposouzeno", "poznamka": str(e)}

    zive = {r["id"] for r in retezy}
    dle_jistoty: dict[str, dict[str, int]] = {}
    chybi = 0
    for z in vzorek:
        if z["id"] not in zive:
            chybi += 1
            continue
        stav = dle_jistoty.setdefault(z["jistota"], {"posouzeno": 0, "sedi": 0})
        stav["posouzeno"] += 1
        stav["sedi"] += 1 if z.get("sedi") else 0
    posouzeno = sum(v["posouzeno"] for v in dle_jistoty.values())
    sedi = sum(v["sedi"] for v in dle_jistoty.values())

    log.info("ověření vzorku", posouzeno=posouzeno, sedi=sedi, zastaralych=chybi)
    return {
        "stav": "ok",
        "posouzeno": posouzeno,
        "sedi": sedi,
        "dle_jistoty": dle_jistoty,
        # Kolik posouzených dvojic už párování nevrací. Nad pár kusů to
        # znamená, že vzorek patří k jiné verzi a je třeba posoudit znovu.
        "zastaralych_ve_vzorku": chybi,
        "zdroj": "config/vzorek_retez_komise.json",
    }


# --------------------------------------------------------------------------
# Kontrola a běh
# --------------------------------------------------------------------------

JISTOTY = {"vysoka", "stredni", "nizka"}


def zkontroluj(projednane: list[dict], retezy: list[dict]) -> None:
    """Radši spadnout než tiše vypustit nesmysl, na kterém web staví."""
    if not projednane:
        raise ZdrojSelhal(
            "Nenašlo se ani jedno doložené projednání zápisu komise. "
            "Usnesení rady je citují pravidelně — párování je rozbité."
        )
    for p in projednane:
        if p["odstup_dni"] < 0:
            raise ZdrojSelhal(f"Projednání {p['id']} předchází jednání komise")
        if p["jistota"] != "dolozeno":
            raise ZdrojSelhal(f"Projednání {p['id']} nemá jistotu „dolozeno“")
    for r in retezy:
        if r["jistota"] not in JISTOTY:
            raise ZdrojSelhal(f"Neznámá jistota {r['jistota']!r} u řetězu {r['id']}")
        if r["odstup_dni"] < 0:
            raise ZdrojSelhal(f"Řetěz {r['id']} má usnesení dřív než doporučení")
        if not r["spolecna_slova"]:
            raise ZdrojSelhal(f"Řetěz {r['id']} nemá společné rozlišující slovo")


METODIKA = {
    "co_to_je": (
        "Co komise navrhly radě a co s tím rada udělala. Dvě různě jisté věci: "
        "doložené projednání zápisu (usnesení samo jmenuje komisi a datum) a "
        "odhad podle tématu (shoda neobvyklých slov, částky a času)."
    ),
    "projednani": (
        "Doložené. Usnesení rady doslova říká, že bere na vědomí zápis z jednání "
        "konkrétní komise z konkrétního dne, a ten zápis v datech je. Když téhož "
        "dne jednaly dvě komise a usnesení nerozlišuje která, spojení se zahodí."
    ),
    "zpusob": (
        "`usneseni` = rada o zápisu přijala usnesení. `program` = zápis je uvedený "
        "jen na programu jednání a samostatné usnesení o něm zdroj nezveřejnil. "
        "Obojí je citace ze zdroje, ale není to totéž — účast na programu není "
        "rozhodnutí."
    ),
    "neprijate_navrhy": (
        "Návrh, u kterého zápis říká, že neprošel, do řetězu nevstupuje. "
        "Doporučení, které komise zamítla, žádné doporučení není."
    ),
    "na_zaklade_doporuceni": (
        "Příznak u projednání: usnesení samo přiznává důvod („na základě doporučení "
        "Komise…“, „v souladu s doporučením komise“). Je to jediné místo, kde rada "
        "říká, odkud návrh vzala."
    ),
    "overeni": (
        "Přesnost odhadu je změřená, ne odhadnutá: na reprodukovatelném vzorku "
        "(všechna spojení s vysokou a střední jistotou, každé čtvrté s nízkou) je "
        "u každé dvojice lidský verdikt v config/vzorek_retez_komise.json. Výsledek "
        "je v poli `overeni`."
    ),
    "odhad": (
        "Domněnka. Mezi zápisem komise a usnesením rady neexistuje společný "
        "identifikátor — spojení drží jen shoda neobvyklých slov, případně částka "
        "a čas. Web to MUSÍ označit jako odhad."
    ),
    "prah_shody": (
        f"Uloží se jen dvojice se dvěma společnými slovy, která jsou v usneseních "
        f"vzácná (nejvýš {VZACNE} výskytů), nebo s jedním velmi vzácným (nejvýš "
        f"{VELMI_VZACNE}) doplněným sedící částkou. Jedno společné slovo je náhoda."
    ),
    "cas": (
        f"Hledá se usnesení do {OKNO_SIROKE} dní po jednání komise. Do {OKNO_TESNE} "
        f"dní je to běžný průběh, nad {OKNO_BEZNE} dní už čas nic nedokazuje."
    ),
    "kauzalita": (
        "NETVRDÍ SE, že rada rozhodla PROTOŽE komise doporučila. I doložené "
        "projednání říká jen tolik, že se o zápisu jednalo."
    ),
    "bez_odezvy": (
        "Doporučení, ke kterému se nic nenašlo. NENÍ to seznam přehlížených návrhů: "
        "rozhodnutí může být zapsané jinými slovy, může patřit jinému orgánu, může "
        "být teprve před námi, nebo ho tohle párování nenašlo. Je to seznam "
        "k dohledání, ne obvinění."
    ),
    "program_jednani": (
        "Bod „Program 37. RM“ je soupis programu a obsahuje názvy všech ostatních "
        "bodů. Do porovnávání témat nevstupuje — trefil by se do čehokoliv."
    ),
    "meze": (
        "Zápisy komisí máme od roku 2015, usnesení rady od roku 2012; u starších "
        "usnesení „doporučení nenalezeno“ neznamená nic. Zápisy zveřejňuje jen část "
        "komisí a 47 zápisů se nepodařilo rozebrat."
    ),
}


def main() -> int:
    log = Log("retez_komise")
    try:
        body = nacti_usneseni(log)
        zapisy, navrhy, neprijatych = nacti_komise(log)

        projednane = projednani(log, zapisy, body)
        retezy, bez = odhady(log, navrhy, body, projednane)
        zkontroluj(projednane, retezy)

        dle_jistoty = {"vysoka": 0, "stredni": 0, "nizka": 0}
        for r in retezy:
            dle_jistoty[r["jistota"]] += 1
        po_komisich: Counter[str] = Counter()
        for r in retezy:
            po_komisich[r["doporuceni"]["komise"] or "neurčeno"] += 1

        stat = {
            "navrhu_pro_radu": len(navrhy),
            # Návrhy, u kterých zápis sám říká, že neprošly. Nejsou mezi
            # `navrhu_pro_radu` — doporučení, které komise zamítla, žádné
            # doporučení není.
            "neprijatych_navrhu": neprijatych,
            "projednani": len(projednane),
            "projednanych_zapisu": len({p["zapis"]["id"] for p in projednane}),
            "projednani_s_duvodem": sum(1 for p in projednane if p["na_zaklade_doporuceni"]),
            "odhadu": len(retezy),
            "dle_jistoty": dle_jistoty,
            "doporuceni_s_odhadem": len({r["doporuceni"]["id"] for r in retezy}),
            "bez_odezvy": len(bez),
            "po_komisich": dict(po_komisich.most_common()),
        }
        log.info("hotovo", **{k: v for k, v in stat.items()
                              if isinstance(v, int)})

        mereni = overeni(retezy, log)
        uloz("retez/komise_rada.json", {
            "generovano": datetime.now(timezone.utc).date().isoformat(),
            "zdroj": "data/komise/prehled.json + data/usneseni/**",
            "metodika": METODIKA,
            "statistika": stat,
            # Kolik z ručně posouzeného vzorku doopravdy sedí. Bez měření
            # jsou stupně jistoty jen slova.
            "overeni": mereni,
            "projednani": projednane,
            "retezy": retezy,
            "bez_odezvy": bez,
        })
        log.pricti(len(projednane) + len(retezy))
    except ZdrojSelhal as e:
        log.chyba(str(e))
        log.uzavri()
        return 1
    log.uzavri()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
