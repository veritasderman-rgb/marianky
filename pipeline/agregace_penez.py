"""Agregace peněz — kdo kolik a kdy od města dostal (a kdo kolik městu zaplatil).

Vstup:  `data/penize/smlouvy/{ico}.json` (vyrábí `scrapers/hlidac.py`)
Výstup: `data/penize/agregace/protistrany.json`  — formát viz docs/PLAN.md
        `data/penize/agregace/souhrn.json`       — podklad pro dashboard

--------------------------------------------------------------------------
!!! ČTENÁŘI GRAFŮ: CHYBĚJÍCÍ ROK V `po_letech` ZNAMENÁ NULU !!!
--------------------------------------------------------------------------
`po_letech` je řídká mapa — rok, ve kterém protistrana nedostala nic, v ní
prostě není. Nuly do dat nedoplňujeme (bylo by to dopočítané číslo tvářící se
jako údaj ze zdroje) a nedá se ani odlišit od „rok mimo sledované období".

Frontend proto MUSÍ osu vykreslit přes celý rozsah `rozsah_let` ze souhrnu
a chybějící roky dokreslit jako **nulu**, ne je z osy vynechat. Když se roky
přeskočí, časová osa lže: firma, která brala peníze v roce 2017 a pak až
v roce 2025, by v grafu vypadala jako plynulý dodavatel dvou po sobě jdoucích
období. Totéž platí pro `souhrn.json` → `po_letech`.

--------------------------------------------------------------------------
Slučování protistran
--------------------------------------------------------------------------
Firmy se přejmenovávají — ve sledovaných datech je toho příkladem IČO 25208438,
které vystupuje jednou jako „KIS Mariánské Lázně s.r.o.", jindy jako
„Infocentrum Mariánské Lázně s.r.o.". Protistrany se proto slučují **podle IČO**.
Když IČO ve zdroji chybí (fyzické osoby, cizí subjekty), sloučí se podle
normalizovaného názvu (`core.slug`) a záznam to přizná polem `klic_dle`.
Zobrazovaný název je ten z nejnovější smlouvy — firma se jmenuje tak, jak se
jmenuje dnes.

--------------------------------------------------------------------------
Co se počítá do holdingu
--------------------------------------------------------------------------
Nemocnice Mariánské Lázně (IČO 26376709) už městu nepatří (`vlastnictvi:
"mimo_mesto"`), takže do součtů holdingu nevstupuje — bere se
`core.sledovane_subjekty(vcetne_mimo_mesto=False)`. Sledujeme ji dál,
její soubory se jen agregují zvlášť do `nemocnice.json`.
"""
from __future__ import annotations

import datetime as _dt

import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import DATA, Log, ZdrojSelhal, nacti, slug, sledovane_subjekty, uloz  # noqa: E402

# „Aktivní" = od města dostala peníze v posledních 12 měsících.
OKNO_AKTIVNI_DNI = 365



# Registr smluv obsahuje nesmyslná data podpisu — ověřeno: v datech jsou
# roky jako "0025" nebo "26". Bez filtru se osa grafu roztáhne od roku 2
# do 2026 a graf přestane být čitelný, případně tvrdí, že firma začala
# brát peníze ve starověku. Neplatné datum proto považujeme za NEZNÁMÉ
# (smlouva se dál počítá do součtů), a kolik jich bylo, se hlásí ve
# výstupu — zahodit je potichu by byla jiná lež než ta původní.
ROK_OD, ROK_DO = 1990, _dt.date.today().year + 1


def _rozumne_datum(datum: str | None, pocitadlo: dict) -> str:
    d = (datum or "").strip()
    if not d or not d[:4].isdigit():
        return ""
    rok = int(d[:4])
    if not (ROK_OD <= rok <= ROK_DO):
        pocitadlo["nesmyslne_datum"] = pocitadlo.get("nesmyslne_datum", 0) + 1
        return ""
    return d


def _nacti_smlouvy(ica: list[str]) -> dict[str, dict]:
    """Načte soubory smluv daných subjektů. Chybějící soubor je chyba, ne prázdno."""
    out = {}
    for ico in ica:
        obsah = nacti(f"penize/smlouvy/{ico}.json")
        if obsah is None:
            raise ZdrojSelhal(
                f"Chybí data/penize/smlouvy/{ico}.json — nejdřív spusť scrapers/hlidac.py"
            )
        out[ico] = obsah
    return out


def _klic(smlouva: dict) -> tuple[str, str]:
    """Klíč protistrany: primárně IČO, jinak normalizovaný název."""
    ico = (smlouva.get("protistrana_ico") or "").strip()
    if ico:
        return ("ico", ico)
    nazev = (smlouva.get("protistrana") or "").strip()
    return ("nazev", slug(nazev) if nazev else "neuvedena")


def agreguj_protistrany(log: Log, k_datu: date | None = None) -> dict:
    holding = sledovane_subjekty(vcetne_mimo_mesto=False)
    ica_holdingu = [s["ico"] for s in holding]
    nazvy_holdingu = {s["ico"]: s["nazev"] for s in holding}
    soubory = _nacti_smlouvy(ica_holdingu)

    k_datu = k_datu or datetime.now(timezone.utc).date()
    hranice_aktivity = (k_datu - timedelta(days=OKNO_AKTIVNI_DNI)).isoformat()

    # Kolik smluv mělo nesmyslné datum podpisu (vada přímo v registru).
    zahozena_data: dict = {}

    # (smer, klic) -> hromádka
    hromady: dict[tuple, dict] = {}

    for ico_subjektu, obsah in soubory.items():
        for s in obsah.get("smlouvy", []):
            smer = s.get("smer")
            if smer not in ("vydaj", "prijem"):
                continue
            # Nájmy, pachty a prodeje majetku mají v registru nespolehlivý
            # směr: zveřejňovatel (město) se zapisuje jako plátce i tam, kde
            # peníze inkasuje. Z Café Classic tak vycházelo, že jí město platí
            # 16 milionů, přitom kavárna platí nájem městu. Takové smlouvy
            # dostávají vlastní směr `neurcen` — nevíme, kdo komu platil,
            # a tvrdit jedno z toho by bylo horší než to přiznat.
            if s.get("smer_jistota") == "neprukazne":
                smer = "neurcen"
            klic = _klic(s)
            h = hromady.setdefault((smer, klic), {
                "klic_dle": klic[0],
                "ico": klic[1] if klic[0] == "ico" else None,
                "nazev": None,
                "nazev_datum": "",
                "smer": smer,
                "po_letech": defaultdict(float),
                "smluv": 0,
                "bez_ceny": 0,
                "vadnych": 0,
                "subjekty": set(),
                "smlouvy_id": set(),
                "prvni_datum": None,
                "posledni_datum": None,
                "drive_nazvy": set(),
            })
            h["subjekty"].add(ico_subjektu)

            # Jedna smlouva může být zapsaná u víc subjektů holdingu naráz
            # (např. kraj uzavře smlouvu s městem i s jeho příspěvkovkou).
            # Peníze i počet smluv se proto počítají jen jednou.
            if s["id"] in h["smlouvy_id"]:
                continue
            h["smlouvy_id"].add(s["id"])
            h["smluv"] += 1

            datum = _rozumne_datum(s.get("datum"), zahozena_data)
            if datum:
                if h["prvni_datum"] is None or datum < h["prvni_datum"]:
                    h["prvni_datum"] = datum
                if h["posledni_datum"] is None or datum > h["posledni_datum"]:
                    h["posledni_datum"] = datum

            nazev = (s.get("protistrana") or "").strip()
            if nazev:
                h["drive_nazvy"].add(nazev)
                if datum >= h["nazev_datum"]:  # název z nejnovější smlouvy
                    h["nazev"] = nazev
                    h["nazev_datum"] = datum

            if s.get("vada"):
                h["vadnych"] += 1

            castka = s.get("castka_czk")
            if castka is None:
                h["bez_ceny"] += 1
                continue
            if datum[:4].isdigit():
                h["po_letech"][datum[:4]] += castka

    protistrany = []
    for h in hromady.values():
        po_letech = {r: round(v, 2) for r, v in sorted(h["po_letech"].items())}
        celkem = round(sum(po_letech.values()), 2)
        interni = h["ico"] in nazvy_holdingu if h["ico"] else False
        drive = sorted(n for n in h["drive_nazvy"] if n != h["nazev"])
        protistrany.append({
            "ico": h["ico"],
            "nazev": h["nazev"],
            "klic_dle": h["klic_dle"],
            "smer": h["smer"],
            "celkem_czk": celkem,
            # Rozsah vztahu se bere z dat podpisu smluv, ne z `po_letech` —
            # protistrana může mít v některém roce jen smlouvy bez uvedené ceny.
            "prvni_rok": int(h["prvni_datum"][:4]) if h["prvni_datum"] else None,
            "posledni_rok": int(h["posledni_datum"][:4]) if h["posledni_datum"] else None,
            "aktivni": bool(h["posledni_datum"] and h["posledni_datum"] >= hranice_aktivity),
            "po_letech": po_letech,
            "smluv": h["smluv"],
            "bez_ceny": h["bez_ceny"],
            "vadnych": h["vadnych"],
            "interni": interni,
            "subjekty": sorted(h["subjekty"]),
        })
        if drive:
            # Firma se mohla mezitím přejmenovat — dřívější názvy si necháme,
            # ať se dá dohledat, pod jakým jménem brala peníze kdysi.
            protistrany[-1]["drive_nazvy"] = drive

    protistrany.sort(key=lambda p: (p["smer"], -p["celkem_czk"], p["nazev"] or ""))

    vysledek = {
        "generovano": k_datu.isoformat(),
        "zdroj": "Hlídač státu — registr smluv",
        "holding": ica_holdingu,
        "metodika": {
            "chybejici_rok": "Chybějící rok v po_letech = nula. Graf ho MUSÍ vykreslit "
                             "jako nulu, ne přeskočit — jinak časová osa lže.",
            "slucovani": "Protistrany se slučují podle IČO; bez IČO podle normalizovaného "
                         "názvu (klic_dle: 'nazev').",
            "aktivni": f"Podpis smlouvy v posledních {OKNO_AKTIVNI_DNI} dnech "
                       f"(od {hranice_aktivity}).",
            "smer_neurcen": "Nájem, pacht nebo prodej majetku, kde registr "
                            "vede město jako plátce i tam, kde peníze inkasuje. "
                            "Směr peněz z dat určit nelze — do součtů výdajů "
                            "ani příjmů nevstupuje.",
            "smer": "vydaj = sledovaný subjekt je v registru veden jako plátce; "
                    "prijem = je veden jako příjemce. Směr se přebírá ze zdroje "
                    "a nepřepisuje se — u nájmů a prodejů zveřejňovatelé často "
                    "zapisují město jako plátce, i když peníze inkasují.",
            "interni": "true = protistrana je sama subjektem městského holdingu "
                       "(přesun peněz uvnitř města, ne platba ven).",
            "castka_null": "Smlouva bez uvedené ceny se počítá do `smluv` a `bez_ceny`, "
                           "do `celkem_czk` a `po_letech` nevstupuje.",
            "pokryti": "Sklizeno přes REST API Hlídače státu v plném rozsahu "
                       "registru pro všechny subjekty holdingu.",
            "nesmyslne_datum": "Registr obsahuje smlouvy s nemožným datem podpisu "
                               "(nalezeny roky jako 0025 nebo 26). Takové datum se "
                               "považuje za neznámé: smlouva se počítá do součtů, ale "
                               "nevstupuje do `po_letech` ani do prvni_rok/posledni_rok, "
                               "aby neroztáhla osu grafu. Počet je v poli `zahozena_data`.",
        },
        "zahozena_data": zahozena_data,
        "protistrany": protistrany,
    }
    uloz("penize/agregace/protistrany.json", vysledek)

    vydaje = [p for p in protistrany if p["smer"] == "vydaj"]
    prijmy = [p for p in protistrany if p["smer"] == "prijem"]
    log.info("protistrany", dodavatelu=len(vydaje), odberatelu=len(prijmy),
             aktivnich=sum(1 for p in protistrany if p["aktivni"]))
    log.pricti(len(protistrany))
    return vysledek


def _pokryti(statistiky: dict, smluv: int, objem: float, dotaci: int) -> dict:
    """Poměr sklizených dat k tomu, co je v registru.

    Podíly se počítají, popisné části se přebírají ze sklizně — nedopisujeme
    k nim nic, co by ve sklizni nebylo zaznamenané.
    """
    p = dict(statistiky.get("pokryti", {}))
    v_registru_smluv = p.get("smluv_v_registru")
    v_registru_objem = p.get("objem_v_registru_czk")
    p.pop("_ucel", None)
    p["smluv_sklizeno"] = smluv
    p["objem_sklizeno_czk"] = round(objem, 2)
    p["dotaci_sklizeno"] = dotaci
    p["podil_smluv"] = round(smluv / v_registru_smluv, 4) if v_registru_smluv else None
    p["podil_objemu"] = round(objem / v_registru_objem, 4) if v_registru_objem else None
    return p


def souhrn(log: Log, agregace: dict) -> dict:
    """Celkové objemy po letech za holding + kontrola proti statistikám Hlídače."""
    holding = sledovane_subjekty(vcetne_mimo_mesto=False)
    ica_holdingu = [s["ico"] for s in holding]
    soubory = _nacti_smlouvy(ica_holdingu)
    statistiky = nacti("penize/statistiky.json", {})

    po_letech: dict[str, dict] = {}
    videno: set[str] = set()
    for ico, obsah in soubory.items():
        for s in obsah.get("smlouvy", []):
            # Každou smlouvu počítáme jednou, i když je zapsaná u dvou subjektů.
            if s["id"] in videno:
                continue
            videno.add(s["id"])
            rok = (s.get("datum") or "")[:4]
            if not rok.isdigit():
                continue
            r = po_letech.setdefault(rok, {
                "smluv": 0, "vydaj_czk": 0.0, "prijem_czk": 0.0,
                "bez_ceny": 0, "vadnych": 0,
            })
            r["smluv"] += 1
            if s.get("vada"):
                r["vadnych"] += 1
            castka = s.get("castka_czk")
            if castka is None:
                r["bez_ceny"] += 1
            elif s.get("smer") == "vydaj":
                r["vydaj_czk"] += castka
            else:
                r["prijem_czk"] += castka

    for r in po_letech.values():
        r["vydaj_czk"] = round(r["vydaj_czk"], 2)
        r["prijem_czk"] = round(r["prijem_czk"], 2)
        r["podil_bez_ceny"] = round(r["bez_ceny"] / r["smluv"], 4) if r["smluv"] else None

    roky = sorted(po_letech)
    protistrany = agregace["protistrany"]

    # Dotace ze sklizně — po letech za holding.
    dotace_po_letech: dict[str, dict] = {}
    dotaci = 0
    for ico in ica_holdingu:
        for d in (nacti(f"penize/dotace/{ico}.json", {}) or {}).get("dotace", []):
            dotaci += 1
            rok = str(d.get("rok") or "")
            if not rok.isdigit():
                continue
            r = dotace_po_letech.setdefault(rok, {"pocet": 0, "czk": 0.0})
            r["pocet"] += 1
            if d.get("castka_czk"):
                r["czk"] += d["castka_czk"]
    for r in dotace_po_letech.values():
        r["czk"] = round(r["czk"], 2)

    celkem_vydaj = round(sum(r["vydaj_czk"] for r in po_letech.values()), 2)
    celkem_prijem = round(sum(r["prijem_czk"] for r in po_letech.values()), 2)

    hlidac_holding = (statistiky.get("holding_dle_hlidace") or {})
    vysledek = {
        "generovano": agregace["generovano"],
        "zdroj": "Hlídač státu — registr smluv, dotace, veřejné zakázky",
        "rozsah_let": {"od": int(roky[0]), "do": int(roky[-1])} if roky else None,
        "holding": [
            {"ico": s["ico"], "nazev": s["nazev"], "typ": s.get("typ"),
             "smluv": len(soubory[s["ico"]].get("smlouvy", []))}
            for s in holding
        ],
        "mimo_holding": [
            {"ico": s["ico"], "nazev": s["nazev"], "duvod": s.get("poznamka")}
            for s in sledovane_subjekty() if s["ico"] not in set(ica_holdingu)
        ],
        # POZOR: chybějící rok = nula, graf ho musí vykreslit, ne přeskočit.
        "po_letech": {r: po_letech[r] for r in roky},
        "celkem": {
            "smluv": len(videno),
            "vydaj_czk": celkem_vydaj,
            "prijem_czk": celkem_prijem,
            "bez_ceny": sum(r["bez_ceny"] for r in po_letech.values()),
            "podil_bez_ceny": round(
                sum(r["bez_ceny"] for r in po_letech.values()) / len(videno), 4
            ) if videno else None,
            "vadnych": sum(r["vadnych"] for r in po_letech.values()),
            "dodavatelu": sum(1 for p in protistrany if p["smer"] == "vydaj"),
            "odberatelu": sum(1 for p in protistrany if p["smer"] == "prijem"),
            "aktivnich_dodavatelu": sum(
                1 for p in protistrany if p["smer"] == "vydaj" and p["aktivni"]
            ),
        },
        # Kolik z registru je ve skutečnosti sklizeno. Tenhle blok se nesmí
        # vypustit — bez něj by se dílčí data četla jako úplná a všechny grafy
        # by tvrdily víc, než data unesou.
        "pokryti": _pokryti(statistiky, len(videno), celkem_vydaj + celkem_prijem, dotaci),
        "kindex": statistiky.get("kindex", []),
        "dotace": {
            "pocet": dotaci,
            "po_letech": {r: dotace_po_letech[r] for r in sorted(dotace_po_letech)},
            "celkem_czk": round(sum(r["czk"] for r in dotace_po_letech.values()), 2),
        },
        # Vlastní součty vedle čísel, která Hlídač publikuje sám. Nikdy je
        # neslaďujeme silou — rozdíl je informace, ne chyba k zamaskování.
        "kontrola": {
            "hlidac_holding_smluv": hlidac_holding.get("smluv"),
            "hlidac_holding_objem_czk": hlidac_holding.get("objem_czk"),
            "hlidac_holding_bez_ceny": hlidac_holding.get("bez_ceny"),
            "hlidac_holding_vadnych": hlidac_holding.get("vadnych"),
            "nase_smluv": len(videno),
            "nase_objem_czk": round(celkem_vydaj + celkem_prijem, 2),
            "poznamka": "Hlídačův holding je jeho vlastní hierarchie (město + příspěvkové "
                        "organizace); náš holding navíc obsahuje městské obchodní "
                        "společnosti a naopak vynechává Nemocnici. Čísla se proto "
                        "nemusí shodovat na jednotku.",
        },
        "metodika": agregace["metodika"],
    }
    uloz("penize/agregace/souhrn.json", vysledek)
    log.info("souhrn", let=len(roky), smluv=len(videno),
             vydaj_mld=round(celkem_vydaj / 1e9, 2), prijem_mld=round(celkem_prijem / 1e9, 2))
    return vysledek


def main() -> None:
    log = Log("agregace_penez")
    try:
        agregace = agreguj_protistrany(log)
        souhrn(log, agregace)
    except ZdrojSelhal as e:
        log.chyba(str(e))
        log.uzavri()
        raise
    log.uzavri()


if __name__ == "__main__":
    main()
