# Mariánky

Občanský portál a týdenní přehled dění v Mariánských Lázních.

Jednou týdně vyjde jedno přehledné číslo o tom, co se ve městě za uplynulý týden stalo — radnice, peníze, městské firmy, akce, média. Vedle toho web drží trvalý prohledávatelný archiv: články z městského zpravodaje rozebrané z PDF do textu, usnesení rady a zastupitelstva včetně jmenovitých hlasování, profily zastupitelů a časové osy dlouhodobých témat.

Pro občana, který se zajímá o dění ve městě, ale nemá čas si sám procházet úřední desku, registr smluv a tři facebookové skupiny.

## Dokumentace

| Dokument | Obsah |
|---|---|
| [`ZADANI.md`](ZADANI.md) | Funkční zadání — co web umí, jak je postavený, jak běží týdenní rutina |
| [`docs/datove-zdroje.md`](docs/datove-zdroje.md) | Technický inventář zdrojů — ověřená dostupnost, formáty, úskalí |

## Stav

Fáze zadání. Implementace zatím nezačala.

Datové zdroje byly ověřeny v praxi 17. 8. 2026 — dostupnost, formáty i technická úskalí jsou popsané v inventáři, včetně toho, co proveditelné **není** (automatizovaný sběr z Facebooku, RSS na webu města).

## Zásada, na které to stojí

> **Scraping dělá kód. Porozumění dělá Claude.**

Jazykový model neparsuje HTML — to je práce pro deterministický skript, který buď funguje, nebo spadne s chybou. Model dostává čistá strukturovaná data a jeho úkolem je jim rozumět, shrnout je a napsat text. Každé tvrzení ve vydání má dohledatelný zdroj.
