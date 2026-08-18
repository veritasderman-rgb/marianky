/**
 * Načítání propojení mezi samosprávou, firmami a penězi.
 *
 * Čte se tolerantně: u každého údaje se zkouší několik obvyklých názvů klíče
 * a přijímá se jak holé pole, tak objekt s obalovým klíčem. Důvod je prostý —
 * tyhle soubory vznikají v jiných modulech a jejich tvar se ještě může hnout.
 *
 * Dvě zásady, které se tu drží tvrdě:
 *
 *   1. `null` znamená „nezjištěno", nikdy nulu. Rozdíl se propisuje až do
 *      textu na stránce („v datech není" vs. „neobchoduje").
 *   2. Zdrojové soubory nesou vlastní `metodiku` — ta se zobrazuje tak, jak je,
 *      aby vysvětlení na webu odpovídalo tomu, jak data doopravdy vznikla.
 *      Web si žádné vlastní vysvětlení nevymýšlí.
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

/** První číselný údaj z uvedených klíčů. */
function cis(o: Zaznam | null | undefined, ...klice: string[]): number | null {
  if (!o) return null;
  for (const k of klice) {
    const v = o[k];
    if (typeof v === 'number' && Number.isFinite(v)) return v;
    if (typeof v === 'string') {
      const cisty = v.replace(/\s| /g, '').replace(',', '.');
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
  if (v === null || v < 0) return null;
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

function vnoreny(z: Zaznam | null | undefined, ...klice: string[]): Zaznam | null {
  if (!z) return null;
  for (const k of klice) {
    const v = z[k];
    if (jeObjekt(v)) return v;
  }
  return null;
}

/** IČO se v datech objevuje jako číslo i jako řetězec s vedoucí nulou. */
function ico(o: Zaznam | null | undefined, ...klice: string[]): string | null {
  const v = txt(o, ...klice);
  if (!v) return null;
  const cisty = v.replace(/\D/g, '');
  if (!cisty) return null;
  return cisty.length < 8 ? cisty.padStart(8, '0') : cisty;
}

/** Metodika ze zdrojového souboru — jen textové položky, ať se dá vypsat. */
export type Metodika = { klic: string; text: string }[];

function nactiMetodiku(data: unknown): Metodika {
  const m = jeObjekt(data) ? data['metodika'] : null;
  if (!jeObjekt(m)) return [];
  const ven: Metodika = [];
  for (const [klic, hodnota] of Object.entries(m)) {
    if (typeof hodnota === 'string' && hodnota.trim()) ven.push({ klic, text: hodnota.trim() });
  }
  return ven;
}

function rokZ(datum: string | null): number | null {
  if (!datum) return null;
  const m = /^(\d{4})/.exec(datum);
  return m ? Number(m[1]) : null;
}

/* ═══════════════════════  propojeni/osoby_firmy.json  ══════════════════ */

/* Typ i popis žijí v `vztahy.ts`, protože je potřebuje i skript v prohlížeči
   a tenhle soubor sahá na disk. Re-export je tu, aby se nemusely přepisovat
   importy po celém webu. */
export { popisVztahu, type VztahKMestu } from './vztahy';
import type { VztahKMestu } from './vztahy';

export interface FirmaOsoby {
  ico: string | null;
  nazev: string;
  url: string | null;
  /** Jak firma souvisí s městem. Rozlišuje městskou organizaci od cizí firmy. */
  vztah: VztahKMestu;
  mestsky: boolean | null;
  vlastnictvi: string | null;
  /** `null` = zdroj se o tom nezmiňuje. NENÍ to „ne". */
  obchoduje: boolean | null;
  od_mesta_czk: number | null;
  mestu_czk: number | null;
  smluv: number | null;
  prvni_rok: number | null;
  posledni_rok: number | null;
  aktivni: boolean | null;
  /** Role ve firmě, pokud ji zdroj u firmy vede. */
  role: string[];
}

export interface SponzoringZaznam {
  osoba_id: string | null;
  darce: string | null;
  strana: string | null;
  strana_ico: string | null;
  castka_czk: number | null;
  datum: string | null;
  rok: number | null;
  druh: string | null;
  popis: string | null;
}

export interface SponzoringOsoby {
  zaznamu: number | null;
  celkem_czk: number | null;
  /** Ví zdroj o tom, že má všechny záznamy? */
  uplne: boolean | null;
  strany: string[];
  zaznamy: SponzoringZaznam[];
}

export interface OsobaFirmy {
  osoba_id: string;
  jmeno: string | null;
  strana: string | null;
  kategorie: string | null;
  role: string[];
  firmy: FirmaOsoby[];
  /**
   * `false`, když zdroj u osoby vede `firmy: null` — tedy „nezjištěno".
   * Prázdný seznam u `true` znamená „zjištěno, žádná firma".
   */
  firmyZjisteny: boolean;
  overeni: { stav: string | null; kandidatu: number | null };
  hlidacUrl: string | null;
  angazovanost: string | null;
  souhrn: {
    celkem: number | null;
    mestskych: number | null;
    obchodujicich: number | null;
    bezVazby: number | null;
  } | null;
  sponzoring: SponzoringOsoby | null;
}

export interface PropojeniOsob {
  osoby: OsobaFirmy[];
  metodika: Metodika;
  souhrn: Zaznam | null;
}

function normalizujVztah(v: string | null): VztahKMestu {
  if (v === 'mestsky-subjekt' || v === 'obchoduje-s-mestem' || v === 'bez-vazby-na-mesto') return v;
  return null;
}

function normalizujFirmu(z: Zaznam): FirmaOsoby {
  const odMesta = cis(z, 'od_mesta_czk', 'celkem_od_mesta_czk', 'celkem_czk', 'objem_czk', 'castka_czk');
  const smluv = cis(z, 'smluv', 'pocet_smluv');
  const vztah = normalizujVztah(txt(z, 'vztah_k_mestu', 'vztah'));
  let obchoduje = ano(z, 'obchoduje_s_mestem', 'obchoduje', 'ma_smlouvu_s_mestem');
  // Když příznak chybí, plyne odpověď z popisu vztahu nebo z čísel.
  if (obchoduje === null && vztah !== null) obchoduje = vztah !== 'bez-vazby-na-mesto';
  if (obchoduje === null && (odMesta !== null || smluv !== null)) {
    obchoduje = (odMesta ?? 0) > 0 || (smluv ?? 0) > 0;
  }
  return {
    ico: ico(z, 'ico', 'firma_ico', 'subjekt_ico'),
    nazev: txt(z, 'nazev', 'firma', 'obchodni_jmeno', 'subjekt') ?? 'Neuvedená firma',
    url: txt(z, 'url', 'odkaz', 'zdroj'),
    vztah,
    mestsky: ano(z, 'mestsky_subjekt', 'mestska'),
    vlastnictvi: txt(z, 'vlastnictvi'),
    obchoduje,
    od_mesta_czk: odMesta,
    mestu_czk: cis(z, 'mestu_czk'),
    smluv,
    prvni_rok: cis(z, 'prvni_rok', 'od_roku'),
    posledni_rok: cis(z, 'posledni_rok', 'do_roku'),
    aktivni: ano(z, 'aktivni', 'trva'),
    role: texty(z, 'role', 'role_ve_firme', 'funkce', 'pozice', 'vztah_osoby'),
  };
}

function normalizujSponzoring(z: Zaznam | null, osobaId: string | null, jmeno: string | null): SponzoringOsoby | null {
  if (!z) return null;
  const zaznamy = objekty(z, 'zaznamy', 'polozky', 'dary').map((s) => {
    const datum = txt(s, 'datum', 'date');
    return {
      osoba_id: txt(s, 'osoba_id') ?? osobaId,
      darce: txt(s, 'darce', 'sponzor') ?? jmeno,
      strana: txt(s, 'strana', 'prijemce'),
      strana_ico: ico(s, 'strana_ico'),
      castka_czk: cis(s, 'castka_czk', 'castka', 'hodnota_czk'),
      datum,
      rok: cis(s, 'rok') ?? rokZ(datum),
      druh: txt(s, 'druh', 'typ', 'forma'),
      popis: txt(s, 'popis', 'poznamka'),
    };
  });
  return {
    zaznamu: cis(z, 'zaznamu', 'pocet') ?? (zaznamy.length > 0 ? zaznamy.length : null),
    celkem_czk: cis(z, 'celkem_czk', 'castka_czk'),
    uplne: ano(z, 'zaznamy_uplne', 'uplne'),
    strany: texty(z, 'strany'),
    zaznamy,
  };
}

export function nactiOsobyFirmy(): Nacteno<PropojeniOsob> {
  const v = nactiJson<unknown>('propojeni/osoby_firmy.json', null);
  const osoby: OsobaFirmy[] = [];

  for (const z of korenSeznam(v.data, 'osoby', 'zastupitele', 'lide', 'propojeni')) {
    const id = txt(z, 'osoba_id', 'id', 'osoba');
    if (!id) continue;
    const jmeno = txt(z, 'jmeno', 'nazev');
    const syroveFirmy = z['firmy'] ?? z['spolecnosti'] ?? z['subjekty'];
    const overeni = vnoreny(z, 'overeni');
    const hlidac = vnoreny(z, 'hlidac');
    const souhrn = vnoreny(z, 'souhrn_firem', 'souhrn');

    osoby.push({
      osoba_id: id,
      jmeno,
      strana: txt(z, 'strana', 'uskupeni', 'strana_posledni'),
      kategorie: txt(z, 'kategorie'),
      role: texty(z, 'role'),
      firmy: Array.isArray(syroveFirmy) ? syroveFirmy.filter(jeObjekt).map(normalizujFirmu) : [],
      firmyZjisteny: Array.isArray(syroveFirmy),
      overeni: {
        stav: txt(overeni, 'stav'),
        kandidatu: cis(overeni, 'kandidatu'),
      },
      hlidacUrl: txt(hlidac, 'url'),
      angazovanost: txt(hlidac, 'angazovanost'),
      souhrn: souhrn
        ? {
            celkem: cis(souhrn, 'celkem'),
            mestskych: cis(souhrn, 'mestskych_subjektu', 'mestskych'),
            obchodujicich: cis(souhrn, 'obchodujicich_s_mestem', 'obchodujicich'),
            bezVazby: cis(souhrn, 'bez_vazby_na_mesto', 'bez_vazby'),
          }
        : null,
      sponzoring: normalizujSponzoring(vnoreny(z, 'sponzoring'), id, jmeno),
    });
  }

  return {
    ...v,
    data: {
      osoby,
      metodika: nactiMetodiku(v.data),
      souhrn: jeObjekt(v.data) && jeObjekt(v.data['souhrn']) ? (v.data['souhrn'] as Zaznam) : null,
    },
  };
}

/** Všechny záznamy sponzoringu napříč osobami. */
export function vsechenSponzoring(p: PropojeniOsob): SponzoringZaznam[] {
  return p.osoby.flatMap((o) => o.sponzoring?.zaznamy ?? []);
}

/** Popis stavu ověření identity. Text, ne barva — a nikdy jako obvinění. */
export function popisOvereni(stav: string | null): string {
  const m: Record<string, string> = {
    potvrzeno: 'identita v rejstříku potvrzena',
    pravdepodobne: 'identita pravděpodobná, ne jistá',
    nejednoznacne: 'identitu se nepodařilo jednoznačně určit',
    nenalezeno: 'osoba se v rejstříku nenašla',
  };
  return stav ? (m[stav] ?? stav) : 'stav ověření v datech není';
}

/* ═════════════════════  propojeni/hlasovani_vazby.json  ════════════════ */

export interface VazbaHlasovani {
  hlasovani_id: string | null;
  bod: string | null;
  organ: string | null;
  datum: string | null;
  nazev: string | null;
  url: string | null;
  castka_czk: number | null;
  osoba_id: string | null;
  jmeno: string | null;
  strana: string | null;
  /** Jak hlasoval. Věcný údaj, nic víc. */
  hlas: string | null;
  role: string[];
  zdrojRole: string[];
  overeni: string | null;
  ico: string | null;
  firma: string | null;
  firmaUrl: string | null;
  vztah: VztahKMestu;
  /** Kolik firma od města dostala. */
  od_mesta_czk: number | null;
  nalezenoDle: string[];
}

export interface VazbyHlasovani {
  vazby: VazbaHlasovani[];
  metodika: Metodika;
  souhrn: Zaznam | null;
}

export function nactiVazbyHlasovani(): Nacteno<VazbyHlasovani> {
  const v = nactiJson<unknown>('propojeni/hlasovani_vazby.json', null);
  const ven: VazbaHlasovani[] = [];

  for (const z of korenSeznam(v.data, 'vazby', 'hlasovani', 'polozky', 'zaznamy')) {
    const firma = vnoreny(z, 'firma', 'subjekt') ?? z;
    const spolecne = {
      hlasovani_id: txt(z, 'hlasovani_id', 'id_hlasovani', 'id'),
      bod: txt(z, 'bod', 'cislo_bodu'),
      organ: txt(z, 'organ'),
      datum: txt(z, 'datum'),
      nazev: txt(z, 'nazev', 'bod_nazev'),
      url: txt(z, 'url'),
      castka_czk: cis(z, 'castka_czk'),
      ico: ico(firma, 'ico', 'firma_ico', 'protistrana_ico'),
      firma: txt(firma, 'nazev', 'firma', 'protistrana'),
      firmaUrl: txt(firma, 'url'),
      vztah: normalizujVztah(txt(firma, 'vztah_k_mestu')),
      od_mesta_czk: cis(firma, 'od_mesta_czk', 'celkem_czk', 'firma_celkem_czk'),
      nalezenoDle: texty(firma, 'nalezeno_dle'),
    };

    // Buď je uvnitř seznam hlasujících, nebo je záznam sám o jedné osobě.
    const hlasujici = objekty(z, 'hlasujici', 'osoby', 'vazby', 'jmenovite');
    const zdroje = hlasujici.length > 0 ? hlasujici : [z];

    for (const o of zdroje) {
      ven.push({
        ...spolecne,
        osoba_id: txt(o, 'osoba_id', 'osoba', 'id_osoby'),
        jmeno: txt(o, 'jmeno', 'osoba_jmeno'),
        strana: txt(o, 'strana', 'uskupeni'),
        hlas: txt(o, 'hlas', 'jak_hlasoval'),
        role: texty(o, 'role_ve_firme', 'role', 'funkce', 'pozice'),
        zdrojRole: texty(o, 'zdroj_role', 'zdroj'),
        overeni: txt(o, 'overeni_osoby', 'overeni'),
      });
    }
  }

  return {
    ...v,
    data: {
      vazby: ven,
      metodika: nactiMetodiku(v.data),
      souhrn: jeObjekt(v.data) && jeObjekt(v.data['souhrn']) ? (v.data['souhrn'] as Zaznam) : null,
    },
  };
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

/* ════════════════════  propojeni/dodavatele_politici.json  ═════════════ */

export interface OsobaUDodavatele {
  osoba_id: string | null;
  jmeno: string | null;
  strana: string | null;
  role: string[];
  zaklad: string[];
  zdroj: string | null;
  overeni: string | null;
  smluv: number | null;
  castka_czk: number | null;
}

export interface DodavatelSVazbou {
  ico: string | null;
  nazev: string;
  url: string | null;
  mestsky: boolean | null;
  vlastnictvi: string | null;
  od_mesta_czk: number | null;
  mestu_czk: number | null;
  smluv: number | null;
  prvni_rok: number | null;
  posledni_rok: number | null;
  aktivni: boolean | null;
  po_letech: Record<string, number>;
  osoby: OsobaUDodavatele[];
}

export interface Dodavatele {
  dodavatele: DodavatelSVazbou[];
  metodika: Metodika;
  souhrn: Zaznam | null;
}

function poLetech(z: Zaznam | null): Record<string, number> {
  const m = vnoreny(z, 'po_letech');
  if (!m) return {};
  const ven: Record<string, number> = {};
  for (const [rok, v] of Object.entries(m)) {
    if (typeof v === 'number' && Number.isFinite(v)) ven[rok] = v;
  }
  return ven;
}

export function nactiDodavatelePolitiky(): Nacteno<Dodavatele> {
  const v = nactiJson<unknown>('propojeni/dodavatele_politici.json', null);
  const ven: DodavatelSVazbou[] = [];

  for (const z of korenSeznam(v.data, 'dodavatele', 'firmy', 'protistrany', 'polozky')) {
    ven.push({
      ico: ico(z, 'ico', 'firma_ico', 'protistrana_ico'),
      nazev: txt(z, 'nazev', 'firma', 'protistrana') ?? 'Neuvedený dodavatel',
      url: txt(z, 'url'),
      mestsky: ano(z, 'mestsky_subjekt'),
      vlastnictvi: txt(z, 'vlastnictvi'),
      od_mesta_czk: cis(z, 'celkem_od_mesta_czk', 'od_mesta_czk', 'celkem_czk', 'castka_czk'),
      mestu_czk: cis(z, 'mestu_czk'),
      smluv: cis(z, 'smluv', 'pocet_smluv'),
      prvni_rok: cis(z, 'prvni_rok'),
      posledni_rok: cis(z, 'posledni_rok'),
      aktivni: ano(z, 'aktivni'),
      po_letech: poLetech(z),
      osoby: objekty(z, 'osoby', 'politici', 'lide').map((o) => ({
        osoba_id: txt(o, 'osoba_id', 'id', 'osoba'),
        jmeno: txt(o, 'jmeno', 'nazev'),
        strana: txt(o, 'strana', 'uskupeni'),
        role: texty(o, 'role', 'funkce', 'pozice'),
        zaklad: texty(o, 'zaklad'),
        zdroj: txt(o, 'zdroj', 'url'),
        overeni: txt(o, 'overeni_osoby', 'overeni'),
        smluv: cis(o, 'smluv_s_holdingem', 'smluv'),
        castka_czk: cis(o, 'castka_smluv_czk', 'castka_czk'),
      })),
    });
  }

  return {
    ...v,
    data: {
      dodavatele: ven,
      metodika: nactiMetodiku(v.data),
      souhrn: jeObjekt(v.data) && jeObjekt(v.data['souhrn']) ? (v.data['souhrn'] as Zaznam) : null,
    },
  };
}

/**
 * Náhrada, když `dodavatele_politici.json` ještě není: totéž se dá poskládat
 * z `osoby_firmy.json`. Vrací se odděleně, aby stránka mohla napsat, odkud
 * čísla pocházejí.
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
          url: f.url,
          mestsky: f.mestsky,
          vlastnictvi: f.vlastnictvi,
          od_mesta_czk: f.od_mesta_czk,
          mestu_czk: f.mestu_czk,
          smluv: f.smluv,
          prvni_rok: f.prvni_rok,
          posledni_rok: f.posledni_rok,
          aktivni: f.aktivni,
          po_letech: {},
          osoby: [],
        };
        podleKlice.set(klic, d);
      }
      d.osoby.push({
        osoba_id: o.osoba_id,
        jmeno: o.jmeno,
        strana: o.strana,
        role: f.role.length > 0 ? f.role : o.role,
        zaklad: [],
        zdroj: f.url,
        overeni: o.overeni.stav,
        smluv: f.smluv,
        castka_czk: f.od_mesta_czk,
      });
    }
  }
  return [...podleKlice.values()].sort((a, b) => (b.od_mesta_czk ?? 0) - (a.od_mesta_czk ?? 0));
}

/* ═══════════════════════════  retez/*.json  ════════════════════════════ */

export type Jistota = 'vysoka' | 'stredni' | 'nizka' | 'varovani' | null;

export interface UsneseniRetezu {
  organ: string | null;
  cj: string | null;
  bod: string | null;
  cislo_usneseni: string | null;
  nazev: string | null;
  datum: string | null;
  castka_czk: number | null;
  url: string | null;
  hlasovani_id: string | null;
  tagy: string[];
}

export interface SmlouvaRetezu {
  id: string | null;
  predmet: string | null;
  datum: string | null;
  castka_czk: number | null;
  protistrana: string | null;
  ico: string | null;
  /** Který subjekt města smlouvu uzavřel. */
  subjekt: string | null;
  smer: string | null;
  vada: boolean | null;
  url: string | null;
}

export interface Retez {
  id: string;
  jistota: Jistota;
  duvod: string | null;
  signaly: string[];
  skore: number | null;
  odstup_dni: number | null;
  kandidatu_usneseni: number | null;
  kandidatu_smluv: number | null;
  usneseni: UsneseniRetezu | null;
  smlouva: SmlouvaRetezu | null;
  /** Souhrn plateb protistraně — ne platby k této smlouvě. */
  protistrana_celkem_czk: number | null;
  protistrana_smluv: number | null;
  /** `true` u vnitřních převodů v rámci města. */
  interni: boolean | null;
}

export interface Retezy {
  retezy: Retez[];
  /** Smlouvy podepsané před usnesením — zdroj je vede zvlášť jako varování. */
  varovani: Retez[];
  metodika: Metodika;
  jistoty: Record<string, string>;
  statistika: Zaznam | null;
}

function normalizujJistotu(v: string | null): Jistota {
  if (!v) return null;
  const s = v.trim().toLowerCase();
  if (s.startsWith('vysok') || s === 'high') return 'vysoka';
  if (s.startsWith('stredn') || s.startsWith('střed') || s === 'medium') return 'stredni';
  if (s.startsWith('nizk') || s.startsWith('nízk') || s === 'low') return 'nizka';
  if (s.startsWith('varov')) return 'varovani';
  return null;
}

function maHodnotu(o: object): boolean {
  return Object.values(o).some((x) => x !== null && !(Array.isArray(x) && x.length === 0));
}

function normalizujUsneseni(z: Zaznam | null): UsneseniRetezu | null {
  if (!z) return null;
  const u: UsneseniRetezu = {
    organ: txt(z, 'organ'),
    cj: txt(z, 'cj', 'cislo_jednaci'),
    bod: txt(z, 'bod'),
    cislo_usneseni: txt(z, 'cislo_usneseni'),
    nazev: txt(z, 'nazev', 'predmet'),
    datum: txt(z, 'datum'),
    castka_czk: cis(z, 'castka_czk', 'castka'),
    url: txt(z, 'url', 'odkaz'),
    hlasovani_id: txt(z, 'hlasovani_id'),
    tagy: texty(z, 'tagy'),
  };
  return maHodnotu(u) ? u : null;
}

function normalizujSmlouvu(z: Zaznam | null): SmlouvaRetezu | null {
  if (!z) return null;
  const s: SmlouvaRetezu = {
    id: txt(z, 'id', 'smlouva_id'),
    predmet: txt(z, 'predmet', 'nazev', 'popis'),
    datum: txt(z, 'datum', 'uzavreno'),
    castka_czk: cis(z, 'castka_czk', 'castka', 'hodnota_czk'),
    protistrana: txt(z, 'protistrana', 'dodavatel'),
    ico: ico(z, 'protistrana_ico', 'ico'),
    subjekt: txt(z, 'subjekt'),
    smer: txt(z, 'smer'),
    vada: ano(z, 'vada'),
    url: txt(z, 'url', 'odkaz'),
  };
  return maHodnotu(s) ? s : null;
}

function normalizujRetez(z: Zaznam, i: number): Retez {
  const penize = vnoreny(z, 'penize', 'plneni');
  return {
    id: txt(z, 'id', 'klic') ?? `retez-${i + 1}`,
    jistota: normalizujJistotu(txt(z, 'jistota', 'uroven_jistoty')),
    duvod: txt(z, 'duvod', 'zduvodneni', 'poznamka'),
    signaly: texty(z, 'signaly'),
    skore: cis(z, 'skore'),
    odstup_dni: cis(z, 'odstup_dni'),
    kandidatu_usneseni: cis(z, 'kandidatu_usneseni'),
    kandidatu_smluv: cis(z, 'kandidatu_smluv'),
    usneseni: normalizujUsneseni(vnoreny(z, 'usneseni', 'bod_usneseni') ?? z),
    smlouva: normalizujSmlouvu(vnoreny(z, 'smlouva', 'kontrakt') ?? z),
    protistrana_celkem_czk: cis(penize, 'protistrana_celkem_czk', 'celkem_czk'),
    protistrana_smluv: cis(penize, 'protistrana_smluv', 'smluv'),
    interni: ano(penize, 'interni'),
  };
}

export function nactiRetezy(): Nacteno<Retezy> {
  const v = nactiJson<unknown>('retez/retezy.json', null);
  const retezy = korenSeznam(v.data, 'retezy', 'polozky', 'spojeni').map(normalizujRetez);
  const varovani = (
    jeObjekt(v.data) && Array.isArray(v.data['podpis_pred_usnesenim'])
      ? (v.data['podpis_pred_usnesenim'] as unknown[]).filter(jeObjekt)
      : []
  ).map(normalizujRetez);

  const jistotyZdroje = jeObjekt(v.data) ? vnoreny(v.data as Zaznam, 'metodika') : null;
  const jistoty: Record<string, string> = {};
  const j = vnoreny(jistotyZdroje, 'jistota');
  if (j) {
    for (const [k, text] of Object.entries(j)) {
      if (typeof text === 'string') jistoty[k] = text;
    }
  }

  return {
    ...v,
    data: {
      retezy,
      varovani,
      metodika: nactiMetodiku(v.data),
      jistoty,
      statistika: jeObjekt(v.data) && jeObjekt(v.data['statistika']) ? (v.data['statistika'] as Zaznam) : null,
    },
  };
}

export interface NespojenaSmlouva {
  id: string | null;
  predmet: string | null;
  datum: string | null;
  castka_czk: number | null;
  protistrana: string | null;
  ico: string | null;
  subjekt: string | null;
  smer: string | null;
  url: string | null;
  poznamka: string | null;
  neurcena: boolean | null;
}

export interface NespojeneUsneseni {
  organ: string | null;
  cj: string | null;
  bod: string | null;
  nazev: string | null;
  datum: string | null;
  castka_czk: number | null;
  /** Zdroj varuje, že částka může být špatně vyparsovaná. */
  castka_podezrela: boolean | null;
  poznamka_k_castce: string | null;
  url: string | null;
  tagy: string[];
}

export interface Nespojene {
  smlouvy: NespojenaSmlouva[];
  usneseni: NespojeneUsneseni[];
  prah_czk: number | null;
  metodika: Metodika;
}

export function nactiNespojene(): Nacteno<Nespojene> {
  const v = nactiJson<unknown>('retez/nespojene.json', null);

  const smlouvy: NespojenaSmlouva[] = korenSeznam(
    v.data,
    'smlouvy_bez_usneseni',
    'nespojene',
    'smlouvy',
    'polozky',
  ).map((z) => {
    const s = normalizujSmlouvu(vnoreny(z, 'smlouva') ?? z);
    return {
      id: s?.id ?? null,
      predmet: s?.predmet ?? null,
      datum: s?.datum ?? null,
      castka_czk: s?.castka_czk ?? null,
      protistrana: s?.protistrana ?? null,
      ico: s?.ico ?? null,
      subjekt: s?.subjekt ?? null,
      smer: s?.smer ?? null,
      url: s?.url ?? null,
      poznamka: txt(z, 'poznamka', 'duvod', 'zduvodneni'),
      neurcena: ano(z, 'protistrana_neurcena'),
    };
  });

  const usneseni: NespojeneUsneseni[] = (
    jeObjekt(v.data) && Array.isArray(v.data['usneseni_bez_smlouvy'])
      ? (v.data['usneseni_bez_smlouvy'] as unknown[]).filter(jeObjekt)
      : []
  ).map((z) => ({
    organ: txt(z, 'organ'),
    cj: txt(z, 'cj'),
    bod: txt(z, 'bod'),
    nazev: txt(z, 'nazev'),
    datum: txt(z, 'datum'),
    castka_czk: cis(z, 'castka_czk'),
    castka_podezrela: ano(z, 'castka_podezrela'),
    poznamka_k_castce: txt(z, 'poznamka_k_castce'),
    url: txt(z, 'url'),
    tagy: texty(z, 'tagy'),
  }));

  smlouvy.sort((a, b) => (b.castka_czk ?? 0) - (a.castka_czk ?? 0));
  usneseni.sort((a, b) => (b.castka_czk ?? 0) - (a.castka_czk ?? 0));

  return {
    ...v,
    data: {
      smlouvy,
      usneseni,
      prah_czk: jeObjekt(v.data) ? cis(v.data as Zaznam, 'prah_czk') : null,
      metodika: nactiMetodiku(v.data),
    },
  };
}

/**
 * Popisek jistoty párování. Text jde vždy s barvou, nikdy barva sama.
 * Vysvětlení se přebírá ze `metodika.jistota` zdrojového souboru, aby na webu
 * stálo přesně to, podle čeho se párovalo.
 */
export function popisJistoty(
  j: Jistota,
  zeZdroje: Record<string, string> = {},
): { nazev: string; uroven: 'dobre' | 'pozor' | 'vazne' | 'neznamo'; vysvetleni: string } {
  const zaklad: Record<string, { nazev: string; uroven: 'dobre' | 'pozor' | 'vazne' | 'neznamo'; vysvetleni: string }> = {
    vysoka: {
      nazev: 'vysoká jistota',
      uroven: 'dobre',
      vysvetleni: 'Spojení stojí na tvrdé shodě identifikátorů.',
    },
    stredni: {
      nazev: 'střední jistota',
      uroven: 'pozor',
      vysvetleni: 'Identita a čas sedí, jedna z tvrdých indicií ale chybí.',
    },
    nizka: {
      nazev: 'nízká jistota — nepotvrzená domněnka',
      uroven: 'vazne',
      vysvetleni:
        'Sedí jen identita protistrany. Je to domněnka, ne zjištění — že smlouva vznikla z tohoto usnesení, doložené není.',
    },
    varovani: {
      nazev: 'smlouva podepsaná před usnesením',
      uroven: 'pozor',
      vysvetleni:
        'Údaje si odpovídají, ale smlouva je podepsaná dřív než usnesení. Zdroj to proto nevede jako spojení, ale jako upozornění.',
    },
  };
  const klic = j ?? '';
  const zakladni = zaklad[klic] ?? {
    nazev: 'jistota neuvedena',
    uroven: 'neznamo' as const,
    vysvetleni: 'Zdroj u tohoto spojení neuvádí, jak jisté párování je.',
  };
  const text = zeZdroje[klic];
  return text ? { ...zakladni, vysvetleni: text } : zakladni;
}

/* ═══════════════════════  lide/profily.json  ═══════════════════════════ */

/** Řez hlasováním — používá se pro celek, orgán, rok i téma. */
export interface Rez {
  prilezitosti: number | null;
  pro: number | null;
  proti: number | null;
  zdrzel: number | null;
  nehlasoval: number | null;
  omluven: number | null;
  nepritomen: number | null;
  pritomen: number | null;
  hlasoval: number | null;
  neucast: number | null;
  podil_pritomen: number | null;
  podil_hlasoval: number | null;
  /** `true`, když je základna malá — pak se ukazují počty, ne procenta. */
  maly_vzorek: boolean;
}

export interface RezTematu extends Rez {
  tag: string;
  nazev: string | null;
}

export interface ShodaSOsobou {
  osoba_id: string | null;
  jmeno: string | null;
  /** 0–1. */
  podil: number | null;
  spolecnych: number | null;
  shodnych: number | null;
  maly_vzorek: boolean;
}

export interface ProfilOsoby {
  osoba_id: string;
  jmeno: string | null;
  role: string[];
  strany: string[];
  organy: string[];
  prvni: string | null;
  posledni: string | null;
  celek: Rez | null;
  podleOrganu: { organ: string; rez: Rez }[];
  podleTagu: RezTematu[];
  velkeCastky: (Rez & { prah_czk: number | null }) | null;
  shodaSVetsinou: { z: number | null; shodnych: number | null; podil: number | null; odlisnych: number | null; jediny: number | null; maly_vzorek: boolean } | null;
  odchylky: { porovnatelnych: number | null; odchylek: number | null; podil: number | null; maly_vzorek: boolean } | null;
  nejcastejiShodne: ShodaSOsobou[];
  nejcastejiOdlisne: ShodaSOsobou[];
  /** Jak velká část neúčastí má rozlišené omluvy. */
  rozliseniOmluv: { prilezitosti: number | null; sRozlisenim: number | null; podil: number | null } | null;
}

export interface Profily {
  profily: Map<string, ProfilOsoby>;
  metodika: Metodika;
  /** Od kdy je příznak omluvy ve zdroji spolehlivý, po orgánech. */
  omluvySpolehliveOd: { organ: string; od: string }[];
  zdroj: Zaznam | null;
}

function normalizujRez(z: Zaznam | null): Rez | null {
  if (!z) return null;
  const r: Rez = {
    prilezitosti: cis(z, 'prilezitosti', 'celkem', 'hlasovani_celkem'),
    pro: cis(z, 'pro'),
    proti: cis(z, 'proti'),
    zdrzel: cis(z, 'zdrzel'),
    nehlasoval: cis(z, 'nehlasoval'),
    omluven: cis(z, 'omluven'),
    nepritomen: cis(z, 'nepritomen'),
    pritomen: cis(z, 'pritomen'),
    hlasoval: cis(z, 'hlasoval'),
    neucast: cis(z, 'neucast'),
    podil_pritomen: podil(z, 'podil_pritomen'),
    podil_hlasoval: podil(z, 'podil_hlasoval', 'podil'),
    maly_vzorek: ano(z, 'maly_vzorek') === true,
  };
  return r.prilezitosti === null && r.hlasoval === null ? null : r;
}

function normalizujShoduSOsobou(z: Zaznam): ShodaSOsobou {
  return {
    osoba_id: txt(z, 'id', 'osoba_id', 'b'),
    jmeno: txt(z, 'jmeno', 'b_jmeno'),
    podil: podil(z, 'podil', 'shoda'),
    spolecnych: cis(z, 'spolecnych'),
    shodnych: cis(z, 'shodnych'),
    maly_vzorek: ano(z, 'maly_vzorek') === true,
  };
}

export function nactiProfily(): Nacteno<Profily> {
  const v = nactiJson<unknown>('lide/profily.json', null);
  const profily = new Map<string, ProfilOsoby>();

  for (const z of korenSeznam(v.data, 'profily', 'osoby', 'lide')) {
    const id = txt(z, 'id', 'osoba_id', 'osoba');
    if (!id) continue;

    const organy = vnoreny(z, 'po_organech');
    const shodaVetsina = vnoreny(z, 'shoda_s_vetsinou');
    const odchylky = vnoreny(z, 'odchylky_od_strany', 'odchylky');
    const velke = vnoreny(z, 'velke_castky');
    const rozliseni = vnoreny(z, 'rozliseni_omluv');
    const rezVelkych = normalizujRez(velke);

    profily.set(id, {
      osoba_id: id,
      jmeno: txt(z, 'jmeno'),
      role: texty(z, 'role'),
      strany: texty(z, 'strany'),
      organy: texty(z, 'organy'),
      prvni: txt(z, 'prvni_hlasovani'),
      posledni: txt(z, 'posledni_hlasovani'),
      celek: normalizujRez(vnoreny(z, 'ucast')),
      podleOrganu: organy
        ? Object.entries(organy)
            .map(([organ, rez]) => ({ organ, rez: normalizujRez(jeObjekt(rez) ? rez : null) }))
            .filter((x): x is { organ: string; rez: Rez } => x.rez !== null)
        : [],
      podleTagu: objekty(z, 'podle_tagu', 'tagy', 'temata')
        .map((t) => {
          const rez = normalizujRez(t);
          const tag = txt(t, 'tag', 'id');
          return rez && tag ? { ...rez, tag, nazev: txt(t, 'nazev') } : null;
        })
        .filter((t): t is RezTematu => t !== null),
      velkeCastky: rezVelkych ? { ...rezVelkych, prah_czk: cis(velke, 'prah_czk') } : null,
      shodaSVetsinou: shodaVetsina
        ? {
            z: cis(shodaVetsina, 'z_hlasovani'),
            shodnych: cis(shodaVetsina, 'shodnych'),
            podil: podil(shodaVetsina, 'podil'),
            odlisnych: cis(shodaVetsina, 'odlisnych'),
            jediny: cis(shodaVetsina, 'jediny_odlisny'),
            maly_vzorek: ano(shodaVetsina, 'maly_vzorek') === true,
          }
        : null,
      odchylky: odchylky
        ? {
            porovnatelnych: cis(odchylky, 'porovnatelnych'),
            odchylek: cis(odchylky, 'odchylek', 'pocet'),
            podil: podil(odchylky, 'podil'),
            maly_vzorek: ano(odchylky, 'maly_vzorek') === true,
          }
        : null,
      nejcastejiShodne: objekty(z, 'nejcasteji_shodne', 'shoda').map(normalizujShoduSOsobou),
      nejcastejiOdlisne: objekty(z, 'nejcasteji_odlisne').map(normalizujShoduSOsobou),
      rozliseniOmluv: rozliseni
        ? {
            prilezitosti: cis(rozliseni, 'prilezitosti'),
            sRozlisenim: cis(rozliseni, 's_rozlisenim'),
            podil: podil(rozliseni, 'podil'),
          }
        : null,
    });
  }

  const dostupnost = jeObjekt(v.data) ? vnoreny(v.data as Zaznam, 'dostupnost_omluv') : null;
  const omluvySpolehliveOd: { organ: string; od: string }[] = [];
  if (dostupnost) {
    for (const [organ, hodnota] of Object.entries(dostupnost)) {
      const od = jeObjekt(hodnota) ? txt(hodnota, 'spolehlive_od') : null;
      if (od) omluvySpolehliveOd.push({ organ, od });
    }
  }

  return {
    ...v,
    data: {
      profily,
      metodika: nactiMetodiku(v.data),
      omluvySpolehliveOd,
      zdroj: jeObjekt(v.data) && jeObjekt(v.data['zdroj']) ? (v.data['zdroj'] as Zaznam) : null,
    },
  };
}

/**
 * Procenta pro UI: 0,87 → „87 %". `null` → „—".
 *
 * Hodnoty pod jedno procento se zaokrouhlují na desetiny: „0 %" u nenulového
 * počtu by tvrdilo, že se to nestalo, a to je rozdíl, na kterém tady záleží.
 */
export function procenta(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  const p = v * 100;
  const text = p > 0 && p < 1 ? p.toFixed(1).replace('.', ',') : p.toFixed(0);
  return `${text} %`;
}
