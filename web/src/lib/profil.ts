/**
 * Hlasovací statistiky jedné osoby, spočítané přímo z `data/hlasovani/`.
 *
 * Proč se to počítá tady a ne se čte z `lide/profily.json`: tohle jsou prosté
 * součty nad daty, která web už načítá. Když soubor profilů ještě nevznikl,
 * stránka díky tomu není prázdná. Co z prostých součtů neplyne (matice shody,
 * odchylky od vlastního uskupení, hlasování o velkých částkách), se odsud
 * NEDOPOČÍTÁVÁ — to patří modulu, který profily staví.
 *
 * Jmenovatel je vždy „hlasování, kde je osoba uvedená ve jmenovitém seznamu".
 * Nic jiného z dat neplyne: kdo v seznamu není, nemusel chybět — nemusel být
 * v tu chvíli členem orgánu. Tenhle rozdíl se propisuje do textu na stránce.
 */
import type { PolozkaHlasovani } from './prehledy';

export interface ZaznamUcasti {
  h: PolozkaHlasovani;
  hlas: string;
}

export interface StatistikyOsoby {
  /** Hlasování, kde je osoba ve jmenovitém seznamu. */
  zaznamy: ZaznamUcasti[];
  /** Počty podle druhu hlasu — klíč je hodnota z dat, nedoplňuje se. */
  pocty: Record<string, number>;
  /** Kolikrát odevzdala hlas (pro / proti / zdržel se). */
  odevzdanych: number;
  /** Podíl odevzdaných hlasů ze zaznamenaných hlasování, 0–1. `null` bez dat. */
  podilOdevzdanych: number | null;
  /** Kolik hlasování za jednotlivé tagy. */
  podleTagu: Map<string, number>;
  /** Podle orgánu — rada a zastupitelstvo se často liší. */
  podleOrganu: Map<string, number>;
  prvni: string | null;
  posledni: string | null;
}

/** Hlasy, které znamenají odevzdaný hlas. Ostatní se jen počítají, nehodnotí. */
const ODEVZDANE = new Set(['pro', 'proti', 'zdrzel']);

export function statistikyOsoby(vsechna: PolozkaHlasovani[], osobaId: string): StatistikyOsoby {
  const zaznamy: ZaznamUcasti[] = [];
  const pocty: Record<string, number> = {};
  const podleTagu = new Map<string, number>();
  const podleOrganu = new Map<string, number>();

  for (const h of vsechna) {
    const j = h.jmenovite.find((x) => x.osoba_id === osobaId);
    if (!j) continue;
    const hlas = typeof j.hlas === 'string' && j.hlas ? j.hlas : 'neuvedeno';
    zaznamy.push({ h, hlas });
    pocty[hlas] = (pocty[hlas] ?? 0) + 1;
    for (const t of h.tagy) podleTagu.set(t, (podleTagu.get(t) ?? 0) + 1);
    podleOrganu.set(h.organ, (podleOrganu.get(h.organ) ?? 0) + 1);
  }

  const odevzdanych = zaznamy.filter((z) => ODEVZDANE.has(z.hlas)).length;
  const data = zaznamy.map((z) => z.h.datum).filter(Boolean).sort();

  return {
    zaznamy,
    pocty,
    odevzdanych,
    podilOdevzdanych: zaznamy.length > 0 ? odevzdanych / zaznamy.length : null,
    podleTagu,
    podleOrganu,
    prvni: data[0] ?? null,
    posledni: data[data.length - 1] ?? null,
  };
}

/** Pořadí druhů hlasu pro grafy a tabulky — pevné, ať se pohled nepřehazuje. */
export const PORADI_HLASU = ['pro', 'proti', 'zdrzel', 'nehlasoval', 'nepritomen', 'omluven', 'neuvedeno'];

export function seradPocty(pocty: Record<string, number>): { hlas: string; pocet: number }[] {
  const znama = PORADI_HLASU.filter((h) => (pocty[h] ?? 0) > 0).map((h) => ({ hlas: h, pocet: pocty[h] }));
  const ostatni = Object.entries(pocty)
    .filter(([h]) => !PORADI_HLASU.includes(h))
    .map(([hlas, pocet]) => ({ hlas, pocet }));
  return [...znama, ...ostatni];
}
