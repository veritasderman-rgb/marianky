"""Přehled podnikatelů — kdo za firmami ve městě stojí a v jakém oboru.

Navazuje na `scrapers/podnikatele.py`, který stáhl výpisy z veřejného
rejstříku. Tenhle modul je otočí naruby: z „firma → lidé" dělá
„člověk → firmy" a doplňuje k tomu obor, peníze od města a veřejné funkce.

CO PŘEHLED ODPOVÍDÁ
-------------------
  osoby.json          kdo je ve kterých firmách statutárem nebo společníkem,
                      s funkcí a obdobím
  obory.json          kdo podniká v ubytování, ve stavebnictví… — filtr podle
                      převažující činnosti CZ-NACE z registru ekonomických
                      subjektů (`data/firmy/subjekty.json`)
  s_mestem.json       kdo z nich má firmu, která obchoduje s městem
                      (`data/penize/agregace/protistrany.json`, klíč IČO)
  verejne_funkce.json kdo z nich je zároveň veřejně činný
  casova_osa.json     kdy kdo ve firmách přibyl a odešel
  souhrn.json         čísla přehledu a žebříčky podle doložitelných kritérií

CO SE TU NEDĚLÁ
---------------
Nehodnotí se. „Jednatel firmy, která od města dostala 12 mil. Kč" je fakt
z registru smluv a smí se napsat. Cokoliv o tom, co to znamená, do dat
nepatří.

Nedělá se ani pořadí „nejvýznamnějších podnikatelů". Obrat ani majetek
nikdo nezveřejňuje, takže by to byl dohad. Žebříčky jsou proto vždy podle
JEDNOHO měřitelného kritéria a je u nich napsané, podle čeho se řadí:
počet firem, kategorie počtu pracovníků těch firem, objem obchodu s městem.

ZTOTOŽŇOVÁNÍ OSOB — KDE PŘEHLED RADĚJI MLČÍ
-------------------------------------------
`osoba_id` je klíč, kterým se člověk páruje s databází osobností, hlasováním
a články. Přiřazuje se jen tam, kde je jisté, o koho jde:

  1. Sběrač musí označit osobu za `jednoznacna` — tedy pod tím jménem je ve
     výpisech právě jeden člověk rozlišený datem narození. Zápisy bez data
     narození a jmenovci `osoba_id` nedostanou nikdy.
  2. Když je v `data/lide/osobnosti.json` osobnost téhož jména, musí navíc
     existovat POTVRZENÍ, že jde o tutéž osobu: shodné IČO firmy
     v `data/propojeni/osoby_firmy.json`. Samotná shoda jména nestačí —
     `osoba_id` zůstane null a kandidát se uloží do `mozna_shoda_s_osobnosti`
     jako otevřená otázka, ne jako zjištění.

Bod 2 je záměrně přísný: spojit podnikatele se zastupitelem téhož jména bez
důkazu je horší než nemít údaj vůbec.

OBORY MĚŘÍ PODNIKATELSKÉ ROLE, NE ČLENSTVÍ V ORGÁNECH
-----------------------------------------------------
Do filtru podle oborů vstupují jen aktuální angažmá v rolích statutár,
společník, akcionář a prokurista. Člen dozorčí rady hotelu v oboru
„ubytování" nepodniká — dohlíží. V `osoby.json` je u něj vidět všechno,
v oborovém filtru ne.

Obor se bere z `nace_prevazujici` v `data/firmy/subjekty.json`. Chybí u části
subjektů; taková firma je v `bez_oboru` a nikam se nedopočítává.
"""
from __future__ import annotations

import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import Log, ZdrojSelhal, nacti, nacti_config, slug, uloz  # noqa: E402
from scrapers.firmy import nace_sekce  # noqa: E402
# Prahy a obory si nedefinujeme znovu — jsou dané v přehledu firem a oba
# přehledy musí říkat totéž.
from pipeline.firmy_prehled import (  # noqa: E402
    FORMY_NEPODNIKATELSKE,
    OBORY_LAZENSKEHO_MESTA,
    PRAH_ZAMESTNAVATELE,
)

# Role, které znamenají „podniká" — vede firmu nebo ji vlastní. Dozorčí rada
# a kontrolní komise jsou dohled, ne podnikání; v přehledu osoby zůstávají,
# do oborového filtru a žebříčků nevstupují.
ROLE_PODNIKATELSKE = {"statutar", "spolecnik", "akcionar", "prokurista"}

# Označení právní formy v názvu firmy. Pro porovnání dvou zápisů téhož názvu
# se odstraňují: databáze osobností vede "Technický a dopravní servis s.r.o.",
# rejstřík "TECHNICKÝ A DOPRAVNÍ SERVIS, s.r.o.".
PRIPONY_FOREM = re.compile(
    r"-(?:s-r-o|spol-s-r-o|a-s|o-p-s|z-s|z-u|v-o-s|k-s|s-p|p-o)(?=-|$)")

ROLE_NAZVY = {
    "statutar": "statutární orgán",
    "spolecnik": "společník",
    "akcionar": "akcionář",
    "prokurista": "prokurista",
    "dozorci_rada": "dozorčí rada",
    "spravni_rada": "správní rada",
    "kontrolni_komise": "kontrolní komise",
    "zakladatel": "zakladatel / zřizovatel",
    "statutar_zrizovatele": "statutár zřizovatele",
    "likvidator": "likvidátor",
    "opatrovnik": "opatrovník",
    "vedouci_zavodu": "vedoucí odštěpného závodu",
    "jiny_organ": "jiný orgán",
}


# --------------------------------------------------------------------------
# Vstupy
# --------------------------------------------------------------------------

def _rok(datum: str | None) -> int | None:
    if not datum or len(datum) < 4 or not datum[:4].isdigit():
        return None
    return int(datum[:4])


def nacti_vstupy() -> dict:
    vypisy = nacti("podnikatele/vypisy.json")
    if not vypisy or not vypisy.get("firmy"):
        raise ZdrojSelhal("chybí data/podnikatele/vypisy.json — "
                          "nejdřív scrapers/podnikatele.py")
    firmy = nacti("firmy/subjekty.json")
    if not firmy or not firmy.get("subjekty"):
        raise ZdrojSelhal("chybí data/firmy/subjekty.json")

    return {
        "vypisy": vypisy,
        "subjekty": {s["ico"]: s for s in firmy["subjekty"] if s.get("ico")},
        "nace_nazvy": (firmy.get("ciselniky") or {}).get("cz_nace") or {},
        "dulezite": {f["ico"] for f in (nacti("firmy/prehled/dulezite.json") or {})
                     .get("firmy", []) if f.get("ico")},
        "protistrany": nacti("penize/agregace/protistrany.json") or {},
        "osobnosti": nacti("lide/osobnosti.json") or [],
        "osoby_firmy": nacti("propojeni/osoby_firmy.json") or {},
        "holding": {s["ico"] for s in nacti_config("subjekty.json")["subjekty"]
                    if s.get("ico")},
    }


def penize_podle_ico(protistrany: dict) -> dict[str, dict]:
    """Peníze mezi městem a protistranou, sečtené na IČO.

    Jedno IČO má v agregaci až dva záznamy — jeden za každý směr. Sčítají se
    zvlášť: `od_mesta_czk` (město platí) a `mestu_czk` (město inkasuje).
    Směr se přebírá ze zdroje a nepřepisuje se.
    """
    out: dict[str, dict] = {}
    for p in protistrany.get("protistrany") or []:
        ico = p.get("ico")
        if not ico:
            continue  # bez IČO se na firmu z rejstříku napojit nedá
        z = out.setdefault(ico, {
            "od_mesta_czk": None, "mestu_czk": None, "smluv": 0,
            "prvni_rok": None, "posledni_rok": None,
            "vnitromestsky_prevod": False, "aktivni": False,
        })
        pole = "od_mesta_czk" if p["smer"] == "vydaj" else "mestu_czk"
        if p.get("celkem_czk") is not None:
            z[pole] = (z[pole] or 0) + p["celkem_czk"]
        z["smluv"] += p.get("smluv") or 0
        z["vnitromestsky_prevod"] = z["vnitromestsky_prevod"] or bool(p.get("interni"))
        z["aktivni"] = z["aktivni"] or bool(p.get("aktivni"))
        for klic, volba in (("prvni_rok", min), ("posledni_rok", max)):
            if p.get(klic) is not None:
                z[klic] = p[klic] if z[klic] is None else volba(z[klic], p[klic])
    return out


# --------------------------------------------------------------------------
# Osoby
# --------------------------------------------------------------------------

def _obor_firmy(subjekt: dict | None, nace_nazvy: dict) -> dict:
    """Převažující obor firmy. Když ho registr nevede, je všude null."""
    if not subjekt or not subjekt.get("nace_prevazujici"):
        return {"obor_kod": None, "obor": None, "oddil": None, "oddil_nazev": None,
                "sekce": None, "sekce_nazev": None}
    kod = subjekt["nace_prevazujici"]
    oddil = kod[:2] if len(kod) >= 2 and kod[:2].isdigit() else None
    sekce, sekce_nazev = nace_sekce(kod)
    return {
        "obor_kod": kod,
        "obor": subjekt.get("nace_prevazujici_nazev"),
        "oddil": oddil,
        "oddil_nazev": nace_nazvy.get(oddil) if oddil else None,
        "sekce": sekce or subjekt.get("nace_sekce"),
        "sekce_nazev": sekce_nazev or subjekt.get("nace_sekce_nazev"),
    }


def sestav_osoby(vstupy: dict) -> list[dict]:
    """Otočí výpisy na pohled po lidech."""
    vypisy = vstupy["vypisy"]
    subjekty = vstupy["subjekty"]
    penize = penize_podle_ico(vstupy["protistrany"])
    rejstrik = {o["osoba_klic"]: o for o in vypisy["osoby"]}

    podle_osob: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    for firma in vypisy["firmy"]:
        for a in firma["angazma"]:
            podle_osob[a["osoba_klic"]].append((firma, a))

    osoby: list[dict] = []
    for klic, polozky in podle_osob.items():
        zaznam = rejstrik.get(klic) or {}
        if zaznam.get("typ") != "fyzicka":
            continue  # právnické osoby v orgánech nejsou podnikatelé-lidé

        firmy: dict[str, dict] = {}
        for firma, a in polozky:
            cil = firmy.get(firma["ico"])
            if cil is None:
                subjekt = subjekty.get(firma["ico"])
                cil = firmy[firma["ico"]] = {
                    "ico": firma["ico"],
                    "nazev": firma["nazev"],
                    "stav_firmy": firma["stav"],
                    "sidlo_v_obci": (subjekt or {}).get("sidlo_v_obci"),
                    "pravni_forma": (subjekt or {}).get("pravni_forma_nazev"),
                    # Spolky, společenství vlastníků a nadace se do přehledu
                    # dostaly přes seznam důležitých firem. Předseda spolku
                    # není podnikatel, takže do oborů a žebříčků nevstupují.
                    "nepodnikatelska_forma": (subjekt or {}).get("pravni_forma")
                                             in FORMY_NEPODNIKATELSKE,
                    "zamestnancu_kategorie": (subjekt or {}).get("zamestnancu_kategorie"),
                    "zamestnancu_rozsah": (subjekt or {}).get("zamestnancu_rozsah"),
                    **_obor_firmy(subjekt, vstupy["nace_nazvy"]),
                    "v_prehledu_dulezitych": firma["ico"] in vstupy["dulezite"],
                    "mestsky_holding": firma["ico"] in vstupy["holding"],
                    "obchod_s_mestem": penize.get(firma["ico"]),
                    "angazma": [],
                }
            cil["angazma"].append({
                "role": a["role"],
                "role_nazev": ROLE_NAZVY.get(a["role"], a["role"]),
                "organ": a["organ"],
                "funkce": a["funkce"],
                "od": a["od"], "do": a["do"],
                "aktualni": a["aktualni"],
                "dle": a["dle"],
                "obdobi": a["obdobi"],
                "podil_procent": a["podil_procent"],
                "vklad_czk": a["vklad_czk"],
            })

        seznam = sorted(firmy.values(),
                        key=lambda f: (not any(a["aktualni"] for a in f["angazma"]),
                                       f["nazev"] or ""))
        for f in seznam:
            f["aktualni"] = any(a["aktualni"] for a in f["angazma"])

        aktualni_firmy = [f for f in seznam if f["aktualni"]]
        role_vse = {a["role"] for f in seznam for a in f["angazma"]}
        role_akt = {a["role"] for f in seznam for a in f["angazma"] if a["aktualni"]}
        zacatky = [a["od"] for f in seznam for a in f["angazma"] if a["od"]]
        podnika = any(a["aktualni"] and a["role"] in ROLE_PODNIKATELSKE
                      for f in seznam if not f["nepodnikatelska_forma"]
                      for a in f["angazma"])

        osoby.append({
            "osoba_klic": klic,
            "osoba_id": None,          # doplní ztotozni()
            "jmeno": zaznam.get("jmeno"),
            "ztotozneni": {
                "jednoznacna": zaznam.get("jednoznacna"),
                "rozliseni": zaznam.get("rozliseni"),
                "zaznamu_tehoz_jmena": zaznam.get("zaznamu_tehoz_jmena"),
                "osoba_id_duvod": None,
                "doklady": None,
            },
            "firem": len(seznam),
            "firem_aktualne": len(aktualni_firmy),
            "role": sorted(role_vse),
            "role_aktualne": sorted(role_akt),
            "podnika_aktualne": podnika,
            "prvni_zaznam": min(zacatky) if zacatky else None,
            "firmy": seznam,
        })

    for o in osoby:
        _dopln_obory(o)
        _dopln_mesto(o)
    return sorted(osoby, key=lambda o: (-o["firem_aktualne"], -o["firem"],
                                        o["osoba_klic"]))


def _dopln_obory(osoba: dict) -> None:
    """Obory osoby. Jen aktuální angažmá v podnikatelských rolích."""
    obory: dict[str, dict] = {}
    bez_oboru = 0
    for f in osoba["firmy"]:
        if f["nepodnikatelska_forma"]:
            continue
        podnikatelske = any(a["aktualni"] and a["role"] in ROLE_PODNIKATELSKE
                            for a in f["angazma"])
        if not podnikatelske:
            continue
        if not f["obor_kod"]:
            bez_oboru += 1
            continue
        klic = f["oddil"] or f["obor_kod"]
        polozka = obory.setdefault(klic, {
            "oddil": f["oddil"], "oddil_nazev": f["oddil_nazev"],
            "sekce": f["sekce"], "sekce_nazev": f["sekce_nazev"], "firem": 0,
        })
        polozka["firem"] += 1
    osoba["obory"] = sorted(obory.values(), key=lambda o: (-o["firem"],
                                                           o["oddil"] or ""))
    osoba["firem_bez_oboru"] = bez_oboru or None


def _soucet_obchodu(firmy: list[dict]) -> dict | None:
    """Sečte obchod daných firem s městem. Bez firem vrací None, ne nulu."""
    soucet = {"firem": 0, "od_mesta_czk": None, "mestu_czk": None, "smluv": 0,
              "prvni_rok": None, "posledni_rok": None,
              "vnitromestskych_firem": 0, "vnitromestsky_od_mesta_czk": None}
    for f in firmy:
        obchod = f["obchod_s_mestem"]
        if not obchod:
            continue
        if obchod["vnitromestsky_prevod"]:
            # Peníze uvnitř městského holdingu (TDS a další) jsou převod, ne
            # zakázka získaná od města. Do součtu nevstupují.
            soucet["vnitromestskych_firem"] += 1
            if obchod.get("od_mesta_czk") is not None:
                soucet["vnitromestsky_od_mesta_czk"] = (
                    (soucet["vnitromestsky_od_mesta_czk"] or 0)
                    + obchod["od_mesta_czk"])
            continue
        soucet["firem"] += 1
        for pole in ("od_mesta_czk", "mestu_czk"):
            if obchod.get(pole) is not None:
                soucet[pole] = (soucet[pole] or 0) + obchod[pole]
        soucet["smluv"] += obchod["smluv"]
        for klic, volba in (("prvni_rok", min), ("posledni_rok", max)):
            if obchod.get(klic) is not None:
                soucet[klic] = (obchod[klic] if soucet[klic] is None
                                else volba(soucet[klic], obchod[klic]))
    return soucet if (soucet["firem"] or soucet["vnitromestskych_firem"]) else None


def _dopln_mesto(osoba: dict) -> None:
    """Obchod firem osoby s městem, zvlášť za dnešní a bývalá angažmá.

    Rozdíl je podstatný: „jednatel firmy, která od města bere zakázky" a
    „člověk, který v takové firmě byl jednatelem do roku 2009" jsou dvě
    různá tvrzení a sečíst je do jednoho čísla by bylo zavádějící.
    """
    dnes = _soucet_obchodu([f for f in osoba["firmy"] if f["aktualni"]])
    drive = _soucet_obchodu([f for f in osoba["firmy"] if not f["aktualni"]])
    osoba["mesto"] = None
    if dnes or drive:
        osoba["mesto"] = {
            "dnes": dnes,
            "drive": drive,
            "pozn": (
                "Částka je CELKOVÝ obrat firmy s městem podle registru smluv, "
                "ne obrat za dobu, kdy v ní osoba působila — registr smlouvy "
                "na osoby neváže. Vnitroměstské převody jsou vedeny zvlášť."
            ),
        }


# --------------------------------------------------------------------------
# Ztotožnění s veřejnými funkcemi
# --------------------------------------------------------------------------

def _klic_nazvu(nazev: str | None) -> str:
    """Porovnávací tvar názvu firmy — bez diakritiky, velikosti a právní formy."""
    return PRIPONY_FOREM.sub("", slug(nazev or "")).strip("-")


def firmy_ze_zivotopisu(osobnost: dict) -> dict[str, str]:
    """Firmy, které databáze osobností u člověka jmenuje.

    Funkce se tam zapisují ve tvaru "člen dozorčí rady — TDS Mariánské Lázně
    s.r.o.". Část za pomlčkou je název firmy a je to nezávislý doklad: když
    životopis osobnosti tu firmu jmenuje a rejstřík v ní vede člověka téhož
    jména, jde o shodu ve dvou údajích, ne jen ve jméně.
    """
    out: dict[str, str] = {}
    for f in osobnost.get("funkce") or []:
        nazev = f.get("nazev") or ""
        if "—" not in nazev:
            continue
        firma = nazev.split("—", 1)[1].strip()
        klic = _klic_nazvu(firma)
        if klic:
            out[klic] = nazev
    return out


def ztotozni(osoby: list[dict], vstupy: dict) -> dict:
    """Přiřadí `osoba_id` a dohledá veřejné funkce. Nejisté případy nespojuje."""
    osobnosti = {o["id"]: o for o in vstupy["osobnosti"] if o.get("id")}
    firmy_osobnosti: dict[str, set[str]] = {}
    for o in (vstupy["osoby_firmy"].get("osoby") or []):
        if not o.get("osoba_id"):
            continue
        firmy_osobnosti[o["osoba_id"]] = {f["ico"] for f in (o.get("firmy") or [])
                                          if f.get("ico")}

    pocty = Counter()
    for osoba in osoby:
        klic = osoba["osoba_klic"]
        osobnost = osobnosti.get(klic)
        nase_ico = {f["ico"] for f in osoba["firmy"]}
        shodne = sorted(nase_ico & firmy_osobnosti.get(klic, set()))
        ze_zivotopisu = firmy_ze_zivotopisu(osobnost) if osobnost else {}
        shodne_zivotopis = sorted(
            {ze_zivotopisu[_klic_nazvu(f["nazev"])]: f["ico"]
             for f in osoba["firmy"]
             if _klic_nazvu(f["nazev"]) in ze_zivotopisu}.items())
        doklady = ([f"shodne_ico:{i}" for i in shodne]
                   + [f"firma_v_zivotopise:{n} ({i})" for n, i in shodne_zivotopis])
        osoba["ztotozneni"]["doklady"] = doklady or None

        if not osoba["ztotozneni"]["jednoznacna"]:
            duvod = ("jmenovec" if osoba["ztotozneni"]["rozliseni"] == "datum_narozeni"
                     else "zapis_bez_data_narozeni")
            osoba["ztotozneni"]["osoba_id_duvod"] = duvod
            pocty[f"bez_id_{duvod}"] += 1
        elif osobnost and not doklady:
            osoba["ztotozneni"]["osoba_id_duvod"] = "shoda_jmena_bez_potvrzeni"
            pocty["bez_id_shoda_jmena_bez_potvrzeni"] += 1
        else:
            osoba["osoba_id"] = klic
            osoba["ztotozneni"]["osoba_id_duvod"] = (
                "potvrzeno_shodnou_firmou" if doklady else "jmenovec_v_datech_neni")
            pocty["s_id"] += 1

        osoba["verejna_funkce"] = None
        osoba["mozna_shoda_s_osobnosti"] = None
        if not osobnost:
            continue
        popis = {
            "osoba_id": osobnost["id"],
            "jmeno": osobnost.get("jmeno"),
            "role": osobnost.get("role"),
            "kategorie": osobnost.get("kategorie"),
            "strana": osobnost.get("strana"),
            "funkce": osobnost.get("funkce"),
            "shodne_firmy": shodne or None,
            "doklady": doklady or None,
            "zdroj": ["data/lide/osobnosti.json", "data/propojeni/osoby_firmy.json"],
        }
        if osoba["osoba_id"]:
            osoba["verejna_funkce"] = {**popis, "stav": (
                "potvrzeno_shodnou_firmou" if doklady
                else "shoda_jmena_bez_jmenovce")}
            pocty["s_verejnou_funkci"] += 1
        else:
            osoba["mozna_shoda_s_osobnosti"] = {**popis, "stav": "neovereno", "pozn": (
                "Osobnost téhož jména. Shodu se nepodařilo doložit shodnou "
                "firmou, takže se osoby NESPOJUJÍ — může jít o jmenovce.")}
            pocty["neovereny_kandidat"] += 1
    return dict(pocty)


# --------------------------------------------------------------------------
# Výstupy
# --------------------------------------------------------------------------

def index_oboru(osoby: list[dict], nace_nazvy: dict) -> dict:
    """Filtr podle oborů: kdo podniká v ubytování, ve stavebnictví…"""
    sekce: dict[str, dict] = {}
    oddily: dict[str, dict] = {}
    for o in osoby:
        for obor in o["obory"]:
            if obor["sekce"]:
                s = sekce.setdefault(obor["sekce"], {
                    "sekce": obor["sekce"], "nazev": obor["sekce_nazev"],
                    "osob": 0, "firem": 0, "osoby": [],
                })
                s["osob"] += 1
                s["firem"] += obor["firem"]
                s["osoby"].append(o["osoba_klic"])
            if obor["oddil"]:
                d = oddily.setdefault(obor["oddil"], {
                    "oddil": obor["oddil"],
                    "nazev": obor["oddil_nazev"] or nace_nazvy.get(obor["oddil"]),
                    "sekce": obor["sekce"], "sekce_nazev": obor["sekce_nazev"],
                    "osob": 0, "firem": 0, "osoby": [],
                })
                d["osob"] += 1
                d["firem"] += obor["firem"]
                d["osoby"].append(o["osoba_klic"])

    lazenstvi = {"nazev": "lázeňství a cestovní ruch",
                 "oddily": OBORY_LAZENSKEHO_MESTA, "osoby": []}
    lazenstvi["osoby"] = sorted({
        o["osoba_klic"] for o in osoby
        for obor in o["obory"] if obor["oddil"] in OBORY_LAZENSKEHO_MESTA
    })

    return {
        "generovano": time.strftime("%Y-%m-%d"),
        "mereni": (
            "Počet OSOB, které dnes vedou nebo vlastní firmu s převažující "
            "činností v daném oboru. Role dozorčí a kontrolní nevstupují, "
            "stejně jako spolky, společenství vlastníků a další formy, které "
            "ze své podstaty nepodnikají. Jeden člověk se počítá do každého "
            "oboru, ve kterém firmu má."
        ),
        "zdroj_oboru": ("nace_prevazujici z data/firmy/subjekty.json — "
                        "převažující činnost podle registru ekonomických "
                        "subjektů, ne náš výběr ze seznamu činností"),
        "skupiny": {"lazenstvi_a_cestovni_ruch": {
            **lazenstvi, "osob": len(lazenstvi["osoby"])}},
        "sekce": sorted(sekce.values(), key=lambda s: -s["osob"]),
        "oddily": sorted(oddily.values(), key=lambda d: -d["osob"]),
    }


def prehled_s_mestem(osoby: list[dict]) -> dict:
    """Kdo z podnikatelů má firmu obchodující s městem."""
    vybrane = []
    for o in osoby:
        if not o["mesto"]:
            continue
        firmy = [{
            "ico": f["ico"], "nazev": f["nazev"], "obor": f["obor"],
            "od_mesta_czk": (f["obchod_s_mestem"] or {}).get("od_mesta_czk"),
            "mestu_czk": (f["obchod_s_mestem"] or {}).get("mestu_czk"),
            "smluv": (f["obchod_s_mestem"] or {}).get("smluv"),
            "vnitromestsky_prevod": (f["obchod_s_mestem"] or {})
                                    .get("vnitromestsky_prevod"),
            "role": sorted({a["role"] for a in f["angazma"]}),
            "aktualni": f["aktualni"],
        } for f in o["firmy"] if f["obchod_s_mestem"]]
        vybrane.append({
            "osoba_klic": o["osoba_klic"], "osoba_id": o["osoba_id"],
            "jmeno": o["jmeno"], "ztotozneni": o["ztotozneni"],
            "mesto": o["mesto"],
            "dnes_v_firme_obchodujici_s_mestem": bool(o["mesto"]["dnes"]),
            "verejna_funkce": bool(o["verejna_funkce"]),
            "firmy": sorted(firmy, key=lambda f: -(f["od_mesta_czk"] or 0)),
        })
    vybrane.sort(key=lambda o: (-((o["mesto"]["dnes"] or {}).get("od_mesta_czk") or 0),
                                -((o["mesto"]["drive"] or {}).get("od_mesta_czk") or 0)))
    dnes = [o for o in vybrane if o["dnes_v_firme_obchodujici_s_mestem"]]
    return {
        "generovano": time.strftime("%Y-%m-%d"),
        "mereni": (
            "Peníze z registru smluv sečtené přes firmy, ve kterých je osoba "
            "vedená ve veřejném rejstříku. Není to příjem osoby — je to obrat "
            "jejích firem s městem. Smlouva bez uvedené ceny se počítá do "
            "počtu smluv, do částky ne."
        ),
        "dnes_a_drive": (
            "Blok `dnes` jsou firmy, ve kterých osoba působí teď; `drive` "
            "firmy, ze kterých je už vypsaná. Sčítat je dohromady nelze."
        ),
        "smer": ("od_mesta_czk = město je v registru vedeno jako plátce; "
                 "mestu_czk = opačný směr"),
        "vnitromestsky_prevod": (
            "Firmy městského holdingu (TDS a další) dostávají peníze uvnitř "
            "města. Vede se zvlášť a do součtu osoby nevstupuje."),
        "osob": len(vybrane),
        "osob_dnes": len(dnes),
        "osoby": vybrane,
    }


def prehled_verejnych_funkci(osoby: list[dict]) -> dict:
    potvrzeni = [o for o in osoby if o["verejna_funkce"]]
    kandidati = [o for o in osoby if o["mozna_shoda_s_osobnosti"]]
    return {
        "generovano": time.strftime("%Y-%m-%d"),
        "metodika": (
            "Průnik lidí z veřejného rejstříku s databází osobností města. "
            "Dělá se od firem — opačný směr (od zastupitelů k firmám) dělá "
            "pipeline/propojeni.py."
        ),
        "stavy": {
            "potvrzeno_shodnou_firmou": "u osobnosti je v datech táž firma (IČO)",
            "shoda_jmena_bez_jmenovce": (
                "jméno sedí, jmenovec v rejstříkových datech není a osoba je "
                "rozlišená datem narození; shodnou firmu se ale doložit "
                "nepodařilo"),
            "neovereno": ("jméno sedí, ale doklad chybí — osoby se NESPOJUJÍ "
                          "a osoba_id zůstává null"),
        },
        "potvrzenych": len(potvrzeni),
        "neoverenych_kandidatu": len(kandidati),
        "osoby": [{
            "osoba_id": o["osoba_id"], "osoba_klic": o["osoba_klic"],
            "jmeno": o["jmeno"], "verejna_funkce": o["verejna_funkce"],
            "firem": o["firem"], "firem_aktualne": o["firem_aktualne"],
            "mesto": o["mesto"],
            "firmy": [{"ico": f["ico"], "nazev": f["nazev"], "obor": f["obor"],
                       "aktualni": f["aktualni"],
                       "role": sorted({a["role"] for a in f["angazma"]})}
                      for f in o["firmy"]],
        } for o in potvrzeni],
        "neovereni_kandidati": [{
            "osoba_klic": o["osoba_klic"], "jmeno": o["jmeno"],
            "ztotozneni": o["ztotozneni"],
            "mozna_shoda_s_osobnosti": o["mozna_shoda_s_osobnosti"],
            "firem": o["firem"],
        } for o in kandidati],
    }


def casova_osa(osoby: list[dict]) -> dict:
    """Kdy lidé ve firmách přibývali a odcházeli."""
    prichody: Counter = Counter()
    odchody: Counter = Counter()
    presnost: Counter = Counter()
    for o in osoby:
        for f in o["firmy"]:
            for a in f["angazma"]:
                presnost[a["dle"]] += 1
                for usek in a["obdobi"]:
                    if _rok(usek["od"]):
                        prichody[_rok(usek["od"])] += 1
                    if _rok(usek["do"]):
                        odchody[_rok(usek["do"])] += 1
    roky = sorted(set(prichody) | set(odchody))
    return {
        "generovano": time.strftime("%Y-%m-%d"),
        "mereni": (
            "Počet angažmá, která v daném roce začala nebo skončila, ve "
            "firmách stažených tímhle modulem. NENÍ to obraz podnikání ve "
            "městě v tom roce: rejstřík vede jen dnes existující firmy, takže "
            "starší roky jsou osekané o všechno, co mezitím zaniklo."
        ),
        "presnost_dat": {
            "funkce": presnost["funkce"],
            "clenstvi": presnost["clenstvi"],
            "zapis": presnost["zapis"],
            "pozn": ("U angažmá s dle='zapis' zdroj přesné datum nemá a jde "
                     "o datum zápisu do rejstříku — horní odhad, ne den, kdy "
                     "člověk do firmy nastoupil."),
        },
        "po_letech": {str(r): {"prichodu": prichody.get(r, 0),
                               "odchodu": odchody.get(r, 0)} for r in roky},
    }


def zebricky(osoby: list[dict]) -> dict:
    """Žebříčky podle jednoho měřitelného kritéria. Ne podle důležitosti."""
    def zaklad(o: dict) -> dict:
        return {"osoba_klic": o["osoba_klic"], "osoba_id": o["osoba_id"],
                "jmeno": o["jmeno"]}

    podnikajici = [o for o in osoby if o["podnika_aktualne"]]
    zamestnavatele = []
    for o in podnikajici:
        firmy = [f for f in o["firmy"]
                 if f["aktualni"] and f["zamestnancu_kategorie"]
                 and f["zamestnancu_kategorie"] >= PRAH_ZAMESTNAVATELE
                 and any(a["aktualni"] and a["role"] in ROLE_PODNIKATELSKE
                         for a in f["angazma"])]
        if firmy:
            nej = max(firmy, key=lambda f: f["zamestnancu_kategorie"])
            zamestnavatele.append({**zaklad(o), "firem": len(firmy),
                                   "nejvetsi_firma": nej["nazev"],
                                   "zamestnancu_rozsah": nej["zamestnancu_rozsah"],
                                   "kategorie": nej["zamestnancu_kategorie"]})
    zamestnavatele.sort(key=lambda z: (z["kategorie"], z["firem"]), reverse=True)

    # Žebříček obchodu s městem bere jen firmy, ve kterých osoba působí teď.
    s_mestem = [o for o in osoby
                if o["mesto"] and (o["mesto"]["dnes"] or {}).get("od_mesta_czk")]
    s_mestem.sort(key=lambda o: -o["mesto"]["dnes"]["od_mesta_czk"])

    return {
        "razeni": ("Každý žebříček má jedno kritérium a to je v jeho názvu. "
                   "Není to pořadí důležitosti — obrat ani majetek se "
                   "nezveřejňuje a projekt si ho nedopočítává."),
        "nejvic_firem": [{**zaklad(o), "firem_aktualne": o["firem_aktualne"],
                          "role": o["role_aktualne"],
                          "obory": [x["oddil_nazev"] for x in o["obory"]][:5]}
                         for o in sorted(podnikajici,
                                         key=lambda o: -o["firem_aktualne"])[:25]],
        "firmy_s_nejvic_zamestnanci": zamestnavatele[:25],
        "nejvetsi_obchod_firem_s_mestem": [
            {**zaklad(o), "od_mesta_czk": o["mesto"]["dnes"]["od_mesta_czk"],
             "firem": o["mesto"]["dnes"]["firem"],
             "smluv": o["mesto"]["dnes"]["smluv"],
             "prvni_rok": o["mesto"]["dnes"]["prvni_rok"],
             "posledni_rok": o["mesto"]["dnes"]["posledni_rok"],
             "role": o["role_aktualne"],
             "verejna_funkce": bool(o["verejna_funkce"]),
             "pozn": "částka je obrat firem osoby s městem, ne příjem osoby"}
            for o in s_mestem[:25]],
    }


# --------------------------------------------------------------------------
# Běh
# --------------------------------------------------------------------------

def main() -> None:
    log = Log("podnikatele_prehled")
    vstupy = nacti_vstupy()

    osoby = sestav_osoby(vstupy)
    log.info("sestaveno osob", osob=len(osoby),
             firem=len(vstupy["vypisy"]["firmy"]))

    pocty = ztotozni(osoby, vstupy)
    log.info("ztotožnění", **pocty)

    obory = index_oboru(osoby, vstupy["nace_nazvy"])
    mesto = prehled_s_mestem(osoby)
    funkce = prehled_verejnych_funkci(osoby)
    osa = casova_osa(osoby)

    podnikajici = [o for o in osoby if o["podnika_aktualne"]]
    souhrn = {
        "generovano": time.strftime("%Y-%m-%d"),
        "zdroje": ["data/podnikatele/vypisy.json", "data/firmy/subjekty.json",
                   "data/penize/agregace/protistrany.json",
                   "data/propojeni/osoby_firmy.json", "data/lide/osobnosti.json"],
        "rozsah": vstupy["vypisy"]["vyber"],
        "osob_celkem": len(osoby),
        "osob_podnikajicich_dnes": len(podnikajici),
        "osob_s_osoba_id": sum(1 for o in osoby if o["osoba_id"]),
        "osob_bez_osoba_id": {
            duvod: sum(1 for o in osoby
                       if not o["osoba_id"]
                       and o["ztotozneni"]["osoba_id_duvod"] == duvod)
            for duvod in ("jmenovec", "zapis_bez_data_narozeni",
                          "shoda_jmena_bez_potvrzeni")
        },
        "osob_s_vice_firmami": sum(1 for o in osoby if o["firem_aktualne"] > 1),
        "osob_s_firmou_obchodujici_s_mestem": {
            "dnes": mesto["osob_dnes"],
            "vcetne_byvalych_angazma": mesto["osob"],
        },
        "osob_ve_verejne_funkci": funkce["potvrzenych"],
        "neoverenych_kandidatu_na_verejnou_funkci": funkce["neoverenych_kandidatu"],
        "firem_v_prehledu": len(vstupy["vypisy"]["firmy"]),
        "nejcastejsi_obory": [
            {"oddil": d["oddil"], "nazev": d["nazev"], "osob": d["osob"]}
            for d in obory["oddily"][:15]],
        "lazenstvi_a_cestovni_ruch_osob": obory["skupiny"][
            "lazenstvi_a_cestovni_ruch"]["osob"],
        "zebricky": zebricky(osoby),
    }

    uloz("podnikatele/prehled/osoby.json", {
        "generovano": time.strftime("%Y-%m-%d"),
        "metodika": {
            "rozsah": ("Lidé zapsaní ve veřejném rejstříku u firem se sídlem "
                       "ve městě. Živnostníci bez zápisu v rejstříku tu nejsou."),
            "osoba_id": ("Přiřazuje se jen jednoznačně rozlišené osobě. Kde je "
                         "jmenovec nebo nedoložená shoda s osobností, je null "
                         "a platí jméno jako text."),
            "osobni_udaje": ("Datum narození ani bydliště se neukládá. Jméno, "
                             "funkce a firma jsou veřejné údaje z veřejného "
                             "rejstříku."),
            "obdobi": ("od/do jsou z rejstříku; pole dle říká, odkud datum je "
                       "— funkce, clenstvi, nebo jen zapis do rejstříku."),
            "null": "null znamená nezjištěno, nikdy nulu.",
        },
        "osob": len(osoby),
        "osoby": osoby,
    })
    uloz("podnikatele/prehled/obory.json", obory)
    uloz("podnikatele/prehled/s_mestem.json", mesto)
    uloz("podnikatele/prehled/verejne_funkce.json", funkce)
    uloz("podnikatele/prehled/casova_osa.json", osa)
    uloz("podnikatele/prehled/souhrn.json", souhrn)

    log.info("uloženo", osob=len(osoby), podnikajicich=len(podnikajici),
             s_mestem=mesto["osob"], verejnych_funkci=funkce["potvrzenych"],
             oboru=len(obory["oddily"]))
    log.pricti(len(osoby))
    log.uzavri()


if __name__ == "__main__":
    main()
