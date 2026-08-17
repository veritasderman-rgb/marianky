# Mariánky — občanský portál a týdenní přehled

**Funkční zadání**
Verze 1.0 · 17. 8. 2026

---

## 1. Co to je a pro koho

Web, který jednou týdně (v neděli ráno) vydá **jedno přehledné číslo** o tom, co se za uplynulý týden stalo v Mariánských Lázních — a zároveň drží **trvalý, prohledávatelný archiv** všeho, co se do něj kdy nasypalo.

**Cílový uživatel:** občan Mariánských Lázní, který se zajímá o dění ve městě, ale nemá čas si sám procházet úřední desku, usnesení rady, registr smluv, tři facebookové skupiny a městský zpravodaj. Chce jednou týdně deset minut čtení a možnost si kdykoliv dohledat „co se vlastně tenkrát schválilo s tou vilou LIL".

**Cílový uživatel není:** novinář hledající kauzy na klik, ani úřad prezentující sám sebe. Tón je věcný, doložený odkazem na zdroj, bez komentáře a bez hodnocení.

**Dvě vrstvy produktu:**

| Vrstva | Co to je | Aktualizace |
|---|---|---|
| **A — Týdenní vydání** | Jedna stránka, jedno číslo, souhrn týdne. Archiv čísel zpětně. | neděle ráno |
| **B — Trvalý portál** | Fulltextový archiv, profily lidí, přehled peněz, časové osy témat. | průběžně týmž během |

Vrstva A je to, co si člověk přečte. Vrstva B je to, proč se na web vrátí.

---

## 2. Struktura týdenního vydání

Jedno číslo = jedna stránka. Řazeno od „musíš vědět" po „když bude čas".

### 2.1 Hlavička
Název, datum vydání, pořadové číslo, období které pokrývá (např. „období 10. 8. – 16. 8. 2026").

### 2.2 Stavový pás
Čtyři až pět dlaždic s aktuálním stavem, každá s barevným indikátorem (klid / pozor / výstraha):

- **Počasí** — předpověď na týden, teplotní extrémy
- **Výstrahy ČHMÚ** — vichr, povodně, vedro, sníh; pro okres Cheb
- **Doprava a uzavírky** — aktuální uzavírky ve městě a na příjezdech
- **Radnice** — kdy je nejbližší jednání rady / zastupitelstva
- **Voda a lázeňské zdroje** *(volitelné, fáze 2)* — stav sledovaných pramenů, pokud jsou data dostupná

### 2.3 Z radnice
Jádro celého vydání.

- Nová usnesení rady a zastupitelstva za uplynulý týden — **shrnutá lidsky**, ne přepsaná úředničinou
- U každého bodu: číslo usnesení, datum, odkaz na originál
- **Jmenovité hlasování** tam, kde bylo — kdo byl pro, proti, zdržel se
- Zvýraznění bodů, které se týkají peněz nad stanovený limit, prodeje majetku, nebo územního plánu
- Nové dokumenty na úřední desce
- Body odložené nebo stažené z programu (často zajímavější než schválené)

### 2.4 Peníze města
- Nové smlouvy v registru smluv (město + jeho firmy a organizace) za uplynulý týden — protistrana, částka, předmět
- Nové dotace přiznané městu nebo jeho organizacím
- Nové veřejné zakázky a jejich výsledky
- Upozornění na smlouvy s formálními vadami (Hlídač státu je označuje)
- Čtvrtletně: souhrnný pohled — K-index, objem smluv, největší dodavatelé

### 2.5 Městské firmy a organizace
Souhrn za městský „holding" — 6 obchodních společností a 18 příspěvkových organizací (viz sekce 3.4). Co je nového: personální změny, výroční zprávy, hospodářské výsledky, jejich vlastní oznámení, změny v obchodním rejstříku.

### 2.6 Co se děje ve městě
Kalendář akcí na nadcházející týden — kultura, sport, radnice, komunitní akce. Řazeno chronologicky, s místem a časem.

### 2.7 Monitoring zpráv
Co o Mariánkách napsala média — regionální i celostátní. Titulek, zdroj, datum, dvouvětné shrnutí, odkaz. Bez přebírání celých textů.

### 2.8 Diskuze občanů
Témata, která rezonovala ve veřejné diskuzi (Facebook, diskuze pod články). **Souhrn témat a nálad, nikoliv citace jednotlivců** — viz omezení v sekci 7.2.

### 2.9 Ze zpravodaje
Když v uplynulém měsíci vyšlo nové číslo Městského zpravodaje: přehled článků s odkazem do fulltextového archivu.

### 2.10 Kdo je kdo
Jeden profil týdne — zastupitel, ředitel městské firmy, nebo osobnost spjatá s městem. Rotuje.

### 2.11 Rychlé odkazy
Stálá patička s odkazy na zdroje: úřední deska, usnesení, kalendář, registr smluv, Hlídač státu, ČHMÚ.

---

## 3. Datové zdroje

Všechny níže uvedené zdroje byly **ověřeny 17. 8. 2026** — dostupnost, formát i technická úskalí. Detailní inventář včetně výstupů testů je v [`docs/datove-zdroje.md`](docs/datove-zdroje.md).

### 3.1 Portál usnesení — `usneseni.muml.cz`

Nejcennější zdroj celého projektu a zároveň nejpodceňovanější.

| Sekce | URL | Rozsah |
|---|---|---|
| Usnesení rady | `/rada/usneseni` | od 2016, aktuálně č. j. 124 (7. 8. 2026) |
| Podklady rady | `/rada/podklady` | |
| **Hlasování rady** | `/rada/hlasovani/usneseni` | + členění na strany a členy |
| Usnesení zastupitelstva | `/zastupitelstvo/usneseni` | od 2019, aktuálně č. j. 28 (20. 7. 2026) |
| Podklady zastupitelstva | `/zastupitelstvo/podklady` | |

**Technicky:** čistě serverové HTML, obsah je přímo v odpovědi (žádný JavaScript rendering). Tabulky přes DataTables. **Vyžaduje hlavičku `User-Agent`** — bez ní server vrací 503.

Sekce *Hlasování → Členové* je zásadní: dává **jmenovitá hlasování**, ze kterých lze postavit hlasovací historii každého zastupitele. To je funkce, kterou nikde jinde pro Mariánky nedostanete.

### 3.2 Web města — `muml.cz`

| Co | URL |
|---|---|
| Úřední deska (archiv) | `/urad/uredni-deska-archiv/` |
| Zpravodaj města | `/aktualne/zpravodaj-mesta/` |
| Novinky | `/aktualne/novinky/` |
| Kalendář akcí | `/aktualne/kalendar-akci/` |
| Zastupitelé | `/samosprava/zastupitelstvo/clenove-1/` |
| Termíny zasedání | `/samosprava/zastupitelstvo/terminy-zasedani/` |
| Online přenos jednání | `/samosprava/zastupitelstvo/online-prenos-jednani/` |
| Obchodní společnosti města | `/urad/povinne-informace/subjekt-obchodni-spolecnosti-81.html` |

**Technicky:** **RSS neexistuje** (ověřeno — `/rss`, `/rss.xml`, `/aktualne/novinky/rss` vracejí 404). Vše se musí scrapovat z HTML. Proto je nutný diff-monitoring (sekce 5.4).

### 3.3 Městský zpravodaj (PDF archiv)

Vychází měsíčně, aktuálně ročník 11. Archiv obsahuje **122 čísel** na stránkovaném výpisu.

**Ověřeno na čísle 8/2026:**
- 32 stran A4, 2,88 MB
- Generováno z Adobe InDesign 19.5 → **plná textová vrstva, OCR není potřeba**
- Extrakce `pdftotext` bez přepínače `-layout` dává **správné pořadí čtení** ve dvousloupcové sazbě a **automaticky spojuje slova rozdělená na konci řádku**
- Výtěžnost: ~151 000 znaků / 14 200 slov z jednoho čísla, čeština s diakritikou v pořádku
- `pdftotext -bbox-layout` dává souřadnice slov → z nich lze odvodit sloupce a velikost písma, tedy **detekovat nadpisy a hranice článků**

**Pozor:** velikost čísel kolísá extrémně (2,5 MB až 117 MB). Velká čísla jsou pravděpodobně obrazově bohatá, ne skenovaná — ale pipeline musí mít **fallback na OCR** (`tesseract` s českým jazykovým modelem), který se spustí, když hustota extrahovaného textu klesne pod prahovou hodnotu (návrh: < 200 znaků na stranu).

**URL vzor:** `muml.cz/modules/file_storage/download.php?file=HASH%7CID` — hash i ID jsou nepředvídatelné, seznam se musí pokaždé sesbírat ze stránky archivu (včetně stránkování).

### 3.4 Městský „holding"

**Město Mariánské Lázně, IČO 00254061.**

Obchodní společnosti (z webu města):

| Společnost | Podíl |
|---|---|
| Infocentrum Mariánské Lázně s.r.o. | 100 % |
| TDS spol. s r.o. | 100 % |
| Lázeňské lesy spol. s r.o. | 100 % |
| DEVELOP CENTRUM Mariánské Lázně s.r.o. | 100 % |
| MĚSTSKÁ DOPRAVA Mariánské Lázně s.r.o. | částečný |
| Nemocnice Mariánské Lázně s.r.o. | částečný |

> **K doplnění při stavbě:** IČO a přesné podíly u obou částečně vlastněných firem web města neuvádí — dohledat v obchodním rejstříku.

Příspěvkové organizace a další navázané subjekty (18 položek dle Hlídače státu) — mj. Technické služby Mariánské Lázně (IČO 00074071), Městské muzeum a galerie, Městská knihovna, Městské divadlo, Domov pro seniory, Správa městských sportovišť, Západočeský symfonický orchestr, 4 základní školy, 5 mateřských škol, ZUŠ F. Chopina, Městský dům dětí a mládeže.

Každý z těchto subjektů má vlastní IČO → vlastní stopu v registru smluv, dotacích a zakázkách. **Monitoring musí pokrývat celý holding, ne jen město.**

### 3.5 Hlídač státu

Dostupný jako MCP server → **žádný scraping, strukturovaná data přímo**. Ověřeno funkčně.

Co z něj brát:
- **Registr smluv** — 4 349 smluv města v hodnotě 3,98 mld. Kč; za celý holding 6 502 smluv / 6,28 mld. Kč
- **Kvalita zveřejňování** — 41 smluv s vážnými nedostatky, 248 bez uvedené ceny
- **K-index** — hodnocení rizikovosti; město drží stupeň **B** za roky 2022–2025
- **Dotace** — 505 dotací městu v objemu 1,09 mld. Kč, za holding 691 / 1,26 mld. Kč
- **Veřejné zakázky**, sponzoring politických stran, insolvence a rejstřík trestů právnických osob u dodavatelů
- Rozhodnutí ÚOHS

### 3.6 Média a regionální zpravodajství

- Český rozhlas Karlovy Vary — `vary.rozhlas.cz`
- Zprávy Karlovarsko — `zpravykarlovarsko.cz`
- Chebský deník / Deník.cz
- Karlovarský kraj — tiskové zprávy
- Celostátní média — vyhledávání na klíčová slova

**Přístup:** webové vyhledávání na dotazy typu „Mariánské Lázně", „mariánskolázeňsk*", jména vedení města a městských firem. Ukládá se **titulek, zdroj, datum, URL a vlastní dvouvětné shrnutí** — nikdy ne plný text článku.

### 3.7 Počasí a výstrahy

- **Předpověď:** Open-Meteo API — zdarma, bez klíče, bez registrace, souřadnice Mariánských Lázní
- **Výstrahy:** ČHMÚ, výstražná služba pro okres Cheb
- **Kvalita ovzduší:** ČHMÚ, nejbližší měřicí stanice

### 3.8 Facebook a veřejná diskuze

Viz omezení v sekci 7.2. Krátce: **automatizovaný sběr z facebookových skupin není technicky ani právně průchozí**. Zadání s tím počítá a řeší to degradovaným režimem.

---

## 4. Trvalý portál (vrstva B)

### 4.1 Fulltextový archiv zpravodaje

Cíl: **rozebrat PDF na jednotlivé články** a udělat z nich prohledávatelný textový archiv.

Každý článek dostane:
- nadpis, perex, plný text
- číslo a rok vydání, strana
- rubrika (Z radnice, Dění ve městě, Kultura, Sport, Inzerce…)
- osoby zmíněné v textu → propojení na profily v sekci Kdo je kdo
- témata / štítky
- odkaz na stránku v originálním PDF

Rozdělení na články je **dvoufázové**: nejdřív heuristika nad souřadnicemi a velikostí písma (`pdftotext -bbox-layout`) najde kandidáty na nadpisy a hranice sloupců, pak jazykový model text vyčistí, ověří hranice článků a doplní metadata. Inzerce se odfiltruje.

**Rozsah zpětného zpracování:** jednorázový dávkový běh přes všech 122 čísel v archivu. Pak už jen jedno nové číslo měsíčně.

### 4.2 Archiv usnesení a hlasování

- Všechna usnesení rady i zastupitelstva, plný text, fulltextově prohledávatelná
- Provázání usnesení → hlasování → zastupitel
- Filtry podle data, orgánu, tématu, částky

### 4.3 Kdo je kdo

Profil pro každou relevantní osobu:

**Zastupitelé** (21 členů) — jméno, politická příslušnost, funkce, členství ve výborech a komisích, **hlasovací historie**, účast na jednáních, zmínky ve zpravodaji a v médiích, případné vazby na dodavatele města (přes Hlídač státu).

Aktuální složení: starosta **Martin Hurajčík** (ANO 2011), místostarosta **Miloslav Pelc** (Změna pro ML). Koalice ANO + Změna pro ML + ODS Plus + Město sobě drží 14 z 21 mandátů. V červnu 2026 rezignoval 1. místostarosta Samuel Zabolotný (ANO).

**Vedení městských firem a organizací** — funkce, od kdy, statutární orgány z obchodního rejstříku.

**Vedoucí odborů úřadu** — z telefonního seznamu města.

**Historické osobnosti spjaté s městem** — statická, ručně psaná sekce (Goethe, Chopin, Edward VII. a další). Nemá vazbu na týdenní běh, ale patří k tomu, co dělá web webem o Mariánkách a ne jen o radnici.

### 4.4 Peníze — přehled

Dashboard nad daty z Hlídače státu: vývoj objemu smluv v čase, největší dodavatelé města, dotační příjmy, K-index v čase, seznam problematických smluv.

### 4.5 Časové osy témat

Dlouhodobá témata dostanou vlastní stránku s chronologií napříč všemi zdroji — usnesení, smlouvy, články ve zpravodaji, mediální výstupy.

Kandidáti na start: **vila LIL**, **UNESCO** (5 let na seznamu), **Nemocnice Mariánské Lázně**, rozpočet města, územní plán.

Témata se zakládají ručně, naplňují automaticky.

### 4.6 Vyhledávání

Jedno vyhledávací pole přes **všechno** — články ze zpravodaje, usnesení, smlouvy, profily lidí, archiv vydání. Musí fungovat na české diakritice a na skloňování (hledám „vila LIL", najdu i „vily LIL").

---

## 5. Technické řešení

### 5.1 Architektura

```
zdroje  →  sběrače (deterministický kód)  →  data/ (JSON + Markdown v gitu)
                                                    ↓
                                        Claude rutina (interpretace + psaní)
                                                    ↓
                                        obsah/ (vydání, shrnutí, profily)
                                                    ↓
                                        generátor statického webu  →  hosting
```

**Zásada, na které to celé stojí:**

> **Scraping dělá kód. Porozumění dělá Claude.**

Jazykový model nikdy neparsuje HTML ani nehledá selektory — to je práce pro deterministický skript, který buď funguje, nebo spadne s chybou. Claude dostává na vstup už čistá strukturovaná data a jeho úkolem je jim rozumět, shrnout je a napsat text. Když se změní HTML na webu města, spadne sběrač a je to vidět. Kdyby to dělal model, tiše by si vymyslel obsah.

### 5.2 Doporučený stack

| Vrstva | Volba | Proč |
|---|---|---|
| Sběrače | Python (`httpx`, `selectolax`, `pdftotext`) | Nejjednodušší cesta k PDF a HTML |
| Úložiště dat | JSON + Markdown soubory v gitu | Verzování zdarma, diffy jsou funkce (viz 5.4) |
| Generátor webu | Astro nebo Eleventy | Statický výstup, rychlý, bez serveru |
| Vyhledávání | Pagefind | Funguje staticky v prohlížeči, umí diakritiku, zvládne desetitisíce stránek |
| Hosting | GitHub Pages nebo Cloudflare Pages | Zdarma, deploy z gitu |
| Plánování | Claude routine (týdenní cron) | Zadání to předpokládá |

Žádná databáze, žádný backend, žádný server k údržbě. Provozní náklady se blíží nule, což je u projektu, který má běžet roky, důležitější než elegance.

### 5.3 Struktura repozitáře

```
/scrapers/          sběrače, jeden soubor na zdroj
/data/
  /usneseni/        usnesení a hlasování, JSON
  /zpravodaj/
    /pdf/           stažené originály
    /clanky/        rozebrané články, Markdown + frontmatter
  /smlouvy/         výstupy z Hlídače státu
  /uredni-deska/
  /akce/
  /media/
  /snapshots/       otisky sledovaných stránek pro diff
/obsah/
  /vydani/          týdenní čísla
  /lide/            profily
  /temata/          časové osy
/web/               generátor statického webu
/docs/              dokumentace projektu
```

### 5.4 Diff-monitoring

Protože město nemá RSS a dokumenty umí zmizet nebo se tiše změnit, každý běh ukládá **otisk sledovaných stránek** do `data/snapshots/`. Git pak sám ukazuje, co se změnilo.

Sledovat: úřední desku, seznam zastupitelů, obchodní společnosti, termíny zasedání, rozpočtové dokumenty.

Když se něco změní, je to položka do týdenního vydání — často zajímavější než oficiální novinky. Zmizelý dokument z úřední desky je zpráva.

### 5.5 Kvalita a bezpečnostní pojistky

- **Každé tvrzení má odkaz na zdroj.** Věta bez dohledatelného zdroje se do vydání nedostane.
- **Sběrač buď uspěje, nebo hlásí chybu.** Žádné tiché degradování na prázdná data.
- Když zdroj selže, vydání vyjde bez dané sekce a **explicitně uvede, že data chybí** — nesmí to vypadat, že se nic nedělo.
- Rozlišovat **„nic se nestalo"** od **„nepodařilo se načíst"**. Vzor v předloze („program se nepodařilo načíst") je správný přístup.
- Ke každému číslu se ukládá **log běhu** — co se stáhlo, co selhalo, kolik položek přibylo.
- Peníze, jména a data se do textu vydání propisují **z dat, ne z generovaného textu** — model může napsat kontext, ale číslo v něm musí odpovídat záznamu.

---

## 6. Týdenní rutina

Spouští se **v neděli ráno**. Celý běh je inkrementální — bere jen to, co přibylo od minula.

**Fáze 1 — Sběr** *(deterministické skripty)*
1. Usnesení a hlasování rady a zastupitelstva — nová jednání
2. Úřední deska — nové dokumenty; porovnání se snapshotem
3. Novinky a kalendář akcí z webu města
4. Registr smluv, dotace a zakázky přes Hlídač státu — pro město i všech 24 navázaných subjektů
5. Kontrola nového čísla zpravodaje; pokud vyšlo → stažení, extrakce, rozdělení na články
6. Počasí a výstrahy
7. Mediální monitoring
8. Snapshoty sledovaných stránek

**Fáze 2 — Zpracování** *(Claude)*
9. Shrnutí usnesení do srozumitelného jazyka
10. Vyhodnocení, co je za týden podstatné a co je rutina — řazení podle důležitosti
11. Doplnění metadat u nových článků ze zpravodaje
12. Aktualizace profilů osob a časových os témat
13. Sepsání týdenního vydání

**Fáze 3 — Publikace**
14. Sestavení statického webu
15. Commit a push → automatický deploy
16. Zápis logu běhu

**Fáze 4 — Kontrola**
17. Souhrn běhu pro provozovatele: co vyšlo, co selhalo, co vyžaduje ruční zásah

**Odhad doby běhu:** 15–30 minut v běžném týdnu, déle v měsíci, kdy vyjde nový zpravodaj.

---

## 7. Omezení, která je potřeba přiznat předem

### 7.1 Autorská práva

Články z Městského zpravodaje ani z médií **se nepřebírají v plném znění**. Fulltextový archiv zpravodaje je určen pro **vyhledávání a citaci s odkazem na originál** — u každého článku vede odkaz na konkrétní stránku původního PDF. U médií se ukládá pouze titulek, zdroj a vlastní shrnutí.

Před spuštěním veřejné verze doporučuji **oslovit redakci zpravodaje** a archiv s nimi vyjasnit. Zpravodaj vydává město, jde o dokument financovaný z veřejných peněz, a šance na vstřícnou domluvu je vysoká — ale je lepší se zeptat než to řešit potom.

### 7.2 Facebook

Tohle je ta část zadání, kterou nelze splnit tak, jak by se chtělo.

- Facebookové **skupiny nejsou dostupné přes žádné veřejné API** — ani pro čtení
- **Automatizovaný scraping porušuje podmínky užití** Meta a technicky se rozbíjí při každé změně na jejich straně
- Přes oficiální Graph API lze číst pouze **stránky, které sám spravujete**

**Navržený režim:**
1. **Základní** — sekce Diskuze občanů se plní ručně: provozovatel jednou týdně přidá 3–5 vět o tom, co ve skupinách rezonovalo. Deset minut práce týdně.
2. **Rozšířený** — pokud správci některé z místních skupin projeví zájem o spolupráci, lze doplnit strukturovaný vstup od nich.
3. **Nikdy** — necitovat jmenovitě jednotlivé občany bez jejich souhlasu. Souhrn nálad ano, jmenovité citace ne.

Zbytek portálu na této sekci nestojí a bez ní funguje.

### 7.3 Osobní údaje

- **Zastupitelé, radní a vedení městských firem** jsou veřejně činné osoby — jejich hlasování, funkce a rozhodnutí patří k výkonu funkce a lze je zveřejňovat.
- **Úředníci** — jen jméno a funkce, nic dalšího.
- **Občané** — nikdy jmenovitě.
- Data z Hlídače státu (sponzoring stran, insolvence, rejstřík trestů právnických osob) se uvádějí **jen tam, kde mají přímou souvislost s městem** — tedy u dodavatelů města. Ne jako samoúčelný profil na člověka.
- Je potřeba **jasně odlišit fakt od interpretace**. „Zastupitel X hlasoval pro" je fakt. „Zastupitel X prosadil" je interpretace a na tento web nepatří.

### 7.4 Provozní rizika

| Riziko | Dopad | Řešení |
|---|---|---|
| Změna HTML na webu města | Sběrač spadne | Chyba v logu + notifikace, ruční oprava selektoru |
| Zpravodaj bez textové vrstvy | Nelze indexovat | Fallback na OCR (tesseract, čeština) |
| Portál usnesení nedostupný | Chybí hlavní sekce | Vydání vyjde s explicitní poznámkou o výpadku |
| Model si vymyslí údaj | Ztráta důvěryhodnosti | Čísla a jména se propisují z dat; každé tvrzení má zdroj |
| Projekt osiří | Web zestárne | Statický hosting přežije bez údržby; poslední vydání zůstane dostupné |

---

## 8. Fáze realizace

**Fáze 1 — Základ** *(nejkratší cesta k něčemu, co má smysl číst)*
Sběrač usnesení a hlasování · úřední deska · napojení na Hlídač státu · počasí · statický web · první týdenní vydání.

*Výstup: funkční týdenní přehled o radnici a penězích města.*

**Fáze 2 — Archiv zpravodaje**
Stažení všech 122 čísel · extrakce a rozdělení na články · fulltextové vyhledávání · propojení na osoby a témata.

*Výstup: prohledávatelná paměť města za posledních 11 let.*

**Fáze 3 — Lidé a souvislosti**
Profily zastupitelů s hlasovací historií · vedení městských firem · časové osy témat · dashboard peněz.

*Výstup: možnost sledovat konkrétní lidi a konkrétní kauzy v čase.*

**Fáze 4 — Rozšíření**
Mediální monitoring · diff-monitoring · historické osobnosti · e-mailový odběr vydání · RSS, které město nemá.

---

## 9. Otevřené otázky

Tyto věci se musí rozhodnout, než se začne stavět — každá z nich mění rozsah práce:

1. **Veřejný web, nebo soukromý?** Veřejný znamená vyřešit autorská práva ke zpravodaji a osobní údaje pořádně. Soukromý pro vlastní potřebu je výrazně jednodušší a lze ho zveřejnit později.
2. **Doména a název.** Pracovní název „Mariánky" nemusí být finální.
3. **Jak hluboko zpět jít s archivem zpravodaje?** Všech 122 čísel, nebo jen posledních pár let? Ovlivňuje to délku prvního dávkového běhu, ne provoz.
4. **Sledovat i okolní obce** (Velká Hleďsebe, Drmoul, Tři Sekery), nebo jen katastr města?
5. **Kdo to bude provozovat**, když bude potřeba opravit rozbitý sběrač?

---

## 10. Shrnutí ověření

Co bylo 17. 8. 2026 fakticky otestováno, ne předpokládáno:

- ✅ Portál usnesení vrací kompletní HTML včetně jmenovitých hlasování; vyžaduje `User-Agent`
- ✅ Zpravodaj má textovou vrstvu; extrakce dává správné pořadí čtení a čistou češtinu; OCR není běžně potřeba
- ✅ Hlídač státu poskytuje strukturovaná data o městě i celém holdingu, včetně K-indexu
- ✅ Seznam 21 zastupitelů i s politickou příslušností je veřejně dostupný
- ✅ Seznam 6 obchodních společností a 18 příspěvkových organizací je zjistitelný
- ❌ RSS na webu města neexistuje — nutný scraping a diff-monitoring
- ❌ Facebookové skupiny nejsou automatizovaně dostupné — nutný degradovaný režim
- ⚠️ Podíly u dvou částečně vlastněných firem je nutné dohledat v obchodním rejstříku
