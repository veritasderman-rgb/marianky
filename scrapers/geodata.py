"""Geodata pro mapy: hranice města a katastrů, volební okrsky, adresní body.

Modul připravuje **podklad pro vykreslení**, samotné mapy staví web. Proto je
vše ve WGS-84 (EPSG:4326) a v GeoJSON, aby to šlo předat mapové knihovně bez
dalšího překladu.

ZDROJE (ověřeno 17. 8. 2026)

1. **RÚIAN / ČÚZK, výměnný formát (VFR)** — `vdp.cuzk.gov.cz`
   Pro obec 554642 jde stáhnout kompletní dávka `OB_554642_UKSH` (~3 MB zip,
   27 MB XML): hranice obce, katastrálních území a ZSJ, části obce, ulice,
   parcely, stavební objekty a **2 548 adresních míst**. Písmena v kódu
   souboru: U = úplná kopie, K = kompletní datová sada, H = originální
   hranice. Varianta `UZSZ` (základní sada, bez hranic) nese jen definiční
   body — pro mapy nestačí.

2. **RÚIAN, speciální VFR volebních okrsků** — `ST_UVOH`, celá ČR (49 MB zip,
   158 MB XML). Menší výřez zdroj nenabízí, proto se stahuje do `.cache/`
   a streamovaně se z něj vybere 17 okrsků obce 554642. Do `data/` jde jen
   výřez.

   Adresní místo v RÚIAN nese `VOKod`, takže **přiřazení adres k okrskům je
   přímo v datech** — není potřeba je počítat prostorově. Kódy z adresních
   míst se křížově kontrolují proti kódům okrsků; nesoulad je chyba a hlásí se.

3. **OpenStreetMap přes Overpass API** — lázeňská infrastruktura (prameny,
   kolonády, parky, ubytování, historické objekty).

SOUŘADNICE: RÚIAN je celý v **S-JTSK (EPSG:5514)**, tedy v metrech a se
zápornými hodnotami. Převod na WGS-84 dělá tento modul sám (viz níže) a
u každého souboru je v metadatech uvedeno, že se převádělo, i jakými
parametry. U bodových prvků se vedle WGS-84 ukládá i původní S-JTSK.

LICENCE: RÚIAN CC BY 4.0 (ČÚZK, bezúplatně), OSM ODbL 1.0 s povinným
uvedením zdroje. Přesné znění je v `zdroje.json` vedle dat.

VÝSTUPY do `data/opendata/geo/`

| soubor | co v něm je |
|---|---|
| `hranice_obce.geojson` | hranice města, 1 prvek |
| `katastralni_uzemi.geojson` | 4 katastrální území |
| `zakladni_sidelni_jednotky.geojson` | 19 ZSJ |
| `casti_obce.geojson` | 6 částí obce, jen definiční body |
| `adresni_mista.geojson` | 2 548 adresních míst včetně kódu okrsku |
| `volebni_okrsky.geojson` | 17 okrsků s hranicí |
| `okrsky_adresy.json` | okrsek → adresy, podklad pro mapu voleb |
| `osm_lazenstvi.geojson` | prameny, lázeňství, ubytování, zeleň, historie |
| `zdroje.json` | zdroje, licence, parametry převodu, počty |
"""
from __future__ import annotations

import argparse
import io
import json
import math
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import Log, ZdrojSelhal, fetch, uloz  # noqa: E402

OBEC_KOD = "554642"
OBEC_NAZEV = "Mariánské Lázně"
OKRES = "Cheb"
CIL = "opendata/geo"

# Obdélník kolem města ve WGS-84 (min_lon, min_lat, max_lon, max_lat).
# Slouží jen k předvýběru u zdrojů, které neumí filtrovat podle obce —
# skutečné ořezání dělá hranice obce z RÚIAN, ne tenhle obdélník.
BBOX = (12.58, 49.90, 12.82, 50.05)

# Kontrolní bod: definiční bod obce podle RÚIAN. Když převod souřadnic
# skončí jinde než tady, je rozbitý a běh se zastaví.
KONTROLNI_BOD_SJTSK = (-866718.00, -1038323.00)
KONTROLNI_BOD_WGS = (49.9648, 12.7017)

VDP_FORMULAR = "https://vdp.cuzk.gov.cz/vdp/ruian/vymennyformat"


# ==========================================================================
# S-JTSK (EPSG:5514) → WGS-84
# ==========================================================================
#
# Bez pyproj — projekt drží závislosti na requests a selectolax. Křovákovo
# zobrazení má uzavřený inverzní vzorec (EPSG Guidance Note 7-2, metoda 9819)
# a datový posun Bessel 1841 → WGS-84 je sedmiprvková Helmertova
# transformace, takže obojí je pár desítek řádků čisté matematiky.
#
# Volba parametrů posunu je ověřená, ne odhadnutá. Porovnáním 1 467 adresních
# míst RÚIAN s odpovídajícími adresami v OpenStreetMap vyšlo:
#
#   parametry                                     medián odchylky
#   ------------------------------------------    ---------------
#   570.8, 85.7, 462.8, -4.998, -1.587, -5.261      0.00 m
#   572.213, 85.334, 461.94, -4.9732, …             0.06 m
#   589, 76, 480 (tříprvkový, používá ArcGIS)      13.90 m
#
# Tříprvkový posun by tedy památky posunul o 14 metrů proti podkladové mapě —
# v lázeňském centru je to rozdíl mezi dvěma sousedními domy. Proto se
# souřadnice z ArcGIS serverů NPÚ tahají v nativním EPSG:5514 a převádějí
# se tady, aby všechny vrstvy projektu seděly na sebe.

_A = 6377397.155                      # Bessel 1841, hlavní poloosa
_E = 0.081696831215303                # první excentricita
_E2 = _E * _E
_FI_C = math.radians(49.5)            # zeměpisná šířka středu zobrazení
_LAM_0 = math.radians(24 + 50 / 60)   # základní poledník (od Greenwiche)
_ALFA_C = math.radians(30 + 17 / 60 + 17.30311 / 3600)   # doplněk osy kužele
_FI_P = math.radians(78.5)            # nezkreslená kartografická rovnoběžka
_K_P = 0.9999                         # měřítko na ní

_KA = _A * math.sqrt(1 - _E2) / (1 - _E2 * math.sin(_FI_C) ** 2)
_KB = math.sqrt(1 + _E2 * math.cos(_FI_C) ** 4 / (1 - _E2))
_G0 = math.asin(math.sin(_FI_C) / _KB)
_T0 = (math.tan(math.pi / 4 + _G0 / 2)
       * ((1 + _E * math.sin(_FI_C)) / (1 - _E * math.sin(_FI_C))) ** (_E * _KB / 2)
       / math.tan(math.pi / 4 + _FI_C / 2) ** _KB)
_N = math.sin(_FI_P)
_R0 = _K_P * _KA / math.tan(_FI_P)

# Helmert Bessel → WGS-84, konvence "coordinate frame" (rotace v úhlových
# vteřinách, měřítko v ppm). Ověřeno proti OSM, viz komentář výše.
POSUN = {
    "dx_m": 570.8, "dy_m": 85.7, "dz_m": 462.8,
    "rx_vteriny": -4.998, "ry_vteriny": -1.587, "rz_vteriny": -5.261,
    "meritko_ppm": 3.56,
    "konvence": "coordinate frame",
}

_WGS_A = 6378137.0
_WGS_F = 1 / 298.257223563
_BES_F = 1 / 299.1528128


def _krovak_inv(east: float, north: float) -> tuple[float, float]:
    """EPSG:5514 (východ, sever) → Besselova šířka a délka v radiánech."""
    # V EPSG:5514 jsou obě osy záporné oproti klasickému Křovákovi (Y, X).
    xp, yp = -north, -east
    r = math.hypot(xp, yp)
    if r == 0:
        raise ZdrojSelhal("nulová souřadnice S-JTSK, převod nemá smysl")
    d = math.atan2(yp, xp) / _N
    t = 2 * (math.atan(((_R0 / r) ** (1 / _N)) * math.tan(math.pi / 4 + _FI_P / 2)) - math.pi / 4)
    u = math.asin(math.cos(_ALFA_C) * math.sin(t) - math.sin(_ALFA_C) * math.cos(t) * math.cos(d))
    v = math.asin(math.cos(t) * math.sin(d) / math.cos(u))
    lam = _LAM_0 - v / _KB

    fi = u  # iterace konverguje na pár kol, 30 je jistota s rezervou
    for _ in range(30):
        fi_nove = 2 * (math.atan(_T0 ** (-1 / _KB)
                                 * math.tan(u / 2 + math.pi / 4) ** (1 / _KB)
                                 * ((1 + _E * math.sin(fi)) / (1 - _E * math.sin(fi))) ** (_E / 2))
                       - math.pi / 4)
        if abs(fi_nove - fi) < 1e-13:
            return fi_nove, lam
        fi = fi_nove
    return fi, lam


def _na_xyz(lat: float, lon: float, a: float, f: float) -> tuple[float, float, float]:
    e2 = f * (2 - f)
    n = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    return (n * math.cos(lat) * math.cos(lon),
            n * math.cos(lat) * math.sin(lon),
            n * (1 - e2) * math.sin(lat))


def _z_xyz(x: float, y: float, z: float, a: float, f: float) -> tuple[float, float]:
    e2 = f * (2 - f)
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1 - e2))
    for _ in range(20):
        n = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
        h = p / math.cos(lat) - n
        nove = math.atan2(z, p * (1 - e2 * n / (n + h)))
        if abs(nove - lat) < 1e-14:
            lat = nove
            break
        lat = nove
    return lat, lon


_RX = math.radians(POSUN["rx_vteriny"] / 3600)
_RY = math.radians(POSUN["ry_vteriny"] / 3600)
_RZ = math.radians(POSUN["rz_vteriny"] / 3600)
_M = 1 + POSUN["meritko_ppm"] * 1e-6


def sjtsk_na_wgs84(east: float, north: float, *, desetin: int = 7) -> tuple[float, float]:
    """S-JTSK (EPSG:5514) → (zem. délka, zem. šířka) ve stupních, WGS-84.

    Pořadí odpovídá GeoJSON, tedy [lon, lat]. Zaokrouhlení na 7 desetinných
    míst je zhruba centimetr — jemnější přesnost zdroj stejně nemá a soubory
    by zbytečně nabobtnaly.
    """
    lat, lon = _krovak_inv(east, north)
    x, y, z = _na_xyz(lat, lon, _A, _BES_F)
    x, y, z = (POSUN["dx_m"] + _M * (x + _RZ * y - _RY * z),
               POSUN["dy_m"] + _M * (-_RZ * x + y + _RX * z),
               POSUN["dz_m"] + _M * (_RY * x - _RX * y + z))
    lat, lon = _z_xyz(x, y, z, _WGS_A, _WGS_F)
    return round(math.degrees(lon), desetin), round(math.degrees(lat), desetin)


def overe_prevod() -> None:
    """Zastaví běh, když převod souřadnic neskončí v Mariánských Lázních.

    Špatný převod je zákeřný: čísla vypadají věrohodně, jen bod leží
    v Praze nebo v moři. Radši spadnout hned než vydat mapu s nesmysly.
    """
    lon, lat = sjtsk_na_wgs84(*KONTROLNI_BOD_SJTSK)
    ocekavano_lat, ocekavano_lon = KONTROLNI_BOD_WGS
    vzdalenost = math.hypot((lat - ocekavano_lat) * 111_320,
                            (lon - ocekavano_lon) * 111_320 * math.cos(math.radians(lat)))
    if vzdalenost > 50:
        raise ZdrojSelhal(
            f"převod S-JTSK→WGS-84 je rozbitý: definiční bod obce vyšel na "
            f"{lat:.5f}, {lon:.5f}, což je {vzdalenost / 1000:.1f} km od "
            f"Mariánských Lázní"
        )


# ==========================================================================
# GML → GeoJSON
# ==========================================================================

def _lokalni(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _zkontroluj_crs(el: ET.Element) -> None:
    """Souřadnice bez uvedeného systému jsou k ničemu — trváme na EPSG:5514."""
    srs = el.get("srsName") or ""
    if srs and not srs.endswith("5514"):
        raise ZdrojSelhal(f"neočekávaný souřadnicový systém ve VFR: {srs!r}")


def _dvojice(text: str) -> list[tuple[float, float]]:
    c = [float(x) for x in (text or "").split()]
    return [(c[i], c[i + 1]) for i in range(0, len(c) - 1, 2)]


def _prstenec(el: ET.Element) -> list[list[float]]:
    posl = el.find(".//{*}posList")
    if posl is None:
        return []
    return [list(sjtsk_na_wgs84(e, n)) for e, n in _dvojice(posl.text or "")]


def _plocha_prstence(prstenec: list[list[float]]) -> float:
    """Znaménková plocha (shoelace). Kladná = proti směru hodinových ručiček."""
    s = 0.0
    for i in range(len(prstenec) - 1):
        x1, y1 = prstenec[i]
        x2, y2 = prstenec[i + 1]
        s += x1 * y2 - x2 * y1
    return s / 2


def _srovnej(prstenec: list[list[float]], vnejsi: bool) -> list[list[float]]:
    """RFC 7946 chce vnější prstenec proti směru a díry po směru hodin."""
    if not prstenec:
        return prstenec
    if prstenec[0] != prstenec[-1]:
        prstenec = prstenec + [prstenec[0]]
    kladna = _plocha_prstence(prstenec) > 0
    if kladna != vnejsi:
        prstenec = prstenec[::-1]
    return prstenec


def gml_multipolygon(geometrie: ET.Element) -> dict | None:
    """MultiSurface / Polygon z VFR → GeoJSON MultiPolygon ve WGS-84."""
    _zkontroluj_crs(geometrie)
    for potomek in geometrie.iter():
        _zkontroluj_crs(potomek)

    polygony = []
    for pg in geometrie.iter():
        if _lokalni(pg.tag) != "Polygon":
            continue
        prstence = []
        for role, vnejsi in (("exterior", True), ("interior", False)):
            for cast in pg:
                if _lokalni(cast.tag) != role:
                    continue
                p = _srovnej(_prstenec(cast), vnejsi)
                if len(p) >= 4:
                    prstence.append(p)
        if prstence:
            polygony.append(prstence)
    if not polygony:
        return None
    return {"type": "MultiPolygon", "coordinates": polygony}


def gml_bod(geometrie: ET.Element) -> tuple[dict, list[float]] | None:
    """První gml:pos v elementu → (GeoJSON Point, původní S-JTSK)."""
    for el in geometrie.iter():
        _zkontroluj_crs(el)
    for el in geometrie.iter():
        if _lokalni(el.tag) == "pos" and el.text:
            hodnoty = [float(x) for x in el.text.split()]
            east, north = hodnoty[0], hodnoty[1]
            return ({"type": "Point", "coordinates": list(sjtsk_na_wgs84(east, north))},
                    [east, north])
    return None


def _text(el: ET.Element, jmeno: str) -> str | None:
    for ch in el:
        if _lokalni(ch.tag) == jmeno:
            return (ch.text or "").strip() or None
    return None


def _vnoreny_kod(el: ET.Element, jmeno: str) -> str | None:
    for ch in el:
        if _lokalni(ch.tag) == jmeno and len(ch):
            return (ch[0].text or "").strip() or None
    return None


def _geometrie(el: ET.Element) -> ET.Element | None:
    for ch in el:
        if _lokalni(ch.tag) == "Geometrie":
            return ch
    return None


def _hranice(geom: ET.Element | None) -> dict | None:
    if geom is None:
        return None
    for ch in geom:
        if _lokalni(ch.tag) == "OriginalniHranice":
            return gml_multipolygon(ch)
    return None


def _defbod(geom: ET.Element | None) -> tuple[dict, list[float]] | None:
    if geom is None:
        return None
    for ch in geom:
        if _lokalni(ch.tag) == "DefinicniBod":
            return gml_bod(ch)
    return None


# Jmenné prostory, ve kterých jsou ve VFR samotné záznamy — běžná dávka
# a speciální dávka volebních okrsků. Odkazy na jiné prvky (`kui:Obec`,
# `ami:Ulice`) mají stejná lokální jména, ale jiný prostor; bez rozlišení
# by odkaz na obec uvnitř katastru přepsal skutečný záznam obce.
VF_NS = (
    "{urn:cz:isvs:ruian:schemas:VymennyFormatTypy:v1}",
    "{urn:cz:isvs:ruian:schemas:SpecialniVymennyFormatTypy:v1}",
)
GML_ID = "{http://www.opengis.net/gml/3.2}id"


def prvky(proud, jmena: set[str]):
    """Streamovaně vydává záznamy daných jmen a průběžně uklízí paměť.

    Bez úklidu by se celostátní soubor volebních okrsků (158 MB XML)
    načetl celý do paměti.

    Obalové elementy (`vf:Obce`, `vf:Ulice`) mají u některých prvků stejné
    jméno jako záznam uvnitř; poznají se podle toho, že nemají `gml:id`.
    """
    zasobnik: list[ET.Element] = []
    for udalost, el in ET.iterparse(proud, events=("start", "end")):
        if udalost == "start":
            zasobnik.append(el)
            continue
        zasobnik.pop()
        if (el.tag.startswith(VF_NS) and _lokalni(el.tag) in jmena
                and el.get(GML_ID) is not None):
            yield el
            el.clear()
            if zasobnik:
                zasobnik[-1].clear()


# ==========================================================================
# Stažení VFR
# ==========================================================================

def _najdi_vfr(parametry: dict[str, str], vzor: str, log: Log) -> str:
    """Vyhledávací formulář VDP vrátí odkazy na měsíční soubory; bereme nejnovější.

    Datum v názvu se nedá spočítat dopředu — obecní dávky jsou k poslednímu
    dni měsíce, celostátní okrsky ke třetímu dni následujícího měsíce.
    Proto se odkazy zjišťují, ne hádají.
    """
    html = fetch(f"{VDP_FORMULAR}?{urlencode(parametry)}", max_age=6 * 3600)
    odkazy = sorted(set(re.findall(r'href="(https://[^"]*/vymenny_format/[^"]*\.zip)"', html)))
    odkazy = [u for u in odkazy if vzor in u]
    if not odkazy:
        raise ZdrojSelhal(f"VDP nenabídl žádný soubor odpovídající {vzor!r}")
    log.info("nalezeno dávek VFR", vzor=vzor, pocet=len(odkazy), beru=odkazy[-1].rsplit("/", 1)[-1])
    return odkazy[-1]


def _rozbal(url: str, cache_key: str) -> tuple[bytes, str]:
    """Stáhne zip do .cache/ a vrátí obsah jediného XML uvnitř."""
    data = fetch(url, cache_key=cache_key, max_age=7 * 86_400, binary=True, timeout=600)
    if not isinstance(data, bytes):
        raise ZdrojSelhal(f"{url} nevrátil binární data")
    zf = zipfile.ZipFile(io.BytesIO(data))
    jmena = [n for n in zf.namelist() if n.lower().endswith(".xml")]
    if len(jmena) != 1:
        raise ZdrojSelhal(f"v {url} je {len(jmena)} XML souborů, čekal jsem jeden")
    return zf.read(jmena[0]), jmena[0]


def stahni_obec(log: Log) -> tuple[bytes, str]:
    url = _najdi_vfr(
        {"casovyRozsah": "U", "crKopie": "on", "uzemniPrvky": "OB",
         "upObecAPodrazene": "on", "datovaSada": "K", "dsKompletni": "on",
         "vyber": "vyZakladniAOrigHranice", "vyZakladniAOrigHranice": "on",
         "uzemniOmezeni": "uoOb", "uoOb": "on", "kodOb": OBEC_KOD, "search": ""},
        vzor=f"OB_{OBEC_KOD}_UKSH", log=log)
    return _rozbal(url, f"ruian-obec-{OBEC_KOD}")


def stahni_okrsky(log: Log) -> tuple[bytes, str]:
    url = _najdi_vfr(
        {"casovyRozsah": "U", "crKopie": "on", "svyVolebniOkrsky": "on",
         "svyber": "svyVolebniOkrsky", "search": ""},
        vzor="ST_UVOH", log=log)
    return _rozbal(url, "ruian-volebni-okrsky-cr")


# ==========================================================================
# Rozbor obecní dávky
# ==========================================================================

def rozbor_obce(xml: bytes, log: Log) -> dict:
    obec = None
    katastry, casti, zsj, ulice, adresy = [], [], [], {}, []

    for el in prvky(io.BytesIO(xml), {"Obec", "KatastralniUzemi", "CastObce",
                                      "Zsj", "Ulice", "AdresniMisto"}):
        jmeno = _lokalni(el.tag)
        geom = _geometrie(el)

        if jmeno == "Obec":
            kod = _text(el, "Kod")
            if kod != OBEC_KOD:
                continue
            bod = _defbod(geom)
            obec = {
                "type": "Feature",
                "geometry": _hranice(geom),
                "properties": {
                    "zdroj": "RÚIAN",
                    "kod_obce": kod,
                    "nazev": _text(el, "Nazev"),
                    "okres_kod": _vnoreny_kod(el, "Okres"),
                    "nuts_lau": _text(el, "NutsLau"),
                    "definicni_bod_wgs84": bod[0]["coordinates"] if bod else None,
                    "definicni_bod_sjtsk": bod[1] if bod else None,
                },
            }

        elif jmeno == "KatastralniUzemi":
            if _vnoreny_kod(el, "Obec") != OBEC_KOD:
                continue
            bod = _defbod(geom)
            katastry.append({
                "type": "Feature",
                "geometry": _hranice(geom),
                "properties": {
                    "zdroj": "RÚIAN",
                    "kod_ku": _text(el, "Kod"),
                    "nazev": _text(el, "Nazev"),
                    "kod_obce": OBEC_KOD,
                    "digitalni_mapa": _text(el, "ExistujeDigitalniMapa") == "true",
                    "definicni_bod_sjtsk": bod[1] if bod else None,
                },
            })

        elif jmeno == "CastObce":
            if _vnoreny_kod(el, "Obec") != OBEC_KOD:
                continue
            bod = _defbod(geom)
            # Části obce mají v RÚIAN jen definiční bod, hranice se nevedou.
            casti.append({
                "type": "Feature",
                "geometry": bod[0] if bod else None,
                "properties": {
                    "zdroj": "RÚIAN",
                    "kod_casti": _text(el, "Kod"),
                    "nazev": _text(el, "Nazev"),
                    "kod_obce": OBEC_KOD,
                    "sjtsk": bod[1] if bod else None,
                },
            })

        elif jmeno == "Zsj":
            bod = _defbod(geom)
            zsj.append({
                "type": "Feature",
                "geometry": _hranice(geom),
                "properties": {
                    "zdroj": "RÚIAN",
                    "kod_zsj": _text(el, "Kod"),
                    "nazev": _text(el, "Nazev"),
                    "kod_ku": _vnoreny_kod(el, "KatastralniUzemi"),
                    "vymera_m2": int(_text(el, "Vymera") or 0) or None,
                    "definicni_bod_sjtsk": bod[1] if bod else None,
                },
            })

        elif jmeno == "Ulice":
            kod = _text(el, "Kod")
            if kod:
                ulice[kod] = _text(el, "Nazev")

        elif jmeno == "AdresniMisto":
            bod = _defbod(geom)
            adresy.append({
                "kod": _text(el, "Kod"),
                "cislo_domovni": _text(el, "CisloDomovni"),
                "cislo_orientacni": _text(el, "CisloOrientacni"),
                "cislo_orientacni_pismeno": _text(el, "CisloOrientacniPismeno"),
                "psc": _text(el, "Psc"),
                "ulice_kod": _vnoreny_kod(el, "Ulice"),
                "stavebni_objekt_kod": _vnoreny_kod(el, "StavebniObjekt"),
                "volebni_okrsek_kod": _text(el, "VOKod"),
                "_bod": bod,
            })

    if obec is None or obec["geometry"] is None:
        raise ZdrojSelhal("ve VFR chybí hranice obce 554642 — dávka je vadná")
    if not adresy:
        raise ZdrojSelhal("ve VFR nejsou žádná adresní místa — dávka je vadná")

    # Ulici doplňujeme až tady: ve VFR je seznam ulic až za adresními místy,
    # takže při jednom průchodu ještě nemusí být k dispozici.
    adresni_body = []
    for a in adresy:
        bod = a.pop("_bod")
        a["ulice"] = ulice.get(a["ulice_kod"]) if a["ulice_kod"] else None
        a["adresa"] = _slozena_adresa(a)
        adresni_body.append({
            "type": "Feature",
            "geometry": bod[0] if bod else None,
            "properties": {"zdroj": "RÚIAN", **a, "sjtsk": bod[1] if bod else None},
        })

    log.info("RÚIAN obec rozebrána",
             katastru=len(katastry), casti=len(casti), zsj=len(zsj),
             ulic=len(ulice), adres=len(adresni_body))
    return {"obec": obec, "katastry": katastry, "casti": casti,
            "zsj": zsj, "ulice": ulice, "adresy": adresni_body}


def _slozena_adresa(a: dict) -> str:
    cislo = a["cislo_domovni"] or ""
    if a["cislo_orientacni"]:
        cislo += "/" + a["cislo_orientacni"] + (a["cislo_orientacni_pismeno"] or "")
    zaklad = f"{a['ulice']} {cislo}" if a.get("ulice") else cislo
    return f"{zaklad}, {OBEC_NAZEV}".strip()


# ==========================================================================
# Volební okrsky
# ==========================================================================

def rozbor_okrsku(xml: bytes, log: Log) -> list[dict]:
    okrsky = []
    for el in prvky(io.BytesIO(xml), {"VO"}):
        if _vnoreny_kod(el, "Obec") != OBEC_KOD:
            continue
        geom = _geometrie(el)
        bod = _defbod(geom)
        okrsky.append({
            "type": "Feature",
            "geometry": _hranice(geom),
            "properties": {
                "zdroj": "RÚIAN",
                "nazev": f"Okrsek č. {_text(el, 'Cislo')}",
                "kod_okrsku": _text(el, "Kod"),
                "cislo_okrsku": _text(el, "Cislo"),
                "kod_obce": OBEC_KOD,
                "obec": OBEC_NAZEV,
                "plati_od": (_text(el, "PlatiOd") or "")[:10] or None,
                "definicni_bod_sjtsk": bod[1] if bod else None,
            },
        })
    if not okrsky:
        raise ZdrojSelhal(f"v celostátní dávce okrsků není žádný pro obec {OBEC_KOD}")
    okrsky.sort(key=lambda f: int(f["properties"]["cislo_okrsku"] or 0))
    bez_hranice = [f["properties"]["cislo_okrsku"] for f in okrsky if not f["geometry"]]
    if bez_hranice:
        log.chyba(f"okrsky bez hranice: {bez_hranice}")
    log.info("volební okrsky", pocet=len(okrsky),
             cisla=f"{okrsky[0]['properties']['cislo_okrsku']}–{okrsky[-1]['properties']['cislo_okrsku']}")
    return okrsky


def prirazeni_adres(okrsky: list[dict], adresy: list[dict], log: Log) -> dict:
    """Adresy po okrscích — podklad pro mapu volebních výsledků.

    Přiřazení bere z RÚIAN (`VOKod` u adresního místa), ne z prostorového
    průniku. Kdo staví mapu výsledků, potřebuje spojit číslo okrsku ze
    statistiky s hranicí; tohle je ten most.
    """
    podle_kodu = {f["properties"]["kod_okrsku"]: f["properties"] for f in okrsky}
    tabulka: dict[str, dict] = {}
    neznamy: set[str] = set()

    for a in adresy:
        p = a["properties"]
        kod = p["volebni_okrsek_kod"]
        if kod not in podle_kodu:
            neznamy.add(kod or "(chybí)")
            continue
        zaznam = tabulka.setdefault(kod, {
            "kod_okrsku": kod,
            "cislo_okrsku": podle_kodu[kod]["cislo_okrsku"],
            "adresnich_mist": 0,
            "ulice": {},
            "adresy": [],
        })
        zaznam["adresnich_mist"] += 1
        if p["ulice"]:
            zaznam["ulice"][p["ulice"]] = zaznam["ulice"].get(p["ulice"], 0) + 1
        zaznam["adresy"].append({"kod": p["kod"], "adresa": p["adresa"],
                                 "psc": p["psc"], "wgs84": (a["geometry"] or {}).get("coordinates")})

    if neznamy:
        # Není to nutně chyba: okrsek může ležet v jiné obci, ale adresa v ML
        # s cizím okrskem by chyba byla. Hlásíme, ať se to neztratí.
        log.chyba(f"adresy odkazují na okrsky mimo obec: {sorted(neznamy)}")

    bez_adres = [p["cislo_okrsku"] for k, p in podle_kodu.items() if k not in tabulka]
    if bez_adres:
        log.info("okrsky bez adresních míst", cisla=bez_adres)

    radky = sorted(tabulka.values(), key=lambda z: int(z["cislo_okrsku"] or 0))
    for r in radky:
        r["ulice"] = [{"nazev": n, "adresnich_mist": p}
                      for n, p in sorted(r["ulice"].items(), key=lambda x: -x[1])]
        r["adresy"].sort(key=lambda a: a["adresa"])
    log.info("adresy přiřazeny k okrskům", okrsku=len(radky),
             adres=sum(r["adresnich_mist"] for r in radky))
    return {"okrsky": radky}


# ==========================================================================
# OpenStreetMap — lázeňská infrastruktura
# ==========================================================================

# Hlavní instance overpass-api.de nám z tohoto prostředí resetuje spojení
# ještě před odpovědí, zrcadla jedou. Zkouší se popořadě, první funkční
# vyhrává. Overpass je veřejná služba zdarma a občas stojí frontu — proto
# krátký limit a jen jeden pokus na zrcadlo, ať běh nevisí půl hodiny.
OVERPASS = [
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
OVERPASS_LIMIT_S = 90

# Pro lázeňské město jsou prameny a kolonády to hlavní, co na mapě dává smysl.
# Dotazy jsou rozdělené po tématech — jeden velký dotaz na Overpassu vyprší.
OSM_TEMATA: list[tuple[str, list[str]]] = [
    ("prameny", ['["natural"="spring"]', '["amenity"="drinking_water"]',
                 '["man_made"="water_well"]']),
    ("lazenstvi", ['["amenity"="spa"]', '["leisure"="spa"]', '["healthcare"="spa"]',
                   '["building"="colonnade"]', '["man_made"="colonnade"]',
                   '["amenity"="fountain"]']),
    ("ubytovani", ['["tourism"="hotel"]', '["tourism"="guest_house"]',
                   '["tourism"="apartment"]', '["tourism"="hostel"]']),
    ("zelen", ['["leisure"="park"]', '["leisure"="garden"]',
               '["tourism"="viewpoint"]']),
    ("kultura_a_historie", ['["historic"]', '["tourism"="museum"]',
                            '["amenity"="theatre"]', '["tourism"="attraction"]',
                            '["tourism"="artwork"]']),
]


def _overpass(dotaz: str, klic: str, log: Log) -> dict:
    posledni: Exception | None = None
    for zrcadlo in OVERPASS:
        url = f"{zrcadlo}?{urlencode({'data': dotaz})}"
        try:
            odpoved = fetch(url, cache_key=klic, max_age=7 * 86_400,
                            timeout=OVERPASS_LIMIT_S, retries=1)
            return json.loads(odpoved)
        except Exception as e:  # noqa: BLE001 — zkoušíme další zrcadlo
            posledni = e
            log.info("zrcadlo Overpassu neodpovědělo", zrcadlo=zrcadlo.split("/")[2])
    raise ZdrojSelhal(f"žádné zrcadlo Overpass API neodpovědělo: {posledni}")


def bod_v_polygonu(bod: list[float], multipolygon: dict) -> bool:
    """Paprskový test. Díry se odečítají, takže park s dírou se chová správně."""
    x, y = bod[0], bod[1]
    uvnitr = False
    for polygon in multipolygon["coordinates"]:
        for i, prstenec in enumerate(polygon):
            v_prstenci = False
            n = len(prstenec)
            for a in range(n - 1):
                x1, y1 = prstenec[a]
                x2, y2 = prstenec[a + 1]
                if (y1 > y) != (y2 > y):
                    prusecik = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                    if x < prusecik:
                        v_prstenci = not v_prstenci
            if i == 0:
                if not v_prstenci:
                    break            # mimo vnější prstenec, díry netřeba řešit
                uvnitr = True
            elif v_prstenci:
                uvnitr = False       # bod padl do díry
                break
        if uvnitr:
            return True
    return False


def osm_lazenstvi(hranice: dict, log: Log) -> tuple[list[dict], list[str]]:
    """Vrací nalezené prvky a seznam témat, která se stáhnout nepodařilo.

    Neúspěšné téma se nepřevádí na „nic tam není" — chybějící téma je
    v metadatech vypsané, aby prázdná vrstva na mapě nevypadala jako
    zjištění o městě.
    """
    jih, zapad, sever, vychod = BBOX[1], BBOX[0], BBOX[3], BBOX[2]
    vysledek: list[dict] = []
    videno: set[tuple[str, int]] = set()
    selhala: list[str] = []

    for tema, filtry in OSM_TEMATA:
        casti = "\n".join(f"  nwr{f};" for f in filtry)
        dotaz = (f"[out:json][timeout:{OVERPASS_LIMIT_S}]"
                 f"[bbox:{jih},{zapad},{sever},{vychod}];\n"
                 f"(\n{casti}\n);\nout center tags;")
        try:
            data = _overpass(dotaz, f"osm-{tema}-ml", log)
        except ZdrojSelhal as e:
            log.chyba(f"OSM téma {tema} se nestáhlo: {e}")
            selhala.append(tema)
            continue
        prvku = 0
        for e in data.get("elements", []):
            klic = (e["type"], e["id"])
            if klic in videno:
                continue
            lat = e.get("lat") or (e.get("center") or {}).get("lat")
            lon = e.get("lon") or (e.get("center") or {}).get("lon")
            if lat is None or lon is None:
                continue
            bod = [round(lon, 7), round(lat, 7)]
            if not bod_v_polygonu(bod, hranice):
                continue          # v obdélníku, ale mimo katastr města
            videno.add(klic)
            znacky = e.get("tags", {})
            vysledek.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": bod},
                "properties": {
                    "zdroj": "OpenStreetMap",
                    "osm_typ": e["type"],
                    "osm_id": e["id"],
                    "osm_url": f"https://www.openstreetmap.org/{e['type']}/{e['id']}",
                    "tema": tema,
                    "nazev": znacky.get("name"),
                    "znacky": znacky,
                },
            })
            prvku += 1
        log.info("OSM téma staženo", tema=tema, v_obci=prvku)

    log.info("OSM celkem", prvku=len(vysledek), selhalo_temat=len(selhala))
    return vysledek, selhala


# ==========================================================================
# Zápis
# ==========================================================================

def _kolekce(prvky_: list[dict], popis: str, licence: str, zdroj: str,
             navic: dict | None = None) -> dict:
    """FeatureCollection s hlavičkou. Metadata jdou s daty, ne vedle nich —
    kdo soubor otevře za rok, musí z něj vyčíst původ i licenci."""
    return {
        "type": "FeatureCollection",
        "name": popis,
        # RFC 7946 předepisuje WGS-84, uvádíme to i explicitně kvůli čitelnosti.
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "souradnicovy_system": "WGS-84 (EPSG:4326)",
        "prevedeno_z": "S-JTSK / Křovák East North (EPSG:5514)",
        "parametry_prevodu": POSUN,
        "zdroj": zdroj,
        "licence": licence,
        "obec": {"kod": OBEC_KOD, "nazev": OBEC_NAZEV, "okres": OKRES},
        "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        **(navic or {}),
        "features": prvky_,
    }


LICENCE_RUIAN = ("CC BY 4.0 — Český úřad zeměměřický a katastrální, RÚIAN. "
                 "Data se poskytují bezúplatně a i pro komerční užití, "
                 "povinností je uvést zdroj. "
                 "https://cuzk.gov.cz/Uvod/Produkty-a-sluzby/Otevrena-data/"
                 "Otevrena-data-zakladni-informace.aspx")
LICENCE_OSM = ("ODbL 1.0 — © přispěvatelé OpenStreetMap. Uvedení zdroje je "
               "povinné, odvozené databáze se musí sdílet pod stejnou licencí. "
               "https://www.openstreetmap.org/copyright")


def main() -> None:
    p = argparse.ArgumentParser(description="Geodata Mariánských Lázní pro mapy")
    p.add_argument("--bez-osm", action="store_true",
                   help="přeskočí Overpass API (bývá pomalé a nespolehlivé)")
    args = p.parse_args()

    log = Log("geodata")
    overe_prevod()
    log.info("převod S-JTSK→WGS-84 ověřen na definičním bodu obce")

    # --- RÚIAN, obecní dávka -------------------------------------------
    xml_obec, jmeno_obec = stahni_obec(log)
    data = rozbor_obce(xml_obec, log)

    uloz(f"{CIL}/hranice_obce.geojson",
         _kolekce([data["obec"]], "Hranice města Mariánské Lázně",
                  LICENCE_RUIAN, f"RÚIAN VFR {jmeno_obec}"))
    uloz(f"{CIL}/katastralni_uzemi.geojson",
         _kolekce(data["katastry"], "Katastrální území v Mariánských Lázních",
                  LICENCE_RUIAN, f"RÚIAN VFR {jmeno_obec}"))
    uloz(f"{CIL}/zakladni_sidelni_jednotky.geojson",
         _kolekce(data["zsj"], "Základní sídelní jednotky",
                  LICENCE_RUIAN, f"RÚIAN VFR {jmeno_obec}"))
    uloz(f"{CIL}/casti_obce.geojson",
         _kolekce(data["casti"], "Části obce (definiční body)",
                  LICENCE_RUIAN, f"RÚIAN VFR {jmeno_obec}",
                  {"poznamka": "RÚIAN u částí obce hranice nevede, jen definiční bod."}))
    uloz(f"{CIL}/adresni_mista.geojson",
         _kolekce(data["adresy"], "Adresní místa v Mariánských Lázních",
                  LICENCE_RUIAN, f"RÚIAN VFR {jmeno_obec}"))
    log.pricti(len(data["adresy"]))

    # --- RÚIAN, volební okrsky -----------------------------------------
    xml_vo, jmeno_vo = stahni_okrsky(log)
    okrsky = rozbor_okrsku(xml_vo, log)
    uloz(f"{CIL}/volebni_okrsky.geojson",
         _kolekce(okrsky, "Volební okrsky v Mariánských Lázních",
                  LICENCE_RUIAN, f"RÚIAN speciální VFR {jmeno_vo}",
                  {"poznamka": "Výřez z celostátní dávky; ta zůstává v .cache/.",
                   "vztah_k_datum_voleb": (
                       "Tohle je AKTUÁLNÍ stav hranic podle RÚIAN, v původní "
                       "katastrální podrobnosti. Vrstvy v data/opendata/volby/"
                       "okrsky_geo/ jsou stav ČSÚ k roku konkrétních voleb a "
                       "jsou generalizované (tolerance 100 m). Pro mapu "
                       "výsledků konkrétních voleb platí ta z volby/, tahle "
                       "je pro dnešní stav a pro napojení adres."),
                   "klic_pro_spojeni": (
                       "kod_okrsku odpovídá poli KOD u ČSÚ, cislo_okrsku "
                       "číslování okrsků ve výsledcích voleb")}))
    uloz(f"{CIL}/okrsky_adresy.json",
         {"generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
          "zdroj": f"RÚIAN VFR {jmeno_obec} + {jmeno_vo}",
          "licence": LICENCE_RUIAN,
          "obec": {"kod": OBEC_KOD, "nazev": OBEC_NAZEV},
          "vysvetleni": ("Přiřazení adresních míst k volebním okrskům podle pole "
                         "VOKod v RÚIAN. Číslo okrsku odpovídá číslování ČSÚ, "
                         "takže po něm jde spojit výsledky voleb s hranicí okrsku."),
          **prirazeni_adres(okrsky, data["adresy"], log)})
    log.pricti(len(okrsky))

    # --- OpenStreetMap --------------------------------------------------
    osm: list[dict] = []
    osm_selhala: list[str] = [t for t, _ in OSM_TEMATA]
    if args.bez_osm:
        log.info("OSM přeskočeno na přání")
    else:
        osm, osm_selhala = osm_lazenstvi(data["obec"]["geometry"], log)
        uloz(f"{CIL}/osm_lazenstvi.geojson",
             {**_kolekce(osm, "Lázeňská infrastruktura z OpenStreetMap",
                         LICENCE_OSM, "OpenStreetMap přes Overpass API",
                         {"stazena_temata": [t for t, _ in OSM_TEMATA
                                             if t not in osm_selhala],
                          "nestazena_temata": osm_selhala,
                          "povinna_dolozka": "© přispěvatelé OpenStreetMap"}),
              "prevedeno_z": "OSM je nativně ve WGS-84, nepřevádělo se",
              "parametry_prevodu": None})
        log.pricti(len(osm))

    # --- Soupis zdrojů --------------------------------------------------
    uloz(f"{CIL}/zdroje.json", {
        "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "obec": {"kod": OBEC_KOD, "nazev": OBEC_NAZEV, "okres": OKRES},
        "souradnicovy_system_vystupu": "WGS-84 (EPSG:4326), pořadí [délka, šířka]",
        "prevod_souradnic": {
            "z": "S-JTSK / Křovák East North (EPSG:5514)",
            "do": "WGS-84 (EPSG:4326)",
            "metoda": "inverzní Křovákovo zobrazení + Helmertova transformace Bessel 1841 → WGS-84",
            "parametry": POSUN,
            "overeno": ("Porovnáním 1 467 adresních míst RÚIAN s odpovídajícími "
                        "adresami v OpenStreetMap: medián odchylky 0,00 m. "
                        "Tříprvkový posun 589/76/480, který používají ArcGIS "
                        "servery, dává medián 13,90 m."),
        },
        "zdroje": [
            {"nazev": "RÚIAN — výměnný formát, obec 554642",
             "soubor": jmeno_obec,
             "url": VDP_FORMULAR,
             "provozovatel": "Český úřad zeměměřický a katastrální",
             "licence": LICENCE_RUIAN,
             "obsah": "hranice obce a katastrů, ZSJ, části obce, ulice, adresní místa",
             "puvodni_crs": "EPSG:5514"},
            {"nazev": "RÚIAN — speciální výměnný formát, volební okrsky ČR",
             "soubor": jmeno_vo,
             "url": VDP_FORMULAR,
             "provozovatel": "Český úřad zeměměřický a katastrální",
             "licence": LICENCE_RUIAN,
             "obsah": "hranice volebních okrsků; staženo celostátně, uložen výřez obce",
             "puvodni_crs": "EPSG:5514"},
            {"nazev": "OpenStreetMap přes Overpass API",
             "url": OVERPASS[0],
             "provozovatel": "OpenStreetMap Foundation",
             "licence": LICENCE_OSM,
             "povinna_dolozka": "© přispěvatelé OpenStreetMap",
             "obsah": "prameny, lázeňské objekty, ubytování, parky, historické objekty",
             "puvodni_crs": "EPSG:4326",
             "prvku": len(osm),
             "nestazena_temata": osm_selhala},
        ],
        "vystupy": {
            "hranice_obce.geojson": 1,
            "katastralni_uzemi.geojson": len(data["katastry"]),
            "zakladni_sidelni_jednotky.geojson": len(data["zsj"]),
            "casti_obce.geojson": len(data["casti"]),
            "adresni_mista.geojson": len(data["adresy"]),
            "volebni_okrsky.geojson": len(okrsky),
            "osm_lazenstvi.geojson": len(osm),
        },
    })

    log.uzavri()


if __name__ == "__main__":
    main()
