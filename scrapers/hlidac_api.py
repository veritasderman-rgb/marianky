"""Plná sklizeň registru smluv přes REST API Hlídače státu.

Nahrazuje dřívější sběr přes MCP nástroje, který zvládl 6 % smluv počtem.
API je za tokenem (zdarma po registraci na hlidacstatu.cz); token se čte
z proměnné HLIDAC_TOKEN nebo ze souboru .env, který je mimo git.

Formát výstupu je shodný s dřívějším sběračem, takže na něj navazující
agregace funguje beze změny. Navíc se plní `predmet`, který přes MCP chyběl.

Poznámka ke směru peněz: pole `platce` a `prijemce` se přebírají tak, jak
je zveřejňovatel zapsal, a NEPŘEPISUJÍ se podle klíčových slov. U nájmů
a prodejů bývá město uvedeno jako plátce, i když peníze inkasuje — je to
vada na straně zdroje a opravovat ji dohadem by z dat udělalo dohad.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import ROOT, Log, ZdrojSelhal, sledovane_subjekty, uloz  # noqa: E402

API = "https://api.hlidacstatu.cz/Api/v2"
NA_STRANKU = 25  # server drží pevně, parametr pocet nemá vliv


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
        except Exception as e:  # noqa: BLE001
            posledni = e
            if pokus < retries - 1:
                time.sleep(2 ** (pokus + 1))
    raise ZdrojSelhal(f"{url} selhalo na {retries} pokusů: {posledni}")


def _cislo(x) -> float | None:
    """Nula v registru znamená 'cena neuvedena', ne nulovou smlouvu.

    Ověřeno: u města vrací filtr 'bez uvedené ceny' 258 smluv a všechny
    mají nulu. Mapujeme na null, aby se nesčítaly jako skutečné nuly.
    """
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v != 0 else None


def _smer(s: dict, ico: str) -> str:
    """vydaj = sledovaný subjekt platí, prijem = inkasuje."""
    platce = (s.get("platce") or {}).get("ico")
    if platce == ico:
        return "vydaj"
    for p in s.get("prijemce") or []:
        if p.get("ico") == ico:
            return "prijem"
    return "vydaj"


def _protistrana(s: dict, ico: str) -> tuple[str | None, str | None]:
    """Druhá strana smlouvy.

    Registr obsahuje chyby: u některých smluv má protistrana přiřazené IČO
    města. Zapisujeme, co ve zdroji je — název se liší, takže je taková
    smlouva v datech dohledatelná, ale neopravujeme ji domněnkou.
    """
    if (s.get("platce") or {}).get("ico") == ico:
        prijemci = s.get("prijemce") or []
        if prijemci:
            return prijemci[0].get("ico"), prijemci[0].get("nazev")
        return None, None
    platce = s.get("platce") or {}
    return platce.get("ico"), platce.get("nazev")


def prevedi(s: dict, ico: str) -> dict:
    ident = s.get("identifikator") or {}
    id_smlouvy = ident.get("idSmlouvy") or s.get("id")
    p_ico, p_nazev = _protistrana(s, ico)
    issues = s.get("issues") or []

    return {
        "id": str(id_smlouvy),
        "datum": (s.get("datumUzavreni") or "")[:10] or None,
        "castka_czk": _cislo(s.get("calculatedPriceWithVATinCZK")),
        "predmet": (s.get("predmet") or None),
        "kategorie": (s.get("classification") or {}).get("typeValue")
        if isinstance(s.get("classification"), dict) else None,
        "vada": any((i or {}).get("importance", 0) >= 3 for i in issues),
        "url": s.get("odkaz") or f"https://www.hlidacstatu.cz/Detail/{id_smlouvy}",
        "protistrana_ico": p_ico,
        "protistrana": p_nazev,
        "smer": _smer(s, ico),
        # POZOR: `sVazbouNaPolitiky` API v2 NEVYPLŇUJE — vrací null v seznamu
        # i v detailu a filtr `sVazbouNaPolitiky:1` nevrací nic. Původně tu
        # bylo bool(...), což z chybějícího údaje udělalo `false`, a všech
        # 6 521 smluv tak tvrdilo „ověřeno: bez vazby na politiky", ačkoliv
        # pravda je „nevíme". Necháváme `null` — neznámý údaj se nesmí tvářit
        # jako zjištěná nula.
        #
        # Vazbu na politiky lze doložit jinudy a spolehlivěji: přes angažmá
        # osoby ve firmě (viz pipeline/propojeni.py).
        "vazba_na_politiky": s.get("sVazbouNaPolitiky"),
        "bez_ceny": _cislo(s.get("calculatedPriceWithVATinCZK")) is None,
    }


def sklid_subjekt(ico: str, nazev: str, tok: str, log: Log) -> list[dict]:
    smlouvy: list[dict] = []
    videne: set[str] = set()
    strana = 1

    while True:
        data = _get("smlouvy/hledat", {"dotaz": f"ico:{ico}", "strana": strana}, tok)
        vysledky = data.get("results") or []
        celkem = data.get("total") or 0
        if not vysledky:
            break

        for s in vysledky:
            zaznam = prevedi(s, ico)
            if zaznam["id"] in videne:
                continue
            videne.add(zaznam["id"])
            smlouvy.append(zaznam)

        if strana == 1:
            log.info(f"{nazev}: v registru {celkem} smluv")
        if len(smlouvy) >= celkem or strana * NA_STRANKU >= celkem:
            break
        strana += 1
        time.sleep(0.15)  # šetrné tempo vůči cizímu API

    return smlouvy


def main() -> None:
    log = Log("hlidac_api")
    tok = token()
    subjekty = sledovane_subjekty()
    log.info("sklízím subjektů", pocet=len(subjekty))

    celkem_smluv = 0
    for s in subjekty:
        ico, nazev = s["ico"], s["nazev"]
        try:
            smlouvy = sklid_subjekt(ico, nazev, tok, log)
        except ZdrojSelhal as e:
            log.chyba(f"{nazev} ({ico}): {e}")
            continue

        uloz(f"penize/smlouvy/{ico}.json", {
            "ico": ico,
            "nazev": nazev,
            "zdroj": "api.hlidacstatu.cz/Api/v2",
            "smlouvy": smlouvy,
        })
        celkem_smluv += len(smlouvy)
        log.pricti(len(smlouvy))

    log.info("sklizeno smluv celkem", pocet=celkem_smluv)
    log.uzavri()


if __name__ == "__main__":
    main()
