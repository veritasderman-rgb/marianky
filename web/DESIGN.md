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
| `/lide` · `/lide/[id]` | Kdo je kdo, profil s hlasovací historií |
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
