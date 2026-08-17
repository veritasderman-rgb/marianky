"""Kontrola kvality výstupu modulu A1 — usnesení a hlasování.

Pomocný skript, ne součást pipeline. Ověřuje, že uložená data odpovídají
formátům z docs/PLAN.md a dává čísla pro závěrečné shrnutí.
"""
import json, glob, sys, re
from collections import Counter
sys.path.insert(0, '/home/user/marianky')
from lib import core

platne = core.platne_tagy()
HLASY = {"pro", "proti", "zdrzel", "nehlasoval", "nepritomen"}
VYSL = {"schvaleno", "neschvaleno", "staženo", "odlozeno"}
chyby = []

print("=" * 72)
print("USNESENÍ")
print("=" * 72)
tagy = Counter(); poc_tagu = Counter()
jednani = Counter(); body = Counter(); castky = 0; s_hlasovanim = 0
obdobi = Counter(); hids = set(); vsechny_body = 0; roky = Counter()
delky = []
for f in sorted(glob.glob('/home/user/marianky/data/usneseni/**/*.json', recursive=True)):
    z = json.load(open(f, encoding='utf-8'))
    organ = z['organ']
    jednani[organ] += 1
    roky[z['datum'][:4]] += 1
    obdobi[z['obdobi']] += 1
    for k in ('organ', 'cj', 'datum', 'obdobi', 'url', 'body'):
        if k not in z: chyby.append(f"{f}: chybí {k}")
    cesta = re.search(r'/usneseni/(rada|zastupitelstvo)/(\d{4})/(-?\d+)\.json$', f)
    if not cesta:
        chyby.append(f"{f}: cesta neodpovídá PLAN.md")
    elif (cesta.group(1), int(cesta.group(2)), int(cesta.group(3))) != (organ, int(z['datum'][:4]), z['cj']):
        chyby.append(f"{f}: cesta nesedí na obsah")
    for b in z['body']:
        vsechny_body += 1
        body[organ] += 1
        for k in ('cislo', 'nazev', 'text', 'tagy', 'castka_czk', 'hlasovani_id'):
            if k not in b: chyby.append(f"{f}: bod {b.get('cislo')} nemá {k}")
        t = b['tagy']
        if not (1 <= len(t) <= 3): chyby.append(f"{f}: {b['cislo']} má {len(t)} tagů")
        for x in t:
            if x not in platne: chyby.append(f"{f}: neplatný tag {x}")
        tagy.update(t); poc_tagu[len(t)] += 1
        delky.append(len(b['text']))
        if b['castka_czk'] is not None: castky += 1
        if b['hlasovani_id']:
            s_hlasovanim += 1
            if b['hlasovani_id'] in hids: chyby.append(f"duplicitní hlasovani_id {b['hlasovani_id']}")
            hids.add(b['hlasovani_id'])
        if not b['nazev'].strip(): chyby.append(f"{f}: {b['cislo']} prázdný název")
        if not b['text'].strip(): chyby.append(f"{f}: {b['cislo']} prázdný text")

n = max(vsechny_body, 1)
print(f"jednání:      {dict(jednani)}  celkem {sum(jednani.values())}")
print(f"bodů:         {dict(body)}  celkem {vsechny_body}")
print(f"s hlasováním: {s_hlasovanim} ({100*s_hlasovanim/n:.1f} %)")
print(f"s částkou:    {castky} ({100*castky/n:.1f} %)")
print(f"tagů na bod:  {dict(sorted(poc_tagu.items()))}")
print(f"medián délky textu: {sorted(delky)[len(delky)//2] if delky else 0} znaků")
print(f"volební období: {dict(sorted(obdobi.items()))}")
print(f"jednání po letech: {dict(sorted(roky.items()))}")
print("\nrozložení tagů:")
for t, k in tagy.most_common():
    print(f"  {t:20} {k:6}  {100*k/n:5.1f} %")

print("\n" + "=" * 72)
print("HLASOVÁNÍ")
print("=" * 72)
h_jednani = Counter(); h_pocet = Counter(); s_jmeny = 0; bez_jmen = 0
osoby = Counter(); strany = Counter(); hlasy = Counter(); nesedi = 0
h_ids = set(); bez_strany = 0; jm_celkem = 0; vysledky = Counter()
for f in sorted(glob.glob('/home/user/marianky/data/hlasovani/**/*.json', recursive=True)):
    if f.endswith('clenove.json'): continue
    z = json.load(open(f, encoding='utf-8'))
    organ = z['organ']; h_jednani[organ] += 1
    for h in z['hlasovani']:
        h_pocet[organ] += 1
        h_ids.add(h['id'])
        vysledky[h['vysledek']] += 1
        if h['vysledek'] not in VYSL: chyby.append(f"{f}: neplatný výsledek {h['vysledek']}")
        for x in h['tagy']:
            if x not in platne: chyby.append(f"{f}: neplatný tag hlasování {x}")
        jm = h['jmenovite']
        if jm:
            s_jmeny += 1
            jm_celkem += len(jm)
            soucet = Counter(x['hlas'] for x in jm)
            ocek = {'pro': h['pro'], 'proti': h['proti'], 'zdrzel': h['zdrzel'],
                    'nehlasoval': h['nehlasoval'], 'nepritomen': h['omluven'] + h['nepritomen']}
            if dict(soucet) != {k: v for k, v in ocek.items() if v}: nesedi += 1
            for x in jm:
                if x['hlas'] not in HLASY: chyby.append(f"{f}: neplatný hlas {x['hlas']}")
                osoby[x['osoba_id']] += 1
                if x['strana']: strany[x['strana']] += 1
                else: bez_strany += 1
                hlasy[x['hlas']] += 1
        else:
            bez_jmen += 1

hp = max(sum(h_pocet.values()), 1)
print(f"jednání:        {dict(h_jednani)}  celkem {sum(h_jednani.values())}")
print(f"hlasování:      {dict(h_pocet)}  celkem {sum(h_pocet.values())}")
print(f"s jmenovitými:  {s_jmeny} ({100*s_jmeny/hp:.1f} %), bez jmenovitých: {bez_jmen}")
print(f"jmenovitých hlasů celkem: {jm_celkem}")
print(f"součty nesedí:  {nesedi}")
print(f"osob:           {len(osoby)}, hlasů bez uvedené strany: {bez_strany}")
print(f"výsledky:       {dict(vysledky)}")
print(f"rozložení hlasů: {dict(hlasy.most_common())}")
print(f"strany: {dict(strany.most_common())}")
print("\nnejvíc hlasů:")
for o, k in osoby.most_common(8): print(f"  {o:26} {k}")

print(f"\nhlasovani_id v usneseních bez záznamu hlasování: {len(hids - h_ids)}")
print(f"hlasování bez odpovídajícího bodu usnesení:     {len(h_ids - hids)}")

print(f"\nCHYBY: {len(chyby)}")
for c in chyby[:20]: print("  ", c)
