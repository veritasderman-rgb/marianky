"""Smlouvy uveřejněné pozdě — co z toho plyne podle zákona o registru smluv.

Spojuje sklizeň Hlídače (`data/penize/smlouvy/*.json`) s daty prvního
uveřejnění ze stránek registru (`data/penize/lhuty_zverejneni.json`,
sběrač `scrapers/registr_lhuty.py`) a ke každé smlouvě spočítá, do které
lhůty zákona č. 340/2015 Sb. spadá:

  * do 30 dnů od uzavření   — v pořádku (§ 5 odst. 2)
  * 31 dnů až 3 měsíce      — pozdě; smlouva je účinná až dnem uveřejnění
                              (§ 6 odst. 1), plnění před ním nemá právní důvod
  * po 3 měsících           — smlouva „je zrušena od počátku" (§ 7 odst. 1)

Lhůty se počítají jen u smluv, na které se § 6 a 7 vztahují:
  * uzavřené 1. 7. 2017 a později (§ 9 — dřív sankce neplatily),
  * s hodnotou nad 50 000 Kč bez DPH (§ 3 odst. 2 písm. h),
  * a mimo ostatní výjimky § 3 odst. 2, z nichž se z dat dají jen tušit:
    protistrana je fyzická osoba bez IČO (písm. a), předmětem je umělecký
    výkon nebo autorské dílo (písm. i — typicky orchestr), plnění převážně
    v zahraničí (písm. d — zájezdy škol, zahraniční protistrana). Takové
    smlouvy se označí jako „možná výjimka", ne jako vyloučené: u převodu
    nemovitosti výjimka a) neplatí a z metadat se nic z toho nepozná jistě.

Kde hodnota bez DPH v registru chybí, odhaduje se z hodnoty s DPH (÷ 1,21)
a je to tak označené. Kde chybí obě, smlouva se do posuzování nepouští
a počítá se zvlášť jako „bez ceny" — neznámá hodnota není nula.

Tenhle modul **neříká, že smlouva je neplatná**. Říká, že registr uvádí
takové datum uzavření a takové datum uveřejnění, a co by z toho podle
litery zákona plynulo. Zda bylo plněno, zda se strany dohodly na
vypořádání, nebo zda spadá pod výjimku, kterou z dat nejde vidět — to je
otázka pro úřad (zákon č. 106/1999 Sb.), ne pro skript.

Výstup: `data/penize/lhuty_prehled.json`
"""
from __future__ import annotations

import argparse
import calendar
import glob
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.core import DATA, Log, nacti, uloz  # noqa: E402

VYSTUP = "penize/lhuty_prehled.json"
SANKCE_OD = date(2017, 7, 1)       # § 9: § 6 a 7 poprvé na smlouvy uzavřené tento den
LIMIT_BEZ_DPH = 50_000.0           # § 3 odst. 2 písm. h) — do 50 000 včetně se neuveřejňuje
DPH = 1.21

RE_UMELEC = re.compile(r"umělec|autorsk|koncert|vystoupen|dirigent|sólist|honorář", re.I)
RE_ZAHRANICI = re.compile(r"zájezd|\bLtd\.?|GmbH|e\.\s?V\.|S\.p\.A|S\.r\.l|Sp\. z o\.o|AG\b|Inc\.", re.I)
RE_OBJEDNAVKA = re.compile(r"^\s*(objedn[aá]vka|obj\.?\s|obj/)", re.I)
RE_DODATEK = re.compile(r"\bdodat(ek|ku|kem)\b", re.I)
# Plnění, které typicky běží od uzavření (ne jednorázová dodávka v budoucnu).
RE_PRUBEZNE = re.compile(
    r"svoz|úklid|údržb|provoz|správ[aě]|nájem|nájmu|pronáj|výpůjč|služb|dodávk\w* (el|plyn|vod|tepl)"
    r"|poskytov|servis|podpor|licenc|pojišt|energ|elekt|teplo|vod[ay]\b|doprav|zajišt",
    re.I,
)


def plus_mesice(d: date, n: int) -> date:
    """d + n kalendářních měsíců (31. 1. + 3 → 30. 4.)."""
    m = d.month - 1 + n
    rok = d.year + m // 12
    mesic = m % 12 + 1
    den = min(d.day, calendar.monthrange(rok, mesic)[1])
    return date(rok, mesic, den)


def posud(s: dict, l: dict) -> dict:
    """Jedna smlouva → zařazení do lhůty a důvody, proč se (ne)posuzuje."""
    uzavreno = date.fromisoformat(l["uzavreno"])
    zverejneno = date.fromisoformat(l["prvni_zverejneni"])
    dnu = (zverejneno - uzavreno).days

    hodnota = l.get("hodnota_bez_dph")
    hodnota_zdroj = "registr bez DPH"
    if hodnota is None and l.get("hodnota_s_dph") is not None:
        hodnota = round(l["hodnota_s_dph"] / DPH, 2)
        hodnota_zdroj = "odhad z hodnoty s DPH"
    if hodnota is None and s.get("castka_czk") is not None:
        hodnota = round(s["castka_czk"] / DPH, 2)
        hodnota_zdroj = "odhad z částky Hlídače (s DPH)"

    duvody_mimo: list[str] = []
    if uzavreno < SANKCE_OD:
        duvody_mimo.append("uzavřeno před 1. 7. 2017 — § 6 a 7 se nepoužijí (§ 9)")
    if hodnota is None:
        duvody_mimo.append("bez ceny — nelze posoudit hranici 50 000 Kč")
    elif hodnota <= LIMIT_BEZ_DPH:
        duvody_mimo.append("do 50 000 Kč bez DPH — povinnost uveřejnit neplatí (§ 3 odst. 2 písm. h)")

    mozna_vyjimka_fo = not s.get("protistrana_ico") and bool(s.get("protistrana"))
    predmet_a_strana = f"{s.get('predmet') or ''} {s.get('protistrana') or ''}"
    mozne_vyjimky: list[str] = []
    if mozna_vyjimka_fo:
        mozne_vyjimky.append("a) fyzická osoba mimo podnikání?")
    if RE_UMELEC.search(s.get("predmet") or ""):
        mozne_vyjimky.append("i) autorské dílo / umělecký výkon?")
    if RE_ZAHRANICI.search(predmet_a_strana):
        mozne_vyjimky.append("d) plnění převážně mimo ČR?")

    if dnu <= 30:
        lhuta = "vcas"
    elif zverejneno <= plus_mesice(uzavreno, 3):
        lhuta = "pozde_do_3m"
    else:
        lhuta = "po_3m"

    predmet = s.get("predmet") or ""
    typ = "dodatek" if RE_DODATEK.search(predmet) else (
        "objednavka" if RE_OBJEDNAVKA.search(predmet) else "smlouva")
    prubezne = bool(RE_PRUBEZNE.search(predmet))

    return {
        "id": s["id"],
        "url": l.get("url") or s.get("url"),
        "predmet": predmet,
        "protistrana": s.get("protistrana"),
        "protistrana_ico": s.get("protistrana_ico"),
        "smer": s.get("smer"),
        "castka_czk": s.get("castka_czk"),
        "hodnota_bez_dph": hodnota,
        "hodnota_zdroj": hodnota_zdroj if hodnota is not None else None,
        "uzavreno": l["uzavreno"],
        "zverejneno": l["prvni_zverejneni"],
        "dnu": dnu,
        "lhuta": lhuta,
        "posuzuje_se": not duvody_mimo,
        "mimo_posouzeni": duvody_mimo,
        "mozna_vyjimka_fo": mozna_vyjimka_fo,
        "mozne_vyjimky": mozne_vyjimky,
        "typ": typ,
        # Odhad, ne údaj: objednávka nebo průběžné plnění, které začalo
        # dřív, než smlouva vůbec mohla být účinná.
        "plneni_pred_ucinnosti_pravdepodobne": lhuta != "vcas" and (typ == "objednavka" or prubezne),
        "utvar": l.get("utvar"),
        "podepsal": l.get("podepsal"),
        "verze": l.get("verze"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=15, help="kolik smluv vypsat do konzole")
    args = ap.parse_args()
    log = Log("lhuty_prehled")

    lhuty = (nacti("penize/lhuty_zverejneni.json") or {}).get("smlouvy") or {}
    if not lhuty:
        log.chyba("chybí data/penize/lhuty_zverejneni.json — spusť scrapers/registr_lhuty.py")
        log.uzavri()
        sys.exit(1)

    subjekty: dict[str, dict] = {}
    for soubor in sorted(glob.glob(str(DATA / "penize" / "smlouvy" / "*.json"))):
        d = nacti(Path(soubor))
        subjekty[d["ico"]] = d

    # Jedna smlouva může být ve sklizni dvou subjektů holdingu (město ↔ TDS).
    # Posuzuje se jednou; subjekty se u ní vyjmenují.
    smlouvy: dict[str, dict] = {}
    u_subjektu: dict[str, list[str]] = defaultdict(list)
    for ico, d in subjekty.items():
        for s in d.get("smlouvy") or []:
            smlouvy.setdefault(s["id"], s)
            u_subjektu[s["id"]].append(ico)

    posouzene: list[dict] = []
    nenalezeno = 0
    bez_lhuty = 0
    for sid, s in smlouvy.items():
        l = lhuty.get(sid)
        if l is None:
            bez_lhuty += 1
            continue
        if l.get("nenalezeno"):
            nenalezeno += 1
            continue
        z = posud(s, l)
        z["subjekty"] = u_subjektu[sid]
        posouzene.append(z)

    def souhrn(vyber: list[dict]) -> dict:
        posuz = [z for z in vyber if z["posuzuje_se"]]
        out = {
            "smluv": len(vyber),
            "posuzovanych": len(posuz),
            "mimo_posouzeni": len(vyber) - len(posuz),
            "vcas": sum(1 for z in posuz if z["lhuta"] == "vcas"),
            "pozde_do_3m": sum(1 for z in posuz if z["lhuta"] == "pozde_do_3m"),
            "po_3m": sum(1 for z in posuz if z["lhuta"] == "po_3m"),
            "po_3m_bez_mozne_vyjimky": sum(1 for z in posuz if z["lhuta"] == "po_3m" and not z["mozne_vyjimky"]),
            "objem_po_3m_bez_mozne_vyjimky_czk": round(sum(z["castka_czk"] or 0 for z in posuz if z["lhuta"] == "po_3m" and not z["mozne_vyjimky"]), 2),
            "objem_po_3m_czk": round(sum(z["castka_czk"] or 0 for z in posuz if z["lhuta"] == "po_3m"), 2),
            "objem_pozde_do_3m_czk": round(sum(z["castka_czk"] or 0 for z in posuz if z["lhuta"] == "pozde_do_3m"), 2),
        }
        out["podil_pozde_pct"] = round(100 * (out["pozde_do_3m"] + out["po_3m"]) / out["posuzovanych"], 1) if out["posuzovanych"] else None
        return out

    po_subjektech = {}
    for ico, d in subjekty.items():
        vyber = [z for z in posouzene if ico in z["subjekty"]]
        if vyber:
            po_subjektech[ico] = {"nazev": d["nazev"], **souhrn(vyber)}

    po_letech = {}
    for rok in sorted({z["uzavreno"][:4] for z in posouzene}):
        po_letech[rok] = souhrn([z for z in posouzene if z["uzavreno"].startswith(rok)])

    # Útvar města: kdo pozdě uveřejňuje (jen u smluv, kde registr útvar uvádí).
    po_utvarech: dict[str, dict] = {}
    for z in posouzene:
        if "00254061" in z["subjekty"] and z["utvar"]:
            po_utvarech.setdefault(z["utvar"], []).append(z)
    po_utvarech = {k: souhrn(v) for k, v in sorted(po_utvarech.items(), key=lambda kv: -len(kv[1]))}

    po_3m = sorted(
        (z for z in posouzene if z["posuzuje_se"] and z["lhuta"] == "po_3m"),
        key=lambda z: -(z["castka_czk"] or 0),
    )
    pozde = sorted(
        (z for z in posouzene if z["posuzuje_se"] and z["lhuta"] == "pozde_do_3m"),
        key=lambda z: -(z["castka_czk"] or 0),
    )
    # Smlouvy bez uvedené hodnoty uveřejněné po 3 měsících: hranici 50 000 Kč
    # u nich posoudit nejde, ale chybějící cena není důvod je zamlčet —
    # Hlídač je počítá mezi zásadní nedostatky a zákon cenu v metadatech
    # vyžaduje (§ 5 odst. 5). Vedou se zvlášť.
    po_3m_bez_ceny = sorted(
        (z for z in posouzene if not z["posuzuje_se"] and z["lhuta"] == "po_3m"
         and z["hodnota_bez_dph"] is None and z["uzavreno"] >= SANKCE_OD.isoformat()),
        key=lambda z: -z["dnu"],
    )

    uloz(VYSTUP, {
        "zdroj": "data/penize/smlouvy/*.json (Hlídač státu) + data/penize/lhuty_zverejneni.json (smlouvy.gov.cz)",
        "metodika": {
            "lhuty": "vcas = do 30 dnů; pozde_do_3m = 31 dnů až 3 kalendářní měsíce; po_3m = později (§ 7 odst. 1: zrušena od počátku)",
            "posuzuje_se": "jen smlouvy uzavřené od 1. 7. 2017 s hodnotou nad 50 000 Kč bez DPH; ostatní jsou v mimo_posouzeni s důvodem",
            "hodnota": "bez DPH z registru; kde chybí, odhad z hodnoty s DPH ÷ 1,21 (označeno v hodnota_zdroj)",
            "mozna_vyjimka_fo": "protistrana bez IČO — může jít o fyzickou osobu mimo podnikání (§ 3 odst. 2 písm. a); z dat to nejde rozhodnout",
            "mozne_vyjimky": "odhad z předmětu a protistrany: a) fyzická osoba, i) umělecký výkon / autorské dílo, d) plnění mimo ČR — smlouva se posuzuje dál, jen je označená",
            "plneni_pred_ucinnosti_pravdepodobne": "ODHAD z předmětu: objednávka nebo průběžné plnění (svoz, nájem, služby…) uveřejněné pozdě",
            "po_3m_bez_ceny": "smlouvy od 1. 7. 2017 bez hodnoty v registru uveřejněné po 3 měsících — hranice 50 000 Kč se u nich posoudit nedá, proto jsou mimo součty, ale vypsané",
            "co_to_neni": "Není to výrok o neplatnosti. Je to porovnání dvou dat z registru s literou zákona.",
        },
        "celkem": souhrn(posouzene),
        "nespojeno": {"bez_lhuty": bez_lhuty, "nenalezeno_v_registru": nenalezeno},
        "po_subjektech": po_subjektech,
        "po_letech": po_letech,
        "po_utvarech_mesta": po_utvarech,
        "po_3m": po_3m,
        "po_3m_bez_ceny": po_3m_bez_ceny,
        "pozde_do_3m": pozde,
    })

    c = souhrn(posouzene)
    log.info("posouzeno", **c)
    log.info("nespojeno", bez_lhuty=bez_lhuty, nenalezeno=nenalezeno)
    log.info("po 3 měsících bez uvedené ceny (vedeno zvlášť)", pocet=len(po_3m_bez_ceny))
    print(f"\nNejvětší smlouvy uveřejněné po 3 měsících (§ 7 odst. 1), top {args.top}:")
    for z in po_3m[: args.top]:
        fo = f" [{'; '.join(z['mozne_vyjimky'])}]" if z["mozne_vyjimky"] else ""
        print(f"  {z['castka_czk'] or 0:>14,.0f} Kč  {z['uzavreno']} → {z['zverejneno']} ({z['dnu']} d)  "
              f"{(z['protistrana'] or '?')[:35]:35}  {z['predmet'][:60]}{fo}")
    log.uzavri()


if __name__ == "__main__":
    main()
