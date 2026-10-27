# DEVELOP CENTRUM Mariánské Lázně s.r.o.: městská firma, její smlouvy a na co se ptát

Profil jedné firmy z městského holdingu: **DEVELOP CENTRUM Mariánské Lázně s.r.o.** (IČO 61776068), do června 2025 **PARKING CENTRUM**. Město ji vlastní na 100 %, od roku 2024 jí svěřuje správu parkovacího systému, od roku 2026 rozvojové projekty (Třešňovka, Nové Centrum, U Pily, Hamrníky) a od srpna 2026 i lázeňské pavilony. Za tu dobu se mezi městem a firmou několikrát přepsal způsob, jak tečou peníze: z provize 90 % parkovného přes paušál 3 mil. Kč ročně a „zálohu na zisk" až po bezúplatnou výpůjčku pozemků a budov.

**Jak to číst.** Stejně jako v [`docs/namety-106.md`](namety-106.md): u každého tématu je odděleno, co je **doložený fakt** (text smlouvy v registru, usnesení rady, listina ve sbírce listin, řádek rozpočtu) a co je **otázka**, tedy to, co z veřejných dat zjistit nejde a je to důvod se zeptat. Nic z toho není výrok, že někdo pochybil. Je to popis mechanismu a otázky, které z něj plynou.

**Odkud jsou data.** Obchodní rejstřík, sbírka listin, ARES a registr plátců DPH přes konektor **Sagasu** (nástroje `verejny_rejstrik`, `obchodni_rejstrik`, `sbirka_listin`, `listina_text`, `verejny_rejstrik_osoba`, `dph_status`); texty smluv z Hlídače státu a registru smluv; usnesení rady a zastupitelstva ze sklizně v `data/usneseni/`; rozpočet města z Monitoru státní pokladny (`data/rozpocet/fin212m/`); data uveřejnění z `data/penize/lhuty_zverejneni.json`. Stav k 27. 10. 2026.

---

## 1. Kdo to je

| | |
|---|---|
| název | DEVELOP CENTRUM Mariánské Lázně s.r.o. (do 6/2025 PARKING CENTRUM s.r.o., do 4/2023 PARKING CENTRUM a.s.) |
| IČO / spisová značka | 61776068, C 43956 Krajský soud v Plzni (dříve B 437) |
| vznik | 14. 10. 1994 |
| sídlo | Pramenská 653/2, Mariánské Lázně (parkovací dům) |
| společník | město Mariánské Lázně, 100 % |
| základní kapitál | 43 000 000 Kč, splacen |
| jednatelé | Karel Henych (od 2023), RNDr. Pavel Poc (od 13. 5. 2025); každý jedná samostatně |
| dozorčí rada | JUDr. Miloslav Chadim a Zdeněk Král (od 1. 4. 2025), Mgr. Ladislav Špelina (od 2025) |
| DPH | plátce, není nespolehlivý; účty 218723922/0300, 115-2423040257/0100 |
| datová schránka | aaffkjx |

Zdroj: Sagasu `verejny_rejstrik` / `obchodni_rejstrik` / `dph_status`; jmenování a odvolání v [RM 1. 4. 2025, 83/39](https://usneseni.muml.cz/rada/usneseni/3347171) a [RM 13. 5. 2025, 88/3](https://usneseni.muml.cz/rada/usneseni/3367347).

**Jak se z parkovací firmy stala rozvojová.** Historie v usneseních rady (283 usnesení zmiňujících firmu od roku 2012):

- 2012–2013: akcie PARKING CENTRUM a.s. držela městská KIS Mariánské Lázně s.r.o. (30 054 ks), rada řešila znalecký posudek a prodej akcií ([RM 13. 3. 2012, 58/14](https://usneseni.muml.cz/rada/usneseni/716417)).
- 2020: město odkoupilo zbylých 400 akcií od ClickPark s.r.o. za 344 000 Kč a má 100 %.
- 2020–2023: město prodalo firmě pozemky pod parkovacím domem; kupní smlouva v registru je z 23. 8. 2023 za **9 764 844 Kč s DPH** ([registr 25530603](https://smlouvy.gov.cz/smlouva/25530603)), splácená v ročních splátkách.
- 2. 2. 2023: rada schválila změnu právní formy na s.r.o. ([RM 11/2](https://usneseni.muml.cz/rada/usneseni/2965240)), projekt změny 16. 5. 2023 ([RM 23/20](https://usneseni.muml.cz/rada/usneseni/3021679)), zapsáno 24. 4. 2023; náklady schválené zastupitelstvem 180 tis. Kč.
- 13. 6. 2025: notářský zápis NZ 156/2025, nová zakladatelská listina: název DEVELOP CENTRUM, předmět podnikání rozšířen o projektovou činnost, pronájem, poradenství (Sagasu `sbirka_listin` → `pdf_obrazek_strany`, 13 stran skenu).
- 12. 6. 2026: rada jako valná hromada **uložila jednatelům připravit projekt snížení základního kapitálu** do 31. 12. 2026 ([RM 119/2](https://usneseni.muml.cz/rada/usneseni/3509919300)).

## 2. Lidé

**Pavel Poc** (nar. 1964) byl v roce 2023 předsedou dozorčí rady, 19. 12. 2023 odvolán, 13. 5. 2025 jmenován jednatelem. Podle veřejného rejstříku (Sagasu `verejny_rejstrik_osoba`) je současně statutárním orgánem nebo členem orgánů ve skupině SUAS (Sokolovská uhelná, SUAS GROUP a.s., SUAS Management, SUAS Ecology), v CHEVAK Cheb a.s., Industrial Park Sokolov a MAS 21, a je **společníkem a jednatelem Zahradní a parková spol. s r.o.** (IČO 25205978).

Zahradní a parková je významný dodavatel města: podle sklizně Hlídače státu **85 smluv za 44,5 mil. Kč** (2023: 15,5 mil., 2025: 7,4 mil.). Jedna z nich, „letničky 2021" za 506 420 Kč, je v seznamu smluv uveřejněných po více než třech měsících v [`namety-106.md`](namety-106.md). SUAS Commodities, dodavatel elektřiny pro Správu městského sportu (5 mil. Kč, uveřejněno po 198 dnech), patří do téže skupiny SUAS.

**Doložený fakt:** jednatel městské firmy je zároveň spolumajitel firmy, která městu ročně fakturuje miliony. **Otázka:** zda a jak byl střet zájmů oznámen podle § 54 a § 55 zákona o obchodních korporacích (jednatel oznamuje valné hromadě, tedy radě), zda rada o oznámení rozhodla a zda DEVELOP CENTRUM při administraci zakázek pro město (Třešňovka, U Pily, stojany, automaty) narazilo na dodavatele propojené s jednatelem. Z dat to poznat nejde.

**Miloslav Chadim** (ANO) a **Zdeněk Král** (ODS) jsou členové rady města a od 1. 4. 2025 členové dozorčí rady; Zdeněk Král předkládal radě změnu právní formy v roce 2023. V `data/propojeni/osoby_firmy.json` je firma u obou vedena jako vazba. Starosta Martin Hurajčík byl z dozorčí rady odvolán k 31. 5. 2025.

## 3. Hospodaření (z účetních závěrek ve sbírce listin)

Čísla v tis. Kč, z listin ve sbírce listin or.justice.cz přečtených přes Sagasu `listina_text` (XML části UZ-*.xml, rok 2025 z PDF).

| | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| tržby | 4 522 | 7 145 | 9 762 | 12 593 | *v závěrce* |
| osobní náklady | · | 1 578 | 2 067 | 5 663 | · |
| z toho mzdy | · | · | 1 534 | 4 152 | · |
| výsledek po zdanění | 512 | 2 193 | 3 101 | 412 | 2 273 |
| vlastní kapitál | · | 46 845 | · | 50 357 | 52 612 |
| aktiva celkem | · | · | · | · | 63 057 |
| peníze | · | · | · | · | 8 284 |
| průměrný počet zaměstnanců | · | 1,65 | · | · | · |

Rozvaha 2025: pozemky 8 864, stavby 38 371, odložený daňový závazek 7 605. Zisk 2025 (2 272 993,29 Kč) rada převedla na nerozdělený zisk ([RM 12. 6. 2026, 119/2](https://usneseni.muml.cz/rada/usneseni/3509919300)); nerozdělený zisk minulých let byl k 5/2025 5 362 tis. Kč ([RM 13. 5. 2025, 88/2](https://usneseni.muml.cz/rada/usneseni/3367310)).

**Co z toho je vidět:** tržby za tři roky téměř trojnásobné (příkazní odměna 90 % parkovného od 8/2024), osobní náklady 2024 více než 2,7× proti 2023, zisk 2024 přitom nejnižší za sledované období. Firma nikdy nevyplatila podíl na zisku společníkovi, dokud rada v lednu 2026 nerozhodla o záloze (viz § 5.3). **Otázka:** počet zaměstnanců a mzdová struktura 2024–2026, odměny jednatelů a členů dozorčí rady (schvaluje rada jako valná hromada; v usneseních je u DEVELOP CENTRA jen „schvaluje vyplacení odměny za provedenou činnost", bez částky).

## 4. Co ve sbírce listin chybí

Sagasu `sbirka_listin` (IČO 61776068) k 27. 10. 2026:

| listina | roky založené | roky chybějící |
|---|---|---|
| účetní závěrka | 2012–2025 (přes finanční úřad) | — |
| zpráva o vztazích mezi propojenými osobami (§ 82 ZOK) | 2013–2015, 2017–2022 | **2016, 2023, 2024, 2025** |
| výroční zpráva | žádná | 2023–2025 (pokud podléhá auditu) |
| zpráva auditora | žádná | 2025 |

Přitom rada jako valná hromada **schválila** zprávu o vztazích za rok 2023 ([RM 14. 5. 2024, 53/5](https://usneseni.muml.cz/rada/usneseni/3195714)), za rok 2024 ([RM 13. 5. 2025, 88/2](https://usneseni.muml.cz/rada/usneseni/3367310)) a vzala na vědomí zprávu o vztazích **i zprávu nezávislého auditora** za rok 2025 ([RM 12. 6. 2026, 119/2](https://usneseni.muml.cz/rada/usneseni/3509919300)). Rada pokaždé uložila jednateli listiny „elektronicky zveřejnit u obchodního soudu v Plzni, v termínu stanoveném zákonem". Ve sbírce listin nejsou.

**Doložený fakt:** zprávy existují (rada je schválila), ale nejsou založené. Zpráva o vztazích se zakládá do sbírky listin spolu s účetní závěrkou (§ 84 odst. 2 ZOK, § 21a zákona o účetnictví), u auditované společnosti i zpráva auditora a výroční zpráva. Nezaložení je přestupek podle zákona o účetnictví a rejstříkový soud může podle § 104 a násl. zákona o veřejných rejstřících uložit pořádkovou pokutu až 100 000 Kč. **Otázka:** proč nejsou založené, a hlavně co v nich je. Zpráva o vztazích za rok 2022 (poslední založená, ještě za PARKING CENTRUM a.s.) uvádí, že město poskytovalo pozemky pod parkovacím domem bezúplatně, firma městu bezúplatně kanceláře pro městskou policii, a firma si stěžovala na **újmu ovládané osoby** tím, že město konkuruje bezplatným parkováním. Zprávy 2023–2025 by měly popisovat příkazní smlouvy, 90 % provizi, nájem pro městskou policii a zálohu na zisk, tedy přesně vztahy, o které tu jde. Zprávu o vztazích lze žádat po samotné firmě (viz § 8).

## 5. Smlouvy s městem: jak se peníze přepisovaly

Firma má v registru smluv 51 záznamů (2016–2026), z toho asi dvě desítky s městem. Celý seznam s daty uveřejnění je v § 6. Tady je mechanismus v časové ose.

### 5.1 Příkazní smlouva o správě parkovacího systému (31. 7. 2024): 90 % parkovného

[Registr 29673568](https://smlouvy.gov.cz/smlouva/29673568), schváleno [RM 23. 7. 2024, 60/14](https://usneseni.muml.cz/rada/usneseni/3228240) (RM/515/24). Účinnost 1. 8. 2024, doba neurčitá. Firma pro město spravuje 34 parkovacích automatů a parkovací systém; odměna je **90 % všech příjmů z parkovacího systému**, a smlouva výslovně říká, že odměna slouží i na „další činnosti a rozvoj společnosti". Hodnota v registru 7 840 800 Kč s DPH. Zastupitelstvo 17. 9. 2024 kvůli ní zvýšilo výdaje rozpočtu o 2 000 tis. Kč.

**Doložený fakt:** parkovné zůstává příjmem města (automaty byly do 5/2025 městské, pozemky městské), ale 90 % z něj město platí firmě jako odměnu za správu. **Otázka:** jak byla výše odměny kalkulována (kalkulace nákladů správy vs. 90 % výnosu), zda před uzavřením byla posouzena jako veřejná zakázka zadaná vertikální spoluprací (§ 11 zákona o zadávání veřejných zakázek vyžaduje mj. více než 80 % činnosti firmy pro zadavatele) a zda jde o podporu podle pravidel veřejné podpory, když smlouva odměnu výslovně určuje i na „rozvoj společnosti".

### 5.2 Co to udělalo s rozpočtem města

Monitor státní pokladny, FIN 2-12 M, paragraf 2219 (ostatní záležitosti pozemních komunikací), město Mariánské Lázně, skutečnost v mil. Kč:

| rok | příjmy pol. 2111 (parkovné) | výdaje pol. 5169 (nákup služeb) | poznámka |
|---|---|---|---|
| 2019 | 6,93 | 0,43 | |
| 2020 | 5,09 | 0,30 | covid |
| 2021 | 5,66 | 0,25 | |
| 2022 | 7,35 | 0,44 | |
| 2023 | 8,65 | 0,48 | |
| 2024 | 8,36 | 1,98 | provize od 8/2024 |
| 2025 | 9,02 | 7,66 | provize celý rok; + 0,38 mil. příjem z prodeje automatů (pol. 3113) |
| 2026 (k 30. 6.) | 0,68 (schváleno 0,50) | 1,95 (schváleno 3,09) | parkovné už není příjmem města |

Zdroj: `data/rozpocet/fin212m/*-12.json`, `2026-06.json`. Výdaj 5169 v roce 2025 (7,66 mil.) odpovídá 90 % z parkovného; v roce 2026 odpovídá paušálu 250 000 Kč měsíčně (§ 5.3) plus další služby. Schválený rozpočet 2026 počítá s parkovným jen 0,5 mil. Kč: od 1. 1. 2026 vybírá parkovné firma do své pokladny.

**Doložený fakt:** příjem města z parkování klesl z 8–9 mil. Kč ročně na zlomek; k městu se z něj má vracet jen „záloha na zisk" (§ 5.3) a to, co firma odvede ze zisku. **Otázka:** jaká je ekonomika celé operace z pohledu města za rok 2025 a 2026 (parkovné vybrané firmou, náklady správy, odvedená záloha, investice firmy do automatů) a zda ji někdo radě předložil.

### 5.3 Dohoda o narovnání (23. 1. 2026): paušál 3 mil. ročně a záloha na zisk ve stejné výši

[Registr 36736349](https://smlouvy.gov.cz/smlouva/36736349), hodnota 3 630 000 Kč s DPH; schváleno [RM 20. 1. 2026, 109/25](https://usneseni.muml.cz/rada/usneseni/3780543056) (RM/910/26). Dohoda ukončila příkazní smlouvu o parkování k 1. 1. 2026 a nahradila ji **Příkazní smlouvou ROZVOJ**: 3 000 000 Kč bez DPH ročně (250 000 Kč měsíčně) za podporu rozvojových projektů, s **výslovně sjednanou zpětnou účinností k 1. 1. 2026** (podpis 23. 1., uveřejnění 10. 2. 2026).

Totéž usnesení o deset řádků níže: rada jako jediný společník rozhodla o **záloze na podíl na zisku za rok 2026 ve výši 3 000 000 Kč, ve dvanácti měsíčních splátkách po 250 000 Kč**, „bez srážky daně". 30. 3. 2026 splátky změněny na čtvrtletní ([RM 114/33](https://usneseni.muml.cz/rada/usneseni/3708452305)). V rozpočtu města se první záloha objevila v červnu 2026 (paragraf 3639, položka 2142: 750 000 Kč) a 15. 9. 2026 rada 750 000 Kč „záloha na zisk – DEVELOP CENTRUM" rozpočtovým opatřením použila na mimořádnou dotaci Západočeskému symfonickému orchestru ([RM 130/2](https://usneseni.muml.cz/rada/usneseni/4017706572)).

**Doložený fakt:** v lednu 2026 rada jedním usnesením schválila paušál 250 000 Kč měsíčně pro firmu a zálohu na zisk 250 000 Kč měsíčně od firmy, tedy dva stejně velké toky opačným směrem. Schválený rozvrh se pak měnil: v březnu na čtvrtletní splátky, v srpnu na dvě splátky po 750 000 Kč (§ 5.4). Skutečné platby z usnesení vyčíst nejde; v rozpočtu města je k 30. 6. 2026 přijatá záloha 750 000 Kč a vydáno na službách § 2219 1,95 mil. Kč. Firma mezitím vybírá parkovné (v roce 2025 přes 9 mil. Kč) do své pokladny. **Otázky:**

- Záloha na zisk vyžaduje mezitímní účetní závěrku prokazující, že firma má na výplatu dost prostředků (§ 40 odst. 2 ZOK). Byla sestavena k lednu 2026? Rozhodnutí z 20. 1. 2026 ji nezmiňuje.
- Zpětná účinnost k 1. 1. 2026 odporuje § 6 odst. 1 zákona o registru smluv (účinnost nejdříve dnem uveřejnění, tedy 10. 2. 2026). Plnění za leden a část února (asi 330 tis. Kč bez DPH) bylo poskytnuto před účinností. Jak bylo vypořádáno?
- Co konkrétně firma za 250 000 Kč měsíčně dodala? Rada 12. 5. a 21. 7. 2026 „schvaluje vyplacení odměny za provedenou činnost" ([RM 117/5](https://usneseni.muml.cz/rada/usneseni/1510186414), [RM 122/8](https://usneseni.muml.cz/rada/usneseni/1807498686)) bez výkazu činnosti v usnesení.
- Zadání příkazní smlouvy za 3 mil. Kč ročně bez soutěže: proběhlo posouzení podle § 11 ZZVZ (vertikální spolupráce)? Když většinu tržeb firmy tvoří parkovné od veřejnosti, podmínka 80 % činnosti pro zadavatele není samozřejmá.

### 5.4 Ukončení ROZVOJ k 30. 6. 2026, opět zpětně; záloha snížena na polovinu

[RM 4. 8. 2026, 123/13](https://usneseni.muml.cz/rada/usneseni/2871212459): rada schválila dohody o ukončení Příkazní smlouvy ROZVOJ a Smlouvy o nájmu částí pozemků a změnila zálohu na zisk na **1 500 000 Kč ve dvou čtvrtletních splátkách po 750 000 Kč**. Dohoda o ukončení byla podepsána 19. 8. 2026 s účinky k 30. 6. 2026 ([registr 39379137](https://smlouvy.gov.cz/smlouva/39379137), uveřejněno 3. 9. 2026). Za první pololetí 2026 tedy město zaplatilo 1,5 mil. Kč bez DPH a dostalo zpět 1,5 mil. Kč zálohy.

Dodatek č. 1 k příkazní smlouvě ROZVOJ (30. 3. 2026) byl uveřejněn až 2. 6. 2026, po 64 dnech ([registr 38227661](https://smlouvy.gov.cz/smlouva/38227661)).

### 5.5 Smlouva o výpůjčce a správě svěřeného majetku (10. 8. 2026): zdarma na 6 let

[Registr 39325283](https://smlouvy.gov.cz/smlouva/39325283), bez uvedené hodnoty; schváleno [RM 4. 8. 2026, 123/12](https://usneseni.muml.cz/rada/usneseni/860601894) (RM/1383/26), účinnost 1. 7. 2026, doba 6 let. Město firmě **bezúplatně půjčuje** všechny pozemky s parkovacími automaty a parkovací plochy (34 lokalit) a k tomu **Kolonádu Ferdinandova pramene, Pavilon Rudolfova pramene a Pavilon Lesního pramene**. Firma smí majetek užívat komerčně (gastro, ubytování, podnájmy se souhlasem), investovat do 500 000 Kč bez DPH na akci bez souhlasu města a výnosy si nechává; pojištění platí město. Dodatek č. 1 z 1. 10. 2026 rozšířil výpůjčku o další plochy pro automaty ([RM 131/25](https://usneseni.muml.cz/rada/usneseni/1086759202)). Podklad: „analýza a právní podklady týkající se správy lázeňských pavilonů" vzaté na vědomí [RM 21. 7. 2026, 122/29](https://usneseni.muml.cz/rada/usneseni/3922839619), příloha usnesení není zveřejněna.

Výpůjčka nahradila **Smlouvu o nájmu částí pozemků pro umístění parkovacích automatů** (schválena [RM 27. 6. 2025, 91/31](https://usneseni.muml.cz/rada/usneseni/3390095) jako RM/477/25, podepsána až 29. 12. 2025, [registr 36633805](https://smlouvy.gov.cz/smlouva/36633805), bez hodnoty, uveřejněna po 36 dnech), kterou rada ukončila týmž usnesením 123/13. Z nájmu se tedy stala výpůjčka.

**Doložený fakt:** majetek, který městu v roce 2025 vynášel přes 9 mil. Kč parkovného, město od 1. 7. 2026 půjčuje své firmě zdarma, včetně tří lázeňských objektů. Povinnost zveřejnit záměr na úřední desce 15 dnů předem (§ 39 odst. 1 zákona o obcích) se tu **neuplatní**: § 39 odst. 3 z ní výpůjčku právnické osobě, kterou obec ovládá, výslovně vyjímá. Zůstává obecná povinnost nakládat s majetkem účelně a hospodárně (§ 38 odst. 1) a schválení radou, které proběhlo. **Otázky:** jaké je zdůvodnění bezúplatnosti a jak rada posoudila hospodárnost (podkladem byla „analýza správy pavilonů", jejíž příloha není zveřejněná); jaké je nájemné obvyklé za 34 parkovacích ploch a tři pavilony; zda byla výpůjčka s komerčním užíváním posouzena z hlediska veřejné podpory; a zda byla uzavřena jako vertikální spolupráce nebo koncese (bezúplatné přenechání majetku s právem na výnosy je ekonomicky koncesí na služby).

### 5.6 Automaty: město prodalo, firma kupuje, výjimky z vnitřního předpisu

- 12. 5. 2025 město prodalo firmě 21 parkovacích automatů za zůstatkovou hodnotu **461 758,50 Kč** ([RM 85/24](https://usneseni.muml.cz/rada/usneseni/3354663), [registr 33267512](https://smlouvy.gov.cz/smlouva/33267512)).
- 18. 3. 2025 rada udělila firmě **výjimku z vnitřního předpisu č. 2017-08 Veřejné zakázky** a pověřila jednatele koupit 10 automatů PSA7 od WSA doprava a parkování s.r.o. ([RM 81/42](https://usneseni.muml.cz/rada/usneseni/3340274)); smlouva o dílo 26. 5. 2025 za 2 070 032 Kč s DPH ([registr 33467688](https://smlouvy.gov.cz/smlouva/33467688)). 25. 2. 2025 schválen nákup 15 automatů a 19 sloupků do 5 mil. Kč bez DPH ([RM 78/32](https://usneseni.muml.cz/rada/usneseni/3325559)).
- 7. 7. 2026 další výjimka: 3 automaty od WSA za 498 240 Kč bez DPH ([RM 121/32](https://usneseni.muml.cz/rada/usneseni/2334157148)); 18. 8. 2026 výjimka na 20 stojanů od KOVODŘEVO.CZ za 288 000 Kč bez DPH ([RM 126/13](https://usneseni.muml.cz/rada/usneseni/2330048859)); 1. 10. 2026 výjimka na údržbu střechy Pavilonu Lesního pramene za 156 864 Kč s DPH ([RM 131/24](https://usneseni.muml.cz/rada/usneseni/212627609)).

**Doložený fakt:** rada opakovaně schvaluje firmě výjimky z městského předpisu o zakázkách, tedy nákup bez poptávky. **Otázka:** zda se vnitřní předpis města na s.r.o. vůbec vztahuje (a pokud ne, proč se výjimky udělují), kolik výjimek firma za roky 2023–2026 dostala a zda má firma vlastní pravidla zadávání.

### 5.7 Pozemky a narovnání: parkovací dům, parcela 1/12, městská policie

- Prodej pozemků pod parkovacím domem: 9 764 844 Kč s DPH (23. 8. 2023, [registr 25530603](https://smlouvy.gov.cz/smlouva/25530603)) po předchozí smlouvě z 26. 7. 2023 za 282 007 Kč ([registr 25370915](https://smlouvy.gov.cz/smlouva/25370915)). Zpráva o vztazích 2022 předtím uváděla bezúplatné užívání pozemků městem poskytované.
- „Dohoda o narovnání sporných nároků" schválená zastupitelstvem 19. 11. 2024 ([ZM 17/28](https://usneseni.muml.cz/zastupitelstvo/usneseni/3280731), ZM/401/24): město firmě 605 000 Kč za „narovnání majetkoprávních vztahů k užívání nebytových prostor vč. energií" ([registr 31129212](https://smlouvy.gov.cz/smlouva/31129212)). Ve stejné výši 605 000 Kč pak firma koupila pozemek p. p. č. 1/12 (977 m²) u Pramenské ([registr 32065240](https://smlouvy.gov.cz/smlouva/32065240), záměr [RM 67/30](https://usneseni.muml.cz/rada/usneseni/3259137)).
- Nájem kanceláří pro městskou policii v parkovacím domě: měsíční smlouvy 2022–2025, od 15. 7. 2025 na dobu neurčitou za 39 680 Kč měsíčně ([registr 34466361](https://smlouvy.gov.cz/smlouva/34466361), uveřejněno po 34 dnech). Zpráva o vztazích 2022 přitom uváděla, že kanceláře poskytovala firma městu bezúplatně.

**Otázka:** co byly „sporné nároky" za 605 000 Kč (užívání kanceláří městskou policií bez smlouvy?), za jaké období, a proč stejná částka hned posloužila jako kupní cena pozemku.

### 5.8 Bydlení, Nové Centrum, Třešňovka

- Příkazní smlouva pro podporu nájemního a dostupného bydlení, 16. 12. 2024 ([registr 31453912](https://smlouvy.gov.cz/smlouva/31453912), schváleno [RM 69/23](https://usneseni.muml.cz/rada/usneseni/3272262)); účinnost 29. 10. 2024 (před podpisem), odměna „součástí odměny za správu parkování", v registru bez hodnoty. Rada podle ní zadává firmě projekty Hamrníky, U Pily, Taormina, Třešňovka a schvaluje jí „mimořádné náklady" (doprůzkum deponií 39 000 Kč, průzkum kontaminace 53 608 Kč, stavební standardy 78 400 Kč).
- Příkazní smlouva Nové Centrum (nová radnice na centrálním parkovišti, PPP), 10. 2. 2025 ([registr 32406080](https://smlouvy.gov.cz/smlouva/32406080), [RM 74/13](https://usneseni.muml.cz/rada/usneseni/3299857), RM/876/24), odměna „dle kalkulací", bez hodnoty. ČSOB Advisory dostala na obě témata rámcové smlouvy s výjimkou z vnitřního předpisu ([RM 112/5](https://usneseni.muml.cz/rada/usneseni/899142487), [RM 122/10](https://usneseni.muml.cz/rada/usneseni/2372869812)).
- **Třešňovka:** nadlimitní zakázka „Komplex bytových domů Třešňovka – Design and Build" (190 mil. Kč bez DPH), administraci rada uložila firmě 26. 5. 2026 ([RM 118/7](https://usneseni.muml.cz/rada/usneseni/1325369221)); tři nabídky 28. 7. 2026; 29. 7. 2026 výzva ÚOHS (ÚOHS-P0777/2026/VZ), vyjádření zadavatele schváleno [RM 7. 8. 2026, 124/3](https://usneseni.muml.cz/rada/usneseni/1238088345); Hlídač státu vede u obou záznamů zakázky stav „Zrušen" (poslední změna 21. 10. 2026), odpověď na stovku šestku ze 7. 10. 2026 (`data/informace106/texty/`) říkala, že řízení pokračuje do 26. 10. 2026.

**Otázka:** zda byla zakázka Třešňovka zrušena a proč, co ÚOHS vytýkal, kolik město zaplatilo za administraci a poradenství (firma, ČSOB Advisory, advokáti) a zda firma jako administrátor zakázky splňovala požadavky na nezávislost.

### 5.9 Firma sama používá bezdůvodné obohacení

13. 1. 2026 uzavřela firma s HOTELIS s.r.o. (Karlovy Vary) „Smlouvu o užívání parkovacích stání **a o vypořádání bezdůvodného obohacení**" za 600 000 Kč bez DPH ([registr 36459385](https://smlouvy.gov.cz/smlouva/36459385)). Vymáhá tedy po soukromém hotelu úhradu za parkování bez smlouvy; totéž pravidlo (§ 2991 o. z.) platí pro plnění ze smluv, které město a firma uzavřely se zpětnou účinností (§ 5.3, 5.4, 5.8).

## 6. Smlouvy firmy v registru a jejich uveřejnění

Všech 51 záznamů, u nichž registr vrátil stránku; dny = od uzavření do prvního uveřejnění. Lhůta 30 dnů (§ 5 odst. 2), zrušení od počátku po 3 měsících (§ 7 odst. 1), výjimka do 50 000 Kč bez DPH (§ 3 odst. 2 písm. h). Zdroj `data/penize/lhuty_zverejneni.json`.

**Po více než třech měsících** (u smluv nad 50 000 Kč bez DPH platí, že jsou zrušené od počátku):

| uzavřeno | uveřejněno | dnů | smlouva | Kč s DPH | protistrana |
|---|---|---|---|---|---|
| 1. 1. 2024 | 14. 6. 2024 | 165 | [smlouva o užívání parkovacích stání](https://smlouvy.gov.cz/smlouva/29086468) | 363 000 | Dopravní podnik Karlovy Vary |
| 31. 7. 2025 | 15. 12. 2025 | 137 | [příkazní smlouva, účetní poradenství](https://smlouvy.gov.cz/smlouva/36042753) | 72 600 | · |
| 23. 6. 2026 | 23. 10. 2026 | 122 | [objednávka zastavovací studie Bydlení u Pily](https://smlouvy.gov.cz/smlouva/40060489) | 118 580 | Studio Prokon s.r.o. |
| 1. 7. 2026 | 23. 10. 2026 | 114 | [objednávka studie proveditelnosti](https://smlouvy.gov.cz/smlouva/40060429) | 266 200 | Dopravní stavby a venkovní architektura |
| 18. 10. 2016 | 20. 7. 2017 | 275 | [prodej parkovacích karet](https://smlouvy.gov.cz/smlouva/2627738) | 121 000 | město (před účinností § 7) |

U smlouvy s Dopravním podnikem Karlovy Vary stojí za pozornost, že 15. 8. 2024 byla uzavřena nová smlouva o užívání parkovacích stání se stejnou protistranou a stejnou hodnotou 363 000 Kč, uveřejněná týž den ([registr 29871560](https://smlouvy.gov.cz/smlouva/29871560)). To odpovídá postupu „zrušená smlouva nahrazena novou"; plnění za leden až srpen 2024 ale novou smlouvou pokryté není, pokud to dohoda neřeší. Dvě objednávky z června a července 2026 byly uveřejněny najednou 23. 10. 2026, čtyři dny před stavem tohoto dokumentu, spolu s objednávkou údržby střechy (1. 10. 2026).

**Po 31 až 90 dnech:** stavební práce na parkovacím domě 825 861 Kč (91 dní, [36798385](https://smlouvy.gov.cz/smlouva/36798385), o den uvnitř tříměsíční lhůty), turniket 365 541 Kč (60 dní), úklidové služby 217 800 Kč (60 dní), Dodatek č. 1 k příkazní ROZVOJ (64 dní, bez hodnoty), smlouvy o užívání parkovacích stání s Reitenberger s.r.o. 544 500 Kč (48 dní), REGION-TRAVEL 43 560 Kč (47) a s menšími protistranami (47 až 85 dní, většinou pod limitem 50 000 Kč), EasyPark (48, bez hodnoty), nájem pro městskou policii (34), objednávka marketingu 155 318 Kč (36), smlouva o nájmu pozemků pro automaty (36, bez hodnoty), dohoda o postoupení nájmu 303 000 Kč (42).

**Zpětná účinnost** (smlouva účinná dřív než uveřejněná, § 6 odst. 1): příkazní ROZVOJ (1. 1. 2026 vs. 10. 2. 2026), příkazní bydlení (29. 10. 2024 vs. 16. 12. 2024), dohoda o ukončení ROZVOJ (30. 6. 2026 vs. 3. 9. 2026), výpůjčka (1. 7. 2026 vs. 31. 8. 2026).

**Bez uvedené hodnoty** v registru: příkazní bydlení, příkazní Nové Centrum, Dodatek č. 1 ROZVOJ, nájem pozemků pro automaty, výpůjčka, dohoda o ukončení ROZVOJ, EasyPark, jedna smlouva o stání. U smluv, kde se cena nedá určit, zákon připouští uvést to místo ceny; u příkazních smluv s odměnou „dle kalkulací" je to ale právě to, na co se ptát.

Co **není** v registru vůbec: 90 % provize se účtuje na základě jedné smlouvy z roku 2024, jednotlivé měsíční faktury se neuveřejňují (nejsou smlouvy). Výši skutečně vyplacené odměny za roky 2024–2025 je tedy třeba žádat.

## 7. Souhrn otázek

1. **Ekonomika pro město.** Kolik parkovného firma vybrala v letech 2024, 2025 a 2026, kolik město firmě zaplatilo (provize, paušál, mimořádné náklady, marketing) a kolik dostalo zpět (záloha na zisk, nájem, kupní ceny). Městu v roce 2025 zbylo z 9 mil. Kč parkovného asi 1,4 mil. Kč.
2. **Záloha na zisk** 3 mil. Kč (pak 1,5 mil.): mezitímní účetní závěrka podle § 40 odst. 2 ZOK; proč záloha ve stejné výši a stejném rytmu jako paušál.
3. **Zpětné účinnosti** čtyř smluv a vypořádání plnění před uveřejněním.
4. **Výpůjčka zdarma** 34 parkovacích ploch a tří pavilonů na 6 let: zdůvodnění bezúplatnosti a hospodárnosti (§ 38 zákona o obcích; zveřejnění záměru se u výpůjčky ovládané firmě nevyžaduje, § 39 odst. 3), posouzení veřejné podpory a koncese.
5. **Zadání bez soutěže**: posouzení § 11 ZZVZ (vertikální spolupráce) u příkazních smluv; výjimky z vnitřního předpisu 2017-08 pro s.r.o.
6. **Sbírka listin**: zprávy o vztazích 2023–2025, výroční zprávy, zpráva auditora 2025.
7. **Střet zájmů jednatele**: oznámení podle § 54–55 ZOK, Zahradní a parková spol. s r.o. jako dodavatel města.
8. **Odměny** jednatelů a dozorčí rady, počet zaměstnanců, mzdové náklady 2024–2026.
9. **Snížení základního kapitálu** (43 mil. Kč): účel a komu se vyplatí.
10. **Třešňovka**: stav zakázky, výtky ÚOHS, náklady administrace.
11. **Narovnání 605 000 Kč** z roku 2024: čeho se sporné nároky týkaly.
12. **Smlouva s Dopravním podnikem KV** 1. 1. 2024: byla ze zákona zrušena, a jak bylo vypořádáno plnění do 15. 8. 2024.

## 8. Komu žádost poslat a jak

**Město** (Městský úřad Mariánské Lázně) je povinný subjekt podle § 2 odst. 1 zákona č. 106/1999 Sb. **Firma sama** je povinným subjektem jako veřejná instituce: Ústavní soud (I. ÚS 260/06, Letiště Praha) a navazující judikatura správních soudů považují obchodní společnost se 100 % účastí obce, zřízenou k obecním úkolům a ovládanou obcí, za veřejnou instituci podle § 2 odst. 1 InfZ. Žádost firmě se posílá do datové schránky **aaffkjx** nebo na adresu sídla. Lhůta 15 dnů (§ 14 odst. 5 písm. d), prodloužení o 10 dnů (§ 14 odst. 6), stížnost podle § 16a; o odvolání a stížnosti u takové firmy rozhoduje Úřad pro ochranu osobních údajů (§ 20 odst. 5 InfZ ve znění od roku 2020).

Co žádat **po městě**: kalkulace odměny 90 %, přehled plateb firmě 2024–2026 po měsících, přehled přijatých záloh na zisk, zdůvodnění bezúplatnosti výpůjčky a posouzení její hospodárnosti, přílohy usnesení RM/515/24, RM/910/26, RM/1383/26 a analýzu správy pavilonů z RM 122/29, posouzení podle § 11 ZZVZ, vnitřní předpis 2017-08 a seznam udělených výjimek, oznámení střetu zájmů jednatele, podklady k rozhodnutí o záloze na zisk (mezitímní závěrka), dohody o ukončení s účinky k 30. 6. 2026, vyúčtování za Třešňovku.

Co žádat **po firmě**: zprávy o vztazích 2023, 2024, 2025 a zprávu auditora 2025, výkaz činnosti k příkazní smlouvě ROZVOJ za 1. pololetí 2026, přehled vybraného parkovného 2024–2026 po měsících, smlouvy a odměny jednatelů a členů dozorčí rady, počet zaměstnanců po letech, vnitřní pravidla pro zadávání zakázek, vypořádání s HOTELIS s.r.o. (odkud se vzala částka 600 000 Kč).

Vzor žádosti a lhůty: [`namety-106.md`, § 6](namety-106.md). Doporučení z téhož dokumentu platí i tady: ptát se na dokumenty (kalkulace, výkaz, oznámení, zápis), ne na názory; zúžit období a částky, aby nešlo o zneužití práva podle § 11a.

## 9. Zdroje

- Veřejný rejstřík a sbírka listin or.justice.cz, ARES, registr plátců DPH: konektor Sagasu (`verejny_rejstrik`, `obchodni_rejstrik`, `sbirka_listin`, `listina_text`, `pdf_obrazek_strany`, `verejny_rejstrik_osoba`, `dph_status`). Přímý odkaz: [or.justice.cz, IČO 61776068](https://or.justice.cz/ias/ui/rejstrik-$firma?ico=61776068).
- Registr smluv a Hlídač státu: odkazy u jednotlivých smluv; sklizeň v `data/penize/smlouvy/61776068.json`, data uveřejnění v `data/penize/lhuty_zverejneni.json` (`scrapers/registr_lhuty.py`).
- Usnesení rady a zastupitelstva: odkazy na usneseni.muml.cz u jednotlivých bodů; sklizeň v `data/usneseni/`.
- Rozpočet města: Monitor státní pokladny, FIN 2-12 M, `data/rozpocet/fin212m/`.
- Odpověď města na žádost o informace k Třešňovce ze 7. 10. 2026: `data/informace106/texty/`.
- Zákony: č. 340/2015 Sb. (registr smluv), č. 90/2012 Sb. (ZOK, § 40, 54–55, 82–84), č. 128/2000 Sb. (o obcích, § 38, 39, 102), č. 134/2016 Sb. (ZZVZ, § 11), č. 563/1991 Sb. (o účetnictví, § 21a), č. 304/2013 Sb. (o veřejných rejstřících, § 104–107), č. 106/1999 Sb. (InfZ), vše na zakonyprolidi.cz.
