/**
 * Stav sekcí pro tabulku „Stav sběru dat" na úvodní stránce.
 *
 * PROČ TENHLE SOUBOR EXISTUJE
 * Tabulka měla šest ručně vypsaných řádků z doby, kdy web měl šest sekcí.
 * Pak přibylo šestnáct dalších — rozpočet, komise, žádosti o informace,
 * slibník, vysvědčení, účet období… — a tabulka o nich mlčela. Čtenář
 * viděl „připraveno" u zpravodaje a nic o tom, že vysvědčení se minulý
 * týden nepřepočítalo. Ručně psaný seznam se rozejde s obsahem vždycky.
 *
 * Tenhle se skládá ze čtyř věcí, které už existují:
 *   – rejstřík sekcí (`sekce.ts`) — CO web má,
 *   – znaky sekcí (`data/znaky/sekce.json`) — KOLIK toho v sekci je a z jakého
 *     souboru se to bere,
 *   – záznam posledního běhu (`data/logy/<den>/beh.json`) — JAK DOPADL krok,
 *     který sekci plní,
 *   – mapa zdrojů (`config/diagramy.json`) — ODKUD data pocházejí.
 *
 * TŘI RŮZNÉ VĚCI, KTERÉ SE NESMÍ SLÍT
 *   1. jestli data NA DISKU jsou (soubor existuje a dá se přečíst),
 *   2. k jakému DATU jsou (kdy je modul naposledy vygeneroval),
 *   3. jak dopadl KROK BĚHU, který je plní (v pořádku / selhal / neběžel).
 * Selhaný krok nad staršími daty je běžný a legitimní stav: web ukazuje
 * minulý výsledek a tabulka to řekne. Kdyby se to slilo do jedné tečky,
 * „selhalo, ale máme týden staré" by vypadalo jako „v pořádku".
 */
import fs from 'node:fs';
import path from 'node:path';
import { KOREN_DAT, nactiConfig, nactiJson, type Nacteno, type Stav } from './data';
import { datumKratke } from './format';
import { SEKCE_HLEDAT, SEKCE_UVOD, SKUPINY, type Sekce } from './sekce';
import { nactiZnaky, type Znak } from './znaky';

/* ─────────────────────────────  Běh  ────────────────────────────────── */

export interface KrokBehu {
  modul: string;
  popis: string;
  povinny: boolean;
  /** `ok`, `selhal`, `chybi_modul`, `chybi_main` — tak to zapisuje run_tyden.py. */
  stav: string;
  chyba?: string;
}

export interface RezimBehu {
  /** `run_tyden.py --bez-sberu`: jen přepočet, sběrače se nespouštěly. */
  bez_sberu?: boolean;
  /** `run_tyden.py --jen …`: cílený běh jen na vyjmenované moduly. */
  jen?: string[];
}

export interface Beh {
  datum: string;
  obdobi_od?: string;
  obdobi_do?: string;
  trvani_s?: number;
  uspech?: boolean;
  /** Zapisuje run_tyden.py od 9/2026; starší záznamy ho nemají a režim se odhaduje. */
  rezim?: RezimBehu;
  kroky: KrokBehu[];
}

/**
 * Režim běhu. Když ho záznam nese, platí ten; u starších záznamů se
 * odhaduje z toho, co v běhu bylo: bez jediného sběrače = přepočet.
 * Cílený běh se bez záznamu poznat nedá — chybějící kroky pak řádky
 * sekcí hlásí jako „neběžel", což je pravda v obou případech.
 */
export function rezimBehu(beh: Beh): { bezSberu: boolean; jen: string[]; zaznamenany: boolean } {
  if (beh.rezim && typeof beh.rezim === 'object') {
    return {
      bezSberu: Boolean(beh.rezim.bez_sberu),
      jen: Array.isArray(beh.rezim.jen) ? beh.rezim.jen.filter((x): x is string => typeof x === 'string') : [],
      zaznamenany: true,
    };
  }
  return { bezSberu: !beh.kroky.some((k) => k.modul.startsWith('scrapers.')), jen: [], zaznamenany: false };
}

/**
 * Poslední zaznamenaný běh. Bere se nejnovější den v `data/logy/`, který má
 * `beh.json` — samostatné spuštění jednoho modulu zakládá den bez něj a to
 * není běh, ale ruční zásah.
 */
export function nactiPosledniBeh(): Nacteno<Beh | null> {
  const adresar = path.join(KOREN_DAT, 'logy');
  let dny: string[];
  try {
    dny = fs
      .readdirSync(adresar, { withFileTypes: true })
      .filter((d) => d.isDirectory() && /^\d{4}-\d{2}-\d{2}$/.test(d.name))
      .map((d) => d.name)
      .sort()
      .reverse();
  } catch {
    return { stav: 'chybi', data: null, zdroj: 'logy', poznamka: 'Adresář logů zatím neexistuje.' };
  }
  for (const den of dny) {
    if (!fs.existsSync(path.join(adresar, den, 'beh.json'))) continue;
    const n = nactiJson<Partial<Beh>>(`logy/${den}/beh.json`, {});
    if (n.stav !== 'ok') return { ...n, data: null };
    return {
      ...n,
      data: {
        datum: typeof n.data.datum === 'string' ? n.data.datum : den,
        obdobi_od: n.data.obdobi_od,
        obdobi_do: n.data.obdobi_do,
        trvani_s: n.data.trvani_s,
        uspech: n.data.uspech,
        rezim: n.data.rezim,
        kroky: Array.isArray(n.data.kroky) ? n.data.kroky : [],
      },
    };
  }
  return { stav: 'chybi', data: null, zdroj: 'logy/*/beh.json', poznamka: 'Žádný běh zatím nemá záznam.' };
}

/**
 * Které kroky běhu plní kterou sekci.
 *
 * Je to znalost o projektu, ne údaj z dat — stejně jako mapa zdrojů
 * v `config/diagramy.json`. Když přibude modul, přibude sem. Sekce bez
 * kroku (historie se píše ručně, hledání skládá build) mají prázdný seznam
 * a tabulka u nich napíše, že je běh neplní.
 */
const KROKY_SEKCE: Record<string, string[]> = {
  /* U odvozených sekcí jsou vyjmenované i VSTUPY: řetěz čte usnesení
     a agregaci peněz, propojení peníze, lidi, usnesení a hlasování.
     Kdyby se hlídal jen poslední krok, selhaný sběr usnesení následovaný
     úspěšným přepočtem ze starých souborů by vyšel „v pořádku". */
  vydani: [
    'scrapers.usneseni',
    'scrapers.hlasovani',
    'scrapers.muml',
    'scrapers.snapshoty',
    'scrapers.hlidac_api',
    'scrapers.zpravodaj',
    'scrapers.media',
    'pipeline.vydani',
  ],
  usneseni: ['scrapers.usneseni', 'pipeline.tagovani'],
  hlasovani: ['scrapers.hlasovani', 'pipeline.profily'],
  slibnik: ['scrapers.usneseni', 'pipeline.slibnik'],
  vysvedceni: ['pipeline.vysvedceni'],
  'ucet-obdobi': ['scrapers.usneseni', 'scrapers.hlasovani', 'pipeline.ucet_obdobi'],
  komise: ['scrapers.komise', 'pipeline.komise_prehled', 'pipeline.retez_komise'],
  informace: ['scrapers.informace106', 'pipeline.informace106_prehled'],
  penize: ['scrapers.hlidac_api', 'scrapers.hlidac', 'pipeline.dodatky', 'pipeline.agregace_penez'],
  hospodareni: [
    'scrapers.monitor',
    'scrapers.srovnani',
    'scrapers.zaverky',
    'pipeline.rozpocet',
    'pipeline.dotace_prehled',
  ],
  tisicovka: ['scrapers.monitor', 'scrapers.csu', 'pipeline.rozpocet'],
  retez: ['scrapers.usneseni', 'scrapers.hlidac_api', 'pipeline.agregace_penez', 'pipeline.retez'],
  lide: ['scrapers.lide', 'scrapers.hlasovani', 'pipeline.profily'],
  firmy: ['scrapers.firmy', 'scrapers.podnikatele', 'pipeline.firmy_prehled', 'pipeline.podnikatele_prehled'],
  propojeni: [
    'scrapers.usneseni',
    'scrapers.hlasovani',
    'scrapers.hlidac_api',
    'scrapers.lide',
    'pipeline.agregace_penez',
    'pipeline.propojeni',
  ],
  volby: ['scrapers.volby', 'scrapers.geodata'],
  mapa: ['scrapers.geodata', 'scrapers.pamatky', 'scrapers.uzemni_plan'],
  statistika: ['scrapers.csu'],
  diagramy: ['pipeline.agregace_penez', 'pipeline.propojeni', 'pipeline.retez', 'pipeline.retez_komise', 'pipeline.diagramy'],
  zpravodaj: ['scrapers.zpravodaj', 'pipeline.clanky'],
  historie: [],
  hledat: [],
};

export type StavBehuSekce = 'ok' | 'selhal' | 'preskocen' | 'schybami' | 'castecne' | 'mimo';

export interface BehSekce {
  stav: StavBehuSekce;
  /** Věta do tabulky. Píše se z dat, ne z barvy — barva sama nic nenese. */
  text: string;
  /** Kroky, které v posledním běhu sekci plnily. */
  kroky: KrokBehu[];
  /** Očekávané kroky, které v běhu vůbec nebyly. */
  chybejici: string[];
  /** Sekce má sběrač, ale v posledním běhu neběžel (běh jen přepočítával). */
  bezSberu: boolean;
}

/**
 * Log modulu z daného dne: `uspech` a počet chyb. Modul se jmenuje podle
 * `lib.core.Log`; web města píše víc logů s prefixem (muml-akce, muml-rada…),
 * proto se berou i soubory `<jméno>-*.json`.
 */
function logyModulu(den: string, modul: string): { uspech: boolean; chyb: number }[] {
  const jmeno = modul.replace(/^.*\./, '');
  let soubory: string[];
  try {
    soubory = fs
      .readdirSync(path.join(KOREN_DAT, 'logy', den))
      .filter((f) => f === `${jmeno}.json` || (f.startsWith(`${jmeno}-`) && f.endsWith('.json')));
  } catch {
    return [];
  }
  const ven: { uspech: boolean; chyb: number }[] = [];
  for (const f of soubory) {
    const n = nactiJson<{ uspech?: boolean; chyby?: unknown[] }>(`logy/${den}/${f}`, {});
    if (n.stav !== 'ok' || typeof n.data.uspech !== 'boolean') continue;
    ven.push({ uspech: n.data.uspech, chyb: Array.isArray(n.data.chyby) ? n.data.chyby.length : 0 });
  }
  return ven;
}

/** Lidský název kroku. Bere se z libovolného záznamu běhu; když modul nikdy neběžel, zůstane jeho jméno. */
let popisyKroku: Map<string, string> | null = null;
function popisKroku(modul: string): string {
  if (!popisyKroku) {
    popisyKroku = new Map();
    const adresar = path.join(KOREN_DAT, 'logy');
    let dny: string[] = [];
    try {
      dny = fs.readdirSync(adresar).filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d));
    } catch {
      dny = [];
    }
    for (const den of dny) {
      const n = nactiJson<{ kroky?: KrokBehu[] }>(`logy/${den}/beh.json`, {});
      for (const k of n.data.kroky ?? []) if (k.modul && k.popis) popisyKroku.set(k.modul, k.popis);
    }
  }
  return popisyKroku.get(modul) ?? modul;
}

function vyjmenuj(moduly: string[]): string {
  return moduly.map((m) => `„${popisKroku(m)}“`).join(', ');
}

/**
 * Stav sekce podle posledního běhu.
 *
 * Hodnotí se KAŽDÝ očekávaný krok, ne jen ty, které v běhu byly:
 *   – krok v běhu selhal                     → selhal
 *   – krok se přeskočil (chybí modul/main)   → přeskočen
 *   – krok doběhl, ale jeho log hlásí chyby   → s chybami
 *   – očekávaný krok v běhu vůbec nebyl       → částečně (u přepočtového
 *     běhu se chybějící sběrače jen zmíní, to je jeho smysl)
 *   – vše proběhlo bez chyb                   → v pořádku
 * Cílený běh (`--jen usneseni`) tak nechá tagování stát jako „neběželo",
 * ne jako zelené. Zelená je jen tehdy, když opravdu všechno doběhlo.
 */
function behSekce(klic: string, beh: Beh | null): BehSekce {
  const moduly = KROKY_SEKCE[klic] ?? [];
  const nic = { kroky: [] as KrokBehu[], chybejici: [] as string[], bezSberu: false };
  if (moduly.length === 0) return { stav: 'mimo', text: 'týdenní běh sekci neplní', ...nic };
  if (!beh) return { stav: 'mimo', text: 'záznam běhu chybí', ...nic };

  const rezim = rezimBehu(beh);
  const podleModulu = new Map(beh.kroky.map((k) => [k.modul, k]));
  const kroky = moduly.map((m) => podleModulu.get(m)).filter((k): k is KrokBehu => Boolean(k));
  const chybejici = moduly.filter((m) => !podleModulu.has(m));
  if (kroky.length === 0) {
    return { stav: 'mimo', text: 'v posledním běhu neběžel žádný krok sekce', kroky, chybejici, bezSberu: false };
  }

  const chybejiciSberace = chybejici.filter((m) => m.startsWith('scrapers.'));
  const chybejiciOstatni = chybejici.filter((m) => !m.startsWith('scrapers.'));
  /* U přepočtového běhu je chybějící sběrač jeho smysl, ne závada. U
     cíleného nebo úplného běhu je chybějící sběrač stejná díra jako
     chybějící přepočet. */
  const omluveneSberace = rezim.bezSberu ? chybejiciSberace : [];
  const neomluvene = rezim.bezSberu ? chybejiciOstatni : chybejici;
  const bezSberu = moduly.some((m) => m.startsWith('scrapers.')) && !kroky.some((k) => k.modul.startsWith('scrapers.'));
  /* Horší stav vyhrává, ale chybějící kroky se přitom nezamlčí. */
  const dovetek = neomluvene.length > 0 ? `; neběžely: ${vyjmenuj(neomluvene)}` : '';

  const selhal = kroky.find((k) => k.stav === 'selhal');
  if (selhal) {
    const proc = selhal.chyba ? ` — ${selhal.chyba.replace(/\s+/g, ' ').trim()}` : '';
    return { stav: 'selhal', text: `selhal krok „${selhal.popis}“${proc}${dovetek}`, kroky, chybejici, bezSberu };
  }
  const preskocen = kroky.find((k) => k.stav === 'chybi_modul' || k.stav === 'chybi_main');
  if (preskocen) {
    const proc = preskocen.stav === 'chybi_main' ? 'modul nemá vstupní bod' : 'modul chybí';
    return { stav: 'preskocen', text: `krok „${preskocen.popis}“ se přeskočil (${proc})${dovetek}`, kroky, chybejici, bezSberu };
  }

  /* Krok doběhl, ale jeho vlastní log hlásí chyby. Orchestrátor to do
     9/2026 nezapisoval — modul vrátil kód 1 a v souhrnu stál jako „ok". */
  const sChybami = kroky
    .map((k) => ({ k, logy: logyModulu(beh.datum, k.modul).filter((l) => !l.uspech) }))
    .filter((x) => x.logy.length > 0);
  if (sChybami.length > 0) {
    const prvni = sChybami[0];
    const chyb = prvni.logy.reduce((a, l) => a + l.chyb, 0);
    return {
      stav: 'schybami',
      text: `krok „${prvni.k.popis}“ doběhl, ale jeho log hlásí ${chyb} ${chyb === 1 ? 'chybu' : chyb < 5 ? 'chyby' : 'chyb'}${dovetek}`,
      kroky,
      chybejici,
      bezSberu,
    };
  }

  if (neomluvene.length > 0) {
    return {
      stav: 'castecne',
      text: `část kroků neběžela: ${vyjmenuj(neomluvene)}`,
      kroky,
      chybejici,
      bezSberu,
    };
  }

  const n = kroky.length;
  const kolik = `${n} ${n === 1 ? 'krok' : n < 5 ? 'kroky' : 'kroků'}`;
  return {
    stav: 'ok',
    text: omluveneSberace.length > 0 ? `přepočet v pořádku (${kolik}), sběr ze zdroje neběžel` : `v pořádku (${kolik})`,
    kroky,
    chybejici,
    bezSberu,
  };
}

/* ─────────────────────────────  Data  ───────────────────────────────── */

export interface DataSekce {
  stav: Stav;
  /** K jakému dni jsou data. `null`, když to soubor neuvádí. */
  k: string | null;
  /** Odkud se stav zjišťoval — cesta k souboru nebo adresáři. */
  zdroj: string;
}

/** Klíče, pod kterými moduly zapisují datum vzniku souboru. */
const KLICE_DATA = ['generovano', 'hodnoceno_k', 'staženo', 'stazeno', 'aktualizovano'];

/**
 * Kdy naposledy úspěšně doběhl některý z kroků sekce — podle logů modulů
 * (`data/logy/<den>/<modul>.json`, pole `konec` a `uspech`). Záloha pro
 * soubory, které si datum nenesou (přehled komisí, žádostí, geodata).
 * Bere se nejnovější úspěšný log; log se jménem modulu píše `lib.core.Log`,
 * takže sběrače s víc logy (muml-*) tu chybí — u nich zůstane „—".
 */
function posledniUspesnyBeh(moduly: string[]): string | null {
  if (moduly.length === 0) return null;
  const adresar = path.join(KOREN_DAT, 'logy');
  let dny: string[];
  try {
    dny = fs
      .readdirSync(adresar, { withFileTypes: true })
      .filter((d) => d.isDirectory() && /^\d{4}-\d{2}-\d{2}$/.test(d.name))
      .map((d) => d.name)
      .sort()
      .reverse();
  } catch {
    return null;
  }
  const jmena = moduly.map((m) => m.replace(/^.*\./, ''));
  for (const den of dny) {
    for (const j of jmena) {
      const n = nactiJson<{ uspech?: boolean; konec?: string }>(`logy/${den}/${j}.json`, {});
      if (n.stav !== 'ok' || n.data.uspech !== true) continue;
      const k = typeof n.data.konec === 'string' ? n.data.konec : den;
      return /^\d{4}-\d{2}-\d{2}/.test(k) ? k.slice(0, 10) : den;
    }
  }
  return null;
}

function datumZeZaznamu(d: unknown): string | null {
  if (!d || typeof d !== 'object') return null;
  for (const k of KLICE_DATA) {
    const v = (d as Record<string, unknown>)[k];
    if (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}/.test(v)) return v.slice(0, 10);
  }
  return null;
}

function maSoubory(abs: string): boolean {
  try {
    return fs.readdirSync(abs).length > 0;
  } catch {
    return false;
  }
}

/**
 * Stav zdrojového souboru sekce. Cesta se bere ze znaku — je to tentýž
 * soubor, ze kterého se počítá číslo na dlaždici, takže číslo a stav
 * mluví o téže věci.
 */
function dataSekce(znak: Znak | undefined): DataSekce {
  const zdroj = (znak?.zdroj ?? '').replace(/^\.?\/*/, '');
  if (!zdroj || !zdroj.startsWith('data/')) {
    /* „součet ostatních sekcí“ (hledání) — nemá vlastní soubor. */
    return { stav: znak?.stav === 'ok' ? 'ok' : 'chybi', k: null, zdroj: zdroj || '—' };
  }
  const rel = zdroj.replace(/^data\//, '');
  const abs = path.join(KOREN_DAT, rel);

  if (rel.endsWith('.json')) {
    const n = nactiJson<unknown>(rel, null);
    return { stav: n.stav, k: n.stav === 'ok' ? datumZeZaznamu(n.data) : null, zdroj: rel };
  }
  if (!fs.existsSync(abs)) return { stav: 'chybi', k: null, zdroj: rel };
  let jeAdresar = false;
  try {
    jeAdresar = fs.statSync(abs).isDirectory();
  } catch {
    return { stav: 'chyba', k: null, zdroj: rel };
  }
  if (jeAdresar) return { stav: maSoubory(abs) ? 'ok' : 'chybi', k: null, zdroj: rel };
  return { stav: 'ok', k: null, zdroj: rel };
}

/* ────────────────────────────  Zdroje  ──────────────────────────────── */

interface ZdrojKonfigurace {
  id: string;
  nazev: string;
  druh?: string;
  plni?: string[];
}

function zdrojeSekci(): Map<string, string[]> {
  const cfg = nactiConfig<{ zdroje?: ZdrojKonfigurace[] }>('diagramy.json', {});
  const ven = new Map<string, string[]>();
  for (const z of cfg.data.zdroje ?? []) {
    for (const s of z.plni ?? []) {
      const pole = ven.get(s);
      if (pole) pole.push(z.nazev);
      else ven.set(s, [z.nazev]);
    }
  }
  return ven;
}

/* ─────────────────────────────  Řádek  ──────────────────────────────── */

export interface StavSekce {
  sekce: Sekce;
  skupina: string;
  znak: Znak | undefined;
  /** „12 908 bodů usnesení", nebo „—" když znak chybí. */
  pocet: string;
  data: DataSekce;
  /** Text do sloupce „Data k". Přebírá se z volajícího, jinak ze souboru. */
  dataK: string;
  beh: BehSekce;
  /** Názvy vnějších zdrojů z config/diagramy.json. Prázdné = skládá se z jiných sekcí. */
  zdroje: string[];
}

export interface SkupinaStavu {
  nazev: string;
  radky: StavSekce[];
}

export interface PrehledStavu {
  beh: Nacteno<Beh | null>;
  znaky: Nacteno<unknown>;
  skupiny: SkupinaStavu[];
  /** Kolik sekcí je v jakém stavu — pro větu nad tabulkou. */
  souhrn: {
    sekci: number;
    dataOk: number;
    dataChybi: number;
    behSelhal: number;
    behPreskocen: number;
    behSChybami: number;
    behCastecne: number;
    bezSberu: number;
  };
}

/**
 * Složí tabulku stavu pro všechny sekce.
 *
 * `dataK` jsou texty pro sloupec „Data k" u sekcí, kde soubor datum nenese
 * (adresáře usnesení a hlasování) a volající ho umí říct líp — třeba
 * „jednání 21. 8. 2026". Klíč je klíč sekce.
 */
export function prehledStavuSekci(dataK: Record<string, string | null | undefined> = {}): PrehledStavu {
  const zZnaku = nactiZnaky();
  const znaky = zZnaku.data?.znaky ?? {};
  const zBehu = nactiPosledniBeh();
  const beh = zBehu.data;
  const zdroje = zdrojeSekci();

  const radek = (sekce: Sekce, skupina: string): StavSekce => {
    const znak = znaky[sekce.klic];
    const data = dataSekce(znak);
    const prepis = dataK[sekce.klic];
    /* Datum: co řekne volající > co si nese soubor > kdy naposledy uspěl
       krok, který ho píše. Až když nic z toho není, je tam pomlčka. */
    const zLogu = data.stav === 'ok' && !data.k ? posledniUspesnyBeh(KROKY_SEKCE[sekce.klic] ?? []) : null;
    const kText = data.k ? datumKratke(data.k) : zLogu ? `přepočet ${datumKratke(zLogu)}` : '—';
    return {
      sekce,
      skupina,
      znak,
      pocet: znak && znak.stav === 'ok' ? `${znak.hodnota} ${znak.jednotka}`.trim() : '—',
      data,
      dataK: prepis ?? kText,
      beh: behSekce(sekce.klic, beh),
      zdroje: zdroje.get(sekce.klic) ?? [],
    };
  };

  const skupiny: SkupinaStavu[] = [
    { nazev: 'Týdenní přehled', radky: [radek(SEKCE_UVOD, 'Týdenní přehled')] },
    ...SKUPINY.map((s) => ({ nazev: s.nazev, radky: s.sekce.map((o) => radek(o, s.nazev)) })),
    { nazev: 'Hledání', radky: [radek(SEKCE_HLEDAT, 'Hledání')] },
  ];

  const vsechny = skupiny.flatMap((s) => s.radky);
  return {
    beh: zBehu,
    znaky: zZnaku,
    skupiny,
    souhrn: {
      sekci: vsechny.length,
      dataOk: vsechny.filter((r) => r.data.stav === 'ok').length,
      dataChybi: vsechny.filter((r) => r.data.stav !== 'ok').length,
      behSelhal: vsechny.filter((r) => r.beh.stav === 'selhal').length,
      behPreskocen: vsechny.filter((r) => r.beh.stav === 'preskocen').length,
      behSChybami: vsechny.filter((r) => r.beh.stav === 'schybami').length,
      behCastecne: vsechny.filter((r) => r.beh.stav === 'castecne').length,
      bezSberu: vsechny.filter((r) => r.beh.bezSberu).length,
    },
  };
}

/** Souhrn kroků posledního běhu — pro větu „21 kroků, 19 v pořádku, 1 selhal". */
export function souhrnBehu(beh: Beh): {
  kroku: number;
  ok: number;
  selhalo: number;
  preskoceno: number;
  sChybami: number;
  /** Sběr ze zdrojů proběhl (úplný běh), ne jen přepočet. */
  sberBezel: boolean;
  /** Cílený běh `--jen …` — které moduly. Prázdné = celý plán. */
  jen: string[];
  /** Režim je v záznamu zapsaný, ne odhadnutý. */
  rezimZaznamenany: boolean;
  selhane: KrokBehu[];
  preskocene: KrokBehu[];
  sChybamiKroky: { krok: KrokBehu; chyb: number }[];
} {
  const rezim = rezimBehu(beh);
  const selhane = beh.kroky.filter((k) => k.stav === 'selhal');
  const preskocene = beh.kroky.filter((k) => k.stav === 'chybi_modul' || k.stav === 'chybi_main');
  const sChybamiKroky = beh.kroky
    .filter((k) => k.stav === 'ok')
    .map((krok) => ({ krok, chyb: logyModulu(beh.datum, krok.modul).filter((l) => !l.uspech).reduce((a, l) => a + l.chyb, 0) }))
    .filter((x) => x.chyb > 0);
  return {
    kroku: beh.kroky.length,
    ok: beh.kroky.filter((k) => k.stav === 'ok').length - sChybamiKroky.length,
    selhalo: selhane.length,
    preskoceno: preskocene.length,
    sChybami: sChybamiKroky.length,
    sberBezel: !rezim.bezSberu,
    jen: rezim.jen,
    rezimZaznamenany: rezim.zaznamenany,
    selhane,
    preskocene,
    sChybamiKroky,
  };
}
