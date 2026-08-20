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

### Značka

Kolonáda: klenutý oblouk s kupolí, dva krajní pilíře a mezi nimi pět sloupů. Čte se dvojím způsobem naráz — sloupy kolonády a sloupce grafu. Výšky drží poměr smluv města v registru za roky 2022–2026 (634, 608, 786, 792, 445).

**Je to značka, ne graf.** Poměr pochází z dat, ale zůstává pevný. Logo, které se mění každý týden, není logo.

**Zlatá je rytmus, ne údaj.** Druhý a čtvrtý sloup mají jinou barvu jen proto, aby se pětice nečetla jako jeden blok. Nic to neznamená a nesmí se to tak vykládat — význam nesou výšky. Kdyby zlatá měla někdy znamenat kategorii, musí to říct legenda, ne logo.

Konstrukce ve `viewBox 0 0 64 64` (obě kopie ji sdílejí):

| díl | geometrie |
| --- | --- |
| základna | `x 3.6, y 56, š 56.8, v 3.4, rx 1.7` |
| oblouk | `M9.4 30 A22.6 22.6 0 0 1 54.6 30`, tah 3.1; archivolta `M14.2 30 A17.8 17.8 0 0 1 49.8 30`, tah 1.1 |
| kupole | makovice `cy 1.15 r 0.95`, klenba `y 4.2`, sokl `y 4.1` — **nad** vnější hranou oblouku (`y 5.85`), jinak se schová za něj |
| pilíře | dřík `x 6.8 / 52.0, š 5.2, y 30.5–53.5`; hlavice a patka `x 5.4 / 50.6, š 8.0, v 1.9` |
| sloupy | `x 15.8` s krokem `6.8`, šířka `5.2`, patka na `y 56`, nejvyšší 26 jednotek |

- Kreslí se přes `currentColor` (`src/components/Znacka.astro`), takže bere barvu z místa, kde stojí, a funguje ve všech třech paletách i v tmavém motivu bez druhé varianty. Zlatá jde přes `var(--zlata, currentColor)` — kdyby token chyběl, značka zůstane celá, jen jednobarevná.
- `public/favicon.svg` má tentýž tvar s natvrdo zapsanými barvami — favicon nemá odkud barvu zdědit. **Když se změní jedno, musí se i druhé.**
- **Favicon musí být platné XML.** Komentář v SVG nesmí obsahovat `--`, takže se v něm názvy tokenů píšou bez prefixu (`zlata`, ne `--zlata`). Předchozí verze byla kvůli tomu měsíce nevalidní a prohlížeč ji vůbec nevykreslil; chyba je tichá. Ověřit `python3 -c "import xml.dom.minidom,sys; xml.dom.minidom.parse('web/public/favicon.svg')"`.
- V hlavičce stojí značka vlevo od jména; jméno se dál sází serifem („Naše Mariánky" plus slabší „v přehledech"). Značka jméno nenahrazuje.
- Držet čitelnost v 16 px. Kdo přidá detail, který se v této velikosti slije, značku zhorší. Proto jsou hlavice sloupů schválně tlusté (1.8 jednotky) — cokoliv jemnějšího zmizí.

### Lázeňská paleta — výchozí

Barvy města: modrá pramene, zlatá kolonády, bílý papír. **Je to výchozí sada** — tokeny stojí v holém `:root`. Původní zelená identita zůstává dostupná jako volba pod stampem `data-paleta="kolonada"`; přepínač motivu ji nabízí jako čtvrtý stav (podle systému → světlý → zelená kolonáda → tmavý).

```css
--paper: #F4F7FB;  --surface: #FFFFFF;  --surface-2: #EEF3F9;
--ink: #131922;  --ink-soft: #48525F;  --ink-faint: #76818F;
--rule: #D7E0EA;  --rule-soft: #E6ECF3;  --accent: #1A4E8F;
--zlata: #E9A900;  --zlata-svetla: #FBEEC2;  --modra-svetla: #DFEAF7;
```

Pravidla, která u ní platí:

- **Barvy grafů se nemění.** `--g1…--g6` a `--r1…--r8` jsou ověřené validátorem; přebarvit je kvůli sladění s modrou by tu validaci zahodilo.
- **Žlutá nikdy nenese text.** Na bílém papíru má kontrast pod 3:1. Smí být linka, podtržení a plocha — ne písmo.
- **Je to světlá sada.** S tmavým motivem se vylučuje, jinak by vznikl modrý text na tmavém pozadí. Hlídá to přepínač: při volbě „lázeňský" se nastaví `data-theme="light"` a `data-paleta="lazne"` zároveň.
- **Zelená identita zůstává dostupná.** Kdo ji má radši, přepne se na ni; zlatá v ní ustupuje mechové zelené, ať pruh pod hlavičkou nekřičí.
- **Detail dělá lázeňský vzhled, ne jen barva.** Zlatý pruh pod hlavičkou, zlatá linka u úvodního odstavce, zlatý vlas pod nadpisem sekce a **arkáda kolonády jako předěl** (`.kolonada-predel`). Arkáda se kreslí maskou nad `--zlata`, takže barvu bere z palety a funguje i v tmavém motivu — obrázek s napevno zapsanou barvou by v jednom z motivů svítil nebo zmizel.
- **V tmavém motivu se zlatá ztlumí** na `#b98c17`. Na tmavém podkladu by jinak svítila víc než obsah.

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
**Heatmapa.** Řádky = protistrana (řazeno od **nejnovější poslední smlouvy**, při shodě podle objemu), sloupce = rok, sytost buňky = objem (sekvenční ramp). Původně se řadilo od roku první smlouvy; tím ale nahoře stály firmy z devadesátých let a čtenář, kterého zajímá dnešek, musel k současným dodavatelům rolovat na konec.

**Osa let běží od aktuálního roku doleva doprava do minulosti** (2026, 2025, …, 1994). Je to vědomá výjimka z pravidla „čas zleva doprava" (§3.7) a platí JEN pro tuhle heatmapu: graf je široký přes tři obrazovky telefonu a vidět je z něj jen levý kraj — kdyby tam stál rok 1994, čtenář by se k současnosti musel dorolovat, a přesně na současnost se ptá. Směr osy musí být napsaný v popisu grafu; časové osy a spojnicové grafy trendů zůstávají chronologické, tam by obrácení lhalo o vývoji.

Nad osou let jsou **pásma volebních období** se jmény starostů. Tři pravidla:

- **Význam nesou roky a jména (text), ne barva.** Střídavý podklad pásma jen odděluje sousedy; kompletní jména se stranami stojí ve větě pod grafem.
- **Podklad pásma nikdy nezasahuje do buněk** — tónovat celé sloupce by posunulo vnímané odstíny rampy a heatmapa by lhala o částkách. Mezi obdobími je jen tenký svislý předěl.
- **Rok voleb patří končícímu období.** Komunální volby jsou na podzim, většinu roku úřadovalo staré vedení — a musí to být napsané u grafu, ne jen v kódu (`web/src/lib/obdobi.ts`).

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

Totéž platí i mimo osu, kdekoliv stojí odhad vedle doloženého údaje. Na `/komise` je vedle sebe „usnesení rady jmenuje tuhle komisi i datum jejího jednání" (citace ze zdroje) a „komise doporučila něco, co zní jako pozdější usnesení" (náš dohad). Rozdíl nese **tvar rámečku štítku**: `znacka--dolozeno` má plnou linku, `znacka--odhad` přerušovanou — a slovo „odhad" je i v textu štítku, ne jen v jeho vzhledu. Kdo štítek nevidí, musí se to dočíst.

Když je na ose hodně událostí, nekresli je jako jednotlivé značky: **900 překrytých koleček neříká nic**. Shlukuj je a velikost značky odvoď od počtu.

U osy jedné entity (osoba, firma, téma) uvádět, z jakých zdrojů se skládá — jinak vypadá jako úplný obraz, ačkoliv obsahuje jen to, co je v našich datech.

### 3.8 Znaky sekcí a grafický rozcestník

Rozcestník je grafická navigace na úvodní stránce. Na telefonu nese význam obraz a krátký název, od 34 rem výš přibývá popis. Znak sekce se opakuje u nadpisu té stránky, aby čtenář poznal, že je tam, kam klikl.

**Znak není ikona.** Projekt nemá ikonovou sadu a mít ji nemá — obrazová složka je výhradně datová. Znak je miniaturní graf ze skutečných dat té sekce: sloupce ročních výdajů u peněz, skutečná hranice katastru z RÚIAN u mapy, 21 teček u zastupitelstva. Kdo sem vloží piktogram, mění identitu, ne detail.

Nepřekročitelná pravidla:

- **Znak nesmí kreslit konstantu.** Když má řada ve všech bodech stejnou hodnotu, netvrdí vývoj — patří tam číslo, ne graf. Hlídá to `kontrola.py`. (Vzniklo z chyby: znak hlasování ukazoval „podíl schválených návrhů", jenže zdroj zveřejňuje jen schválená hlasování, takže podíl byl vždy 100 %.)
- **`null` je mezera, nula je nula.** Chybějící hodnota dostane tečkovanou patku u osy, aby mezera nešla přečíst jako konec dat. Nulová hodnota dostane 1px proužek, aby se nula a neznámo nekreslily stejně, tedy nijak.
- **Znak sám nikdy nenese informaci.** Vedle něj je vždy číslo a slovo; pro čtečku je `aria-hidden`, protože totéž je vedle napsané.
- **Sekce bez dat dostane přerušovaný rám**, ne prázdnou plochu. Prázdná plocha by tvrdila, že sekce je prázdná — přitom jen nevíme.
- **Druhá série se kreslí na vrcholu sloupce**, ne vedle něj, když je částí celku (nejednomyslná hlasování z celkových). Vedle by to byly dvě veličiny a součet by přestal platit.
- **Žádný runtime JavaScript.** SVG vzniká při buildu z `data/znaky/sekce.json`, který počítá `pipeline/znaky_sekci.py`.

### 3.9 Schémata

Osm diagramů na `/diagramy`, plus výběr na stránkách sekcí. Data počítá `pipeline/diagramy.py`, SVG skládá `web/src/lib/diagramy.ts` při buildu.

Typy: `strom` (holding, vedení), `tok` (týdenní běh, řetěz usnesení → smlouva), `sit` (osoby ↔ firmy, zdroje ↔ sekce), `mysl` (číselník témat), `erd` (datový model).

Nepřekročitelná pravidla:

- **Schéma se nekreslí v kreslicím nástroji.** Obrázek nakreslený jednou by za měsíc tvrdil něco, co už neplatí, neuměl by tmavý motiv a musel by se odněkud načíst. Schéma vzniká z dat při buildu.
- **Ke každému schématu patří tabulka s týmiž údaji.** Není to doplněk jako u grafů — schéma se nedá přečíst čtečkou, vytisknout na úzký papír ani zobrazit na telefonu bez rolování. Tabulka nese totéž a je čitelná vždycky.
- **Zjištěné se nesmí plést s tvrzeným.** Šest schémat je z dat města; mapa zdrojů a datový model stojí na `config/diagramy.json`, což je znalost o projektu. U obou je to napsané.
- **Přerušovaný obrys znamená „nepatří do celku" nebo „je to odhad".** Nemocnice mimo holding, nízká jistota u řetězu, nejednoznačná identita u propojení. Totéž pravidlo jako u značek na časové ose (§3.7).
- **Barvy jsou tokeny, nikdy hexy**, a legenda musí používat tytéž klíče, jaké nesou data. (Vzniklo z chyby: legenda měla klíče `dodavatel` a `bez-vazby`, data `obchoduje-s-mestem` a `bez-vazby-na-mesto` — vzorky vyšly bílé.)
- **Schéma se nezmenšuje pod čitelnost popisků.** Kreslí se na pevnou šířku a plocha roluje do strany (`.diagram-plocha`), stejně jako grafy. Rolovatelná oblast musí být dosažitelná klávesnicí.
- **V síti se dá klepnout na uzel** a zvýraznit jeho spojení; funguje to oběma směry a klávesnicí (`role="button"`, Enter i mezerník, Escape ruší). Nevybrané uzly se **ztlumí, nezmizí** — skryté by tvrdily, že tam nic není, a je to napsané i v textu nad schématem. Je to jediná výjimka z pravidla „nic se nezeslabuje opacitou": bez ztlumení nemá výběr žádný účinek. Barvu uzlu výběr nemění, protože barva nese vztah firmy k městu.
- **Sloupce sítě se řadí barycentricky**, ne abecedně. Abecední pořadí vyrobilo z 72 čar klubko, ve kterém nešlo nic sledovat. Pořadí je pouze vizuální — nic neskrývá.
- **Cizí data jdou do SVG výhradně přes `esc()`.** Názvy firem, jména a odbory pocházejí z cizích zdrojů.

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
| `/komise` | Komise a výbory, co navrhly a co s tím rada udělala — doložené odděleně od odhadu |
| `/penize` | Dashboard s grafy výše |
| `/penize/[ico]` | Detail protistrany — co dostala a kdy |
| `/hospodareni` | Rozpočet města z Monitoru státní pokladny: příjmy a výdaje po letech, saldo, struktura, plnění plánu, majetek a dluhy, výkazy organizací. Covidová léta 2020–2021 jsou v grafech vyznačená pásmem s popiskem a větou s čísly. Vše po konsolidaci; rozpracovaný rok se do meziročních grafů nekreslí |
| `/zpravodaj` · `/zpravodaj/[id]` | Archiv článků |
| `/temata/[tema]` | Časové osy témat |
| `/hledat` | Fulltext přes vše (Pagefind) |

## 5. Provoz

- Astro, statický výstup, deploy na **Vercel**.
- Fulltext **Pagefind** — musí zvládat českou diakritiku.
- **Veřejný přehled, bez přihlášení.** Dřív neveřejnost zajišťovala neznámá adresa a v hlavičce stálo `noindex`; portál je teď veřejný záměrně — kdo hledá, jak zastupitel hlasoval, má sem dojít z vyhledávače. `robots.txt` pouští roboty dovnitř, `astro.config.mjs` má `site` a generuje se sitemap.
- **Co veřejnost mění v obsahu.** Dvě věci se kvůli ní drží jinak:
  - **Jméno hosta komise se nezobrazuje.** V datech zůstává, na stránce ne. Stopa je o organizaci; jméno konkrétní osoby vedle částky ze smluv jejího zaměstnavatele by bylo narážkou, ne zjištěním.
  - **Spojení s nízkou jistotou se nerozbaluje samo.** Měřením vyšlo, že zhruba každé druhé je vedle. Vedle jistějších by se četlo jako rovnocenné zjištění a dá se vyfotit bez štítku „odhad" — proto je pod `<details>` a v jeho popisku stojí naměřená úspěšnost.
- `robots.txt` s `Disallow: /` a `<meta name="robots" content="noindex, nofollow">` na každé stránce, aby se adresa nedostala do vyhledávačů sama od sebe.
- Respektovat `prefers-reduced-motion`, viditelný stav focusu, tabulky ve vlastním `overflow-x: auto` kontejneru.
