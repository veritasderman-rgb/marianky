/**
 * Časové řady o městě — `data/opendata/csu/`.
 *
 * Zdroj: `casove_rady.json` (jednotlivé řady) a `prehled.json` (metadata sad,
 * zdroj a licence). Zdroj sám formuluje pravidla, která web jen přenáší:
 *
 *   > Chybějící hodnota je `null`. Když ji ČSÚ tají kvůli malému počtu
 *   > subjektů, je navíc `duverne: true` — to je **neznámo, ne nula**.
 *
 * Řady se nemíchají do jednoho grafu napříč jednotkami (web/DESIGN.md §2
 * bod 1). Do jednoho grafu smí jen členění téhož ukazatele — tam je jednotka
 * z definice stejná.
 */
import { nactiJson, type Nacteno } from './data';
import { cislo } from './format';
import { cis, jeObjekt, objekty, txt, type Zaznam } from './tolerantni';

export type Perioda = 'rok' | 'mesic' | 'scitani' | 'jina';

export interface BodRadyCsu {
  obdobi: string;
  hodnota: number | null;
  /** ČSÚ hodnotu tají kvůli malému počtu subjektů. Není to nula. */
  duverne: boolean;
}

export interface RadaCsu {
  kod: string;
  /** Název ukazatele, např. „Počet obyvatel k 31. 12.". */
  nazev: string;
  jednotka: string | null;
  /** Členění ukazatele — věk, pohlaví, země… Prázdné u součtu za celek. */
  cleneni: { klic: string; hodnota: string }[];
  perioda: Perioda;
  sada: string;
  od: string | null;
  do: string | null;
  body: Map<string, BodRadyCsu>;
  chybejiciObdobi: string[];
}

export interface SadaCsu {
  kod: string;
  nazev: string;
  stav: string | null;
  perioda: Perioda;
  od: string | null;
  do: string | null;
  zaznamu: number | null;
  ukazatelu: number | null;
}

export interface DataCsu {
  rady: RadaCsu[];
  sady: SadaCsu[];
  zdroj: string | null;
  licence: string | null;
  poznamka: string | null;
  obec: string | null;
}

function periodaZ(v: string | null): Perioda {
  const s = (v ?? '').trim().toLowerCase();
  return s === 'rok' || s === 'mesic' || s === 'scitani' ? s : 'jina';
}

function cleneniZ(z: Zaznam): { klic: string; hodnota: string }[] {
  // Zdroj používá klíč s diakritikou (`clenění`); přijímá se i bez ní.
  const c = jeObjekt(z['clenění']) ? z['clenění'] : jeObjekt(z.cleneni) ? z.cleneni : null;
  if (!c) return [];
  return Object.entries(c)
    .filter(([, v]) => typeof v === 'string' && v.trim())
    .map(([klic, v]) => ({ klic, hodnota: (v as string).trim() }));
}

export function nactiCsu(): Nacteno<DataCsu> {
  const zRad = nactiJson<unknown>('opendata/csu/casove_rady.json', null);
  const zPrehledu = nactiJson<unknown>('opendata/csu/prehled.json', null);

  const koren = jeObjekt(zRad.data) ? zRad.data : {};
  const prehled = jeObjekt(zPrehledu.data) ? zPrehledu.data : {};

  const rady: RadaCsu[] = objekty(koren, 'rady', 'řady', 'series')
    .map((z) => {
      const kod = txt(z, 'kod');
      const nazev = txt(z, 'nazev', 'ukazatel');
      if (!kod || !nazev) return null;

      const body = new Map<string, BodRadyCsu>();
      for (const b of objekty(z, 'body', 'hodnoty')) {
        const obdobi = txt(b, 'obdobi', 'období', 'rok');
        if (!obdobi) continue;
        const hodnota = typeof b.hodnota === 'number' && Number.isFinite(b.hodnota) ? b.hodnota : null;
        body.set(obdobi, { obdobi, hodnota, duverne: b.duverne === true });
      }

      return {
        kod,
        nazev,
        jednotka: txt(z, 'jednotka'),
        cleneni: cleneniZ(z),
        perioda: periodaZ(txt(z, 'perioda')),
        sada: txt(z, 'sada') ?? 'ostatni',
        od: txt(z, 'od'),
        do: txt(z, 'do'),
        body,
        chybejiciObdobi: Array.isArray(z.chybejici_obdobi)
          ? z.chybejici_obdobi.filter((x): x is string => typeof x === 'string')
          : [],
      };
    })
    .filter((r): r is RadaCsu => r !== null);

  const sady: SadaCsu[] = objekty(prehled, 'sady', 'sets')
    .map((z) => {
      const kod = txt(z, 'kod');
      if (!kod) return null;
      return {
        kod,
        nazev: txt(z, 'nazev') ?? kod,
        stav: txt(z, 'stav'),
        perioda: periodaZ(txt(z, 'perioda')),
        od: txt(z, 'od'),
        do: txt(z, 'do'),
        zaznamu: cis(z, 'zaznamu'),
        ukazatelu: cis(z, 'ukazatelu'),
      };
    })
    .filter((s): s is SadaCsu => s !== null);

  const stav = zRad.stav === 'ok' ? zPrehledu.stav : zRad.stav;
  return {
    stav: rady.length > 0 ? zRad.stav : stav,
    zdroj: zRad.zdroj,
    poznamka: zRad.poznamka ?? zPrehledu.poznamka,
    data: {
      rady,
      sady,
      zdroj: txt(prehled, 'zdroj') ?? txt(koren, 'zdroj'),
      licence: txt(prehled, 'licence'),
      poznamka: txt(koren, 'poznamka'),
      obec: jeObjekt(prehled.obec) ? txt(prehled.obec, 'nazev') : null,
    },
  };
}

/* ─────────────────────────  Práce s obdobími  ──────────────────────── */

/**
 * Souvislá řada období od–do. Bez tohohle by se osa scvrkla na body, ve
 * kterých zdroj hodnotu má, a chybějící roky by z grafu zmizely místo aby
 * v něm zůstaly jako mezera.
 */
export function souvisleObdobi(perioda: Perioda, od: string, doo: string): string[] {
  if (perioda === 'mesic') {
    const rozloz = (s: string): [number, number] | null => {
      const m = /^(\d{4})-(\d{2})/.exec(s);
      return m ? [Number(m[1]), Number(m[2])] : null;
    };
    const a = rozloz(od);
    const b = rozloz(doo);
    if (!a || !b) return [];
    const ven: string[] = [];
    let [r, me] = a;
    for (let i = 0; i < 2400 && (r < b[0] || (r === b[0] && me <= b[1])); i++) {
      ven.push(`${r}-${String(me).padStart(2, '0')}`);
      me++;
      if (me > 12) {
        me = 1;
        r++;
      }
    }
    return ven;
  }

  const rokZ = (s: string): number | null => {
    const m = /^(\d{4})/.exec(s);
    return m ? Number(m[1]) : null;
  };
  const a = rokZ(od);
  const b = rokZ(doo);
  if (a === null || b === null) return [];
  const ven: string[] = [];
  for (let r = a; r <= b && ven.length < 400; r++) ven.push(String(r));
  return ven;
}

/** Popisek období pro osu: „2024", „3/2015". */
export function popisekObdobi(obdobi: string, perioda: Perioda): string {
  if (perioda === 'mesic') {
    const m = /^(\d{4})-(\d{2})/.exec(obdobi);
    if (m) return `${Number(m[2])}/${m[1]}`;
  }
  const r = /^(\d{4})/.exec(obdobi);
  return r ? r[1] : obdobi;
}

/**
 * Hodnota pro dané období. Vrací i to, PROČ chybí — „ČSÚ ji tají" a „v datech
 * není" jsou dva různé stavy a ani jeden z nich není nula.
 */
export function hodnotaVObdobi(
  r: RadaCsu,
  obdobi: string,
  perioda: Perioda,
): { hodnota: number | null; duverne: boolean; nalezeno: boolean } {
  const primo = r.body.get(obdobi);
  if (primo) return { hodnota: primo.hodnota, duverne: primo.duverne, nalezeno: true };
  // U sčítání se roky mezi řadami píšou s celým datem („2011-03-26").
  if (perioda !== 'mesic') {
    for (const [klic, b] of r.body) {
      if (klic.startsWith(obdobi)) return { hodnota: b.hodnota, duverne: b.duverne, nalezeno: true };
    }
  }
  return { hodnota: null, duverne: false, nalezeno: false };
}

/** Formátovač podle jednotky. Procenta s desetinou, počty celé. */
export function formatujHodnotu(jednotka: string | null): (v: number) => string {
  const j = (jednotka ?? '').trim();
  if (j === '%' || /procent/i.test(j)) return (v) => `${v.toFixed(1).replace('.', ',')} %`;
  if (/kč|czk/i.test(j)) return (v) => `${cislo(Math.round(v))} Kč`;
  return (v) => (Number.isInteger(v) ? cislo(v) : cislo(Math.round(v * 10) / 10));
}

/** Popis členění pro legendu: „0 až 14", „ženy", „celkem". */
export function popisCleneni(r: RadaCsu): string {
  if (r.cleneni.length === 0) return 'celkem';
  return r.cleneni.map((c) => c.hodnota).join(', ');
}

/**
 * Ukazatele uvnitř jedné sady. Řady téhož názvu a jednotky patří do jednoho
 * grafu — je to totéž měřeno po členěních, takže osa Y platí pro všechny.
 */
export interface Ukazatel {
  klic: string;
  nazev: string;
  jednotka: string | null;
  perioda: Perioda;
  rady: RadaCsu[];
}

export function ukazateleSady(rady: RadaCsu[], sada: string): Ukazatel[] {
  const podle = new Map<string, Ukazatel>();
  for (const r of rady) {
    if (r.sada !== sada) continue;
    const klic = `${r.nazev}|${r.jednotka ?? ''}|${r.perioda}`;
    const stav = podle.get(klic) ?? {
      klic: klic.replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-+|-+$/g, '').toLowerCase() || sada,
      nazev: r.nazev,
      jednotka: r.jednotka,
      perioda: r.perioda,
      rady: [],
    };
    stav.rady.push(r);
    podle.set(klic, stav);
  }
  // Nejdřív ukazatele s víc členěními — nesou víc informace.
  return [...podle.values()].sort((a, b) => b.rady.length - a.rady.length || a.nazev.localeCompare(b.nazev, 'cs-CZ'));
}

/** Rozsah období napříč řadami ukazatele. */
export function rozsahUkazatele(u: Ukazatel): { od: string; do: string } | null {
  const od = u.rady.map((r) => r.od).filter((x): x is string => Boolean(x)).sort();
  const doo = u.rady.map((r) => r.do).filter((x): x is string => Boolean(x)).sort();
  if (od.length === 0 || doo.length === 0) return null;
  return { od: od[0], do: doo[doo.length - 1] };
}
