# Design webu — závazná specifikace

Kdo staví web, drží se tohohle. Barvy grafů **nejsou věc vkusu** — byly ověřeny validátorem na barvosleposti a kontrast proti povrchům tohoto webu. Neměň je bez opětovné validace.

---

## 1. Identita

Paleta vychází z lázeňského prostředí: kovová zeleň kolonády a chladný papír. Neutrály mají mírný zelený nádech, aby působily zvoleně, ne převzatě.

```css
:root {
  --paper:      #F5F7F4;   /* plocha stránky */
  --surface:    #FFFFFF;   /* karty, povrch grafů */
  --surface-2:  #EDF1EC;
  --ink:        #141A16;
  --ink-soft:   #4A544D;
  --ink-faint:  #78837B;
  --rule:       #D6DED8;
  --rule-soft:  #E4EAE4;
  --accent:     #1F5540;
}
```

Tmavý režim (deklarovat pod `@media (prefers-color-scheme: dark)` s guardem `:root:not([data-theme="light"])` **i** pod `:root[data-theme="dark"]`):

```css
--paper: #0E1210;  --surface: #151B17;  --surface-2: #1C231E;
--ink: #E4EAE5;  --ink-soft: #A6B2A9;  --ink-faint: #7C8880;
--rule: #2A332D;  --rule-soft: #212A24;  --accent: #6FC79C;
```

**Pravidlo:** žádná barva nesmí být definovaná jen uvnitř media query nebo `[data-theme]` bloku. Vše přes tokeny, jinak se stránka rozbije ve výchozím „system" režimu.

### Typografie

- Nadpisy: `"Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif`
- Text a UI: `ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`
- Data, IČO, částky, kód: `ui-mono, "SF Mono", Menlo, Consolas, monospace`
- **Grafy používají výhradně sans**, i pro velká čísla. Serif do grafu nepatří.
- Kde se čísla řadí pod sebe (tabulky, osy): `font-variant-numeric: tabular-nums`.

---

## 2. Barvy grafů — ověřeno, neměnit

Validováno proti povrchům `#FFFFFF` (světlý) a `#151B17` (tmavý). Prošlo všemi kontrolami včetně odstupu při barvosleposti.

**Kategorie (max 6 + „Ostatní"), v tomto pořadí — pořadí je bezpečnostní mechanismus, ne kosmetika:**

| Pořadí | Světlý | Tmavý |
|---|---|---|
| 1 | `#2a78d6` | `#3987e5` |
| 2 | `#eb6834` | `#d95926` |
| 3 | `#1baf7a` | `#199e70` |
| 4 | `#eda100` | `#c98500` |
| 5 | `#e87ba4` | `#d55181` |
| 6 | `#008300` | `#008300` |
| Ostatní | `#898781` | `#898781` |

**Sekvenční ramp** (pro heatmapu, málo → hodně): `#cde2fb` `#9ec5f4` `#6da7ec` `#3987e5` `#2a78d6` `#256abf` `#184f95` `#0d366b`

**Chrome grafu:** mřížka `#e1e0d9` / `#2c2c2a`, osa `#c3c2b7` / `#383835`, popisky `#898781` v obou režimech.

### Nepřekročitelná pravidla

1. **Nikdy dvě osy Y v jednom grafu.** Dvě různě velké veličiny → dva grafy nebo index ke společnému základu.
2. **Barva patří subjektu, ne pořadí.** Když filtr změní počet firem, zbylým se barva nesmí přebarvit — přiřazuj barvu podle IČO, ne podle indexu v poli.
3. Sedmá a další firma se **neobarvuje novou barvou** — spadne do „Ostatní".
4. Při 2 a více sériích je **legenda vždy**; u jedné série legenda není (název grafu ji pojmenuje).
5. **Ke každému grafu patří tabulkový pohled** (rozbalovací „Zobrazit jako tabulku"). Ve světlém režimu to není volitelné — tři z barev mají kontrast pod 3:1 a tabulka je povinná úleva.
6. Popisky a čísla jsou v barvě textu, **nikdy v barvě série**.
7. Text v grafu nesmí nést význam jen barvou.

---

## 3. Grafy, které web má mít

Podklad: `data/penize/agregace/protistrany.json` a `souhrn.json`.

### 3.1 Objem plateb města po letech
Sloupcový graf, **jedna série**, bez legendy. Osa Y v Kč (zkracovat na „12,4 mil."). Hover ukáže přesnou částku a počet smluv.

### 3.2 Kdo od města dostává peníze
Skládaný sloupcový graf po letech: **6 největších dodavatelů + „Ostatní"**. Legenda povinná. Mezi segmenty **2px mezera v barvě povrchu**. Přepínač dodavatelé / odběratelé (`smer: vydaj` / `prijem`).

### 3.3 Časová osa protistran — kdo kdy začal a kdy přestal
**Heatmapa.** Řádky = protistrana (řazeno podle `prvni_rok`), sloupce = rok, sytost buňky = objem (sekvenční ramp).

Tohle je hlavní graf celého dashboardu a rozhoduje o něm jeden detail:

> **Rok bez peněz musí vypadat jinak než rok s malou částkou.** Prázdná buňka = barva povrchu s tenkým rámečkem, nikdy nejsvětlejší krok rampy. Jinak graf lže o tom, kdy firma začala a přestala brát.

V datech chybějící rok znamená nulu — do osy ho **doplň jako nulu**, nepřeskakuj ho, jinak se časová osa scvrkne a posune.

Hover na buňku: firma, rok, částka, počet smluv. Klik: detail protistrany.

### 3.5 Vlastnictví se nesmí slít — jinak graf tvrdí opak

U každého pohledu na peníze musí být vidět, jestli protistrana **patří městu**, nebo je cizí. Není to kosmetika, je to rozdíl mezi pravdou a opakem:

> Z 1,34 mld. Kč u „dodavatelů s vazbou na politiky" připadá **99,1 % na vlastní organizace města** — technické služby, orchestr, infocentrum, sportoviště. Mimo město jde **11,5 mil. Kč, tedy 0,9 %**.

Bez odlišení by přehled hlásil miliardu odteklou firmám napojeným na politiky. Ve skutečnosti město platí své vlastní organizace a „vazba na politiky" znamená, že v jejich dozorčích radách sedí zastupitelé — což je jejich úkol.

Totéž platí pro TDS, největšího příjemce peněz od města: je to **městská firma**, ne cizí dodavatel.

Proto: sloupec vlastnictví v tabulkách, přepínač „všechny / jen mimo město" u grafů, a věta, která rozdíl pojmenuje.

### 3.6 Mapy

Kreslit jako **SVG generované při buildu z GeoJSON**, stejně jako ostatní grafy. Žádná mapová knihovna ani dlaždice z cizího serveru — data jsou známá při buildu a runtime knihovna by jen zpomalovala a přidala závislost na cizí službě.

Souřadnice převádět do jednotné projekce při buildu. Vždy uvést **zdroj a licenci** dat (OpenStreetMap to vyžaduje).

**Volební mapa má vestavěnou past.** Barví se plocha, ale volí lidé — velký okrsek s hrstkou voličů zabere na mapě víc místa než hustě obydlený panelák. Mapa proto **nikdy nesmí stát sama**: vedle ní patří sloupcový graf nebo tabulka s počty voličů, aby šlo poznat, že rozlehlá barevná plocha nemusí znamenat mnoho hlasů. K okrskům vždy uvádět **absolutní počty**, ne jen procenta.

Barvení podle **účasti nebo podílu** → sekvenční rampa. Barvení podle **vítězné strany** → kategoriální paleta, max 6 + „Ostatní", a stranám se barva přiřazuje podle jejich identity, ne podle pořadí ve výsledku.

Okrsky se v čase mění — když se srovnávají volební roky, musí to být u mapy napsané. Zdroj sám u polygonů uvádí šest různých dat platnosti, a **shodné číslo okrsku neznamená shodné území**.

**U komunálních voleb se nesmí srovnávat hlasy s účastí.** Volič má tolik hlasů, kolik se volí zastupitelů, takže „platných hlasů" je 70 704 při 10 008 voličích. Kdo ta dvě čísla postaví vedle sebe jako srovnatelná, vyrobí nesmysl.

Pravidlo o doprovodu mapy **je vynucené v kódu**, ne jen popsané: komponenta mapy s barvením ploch se bez doprovodných absolutních počtů nevykreslí a napíše proč. Zapsané pravidlo se dá přehlédnout, vynucené ne.

### 3.7 Časové osy

Vodorovná osa, události jako značky, čas zleva doprava. U delších období osa **nesmí přeskakovat prázdné roky** — mezera je informace stejně jako značka.

Události se liší jistotou a **jsou tři, ne dvě** — původně tu stály jen „fakt" a „nízká jistota", data ale rozlišují i třetí případ:

| stav | co znamená | jak vypadá |
|---|---|---|
| `fakt` | doložený údaj | plná značka |
| `sporne` | **doložený** údaj, ale prameny se rozcházejí (např. založení Teplé 1193 vs. 1197) | jiný tvar značky + rozpor vypsaný slovy |
| odhad | spojení dopočítané párováním, se stupněm jistoty | slabší značka, u nízké jistoty výslovná výhrada |

Rozdíl mezi `sporne` a odhadem je podstatný: **sporný údaj je doložený, jen si zdroje odporují** — není to náš dohad. Slít je dohromady by křivdilo oběma směry.

Odlišuj **tvarem, ne jen barvou** — barva sama nesmí nést význam.

Když je na ose hodně událostí, nekresli je jako jednotlivé značky: **900 překrytých koleček neříká nic**. Shlukuj je a velikost značky odvoď od počtu.

U osy jedné entity (osoba, firma, téma) uvádět, z jakých zdrojů se skládá — jinak vypadá jako úplný obraz, ačkoliv obsahuje jen to, co je v našich datech.

### 3.4 Dlaždice nad grafy
Celkový objem · počet protistran · kolik z nich je aktivních · K-index (se stavovou barvou a **vždy i textovým popiskem**, ne barvou samotnou).

---

## 4. Struktura webu

| Cesta | Obsah |
|---|---|
| `/` | Poslední týdenní vydání |
| `/vydani/[id]` | Archiv vydání |
| `/usneseni` | Usnesení, filtr podle orgánu, roku a tagu |
| `/hlasovani` | Hlasování, **filtr podle tagu** — výslovné přání zadavatele |
| `/hlasovani/tag/[tag]` | Hlasování k jednomu tématu |
| `/lide` · `/lide/[id]` | Kdo je kdo, profil s hlasovací historií a sekcí „Kde je aktivní" |
| `/propojeni` | Kdo ze samosprávy sedí ve kterých firmách |
| `/retez` | Řetěz usnesení → smlouva → peníze, vždy s uvedenou jistotou |
| `/penize` | Dashboard s grafy výše |
| `/penize/[ico]` | Detail protistrany — co dostala a kdy |
| `/zpravodaj` · `/zpravodaj/[id]` | Archiv článků |
| `/temata/[tema]` | Časové osy témat |
| `/hledat` | Fulltext přes vše (Pagefind) |

## 5. Provoz

- Astro, statický výstup, deploy na **Vercel**.
- Fulltext **Pagefind** — musí zvládat českou diakritiku.
- **Bez přihlášení a bez hesla.** Neveřejnost zajišťuje neznámá adresa.
- `robots.txt` s `Disallow: /` a `<meta name="robots" content="noindex, nofollow">` na každé stránce, aby se adresa nedostala do vyhledávačů sama od sebe.
- Respektovat `prefers-reduced-motion`, viditelný stav focusu, tabulky ve vlastním `overflow-x: auto` kontejneru.
