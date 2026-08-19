# Naše Mariánky v přehledech

Veřejný přehled dění v Mariánských Lázních. Jednou týdně vyjde jedno číslo o tom, co se ve městě stalo — radnice, peníze, městské firmy, akce, média. Vedle toho web drží trvalý prohledávatelný archiv.

Pro občana, který se zajímá o dění ve městě, ale nemá čas si sám procházet úřední desku, usnesení rady a registr smluv.

## Co je v datech

| | |
|---|---|
| jednání rady a zastupitelstva | **690** (2012–2026) |
| bodů usnesení | **12 890**, otagovaných podle 33 témat |
| hlasování | **12 349**, z toho **121 935 jmenovitých hlasů** |
| smluv v registru | **6 521** za 25 subjektů městského holdingu |
| protistran města | **1 566**, roky 1994–2026 |
| čísel zpravodaje | **122** (02/2016–08/2026), rozebraných na **4 519 článků** |
| osobností | **199** v osmi kategoriích |
| mediálních článků | **713** (2004–2026) |
| spojení usnesení → smlouva → peníze | **2 289** |
| týdenních vydání | **13** včetně zpětného archivu |

## Co web umí

**Týdenní vydání** — jedno číslo za týden, s archivem zpět.

**Peníze** — kdo od města bere peníze a kdy. Heatmapa ukazuje, kdy která firma začala a kdy přestala; skládaný graf rozděluje objem po letech. Platby vlastním firmám města jsou označené jako vnitřní převod, ne jako plnění cizímu dodavateli.

**Hlasování podle témat** — 12 349 hlasování filtrovatelných podle 33 tagů z pevného číselníku.

**Kdo je kdo** — profily s hlasovací historií, účastí a aktivitou podle témat. U zastupitelů i seznam **všech firem, kde jsou aktivní** — včetně těch, které s městem vůbec neobchodují. To je smyslem: ukázat celý obrázek, ne jen podezřelé věci.

**Propojení** — kdo ze samosprávy sedí ve kterých firmách a kolik ty firmy od města dostaly. Fakta vedle sebe, úsudek na čtenáři.

**Archiv zpravodaje** — 4 519 článků z jedenácti ročníků, fulltextově prohledávatelných.

**Řetěz usnesení → smlouva → peníze** — co rada schválila, jaká smlouva se podepsala a kolik odteklo. U každého spojení je uvedená jistota; nízká je označená jako domněnka.

## Dokumentace

| Dokument | Obsah |
|---|---|
| [`docs/PROVOZ.md`](docs/PROVOZ.md) | **Začni tady.** Co spustit, co dělat při selhání, na co si dát pozor v datech |
| [`ZADANI.md`](ZADANI.md) | Funkční zadání |
| [`docs/PLAN.md`](docs/PLAN.md) | Kontrakt datových formátů |
| [`docs/datove-zdroje.md`](docs/datove-zdroje.md) | Inventář zdrojů — co funguje, co ne a proč |
| [`web/DESIGN.md`](web/DESIGN.md) | Vzhled a pravidla grafů |

## Zásada, na které to stojí

> **Scraping dělá kód. Porozumění dělá Claude.**

Model neparsuje HTML — to je práce pro deterministický skript, který buď funguje, nebo spadne s chybou. Když se web města změní, sběrač spadne a je to vidět; kdyby to dělal model, tiše by si obsah vymyslel.

Z toho plyne druhá zásada: **prázdno a neznámo nejsou totéž**. Každá sekce vydání rozlišuje „nic se nedělo" od „zdroj nebyl dostupný" a od „zdroj odpověděl, ale jeho data končí dávno před obdobím". Kdyby to splynulo, přehled by tiše lhal právě v tom týdnu, kdy by na tom nejvíc záleželo.

Totéž platí o hodnotách: neznámý údaj se nikdy neukládá jako nula. Pole `vazba_na_politiky` je u všech smluv `null`, protože ho Hlídač přes API nevyplňuje — dřív tam bylo `false`, což znamenalo „ověřeno, že vazba není", a to byla nepravda.

## Rychlý start

```bash
pip install requests selectolax
sudo apt-get update && sudo apt-get install -y poppler-utils
echo 'HLIDAC_TOKEN=...' > .env        # zdarma po registraci na hlidacstatu.cz
cd web && npm install && cd ..

python3 run_tyden.py                  # týdenní běh
cd web && npm run build               # sestavení webu
```

Podrobnosti a řešení potíží v [`docs/PROVOZ.md`](docs/PROVOZ.md).

## Stav

Fáze 1 až 4 hotové. Dvě věci musí proběhnout z jiné sítě, než ve které projekt vznikal:

- **Přepisy jednání zastupitelstva** — kód je hotový a otestovaný, ale YouTube vracel kontejneru `429`. Ověřeno, že záznamů je 94 a mají v názvu datum, takže se spárují s usneseními.
- **Aktuální úřední deska** — `www.muml.cz` nám resetuje spojení; data končí v květnu 2025 a vydání to přiznává stavem `zastarale`.

**Portál je veřejný**, bez hesla a bez přihlášení. `robots.txt` pouští vyhledávače dovnitř a generuje se sitemap — kdo hledá, jak zastupitel hlasoval, má sem dojít. Není to web města ani jeho oficiální kanál.
