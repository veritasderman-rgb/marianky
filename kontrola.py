"""Kontrola dat před publikací.

Pojistka mezi týdenním během a nasazením webu. Když neprojde, web se
nemá publikovat — lepší je nechat venku minulé číslo než vydat nové
s tichou lží.

Každá kontrola tu je proto, že odpovídající chyba **se v tomhle projektu
opravdu stala**. Nejsou to hypotetické stavy, ale seznam už jednou
zaplacených omylů:

  * částky slepené s letopočtem — rozpočet vycházel na 2 020 700 000 Kč
  * částky rozdělené na tisícinásobek — 397 mil. se zobrazovalo jako 938 tis.
  * účetní kódy spolknuté do částky — 190 tis. vyšlo jako 209 mil.
  * neznámý údaj uložený jako `false` — 6 521 smluv tvrdilo „ověřeno,
    že vazba na politiky není", ačkoliv to zdroj vůbec nevyplňuje
  * sběrač četl archiv místo živé stránky — úřední deska stála 15 měsíců
    a sekce vypadala, že se ve městě nic neděje
  * lidé s tisíci hlasy bez profilu — data na sebe nesedla

Spuštění:
    python3 kontrola.py            # projde, nebo vypíše, co je špatně
    python3 kontrola.py --tvrde    # varování se počítají jako chyby
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.core import DATA, nacti  # noqa: E402

# Rozpočet celého města je ve stovkách milionů. Jediný bod usnesení nad
# miliardu v třináctitisícovém městě znamenal vždycky špatně přečtené číslo.
STROP_CASTKY = 1_000_000_000

# Jak dlouho smí být zdroj bez pohybu, než to začne být podezřelé.
# Odpovídá tomu, jak často se který zdroj reálně mění.
STARI_DNI = {
    "usneseni": 75,        # rada zasedá po ~2 týdnech, zastupitelstvo po ~2 měsících
    "uredni-deska": 21,    # deska se mění téměř denně
    "media": 45,
}


class Vysledek:
    def __init__(self) -> None:
        self.chyby: list[str] = []
        self.varovani: list[str] = []
        self.ok: list[str] = []

    def chyba(self, text: str) -> None:
        self.chyby.append(text)

    def varuj(self, text: str) -> None:
        self.varovani.append(text)

    def projde(self, text: str) -> None:
        self.ok.append(text)


def _body_usneseni():
    for f in glob.glob(str(DATA / "usneseni" / "*" / "*" / "*.json")):
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for b in d.get("body", []):
            yield d, b


# --------------------------------------------------------------------------

def kontrola_castek(v: Vysledek) -> None:
    """Nesmyslné částky v usneseních."""
    velke = [(d["datum"], b.get("nazev"), b["castka_czk"])
             for d, b in _body_usneseni()
             if b.get("castka_czk") and b["castka_czk"] > STROP_CASTKY]
    if velke:
        v.chyba(f"{len(velke)} bodů usnesení má částku nad miliardu — "
                f"skoro jistě špatně vyparsované číslo. Např. "
                f"{velke[0][0]}: {velke[0][2]:,.0f} Kč u „{(velke[0][1] or '')[:50]}“")
    else:
        v.projde("žádná částka v usneseních nepřesahuje miliardu")

    # Rozpočet města je dobrý kontrolní bod, ale jen tam, kde je jeho výše
    # v textu opravdu napsaná. Od roku 2023 zastupitelstvo schvaluje
    # rozpočet „dle přílohy k usnesení“ a v textu pak zůstane jen Fond
    # z pobytu — částka je správně vyparsovaná, jen to není rozpočet.
    # Kontrolujeme proto výhradně usnesení, která celkovou výši uvádějí.
    rozpocty = [(d["datum"], b["castka_czk"]) for d, b in _body_usneseni()
                if "Rozpočet města" in (b.get("nazev") or "")
                and b.get("castka_czk")
                and ("celkové příjmy" in (b.get("text") or "")
                     or "celkové výdaje" in (b.get("text") or ""))]
    mimo = [r for r in rozpocty if not (1e8 <= r[1] <= 1e9)]
    if mimo:
        v.chyba(f"{len(mimo)} rozpočtů města je mimo očekávaný řád stovek milionů "
                f"(např. {mimo[0][0]}: {mimo[0][1]:,.0f} Kč) — "
                f"nejspíš rozpadlý převod jednotek „tis. Kč“")
    elif rozpocty:
        v.projde(f"{len(rozpocty)} rozpočtů s uvedenou výší je v řádu stovek milionů")

    # Ta příloha je ale sama o sobě zpráva pro web: u těch let se u bodu
    # „Rozpočet města“ zobrazí částka Fondu z pobytu, ne rozpočet. Číslo
    # je pravdivé, čtenář si ho ale spojí s nadpisem a bude uveden v omyl.
    v_priloze = [d["datum"] for d, b in _body_usneseni()
                 if "Rozpočet města" in (b.get("nazev") or "")
                 and b.get("castka_czk")
                 and "dle přílohy" in (b.get("text") or "")]
    if v_priloze:
        v.varuj(f"{len(v_priloze)} usnesení o rozpočtu má výši jen v příloze "
                f"({', '.join(sorted(v_priloze)[-3:])}). Částka u bodu je správná, "
                f"ale NENÍ to rozpočet — web ji u těchto bodů nemá vydávat za jeho výši")


def kontrola_falesnych_nul(v: Vysledek) -> None:
    """Neznámý údaj se nesmí tvářit jako zjištěná nula."""
    falesne = 0
    for f in glob.glob(str(DATA / "penize" / "smlouvy" / "*.json")):
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        falesne += sum(1 for s in d.get("smlouvy", [])
                       if s.get("vazba_na_politiky") is False)
    if falesne:
        v.chyba(f"{falesne} smluv má „vazba_na_politiky: false“. Hlídač to pole "
                f"přes API nevyplňuje, takže to není ověřená nula, ale neznámo — "
                f"patří tam null")
    else:
        v.projde("neznámé údaje se neukládají jako nula")


def kontrola_stari(v: Vysledek) -> None:
    """Zdroj, který se dávno nehnul, znamená rozbitý sběrač."""
    dnes = date.today()

    def stari(nejnovejsi: str | None) -> int | None:
        if not nejnovejsi:
            return None
        try:
            return (dnes - date.fromisoformat(nejnovejsi[:10])).days
        except ValueError:
            return None

    # usnesení
    data_jednani = [d.get("datum") for d, _ in _body_usneseni() if d.get("datum")]
    if data_jednani:
        dni = stari(max(data_jednani))
        if dni is not None and dni > STARI_DNI["usneseni"]:
            v.varuj(f"poslední jednání je staré {dni} dní — ověř, jestli sběrač usnesení běží")
        else:
            v.projde(f"usnesení jsou čerstvá (poslední jednání před {dni} dny)")

    # úřední deska
    deska = nacti("mesto/uredni-deska.json")
    if deska is None:
        v.chyba("chybí data úřední desky")
    else:
        polozky = deska if isinstance(deska, list) else deska.get("polozky", [])
        nej = max((p.get("vyveseno_od") or "" for p in polozky), default="")
        dni = stari(nej)
        if dni is None:
            v.chyba("úřední deska nemá použitelná data vyvěšení")
        elif dni > STARI_DNI["uredni-deska"]:
            v.chyba(f"úřední deska se {dni} dní nehnula (poslední {nej}). "
                    f"Pozor: živá deska je /urad/uredni-deska/, archiv složek "
                    f"/urad/uredni-deska-archiv/ končí rokem 2025")
        else:
            v.projde(f"úřední deska je aktuální (poslední záznam {nej})")


def kontrola_provazani(v: Vysledek) -> None:
    """Odkazy mezi datovými sadami musí sedět."""
    osoby = {o["id"] for o in (nacti("lide/osobnosti.json") or [])}
    if not osoby:
        v.chyba("chybí databáze osobností")
        return

    hlasujici: dict[str, int] = {}
    for f in glob.glob(str(DATA / "hlasovani" / "*" / "*" / "*.json")):
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for h in d.get("hlasovani", []):
            for j in h.get("jmenovite") or []:
                hlasujici[j["osoba_id"]] = hlasujici.get(j["osoba_id"], 0) + 1

    chybi = {k: n for k, n in hlasujici.items() if k not in osoby}
    if chybi:
        nej = sorted(chybi.items(), key=lambda x: -x[1])[:3]
        v.varuj(f"{len(chybi)} z {len(hlasujici)} hlasujících nemá profil "
                f"(např. {', '.join(f'{k} — {n} hlasů' for k, n in nej)}) — "
                f"web jim nepostaví stránku")
    else:
        v.projde(f"všech {len(hlasujici)} hlasujících má profil")


def kontrola_tagu(v: Vysledek) -> None:
    """Tagy se vybírají z číselníku, nikdy nevymýšlejí."""
    platne = {t["id"] for t in (nacti("../config/tagy.json") or json.loads(
        (Path(__file__).parent / "config" / "tagy.json").read_text(encoding="utf-8")))["tagy"]} \
        if False else {t["id"] for t in json.loads(
            (Path(__file__).parent / "config" / "tagy.json").read_text(encoding="utf-8"))["tagy"]}

    cizi: set[str] = set()
    for _, b in _body_usneseni():
        cizi |= {t for t in (b.get("tagy") or []) if t not in platne}
    if cizi:
        v.chyba(f"v usneseních je {len(cizi)} tagů mimo číselník: {sorted(cizi)[:5]} — "
                f"filtrování podle témat tím přestane fungovat")
    else:
        v.projde("všechny tagy jsou z číselníku")


def kontrola_vydani(v: Vysledek) -> None:
    """Vydání musí existovat a přiznat, co v něm chybí."""
    index = nacti("vydani/index.json")
    if not index:
        v.chyba("chybí index vydání — týdenní číslo nevzniklo")
        return

    posledni = nacti(f"vydani/{index[0]['id']}.json")
    if not posledni:
        v.chyba("poslední vydání se nepodařilo načíst")
        return

    problem = [s for s in posledni["sekce"] if s["stav"] in ("chybi", "zastarale")]
    if problem:
        v.varuj(f"poslední vydání má {len(problem)} sekcí bez dat: "
                f"{', '.join(s['nadpis'] for s in problem)}. "
                f"Vydání to přiznává, ale zkontroluj, jestli je to záměr")
    else:
        v.projde(f"poslední vydání ({posledni['id']}) má všechny sekce s daty")


def kontrola_souradnic(v: Vysledek) -> None:
    """Body musí padnout do Mariánských Lázní, ne do Prahy nebo do moře."""
    soubory = glob.glob(str(DATA / "opendata" / "**" / "*.geojson"), recursive=True)
    if not soubory:
        return
    mimo = 0
    celkem = 0
    for f in soubory:
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for prvek in d.get("features", []):
            g = prvek.get("geometry") or {}
            if g.get("type") != "Point":
                continue
            lon, lat = g["coordinates"][:2]
            celkem += 1
            if not (12.4 < lon < 13.0 and 49.8 < lat < 50.2):
                mimo += 1
    if mimo:
        v.chyba(f"{mimo} z {celkem} bodů leží mimo okolí Mariánských Lázní — "
                f"nejspíš rozbitý převod souřadnic")
    elif celkem:
        v.projde(f"všech {celkem} bodů padlo do okolí Mariánských Lázní")


def kontrola_znaku(v: Vysledek) -> None:
    """Znak sekce nesmí kreslit konstantu a vydávat ji za vývoj.

    Stalo se: znak hlasování ukazoval „podíl schválených návrhů" — jenže
    zdroj zveřejňuje jen schválená hlasování, takže podíl byl vždy 100 %.
    Mřížka vyšla ve všech letech stejně sytá a budila dojem, že se něco
    měří. Kontrola hlídá, že každý znak má v datech aspoň dvě různé
    hodnoty; jinak není co kreslit a patří tam číslo, ne graf.
    """
    cesta = DATA / "znaky" / "sekce.json"
    if not cesta.exists():
        v.varovani("znaky sekcí zatím nejsou spočítané "
                   "(pipeline/znaky_sekci.py) — rozcestník bude bez obrázků")
        return
    try:
        znaky = (json.loads(cesta.read_text(encoding="utf-8")) or {}).get("znaky") or {}
    except (json.JSONDecodeError, OSError) as e:
        v.chyba(f"data/znaky/sekce.json nejde přečíst: {e}")
        return

    ploche: list[str] = []
    for klic, z in znaky.items():
        if z.get("stav") != "ok":
            continue
        hodnoty = [h for h in (z.get("hodnoty") or []) if h is not None]
        hodnoty += [b.get("v") for b in (z.get("bunky") or []) if b.get("v") is not None]
        hodnoty += [b.get("v") for b in (z.get("policka") or []) if b.get("v") is not None]
        # Tvary bez číselné řady (mapa, řetěz, síť, úseky, tečky) se neměří —
        # jejich obsahem není vývoj v čase.
        if len(hodnoty) >= 3 and len(set(hodnoty)) == 1:
            ploche.append(klic)

    if ploche:
        v.chyba("znak kreslí ve všech bodech stejnou hodnotu, takže tvrdí vývoj, "
                f"který v datech není: {', '.join(sorted(ploche))}")
    else:
        v.projde(f"znaky sekcí ({len(znaky)}) nekreslí konstantu")


KONTROLY = [
    ("částky v usneseních", kontrola_castek),
    ("falešné nuly", kontrola_falesnych_nul),
    ("stáří zdrojů", kontrola_stari),
    ("provázání dat", kontrola_provazani),
    ("číselník tagů", kontrola_tagu),
    ("týdenní vydání", kontrola_vydani),
    ("souřadnice", kontrola_souradnic),
    ("znaky sekcí", kontrola_znaku),
]


def main() -> int:
    p = argparse.ArgumentParser(description="Kontrola dat před publikací")
    p.add_argument("--tvrde", action="store_true",
                   help="varování se počítají jako chyby")
    args = p.parse_args()

    v = Vysledek()
    print("=" * 66)
    print("  KONTROLA DAT PŘED PUBLIKACÍ")
    print("=" * 66)

    for nazev, fn in KONTROLY:
        try:
            fn(v)
        except Exception as e:  # noqa: BLE001
            v.chyba(f"kontrola „{nazev}“ sama spadla: {e}")

    for text in v.ok:
        print(f"  ✓  {text}")
    for text in v.varovani:
        print(f"  !  {text}")
    for text in v.chyby:
        print(f"  ✗  {text}")

    print("=" * 66)
    selhalo = bool(v.chyby) or (args.tvrde and bool(v.varovani))
    if selhalo:
        print("  NEPROŠLO — web nepublikovat, dokud se to nespraví.")
    else:
        print(f"  V pořádku. {len(v.ok)} kontrol prošlo, {len(v.varovani)} varování.")
    print("=" * 66)
    return 1 if selhalo else 0


if __name__ == "__main__":
    raise SystemExit(main())
