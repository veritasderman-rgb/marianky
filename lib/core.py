"""Sdílené jádro pro všechny sběrače.

ZÁSADA PROJEKTU: scraping dělá kód, porozumění dělá Claude.
Tento modul je ta "kódová" půlka — je deterministický a když zdroj selže,
vyhodí chybu. Nikdy nevrací prázdná data tvářící se jako úspěch.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import unicodedata
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = ROOT / ".cache"
CONFIG = ROOT / "config"

# usneseni.muml.cz vrací 503 bez User-Agent. Ověřeno 17. 8. 2026.
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


class ZdrojSelhal(Exception):
    """Zdroj se nepodařilo načíst. Vždy bublá nahoru — nikdy se nepolyká."""


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def fetch(
    url: str,
    *,
    cache_key: str | None = None,
    max_age: int = 86_400,
    timeout: int = 60,
    retries: int = 4,
    binary: bool = False,
    referer: str | None = None,
) -> bytes | str:
    """Stáhne URL s opakováním a diskovou cache.

    Cache šetří opakované běhy: dávkové zpracování 122 čísel zpravodaje
    nebo 94 zápisů se nesmí při každém spuštění stahovat znovu.
    Nastav max_age=0 pro vynucení čerstvého stažení.
    """
    key = cache_key or hashlib.sha256(url.encode()).hexdigest()[:24]
    path = CACHE / ("bin" if binary else "txt") / f"{key}{'.bin' if binary else '.txt'}"

    if max_age and path.exists() and (time.time() - path.stat().st_mtime) < max_age:
        return path.read_bytes() if binary else path.read_text(encoding="utf-8")

    headers = {"User-Agent": UA, "Accept-Language": "cs,en;q=0.8"}
    if referer:
        headers["Referer"] = referer

    last: Exception | None = None
    for pokus in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 429 or 500 <= r.status_code < 600:
                raise ZdrojSelhal(f"HTTP {r.status_code} u {url}")
            r.raise_for_status()
            data = r.content if binary else r.text
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data if binary else data.encode("utf-8"))
            return data
        except Exception as e:  # noqa: BLE001 — chceme opakovat na čemkoliv síťovém
            last = e
            if pokus < retries - 1:
                time.sleep(2 ** (pokus + 1))

    raise ZdrojSelhal(f"Nepodařilo se stáhnout {url} ani na {retries} pokusů: {last}")


# --------------------------------------------------------------------------
# Ukládání
# --------------------------------------------------------------------------

def uloz(rel_path: str | Path, obj: Any) -> Path:
    """Atomicky uloží JSON do data/. Vrací výslednou cestu."""
    path = DATA / rel_path if not Path(rel_path).is_absolute() else Path(rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(_serializovatelne(obj), ensure_ascii=False, indent=2, sort_keys=False),
        encoding="utf-8",
    )
    tmp.replace(path)  # atomický přesun — nikdy nezůstane rozepsaný soubor
    return path


def nacti(rel_path: str | Path, default: Any = None) -> Any:
    path = DATA / rel_path if not Path(rel_path).is_absolute() else Path(rel_path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def nacti_config(nazev: str) -> Any:
    return json.loads((CONFIG / nazev).read_text(encoding="utf-8"))


def _serializovatelne(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return _serializovatelne(asdict(obj))
    if isinstance(obj, dict):
        return {k: _serializovatelne(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serializovatelne(v) for v in obj]
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    return obj


# --------------------------------------------------------------------------
# Log běhu
# --------------------------------------------------------------------------

class Log:
    """Log jednoho běhu sběrače.

    Rozlišuje "nic nepřibylo" od "nepodařilo se načíst" — to je rozdíl,
    na kterém stojí důvěryhodnost celého webu.
    """

    def __init__(self, jmeno: str):
        self.jmeno = jmeno
        self.zacatek = datetime.now(timezone.utc)
        self.polozky: list[dict] = []
        self.chyby: list[str] = []
        self.novych = 0

    def info(self, zprava: str, **kv: Any) -> None:
        print(f"  [{self.jmeno}] {zprava}" + (f" {kv}" if kv else ""), flush=True)
        self.polozky.append({"zprava": zprava, **kv})

    def chyba(self, zprava: str) -> None:
        print(f"  [{self.jmeno}] CHYBA: {zprava}", flush=True)
        self.chyby.append(zprava)

    def pricti(self, n: int = 1) -> None:
        self.novych += n

    def uzavri(self) -> dict:
        vysledek = {
            "sberac": self.jmeno,
            "zacatek": self.zacatek.isoformat(),
            "konec": datetime.now(timezone.utc).isoformat(),
            "trvani_s": round((datetime.now(timezone.utc) - self.zacatek).total_seconds(), 1),
            "novych_polozek": self.novych,
            "uspech": not self.chyby,
            "chyby": self.chyby,
        }
        den = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        uloz(f"logy/{den}/{self.jmeno}.json", vysledek)
        stav = "OK" if vysledek["uspech"] else f"SELHALO ({len(self.chyby)} chyb)"
        print(f"[{self.jmeno}] {stav}, nových: {self.novych}, {vysledek['trvani_s']}s", flush=True)
        return vysledek


# --------------------------------------------------------------------------
# Pomocníci
# --------------------------------------------------------------------------

def slug(text: str, max_len: int = 80) -> str:
    """Diakritika pryč, mezery na pomlčky. Pro názvy souborů a URL."""
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:max_len] or "bez-nazvu"


CZ_MESICE = {
    "leden": 1, "unor": 2, "brezen": 3, "duben": 4, "kveten": 5, "cerven": 6,
    "cervenec": 7, "srpen": 8, "zari": 9, "rijen": 10, "listopad": 11, "prosinec": 12,
}


def parse_datum(text: str) -> str | None:
    """Vytáhne z textu první české datum a vrátí ho jako ISO (YYYY-MM-DD).

    Zvládá '7.8.2026', '07. 08. 2026' i '17.9.2024'.
    """
    m = re.search(r"(\d{1,2})\s*\.\s*(\d{1,2})\s*\.\s*(\d{4})", text or "")
    if not m:
        return None
    d, mo, y = (int(g) for g in m.groups())
    try:
        return datetime(y, mo, d).strftime("%Y-%m-%d")
    except ValueError:
        return None


def pdf_na_text(pdf: Path, *, prvni: int | None = None, posledni: int | None = None) -> str:
    """Extrahuje text z PDF.

    POZOR: záměrně BEZ přepínače -layout. Ověřeno na zpravodaji 8/2026:
    s -layout se dvousloupcová sazba prolíná a text nelze číst souvisle,
    zatímco výchozí režim dá správné pořadí čtení a sám spojí slova
    rozdělená na konci řádku.
    """
    cmd = ["pdftotext", "-enc", "UTF-8"]
    if prvni:
        cmd += ["-f", str(prvni)]
    if posledni:
        cmd += ["-l", str(posledni)]
    cmd += [str(pdf), "-"]
    r = subprocess.run(cmd, capture_output=True, timeout=600)
    if r.returncode != 0:
        raise ZdrojSelhal(f"pdftotext selhal na {pdf.name}: {r.stderr.decode()[:200]}")
    return r.stdout.decode("utf-8", errors="replace")


def pdf_pocet_stran(pdf: Path) -> int:
    r = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, timeout=120)
    m = re.search(rb"Pages:\s+(\d+)", r.stdout)
    return int(m.group(1)) if m else 0


def potrebuje_ocr(text: str, stran: int, prah: int = 200) -> bool:
    """Rozhodne, jestli má PDF tak řídkou textovou vrstvu, že jde nejspíš o sken.

    Aktuální čísla zpravodaje jdou z InDesignu a textovou vrstvu mají,
    ale starší ročníky mohou být skenované.
    """
    if stran <= 0:
        return True
    return (len(text) / stran) < prah


def cistit(text: str) -> str:
    """Sjednotí bílé znaky, ale zachová odstavce."""
    text = (text or "").replace("\xa0", " ").replace("​", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def davky(polozky: Iterable, velikost: int):
    """Rozdělí iterable na dávky dané velikosti."""
    davka = []
    for p in polozky:
        davka.append(p)
        if len(davka) >= velikost:
            yield davka
            davka = []
    if davka:
        yield davka


def sledovane_subjekty(vcetne_mimo_mesto: bool = True) -> list[dict]:
    """Subjekty k monitoringu. Nemocnice už městu nepatří — je označená
    vlastnictvi='mimo_mesto' a do součtů městského holdingu se nepočítá,
    ale sledujeme ji dál kvůli významu pro město."""
    cfg = nacti_config("subjekty.json")
    out = [s for s in cfg["subjekty"] if s.get("sledovat") and s.get("ico")]
    if not vcetne_mimo_mesto:
        out = [s for s in out if s.get("vlastnictvi") != "mimo_mesto"]
    return out


def platne_tagy() -> set[str]:
    return {t["id"] for t in nacti_config("tagy.json")["tagy"]}
