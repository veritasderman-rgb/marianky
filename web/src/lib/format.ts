/** Formátování čísel a dat pro české UI. Vše se počítá při buildu. */

const CZ = 'cs-CZ';

const fmtCele = new Intl.NumberFormat(CZ, { maximumFractionDigits: 0 });
const fmt1 = new Intl.NumberFormat(CZ, { minimumFractionDigits: 1, maximumFractionDigits: 1 });

/** Přesná částka: „12 400 000 Kč". Do tabulek a tooltipů. */
export function kc(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  return `${fmtCele.format(Math.round(n))} Kč`;
}

/** Zkrácená částka pro osy a dlaždice: „12,4 mil.". */
export function kcZkraceno(n: number | null | undefined, sJednotkou = false): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  const zn = n < 0 ? '−' : '';
  const a = Math.abs(n);
  const jed = sJednotkou ? ' Kč' : '';
  if (a >= 1e9) return `${zn}${fmt1.format(a / 1e9)} mld.${jed}`;
  if (a >= 1e6) return `${zn}${fmt1.format(a / 1e6)} mil.${jed}`;
  if (a >= 1e3) return `${zn}${fmtCele.format(Math.round(a / 1e3))} tis.${jed}`;
  return `${zn}${fmtCele.format(Math.round(a))}${jed}`;
}

export function cislo(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  return fmtCele.format(n);
}

const MESICE = [
  'ledna', 'února', 'března', 'dubna', 'května', 'června',
  'července', 'srpna', 'září', 'října', 'listopadu', 'prosince',
];

/** „7. srpna 2026" z ISO „2026-08-07". Nevalidní vstup vrací původní řetězec. */
export function datum(iso: string | null | undefined): string {
  if (!iso) return '—';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  const [, r, me, d] = m;
  const mi = Number(me) - 1;
  if (mi < 0 || mi > 11) return iso;
  return `${Number(d)}. ${MESICE[mi]} ${r}`;
}

/** Krátký tvar „7. 8. 2026" pro tabulky. */
export function datumKratke(iso: string | null | undefined): string {
  if (!iso) return '—';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${Number(m[3])}. ${Number(m[2])}. ${m[1]}`;
}

export function rokZData(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const m = /^(\d{4})/.exec(iso);
  return m ? Number(m[1]) : null;
}

/** České skloňování počtu: sklonuj(3, 'usnesení','usnesení','usnesení'). */
export function sklonuj(n: number, jeden: string, dva: string, pet: string): string {
  const a = Math.abs(n);
  if (a === 1) return jeden;
  if (a >= 2 && a <= 4) return dva;
  return pet;
}

/** Odstraní diakritiku — pro klientské filtrování a řazení. */
export function bezDiakritiky(s: string): string {
  return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

export function orderCs(a: string, b: string): number {
  return a.localeCompare(b, CZ);
}

export function nazevOrganu(o: string): string {
  if (o === 'rada') return 'Rada města';
  if (o === 'zastupitelstvo') return 'Zastupitelstvo';
  return o;
}

export function nazevVysledku(v: string): string {
  const m: Record<string, string> = {
    schvaleno: 'Schváleno',
    neschvaleno: 'Neschváleno',
    'staženo': 'Staženo',
    stazeno: 'Staženo',
    odlozeno: 'Odloženo',
  };
  return m[v] ?? v;
}

export function nazevHlasu(h: string): string {
  const m: Record<string, string> = {
    pro: 'pro',
    proti: 'proti',
    zdrzel: 'zdržel se',
    nehlasoval: 'nehlasoval',
    nepritomen: 'nepřítomen',
  };
  return m[h] ?? h;
}

/** Ořízne text na délku na hranici slova, s výpustkou. */
export function orez(s: string, max: number): string {
  if (!s) return '';
  if (s.length <= max) return s;
  const rez = s.slice(0, max);
  const mezera = rez.lastIndexOf(' ');
  return `${(mezera > max * 0.6 ? rez.slice(0, mezera) : rez).trimEnd()}…`;
}
