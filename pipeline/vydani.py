"""Sestavení týdenního vydání.

Vezme, co se za období nasbíralo, a složí z toho jedno číslo.

Nejdůležitější vlastnost celého modulu: každá sekce nese `stav`, který
rozlišuje tři různé věci, jež by jinak vypadaly stejně — jako prázdná
sekce:

    ok        — data se načetla a něco v období bylo
    prazdno   — data se načetla a v období opravdu nic nebylo
    chybi     — zdroj nebyl k dispozici, o období nevíme nic
    zastarale — data sice jsou, ale končí dávno před sledovaným obdobím

Kdyby se „nic se nedělo" slilo s „nepodařilo se načíst", přehled by tiše
lhal právě v tom týdnu, kdy by na tom nejvíc záleželo. Web má u stavu
`chybi` napsat, že data chybí, ne mlčet.

Stav `zastarale` vznikl z konkrétní chyby: sběrač úřední desky natáhl jen
archiv končící v květnu 2025, takže sekce ve vydání za srpen 2026 vyšla
prázdná. Vypadalo to, že město nic nevyvěsilo — přitom jsme jen měli
patnáct měsíců stará data. Prázdná sekce z prázdného zdroje a prázdná
sekce ze zastaralého zdroje jsou dvě různé zprávy.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import DATA, Log, nacti, uloz  # noqa: E402

NAZEV = "Naše Mariánky v přehledech"

# Nad touto částkou se bod usnesení zvýrazňuje jako významný.
VYZNAMNA_CASTKA = 1_000_000


class Sekce:
    def __init__(self, id_: str, nadpis: str, popis: str = ""):
        self.id = id_
        self.nadpis = nadpis
        self.popis = popis
        self.polozky: list[dict] = []
        self.stav = "prazdno"
        self.poznamka = ""
        self.nejnovejsi: str | None = None

    def chybi(self, duvod: str) -> "Sekce":
        self.stav = "chybi"
        self.poznamka = duvod
        return self

    def dopln(self, polozky: list[dict], nejnovejsi: str | None = None,
              obdobi_do: str | None = None, tolerance_dni: int = 30) -> "Sekce":
        """`nejnovejsi` je nejmladší datum v celém zdroji, ne jen v období.

        Zastaralost se poměřuje TOLERANCÍ, ne začátkem období. Rada zasedá
        jednou za dva týdny, takže týden bez usnesení je normální stav, ne
        výpadek — kdyby se hlídalo jen "zdroj nesahá do období", hlásilo by
        se zastaralé skoro každý druhý týden a upozornění by zesládlo.
        Tolerance proto odpovídá tomu, jak často se zdroj reálně mění.
        """
        self.polozky = polozky
        hranice = None
        if nejnovejsi and obdobi_do:
            hranice = (date.fromisoformat(obdobi_do) - timedelta(days=tolerance_dni)).isoformat()
        if polozky:
            self.stav = "ok"
        elif hranice and nejnovejsi < hranice:
            self.stav = "zastarale"
            self.poznamka = (
                f"Zdroj obsahuje data jen do {nejnovejsi}. Že je sekce prázdná, "
                f"neznamená, že se nic nedělo — o tomto období nemáme data."
            )
        else:
            self.stav = "prazdno"
        self.nejnovejsi = nejnovejsi
        return self

    def json(self) -> dict:
        return {
            "id": self.id,
            "nadpis": self.nadpis,
            "popis": self.popis,
            "stav": self.stav,
            "poznamka": self.poznamka,
            "nejnovejsi_ve_zdroji": self.nejnovejsi,
            "pocet": len(self.polozky),
            "polozky": self.polozky,
        }


def _v_obdobi(datum: str | None, od: str, do: str) -> bool:
    return bool(datum) and od <= datum[:10] <= do


def _otisk_smlouvy(sml: dict) -> tuple:
    """Otisk pro rozpoznání téže smlouvy vložené do registru dvakrát.

    Text předmětu se normalizuje, protože dvojí vložení bývá i s překlepem.
    Ověřený případ: dodatek ke smlouvě F000123 ze 14. 8. 2026 je v registru
    pod dvěma identifikátory a jeho předmět se liší JEDINOU ČÁRKOU —
    „sběru, svozu" proti „sběru svozu". Přesná shoda textu takový pár
    nenajde, a ve vydání pak stojí dvakrát vedle sebe jako chyba webu.

    Proto se z předmětu vyhodí všechno kromě písmen a číslic. Zbývající
    tři údaje — datum, protistrana a částka na haléře — jsou samy o sobě
    dost úzké; text je jen pojistka, aby se neslily dvě opravdu různé
    smlouvy stejné hodnoty z téhož dne.
    """
    predmet = re.sub(r"[^0-9a-záčďéěíňóřšťúůýž]", "",
                     (sml.get("predmet") or "").lower())
    return (sml.get("datum"), sml.get("protistrana_ico"),
            sml.get("castka_czk"), predmet)


# --------------------------------------------------------------------------
# jednotlivé sekce
# --------------------------------------------------------------------------

def sekce_radnice(od: str, do: str) -> Sekce:
    s = Sekce("z-radnice", "Z radnice",
              "Co projednala rada a zastupitelstvo")
    soubory = glob.glob(str(DATA / "usneseni" / "*" / "*" / "*.json"))
    if not soubory:
        return s.chybi("Nepodařilo se načíst usnesení — o jednáních za toto období nevíme nic.")

    hlasovani_index: dict[str, dict] = {}
    for f in glob.glob(str(DATA / "hlasovani" / "*" / "*" / "*.json")):
        try:
            for h in json.loads(Path(f).read_text(encoding="utf-8")).get("hlasovani", []):
                if h.get("id"):
                    hlasovani_index[h["id"]] = h
        except (json.JSONDecodeError, OSError):
            continue

    polozky = []
    for f in soubory:
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not _v_obdobi(d.get("datum"), od, do):
            continue

        for bod in d.get("body", []):
            h = hlasovani_index.get(bod.get("hlasovani_id") or "")
            polozky.append({
                "organ": d.get("organ"),
                "datum": d.get("datum"),
                "cj": d.get("cj"),
                "cislo": bod.get("cislo"),
                "nazev": bod.get("nazev"),
                "tagy": bod.get("tagy") or [],
                "castka_czk": bod.get("castka_czk"),
                "vyznamne": bool(bod.get("castka_czk") and bod["castka_czk"] >= VYZNAMNA_CASTKA),
                "vysledek": (h or {}).get("vysledek"),
                "hlasovani": {
                    "pro": (h or {}).get("pro"), "proti": (h or {}).get("proti"),
                    "zdrzel": (h or {}).get("zdrzel"),
                    "jmenovite": (h or {}).get("jmenovite") or [],
                } if h else None,
                "url": d.get("url"),
            })

    # Nejdřív peníze a body, které neprošly — tam se čte nejzajímavěji.
    polozky.sort(key=lambda p: (
        0 if p["vysledek"] in ("neschvaleno", "staženo", "odlozeno") else 1,
        -(p["castka_czk"] or 0),
    ))
    nej = None
    for f in soubory:
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if d.get("datum") and (nej is None or d["datum"] > nej):
            nej = d["datum"]
    # Rada zasedá po ~2 týdnech, zastupitelstvo po ~2 měsících.
    return s.dopln(polozky, nej, do, tolerance_dni=75)


def sekce_penize(od: str, do: str) -> Sekce:
    s = Sekce("penize", "Peníze města",
              "Nové smlouvy a dotace za město i jeho organizace")
    soubory = glob.glob(str(DATA / "penize" / "smlouvy" / "*.json"))
    if not soubory:
        return s.chybi("Nepodařilo se načíst registr smluv — o smlouvách za toto období nevíme nic.")

    # Odstranění duplicit má DVĚ úrovně, protože jedna nestačí.
    #
    # Podle identifikátoru: tatáž smlouva je v datech dvakrát, když ji
    # vedou oba sledované subjekty (257 takových případů).
    #
    # Podle obsahu: registr smluv obsahuje tutéž smlouvu i pod DVĚMA
    # RŮZNÝMI identifikátory — zveřejňovatel ji vložil dvakrát. Ověřeno
    # na dodatku ke smlouvě F000123 z 14. 8. 2026, který má id 36778734
    # i 36777210, shodné datum, částku i předmět. Podle id se nepozná,
    # ale ve vydání vedle sebe vypadá jako chyba webu.
    #
    # Shoda ve všech čtyřech údajích naráz je u dvou skutečně různých
    # smluv nepravděpodobná; kolik se jich slilo, se hlásí v poznámce,
    # takže se to neděje potichu.
    videne: set[str] = set()
    obsahove: set[tuple] = set()
    slito = 0
    polozky = []
    for f in soubory:
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for sml in d.get("smlouvy", []):
            if not _v_obdobi(sml.get("datum"), od, do) or sml["id"] in videne:
                continue
            otisk = _otisk_smlouvy(sml)
            if otisk in obsahove:
                slito += 1
                continue
            obsahove.add(otisk)
            videne.add(sml["id"])
            polozky.append({
                "subjekt": d.get("nazev"),
                "datum": sml.get("datum"),
                "protistrana": sml.get("protistrana"),
                "protistrana_ico": sml.get("protistrana_ico"),
                "castka_czk": sml.get("castka_czk"),
                "predmet": sml.get("predmet"),
                "smer": sml.get("smer"),
                "vada": sml.get("vada"),
                "vazba_na_politiky": sml.get("vazba_na_politiky"),
                "url": sml.get("url"),
            })

    polozky.sort(key=lambda p: -(p["castka_czk"] or 0))
    s.dopln(polozky)
    if slito:
        # Čeština skloňuje podle počtu: 1 smlouva, 2-4 smlouvy, 5+ smluv.
        tvar = "smlouva byla" if slito == 1 else ("smlouvy byly" if slito < 5 else "smluv bylo")
        s.poznamka = (f"{slito} {tvar} v registru zveřejněna dvakrát pod různými "
                      f"identifikátory; ve výpisu je jednou.")
    return s


def sekce_deska(od: str, do: str) -> Sekce:
    s = Sekce("uredni-deska", "Úřední deska", "Nově vyvěšené dokumenty")
    data = nacti("mesto/uredni-deska.json")
    if data is None:
        return s.chybi("Nepodařilo se načíst úřední desku.")

    polozky = [
        {"nazev": p.get("nazev"), "kategorie": p.get("kategorie"),
         "od": p.get("vyveseno_od"), "do": p.get("vyveseno_do"), "url": p.get("url")}
        for p in (data if isinstance(data, list) else data.get("polozky", []))
        if _v_obdobi(p.get("vyveseno_od"), od, do)
    ]
    vse = data if isinstance(data, list) else data.get("polozky", [])
    nej = max((p.get("vyveseno_od") or "" for p in vse), default="") or None
    # Deska se mění téměř denně — třítýdenní mezera už je podezřelá.
    return s.dopln(polozky, nej, do, tolerance_dni=21)


def sekce_akce(do: str, dni: int = 7) -> Sekce:
    """Akce se dívají DOPŘEDU — ostatní sekce dozadu."""
    konec = (date.fromisoformat(do) + timedelta(days=dni)).isoformat()
    s = Sekce("akce", "Co se děje ve městě", f"Akce od {do} do {konec}")
    data = nacti("mesto/akce.json")
    if data is None:
        return s.chybi("Nepodařilo se načíst kalendář akcí.")

    polozky = [
        {"nazev": a.get("nazev"), "typ": a.get("typ"), "datum": a.get("datum_od"),
         "cas": a.get("cas_od"), "misto": a.get("misto"), "url": a.get("url")}
        for a in (data if isinstance(data, list) else data.get("akce", []))
        if _v_obdobi(a.get("datum_od"), do, konec)
    ]
    polozky.sort(key=lambda p: (p["datum"] or "", p["cas"] or ""))
    return s.dopln(polozky)


def sekce_media(od: str, do: str) -> Sekce:
    s = Sekce("media", "Psali o nás", "Zprávy o Mariánských Lázních")
    data = nacti("media/clanky.json")
    if data is None:
        return s.chybi("Nepodařilo se načíst mediální monitoring.")

    polozky = [
        {"titulek": c.get("titulek"), "zdroj": c.get("zdroj"), "datum": c.get("datum"),
         "shrnuti": c.get("shrnuti"), "url": c.get("url"), "tagy": c.get("tagy") or []}
        for c in (data if isinstance(data, list) else data.get("clanky", []))
        if _v_obdobi(c.get("datum"), od, do)
    ]
    polozky.sort(key=lambda p: p["datum"] or "", reverse=True)
    vse = data if isinstance(data, list) else data.get("clanky", [])
    nej = max((c.get("datum") or "" for c in vse), default="") or None
    return s.dopln(polozky, nej, do, tolerance_dni=30)


def sekce_zpravodaj(od: str, do: str) -> Sekce:
    s = Sekce("zpravodaj", "Ze zpravodaje", "Nové číslo Městského zpravodaje")
    cisla = nacti("zpravodaj/cisla.json")
    if cisla is None:
        return s.chybi("Nepodařilo se načíst archiv zpravodaje.")

    mesic = do[:7]
    polozky = []
    for c in (cisla if isinstance(cisla, list) else cisla.get("cisla", [])):
        if f"{c.get('rok')}-{int(c.get('mesic', 0)):02d}" != mesic:
            continue
        clanky = []
        for f in sorted(glob.glob(str(DATA / "zpravodaj" / "clanky" / c["id"] / "*.json"))):
            try:
                a = json.loads(Path(f).read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            clanky.append({"nadpis": a.get("nadpis"), "rubrika": a.get("rubrika"),
                           "strana": a.get("strana"), "id": a.get("id")})
        polozky.append({"cislo": c.get("id"), "nazev": c.get("nazev"),
                        "stran": c.get("stran"), "clanku": len(clanky), "clanky": clanky})
    return s.dopln(polozky)


def sekce_zmeny() -> Sekce:
    """Tiché změny na webu města. Zmizelý dokument je zpráva."""
    s = Sekce("zmeny", "Změny na webu města",
              "Co se na stránkách města tiše změnilo nebo zmizelo")
    zmeny = nacti("mesto/snapshots/zmeny.json")
    if zmeny is None:
        return s.dopln([])  # snapshoty ještě nemusí existovat, není to výpadek zdroje
    return s.dopln(zmeny if isinstance(zmeny, list) else zmeny.get("zmeny", []))


# --------------------------------------------------------------------------

def sestav(do: date, dni: int = 7) -> dict:
    od = (do - timedelta(days=dni)).isoformat()
    do_s = do.isoformat()

    sekce = [
        sekce_radnice(od, do_s),
        sekce_penize(od, do_s),
        sekce_deska(od, do_s),
        sekce_akce(do_s),
        sekce_media(od, do_s),
        sekce_zpravodaj(od, do_s),
        sekce_zmeny(),
    ]

    aktivni = [s for s in sekce if s.stav == "ok"]
    chybejici = [s for s in sekce if s.stav == "chybi"]
    zastarale = [s for s in sekce if s.stav == "zastarale"]

    # Zastaralá sekce patří do perexu stejně jako chybějící. Kdyby se
    # zmínily jen ty načtené, vydání by navenek vypadalo úplně.
    if chybejici or zastarale:
        potize = []
        if chybejici:
            potize.append(f"{len(chybejici)} se nepodařilo načíst")
        if zastarale:
            potize.append(
                f"{len(zastarale)} stojí na zastaralých datech ("
                + ", ".join(s.nadpis.lower() for s in zastarale) + ")")
        perex = (f"Přehled za období {od} až {do_s}. "
                 f"Pozor: ze {len(sekce)} sekcí " + " a ".join(potize)
                 + " — o té části dění nevíme nic.")
    elif aktivni:
        perex = (f"Přehled za období {od} až {do_s}: "
                 + ", ".join(f"{s.nadpis.lower()} ({len(s.polozky)})" for s in aktivni) + ".")
    else:
        perex = f"Za období {od} až {do_s} nepřibylo v žádném ze sledovaných zdrojů nic nového."

    return {
        "id": do_s,
        "nazev": NAZEV,
        "datum": do_s,
        "obdobi_od": od,
        "obdobi_do": do_s,
        "perex": perex,
        "vygenerovano": datetime.now().isoformat(timespec="seconds"),
        "souhrn": {
            "sekci_ok": len(aktivni),
            "sekci_prazdnych": sum(1 for s in sekce if s.stav == "prazdno"),
            "sekci_chybejicich": len(chybejici),
            "polozek": sum(len(s.polozky) for s in sekce),
        },
        "sekce": [s.json() for s in sekce],
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Sestaví týdenní vydání")
    p.add_argument("--do", help="Konec období (YYYY-MM-DD), výchozí dnes")
    p.add_argument("--dni", type=int, default=7)
    p.add_argument("--zpetne", type=int, default=0,
                   help="Vygenerovat i N předchozích týdnů do archivu")
    args = p.parse_args()

    log = Log("vydani")
    konec = date.fromisoformat(args.do) if args.do else date.today()

    for i in range(args.zpetne + 1):
        d = konec - timedelta(days=7 * i)
        v = sestav(d, args.dni)
        uloz(f"vydani/{v['id']}.json", v)
        log.info(f"vydání {v['id']}", polozek=v["souhrn"]["polozek"],
                 chybi=v["souhrn"]["sekci_chybejicich"])
        log.pricti()

    # Index pro rozcestník na webu
    vydani = []
    for f in sorted(glob.glob(str(DATA / "vydani" / "*.json")), reverse=True):
        if Path(f).name == "index.json":
            continue
        try:
            v = json.loads(Path(f).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        vydani.append({k: v[k] for k in ("id", "datum", "obdobi_od", "obdobi_do", "perex", "souhrn")})
    uloz("vydani/index.json", vydani)
    log.info("index vydání", pocet=len(vydani))
    log.uzavri()


if __name__ == "__main__":
    main()
