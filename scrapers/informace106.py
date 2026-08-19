"""Poskytnuté informace podle zákona 106/1999 Sb.

PROČ TO STOJÍ ZA SBĚR
---------------------
Úřad má povinnost zveřejnit, na co se ho někdo zeptal a co odpověděl.
Je to jediné místo, kde se dá zjistit, **co lidi o městě zajímá natolik,
že si o to museli napsat** — a co jim úřad odmítl dát.

Zveřejněná odpověď má pravidelnou stavbu:

    Žádost: č.j. MUML/2026/27606, vedená pod spis. zn. S-MUML/2026/3787
    Předmět žádosti:
    Informace týkající se správních řízení vedených u stavebního úřadu…
    Poskytnuté informace:
    V návaznosti na žádost byly žadateli zaslány informace dne 29.07.2026…
    Informace poskytla:
    Magdalena Dicková, referent - stavební úřad

Z toho jde vyčíst téma dotazu, který odbor odpovídal a kdy. Rozbor textu
dělá `pipeline/informace106_prehled.py`; tenhle modul jen stahuje.

ŽADATEL SE NEZVEŘEJŇUJE. Texty odpovědí ho neuvádějí (ověřeno na všech
98 stažených), ale starší záznamy ho mají v NÁZVU: „žádost ze dne
06.09.2016 Jiří Škroch". Jméno fyzické osoby se proto odstraňuje už při
sběru — ne až při zobrazení, protože repozitář projektu je veřejný.

Ptát se úřadu je zákonné právo a přehled z jeho výkonu nedělá veřejnou
stopu. Zajímavé je, NA CO se někdo ptal. Názvy organizací zůstávají:
žádost spolku, komory nebo advokátní kanceláře je jednání instituce.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import DATA, Log, ZdrojSelhal, fetch, pdf_na_text, potrebuje_ocr, uloz  # noqa: E402
from lib.dokumenty import (  # noqa: E402
    ZAKLAD,
    cesta_ke_stazenemu,
    klic_dokumentu,
    sklid_rejstrik,
)

REJSTRIK = f"{ZAKLAD}/urad/dokumenty/poskytnute-informace-106-1999-sb/"

# ── Jméno žadatele ──────────────────────────────────────────────────────
# Starší záznamy mají žadatele přímo v názvu: „žádost ze dne 06.09.2016
# Jiří Škroch". Novější ne — jmenují se „Žádost podle § 106 id MUMLX…".
# Ověřeno na celé sklizni: ze 127 dokumentů má jméno v názvu 20 a v textu
# samotných odpovědí není žadatel uvedený ani jednou.
#
# ROZHODNUTÍ: jméno fyzické osoby se NEUKLÁDÁ ani nezveřejňuje. Ptát se
# úřadu je zákonné právo a přehled z jeho výkonu nedělá veřejnou stopu.
# Zajímavé je, NA CO se někdo ptal, ne kdo to byl. Město to zveřejňuje;
# tenhle projekt to dál nešíří — repozitář je veřejný a agregovaný
# seznam se hledá líp než jednotlivá stránka úřadu.
#
# Organizace se ponechávají. Žádost spolku, advokátní kanceláře nebo
# komory je jednání instituce, ne soukromá věc, a bývá to podstatná část
# příběhu („Oživení se ptalo na…").
_DATUM_V_NAZVU = re.compile(r"(?i)^\s*žádost\s+ze\s+dne\s+(\d{1,2}\.\d{1,2}\.\d{4})\s*(?P<kdo>.*)$")

# POZOR NA VOLNÉ ZKRATKY. První verze měla mezi vzory `a\.?\s?s\b`, tedy
# „as" s nepovinnou tečkou — a trefila se do konce příjmení „Pavlas".
# Jméno fyzické osoby tak prošlo jako organizace a zůstalo v datech.
# Zkratky proto MUSÍ mít tečku a stát samostatně; holé „as", „zs", „sro"
# se nepoznají od kusu slova.
_ORGANIZACE = re.compile(
    r"(?i)(?:"
    r"\bs\.\s?r\.\s?o\b|\bspol\.\s*s\s*r\.\s?o\b|\ba\.\s?s\.|"
    r"\bz\.\s?s\b|\bo\.\s?p\.\s?s\b|\bp\.\s?o\b|"
    r"advok|komor[ay]|sdružen|spolek|spolku|institut|společnost|úřad|"
    r"ministerstv|kancelář|redakce|deník|noviny|oživení|transparen|nadac"
    r")"
)


# Název bez data, ale se jménem: „žádost podle § 106 Roman Míka".
_NAZEV_SE_JMENEM = re.compile(
    r"(?i)^\s*(?P<hlava>žádost(?:\s+podle)?\s*(?:§\s*106|dle\s*§\s*106)?)\s*"
    r"(?P<kdo>[^\n]{2,80})$"
)

# Řádek, na kterém bývá žadatel: „Žádost: č.j. FIN/22/5933/LP – paní Renata Jokl".
# Číslo jednací se ponechá, jméno za pomlčkou ne.
_RADEK_ZADOSTI = re.compile(
    r"(?im)^(?P<hlava>\s*žádost\s*:?[^\n]*?č\.\s?j\.[^\n–—-]{0,60})"
    r"\s*[–—-]\s*(?P<kdo>[^\n]{2,90})$"
)

_OSLOVENI = re.compile(r"(?i)\b(pan[íu]?)\s+(?:[A-ZÁ-Ž][\wá-žÁ-Ž]+\s+){1,2}[A-ZÁ-Ž][\wá-žÁ-Ž]+")


# Jméno fyzické osoby, případně s akademickými tituly:
# „JUDr. Ing. Pavel Cink, LL.M., MBA – advokát". Slovo „advokát" u něj
# neznamená firmu — je to člověk vykonávající profesi, a jeho jméno do
# přehledu nepatří o nic víc než jméno kohokoliv jiného.
_JE_OSOBA = re.compile(
    r"(?i)^\s*(?:(?:JUDr|Ing|Mgr|Bc|MUDr|MVDr|PhDr|RNDr|PaedDr|doc|prof)\.\s*)*"
    r"[A-ZÁ-Ž][a-zá-ž]+\s+(?:[A-ZÁ-Ž][a-zá-ž]+\s+)?[A-ZÁ-Ž][a-zá-ž]+\b"
)

# Právní forma je jediný spolehlivý znak firmy. Ostatní slova („advokát",
# „komora") mohou stát i u člověka, proto rozhodují až po vyloučení osoby.
_PRAVNI_FORMA = re.compile(
    r"(?i)\bs\.\s?r\.\s?o\b|\bspol\.\s*s\s*r\.\s?o\b|\ba\.\s?s\.|"
    r"\bz\.\s?s\b|\bo\.\s?p\.\s?s\b|\bp\.\s?o\b"
)


def _je_organizace(kdo: str) -> bool:
    kdo = (kdo or "").strip()
    if _PRAVNI_FORMA.search(kdo):
        return True
    # Vypadá to jako jméno člověka? Pak to člověk je, i když má u sebe
    # profesi. Jinak rozhodne slovník institucí.
    if _JE_OSOBA.match(kdo):
        return False
    return bool(_ORGANIZACE.search(kdo))


def anonymizuj_text(text: str) -> tuple[str, int]:
    """Odstraní z textu jméno žadatele. Vrací (text, kolikrát zasaženo).

    NEHLEDÁ jména obecně — to by nešlo spolehlivě a mazalo by to i úředníky,
    kteří informaci poskytli (ti se uvádět mají, je to výkon funkce).
    Zasahuje jen dvě místa, kde žadatel v těchhle dokumentech stojí:
    za pomlčkou na řádku „Žádost: č.j. …" a v oslovení „paní Jméno Příjmení".

    Organizace zůstávají.
    """
    zasahu = 0

    def nahrad_radek(m: "re.Match[str]") -> str:
        nonlocal zasahu
        kdo = m.group("kdo").strip()
        if _je_organizace(kdo):
            return m.group(0)
        zasahu += 1
        return f"{m.group('hlava').rstrip()} — žadatel neuveden"

    text = _RADEK_ZADOSTI.sub(nahrad_radek, text)

    def nahrad_osloveni(m: "re.Match[str]") -> str:
        nonlocal zasahu
        zasahu += 1
        return f"{m.group(1)} (jméno neuvedeno)"

    text = _OSLOVENI.sub(nahrad_osloveni, text)
    return text, zasahu


def verejny_nadpis(nadpis: str) -> tuple[str, bool]:
    """Název dokumentu bez jména fyzické osoby.

    Vrací (název, bylo_odstraněno_jméno).
    """
    m = _DATUM_V_NAZVU.match(nadpis or "")
    if m:
        kdo = (m.group("kdo") or "").strip(" ,;-")
        if not kdo:
            return nadpis.strip(), False
        if _je_organizace(kdo):
            return f"žádost ze dne {m.group(1)} — {kdo}", False
        return f"žádost ze dne {m.group(1)}", True

    # Druhý formát: „žádost podle § 106 Roman Míka" — bez data.
    # Identifikátory („id MUMLX…", „e.č. ML-…") nejsou jména a zůstávají.
    m2 = _NAZEV_SE_JMENEM.match(nadpis or "")
    if m2:
        kdo = (m2.group("kdo") or "").strip(" ,;-")
        if not kdo or re.match(r"(?i)^(id|e\.?\s?č\.?|č\.\s?j\.)\b", kdo) or _je_organizace(kdo):
            return nadpis.strip(), False
        return m2.group("hlava").strip(), True

    return nadpis, False


def stahni_texty(dokumenty: list[dict], log: Log) -> tuple[int, int]:
    """Stáhne PDF a uloží text. Vrací (nových, bez textu)."""
    novych = 0
    bez_textu = 0
    for d in dokumenty:
        cil = Path("informace106/texty") / f"{klic_dokumentu(d)}.json"
        if (DATA / cil).exists():
            continue

        pdf = cesta_ke_stazenemu(d, "informace106")
        try:
            if not pdf.exists():
                data = fetch(d["url"], cache_key=f"i106-{pdf.stem}", max_age=0, binary=True)
                assert isinstance(data, bytes)
                pdf.parent.mkdir(parents=True, exist_ok=True)
                pdf.write_bytes(data)
            text = pdf_na_text(pdf)
        except ZdrojSelhal as e:
            log.chyba(f"{d['nadpis']}: {e}")
            bez_textu += 1
            continue

        stran = text.count("\f") + 1
        if potrebuje_ocr(text, stran):
            # Sken bez textové vrstvy. Prázdný text by vypadal jako
            # odpověď bez obsahu.
            log.chyba(f"{d['nadpis']}: PDF nemá textovou vrstvu (potřeboval by OCR)")
            bez_textu += 1
            continue

        # Anonymizace PŘED uložením — text jde do repozitáře, který je veřejný.
        text, zasahu = anonymizuj_text(text)
        uloz(cil, {**d, "stran": stran, "text": text, "zadatel_skryt_v_textu": zasahu})
        novych += 1
    return novych, bez_textu


def main() -> None:
    log = Log("informace106")

    dokumenty = sklid_rejstrik(REJSTRIK, "i106", log)
    dokumenty.sort(key=lambda d: (d["vlozeno"] or ""), reverse=True)

    # Jména fyzických osob se odstraní JEŠTĚ PŘED uložením. Kdyby se
    # ukládala a schovávala se až na webu, ležela by v repozitáři, který
    # je veřejný.
    anonymizovano = 0
    for d in dokumenty:
        nazev, upraveno = verejny_nadpis(d["nadpis"])
        d["nadpis"] = nazev
        d["zadatel_odstranen"] = upraveno
        # Název souboru nese jméno taky („žádost … Jiří Škroch.pdf").
        if upraveno:
            d["soubor"] = None
        anonymizovano += 1 if upraveno else 0

    uloz("informace106/rejstrik.json", {
        "zdroj": [REJSTRIK],
        "metodika": {
            "co_to_je": (
                "Rejstřík informací poskytnutých podle zákona 106/1999 Sb., "
                "jak je zveřejňuje web města."
            ),
            "zadatel": (
                "Jméno fyzické osoby se neukládá ani nezveřejňuje, i když ho web města "
                "u starších záznamů uvádí v názvu. Ptát se úřadu je zákonné právo a "
                "přehled z jeho výkonu nedělá veřejnou stopu; zajímavé je, NA CO se "
                "někdo ptal. Odstraňuje se už při sběru, ne až při zobrazení — "
                "repozitář projektu je veřejný. Názvy organizací (spolek, advokátní "
                "kancelář, komora) zůstávají: žádost instituce je jednání instituce."
            ),
            "anonymizovano": anonymizovano,
            "stazeno": "Počet stažení uvádí web města. Je to údaj o zájmu, ne o obsahu.",
            "prazdno": (
                "Prázdný rejstřík se neuloží. Když stránka nevrátí ani jednu položku, "
                "sběrač spadne — „žádné žádosti nebyly“ je jiné tvrzení než „nepodařilo se“."
            ),
        },
        "celkem": len(dokumenty),
        "dokumenty": dokumenty,
    })

    novych, bez_textu = stahni_texty(dokumenty, log)
    log.pricti(novych)
    log.info("odpovědí s novým textem", pocet=novych)
    if anonymizovano:
        log.info("záznamů se skrytým jménem žadatele", pocet=anonymizovano)
    if bez_textu:
        log.info("dokumentů bez textové vrstvy", pocet=bez_textu)
    log.uzavri()


if __name__ == "__main__":
    main()
