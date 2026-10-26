"""Lhůty uveřejnění smluv v registru smluv (smlouvy.gov.cz).

Sklizeň přes Hlídač (`scrapers/hlidac_api.py`) má u smlouvy jen datum
uzavření. Jestli byla smlouva uveřejněna včas, se z toho nepozná — a právě
na tom stojí § 6 a § 7 zákona č. 340/2015 Sb.: smlouva nabývá účinnosti
nejdřív dnem uveřejnění a neuveřejněná do tří měsíců od uzavření je
zrušena od počátku.

Tenhle sběrač ke každé smlouvě z `data/penize/smlouvy/*.json` stáhne
stránku záznamu v registru a vytáhne z ní:

  * datum uzavření a datum PRVNÍHO uveřejnění (u smluv s více verzemi
    je rozhodné první uveřejnění, ne poslední oprava),
  * hodnotu bez DPH a s DPH (hranice povinnosti uveřejnit je 50 000 Kč
    bez DPH, § 3 odst. 2 písm. h),
  * ID smlouvy a verze, číslo verze, útvar a podepisující osobu.

Výstup: `data/penize/lhuty_zverejneni.json`
    { "zdroj": ..., "stazeno": "YYYY-MM-DD",
      "smlouvy": { "<id hlídače>": { "uzavreno": "YYYY-MM-DD",
                                      "prvni_zverejneni": "YYYY-MM-DD",
                                      "zverejneni_verze": "YYYY-MM-DD",
                                      "dnu": 240,          # od uzavření do prvního uveřejnění
                                      "hodnota_bez_dph": 6000000.0 | null,
                                      "hodnota_s_dph": 7260000.0 | null,
                                      "id_smlouvy": "19980327", "id_verze": "21469611",
                                      "verze": 1, "utvar": "...", "podepsal": "...",
                                      "url": "https://smlouvy.gov.cz/smlouva/21469611" } } }

Smlouva, jejíž stránka vrátí 404 nebo hlásí „verze smlouvy je znepřístupněna"
(na žádost subjektu), se uloží jako `{"nenalezeno": true, "znepristupneno": …}`
— chybějící záznam a chybějící datum nejsou totéž.

Zásady:
  * Hodnotí se jen to, co stránka říká. „dnu" je prostý rozdíl dat; co z něj
    plyne právně, rozhoduje čtenář s § 3, 6 a 7 v ruce, ne tenhle skript.
  * Běh je obnovitelný: už stažené smlouvy se znovu nestahují.
  * Nejvýš dva až tři požadavky za sekundu — registr je cizí infrastruktura.

Spuštění:
    python3 scrapers/registr_lhuty.py            # dotáhne, co chybí
    python3 scrapers/registr_lhuty.py --znovu    # stáhne všechno znovu

Sedm tisíc stránek po sekundě je dvě hodiny. Běh jde rozdělit na díly,
které běží vedle sebe a každý píše do vlastního souboru (odstup na
hostitele drží `lib.core.fetch` napříč procesy):
    python3 scrapers/registr_lhuty.py --cast 1/3 &
    python3 scrapers/registr_lhuty.py --cast 2/3 &
    python3 scrapers/registr_lhuty.py --cast 3/3 &
    wait; python3 scrapers/registr_lhuty.py --slouc   # díly → hlavní soubor
"""
from __future__ import annotations

import argparse
import glob
import html as html_modul
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import DATA, Log, ZdrojSelhal, fetch, nacti, uloz  # noqa: E402

VYSTUP = "penize/lhuty_zverejneni.json"
ZDROJ = "https://smlouvy.gov.cz/smlouva/{id}"

# <span class="name">Datum uzavření:</span><span class="value">01.01.2022</span>
RE_POLE = re.compile(
    r'<span class="name">\s*(.*?)\s*</span>\s*<span class="value">\s*(.*?)\s*</span>',
    re.S,
)
RE_DATUM = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


def _datum(text: str | None) -> str | None:
    if not text:
        return None
    m = RE_DATUM.search(text)
    if not m:
        return None
    d, mo, r = (int(x) for x in m.groups())
    try:
        return date(r, mo, d).isoformat()
    except ValueError:
        return None


def _castka(text: str | None) -> float | None:
    """„6 000 000,00 CZK" → 6000000.0; prázdné pole → None (ne nula)."""
    if not text:
        return None
    t = text.replace("\xa0", " ").replace(" ", "").replace("CZK", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def rozeber(stranka: str, url: str) -> dict:
    """Z HTML stránky záznamu vytáhne pole. Když chybí datum uzavření,
    stránka není záznam smlouvy — to je chyba, ne prázdný výsledek."""
    pole: dict[str, str] = {}
    for nazev, hodnota in RE_POLE.findall(stranka):
        # Útvar je zabalený v <abbr title="…">: bere se text uvnitř, ne title.
        nazev = html_modul.unescape(re.sub(r"<[^>]+>", "", nazev)).strip().rstrip(":").strip()
        hodnota = html_modul.unescape(re.sub(r"<[^>]+>", "", hodnota)).strip()
        # Útvar a plátce/příjemce se na stránce opakují (za každou stranu);
        # první výskyt patří zveřejňující straně.
        pole.setdefault(nazev, hodnota)

    uzavreno = _datum(pole.get("Datum uzavření"))
    prvni = _datum(pole.get("První zveřejnění"))
    if not uzavreno or not prvni:
        raise ZdrojSelhal(f"Stránka {url} neobsahuje datum uzavření/prvního zveřejnění")

    dnu = (date.fromisoformat(prvni) - date.fromisoformat(uzavreno)).days
    verze = pole.get("Verze smlouvy") or pole.get("Číslo verze")
    return {
        "uzavreno": uzavreno,
        "prvni_zverejneni": prvni,
        "zverejneni_verze": _datum(pole.get("Zveřejnění")),
        "dnu": dnu,
        "hodnota_bez_dph": _castka(pole.get("Hodnota bez DPH")),
        "hodnota_s_dph": _castka(pole.get("Hodnota vč. DPH")),
        "id_smlouvy": pole.get("ID smlouvy") or None,
        "id_verze": pole.get("ID verze") or None,
        "verze": int(verze) if verze and verze.isdigit() else None,
        "utvar": pole.get("Útvar / Odbor") or None,
        "podepsal": pole.get("Podepisující osoba") or None,
        "url": url,
    }


def _stahni(url: str) -> str | None:
    """HTML záznamu, nebo None při 404 (záznam znepřístupněn)."""
    try:
        return fetch(url, max_age=0)
    except ZdrojSelhal as e:
        if "404" in str(e):
            return None
        raise


def vsechny_smlouvy() -> list[dict]:
    out = []
    for soubor in sorted(glob.glob(str(DATA / "penize" / "smlouvy" / "*.json"))):
        d = nacti(Path(soubor))
        for s in d.get("smlouvy") or []:
            out.append({"id": s["id"], "url": s.get("url"), "ico": d["ico"]})
    return out


def _soubory_dilu() -> list[Path]:
    return sorted((DATA / "penize").glob("lhuty_zverejneni.cast*.json"))


def _nactene(soubor: str | Path) -> dict[str, dict]:
    return dict((nacti(soubor) or {}).get("smlouvy") or {})


def slouc(log: Log) -> None:
    """Díly z paralelního běhu přisype do hlavního souboru a smaže je."""
    hotovo = _nactene(VYSTUP)
    for dil in _soubory_dilu():
        cast = _nactene(dil)
        hotovo.update(cast)
        log.info("sloučen díl", soubor=dil.name, smluv=len(cast))
        dil.unlink()
    _uloz_vystup(VYSTUP, hotovo)
    log.info("sloučeno", celkem=len(hotovo))


def _uloz_vystup(cesta: str | Path, hotovo: dict[str, dict]) -> None:
    uloz(cesta, {
        "zdroj": "smlouvy.gov.cz — stránka záznamu smlouvy",
        "stazeno": datetime.now().strftime("%Y-%m-%d"),
        "poznamka": (
            "dnu = počet dní od data uzavření do PRVNÍHO uveřejnění. "
            "Hranice zákona: 30 dnů (§ 5 odst. 2, pořádková), 3 měsíce "
            "(§ 7 odst. 1, zrušení od počátku) — jen u smluv nad 50 000 Kč "
            "bez DPH uzavřených od 1. 7. 2017, které nespadají pod výjimky § 3."
        ),
        "smlouvy": hotovo,
    })


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--znovu", action="store_true", help="stáhnout všechno znovu")
    ap.add_argument("--limit", type=int, default=0, help="jen prvních N (ladění)")
    ap.add_argument("--cast", default="", metavar="K/N",
                    help="zpracovat jen K-tý díl z N (paralelní běh, vlastní výstup)")
    ap.add_argument("--slouc", action="store_true", help="sloučit díly do hlavního souboru")
    args = ap.parse_args()

    log = Log("registr_lhuty")
    if args.slouc:
        slouc(log)
        log.uzavri()
        return

    k, n = 1, 1
    vystup: str | Path = VYSTUP
    if args.cast:
        k, n = (int(x) for x in args.cast.split("/"))
        vystup = DATA / "penize" / f"lhuty_zverejneni.cast{k}.json"

    # Hotové = hlavní soubor + všechny díly (ať se díly nepřekrývají),
    # ale zapisuje se jen do vlastního výstupu.
    hotovo: dict[str, dict] = {}
    if not args.znovu:
        hotovo.update(_nactene(VYSTUP))
        for dil in _soubory_dilu():
            hotovo.update(_nactene(dil))
    vlastni: dict[str, dict] = _nactene(vystup) if not args.znovu else {}

    smlouvy = vsechny_smlouvy()
    videne: set[str] = set()
    zbyva = []
    for s in smlouvy:
        if s["id"] in hotovo or s["id"] in videne:
            continue
        videne.add(s["id"])
        zbyva.append(s)
    zbyva = zbyva[k - 1 :: n]
    if args.limit:
        zbyva = zbyva[: args.limit]
    log.info("smluv celkem", celkem=len(smlouvy), hotovo=len(hotovo), zbyva=len(zbyva), dil=args.cast or "vše")

    def uloz_prubezne() -> None:
        _uloz_vystup(vystup, vlastni)


    chyb_za_sebou = 0
    for i, s in enumerate(zbyva, 1):
        sid = s["id"]
        # Hlídač vrací odkaz na konkrétní verzi; když verze už není, zkusí se ID.
        kandidati = [u for u in (s.get("url"), ZDROJ.format(id=sid)) if u]
        kandidati = list(dict.fromkeys(kandidati))
        zaznam: dict | None = None
        znepristupneno = False
        try:
            for url in kandidati:
                stranka = _stahni(url)
                if stranka is None:
                    continue
                # „Na žádost subjektu byla tato verze smlouvy znepřístupněna."
                # Stránka existuje, ale bez dat — zkusí se další kandidát.
                if "znepřístupněna" in stranka:
                    znepristupneno = True
                    continue
                zaznam = rozeber(stranka, url)
                break
            if zaznam is None:
                zaznam = {"nenalezeno": True, "znepristupneno": znepristupneno, "zkouseno": kandidati}
            vlastni[sid] = zaznam
            chyb_za_sebou = 0
            log.pricti()
        except ZdrojSelhal as e:
            chyb_za_sebou += 1
            log.chyba(f"{sid}: {e}")
            if chyb_za_sebou >= 10:
                log.chyba("10 chyb za sebou — zdroj zřejmě nefunguje, končím")
                break
        if i % 100 == 0:
            uloz_prubezne()
            log.info("průběžně uloženo", hotovo=len(hotovo) + len(vlastni), z=len(smlouvy))
        time.sleep(0.1)  # k tomu odstup 0,3 s na hostitele z lib.core.fetch

    uloz_prubezne()
    log.uzavri()


if __name__ == "__main__":
    main()
