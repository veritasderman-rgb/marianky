/** Zploštění usnesení a hlasování do seznamů, se kterými se dá filtrovat. */
import type { BodUsneseni, Hlas, HlasovaniSoubor, JmenovityHlas, Tag, Usneseni } from './data';
import { rokZData } from './format';

export interface PolozkaHlasovani {
  id: string;
  organ: string;
  cj: number;
  datum: string;
  rok: number | null;
  bod: string;
  nazev: string;
  tagy: string[];
  vysledek: string;
  pro: number;
  proti: number;
  zdrzel: number;
  nehlasoval: number;
  jmenovite: JmenovityHlas[];
}

export interface PolozkaUsneseni extends BodUsneseni {
  organ: string;
  cj: number;
  datum: string;
  rok: number | null;
  url?: string;
}

export function zplostiHlasovani(soubory: HlasovaniSoubor[]): PolozkaHlasovani[] {
  const ven: PolozkaHlasovani[] = [];
  for (const s of soubory) {
    for (const h of s.hlasovani ?? []) {
      if (!h) continue;
      ven.push({
        id: h.id ?? `${s.organ}-${s.cj}-${h.bod ?? ven.length}`,
        organ: s.organ ?? 'neznamo',
        cj: s.cj,
        datum: s.datum ?? '',
        rok: rokZData(s.datum),
        bod: h.bod ?? '',
        nazev: h.nazev ?? '(bez názvu)',
        tagy: Array.isArray(h.tagy) ? h.tagy : [],
        vysledek: h.vysledek ?? 'neznamo',
        pro: cele(h.pro),
        proti: cele(h.proti),
        zdrzel: cele(h.zdrzel),
        nehlasoval: cele(h.nehlasoval),
        jmenovite: Array.isArray(h.jmenovite) ? h.jmenovite : [],
      });
    }
  }
  ven.sort((a, b) => b.datum.localeCompare(a.datum) || a.bod.localeCompare(b.bod));
  return ven;
}

export function zplostiUsneseni(soubory: Usneseni[]): PolozkaUsneseni[] {
  const ven: PolozkaUsneseni[] = [];
  for (const u of soubory) {
    for (const b of u.body ?? []) {
      if (!b) continue;
      ven.push({
        ...b,
        tagy: Array.isArray(b.tagy) ? b.tagy : [],
        organ: u.organ ?? 'neznamo',
        cj: u.cj,
        datum: u.datum ?? '',
        rok: rokZData(u.datum),
        url: u.url,
      });
    }
  }
  ven.sort((a, b) => b.datum.localeCompare(a.datum) || String(a.cislo).localeCompare(String(b.cislo)));
  return ven;
}

function cele(v: unknown): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : 0;
}

/** Kolikrát se který tag v seznamu vyskytl. Nabízíme jen tagy, které něco najdou. */
export function spocitejTagy(polozky: { tagy?: string[] }[]): Map<string, number> {
  const m = new Map<string, number>();
  for (const p of polozky) for (const t of p.tagy ?? []) m.set(t, (m.get(t) ?? 0) + 1);
  return m;
}

export function mapaTagu(tagy: Tag[]): Map<string, Tag> {
  return new Map(tagy.map((t) => [t.id, t]));
}

export function seradRoky(polozky: { rok: number | null }[]): number[] {
  const s = new Set<number>();
  for (const p of polozky) if (p.rok !== null) s.add(p.rok);
  return [...s].sort((a, b) => b - a);
}

export function tridaVysledku(v: string): string {
  if (v === 'schvaleno') return 'schvaleno';
  if (v === 'neschvaleno') return 'neschvaleno';
  return 'jine';
}

export function souhrnHlasu(h: PolozkaHlasovani): { pro: JmenovityHlas[]; proti: JmenovityHlas[]; zdrzel: JmenovityHlas[]; ostatni: JmenovityHlas[] } {
  const pro: JmenovityHlas[] = [];
  const proti: JmenovityHlas[] = [];
  const zdrzel: JmenovityHlas[] = [];
  const ostatni: JmenovityHlas[] = [];
  for (const j of h.jmenovite) {
    if (j.hlas === 'pro') pro.push(j);
    else if (j.hlas === 'proti') proti.push(j);
    else if (j.hlas === 'zdrzel') zdrzel.push(j);
    else ostatni.push(j);
  }
  return { pro, proti, zdrzel, ostatni };
}

export type { Hlas };
