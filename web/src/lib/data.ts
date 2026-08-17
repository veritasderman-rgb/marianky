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

/*
 * Když kořen dat vůbec neexistuje, tichý build by vyrobil web, na kterém je
 * všude „data zatím nejsou" — a vypadalo by to jako stav světa, ne jako špatná
 * konfigurace. Proto o tom build hlasitě řekne. Nepadá: částečná data jsou
 * legitimní stav, chybějící adresář dat obvykle znamená špatné nastavení
 * Root Directory na Vercelu.
 */
if (!fs.existsSync(KOREN_DAT)) {
  console.warn(
    `\n[mariánky] POZOR: adresář s daty neexistuje: ${KOREN_DAT}\n` +
      '           Web se sestaví, ale všechny sekce budou hlásit „data zatím nejsou".\n' +
      '           Zkontrolujte, že build vidí data/ v kořeni repozitáře, nebo nastavte MARIANKY_DATA.\n',
  );
}

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

/** Rekurzivně posbírá cesty k souborům s danou příponou (relativně ke KOREN_DAT). */
function sesbirejSoubory(absAdresar: string, pripony: string[], ven: string[]): void {
  let polozky: fs.Dirent[];
  try {
    polozky = fs.readdirSync(absAdresar, { withFileTypes: true });
  } catch {
    return;
  }
  for (const p of polozky) {
    const plna = path.join(absAdresar, p.name);
    if (p.isDirectory()) sesbirejSoubory(plna, pripony, ven);
    else if (p.isFile() && pripony.some((x) => p.name.endsWith(x))) ven.push(plna);
  }
}

/** Jeden soubor z adresáře i s cestou — mapy potřebují vědět, z čeho vrstva vznikla. */
export interface SouborDat<T> {
  /** Cesta relativní ke KOREN_DAT, např. `opendata/geo/okrsky.geojson`. */
  cesta: string;
  /** Jméno souboru bez přípony — výchozí název vrstvy, když ho data neuvádějí. */
  jmeno: string;
  data: T;
}

/**
 * Načte všechny soubory s danou příponou pod adresářem, i s cestou ke každému.
 * Jeden vadný soubor neshodí zbytek — skončí v `chybneSoubory` a stav se
 * překlopí na `chyba`, aby se o tom vědělo.
 *
 * GeoJSON se ukládá s příponou `.json` i `.geojson`; proto je seznam přípon
 * parametr a ne konstanta.
 */
export function nactiAdresarSoubory<T>(
  relAdresar: string,
  pripony: string[] = ['.json'],
): Nacteno<SouborDat<T>[]> & { chybneSoubory: string[] } {
  const absAdresar = path.join(KOREN_DAT, relAdresar);
  if (!fs.existsSync(absAdresar)) {
    return { ...chybi<SouborDat<T>[]>([], relAdresar), chybneSoubory: [] };
  }
  const soubory: string[] = [];
  sesbirejSoubory(absAdresar, pripony, soubory);
  soubory.sort();

  const data: SouborDat<T>[] = [];
  const chybne: string[] = [];
  for (const s of soubory) {
    const rel = path.relative(KOREN_DAT, s).split(path.sep).join('/');
    try {
      data.push({
        cesta: rel,
        jmeno: path.basename(s).replace(/\.[^.]+$/, ''),
        data: JSON.parse(fs.readFileSync(s, 'utf8')) as T,
      });
    } catch {
      chybne.push(rel);
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

/**
 * Načte všechny `*.json` pod adresářem. Jeden vadný soubor neshodí zbytek —
 * skončí v `chybneSoubory` a stav se překlopí na `chyba`, aby se o tom vědělo.
 */
export function nactiAdresar<T>(relAdresar: string): Nacteno<T[]> & { chybneSoubory: string[] } {
  const v = nactiAdresarSoubory<T>(relAdresar, ['.json']);
  return { ...v, data: v.data.map((s) => s.data) };
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
  /** `null` u protistran, které Hlídač vede bez IČO (slučují se podle názvu). */
  ico: string | null;
  /**
   * Stabilní klíč do URL a do registru barev. IČO tam, kde je; jinak slug
   * z názvu. Doplňuje ho `nactiProtistrany()` — v datech není.
   */
  klic: string;
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

/**
 * `souhrn.json` — docs/PLAN.md tenhle soubor nepopisuje, jen ho zmiňuje.
 * Čteme ho proto tolerantně a zvlášť ošetřujeme obě podoby, na které jsme
 * narazili: vnořenou (`celkem.vydaj_czk`, `kindex[]`) i plochou.
 * Cokoliv, co nesedí, se prostě neukáže — nic se nedohaduje.
 */
export interface SouhrnCelkem {
  smluv?: number;
  vydaj_czk?: number;
  prijem_czk?: number;
  bez_ceny?: number;
  podil_bez_ceny?: number;
  vadnych?: number;
  dodavatelu?: number;
  odberatelu?: number;
  aktivnich_dodavatelu?: number;
}

export interface ZaznamKindexu {
  rok?: number;
  stupen?: string;
  popis?: string;
}

export interface Souhrn {
  generovano?: string;
  zdroj?: string;
  rozsah_let?: { od?: number; do?: number };
  celkem?: SouhrnCelkem;
  kindex?: ZaznamKindexu[];
  po_letech?: Record<string, { smluv?: number; vydaj_czk?: number; prijem_czk?: number; vadnych?: number }>;
  /* plochá varianta */
  celkem_czk?: number;
  kindex_stupen?: string | null;
  kindex_rok?: number | null;
  [k: string]: unknown;
}

/** Nejnovější záznam K-indexu. `null`, když v souhrnu žádný není. */
export function posledniKindex(s: Souhrn): ZaznamKindexu | null {
  if (Array.isArray(s?.kindex) && s.kindex.length > 0) {
    return [...s.kindex].sort((a, b) => (b.rok ?? 0) - (a.rok ?? 0))[0];
  }
  if (s?.kindex_stupen) return { stupen: String(s.kindex_stupen), rok: s.kindex_rok ?? undefined };
  return null;
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
  /**
   * Omluvená neúčast. Zdroj ji zapisuje jako `hlas: "nepritomen"` s tímhle
   * příznakem — a jen u novějších zápisů. Chybějící příznak proto NEZNAMENÁ,
   * že se člověk neomluvil.
   */
  omluven?: boolean;
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

/**
 * Sekce týdenního vydání. `stav` rozlišuje čtyři různé věci, které se nesmí
 * slít dohromady: sebralo se něco (`ok`), sebralo se a nic tam nebylo
 * (`prazdno`), zdroj se nepodařilo přečíst (`chyba` / `chybi`) a zdroj se sice
 * načetl, ale je zjevně starý (`zastarale`). Neznámý stav se nechává být.
 */
export interface SekceVydani {
  id?: string;
  nadpis: string;
  popis?: string;
  text?: string;
  poznamka?: string;
  stav?: string;
  pocet?: number;
  /** Datum posledního záznamu ve zdroji — u prázdné sekce říká, odkdy je ticho. */
  nejnovejsi_ve_zdroji?: string | null;
  polozky?: unknown[];
  [k: string]: unknown;
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
  souhrn?: {
    sekci_ok?: number;
    sekci_prazdnych?: number;
    sekci_chybejicich?: number;
    polozek?: number;
  };
  sekce?: SekceVydani[];
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

/** Slug pro URL — bez diakritiky, jen písmena, číslice a pomlčky. */
export function slug(s: string): string {
  return s
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60);
}

/**
 * Klíč protistrany. Musí se počítat na jednom místě, aby agregace
 * (`protistrany.json`) a jednotlivé smlouvy (`smlouvy/*.json`) spadly do
 * stejného kbelíku i tam, kde registr IČO neuvádí.
 */
export function klicProtistrany(ico: string | null | undefined, nazev: string | null | undefined): string {
  if (typeof ico === 'string' && ico) return ico;
  return `n-${slug(nazev ?? '')}`;
}

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
    // Protistrany bez IČO (Hlídač je slučuje podle názvu) se NEZAHAZUJÍ —
    // jsou mezi nimi firmy s desítkami milionů a bez nich by „Ostatní"
    // i celkové objemy tvrdily míň, než ve skutečnosti odteklo.
    const videne = new Set<string>();
    v.data.protistrany = v.data.protistrany
      .filter((p) => p && typeof p.nazev === 'string' && p.nazev.length > 0)
      .map((p) => {
        const zaklad = klicProtistrany(p.ico, p.nazev);
        let klic = zaklad;
        for (let i = 2; videne.has(klic); i++) klic = `${zaklad}-${i}`;
        videne.add(klic);
        return { ...p, ico: typeof p.ico === 'string' && p.ico ? p.ico : null, klic };
      });
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
