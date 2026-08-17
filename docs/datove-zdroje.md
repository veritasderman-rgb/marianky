# Inventář datových zdrojů

Technická příloha k [`ZADANI.md`](../ZADANI.md). Všechny údaje ověřeny **17. 8. 2026**.

Účel dokumentu: než někdo začne psát sběrač, ať ví, co ho čeká — kde je JavaScript, kde je potřeba hlavička, kde je PDF sken a kde ne.

---

## 1. usneseni.muml.cz — portál usnesení

**Priorita: nejvyšší.** Nejhodnotnější a nejlépe strukturovaný zdroj projektu.

### Endpointy

| URL | Obsah |
|---|---|
| `https://usneseni.muml.cz/rada/usneseni` | Usnesení rady |
| `https://usneseni.muml.cz/rada/podklady` | Podklady k jednání rady |
| `https://usneseni.muml.cz/rada/hlasovani/usneseni` | Hlasování — dále členěno na *Strany* a *Členy* |
| `https://usneseni.muml.cz/zastupitelstvo/usneseni` | Usnesení zastupitelstva |
| `https://usneseni.muml.cz/zastupitelstvo/podklady` | Podklady k jednání zastupitelstva |

### Technické poznámky

> **Opraveno po implementaci.** Původně tu stálo, že obsah je přímo v HTML. Není — úvodní stránka jen nese kostru, samotné výpisy jedou AJAXem. Níže je stav ověřený stažením celého archivu.

- **Výpisy jedou přes AJAX**, ne z HTML: `POST /{organ}/ajax/list/…` s parametry `filter[...]`.
- **Nutné jsou DVĚ nestandardní hlavičky**, každá jinak selže:
  ```
  bez User-Agent                     → 503
  bez X-Requested-With: XMLHttpRequest → 500
  ```
  `lib/core.fetch()` posílá User-Agent sám; druhou hlavičku si volající předá parametrem `headers=`.
- **Odpověď nemá v `Content-Type` charset.** `requests` pak podle staré normy hádá ISO-8859-1 a čeština se rozsype na mojibake — a protože je výsledek platný řetězec, projde to bez chyby až do dat. `core.fetch()` to už řeší (`_dekoduj`): když charset chybí, zkouší UTF-8, pak windows-1250 a iso-8859-2.
- **`recordsTotal` v odpovědi je při filtrování nepravdivý** — počítej délku pole `data`.
- **Keep-alive se vyplatí**: sdílená session dělá 0,26 s na stránku místo 0,67 s. `core.fetch()` ji drží.
- Jednání jsou identifikována dvojicí **datum + č. j.** — vhodný primární klíč.

### Rozsah archivu (ověřeno staženým archivem)

| | rada | zastupitelstvo | celkem |
|---|---|---|---|
| jednání | 579 | 111 | **690** |
| bodů usnesení | 10 289 | 2 601 | **12 890** |
| hlasování | 9 801 | 2 548 | **12 349** |
| jmenovitých hlasů | | | **121 935** |

**Archiv sahá k roku 2012** u obou orgánů — o čtyři roky hlouběji, než tu stálo původně. Rada zasedá zhruba jednou za dva týdny, zastupitelstvo zhruba 6× ročně.

Číslování č. j. se resetuje s volebním obdobím, takže `č. j. 28` samo o sobě není unikátní — klíč je `(rok, č. j.)`. **Pozor na výjimku:** rada má 22. 11. 2022 jednání č. j. **0** zařazené až za č. j. 3, takže naivní detekce resetu podle „menší než minule" tam vyrobí falešné volební období. Sběrač detekuje propad ≥ 10.

### Kvalita a zvláštnosti dat

- **Jmenovité hlasy jsou u 100 % hlasování** (12 349 z 12 349), 56 osob, žádný hlas bez uvedené strany. Křížová kontrola součtů proti souhrnům portálu: **0 nesrovnalostí**.
- **Portál rozlišuje 6 typů hlasu**, ne 5: přibývá *omluven*. Bez odděleného počtu omluvených a nepřítomných součty nedávají smysl.
- **Pole `vysledek` je prakticky jednohodnotové** — portál u všech 12 349 hlasování uvádí „schváleno". Hodnoty `neschvaleno`, `staženo` ani `odlozeno` se v archivu nevyskytují.
- **Ve čtyřech hlasováních zastupitelstva je proti víc hlasů než pro, a portál je přesto vede jako „schváleno"** (např. 731/18: 4 pro, 8 proti). Ukládá se, co zdroj tvrdí. Web na to musí brát ohled a nespoléhat na `vysledek` jako na pravdu — spolehlivější je porovnat počty hlasů.
- Částka je rozpoznána u 30,1 % bodů; jinde je `null`, protože v textu žádná není.
- 27 bodů (0,2 %) má prázdný text — ověřeno, že je prázdný i na zdroji, není to chyba parseru.

### Proč je hlasování klíčové

Sekce *Hlasování → Členové* dává **jmenovitá hlasování**. To umožňuje postavit hlasovací historii jednotlivých zastupitelů — funkci, kterou pro Mariánské Lázně jinde nenajdete. Je to nejsilnější věc, kterou celý portál nabídne.

---

## 2. muml.cz — oficiální web města

### Endpointy

| URL | Obsah |
|---|---|
| **`/urad/uredni-deska/`** | **Živá úřední deska — viz varování níže** |
| `/urad/uredni-deska-archiv/` | Archiv složek dokumentů (končí rokem 2025) |
| `/aktualne/zpravodaj-mesta/` | Archiv PDF zpravodaje (stránkovaný) |
| `/aktualne/novinky/` | Novinky |
| `/aktualne/kalendar-akci/` | Kalendář akcí |
| `/samosprava/zastupitelstvo/clenove-1/` | Seznam zastupitelů |
| `/samosprava/zastupitelstvo/terminy-zasedani/` | Termíny zasedání |
| `/samosprava/zastupitelstvo/online-prenos-jednani/` | Online přenos jednání |
| `/samosprava/vedeni-mesta/` | Vedení města |
| `/urad/povinne-informace/subjekt-obchodni-spolecnosti-81.html` | Obchodní společnosti města |
| `/kontakty/telefonni-seznam/` | Telefonní seznam úřadu |
| `/urad/dokumenty/strategicke-dokumenty/` | Strategické dokumenty |

### Tři věci, které tu byly špatně

**Úřední deska jsou DVĚ různé stránky.** `/urad/uredni-deska-archiv/`, kterou jsem tu původně uvedl jako *tu* desku, je jen **archiv složek dokumentů** a končí rokem 2025. Živá deska s dokumenty v zákonné lhůtě včetně všech letošních je **`/urad/uredni-deska/`** — jiná šablona, název kategorie v `<button>` místo `<a>`. Kvůli téhle záměně měl projekt data zaseklá v květnu 2025 a týdenní vydání muselo sekci hlásit jako zastaralou. Sbírat je potřeba **obojí**, rozlišené polem `deska`. Po opravě: 6 728 dokumentů, 2013–2026, 123 aktuálně vyvěšených.

**Kalendář akcí na muml.cz vůbec není.** `/aktualne/kalendar-akci/` je jen rozcestník s obrázkovým odkazem na turistický portál **`marianskelazne.cz/kalendar/`**, kde kalendář skutečně je. Výpis je „načítací": `?page=N` vrací kumulativně 13 + (N−1)·12 akcí, takže stačí jeden dotaz s vysokým `page`.

**IČO městských firem na webu jsou** — ne na přehledu, ale v detailu každé firmy: Infocentrum 25208438, TDS 25213261, Lázeňské lesy 64831086, DEVELOP CENTRUM 61776068, MĚSTSKÁ DOPRAVA 26412501. U Nemocnice je web opravdu neuvádí.

### Tempo: web má strop a je sdílený

Při stahování archivu novinek rychlostí **~2,5 dotazu za sekundu** server po několika tisících požadavcích přestal přijímat spojení — **plošně na celý web, ne jen na jednotlivé adresy**. Blokace trvala zhruba **90 minut** a dopadla i na souběžně běžící sběrače.

Ověřené udržitelné tempo je **~1,3 dotazu za sekundu**. `lib/core.fetch()` navíc drží minimální odstup 1,5 s mezi požadavky na `muml.cz`, sdílený přes soubor mezi procesy. **Kdo z muml.cz tahá hromadně, musí počítat s tím, že strop je společný pro všechny běžící moduly.**

### RSS neexistuje

Ověřeno, všechny varianty vracejí **404**:

```
https://www.muml.cz/rss              → 404
https://www.muml.cz/rss.xml          → 404
https://www.muml.cz/aktualne/novinky/rss → 404
```

**Důsledek:** vše se musí scrapovat z HTML a hlídat přes snapshoty (diff-monitoring). Zároveň je to argument pro vlastní RSS feed portálu — město ho nemá a lidem by se hodil.

### Územní plánování

Čtyři stránky, ne jedna:

| URL | Obsah |
|---|---|
| `/urad/uzemni-planovani/uzemne-planovaci-dokumentace-a-studie/` | Rozcestník, členěný **po obcích** — Mariánky jsou úřad územního plánování i pro 13 okolních obcí |
| `/urad/uzemni-planovani/novy-uzemni-plan-marianske-lazne/` | Nový územní plán — živý proces |
| `/urad/uzemni-planovani/uzemne-analyticke-podklady/` | ÚAP, 84 dokumentů |
| `/urad/uzemni-planovani/urad-uzemniho-planovani/` | Kontakty a agenda |

`/mesto/investice-a-rozvoj/uzemni-planovani/` je jen **zrcadlo rozcestníku** s totožným obsahem — zpracovávat podruhé nemá smysl.

**Kořenový výpis obce lže o kategoriích.** Vypíše všech 234 dokumentů, ale nadpis kategorie neopakuje při každé změně, takže vizuálně přiřkne jedenáct dokumentů cizí kategorii. Autoritativní je `<select>` na stránce obce — a je i úplnější, regulační plán města na rozcestníku vůbec není.

**Datum „Vloženo" u souboru je datum migrace webu** (u celého archivu změn shodně 25. 4. 2018), ne datum vydání dokumentu.

**Oznámení o vydání jsou skeny** — deset jednostránkových PDF s nulovou textovou vrstvou. Právě v nich je datum nabytí účinnosti, takže u změn 1–19 ho doložit nelze; archiv usnesení začíná až 2012.

**PDF z roku 2012 mají rozbité kódování** — vypadané háčky, „Zm ny .23". Pozná se to spolehlivě: zdravý český text má 3,5–4,7 % háčkovaných písmen, tyhle přesně 0 %.

**Past při dohledávání dat účinnosti:** hledat „nabylo účinnosti dne" v textových částech územního plánu vrací data **cizích předpisů** (zásady územního rozvoje kraje). Hledat se smí jen v dokumentech, které o vydání samy jsou — jinak vzniknou vymyšlená data, která vypadají doložená.

Město důsledně rozlišuje **„Územní plán *města* Mariánské Lázně"** (platný, z roku 2002) od **„Územní plán Mariánské Lázně"** (nový, pořizovaný). Ten rozdíl je jediné, co ta dvě usnesení odlišuje.

### Stahování souborů

Přílohy a PDF jdou přes **dva různé** skripty:

```
/modules/file_storage/download.php?file=<HASH>%7C<ID>     … běžné stránky
/e_download.php?file=/data/editor/…&original=…            … stránky psané v editoru
```

Druhý používají stránky nového územního plánu a ÚAP; nese navíc velikost a typ souboru v atributu `title`.

`HASH` je 8 znaků hex, `ID` je číslo souboru, oddělovač je URL-enkódovaná svislice (`%7C`). **Ani jedno nelze odvodit** — seznam odkazů se musí pokaždé sesbírat z příslušné stránky.

Server vrací korektní `Content-Disposition` s původním názvem souboru, což je použitelné pro pojmenování:
```
Content-Disposition: attachment; filename="ml zpravodaj - 2026 - srpen.pdf"
Content-Type: application/pdf
```

---

## 3. Městský zpravodaj — PDF

### Základní parametry

- Měsíčník, aktuálně **ročník 11**
- V archivu **122 čísel** (stránkovaný výpis)
- Velikost kolísá extrémně: **2,5 MB až 117 MB**

### Ověřeno na čísle 8/2026

```
Pages:        32
Page size:    595.276 x 841.89 pts (A4)
Creator:      Adobe InDesign 19.5 (Macintosh)
Producer:     Adobe PDF Library 17.0
CreationDate: Fri Jul 24 10:50:50 2026 UTC
Encrypted:    no
Velikost:     2 882 692 B
```

**Generováno z InDesignu → plná textová vrstva. OCR není potřeba.**

### Extrakce textu

Výtěžnost z jednoho čísla: **151 428 znaků / 14 192 slov**.

**Zásadní zjištění: `pdftotext` použít BEZ přepínače `-layout`.**

| Režim | Chování |
|---|---|
| `pdftotext -layout` | Zachová vizuální rozložení → **sloupce se prolínají**, text nelze číst souvisle |
| `pdftotext` (výchozí) | **Správné pořadí čtení** napříč dvousloupcovou sazbou + **automatické spojení slov rozdělených na konci řádku** |

Ukázka výstupu ve výchozím režimu — všimněte si, že „mykologický" je správně spojeno z „mykologic-" + „ký":

```
Město získalo dotaci na další
přípravy záchrany vily LIL
Mariánské Lázně získaly od Karlovarského kraje dotaci na další
přípravné práce směřující k záchraně vily LIL. V posledních dvou
letech už bylo provedeno digitální zaměření objektu, mykologický
průzkum a odborné posouzení jeho stavebně-technického
a statického stavu.
```

Čeština s diakritikou i uvozovky „…" vycházejí správně.

### Detekce hranic článků

`pdftotext -bbox-layout` vrací souřadnice každého slova:

```xml
<word xMin="28.346400" yMin="34.182000" xMax="55.513400" yMax="43.156000">Městský</word>
```

> **Opraveno po zpracování celého archivu.** Dvě doporučení, která tu původně stála, se na 122 číslech neosvědčila.

**Výška boxu NENÍ velikost písma.** Původně tu stálo, že se dá odvodit z `yMax - yMin`. Nedá: v čísle 3/2020 vychází běžný text na 30,7 pt a nadpisy na 28,5 pt, protože tělo je sázené písmem s obrovským deklarovaným FontBBoxem. Signál je tedy obrácený a heuristika by systematicky prohlašovala běžný text za nadpisy. Použitelná je místo toho **šířka slova na znak** — ta je napříč všemi ročníky konzistentní a nadpisy vycházejí 1,65× až 3,8× nad tělem textu.

**Výchozí pořadí čtení `pdftotext` neplatí univerzálně.** Pro dvousloupcovou sazbu od roku 2024 ano, ale v ročnících 2016–2017 stojí vedle sebe dva nezávislé články a poppler je prokládá po vodorovných pásech — z jednoho odstavce se stane směs dvou textů. Na tyto ročníky je potřeba **vlastní rekurzivní XY-řez**. Nadpisy se z měření mezer vynechávají (přetékají přes sloupce) a přiřazují se k textu pod sebou.

Drobnost, na které se dá ztratit půl hodiny: `-bbox-layout` občas vrátí uvnitř textu řídicí znak `\x08`, na kterém XML parser spadne. Parsovat selectolaxem.

### OCR fallback — nakonec nebyl potřeba nikde

Předpokládalo se, že starší ročníky budou skenované. **Nejsou: všech 122 čísel má plnou textovou vrstvu až do 02/2016**, takže OCR se nespustilo ani jednou. Detekce zůstává v kódu jako pojistka pro budoucí čísla (práh < 200 znaků na stranu, `tesseract` s modelem `ces`).

### Výsledek zpracování archivu

| | |
|---|---|
| čísel | **122 / 122** (02/2016 – 08/2026) |
| stran | 2 476 |
| článků | **4 519** |
| pokrytí textu čísla | **93,4 %** (nejhůř 79 %) |
| skenů | 0 |
| článků začínajících uprostřed věty | 3,4 % |

V archivu **chybí 01/2016 a 08/2020** — nejsou tam vůbec, není to chyba sběrače. Prázdninová dvojčísla (07-08 v letech 2019, 2021, 2022, 2023) dostávají id podle prvního měsíce a pole `mesic_do`.

**Názvu souboru se nedá věřit** — číslo 02/2021 je v archivu nahrané jako `ml zpravodaj - 2020 - unor.pdf`. Autoritativní je nadpis položky ve výpisu, `Content-Disposition` slouží jen jako záloha.

**`?page=N` za koncem výpisu vrací pořád poslední stránku**, ne prázdno; konec stránkování se pozná podle opakování obsahu.

Prostý text každého čísla se odkládá do `data/zpravodaj/text/` (11 MB). Archiv tak přežije smazání PDF — a právě z něj staví web, protože 1,7 GB originálů se do repozitáře ani na Vercel nevejde.

### Prostředí

`poppler-utils` nemusí být v kontejneru přítomen. Ověřeno, že instalace funguje, ale **až po `apt-get update`** — bez něj selže stažení balíčku na 404 kvůli zastaralému indexu.

---

## 4. Hlídač státu

Dostupný jako **MCP server** → strukturovaná data, žádný scraping. Ověřeno funkčně.

### Město Mariánské Lázně, IČO 00254061

| Ukazatel | Město | Celý holding |
|---|---|---|
| Smluv v registru | 4 349 | 6 502 |
| Objem smluv | 3,98 mld. Kč | 6,28 mld. Kč |
| Smlouvy s vážnými nedostatky | 41 | 111 |
| Smlouvy bez uvedené ceny | 248 | 581 |
| Smlouvy blízko limitu zakázky | 53 | 76 |
| Dotací | 505 | 691 |
| Objem dotací | 1,09 mld. Kč | 1,26 mld. Kč |

**K-index:** stupeň **B** za roky 2022, 2023, 2024 i 2025 — „chování s malou mírou rizikových faktorů".

Hlavní kategorie smluv: Stavebnictví, Technické služby, Dary a dotace.

### Užitečné metriky, které Hlídač počítá sám

- Meziroční změny objemu zakázek
- Smlouvy s firmami, jejichž majitelé sponzorovali politické strany (31 smluv v roce 2023, 25 v roce 2022)
- Podíl smluv bez uvedené ceny

### Dostupné nástroje

Registr smluv, veřejné zakázky, dotace, sponzoring politických stran, platy politiků, insolvence, rejstřík trestů právnických osob, rozhodnutí ÚOHS, K-index, legislativa v přípravě (VeKLEP).

**Poznámka:** data jsou v češtině, dotazy je nutné psát česky.

---

## 5. Městský holding — subjekty k monitoringu

Každý subjekt má vlastní IČO a tedy vlastní stopu v registru smluv, dotacích a zakázkách. **Monitoring musí pokrývat všechny, ne jen město.**

### Obchodní společnosti

| Společnost | Podíl města | IČO |
|---|---|---|
| Infocentrum Mariánské Lázně s.r.o. | 100 % | *dohledat* |
| TDS spol. s r.o. | 100 % | *dohledat* |
| Lázeňské lesy spol. s r.o. | 100 % | *dohledat* |
| DEVELOP CENTRUM Mariánské Lázně s.r.o. | 100 % | *dohledat* |
| MĚSTSKÁ DOPRAVA Mariánské Lázně s.r.o. | částečný | *dohledat* |
| Nemocnice Mariánské Lázně s.r.o. | částečný | *dohledat* |

> Web města neuvádí IČO ani přesné podíly u částečně vlastněných firem. Dohledat v obchodním rejstříku (justice.cz) při stavbě sběračů.

### Příspěvkové organizace a navázané subjekty

| IČO | Název |
|---|---|
| 00074071 | Technické služby Mariánské Lázně |
| 00368997 | Městské muzeum a galerie Mariánské Lázně |
| 00575143 | Domov pro seniory a dům s pečovatelskou službou |
| 19882629 | Městské divadlo Mariánské Lázně |
| 47720654 | Městská knihovna Mariánské Lázně |
| 72559772 | Správa městských sportovišť |
| 26320053 | Západočeský symfonický orchestr Mariánské Lázně o.p.s. |
| 47721472 | ZUŠ Fryderyka Chopina |
| 69979430 | Městský dům dětí a mládeže |
| 47723505 | ZŠ JIH, Komenského 459 |
| 47724978 | ZŠ Vítězství |
| 70997543 | ZŠ Úšovice, Školní náměstí 472 |
| 47723483 | MŠ Vora, Za Tratí 687 |
| 70997560 | MŠ Křižíkova 555 |
| 70997578 | MŠ Hlavní 440 |
| 70997586 | MŠ Úšovice, Skalníkova 518 |
| 70997594 | MŠ Na Třešňovce 603 |
| 72073993 | Společenství pro dům Danzer, Hlavní třída 131/50 |

Celkem **24 subjektů** k monitoringu včetně města a obchodních společností.

---

## 6. Zastupitelstvo — složení

21 členů, volební období od roku 2022.

| Jméno | Uskupení | Funkce |
|---|---|---|
| Martin Hurajčík | ANO 2011 | **starosta** |
| Mgr. Miloslav Pelc | Změna pro ML | **místostarosta** |
| Mgr. Luboš Borka | Město sobě | zastupitel |
| Ing. Jan Budka | ANO 2011 | zastupitel |
| MUDr. Roman Dubnický | ANO 2011 | zastupitel |
| Mgr. Dušan Drexler | STAN | zastupitel |
| Ing. arch. Vojtěch Franta | Piráti | zastupitel |
| Mgr. Petr Hála | Změna pro ML | zastupitel |
| PaedDr. Alena Hálová | Změna pro ML | zastupitelka |
| Martin Hladík | SPD | zastupitel |
| JUDr. Miloslav Chadim | ANO 2011 | zastupitel |
| Mgr. Vladimír Kafka | ANO 2011 | zastupitel |
| Ing. Martin Kalina | Piráti | zastupitel |
| Zdeněk Král | ODS Plus | zastupitel |
| Ing. arch. Ludmila Míková | ODS Plus | zastupitelka |
| Ivana Mottlová | ANO 2011 | zastupitelka |
| Bc. Josef Pavlovic | Piráti | zastupitel |
| Mgr. Jana Roubalová | ANO 2011 | zastupitelka |
| Štěpán Stráník | SPD | zastupitel |
| Ing. Kamil Špindler | STAN | zastupitel |
| Samuel Zabolotný | ANO 2011 | zastupitel |

**Koalice:** ANO 2011 + Změna pro Mariánské Lázně + ODS Plus + Město sobě — **14 z 21 mandátů**.

**Změna 2026:** v červnu 2026 rezignoval na funkci 1. místostarosty **Samuel Zabolotný** (ANO); v zastupitelstvu zůstává. Sběrač musí počítat s tím, že se funkce v průběhu období mění — proto **ukládat funkce s platností od–do**, ne jako aktuální stav.

---

## 6b. ARES — firmy se sídlem ve městě

`https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/vyhledat`, POST s JSON. Kód obce Mariánské Lázně je **554642**.

**Staženo 4 177 ze 4 177 subjektů** — 1 499 právnických osob, 2 678 živnostníků.

### Stahování se musí řezat

ARES odmítne dotaz, který by vrátil **přes 1 000 výsledků**, a to ještě před první stránkou:

```json
{"kod":"CHYBA_VSTUPU","subKod":"VYSTUP_PRILIS_MNOHO_VYSLEDKU",
 "popis":"Zadaný dotaz vrací příliš mnoho výsledků (4 177)."}
```

Řeší se kaskádou řezů: **právní forma** (151 kódů, jejich součet dá přesně 4 177, takže je rozklad ověřitelně úplný) → **část obce** → **ulice** → **číslo domovní**. Každý řez se porovnává s počtem, který ARES sám hlásí; rozdíl se zapisuje jako mezera, ne zamlčuje. První běh takto přiznal 7 chybějících subjektů v Úšovicích.

Převažující obor (`czNacePrevazujici`) a kategorii počtu pracovníků dotahuje RES po stovce IČO na dotaz — celé město je 42 dotazů.

### Dvě pasti, kvůli kterým by graf lhal

**Obory nejde vykreslit naivně.** Ve městě je **396 společenství vlastníků jednotek** a všechna mají CZ-NACE „činnosti v oblasti nemovitostí". Z bytových domů by tak vyšlo, že hlavní obor lázeňského města je realitní byznys (663 subjektů, první místo). Bez SVJ a spolků spadnou nemovitosti na 263 a čtvrté místo, a nahoru se dostane to, co město opravdu živí: **stravování 364, maloobchod 327, osobní služby 272**. Ubytování a stravování dohromady dává **508 subjektů** — to je lázeňský podpis města.

**Časová osa vzniků měří něco jiného, než se zdá.** Adresní index ARES vede převážně žijící subjekty, takže osa neříká „kolik firem v tom roce vzniklo", ale „kolik dnes existujících subjektů v tom roce vzniklo". Starší roky jsou osekané o všechno, co mezitím skončilo — je to přežití, ne vznik. Osa to nese v poli `mereni` a **graf to musí napsat**, jinak tvrdí, že podnikání ve městě setrvale roste.

**Zániky nejde doplnit.** `datumZaniku` v ARES neexistuje ani ve vyhledávání, ani v detailu — má ho až obchodní rejstřík. Osa zániků nese `stav: "neuplne"`.

**Obrat ARES nezveřejňuje vůbec.** Kategorie počtu pracovníků chybí u 2 639 ze 4 177 subjektů. Pásma obratu jsou jen u 21 nejvýznamnějších firem doplněných z Hlídače státu — a jsou to pásma, ne čísla.

### Drobnosti, na kterých se dá ztratit čas

- U části subjektů vrací ARES **`ico: null`** a jen interní `icoId` tvaru `ARES_00361728`. Číslo v něm vypadá jako IČO, ale detail pod ním vrací 404 — neodvozovat.
- Dvanáct položek číselníku CZ-NACE má místo středníku rozbitou entitu `&amp;#59^`.

### Kdo ve městě opravdu je

Můj původní odhad („Danubius, Ensana") **neseděl** — ani jedna z nich nemá v Mariánských Lázních sídlo. Lázeňský provozovatel je veden jako **Léčebné lázně Mariánské Lázně a.s.** A druhý největší zaměstnavatel není lázeňský ani hotelový, ale **strojírenský: ELEKTROMETALL** (500–999 zaměstnanců).

Největší zaměstnavatel je **OREA HOTELS** (1 000–1 500 zaměstnanců).

Z 1 115 protistran města s IČO jich **248 sídlí přímo ve městě** a připadá na ně 1,74 mld. z 3,74 mld. Kč.

## 7. Média a regionální zpravodajství

> **Doplněno po sklizni.** Otázka zněla, jestli jde jít 12 let zpět. Odpověď: **jde, ale jen u dvou zdrojů ze čtyř** — a u zbylých dvou to není technická překážka, nýbrž fakt, že ty weby dřív neexistovaly.

| Zdroj | URL | Staženo | Rozsah | Poznámka |
|---|---|---|---|---|
| Český rozhlas Karlovy Vary | `vary.rozhlas.cz` | 369 | **2011–2026 (15 let)** | Nejlepší zdroj. Sitemapa 14 057 URL bez stránkování. `Crawl-delay: 10` — dávka trvá přes hodinu. |
| Karlovarský kraj | `kr-karlovarsky.cz` | 125 | **2004–2026 (22 let)** | Sahá nejdál, ale je to tiskový servis kraje, ne zpravodajství o městě. |
| Karlovarská Drbna | `karlovarska.drbna.cz` | 134 | 2020–2026 | Web vznikl 03/2020 — strop je daný realitou, ne technikou. |
| Zprávy Karlovarsko | `zpravykarlovarsko.cz` | 82 | 2020–2026 | Web vznikl 11/2020. |
| Chebský deník / Deník.cz | `denik.cz` | **0** | — | **Zakázáno v robots.txt, viz níže.** |

**Celkem 713 článků, 2004–2026, každý s ověřeným datem.** Souvislé pokrytí od roku 2011.

#### Deník je pro nás zavřený

`denik.cz` i `chebsky.denik.cz` mají v robots.txt sekci „AI bots protection", která jmenovitě zakazuje `ClaudeBot`, `Claude-Web` a `anthropic-ai` přes `Disallow: /`.

Sběrač to respektuje a **zákaz se neobchází přepnutím User-Agenta** — kontrola se ptá na naši skutečnou identitu, ne na hlavičku, kterou bychom si mohli vymyslet. Zdroj má natvrdo `povoleno=False`.

Je to citelná ztráta: podle vyhledávání je Deník nejpodrobnější zdroj o komunální politice Mariánských Lázní. Cesta ven je ruční režim `--rucne`, který uloží odkaz a vlastní shrnutí, aniž by cokoliv stahoval.

Rozlišuj hosty: **`irozhlas.cz` ClaudeBota blokuje, ale regionální `vary.rozhlas.cz` ne** — jsou to jiné weby s jiným robots.txt, a ten náš nejcennější je povolený.

#### Datum se nesmí brát ze sitemapy

U všech tří velkých zdrojů je `lastmod` **razítko migrace CMS, ne datum vydání**. Článek rozhlasu s `lastmod` 2014 má ve skutečnosti `article:published_time` 2011-05-16; u kraje je 90 % `lastmod` z roku 2024. Kdo by datoval podle sitemapy, dostal by nesmysl. Datum se bere výhradně z metadat stránky.

#### Past na název

„Lázeňské lesy" **není** jednoznačný výraz — Karlovy Vary mají vlastní firmu téhož jména a do dat se přes něj dostalo 19 článků o karlovarské firmě. Z ostré kontroly byl vyřazen.

**Sledované výrazy:** „Mariánské Lázně", „mariánskolázeňsk*", jména vedení města, názvy městských firem, „vila LIL", „UNESCO Mariánské Lázně".

**Co se ukládá:** titulek, zdroj, datum, URL, vlastní dvouvětné shrnutí. **Nikdy plný text.**

---

## 8. Počasí a výstrahy

| Data | Zdroj | Poznámka |
|---|---|---|
| Předpověď | Open-Meteo API | Zdarma, bez klíče, bez registrace |
| Výstrahy | ČHMÚ (SIVS) | Okres Cheb |
| Kvalita ovzduší | ČHMÚ | Nejbližší měřicí stanice |

Souřadnice Mariánských Lázní: **49,9646° N, 12,7010° E**.

---

## 9. Facebook — proč to nejde

| Cesta | Stav |
|---|---|
| Skupiny přes API | **Neexistuje** — Meta nenabízí veřejné API pro čtení skupin |
| Scraping skupin | **Porušuje podmínky užití** + technicky nestabilní |
| Graph API pro stránky | Funguje **jen pro stránky, které sám spravujete** |
| Meta MCP konektor | Zaměřen na **reklamu**, ne na obsah skupin |

**Řešení:** ruční vstup provozovatele, 3–5 vět týdně o tom, co ve skupinách rezonovalo. Souhrn témat, **nikdy jmenovité citace občanů**.

---

## 10. Shrnutí dostupnosti

| Zdroj | Formát | Náročnost | Stav |
|---|---|---|---|
| Usnesení a hlasování | HTML | nízká *(nutný UA)* | ✅ ověřeno |
| Zpravodaj PDF | PDF s textovou vrstvou | střední *(segmentace článků)* | ✅ ověřeno |
| Hlídač státu | MCP, strukturovaná data | nízká | ✅ ověřeno |
| Zastupitelé | HTML | nízká | ✅ ověřeno |
| Městské firmy | HTML | nízká *(chybí IČO)* | ⚠️ částečně |
| Úřední deska | HTML | střední *(bez RSS)* | ✅ dostupné |
| Novinky a kalendář | HTML | střední *(bez RSS)* | ✅ dostupné |
| Počasí | JSON API | nízká | ✅ dostupné |
| Média | web search | střední | ✅ dostupné |
| Facebook | — | **neproveditelné** | ❌ ruční režim |
