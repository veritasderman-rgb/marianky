"""Propojení lidí, firem a peněz — modul P1.

K ČEMU TO JE
------------
Web má vedle sebe ukázat tři věci, které jinak leží každá v jiném souboru:
kde je veřejně činná osoba angažovaná, kolik ta která firma dostala od města
a jak dotyčný hlasoval, když se o firmě jednalo.

**Ukládají se fakta, ne závěry.** Nikde se nehodnotí, jestli je něco v pořádku
nebo není — od toho je čtenář. Proto tenhle modul neobsahuje slova jako
„konflikt zájmů“ nebo „prosadil“ a ani je do dat nezapisuje. Neúčast na
hlasování se nijak nezvýrazňuje: může být stejně dobře tím správným krokem
jako čímkoliv jiným, a data o tom nic neříkají.

VSTUPY
------
- `data/propojeni/zdroje/osoby_hlidac.json` — ze `scrapers/osoby_firmy.py`
- `data/penize/agregace/protistrany.json` — kdo kolik dostal od města (A3)
- `data/penize/smlouvy/*.json` — jednotlivé smlouvy (A3)
- `data/usneseni/**`, `data/hlasovani/**` — body a jmenovitá hlasování (A1)
- `data/lide/osobnosti.json` — role a funkce (B1)
- `config/subjekty.json` — co patří do městského holdingu

VÝSTUPY
-------

### `data/propojeni/osoby_firmy.json`

Pro každou veřejně činnou osobu seznam firem s příznakem vztahu k městu.
Firmy bez jakékoliv vazby na město se **záměrně uvádějí taky** — smyslem je
ukázat, kde všude je člověk aktivní, ne jen tam, kde se to týká města.

```json
{ "osoby": [{
  "osoba_id": "chadim-miloslav", "jmeno": "Miloslav Chadim",
  "role": ["zastupitel", "radní", "člen dozorčí rady"], "strana": "ANO 2011",
  "hlidac": { "person_id": "miloslav-chadim", "url": "…", "narozen": "1966" },
  "overeni": { "stav": "potvrzeno", "zaklad": ["firma-mesta"], "kandidatu": 1 },
  "firmy": [{
    "ico": "25208438", "nazev": "Infocentrum Mariánské Lázně s.r.o.",
    "url": "https://www.hlidacstatu.cz/subjekt/25208438",
    "vztah_k_mestu": "mestsky-subjekt",
    "mestsky_subjekt": true, "vlastnictvi": "mesto_100",
    "obchoduje_s_mestem": true,
    "od_mesta_czk": 12345.0, "mestu_czk": null, "smluv": 12,
    "prvni_rok": 2017, "posledni_rok": 2026, "aktivni": true,
    "po_letech": { "2017": 1200000.0 }
  }],
  "souhrn_firem": { "celkem": 10, "mestskych_subjektu": 2,
                    "obchodujicich_s_mestem": 3, "bez_vazby_na_mesto": 6 },
  "sponzoring": { "zaznamu": 2, "celkem_czk": 325000.0, "strany": ["ANO"] },
  "smlouvy_holdingu": { "smluv": 120, "protistrany": [] }
}]}
```

`vztah_k_mestu` ∈ `mestsky-subjekt` | `obchoduje-s-mestem` | `bez-vazby-na-mesto`.
`od_mesta_czk` je součet smluv, kde je město (nebo jiný subjekt holdingu)
vedeno jako plátce; `mestu_czk` opačný směr. `null` = údaj není, ne nula.

### `data/propojeni/hlasovani_vazby.json`

Hlasování, u kterých se projednávaný bod týká firmy, kde má některý
z hlasujících funkci nebo angažmá. Záznam obsahuje jen fakta: kdo, jak
hlasoval, jakou má ve firmě roli a kolik ta firma od města dostala.

```json
{ "vazby": [{
  "hlasovani_id": "rada-2026-124-1", "organ": "rada", "cj": 124,
  "datum": "2026-08-07", "bod": "124/1", "nazev": "…",
  "url": "https://usneseni.muml.cz/…",
  "vysledek": "schvaleno", "pro": 6, "proti": 1, "zdrzel": 0,
  "nehlasoval": 0, "nepritomen": 0,
  "firma": { "ico": "25213261", "nazev": "…", "url": "…",
             "nalezeno_dle": ["ico", "nazev"],
             "vztah_k_mestu": "mestsky-subjekt", "od_mesta_czk": 748600000.0 },
  "hlasujici": [{
    "osoba_id": "dubnicky-roman", "jmeno": "MUDr. Roman Dubnický",
    "strana": "ANO 2011", "hlas": "pro",
    "role_ve_firme": ["člen dozorní rady — Technický a dopravní servis s.r.o."],
    "zdroj_role": ["data/lide/osobnosti.json",
                   "https://www.hlidacstatu.cz/osoba/roman-dubnicky"],
    "overeni_osoby": "potvrzeno"
  }]
}]}
```

`hlas` se přebírá beze změny z `data/hlasovani/**`, včetně `nepritomen`.
Období, po které osoba funkci ve firmě zastávala, zdroje neuvádějí
(`obdobi_funkce_zname: false`), takže se vazba zapisuje ke každému hlasování,
kterého se osoba podle jmenovitého záznamu účastnila. Datum hlasování je
v záznamu, ať si čtenář zařadí sám.

### `data/propojeni/dodavatele_politici.json`

Dodavatelé města, u kterých Hlídač státu vede angažmá některé z veřejně
činných osob města.

```json
{ "dodavatele": [{
  "ico": "…", "nazev": "…", "url": "…",
  "celkem_od_mesta_czk": 1234.0, "smluv": 12,
  "prvni_rok": 2017, "posledni_rok": 2026, "aktivni": true,
  "po_letech": {}, "mestsky_subjekt": false,
  "osoby": [{ "osoba_id": "…", "jmeno": "…", "role": [], "strana": "…",
              "zaklad": ["angazma-dle-hlidace"], "zdroj": "…",
              "smluv_s_holdingem": 72, "castka_smluv_czk": 123.0 }]
}]}
```

POZNÁMKA KE ZDROJI PŘÍZNAKU
---------------------------
Smlouvy v `data/penize/smlouvy/*.json` mají pole `vazba_na_politiky`, které
`scrapers/hlidac_api.py` plní z pole `sVazbouNaPolitiky`. **U všech 6 521
smluv je `false`, protože API v2 to pole nevyplňuje** — vrací `null`, a to
i v detailu jedné smlouvy; filtr `sVazbouNaPolitiky:1` v dotazu vrací nula
výsledků (ověřeno 17. 8. 2026). Příznak se proto k ničemu nepoužívá a v datech
je jako `hlidac_priznak_vazby: null`, tedy „nezjištěno“, ne „žádná vazba“.

Místo něj se vazba počítá ze dvou doložitelných zdrojů:
- `angazma-dle-hlidace` — osoba je podle Hlídače angažovaná ve firmě
- `smlouvy-dle-hlidace` — Hlídač váže smlouvy holdingu na osobu přes dotaz
  `osobaId:{id} AND holding:{ico_mesta}`

JAK SE POZNÁ, ŽE BOD JEDNÁ O FIRMĚ
-----------------------------------
Hledá se v názvu a textu bodu usnesení:
- **podle IČO** — osmičíslí uvozené zkratkou IČ/IČO (samotné osmimístné číslo
  se neuznává, v usneseních jsou to většinou parcelní čísla a částky)
- **podle názvu** — název firmy zbavený diakritiky a koncové právní formy
  („s.r.o.“, „a.s.“, „příspěvková organizace“). Právní forma se odstraňuje
  jen ze konce názvu, aby se nerozbila slova uvnitř — „TECHNICKÝ A DOPRAVNÍ
  SERVIS" o své „servis“ nesmí přijít. Klíč musí mít aspoň dvě slova nebo
  aspoň sedm znaků, jinak by obecné slovo chytalo cizí body.
"""
from __future__ import annotations

import glob
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import DATA, Log, ZdrojSelhal, nacti, nacti_config, uloz  # noqa: E402

ZDROJ_OSOB = "propojeni/zdroje/osoby_hlidac.json"
WEB_SUBJEKT = "https://www.hlidacstatu.cz/subjekt/"

# Stavy rozpoznání, u kterých se firmy osoby považují za doložené.
POUZITELNE = {"potvrzeno", "pravdepodobne"}

# Tokeny právní formy — odstraňují se jen z KONCE názvu, aby zůstala
# nedotčená slova uvnitř („SERVIS“ nesmí přijít o „se“).
KONCOVE_TOKENY = {
    "s", "r", "o", "a", "p", "z", "u", "spol", "se", "as", "sro", "ops", "zs",
    "v", "likvidaci", "prispevkova", "organizace", "zapsany", "spolek", "ustav",
}

# Bod „Program 3. ZM“ je hlasování o programu schůze jako celku. Jeho text
# vyjmenovává všechny body jednání, takže se v něm objeví kdejaká firma —
# ale hlasuje se o pořadu jednání, ne o té firmě. Takové body se vynechávají
# a jejich počet se uvádí v souhrnu, aby nezmizely potichu.
# Pozor na „Program regenerace městské památkové zóny“ a podobné: ty jsou
# věcné a vynechat se nesmí, proto vzor vyžaduje číslo schůze a orgán.
POR_JEDNANI = re.compile(r"^\s*program\s*\d+\s*\.?\s*(rm|zm)\b", re.I)


# --------------------------------------------------------------------------
# Normalizace
# --------------------------------------------------------------------------

def bez_diakritiky(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def normalizuj(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", bez_diakritiky(text)).split())


def klic_firmy(nazev: str) -> str | None:
    """Název bez diakritiky a bez koncové právní formy.

    Vrací None, když by klíč byl tak krátký, že by chytal cizí body.
    """
    tokeny = normalizuj(nazev).split()
    while tokeny and tokeny[-1] in KONCOVE_TOKENY:
        tokeny.pop()
    if not tokeny:
        return None
    klic = " ".join(tokeny)
    if len(tokeny) < 2 and len(klic) < 7:
        return None
    return klic


# --------------------------------------------------------------------------
# Peníze
# --------------------------------------------------------------------------

def index_penez() -> dict[str, dict]:
    """IČO → souhrn toků mezi firmou a městským holdingem.

    Protistrany mohou být v agregaci u jednoho IČO dvakrát, jednou za každý
    směr. Sčítá se to dohromady, ale směry se drží odděleně, aby se
    nespletlo „město zaplatilo“ s „město inkasovalo“.
    """
    agregace = nacti("penize/agregace/protistrany.json")
    if not agregace or not agregace.get("protistrany"):
        raise ZdrojSelhal(
            "Chybí data/penize/agregace/protistrany.json — bez něj nejde říct, "
            "kolik která firma od města dostala."
        )

    index: dict[str, dict] = {}
    for p in agregace["protistrany"]:
        ico = p.get("ico")
        if not ico:
            continue  # protistrany bez IČO se párovat nedají, viz klic_dle
        z = index.setdefault(ico, {
            "nazev": p.get("nazev"), "od_mesta_czk": None, "mestu_czk": None,
            "smluv": 0, "prvni_rok": None, "posledni_rok": None,
            "aktivni": False, "po_letech": {}, "interni": False,
        })
        smer = p.get("smer")
        castka = p.get("celkem_czk")
        pole = "od_mesta_czk" if smer == "vydaj" else "mestu_czk"
        if castka is not None:
            z[pole] = (z[pole] or 0.0) + float(castka)

        z["smluv"] += p.get("smluv") or 0
        z["aktivni"] = z["aktivni"] or bool(p.get("aktivni"))
        z["interni"] = z["interni"] or bool(p.get("interni"))
        for rok, c in (p.get("po_letech") or {}).items():
            z["po_letech"][rok] = z["po_letech"].get(rok, 0.0) + float(c or 0)
        for pole_rok, volba in (("prvni_rok", min), ("posledni_rok", max)):
            r = p.get(pole_rok)
            if r is not None:
                z[pole_rok] = r if z[pole_rok] is None else volba(z[pole_rok], r)

    for z in index.values():
        for pole in ("od_mesta_czk", "mestu_czk"):
            if z[pole] is not None:
                z[pole] = round(z[pole], 2)
        z["po_letech"] = {r: round(c, 2) for r, c in sorted(z["po_letech"].items())}
    return index


def priznak_vazby_ve_smlouvach() -> dict:
    """Kolik smluv nese příznak `vazba_na_politiky` — a jestli je vůbec plněný."""
    celkem = s_priznakem = 0
    for cesta in glob.glob(str(DATA / "penize/smlouvy/*.json")):
        d = nacti(cesta) or {}
        for s in d.get("smlouvy", []):
            celkem += 1
            if s.get("vazba_na_politiky"):
                s_priznakem += 1
    return {"smluv_celkem": celkem, "s_priznakem": s_priznakem,
            "pole_plnene": s_priznakem > 0}


# --------------------------------------------------------------------------
# Firmy osob
# --------------------------------------------------------------------------

def obohat_firmu(firma: dict, subjekty: dict, penize: dict) -> dict:
    ico = firma["ico"]
    subj = subjekty.get(ico)
    tok = penize.get(ico)

    if subj:
        vztah = "mestsky-subjekt"
    elif tok:
        vztah = "obchoduje-s-mestem"
    else:
        vztah = "bez-vazby-na-mesto"

    return {
        "ico": ico,
        "nazev": firma["nazev"],
        "url": firma.get("url") or f"{WEB_SUBJEKT}{ico}",
        "vztah_k_mestu": vztah,
        "mestsky_subjekt": subj is not None,
        "vlastnictvi": subj.get("vlastnictvi") if subj else None,
        "obchoduje_s_mestem": tok is not None,
        "od_mesta_czk": tok["od_mesta_czk"] if tok else None,
        "mestu_czk": tok["mestu_czk"] if tok else None,
        "smluv": tok["smluv"] if tok else None,
        "prvni_rok": tok["prvni_rok"] if tok else None,
        "posledni_rok": tok["posledni_rok"] if tok else None,
        "aktivni": tok["aktivni"] if tok else None,
        "po_letech": tok["po_letech"] if tok else None,
    }


def sestav_osoby(zdroj: dict, subjekty: dict, penize: dict) -> list[dict]:
    osoby: list[dict] = []
    for o in zdroj["osoby"]:
        pouzitelna = o["overeni"]["stav"] in POUZITELNE
        firmy = None
        souhrn = None
        if pouzitelna and o.get("firmy") is not None:
            firmy = [obohat_firmu(f, subjekty, penize) for f in o["firmy"]]
            firmy.sort(key=lambda f: (f["od_mesta_czk"] is None, -(f["od_mesta_czk"] or 0)))
            souhrn = {
                "celkem": len(firmy),
                "mestskych_subjektu": sum(1 for f in firmy if f["mestsky_subjekt"]),
                "obchodujicich_s_mestem": sum(
                    1 for f in firmy if f["obchoduje_s_mestem"] and not f["mestsky_subjekt"]
                ),
                "bez_vazby_na_mesto": sum(
                    1 for f in firmy if f["vztah_k_mestu"] == "bez-vazby-na-mesto"
                ),
            }

        osoby.append({
            "osoba_id": o["osoba_id"],
            "jmeno": o["jmeno"],
            "role": o["role"],
            "kategorie": o.get("kategorie"),
            "strana": o.get("strana"),
            "funkce": o.get("funkce") or [],
            "hlidac": o["hlidac"],
            "overeni": o["overeni"],
            "firmy": firmy,
            "souhrn_firem": souhrn,
            "sponzoring": o.get("sponzoring"),
            "smlouvy_se_statem": o.get("smlouvy_se_statem"),
            "smlouvy_holdingu": o.get("smlouvy_holdingu"),
        })
    return osoby


# --------------------------------------------------------------------------
# Vazby na hlasování
# --------------------------------------------------------------------------

def role_ve_firmach(osoby: list[dict], subjekty: dict) -> dict[str, dict[str, dict]]:
    """osoba_id → IČO → {role, zdroje}.

    Role se skládá ze dvou zdrojů: z funkcí v `osobnosti.json`, kde je firma
    napsaná slovem za pomlčkou, a z angažmá vedeného Hlídačem.
    """
    # Název firmy → IČO, aby šla funkce „ředitel — Městská knihovna“ navázat
    # na konkrétní firmu. Mapa se staví celá dopředu, ne za pochodu, jinak by
    # výsledek závisel na pořadí osob.
    dle_nazvu: dict[str, str] = {}
    for ico, s in subjekty.items():
        if k := klic_firmy(s["nazev"]):
            dle_nazvu.setdefault(k, ico)
    for o in osoby:
        if o["overeni"]["stav"] not in POUZITELNE:
            continue
        for f in o["firmy"] or []:
            if k := klic_firmy(f["nazev"]):
                dle_nazvu.setdefault(k, f["ico"])

    vazby: dict[str, dict[str, dict]] = defaultdict(dict)
    for o in osoby:
        if o["overeni"]["stav"] not in POUZITELNE:
            continue

        firmy_osoby = {f["ico"]: f for f in (o["firmy"] or [])}

        # 1) funkce zapsané slovem v osobnosti.json
        for fce in o.get("funkce") or []:
            nazev = fce.get("nazev") or ""
            if "—" not in nazev and "-" not in nazev:
                continue
            cast = re.split(r"—|(?<=\s)-(?=\s)", nazev, maxsplit=1)
            if len(cast) < 2:
                continue
            klic = klic_firmy(cast[1])
            if not klic:
                continue
            ico = dle_nazvu.get(klic)
            if not ico:
                # Zkusí se i shoda na začátku, názvy bývají zkrácené
                # („Základní škola Vítězství“ vs. plný zápis v rejstříku).
                ico = next((v for k, v in dle_nazvu.items()
                            if k.startswith(klic) or klic.startswith(k)), None)
            if not ico:
                continue
            z = vazby[o["osoba_id"]].setdefault(ico, {"role": [], "zdroje": []})
            if nazev not in z["role"]:
                z["role"].append(nazev)
            if "data/lide/osobnosti.json" not in z["zdroje"]:
                z["zdroje"].append("data/lide/osobnosti.json")

        # 2) angažmá dle Hlídače
        url_osoby = o["hlidac"].get("url")
        for ico in firmy_osoby:
            z = vazby[o["osoba_id"]].setdefault(ico, {"role": [], "zdroje": []})
            if "angažován dle Hlídače státu" not in z["role"]:
                z["role"].append("angažován dle Hlídače státu")
            if url_osoby and url_osoby not in z["zdroje"]:
                z["zdroje"].append(url_osoby)

    return vazby


def firmy_v_bodu(text: str, klice: list[tuple[str, str]], ica: set[str]) -> dict[str, list[str]]:
    """IČO firem zmíněných v bodu → čím byly nalezeny (`ico` / `nazev`)."""
    norm = normalizuj(text)
    nalezene: dict[str, list[str]] = defaultdict(list)

    for ico in ica:
        # Samotné osmičíslí nestačí — v usneseních to bývají parcelní čísla.
        if re.search(rf"\bic[o]?\s*[:.]?\s*{ico}\b", norm):
            nalezene[ico].append("ico")
    for ico, klic in klice:
        if klic in norm:
            nalezene[ico].append("nazev")
    return nalezene


def nacti_hlasovani() -> dict[str, dict]:
    """hlasovani_id → záznam hlasování včetně orgánu a čj."""
    index: dict[str, dict] = {}
    for cesta in glob.glob(str(DATA / "hlasovani/*/*/*.json")):
        d = nacti(cesta) or {}
        for h in d.get("hlasovani", []):
            if h.get("id"):
                index[h["id"]] = {**h, "organ": d.get("organ"),
                                  "cj": d.get("cj"), "datum": d.get("datum")}
    return index


def sestav_hlasovani(osoby: list[dict], subjekty: dict, penize: dict,
                     log: Log) -> tuple[list[dict], dict]:
    vazby_osob = role_ve_firmach(osoby, subjekty)
    if not vazby_osob:
        raise ZdrojSelhal("Nepodařilo se sestavit žádnou vazbu osoba–firma.")

    # Firmy, které vůbec má smysl v usneseních hledat.
    firmy: dict[str, str] = {}
    for osoba_vazby in vazby_osob.values():
        for ico in osoba_vazby:
            firmy.setdefault(ico, "")
    for o in osoby:
        for f in o["firmy"] or []:
            if f["ico"] in firmy:
                firmy[f["ico"]] = f["nazev"]
    for ico, s in subjekty.items():
        if ico in firmy and not firmy[ico]:
            firmy[ico] = s["nazev"]

    klice = [(ico, k) for ico, nazev in firmy.items() if (k := klic_firmy(nazev))]
    ica = set(firmy)
    log.info("firem k hledání v usneseních", pocet=len(ica), s_klicem=len(klice))

    hlasovani = nacti_hlasovani()
    if not hlasovani:
        raise ZdrojSelhal("Nenačetlo se žádné hlasování z data/hlasovani/**.")

    vysledek: list[dict] = []
    bodu_s_firmou = 0
    bodu_por_jednani = 0

    for cesta in sorted(glob.glob(str(DATA / "usneseni/*/*/*.json"))):
        d = nacti(cesta) or {}
        for bod in d.get("body", []):
            text = f"{bod.get('nazev') or ''} {bod.get('text') or ''}"
            nalezene = firmy_v_bodu(text, klice, ica)
            if not nalezene:
                continue
            if POR_JEDNANI.match(bod.get("nazev") or ""):
                bodu_por_jednani += 1
                continue
            bodu_s_firmou += 1

            h_id = bod.get("hlasovani_id")
            hlas = hlasovani.get(h_id) if h_id else None
            if not hlas:
                continue  # bez jmenovitého hlasování není co k firmě přiřadit

            for ico, jak in nalezene.items():
                dotceni = []
                for j in hlas.get("jmenovite") or []:
                    vazba = vazby_osob.get(j.get("osoba_id"), {}).get(ico)
                    if not vazba:
                        continue
                    osoba = next((o for o in osoby if o["osoba_id"] == j["osoba_id"]), None)
                    dotceni.append({
                        "osoba_id": j["osoba_id"],
                        "jmeno": j.get("jmeno"),
                        "strana": j.get("strana"),
                        "hlas": j.get("hlas"),
                        "role_ve_firme": vazba["role"],
                        "zdroj_role": vazba["zdroje"],
                        "overeni_osoby": osoba["overeni"]["stav"] if osoba else None,
                    })
                if not dotceni:
                    continue

                tok = penize.get(ico)
                subj = subjekty.get(ico)
                vysledek.append({
                    "hlasovani_id": h_id,
                    "organ": hlas.get("organ"),
                    "cj": hlas.get("cj"),
                    "datum": hlas.get("datum"),
                    "bod": bod.get("cislo"),
                    "cislo_usneseni": bod.get("cislo_usneseni"),
                    "nazev": bod.get("nazev"),
                    "url": bod.get("url") or d.get("url"),
                    "tagy": bod.get("tagy") or [],
                    "castka_czk": bod.get("castka_czk"),
                    "vysledek": hlas.get("vysledek"),
                    "pro": hlas.get("pro"), "proti": hlas.get("proti"),
                    "zdrzel": hlas.get("zdrzel"), "nehlasoval": hlas.get("nehlasoval"),
                    "omluven": hlas.get("omluven"), "nepritomen": hlas.get("nepritomen"),
                    "firma": {
                        "ico": ico,
                        "nazev": firmy.get(ico),
                        "url": f"{WEB_SUBJEKT}{ico}",
                        "nalezeno_dle": sorted(set(jak)),
                        "vztah_k_mestu": ("mestsky-subjekt" if subj else
                                          "obchoduje-s-mestem" if tok else
                                          "bez-vazby-na-mesto"),
                        "od_mesta_czk": tok["od_mesta_czk"] if tok else None,
                    },
                    "hlasujici": dotceni,
                })

    vysledek.sort(key=lambda v: (v["datum"] or "", v["bod"] or ""))
    souhrn = {
        "bodu_se_zminkou_firmy": bodu_s_firmou,
        "bodu_por_jednani_vynechano": bodu_por_jednani,
        "hlasovani_s_vazbou": len({v["hlasovani_id"] for v in vysledek}),
        "zaznamu": len(vysledek),
        "dotcenych_osob": len({h["osoba_id"] for v in vysledek for h in v["hlasujici"]}),
        "dotcenych_firem": len({v["firma"]["ico"] for v in vysledek}),
    }
    return vysledek, souhrn


# --------------------------------------------------------------------------
# Dodavatelé se stopou k politice
# --------------------------------------------------------------------------

def sestav_dodavatele(osoby: list[dict], subjekty: dict, penize: dict) -> list[dict]:
    dodavatele: dict[str, dict] = {}

    def zaznam(ico: str, nazev: str | None) -> dict:
        tok = penize.get(ico)
        subj = subjekty.get(ico)
        return dodavatele.setdefault(ico, {
            "ico": ico,
            "nazev": nazev or (tok or {}).get("nazev") or (subj or {}).get("nazev"),
            "url": f"{WEB_SUBJEKT}{ico}",
            "mestsky_subjekt": subj is not None,
            "vlastnictvi": (subj or {}).get("vlastnictvi"),
            "celkem_od_mesta_czk": (tok or {}).get("od_mesta_czk"),
            "mestu_czk": (tok or {}).get("mestu_czk"),
            "smluv": (tok or {}).get("smluv"),
            "prvni_rok": (tok or {}).get("prvni_rok"),
            "posledni_rok": (tok or {}).get("posledni_rok"),
            "aktivni": (tok or {}).get("aktivni"),
            "po_letech": (tok or {}).get("po_letech"),
            # Pole sVazbouNaPolitiky API nevyplňuje — viz docstring modulu.
            "hlidac_priznak_vazby": None,
            "osoby": [],
        })

    for o in osoby:
        if o["overeni"]["stav"] not in POUZITELNE:
            continue
        url_osoby = o["hlidac"].get("url")

        # (a) angažmá ve firmě, která od města inkasuje
        for f in o["firmy"] or []:
            if not f["obchoduje_s_mestem"]:
                continue
            d = zaznam(f["ico"], f["nazev"])
            d["osoby"].append({
                "osoba_id": o["osoba_id"], "jmeno": o["jmeno"],
                "role": o["role"], "strana": o.get("strana"),
                "zaklad": ["angazma-dle-hlidace"], "zdroj": url_osoby,
                "smluv_s_holdingem": None, "castka_smluv_czk": None,
                "overeni_osoby": o["overeni"]["stav"],
            })

        # (b) smlouvy holdingu, které Hlídač na osobu váže.
        # Dotaz `osobaId:X AND holding:Y` vrací i druhou stranu smlouvy — u
        # ředitelky domova pro seniory tak mezi protistranami vyjdou dodavatelé
        # potravin. To ale není stopa k politice u těch dodavatelů, jen u té
        # organizace. Bere se proto jen protistrana, která je sama firmou dané
        # osoby; ostatní se zahazují.
        vlastni_ica = {f["ico"] for f in (o["firmy"] or [])}
        for p in (o.get("smlouvy_holdingu") or {}).get("protistrany") or []:
            if p["ico"] not in vlastni_ica:
                continue
            d = zaznam(p["ico"], p.get("nazev"))
            stavajici = next((x for x in d["osoby"] if x["osoba_id"] == o["osoba_id"]), None)
            if stavajici:
                stavajici["zaklad"].append("smlouvy-dle-hlidace")
                stavajici["smluv_s_holdingem"] = p["smluv"]
                stavajici["castka_smluv_czk"] = p["castka_czk"]
            else:
                d["osoby"].append({
                    "osoba_id": o["osoba_id"], "jmeno": o["jmeno"],
                    "role": o["role"], "strana": o.get("strana"),
                    "zaklad": ["smlouvy-dle-hlidace"], "zdroj": url_osoby,
                    "smluv_s_holdingem": p["smluv"], "castka_smluv_czk": p["castka_czk"],
                    "overeni_osoby": o["overeni"]["stav"],
                })

    for d in dodavatele.values():
        d["osoby"].sort(key=lambda x: x["osoba_id"])
    return sorted(dodavatele.values(),
                  key=lambda d: -(d["celkem_od_mesta_czk"] or 0))


# --------------------------------------------------------------------------
# Hlavní běh
# --------------------------------------------------------------------------

def main() -> None:
    log = Log("propojeni")

    zdroj = nacti(ZDROJ_OSOB)
    if not zdroj or not zdroj.get("osoby"):
        raise ZdrojSelhal(
            f"Chybí {ZDROJ_OSOB} — spusť nejdřív scrapers/osoby_firmy.py."
        )

    cfg = nacti_config("subjekty.json")
    subjekty = {s["ico"]: s for s in cfg["subjekty"] if s.get("ico")}
    penize = index_penez()
    priznak = priznak_vazby_ve_smlouvach()
    log.info("načteno", osob=len(zdroj["osoby"]), protistran=len(penize),
             subjektu=len(subjekty))

    zdroje = [
        "https://www.hlidacstatu.cz",
        "https://api.hlidacstatu.cz/Api/v2",
        "https://smlouvy.gov.cz",
        "https://usneseni.muml.cz",
    ]

    # 1) osoby a jejich firmy
    osoby = sestav_osoby(zdroj, subjekty, penize)
    s_firmami = [o for o in osoby if o["firmy"]]
    uloz("propojeni/osoby_firmy.json", {
        "generovano": date.today().isoformat(),
        "zdroje": zdroje,
        "metodika": {
            "rozsah": "Veřejně činné osoby: zastupitelé, radní, statutáři a členové "
                      "dozorčích rad městských firem. Řadoví občané se neuvádějí.",
            "firmy_bez_vazby": "Firmy bez jakéhokoliv vztahu k městu se uvádějí "
                               "záměrně — jde o to ukázat, kde všude je osoba aktivní.",
            "overeni": "Firmy se zapisují jen u stavu potvrzeno a pravdepodobne. "
                       "Jinak je firmy=null a v overeni.kandidati je vidět proč.",
            "null": "null znamená nezjištěno, nikdy nulu. Prázdný seznam znamená, "
                    "že zdroj u osoby žádnou položku nevede.",
            "castky": "od_mesta_czk = smlouvy, kde je subjekt holdingu veden jako "
                      "plátce; mestu_czk = opačný směr. Směr se přebírá ze zdroje.",
        },
        "souhrn": {
            "osob": len(osoby),
            "osob_s_dohledanou_identitou": sum(
                1 for o in osoby if o["overeni"]["stav"] in POUZITELNE),
            "osob_s_firmou": len(s_firmami),
            "firem_celkem": sum(len(o["firmy"]) for o in s_firmami),
            "firem_unikatnich": len({f["ico"] for o in s_firmami for f in o["firmy"]}),
            "firem_bez_vazby_na_mesto": len({
                f["ico"] for o in s_firmami for f in o["firmy"]
                if f["vztah_k_mestu"] == "bez-vazby-na-mesto"}),
            "dle_stavu": zdroj.get("pocty"),
        },
        "osoby": osoby,
    })
    log.info("osoby_firmy.json", osob=len(osoby),
             firem=sum(len(o["firmy"]) for o in s_firmami))

    # 2) hlasování s vazbou na firmu
    vazby, souhrn_hlasovani = sestav_hlasovani(osoby, subjekty, penize, log)
    uloz("propojeni/hlasovani_vazby.json", {
        "generovano": date.today().isoformat(),
        "zdroje": zdroje,
        "metodika": {
            "co_to_je": "Hlasování, kde projednávaný bod zmiňuje firmu, ve které "
                        "má některý z hlasujících funkci nebo angažmá. Zaznamenávají "
                        "se fakta: kdo, jak hlasoval, jakou má roli a kolik firma "
                        "od města dostala. Hodnocení je na čtenáři.",
            "nalezeni_firmy": "Podle IČO uvozeného zkratkou IČ/IČO, nebo podle názvu "
                              "firmy bez diakritiky a bez koncové právní formy.",
            "vynechany_por_jednani": "Body typu „Program 3. ZM“ se vynechávají. Jejich "
                                     "text vyjmenovává celý pořad jednání, takže se v něm "
                                     "objeví kdejaká firma, ale hlasuje se o pořadu jednání, "
                                     "ne o té firmě. Počet je v souhrnu.",
            "obdobi_funkce_zname": False,
            "obdobi_funkce_pozn": "Zdroje neuvádějí, od kdy do kdy osoba funkci ve "
                                  "firmě zastávala. Vazba se proto zapisuje ke každému "
                                  "hlasování, u kterého je osoba ve jmenovitém záznamu. "
                                  "Datum hlasování je součástí záznamu.",
            "neucast": "Hodnota hlasu se přebírá beze změny, včetně nepritomen a "
                       "nehlasoval. Neúčast se nijak nezvýrazňuje.",
        },
        "souhrn": souhrn_hlasovani,
        "vazby": vazby,
    })
    log.info("hlasovani_vazby.json", **souhrn_hlasovani)

    # 3) dodavatelé se stopou k politice
    dodavatele = sestav_dodavatele(osoby, subjekty, penize)
    uloz("propojeni/dodavatele_politici.json", {
        "generovano": date.today().isoformat(),
        "zdroje": zdroje,
        "metodika": {
            "co_to_je": "Dodavatelé a protistrany městského holdingu, u kterých "
                        "Hlídač státu vede angažmá některé z veřejně činných osob města.",
            "zaklad": {
                "angazma-dle-hlidace": "Osoba je podle Hlídače angažovaná ve firmě.",
                "smlouvy-dle-hlidace": "Hlídač váže smlouvy holdingu na osobu "
                                       "dotazem osobaId:{id} AND holding:{ico_mesta}. "
                                       "Započítává se jen protistrana, která je sama "
                                       "firmou dané osoby — dotaz vrací i druhou stranu "
                                       "smlouvy (u ředitelky domova pro seniory tak vyjdou "
                                       "i dodavatelé potravin), a to stopa k politice "
                                       "u takového dodavatele není.",
            },
            "priznak_vazba_na_politiky": (
                "Pole `vazba_na_politiky` v data/penize/smlouvy/*.json je u všech "
                f"{priznak['smluv_celkem']} smluv false, protože API v2 Hlídače pole "
                "sVazbouNaPolitiky nevyplňuje (vrací null i v detailu smlouvy a filtr "
                "sVazbouNaPolitiky:1 vrací nula výsledků, ověřeno 17. 8. 2026). "
                "Příznak se proto nepoužívá a v záznamech je jako null = nezjištěno."
            ),
        },
        "priznak_ve_smlouvach": priznak,
        "souhrn": {
            "dodavatelu": len(dodavatele),
            "mestskych_subjektu": sum(1 for d in dodavatele if d["mestsky_subjekt"]),
            "mimo_holding": sum(1 for d in dodavatele if not d["mestsky_subjekt"]),
            "celkem_od_mesta_czk": round(
                sum(d["celkem_od_mesta_czk"] or 0 for d in dodavatele), 2),
            "dotcenych_osob": len({o["osoba_id"] for d in dodavatele for o in d["osoby"]}),
        },
        "dodavatele": dodavatele,
    })
    log.info("dodavatele_politici.json", dodavatelu=len(dodavatele))
    log.pricti(len(osoby) + len(vazby) + len(dodavatele))
    log.uzavri()


if __name__ == "__main__":
    main()
