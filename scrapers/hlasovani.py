"""Sběrač jmenovitých hlasování z portálu usneseni.muml.cz.

Tohle je nejcennější část celého projektu: portál u každého usnesení zveřejňuje,
**jak hlasoval jmenovitě každý člen** rady i zastupitelstva. Z toho jde postavit
hlasovací historii konkrétního politika — něco, co pro Mariánské Lázně jinde není.

Klíčová úspora: jmenovité hlasy se NEstahují po usneseních (to by bylo přes
12 000 požadavků), ale **po členech**. Endpoint `vote/participant` vrátí celou
hlasovací historii jednoho člověka v jedné odpovědi, takže celý archiv obou
orgánů je 81 požadavků místo 12 349.

Stranická příslušnost se v čase mění, a portál ji uvádí jen u konkrétního
hlasování. Bere se proto vzorek jednoho usnesení z každého jednání — tím
vznikne mapa "kdo byl za koho v tomhle jednání", platná i pro starší období.

Výstup podle PLAN.md: `data/hlasovani/{organ}/{rok}/{cj}.json`,
navíc rejstřík členů `data/hlasovani/clenove.json` jako podklad pro modul B1.
"""
from __future__ import annotations

import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import core  # noqa: E402
from scrapers import usneseni as U  # noqa: E402

# Popisky hlasů, jak je portál posílá v `type_title`, na hodnoty z PLAN.md.
# PLAN.md rozlišuje pět hodnot, portál šest — "omluven" je podmnožina
# nepřítomnosti, takže se do `hlas` mapuje na `nepritomen` a původní rozlišení
# zůstává v `omluven` u záznamu, ať se neztratí.
HLAS_MAPA = {
    "Pro": "pro",
    "Proti": "proti",
    "Zdržel se": "zdrzel",
    "Nehlasoval": "nehlasoval",
    "Omluven": "nepritomen",
    "Nepřítomen": "nepritomen",
}

# Sloupce souhrnného výpisu hlasování (`vote/decrees`) — pořadí drží portál.
POCTY_MAPA = {
    "votes_type_1": "pro",
    "votes_type_2": "proti",
    "votes_type_3": "zdrzel",
    "votes_type_4": "nehlasoval",
    "votes_type_5": "omluven",
    "votes_type_6": "nepritomen",
}

# Akademické tituly a spojky, které nepatří do jména. Slova s tečkou padnou
# sama (Mgr., Ph.D., DiS.), tohle je zbytek.
NEJMENA = {"et", "bc", "mgr", "ing", "arch", "dr", "judr", "mudr", "mvdr", "paeddr", "rndr", "phdr", "msi"}


# Detail už proběhlého usnesení se na portálu nemění, takže cache platí
# prakticky napořád. Bez toho by týdenní běh po vypršení cache stáhl znovu
# všech 12 349 stránek jen kvůli jedné položce "Výsledek".
CACHE_NAVZDY = 10 * 365 * 86_400


class Nespojeno(Exception):
    """Hlasování se nepodařilo spárovat s bodem usnesení."""


# --------------------------------------------------------------------------
# Identita člověka
# --------------------------------------------------------------------------

def osoba_id(jmeno: str) -> str:
    """Ze jména s tituly udělá slug `prijmeni-jmeno` podle PLAN.md.

    'Mgr. Bc. Miloslav Pelc'      -> 'pelc-miloslav'
    'Dr. Vladimír Kajlik, Ph.D.'  -> 'kajlik-vladimir'
    'Bc. et Bc. Karolína Vejmělková' -> 'vejmelkova-karolina'
    """
    cele = (jmeno or "").split(",")[0]  # tituly za jménem odřízneme s čárkou
    slova = []
    for slovo in cele.split():
        if slovo.endswith("."):
            continue
        holy = unicodedata.normalize("NFKD", slovo)
        holy = "".join(c for c in holy if not unicodedata.combining(c)).lower()
        if holy.strip(".") in NEJMENA:
            continue
        slova.append(slovo)
    if len(slova) < 2:
        raise Nespojeno(f"ze jména {jmeno!r} nejde odvodit osoba_id")
    return f"{core.slug(slova[-1])}-{core.slug(slova[0])}"


# --------------------------------------------------------------------------
# Stažení z portálu
# --------------------------------------------------------------------------

def _id_z_odkazu(html: str) -> str | None:
    m = re.search(r"/hlasovani/clenove/(\d+)", html or "")
    return m.group(1) if m else None


def clenove(organ: str) -> list[dict]:
    """Seznam členů orgánu se souhrnem účasti. Jeden požadavek."""
    radky = U.ajax(organ, "vote/participants", max_age=6 * 3600)
    if not radky:
        raise core.ZdrojSelhal(f"{organ}: prázdný seznam členů hlasování")
    out = []
    for r in radky:
        cid = _id_z_odkazu(r.get("buttons", "")) or _id_z_odkazu(str(r.get("DT_RowAttr", "")))
        if not cid:
            raise core.ZdrojSelhal(f"{organ}: u člena {r.get('participant')!r} chybí odkaz s id")
        out.append({
            "zdroj_id": cid,
            "jmeno": core.cistit(r["participant"]),
            "hlasu": r.get("vote_count"),
        })
    return out


def hlasy_clena(organ: str, zdroj_id: str) -> list[dict]:
    """Celá hlasovací historie jednoho člena. Jeden požadavek na člověka."""
    return U.ajax(organ, "vote/participant", filtr={"id": zdroj_id}, max_age=6 * 3600)


def souhrny_hlasovani(organ: str) -> list[dict]:
    """Všechna hlasování orgánu se součty. Jeden požadavek."""
    radky = U.ajax(organ, "vote/decrees", max_age=6 * 3600)
    if not radky:
        raise core.ZdrojSelhal(f"{organ}: prázdný výpis hlasování")
    return radky


def strany_u_hlasovani(organ: str, usneseni_id: str) -> dict[str, str]:
    """Mapa zdroj_id člena -> strana, jak ji portál uvádí u jednoho hlasování."""
    radky = U.ajax(organ, "decree/voteParticipants", filtr={"id": usneseni_id}, max_age=CACHE_NAVZDY)
    out = {}
    for r in radky:
        cid = _id_z_odkazu(r.get("buttons", ""))
        if cid:
            out[cid] = core.cistit(r.get("party") or "") or None
    return out


# --------------------------------------------------------------------------
# Sestavení
# --------------------------------------------------------------------------

def _body_usneseni(organ: str) -> dict[str, dict]:
    """Načte uložená usnesení a udělá rejstřík `id usnesení na portálu -> bod`.

    Bez uložených usnesení nemáme na co hlasování navázat — tagy ani číslo bodu
    si nevymýšlíme, takže se to hlásí jako chyba, ne jako prázdný výsledek.
    """
    koren = core.DATA / "usneseni" / organ
    rejstrik: dict[str, dict] = {}
    for soubor in sorted(koren.rglob("*.json")) if koren.exists() else []:
        zaznam = core.nacti(soubor)
        for bod in zaznam.get("body", []):
            m = re.search(r"/usneseni/(\d+)", bod.get("url", ""))
            if m:
                rejstrik[m.group(1)] = {**bod, "cj": zaznam["cj"], "rok": int(zaznam["datum"][:4]),
                                        "datum": zaznam["datum"]}
    return rejstrik


def _vysledek(bod: dict) -> str | None:
    """Výsledek hlasování k bodu usnesení.

    Souhrnný výpis hlasování má všechno kromě výsledku — ten je jen na detailu
    usnesení. Sběrač usnesení ho proto ukládá rovnou k bodu; tahle funkce ho
    jen přečte a k portálu sáhne jen u starších záznamů, které pole ještě nemají.
    Když výsledek nikde není, vrací None — nic "pravděpodobného" se nedosazuje.
    """
    if "vysledek" in bod:
        return bod["vysledek"]
    return U.parsuj_detail(U.stahni(bod["url"], max_age=CACHE_NAVZDY))["vysledek"]


def zpracuj_organ(organ: str, log: core.Log) -> dict:
    jednani = {j["id"]: j for j in U.jednani(organ)}
    body = _body_usneseni(organ)
    if not body:
        raise core.ZdrojSelhal(
            f"{organ}: v data/usneseni nic není — pusť nejdřív scrapers.usneseni"
        )

    souhrny = souhrny_hlasovani(organ)
    log.info(f"{organ}: {len(souhrny)} hlasování, {len(body)} uložených bodů usnesení")

    # 1) jmenovité hlasy — po členech, ne po usneseních
    seznam_clenu = clenove(organ)
    jmenovite: dict[str, list[tuple[str, str]]] = defaultdict(list)  # usneseni_id -> [(zdroj_id, typ)]
    jmena: dict[str, str] = {}
    for clen in seznam_clenu:
        jmena[clen["zdroj_id"]] = clen["jmeno"]
        for h in hlasy_clena(organ, clen["zdroj_id"]):
            jmenovite[str(h["id"])].append((clen["zdroj_id"], h["type_title"]))
        time.sleep(U.PAUZA)
    log.info(f"{organ}: {len(seznam_clenu)} členů, jmenovité hlasy u {len(jmenovite)} hlasování")

    # 2) stranická příslušnost — vzorek jednoho hlasování z každého jednání
    vzorek: dict[str, str] = {}
    for s in souhrny:
        vzorek.setdefault(str(s["meeting_id"]), str(s["id"]))
    strany: dict[tuple[str, str], str] = {}  # (meeting_id, zdroj_id) -> strana
    for mid, uid in vzorek.items():
        for cid, strana in strany_u_hlasovani(organ, uid).items():
            strany[(mid, cid)] = strana
        time.sleep(U.PAUZA)
    log.info(f"{organ}: stranická příslušnost z {len(vzorek)} jednání")

    # 3) sestavení po jednáních
    po_jednanich: dict[str, list[dict]] = defaultdict(list)
    nespojenych = 0
    bez_jmenovitych = 0
    nesouhlasi = 0
    for s in souhrny:
        uid = str(s["id"])
        bod = body.get(uid)
        if bod is None or not bod.get("hlasovani_id"):
            nespojenych += 1
            continue
        try:
            vysledek = _vysledek(bod)
        except core.ZdrojSelhal as e:
            vysledek = None
            log.chyba(f"{organ}: výsledek hlasování u {bod['url']} nejde přečíst: {e}")
        if not vysledek:
            # Radši hlasování vynechat, než mu dopsat výsledek, který nikde nestojí.
            log.chyba(f"{organ}: {bod['url']} nemá výsledek hlasování, vynecháno")
            nespojenych += 1
            continue

        mid = str(s["meeting_id"])
        pocty = {nazev: int(s.get(sloupec) or 0) for sloupec, nazev in POCTY_MAPA.items()}

        hlasy = []
        # Řadíme podle osoba_id, tedy podle příjmení — jména z portálu začínají
        # tituly a řadit podle nich by dalo pořadí "Bc., Ing., JUDr., Mgr.".
        for cid, typ in sorted(jmenovite.get(uid, []), key=lambda x: osoba_id(jmena[x[0]])):
            if typ not in HLAS_MAPA:
                raise core.ZdrojSelhal(f"{organ}: neznámý typ hlasu {typ!r}")
            jmeno = jmena[cid]
            zaznam = {
                "osoba_id": osoba_id(jmeno),
                "jmeno": jmeno,
                "strana": strany.get((mid, cid)),
                "hlas": HLAS_MAPA[typ],
            }
            if typ == "Omluven":
                # PLAN.md nemá pro omluvu vlastní hodnotu; ať se ale nezahodí
                # rozdíl mezi "omluven" a "prostě tam nebyl".
                zaznam["omluven"] = True
            hlasy.append(zaznam)

        if not hlasy:
            bez_jmenovitych += 1
        else:
            kontrola = Counter(h["hlas"] for h in hlasy)
            ocekavano = {"pro": pocty["pro"], "proti": pocty["proti"], "zdrzel": pocty["zdrzel"],
                         "nehlasoval": pocty["nehlasoval"],
                         "nepritomen": pocty["omluven"] + pocty["nepritomen"]}
            if {k: v for k, v in kontrola.items()} != {k: v for k, v in ocekavano.items() if v}:
                nesouhlasi += 1

        po_jednanich[mid].append({
            "id": bod["hlasovani_id"],
            "bod": bod["cislo"],
            "nazev": bod["nazev"],
            "tagy": bod.get("tagy") or ["ruzne"],
            "vysledek": vysledek,
            "pro": pocty["pro"],
            "proti": pocty["proti"],
            "zdrzel": pocty["zdrzel"],
            "nehlasoval": pocty["nehlasoval"],
            "omluven": pocty["omluven"],
            "nepritomen": pocty["nepritomen"],
            "jmenovite": hlasy,
        })

    ulozeno = 0
    for mid, seznam in po_jednanich.items():
        jed = jednani.get(mid)
        if jed is None:
            log.chyba(f"{organ}: hlasování odkazuje na neznámé jednání {mid}")
            continue
        seznam.sort(key=lambda h: int(h["bod"].split("/")[-1]))
        core.uloz(f"hlasovani/{organ}/{jed['rok']}/{jed['cj']}.json", {
            "organ": organ,
            "cj": jed["cj"],
            "datum": jed["datum"],
            "hlasovani": seznam,
        })
        ulozeno += 1
        log.pricti(len(seznam))

    if nespojenych:
        log.info(f"{organ}: {nespojenych} hlasování bez uloženého bodu usnesení (nespárováno)")
    if bez_jmenovitych:
        log.info(f"{organ}: {bez_jmenovitych} hlasování bez jmenovitých hlasů")
    if nesouhlasi:
        log.info(f"{organ}: {nesouhlasi} hlasování, kde jmenovité hlasy nesedí na součty portálu")

    return {
        "jednani": ulozeno,
        "hlasovani": sum(len(v) for v in po_jednanich.values()),
        "clenu": len(seznam_clenu),
        "nespojenych": nespojenych,
        "bez_jmenovitych": bez_jmenovitych,
        "nesouhlasi": nesouhlasi,
        "clenove": seznam_clenu,
        "strany": strany,
        "jmena": jmena,
    }


def _uloz_rejstrik_clenu(po_organech: dict[str, dict]) -> int:
    """Rejstřík lidí, kteří kdy hlasovali. Podklad pro modul B1 (Kdo je kdo) —
    `osoba_id` tady musí sednout na `data/lide/osobnosti.json`."""
    lide: dict[str, dict] = {}
    for organ, v in po_organech.items():
        for clen in v["clenove"]:
            oid = osoba_id(clen["jmeno"])
            zaznam = lide.setdefault(oid, {"id": oid, "jmeno": clen["jmeno"],
                                           "zdroj_id": {}, "hlasu": {}, "strany": []})
            zaznam["zdroj_id"][organ] = clen["zdroj_id"]
            zaznam["hlasu"][organ] = clen["hlasu"]
        for (_mid, cid), strana in v["strany"].items():
            jmeno = v["jmena"].get(cid)
            if not jmeno or not strana:
                continue
            zaznam = lide.get(osoba_id(jmeno))
            if zaznam is not None and strana not in zaznam["strany"]:
                zaznam["strany"].append(strana)
    core.uloz("hlasovani/clenove.json", sorted(lide.values(), key=lambda o: o["id"]))
    return len(lide)


def main() -> dict:
    log = core.Log("hlasovani")
    po_organech = {}
    for organ in U.ORGANY:
        try:
            po_organech[organ] = zpracuj_organ(organ, log)
        except core.ZdrojSelhal as e:
            log.chyba(f"{organ}: {e}")
    if not po_organech:
        raise core.ZdrojSelhal("nepodařilo se stáhnout hlasování ani jednoho orgánu")

    lidi = _uloz_rejstrik_clenu(po_organech)
    log.info("rejstřík členů", osob=lidi)
    for organ, v in po_organech.items():
        log.info(f"{organ}: uloženo", jednani=v["jednani"], hlasovani=v["hlasovani"], clenu=v["clenu"])

    vysledek = log.uzavri()
    vysledek["prehled"] = {o: {k: v[k] for k in ("jednani", "hlasovani", "clenu", "nespojenych",
                                                 "bez_jmenovitych", "nesouhlasi")}
                           for o, v in po_organech.items()}
    return vysledek


if __name__ == "__main__":
    main()
