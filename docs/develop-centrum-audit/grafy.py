"""Grafy pro auditní zprávu o DEVELOP CENTRU (docs/develop-centrum-audit.pdf).

Vstupy: `data/rozpocet/parkovani_mesicne.json` (Monitor státní pokladny),
čísla z účetních závěrek ve sbírce listin (ručně opsaná níže, zdroj u každé
tabulky), sklizeň registru smluv v `data/penize/`.

Výstup: SVG do `docs/develop-centrum-audit/grafy/`. Spouštět z kořene repa:

    python3 docs/develop-centrum-audit/grafy.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

KOREN = Path(__file__).resolve().parents[2]
VYSTUP = Path(__file__).resolve().parent / "grafy"
VYSTUP.mkdir(exist_ok=True)

# Paleta (validovaná dataviz skriptem, světlý režim): město modře, firma oranžově,
# „zůstalo městu" akvamarín, neutrální šedá, upozornění červeně.
MESTO = "#2a78d6"
FIRMA = "#eb6834"
ZBYLO = "#1baf7a"
CTVRTA = "#eda100"
SEDA = "#9a9893"
TEXT = "#0b0b0b"
TEXT2 = "#52514e"
MRIZKA = "#e6e5e1"
VAROVANI = "#e34948"

plt.rcParams.update({
    "font.family": ["Inter", "DejaVu Sans"],
    "font.size": 9,
    "axes.edgecolor": MRIZKA,
    "axes.labelcolor": TEXT2,
    "xtick.color": TEXT2,
    "ytick.color": TEXT2,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.spines.left": False,
    "axes.grid": True,
    "axes.grid.axis": "y",
    "grid.color": MRIZKA,
    "grid.linewidth": 0.6,
    "axes.axisbelow": True,
    "svg.fonttype": "none",
    "figure.dpi": 100,
})


def mil(x, _pos=None):
    return f"{x:,.1f}".replace(",", " ").replace(".", ",")


def popisky(ax, bars, fmt=mil, dy=0.02, barva=TEXT2, velikost=8):
    """Přímé popisky nad sloupci (paleta má slabší kontrast, popisek je povinný)."""
    for b in bars:
        v = b.get_height()
        if v == 0:
            continue
        y = v if v > 0 else 0
        ax.annotate(fmt(v), (b.get_x() + b.get_width() / 2, y),
                    xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontsize=velikost, color=barva)


def uloz(fig, jmeno):
    fig.savefig(VYSTUP / f"{jmeno}.svg", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("  ", jmeno)


# --------------------------------------------------------------------------
# Data z Monitoru
# --------------------------------------------------------------------------

mesicne = json.loads((KOREN / "data/rozpocet/parkovani_mesicne.json").read_text())["obdobi"]


def hodnota(obdobi: str, paragraf: str, polozka: str) -> float:
    return sum(r["skutecnost"] for r in mesicne.get(obdobi, [])
               if r["paragraf"] == paragraf and r["polozka"] == polozka)


ROKY = [2019, 2020, 2021, 2022, 2023, 2024, 2025]
rocni = {}
for r in ROKY:
    k = f"{r}-12"
    rocni[r] = {
        "parkovne": hodnota(k, "2219", "2111") / 1e6,
        "sluzby": hodnota(k, "2219", "5169") / 1e6,
        "opravy": hodnota(k, "2219", "5171") / 1e6,
        "investice": hodnota(k, "2219", "6121") / 1e6,
    }
rocni[2026] = {
    "parkovne": hodnota("2026-09", "2219", "2111") / 1e6,
    "sluzby": hodnota("2026-09", "2219", "5169") / 1e6,
    "opravy": hodnota("2026-09", "2219", "5171") / 1e6,
    "investice": hodnota("2026-09", "2219", "6121") / 1e6,
    "zaloha": hodnota("2026-09", "3639", "2142") / 1e6,
}
for r in rocni:
    rocni[r]["zbylo"] = rocni[r]["parkovne"] - rocni[r]["sluzby"] - rocni[r]["opravy"]

# --------------------------------------------------------------------------
# G1 Parkovné města a co z něj zůstalo
# --------------------------------------------------------------------------

def g1():
    roky = list(rocni)
    x = range(len(roky))
    w = 0.27
    fig, ax = plt.subplots(figsize=(8.2, 3.6))
    b1 = ax.bar([i - w for i in x], [rocni[r]["parkovne"] for r in roky], w, color=MESTO,
                label="parkovné vybrané městem", linewidth=0)
    b2 = ax.bar([i for i in x], [rocni[r]["sluzby"] + rocni[r]["opravy"] for r in roky], w,
                color=FIRMA, label="zaplaceno za služby a opravy (§ 2219)", linewidth=0)
    b3 = ax.bar([i + w for i in x], [rocni[r]["zbylo"] for r in roky], w, color=ZBYLO,
                label="zůstalo městu", linewidth=0)
    popisky(ax, b1); popisky(ax, b2); popisky(ax, b3)
    ax.set_xticks(list(x))
    ax.set_xticklabels([str(r) if r != 2026 else "2026\n(do 30. 9.)" for r in roky])
    ax.yaxis.set_major_formatter(FuncFormatter(mil))
    ax.set_ylabel("mil. Kč")
    ax.axhline(0, color=SEDA, linewidth=0.8)
    ax.set_ylim(-2.2, 11.8)
    ax.legend(frameon=False, loc="upper left", fontsize=8, ncol=3, bbox_to_anchor=(0, 1.08))
    ax.annotate("od 8/2024\nprovize 90 %", (5, 10.0), fontsize=8, color=TEXT2, ha="center")
    ax.annotate("od 1/2026\ninkasuje firma", (7, 4.2), fontsize=8, color=TEXT2, ha="center")
    uloz(fig, "g1_parkovne_rocne")


# --------------------------------------------------------------------------
# G2 Měsíční tok 2024-08 až 2026-09
# --------------------------------------------------------------------------

def g2():
    obdobi = [k for k in sorted(mesicne) if k >= "2024-06" and not k.endswith("-12") or k in ("2024-12", "2025-12")]
    obdobi = sorted(set(obdobi))
    # měsíční přírůstky kumulované skutečnosti v rámci roku
    def prirustky(par, pol):
        out = []
        prev_rok, prev = None, 0.0
        for k in obdobi:
            rok = k[:4]
            v = hodnota(k, par, pol)
            if rok != prev_rok:
                prev = 0.0
            out.append((v - prev) / 1e6)
            prev_rok, prev = rok, v
        return out

    park = prirustky("2219", "2111")
    sluz = prirustky("2219", "5169")
    sluz3639 = prirustky("3639", "5169")
    zal = prirustky("3639", "2142")
    # § 3639 je stažený jen pro rok 2026 a prosince
    sluz3639 = [v if k.startswith("2026") else 0 for v, k in zip(sluz3639, obdobi)]
    # 2024-06 slouží jen jako základ pro přírůstek 2024-08 (pololetní součet se nekreslí)
    if obdobi and obdobi[0] == "2024-06":
        obdobi, park, sluz, sluz3639, zal = obdobi[1:], park[1:], sluz[1:], sluz3639[1:], zal[1:]

    x = range(len(obdobi))
    w = 0.28
    fig, ax = plt.subplots(figsize=(8.6, 3.8))
    ax.bar([i - w for i in x], park, w, color=MESTO, label="parkovné přijaté městem", linewidth=0)
    ax.bar([i for i in x], sluz, w, color=FIRMA, label="město zaplatilo za služby § 2219", linewidth=0)
    ax.bar([i for i in x], sluz3639, w, bottom=sluz, color=CTVRTA,
           label="město zaplatilo za služby § 3639 (jen 2026)", linewidth=0)
    ax.bar([i + w for i in x], zal, w, color=ZBYLO, label="záloha na zisk od firmy", linewidth=0)
    for i, (a, b, c, d) in enumerate(zip(park, sluz, sluz3639, zal)):
        if b + c >= 1.0:
            ax.annotate(mil(b + c), (i, b + c), xytext=(0, 3), textcoords="offset points",
                        ha="center", fontsize=7.5, color=TEXT2)
        if d > 0:
            ax.annotate(mil(d), (i + w, d), xytext=(0, 3), textcoords="offset points",
                        ha="center", fontsize=7.5, color=TEXT2)
        if a < 0:
            ax.annotate(mil(a), (i - w, a), xytext=(0, -10), textcoords="offset points",
                        ha="center", fontsize=7.5, color=VAROVANI)
    ax.set_xticks(list(x))
    ax.set_xticklabels([k[2:].replace("-", "/") for k in obdobi], rotation=60, ha="right", fontsize=7.5)
    ax.yaxis.set_major_formatter(FuncFormatter(mil))
    ax.set_ylabel("mil. Kč za měsíc výkazu")
    ax.axhline(0, color=SEDA, linewidth=0.8)
    ax.set_ylim(-0.8, 3.0)
    ax.legend(frameon=False, fontsize=7.5, loc="upper left", ncol=2, bbox_to_anchor=(0, 1.12))
    uloz(fig, "g2_mesicni_tok")


# --------------------------------------------------------------------------
# G3 Hospodaření firmy z účetních závěrek (tis. Kč)
# Zdroj: sbírka listin or.justice.cz, IČO 61776068, přečteno přes Sagasu (listina_text).
# --------------------------------------------------------------------------

FIRMA_ROKY = [2021, 2022, 2023, 2024, 2025]
TRZBY = [4522, 7145, 9762, 12593, None]
OSOBNI = [None, 1578, 2067, 5663, None]
ZISK = [512, 2193, 3101, 412, 2273]
VK = {2022: 46845, 2024: 50357, 2025: 52612}


def g3():
    fig, axs = plt.subplots(1, 2, figsize=(8.6, 3.4), gridspec_kw={"width_ratios": [3, 2]})
    ax = axs[0]
    x = range(len(FIRMA_ROKY))
    w = 0.27
    b1 = ax.bar([i - w for i in x], [v or 0 for v in TRZBY], w, color=FIRMA, label="tržby", linewidth=0)
    b2 = ax.bar([i for i in x], [v or 0 for v in OSOBNI], w, color=CTVRTA, label="osobní náklady", linewidth=0)
    b3 = ax.bar([i + w for i in x], ZISK, w, color=ZBYLO, label="zisk po zdanění", linewidth=0)
    f = lambda v, _p=None: f"{v/1000:.1f}".replace(".", ",")
    popisky(ax, b1, f); popisky(ax, b2, f); popisky(ax, b3, f)
    for i, v in enumerate(TRZBY):
        if v is None:
            ax.annotate("tržby a osobní náklady\n2025 závěrka neuvádí", (i - w / 2, 3200), ha="center",
                        fontsize=6.8, color=SEDA)
    ax.set_xticks(list(x)); ax.set_xticklabels([str(r) for r in FIRMA_ROKY])
    ax.yaxis.set_major_formatter(FuncFormatter(f))
    ax.set_ylabel("mil. Kč")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.set_title("Tržby, osobní náklady a zisk firmy", fontsize=9, loc="left", color=TEXT)

    ax = axs[1]
    roky = list(VK)
    b = ax.bar(range(len(roky)), [VK[r] / 1000 for r in roky], 0.5, color=FIRMA, linewidth=0)
    popisky(ax, b, lambda v, _p=None: f"{v:.1f}".replace(".", ","))
    ax.set_xticks(range(len(roky))); ax.set_xticklabels([str(r) for r in roky])
    ax.set_ylim(40, 56)
    ax.set_ylabel("mil. Kč")
    ax.set_title("Vlastní kapitál firmy (ZK 43,0)", fontsize=9, loc="left", color=TEXT)
    ax.axhline(43, color=SEDA, linewidth=0.8, linestyle="--")
    ax.annotate("základní kapitál 43,0", (0, 43.2), fontsize=7.5, color=TEXT2)
    uloz(fig, "g3_firma_hospodareni")


# --------------------------------------------------------------------------
# G4 Kam se dostaly peníze z parkování 2025 (vodopád)
# --------------------------------------------------------------------------

def g4():
    kroky = [
        ("parkovné vybrané\nměstem 2025", 9.02, MESTO),
        ("provize firmě\n(90 %)", -7.66, FIRMA),
        ("opravy a služby\nplacené městem", -0.72, FIRMA),
        ("zůstalo městu", None, ZBYLO),
    ]
    fig, ax = plt.subplots(figsize=(8.2, 3.2))
    bezny = 0
    for i, (lab, v, c) in enumerate(kroky):
        if v is None:
            ax.bar(i, bezny, 0.55, color=c, linewidth=0)
            ax.annotate(mil(bezny), (i, bezny), xytext=(0, 3), textcoords="offset points",
                        ha="center", fontsize=8.5, color=TEXT)
        elif v > 0:
            ax.bar(i, v, 0.55, color=c, linewidth=0)
            ax.annotate(mil(v), (i, v), xytext=(0, 3), textcoords="offset points",
                        ha="center", fontsize=8.5, color=TEXT)
            bezny = v
        else:
            ax.bar(i, -v, 0.55, bottom=bezny + v, color=c, linewidth=0)
            ax.annotate(mil(v), (i, bezny), xytext=(0, 3), textcoords="offset points",
                        ha="center", fontsize=8.5, color=TEXT)
            bezny += v
    ax.set_xticks(range(len(kroky))); ax.set_xticklabels([k[0] for k in kroky], fontsize=8)
    ax.yaxis.set_major_formatter(FuncFormatter(mil))
    ax.set_ylabel("mil. Kč")
    # srovnání: průměr 2021–2024
    prum = sum(rocni[r]["zbylo"] for r in (2021, 2022, 2023, 2024)) / 4
    ax.axhline(prum, color=SEDA, linewidth=0.9, linestyle="--")
    ax.annotate(f"průměr 2021–2024: městu zůstávalo {mil(prum)} mil. Kč ročně",
                (3.3, prum + 0.15), ha="right", fontsize=8, color=TEXT2)
    uloz(fig, "g4_vodopad_2025")


# --------------------------------------------------------------------------
# G5 Zahradní a parková spol. s r.o. — smlouvy s městem po letech
# Zdroj: data/penize/smlouvy/ (Hlídač státu), protistrana IČO 25205978.
# --------------------------------------------------------------------------

def g5():
    import glob
    import collections
    tot = collections.defaultdict(float)
    for f in glob.glob(str(KOREN / "data/penize/smlouvy/*.json")):
        for s in json.loads(Path(f).read_text())["smlouvy"]:
            if s.get("protistrana_ico") == "25205978":
                tot[int(s["datum"][:4])] += (s.get("castka_czk") or 0) / 1e6
    roky = list(range(2016, 2027))
    fig, ax = plt.subplots(figsize=(8.2, 3.0))
    b = ax.bar(roky, [tot.get(r, 0) for r in roky], 0.6, color=MESTO, linewidth=0)
    popisky(ax, b)
    ax.yaxis.set_major_formatter(FuncFormatter(mil))
    ax.set_ylabel("mil. Kč s DPH (hodnota smluv)")
    ax.set_xticks(roky)
    ax.axvspan(2022.6, 2023.97, color=CTVRTA, alpha=0.12, linewidth=0)
    ax.annotate("P. Poc předsedou\ndozorčí rady firmy\n(2023)", (2022.45, 13.0), fontsize=7.5, color=TEXT2, ha="right")
    ax.axvspan(2025.35, 2026.5, color=CTVRTA, alpha=0.12, linewidth=0)
    ax.annotate("P. Poc jednatelem\nfirmy (od 5/2025)", (2025.9, 9.5), fontsize=7.5, color=TEXT2, ha="center")
    uloz(fig, "g5_zahradni_a_parkova")


# --------------------------------------------------------------------------
# G6 Jak rychle firma uveřejňuje smlouvy
# --------------------------------------------------------------------------

def g6():
    lh = json.loads((KOREN / "data/penize/lhuty_zverejneni.json").read_text())["smlouvy"]
    sm = json.loads((KOREN / "data/penize/smlouvy/61776068.json").read_text())["smlouvy"]
    dny = []
    for s in sm:
        l = lh.get(str(s["id"]), {})
        if l.get("dnu") is not None and s["datum"] >= "2017-07-01":
            dny.append(l["dnu"])
    # třetí koš podle kalendářních měsíců (§ 7 odst. 1), ne podle 90 dnů
    import datetime as dt

    def plus_mesice(d, n):
        r, m = d.year, d.month + n
        while m > 12:
            r, m = r + 1, m - 12
        den = min(d.day, [31, 29 if r % 4 == 0 and (r % 100 != 0 or r % 400 == 0) else 28,
                          31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
        return dt.date(r, m, den)

    po3m = vcas = pozde = 0
    for s in sm:
        l = lh.get(str(s["id"]), {})
        if l.get("dnu") is None or s["datum"] < "2017-07-01":
            continue
        u = dt.date.fromisoformat(l["uzavreno"])
        z = dt.date.fromisoformat(l["prvni_zverejneni"])
        if z > plus_mesice(u, 3):
            po3m += 1
        elif l["dnu"] > 30:
            pozde += 1
        else:
            vcas += 1
    kose = [(vcas, "do 30 dnů\n(zákonná lhůta)", ZBYLO), (pozde, "31 dnů až 3 měsíce\n(pozdě)", CTVRTA),
            (po3m, "po 3 měsících\n(zrušena od počátku)", VAROVANI)]
    hodnoty = [k[0] for k in kose]
    fig, ax = plt.subplots(figsize=(8.2, 2.6))
    b = ax.bar(range(3), hodnoty, 0.5, color=[k[2] for k in kose], linewidth=0)
    popisky(ax, b, lambda v, _p=None: f"{int(v)} smluv")
    ax.set_xticks(range(3)); ax.set_xticklabels([k[1] for k in kose], fontsize=8)
    ax.set_ylabel("počet smluv")
    ax.set_title(f"{len(dny)} smluv firmy uzavřených od 1. 7. 2017 se známým datem uveřejnění",
                 fontsize=8.5, loc="left", color=TEXT2)
    uloz(fig, "g6_lhuty")


# --------------------------------------------------------------------------
# G7 Zisk firmy zůstává ve firmě: kumulovaný zisk vs. výplaty městu
# --------------------------------------------------------------------------

def g7():
    roky = FIRMA_ROKY
    kum = []
    s = 0
    for z in ZISK:
        s += z / 1000
        kum.append(s)
    vyplaty = [0, 0, 0, 0, 0]
    fig, ax = plt.subplots(figsize=(8.2, 2.9))
    x = range(len(roky))
    w = 0.35
    b1 = ax.bar([i - w / 2 for i in x], kum, w, color=FIRMA, label="kumulovaný zisk po zdanění 2021–2025", linewidth=0)
    b2 = ax.bar([i + w / 2 for i in x], vyplaty, w, color=MESTO, label="vyplaceno městu jako podíl na zisku", linewidth=0)
    popisky(ax, b1)
    for i in x:
        ax.annotate("0", (i + w / 2, 0), xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8, color=TEXT2)
    ax.bar([len(roky) + w / 2], [1.5], w, color=MESTO, linewidth=0)
    ax.annotate("1,5\n(záloha 2026)", (len(roky) + w / 2, 1.5), xytext=(0, 3), textcoords="offset points",
                ha="center", fontsize=8, color=TEXT2)
    ax.set_xticks(list(x) + [len(roky)]); ax.set_xticklabels([str(r) for r in roky] + ["2026\n(do 9/2026)"])
    ax.yaxis.set_major_formatter(FuncFormatter(mil))
    ax.set_ylabel("mil. Kč")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    uloz(fig, "g7_zisk_vs_vyplaty")


# --------------------------------------------------------------------------
# G8 Investice města na § 2219 (ostatní záležitosti pozemních komunikací)
# --------------------------------------------------------------------------

def g8():
    roky = list(rocni)
    fig, ax = plt.subplots(figsize=(8.2, 2.6))
    b = ax.bar(range(len(roky)), [rocni[r]["investice"] for r in roky], 0.55, color=MESTO, linewidth=0)
    popisky(ax, b)
    ax.set_xticks(range(len(roky)))
    ax.set_xticklabels([str(r) if r != 2026 else "2026\n(do 30. 9.;\nrozpočet 57,9)" for r in roky], fontsize=8)
    ax.yaxis.set_major_formatter(FuncFormatter(mil))
    ax.set_ylabel("mil. Kč")
    uloz(fig, "g8_investice_2219")


if __name__ == "__main__":
    print("grafy →", VYSTUP)
    for f in (g1, g2, g3, g4, g5, g6, g7, g8):
        f()
