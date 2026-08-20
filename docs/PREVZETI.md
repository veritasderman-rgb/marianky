# Zadání pro Claude Code: občanský přehled pro obec XY

**Jak převzít tenhle nápad pro jiné město.**
Verze 1.0 · 19. 8. 2026

Tenhle soubor je **zadání, které se dá podat Claude Code jako první zpráva** —
stačí nahradit „obec XY" jménem konkrétní obce. Zbytek repozitáře je referenční
implementace pro Mariánské Lázně; ber ji jako vzor, ne jako šablonu k okopírování.
Každá radnice zveřejňuje jinak a **90 % práce je v tom zjistit, jak zveřejňuje ta
tvoje.**

---

## 0. Co se staví

Veřejný web, který na jednom místě sesbírá a **propojí** to, co obec zveřejňuje
rozházeně a v PDF: usnesení rady a zastupitelstva, jmenovitá hlasování, rozpočet,
smlouvy z registru, zápisy z komisí, úřední desku, odpovědi na žádosti podle
zákona 106/1999 Sb., volební výsledky, zpravodaj.

**Hodnota není v tom, že se data zobrazí. Je v tom, že se dají proklikat:**
od jména zastupitele k jeho hlasování, od hlasování k usnesení, od usnesení
ke smlouvě, od smlouvy k firmě a od firmy zpátky k lidem. Každý z těch skoků
existuje ve zdrojích, ale žádný zdroj ho neudělá za tebe.

Statický web (žádný server, žádná databáze, žádné cookies), fulltext nad
předgenerovaným indexem, hosting zdarma. Data v gitu jako JSON, aby šlo vidět,
kdy se co změnilo.

---

## 1. Zásady, které se nesmí porušit

Tyhle čtyři jsou dražší, než vypadají — každá vznikla z chyby, která se
na webu už objevila.

### 1.1 Scraping dělá kód, porozumění dělá model

Python jenom stahuje, normalizuje a počítá. **Nic nedopočítává a nic nehádá.**
Když ve zdroji chybí částka, je `null`, ne nula a ne odhad. Interpretace
(„tohle usnesení souvisí s tímhle doporučením komise") patří do zvlášť
označené vrstvy, ne do sběru.

### 1.2 Prázdno není nula

Nejčastější a nejzákeřnější chyba celé kategorie. „Nezjištěno" se nesmí uložit
jako `0` a nesmí se nakreslit jako nulový sloupec — čtenář to přečte jako
„nic tam není", což je tvrzení o skutečnosti, které nemáš podložené.
Rozlišuj tři stavy: **hodnota / nula / neznámo**, a to v datech, v grafu
i v textu. Napiš na to kontrolu (viz §7).

### 1.3 Odhad musí být označený jako odhad — a změřený

Jakmile něco páruješ heuristikou (komise → rada, usnesení → smlouva),
vznikají dvě různé věci a **nesmí skončit v jedné tabulce**:

- **doloženo** — zdroj to říká sám (usnesení cituje komisi, program jednání ji jmenuje),
- **odhad** — spočítali jsme, že to k sobě nejspíš patří.

U odhadu ulož míru jistoty a **změř, jak často sedí**: udělej ruční vzorek
30–40 případů, rozsuď je sám a ulož výsledek do repozitáře jako `config/vzorek_*.json`.
Bez toho čísla je „vysoká jistota" jen slovo. V referenční implementaci vyšlo
23/35 celkově, ale 3/3 u nejvyšší třídy a 10/19 u nejnižší — a **ta nejnižší
je proto na webu schovaná pod rozbalovátkem s uvedenou úspěšností**.

### 1.4 Odkaz na zdroj u každého čísla

Cokoliv, co web tvrdí, musí jít ověřit bez nás — odkazem na konkrétní PDF,
smlouvu nebo záznam. Když to nejde odkázat, radši to nepiš.

---

## 2. Fáze 0 — rešerše. Nepiš zatím žádný kód.

Nejdřív zjisti, **co obec XY vůbec zveřejňuje a v jaké podobě.** Tohle rozhodne
o všem ostatním a udělá se to rychleji ručně než na třetí přepis scraperu.
Projdi a zapiš do `docs/datove-zdroje.md` u každé položky: URL, formát, rozsah
od kdy, jak se stránkuje, jestli je za JS a jestli má stabilní ID.

**Povinné minimum:**

1. **Usnesení rady a zastupitelstva** — bývá vlastní portál (`usneseni.*`,
   Gordic, VERA, Marbes, T-WIST) nebo jen složka PDF na webu. Zjisti, jestli
   existuje HTML výpis bodů, nebo jen sken zápisu — to je rozdíl mezi projektem
   na týden a na měsíc.
2. **Jmenovitá hlasování** — publikuje je jen menšina obcí. Když existují,
   jsou to nejcennější data celého webu, protože jako jediná spojují jméno
   s rozhodnutím. Když neexistují, **nepředstírej je** a napiš na web, že chybí.
3. **Úřední deska** — skoro vždy má strojové rozhraní podle otevřených
   formalizovaných dat (`/deska` + JSON-LD). Zkus to dřív, než začneš parsovat HTML.
4. **Rozpočet a rozpočtová opatření** — a hlavně: je částka v PDF u bodu,
   nebo až v příloze? (Viz past §8.3.)
5. **Zápisy z komisí a výborů** — nejčastěji úplně chybí; když jsou, bývají
   v ZIP archivech (viz §8.1).
6. **Žádosti podle zákona 106** — rejstřík odpovědí. **Pozor na jména žadatelů,
   §6.**
7. **Zpravodaj obce** — archiv PDF, dobrý zdroj kontextu a jmen.
8. **Volby** — ČSÚ (`volby.cz`) má stabilní strojová data po okrscích pro
   celou ČR, takže tady se nic nevymýšlí.
9. **Registr smluv** — přes Hlídač státu, §4.
10. **Seznam orgánů a lidí** — rada, zastupitelstvo, komise, výbory, obsazení
    a od kdy do kdy. Bez tohohle číselníku nejde nic spárovat.

**Zapiš i to, co obec nezveřejňuje.** Ta věta patří na web — je to zjištění,
ne mezera. („Komise dopravy za tři roky nezveřejnila jediný zápis.")

**Rozsah:** rozhodni, kolik let dozadu. Referenční implementace jede od roku 2016,
protože tehdy vznikl registr smluv.

---

## 3. Fáze 1 — sběr

Struktura, která se osvědčila:

```
scrapers/    stahování a normalizace, jeden modul na zdroj
pipeline/    zpracování a propojování napříč zdroji
lib/         sdílené (fetch s cache a retry, PDF, ZIP, logování)
data/        výstupní JSON, verzované v gitu
config/      číselníky, které píše člověk (orgány, lidé, tagy, vzorky)
.cache/      stažené originály, mimo git
web/         Astro
kontrola.py  kontroly před publikací
```

**Pravidla sběru:**

- **Cachuj originály na disk** (`.cache/`) a nikdy nestahuj podruhé to, co už máš.
  Během vývoje přeparsuješ tentýž PDF padesátkrát; radnici zatížíš jednou.
- **Buď slušný:** rozumný interval mezi požadavky, vlastní `User-Agent`, respektuj
  `robots.txt`. Jsi host.
- **Když zdroj selže, ulož to jako stav**, ne jako prázdná data. Web musí umět
  napsat „zdroj se nepodařilo načíst" místo toho, aby tvrdil, že tam nic není.
- **Stabilní ID.** Odvoď je ze zdroje (číslo usnesení + datum), ne z pořadí
  v seznamu — jinak se ti při dalším běhu přečíslují všechny odkazy.

**PDF:** `pdftotext` **bez** `-layout`. S `-layout` sice text vypadá líp, ale
rozpadne se do sloupců a věty se přeruší uprostřed, což zabije každý regex.
Napiš si funkci `potrebuje_ocr()`, která pozná sken (málo textu na stránku),
a **skeny přiznej**, ne zahoď. V referenční implementaci jich je 82.

---

## 4. Napojení na Hlídač státu

[Hlídač státu](https://www.hlidacstatu.cz) je česká nezisková organizace, která
od roku 2016 sbírá a **propojuje** data o hospodaření státu: registr smluv,
dotace, veřejné zakázky, insolvence, rejstřík trestů právnických osob,
sponzorské dary politickým stranám, platy politiků, rozhodnutí ÚOHS a legislativu
v přípravě. Indexuje je přes IČO a jména osob — což je přesně to propojení,
které pro obec potřebuješ a sám bys ho nepostavil.

**Dvě cesty k datům, obě používej:**

1. **REST API** `https://api.hlidacstatu.cz/Api/v2` — token zdarma po registraci.
   Tohle je hlavní cesta pro hromadnou sklizeň. Token drž v `.env` mimo git
   a **nikdy ho necommituj** (ověř si i historii).
2. **MCP server** `mcp__hlidac_statu__*` — nástroje, které volá přímo model.
   Vhodné na rešerši, dohledání jednoho subjektu, ověření sporného případu.
   Na sklizeň tisíců smluv se nehodí (v referenční implementaci pokryl 6 %
   a musel se nahradit REST API).

**Postup:**

1. `find_legal_entity_by_name` → IČO obce.
2. **Sestav seznam sledovaných IČO**, ne jen obec: příspěvkové organizace
   (školy, muzeum, technické služby) a **městské obchodní společnosti**.
   Hlídač má vlastní pojem „holding", ale ten obchodní společnosti neobsahuje —
   ty si musíš dohledat sám a rozdíl **napsat na web**, jinak čtenář uvidí
   výseč a bude ji číst jako celek.
3. `search_contracts` / `search_subsidies` / `search_public_tenders` po IČO,
   stránkovaně, do lokálního JSON.
4. `get_kindex_for_legal_entity` — roční známka A–F podle rizikovosti smluv.
   **Přebírej ji i se zdůvodněním a nepřepočítávej.** Je to hodnocení Hlídače,
   ne tvoje, a tak to musí být na webu napsané.
5. `find_party_sponsoring_by_person` / `_by_company` — sponzorské dary. Tohle
   je citlivé: jde o zákonně zveřejněné údaje, ale kontext dodáváš ty, tak ho
   dodej opatrně a bez závěrů.
6. `get_business_with_government`, `find_insolvency_records_by_ico`,
   `find_criminal_records_by_ico` — doplňkové, k profilům firem.

**Směr peněz nepřepisuj.** Pole `platce` a `prijemce` ber tak, jak je
zveřejňovatel zapsal. U nájmů a prodejů bývá obec vedená jako plátce, i když
peníze inkasuje. Je to vada zdroje a opravovat ji dohadem znamená udělat
z dat dohad. Přiznej to v metodice.

**Poděkuj.** Bez Hlídače tenhle typ projektu neexistuje. Dej mu na webu vlastní
oddíl, ne řádek v patičce — a napiš k tomu, že za tvým webem nestojí.

---

## 5. Další MCP servery a zdroje, které se hodí

- **ARES / veřejný rejstřík** — názvy firem, sídla, statutární orgány. Volné API,
  nepotřebuje MCP.
- **ČSÚ, `volby.cz`** — volební výsledky po okrscích, demografie. Strojová data.
- **ČÚZK, RÚIAN, OpenStreetMap** — mapové vrstvy, adresy, parcely. U map vždy
  uveď zdroj a licenci **u té mapy**, ne globálně.
- **ČHMÚ** — výstrahy, když chceš stavový pás.
- **GitHub MCP** — když projekt poběží jako veřejný repozitář s PR review.
- **Vercel / Netlify MCP** — nasazení a kontrola buildu.

**Co nescrapovat:**
**Registr oznámení o střetu zájmů** (`cro.justice.cz`) je za registrací
a zákon 159/2006 Sb. omezuje další zpracování údajů z něj. **Odkazuj na něj,
nestahuj ho.** Vazby na firmy si postav z veřejného rejstříku a z Hlídače.

---

## 6. Právo a etika. Rozmysli dřív, než sbíráš.

Zdrojová data projektu jsou veřejná (git), takže **co jednou sesbíráš,
zveřejníš** — filtrovat až při zobrazení je pozdě.

- **Jména žadatelů podle zákona 106 neukládej.** Obce je běžně nechávají
  v názvu souboru i v textu odpovědi. Ptát se úřadu je zákonné právo a přehled
  z jeho výkonu nesmí udělat dohledatelnou stopu. **Odstraň je už při sběru.**
  Názvy organizací (spolek, advokátní kancelář, komora) zůstávají — to je
  jednání instituce. Jméno úředníka, který odpověděl, taky: to je výkon funkce.
- **Jména hostů na komisích** zpracuj opatrně — organizaci ano, jméno fyzické
  osoby na veřejném webu spíš ne.
- **Volení funkcionáři a jejich hlasování jsou veřejná věc.** Tady necenzuruj,
  to je jádro celého projektu.
- **Nehodnoť.** Web ukazuje, co se stalo, s odkazem na zdroj. Slova jako
  „podezřelý", „klientelismus", „netransparentní" na něm nemají co dělat —
  jednak to není doložené, jednak to čtenáře odvádí od dat.
- **Napiš viditelně, že to není web obce.** Do patičky i na stránku o zdrojích.
- **O čtenáři sbírej co nejmíň — a co sbíráš, napiš na web.** Žádná cizí písma,
  žádné cookies. Nulová analytika je nejjednodušší a je to jistý způsob, jak
  nemuset řešit lištu se souhlasem.

  Referenční implementace to nakonec nedodržela: měří návštěvnost přes Vercel
  Web Analytics, protože běží na jejich hostingu zdarma. Je to bez cookies
  a bez profilů napříč návštěvami, ale ukládá se u toho i přibližné místo
  a verze prohlížeče. **Podstatné je, že to na webu stojí napsané** — věta
  „o čtenáři se nic nesbírá" v patičce přežila zapnutí měření o několik hodin
  a byla to nejhorší chyba dne. Na webu, který stojí na ověřitelnosti, se
  nelže ani o sobě: buď neměř, nebo měření popiš dřív, než ho zapneš.

---

## 7. Fáze 3 — web a vizualizace

Statický generátor (referenční implementace je Astro 5), fulltext přes Pagefind
nad hotovým buildem, **grafy jako SVG generované při buildu** — žádná grafová
knihovna v prohlížeči.

**Věci, které se snadno podcení:**

- **Rozpočet DOM uzlů.** Velikost přenesených dat neříká nic; brotli zabalí
  megabajt HTML na pár desítek kilobajtů, ale prohlížeč pak staví čtvrt milionu
  uzlů a stránka se **neotevře**. Přesně to se stalo `/hlasovani` (250 289 uzlů).
  **Napiš kontrolu nad `dist/`** se stropem (osvědčilo se 45 000, varování na 25 000)
  a dlouhé seznamy sázej po dávkách.
- **Tři stavy motivu, ne dva.** `:root` světlý, `@media (prefers-color-scheme: dark)`
  a k tomu `:root[data-theme="dark"]`, aby ruční přepnutí vyhrálo v obou směrech.
  **Žádná barva nesmí být definovaná jen uvnitř media query** — v systémovém
  režimu by chyběla.
- **Paleta bezpečná pro barvoslepé** a **barva nikdy sama.** Stavová tečka
  vždycky s textovým popiskem vedle. Rozdíl mezi „doloženo" a „odhad" nes
  tvarem rámečku *a* slovem v textu, ne odstínem.
- **Čeština.** Skloňování počítaných podstatných jmen (1 zápis / 2 zápisy /
  5 zápisů) napiš jako funkci a používej ji všude. Uvozovky „takhle".
  Řazení podle `localeCompare('cs')`, jinak skončí Ž před A.

---

## 8. Kontroly před publikací

Napiš `kontrola.py`, které se pouští před každým nasazením a které **řve, když
data nedávají smysl** — ne když spadne kód. Osvědčené kontroly:

- žádná částka nepřesahuje **strop odvozený z rozpočtu té konkrétní obce**
  (a zapsaný v `config/`, ne natvrdo v kódu). Vesnice s rozpočtem 40 milionů
  a Brno mají jiný řád; univerzální „obec nemá miliardy" by Praze, Brnu nebo
  Ostravě zablokovalo publikaci na správných datech,
- neznámé údaje nejsou uložené jako nula,
- data jsou čerstvá (poslední jednání není starší než N dní),
- každý, kdo hlasoval, má profil (jinak jsou odkazy slepé),
- všechny tagy jsou z číselníku,
- všechny geo body padly do okolí obce,
- odhady nemíří zpátky v čase: **datum usnesení rady nesmí být dřívější než
  datum doporučení komise**, které na něj má navazovat. Platný sled je
  komise → rada; obrácené pořadí znamená, že se pár spároval špatně,
- rozpočet DOM uzlů nad `dist/`.

Kontrola, která jen loguje, není kontrola — musí umět build zastavit.

---

## 9. Pasti, na které jsme narazili

Ušetří ti to pár dní.

**9.1 ZIP archivy.** Zápisy bývají v ZIP. Jména souborů v nich jsou často
v **CP852** (nebo CP437), ne v UTF-8, a z macOS chodí v **NFD** — takže
`z[áa]pis` nenajde „Zápis". Normalizuj na NFC. Archiv poznávej podle **obsahu**
(magické bajty `PK`), ne podle přípony. A když v archivu hledáš hlavní dokument,
**nezkoušej záložní kandidáty napříč třídami souborů** — jinak uložíš prezentaci
jako zápis z jednání. (Přesně tohle se stalo.)

**9.2 Regexy nad češtinou potřebují hranice slov.** `[žz][áa]d[áa]` bez `\b`
matchne „**Zadá**vací dokumentace" a udělá z ní žádost komise. Třináct položek
bylo takhle špatně. Totéž pořadí alternativ: `nesouhlasí` musí být testované
**před** `souhlasí`.

**9.3 Nepřijaté návrhy nejsou doporučení.** „PRO: 4 PROTI: 2 … Navržené usnesení
nebylo přijato" znamená opak toho, co regex na „doporučuje" najde. Zaveď
tříhodnotový stav *přijato / nepřijato / neznámo*. A když hledáš zamítnutí
v okolí bodu, **omez okno koncem bodu**, ne pevným počtem znaků — jinak se
podíváš do dalšího bodu a označíš schválený návrh za zamítnutý.

**9.4 Částka u bodu nemusí být částka rozpočtu.** Když je výše až v příloze,
číslo u bodu je něco jiného. Nevydávej ho za rozpočet.

**9.5 Párování orgánů podle jména selže na překlepech.** „Komise lázeňství,
CR a UNESCO" versus „…cestovního ruchu…" — 87 zápisů se ztratilo. Páruj:
nejdřív přesná shoda normalizovaného názvu, teprve pak překryv klíčových slov,
a **při remíze radši nespáruj nic**. A účast páruj na **konkrétní komisi**,
ne jen na jméno člověka — jinak se docházka z jedné komise objeví u druhé.

**9.6 Nedělej si závěry o datech, která jsi neotevřel.** Tvrdil jsem, že
47 nerozebraných zápisů jsou skeny. Nebyly — všechny měly textovou vrstvu,
jen neměly strukturu. Než něco napíšeš na web jako důvod, ověř to na datech.

**9.7 XML komentář nesmí obsahovat `--`.** Favicon byl kvůli názvu CSS proměnné
v komentáři měsíce nevalidní a prohlížeč ho nevykresloval vůbec. Chyba je tichá.
Ověřuj SVG parserem.

---

## 10. Provoz

- **Jeden běh týdně** stačí a je slušný k radnici. Pusť sběr, kontroly, build,
  nasazení; když kontrola spadne, nenasazuj.
- **Data verzuj v gitu.** Diff mezi běhy je sám o sobě informace — je z něj
  vidět, kdy radnice něco přepsala nebo stáhla.
- **Piš, kdy byla data stažená**, u každé sekce. „Aktuální" bez data je lež
  s odloženou splatností.
- **Počítej s tím, že se zdroj rozbije.** Ne „jestli". Proto ty stavy místo
  prázdných polí.

---

## 11. První kroky, kdyby sis nevěděl rady

1. Udělej §2 (rešerši) a zapiš ji do `docs/datove-zdroje.md`. Nic víc.
2. Ukaž ji člověku, který obec zná, a nech si říct, co chybí.
3. Vezmi **jeden** zdroj — ideálně usnesení — a dotáhni ho celý: sběr, kontrola,
   stránka na webu, odkaz na zdroj u každého bodu.
4. Teprve pak přidávej další. Šest napůl hotových zdrojů je horší než jeden
   hotový, protože u napůl hotového nepoznáš, jestli je prázdný, nebo rozbitý.
