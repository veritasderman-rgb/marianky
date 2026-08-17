/**
 * Načítání propojení mezi samosprávou, firmami a penězi.
 *
 * Tyhle soubory teprve vznikají v jiných modulech a jejich přesný tvar zatím
 * není v docs/PLAN.md popsaný. Proto se čtou ZÁMĚRNĚ TOLERANTNĚ:
 *
 *   – přijímá se jak holé pole, tak objekt s obalovým klíčem
 *   – u každého údaje se zkouší několik obvyklých názvů klíče
 *   – co v datech není, je `null` a v UI se napíše „v datech není" —
 *     nikdy se nedopočítává a nikdy se nedohaduje
 *
 * Nic z toho nemění zásadu projektu: v UI se zobrazují jen fakta ze zdroje.
 * Interpretace se do těchhle struktur nedostane, protože tu žádná nevzniká.
 */
import { nactiJson, type Nacteno } from './data';

/* ─────────────────────────  Tolerantní čtení  ───────────────────────── */

type Zaznam = Record<string, unknown>;

function jeObjekt(v: unknown): v is Zaznam {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** První neprázdný textový údaj z uvedených klíčů. */
function txt(o: Zaznam | null | undefined, ...klice: string[]): string | null {
  if (!o) return null;
  for (const k of klice) {
    const v = o[k];
    if (typeof v === 'string' && v.trim()) return v.trim();
    if (typeof v === 'number' && Number.isFinite(v)) return String(v);
  }
  return null;
}

/** První číselný údaj z uvedených klíčů. Text „1 200 000" se převede taky. */
function cis(o: Zaznam | null | undefined, ...klice: string[]): number | null {
  if (!o) return null;
  for (const k of klice) {
    const v = o[k];
    if (typeof v === 'number' && Number.isFinite(v)) return v;
    if (typeof v === 'string') {
      const cisty = v.replace(/\s| /g, '').replace(',', '.');
      if (/^-?\d+(\.\d+)?$/.test(cisty)) return Number(cisty);
    }
  }
  return null;
}

/** `true` / `false` / `null`, když se o tom v datech nic nepíše. */
function ano(o: Zaznam | null | undefined, ...klice: string[]): boolean | null {
  if (!o) return null;
  for (const k of klice) {
    const v = o[k];
    if (typeof v === 'boolean') return v;
    if (typeof v === 'string') {
      const s = v.trim().toLowerCase();
      if (s === 'ano' || s === 'true' || s === 'yes') return true;
      if (s === 'ne' || s === 'false' || s === 'no') return false;
    }
  }
  return null;
}

/** Podíl vždy v rozsahu 0–1. Zdroj může psát procenta i zlomek. */
function podil(o: Zaznam | null | undefined, ...klice: string[]): number | null {
  const v = cis(o, ...klice);
  if (v === null) return null;
  if (v < 0) return null;
  // 0–1 bereme jako zlomek, 1–100 jako procenta. Přesně 1 je zlomek (=100 %).
  return v > 1 && v <= 100 ? v / 100 : v > 100 ? null : v;
}

/** Seznam objektů z uvedených klíčů. */
function objekty(o: Zaznam | null | undefined, ...klice: string[]): Zaznam[] {
  if (!o) return [];
  for (const k of klice) {
    const v = o[k];
    if (Array.isArray(v)) return v.filter(jeObjekt);
  }
  return [];
}

/** Seznam textů. Přijme řetězec, pole řetězců i pole objektů s názvem. */
function texty(o: Zaznam | null | undefined, ...klice: string[]): string[] {
  if (!o) return [];
  for (const k of klice) {
    const v = o[k];
    if (typeof v === 'string' && v.trim()) return [v.trim()];
    if (Array.isArray(v)) {
      const ven: string[] = [];
      for (const p of v) {
        if (typeof p === 'string' && p.trim()) ven.push(p.trim());
        else if (jeObjekt(p)) {
          const n = txt(p, 'nazev', 'role', 'funkce', 'pozice', 'name');
          if (n) ven.push(n);
        }
      }
      if (ven.length > 0) return ven;
    }
  }
  return [];
}

/** Kořen souboru: buď holé pole, nebo objekt s jedním z obalových klíčů. */
function korenSeznam(data: unknown, ...klice: string[]): Zaznam[] {
  if (Array.isArray(data)) return data.filter(jeObjekt);
  if (jeObjekt(data)) {
    for (const k of klice) {
      const v = data[k];
      if (Array.isArray(v)) return v.filter(jeObjekt);
    }
  }
  return [];
}

/** IČO se v datech objevuje jako číslo i jako řetězec s vedoucí nulou. */
function ico(o: Zaznam | null | undefined, ...klice: string[]): string | null {
  const v = txt(o, ...klice);
  if (!v) return null;
  const cisty = v.replace(/\D/g, '');
  if (!cisty) return null;
  return cisty.length < 8 ? cisty.padStart(8, '0') : cisty;
}

/* ═══════════════════════  propojeni/osoby_firmy.json  ══════════════════ */

export interface FirmaOsoby {
  ico: string | null;
  nazev: string;
  /** Role ve firmě — jednatel, člen dozorčí rady, společník… */
  role: string[];
  od: string | null;
  do: string | null;
  /** Trvá angažmá? `null`, když to v datech není. */
  aktivni: boolean | null;
  /**
   * Obchoduje firma s městem? `null` znamená, že se o tom zdroj nezmiňuje —
   * NEZNAMENÁ to „ne". Rozdíl se propisuje až do textu na stránce.
   */
  obchoduje: boolean | null;
  /** Kolik firma od města a jeho organizací dostala. */
  celkem_czk: number | null;
  smluv: number | null;
  zdroj: string | null;
}

export interface Sponzoring {
  strana: string | null;
  darce: string | null;
  osoba_id: string | null;
  ico: string | null;
  castka_czk: number | null;
  rok: number | null;
  datum: string | null;
  typ: string | null;
  zdroj: string | null;
}

export interface OsobaFirmy {
  osoba_id: string;
  jmeno: string | null;
  strana: string | null;
  firmy: FirmaOsoby[];
  sponzoring: Sponzoring[];
}

export interface PropojeniOsob {
  osoby: OsobaFirmy[];
  /** Sponzoring, který zdroj vede mimo jednotlivé osoby. */
  sponzoring: Sponzoring[];
}

function normalizujSponzoring(z: Zaznam, vychoziOsoba: string | null): Sponzoring {
  return {
    strana: txt(z, 'strana', 'prijemce', 'subjekt', 'politicka_strana'),
    darce: txt(z, 'darce', 'sponzor', 'od', 'jmeno', 'nazev'),
    osoba_id: txt(z, 'osoba_id', 'osoba', 'id') ?? vychoziOsoba,
    ico: ico(z, 'ico', 'darce_ico', 'firma_ico'),
    castka_czk: cis(z, 'castka_czk', 'castka', 'hodnota_czk', 'suma_czk', 'celkem_czk'),
    rok: cis(z, 'rok', 'year'),
    datum: txt(z, 'datum', 'date'),
    typ: txt(z, 'typ', 'druh', 'forma'),
    zdroj: txt(z, 'zdroj', 'url', 'odkaz'),
  };
}

function normalizujFirmu(z: Zaznam): FirmaOsoby {
  const celkem = cis(z, 'celkem_czk', 'od_mesta_czk', 'objem_czk', 'castka_czk', 'celkem', 'plneni_czk');
  const smluv = cis(z, 'smluv', 'pocet_smluv', 'smluv_s_mestem', 'smluv_celkem');
  let obchoduje = ano(
    z,
    'obchoduje_s_mestem',
    'obchoduje',
    'ma_smlouvu_s_mestem',
    'dodavatel_mesta',
    'vazba_na_mesto',
    'penize_od_mesta',
  );
  // Když příznak chybí, ale zdroj uvádí objem nebo počet smluv, plyne odpověď
  // přímo z čísla. Nic se nedohaduje — 0 Kč a 0 smluv je „neobchoduje".
  if (obchoduje === null && (celkem !== null || smluv !== null)) {
    obchoduje = (celkem ?? 0) > 0 || (smluv ?? 0) > 0;
  }
  return {
    ico: ico(z, 'ico', 'firma_ico', 'subjekt_ico'),
    nazev: txt(z, 'nazev', 'firma', 'obchodni_jmeno', 'subjekt', 'spolecnost') ?? 'Neuvedená firma',
    role: texty(z, 'role', 'funkce', 'pozice', 'vztah', 'angazma'),
    od: txt(z, 'od', 'plati_od', 'zacatek', 'od_data'),
    do: txt(z, 'do', 'plati_do', 'konec', 'do_data'),
    aktivni: ano(z, 'aktivni', 'aktivni_vazba', 'trva', 'aktualni'),
    obchoduje,
    celkem_czk: celkem,
    smluv,
    zdroj: txt(z, 'zdroj', 'url', 'odkaz'),
  };
}

export function nactiOsobyFirmy(): Nacteno<PropojeniOsob> {
  const v = nactiJson<unknown>('propojeni/osoby_firmy.json', null);
  const osoby: OsobaFirmy[] = [];
  const sponzoringGlobalni: Sponzoring[] = [];

  for (const z of korenSeznam(v.data, 'osoby', 'zastupitele', 'lide', 'propojeni', 'vazby')) {
    const id = txt(z, 'osoba_id', 'id', 'osoba');
    if (!id) continue;
    osoby.push({
      osoba_id: id,
      jmeno: txt(z, 'jmeno', 'nazev'),
      strana: txt(z, 'strana', 'uskupeni', 'politicka_prislusnost'),
      firmy: objekty(z, 'firmy', 'spolecnosti', 'subjekty', 'angazma', 'vazby').map(normalizujFirmu),
      sponzoring: objekty(z, 'sponzoring', 'dary', 'sponzorstvi').map((s) => normalizujSponzoring(s, id)),
    });
  }

  if (jeObjekt(v.data)) {
    for (const s of objekty(v.data, 'sponzoring', 'dary', 'sponzorstvi', 'sponzoring_stran')) {
      sponzoringGlobalni.push(normalizujSponzoring(s, null));
    }
  }

  return { ...v, data: { osoby, sponzoring: sponzoringGlobalni } };
}

/** Sponzoring dohromady — z osob i z globální sekce, ať leží kdekoliv. */
export function vsechenSponzoring(p: PropojeniOsob): Sponzoring[] {
  return [...p.sponzoring, ...p.osoby.flatMap((o) => o.sponzoring)];
}

/* ═════════════════════  propojeni/hlasovani_vazby.json  ════════════════ */

export interface VazbaHlasovani {
  hlasovani_id: string | null;
  bod: string | null;
  organ: string | null;
  datum: string | null;
  nazev: string | null;
  osoba_id: string | null;
  jmeno: string | null;
  /** Jak hlasoval. Věcný údaj, nic víc. */
  hlas: string | null;
  ico: string | null;
  firma: string | null;
  role: string[];
  /** Kolik firma od města dostala. */
  celkem_czk: number | null;
  smluv: number | null;
  zdroj: string | null;
}

function normalizujVazbuHlasovani(z: Zaznam, rodic: Zaznam | null): VazbaHlasovani {
  const zdrojHlasovani = rodic ?? z;
  return {
    hlasovani_id: txt(zdrojHlasovani, 'hlasovani_id', 'id_hlasovani', 'id'),
    bod: txt(zdrojHlasovani, 'bod', 'cislo_bodu'),
    organ: txt(zdrojHlasovani, 'organ'),
    datum: txt(zdrojHlasovani, 'datum', 'date'),
    nazev: txt(zdrojHlasovani, 'nazev', 'bod_nazev', 'predmet'),
    osoba_id: txt(z, 'osoba_id', 'osoba', 'id_osoby'),
    jmeno: txt(z, 'jmeno', 'osoba_jmeno'),
    hlas: txt(z, 'hlas', 'jak_hlasoval', 'vote'),
    ico: ico(z, 'ico', 'firma_ico', 'protistrana_ico', 'subjekt_ico'),
    firma: txt(z, 'firma', 'nazev_firmy', 'protistrana', 'subjekt', 'nazev'),
    role: texty(z, 'role', 'funkce', 'pozice', 'vztah'),
    celkem_czk: cis(z, 'celkem_czk', 'od_mesta_czk', 'firma_celkem_czk', 'objem_czk', 'castka_czk'),
    smluv: cis(z, 'smluv', 'pocet_smluv'),
    zdroj: txt(z, 'zdroj', 'url', 'odkaz'),
  };
}

export function nactiVazbyHlasovani(): Nacteno<VazbaHlasovani[]> {
  const v = nactiJson<unknown>('propojeni/hlasovani_vazby.json', null);
  const ven: VazbaHlasovani[] = [];

  for (const z of korenSeznam(v.data, 'vazby', 'hlasovani', 'polozky', 'zaznamy')) {
    // Dvě podoby: buď je záznam přímo jedna vazba (osoba + firma),
    // nebo je to hlasování se seznamem osob uvnitř.
    const vnorene = objekty(z, 'osoby', 'vazby', 'hlasujici', 'jmenovite');
    if (vnorene.length > 0) {
      for (const o of vnorene) ven.push(normalizujVazbuHlasovani(o, z));
    } else {
      ven.push(normalizujVazbuHlasovani(z, null));
    }
  }

  return { ...v, data: ven };
}

/** Vazby seskupené podle id hlasování — pro označení u konkrétního hlasování. */
export function vazbyPodleHlasovani(vazby: VazbaHlasovani[]): Map<string, VazbaHlasovani[]> {
  const m = new Map<string, VazbaHlasovani[]>();
  for (const v of vazby) {
    if (!v.hlasovani_id) continue;
    const pole = m.get(v.hlasovani_id);
    if (pole) pole.push(v);
    else m.set(v.hlasovani_id, [v]);
  }
  return m;
}

export function vazbyPodleOsoby(vazby: VazbaHlasovani[]): Map<string, VazbaHlasovani[]> {
  const m = new Map<string, VazbaHlasovani[]>();
  for (const v of vazby) {
    if (!v.osoba_id) continue;
    const pole = m.get(v.osoba_id);
    if (pole) pole.push(v);
    else m.set(v.osoba_id, [v]);
  }
  return m;
}

/* ════════════════════  propojeni/dodavatele_politici.json  ═════════════ */

export interface OsobaUDodavatele {
  osoba_id: string | null;
  jmeno: string | null;
  strana: string | null;
  role: string[];
  od: string | null;
  do: string | null;
}

export interface DodavatelSVazbou {
  ico: string | null;
  nazev: string;
  celkem_czk: number | null;
  smluv: number | null;
  prvni_rok: number | null;
  posledni_rok: number | null;
  osoby: OsobaUDodavatele[];
  zdroj: string | null;
}

export function nactiDodavatelePolitiky(): Nacteno<DodavatelSVazbou[]> {
  const v = nactiJson<unknown>('propojeni/dodavatele_politici.json', null);
  const ven: DodavatelSVazbou[] = [];

  for (const z of korenSeznam(v.data, 'dodavatele', 'firmy', 'protistrany', 'polozky')) {
    ven.push({
      ico: ico(z, 'ico', 'firma_ico', 'protistrana_ico'),
      nazev: txt(z, 'nazev', 'firma', 'protistrana', 'obchodni_jmeno') ?? 'Neuvedený dodavatel',
      celkem_czk: cis(z, 'celkem_czk', 'od_mesta_czk', 'objem_czk', 'castka_czk', 'celkem'),
      smluv: cis(z, 'smluv', 'pocet_smluv'),
      prvni_rok: cis(z, 'prvni_rok', 'od_roku'),
      posledni_rok: cis(z, 'posledni_rok', 'do_roku'),
      osoby: objekty(z, 'osoby', 'politici', 'vazby', 'lide').map((o) => ({
        osoba_id: txt(o, 'osoba_id', 'id', 'osoba'),
        jmeno: txt(o, 'jmeno', 'nazev'),
        strana: txt(o, 'strana', 'uskupeni'),
        role: texty(o, 'role', 'funkce', 'pozice', 'vztah'),
        od: txt(o, 'od', 'plati_od'),
        do: txt(o, 'do', 'plati_do'),
      })),
      zdroj: txt(z, 'zdroj', 'url', 'odkaz'),
    });
  }

  return { ...v, data: ven };
}

/**
 * Náhrada, když `dodavatele_politici.json` ještě není: totéž se dá poskládat
 * z `osoby_firmy.json`, protože tam je u firem příznak obchodování s městem.
 * Vrací se odděleně, aby stránka mohla napsat, odkud čísla jsou.
 */
export function dodavateleZOsob(p: PropojeniOsob): DodavatelSVazbou[] {
  const podleKlice = new Map<string, DodavatelSVazbou>();
  for (const o of p.osoby) {
    for (const f of o.firmy) {
      if (f.obchoduje !== true) continue;
      const klic = f.ico ?? `n-${f.nazev.toLowerCase()}`;
      let d = podleKlice.get(klic);
      if (!d) {
        d = {
          ico: f.ico,
          nazev: f.nazev,
          celkem_czk: f.celkem_czk,
          smluv: f.smluv,
          prvni_rok: null,
          posledni_rok: null,
          osoby: [],
          zdroj: f.zdroj,
        };
        podleKlice.set(klic, d);
      }
      d.osoby.push({
        osoba_id: o.osoba_id,
        jmeno: o.jmeno,
        strana: o.strana,
        role: f.role,
        od: f.od,
        do: f.do,
      });
    }
  }
  return [...podleKlice.values()].sort((a, b) => (b.celkem_czk ?? 0) - (a.celkem_czk ?? 0));
}

/* ═══════════════════════════  retez/*.json  ════════════════════════════ */

export type Jistota = 'vysoka' | 'stredni' | 'nizka' | null;

export interface UsneseniRetezu {
  organ: string | null;
  cj: string | null;
  bod: string | null;
  nazev: string | null;
  datum: string | null;
  castka_czk: number | null;
  url: string | null;
  hlasovani_id: string | null;
}

export interface SmlouvaRetezu {
  id: string | null;
  predmet: string | null;
  datum: string | null;
  castka_czk: number | null;
  protistrana: string | null;
  ico: string | null;
  url: string | null;
}

export interface Retez {
  id: string;
  jistota: Jistota;
  duvod: string | null;
  usneseni: UsneseniRetezu | null;
  smlouva: SmlouvaRetezu | null;
  /** Skutečně proplacené peníze, když je zdroj rozlišuje od ceny smlouvy. */
  penize_czk: number | null;
  plateb: number | null;
  rozdil_czk: number | null;
}

function normalizujJistotu(v: string | null): Jistota {
  if (!v) return null;
  const s = v.trim().toLowerCase();
  if (s.startsWith('vysok') || s === 'high') return 'vysoka';
  if (s.startsWith('stredn') || s.startsWith('střed') || s === 'medium') return 'stredni';
  if (s.startsWith('nizk') || s.startsWith('nízk') || s === 'low') return 'nizka';
  return null;
}

function normalizujUsneseni(z: Zaznam | null): UsneseniRetezu | null {
  if (!z) return null;
  const u: UsneseniRetezu = {
    organ: txt(z, 'organ'),
    cj: txt(z, 'cj', 'cislo_jednaci', 'cislo'),
    bod: txt(z, 'bod', 'cislo_bodu'),
    nazev: txt(z, 'nazev', 'predmet', 'text'),
    datum: txt(z, 'datum', 'date'),
    castka_czk: cis(z, 'castka_czk', 'castka', 'schvalena_castka_czk'),
    url: txt(z, 'url', 'odkaz', 'zdroj'),
    hlasovani_id: txt(z, 'hlasovani_id'),
  };
  return Object.values(u).some((x) => x !== null) ? u : null;
}

function normalizujSmlouvu(z: Zaznam | null): SmlouvaRetezu | null {
  if (!z) return null;
  const s: SmlouvaRetezu = {
    id: txt(z, 'id', 'smlouva_id'),
    predmet: txt(z, 'predmet', 'nazev', 'popis'),
    datum: txt(z, 'datum', 'date', 'uzavreno'),
    castka_czk: cis(z, 'castka_czk', 'castka', 'hodnota_czk', 'cena_czk'),
    protistrana: txt(z, 'protistrana', 'dodavatel', 'firma', 'nazev_protistrany'),
    ico: ico(z, 'protistrana_ico', 'ico', 'dodavatel_ico'),
    url: txt(z, 'url', 'odkaz', 'zdroj'),
  };
  return Object.values(s).some((x) => x !== null) ? s : null;
}

function vnorenyObjekt(z: Zaznam, ...klice: string[]): Zaznam | null {
  for (const k of klice) {
    const v = z[k];
    if (jeObjekt(v)) return v;
  }
  return null;
}

export function nactiRetezy(): Nacteno<Retez[]> {
  const v = nactiJson<unknown>('retez/retezy.json', null);
  const ven: Retez[] = [];

  korenSeznam(v.data, 'retezy', 'polozky', 'spojeni', 'zaznamy').forEach((z, i) => {
    const vnoreneU = vnorenyObjekt(z, 'usneseni', 'bod', 'bod_usneseni');
    const vnorenaS = vnorenyObjekt(z, 'smlouva', 'kontrakt');
    const penize = vnorenyObjekt(z, 'penize', 'plneni', 'platby');
    ven.push({
      id: txt(z, 'id', 'klic') ?? `retez-${i + 1}`,
      jistota: normalizujJistotu(txt(z, 'jistota', 'confidence', 'uroven_jistoty')),
      duvod: txt(z, 'duvod', 'zduvodneni', 'poznamka', 'reason'),
      // Když zdroj nemá vnořené objekty, zkusí se ploché klíče na kořeni.
      usneseni: normalizujUsneseni(vnoreneU ?? z),
      smlouva: normalizujSmlouvu(vnorenaS ?? z),
      penize_czk: cis(penize ?? z, 'celkem_czk', 'castka_czk', 'proplaceno_czk', 'penize_czk'),
      plateb: cis(penize ?? z, 'plateb', 'pocet_plateb'),
      rozdil_czk: cis(penize ?? z, 'rozdil_czk', 'rozdil'),
    });
  });

  return { ...v, data: ven };
}

export interface NespojenaSmlouva {
  id: string | null;
  predmet: string | null;
  datum: string | null;
  castka_czk: number | null;
  protistrana: string | null;
  ico: string | null;
  url: string | null;
  duvod: string | null;
}

export function nactiNespojene(): Nacteno<NespojenaSmlouva[]> {
  const v = nactiJson<unknown>('retez/nespojene.json', null);
  const ven: NespojenaSmlouva[] = [];

  for (const z of korenSeznam(v.data, 'nespojene', 'smlouvy', 'polozky', 'zaznamy')) {
    const s = normalizujSmlouvu(vnorenyObjekt(z, 'smlouva') ?? z);
    ven.push({
      id: s?.id ?? null,
      predmet: s?.predmet ?? null,
      datum: s?.datum ?? null,
      castka_czk: s?.castka_czk ?? null,
      protistrana: s?.protistrana ?? null,
      ico: s?.ico ?? null,
      url: s?.url ?? null,
      duvod: txt(z, 'duvod', 'zduvodneni', 'poznamka', 'reason'),
    });
  }

  ven.sort((a, b) => (b.castka_czk ?? 0) - (a.castka_czk ?? 0));
  return { ...v, data: ven };
}

/* ═══════════════════════  lide/profily.json  ═══════════════════════════ */

export interface PolozkaOdchylky {
  hlasovani_id: string | null;
  datum: string | null;
  nazev: string | null;
  hlas: string | null;
  /** Jak hlasovala většina vlastního uskupení. */
  vetsina: string | null;
}

export interface PolozkaVelkeCastky {
  hlasovani_id: string | null;
  datum: string | null;
  nazev: string | null;
  castka_czk: number | null;
  hlas: string | null;
  vysledek: string | null;
}

export interface ShodaSOsobou {
  osoba_id: string | null;
  jmeno: string | null;
  /** 0–1. */
  shoda: number | null;
  spolecnych: number | null;
}

export interface ProfilOsoby {
  osoba_id: string;
  ucast: { celkem: number | null; hlasoval: number | null; podil: number | null } | null;
  hlasy: Record<string, number>;
  podle_tagu: { tag: string; pocet: number }[];
  odchylky: { pocet: number | null; podil: number | null; polozky: PolozkaOdchylky[] };
  velke_castky: PolozkaVelkeCastky[];
  shoda: ShodaSOsobou[];
}

export interface Profily {
  profily: Map<string, ProfilOsoby>;
  /** Dvojice ze samostatné matice shody, když ji zdroj vede mimo profily. */
  matice: Map<string, ShodaSOsobou[]>;
}

const KLICE_HLASU = ['pro', 'proti', 'zdrzel', 'nehlasoval', 'nepritomen', 'omluven'];

function normalizujHlasy(z: Zaznam | null): Record<string, number> {
  const ven: Record<string, number> = {};
  const zdroj = z ?? {};
  for (const k of KLICE_HLASU) {
    const v = cis(zdroj, k);
    if (v !== null) ven[k] = v;
  }
  return ven;
}

function normalizujShodu(z: Zaznam): ShodaSOsobou {
  return {
    osoba_id: txt(z, 'osoba_id', 'id', 'osoba', 's_kym', 'b'),
    jmeno: txt(z, 'jmeno', 'nazev'),
    shoda: podil(z, 'shoda', 'podil', 'procento', 'hodnota'),
    spolecnych: cis(z, 'spolecnych', 'spolecnych_hlasovani', 'pocet', 'zaklad'),
  };
}

export function nactiProfily(): Nacteno<Profily> {
  const v = nactiJson<unknown>('lide/profily.json', null);
  const profily = new Map<string, ProfilOsoby>();
  const matice = new Map<string, ShodaSOsobou[]>();

  for (const z of korenSeznam(v.data, 'profily', 'osoby', 'lide')) {
    const id = txt(z, 'osoba_id', 'id', 'osoba');
    if (!id) continue;

    const ucastZ = vnorenyObjekt(z, 'ucast', 'dochazka');
    const celkem = cis(ucastZ ?? z, 'celkem', 'hlasovani_celkem', 'z_celkem', 'moznych');
    const hlasoval = cis(ucastZ ?? z, 'hlasoval', 'ucastnil_se', 'odevzdanych', 'pritomen');
    const podilUcasti = podil(ucastZ ?? z, 'podil', 'ucast', 'procento', 'podil_ucasti');

    const odchylkyZ = vnorenyObjekt(z, 'odchylky_od_strany', 'odchylky', 'odlisne_hlasy');

    profily.set(id, {
      osoba_id: id,
      ucast:
        celkem !== null || hlasoval !== null || podilUcasti !== null
          ? { celkem, hlasoval, podil: podilUcasti }
          : null,
      hlasy: normalizujHlasy(vnorenyObjekt(z, 'hlasy', 'rozlozeni', 'rozlozeni_hlasu') ?? z),
      podle_tagu: objekty(z, 'podle_tagu', 'tagy', 'aktivita_podle_tagu', 'temata')
        .map((t) => ({
          tag: txt(t, 'tag', 'id', 'nazev') ?? '',
          pocet: cis(t, 'pocet', 'hlasovani', 'count') ?? 0,
        }))
        .filter((t) => t.tag),
      odchylky: {
        pocet: cis(odchylkyZ ?? z, 'pocet', 'odchylek', 'celkem'),
        podil: podil(odchylkyZ ?? z, 'podil', 'procento'),
        polozky: objekty(odchylkyZ ?? z, 'polozky', 'hlasovani', 'seznam', 'odchylky').map((p) => ({
          hlasovani_id: txt(p, 'hlasovani_id', 'id'),
          datum: txt(p, 'datum'),
          nazev: txt(p, 'nazev', 'bod', 'predmet'),
          hlas: txt(p, 'hlas', 'jeho_hlas'),
          vetsina: txt(p, 'vetsina', 'vetsina_strany', 'strana_hlas', 'klub'),
        })),
      },
      velke_castky: objekty(z, 'velke_castky', 'velke_penize', 'vysoke_castky', 'castky').map((p) => ({
        hlasovani_id: txt(p, 'hlasovani_id', 'id'),
        datum: txt(p, 'datum'),
        nazev: txt(p, 'nazev', 'bod', 'predmet'),
        castka_czk: cis(p, 'castka_czk', 'castka'),
        hlas: txt(p, 'hlas'),
        vysledek: txt(p, 'vysledek'),
      })),
      shoda: objekty(z, 'shoda', 'matice_shody', 'shody', 'nejblize').map(normalizujShodu),
    });
  }

  // Matice shody vedená mimo profily: buď pole dvojic, nebo mapa mapa→číslo.
  if (jeObjekt(v.data)) {
    const m = v.data['matice_shody'] ?? v.data['matice'] ?? v.data['shoda'];
    if (Array.isArray(m)) {
      for (const p of m) {
        if (!jeObjekt(p)) continue;
        const a = txt(p, 'a', 'osoba_id', 'osoba_a', 'od');
        const b = txt(p, 'b', 'osoba_b', 's_kym', 'do');
        const hodnota = podil(p, 'shoda', 'podil', 'hodnota', 'procento');
        const spolecnych = cis(p, 'spolecnych', 'pocet', 'zaklad');
        if (!a || !b) continue;
        pridej(a, { osoba_id: b, jmeno: txt(p, 'jmeno_b', 'b_jmeno'), shoda: hodnota, spolecnych });
        pridej(b, { osoba_id: a, jmeno: txt(p, 'jmeno_a', 'a_jmeno'), shoda: hodnota, spolecnych });
      }
    } else if (jeObjekt(m)) {
      for (const [a, radek] of Object.entries(m)) {
        if (!jeObjekt(radek)) continue;
        for (const [b, hodnota] of Object.entries(radek)) {
          if (a === b) continue;
          const h = podil({ v: hodnota } as Zaznam, 'v');
          if (h === null) continue;
          pridej(a, { osoba_id: b, jmeno: null, shoda: h, spolecnych: null });
        }
      }
    }
  }

  function pridej(id: string, s: ShodaSOsobou) {
    const pole = matice.get(id);
    if (pole) pole.push(s);
    else matice.set(id, [s]);
  }

  return { ...v, data: { profily, matice } };
}

/** Shoda pro jednu osobu — z profilu, jinak ze samostatné matice. */
export function shodaOsoby(p: Profily, osobaId: string): ShodaSOsobou[] {
  const zProfilu = p.profily.get(osobaId)?.shoda ?? [];
  const zdroj = zProfilu.length > 0 ? zProfilu : (p.matice.get(osobaId) ?? []);
  return [...zdroj]
    .filter((s) => s.osoba_id && s.shoda !== null)
    .sort((a, b) => (b.shoda ?? 0) - (a.shoda ?? 0));
}

/** Procenta pro UI: 0,87 → „87 %". `null` → „—". */
export function procenta(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return `${(v * 100).toFixed(0)} %`;
}

/** Popisek jistoty párování. Text jde vždy s barvou, nikdy barva sama. */
export function popisJistoty(j: Jistota): {
  nazev: string;
  uroven: 'dobre' | 'pozor' | 'vazne' | 'neznamo';
  vysvetleni: string;
} {
  if (j === 'vysoka') {
    return {
      nazev: 'vysoká jistota',
      uroven: 'dobre',
      vysvetleni: 'Spojení je doložené shodným identifikátorem ve zdrojích.',
    };
  }
  if (j === 'stredni') {
    return {
      nazev: 'střední jistota',
      uroven: 'pozor',
      vysvetleni: 'Spojení vychází z shody více údajů, ale není potvrzené jedním identifikátorem.',
    };
  }
  if (j === 'nizka') {
    return {
      nazev: 'nízká jistota — odhad',
      uroven: 'vazne',
      vysvetleni:
        'Spojení je odhad podle podobnosti údajů. Může být chybné a nedá se z něj vyvozovat, že usnesení a smlouva spolu skutečně souvisejí.',
    };
  }
  return {
    nazev: 'jistota neuvedena',
    uroven: 'neznamo',
    vysvetleni: 'Zdroj u tohoto spojení neuvádí, jak jisté párování je.',
  };
}
