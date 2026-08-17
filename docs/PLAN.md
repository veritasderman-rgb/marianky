# Naše Mariánky v přehledech — plán implementace

Neveřejný přehled dění ve městě. Provoz pod vlastním jménem provozovatele, přístup přes neveřejnou adresu.

Tenhle dokument je **sdílený kontrakt** — každý, kdo staví kterýkoliv modul, se drží formátů níže. Kdo se od nich odchýlí, rozbije web ostatním.

---

## Základní zásady

1. **Scraping dělá kód, porozumění dělá Claude.** Model nikdy neparsuje HTML a nehledá selektory. Dostává čistá strukturovaná data a shrnuje je.
2. **Sběrač buď uspěje, nebo vyhodí `ZdrojSelhal`.** Žádné tiché prázdné výsledky.
3. **Čísla a jména se propisují z dat, ne z generovaného textu.**
4. **Tagy se vybírají z pevného číselníku** `config/tagy.json`, nikdy se nevymýšlejí nové.
5. Vše ukládat přes `lib/core.uloz()` — atomický zápis, konzistentní formát.

## Prostředí

- Python 3.11, `requests`, `selectolax` — **žádné další závislosti bez důvodu**
- `pdftotext` / `pdfinfo` (poppler-utils) — instalace vyžaduje `apt-get update` předem
- Node 22 + npm 10 pro web
- Sdílené jádro: `lib/core.py` — `fetch`, `uloz`, `nacti`, `Log`, `pdf_na_text`, `slug`, `parse_datum`

**`fetch()` posílá správný User-Agent** — `usneseni.muml.cz` bez něj vrací 503.
**`pdf_na_text()` volá pdftotext bez `-layout`** — s ním se dvousloupcová sazba prolíná.

---

## Rozdělení práce

Každý modul vlastní své soubory. **Nikdo nesahá do cizích.**

| Modul | Vlastní soubory | Zapisuje do |
|---|---|---|
| A1 Usnesení a hlasování | `scrapers/usneseni.py`, `scrapers/hlasovani.py`, `pipeline/tagovani.py` | `data/usneseni/`, `data/hlasovani/` |
| A2 Zpravodaj | `scrapers/zpravodaj.py`, `pipeline/clanky.py` | `data/zpravodaj/` |
| A3 Peníze | `scrapers/hlidac.py`, `scrapers/hlidac_api.py`, `pipeline/agregace_penez.py` | `data/penize/` |
| A4 Web města | `scrapers/muml.py`, `scrapers/snapshoty.py` | `data/mesto/` |
| B1 Kdo je kdo | `data/lide/osobnosti.json`, `scrapers/lide.py` | `data/lide/` |
| B2/O5 Web | `web/**` | — |
| B3 Média | `scrapers/media.py` | `data/media/` |
| C1 Zastupitelstvo video | `scrapers/zaznamy.py`, `pipeline/prepis.py` | `data/zaznamy/` |
| P1 Propojení lidí a firem | `scrapers/osoby_firmy.py`, `pipeline/propojeni.py` | `data/propojeni/` |
| P2 Řetěz usnesení→smlouva | `pipeline/retez.py` | `data/retez/` |
| P3 Hlasovací profily | `pipeline/profily.py` | `data/lide/profily.json` |
| O1 Volby a statistiky | `scrapers/volby.py`, `scrapers/csu.py` | `data/opendata/volby/`, `data/opendata/csu/` |
| O2 Firmy ve městě | `scrapers/firmy.py`, `pipeline/firmy_prehled.py` | `data/firmy/` |
| O3 Památky a geodata | `scrapers/pamatky.py`, `scrapers/geodata.py` | `data/opendata/pamatky/`, `data/opendata/geo/` |
| O4 Historie a časová osa | `pipeline/casova_osa.py` | `data/historie/`, `data/casova_osa/`, `data/osy/` |
| Rozpočet | `scrapers/monitor.py`, `pipeline/rozpocet.py` | `data/rozpocet/` |
| Územní plánování | `scrapers/uzemni_plan.py` | `data/uzemni_plan/` |
| Vydání | `pipeline/vydani.py` | `data/vydani/` |

**Formáty novějších modulů jsou zdokumentované v docstringu příslušného modulu**, ne tady — dokument by se jinak rozešel se skutečností rychleji, než by se dal udržovat. Níže zůstávají formáty základních sad, na kterých stojí zbytek.

---

## Formáty záznamů

### Usnesení — `data/usneseni/{orgán}/{rok}/{čj}.json`

`orgán` je `rada` nebo `zastupitelstvo`.

```json
{
  "organ": "rada",
  "cj": 124,
  "datum": "2026-08-07",
  "obdobi": "2022-2026",
  "url": "https://usneseni.muml.cz/...",
  "body": [
    {
      "cislo": "124/1",
      "nazev": "Prodej pozemku p.č. 123/4 v k.ú. Úšovice",
      "text": "Rada města schvaluje ...",
      "tagy": ["majetek-prodej"],
      "castka_czk": 1250000,
      "hlasovani_id": "rada-2026-124-1"
    }
  ]
}
```

- `castka_czk` — `null`, když v textu žádná částka není. **Nikdy nehádat.**
- `tagy` — 1 až 3 položky, výhradně `id` z `config/tagy.json`.
- `hlasovani_id` — `null`, když se u bodu hlasování nedohledalo.

### Hlasování — `data/hlasovani/{orgán}/{rok}/{čj}.json`

```json
{
  "organ": "rada",
  "cj": 124,
  "datum": "2026-08-07",
  "hlasovani": [
    {
      "id": "rada-2026-124-1",
      "bod": "124/1",
      "nazev": "Prodej pozemku p.č. 123/4",
      "tagy": ["majetek-prodej"],
      "vysledek": "schvaleno",
      "pro": 6, "proti": 1, "zdrzel": 0, "nehlasoval": 0,
      "jmenovite": [
        { "osoba_id": "hurajcik-martin", "jmeno": "Martin Hurajčík", "strana": "ANO 2011", "hlas": "pro" }
      ]
    }
  ]
}
```

- `hlas` ∈ `pro` | `proti` | `zdrzel` | `nehlasoval` | `nepritomen`
- `vysledek` ∈ `schvaleno` | `neschvaleno` | `staženo` | `odlozeno`
- `osoba_id` — slug `prijmeni-jmeno`, musí odpovídat `data/lide/osobnosti.json`

**Tagy se na hlasování kopírují z odpovídajícího bodu usnesení**, aby šlo filtrovat hlasování podle tématu.

### Zpravodaj — index `data/zpravodaj/cisla.json`

```json
[{ "id": "2026-08", "rok": 2026, "mesic": 8, "nazev": "Zpravodaj města 08/2026",
   "url": "https://www.muml.cz/modules/file_storage/download.php?file=...",
   "soubor": "data/zpravodaj/pdf/2026-08.pdf", "stran": 32, "ocr": false }]
```

### Článek — `data/zpravodaj/clanky/{id_cisla}/{poradi}.json`

```json
{
  "id": "2026-08-005",
  "cislo": "2026-08",
  "strana": 5,
  "rubrika": "Dění ve městě",
  "nadpis": "Město získalo dotaci na další přípravy záchrany vily LIL",
  "perex": "Mariánské Lázně získaly od Karlovarského kraje dotaci ...",
  "text": "…plné znění…",
  "osoby": ["stejskalova-zuzana", "hurajcik-martin"],
  "tagy": ["pamatky", "dotace-prijate"],
  "pdf_odkaz": "…?file=…#page=5"
}
```

Inzerce se **nezpracovává** — `rubrika: "Inzerce"` se zahazuje.

### Peníze — `data/penize/smlouvy/{ico}.json`

```json
{
  "ico": "00254061",
  "nazev": "Město Mariánské Lázně",
  "smlouvy": [
    { "id": "…", "datum": "2026-03-14", "castka_czk": 2400000,
      "protistrana_ico": "12345678", "protistrana": "Stavby s.r.o.",
      "predmet": "Rekonstrukce chodníku", "kategorie": "Stavebnictví",
      "smer": "vydaj", "vada": false, "url": "https://www.hlidacstatu.cz/…" }
  ]
}
```

- `smer` ∈ `vydaj` (město platí — protistrana je **dodavatel**) | `prijem` (město inkasuje — protistrana je **odběratel**)
- `vada: true` u smluv, které Hlídač označuje za vážně vadné

### Agregace peněz — `data/penize/agregace/protistrany.json`

Tohle je podklad pro grafy „kdo kolik a kdy od města dostal".

```json
{
  "generovano": "2026-08-17",
  "protistrany": [
    {
      "ico": "12345678",
      "nazev": "Stavby s.r.o.",
      "smer": "vydaj",
      "celkem_czk": 48200000,
      "prvni_rok": 2017,
      "posledni_rok": 2026,
      "aktivni": true,
      "po_letech": { "2017": 1200000, "2018": 8400000, "2026": 3100000 },
      "smluv": 34,
      "subjekty": ["00254061", "00074071"]
    }
  ]
}
```

- `aktivni` — dostal peníze v posledních 12 měsících
- `po_letech` — chybějící rok znamená nula; **do grafu se doplní nulou, ne přeskočí**, jinak časová osa lže
- `subjekty` — od kterých subjektů holdingu peníze tekly

### Osobnost — `data/lide/osobnosti.json`

```json
[{
  "id": "hurajcik-martin",
  "jmeno": "Martin Hurajčík",
  "role": ["starosta"],
  "kategorie": "politika",
  "strana": "ANO 2011",
  "funkce": [{ "nazev": "starosta", "od": "2022-10", "do": null }],
  "popis": "…2–4 věty…",
  "zdroje": ["https://www.muml.cz/…"],
  "zijici": true
}]
```

- `kategorie` ∈ `politika` | `urad` | `mestske-firmy` | `kultura` | `sport` | `historie` | `veda` | `podnikani`
- `funkce[].od` / `.do` — funkce se v čase mění, ukládat s platností, ne jako aktuální stav
- U historických osobností `zijici: false` a `zdroje` povinné

---

## Konvence, na kterých stojí propojení dat

Tohle jsou dohody, jejichž porušení se projeví až tím, že se data nespárují.

**`osoba_id` = `prijmeni-jmeno`**, bez titulů a s jedním křestním jménem (`goethe-johann`, ne `goethe-johann-wolfgang`). Používá se v hlasování, v článcích zpravodaje, v médiích, v profilech i v osobnostech — jakmile se dva moduly rozejdou, vznikne z jednoho člověka dvojice. Zdroje se v přepisu jmen liší (ČSÚ píše *Zabolotnij*, web města *Zabolotný*); rozhoduje tvar z hlasování.

**Protistrany se slučují podle IČO, ne podle názvu.** Firmy se přejmenovávají — IČO 25208438 vystupuje jako KIS i jako Infocentrum. Kde IČO chybí, slučuje se podle normalizovaného názvu a záznam to přizná polem `klic_dle`.

**Tagy se vybírají z `config/tagy.json`, nikdy nevymýšlejí.** Jinak každý běh vytvoří jiné názvy a filtrování po půl roce přestane fungovat.

## Fáze

| Fáze | Obsah | Stav |
|---|---|---|
| 1 | Usnesení, hlasování, tagy, peníze, web města, statický web | hotovo |
| 2 | Archiv 122 čísel zpravodaje, fulltext | hotovo |
| 3 | Kdo je kdo, grafy peněz, propojení, profily, řetěz | hotovo |
| 4 | Mediální monitoring, diff-monitoring, přepisy zastupitelstva | hotovo mimo přepisy — čekají na síť, viz PROVOZ.md |
| 5 | Volby, statistiky, firmy, památky, mapy, historie, časové osy | hotovo |
| 6 | Rozpočet z Monitoru státní pokladny, územní plánování | rozpracováno |

## Hosting

Vercel, statický výstup. **Bez přihlášení a bez hesla** — neveřejnost zajišťuje neznámá adresa.
Přidat `robots.txt` s `Disallow: /` a meta `noindex`, aby se adresa nedostala do vyhledávačů sama od sebe.
