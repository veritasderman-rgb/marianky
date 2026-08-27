/**
 * Vysvědčení koalici 2022–2026 — ruční audit projektů a slibů.
 *
 * Data vyrábí `pipeline/vysvedceni.py` z podkladového sešitu. Na rozdíl od
 * zbytku webu tohle NENÍ výsledek sběrače: čísla ověřoval člověk proti
 * registru smluv, věstníku zakázek, registrům dotací a závěrečným účtům.
 * Web to musí říct nahlas — známka je hodnocení, ne měření.
 */
import { nactiJson, type Nacteno } from './data';

export interface Projekt {
  id: number;
  nazev: string | null;
  tema: string | null;
  typ: string | null;
  deklarovany_stav: string | null;
  deklarovany_termin: string | null;
  deklarovany_rozpocet_czk: number | null;
  deklarovana_dotace_czk: number | null;
  skutecny_stav: string | null;
  dolozene_naklady_czk: number | null;
  dolozena_dotace_czk: number | null;
  znamka: number | null;
  hodnoceni: string | null;
  rozpor: string | null;
  jistota: string | null;
  zdroje: string[];
}

export interface Slib {
  oblast: string | null;
  slib: string;
  stav: string | null;
  /**
   * `false` = nepodařilo se dohledat veřejný doklad o plnění.
   *
   * V sešitu má takový slib známku 5 stejně jako doložené nesplnění, ale
   * není to totéž a web to nesmí slít: nenález není důkaz. Sedm z dvanácti
   * „pětek" je právě tenhle případ.
   */
  dolozeno: boolean;
  doklad: string | null;
  znamka: number | null;
}

export interface MimoPortal {
  tema: string;
  slibeno: string | null;
  stalo_se: string | null;
  hodnoceni: string | null;
  zdroje: string[];
}

export interface RokRozpoctu {
  rok: string;
  schvaleno_tis: number | null;
  upraveno_tis: number | null;
  skutecnost_tis: number;
  plneni_upraveny: number | null;
  nevycerpano_tis: number | null;
}

export interface NuloveCerpani {
  rok: string;
  akce: string;
  upraveno_tis: number | null;
  skutecnost_tis: number | null;
  cerpani: number | null;
}

export interface Portal {
  nazev: string;
  url: string;
  /** Kdo portál provozuje — je to deklarace města o vlastní práci, ne nezávislý zdroj. */
  provozuje: string;
}

export interface Audit {
  hodnoceno_k: string;
  volebni_obdobi: string;
  predmet: string;
  portal: Portal | null;
  sesit: string;
  znamky: Record<string, string>;
  souhrn: {
    projektu: number;
    podle_znamky: Record<string, number>;
    deklarovany_rozpocet_czk: number;
    deklarovana_dotace_czk: number;
    dolozene_naklady_czk: number;
    dolozena_dotace_czk: number;
    slibu: number;
    slibu_dolozenych: number;
    slibu_nedohledanych: number;
  };
  projekty: Projekt[];
  sliby: Slib[];
  mimo_portal: MimoPortal[];
  rozpocet: {
    roky: RokRozpoctu[];
    souhrn_obdobi: RokRozpoctu | null;
    nulove_cerpani: NuloveCerpani[];
  };
  metodika: { nadpis: string; text: string }[];
}

const PRAZDNO: Audit = {
  hodnoceno_k: '',
  volebni_obdobi: '',
  predmet: '',
  portal: null,
  sesit: '',
  znamky: {},
  souhrn: {
    projektu: 0,
    podle_znamky: {},
    deklarovany_rozpocet_czk: 0,
    deklarovana_dotace_czk: 0,
    dolozene_naklady_czk: 0,
    dolozena_dotace_czk: 0,
    slibu: 0,
    slibu_dolozenych: 0,
    slibu_nedohledanych: 0,
  },
  projekty: [],
  sliby: [],
  mimo_portal: [],
  rozpocet: { roky: [], souhrn_obdobi: null, nulove_cerpani: [] },
  metodika: [],
};

export function nactiVysvedceni(): Nacteno<Audit> {
  return nactiJson<Audit>('vysvedceni/audit.json', PRAZDNO);
}

/**
 * Zdroj z auditu na odkaz, pokud to odkaz je.
 *
 * Buňka „Klíčové zdroje" míchá adresy (`hlidacstatu.cz/Detail/…`) s popisy
 * dokumentů („Hlídač státu – dotace NPO/MPSV“). Z popisu se odkaz vyrobit
 * nedá a vyrobit ho odhadem by znamenalo poslat čtenáře na adresu, kterou
 * nikdo neověřil. Popis proto zůstane textem.
 *
 * ZKRÁCENÝ ZDROJ SE NEODKAZUJE. Šestadvacet zdrojů v sešitu končí výpustkou
 * (`…/KarlovarskyKraj-A276A663…`) — jsou to zkrácené identifikátory, ne celé
 * adresy. Udělat z nich odkaz vypadá vstřícně, ale pošle čtenáře na 404 pod
 * hlavičkou „kde si to zkontrolujete". Zůstávají textem, protože jako text
 * se dají vyhledat, kdežto jako rozbitý odkaz nejsou k ničemu.
 */
export function zdrojJakoOdkaz(zdroj: string): string | null {
  const s = zdroj.trim();
  if (s.includes('…') || s.endsWith('...')) return null;
  if (/^https?:\/\//i.test(s)) return s;
  // Doména na začátku bez schématu — typicky `hlidacstatu.cz/Detail/123`.
  if (/^(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+\//i.test(s)) return `https://${s}`;
  return null;
}
