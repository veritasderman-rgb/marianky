"""Podnikatelé ve městě — výpisy z veřejného rejstříku k firmám z ARES.

Modul „Podnikatelé a obory". Navazuje na `scrapers/firmy.py`, který zjistil,
JAKÉ subjekty ve městě sídlí. Tenhle sběrač dohledává, KDO za nimi stojí:
statutární orgány, dozorčí rady, společníky a akcionáře.

ZDROJ
-----
`https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty-vr/{ico}`
— výpis z veřejného rejstříku (obchodní, spolkový, …). Vrací `zaznamy[]`
a v nich `statutarniOrgany`, `ostatniOrgany`, `spolecnici`, `akcionari`,
`zakladniKapital`, `datumZapisu`, `stavSubjektu`, `zpusobRizeni`,
`spisovaZnacka`. Živnostník v žádném takovém rejstříku zapsaný není a
endpoint na něj vrací 404 — to není chyba, je to odpověď.

CO SE STAHUJE A PROČ NE VŠECHNO
-------------------------------
Ve městě je 4 177 subjektů, ale 2 678 z nich jsou živnostníci, kteří žádný
statutární orgán nemají a výpis pro ně neexistuje. Stahuje se proto jen to,
kde se dá někoho čekat, a kritérium se zapisuje do dat (`vyber` ve výstupu):

  1. **podnikatelské právnické osoby** — právní forma není fyzická osoba
     ani z forem, které ze své podstaty nepodnikají (společenství vlastníků
     jednotek, spolky, nadace…). Obojí se bere ze seznamů modulu firem,
     aby se kritérium nerozešlo mezi dvěma přehledy.
  2. **firmy z přehledu důležitých** (`data/firmy/prehled/dulezite.json`) —
     bez ohledu na formu. Je mezi nimi 89 živnostníků, kteří s městem
     obchodují; výpis pro ně nejspíš nebude, ale zeptat se je poctivější
     než je předem škrtnout. Že se nenašel, je v datech vidět.

Sjednocení obou kritérií je zhruba 1 070 dotazů. Tempo drží sdílená značka
`core._pockej_na_rade`, odpovědi se cachují na týden, takže opakovaný běh
API vůbec nezatíží.

OSOBNÍ ÚDAJE — CO SE ZÁMĚRNĚ NEUKLÁDÁ
-------------------------------------
Obchodní rejstřík je veřejný a jméno, funkce a firma jsou v něm veřejné
údaje. **Datum narození a adresa bydliště se ale neukládají**, i když je
ARES vrací. Na web nepatří a k ničemu, co tenhle projekt dělá, nejsou
potřeba.

Datum narození se používá **jen v paměti** k jediné věci: rozlišit dva lidi
téhož jména. Bez něj by z „Jana Nováka" jednatele a „Jana Nováka"
společníka jiné firmy vznikl jeden vymyšlený člověk. Po přiřazení klíče se
zahazuje a do žádného souboru se nedostane — hlídá to `_zkontroluj_soukromi()`,
která běh shodí, kdyby se do výstupu propsalo cokoliv zakázaného.

Jak se klíč přiřazuje:

  - `osoba_klic` je `prijmeni-jmeno` (konvence projektu, jedno křestní jméno)
  - když je pod jedním jménem víc různých dat narození, dostane druhý a
    další člověk příponu `-2`, `-3` a **všichni** takoví mají `jmenovcu > 1`.
    Navazující přehled jim pak nesmí přiřadit `osoba_id`.
  - starší zápisy datum narození občas nemají. Bezdatový záznam se přilepí
    k jedinému známému člověku toho jména (`rozliseni:
    "datum_narozeni_castecne"`); když jich je víc, zůstane samostatný
    s `rozliseni: "bez_data_narozeni"` — raději dva záznamy než vymyšlený
    člověk.

VÝSTUP
------
`data/podnikatele/vypisy.json`

```json
{
  "generovano": "2026-08-17",
  "zdroj": "ares.gov.cz/.../ekonomicke-subjekty-vr/{ico}",
  "vyber": { "kriterium": "...", "dotazovano": 1067, "s_vypisem": 900 },
  "osobni_udaje": { "...metodika..." },
  "osoby": [{ "osoba_klic": "novak-jan", "jmeno": "Jan Novák", "typ": "fyzicka",
              "jednoznacna": true, "rozliseni": "datum_narozeni",
              "zaznamu_tehoz_jmena": 1, "angazma": 3, "firem": 2 }],
  "firmy": [{
    "ico": "25213261", "nazev": "TECHNICKÝ A DOPRAVNÍ SERVIS, s.r.o.",
    "rejstrik": "OR", "spisova_znacka": "C 9012", "soud": "KSPL",
    "stav": "AKTIVNI", "datum_zapisu": "1997-08-27",
    "zakladni_kapital_czk": 100000.0,
    "angazma": [{
      "osoba_klic": "javurek-daniel", "jmeno": "Daniel Javůrek",
      "typ_osoby": "fyzicka", "role": "statutar", "organ": "Statutární orgán",
      "funkce": "jednatel", "od": "2007-09-01", "do": null,
      "aktualni": true, "dle": "funkce", "obdobi": [{"od": "...", "do": null}]
    }]
  }],
  "bez_vypisu": [{ "ico": "...", "nazev": "...", "duvod": "nenalezeno_v_rejstriku" }]
}
```

`do: null` u aktuálního angažmá znamená „trvá". `do: null` u neaktuálního
by znamenalo „nevíme kdy skončilo" — takový případ se neukládá bez pole
`dle`, ze kterého je vidět, odkud datum je: `funkce` (vznik/zánik funkce),
`clenstvi` (vznik/zánik členství), `zapis` (jen datum zápisu a výmazu
záznamu v rejstříku, tedy horní odhad).
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import core  # noqa: E402
from lib.core import CACHE, Log, ZdrojSelhal, nacti, slug, uloz  # noqa: E402
# Kritérium "podnikatelská právnická osoba" je definované u modulu firem.
# Čte se odtud, aby se oba přehledy nerozešly v tom, koho za podnikatele
# považují.
from pipeline.firmy_prehled import (  # noqa: E402
    FORMY_FYZICKYCH_OSOB,
    FORMY_NEPODNIKATELSKE,
)

ARES_VR = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty-vr"
ARES_HOST = "ares.gov.cz"
CACHE_VR = CACHE / "ares_vr"

# Role podle typu angažmá, jak ho pojmenovává ARES. Neznámé typy se ukládají
# jako "jiny_organ" a vypisují se do logu — ať je vidět, co zdroj přinesl
# nového, místo aby to tiše zapadlo.
ROLE_PODLE_ANGAZMA: dict[str, str] = {
    "STATUTARNI_ORGAN_CLEN": "statutar",
    "STATUTARNI_ORGAN_OSOBA": "statutar",
    "PROKURA_OSOBA": "prokurista",
    "SPOLECNIK_OSOBA": "spolecnik",
    "AKCIONAR": "akcionar",
    "DOZORCI_RADA_CLEN": "dozorci_rada",
    "SPRAVNI_RADA_CLEN": "spravni_rada",
    "KONTROLNI_KOMISE_CLEN": "kontrolni_komise",
    "VEDOUCI_ORGANIZACNI_SLOZKY": "vedouci_zavodu",
    "ZAKLADATEL": "zakladatel",
    "STATUTAR_ZRIZOVATELE_OSOBA": "statutar_zrizovatele",
    "OPATROVNIK_VR": "opatrovnik",
    "LIKVIDATOR_OSOBA_VR": "likvidator",
    "LIKVIDATOR_OSOBA": "likvidator",
}

# Klíče, které se do výstupu nesmí dostat za žádných okolností.
ZAKAZANE_KLICE = {"datumNarozeni", "datum_narozeni", "adresa", "textovaAdresa",
                  "bydliste", "_dn", "fyzickaOsoba"}

# Jak přesný je zdroj data u angažmá. Menší číslo vyhrává.
PRESNOST_DATA = {"funkce": 0, "clenstvi": 1, "zapis": 2}

_SESSION: requests.Session | None = None


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def _session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
    return _SESSION


def _get_vr(ico: str, *, max_age: int = 7 * 86_400, retries: int = 3) -> tuple[int, dict]:
    """Stáhne výpis z veřejného rejstříku pro jedno IČO.

    Do cache jde i 404 ("subjekt v rejstříku není"). Je to platná odpověď
    zdroje, ne výpadek, a při opakovaném běhu nemá smysl se na ni ptát znovu.
    """
    otisk = hashlib.sha256(f"vr:{ico}".encode()).hexdigest()[:24]
    soubor = CACHE_VR / f"{otisk}.json"
    if max_age and soubor.exists() and (time.time() - soubor.stat().st_mtime) < max_age:
        ulozene = json.loads(soubor.read_text(encoding="utf-8"))
        return ulozene["status"], ulozene["telo"]

    hlavicky = {"User-Agent": core.UA, "Accept": "application/json",
                "Accept-Language": "cs"}
    posledni: Exception | None = None
    for pokus in range(retries):
        try:
            core._pockej_na_rade(ARES_HOST)  # sdílené tempo projektu
            r = _session().get(f"{ARES_VR}/{ico}", headers=hlavicky, timeout=90)
            if r.status_code == 429 or 500 <= r.status_code < 600:
                raise ZdrojSelhal(f"HTTP {r.status_code} u výpisu {ico}")
            telo = r.json() if r.content else {}
            soubor.parent.mkdir(parents=True, exist_ok=True)
            soubor.write_text(json.dumps({"status": r.status_code, "telo": telo},
                                         ensure_ascii=False), encoding="utf-8")
            return r.status_code, telo
        except Exception as e:  # noqa: BLE001 — opakujeme na čemkoliv síťovém
            posledni = e
            if pokus < retries - 1:
                time.sleep(2 ** (pokus + 1))
    raise ZdrojSelhal(f"výpis {ico} selhal na {retries} pokusů: {posledni}")


# --------------------------------------------------------------------------
# Výběr firem
# --------------------------------------------------------------------------

def vyber_firem(subjekty: list[dict], dulezite_ico: set[str]) -> list[dict]:
    """Které subjekty se budou dotahovat a proč. Důvod jde do dat."""
    vybrane: list[dict] = []
    for s in subjekty:
        ico = s.get("ico")
        if not ico:
            continue  # bez IČO se výpis dotáhnout nedá, viz poznámka u firmy.py
        duvody = []
        forma = s.get("pravni_forma")
        if forma not in FORMY_FYZICKYCH_OSOB and forma not in FORMY_NEPODNIKATELSKE:
            duvody.append("podnikatelska_pravnicka_osoba")
        if ico in dulezite_ico:
            duvody.append("prehled_dulezitych")
        if duvody:
            vybrane.append({"ico": ico, "nazev": s.get("nazev"), "duvody": duvody})
    return sorted(vybrane, key=lambda f: f["ico"])


# --------------------------------------------------------------------------
# Drobní pomocníci nad odpovědí
# --------------------------------------------------------------------------

def _zivy(polozky: list[dict] | None) -> dict | None:
    """Platná verze údaje: ta, která nemá datum výmazu.

    Rejstřík vede každý údaj jako řadu verzí. Živá je ta bez `datumVymazu`;
    když živá není žádná, bere se poslední zapsaná.
    """
    if not polozky:
        return None
    zive = [p for p in polozky if not p.get("datumVymazu")]
    if zive:
        return max(zive, key=lambda p: p.get("datumZapisu") or "")
    return max(polozky, key=lambda p: p.get("datumZapisu") or "")


def _castka(obnos: dict | None) -> float | None:
    """Částka z obnosu ARES. Desetinný oddělovač je tam středník: '100000;00'.

    Je to tentýž rozbitý escape jako v číselníku CZ-NACE. Když je typ jiný
    než koruny, vrací se None — přepočet měn si projekt nevymýšlí.
    """
    if not obnos or obnos.get("typObnos") != "KORUNY":
        return None
    hodnota = (obnos.get("hodnota") or "").replace(";", ".").replace(" ", "")
    try:
        return float(hodnota)
    except ValueError:
        return None


def _procenta(velikost: dict | None) -> float | None:
    if not velikost:
        return None
    hodnota = (velikost.get("hodnota") or "").replace(";", ".").replace(" ", "")
    if velikost.get("typObnos") == "PROCENTA":
        try:
            return float(hodnota)
        except ValueError:
            return None
    if velikost.get("typObnos") == "TEXT":
        # "100 %" nebo "1/2". Zlomek se nepřepočítává — kdo ho chce, má text.
        m = re.fullmatch(r"(\d+(?:[.,]\d+)?)%", hodnota.replace(",", "."))
        return float(m.group(1)) if m else None
    return None


def _datum(hodnota: str | None) -> str | None:
    return hodnota[:10] if hodnota else None


def _ico(hodnota: str | None) -> str | None:
    """Doplní IČO na osm míst.

    PAST: výpis z rejstříku vrací u právnických osob v orgánech IČO někdy
    s vedoucími nulami ('00254061'), jinde bez nich ('254061') — a to i pro
    tentýž subjekt v jiné firmě. Celý projekt slučuje protistrany podle IČO,
    takže bez doplnění nul by se město samo se sebou nespárovalo.
    """
    if not hodnota:
        return None
    ocistene = hodnota.strip()
    return ocistene.zfill(8) if ocistene.isdigit() and len(ocistene) <= 8 else ocistene


def _uprav_velikost(text: str) -> str:
    """ARES vrací část jmen verzálkami ('DANIEL JAVŮREK'). Sjednotí se.

    Mění se jen jméno psané CELÉ verzálkami — u ostatních by úprava mohla
    přepsat tvar, který je ve zdroji správně (např. 'de Vries').
    """
    pismena = [c for c in text if c.isalpha()]
    if not pismena or not all(c.isupper() for c in pismena):
        return text
    return " ".join(
        "-".join(c[:1].upper() + c[1:].lower() for c in slovo.split("-"))
        for slovo in text.split()
    )


def _osoba_z_uzlu(uzel: dict) -> dict | None:
    """Osoba z uzlu rejstříku. `_dn` je datum narození JEN pro rozlišení."""
    fo = uzel.get("fyzickaOsoba")
    if fo:
        prijmeni = _uprav_velikost((fo.get("prijmeni") or "").strip())
        jmena = _uprav_velikost((fo.get("jmeno") or "").strip())
        if not prijmeni and not jmena:
            return None
        krestni = jmena.split()[0] if jmena else ""
        return {
            "typ": "fyzicka",
            "jmeno": " ".join(x for x in (jmena, prijmeni) if x),
            "_zaklad": slug(f"{prijmeni} {krestni}"),
            "_dn": fo.get("datumNarozeni"),
        }
    po = uzel.get("pravnickaOsoba")
    if po:
        nazev = (po.get("obchodniJmeno") or "").strip()
        ico = _ico(po.get("ico"))
        if not nazev and not ico:
            return None
        return {
            "typ": "pravnicka",
            "jmeno": nazev or f"IČO {ico}",
            "ico": ico,
            "_zaklad": f"firma-{ico}" if ico else f"firma-{slug(nazev)}",
            "_dn": None,
        }
    return None


# --------------------------------------------------------------------------
# Parsování angažmá
# --------------------------------------------------------------------------

def _obdobi_uzlu(uzel: dict) -> tuple[str | None, str | None, str, bool]:
    """Od kdy do kdy angažmá platí a odkud to datum je.

    Pořadí zdrojů je od nejpřesnějšího k nejhrubšímu:
      `funkce`   — vznik a zánik funkce, přesně to, co nás zajímá
      `clenstvi` — vznik a zánik členství v orgánu
      `zapis`    — datum zápisu a výmazu záznamu v rejstříku. To je horní
                   odhad: záznam se maže i při přepisu adresy, ne jen když
                   člověk odejde.
    """
    clenstvi = uzel.get("clenstvi") or {}
    funkce = clenstvi.get("funkce") or {}
    cl = clenstvi.get("clenstvi") or {}
    zivy_zaznam = not uzel.get("datumVymazu")

    if funkce.get("vznikFunkce") or funkce.get("zanikFunkce"):
        return (_datum(funkce.get("vznikFunkce")), _datum(funkce.get("zanikFunkce")),
                "funkce", zivy_zaznam and not funkce.get("zanikFunkce"))
    if cl.get("vznikClenstvi") or cl.get("zanikClenstvi"):
        return (_datum(cl.get("vznikClenstvi")), _datum(cl.get("zanikClenstvi")),
                "clenstvi", zivy_zaznam and not cl.get("zanikClenstvi"))
    return (_datum(uzel.get("datumZapisu")), _datum(uzel.get("datumVymazu")),
            "zapis", zivy_zaznam)


def _role(uzel: dict, typ_organu: str | None, nezname: dict[str, int]) -> str:
    typ = uzel.get("typAngazma") or typ_organu or ""
    role = ROLE_PODLE_ANGAZMA.get(typ)
    if role:
        return role
    if typ:
        nezname[typ] = nezname.get(typ, 0) + 1
    return "jiny_organ"


def _zaznamy_organu(organ: dict, sekce: str, nezname: dict[str, int]) -> list[dict]:
    """Rozloží jeden orgán na jednotlivé záznamy o lidech."""
    out: list[dict] = []
    nazev_organu = organ.get("nazevOrganu") or sekce
    typ_organu = organ.get("typOrganu")

    uzly: list[tuple[dict, dict | None]] = []
    for c in organ.get("clenoveOrganu") or []:
        uzly.append((c, None))
    for sp in organ.get("spolecnik") or []:
        osoba = sp.get("osoba")
        if osoba:
            uzly.append((osoba, sp))

    for uzel, obal in uzly:
        osoba = _osoba_z_uzlu(uzel)
        if not osoba:
            continue
        od, do, dle, aktualni = _obdobi_uzlu(uzel)
        funkce = ((uzel.get("clenstvi") or {}).get("funkce") or {}).get("nazev")
        zaznam = {
            "osoba": osoba,
            "role": _role(uzel, typ_organu, nezname),
            "organ": nazev_organu,
            "funkce": funkce,
            "od": od, "do": do, "dle": dle, "aktualni": aktualni,
            "podil_procent": None, "vklad_czk": None,
        }
        if obal is not None:
            # Podíl společníka. Bere se živá verze — starší verze podílu jsou
            # historie vkladů, ne dnešní stav.
            podil = _zivy(obal.get("podil"))
            if podil:
                zaznam["podil_procent"] = _procenta(podil.get("velikostPodilu"))
                zaznam["vklad_czk"] = _castka(podil.get("vklad"))
            if obal.get("datumVymazu"):
                zaznam["aktualni"] = False
        out.append(zaznam)
    return out


def _sluc_obdobi(obdobi: list[dict]) -> list[dict]:
    """Slije navazující a překrývající se úseky do jednoho.

    Rejstřík zakládá nový záznam při každé změně (i při přestěhování), takže
    jeden nepřetržitý výkon funkce se ve výpisu tváří jako pět úseků na sebe
    navazujících. Bez slití by časová osa hlásila pět příchodů a pět odchodů
    jednoho člověka.
    """
    setrideno = sorted(obdobi, key=lambda o: (o["od"] or "", o["do"] or "9999-99-99"))
    slite: list[dict] = []
    for u in setrideno:
        if not slite:
            slite.append(dict(u))
            continue
        posledni = slite[-1]
        if posledni["do"] is None:
            continue  # otevřený úsek pohltí všechno, co začíná později
        if (u["od"] or "") <= posledni["do"]:
            if u["do"] is None:
                posledni["do"] = None
            else:
                posledni["do"] = max(posledni["do"], u["do"])
        else:
            slite.append(dict(u))
    return slite


def _sluc_angazma(zaznamy: list[dict]) -> list[dict]:
    """Sloučí verze téhož angažmá do jednoho záznamu s obdobími."""
    skupiny: dict[tuple, dict] = {}
    for z in zaznamy:
        klic = (z["osoba"]["_zaklad"], z["osoba"].get("_dn"), z["role"],
                z["organ"], (z["funkce"] or "").casefold())
        s = skupiny.get(klic)
        if s is None:
            s = skupiny[klic] = {
                "osoba": z["osoba"],
                "role": z["role"],
                "organ": z["organ"],
                "funkce": z["funkce"],
                "aktualni": False,
                "dle": z["dle"],
                "podil_procent": None,
                "vklad_czk": None,
                "_useky": [],
            }
        s["_useky"].append({"od": z["od"], "do": z["do"]})
        s["aktualni"] = s["aktualni"] or z["aktualni"]
        # Nejpřesnější zdroj data vyhrává: funkce > členství > zápis.
        if PRESNOST_DATA[z["dle"]] < PRESNOST_DATA[s["dle"]]:
            s["dle"] = z["dle"]
        if z["podil_procent"] is not None and z["aktualni"]:
            s["podil_procent"] = z["podil_procent"]
        if z["vklad_czk"] is not None and z["aktualni"]:
            s["vklad_czk"] = z["vklad_czk"]
        if z["funkce"] and not s["funkce"]:
            s["funkce"] = z["funkce"]

    out = []
    for s in skupiny.values():
        obdobi = _sluc_obdobi(s.pop("_useky"))
        s["obdobi"] = obdobi
        s["od"] = obdobi[0]["od"] if obdobi else None
        s["do"] = None if s["aktualni"] else (obdobi[-1]["do"] if obdobi else None)
        out.append(s)
    return out


def _dopln_data_narozeni_v_ramci_firmy(zaznamy: list[dict]) -> None:
    """Doplní chybějící datum narození uvnitř JEDNÉ firmy.

    Zápisy z devadesátých let datum narození často nemají — rejstřík ho
    tehdy nevedl. Když je ale v téže firmě pod stejným jménem právě jedno
    datum narození, jde skoro jistě o tutéž osobu (typicky starší verze
    téhož záznamu) a spojení je bezpečné.

    Přes hranici firmy se takhle nespojuje NIKDY. Že v jedné firmě byl
    v roce 1992 jednatel Jan Novák a v jiné je dnes společník Jan Novák,
    není důvod udělat z nich jednoho člověka.
    """
    podle_jmena: dict[str, set[str]] = {}
    for z in zaznamy:
        osoba = z["osoba"]
        if osoba["typ"] == "fyzicka" and osoba.get("_dn"):
            podle_jmena.setdefault(osoba["_zaklad"], set()).add(osoba["_dn"])
    for z in zaznamy:
        osoba = z["osoba"]
        if osoba["typ"] != "fyzicka" or osoba.get("_dn"):
            continue
        data = podle_jmena.get(osoba["_zaklad"])
        if data and len(data) == 1:
            osoba["_dn"] = next(iter(data))
            osoba["_dn_doplneno"] = True


def parsuj_vypis(ico: str, telo: dict, nezname: dict[str, int]) -> dict:
    """Převede odpověď ARES na náš formát. Datum narození drží jen v `_dn`."""
    zaznamy = telo.get("zaznamy") or []
    hlavni = [z for z in zaznamy if z.get("primarniZaznam")] or zaznamy

    surova: list[dict] = []
    nazev = stav = rejstrik = datum_zapisu = zpusob_rizeni = None
    spisova = soud = None
    kapital_czk = None
    kapital_text = None

    for z in hlavni:
        rejstrik = rejstrik or z.get("rejstrik")
        stav = stav or z.get("stavSubjektu")
        datum_zapisu = datum_zapisu or _datum(z.get("datumZapisu"))
        jmeno = _zivy(z.get("obchodniJmeno"))
        if jmeno and not nazev:
            nazev = jmeno.get("hodnota")
        zn = _zivy(z.get("spisovaZnacka"))
        if zn and not spisova:
            spisova = " ".join(str(x) for x in (zn.get("oddil"), zn.get("vlozka")) if x)
            soud = soud or zn.get("soud")
        rizeni = _zivy(z.get("zpusobRizeni"))
        if rizeni and not zpusob_rizeni:
            zpusob_rizeni = rizeni.get("typ")
        kapital = _zivy(z.get("zakladniKapital"))
        if kapital and kapital_czk is None and kapital_text is None:
            kapital_czk = _castka(kapital.get("vklad"))
            kapital_text = kapital.get("text")

        for sekce in ("statutarniOrgany", "ostatniOrgany", "spolecnici", "akcionari"):
            for organ in z.get(sekce) or []:
                surova += _zaznamy_organu(organ, sekce, nezname)

    _dopln_data_narozeni_v_ramci_firmy(surova)

    return {
        "ico": ico,
        "nazev": nazev,
        "rejstrik": rejstrik,
        "spisova_znacka": spisova,
        "soud": soud,
        "stav": stav,
        "datum_zapisu": datum_zapisu,
        "zpusob_rizeni": zpusob_rizeni,
        "zakladni_kapital_czk": kapital_czk,
        "zakladni_kapital_text": kapital_text,
        "zaznamu_v_rejstriku": len(zaznamy),
        "angazma": _sluc_angazma(surova),
    }


# --------------------------------------------------------------------------
# Rozlišení osob
# --------------------------------------------------------------------------

def prirad_klice(firmy: list[dict]) -> dict[str, dict]:
    """Přiřadí každé osobě klíč a přizná, nakolik je ztotožnění doložené.

    Postup je dvoufázový — jmenovce nejde poznat dřív, než se projdou všechny
    firmy. Pod jedním jménem vznikne tolik záznamů, kolik různých dat narození
    se ve výpisech objevilo, plus nanejvýš jeden záznam pro zápisy, které
    datum narození nemají vůbec (ty jsou skoro vždy z devadesátých let).

    `jednoznacna` je klíčové pole pro navazující přehled:

      true  — v našich datech je pod tímhle klíčem právě jeden doložený
              člověk: má datum narození a je jediný toho jména. Takovému
              člověku smí přehled přiřadit `osoba_id`.
      false — buď je jmenovců víc, nebo jde o zápisy bez data narození,
              které nešlo k nikomu přiřadit. `osoba_id` musí zůstat null
              a jméno se uvádí jako text.

    Přípony `-2`, `-3` nejsou trvalé identifikátory. Pořadí je dané datem
    narození, takže nový jmenovec ve zdroji jimi může pohnout.
    """
    varianty: dict[str, dict[str | None, dict]] = {}
    for firma in firmy:
        for a in firma["angazma"]:
            osoba = a["osoba"]
            bucket = varianty.setdefault(osoba["_zaklad"], {})
            zapis = bucket.setdefault(osoba.get("_dn"), {
                "jmeno": osoba["jmeno"], "typ": osoba["typ"],
                "ico": osoba.get("ico"), "angazma": 0, "firem": set(),
                "doplneno": 0,
            })
            zapis["angazma"] += 1
            zapis["firem"].add(firma["ico"])
            zapis["doplneno"] += 1 if osoba.get("_dn_doplneno") else 0
            # Delší tvar jména vyhrává — zdroj někdy vede jen iniciálu.
            if len(osoba["jmeno"]) > len(zapis["jmeno"]):
                zapis["jmeno"] = osoba["jmeno"]

    prirazeni: dict[str, dict[str | None, str]] = {}
    rejstrik: dict[str, dict] = {}
    for zaklad, bucket in sorted(varianty.items()):
        s_datem = sorted(dn for dn in bucket if dn)
        poradi = s_datem + ([None] if None in bucket else [])
        for i, dn in enumerate(poradi):
            klic = zaklad if i == 0 else f"{zaklad}-{i + 1}"
            prirazeni.setdefault(zaklad, {})[dn] = klic
            zapis = bucket[dn]
            pravnicka = zapis["typ"] == "pravnicka"
            rejstrik[klic] = {
                "osoba_klic": klic,
                "jmeno": zapis["jmeno"],
                "typ": zapis["typ"],
                "ico": zapis.get("ico"),
                "jednoznacna": bool(zapis.get("ico")) if pravnicka
                               else (dn is not None and len(s_datem) == 1),
                "rozliseni": (
                    "ico" if pravnicka and zapis.get("ico")
                    else "jen_nazev" if pravnicka
                    else "datum_narozeni" if dn is not None
                    else "bez_data_narozeni"
                ),
                "zaznamu_tehoz_jmena": len(poradi),
                "angazma": zapis["angazma"],
                "firem": len(zapis["firem"]),
            }

    # Druhá fáze: klíč do angažmá, datum narození pryč.
    for firma in firmy:
        for a in firma["angazma"]:
            osoba = a.pop("osoba")
            klic = prirazeni[osoba["_zaklad"]][osoba.get("_dn")]
            a["osoba_klic"] = klic
            a["jmeno"] = rejstrik[klic]["jmeno"]
            a["typ_osoby"] = osoba["typ"]
            a["ico_osoby"] = osoba.get("ico")
        firma["angazma"].sort(key=lambda a: (not a["aktualni"], a["role"],
                                             a["jmeno"] or ""))
    return rejstrik


def _zkontroluj_soukromi(obj: Any, cesta: str = "") -> None:
    """Pojistka: kdyby se do výstupu propsalo datum narození nebo adresa,
    běh skončí chybou. Radši nic než tichý únik osobních údajů."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ZAKAZANE_KLICE:
                raise ZdrojSelhal(f"do výstupu se dostal zakázaný údaj '{k}' ({cesta})")
            _zkontroluj_soukromi(v, f"{cesta}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _zkontroluj_soukromi(v, f"{cesta}[{i}]")


# --------------------------------------------------------------------------
# Běh
# --------------------------------------------------------------------------

def main() -> None:
    log = Log("podnikatele")
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    zdroj = nacti("firmy/subjekty.json")
    if not zdroj or not zdroj.get("subjekty"):
        raise ZdrojSelhal("chybí data/firmy/subjekty.json — nejdřív scrapers/firmy.py")
    dulezite = nacti("firmy/prehled/dulezite.json") or {}
    dulezite_ico = {f["ico"] for f in dulezite.get("firmy") or [] if f.get("ico")}
    if not dulezite_ico:
        log.chyba("data/firmy/prehled/dulezite.json chybí nebo je prázdný — "
                  "výběr stojí jen na právní formě")

    vybrane = vyber_firem(zdroj["subjekty"], dulezite_ico)
    if limit:
        vybrane = vybrane[:limit]
    log.info("vybráno k dotažení", firem=len(vybrane),
             pravnickych=sum(1 for v in vybrane
                             if "podnikatelska_pravnicka_osoba" in v["duvody"]),
             z_dulezitych=sum(1 for v in vybrane
                              if "prehled_dulezitych" in v["duvody"]))

    firmy: list[dict] = []
    bez_vypisu: list[dict] = []
    neznama_angazma: dict[str, int] = {}
    for i, v in enumerate(vybrane, 1):
        status, telo = _get_vr(v["ico"])
        if status == 404:
            bez_vypisu.append({"ico": v["ico"], "nazev": v["nazev"],
                               "duvod": "nenalezeno_v_rejstriku",
                               "duvody_vyberu": v["duvody"]})
        elif status != 200:
            bez_vypisu.append({"ico": v["ico"], "nazev": v["nazev"],
                               "duvod": f"http_{status}",
                               "duvody_vyberu": v["duvody"]})
            log.chyba(f"výpis {v['ico']} vrátil HTTP {status}")
        else:
            firma = parsuj_vypis(v["ico"], telo, neznama_angazma)
            firma["nazev"] = firma["nazev"] or v["nazev"]
            firma["duvody_vyberu"] = v["duvody"]
            firmy.append(firma)
        if i % 200 == 0:
            log.info("průběh", hotovo=i, z=len(vybrane), s_vypisem=len(firmy))

    if neznama_angazma:
        log.info("neznámé typy angažmá (uloženy jako jiny_organ)", **neznama_angazma)

    rejstrik = prirad_klice(firmy)
    osoby = sorted(rejstrik.values(), key=lambda o: (-o["angazma"], o["osoba_klic"]))
    fyzickych = [o for o in osoby if o["typ"] == "fyzicka"]
    jmenovcu = [o for o in fyzickych if o["zaznamu_tehoz_jmena"] > 1]

    vystup = {
        "generovano": time.strftime("%Y-%m-%d"),
        "zdroj": "ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty-vr/{ico}",
        "vyber": {
            "kriterium": (
                "podnikatelské právnické osoby se sídlem ve městě (právní forma "
                "není fyzická osoba ani forma, která ze své podstaty nepodniká) "
                "SJEDNOCENO s firmami z data/firmy/prehled/dulezite.json"
            ),
            "zdroj_vyberu": ["data/firmy/subjekty.json",
                             "data/firmy/prehled/dulezite.json"],
            "subjektu_ve_meste_celkem": len(zdroj["subjekty"]),
            "dotazovano": len(vybrane),
            "s_vypisem": len(firmy),
            "bez_vypisu": len(bez_vypisu),
            "poznamka": (
                "Nedotazované subjekty jsou živnostníci a nepodnikatelské formy "
                "mimo přehled důležitých. Výpis z veřejného rejstříku pro ně "
                "neexistuje, takže jejich nepřítomnost není mezera v datech."
            ),
        },
        "osobni_udaje": {
            "co_se_neuklada": (
                "Datum narození ani adresa bydliště. ARES je vrací, projekt je "
                "zahazuje — na web nepatří a k ničemu tu nejsou potřeba."
            ),
            "rozliseni_jmenovcu": (
                "Datum narození se používá jen v paměti k rozlišení dvou lidí "
                "téhož jména a pak se zahazuje. Kdo nemá jednoznacna=true, "
                "nesmí dostat osoba_id ani se ztotožnit s osobou z databáze "
                "osobností — pod jedním jménem je v datech víc lidí, nebo jde "
                "o starý zápis bez data narození."
            ),
            "zapisy_bez_data_narozeni": (
                "Rejstřík u zápisů z devadesátých let datum narození nevede. "
                "Uvnitř jedné firmy se takový zápis přiřadí k jedinému člověku "
                "téhož jména; přes hranici firmy se nespojuje nikdy a zůstane "
                "samostatným záznamem s jednoznacna=false."
            ),
            "co_je_verejne": (
                "Jméno, funkce, období a firma jsou veřejné údaje z veřejného "
                "rejstříku. Uvádí se jako fakt, bez hodnocení."
            ),
        },
        "souhrn": {
            "firem_s_vypisem": len(firmy),
            "angazma_celkem": sum(len(f["angazma"]) for f in firmy),
            "osob_fyzickych": len(fyzickych),
            "osob_pravnickych": len(osoby) - len(fyzickych),
            "osob_jednoznacnych": sum(1 for o in fyzickych if o["jednoznacna"]),
            "zaznamu_se_jmenovcem": len(jmenovcu),
            "zaznamu_bez_data_narozeni": sum(1 for o in fyzickych
                                             if o["rozliseni"] == "bez_data_narozeni"),
        },
        "osoby": osoby,
        "firmy": sorted(firmy, key=lambda f: f["ico"]),
        "bez_vypisu": sorted(bez_vypisu, key=lambda f: f["ico"]),
    }

    _zkontroluj_soukromi(vystup)
    uloz("podnikatele/vypisy.json", vystup)

    log.info("hotovo", firem=len(firmy), osob=len(fyzickych),
             angazma=vystup["souhrn"]["angazma_celkem"], jmenovcu=len(jmenovcu),
             bez_vypisu=len(bez_vypisu))
    log.pricti(len(firmy))
    log.uzavri()


if __name__ == "__main__":
    main()
