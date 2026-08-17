"""Přepisy jednání zastupitelstva do prohledávatelné podoby.

Cíl: aby šlo hledat v tom, co na zastupitelstvu skutečně zaznělo, a z
výsledku skočit rovnou na tu vteřinu videa.

Postup je odstupňovaný podle ceny:
  1. automatické titulky z YouTube — hotové, zdarma, stačí stáhnout
  2. Whisper — až když titulky nejsou; 350 hodin záznamů je hodně strojového času

Rozpoznání řečníka je záměrně skromné. Diarizace by vyžadovala další model
a stejně nezná jména; předsedající ale mluvčí zpravidla vyvolává ("slovo má
pan zastupitel Novák"), takže se jména dají zachytit z textu. Kde si skript
jistý není, řečníka nechá prázdného — vymyšlené jméno u výroku by bylo horší
než žádné.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import DATA, Log, cistit, nacti, slug, uloz  # noqa: E402

# Segmenty kratší než tohle se slučují — jednotlivé řádky titulků jsou
# pro vyhledávání příliš krátké a bez kontextu.
MIN_ZNAKU = 400


def vtt_na_segmenty(cesta: Path) -> list[dict]:
    """Rozparsuje VTT titulky na segmenty s časem v sekundách."""
    text = cesta.read_text(encoding="utf-8", errors="replace")
    segmenty: list[dict] = []
    cas_re = re.compile(
        r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[.,](\d{3})"
    )

    aktualni: dict | None = None
    for radek in text.splitlines():
        m = cas_re.search(radek)
        if m:
            h1, m1, s1, _, h2, m2, s2, _ = (int(g) for g in m.groups())
            if aktualni:
                segmenty.append(aktualni)
            aktualni = {
                "od": h1 * 3600 + m1 * 60 + s1,
                "do": h2 * 3600 + m2 * 60 + s2,
                "text": "",
            }
            continue
        if aktualni is None:
            continue
        radek = radek.strip()
        if not radek or radek.startswith(("WEBVTT", "NOTE", "Kind:", "Language:")):
            continue
        # YouTube do automatických titulků cpe inline časování a zvýraznění
        radek = re.sub(r"<[^>]+>", "", radek)
        if radek and radek not in aktualni["text"]:
            aktualni["text"] = (aktualni["text"] + " " + radek).strip()

    if aktualni:
        segmenty.append(aktualni)

    # Automatické titulky opakují konec předchozího řádku na začátku dalšího.
    ocistene = []
    for s in segmenty:
        t = cistit(s["text"])
        if not t:
            continue
        if ocistene and ocistene[-1]["text"].endswith(t):
            continue
        s["text"] = t
        ocistene.append(s)
    return ocistene


def sluc(segmenty: list[dict], min_znaku: int = MIN_ZNAKU) -> list[dict]:
    """Sloučí drobné segmenty do odstavců vhodných pro vyhledávání.

    Slučuje POUZE v rámci jednoho řečníka. Kdyby slučování přeskočilo přes
    změnu mluvčího, slila by se do jednoho bloku řeč dvou lidí a přiřazení
    výroku by přestalo platit — což je horší než dlouhý blok.
    """
    bloky: list[dict] = []
    buffer: dict | None = None

    for s in segmenty:
        zmena_recnika = buffer is not None and s.get("recnik_id") != buffer.get("recnik_id")

        if buffer is not None and (zmena_recnika or len(buffer["text"]) >= min_znaku):
            bloky.append(buffer)
            buffer = None

        if buffer is None:
            buffer = {
                "od": s["od"], "do": s["do"], "text": s["text"],
                "recnik_id": s.get("recnik_id"), "recnik": s.get("recnik"),
                "recnik_jistota": s.get("recnik_jistota"),
            }
        else:
            buffer["text"] = f"{buffer['text']} {s['text']}".strip()
            buffer["do"] = s["do"]

    if buffer and buffer["text"]:
        bloky.append(buffer)
    return bloky


def _bez_diakritiky(t: str) -> str:
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def priradit_recniky(bloky: list[dict], osoby: list[dict]) -> list[dict]:
    """Pokusí se k blokům přiřadit řečníka podle vyvolání předsedajícím.

    Hledá obraty typu "slovo má pan Novák", "děkuji, paní Nováková",
    "prosím pana zastupitele Nováka". Jakmile někoho najde, drží ho jako
    aktuálního řečníka, dokud nepřijde jiné vyvolání.

    Zásadní: co se nepodaří určit, zůstane `null`. Přiřadit výrok
    nesprávnému zastupiteli by bylo mnohem horší než ho nepřiřadit.
    """
    prijmeni: dict[str, dict] = {}
    for o in osoby:
        cele = o.get("jmeno", "")
        casti = cele.split()
        if len(casti) >= 2:
            prijmeni[_bez_diakritiky(casti[-1])] = o

    # Čeština skloňuje všechno včetně oslovení: "pana zastupitele Kalinu",
    # "paní zastupitelku Míkovou". Vzor proto musí připustit koncovky
    # u oslovení i u titulu, ne jen základní tvar.
    # Spouštěč i oslovení ignorují velikost písmen — věta začíná "Prosím"
    # nebo "Slovo má" s velkým písmenem. Samotné příjmení ale velikost
    # rozlišovat MUSÍ, jinak by se chytalo každé slovo ve větě.
    vzor = re.compile(
        r"(?i:slovo m[áa]|prosím|d[ěe]kuji|dávám slovo|hlásí se|vystoupí|udílím slovo)\s+"
        r"(?i:pan[aiouíě]?\s+)?"
        r"(?i:zastupitel\w*\s+|starost\w+\s+|místostarost\w+\s+|radn\w+\s+|"
        r"inženýr\w*\s+|doktor\w*\s+|magistr\w*\s+|architekt\w*\s+)?"
        r"([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][\wáčďéěíňóřšťúůýž]{2,})",
        re.UNICODE,
    )

    def _dohledej(kandidat: str) -> dict | None:
        k = _bez_diakritiky(kandidat)
        # Skloňování příjmení: "Kalinu"->"Kalina", "Míkovou"->"Míková",
        # "Nováka"->"Novák". Zkoušíme osekávání i doplnění typicky ženských
        # koncovek, protože přechýlená příjmení se skloňují jinak.
        varianty = [k, k[:-1], k[:-2], k[:-3]]
        if k.endswith(("ovou", "ove", "ovy")):
            varianty.append(k[:-3] + "a")   # mikovou -> mikova
        if k.endswith("u"):
            varianty.append(k[:-1] + "a")   # kalinu -> kalina
        for v in varianty:
            if v and v in prijmeni:
                return prijmeni[v]
        return None

    aktualni: dict | None = None
    for b in bloky:
        for m in vzor.finditer(b["text"]):
            nalezen = _dohledej(m.group(1))
            if nalezen:
                aktualni = nalezen

        b["recnik_id"] = aktualni["id"] if aktualni else None
        b["recnik"] = aktualni["jmeno"] if aktualni else None
        b["recnik_jistota"] = "vyvolani" if aktualni else None

    return bloky


def zpracuj_zaznam(zaznam: dict, vtt: Path, osoby: list[dict]) -> dict:
    segmenty = vtt_na_segmenty(vtt)
    if not segmenty:
        raise ValueError(f"z {vtt.name} nevznikly žádné segmenty")

    # Pořadí je podstatné: řečníky přiřazujeme na jednotlivé segmenty a
    # teprve pak slučujeme, aby slučování nepřeskočilo přes změnu mluvčího.
    bloky = sluc(priradit_recniky(segmenty, osoby), MIN_ZNAKU)
    vid = zaznam["video_id"]

    for i, b in enumerate(bloky):
        b["id"] = f"{vid}-{i:04d}"
        # Odkaz rovnou na tu vteřinu videa — tohle je pointa celé funkce.
        b["odkaz"] = f"https://www.youtube.com/watch?v={vid}&t={b['od']}s"
        b["cas"] = f"{b['od'] // 3600:d}:{(b['od'] % 3600) // 60:02d}:{b['od'] % 60:02d}"

    return {
        "video_id": vid,
        "nazev": zaznam.get("nazev"),
        "datum": zaznam.get("datum"),
        "cj": zaznam.get("cj"),
        "url": zaznam.get("url"),
        "usneseni": zaznam.get("usneseni"),
        "bloku": len(bloky),
        "znaku": sum(len(b["text"]) for b in bloky),
        "bloky": bloky,
    }


def main() -> None:
    log = Log("prepis")
    zaznamy = nacti("zaznamy/index.json", [])
    if not zaznamy:
        log.chyba("chybí data/zaznamy/index.json — spusť nejdřív scrapers/zaznamy.py")
        log.uzavri()
        raise SystemExit(2)

    osoby = nacti("lide/osobnosti.json", []) or []
    titulky_dir = DATA / "zaznamy" / "titulky"
    hotovo = 0

    for z in zaznamy:
        vtt_soubory = sorted(titulky_dir.glob(f"{z['video_id']}*.vtt"))
        if not vtt_soubory:
            log.info("bez titulků, přeskočeno", video=z["video_id"])
            continue
        try:
            vysledek = zpracuj_zaznam(z, vtt_soubory[0], osoby)
        except Exception as e:  # noqa: BLE001
            log.chyba(f"{z['video_id']}: {e}")
            continue

        uloz(f"zaznamy/prepisy/{z['datum'] or z['video_id']}.json", vysledek)
        log.pricti()
        hotovo += 1

    log.info("přepsáno jednání", pocet=hotovo)
    log.uzavri()


if __name__ == "__main__":
    main()
