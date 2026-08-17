/**
 * Odolné načítání dat z `data/`.
 *
 * Zásada celého projektu: rozlišovat „nic se nestalo" od „nepodařilo se načíst".
 * Proto každý loader vrací `Nacteno<T>` se stavem, ne jen holá data.
 *
 *   ok    — soubor existuje a dal se přečíst (data mohou být prázdná = nic se nestalo)
 *   chybi — soubor/adresář zatím neexistuje (jiný modul ho ještě nenaplnil)
 *   chyba — soubor existuje, ale nešel přečíst nebo rozparsovat (to je porucha)
 *
 * Build nikdy nepadá kvůli chybějícím datům.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export type Stav = 'ok' | 'chybi' | 'chyba';

export interface Nacteno<T> {
  stav: Stav;
  data: T;
  /** Cesta relativní ke kořeni dat — pro hlášku „čeká se na `penize/agregace/…`". */
  zdroj: string;
  /** Lidský popis problému. `null`, když je stav `ok`. */
  poznamka: string | null;
}

const KOREN_WEBU = fileURLToPath(new URL('../../', import.meta.url));
const KOREN_REPO = path.resolve(KOREN_WEBU, '..');

/**
 * Kde build hledá data. Primárně skutečná data v `data/` v kořeni repozitáře.
 * `MARIANKY_DATA` přebije cestu, `MARIANKY_FIXTURES=1` přepne na `web/fixtures/`
 * (jen pro vývoj webu, když ostatní moduly ještě neběžely).
 */
export const KOREN_DAT: string = process.env.MARIANKY_DATA
  ? path.resolve(process.env.MARIANKY_DATA)
  : process.env.MARIANKY_FIXTURES === '1'
    ? path.join(KOREN_WEBU, 'fixtures')
    : path.join(KOREN_REPO, 'data');

export const POUZIVA_FIXTURES: boolean =
  KOREN_DAT === path.join(KOREN_WEBU, 'fixtures');

export const KOREN_CONFIG: string = path.join(KOREN_REPO, 'config');

function ok<T>(data: T, zdroj: string): Nacteno<T> {
  return { stav: 'ok', data, zdroj, poznamka: null };
}
function chybi<T>(data: T, zdroj: string): Nacteno<T> {
  return { stav: 'chybi', data, zdroj, poznamka: `Data zatím nejsou — soubor ${zdroj} ještě nevznikl.` };
}
function chyba<T>(data: T, zdroj: string, e: unknown): Nacteno<T> {
  const zprava = e instanceof Error ? e.message : String(e);
  return { stav: 'chyba', data, zdroj, poznamka: `Data se nepodařilo načíst: ${zprava}` };
}

/** Načte jeden JSON soubor. Nikdy nevyhodí výjimku. */
export function nactiJson<T>(relCesta: string, vychozi: T): Nacteno<T> {
  const plna = path.join(KOREN_DAT, relCesta);
  let syrove: string;
  try {
    if (!fs.existsSync(plna)) return chybi(vychozi, relCesta);
    syrove = fs.readFileSync(plna, 'utf8');
  } catch (e) {
    return chyba(vychozi, relCesta, e);
  }
  try {
    const parsed = JSON.parse(syrove) as T;
    return ok(parsed, relCesta);
  } catch (e) {
    return chyba(vychozi, relCesta, e);
  }
}

/** Načte JSON z `config/` v kořeni repozitáře (číselníky, ne data). */
export function nactiConfig<T>(soubor: string, vychozi: T): Nacteno<T> {
  const plna = path.join(KOREN_CONFIG, soubor);
  try {
    if (!fs.existsSync(plna)) return chybi(vychozi, `config/${soubor}`);
    return ok(JSON.parse(fs.readFileSync(plna, 'utf8')) as T, `config/${soubor}`);
  } catch (e) {
    return chyba(vychozi, `config/${soubor}`, e);
  }
}

/** Rekurzivně posbírá cesty k `*.json` pod daným adresářem (relativně ke KOREN_DAT). */
function sesbirejJson(absAdresar: string, ven: string[]): void {
  let polozky: fs.Dirent[];
  try {
    polozky = fs.readdirSync(absAdresar, { withFileTypes: true });
  } catch {
    return;
  }
  for (const p of polozky) {
    const plna = path.join(absAdresar, p.name);
    if (p.isDirectory()) sesbirejJson(plna, ven);
    else if (p.isFile() && p.name.endsWith('.json')) ven.push(plna);
  }
}

/**
 * Načte všechny `*.json` pod adresářem. Jeden vadný soubor neshodí zbytek —
 * skončí v `chybneSoubory` a stav se překlopí na `chyba`, aby se o tom vědělo.
 */
export function nactiAdresar<T>(relAdresar: string): Nacteno<T[]> & { chybneSoubory: string[] } {
  const absAdresar = path.join(KOREN_DAT, relAdresar);
  if (!fs.existsSync(absAdresar)) {
    return { ...chybi<T[]>([], relAdresar), chybneSoubory: [] };
  }
  const soubory: string[] = [];
  sesbirejJson(absAdresar, soubory);
  soubory.sort();

  const data: T[] = [];
  const chybne: string[] = [];
  for (const s of soubory) {
    try {
      data.push(JSON.parse(fs.readFileSync(s, 'utf8')) as T);
    } catch {
      chybne.push(path.relative(KOREN_DAT, s));
    }
  }
  if (chybne.length > 0) {
    return {
      stav: 'chyba',
      data,
      zdroj: relAdresar,
      poznamka: `Nepodařilo se přečíst ${chybne.length} souborů v ${relAdresar} (${chybne.slice(0, 3).join(', ')}${chybne.length > 3 ? ', …' : ''}).`,
      chybneSoubory: chybne,
    };
  }
  return { ...ok(data, relAdresar), chybneSoubory: [] };
}

/** Spojí stavy více zdrojů do jednoho — nejhorší vyhrává (chyba > chybi > ok). */
export function spojStavy(...zdroje: Nacteno<unknown>[]): { stav: Stav; poznamky: string[] } {
  const poznamky = zdroje.map((z) => z.poznamka).filter((p): p is string => Boolean(p));
  if (zdroje.some((z) => z.stav === 'chyba')) return { stav: 'chyba', poznamky };
  if (zdroje.some((z) => z.stav === 'chybi')) return { stav: 'chybi', poznamky };
  return { stav: 'ok', poznamky };
}

/* ─────────────────────────  Typy podle docs/PLAN.md  ───────────────────────── */

export interface Protistrana {
  ico: string;
  nazev: string;
  smer: 'vydaj' | 'prijem';
  celkem_czk: number;
  prvni_rok: number;
  posledni_rok: number;
  aktivni: boolean;
  po_letech: Record<string, number>;
  smluv: number;
  subjekty?: string[];
  kategorie?: string;
}

export interface AgregaceProtistran {
  generovano?: string;
  protistrany: Protistrana[];
}

/** `souhrn.json` — formát není v PLAN.md pevně daný, čteme ho tolerantně. */
export interface Souhrn {
  generovano?: string;
  celkem_czk?: number;
  smluv?: number;
  protistran?: number;
  kindex?: string | number | null;
  kindex_stupen?: string | null;
  kindex_rok?: number | null;
  kindex_url?: string | null;
  vadnych_smluv?: number | null;
  [k: string]: unknown;
}

export interface BodUsneseni {
  cislo: string;
  nazev: string;
  text?: string;
  tagy?: string[];
  castka_czk?: number | null;
  hlasovani_id?: string | null;
}

export interface Usneseni {
  organ: 'rada' | 'zastupitelstvo' | string;
  cj: number;
  datum: string;
  obdobi?: string;
  url?: string;
  body: BodUsneseni[];
}

export interface JmenovityHlas {
  osoba_id: string;
  jmeno: string;
  strana?: string;
  hlas: 'pro' | 'proti' | 'zdrzel' | 'nehlasoval' | 'nepritomen' | string;
}

export interface Hlas {
  id: string;
  bod: string;
  nazev: string;
  tagy?: string[];
  vysledek: string;
  pro: number;
  proti: number;
  zdrzel: number;
  nehlasoval?: number;
  jmenovite?: JmenovityHlas[];
}

export interface HlasovaniSoubor {
  organ: string;
  cj: number;
  datum: string;
  hlasovani: Hlas[];
}

export interface Osobnost {
  id: string;
  jmeno: string;
  role?: string[];
  kategorie?: string;
  strana?: string;
  funkce?: { nazev: string; od?: string | null; do?: string | null }[];
  popis?: string;
  zdroje?: string[];
  zijici?: boolean;
}

export interface CisloZpravodaje {
  id: string;
  rok: number;
  mesic: number;
  mesic_do?: number | null;
  nazev: string;
  url?: string;
  soubor?: string;
  stran?: number | null;
  znaku?: number | null;
  ocr?: boolean;
}

export interface Clanek {
  id: string;
  cislo: string;
  strana?: number;
  rubrika?: string;
  nadpis: string;
  perex?: string;
  text?: string;
  osoby?: string[];
  tagy?: string[];
  pdf_odkaz?: string;
}

export interface Smlouva {
  id: string;
  datum: string;
  castka_czk: number | null;
  protistrana_ico?: string;
  protistrana?: string;
  predmet?: string;
  kategorie?: string;
  smer: 'vydaj' | 'prijem' | string;
  vada?: boolean;
  url?: string;
}

export interface SmlouvySubjektu {
  ico: string;
  nazev: string;
  smlouvy: Smlouva[];
}

/** Týdenní vydání — formát PLAN.md nedefinuje, čteme tolerantně. */
export interface Vydani {
  id: string;
  cislo?: number;
  nazev?: string;
  datum?: string;
  obdobi_od?: string;
  obdobi_do?: string;
  obdobi?: string;
  perex?: string;
  sekce?: { nadpis: string; text?: string; poznamka?: string; polozky?: unknown[] }[];
  [k: string]: unknown;
}

export interface Tag {
  id: string;
  nazev: string;
  skupina: string;
  popis?: string;
}
export interface Ciselnik {
  tagy: Tag[];
  skupiny: { id: string; nazev: string }[];
}

/* ─────────────────────────────  Konkrétní loadery  ────────────────────────── */

export function nactiProtistrany(): Nacteno<AgregaceProtistran> {
  const v = nactiJson<AgregaceProtistran>('penize/agregace/protistrany.json', { protistrany: [] });
  // Obrana proti neúplnému souboru: chybějící pole neshodí build.
  if (v.stav === 'ok' && !Array.isArray(v.data?.protistrany)) {
    return {
      stav: 'chyba',
      data: { protistrany: [] },
      zdroj: v.zdroj,
      poznamka: 'Soubor protistrany.json nemá očekávané pole `protistrany`.',
    };
  }
  if (v.stav === 'ok') {
    v.data.protistrany = v.data.protistrany.filter((p) => p && typeof p.ico === 'string');
  }
  return v;
}

export function nactiSouhrn(): Nacteno<Souhrn> {
  return nactiJson<Souhrn>('penize/agregace/souhrn.json', {});
}

export function nactiSmlouvy(): Nacteno<SmlouvySubjektu[]> {
  return nactiAdresar<SmlouvySubjektu>('penize/smlouvy');
}

export function nactiUsneseni(): Nacteno<Usneseni[]> {
  const v = nactiAdresar<Usneseni>('usneseni');
  v.data = v.data.filter((u) => u && Array.isArray(u.body));
  v.data.sort((a, b) => String(b.datum ?? '').localeCompare(String(a.datum ?? '')));
  return v;
}

export function nactiHlasovani(): Nacteno<HlasovaniSoubor[]> {
  const v = nactiAdresar<HlasovaniSoubor>('hlasovani');
  v.data = v.data.filter((h) => h && Array.isArray(h.hlasovani));
  v.data.sort((a, b) => String(b.datum ?? '').localeCompare(String(a.datum ?? '')));
  return v;
}

export function nactiLidi(): Nacteno<Osobnost[]> {
  const v = nactiJson<Osobnost[]>('lide/osobnosti.json', []);
  if (v.stav === 'ok' && !Array.isArray(v.data)) {
    return { stav: 'chyba', data: [], zdroj: v.zdroj, poznamka: 'osobnosti.json není pole.' };
  }
  return v;
}

export function nactiCisla(): Nacteno<CisloZpravodaje[]> {
  const v = nactiJson<CisloZpravodaje[]>('zpravodaj/cisla.json', []);
  if (v.stav === 'ok' && !Array.isArray(v.data)) {
    return { stav: 'chyba', data: [], zdroj: v.zdroj, poznamka: 'cisla.json není pole.' };
  }
  if (v.stav === 'ok') {
    v.data = [...v.data].sort((a, b) => String(b.id ?? '').localeCompare(String(a.id ?? '')));
  }
  return v;
}

export function nactiClanky(): Nacteno<Clanek[]> {
  const v = nactiAdresar<Clanek>('zpravodaj/clanky');
  v.data = v.data.filter((c) => c && typeof c.nadpis === 'string' && c.rubrika !== 'Inzerce');
  return v;
}

/**
 * Týdenní vydání. ZADANI.md je umisťuje do `obsah/vydani/`, PLAN.md formát
 * nedefinuje a žádný modul je zatím negeneruje — hledáme na obou místech.
 */
export function nactiVydani(): Nacteno<Vydani[]> {
  const a = nactiAdresar<Vydani>('vydani');
  if (a.stav === 'ok' && a.data.length > 0) return serad(a);
  const b = nactiAdresar<Vydani>('../obsah/vydani');
  if (b.stav === 'ok' && b.data.length > 0) return serad(b);
  return serad(a.stav === 'chybi' && b.stav !== 'chybi' ? b : a);

  function serad(v: Nacteno<Vydani[]>): Nacteno<Vydani[]> {
    v.data = v.data
      .filter((x) => x && typeof x.id === 'string')
      .sort((x, y) => String(y.datum ?? y.id).localeCompare(String(x.datum ?? x.id)));
    return v;
  }
}

export function nactiCiselnikTagu(): Nacteno<Ciselnik> {
  return nactiConfig<Ciselnik>('tagy.json', { tagy: [], skupiny: [] });
}

export function nactiSubjekty(): Nacteno<{ mesto?: { ico: string; nazev: string }; subjekty: { ico: string | null; nazev: string }[] }> {
  return nactiConfig('subjekty.json', { subjekty: [] });
}
