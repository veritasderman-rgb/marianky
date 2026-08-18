/**
 * Vztah firmy k městu — typ a jeho slovní popis.
 *
 * Stojí to zvlášť, i když je to pár řádků, kvůli tomu, co je smí použít.
 * `vazby.ts` načítá soubory přes `node:fs`, takže z prohlížeče se z něj
 * nedá importovat nic — kdo to zkusí, shodí build na
 * „fileURLToPath is not exported by __vite-browser-external".
 *
 * Seznam hlasování se přitom skládá i v prohlížeči a popis vztahu potřebuje.
 * Tenhle soubor proto nic nenačítá a nesmí začít.
 */

export type VztahKMestu =
  | 'mestsky-subjekt'
  | 'obchoduje-s-mestem'
  | 'bez-vazby-na-mesto'
  | null;

/** Popis vztahu firmy k městu. */
export function popisVztahu(v: VztahKMestu): string {
  if (v === 'mestsky-subjekt') return 'městská organizace nebo firma města';
  if (v === 'obchoduje-s-mestem') return 'obchoduje s městem';
  if (v === 'bez-vazby-na-mesto') return 's městem neobchoduje';
  return 'v datech není uvedeno';
}
