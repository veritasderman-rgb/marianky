/** Formátování čísel a dat pro české UI. */

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

/** Měsíce v 1. pádě — pro tvar bez dne („březen 2015"). */
const MESICE_1 = [
  'leden', 'únor', 'březen', 'duben', 'květen', 'červen',
  'červenec', 'srpen', 'září', 'říjen', 'listopad', 'prosinec',
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

/**
 * Datum v té přesnosti, kterou zdroj uvádí — rok, měsíc i den.
 * „2022-09-23" → „23. září 2022", „2015-03" → „březen 2015", „2012" → „2012".
 * Nerozpoznaný tvar se vrací beze změny, nikdy se nic nedomýšlí.
 */
export function datumVolne(iso: string | null | undefined): string {
  if (!iso) return '—';
  const s = String(iso).trim();
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return datum(s);
  const m = /^(\d{4})-(\d{2})$/.exec(s);
  if (m) {
    const mi = Number(m[2]) - 1;
    if (mi >= 0 && mi <= 11) return `${MESICE_1[mi]} ${m[1]}`;
  }
  return s;
}

/** Totéž krátce: „23. 9. 2022", „3/2015", „2012". Do tabulek a řádků. */
export function datumVolneKratke(iso: string | null | undefined): string {
  if (!iso) return '—';
  const s = String(iso).trim();
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return datumKratke(s);
  const m = /^(\d{4})-(\d{2})$/.exec(s);
  if (m) return `${Number(m[2])}/${m[1]}`;
  return s;
}

/**
 * Rozsah dat česky: „10. až 17. srpna 2026", při různých měsících
 * „27. července až 3. srpna 2026". Když jeden konec chybí, vrátí druhý.
 */
export function obdobiText(
  od: string | null | undefined,
  do_: string | null | undefined,
): string | null {
  if (!od && !do_) return null;
  if (!od) return `do ${datumVolne(do_)}`;
  if (!do_) return `od ${datumVolne(od)}`;

  const a = /^(\d{4})-(\d{2})-(\d{2})/.exec(od);
  const b = /^(\d{4})-(\d{2})-(\d{2})/.exec(do_);
  if (!a || !b) return `${datumVolne(od)} až ${datumVolne(do_)}`;

  const stejnyRok = a[1] === b[1];
  const stejnyMesic = stejnyRok && a[2] === b[2];
  const mi = Number(b[2]) - 1;
  if (mi < 0 || mi > 11) return `${datumVolne(od)} až ${datumVolne(do_)}`;

  if (stejnyMesic) return `${Number(a[3])}. až ${Number(b[3])}. ${MESICE[mi]} ${b[1]}`;
  if (stejnyRok) {
    const mia = Number(a[2]) - 1;
    return `${Number(a[3])}. ${MESICE[mia]} až ${Number(b[3])}. ${MESICE[mi]} ${b[1]}`;
  }
  return `${datumVolne(od)} až ${datumVolne(do_)}`;
}

/**
 * Data ve tvaru 2026-08-17 se v textech ze zdrojů nahradí českým zápisem.
 * Používá se na texty, které přebíráme, ne na ty, které píšeme sami.
 */
export function polidstiData(text: string | null | undefined): string {
  if (!text) return '';
  return String(text).replace(/(\d{4})-(\d{2})-(\d{2})/g, (cely, r: string, me: string, d: string) => {
    const mi = Number(me) - 1;
    if (mi < 0 || mi > 11) return cely;
    return `${Number(d)}. ${Number(me)}. ${r}`;
  });
}

/* ──────────────────────  Jak se jmenují zdroje dat  ────────────────────
   V datech se zdroj označuje cestou k souboru. Čtenáři to nic neříká, takže
   se překládá na název, který dává smysl bez znalosti projektu. Co přeložit
   nejde, zůstává tak, jak to zdroj uvádí — nic se nezamlčuje. */

const NAZVY_ZDROJU: Record<string, string> = {
  'historie/udalosti.json': 'soupis historických událostí',
  'historie/prehled.json': 'přehled dějin města',
  'lide/osobnosti.json': 'přehled osobností města',
  'lide/profily.json': 'hlasovací profily zastupitelů',
  'propojeni/osoby_firmy.json': 'propojení osob a firem',
  'propojeni/dodavatele_politici.json': 'seznam dodavatelů s vazbou na politiky',
  'penize/agregace/protistrany.json': 'agregace plateb z registru smluv',
  'penize/agregace/souhrn.json': 'souhrnné ukazatele registru smluv',
  'firmy/subjekty.json': 'rejstřík ARES',
  'firmy/prehled/mesto_a_firmy.json': 'přehled vztahů firem k městu',
  'config/subjekty.json': 'seznam organizací města',
  'config/tagy.json': 'seznam témat',
  'zpravodaj/cisla.json': 'archiv Městského zpravodaje',
  'zpravodaj/clanky': 'články z Městského zpravodaje',
};

const NAZVY_SLOZEK: Record<string, string> = {
  historie: 'dějiny města',
  lide: 'přehled osobností města',
  penize: 'registr smluv',
  propojeni: 'propojení osob a firem',
  zpravodaj: 'Městský zpravodaj',
  usneseni: 'usnesení rady a zastupitelstva',
  hlasovani: 'jmenovitá hlasování',
  firmy: 'rejstřík firem',
  config: 'nastavení přehledu',
  opendata: 'otevřená data',
  casova_osa: 'jednotná časová osa',
  volby: 'výsledky voleb',
  media: 'mediální monitoring',
  vydani: 'týdenní vydání',
  retez: 'spojení usnesení, smluv a plateb',
};

function prelozCestu(cesta: string): string | null {
  const c = cesta.replace(/^\.?\/*/, '').replace(/^data\//, '').replace(/\/+$/, '');
  if (NAZVY_ZDROJU[c]) return NAZVY_ZDROJU[c];
  const prvni = c.split('/')[0];
  return NAZVY_SLOZEK[prvni] ?? null;
}

/**
 * Cesty k souborům v textu nahradí názvem zdroje. Odkazy (http…) nechává být —
 * tam je cesta součástí adresy, na kterou se dá kliknout.
 */
export function nazevZdroje(text: string | null | undefined): string {
  if (!text) return '';
  const s = String(text);
  if (s.includes('://')) return s;
  return s.replace(/(?:[\w.-]+\/)+[\w.*-]*|[\w.-]+\.json/g, (kus) => prelozCestu(kus) ?? kus);
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
  return s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
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
