"""Kulturní památky v Mariánských Lázních se souřadnicemi.

Mariánské Lázně jsou od roku 2021 součástí statku světového dědictví UNESCO
*Slavná lázeňská města Evropy*, takže památková ochrana tu není okrajové
téma — je to jedna z věcí, podle kterých se ve městě rozhoduje o stavbách.
Tenhle modul připravuje data, ze kterých jde postavit mapu: kde památky
jsou, jakého jsou typu a jak daleko sahá plošná ochrana.

ZDROJE (ověřeno 17. 8. 2026)

1. **Otevřená data ÚSKP** — `pamatkovykatalog.cz/opendata/npu_opendata_*.csv`
   Sedm datových sad (KP, NKP, PZ, PR, SD, OP, NZ) s názvem, kategorií,
   adresou, katastrálním územím, rejstříkovým číslem a anotací.
   **Souřadnice v nich nejsou** — jsou jen v geografickém systému NPÚ.
   Aktualizace 1× měsíčně k poslednímu dni měsíce, licence CC BY 4.0.

   Pozor na pole `obec`: u plošné ochrany je to středníkem oddělený seznam
   (`"Mariánské Lázně; Valy"`), takže rovnost na řetězec by chráněná území
   ztratila. A není spolehlivé úplně: nárazníková zóna UNESCO má v CSV
   uvedené jen Karlovy Vary, přestože sahá i sem. Proto se plošná ochrana
   navíc dohledává prostorově.

2. **Geoportál NPÚ (ArcGIS REST)** — `geoportal.npu.cz/arcgis/rest/services`
   Vrstvy `Tematicke/CP_PaKaOchreKP` a `…NKP` mají definiční body památek,
   `Tematicke/CP_Prstav_PVO` plošná vymezení ochrany. Klíč `prStavId`
   propojuje obojí s CSV. Vrstvy s body hlásí licenci CC BY-SA 4.0 NPÚ,
   vrstva plošných vymezení uvádí jen autora — obojí se do dat ukládá tak,
   jak to služba tvrdí, včetně toho, že u jedné licence chybí.

SOUŘADNICE: geoportál je nativně v **S-JTSK (EPSG:5514)**. Data se stahují
v něm a převádějí se stejnou transformací jako RÚIAN (`scrapers.geodata`),
aby všechny vrstvy projektu seděly na sebe. Kdyby se nechal převádět server,
byly by památky proti adresním bodům jinde. Ve výstupu je vedle WGS-84
uložená i původní S-JTSK souřadnice.

BEZ SOUŘADNIC: památka, ke které geoportál nemá definiční bod, se
nezahazuje ani nedostane vymyšlenou polohu — jde do `pamatky_bez_bodu.json`
a je vidět, že o její poloze nevíme.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import Log, ZdrojSelhal, fetch, nacti, uloz  # noqa: E402
from scrapers.geodata import (BBOX, OBEC_KOD, OBEC_NAZEV, OKRES,  # noqa: E402
                              POSUN, bod_v_polygonu, overe_prevod, sjtsk_na_wgs84)

CIL = "opendata/pamatky"

KATALOG = "https://www.pamatkovykatalog.cz"
OPENDATA = KATALOG + "/opendata/npu_opendata_{kod}.csv"
GEOPORTAL = "https://geoportal.npu.cz/arcgis/rest/services/Tematicke"

# Kódy datových sad ÚSKP a co znamenají. Pořadí drží i pořadí ve výstupu.
SADY = {
    "KP": "kulturní památky",
    "NKP": "národní kulturní památky",
    "PR": "památkové rezervace",
    "PZ": "památkové zóny",
    "SD": "památky světového dědictví UNESCO",
    "OP": "ochranná pásma",
    "NZ": "nárazníkové zóny světového dědictví UNESCO",
}
BODOVE = ("KP", "NKP")          # sady, ke kterým geoportál vede definiční body
PLOSNE = ("PR", "PZ", "SD", "OP", "NZ")

# Vrstvy s definičními body. 0 = hlavní bod prvku (jeden na památku),
# 1 = všechny body včetně dílčích částí areálů, 2 = nepřímo lokalizované.
# Pro mapu chceme jeden bod na památku, proto 0; z 2 bereme, co v 0 chybí.
VRSTVY_BODU = {"KP": f"{GEOPORTAL}/CP_PaKaOchreKP/MapServer",
               "NKP": f"{GEOPORTAL}/CP_PaKaOchreNKP/MapServer"}
VRSTVA_PLOCH = f"{GEOPORTAL}/CP_Prstav_PVO/MapServer/0"

LICENCE_NPU = ("CC BY 4.0 — Národní památkový ústav. Data lze užít i komerčně, "
               "povinností je uvést původ a odkaz na licenci. "
               "https://creativecommons.org/licenses/by/4.0/deed.cs")
LICENCE_GEOPORTAL = ("CC BY-SA 4.0 — Národní památkový ústav (uvedeno v poli "
                     "copyrightText služby geoportálu). Odvozená díla se musí "
                     "sdílet pod stejnou licencí.")
# Vrstva plošných vymezení uvádí v copyrightText jen "Národní památkový ústav",
# tedy autora, ne licenci. Nedomýšlíme si ji.
LICENCE_PVO = ("Služba uvádí jen autora (Národní památkový ústav), licenci ne. "
               "Sousední vrstvy geoportálu mají CC BY-SA 4.0, otevřená data "
               "ÚSKP CC BY 4.0. Zdroj se uvádí vždy; před komerčním užitím "
               "se doptat NPÚ.")


def dolozka(datum: str) -> str:
    """Doložka, kterou NPÚ u odvozených děl vyžaduje. Znění je jejich, ne naše."""
    return (f"datový podklad: Národní památkový ústav, {KATALOG}/, "
            f"datum aktualizace {datum}, licence CC BY 4.0")


# ==========================================================================
# Otevřená data ÚSKP
# ==========================================================================

def datum_aktualizace(log: Log) -> str:
    """Datum poslední aktualizace sad, jak ho hlásí portál. Patří do doložky."""
    html = fetch(f"{KATALOG}/otevrena-data", max_age=86_400)
    m = re.search(r'openDataDate:\s*"(\d{2}\.\d{2}\.\d{4})"', html)
    if not m:
        raise ZdrojSelhal("na stránce otevřených dat NPÚ chybí datum aktualizace")
    log.info("otevřená data ÚSKP", aktualizace=m.group(1))
    return m.group(1)


def _obce(radek: dict) -> set[str]:
    """Pole `obec` je u plošné ochrany seznam oddělený středníky."""
    return {x.strip() for x in (radek.get("obec") or "").split(";") if x.strip()}


def uskp(log: Log) -> dict[str, list[dict]]:
    """Načte sady ÚSKP a vybere záznamy patřící Mariánským Lázním."""
    vybrane: dict[str, list[dict]] = {}
    for kod, popis in SADY.items():
        text = fetch(OPENDATA.format(kod=kod), cache_key=f"uskp-{kod}",
                     max_age=7 * 86_400, timeout=300)
        radky = list(csv.DictReader(io.StringIO(text)))
        if not radky:
            raise ZdrojSelhal(f"sada ÚSKP {kod} je prázdná")
        ml = [r for r in radky if OBEC_NAZEV in _obce(r)]
        vybrane[kod] = ml
        log.info("sada ÚSKP", kod=kod, popis=popis, celkem_cr=len(radky), v_ml=len(ml))
    if not vybrane["KP"]:
        raise ZdrojSelhal("v ÚSKP nevyšla ani jedna kulturní památka v Mariánských "
                          "Lázních — to je jistě chyba filtru, ne skutečnost")
    return vybrane


# Jména vlastností jsou volená tak, aby je přečetl web (`web/src/lib/geodata.ts`
# hledá `rejstrik`, `ochrana`, `unesco`, `rok_zapisu`). Význam každého pole je
# v hlavičce souboru pod klíčem `vysvetlivky`, ať se to nedá splést.
VYSVETLIVKY = {
    "rejstrik": "rejstříkové číslo Ústředního seznamu kulturních památek ČR",
    "ochrana": "typ památkové ochrany podle zákona 20/1987 Sb.",
    "kategorie": "objekt / část objektu / areál / soubor / území",
    "rok_zapisu": "rok, od kterého ochrana platí (datumOchranyOd v geoportálu NPÚ)",
    "unesco": "leží bod uvnitř statku světového dědictví UNESCO",
    "v_uzemich": "plošná ochrana, do které bod spadá",
    "sjtsk": "původní souřadnice zdroje v EPSG:5514 [východ, sever]",
    "lokalizace": "jak je bod ve zdroji určen",
    "prstav_id": "identifikátor právního stavu ochrany, spojuje ÚSKP s geoportálem",
}


def _vlastnosti(radek: dict, sada: str) -> dict:
    return {
        "zdroj": "NPÚ, Ústřední seznam kulturních památek ČR",
        "sada": sada,
        "katalogove_cislo": radek["katalogové_číslo"],
        "nazev": radek["název"],
        "kategorie": radek["kategorie"],
        "ochrana": radek["typ_památkové_ochrany"],
        "rejstrik": radek["rejstříkové_číslo_ÚSKP"],
        "prstav_id": radek["PrStavId"],
        "aktstav_id": radek["AktStav_Id"],
        "adresa": radek["adresa"] or None,
        "obec": radek["obec"],
        "cast_obce": radek["část_obce"] or None,
        "katastralni_uzemi": radek["katastrální_území"] or None,
        "okres": radek["okres"],
        "kraj": radek["kraj"],
        "anotace": radek["anotace"] or None,
        "url": f"{KATALOG}/{radek['katalogové_číslo']}",
    }


# ==========================================================================
# Geoportál NPÚ
# ==========================================================================

def _dotaz(url: str, parametry: dict, klic: str) -> dict:
    odpoved = fetch(f"{url}/query?{urlencode(parametry)}", cache_key=klic,
                    max_age=7 * 86_400, timeout=180)
    data = json.loads(odpoved)
    if "error" in data:
        raise ZdrojSelhal(f"geoportál NPÚ odmítl dotaz: {data['error']}")
    return data


def sluzba_licence(url: str) -> str | None:
    """Licenci bereme z pole `copyrightText` služby, ne z paměti.

    Metadata visí na MapServeru, ne na jednotlivé vrstvě, takže se koncové
    číslo vrstvy odřízne.
    """
    if url.rsplit("/", 1)[-1].isdigit():
        url = url.rsplit("/", 1)[0]
    try:
        data = json.loads(fetch(f"{url}?f=json", max_age=7 * 86_400))
        return (data.get("copyrightText") or "").strip() or None
    except Exception:  # noqa: BLE001 — licence je doplněk, ne důvod ke spadnutí
        return None


def _rok(ms) -> int | None:
    """ArcGIS vrací datum jako milisekundy od 1970, klidně záporné."""
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).year
    except (OverflowError, OSError, ValueError):
        return None


def body(prstav_ids: dict[str, list[str]], log: Log) -> dict[str, dict]:
    """Definiční body památek z geoportálu, klíčem je prStavId.

    Stahuje se v EPSG:5514 a převádí se vlastní transformací — viz úvodní
    komentář. Ověřeno na třech památkách: shoda s WGS-84 výstupem serveru
    je 0,0 m, takže převod nic neposouvá.
    """
    nalezene: dict[str, dict] = {}
    for sada, ids in prstav_ids.items():
        if not ids:
            continue
        seznam = ",".join(ids)
        for vrstva, lokalizace in ((0, "hlavní definiční bod"),
                                   (2, "nepřímo lokalizováno")):
            data = _dotaz(f"{VRSTVY_BODU[sada]}/{vrstva}",
                          {"where": f"prStavId IN ({seznam})", "outFields": "*",
                           "outSR": 5514, "returnGeometry": "true", "f": "json"},
                          f"npu-body-{sada}-{vrstva}")
            for f in data.get("features", []):
                g = f.get("geometry") or {}
                if g.get("x") is None:
                    continue
                klic = str(f["attributes"].get("prStavId"))
                if klic in nalezene:
                    continue                    # hlavní bod má přednost
                lon, lat = sjtsk_na_wgs84(g["x"], g["y"])
                nalezene[klic] = {
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "sjtsk": [round(g["x"], 2), round(g["y"], 2)],
                    "lokalizace": lokalizace,
                    "chraneno": f["attributes"].get("chraneno") == 1,
                    "faze_ochrany": f["attributes"].get("fazeOchranyNazev"),
                    "rok_zapisu": _rok(f["attributes"].get("datumOchranyOd")),
                    "ruian_stavebni_objekt": f["attributes"].get("KodStavObjRUIAN"),
                    "npu_nazev_prvku": f["attributes"].get("NazevPrvku"),
                }
            log.info("definiční body z geoportálu", sada=sada, vrstva=vrstva,
                     prvku=len(data.get("features", [])))
    return nalezene


def _esri_na_multipolygon(rings: list) -> dict | None:
    """Esri `rings` → GeoJSON MultiPolygon ve WGS-84.

    Esri vede vnější prstenec po směru hodinových ručiček a díry proti němu,
    GeoJSON to má obráceně. Podle znaménka plochy se pozná, co je co, a díra
    se přiřadí k naposledy otevřenému polygonu.
    """
    polygony: list[list[list[list[float]]]] = []
    for prstenec in rings:
        prevedeny = [list(sjtsk_na_wgs84(x, y)) for x, y in
                     ((b[0], b[1]) for b in prstenec)]
        if len(prevedeny) < 4:
            continue
        if prevedeny[0] != prevedeny[-1]:
            prevedeny.append(prevedeny[0])
        plocha = 0.0
        for i in range(len(prevedeny) - 1):
            plocha += prevedeny[i][0] * prevedeny[i + 1][1] - prevedeny[i + 1][0] * prevedeny[i][1]
        vnejsi = plocha < 0            # Esri: vnější prstenec po směru hodin
        if vnejsi:
            polygony.append([prevedeny[::-1]])          # GeoJSON chce proti směru
        elif polygony:
            polygony[-1].append(prevedeny[::-1])        # díra, obráceně
        else:
            polygony.append([prevedeny[::-1]])
    return {"type": "MultiPolygon", "coordinates": polygony} if polygony else None


def _plochy_dotaz(parametry: dict, klic: str) -> list[dict]:
    data = _dotaz(VRSTVA_PLOCH, {"outFields": "*", "outSR": 5514,
                                 "returnGeometry": "true", "f": "json", **parametry}, klic)
    prvky = []
    for f in data.get("features", []):
        geom = _esri_na_multipolygon((f.get("geometry") or {}).get("rings") or [])
        if geom is None:
            continue
        a = f["attributes"]
        prvky.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "zdroj": "NPÚ, Památkový geografický informační systém",
                "nazev": a.get("PrStavNazev"),
                "ochrana_kod": a.get("typOchranyKod"),
                "ochrana": a.get("typOchranyNazev"),
                "unesco": a.get("typOchranyKod") == "SD",
                "upresneni_ochrany": a.get("upresneniTypuOchrany"),
                "rejstrik": a.get("rejstrikoveCisloUSKP"),
                "prstav_id": str(a.get("pravniStavId")) if a.get("pravniStavId") else None,
                "chraneno": a.get("chraneno") == 1,
                "faze_ochrany": a.get("fazeOchranyNazev"),
                "rok_zapisu": _rok(a.get("datumStavuOchrany")),
                "url": a.get("urlExt"),
            },
        })
    return prvky


def _hranice_obce() -> dict | None:
    """Hranice města z modulu geodata, pokud už proběhl.

    Slouží jen k ověření, že plošná ochrana nalezená prostorově opravdu
    zasahuje do města. Když soubor není, ověření se přeskočí a řekne se to.
    """
    data = nacti("opendata/geo/hranice_obce.geojson")
    if not data or not data.get("features"):
        return None
    return data["features"][0].get("geometry")


def plochy(vybrane: dict[str, list[dict]], log: Log) -> tuple[list[dict], list[dict]]:
    """Plošná vymezení: zvlášť jednotlivé památky, zvlášť chráněná území."""
    ids_pamatek = [r["PrStavId"] for k in BODOVE for r in vybrane[k]]
    ids_uzemi = [r["PrStavId"] for k in PLOSNE for r in vybrane[k]]

    pamatky_plochy = []
    if ids_pamatek:
        pamatky_plochy = _plochy_dotaz(
            {"where": f"pravniStavId IN ({','.join(ids_pamatek)})"}, "npu-plochy-pamatky")
        for f in pamatky_plochy:
            f["properties"]["prislusnost_k_obci"] = "ÚSKP: obec uvedena u záznamu"
    log.info("plošná vymezení jednotlivých památek", prvku=len(pamatky_plochy))

    uzemi = []
    videno: set[str] = set()
    if ids_uzemi:
        for f in _plochy_dotaz({"where": f"pravniStavId IN ({','.join(ids_uzemi)})"},
                               "npu-plochy-uzemi-uskp"):
            f["properties"]["prislusnost_k_obci"] = "ÚSKP: obec uvedena u záznamu"
            uzemi.append(f)
            videno.add(f["properties"]["prstav_id"] or "")

    # Dohledání prostorem: CSV u nárazníkové zóny UNESCO neuvádí Mariánské
    # Lázně, přestože zóna nad městem leží. Bez tohohle kroku by ve výstupu
    # chyběla právě ta vrstva, kvůli které je město na seznamu UNESCO.
    hranice = _hranice_obce()
    if hranice is None:
        log.info("hranice obce zatím nejsou, prostorové dohledání se přeskakuje "
                 "(spusť nejdřív scrapers/geodata.py)")
    else:
        obdelnik = f"{BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]}"
        nalezene = _plochy_dotaz(
            {"geometry": obdelnik, "geometryType": "esriGeometryEnvelope",
             "inSR": 4326, "spatialRel": "esriSpatialRelIntersects",
             "where": "typOchranyKod <> 'KP'"}, "npu-plochy-uzemi-prostor")
        for f in nalezene:
            klic = f["properties"]["prstav_id"] or ""
            if klic in videno:
                continue
            if not _zasahuje_do_obce(f["geometry"], hranice):
                continue
            f["properties"]["prislusnost_k_obci"] = (
                "prostorový průnik s hranicí obce; ÚSKP u záznamu obec neuvádí")
            uzemi.append(f)
            videno.add(klic)

    uzemi.sort(key=lambda f: (f["properties"]["ochrana_kod"] or "",
                              f["properties"]["nazev"] or ""))
    log.info("chráněná území zasahující do města", prvku=len(uzemi),
             nazvy=[f["properties"]["nazev"] for f in uzemi])
    return pamatky_plochy, uzemi


def _zasahuje_do_obce(plocha: dict, hranice: dict) -> bool:
    """Hrubý, ale poctivý test: leží některý vrchol hranice obce uvnitř plochy?

    Není to úplný průnik polygonů — na to by projekt potřeboval geometrickou
    knihovnu. Pro chráněná území, která jsou vždy o řád větší než jednotlivé
    domy, to stačí; drobný útvar celý uvnitř obce a bez společného vrcholu by
    test minul, takže se používá jen jako doplněk k údaji z ÚSKP.
    """
    for polygon in hranice["coordinates"]:
        for bod in polygon[0][::5]:
            if bod_v_polygonu(bod, plocha):
                return True
    return False


# ==========================================================================
# Sestavení a zápis
# ==========================================================================

def zarad_do_uzemi(prvky: list[dict], uzemi: list[dict], log: Log) -> None:
    """Ke každé památce doplní, do jaké plošné ochrany její bod spadá.

    Kvůli UNESCO to je hlavní údaj, podle kterého se mapa dá filtrovat:
    „která z památek leží uvnitř statku Slavná lázeňská města Evropy".
    Počítá se z geometrie, ne z domněnky — nárazníková zóna má uprostřed
    díru a bod v ní tedy správně nespadá do zóny, ale do statku.
    """
    for f in prvky:
        bod = f["geometry"]["coordinates"]
        v_uzemich = [{"kod": u["properties"]["ochrana_kod"],
                      "nazev": u["properties"]["nazev"]}
                     for u in uzemi if bod_v_polygonu(bod, u["geometry"])]
        f["properties"]["v_uzemich"] = v_uzemich
        f["properties"]["unesco"] = any(u["kod"] == "SD" for u in v_uzemich)
    log.info("památky uvnitř statku UNESCO",
             pocet=sum(1 for f in prvky if f["properties"]["unesco"]),
             z_celkem=len(prvky))


def _kolekce(prvky: list[dict], popis: str, licence: str, zdroj: str,
             datum: str, navic: dict | None = None) -> dict:
    return {
        "type": "FeatureCollection",
        "name": popis,
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "souradnicovy_system": "WGS-84 (EPSG:4326), pořadí [délka, šířka]",
        "prevedeno_z": "S-JTSK / Křovák East North (EPSG:5514)",
        "parametry_prevodu": POSUN,
        "zdroj": zdroj,
        "licence": licence,
        "dolozka": dolozka(datum),
        "obec": {"kod": OBEC_KOD, "nazev": OBEC_NAZEV, "okres": OKRES},
        "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        **(navic or {}),
        "features": prvky,
    }


def main() -> None:
    argparse.ArgumentParser(description="Kulturní památky v Mariánských Lázních").parse_args()

    log = Log("pamatky")
    overe_prevod()

    datum = datum_aktualizace(log)
    vybrane = uskp(log)

    prstav_ids = {sada: [r["PrStavId"] for r in vybrane[sada]] for sada in BODOVE}
    souradnice = body(prstav_ids, log)

    prvky, bez_bodu = [], []
    for sada in BODOVE:
        for radek in vybrane[sada]:
            vlastnosti = _vlastnosti(radek, SADY[sada])
            bod = souradnice.get(radek["PrStavId"])
            if bod is None:
                bez_bodu.append(vlastnosti)
                continue
            prvky.append({
                "type": "Feature",
                "geometry": bod["geometry"],
                "properties": {
                    **vlastnosti,
                    "sjtsk": bod["sjtsk"],
                    "lokalizace": bod["lokalizace"],
                    "chraneno": bod["chraneno"],
                    "faze_ochrany": bod["faze_ochrany"],
                    "rok_zapisu": bod["rok_zapisu"],
                    "ruian_stavebni_objekt": bod["ruian_stavebni_objekt"],
                },
            })

    if not prvky:
        raise ZdrojSelhal("žádná památka nedostala souřadnice — geoportál NPÚ selhal")

    # Ověření, že body opravdu padly do Mariánských Lázní. Špatný převod dá
    # čísla, která vypadají věrohodně, jen leží někde jinde.
    mimo = [f["properties"]["nazev"] for f in prvky
            if not (BBOX[0] <= f["geometry"]["coordinates"][0] <= BBOX[2]
                    and BBOX[1] <= f["geometry"]["coordinates"][1] <= BBOX[3])]
    if mimo:
        raise ZdrojSelhal(f"{len(mimo)} památek vyšlo mimo okolí města, "
                          f"převod souřadnic je špatně: {mimo[:3]}")

    prvky.sort(key=lambda f: (f["properties"]["sada"], f["properties"]["nazev"] or ""))
    pamatky_plochy, uzemi = plochy(vybrane, log)
    zarad_do_uzemi(prvky, uzemi, log)

    uloz(f"{CIL}/pamatky.geojson",
         _kolekce(prvky, "Kulturní a národní kulturní památky v Mariánských Lázních",
                  LICENCE_NPU + " | body: " + LICENCE_GEOPORTAL,
                  "NPÚ — otevřená data ÚSKP + geoportál NPÚ", datum,
                  {"datum_aktualizace_uskp": datum,
                   "bez_souradnic": len(bez_bodu),
                   "vysvetlivky": VYSVETLIVKY}))
    uloz(f"{CIL}/pamatky_plochy.geojson",
         _kolekce(pamatky_plochy, "Plošná vymezení jednotlivých památek",
                  LICENCE_PVO, "NPÚ — geoportál, CP_Prstav_PVO", datum))
    uloz(f"{CIL}/ochranna_uzemi.geojson",
         _kolekce(uzemi, "Plošná památková ochrana zasahující do Mariánských Lázní",
                  LICENCE_PVO, "NPÚ — geoportál, CP_Prstav_PVO", datum,
                  {"poznamka": ("Území přesahují hranice města; ukládá se celý "
                                "polygon, ne výřez, aby souhlasil s právním stavem.")}))
    if bez_bodu:
        uloz(f"{CIL}/pamatky_bez_bodu.json",
             {"generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
              "vysvetleni": ("Památky, které jsou v ÚSKP vedené v Mariánských "
                             "Lázních, ale geoportál k nim nemá definiční bod. "
                             "Poloha se nedopočítává ani neodhaduje."),
              "pocet": len(bez_bodu), "pamatky": bez_bodu})
    log.pricti(len(prvky))

    prehled = {sada: len(vybrane[sada]) for sada in SADY}
    uloz(f"{CIL}/zdroje.json", {
        "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "obec": {"kod": OBEC_KOD, "nazev": OBEC_NAZEV, "okres": OKRES},
        "souradnicovy_system_vystupu": "WGS-84 (EPSG:4326), pořadí [délka, šířka]",
        "prevod_souradnic": {
            "z": "S-JTSK / Křovák East North (EPSG:5514)",
            "do": "WGS-84 (EPSG:4326)",
            "parametry": POSUN,
            "provadi": "scrapers/geodata.py — stejná transformace jako u dat RÚIAN",
        },
        "zdroje": [
            {"nazev": "Otevřená data ÚSKP (Památkový katalog NPÚ)",
             "url": KATALOG + "/otevrena-data",
             "soubory": [OPENDATA.format(kod=k) for k in SADY],
             "provozovatel": "Národní památkový ústav",
             "licence": LICENCE_NPU,
             "povinna_dolozka": dolozka(datum),
             "datum_aktualizace": datum,
             "aktualizace": "1× měsíčně k poslednímu dni měsíce",
             "puvodni_crs": "žádné — sady souřadnice neobsahují",
             "zaznamu_v_ml": prehled},
            {"nazev": "Geoportál NPÚ — definiční body památek",
             "url": VRSTVY_BODU["KP"],
             "provozovatel": "Národní památkový ústav",
             "copyright_sluzby": sluzba_licence(VRSTVY_BODU["KP"]),
             "licence": LICENCE_GEOPORTAL,
             "puvodni_crs": "EPSG:5514",
             "bodu": len(prvky)},
            {"nazev": "Geoportál NPÚ — plošná vymezení ochrany",
             "url": VRSTVA_PLOCH,
             "provozovatel": "Národní památkový ústav",
             # Tahle služba v copyrightText uvádí jen autora, licenci ne.
             # Nedomýšlíme si ji: ukládá se doslovné znění i to, že chybí.
             "copyright_sluzby": sluzba_licence(VRSTVA_PLOCH),
             "licence": LICENCE_PVO,
             "puvodni_crs": "EPSG:5514",
             "ploch_pamatek": len(pamatky_plochy),
             "chranenych_uzemi": len(uzemi)},
        ],
        "vystupy": {
            "pamatky.geojson": len(prvky),
            "pamatky_plochy.geojson": len(pamatky_plochy),
            "ochranna_uzemi.geojson": len(uzemi),
            "pamatky_bez_bodu.json": len(bez_bodu),
        },
        "unesco": [f["properties"]["nazev"] for f in uzemi
                   if f["properties"]["ochrana_kod"] in ("SD", "NZ")],
    })

    if bez_bodu:
        log.info("památky bez souřadnic", pocet=len(bez_bodu),
                 nazvy=[p["nazev"] for p in bez_bodu][:5])
    log.uzavri()


if __name__ == "__main__":
    main()
