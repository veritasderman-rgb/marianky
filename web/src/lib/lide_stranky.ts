/* Jen pro build (čte data z disku) — nesmí se importovat z klientských skriptů. */
import { jednou } from './cache';
import { nactiHlasovani, nactiLidi } from './data';
import { zplostiHlasovani } from './prehledy';

/**
 * Id → jméno všech lidí, kteří mají na webu stránku `/lide/{id}`.
 *
 * Stránku dostává každý z `lide/osobnosti.json` a navíc ten, kdo se objevil
 * ve jmenovitém hlasování, i když profil zatím nemá — přesně podle
 * `getStaticPaths` v `pages/lide/[id].astro`. Kdo odkazuje na osobu odjinud
 * (zpravodaj), ptá se tady, jestli odkaz někam povede.
 */
export function jmenaLidiSeStrankou(): Map<string, string> {
  return jednou('lide-se-strankou', () => {
    const { data: lide } = jednou('lide', nactiLidi);
    const { data: soubory } = jednou('hlasovani', nactiHlasovani);
    const hlasovani = jednou('hlasovani-ploche', () => zplostiHlasovani(soubory ?? []));
    const jmena = new Map<string, string>();
    for (const o of lide ?? []) {
      if (o?.id) jmena.set(o.id, o.jmeno ?? o.id);
    }
    for (const h of hlasovani) {
      for (const j of h.jmenovite) {
        if (j.osoba_id && !jmena.has(j.osoba_id)) jmena.set(j.osoba_id, j.jmeno ?? j.osoba_id);
      }
    }
    return jmena;
  });
}
