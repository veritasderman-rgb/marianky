/**
 * Jednorázové načtení dat v rámci jednoho buildu.
 *
 * Stránky s `getStaticPaths()` (profily lidí, protistrany, firmy) se renderují
 * po stovkách a jejich frontmatter běží pro každou z nich znovu. Bez tohohle
 * by se `data/penize/smlouvy/` četlo z disku pětsetkrát.
 *
 * Modul se v Astro naimportuje jednou, takže mapa přežije mezi stránkami.
 * Cache je jen pro čtení při buildu — nic se nemění, takže se nemá co zkazit.
 */
const ulozene = new Map<string, unknown>();

export function jednou<T>(klic: string, nacti: () => T): T {
  if (!ulozene.has(klic)) ulozene.set(klic, nacti());
  return ulozene.get(klic) as T;
}
