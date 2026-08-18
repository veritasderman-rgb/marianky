# Provoz

Co spustit, v jakém pořadí a co dělat, když něco selže.

---

## Rychlý start

```bash
# jednorázově
pip install requests selectolax
sudo apt-get update && sudo apt-get install -y poppler-utils   # bez update selže na 404
cd web && npm install

# token Hlídače státu (zdarma po registraci na hlidacstatu.cz)
echo 'HLIDAC_TOKEN=...' > .env      # .env je mimo git, nikdy ho necommituj

# týdenní běh
python3 run_tyden.py
```

Vydání se generuje do `data/vydani/`, web se staví z `web/`.

---

## Dvě věci, které musí proběhnout z tvé sítě

Kontejner, ve kterém projekt vznikal, má u dvou zdrojů zablokovaný přístup. **Není to chyba kódu** a z jiné sítě to má fungovat napoprvé.

### 1. Přepisy jednání zastupitelstva

YouTube na sdílené adrese kontejneru vracel `HTTP 429`. Výpis playlistu prošel (proto víme, že záznamů je 94), stažení titulků ne.

```bash
python3 scrapers/zaznamy.py     # seznam záznamů + spárování s usneseními
python3 -m pipeline.prepis      # titulky → prohledávatelné bloky s odkazem na vteřinu
```

#### Titulky NEJSOU — ověřeno, cesta vede jen přes Whisper

Tohle je zjištěné, ne odhadnuté, a **ruší dřívější předpoklad, že stačí stáhnout automatické titulky**.

Knihovnou `youtube-transcript` bylo otestováno osm záznamů zastupitelstva napříč roky 2024–2026. Výsledek: **0 z 8**, u všech `TranscriptDisabledError`. Kontrolní video s titulky přitom prošlo (61 segmentů), takže **nejde o blokaci prostředí** — město má u svých záznamů titulky prostě vypnuté.

Z toho plyne, že žádný nástroj na stahování přepisů nepomůže. Není co stahovat.

**Zbývá tedy jediná cesta: přepis ze zvuku (Whisper).** Rozsah je změřený z playlistu:

| | |
|---|---|
| záznamů | 93 (delších než 10 minut) |
| celkem zvuku | **312 hodin** |
| medián délky | 3,5 h |
| nejdelší | 7,3 h |

To je práce na dny strojového času, ne na odpoledne. Rozumný postup:

1. **Začni jedním záznamem**, ať víš, jaká je kvalita přepisu u sálového zvuku a jestli dává smysl pokračovat.
2. Použij `faster-whisper` s modelem `small` nebo `medium` a češtinou (`--language cs`); `large` je přesnější, ale na 312 hodin neúměrně pomalý.
3. **Na GPU to trvá hodiny, na CPU dny.** Dá se to rozložit — pipeline zpracuje každý záznam samostatně, takže se dá přidávat postupně.
4. Stahování zvuku (`yt-dlp`) musí běžet z tvé sítě, kontejner má IP blokovanou.

Priority podle užitku: nejnovější volební období napřed, starší záznamy až potom.

Skript rozliší „video nemá titulky" od „YouTube nás odmítl" — druhé je chyba prostředí, ne zdroje.

#### Co přesně blokuje a co s tím nepomůže

Ověřeno měřením, ne odhadem: požadavek na stránku videa se přesměruje na `google.com/sorry/index`, což je **antiabuzní blokace Googlu**, a se souhlasovou cookie přijde `HTTP 429` s hláškou o neobvyklém provozu.

Blokace tedy sedí na **odchozí IP adrese**, ne na použité metodě. Z toho plyne praktický důsledek:

- **Nástroj běžící ve stejném prostředí nepomůže** — ať jde o `yt-dlp`, knihovnu pro přepisy nebo jinou obálku, všechny nakonec sáhnou na tutéž adresu z téže IP a dostanou tentýž 429. Souhlasová cookie ani jiná hlavička na tom nic nemění.
- **Pomůže cokoliv, co běží jinde** — spuštění z vlastní sítě, nebo služba, která přepis stáhne na svých serverech a vrátí hotový text.

#### Tři cesty, jak přepis pořídit

Pipeline je schválně nenáročná na to, odkud text přijde. Stačí soubor v `data/zaznamy/titulky/` pojmenovaný podle identifikátoru videa:

| formát | přípona | odkud |
|---|---|---|
| titulky WebVTT | `.vtt` | `yt-dlp`, stažení z vlastní sítě |
| titulky SubRip | `.srt` | Whisper a většina přepisovacích nástrojů |
| **prostý přepis** | `.txt` | **tlačítko „Zobrazit přepis" přímo na YouTube — zkopírovat a vložit** |

Poslední řádek je záměrná pojistka: prostý přepis se střídavými řádky „čas / text" **nepotřebuje žádný nástroj, přihlášení ani průchodnou IP adresu**. Když všechno ostatní selže, přepis se dá pořídit ručně a pipeline ho zpracuje stejně — rozdělí na bloky, přiřadí řečníky a udělá odkazy na vteřinu záznamu.

```bash
# ať už přepis vznikl jakkoliv:
cp muj-prepis.txt data/zaznamy/titulky/ml3vq41WpEs.txt
python3 -m pipeline.prepis
```

### 2. Aktuální úřední deska

`www.muml.cz` nám **resetuje spojení ještě před TLS**, a to i na `robots.txt`. Portál usnesení na hostu `usneseni.muml.cz` přitom jede normálně, takže jde o blokaci konkrétního hosta, ne o výpadek města.

Nejspíš jsme si to způsobili sami: v jedné fázi na web chodilo pět modulů naráz a stáhlo se z něj 1,7 GB. `lib/core.fetch()` proto teď drží minimální odstup mezi požadavky na stejný server (1,5 s na `muml.cz`), aby se to neopakovalo.

**Důsledek pro data:** úřední deska je natažená jen do **května 2025** a chybí aktuální stav. Týdenní vydání to nezakrývá — sekce dostane stav `zastarale` a napíše, že o tom období nemáme data.

```bash
python3 scrapers/muml.py        # až bude web dostupný
python3 -m pipeline.vydani      # přegenerovat vydání
```

---

## Týdenní běh

`run_tyden.py` spouští sběrače a pak navazující zpracování. Je inkrementální — bere jen to, co přibylo.

```bash
python3 run_tyden.py                 # celý běh
python3 run_tyden.py --bez-sberu     # jen přepočítat z už stažených dat
python3 run_tyden.py --jen usneseni hlasovani
```

Návratový kód **1** znamená, že selhal povinný zdroj. Log každého běhu je v `data/logy/{datum}/`.

### Co se rozlišuje a proč na tom záleží

Každá sekce vydání nese stav:

| stav | význam |
|---|---|
| `ok` | data se načetla a v období se něco dělo |
| `prazdno` | data se načetla a v období opravdu nic nebylo |
| `chybi` | zdroj nebyl dostupný — **o období nevíme nic** |
| `zastarale` | zdroj odpověděl, ale končí dávno před obdobím |

Tohle je páteř celé důvěryhodnosti. Kdyby „nic se nedělo" splynulo s „nepodařilo se načíst", přehled by tiše lhal právě v tom týdnu, kdy by na tom nejvíc záleželo.

### Znaky sekcí

Poslední krok běhu je `pipeline.znaky_sekci`. Spočítá z hotových dat miniaturní grafiku, kterou má na webu každá sekce — sloupce ročních výdajů u peněz, hranici katastru u mapy, 21 teček u zastupitelstva. Vzniká `data/znaky/sekce.json`, web z něj při buildu skládá SVG.

Není povinný: bez něj se web sestaví a odkazy fungují, dlaždice rozcestníku jen nemají obrázek dat a na stránce je o tom napsaná hláška.

Znak je vždy graf ze skutečných dat, nikdy piktogram. Proto se dá i pokazit stejně jako graf, a `kontrola.py` na to má test: **znak nesmí kreslit ve všech bodech stejnou hodnotu.** Přesně to se stalo napoprvé — znak hlasování ukazoval „podíl schválených návrhů", jenže portál zveřejňuje jen schválená hlasování, takže podíl byl u všech 12 349 záznamů 100 %. Obrázek se tvářil, že něco měří, a přitom kreslil konstantu. Teď ukazuje počet hlasování za rok s barevnou špičkou nejednomyslných — a je z něj vidět, že jich ubývá: ze 131 z 471 v roce 2012 na 57 z 968 v roce 2025.

### Schémata

Po znacích sekcí běží `pipeline.diagramy`. Spočítá osm schémat do `data/diagramy/*.json`; web z nich při buildu skládá SVG na `/diagramy` a na stránky sekcí.

Šest schémat je celé z dat města. Dvě — mapa „který zdroj plní kterou sekci" a datový model projektu — stojí na `config/diagramy.json`, protože to je znalost o projektu, ne údaj o městě. **Když se přidá zdroj nebo se změní struktura dat, musí se ten soubor upravit ručně;** sběr to nepozná.

Schéma týdenního běhu si seznam kroků čte přímo z `run_tyden.py`, takže se nemůže rozejít s tím, co se v neděli spustí. Nový modul se v diagramu objeví sám.

Modul není povinný. Bez něj se web sestaví a stránka `/diagramy` napíše, že se schémata nepodařilo spočítat.

Zastaralost se poměřuje **tolerancí podle toho, jak často se zdroj mění** — rada zasedá po dvou týdnech, takže týden bez usnesení je normální stav, kdežto tři týdny bez pohybu na úřední desce nikoliv. Bez tolerance by se hlásil poplach skoro každý druhý týden a přestal by být slyšet.

---

## Web

```bash
cd web
npm run build      # astro build + pagefind
npm run preview
```

### Nasazení na Vercel

Konfigurace je ve **dvou souborech schválně**. Vercel čte `vercel.json` z adresáře nastaveného jako Root Directory:

| Root Directory | přečte se | výsledek |
|---|---|---|
| kořen repozitáře (výchozí) | `/vercel.json` | build se spustí ve `web/`, výstup `web/dist` |
| `web` | `/web/vercel.json` | build se spustí přímo tam |

Obojí vede ke stejnému výsledku, takže nasazení **nezávisí na tom, jestli si někdo v administraci vzpomene Root Directory přepnout**. Bez kořenové konfigurace Vercel na kořeni nenajde žádný framework, nenasadí nic a každá adresa vrátí `404 NOT_FOUND`.

Build musí běžet **s celým checkoutem** — web čte `data/` a `config/` z kořene repozitáře, ne z `web/`. Cestu jde přebít proměnnou `MARIANKY_DATA`.

**Dvě věci, na kterých to spadlo v praxi:**

1. **Chybějící větev `main`.** Vercel má výchozí produkční větev `main`; když v repozitáři není, neproběhne žádné produkční nasazení a produkční adresa vrací 404 — i když se deploy „povede". Buď musí `main` existovat, nebo se v *Settings → Git → Production Branch* nastaví jiná.
2. **`vercel.json` nesmí obsahovat cizí klíče.** JSON nemá komentáře a Vercel schéma odmítá i klíč typu `_comment` chybou *„should NOT have additional property"*. Vysvětlivky patří sem do dokumentace, ne do konfigurace.

Když adresář s daty není vidět, build projde, ale do logu vypíše `[mariánky] POZOR: adresář s daty neexistuje`. Bez toho by prázdný web vypadal jako stav světa, ne jako špatná konfigurace.

**Neveřejnost zajišťuje neznámá adresa** — žádné heslo, žádné přihlášení. Web má `robots.txt` s `Disallow: /` a `noindex` na každé stránce, aby se adresa nedostala do vyhledávačů sama od sebe. To ale **není ochrana**: kdo adresu dostane, dostane se dovnitř, a kdyby ji někde zveřejnil, je veřejná. Ber to podle toho, komu ji dáváš.

Do gitu jde **extrahovaný text zpravodaje, ne PDF** — originály mají 1,7 GB. Bez toho textu by web na Vercelu neměl z čeho archiv postavit.

---

## Když něco selže

| Příznak | Příčina | Co s tím |
|---|---|---|
| `503` z portálu usnesení | chybí `User-Agent` | `core.fetch()` ji posílá; vlastní klient si ji musí přidat |
| `500` z AJAX výpisu usnesení | chybí `X-Requested-With: XMLHttpRequest` | předat přes `headers=` |
| rozsypaná čeština | odpověď nemá v `Content-Type` charset | `core.fetch()` to řeší; vlastní klient musí dekódovat sám |
| `000` / reset spojení z `muml.cz` | blokace hosta | počkat, spustit odjinud; tempo drží `core.fetch()` |
| `429` z YouTube | omezení sdílené adresy | spustit z vlastní sítě |
| `302` na přihlášení z Hlídače | chybí nebo je neplatný token | zkontrolovat `.env` |
| `apt-get` selže na 404 u poppleru | zastaralý index | nejdřív `apt-get update` |

---

## Na co si dát pozor v datech

Věci ověřené v praxi, které vypadají jako chyba, ale nejsou — nebo naopak.

- **Portál vede všech 12 349 hlasování jako „schváleno"**, včetně tří, kde je proti víc hlasů než pro. Pole `vysledek` proto **není spolehlivý údaj** — pracuj s počty hlasů.
- **Příznak „omluven" ve starších datech neexistuje** (zastupitelstvo od 2019, rada od 2023). Mimo spolehlivé období se smí ukazovat jen souhrnná neúčast, nikdy rozpad na omluvené a neomluvené. Jinak by z jednoho zastupitele vyšlo 793 neomluvených absencí — což je tvrzení o zdroji, ne o člověku.
- **`vazba_na_politiky` u smluv je vždy `null`**, protože API Hlídače to pole nevyplňuje. Je to *neznámo*, ne ověřená nula. Vazby na politiky dokládá `pipeline/propojeni.py` přes angažmá osob ve firmách.
- **Registr smluv začal 1. 7. 2016**, usnesení máme od 2012. U starších usnesení „smlouva nenalezena" neznamená nic.
- **Fyzické osoby jsou v usneseních anonymizované** (`*****`), takže se párují jen přes IČO, které u nich zdroj většinou nemá.
- **Směr peněz u nájmů a prodejů majetku je v registru nespolehlivý.** Zveřejňovatel (město) se zapisuje do pole `platce` i tam, kde peníze inkasuje. Z toho vycházelo, že město platí kavárně Café Classic 16 milionů — přitom kavárna platí nájem za prostor na Hlavní 131, který město vlastní. Takové smlouvy (623 z 6 521, celkem 314 mil.) nesou `smer_jistota: "neprukazne"` a v agregaci mají vlastní směr `neurcen`; **do součtů výdajů ani příjmů nevstupují**. Směr se schválně NEPŘEPISUJE podle klíčových slov — otočit ho dohadem by jednu domněnku nahradilo druhou.
  **Zbytková nepřesnost:** pravidlo pozná jen smlouvy, které mají nájem či prodej v předmětu. Smlouva pojmenovaná pouze adresou (u Café Classic „Cafe Classic – Hlavní 131", 8,2 mil.) projde dál jako výdaj, i když jde nejspíš o tentýž nájemní vztah. U protistran, kde je aspoň jedna smlouva neprůkazná, to přehled firem uvádí větou „u dalších smluv směr peněz určit nelze".
- **TDS je městská firma**, ne cizí dodavatel. Peníze, které jí od města tečou, jsou vnitřní převod a musí být takto označené.
- **Nemocnice už městu nepatří.** Sleduje se dál, ale do součtů holdingu nevstupuje.
- **Řetěz usnesení → smlouva** je odhad. Vysokou a střední jistotu lze publikovat jako zjištění, **nízkou jen jako označenou domněnku**.
