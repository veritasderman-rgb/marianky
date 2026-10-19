"""Kdo v zastupitelstvu sedí teď — z webu města, nebo z výsledků voleb.

Web města ukazuje jediné složení zastupitelstva a po volbách ho mění se
zpožděním: po komunálních volbách 9.–10. 10. 2026 na něm ještě týdny stálo
odcházející zastupitelstvo 2022–2026. Mandát přitom vzniká zvolením a ten
starý dnem voleb zaniká — podle zákona, ne podle webu.

Proto: dokud `scrapers/muml.py` hlásí `web_zaostava_za_volbami`, bere se
složení z výsledků ČSÚ (`opendata/volby/zastupitele.json`) a uskupení je
kandidátní listina. Jakmile web dožene volby, vrací se seznam z webu, který
nese i funkce a kontakty.

Rada je jiný případ: vykonává působnost i po volbách až do zvolení nové
rady na ustavujícím zasedání, takže `mesto/rada.json` platí dál.
"""
from __future__ import annotations

from typing import Any

from lib.core import nacti, nacti_config

ZDROJ_WEB = "data/mesto/zastupitele.json"
ZDROJ_VOLBY = "data/opendata/volby/zastupitele.json"


def _aliasy() -> dict[str, str]:
    try:
        aliasy = nacti_config("tataz_osoba.json").get("aliasy", [])
    except FileNotFoundError:
        return {}
    return {j: a["id"] for a in aliasy for j in a.get("jina_id", [])}


def zvoleni_v_poslednich_volbach() -> tuple[int | None, list[dict[str, Any]]]:
    """Rok posledních komunálních voleb a jejich zvolení (id, jméno, listina)."""
    zvoleni = [z for z in (nacti("opendata/volby/zastupitele.json", []) or [])
               if str(z.get("cyklus", "")).startswith("kv") and z.get("rok")]
    if not zvoleni:
        return None, []
    rok = max(z["rok"] for z in zvoleni)
    alias = _aliasy()
    out = [{
        "id": alias.get(z.get("osoba_id"), z.get("osoba_id")),
        "jmeno": z.get("jmeno"),
        "uskupeni": z.get("strana"),
        "datum_voleb": z.get("datum"),
    } for z in zvoleni if z["rok"] == rok]
    return rok, out


def soucasne_zastupitelstvo() -> dict[str, Any] | None:
    """Současné složení: `zastupitele`, `volebni_obdobi`, `zdroj`, `podle_voleb`.

    `podle_voleb` je True, když se složení vzalo z výsledků voleb, protože
    web města ukazuje minulé období. Vrací None, když není ani jeden zdroj.
    """
    web = nacti("mesto/zastupitele.json")
    if web and not web.get("web_zaostava_za_volbami"):
        return {"zastupitele": web.get("zastupitele") or [],
                "volebni_obdobi": web.get("volebni_obdobi"),
                "zdroj": ZDROJ_WEB, "podle_voleb": False}
    rok, zvoleni = zvoleni_v_poslednich_volbach()
    if not zvoleni:
        if not web:
            return None
        return {"zastupitele": web.get("zastupitele") or [],
                "volebni_obdobi": web.get("volebni_obdobi"),
                "zdroj": ZDROJ_WEB, "podle_voleb": False}
    return {"zastupitele": zvoleni, "volebni_obdobi": f"{rok}-{rok + 4}",
            "zdroj": ZDROJ_VOLBY, "podle_voleb": True,
            "web_obdobi": (web or {}).get("volebni_obdobi")}
