"""Sběr vazeb veřejně činných osob na firmy — modul P1.

CO TENHLE SBĚRAČ DĚLÁ
---------------------
Pro veřejně činné osoby města (zastupitelé, radní, statutáři a dozorčí rady
městských firem) dohledá v Hlídači státu úplný seznam firem, ve kterých je
osoba angažovaná — **včetně firem, které s městem nemají nic společného**.
To je záměr: přiznat, kde všude je člověk aktivní, ne jen tam, kde se to
protíná s městskou kasou.

Výstup je surovina pro `pipeline/propojeni.py`, které k firmám teprve
připojuje peníze a hlasování.

ODKUD DATA JSOU
---------------
Dvě cesty, každá pokrývá to, co ta druhá neumí:

1. **MCP nástroje Hlídače státu** — jediný zdroj seznamu firem u osoby
   (`get_person_detail` → `involved_In_Companies`). REST API v2 tohle nevrací:
   `/osoby/{id}` seznam firem neobsahuje a `/osoby/hledatFtx` vrací jen osoby
   vedené jako politik nebo sponzor strany, zbytek je za komerční licencí
   (ověřeno 17. 8. 2026). MCP nejde volat z Pythonu, proto je sklizeň uložená
   jako vstupní soubor `data/propojeni/zdroje/hlidac_mcp.json`; obnovuje ji
   operátor s přístupem k MCP nástrojům. Když soubor chybí, sběrač skončí
   `ZdrojSelhal` — nikdy nedoběhne s prázdnem.

2. **REST API v2 Hlídače státu** — kód si sám dotáhne smlouvy městského
   holdingu, ve kterých je osoba angažovaná, dotazem
   `osobaId:{id} AND holding:{ico_mesta}`. Tenhle operátor funguje a je to
   náhrada za pole `sVazbouNaPolitiky`, které API u smluv nevyplňuje
   (vrací `null`, viz poznámka v `pipeline/propojeni.py`).

ROZPOZNÁVÁNÍ OSOB
-----------------
Jmenovky se v Hlídači opakují — „Jan Budka" má 9 záznamů, „Martin Hladík" 10.
Přiřadit zastupiteli firmy cizího člověka stejného jména by bylo horší než
nemít údaj žádný, takže se nikdy nehádá. Kandidát musí souhlasit jménem
i příjmením (bez diakritiky, i prohozeně — Hlídač má pár záznamů s prohozenými
poli) a pak se hledá potvrzení:

- `firma-mesta` — osoba je angažovaná ve firmě z `config/subjekty.json`
- `organ-mestske-firmy` — osoba je v Hlídači vedená u městského subjektu
- `aktivita-marianske-lazne` — životopis v Hlídači zmiňuje Mariánské Lázně
- `shoda-strany` — strana v Hlídači odpovídá straně v `data/lide/osobnosti.json`

Podle toho se nastaví `stav`:

- `potvrzeno`     — jediný kandidát na jméno a aspoň jedno potvrzení
- `pravdepodobne` — jediný kandidát bez potvrzení a bez životopisu v Hlídači
                    (Hlídač o něm nic, co by odporovalo, neví), nebo více
                    kandidátů, z nichž právě jeden má vazbu na městskou firmu
- `nejednoznacne` — víc kandidátů bez rozlišujícího potvrzení, nebo jediný
                    kandidát, jehož životopis popisuje jinou veřejnou dráhu
                    (typicky bývalý senátor stejného jména)
- `nenalezeno`    — Hlídač osobu shodného jména nezná

Firmy se zapisují jen u `potvrzeno` a `pravdepodobne`. U ostatních je `firmy`
`null` a v záznamu je vypsaný seznam kandidátů, aby bylo vidět, proč se údaj
nedoplnil. Prázdný seznam `[]` znamená něco jiného než `null`: Hlídač osobu zná
a žádnou firmu u ní nevede.

KOHO SLEDUJEME
--------------
Výhradně veřejně činné osoby: zastupitele, radní a statutáry či členy
dozorčích rad městských firem. Řadoví občané se stejným jménem se do výstupu
nedostanou ani jako kandidáti s firmami — u nich se ukládá jen person_id,
rok narození a počet firem, tedy to, co je potřeba k doložení nejednoznačnosti.

VÝSTUP
------
`data/propojeni/zdroje/osoby_hlidac.json`

```json
{
  "generovano": "2026-08-17",
  "zdroje": ["https://www.hlidacstatu.cz", "https://api.hlidacstatu.cz/Api/v2"],
  "osoby": [{
    "osoba_id": "dubnicky-roman",
    "jmeno": "Roman Dubnický",
    "role": ["zastupitel", "člen dozorčí rady"],
    "strana": "ANO 2011",
    "hlidac": {
      "person_id": "roman-dubnicky",
      "url": "https://www.hlidacstatu.cz/osoba/roman-dubnicky",
      "narozen": "1981",
      "angazovanost": "Bez vazby na politiku",
      "aktivity": null
    },
    "overeni": { "stav": "potvrzeno", "zaklad": ["firma-mesta"],
                 "kandidatu": 1, "kandidati": [] },
    "firmy": [{ "ico": "25213261", "nazev": "TECHNICKÝ A DOPRAVNÍ SERVIS, s.r.o.",
                "url": "https://www.hlidacstatu.cz/subjekt/25213261" }],
    "sponzoring": { "zaznamu": 0, "celkem_czk": 0.0, "strany": [],
                    "zaznamy_uplne": true, "zaznamy": [] },
    "smlouvy_se_statem": [{ "rok": 2019, "smluv": 3, "castka_czk": 274801.2 }],
    "smlouvy_holdingu": { "smluv": 72, "protistrany": [
        { "ico": "25213261", "nazev": "TECHNICKÝ A DOPRAVNÍ SERVIS, s.r.o.",
          "smluv": 72, "castka_czk": 12345.0 }]}
  }]
}
```

Chybějící údaj je vždy `null`, nikdy dohad.
"""
from __future__ import annotations

import os
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import (  # noqa: E402
    ROOT,
    Log,
    ZdrojSelhal,
    nacti,
    nacti_config,
    sledovane_subjekty,
    uloz,
)

API = "https://api.hlidacstatu.cz/Api/v2"
NA_STRANKU = 25  # server drží pevně, parametr pocet nemá vliv
WEB_OSOBA = "https://www.hlidacstatu.cz/osoba/"
WEB_SUBJEKT = "https://www.hlidacstatu.cz/subjekt/"

SKLIZEN = "propojeni/zdroje/hlidac_mcp.json"
VYSTUP = "propojeni/zdroje/osoby_hlidac.json"

# Role, které z osoby dělají veřejně činnou osobu pro účely tohohle modulu.
VEREJNE_ROLE = {"zastupitel", "radní", "vedení města", "statutár", "člen dozorčí rady"}

# Strany se v obou zdrojích píší jinak. Mapuje se na společný tvar, aby
# „ANO 2011" a „ANO" byly shoda a „Piráti" a „Česká pirátská strana" taky.
STRANY = {
    "ano 2011": "ano", "ano": "ano",
    "pirati": "pirati", "ceska piratska strana": "pirati",
    "sdruzeni stan nk": "stan", "stan": "stan",
    "ods plus": "ods", "ods": "ods",
    "spd": "spd",
    "zmena pro ml": "zmena-pro-ml", "zmena pro marianske lazne": "zmena-pro-ml",
    "mesto sobe": "mesto-sobe",
}


# --------------------------------------------------------------------------
# Pomocníci
# --------------------------------------------------------------------------

def bez_diakritiky(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower().strip()


def klic_strany(strana: str | None) -> str | None:
    if not strana:
        return None
    zaklad = bez_diakritiky(strana).replace('"', "").replace(",", "")
    zaklad = " ".join(zaklad.split())
    return STRANY.get(zaklad, zaklad)


def rozlozit_jmeno(cele: str) -> tuple[str, str]:
    """Z 'Roman Dubnický' udělá ('roman', 'dubnicky'). Tituly se zahazují."""
    casti = [c for c in bez_diakritiky(cele).replace(".", " ").split() if len(c) > 1]
    tituly = {"mgr", "ing", "bc", "mudr", "judr", "phdr", "rndr", "mvdr", "arch", "ph", "csc", "dis"}
    casti = [c for c in casti if c not in tituly]
    if len(casti) < 2:
        return (casti[0] if casti else ""), ""
    return casti[0], casti[-1]


def token() -> str:
    t = os.environ.get("HLIDAC_TOKEN", "").strip()
    if not t:
        env = ROOT / ".env"
        if env.exists():
            for radek in env.read_text(encoding="utf-8").splitlines():
                if radek.startswith("HLIDAC_TOKEN="):
                    t = radek.split("=", 1)[1].strip()
                    break
    if not t:
        raise ZdrojSelhal(
            "Chybí HLIDAC_TOKEN. Získej zdarma na hlidacstatu.cz a vlož do .env "
            "jako HLIDAC_TOKEN=... (soubor je mimo git)."
        )
    return t


def _get(cesta: str, params: dict, tok: str, retries: int = 4) -> dict:
    url = f"{API}/{cesta}"
    hlavicky = {"Authorization": f"Token {tok}", "Accept": "application/json"}
    posledni: Exception | None = None
    for pokus in range(retries):
        try:
            r = requests.get(url, params=params, headers=hlavicky, timeout=60)
            if r.status_code == 429 or 500 <= r.status_code < 600:
                raise ZdrojSelhal(f"HTTP {r.status_code}")
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001 — opakujeme na čemkoliv síťovém
            posledni = e
            if pokus < retries - 1:
                time.sleep(2 ** (pokus + 1))
    raise ZdrojSelhal(f"{url} selhalo na {retries} pokusů: {posledni}")


# --------------------------------------------------------------------------
# Rozpoznání osoby v Hlídači
# --------------------------------------------------------------------------

def kandidati_pro(osoba: dict, sklizen: dict) -> list[dict]:
    """Kandidáti se shodným jménem — z hledání i z orgánů městských firem.

    Hledání podle jména Hlídač dělá fuzzy, takže vrací i jiná příjmení
    („Petr Hála" → „Petr Halada"). Ta se zahazují. Naopak osoby vedené
    u městských subjektů se do kandidátů přidávají, protože přes hledání
    jména se na ně někdy vůbec nedá dostat.
    """
    jmeno, prijmeni = rozlozit_jmeno(osoba["jmeno"])
    nalezeni: dict[str, dict] = {}

    def zvaz(pid: str | None, k_jmeno: str, k_prijmeni: str, **extra) -> None:
        if not pid:
            return
        a, b = bez_diakritiky(k_jmeno), bez_diakritiky(k_prijmeni)
        # Hlídač má pár záznamů s prohozeným jménem a příjmením.
        if not ((a == jmeno and b == prijmeni) or (a == prijmeni and b == jmeno)):
            return
        nalezeni.setdefault(pid, {"person_id": pid, **extra})

    for kand in sklizen["hledani"].get(osoba["jmeno"], []):
        zvaz(kand["id"], kand["jmeno"], kand["prijmeni"],
             narozen=kand.get("narozen"), angazovanost=kand.get("angazovanost"),
             strana=kand.get("strana"), firem=kand.get("firem"))

    for ico, subj in sklizen["subjekty"].items():
        for clen in subj.get("osoby", []):
            zvaz(clen["id"], clen["jmeno"], clen["prijmeni"], narozen=clen.get("narozen"))
            if clen["id"] in nalezeni:
                nalezeni[clen["id"]].setdefault("organy_mesta", []).append(ico)

    return list(nalezeni.values())


def potvrzeni(kand: dict, osoba: dict, sklizen: dict, ica_mesta: set[str]) -> list[str]:
    """Co u kandidáta svědčí pro to, že jde o naši veřejně činnou osobu."""
    zaklad: list[str] = []
    detail = sklizen["osoby"].get(kand["person_id"]) or {}

    if any(f["ico"] in ica_mesta for f in detail.get("firmy", [])):
        zaklad.append("firma-mesta")
    if kand.get("organy_mesta"):
        zaklad.append("organ-mestske-firmy")
    if "mariansk" in bez_diakritiky(detail.get("aktivity") or ""):
        zaklad.append("aktivita-marianske-lazne")

    strana_hlidac = klic_strany(detail.get("strana") or kand.get("strana"))
    if strana_hlidac and strana_hlidac == klic_strany(osoba.get("strana")):
        zaklad.append("shoda-strany")

    return zaklad


def rozpoznej(osoba: dict, sklizen: dict, ica_mesta: set[str]) -> dict:
    """Vrátí {person_id, stav, zaklad, kandidati} podle pravidel v docstringu."""
    kandidati = kandidati_pro(osoba, sklizen)
    prazdny = {"person_id": None, "stav": "nenalezeno", "zaklad": [],
               "kandidatu": 0, "kandidati": []}
    if not kandidati:
        return prazdny

    for k in kandidati:
        k["zaklad"] = potvrzeni(k, osoba, sklizen, ica_mesta)

    prehled = [
        {"person_id": k["person_id"], "narozen": k.get("narozen"),
         "angazovanost": k.get("angazovanost"), "firem": k.get("firem"),
         "zaklad": k["zaklad"]}
        for k in kandidati
    ]

    if len(kandidati) == 1:
        k = kandidati[0]
        detail = sklizen["osoby"].get(k["person_id"]) or {}
        if k["zaklad"]:
            stav = "potvrzeno"
        elif not (detail.get("aktivity") or "").strip():
            # Hlídač o něm neví nic, co by mohlo odporovat.
            stav = "pravdepodobne"
        else:
            # Hlídač zná jeho veřejnou dráhu a ta naši osobu nepřipomíná.
            stav = "nejednoznacne"
        return {"person_id": k["person_id"] if stav != "nejednoznacne" else None,
                "stav": stav, "zaklad": k["zaklad"], "kandidatu": 1,
                "kandidati": prehled if stav == "nejednoznacne" else []}

    # Víc kandidátů: rozhoduje jedině vazba na městskou firmu, a to jen když
    # ji má právě jeden z nich.
    s_vazbou = [k for k in kandidati
                if "firma-mesta" in k["zaklad"] or "organ-mestske-firmy" in k["zaklad"]]
    if len(s_vazbou) == 1:
        k = s_vazbou[0]
        return {"person_id": k["person_id"], "stav": "pravdepodobne",
                "zaklad": k["zaklad"], "kandidatu": len(kandidati), "kandidati": prehled}

    return {"person_id": None, "stav": "nejednoznacne", "zaklad": [],
            "kandidatu": len(kandidati), "kandidati": prehled}


# --------------------------------------------------------------------------
# Smlouvy městského holdingu, kde je osoba angažovaná
# --------------------------------------------------------------------------

def smlouvy_holdingu(person_id: str, ico_mesta: str, tok: str) -> dict:
    """Smlouvy holdingu města, u nichž je osoba vedená jako angažovaná.

    Operátor `osobaId:` Hlídač podporuje; `holding:{ico}` omezí na město
    a jím ovládané subjekty. Sčítá se podle protistrany.
    """
    dotaz = f"osobaId:{person_id} AND holding:{ico_mesta}"
    protistrany: dict[str, dict] = {}
    celkem_smluv = 0
    strana = 1

    while True:
        data = _get("smlouvy/hledat", {"dotaz": dotaz, "strana": strana}, tok)
        vysledky = data.get("results") or []
        celkem = data.get("total") or 0
        if not vysledky:
            break

        for s in vysledky:
            celkem_smluv += 1
            prijemci = s.get("prijemce") or []
            druha = prijemci[0] if prijemci else (s.get("platce") or {})
            ico = druha.get("ico")
            if not ico:
                continue
            zaznam = protistrany.setdefault(
                ico, {"ico": ico, "nazev": druha.get("nazev"), "smluv": 0, "castka_czk": 0.0}
            )
            zaznam["smluv"] += 1
            cena = s.get("calculatedPriceWithVATinCZK")
            # Nula v registru znamená „cena neuvedena", ne nulovou smlouvu.
            if isinstance(cena, (int, float)) and cena:
                zaznam["castka_czk"] += float(cena)

        if celkem_smluv >= celkem or strana * NA_STRANKU >= celkem:
            break
        strana += 1
        time.sleep(0.3)  # šetrné tempo vůči cizímu API

    razeno = sorted(protistrany.values(), key=lambda p: -p["castka_czk"])
    for p in razeno:
        p["castka_czk"] = round(p["castka_czk"], 2)
    return {"smluv": celkem_smluv, "protistrany": razeno}


# --------------------------------------------------------------------------
# Hlavní běh
# --------------------------------------------------------------------------

def verejne_cinne(osobnosti: list[dict]) -> list[dict]:
    return [o for o in osobnosti if VEREJNE_ROLE & set(o.get("role") or [])]


def main() -> None:
    log = Log("osoby_firmy")

    sklizen = nacti(SKLIZEN)
    if not sklizen or not sklizen.get("osoby"):
        raise ZdrojSelhal(
            f"Chybí sklizeň z MCP nástrojů Hlídače ({SKLIZEN}). "
            "Obnovuje ji operátor s přístupem k MCP — viz docstring tohoto modulu."
        )

    osobnosti = nacti("lide/osobnosti.json")
    if not osobnosti:
        raise ZdrojSelhal("Chybí data/lide/osobnosti.json — bez něj není koho dohledávat.")

    subjekty = sledovane_subjekty()
    ica_mesta = {s["ico"] for s in subjekty}
    ico_mesta = nacti_config("subjekty.json")["mesto"]["ico"]

    sledovani = verejne_cinne(osobnosti)
    log.info("veřejně činných osob k dohledání", pocet=len(sledovani))

    tok = token()
    vystup: list[dict] = []
    pocty = {"potvrzeno": 0, "pravdepodobne": 0, "nejednoznacne": 0, "nenalezeno": 0}

    for osoba in sorted(sledovani, key=lambda o: o["id"]):
        rozpoznani = rozpoznej(osoba, sklizen, ica_mesta)
        pocty[rozpoznani["stav"]] += 1
        pid = rozpoznani["person_id"]
        detail = sklizen["osoby"].get(pid) if pid else None

        # Prázdný seznam znamená „Hlídač u osoby žádnou firmu nevede".
        # Když detail osoby ve sklizni chybí, je to neznámý údaj, tedy null —
        # ta dvě se nesmí splést.
        firmy = None
        if detail:
            firmy = [
                {"ico": f["ico"], "nazev": f["nazev"], "url": f"{WEB_SUBJEKT}{f['ico']}"}
                for f in detail.get("firmy", [])
            ]

        # Totéž u sponzoringu: null = nedohledáno, ne „nesponzoroval".
        sponzor = sklizen["sponzoring"].get(pid) if pid else None

        holding = {"smluv": None, "protistrany": []}
        if pid:
            try:
                holding = smlouvy_holdingu(pid, ico_mesta, tok)
            except ZdrojSelhal as e:
                log.chyba(f"{osoba['jmeno']} ({pid}): smlouvy holdingu — {e}")
            time.sleep(0.3)

        vystup.append({
            "osoba_id": osoba["id"],
            "jmeno": osoba["jmeno"],
            "role": osoba.get("role") or [],
            "kategorie": osoba.get("kategorie"),
            "strana": osoba.get("strana"),
            "funkce": osoba.get("funkce") or [],
            "hlidac": {
                "person_id": pid,
                "url": f"{WEB_OSOBA}{pid}" if pid else None,
                "narozen": (detail or {}).get("narozen"),
                "angazovanost": (detail or {}).get("angazovanost"),
                "aktivity": ((detail or {}).get("aktivity") or None),
            },
            "overeni": {
                "stav": rozpoznani["stav"],
                "zaklad": rozpoznani["zaklad"],
                "kandidatu": rozpoznani["kandidatu"],
                "kandidati": rozpoznani["kandidati"],
            },
            "firmy": firmy,
            "sponzoring": sponzor,
            "smlouvy_se_statem": detail.get("smlouvy_se_statem") if detail else None,
            "smlouvy_holdingu": holding,
        })
        log.pricti()

    uloz(VYSTUP, {
        "generovano": date.today().isoformat(),
        "zdroje": [
            "https://www.hlidacstatu.cz",
            "https://api.hlidacstatu.cz/Api/v2",
        ],
        "licence": sklizen.get("licence"),
        "sklizeno_mcp": sklizen.get("sklizeno"),
        "metodika": (
            "Kandidát v Hlídači musí souhlasit jménem i příjmením bez diakritiky. "
            "Firmy se zapisují jen u stavu potvrzeno a pravdepodobne; jinak zůstává "
            "seznam prázdný a v overeni.kandidati je vidět, proč se údaj nedoplnil."
        ),
        "pocty": pocty,
        "osoby": vystup,
    })

    log.info("rozpoznání", **pocty)
    log.uzavri()


if __name__ == "__main__":
    main()
