"""Znaky sekcí — malá datová grafika, která na webu zastupuje ikonu.

PROČ TENHLE MODUL EXISTUJE
--------------------------
Web potřeboval na telefonu rozcestník, na kterém se sekce poznají dřív, než
se stihne přečíst popisek. Obvyklé řešení je ikonová sada. Do tohohle projektu
ale nepatří: design systém říká „obrazová složka je výhradně datová, každý
pixel má být údaj". Kreslený paragraf u usnesení nebo pytlík peněz u rozpočtu
by byl první dekorativní obrázek na webu, kde jinak všechno něco měří.

Znak sekce je proto miniaturní graf z jejích skutečných dat. Sekce „Peníze"
nemá vedle sebe minci, ale patnáct sloupečků skutečných ročních výdajů —
takže z rozcestníku je vidět nejen KAM odkaz vede, ale i JAK to tam vypadá.
Znaky se přepočítávají s daty; když do sekce přibude rok, přibude sloupec.

PRÁZDNO NENÍ NULA
-----------------
Neznámá hodnota se ukládá jako `null` a vykresluje se jako mezera, ne jako
nulový sloupec. Rok, ve kterém se opravdu nic nestalo, je nula a nakreslí se.
Rozdíl mezi „nic se nedělo" a „nevíme" drží i tahle drobná grafika.

VÝSTUP
------
data/znaky/sekce.json — pro každou sekci jeden znak:

    {"tvar": "sloupce", "hodnoty": [...], "osa": [...],
     "hodnota": "3,8 mld.", "jednotka": "Kč od roku 1994",
     "veta": "...", "stav": "ok", "zdroj": "..."}

Tvary, které web umí vykreslit (web/src/lib/znaky.ts):
    sloupce  — sloupcový graf, `null` = mezera
    pruh     — řada políček v sekvenční rampě (hustota v čase)
    mrizka   — mřížka buněk 0..1, `null` = prázdná buňka
    body     — tečky ve skupinách (lidé, uskupení)
    retez    — tři navazující uzly s počty
    sit      — dvě řady uzlů a hrany mezi nimi
    obrys    — skutečný polygon (hranice města) jako SVG path
    useky    — vodorovné úseky na časové ose (období dějin)
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import DATA, Log, nacti, uloz  # noqa: E402

# Kolik let zpět se kreslí do sloupcových znaků. Víc se do 120 px nevejde
# čitelně; méně by zakrylo trend.
LET_V_ZNAKU = 16

# Rok, pod který data v tomhle projektu nesahají. Registr smluv obsahuje
# záznamy s useknutým tisíciletím (rok 2, 25, 26) — do znaku nepatří.
PRVNI_ROZUMNY_ROK = 1990


def _cely(x) -> int | None:
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _rok(klic) -> int | None:
    r = _cely(klic)
    if r is None or r < PRVNI_ROZUMNY_ROK or r > 2100:
        return None
    return r


def _zkraceno(czk: float | None) -> str:
    """Částka do dlaždice. Stejná pravidla jako web/src/lib/format.ts."""
    if czk is None:
        return "—"
    a = abs(czk)
    if a >= 1_000_000_000:
        return f"{czk / 1_000_000_000:.2f}".replace(".", ",") + " mld."
    if a >= 1_000_000:
        return f"{czk / 1_000_000:.1f}".replace(".", ",") + " mil."
    if a >= 1_000:
        return f"{czk / 1_000:.0f}" + " tis."
    return f"{czk:.0f}"


def _mezerou(n: int | None) -> str:
    if n is None:
        return "—"
    return f"{n:,}".replace(",", " ")


def _chybi(klic: str, zdroj: str, veta: str) -> dict:
    """Znak pro sekci, jejíž data se nepodařilo načíst.

    Nekreslí se nic. Prázdný obrazec by tvrdil, že sekce je prázdná —
    přitom nevíme, co v ní je.
    """
    return {
        "tvar": "chybi",
        "pocet": None,
        "hodnota": "—",
        "jednotka": "",
        "veta": veta,
        "stav": "chybi",
        "zdroj": zdroj,
    }


# ═══════════════════════════  jednotlivé znaky  ═══════════════════════════


def znak_vydani() -> dict:
    """Týdenní přehled — kolik položek přinesla která z posledních vydání.

    Čte se z `data/vydani/*.json`; každý soubor je jedno číslo.
    """
    # index.json je rejstřík všech čísel, ne jedno číslo — do znaku nepatří.
    soubory = [p for p in sorted((DATA / "vydani").glob("*.json")) if p.stem != "index"]
    if not soubory:
        return _chybi("vydani", "data/vydani", "Zatím nevyšlo žádné číslo.")

    policka: list[dict] = []
    for p in soubory[-18:]:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            policka.append({"v": None, "p": p.stem})
            continue
        souhrn = (d or {}).get("souhrn") or {}
        policka.append({"v": _cely(souhrn.get("polozek")), "p": d.get("datum") or p.stem})

    return {
        "tvar": "pruh",
        "policka": policka,
        "pocet": len(soubory),
        "hodnota": _mezerou(len(soubory)),
        "jednotka": "čísel přehledu",
        "veta": "Sytost políčka odpovídá počtu položek v daném týdnu.",
        "stav": "ok",
        "zdroj": "data/vydani",
    }


def znak_usneseni() -> dict:
    """Usnesení — počet projednaných bodů po letech."""
    po_letech: Counter[int] = Counter()
    nasel = False
    for organ in ("rada", "zastupitelstvo"):
        korenu = DATA / "usneseni" / organ
        if not korenu.exists():
            continue
        for rok_dir in korenu.iterdir():
            r = _rok(rok_dir.name)
            if r is None:
                continue
            for soubor in rok_dir.glob("*.json"):
                try:
                    d = json.loads(soubor.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    continue
                nasel = True
                po_letech[r] += len(d.get("body") or [])

    if not nasel:
        return _chybi("usneseni", "data/usneseni", "Usnesení zatím nejsou sebraná.")

    return _sloupce_z_let(
        po_letech,
        hodnota=_mezerou(sum(po_letech.values())),
        jednotka="bodů usnesení",
        veta="Každý sloupec je jeden rok jednání rady a zastupitelstva.",
        zdroj="data/usneseni",
    )


def znak_hlasovani() -> dict:
    """Hlasování — kolik hlasování ročně a kolik z nich nebylo jednomyslných.

    POZOR NA SAMOZŘEJMÝ ÚDAJ: zdroj zveřejňuje jen výsledek „schvaleno" —
    všech 12 349 záznamů má stejnou hodnotu. Podíl schválených návrhů je
    tedy vždy 100 % a znak z něj kreslil konstantu, která budila dojem, že
    se něco mění. Ověřeno na celé sklizni, ne na vzorku.

    Co se skutečně liší, je JEDNOMYSLNOST: kolikrát někdo hlasoval proti
    nebo se zdržel. To je na hlasování to zajímavé a mění se to rok od roku.
    """
    celkem: Counter[int] = Counter()
    sporne: Counter[int] = Counter()
    nasel = False
    for organ in ("rada", "zastupitelstvo"):
        korenu = DATA / "hlasovani" / organ
        if not korenu.exists():
            continue
        for rok_dir in korenu.iterdir():
            r = _rok(rok_dir.name)
            if r is None:
                continue
            for soubor in rok_dir.glob("*.json"):
                try:
                    d = json.loads(soubor.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    continue
                nasel = True
                for h in d.get("hlasovani") or []:
                    celkem[r] += 1
                    proti = _cely(h.get("proti")) or 0
                    zdrzel = _cely(h.get("zdrzel")) or 0
                    if proti or zdrzel:
                        sporne[r] += 1

    if not nasel:
        return _chybi("hlasovani", "data/hlasovani", "Hlasování zatím nejsou sebraná.")

    roky = [r for r in sorted(celkem) if celkem[r]][-LET_V_ZNAKU:]
    vsech = sum(celkem.values())
    vsech_spornych = sum(sporne.values())
    return {
        "tvar": "sloupce",
        "osa": [str(r) for r in roky],
        "hodnoty": [float(celkem[r]) for r in roky],
        # Druhá série se kreslí NA VRCHOL sloupce, ne vedle něj — je to část
        # celku, ne samostatná veličina.
        "hodnoty2": [float(sporne[r]) for r in roky],
        "pocet": vsech,
        "hodnota": _mezerou(vsech),
        "jednotka": "hlasování",
        "veta": (
            f"Sloupec je rok, barevná špička nejednomyslná hlasování "
            f"({_mezerou(vsech_spornych)} z {_mezerou(vsech)})."
        ),
        "stav": "ok",
        "zdroj": "data/hlasovani",
    }


def znak_komise() -> dict:
    """Komise a výbory — zápisy z jednání po letech."""
    prehled = nacti("komise/prehled.json")
    if not prehled:
        return _chybi("komise", "data/komise/prehled.json",
                      "Zápisy komisí zatím nejsou rozebrané.")

    poc: Counter[int] = Counter()
    for z in prehled.get("zapisy") or []:
        r = _rok((z.get("datum") or "")[:4])
        if r is not None:
            poc[r] += 1
    if not poc:
        return _chybi("komise", "data/komise/prehled.json",
                      "V přehledu komisí není žádný zápis s datem.")

    souhrn = prehled.get("souhrn") or {}
    doporuceni = _cely(souhrn.get("doporuceni_rade"))
    return _sloupce_z_let(
        poc,
        hodnota=_mezerou(sum(poc.values())),
        jednotka="zápisů z jednání",
        veta=("Sloupec je jeden rok zápisů."
              + (f" Komise z nich radě daly {_mezerou(doporuceni)} doporučení."
                 if doporuceni else "")),
        zdroj="data/komise/prehled.json",
    )


def znak_informace() -> dict:
    """Žádosti o informace (zákon 106/1999) — rozebrané žádosti po letech."""
    prehled = nacti("informace106/prehled.json")
    if not prehled:
        return _chybi("informace", "data/informace106/prehled.json",
                      "Žádosti o informace zatím nejsou rozebrané.")

    poc: Counter[int] = Counter()
    for z in prehled.get("zadosti") or []:
        # Jen skutečně rozebrané žádosti — přehled nese i pár stažených,
        # ale nerozebraných, a znak by jinak hlásil víc „rozebraných",
        # než kolik jich souhrn přiznává.
        if not z.get("rozebrano"):
            continue
        r = _rok((z.get("vlozeno") or "")[:4])
        if r is not None:
            poc[r] += 1
    if not poc:
        return _chybi("informace", "data/informace106/prehled.json",
                      "V přehledu není žádná rozebraná žádost s datem.")

    v_rejstriku = _cely((prehled.get("souhrn") or {}).get("v_rejstriku"))
    return _sloupce_z_let(
        poc,
        hodnota=_mezerou(sum(poc.values())),
        jednotka="rozebraných žádostí",
        veta=("Sloupec je jeden rok žádostí podle stovky šestky."
              + (f" Rejstřík úřadu jich vede {_mezerou(v_rejstriku)}."
                 if v_rejstriku else "")),
        zdroj="data/informace106/prehled.json",
    )


def znak_diagramy() -> dict:
    """Schémata — jedna tečka za diagram, skupina je typ diagramu."""
    index = nacti("diagramy/index.json")
    if not index:
        return _chybi("diagramy", "data/diagramy/index.json",
                      "Schémata zatím nejsou spočítaná.")

    poc: Counter[str] = Counter()
    for d in index.get("diagramy") or []:
        if d.get("stav") == "ok":
            poc[(d.get("typ") or "jiný").strip()] += 1
    if not poc:
        return _chybi("diagramy", "data/diagramy/index.json",
                      "V rejstříku není žádné vykreslitelné schéma.")

    skupiny = [{"nazev": n, "pocet": p}
               for n, p in sorted(poc.items(), key=lambda kv: (-kv[1], kv[0]))]
    celkem = sum(poc.values())
    return {
        "tvar": "body",
        "skupiny": skupiny,
        "pocet": celkem,
        "hodnota": _mezerou(celkem),
        "jednotka": "schémat z dat",
        "veta": f"Jedna tečka je jedno schéma, barva je typ ({len(skupiny)} typů).",
        "stav": "ok",
        "zdroj": "data/diagramy/index.json",
    }


def znak_penize() -> dict:
    """Peníze — výdaje města po letech ze souhrnu registru smluv."""
    souhrn = nacti("penize/agregace/souhrn.json")
    if not souhrn:
        return _chybi("penize", "data/penize/agregace", "Souhrn plateb zatím není spočítaný.")

    po_letech: dict[int, float] = {}
    for k, v in (souhrn.get("po_letech") or {}).items():
        r = _rok(k)
        if r is None:
            continue
        po_letech[r] = float((v or {}).get("vydaj_czk") or 0.0)

    if not po_letech:
        return _chybi("penize", "data/penize/agregace", "V souhrnu nejsou žádné roky.")

    celkem = (souhrn.get("celkem") or {}).get("vydaj_czk")
    smluv = _cely((souhrn.get("celkem") or {}).get("smluv"))
    znak = _sloupce_z_let(
        Counter(),  # naplní se ručně, hodnoty jsou desetinné
        hodnota=_zkraceno(celkem),
        jednotka="Kč ve smlouvách",
        veta="Sloupec je jeden rok. Rok bez smluv je nula, ne mezera.",
        zdroj="data/penize/agregace/souhrn.json",
        pocet=smluv,
    )
    roky = sorted(po_letech)[-LET_V_ZNAKU:]
    znak["osa"] = [str(r) for r in roky]
    # Chybějící rok uvnitř rozsahu je skutečná nula (souhrn to výslovně říká
    # v `metodika.chybejici_rok`), proto `.get(r, 0.0)`, ne `None`.
    znak["hodnoty"] = [po_letech.get(r, 0.0) for r in roky]
    znak["stav"] = "ok"
    return znak


def znak_hospodareni() -> dict:
    """Hospodaření — skutečné výdaje města po konsolidaci, po letech.

    Čte se z přehledu Monitoru státní pokladny. Berou se jen UZAVŘENÉ roky
    (`koncove: true`) — rozpracovaný rok je stav k měsíci a vedle celých roků
    by ve znaku vypadal jako propad, který se nestal.
    """
    osa = nacti("rozpocet/prehled/po_letech.json")
    if not osa:
        return _chybi("hospodareni", "data/rozpocet/prehled",
                      "Přehled rozpočtu zatím není spočítaný.")

    po_letech: dict[int, float] = {}
    for r in osa.get("roky") or []:
        if not r.get("koncove"):
            continue
        rok = _rok(r.get("rok"))
        vydaje = ((r.get("vydaje") or {}).get("skutecnost"))
        if rok is None or vydaje is None:
            continue
        po_letech[rok] = float(vydaje)

    if not po_letech:
        return _chybi("hospodareni", "data/rozpocet/prehled",
                      "V přehledu rozpočtu není žádný uzavřený rok.")

    posledni = max(po_letech)
    znak = _sloupce_z_let(
        Counter(),  # naplní se ručně, hodnoty jsou desetinné
        hodnota=_zkraceno(po_letech[posledni]),
        jednotka=f"Kč výdajů města v roce {posledni}",
        veta="Sloupec je jeden uzavřený rok skutečných výdajů po konsolidaci.",
        zdroj="data/rozpocet/prehled/po_letech.json",
        pocet=len(po_letech),
    )
    roky = sorted(po_letech)[-LET_V_ZNAKU:]
    znak["osa"] = [str(r) for r in roky]
    # Rok bez dat uvnitř rozsahu by byl neznámo (None), ne nula — v datech
    # Monitoru ale žádný takový není a `roky_bez_dat` to hlídá.
    znak["hodnoty"] = [po_letech.get(r) for r in roky]
    znak["stav"] = "ok"
    return znak


def znak_retez() -> dict:
    """Od usnesení k penězům — tři navazující kroky se skutečnými počty."""
    retez = nacti("retez/retezy.json")
    if not retez:
        return _chybi("retez", "data/retez/retezy.json", "Řetězy zatím nejsou spočítané.")

    st = retez.get("statistika") or {}
    dle = st.get("dle_jistoty") or {}
    return {
        "tvar": "retez",
        "kroky": [
            {"nazev": "usnesení", "pocet": _cely(st.get("retezu"))},
            {"nazev": "smlouva", "pocet": _cely(st.get("retezu"))},
            {"nazev": "jistota", "pocet": _cely(dle.get("vysoka"))},
        ],
        "pocet": _cely(st.get("retezu")),
        "hodnota": _mezerou(_cely(st.get("retezu"))),
        "jednotka": "dohledaných vazeb",
        "veta": "Vazba usnesení → smlouva je odhad; plný uzel je vysoká jistota.",
        "stav": "ok",
        "zdroj": "data/retez/retezy.json",
    }


def znak_lide() -> dict:
    """Lidé — 21 zastupitelů jako tečky seskupené podle uskupení."""
    z = nacti("mesto/zastupitele.json")
    profily = nacti("lide/profily.json")
    if not z:
        return _chybi("lide", "data/mesto/zastupitele.json", "Seznam zastupitelů zatím není.")

    poc: Counter[str] = Counter()
    for c in z.get("zastupitele") or []:
        poc[(c.get("uskupeni") or "bez uskupení").strip()] += 1

    skupiny = [
        {"nazev": n, "pocet": p}
        for n, p in sorted(poc.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    hlasujicich = len((profily or {}).get("profily") or []) if profily else None
    osobnosti = nacti("lide/osobnosti.json")
    osob = len(osobnosti) if isinstance(osobnosti, list) else hlasujicich
    return {
        "tvar": "body",
        "skupiny": skupiny,
        # Do korpusu hledání patří všechny profilované osoby, ne jen 21 členů
        # současného zastupitelstva.
        "pocet": osob,
        "hodnota": _mezerou(_cely(z.get("celkem")) or sum(poc.values())),
        "jednotka": "zastupitelů",
        "veta": (
            "Jedna tečka je jeden zastupitel, barva je volební uskupení."
            + (f" Hlasovací profil má {_mezerou(hlasujicich)} osob." if hlasujicich else "")
        ),
        "stav": "ok",
        "zdroj": "data/mesto/zastupitele.json",
    }


def znak_firmy() -> dict:
    """Firmy — ekonomické subjekty se sídlem ve městě podle právní formy."""
    s = nacti("firmy/subjekty.json")
    if not s:
        return _chybi("firmy", "data/firmy/subjekty.json", "Rejstřík firem zatím není stažený.")

    ciselnik = ((s.get("ciselniky") or {}).get("pravni_formy") or {})
    poc: Counter[str] = Counter()
    for f in s.get("subjekty") or []:
        kod = str(f.get("pravni_forma") or "")
        poc[ciselnik.get(kod, "jiná forma")] += 1

    nej = poc.most_common(6)
    zbytek = sum(poc.values()) - sum(p for _, p in nej)
    osa = [n for n, _ in nej] + (["ostatní"] if zbytek else [])
    hod = [float(p) for _, p in nej] + ([float(zbytek)] if zbytek else [])
    return {
        "tvar": "sloupce",
        "osa": osa,
        "hodnoty": hod,
        "pocet": sum(poc.values()),
        "hodnota": _mezerou(sum(poc.values())),
        "jednotka": "firem ve městě",
        "veta": "Sloupce jsou nejčastější právní formy podle rejstříku ARES.",
        "stav": "ok",
        "zdroj": "data/firmy/subjekty.json",
    }


def znak_propojeni() -> dict:
    """Propojení — osoby vlevo, firmy vpravo, hrany mezi nimi."""
    p = nacti("propojeni/osoby_firmy.json")
    if not p:
        return _chybi("propojeni", "data/propojeni/osoby_firmy.json", "Vazby zatím nejsou dohledané.")

    s = p.get("souhrn") or {}
    return {
        "tvar": "sit",
        "vlevo": _cely(s.get("osob_s_firmou")) or 0,
        "vpravo": _cely(s.get("firem_unikatnich")) or _cely(s.get("firem_celkem")) or 0,
        "hran": _cely(s.get("firem_celkem")) or 0,
        "pocet": _cely(s.get("firem_celkem")),
        "hodnota": _mezerou(_cely(s.get("firem_celkem"))),
        "jednotka": "vazeb na firmy",
        "veta": "Vlevo veřejně činné osoby, vpravo firmy, čára je doložené angažmá.",
        "stav": "ok",
        "zdroj": "data/propojeni/osoby_firmy.json",
    }


def znak_volby() -> dict:
    """Volby — účast v jednotlivých volebních cyklech."""
    v = nacti("opendata/volby/prehled.json")
    if not v:
        return _chybi("volby", "data/opendata/volby/prehled.json", "Volební data zatím nejsou.")

    cykly = [c for c in (v.get("cykly") or []) if _cely(c.get("rok"))]
    cykly.sort(key=lambda c: (c.get("rok"), c.get("cyklus") or ""))
    posledni = cykly[-LET_V_ZNAKU:]
    # V jednom roce bývá voleb několik (sněmovní, krajské, komunální).
    # Samotný rok by se na ose opakoval třikrát a nedal by se přečíst.
    druhy = {
        "komunalni": "kom.", "senatni": "sen.", "snemovni": "sněm.",
        "prezidentske": "prez.", "krajske": "kraj.", "evropske": "EP",
    }

    def popisek(c: dict) -> str:
        d = druhy.get(c.get("druh") or "", (c.get("druh") or "")[:4])
        return f"{c.get('rok')} {d}".strip()

    return {
        "tvar": "sloupce",
        "osa": [popisek(c) for c in posledni],
        # Účast, kterou zdroj neuvádí, zůstává mezerou. Nula by tvrdila,
        # že k volbám nikdo nepřišel.
        "hodnoty": [
            float(c["ucast_proc"]) if isinstance(c.get("ucast_proc"), (int, float)) else None
            for c in posledni
        ],
        "pocet": len(cykly),
        "hodnota": _mezerou(len(cykly)),
        "jednotka": "volebních cyklů",
        "veta": "Výška sloupce je volební účast, mezera znamená, že ji zdroj neuvádí.",
        "stav": "ok",
        "zdroj": "data/opendata/volby/prehled.json",
    }


def znak_mapa() -> dict:
    """Mapa — skutečná hranice města jako SVG path.

    Bod se převádí prostou rovnoběžnou projekcí se zeměpisnou korekcí
    (`cos(lat)`), protože na výřezu velikosti jedné obce je zkreslení
    zanedbatelné a přesnější projekce by si vyžádala další závislost.
    """
    cesta = DATA / "opendata" / "geo" / "hranice_obce.geojson"
    if not cesta.exists():
        return _chybi("mapa", "data/opendata/geo", "Geodata hranice města zatím nejsou.")

    try:
        g = json.loads(cesta.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return _chybi("mapa", "data/opendata/geo", f"Geodata se nepodařilo přečíst: {e}")

    prstence: list[list[tuple[float, float]]] = []
    for f in g.get("features") or []:
        geom = f.get("geometry") or {}
        typ = geom.get("type")
        souradnice = geom.get("coordinates") or []
        polygony = souradnice if typ == "MultiPolygon" else [souradnice]
        for poly in polygony:
            for prsten in poly:
                body = [(float(b[0]), float(b[1])) for b in prsten if len(b) >= 2]
                if len(body) >= 4:
                    prstence.append(body)

    if not prstence:
        return _chybi("mapa", "data/opendata/geo", "V geodatech není žádný polygon.")

    vsechny = [b for p in prstence for b in p]
    lon_min = min(b[0] for b in vsechny)
    lon_max = max(b[0] for b in vsechny)
    lat_min = min(b[1] for b in vsechny)
    lat_max = max(b[1] for b in vsechny)
    lat_stred = (lat_min + lat_max) / 2
    korekce = math.cos(math.radians(lat_stred))

    sirka_deg = (lon_max - lon_min) * korekce or 1e-9
    vyska_deg = (lat_max - lat_min) or 1e-9
    # Kreslíme do čtverce 100×100 se zachovaným poměrem stran.
    meritko = 96 / max(sirka_deg, vyska_deg)
    posun_x = (100 - sirka_deg * meritko) / 2
    posun_y = (100 - vyska_deg * meritko) / 2

    def bod(lon: float, lat: float) -> tuple[float, float]:
        x = (lon - lon_min) * korekce * meritko + posun_x
        y = (lat_max - lat) * meritko + posun_y  # sever nahoru
        return round(x, 2), round(y, 2)

    # Zjednodušení: v miniatuře je 1479 bodů zbytečných a nafouklo by HTML.
    # Bere se každý n-tý bod tak, aby v prstenci zbylo nejvýš ~140.
    kusy: list[str] = []
    for prsten in prstence:
        krok = max(1, len(prsten) // 140)
        vzorek = prsten[::krok]
        if vzorek[0] != prsten[-1]:
            vzorek.append(prsten[-1])
        d = []
        for i, (lon, lat) in enumerate(vzorek):
            x, y = bod(lon, lat)
            d.append(("M" if i == 0 else "L") + f"{x} {y}")
        kusy.append(" ".join(d) + " Z")

    return {
        "tvar": "obrys",
        "path": " ".join(kusy),
        "pocet": 1,
        "hodnota": "1",
        "jednotka": "katastr města",
        "veta": "Skutečná hranice města podle RÚIAN, ne ilustrace.",
        "stav": "ok",
        "zdroj": "data/opendata/geo/hranice_obce.geojson",
    }


def znak_statistika() -> dict:
    """Čísla o městě — první časová řada ČSÚ, která má dost bodů."""
    c = nacti("opendata/csu/casove_rady.json")
    if not c:
        return _chybi("statistika", "data/opendata/csu", "Otevřená data ČSÚ zatím nejsou.")

    rady = c.get("rady") or []
    # Podle KÓDU, ne podle názvu. Řady „Počet obyvatel k 31. 12." je šest
    # (celkem, muži, ženy, tři věkové skupiny) a shoda na podřetězec vytáhla
    # věkovou skupinu 0–14 — znak pak tvrdil, že město má 1 795 obyvatel.
    vybrana = next((r for r in rady if r.get("kod") == "obyvatel_celkem"), None)
    if vybrana is None:
        vybrana = max(rady, key=lambda r: _cely(r.get("bodu")) or 0, default=None)
    if not vybrana:
        return _chybi("statistika", "data/opendata/csu", "V katalogu ČSÚ není žádná řada.")

    body = vybrana.get("body") or vybrana.get("hodnoty") or []
    dvojice: list[tuple[str, float | None]] = []
    for b in body:
        if isinstance(b, dict):
            obdobi = str(b.get("obdobi") or b.get("rok") or "")
            hod = b.get("hodnota")
            dvojice.append((obdobi, float(hod) if isinstance(hod, (int, float)) else None))
    dvojice = dvojice[-LET_V_ZNAKU:]
    if not dvojice:
        return _chybi("statistika", "data/opendata/csu", "Řada ČSÚ je bez hodnot.")

    posledni = next((h for _, h in reversed(dvojice) if h is not None), None)
    return {
        "tvar": "sloupce",
        "osa": [o for o, _ in dvojice],
        # `null` zůstává `null`: ČSÚ hodnotu buď nevydal, nebo ji tají kvůli
        # malému počtu subjektů. Ani jedno není nula.
        "hodnoty": [h for _, h in dvojice],
        "pocet": _cely(vybrana.get("bodu")),
        "hodnota": _mezerou(int(posledni)) if posledni is not None else "—",
        "jednotka": (vybrana.get("nazev") or "řada ČSÚ").lower(),
        "veta": "Poslední známá hodnota; mezera znamená, že ČSÚ údaj nevydal.",
        "stav": "ok",
        "zdroj": "data/opendata/csu/casove_rady.json",
    }


def znak_zpravodaj() -> dict:
    """Zpravodaj — jedno políčko je jeden měsíc archivu.

    Roční pruh tu nefungoval: zpravodaj vychází dvanáctkrát ročně, takže
    všechny roky vyšly stejně syté a znak se nedal odlišit od ostatních
    mřížek. Měsíční rozlišení naopak ukáže to podstatné — kde v archivu
    jsou díry a kdy dvojčíslo nahradilo dvě čísla.
    """
    cisla = nacti("zpravodaj/cisla.json")
    if not cisla:
        return _chybi("zpravodaj", "data/zpravodaj/cisla.json", "Archiv zpravodaje zatím není.")

    mesice: Counter[tuple[int, int]] = Counter()
    for c in cisla:
        r = _rok(c.get("rok"))
        m = _cely(c.get("mesic"))
        if r is None or m is None or not 1 <= m <= 12:
            continue
        mesice[(r, m)] += 1
        # Dvojčíslo („7–8/2019") pokrývá dva měsíce; ten druhý by jinak
        # vypadal jako díra v archivu, přitom vyšel.
        m_do = _cely(c.get("mesic_do"))
        if m_do and 1 <= m_do <= 12:
            for mm in range(m + 1, m_do + 1):
                mesice[(r, mm)] += 1

    if not mesice:
        return _chybi("zpravodaj", "data/zpravodaj/cisla.json", "Čísla nemají rok a měsíc.")

    roky = sorted({r for r, _ in mesice})
    policka = [
        {"v": mesice.get((r, m), 0), "p": f"{m}/{r}"}
        for r in roky
        for m in range(1, 13)
    ]
    return {
        "tvar": "pruh",
        "sloupcu": 12,
        "policka": policka,
        "pocet": len(cisla),
        "hodnota": _mezerou(len(cisla)),
        "jednotka": "čísel zpravodaje",
        "veta": f"Řádek je rok {roky[0]}–{roky[-1]}, políčko měsíc; prázdné políčko = číslo v archivu není.",
        "stav": "ok",
        "zdroj": "data/zpravodaj/cisla.json",
    }


def znak_historie() -> dict:
    """Historie — období dějin města jako úseky na ose."""
    h = nacti("historie/prehled.json")
    if not h:
        return _chybi("historie", "data/historie/prehled.json", "Dějiny zatím nejsou sebrané.")

    useky = []
    for o in h.get("obdobi") or []:
        od, do = _cely(o.get("od")), _cely(o.get("do"))
        if od is None:
            continue
        useky.append({"od": od, "do": do if do is not None else od, "nazev": o.get("nazev") or ""})
    if not useky:
        return _chybi("historie", "data/historie/prehled.json", "Období nemají letopočty.")

    st = h.get("statistika") or {}
    return {
        "tvar": "useky",
        "useky": useky,
        "pocet": _cely(st.get("udalosti")),
        "hodnota": _mezerou(_cely(st.get("udalosti"))),
        "jednotka": "datovaných událostí",
        "veta": "Osa od první zprávy o pramenech po dnešek, úsek je jedno období.",
        "stav": "ok",
        "zdroj": "data/historie/prehled.json",
    }


def pocet_clanku() -> int | None:
    """Kolik článků ze zpravodaje je rozebraných.

    Články leží po ročnících v `data/zpravodaj/clanky/RRRR-MM/*.json`; počet
    čísel (122) a počet článků (tisíce) jsou dvě různá čísla a hledání
    prochází ta druhá.
    """
    koren = DATA / "zpravodaj" / "clanky"
    if not koren.exists():
        return None
    return sum(1 for _ in koren.rglob("*.json"))


def znak_hledat(znaky: dict, clanku: int | None) -> dict:
    """Hledání — z čeho se skládá prohledávaný korpus.

    Počty se berou z polí `pocet`, která si každý znak spočítal ze svého
    zdroje. Dřív se tu parsovaly naformátované řetězce („3,83 mld.") a sekce
    peníze z toho vyšla jako neznámo — formát pro člověka není číslo.

    Jednotky se nesčítají mechanicky: co je „záznam" v jedné sekci, je jinde
    celý ročník. Proto se sčítá jen to, co je v Pagefindu skutečně jedna
    prohledávaná položka.
    """
    slozky = [
        ("usnesení", "usneseni"),
        ("hlasování", "hlasovani"),
        ("smlouvy", "penize"),
        ("články", None),  # doplní se zvlášť — mark „zpravodaj" počítá čísla, ne články
        ("lidé", "lide"),
    ]
    osa, hodnoty = [], []
    for popisek, klic in slozky:
        osa.append(popisek)
        p = clanku if klic is None else (znaky.get(klic) or {}).get("pocet")
        hodnoty.append(float(p) if isinstance(p, (int, float)) else None)

    if all(h is None for h in hodnoty):
        return _chybi("hledat", "—", "Zatím není co prohledávat.")

    znamych = [h for h in hodnoty if h is not None]
    return {
        "tvar": "sloupce",
        "osa": osa,
        "hodnoty": hodnoty,
        "pocet": int(sum(znamych)),
        "hodnota": _mezerou(int(sum(znamych))),
        "jednotka": (
            "prohledávaných záznamů"
            if len(znamych) == len(hodnoty)
            else f"záznamů z {len(znamych)} z {len(hodnoty)} zdrojů"
        ),
        "veta": "Z čeho se skládá prohledávaný archiv.",
        "stav": "ok",
        "zdroj": "součet ostatních sekcí",
    }


# ═════════════════════════════════  pomůcky  ══════════════════════════════


def _sloupce_z_let(
    po_letech: Counter, *, hodnota: str, jednotka: str, veta: str, zdroj: str,
    pocet: int | None = None,
) -> dict:
    roky = sorted(po_letech)[-LET_V_ZNAKU:] if po_letech else []
    return {
        "tvar": "sloupce",
        "osa": [str(r) for r in roky],
        "hodnoty": [float(po_letech[r]) for r in roky],
        "pocet": pocet if pocet is not None else (sum(po_letech.values()) or None),
        "hodnota": hodnota,
        "jednotka": jednotka,
        "veta": veta,
        "stav": "ok",
        "zdroj": zdroj,
    }


def main() -> None:
    log = Log("znaky_sekci")

    znaky: dict[str, dict] = {}
    stavitele = [
        ("vydani", znak_vydani),
        ("usneseni", znak_usneseni),
        ("hlasovani", znak_hlasovani),
        ("komise", znak_komise),
        ("informace", znak_informace),
        ("penize", znak_penize),
        ("hospodareni", znak_hospodareni),
        ("retez", znak_retez),
        ("diagramy", znak_diagramy),
        ("lide", znak_lide),
        ("firmy", znak_firmy),
        ("propojeni", znak_propojeni),
        ("volby", znak_volby),
        ("mapa", znak_mapa),
        ("statistika", znak_statistika),
        ("zpravodaj", znak_zpravodaj),
        ("historie", znak_historie),
    ]

    for klic, stavitel in stavitele:
        try:
            znaky[klic] = stavitel()
        except Exception as e:  # noqa: BLE001
            # Jeden rozbitý zdroj nesmí shodit celý rozcestník. Sekce dostane
            # znak „chybí" a v logu je proč.
            log.chyba(f"znak {klic}: {e}")
            znaky[klic] = _chybi(klic, "—", f"Znak se nepodařilo spočítat: {e}")

    znaky["hledat"] = znak_hledat(znaky, pocet_clanku())

    chybejicich = sum(1 for z in znaky.values() if z.get("stav") != "ok")
    uloz("znaky/sekce.json", {
        "metodika": {
            "co_to_je": (
                "Miniaturní grafika sekcí pro rozcestník. Každý znak je graf ze "
                "skutečných dat té sekce, ne ikona — projekt nemá ikonovou sadu "
                "a obrazová složka je výhradně datová."
            ),
            "prazdno": (
                "`null` v hodnotách znamená NEZNÁMO a kreslí se jako mezera. "
                "Nula se kreslí jako nula. Zaměnit obojí je v tomhle projektu chyba."
            ),
            "tvary": [
                "sloupce", "pruh", "mrizka", "body", "retez", "sit", "obrys", "useky", "chybi",
            ],
            "kdy_se_prepocitava": "při každém týdenním běhu, po naplnění ostatních dat",
        },
        "znaku": len(znaky),
        "chybejicich": chybejicich,
        "znaky": znaky,
    })

    log.pricti(len(znaky))
    log.info("znaky spočítány", pocet=len(znaky))
    if chybejicich:
        log.info("znaků bez dat", pocet=chybejicich)
    log.uzavri()


if __name__ == "__main__":
    main()
