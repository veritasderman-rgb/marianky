/**
 * Načítání přehledů rozpočtu města z `data/rozpocet/prehled/`.
 *
 * Data počítá `pipeline/rozpocet.py` z výkazů Monitoru státní pokladny
 * (FIN 2-12 M, rozvaha, výkaz zisku a ztráty). Tady se jen čtou a typují —
 * žádné dopočty; všechna metodická pravidla (konsolidace, převody vlastním
 * fondům, null ≠ nula) jsou vyřešená v pipeline a data je nesou s sebou.
 *
 * Tři věci, které musí každý odběratel těchhle dat vědět:
 *
 *   1. **`null` znamená „výkaz to neuvádí", ne nulu.** `0` je vykázaná nula.
 *   2. **Období s `koncove: false` je rozpracovaný rok** (stav k danému
 *      měsíci) a do meziročního srovnání nepatří — grafy ho vynechávají
 *      a ukazují ho zvlášť.
 *   3. **Členění po třídách a paragrafech je PŘED konsolidací.** Do grafů
 *      „kam jdou peníze" patří `skutecnost_bez_prevodu`, jinak vyjde, že
 *      největší kapitolou města je přesouvání peněz mezi vlastními účty.
 */
import { nactiJson, type Nacteno } from './data';

/** Schválený / upravený rozpočet a skutečnost. `null` = výkaz neuvádí. */
export interface Trojice {
  schvaleny: number | null;
  upraveny: number | null;
  skutecnost: number | null;
}

export interface StrukturaPrijmu {
  danove: Trojice;
  nedanove: Trojice;
  kapitalove_prijmy: Trojice;
  transfery: Trojice;
  soucet_pred_konsolidaci: Trojice;
  minus_konsolidace: Trojice;
  po_konsolidaci: Trojice;
}

export interface StrukturaVydaju {
  bezne_vydaje: Trojice;
  kapitalove_vydaje: Trojice;
  soucet_pred_konsolidaci: Trojice;
  minus_konsolidace: Trojice;
  po_konsolidaci: Trojice;
}

export interface RokRozpoctu {
  rok: number;
  obdobi: string;
  /** `false` = rozpracovaný rok (stav k měsíci), do srovnání let nepatří. */
  koncove: boolean;
  zdroj_souctu: 'rekapitulace' | 'dopocet_z_polozek' | string;
  prijmy: Trojice;
  vydaje: Trojice;
  saldo: Trojice;
  financovani: Trojice;
  plneni_prijmu_pct: number | null;
  plneni_vydaju_pct: number | null;
  prijmy_struktura: StrukturaPrijmu;
  vydaje_struktura: StrukturaVydaju;
}

export interface RozpocetPoLetech {
  generovano?: string;
  jednotka?: string;
  metodika?: string[];
  kontrola_dopoctu?: {
    porovnanych_hodnot: number;
    neshod: number;
    zaver: string;
  };
  overeni_proti_usnesenim?: {
    sedi: number;
    neshod: number;
    neporovnano: number;
    zaver: string;
  } | null;
  roky: RokRozpoctu[];
  roky_bez_dat?: number[];
}

export interface PolozkaStruktury {
  kod: string;
  nazev: string | null;
  uroven: 'skupina' | 'oddil' | 'paragraf' | string;
  obsahuje_prevody_vlastnim_fondum: boolean;
  schvaleny: number;
  upraveny: number;
  skutecnost: number;
  schvaleny_bez_prevodu: number;
  upraveny_bez_prevodu: number;
  skutecnost_bez_prevodu: number;
  podil_pct: number | null;
  podil_bez_prevodu_pct: number | null;
}

export interface RokStruktury {
  rok: number;
  obdobi: string;
  koncove: boolean;
  celkem: { schvaleny: number; upraveny: number; skutecnost: number };
  bez_prevodu_vlastnim_fondum: { schvaleny: number; upraveny: number; skutecnost: number };
  prevody_vlastnim_fondum: { schvaleny: number; upraveny: number; skutecnost: number };
  skupiny: PolozkaStruktury[];
  oddily: PolozkaStruktury[];
  paragrafy: PolozkaStruktury[];
}

export interface VydajeStruktura {
  metodika?: string[];
  roky: RokStruktury[];
}

export interface RozchodOddilu {
  kod: string;
  nazev: string | null;
  schvaleny: number;
  upraveny: number;
  skutecnost: number;
  rozdil_proti_schvalenemu: number;
  rozdil_proti_upravenemu: number;
  plneni_pct: number | null;
}

export interface RokPlanu {
  rok: number;
  obdobi: string;
  koncove: boolean;
  prijmy: Trojice & {
    plneni_pct: number | null;
    navyseni_rozpoctu: number | null;
    navyseni_rozpoctu_pct: number | null;
    odchylka_od_planu: number | null;
    odchylka_od_schvaleneho: number | null;
  };
  vydaje: RokPlanu['prijmy'];
  saldo_planovane: number | null;
  saldo_skutecne: number | null;
  nejvetsi_rozchody_oddilu: RozchodOddilu[];
}

export interface PlanVsSkutecnost {
  metodika?: string[];
  roky: RokPlanu[];
}

export interface RozvahaMesta {
  aktiva: number | null;
  stala_aktiva: number | null;
  dlouhodoby_hmotny_majetek: number | null;
  dlouhodoby_financni_majetek: number | null;
  obezna_aktiva: number | null;
  vlastni_kapital: number | null;
  cizi_zdroje: number | null;
  dlouhodobe_zavazky: number | null;
  dlouhodobe_uvery: number | null;
  kratkodobe_zavazky: number | null;
  kratkodobe_uvery: number | null;
  dodavatele: number | null;
}

export interface RokMajetku {
  rok: number;
  obdobi: string;
  koncove: boolean;
  rozvaha: RozvahaMesta;
  uvery_celkem: number | null;
  financovani: Record<string, number | null> | null;
  bankovni_ucty: {
    ucty: { kod: string; nazev: string | null; pocatecni_stav: number | null; koncovy_stav: number | null; zmena: number | null }[];
    bezne_ucty_celkem: { pocatecni_stav: number | null; koncovy_stav: number | null; zdroj: 'vykaz' | 'neuvedeno' | string };
  } | null;
}

export interface MajetekZadluzenost {
  metodika?: string[];
  roky: RokMajetku[];
}

export interface VyzzObdobi {
  hlavni_cinnost: Record<string, number | null>;
  hospodarska_cinnost: Record<string, number | null>;
  naklady_celkem: number | null;
  vynosy_celkem: number | null;
  vysledek_hospodareni_celkem: number | null;
  /** `dopocet` = výkaz řádek s výsledkem nemá (roky 2010–2011), počítá se z rozdílu. */
  vysledek_zdroj: 'vykaz' | 'dopocet' | string;
}

export interface ObdobiOrganizace {
  obdobi: string;
  rok: number;
  koncove: boolean;
  rozvaha?: Record<string, number | null>;
  vyzz?: VyzzObdobi;
}

export interface OrganizaceVykazy {
  metodika?: string[];
  organizace: {
    ico: string;
    nazev: string | null;
    typ: string | null;
    vlastnictvi: string | null;
    obdobi: ObdobiOrganizace[];
  }[];
  /** Obchodní společnosti města v CSÚIS nejsou — nejsou to vybrané účetní jednotky. */
  subjekty_bez_vykazu: { ico: string; nazev: string; typ?: string | null }[];
}

export interface RokKryti {
  rok: number;
  koncove: boolean;
  vydaje_skutecnost: number | null;
  smlouvy_hodnota: number | null;
  smluv: number | null;
  smluv_bez_ceny: number | null;
  z_toho_vnitrni_holding: number | null;
  vnitrnich_smluv: number | null;
  podil_smluv_na_vydajich_pct: number | null;
  stav_registru: 'ok' | 'castecny_rok' | 'mimo_registr' | string;
}

export interface KrytiSmlouvami {
  stav?: string;
  duvod?: string;
  metodika?: string[];
  roky: RokKryti[];
}

export interface RozpocetSouhrn {
  rozsah_dat?: { prvni_rok: number | null; posledni_uzavreny_rok: number | null; bezici_obdobi: string | null };
  posledni_uzavreny_rok?: RokRozpoctu | null;
  bezici_obdobi?: RokRozpoctu | null;
  nejvetsi_oddily_vydaju?: PolozkaStruktury[];
  majetek?: RozvahaMesta | null;
  uvery_celkem?: number | null;
  organizaci_s_vykazy?: number;
  subjektu_bez_vykazu?: number;
  overeni?: {
    dopocet_proti_souhrnum_vykazu?: { porovnanych_hodnot: number; neshod: number; zaver: string };
    schvaleny_rozpocet_proti_usnesenim?: { sedi: number; neshod: number; neporovnano: number; zaver: string };
  };
}

/* ─────────────────────────────  Loadery  ────────────────────────────── */

const PREHLED = 'rozpocet/prehled';

export function nactiRozpocetPoLetech(): Nacteno<RozpocetPoLetech> {
  const v = nactiJson<RozpocetPoLetech>(`${PREHLED}/po_letech.json`, { roky: [] });
  if (v.stav === 'ok' && !Array.isArray(v.data?.roky)) {
    return { stav: 'chyba', data: { roky: [] }, zdroj: v.zdroj, poznamka: 'po_letech.json nemá pole `roky`.' };
  }
  return v;
}

export function nactiVydajeStrukturu(): Nacteno<VydajeStruktura> {
  const v = nactiJson<VydajeStruktura>(`${PREHLED}/vydaje_struktura.json`, { roky: [] });
  if (v.stav === 'ok' && !Array.isArray(v.data?.roky)) {
    return { stav: 'chyba', data: { roky: [] }, zdroj: v.zdroj, poznamka: 'vydaje_struktura.json nemá pole `roky`.' };
  }
  return v;
}

export function nactiPlanVsSkutecnost(): Nacteno<PlanVsSkutecnost> {
  return nactiJson<PlanVsSkutecnost>(`${PREHLED}/plan_vs_skutecnost.json`, { roky: [] });
}

export function nactiMajetekZadluzenost(): Nacteno<MajetekZadluzenost> {
  return nactiJson<MajetekZadluzenost>(`${PREHLED}/majetek_zadluzenost.json`, { roky: [] });
}

export function nactiOrganizaceVykazy(): Nacteno<OrganizaceVykazy> {
  return nactiJson<OrganizaceVykazy>(`${PREHLED}/organizace.json`, { organizace: [], subjekty_bez_vykazu: [] });
}

export function nactiKrytiSmlouvami(): Nacteno<KrytiSmlouvami> {
  return nactiJson<KrytiSmlouvami>(`${PREHLED}/kryti_smlouvami.json`, { roky: [] });
}

export function nactiRozpocetSouhrn(): Nacteno<RozpocetSouhrn> {
  return nactiJson<RozpocetSouhrn>(`${PREHLED}/souhrn.json`, {});
}

/* ─────────────────────────────  Pomocníci  ──────────────────────────── */

/** Jen uzavřené roky — rozpracovaný rok do meziročního srovnání nepatří. */
export function uzavreneRoky<T extends { koncove: boolean }>(roky: T[]): T[] {
  return roky.filter((r) => r.koncove);
}

/** Poslední rozpracované období (běžící rok), pokud v datech je. */
export function beziciObdobi<T extends { koncove: boolean }>(roky: T[]): T | null {
  return [...roky].reverse().find((r) => !r.koncove) ?? null;
}
