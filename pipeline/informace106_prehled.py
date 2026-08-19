"""Rozbor odpovědí podle zákona 106/1999 Sb.

CO SE Z TOHO DÁ ČÍST
--------------------
Zveřejněná odpověď má pravidelnou stavbu a nese tři věci:

  Předmět žádosti     — NA CO se někdo ptal
  Poskytnuté informace — co úřad odpověděl (nebo že odmítl)
  Informace poskytl(a) — který odbor a kdo za něj

Z toho se dá zjistit, čím se lidi zabývají natolik, že si o to museli
napsat, a který odbor dostává nejvíc dotazů. Je to jediné místo, kde je
vidět poptávka po informacích — všude jinde je vidět jen nabídka.

CO SE NESLEDUJE
---------------
Žadatel. Jméno fyzické osoby odstraňuje už sběrač (`scrapers/informace106.py`),
tenhle modul s ním nepracuje ani ho nedopočítává. Ptát se úřadu je zákonné
právo a přehled z jeho výkonu nedělá veřejnou stopu.

Jméno úředníka, který informaci poskytl, se naopak ponechává — je to výkon
funkce a odbor bez člověka by byl anonymní úřad.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import DATA, Log, nacti, uloz  # noqa: E402

# Pole odpovědi. Hodnota jde od dvojtečky po další známý nadpis.
_POLE = [
    ("predmet", r"P[řr]edm[ěe]t\s+[žz][áa]dosti"),
    ("odpoved", r"Poskytnut[éeá]\s+informac\w*"),
    ("poskytl", r"Informace\s+poskyt\w+"),
]
_VSECHNY = re.compile(
    r"(?i)(" + "|".join(v for _, v in _POLE) + r"|Zve[řr]ejn[ěe]n[íi]\s+informac)\s*:?"
)

_CJ = re.compile(r"(?i)č\.\s?j\.\s*([A-Za-zÁ-Žá-ž0-9/\-]+)")
_SPIS = re.compile(r"(?i)spis\.?\s*zn\.?\s*([A-Za-zÁ-Žá-ž0-9/\-]+)")

# Odbor se NEHÁDÁ z textu, přiřazuje se k seznamu odborů úřadu.
#
# První verze brala volný vzor „odbor…" a vytáhla z textu „Odboru olsažu"
# a „Odboru životního prostředí městského úřadu mariánské". Volný vzor si
# vymýšlí názvy; seznam odborů je známý (data/mesto/urad.json) a stačí
# hledat, který z nich se ve větě vyskytuje.
#
# Útvary, které v seznamu nejsou, ale odpovídají (městská policie), jsou
# doplněné ručně — je jich pár a je to vidět.
RUCNI_UTVARY = ["Městská policie"]


def _slovnik_odboru() -> list[tuple[str, str]]:
    """(normalizovaný tvar, název k zobrazení), od nejdelšího názvu.

    Od nejdelšího proto, že „Odbor stavebního úřadu" obsahuje „Odbor" —
    kdyby se hledalo od nejkratšího, spadlo by všechno do prvního odboru
    v seznamu.
    """
    urad = nacti("mesto/urad.json") or {}
    nazvy = [o.get("nazev") for o in (urad.get("odbory") or []) if o.get("uroven")]
    nazvy = [n for n in nazvy if n] + RUCNI_UTVARY
    slovnik = [(_bez_diakritiky(n), n) for n in nazvy]
    return sorted(slovnik, key=lambda x: -len(x[0]))


# Délka kmene, na kterou se slova zkracují při porovnání. Pět znaků
# odliší „odbor" od „oddělení" a přitom sedne na všechny pády:
# odbor/odboru, prostředí/prostředím, dopravy/doprava.
KMEN = 5


def _kmeny(text: str) -> list[str]:
    return [w[:KMEN] for w in _bez_diakritiky(text).split() if len(w) >= KMEN]


def _urci_odbor(veta: str, slovnik: list[tuple[str, str]]) -> str | None:
    """Který útvar úřadu větu podepsal.

    Porovnává se na kmenech slov, protože věta je skloňovaná („informace
    poskytl odbor**u** životní**ho** prostředí"), kdežto seznam odborů je
    v prvním pádě. Prosté hledání podřetězce proto minulo 87 z 98 žádostí.

    Vybírá se VŽDY ze seznamu odborů; když se žádný netrefí, vrací se
    `None`. Vymyslet název by bylo horší než ho neuvést.
    """
    if not veta:
        return None
    kmeny_vety = _kmeny(veta)
    if not kmeny_vety:
        return None
    for klic, nazev in slovnik:
        kmeny_odboru = _kmeny(klic)
        # Všechna významová slova názvu musí být ve větě. Jedno slovo by
        # nestačilo — „odbor" je v každé.
        if len(kmeny_odboru) >= 2 and all(k in kmeny_vety for k in kmeny_odboru):
            return nazev
    return None

# Odmítnutí se pozná ze slovesa. Je to jediný údaj, kde odpověď říká „ne“.
_ODMITNUTO = re.compile(
    r"(?i)\b(odm[íi]tnut|neposkyt|nevyhov|zam[íi]tnut|částečně\s+odm[íi]t)"
)


def _bez_diakritiky(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn"
    ).lower()


def _pole(text: str) -> dict[str, str | None]:
    ven: dict[str, str | None] = {}
    for klic, vzor in _POLE:
        m = re.search(r"(?i)" + vzor + r"\s*:?\s*", text)
        if not m:
            ven[klic] = None
            continue
        zbytek = text[m.end():]
        dalsi = _VSECHNY.search(zbytek)
        hodnota = zbytek[: dalsi.start()] if dalsi else zbytek[:600]
        hodnota = re.sub(r"\s+", " ", hodnota).strip(" .,;–—-")
        ven[klic] = hodnota or None
    return ven


def rozeber(zaznam: dict, slovnik_odboru: list[tuple[str, str]]) -> dict:
    text = zaznam.get("text") or ""
    pole = _pole(text)
    cj = _CJ.search(text)
    spis = _SPIS.search(text)

    poskytl = pole.get("poskytl") or ""

    return {
        "id": zaznam.get("url", "").split("file=")[-1][:40],
        "nadpis": zaznam.get("nadpis"),
        "vlozeno": zaznam.get("vlozeno"),
        "url": zaznam.get("url"),
        "stazeno": zaznam.get("stazeno"),
        "cislo_jednaci": cj.group(1) if cj else None,
        "spisova_znacka": spis.group(1) if spis else None,
        "predmet": pole.get("predmet"),
        "odpoved": pole.get("odpoved"),
        "poskytl": poskytl or None,
        # Odbor se bere z věty o tom, kdo informaci poskytl. Když ji zápis
        # nemá, zůstává `null` — „neurčeno" by vypadalo jako zjištěný údaj.
        "odbor": _urci_odbor(poskytl, slovnik_odboru),
        # Odmítnutí je jediné místo, kde odpověď říká „ne". Poznává se ze
        # slovesa v textu odpovědi, ne z rozhodnutí — úplný výrok je v PDF.
        "odmitnuto": bool(_ODMITNUTO.search(pole.get("odpoved") or text)),
        "zadatel_skryt": bool(zaznam.get("zadatel_odstranen") or zaznam.get("zadatel_skryt_v_textu")),
        "rozebrano": bool(pole.get("predmet") or pole.get("odpoved")),
    }


def main() -> None:
    log = Log("informace106_prehled")

    koren = DATA / "informace106" / "texty"
    if not koren.exists():
        log.chyba("data/informace106/texty neexistuje — nejdřív scrapers/informace106.py")
        log.uzavri()
        return

    zaznamy = []
    for soubor in sorted(koren.glob("*.json")):
        try:
            zaznamy.append(json.loads(soubor.read_text(encoding="utf-8")))
        except Exception as e:  # noqa: BLE001
            log.chyba(f"{soubor.name}: {e}")

    slovnik = _slovnik_odboru()
    if not slovnik:
        log.chyba("data/mesto/urad.json nemá odbory — odbory u žádostí zůstanou prázdné")
    rozebrane = [rozeber(z, slovnik) for z in zaznamy]
    rozebrane.sort(key=lambda r: (r["vlozeno"] or ""), reverse=True)

    rejstrik = json.loads((DATA / "informace106" / "rejstrik.json").read_text(encoding="utf-8"))
    v_rejstriku = int(rejstrik.get("celkem") or 0)

    po_odborech: Counter[str] = Counter()
    po_letech: Counter[str] = Counter()
    for r in rozebrane:
        po_odborech[r["odbor"] or "odbor neuveden"] += 1
        if r["vlozeno"]:
            po_letech[r["vlozeno"][:4]] += 1

    nerozebrano = [r for r in rozebrane if not r["rozebrano"]]
    odmitnuto = [r for r in rozebrane if r["odmitnuto"]]

    uloz("informace106/prehled.json", {
        "metodika": {
            "co_to_je": (
                "Rozbor informací poskytnutých podle zákona 106/1999 Sb. Vytahuje "
                "předmět žádosti, odpověď úřadu a odbor, který ji vyřídil."
            ),
            "zadatel": (
                "Jméno fyzické osoby se nesleduje a v datech není — odstraňuje ho už "
                "sběrač. Jméno úředníka, který informaci poskytl, zůstává: je to výkon "
                "funkce."
            ),
            "odmitnuto": (
                "Poznává se ze slovesa v textu odpovědi („odmítnuto“, „neposkytnuto“, "
                "„nevyhověno“). Není to výrok rozhodnutí — ten je v PDF. Ber to jako "
                "vodítko, ne jako právní závěr."
            ),
            "odbor": (
                "Přiřazuje se k seznamu odborů úřadu (data/mesto/urad.json), nehádá se "
                "z textu. Odbor, který se nepodařilo přiřadit, zůstává prázdný — vymyslet "
                "název by bylo horší než ho neuvést."
            ),
            "pokryti": (
                f"Web města má v rejstříku {v_rejstriku} dokumentů, textovou vrstvu má "
                f"{len(rozebrane)}. Zbytek jsou skeny; bez OCR z nich text nedostaneme "
                "a nepředstírá se, že tam nic není."
            ),
        },
        "souhrn": {
            "v_rejstriku": v_rejstriku,
            "s_textem": len(rozebrane),
            "rozebranych": len(rozebrane) - len(nerozebrano),
            "odmitnuto": len(odmitnuto),
            "se_skrytym_zadatelem": sum(1 for r in rozebrane if r["zadatel_skryt"]),
            "po_odborech": dict(po_odborech.most_common()),
            "po_letech": dict(sorted(po_letech.items())),
        },
        "zadosti": rozebrane,
    })

    log.pricti(len(rozebrane))
    log.info("žádostí rozebráno", pocet=len(rozebrane) - len(nerozebrano))
    log.info("z toho odmítnutých nebo částečných", pocet=len(odmitnuto))
    if nerozebrano:
        log.info("bez rozeznatelné struktury", pocet=len(nerozebrano))
    log.uzavri()


if __name__ == "__main__":
    main()
