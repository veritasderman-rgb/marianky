# Na co se ptát podle stovky šestky: smlouvy uveřejněné pozdě

Náměty na žádosti podle zákona č. 106/1999 Sb., o svobodném přístupu k informacím, vytěžené z registru smluv. Téma je jedno: **smlouvy městského holdingu, které byly v registru uveřejněny pozdě** — a co se z toho podle zákona o registru smluv stalo s jejich platností a s penězi, které podle nich tekly.

**Jak to číst.** U každého námětu je oddělené, co je **doložený fakt** (dvě data z registru, text smlouvy, usnesení rady) a co je **otázka** — tedy to, co z veřejných dat zjistit nejde a je to právě důvod, proč se ptát. Nic z toho není výrok o tom, že smlouva je neplatná nebo že někdo pochybil. Je to porovnání dvou dat s literou zákona a otázky, které z něj plynou.

Čísla v tomhle dokumentu vznikla takto: `scrapers/registr_lhuty.py` stáhl ke každé smlouvě ze sklizně Hlídače stránku záznamu v registru (datum uzavření, datum **prvního** uveřejnění, hodnotu bez DPH), `pipeline/lhuty_prehled.py` je porovnal s lhůtami zákona. Výstup je v `data/penize/lhuty_prehled.json` a dá se přepočítat.

---

## 1. Co říká zákon (a co z toho nejde vyčíst z dat)

Zákon č. 340/2015 Sb., o registru smluv, ve znění k 1. 1. 2025 ([zakonyprolidi.cz](https://www.zakonyprolidi.cz/cs/2015-340)):

| ustanovení | co říká | jak se to projevuje v datech |
|---|---|---|
| § 2 odst. 1 | povinnost uveřejnit má mj. obec (písm. b), její příspěvková organizace (písm. g), o.p.s. jí založená (písm. i) a právnická osoba, v níž má obec většinový podíl (písm. m) | všech 24 sledovaných subjektů holdingu, s výhradou u Městské dopravy (město nemá 100 %) a Nemocnice (už městu nepatří) |
| § 3 odst. 2 písm. h) | neuveřejňuje se smlouva s hodnotou předmětu **do 50 000 Kč bez DPH včetně** | posuzují se jen smlouvy nad tuto hranici; kde registr hodnotu bez DPH neuvádí, odhaduje se z hodnoty s DPH a je to označené |
| § 3 odst. 2 písm. a) | neuveřejňuje se smlouva s fyzickou osobou mimo její podnikání (neplatí pro převod nemovitosti) | protistrana bez IČO je označená jako „možná výjimka" — z metadat se nepozná, zda jde o nepodnikatele a zda nejde o nemovitost |
| § 5 odst. 2 | smlouvu je třeba zaslat k uveřejnění **bez zbytečného odkladu, nejpozději do 30 dnů** od uzavření | lhůta je pořádková: její překročení samo o sobě sankci nemá |
| § 6 odst. 1 | smlouva **nabývá účinnosti nejdříve dnem uveřejnění** | plnění poskytnuté před uveřejněním nemá smluvní právní důvod — je to bezdůvodné obohacení (§ 2991 o. z.) |
| § 7 odst. 1 | nebyla-li smlouva uveřejněna **ani do tří měsíců od uzavření, platí, že je zrušena od počátku** | nevyvratitelná domněnka, působí ze zákona, soud ji nevyslovuje; Nejvyšší soud ji staví na roveň absolutní neplatnosti |
| § 7 odst. 2 | zrušení se nepoužije, byla-li neuveřejněna jen část smlouvy nebo chybně vyloučena metadata a strana to opraví do 30 dnů od zjištění | z dat nejde poznat; verze záznamu > 1 naznačuje opravu |
| § 8 odst. 6 | dodržování zákona **nepodléhá dozoru ani kontrole** podle zákona o obcích | kraj ani ministerstvo to z úřední moci nekontrolují |
| § 9 | § 6 a 7 se použijí poprvé na smlouvy uzavřené **1. 7. 2017** a později | smlouvy uzavřené dřív se do posuzování nepouštějí |

Ministerstvo vnitra k tomu vede [metodický návod](https://testrs.gov.cz/smlouva/soubor/232294/Metodicky_navod_k_aplikaci_ZRS_-_v1-11.pdf) (verze 1.11, leden 2021); ten výslovně počítá s tím, že plnění před účinností je bezdůvodné obohacení.

**Co z registru vyčíst nejde a proto se musí ptát úřadu:**

- zda a kdy bylo **plněno** — tedy zda dodavatel pracoval a město platilo v době, kdy smlouva ještě nebyla účinná (nebo kdy už byla ze zákona zrušená),
- zda strany stav **vypořádaly** (dohodou o narovnání podle § 1903 o. z., dohodou o vypořádání bezdůvodného obohacení, novou smlouvou),
- **kdo** měl uveřejnění na starosti (vnitřní předpis úřadu) a zda byla za pochybení vyvozena odpovědnost,
- zda u smluv financovaných z **dotace** poskytovatel o zrušení ví a zda došlo ke krácení.

## 2. Jaké jsou „tresty"

Zákon o registru smluv **žádnou pokutu ani přestupek nezná**. Jeho sankce jsou soukromoprávní a dopadají na smlouvu, ne na úředníka. Co z pozdního uveřejnění plyne:

1. **Smlouva není účinná** až do uveřejnění (§ 6 odst. 1). Co bylo plněno dřív, bylo plněno bez smlouvy.
2. **Smlouva je zrušena od počátku**, když se do tří měsíců neuveřejnila (§ 7 odst. 1). Platí to automaticky, i když to nikdo nenamítne, a i když obě strany dál plní, jako by nic.
3. **Bezdůvodné obohacení** na obou stranách (§ 2991 a násl. o. z.): dodavatel má vydat, co dostal, město má nahradit hodnotu toho, co dostalo. V praxi se to řeší dohodou o narovnání a započtením. Nejvyšší soud ale v rozsudku **23 Cdo 88/2025 z 24. 6. 2026** doplnil zásadní věc: u smlouvy zrušené podle § 7 odst. 1 má dodavatel nárok na peněžitou náhradu **jen do výše ceny hospodárného plnění, zpravidla ceny obvyklé** — pokud sjednaná cena byla nehospodárná, nad obvyklou cenu nedostane nic ([shrnutí na epravo.cz](https://www.epravo.cz/top/soudni-rozhodnuti/bezduvodne-obohaceni-121644.html)). Jinými slovy: zrušená smlouva otevírá otázku, zda město neplatilo víc, než muselo.
4. **Dotace**: plnění bez platného právního titulu může být nezpůsobilý výdaj a vést ke krácení nebo odvodu ([Bulušek, Skalská, epravo.cz 2018](https://www.epravo.cz/top/clanky/dusledky-poskytnuti-plneni-v-navaznosti-na-smlouvu-neuverejnenou-v-registru-smluv-107993.html)); u dotačních smluv samotných jde o porušení rozpočtové kázně podle § 22 zákona č. 250/2000 Sb. ([Kvapil, Hřebačka, Deník veřejné správy 2018](https://denik.obce.cz/clanek.asp?id=6755507)).
5. **Veřejné zakázky**: po zrušení smlouvy ze zadávacího řízení není jasné, zda se řízení „vrací" před podpis, nebo zda je nutné zadat zakázku znovu; ÚOHS zpětnou účinnost u takových smluv vylučuje (ÚOHS-R376/2015/VZ).
6. **Přezkoumání hospodaření** (zákon č. 420/2004 Sb.): kraj nebo auditor to sice z úřední moci „nedozoruje" (§ 8 odst. 6), ale neuveřejnění smlouvy v registru nebo uveřejnění po lhůtě se ve zprávách o přezkoumání objevuje jako chyba a nedostatek — Ministerstvo financí ve [souhrnné zprávě za rok 2024](https://mf.gov.cz/assets/attachments/2025-11-11_Souhrnna-zprava-o-vysledcich-prezkoumani-hospodareni-UC-za-rok-2024.pdf) vytýká auditorům, že „nezveřejnění smluv v registru smluv nebo zveřejnění až po uplynutí zákonné lhůty" nevyhodnotili jako porušení předpisů. Zprávy o přezkoumání města za roky 2021–2025 jsou na úřední desce jen jako skeny, bez textové vrstvy — co v nich k registru stojí, je samo otázka pro stovku šestku.
7. **Odpovědnost lidí**: podle zákona o finanční kontrole odpovídá za nastavení procesů vedoucí orgánu veřejné správy, v obci starosta; za škodu způsobenou zaviněným porušením pracovních povinností odpovídá zaměstnanec podle § 250 zákoníku práce (při nedbalosti do 4,5násobku průměrného měsíčního výdělku, § 257 odst. 2). Trestní rovina (§ 220 a § 221 trestního zákoníku, porušení povinnosti při správě cizího majetku) přichází v úvahu jen při vzniku škody — hranice jsou 50 000 Kč („nikoli malá") u úmyslné a 100 000 Kč („větší") u nedbalostní varianty a škodu by bylo nutné prokázat, což u plnění, které město skutečně dostalo, není samozřejmé. Žádný rozsudek, který by za pozdní uveřejnění trestal úředníka, dohledán nebyl.
8. **Kdo se může zrušení dovolat**: zákon to neříká. Určovací žaloby občanů soudy odmítají pro chybějící naléhavý právní zájem; schůdná cesta je podnět státnímu zastupitelství (§ 42 zákona o státním zastupitelství) nebo právě žádost o informace, která stav zdokumentuje ([Bouda, pravniprostor.cz 2016](https://www.pravniprostor.cz/clanky/ostatni-pravo/kdo-muze-iniciovat-zruseni-smlouvy-nezverejnene-v-souladu-se-zakonem-o-registru-smluv)).

Shrnuto: za pozdě uveřejněnou smlouvu nikdo pokutu nedostane. Město ale roky platilo podle smluv, které podle zákona neexistovaly, a u každé koruny z nich platí, že právním titulem není smlouva, ale bezdůvodné obohacení — s rizikem u dotací a s otázkou obvyklé ceny.

## 3. Co data ukazují

Registr smluv zná u 6 897 smluv městského holdingu datum uzavření i datum prvního uveřejnění (pět záznamů je na žádost subjektu znepřístupněných). Po odečtení smluv, na které § 6 a 7 nedopadají (uzavřené před 1. 7. 2017, do 50 000 Kč bez DPH, bez uvedené hodnoty), zbývá **5 144 posuzovaných smluv**:

| lhůta | smluv | podíl | objem podle Hlídače |
|---|---|---|---|
| do 30 dnů | 4 697 | 91,3 % | — |
| 31 dnů až 3 měsíce (účinnost až uveřejněním) | 355 | 6,9 % | 220,2 mil. Kč |
| **po 3 měsících (§ 7 odst. 1: zrušena od počátku)** | **92** | **1,8 %** | **33,4 mil. Kč** |
| z toho bez známky možné výjimky § 3 | 76 | | 30,9 mil. Kč |
| navíc: po 3 měsících, hodnota v registru neuvedena | 21 | | neznámý |

Devadesát dva smluv tedy podle registru nikdy nenabylo účinnosti. U šestnácti z nich data naznačují možnou výjimku (umělecký výkon u orchestru, zájezd do zahraničí u ZUŠ, fyzická osoba) — ty se v součtu drží zvlášť. U dalších 21 smluv registr neuvádí žádnou hodnotu, takže se hranice 50 000 Kč posoudit nedá; jsou mezi nimi smlouvy uveřejněné **pět až osm let** po uzavření (CENDIS 2018 → 2026, BAKALÁŘI 2018 → 2025, INISOFT 2018 → 2023).

**Kdo uveřejňuje pozdě** (podíl smluv uveřejněných po 30 dnech z posuzovaných, subjekty s alespoň 25 posuzovanými smlouvami):

| subjekt | posuzovaných | po 30 dnech | po 3 měsících | objem po 3 měs. |
|---|---|---|---|---|
| Mateřská škola Vora | 25 | 44,0 % | 6 | 0,98 mil. |
| ZUŠ F. Chopina | 80 | 40,0 % | 11 (5 bez možné výjimky) | 1,35 mil. |
| Mateřská škola Křižíkova | 39 | 38,5 % | 0 | — |
| Mateřská škola Na Třešňovce | 35 | 34,3 % | 5 | 0,75 mil. |
| DEVELOP CENTRUM | 36 | 30,6 % | 4 | 0,82 mil. |
| Západočeský symfonický orchestr | 75 | 28,0 % | 7 (0 bez možné výjimky) | 1,41 mil. |
| Správa městských sportovišť | 168 | 22,0 % | 8 | 5,72 mil. |
| Mateřská škola Hlavní 440 | 41 | 22,0 % | 1 | 0,06 mil. |
| Městská knihovna | 39 | 17,9 % | 0 | — |
| Mateřská škola Úšovice | 34 | 17,6 % | 1 | 0,24 mil. |
| TDS | 213 | 16,9 % | 7 | 11,07 mil. |
| Domov pro seniory | 205 | 16,1 % | 10 | 3,72 mil. |
| ZŠ Úšovice | 117 | 10,3 % | 1 | 1,63 mil. |
| ZŠ JIH | 157 | 10,2 % | 2 | 0,17 mil. |
| Infocentrum | 265 | 8,3 % | 3 | 0,44 mil. |
| Městská doprava | 76 | 7,9 % | 3 | 0,52 mil. |
| **Město Mariánské Lázně** | **3 556** | **4,7 %** | **29** | **15,26 mil.** |
| Městské divadlo | 89 | 2,2 % | 0 | — |

Město samo je na tom relativně nejlépe, ale největší částky jsou právě jeho — a jeho smlouvy s vlastní firmou TDS se počítají oběma. Malé příspěvkové organizace (školky, ZUŠ) uveřejňují pozdě každou třetí až druhou smlouvu.

**V čase** se to nelepší. Podíl smluv uveřejněných po 30 dnech klesl z 23,5 % v roce 2017 na 3,8 % v roce 2021, pak se vrátil: 8,1 % (2022), 6,6 % (2023), 5,1 % (2024), **12,6 % (2025)** a 11,3 % (2026, do října). Smluv po 3 měsících bylo v roce 2025 nejvíc za celou dobu (22).

**Odbory města** (registr uvádí útvar jen u části smluv): Odbor kultury, lázeňství, cestovního ruchu a UNESCO uveřejnil po 30 dnech 16 ze 74 smluv (23 %), Odbor rozvoje města, investic a dotací 18 ze 135 (15 %), Odbor správy majetku města 10 ze 127 (9 %). Odbor životního prostředí 3 z 55, ostatní odbory nula.

**Co se zřejmě plnilo před účinností.** Z 92 smluv po 3 měsících má 36 v předmětu objednávku (13) nebo průběžné plnění (svoz, dodávka energie, nájem, správa, služby) počínající dnem uzavření — u nich je plnění před uveřejněním nejen pravděpodobné, ale v několika případech přímo napsané v textu smlouvy (viz níže). Žádná ze smluv po 3 měsících nemá v registru druhou verzi, tedy opravu podle § 7 odst. 2.

**Kontrola proti Hlídači státu.** Hlídač u města hlásí 43 smluv s nálezem „Smlouva nebyla zveřejněna do 3 měsíců od podpisu a nikdy nezačala platit", tenhle výpočet 29 plus 15 bez ceny. Rozdíl je metodický: Hlídač počítá i smlouvy bez uvedené hodnoty (ty tu jsou vedené zvlášť), naopak tu přibyla jedna smlouva s fyzickou osobou (56 627 Kč bez DPH, Hlídač ji nejspíš považuje za podlimitní). Na úrovni jednotlivých smluv se obě metody shodují.

## 4. Konkrétní smlouvy, u kterých má žádost smysl

Seřazeno podle toho, kolik peněz a jak jasný právní problém je ve hře. U každé je uvedeno, co je doložené a na co se ptát. Čísla smluv a odkazy jsou v tabulce v příloze.

### 4.1 Svoz komunálního odpadu, TDS — 7,26 mil. a 1,29 mil. Kč ročně, 240 dnů

**Doloženo.** Dvě smlouvy o dílo mezi městem a TDS (shromažďování, sběr, svoz a odstraňování směsného komunálního odpadu; totéž u odpadkových košů), obě **uzavřené 1. 1. 2022, uveřejněné 29. 8. 2022**. Rada města uzavření schválila 7. 12. 2021 (usnesení RM 131/7). Text smlouvy: *„Zhotovitel zahájí činnost … od 01. 01. 2022"*, *„Smlouva je platná ode dne podpisu obou smluvních stran a účinná od 01. 01. 2022"*, cena se hradí *„na základě faktur vystavených měsíčně za práce realizované v uplynulém kalendářním měsíci"*. Smlouva je na dobu neurčitou. Hlídač ji eviduje s nálezem „nikdy nezačala platit". Tři týdny po uveřejnění, 20. 9. 2022, rada schválila Dodatek č. 1 (RM 158/9).

**Co z toho plyne podle zákona.** Smlouva se podle § 7 odst. 1 zrušila od počátku 1. 4. 2022; TDS vozilo odpad a město platilo měsíční faktury leden až srpen 2022 bez smlouvy a dál podle smlouvy, která podle zákona neexistuje. Ujednání o účinnosti od 1. 1. 2022 je v rozporu s § 6 odst. 1.

**Na co se ptát.** Faktury TDS za svoz odpadu a košů od ledna 2022 dosud s daty úhrad; na základě jakého právního titulu město platí od 1. 4. 2022; zda Dodatek č. 1 z září 2022 řešil účinnost nebo vypořádání a jeho text (v registru pod tímto předmětem dohledán nebyl); zda byla uzavřena nová smlouva nebo dohoda o narovnání; kdo měl uveřejnění na starosti a proč trvalo 240 dnů. Jde o smlouvu s vlastní firmou města, takže otázka obvyklé ceny z rozsudku 23 Cdo 88/2025 je tu zároveň otázkou in-house zadání bez soutěže.

### 4.2 Rekonstrukce trolejového vedení, Městská doprava — 28,7 mil. Kč, zrušení smlouvy přiznané

**Doloženo.** Dohoda o narovnání z 27. 7. 2023 mezi MĚSTSKOU DOPRAVOU Mariánské Lázně s.r.o. a Elektrizací železnic Praha a.s. říká doslova: smlouva o dílo z 2. 6. 2022 ze zadávacího řízení *„byla administrativní chybou zveřejněna v registru smluv až ke dni 25. 10. 2022 a došlo tím k překročení lhůty dle § 7 … smlouva byla tímto zrušena od počátku. Tato skutečnost se vztahuje i na dva následné dodatky"*; strany si započítávají bezdůvodné obohacení (dílo za 23,7 mil. bez DPH proti zaplacené ceně). Projekt je financovaný ze Státního fondu dopravní infrastruktury (rámcová smlouva 45 mil. Kč z 19. 4. 2022 kryje měnírnu a trolejové vedení). Ve stejný den, 4. 3. 2024, uzavřela Městská doprava další tři dohody o narovnání — k příkazním smlouvám na administraci obou zakázek (BM asistent) a ke smlouvě koordinátora BOZP (APOSTAV).

**Na co se ptát.** Městské dopravy (jako veřejné instituce) nebo města jako společníka: zda a kdy byl SFDI o zrušení smlouvy informován a jak rozhodl o způsobilosti výdajů; zda ÚOHS nebo poskytovatel řešili, že plnění veřejné zakázky proběhlo bez platné smlouvy; proč byly ve stejný den narovnány tři další smlouvy k týmž zakázkám (byly neuveřejněné také?); zda byla vyvozena odpovědnost za „administrativní chybu" a kolik stálo právní řešení. Pozor: Městská doprava není ze sta procent městská, u ní je povinnost podle InfZ třeba opřít o judikaturu k veřejným institucím; město jako společník informace má a poskytnout je musí.

### 4.3 Elektřina pro sportoviště — 5 mil. Kč, 198 dnů; a 3,7 mil. Kč, 36 dnů

**Doloženo.** Správa městských sportovišť uzavřela 27. 11. 2024 smlouvu o sdružených službách dodávky elektřiny ze sítě VN se SUAS Commodities (5 mil. Kč) **s účinností od 1. 1. 2025 do 31. 12. 2025**; uveřejněna 13. 6. 2025. Rok předtím podobná smlouva (3,7 mil. Kč, 6. 12. 2023) byla uveřejněna za 36 dnů.

**Co z toho plyne.** Elektřina tekla od ledna 2025, smlouva se zrušila od počátku 27. 2. 2025 a celý rok 2025 se dodávalo a platilo bez účinné smlouvy.

**Na co se ptát.** Faktury za elektřinu 2025 a jejich úhrady; zda SMS nebo zřizovatel stav vypořádali; kdo v příspěvkové organizaci za uveřejňování odpovídá a zda zřizovatel (odbor školství provádí veřejnosprávní kontroly příspěvkových organizací) na to při kontrole narazil.

### 4.4 Správa pohřebiště, TDS — 1,64 mil. Kč, 249 dnů

**Doloženo.** Smlouva o správě, provozu a údržbě veřejného pohřebiště mezi městem a TDS s účinností od 1. 9. 2023 (schváleno RM 529/23 z 22. 8. 2023), uveřejněná 6. 3. 2024. Sama smlouva stanoví, že uveřejnění *„zajistí nejpozději do 15 pracovních dnů ode dne uzavření … provozovatel"* — tedy TDS — a počítá s účinností dnem uveřejnění, dojde-li k němu později. Trvalo to půl roku.

**Na co se ptát.** Úhrady za správu pohřebiště září 2023 až březen 2024; zda město po TDS vymáhalo smluvní odpovědnost za porušení lhůty 15 dnů; zda byla uzavřena nová smlouva.

### 4.5 Rámcové kupní smlouvy na potraviny, Domov pro seniory — 5 × 605 tis. Kč, 100 až 103 dnů

**Doloženo.** Pět rámcových kupních smluv (MAKRO, V & M FROZEN) na maso, mléko, koloniál, ovoce a zeleninu, uzavřených 25. a 28. 4. 2025, všechny uveřejněné 6. 8. 2025. Tříměsíční lhůta uplynula o týden až deset dnů. Domov pro seniory má 10 smluv po 3 měsících, nejvíc ze všech příspěvkových organizací počtem; objemem (3,7 mil.) je druhý za Správou sportovišť.

**Na co se ptát.** Odběry a faktury z těchto rámcových smluv květen až srpen 2025; zda jsou dodávky od srpna 2025 kryté novou smlouvou; vnitřní předpis Domova k registru smluv a kdo smlouvy do registru vkládá.

### 4.6 Teplo pro školy od Veolie — 1,63 mil. Kč (ZŠ Úšovice, 379 dnů) a 2 × 286 tis. Kč (MŠ Vora, 368 dnů)

**Doloženo.** Roční cenová ujednání k dodávce tepla (RECE VEML) uzavřená 10. 1. 2018, resp. 4. 1. 2020, uveřejněná až po skončení roku, na který platila. Totéž u ZŠ JIH v roce 2023 (3 × 2,3 mil., 35–36 dnů). Smlouvu uveřejňuje jedna ze stran; u Veolie je obvyklé, že to dělá škola.

**Na co se ptát** (zřizovatele, tj. města, nebo přímo škol): kdo podle smlouvy uveřejňuje; zda škola za teplo v roce 2018, resp. 2020 platila podle neúčinné smlouvy a zda to zřizovatel při veřejnosprávní kontrole zjistil. Město samo ve zprávě z kontrol za rok 2019 uvádí, že jedna příspěvková organizace „neuveřejnila smlouvu nad 50 000 Kč prostřednictvím registru smluv, a to ani do tří měsíců" — stojí za to chtít, které a co se stalo dál.

### 4.7 Dar od Hasičského záchranného sboru — 1 mil. Kč, 367 dnů

**Doloženo.** Darovací smlouva, podle níž HZS Karlovarského kraje daruje městu 1 mil. Kč, uzavřená 6. 1. 2024, uveřejněná 7. 1. 2025 (uveřejnil HZS). Po 6. 4. 2024 je podle § 7 zrušená.

**Na co se ptát.** Zda město dar přijalo a kdy; z jakého titulu ho drží, když darovací smlouva zanikla; zda strany uzavřely novou smlouvu. Je to zrcadlový případ: tady je město příjemcem a riziko vrácení peněz je na jeho straně.

### 4.8 DEVELOP CENTRUM: zpětná účinnost sjednaná výslovně, parkování a příkazní smlouvy

**Doloženo.** Dohoda o narovnání vztahů z příkazních smluv mezi městem a DEVELOP CENTRUM z 23. 1. 2026 (3 mil. Kč bez DPH ročně, uveřejněna 10. 2. 2026, schválena RM 910/26) obsahuje větu: *„Smluvní strany … explicitně sjednávají zpětnou účinnost dohody a její přílohy … k 01. 01. 2026"* s odůvodněním, že prodleva mezi schválením a zveřejněním *„není v kontextu všech okolností významná"*. Zároveň konstatuje, že příkazní smlouva na parkování ze 31. 7. 2024 zanikla uzavřením nájemní smlouvy a že odměna z příkazní smlouvy na bydlení *„již není … vyplácena"*. Samostatně: smlouva o užívání parkovacích stání PARKING CENTRUM s.r.o. (363 tis. Kč, 1. 1. 2024) byla uveřejněna po 165 dnech; 13. 1. 2026 uzavřelo DEVELOP CENTRUM „smlouvu o užívání parkovacích stání a o vypořádání bezdůvodného obohacení" (726 tis. Kč). Čtyři smlouvy DEVELOP CENTRUM jsou po 3 měsících, včetně dvou objednávek studií z léta 2026.

**Co z toho plyne.** Zpětná účinnost smlouvy povinného subjektu je v rozporu s kogentním § 6 odst. 1 (Nejvyšší soud 23 Cdo 5457/2014 zpětné účinky proti kogentním normám nepřipouští); odměna za leden 2026 byla tedy vyplacena za období před účinností.

**Na co se ptát.** Faktury DEVELOP CENTRUM za leden a únor 2026 a právní titul; na základě čeho vzniklo bezdůvodné obohacení vypořádávané smlouvou z 13. 1. 2026 a v jaké výši; úhrady za parkovací stání leden až červen 2024; právní stanovisko, o něž se opírá sjednaná zpětná účinnost (pokud existuje jako dokument).

### 4.9 Čtyřicet dohod o narovnání napříč holdingem

**Doloženo.** V registru je asi 40 dohod o narovnání nebo vypořádání bezdůvodného obohacení subjektů holdingu, z toho většina u škol s předmětem *„Dohoda o narovnání k objednávce ze dne …"* (ZŠ Vítězství šestkrát, ZŠ Úšovice sedmkrát, MŠ Vora, MŠ Úšovice, MŠ Hlavní, knihovna, muzeum). To je učebnicový způsob, jak se řeší objednávka, která se do registru nedostala včas — a zároveň jediná stopa po smlouvách, které v registru vůbec nejsou.

**Na co se ptát** (město jako zřizovatel): seznam dohod o narovnání uzavřených příspěvkovými organizacemi z důvodu neuveřejnění původní objednávky nebo smlouvy, s původní smlouvou a částkou; zda zřizovatel vede o takových případech evidenci a zda z nich plynula opatření.

### 4.10 Smlouvy bez ceny uveřejněné po letech

**Doloženo.** 21 smluv od roku 2017 bez uvedené hodnoty, uveřejněných po 3 měsících; město jich má 14. Nejdelší prodlevy: smlouva s CENDIS, s.p. na technické zařízení pro digitalizované fotografie a podpisy (2018, uveřejněna 2026, 2 879 dnů) a její prodloužení (2022 → 2026), dodatek k servisní smlouvě INISOFT (2018 → 2023), smlouva o dodávce vody CHEVAK (2021 → 2025), výpůjčka budovy č. p. 74 v Ruské ulici jako náhradní radnice (2018 → 2021), smlouva s KOTEC o.p.s. na protidrogového koordinátora (2023 → 2024). Chybějící cena v metadatech je sama nedostatkem (§ 5 odst. 5: bez ceny se smlouva nepovažuje za uveřejněnou), takže u těchto smluv je otázka účinnosti dvojnásobná.

**Na co se ptát.** Hodnotu plnění každé z nich a úhrady; proč byly uveřejněny s prodlevou let (u CENDIS a INISOFT jde patrně o dodatečné „dočištění" registru v létě 2026 a v roce 2023 — kdo ho dělal a na základě čeho); zda město vede evidenci smluv, které v registru chybí.

### 4.11 Co nejspíš kauza není

Západočeský symfonický orchestr (7 smluv po 3 měsících, 1,4 mil.) a ZUŠ F. Chopina (zájezdy do zahraničí, letenky) mohou spadat pod výjimky § 3 odst. 2 písm. i) a d) — autorské dílo a umělecký výkon, plnění převážně mimo ČR. Hlídač je přesto počítá mezi zásadní nedostatky. Smlouvy uveřejněné 31 až 90 dnů po uzavření (355 smluv, 220 mil. Kč, mezi nimi silniční stavby za 11,7 a 4,9 mil.) jsou porušením pořádkové lhůty, ale právní následek je jen posun účinnosti — plnění před uveřejněním u nich bývá kratší a u stavebních zakázek často žádné. Jsou vypsané v `data/penize/lhuty_prehled.json`, pole `pozde_do_3m`.

## 5. Systémové otázky pro úřad

Jednotlivé smlouvy ukazují na proces. Co se stát nemělo a stalo se opakovaně:

- **Lhůta uveřejnění není v rukou jedné osoby.** U pohřebiště uveřejňoval provozovatel (TDS), u Veolie škola, u HZS dárce, u SUAS příspěvková organizace. Město má vnitřní předpis k registru smluv? Pokud ano, platí i pro příspěvkové organizace a městské firmy?
- **Kontrola ex post chybí nebo nefunguje.** Smlouvu z roku 2018 a její prodloužení z roku 2022 uveřejnilo město v srpnu 2026 — někdo registr procházel. Výsledek toho procházení (seznam dohledaných neuveřejněných smluv) je informace, kterou lze žádat.
- **Příspěvkové organizace** uveřejňují pozdě třetinu až polovinu smluv. Zřizovatel u nich dělá veřejnosprávní kontroly a v roce 2019 jednu takovou chybu zjistil. Zprávy z kontrol za roky 2020–2025 a jejich zjištění k registru smluv jsou k dispozici na žádost.
- **Přezkoumání hospodaření** za roky 2021–2025 (Krajský úřad Karlovarského kraje) je na úřední desce jen jako sken; zda kraj registr smluv vytkl a co město přijalo za opatření, se dá zjistit jedinou žádostí.
- **Rok 2025** byl nejhorší od roku 2017 — 12,6 % smluv po lhůtě a 22 smluv po 3 měsících. Co se v roce 2025 změnilo (personálně, v systému spisové služby, v předpisech)?

## 6. Pořadí, kdyby mělo jít jen o pár žádostí

1. Svoz odpadu TDS 2022 (4.1) — nejvyšší částka, nejjasnější důkaz plnění před účinností, in-house.
2. Systémová žádost (vnitřní předpis, evidence pozdních smluv, dohody o narovnání, zprávy z kontrol a přezkumu) — jedna žádost, odpověď pokryje všechno ostatní.
3. Trolejové vedení Městské dopravy (4.2) — dotace SFDI, veřejná zakázka, zrušení přiznané písemně.
4. Elektřina SMS 2025 (4.3) a pohřebiště TDS (4.4).
5. DEVELOP CENTRUM a zpětná účinnost (4.8).

---

## Příloha: všech 92 smluv uveřejněných po 3 měsících od uzavření

Smlouvy uzavřené od 1. 7. 2017 s hodnotou nad 50 000 Kč bez DPH (nebo odhadem z hodnoty s DPH), seřazené podle částky z Hlídače (s DPH). Sloupec „možná výjimka" je odhad z předmětu a protistrany, ne zjištění. Stav registru k 26. 10. 2026.

| uzavřeno | uveřejněno | dnů | Kč (Hlídač) | protistrana | předmět | subjekt | možná výjimka | odkaz |
|---|---|---|---|---|---|---|---|---|
| 2022-01-01 | 2022-08-29 | 240 | 7 260 000 | TECHNICKÝ A DOPRAVNÍ SERVIS, s.r.o. | Shromažďování, sběr, svoz, využívání nebo odstraňování směsného komunálního odpa | město + TDS |  | [registr](https://smlouvy.gov.cz/smlouva/21469611) |
| 2024-11-27 | 2025-06-13 | 198 | 5 000 000 | SPRÁVA MĚSTSKÝCH SPORTOVIŠŤ příspěvková organizace | Smlouva o sdružených službách dodávky elektřiny ze sítě VN | SMS |  | [registr](https://smlouvy.gov.cz/smlouva/33679356) |
| 2023-07-01 | 2024-03-06 | 249 | 1 640 178 | TECHNICKÝ A DOPRAVNÍ SERVIS, s.r.o. | Smlouva o správě, provozu a údržbě veřejného pohřebiště v Mariánských Lázních +  | město + TDS |  | [registr](https://smlouvy.gov.cz/smlouva/27882135) |
| 2018-01-10 | 2019-01-24 | 379 | 1 634 710 | Veolia Energie Mariánské Lázně, s.r.o. | RECE VEML/44727/OD/201901 | Základní škola Úšovice, Školní náměstí 472 |  | [registr](https://smlouvy.gov.cz/smlouva/7994499) |
| 2022-01-01 | 2022-08-29 | 240 | 1 294 000 | TECHNICKÝ A DOPRAVNÍ SERVIS, s.r.o. | shromažďování, sběr, svoz, využívání nebo odstraňování směsného komunálního odpa | město + TDS |  | [registr](https://smlouvy.gov.cz/smlouva/21469615) |
| 2024-01-06 | 2025-01-07 | 367 | 1 000 000 | Hasičský záchranný sbor Karlovarského kraje | Darovací smlouva - finanční prostředky | město |  | [registr](https://smlouvy.gov.cz/smlouva/31652724) |
| 2025-04-28 | 2025-08-06 | 100 | 605 000 | V & M FROZEN mořský potvory, s.r.o. | Rámcová kupní smlouva č. 21/2025 Dodávka komodity - ovoce a zelenina | Domov pro seniory |  | [registr](https://smlouvy.gov.cz/smlouva/37795469) |
| 2025-04-28 | 2025-08-06 | 100 | 605 000 | MAKRO Cash & Carry ČR s.r.o. | Rámcová kupní smlouva č. 20/2025 Dodávka komodity - koloniál, nápoje | Domov pro seniory |  | [registr](https://smlouvy.gov.cz/smlouva/34352001) |
| 2025-04-28 | 2025-08-06 | 100 | 605 000 | MAKRO Cash & Carry ČR s.r.o. | Rámcová kupní smlouva č. 19/2025 Dodávka komodity - mléko a mléčné výrobky | Domov pro seniory |  | [registr](https://smlouvy.gov.cz/smlouva/34351745) |
| 2025-04-28 | 2025-08-06 | 100 | 605 000 | MAKRO Cash & Carry ČR s.r.o. | Rámcová kupní smlouva č. 18/2025 Dodávka komodity - ovoce a zelenina | Domov pro seniory |  | [registr](https://smlouvy.gov.cz/smlouva/37865877) |
| 2025-04-25 | 2025-08-06 | 103 | 605 000 | MAKRO Cash & Carry ČR s.r.o. | Rámcová kupní smlouva č. 17/2025 Dodávka komodity - maso, uzeniny, ryby | Domov pro seniory |  | [registr](https://smlouvy.gov.cz/smlouva/37865789) |
| 2021-01-29 | 2021-07-22 | 174 | 506 420 | Zahradní a parková spol. s r.o. | Dodání letniček pro výsadby 2021 | město |  | [registr](https://smlouvy.gov.cz/smlouva/17261267) |
| 2022-09-22 | 2022-12-27 | 96 | 496 100 | TECHNICKÝ A DOPRAVNÍ SERVIS, s.r.o. | Posypová sůl | TDS |  | [registr](https://smlouvy.gov.cz/smlouva/22899845) |
| 2026-03-02 | 2026-06-25 | 115 | 407 820 | ZÁPADOČESKÝ SYMFONICKÝ ORCHESTR MARIÁNSKÉ LÁZNĚ o.p.s. | Smlouva o dodání uměleckého pořadu | ZSO | i) autorské dílo / umělecký výkon? | [registr](https://smlouvy.gov.cz/smlouva/38513422) |
| 2017-10-04 | 2018-02-07 | 126 | 378 004 | APRIS 3MP s.r.o. | Vypracování studie proveditelnosti a posouzení týkající se rekonstrukce stávajíc | město |  | [registr](https://smlouvy.gov.cz/smlouva/4625604) |
| 2024-01-01 | 2024-06-14 | 165 | 363 000 | PARKING CENTRUM s.r.o. | Smlouva o užívání parkovacích stání | DEVELOP CENTRUM |  | [registr](https://smlouvy.gov.cz/smlouva/29086468) |
| 2019-07-01 | 2019-10-23 | 114 | 291 000 | KIS Mariánské Lázně s.r.o. | Objednávka dotisku propagačního materiálu | město + Infocentrum |  | [registr](https://smlouvy.gov.cz/smlouva/10525442) |
| 2019-08-08 | 2019-11-13 | 97 | 290 400 | Jana Rádlová | Nájemní smlouva - Jana Rádlová | město | a) fyzická osoba mimo podnikání? | [registr](https://smlouvy.gov.cz/smlouva/10732416) |
| 2019-07-01 | 2019-11-08 | 130 | 290 400 | Šťastná Hana, JUDr., advokátka | poskytování právní pomoci | Domov pro seniory |  | [registr](https://smlouvy.gov.cz/smlouva/10677012) |
| 2022-05-20 | 2023-03-30 | 314 | 286 420 | RAJAN EKO s.r.o. | dopravní hřiště | Mateřská škola, Na Třešňovce 603 |  | [registr](https://smlouvy.gov.cz/smlouva/23937173) |
| 2020-01-04 | 2021-01-06 | 368 | 285 560 | Veolia Energie Mariánské Lázně, s.r.o. | RECE VEML/11692/CU/202101 | Mateřská škola Vora, Za Tratí 687 |  | [registr](https://smlouvy.gov.cz/smlouva/15098271) |
| 2020-01-04 | 2021-01-06 | 368 | 285 560 | Veolia Energie Mariánské Lázně, s.r.o. | RECE VEML/11692/OD/202101 | Mateřská škola Vora, Za Tratí 687 |  | [registr](https://smlouvy.gov.cz/smlouva/15098391) |
| 2019-06-28 | 2019-11-08 | 133 | 278 638 | Karel Benda Zemní a výkopové práce | Provedení asfaltové příjezdové komunikace k rodinému domu na p.p.č.14/2,k.ú. Úšo | město |  | [registr](https://smlouvy.gov.cz/smlouva/10683920) |
| 2026-07-01 | 2026-10-23 | 114 | 266 200 | Dopravní stavby a venkovní architektura s.r.o. | Objednávka Studie proveditelnosti | DEVELOP CENTRUM |  | [registr](https://smlouvy.gov.cz/smlouva/40060429) |
| 2019-06-20 | 2020-09-24 | 462 | 264 500 | Základní umělecká škola Fryderyka Chopina Mariánské Lázně, příspěvková organizace | Koupě letenek | ZUŠ |  | [registr](https://smlouvy.gov.cz/smlouva/13929992) |
| 2022-08-10 | 2022-11-11 | 93 | 244 323 | DŘEVOARTIKL, spol. s r.o. | dodání a montáž herních prvků na zahradu MŠ | Mateřská škola Úšovice, Skalníkova 518 |  | [registr](https://smlouvy.gov.cz/smlouva/22323601) |
| 2021-09-10 | 2023-01-13 | 490 | 235 950 | PORSENNA o.p.s. | Komplexní zajištění výběru dodavatele a žádosti o dotaci na obnovu části soustav | město |  | [registr](https://smlouvy.gov.cz/smlouva/23081177) |
| 2025-05-28 | 2025-09-28 | 123 | 229 900 | ZÁPADOČESKÝ SYMFONICKÝ ORCHESTR MARIÁNSKÉ LÁZNĚ o.p.s. | smlouva o uměleckém výkonu | ZSO | i) autorské dílo / umělecký výkon? | [registr](https://smlouvy.gov.cz/smlouva/34976945) |
| 2024-03-13 | 2024-07-09 | 118 | 227 353 | Jiří Smrčka  | Výměna podlahové krytiny | MDDM |  | [registr](https://smlouvy.gov.cz/smlouva/29417540) |
| 2024-06-17 | 2024-10-17 | 122 | 209 330 | Ing. Ivan Hložek | Objednávka - Přemístění okružní křižovatky v centru M.L. | město |  | [registr](https://smlouvy.gov.cz/smlouva/30593120) |
| 2025-08-26 | 2026-01-06 | 133 | 207 885 | MĚSTSKÁ DOPRAVA Mariánské Lázně s.r.o. | Oprava informačního systému nádraží - oprava led panelů a obnova řídící jednotky | město + Městská doprava |  | [registr](https://smlouvy.gov.cz/smlouva/36267889) |
| 2026-05-29 | 2026-09-01 | 95 | 202 780 | ZÁPADOČESKÝ SYMFONICKÝ ORCHESTR MARIÁNSKÉ LÁZNĚ o.p.s. | Smlouva o dodání uměleckého pořadu | ZSO | i) autorské dílo / umělecký výkon? | [registr](https://smlouvy.gov.cz/smlouva/39334327) |
| 2023-04-28 | 2023-10-09 | 164 | 200 000 | SPRÁVA MĚSTSKÝCH SPORTOVIŠŤ příspěvková organizace | Smlouva o užívání sportovního areálu | SMS |  | [registr](https://smlouvy.gov.cz/smlouva/32610592) |
| 2019-07-10 | 2019-11-04 | 117 | 191 134 | Bonita Group Service s.r.o. | Zahradní prvky | Mateřská škola Vora, Za Tratí 687 |  | [registr](https://smlouvy.gov.cz/smlouva/25149519) |
| 2025-03-20 | 2025-09-28 | 192 | 182 710 | ZÁPADOČESKÝ SYMFONICKÝ ORCHESTR MARIÁNSKÉ LÁZNĚ o.p.s. | smlouva o uměleckém výkonu | ZSO | i) autorské dílo / umělecký výkon? | [registr](https://smlouvy.gov.cz/smlouva/34976925) |
| 2025-01-13 | 2025-09-28 | 258 | 181 500 | ZÁPADOČESKÝ SYMFONICKÝ ORCHESTR MARIÁNSKÉ LÁZNĚ o.p.s. | smlouva o uměleckém výkonu | ZSO | i) autorské dílo / umělecký výkon? | [registr](https://smlouvy.gov.cz/smlouva/34976909) |
| 2025-09-04 | 2026-02-25 | 174 | 181 500 | BM asistent s.r.o. | Příkazní smlouva - administrace žádosti o dotaci | Městská doprava |  | [registr](https://smlouvy.gov.cz/smlouva/36927897) |
| 2017-09-18 | 2018-09-26 | 373 | 178 838 | Diakonická akademie s.r.o. | příprava a realizace akreditovaného kurzu Validace podle Naomi Feil I. a Validac | Domov pro seniory |  | [registr](https://smlouvy.gov.cz/smlouva/8067515) |
| 2025-07-01 | 2025-12-05 | 157 | 166 721 | Václav Špicl | Doprava dětí | ZUŠ |  | [registr](https://smlouvy.gov.cz/smlouva/35913697) |
| 2021-04-21 | 2021-09-27 | 159 | 162 590 | MUSIL gastro spol. s r.o. | nákup konvektomatu | Mateřská škola, Na Třešňovce 603 |  | [registr](https://smlouvy.gov.cz/smlouva/17869679) |
| 2022-07-07 | 2022-11-28 | 144 | 162 301 | Muzsa Festival Organising Office Ltd. | Kupní smlouva | ZUŠ | a) fyzická osoba mimo podnikání?; d) plnění převážně mimo ČR? | [registr](https://smlouvy.gov.cz/smlouva/22511521) |
| 2025-06-25 | 2025-12-05 | 163 | 154 162 | Muzsa Festival Organising Office Ltd. | Zájezd pro děti | ZUŠ | a) fyzická osoba mimo podnikání?; d) plnění převážně mimo ČR? | [registr](https://smlouvy.gov.cz/smlouva/35913809) |
| 2023-04-28 | 2023-10-09 | 164 | 150 000 | SPRÁVA MĚSTSKÝCH SPORTOVIŠŤ příspěvková organizace | Smlouva o užívání sportovního areálu | SMS |  | [registr](https://smlouvy.gov.cz/smlouva/26022331) |
| 2018-05-09 | 2020-06-04 | 757 | 141 121 | 4CITY s.r.o. | dodávka a montáž venkovního dětského fitness | Mateřská škola, Na Třešňovce 603 |  | [registr](https://smlouvy.gov.cz/smlouva/12874124) |
| 2021-06-23 | 2021-11-09 | 139 | 138 509 | TECHNICKÝ A DOPRAVNÍ SERVIS, s.r.o. | Demolice stavebních buněk a následné roztřídění a odstranění vzniklého odpadu na | město + TDS |  | [registr](https://smlouvy.gov.cz/smlouva/18315163) |
| 2021-06-23 | 2021-11-09 | 139 | 138 509 | TECHNICKÝ A DOPRAVNÍ SERVIS, s.r.o. | Demolice stavebních buněk a následné roztřídění a odstranění vzniklého odpadu na | město + TDS |  | [registr](https://smlouvy.gov.cz/smlouva/18315167) |
| 2017-07-20 | 2017-10-30 | 102 | 133 100 | Plzeňské městské dopravní podniky, a.s.  | Smlouva o nájmu dopravního prostředku | Městská doprava |  | [registr](https://smlouvy.gov.cz/smlouva/3589660) |
| 2022-05-30 | 2022-09-23 | 116 | 127 776 | Lázeňské lesy, spol. s r.o. | objednávka mobiliáře v rámci Participativního rozpočtu- Venkovní sezení do zóny  | město + Lázeňské lesy |  | [registr](https://smlouvy.gov.cz/smlouva/21764881) |
| 2025-04-24 | 2025-09-28 | 157 | 121 000 | ZÁPADOČESKÝ SYMFONICKÝ ORCHESTR MARIÁNSKÉ LÁZNĚ o.p.s. | smlouva o uměleckém výkonu | ZSO | i) autorské dílo / umělecký výkon? | [registr](https://smlouvy.gov.cz/smlouva/34976933) |
| 2019-07-08 | 2019-10-16 | 100 | 120 153 | Neogenia s.r.o. | Smlouva o poskytování služeb komunikační platformy mobilní rozhlas | město |  | [registr](https://smlouvy.gov.cz/smlouva/10445898) |
| 2019-04-05 | 2019-11-06 | 215 | 120 000 | Hotel Krakonoš, s.r.o. | Objednávka - Cyklus akcí na vrchu Krakonoš 2019 | město |  | [registr](https://smlouvy.gov.cz/smlouva/10653916) |
| 2026-06-23 | 2026-10-23 | 122 | 118 580 | Studio Prokon s.r.o. | Objednávka Zpracování zastavovací studie - Bydlení u Pily | DEVELOP CENTRUM |  | [registr](https://smlouvy.gov.cz/smlouva/40060489) |
| 2025-03-24 | 2025-09-22 | 182 | 114 950 | AQE advisors, a.s. | Zpracování žádosti o dotaci do výzvy: 73 výzva OŽP - „Revitalizace rybníka Velký | město |  | [registr](https://smlouvy.gov.cz/smlouva/34902333) |
| 2023-08-21 | 2023-12-13 | 114 | 105 875 | Milan Vojtěch | oprava dřevěných herních prvků DH u nemocnice | město |  | [registr](https://smlouvy.gov.cz/smlouva/26880203) |
| 2025-03-27 | 2025-07-16 | 111 | 102 359 | Technický a dopravní servis s.r.o. | Objednávka TDS - ZLS 2025 | město + TDS |  | [registr](https://smlouvy.gov.cz/smlouva/34111877) |
| 2025-06-20 | 2025-12-05 | 168 | 101 931 | Muzsa Festival Organising Office Ltd. | Ubytování žáků na zájezdu | ZUŠ | a) fyzická osoba mimo podnikání?; d) plnění převážně mimo ČR? | [registr](https://smlouvy.gov.cz/smlouva/35911001) |
| 2023-04-01 | 2023-07-28 | 118 | 100 000 | SPRÁVA MĚSTSKÝCH SPORTOVIŠŤ příspěvková organizace | Smlouva o zajištění služeb - internetové služby | SMS |  | [registr](https://smlouvy.gov.cz/smlouva/25281535) |
| 2023-09-01 | 2024-01-26 | 147 | 97 192 | Vlastimil Šplíchal | Doprava dětí do Itálie | ZUŠ |  | [registr](https://smlouvy.gov.cz/smlouva/27409351) |
| 2023-12-22 | 2025-12-22 | 731 | 95 460 | BLAHOUT ROSTISLAV nar. 1979 | Smlouva o nájmu bytu | město | a) fyzická osoba mimo podnikání? | [registr](https://smlouvy.gov.cz/smlouva/36180725) |
| 2024-08-09 | 2025-01-17 | 161 | 95 000 | Filip Kopecký | projektové řízení, rešerše a průzkum, web a grafický desing v rámci "interaktivn | město |  | [registr](https://smlouvy.gov.cz/smlouva/31794496) |
| 2022-11-22 | 2023-11-29 | 372 | 92 830 | L I N E T spol. s r.o. | Matrace PrimaCare, doprava a instalace | Domov pro seniory |  | [registr](https://smlouvy.gov.cz/smlouva/26659823) |
| 2025-06-09 | 2025-12-05 | 179 | 90 708 | Thomann GmbH | Nákup hudebních nástrojů | ZUŠ | a) fyzická osoba mimo podnikání?; d) plnění převážně mimo ČR? | [registr](https://smlouvy.gov.cz/smlouva/35911769) |
| 2019-02-28 | 2019-06-05 | 97 | 89 661 | WSA doprava a parkování s.r.o. | obj. změna tarifů WSA | město |  | [registr](https://smlouvy.gov.cz/smlouva/9256535) |
| 2025-06-07 | 2025-09-28 | 113 | 86 625 | ZÁPADOČESKÝ SYMFONICKÝ ORCHESTR MARIÁNSKÉ LÁZNĚ o.p.s. | smlouva o uměleckém výkonu | ZSO | i) autorské dílo / umělecký výkon? | [registr](https://smlouvy.gov.cz/smlouva/34976937) |
| 2024-02-24 | 2024-06-03 | 100 | 85 281 | Avast Software s.r.o. | AVG | ZUŠ |  | [registr](https://smlouvy.gov.cz/smlouva/28929792) |
| 2025-04-11 | 2025-12-05 | 238 | 85 228 | Muzsa Festival Organising Office Ltd. | Zájezd DOM | ZUŠ | a) fyzická osoba mimo podnikání?; d) plnění převážně mimo ČR? | [registr](https://smlouvy.gov.cz/smlouva/35911857) |
| 2018-08-21 | 2020-06-04 | 653 | 84 191 | MUSIL gastro spol. s r.o. | dodávka sporáku s troubou | Mateřská škola, Na Třešňovce 603 |  | [registr](https://smlouvy.gov.cz/smlouva/12879460) |
| 2024-08-01 | 2024-11-18 | 109 | 83 571 | Základní škola JIH, Mariánské Lázně, Komenského 459, příspěvková organizace | Objednávka - oprava rozvodů vody ve třídě u věže | Základní škola JIH, Komenského 459 |  | [registr](https://smlouvy.gov.cz/smlouva/31038632) |
| 2025-05-20 | 2025-09-09 | 112 | 81 600 | Základní škola JIH, Mariánské Lázně, Komenského 459, příspěvková organizace | Objednávka - letová ukázka dravců | Základní škola JIH, Komenského 459 |  | [registr](https://smlouvy.gov.cz/smlouva/34732237) |
| 2019-03-26 | 2019-08-14 | 141 | 80 000 | KIS Mariánské Lázně s.r.o. | zajištění akce Kapsa plná pohádek | město + Infocentrum |  | [registr](https://smlouvy.gov.cz/smlouva/9879483) |
| 2022-09-15 | 2023-09-15 | 365 | 79 981 | Základní škola Vítězství Mariánské Lázně, příspěvková organizace | Dohoda o narovnání k objednávce ze dne 05.10.2022 | Základní škola Vítězství |  | [registr](https://smlouvy.gov.cz/smlouva/25770727) |
| 2017-07-26 | 2017-12-15 | 142 | 79 848 | Rosenkranc – Sváta | Objednávka opravy chodníku v areálu ZŠ Vítězství Mariánské Lázně | Základní škola Vítězství |  | [registr](https://smlouvy.gov.cz/smlouva/4110508) |
| 2020-10-27 | 2021-09-27 | 335 | 78 000 | E.ON Česká republika, s. r. o. | dodávka el.energie | Mateřská škola, Na Třešňovce 603 |  | [registr](https://smlouvy.gov.cz/smlouva/17869299) |
| 2022-05-30 | 2024-01-19 | 599 | 73 447 | 07542984 | Objednávka odtahu vozidel | město |  | [registr](https://smlouvy.gov.cz/smlouva/27333575) |
| 2021-06-01 | 2021-12-10 | 192 | 72 900 | Avast Software s.r.o. | Prodloužení licence AVG | ZUŠ |  | [registr](https://smlouvy.gov.cz/smlouva/18691347) |
| 2024-03-17 | 2025-06-26 | 466 | 72 726 | Mateřská škola Vora, Mariánské Lázně, Za Tratí 687, příspěvková organizace | Dohoda o narovnání k objednávce ze dne 17. 03. 2024 | Mateřská škola Vora, Za Tratí 687 |  | [registr](https://smlouvy.gov.cz/smlouva/33849157) |
| 2022-05-30 | 2022-09-14 | 107 | 72 600 | FT Technologies, a.s. | Dodatek č. 1 Smlouvy č.: 20190025 | město |  | [registr](https://smlouvy.gov.cz/smlouva/21658381) |
| 2022-05-30 | 2022-09-14 | 107 | 72 600 | FT Technologies, a.s. | Dodatek č. 1 ke Smlouvě o poskytování údržby a podpory č.: 20190026 | město |  | [registr](https://smlouvy.gov.cz/smlouva/21658361) |
| 2025-07-31 | 2025-12-15 | 137 | 72 600 | DEVELOP CENTRUM Mariánské Lázně s. r. o. | Příkazní smlouva - účetní poradenství | DEVELOP CENTRUM |  | [registr](https://smlouvy.gov.cz/smlouva/36042753) |
| 2020-06-24 | 2021-06-18 | 359 | 72 000 | Thomann GmbH | Nákup hudebního nástroje | ZUŠ | a) fyzická osoba mimo podnikání?; d) plnění převážně mimo ČR? | [registr](https://smlouvy.gov.cz/smlouva/16952587) |
| 2021-08-22 | 2022-03-25 | 215 | 70 407 | Mateřská škola Vora | Oprava-umývárna Medvíďata | Mateřská škola Vora, Za Tratí 687 |  | [registr](https://smlouvy.gov.cz/smlouva/19799019) |
| 2023-11-27 | 2024-04-02 | 127 | 70 000 | SPRÁVA MĚSTSKÝCH SPORTOVIŠŤ příspěvková organizace | Pronájem nebytových prostor | SMS |  | [registr](https://smlouvy.gov.cz/smlouva/28179915) |
| 2023-11-27 | 2024-04-02 | 127 | 70 000 | SPRÁVA MĚSTSKÝCH SPORTOVIŠŤ příspěvková organizace | Pronájem nebytových prostor | SMS |  | [registr](https://smlouvy.gov.cz/smlouva/28180059) |
| 2025-12-15 | 2026-09-09 | 268 | 69 916 | Mateřská škola Vora, Mariánské Lázně, Za Tratí 687, příspěvková organizace | Koberec na třídě, podlaha ŠJ | Mateřská škola Vora, Za Tratí 687 |  | [registr](https://smlouvy.gov.cz/smlouva/39461065) |
| 2024-09-10 | 2025-01-17 | 129 | 68 936 | ReklamniPlachty.cz s.r.o. | Perforovaná plachta MESH (tisk, svar oka) | město |  | [registr](https://smlouvy.gov.cz/smlouva/31794492) |
| 2020-06-05 | 2020-09-17 | 104 | 68 728 | KOVODŘEVO.CZ, s.r.o. | zhotovení a montáž nájezdu pro popelnice, úprava schodiště pro chodítka, zřízení | Domov pro seniory |  | [registr](https://smlouvy.gov.cz/smlouva/13815708) |
| 2026-01-26 | 2026-05-05 | 99 | 68 559 | Generali Česká pojišťovna a.s. | Sdružené pojištění vozidla | SMS |  | [registr](https://smlouvy.gov.cz/smlouva/37843197) |
| 2024-11-22 | 2026-06-12 | 567 | 67 520 | Institut lázeňství a balneologie, v. v. i. | Objednávka č. 35/2024 - pronájem prostor | Infocentrum |  | [registr](https://smlouvy.gov.cz/smlouva/38350627) |
| 2020-01-14 | 2020-06-04 | 142 | 64 983 | MUSIL gastro spol. s r.o. | nákup myčky | Mateřská škola, Hlavní 440 |  | [registr](https://smlouvy.gov.cz/smlouva/17842743) |
| 2018-01-01 | 2018-07-02 | 182 | 62 000 | SPRÁVA MĚSTSKÝCH SPORTOVIŠŤ příspěvková organizace | Nájemní smlouva 2018 sportovní haly | SMS |  | [registr](https://smlouvy.gov.cz/smlouva/6050331) |
| 2019-04-25 | 2019-11-08 | 197 | 60 984 | APOSTAV spol. s r. o. | obstarání záležitostí na úseku požární ochrany a bezpečonosti práce | Domov pro seniory |  | [registr](https://smlouvy.gov.cz/smlouva/10677120) |
| 2024-06-12 | 2025-01-17 | 219 | 56 627 | Christopher Pound MSC BSc Hons RIBA MRTPI IHBC | Prezentace" Therapeutic Spa Landscape" | město | a) fyzická osoba mimo podnikání? | [registr](https://smlouvy.gov.cz/smlouva/31801716) |

Smlouvy bez uvedené hodnoty uveřejněné po 3 měsících (21) a smlouvy uveřejněné 31 až 90 dnů po uzavření (355) jsou v `data/penize/lhuty_prehled.json`.


## 7. Jak žádost napsat a co čekat

Lhůty podle § 14 odst. 5 písm. d) InfZ: úřad má **15 dnů** od doručení; ze závažných důvodů může lhůtu prodloužit o 10 dnů, musí to ale včas oznámit (§ 14 odst. 6). Když nepřijde nic, den po uplynutí lhůty lze podat stížnost na nečinnost (§ 16a), nejpozději do 30 dnů. Odmítnutí musí mít formu rozhodnutí (§ 15), proti němuž je odvolání ke Krajskému úřadu Karlovarského kraje (§ 16). Za mimořádně rozsáhlé vyhledání může úřad chtít úhradu (§ 17), musí ji ale předem oznámit s výpočtem.

Od 1. 1. 2023 může úřad odmítnout žádost pro **zneužití práva** (§ 11a), typicky nepřiměřeně zatěžující. Proto je lepší posílat **několik konkrétních žádostí po jedné smlouvě** než jednu žádost na celý registr — a u každé jmenovat číslo smlouvy, data a částky, které už jsou veřejné.

Co lze chtít a úřad to nesmí odmítnout jako obchodní tajemství nebo osobní údaj: **faktury a doklady o úhradách** (rozsah a příjemce veřejných prostředků, § 9 odst. 2), **jména úředníků**, kteří smlouvu podepsali, schválili nebo měli uveřejnit (§ 8a odst. 2), vnitřní předpisy úřadu, zápisy z kontrol. Co žádat nelze: názor úřadu, zda je smlouva platná (§ 2 odst. 4 — úřad poskytuje informace, ne právní stanoviska). Ptát se je proto třeba na **dokumenty a čísla**, z nichž si závěr udělá čtenář.

Město odpovědi na žádosti zveřejňuje na webu a portál je sbírá (sekce **Žádosti o informace**, `data/informace106/`). Odpověď na kteroukoli z těchto žádostí se tam objeví a bude dohledatelná.

### Vzor žádosti k jedné smlouvě

```text
Město Mariánské Lázně, Ruská 155/3, 353 01 Mariánské Lázně
(datová schránka bprbqms)

Žádost o poskytnutí informací podle zákona č. 106/1999 Sb.

Věc: smlouva {{číslo smlouvy / předmět}} s {{protistrana, IČO}}, uzavřená {{datum uzavření}},
v registru smluv uveřejněná {{datum prvního uveřejnění}} (https://smlouvy.gov.cz/smlouva/{{id}})

Žádám o poskytnutí těchto informací:

1. Seznam všech faktur a jiných dokladů, na jejichž základě město podle této smlouvy plnilo
   nebo přijalo plnění, s datem vystavení, datem uskutečnění plnění, částkou a datem úhrady,
   a to za období od {{datum uzavření}} do dneška; postačí tabulka (CSV/XLSX).
2. Kopie dokladů podle bodu 1 za období od {{datum uzavření}} do {{datum uveřejnění}}, tedy
   za dobu před uveřejněním smlouvy v registru smluv.
3. Informaci, zda město k této smlouvě uzavřelo dohodu o narovnání, dohodu o vypořádání
   bezdůvodného obohacení nebo novou smlouvu v souvislosti s § 6 a § 7 zákona č. 340/2015 Sb.;
   pokud ano, jejich kopie.
4. Informaci, který útvar a která osoba (funkce a jméno) byla podle vnitřních předpisů města
   odpovědná za uveřejnění této smlouvy v registru smluv, a kopii tohoto vnitřního předpisu
   ve znění platném k datu uzavření smlouvy.
5. Informaci, zda město v souvislosti s uveřejněním této smlouvy po lhůtě přijalo opatření
   (kontrolní zjištění, náhrada škody, pracovněprávní postih, změna vnitřních předpisů);
   pokud ano, kopie příslušných dokumentů s anonymizací pouze v rozsahu § 8a zákona.

Informace prosím poskytněte elektronicky do datové schránky / na e-mail {{adresa}}.
Pokud některou informaci neposkytnete, žádám o rozhodnutí o odmítnutí v tomto rozsahu (§ 15).
Pokud hodláte požadovat úhradu nákladů, žádám o její předchozí oznámení s výpočtem (§ 17 odst. 3).

{{jméno, datum narození, adresa trvalého pobytu, adresa pro doručování}}
```

### Vzor systémové žádosti (jedna pro celý úřad)

```text
Věc: uveřejňování smluv města v registru smluv

1. Kopie vnitřního předpisu (směrnice, příkazu tajemníka) upravujícího uveřejňování smluv
   a objednávek v registru smluv, ve všech zněních od 1. 7. 2016.
2. Informaci, zda město eviduje smlouvy, které byly uveřejněny po více než 3 měsících od
   uzavření; pokud ano, jejich seznam (číslo smlouvy, protistrana, datum uzavření, datum
   uveřejnění, hodnota).
3. Seznam dohod o narovnání, dohod o vypořádání bezdůvodného obohacení a nově uzavřených
   smluv, které město od 1. 7. 2017 uzavřelo z důvodu neuveřejnění nebo pozdního uveřejnění
   smlouvy v registru smluv.
4. Část zpráv o výsledku přezkoumání hospodaření města za roky 2021–2025 týkající se
   registru smluv (textová podoba, ne sken), a přijatá opatření k nápravě.
5. Zápisy z jednání kontrolního a finančního výboru, které se registru smluv týkaly.
```

---

## Zdroje

- Zákon č. 340/2015 Sb., o registru smluv — [zakonyprolidi.cz](https://www.zakonyprolidi.cz/cs/2015-340)
- Zákon č. 106/1999 Sb., o svobodném přístupu k informacím — [zakonyprolidi.cz](https://www.zakonyprolidi.cz/cs/1999-106)
- Trestní zákoník, § 138, § 220, § 221 — [zakonyprolidi.cz](https://www.zakonyprolidi.cz/cs/2009-40)
- Nejvyšší soud, 23 Cdo 88/2025 (24. 6. 2026) — [epravo.cz](https://www.epravo.cz/top/soudni-rozhodnuti/bezduvodne-obohaceni-121644.html)
- Bulušek, Skalská: Důsledky poskytnutí plnění v návaznosti na smlouvu neuveřejněnou v registru smluv — [epravo.cz, 2018](https://www.epravo.cz/top/clanky/dusledky-poskytnuti-plneni-v-navaznosti-na-smlouvu-neuverejnenou-v-registru-smluv-107993.html)
- Bouda: Kdo může iniciovat zrušení smlouvy nezveřejněné v souladu se zákonem o registru smluv — [pravniprostor.cz, 2016](https://www.pravniprostor.cz/clanky/ostatni-pravo/kdo-muze-iniciovat-zruseni-smlouvy-nezverejnene-v-souladu-se-zakonem-o-registru-smluv)
- Kvapil, Hřebačka: Registr smluv — [Deník veřejné správy, 2018](https://denik.obce.cz/clanek.asp?id=6755507)
- Ministerstvo financí: Souhrnná zpráva o výsledcích přezkoumání hospodaření územních celků za rok 2024 — [mf.gov.cz](https://mf.gov.cz/assets/attachments/2025-11-11_Souhrnna-zprava-o-vysledcich-prezkoumani-hospodareni-UC-za-rok-2024.pdf)
- Ministerstvo vnitra: Metodický návod k aplikaci zákona o registru smluv, v. 1.11 — [testrs.gov.cz](https://testrs.gov.cz/smlouva/soubor/232294/Metodicky_navod_k_aplikaci_ZRS_-_v1-11.pdf)
- Hlídač státu — detaily smluv a kontrola „Smlouva nebyla zveřejněna do 3 měsíců od podpisu" (issue 21) — [hlidacstatu.cz](https://www.hlidacstatu.cz)
- Registr smluv — stránky záznamů — [smlouvy.gov.cz](https://smlouvy.gov.cz)
