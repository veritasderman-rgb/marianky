#!/usr/bin/env python3
"""Srovnání hospodaření s podobnými městy — rekapitulace FIN + obyvatelé.

Dva zdroje, oba už projekt umí, tenhle sběrač je jen míří na víc měst:

1. **Monitor státní pokladny** — z celostátních extraktů FIN 2-12 M se
   vybírá souhrnná tabulka (rekapitulace, výkaz 051 / tabulka 000400) pro
   města ze `config/srovnani.json`. Berou se jen UZAVŘENÉ roky (prosinec):
   od roku 2026 nese výkaz kód 063 a rekapitulaci nemá vůbec, dopočítávat
   ji z položek pro šest cizích měst by znamenalo vozit statisíce řádků
   kvůli jednomu grafu.

2. **ČSÚ, sada 130149 (obyvatelstvo)** — počet obyvatel k 31. 12. pro
   tatáž města, aby šly rozpočty přepočítat na obyvatele. Soubor je
   celorepublikový a čte se proudově, stejně jako v `scrapers/csu.py`.

Proč se nerozšiřuje rovnou `scrapers/monitor.py`: jeho výstup
`data/rozpocet/fin212m/` je vstupem pro `pipeline/rozpocet.py`, který v něm
čeká výhradně město a jeho holding. Přimíchat tam šest cizích měst by
znamenalo učit každý navazující výpočet, koho má ignorovat. Srovnání proto
žije ve vlastní složce `data/rozpocet/srovnani/`.

Extrakty FIN mají 10–25 MB na ročník; stažený ZIP se po přečtení maže
(`--ponechat-cache` ho nechá pro další běhy — hodí se, když na stejném
stroji běží i `scrapers/monitor.py`).

Kontrola identity: u obyvatel se ověřuje, že název obce ve zdroji odpovídá
názvu v konfiguraci. Kdyby kód obce ukazoval jinam, spadne to tady, ne až
v grafu s cizími čísly.

Spuštění:
    python3 scrapers/srovnani.py
    python3 scrapers/srovnani.py --jen fin        # jen rozpočty
    python3 scrapers/srovnani.py --jen obyvatele  # jen ČSÚ
    python3 scrapers/srovnani.py --ponechat-cache
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import ROOT, Log, ZdrojSelhal, uloz  # noqa: E402
from scrapers.monitor import (  # noqa: E402
    VYKAZY,
    cti_extrakt,
    nacti_katalog,
    popis_sady,
    sady_vykazu,
    soubor_ke_stazeni,
)
from scrapers.monitor import _nazev_sady, _stahni  # noqa: E402
from scrapers import csu  # noqa: E402

VYSTUP = "rozpocet/srovnani"


def mesta() -> list[dict]:
    cesta = ROOT / "config" / "srovnani.json"
    if not cesta.exists():
        raise ZdrojSelhal("chybí config/srovnani.json se seznamem měst")
    data = json.loads(cesta.read_text(encoding="utf-8"))
    out = data.get("mesta") or []
    if not out:
        raise ZdrojSelhal("config/srovnani.json nemá žádná města")
    return out


# --------------------------------------------------------------------------
# 1. Rekapitulace FIN pro srovnávaná města
# --------------------------------------------------------------------------

def sber_fin(seznam: list[dict], log: Log, ponechat_cache: bool) -> int:
    # Jen souhrnná tabulka — položkové tabulky šesti měst by byly statisíce
    # řádků, ze kterých srovnání potřebuje třicet.
    vykaz = replace(VYKAZY["fin212m"], tabulky={("051", "000400"): "rekapitulace"})
    ica = {m["ico"] for m in seznam}
    podle_ica = {m["ico"]: m for m in seznam}

    katalog = nacti_katalog()
    sady = sady_vykazu(katalog, vykaz)
    rocni = [s for s in sady if s[1] == 12]
    if not rocni:
        raise ZdrojSelhal("v katalogu MF není žádná prosincová sada FIN 2-12 M")
    log.info(f"FIN: {len(rocni)} uzavřených ročníků ke srovnání")

    hotovo = 0
    for rok, mesic, iri in rocni:
        nazev_sady = _nazev_sady(iri)
        detail = popis_sady(iri)
        url = soubor_ke_stazeni(detail, "CSV")
        if not url:
            log.chyba(f"{nazev_sady}: v katalogu není CSV distribuce")
            continue

        cesta = _stahni(url, f"{nazev_sady}.zip", log)
        oddily, meta = cti_extrakt(cesta, vykaz, ica, log)
        if not ponechat_cache:
            cesta.unlink(missing_ok=True)

        radky = oddily.get("rekapitulace") or []
        po_mestech: dict[str, dict] = {}
        for r in radky:
            kod = r.get("polozka_vykazu")
            if not kod:
                continue
            po_mestech.setdefault(r["ico"], {})[kod] = {
                "schvaleny": r.get("schvaleny"),
                "upraveny": r.get("upraveny"),
                "skutecnost": r.get("skutecnost"),
            }

        nalezena = sorted(po_mestech)
        uloz(f"{VYSTUP}/fin/{rok}-12.json", {
            "rok": rok,
            "obdobi": f"{rok}-12",
            "koncove": True,
            "jednotka": "CZK",
            "zdroj": {
                "sada": iri,
                "soubor": url,
                "staženo": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            },
            "kody_vykazu": meta["kody_vykazu"],
            "mesta_v_datech": [
                {"ico": i, "nazev": podle_ica[i]["nazev"]} for i in nalezena
            ],
            # Ověřená nepřítomnost ve zdroji, ne chyba stahování.
            "mesta_bez_dat": [
                {"ico": m["ico"], "nazev": m["nazev"]}
                for m in seznam if m["ico"] not in po_mestech
            ],
            "rekapitulace": po_mestech,
        })
        log.pricti()
        log.info(f"FIN {rok}: rekapitulace pro {len(nalezena)} z {len(seznam)} měst")
        hotovo += 1
    return hotovo


# --------------------------------------------------------------------------
# 2. Obyvatelé srovnávaných měst z ČSÚ
# --------------------------------------------------------------------------

def sber_obyvatel(seznam: list[dict], log: Log) -> None:
    sada = next(s for s in csu.SADY if s.kod == "obyvatelstvo")
    katalog_radky = csu.katalog(log)
    zdroje = csu.sady_z_katalogu(sada, katalog_radky)
    if not zdroje:
        raise ZdrojSelhal("katalog ČSÚ nezná sadu obyvatelstva (130149)")

    kody = {m["kod_obce"]: m for m in seznam}
    po_obcich: dict[str, dict[str, int]] = {m["kod_obce"]: {} for m in seznam}
    nazvy_ve_zdroji: dict[str, str] = {}
    pouzite = []

    for z in zdroje:
        for d in csu.distribuce(z):
            pripona = ".zip" if ".zip" in d["url"].lower() else ".csv"
            jmeno = f"srovnani-obyv-{z['dataset_id']}{pripona}"
            cesta = csu._stahni(d["url"], jmeno, log)
            for r in csu._radky_csv(cesta):
                kod = next(((r.get(s) or "").strip() for s in csu.SLOUPCE_UZEMI
                            if (r.get(s) or "").strip()), "")
                if kod not in kody:
                    continue
                # Jen celkový počet obyvatel: bez členění na pohlaví a věk.
                if (r.get("pohlavi_txt") or "").strip() or (r.get("vek_txt") or "").strip():
                    continue
                stapro = (r.get("stapro_kod") or "").strip()
                if stapro and stapro != "2406":
                    continue
                obdobi = csu._obdobi(r, "rok")
                hodnota, _ = csu._hodnota(r)
                if not obdobi or hodnota is None:
                    continue
                po_obcich[kod][obdobi] = int(hodnota)
                nazev = (r.get("uzemi_txt") or r.get("vuzemi_txt") or "").strip()
                if nazev:
                    nazvy_ve_zdroji[kod] = nazev
            pouzite.append({"dataset_id": z["dataset_id"], "url": d["url"]})

    # Kontrola identity: kód obce musí ve zdroji nést stejné jméno jako
    # v konfiguraci. Jinak by se srovnávala cizí obec a nikdo by to nepoznal.
    for kod, m in kody.items():
        nazev = nazvy_ve_zdroji.get(kod)
        if nazev and nazev != m["nazev"]:
            raise ZdrojSelhal(
                f"kód obce {kod} nese ve zdroji ČSÚ název „{nazev}“, "
                f"konfigurace čeká „{m['nazev']}“ — srovnání by lhalo")
        if not po_obcich[kod]:
            log.chyba(f"obyvatelé: pro {m['nazev']} ({kod}) zdroj nic nevrátil")

    uloz(f"{VYSTUP}/obyvatele.json", {
        "generovano": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "zdroj": {
            "popis": "ČSÚ, otevřená sada 130149 — počet obyvatel k 31. 12.",
            "sady": pouzite,
        },
        "metodika": [
            "Počet obyvatel je stav k 31. 12. daného roku (ukazatel 2406), "
            "bez členění na pohlaví a věk.",
            "Název obce ve zdroji se kontroluje proti konfiguraci — kdyby "
            "kód obce ukazoval jinam, sběr spadne, místo aby tiše srovnával "
            "cizí čísla.",
        ],
        "obce": [
            {
                "ico": m["ico"],
                "kod_obce": m["kod_obce"],
                "nazev": m["nazev"],
                "nazev_ve_zdroji": nazvy_ve_zdroji.get(m["kod_obce"]),
                "po_letech": dict(sorted(po_obcich[m["kod_obce"]].items())),
            }
            for m in seznam
        ],
    })
    log.pricti()
    log.info("obyvatelé: uloženo pro "
             f"{sum(1 for k in po_obcich.values() if k)} z {len(seznam)} měst")


def main() -> int:
    ap = argparse.ArgumentParser(description="Srovnání hospodaření měst")
    ap.add_argument("--jen", choices=["fin", "obyvatele"])
    ap.add_argument("--ponechat-cache", action="store_true",
                    help="nemazat stažené extrakty (sdílí je scrapers/monitor.py)")
    args = ap.parse_args()

    log = Log("srovnani")
    try:
        seznam = mesta()
        if args.jen in (None, "fin"):
            sber_fin(seznam, log, args.ponechat_cache)
        if args.jen in (None, "obyvatele"):
            sber_obyvatel(seznam, log)
    except ZdrojSelhal as e:
        log.chyba(str(e))
        log.uzavri()
        return 1
    vysledek = log.uzavri()
    return 0 if vysledek["uspech"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
