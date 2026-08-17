/**
 * Časové řady o městě — `data/opendata/csu/`.
 *
 * Obyvatelstvo, nezaměstnanost, cestovní ruch. Formát zatím zapsaný není,
 * čte se tolerantně: soubor může být jedna řada, pole řad, slovník řad i
 * prostá mapa `rok → hodnota`.
 *
 * Jednotky se nemíchají. Každá řada má svůj graf s jednou osou Y; společné
 * srovnání se dělá indexem k základnímu roku (web/DESIGN.md §2 bod 1).
 */
import { nactiAdresarSoubory, slug, type Nacteno } from './data';
import { cislo } from './format';
import { jeObjekt, radaPoLetech, txt, type Zaznam } from './tolerantni';

export interface RadaCsu {
  klic: string;
  nazev: string;
  /** Např. „osob", „%", „lůžek". `null`, když ji zdroj neuvádí. */
  jednotka: string | null;
  popis: string | null;
  zdroj: string | null;
  skupina: string;
  /** Rok → hodnota. Chybějící rok se NEDOPLŇUJE nulou. */
  hodnoty: Map<number, number>;
  cesta: string;
}

const KLICE_HODNOT = ['hodnoty', 'rada', 'řada', 'data', 'values', 'series', 'po_letech', 'roky'];
const KLICE_HODNOTY_POLOZKY = ['hodnota', 'value', 'pocet', 'počet', 'castka_czk', 'castka', 'mira', 'míra'];

function skupinaZ(cesta: string, nazev: string): string {
  const s = `${cesta} ${nazev}`.toLowerCase();
  if (s.includes('obyvatel') || s.includes('populac') || s.includes('narozen') || s.includes('zemrel') || s.includes('stehov')) {
    return 'Obyvatelstvo';
  }
  if (s.includes('nezamest') || s.includes('nezaměst') || s.includes('prace') || s.includes('práce') || s.includes('uchazec')) {
    return 'Práce a nezaměstnanost';
  }
  if (s.includes('turis') || s.includes('cestovn') || s.includes('host') || s.includes('lazn') || s.includes('lázn') || s.includes('ubytov') || s.includes('prenocov')) {
    return 'Cestovní ruch';
  }
  return 'Další ukazatele';
}

function radaZe(z: Zaznam, cesta: string, jmeno: string, klicZeSlovniku: string | null): RadaCsu | null {
  const surove = KLICE_HODNOT.map((k) => z[k]).find((v) => typeof v !== 'undefined');
  const hodnoty = radaPoLetech(surove ?? z, KLICE_HODNOTY_POLOZKY);
  if (hodnoty.size === 0) return null;

  const nazev =
    txt(z, 'nazev', 'název', 'ukazatel', 'title', 'name', 'popis_ukazatele') ??
    (klicZeSlovniku ? hezky(klicZeSlovniku) : hezky(jmeno));

  return {
    klic: slug(`${jmeno}-${klicZeSlovniku ?? nazev}`) || slug(nazev) || jmeno,
    nazev,
    jednotka: txt(z, 'jednotka', 'unit', 'mj', 'merna_jednotka', 'měrná_jednotka'),
    popis: txt(z, 'popis', 'description', 'poznamka', 'metodika'),
    zdroj: txt(z, 'zdroj', 'source', 'url', 'zdroj_dat'),
    skupina: txt(z, 'skupina', 'oblast', 'kategorie') ?? skupinaZ(cesta, nazev),
    hodnoty,
    cesta,
  };
}

function hezky(s: string): string {
  const t = s.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : 'Řada';
}

/** Všechny časové řady z `opendata/csu/`. */
export function nactiCsu(): Nacteno<RadaCsu[]> {
  const v = nactiAdresarSoubory<unknown>('opendata/csu', ['.json']);
  const ven: RadaCsu[] = [];
  const videne = new Set<string>();

  const pridej = (r: RadaCsu | null) => {
    if (!r) return;
    let klic = r.klic;
    for (let i = 2; videne.has(klic); i++) klic = `${r.klic}-${i}`;
    videne.add(klic);
    ven.push({ ...r, klic });
  };

  for (const s of v.data) {
    const obsah = s.data;

    if (Array.isArray(obsah)) {
      const objekty = obsah.filter(jeObjekt);
      // Buď pole řad, nebo pole dvojic rok/hodnota — pozná se podle toho,
      // jestli položky nesou vlastní hodnoty.
      const jsouRady = objekty.some((o) => KLICE_HODNOT.some((k) => typeof o[k] !== 'undefined'));
      if (jsouRady) objekty.forEach((o) => pridej(radaZe(o, s.cesta, s.jmeno, null)));
      else pridej(radaZe({ hodnoty: objekty }, s.cesta, s.jmeno, null));
      continue;
    }

    if (!jeObjekt(obsah)) continue;

    const vnorene = KLICE_HODNOT.every((k) => typeof obsah[k] === 'undefined');
    const seznamRad = ['rady', 'řady', 'serie', 'série', 'ukazatele', 'series'].map((k) => obsah[k]).find(Array.isArray);

    if (Array.isArray(seznamRad)) {
      seznamRad.filter(jeObjekt).forEach((o) => pridej(radaZe(o, s.cesta, s.jmeno, null)));
      continue;
    }

    const primo = radaZe(obsah, s.cesta, s.jmeno, null);
    if (primo) {
      pridej(primo);
      continue;
    }

    // Slovník řad: `{ "obyvatelstvo": {...}, "nezamestnanost": {...} }`
    if (vnorene) {
      for (const [k, hodnota] of Object.entries(obsah)) {
        if (jeObjekt(hodnota)) pridej(radaZe(hodnota, s.cesta, s.jmeno, k));
        else if (Array.isArray(hodnota)) pridej(radaZe({ hodnoty: hodnota }, s.cesta, s.jmeno, k));
      }
    }
  }

  ven.sort((a, b) => a.skupina.localeCompare(b.skupina, 'cs-CZ') || a.nazev.localeCompare(b.nazev, 'cs-CZ'));
  return { stav: v.stav, zdroj: v.zdroj, poznamka: v.poznamka, data: ven };
}

/** Formátovač podle jednotky. Procenta se píšou s desetinou, počty celé. */
export function formatujHodnotu(jednotka: string | null): (v: number) => string {
  const j = (jednotka ?? '').trim();
  if (j === '%' || /procent/i.test(j)) {
    return (v) => `${v.toFixed(1).replace('.', ',')} %`;
  }
  if (/kč|czk/i.test(j)) {
    return (v) => `${cislo(Math.round(v))} Kč`;
  }
  return (v) => (Number.isInteger(v) ? cislo(v) : cislo(Math.round(v * 10) / 10));
}

/** Rozsah let, ve kterém řada má aspoň jeden údaj. */
export function rozsahRady(r: RadaCsu): { od: number; do: number } | null {
  const roky = [...r.hodnoty.keys()];
  if (roky.length === 0) return null;
  return { od: Math.min(...roky), do: Math.max(...roky) };
}
