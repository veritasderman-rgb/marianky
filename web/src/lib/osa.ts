/**
 * Časové osy (web/DESIGN.md §3.7).
 *
 * Podklad je `data/casova_osa/` — jednotný formát událostí ze všech zdrojů
 * projektu. Čte se PO ENTITÁCH (`osoby/{id}.json`, `firmy/{ico}.json`,
 * `tagy/{tag}.json`, `mesto.json`), ne celý adresář: `roky/` má desítky
 * megabajtů a načítat je kvůli jednomu profilu by build zbytečně zdrželo.
 *
 * Tři pravidla, která tenhle soubor drží tvrdě:
 *
 *   1. **Osa nepřeskakuje prázdné roky.** Čas je spojitá lineární škála, ne
 *      seznam let, ve kterých se něco stalo. Mezera je informace stejně jako
 *      značka — deset let ticha musí být vidět jako deset let ticha.
 *   2. **Odhad se nesmí tvářit jako fakt.** Zdroj rozlišuje `fakt`, `sporne`
 *      (prameny se rozcházejí) a odhad spojení usnesení → smlouva ve třech
 *      stupních. Osa to přebírá do TVARU značky, ne do barvy — barva už nese
 *      druh události — a v tabulce je jistota vypsaná slovy.
 *   3. **Přesnost datace se nedoplňuje.** „1193" zůstane rokem; nestane se
 *      z něj 1. leden. Pole `razeni` ze zdroje slouží jen k řazení a nikde
 *      se nezobrazuje — zdroj to výslovně zakazuje.
 */
import { nactiJson, type Nacteno } from './data';
import { escSvg, tipAtribut, type LegendaPolozka, type Tabulka, type TipRadek } from './grafy';
import { cssBarvaSlotu, MAX_KATEGORII } from './barvy';
import { cislo, datumKratke, kc, orez } from './format';
import { cis, jeObjekt, texty, txt, type Zaznam } from './tolerantni';

/* ─────────────────────────────  Událost  ───────────────────────────── */

/**
 * Jistota podle `casova_osa/souhrn.json`:
 *   fakt    — doložený záznam (usnesení, smlouva, článek)
 *   sporne  — doložený, ale prameny se rozcházejí (důvod je v `jistotaDuvod`)
 *   vysoka / stredni / nizka — ODHAD spojení usnesení → smlouva
 * `null` znamená, že zdroj o jistotě nic neříká. To není totéž jako „fakt".
 */
export type JistotaOsy = 'fakt' | 'sporne' | 'vysoka' | 'stredni' | 'nizka' | null;

export type Presnost = 'den' | 'mesic' | 'rok' | 'obdobi' | null;

export interface UdalostOsy {
  id: string;
  /** ISO v přesnosti, kterou zdroj uvádí: `YYYY`, `YYYY-MM` i `YYYY-MM-DD`. */
  datum: string;
  datum_do: string | null;
  presnost: Presnost;
  rok: number | null;
  /** Zdroj sám označil datum za zjevně zkomolené. Do rozsahu osy nevstupuje. */
  podezrele: boolean;
  /** Klíč pruhu — určuje řádek osy i barvu. */
  druh: string;
  nadpis: string;
  popis: string | null;
  castka_czk: number | null;
  jistota: JistotaOsy;
  jistotaDuvod: string | null;
  odkaz: string | null;
  /** Odkud údaj pochází — vypisuje se pod osou i v tabulce. */
  zdroj: string | null;
  /** Krátký doplněk do tooltipu a tabulky. */
  detail: string | null;
  osoby: string[];
  firmy: string[];
  tagy: string[];
}

/**
 * Kanonické pruhy. Pořadí je pořadím řádků na ose a zároveň pořadím, ve kterém
 * se rozdávají barvy — nejvýše šesti pruhům, které se na dané ose objeví,
 * zbytek spadne do „Ostatní" (web/DESIGN.md §2 bod 3). Přiřazení se odvíjí od
 * identity pruhu, ne od četnosti událostí, takže dvě osy nad stejnou množinou
 * druhů vypadají stejně.
 */
export const PRUHY: { klic: string; nazev: string }[] = [
  { klic: 'funkce', nazev: 'Funkce a mandáty' },
  { klic: 'usneseni', nazev: 'Usnesení' },
  { klic: 'hlasovani', nazev: 'Hlasování' },
  { klic: 'smlouva', nazev: 'Smlouvy a platby' },
  { klic: 'retez', nazev: 'Řetěz usnesení → smlouva' },
  { klic: 'zpravodaj', nazev: 'Zpravodaj' },
  { klic: 'media', nazev: 'Média' },
  { klic: 'volby', nazev: 'Volby' },
  { klic: 'firma', nazev: 'Firmy' },
  { klic: 'historie', nazev: 'Dějiny města' },
  { klic: 'ostatni', nazev: 'Ostatní' },
];

const NAZVY_PRUHU = new Map(PRUHY.map((p) => [p.klic, p.nazev]));
const ZNAME_PRUHY = new Set(PRUHY.map((p) => p.klic));

/** Sjednotí, jak jednotlivé moduly píšou druh události. */
export function normalizujDruh(v: string | null | undefined): string {
  const s = (v ?? '').trim().toLowerCase();
  if (!s) return 'ostatni';
  if (ZNAME_PRUHY.has(s)) return s;
  if (s.startsWith('usnes')) return 'usneseni';
  if (s.startsWith('hlas')) return 'hlasovani';
  if (s.startsWith('smlouv') || s.startsWith('platb') || s.startsWith('zakazk') || s.startsWith('penize')) return 'smlouva';
  if (s.startsWith('retez') || s.startsWith('řetěz')) return 'retez';
  if (s.startsWith('zpravodaj') || s.startsWith('clanek') || s.startsWith('článek')) return 'zpravodaj';
  if (s.startsWith('medi') || s.startsWith('médi') || s.startsWith('tisk')) return 'media';
  if (s.startsWith('funkc') || s.startsWith('mandat') || s.startsWith('role')) return 'funkce';
  if (s.startsWith('firm') || s.startsWith('subjekt')) return 'firma';
  if (s.startsWith('volb')) return 'volby';
  if (s.startsWith('histor') || s.startsWith('dejin') || s.startsWith('dějin')) return 'historie';
  return 'ostatni';
}

export function nazevDruhu(klic: string): string {
  return NAZVY_PRUHU.get(klic) ?? 'Ostatní';
}

export function normalizujJistotu(v: string | null | undefined): JistotaOsy {
  const s = (v ?? '').trim().toLowerCase();
  if (!s) return null;
  if (s === 'fakt' || s.startsWith('dolož') || s.startsWith('dolozen')) return 'fakt';
  if (s.startsWith('sporn') || s.startsWith('nejist')) return 'sporne';
  if (s.startsWith('vysok')) return 'vysoka';
  if (s.startsWith('stredn') || s.startsWith('střed')) return 'stredni';
  if (s.startsWith('nizk') || s.startsWith('nízk')) return 'nizka';
  return null;
}

/** Odhad spojení — NIKDY se nesmí zobrazit jako doložený fakt. */
export function jeOdhad(j: JistotaOsy): boolean {
  return j === 'vysoka' || j === 'stredni' || j === 'nizka';
}

/** Doložený záznam, ve kterém se ale prameny rozcházejí. */
export function jeSporne(j: JistotaOsy): boolean {
  return j === 'sporne';
}

export function popisekJistoty(j: JistotaOsy): string {
  if (j === 'fakt') return 'doložený záznam';
  if (j === 'sporne') return 'prameny se rozcházejí — údaj není jistý';
  if (j === 'vysoka') return 'odhad spojení, vysoká jistota — není to doložený fakt';
  if (j === 'stredni') return 'odhad spojení, střední jistota — není to doložený fakt';
  if (j === 'nizka') return 'odhad spojení, nízká jistota — nepotvrzená domněnka';
  return 'jistota v datech není';
}

/* ──────────────────  Čtení data/casova_osa/{entita}.json  ──────────────── */

export interface SouborOsy {
  entita: { typ: string | null; id: string | null; nazev: string | null } | null;
  udalosti: UdalostOsy[];
  rozsah: { prvniRok: number | null; posledniRok: number | null; podezrelychDat: number };
  pocty: { celkem: number | null; dolozenych: number | null; odhadu: number | null };
  /** Kolik hlasování je ve zdroji jen v souhrnu a na osu se nedostalo. */
  hlasovaniVSouhrnu: number | null;
  /** Zdroje (moduly), ze kterých se osa skládá — vypisují se pod osou. */
  moduly: string[];
}

const PRAZDNY: SouborOsy = {
  entita: null,
  udalosti: [],
  rozsah: { prvniRok: null, posledniRok: null, podezrelychDat: 0 },
  pocty: { celkem: null, dolozenych: null, odhadu: null },
  hlasovaniVSouhrnu: null,
  moduly: [],
};

function presnostZ(v: string | null): Presnost {
  const s = (v ?? '').trim().toLowerCase();
  if (s === 'den' || s === 'mesic' || s === 'rok' || s === 'obdobi') return s;
  return null;
}

/** Krátký doplněk podle druhu — čte se z `detail`, nedopočítává se. */
function detailUdalosti(z: Zaznam, druh: string, castka: number | null): string | null {
  const d = jeObjekt(z.detail) ? z.detail : null;
  const kusy: string[] = [];

  if (castka !== null) kusy.push(kc(castka));

  const role = jeObjekt(z.role) ? txt(z.role, 'vztah') : null;
  if (role) kusy.push(popisVztahu(role));

  if (d) {
    if (druh === 'volby') {
      const ucast = jeObjekt(d.ucast) ? cis(d.ucast, 'ucast_proc') : null;
      if (ucast !== null) kusy.push(`účast ${ucast.toFixed(2).replace('.', ',')} %`);
      const kolo = cis(d, 'kolo');
      if (kolo !== null) kusy.push(`${kolo}. kolo`);
    }
    const smer = txt(d, 'smer');
    if (smer) kusy.push(smer === 'prijem' ? 'město inkasuje' : 'město platí');
    const protistrana = txt(d, 'protistrana', 'dodavatel');
    if (protistrana) kusy.push(protistrana);
    const organ = txt(d, 'organ');
    if (organ) kusy.push(organ === 'rada' ? 'Rada města' : organ === 'zastupitelstvo' ? 'Zastupitelstvo' : organ);
    const kategorie = txt(d, 'kategorie');
    if (kategorie && kusy.length === 0) kusy.push(kategorie);
  }

  return kusy.length > 0 ? kusy.join(' · ') : null;
}

function popisVztahu(v: string): string {
  const m: Record<string, string> = {
    funkce: 'funkce',
    zminen_v_clanku: 'zmíněn v článku',
    hlasoval: 'hlasoval',
    kandidoval: 'kandidoval',
    zvolen: 'zvolen',
    protistrana: 'protistrana smlouvy',
    navrhovatel: 'navrhovatel',
  };
  return m[v] ?? v.replace(/_/g, ' ');
}

function zdrojUdalosti(z: Zaznam): string | null {
  if (jeObjekt(z.zdroj)) {
    const modul = txt(z.zdroj, 'modul');
    const soubor = txt(z.zdroj, 'soubor');
    return soubor ? (modul ? `${modul} — ${soubor}` : soubor) : modul;
  }
  return txt(z, 'zdroj_soubor', 'zdroj', 'soubor');
}

function udalostZe(z: Zaznam, poradi: number): UdalostOsy | null {
  const datum = txt(z, 'datum');
  const nadpis = txt(z, 'nadpis', 'nazev', 'název');
  if (!datum || !nadpis) return null;

  const entity = jeObjekt(z.entity) ? z.entity : null;
  const druh = normalizujDruh(txt(z, 'typ', 'druh'));
  const castka = cis(z, 'castka_czk');
  const doIso = txt(z, 'datum_do');

  return {
    id: txt(z, 'id') ?? `udalost-${poradi + 1}`,
    datum,
    datum_do: doIso && doIso >= datum ? doIso : null,
    presnost: presnostZ(txt(z, 'presnost')),
    rok: cis(z, 'rok') ?? rokZIso(datum),
    podezrele: z.datum_podezrele === true,
    druh,
    nadpis,
    popis: txt(z, 'popis'),
    castka_czk: castka,
    jistota: normalizujJistotu(txt(z, 'jistota')),
    jistotaDuvod: txt(z, 'jistota_duvod', 'poznamka'),
    odkaz: txt(z, 'url', 'odkaz') ?? (jeObjekt(z.zdroj) ? txt(z.zdroj, 'url') : null),
    zdroj: zdrojUdalosti(z),
    detail: detailUdalosti(z, druh, castka),
    osoby: entity ? texty(entity, 'osoby') : texty(z, 'osoby'),
    firmy: entity ? texty(entity, 'firmy') : texty(z, 'firmy', 'ica'),
    tagy: entity ? texty(entity, 'tagy') : texty(z, 'tagy'),
  };
}

function souborOsy(v: Nacteno<unknown>): Nacteno<SouborOsy> {
  const koren = jeObjekt(v.data) ? v.data : null;
  if (!koren) return { ...v, data: PRAZDNY };

  const surove = Array.isArray(koren.udalosti) ? koren.udalosti.filter(jeObjekt) : [];
  const udalosti = surove
    .map((z, i) => udalostZe(z, i))
    .filter((u): u is UdalostOsy => u !== null)
    .sort((a, b) => a.datum.localeCompare(b.datum));

  const rozsah = jeObjekt(koren.rozsah) ? koren.rozsah : null;
  const pocty = jeObjekt(koren.pocty) ? koren.pocty : null;
  const entita = jeObjekt(koren.entita) ? koren.entita : null;

  const moduly = [
    ...new Set(
      surove
        .map((z) => (jeObjekt(z.zdroj) ? txt(z.zdroj, 'modul') : null) ?? txt(z, 'zdroj_soubor'))
        .filter((x): x is string => Boolean(x)),
    ),
  ].sort((a, b) => a.localeCompare(b, 'cs-CZ'));

  return {
    ...v,
    data: {
      entita: entita
        ? { typ: txt(entita, 'typ'), id: txt(entita, 'id'), nazev: txt(entita, 'nazev', 'jmeno') }
        : null,
      udalosti,
      rozsah: {
        prvniRok: cis(rozsah, 'prvni_rok'),
        posledniRok: cis(rozsah, 'posledni_rok'),
        podezrelychDat: cis(rozsah, 'podezrelych_dat') ?? 0,
      },
      pocty: {
        celkem: cis(pocty, 'celkem'),
        dolozenych: cis(pocty, 'dolozenych'),
        odhadu: cis(pocty, 'odhadu'),
      },
      hlasovaniVSouhrnu: cis(pocty, 'hlasovani_v_souhrnu'),
      moduly,
    },
  };
}

/** Slug do jména souboru — `casova_osa/` používá stejné klíče jako zbytek webu. */
function bezpecnyKlic(s: string): string {
  return s.replace(/[^A-Za-z0-9_.-]/g, '');
}

export function nactiOsuMesta(): Nacteno<SouborOsy> {
  return souborOsy(nactiJson<unknown>('casova_osa/mesto.json', null));
}
export function nactiOsuOsoby(id: string): Nacteno<SouborOsy> {
  return souborOsy(nactiJson<unknown>(`casova_osa/osoby/${bezpecnyKlic(id)}.json`, null));
}
export function nactiOsuFirmy(ico: string): Nacteno<SouborOsy> {
  return souborOsy(nactiJson<unknown>(`casova_osa/firmy/${bezpecnyKlic(ico)}.json`, null));
}
export function nactiOsuTagu(tag: string): Nacteno<SouborOsy> {
  return souborOsy(nactiJson<unknown>(`casova_osa/tagy/${bezpecnyKlic(tag)}.json`, null));
}

export interface SouhrnOsy {
  stavZdroju: Record<string, string>;
  vysvetlivky: Record<string, string>;
  celkem: number | null;
  dolozenych: number | null;
  odhadu: number | null;
  dleTypu: Record<string, number>;
  metodika: Record<string, string>;
}

export function nactiSouhrnOsy(): Nacteno<SouhrnOsy> {
  const v = nactiJson<unknown>('casova_osa/souhrn.json', null);
  const k = jeObjekt(v.data) ? v.data : {};
  const pocty = jeObjekt(k.pocty) ? k.pocty : {};
  const textovaMapa = (x: unknown): Record<string, string> => {
    if (!jeObjekt(x)) return {};
    const ven: Record<string, string> = {};
    for (const [a, b] of Object.entries(x)) if (typeof b === 'string') ven[a] = b;
    return ven;
  };
  const cisMapa = (x: unknown): Record<string, number> => {
    if (!jeObjekt(x)) return {};
    const ven: Record<string, number> = {};
    for (const [a, b] of Object.entries(x)) if (typeof b === 'number') ven[a] = b;
    return ven;
  };
  return {
    ...v,
    data: {
      stavZdroju: textovaMapa(k.stav_zdroju),
      vysvetlivky: textovaMapa(k.vysvetlivky_stavu),
      celkem: cis(pocty, 'celkem'),
      dolozenych: cis(pocty, 'dolozenych'),
      odhadu: cis(pocty, 'odhadu'),
      dleTypu: cisMapa(pocty.dle_typu),
      metodika: textovaMapa(k.metodika),
    },
  };
}

/* ───────────────────────────  Práce s datem  ───────────────────────── */

export function rokZIso(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const m = /^(-?\d{1,4})/.exec(iso);
  if (!m) return null;
  const r = Number(m[1]);
  return Number.isFinite(r) ? r : null;
}

/**
 * Podíl roku 0–1. Když zdroj uvádí jen rok, vrací 0,5 — značka sedí doprostřed
 * roku, ne na 1. ledna, aby nepředstírala přesnost, kterou zdroj nemá.
 */
export function pozicevRoce(iso: string | null | undefined): number {
  if (!iso) return 0.5;
  const m = /^-?\d{1,4}-(\d{2})(?:-(\d{2}))?/.exec(iso);
  if (!m) return 0.5;
  const mesic = Number(m[1]);
  if (!Number.isFinite(mesic) || mesic < 1 || mesic > 12) return 0.5;
  const den = m[2] ? Number(m[2]) : null;
  const zaklad = (mesic - 1) / 12;
  return den && den >= 1 && den <= 31 ? zaklad + ((den - 1) / 31) * (1 / 12) : zaklad + 1 / 24;
}

/** Datum tak přesně, jak ho zdroj uvádí. Rok se nedoplňuje na 1. leden. */
export function popisDatumu(u: Pick<UdalostOsy, 'datum' | 'datum_do'>): string {
  const jeden = (iso: string): string => {
    if (/^-?\d{1,4}-\d{2}-\d{2}/.test(iso)) return datumKratke(iso);
    const m = /^(-?\d{1,4})-(\d{2})$/.exec(iso);
    if (m) return `${Number(m[2])}/${m[1]}`;
    return iso;
  };
  return u.datum_do && u.datum_do !== u.datum ? `${jeden(u.datum)} – ${jeden(u.datum_do)}` : jeden(u.datum);
}

/* ──────────────────────────  Kreslení osy  ─────────────────────────── */

export interface Osa {
  svg: string;
  sirka: number;
  legenda: LegendaPolozka[];
  /** Legenda jistoty — rozdíl nese tvar značky, ne barva. */
  legendaJistoty: { nazev: string; trida: string }[];
  tabulka: Tabulka;
  poznamky: string[];
  rokOd: number;
  rokDo: number;
  pocet: number;
  vykresleno: number;
  vynechanoVTabulce: number;
}

const VYSKA_PRUHU = 38;
const SIRKA_POPISKU = 186;
const HLAVICKA = 32;
const SPODEK = 30;
const MAX_ZNACEK = 900;
const MAX_RADKU_TABULKY = 300;
const UROVNE_POSUNU = [0, -10, 10];

function krokLet(rozsah: number): number {
  for (const k of [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500]) {
    if (rozsah / k <= 12) return k;
  }
  return 1000;
}

export function grafCasovaOsa(udalosti: UdalostOsy[], nazev: string, sirka = 900): Osa {
  // Podezřelé datum zdroj sám označuje za zkomolené — do rozsahu osy nevstupuje,
  // jinak by jedna useknutá číslice roztáhla osu o dva tisíce let.
  const platne = udalosti.filter((u) => rokZIso(u.datum) !== null && !u.podezrele);
  const roky = platne.map((u) => rokZIso(u.datum) as number);
  const rokyDo = platne.map((u) => rokZIso(u.datum_do) ?? (rokZIso(u.datum) as number));
  const rokOd = roky.length ? Math.min(...roky) : new Date().getFullYear();
  const rokDo = rokyDo.length ? Math.max(...rokyDo) : rokOd;

  const pritomne = PRUHY.map((p) => p.klic).filter((k) => platne.some((u) => u.druh === k));
  const barvaPruhu = new Map<string, string>();
  pritomne.forEach((k, i) => {
    barvaPruhu.set(k, k === 'ostatni' ? cssBarvaSlotu(null) : cssBarvaSlotu(i < MAX_KATEGORII ? i : null));
  });

  const W = sirka;
  const pw = W - SIRKA_POPISKU - 16;
  const H = HLAVICKA + Math.max(1, pritomne.length) * VYSKA_PRUHU + SPODEK;

  const rozsah = rokDo + 1 - rokOd;
  const x = (rok: number, frakce: number) => SIRKA_POPISKU + ((rok + frakce - rokOd) / rozsah) * pw;

  const casti: string[] = [];

  /* Mřížka let. Krok se volí tak, aby se popisky nepřekrývaly — osa přitom
     zůstává spojitá, takže prázdné roky se NEPŘESKAKUJÍ, jen nemají popisek. */
  const krok = krokLet(rozsah);
  const spodekMrizky = HLAVICKA + Math.max(1, pritomne.length) * VYSKA_PRUHU;
  for (let r = Math.ceil(rokOd / krok) * krok; r <= rokDo + 1; r += krok) {
    const px = x(r, 0);
    if (px > W - 4) break;
    casti.push(
      `<line class="g-mrizka" x1="${px.toFixed(1)}" y1="${HLAVICKA - 8}" x2="${px.toFixed(1)}" y2="${spodekMrizky}"/>`,
      `<text class="g-popisek g-popisek--x" x="${px.toFixed(1)}" y="${HLAVICKA - 14}">${r}</text>`,
    );
  }
  casti.push(
    `<line class="g-osa" x1="${SIRKA_POPISKU}" y1="${spodekMrizky}" x2="${(SIRKA_POPISKU + pw).toFixed(1)}" y2="${spodekMrizky}"/>`,
  );

  /* Značky. Když je jich přes limit, kreslí se nejnovější — starší zůstávají
     v tabulce. Zamlčet se nesmí ani jedno, proto je o tom poznámka. */
  const kresleneVse = [...platne].sort((a, b) => b.datum.localeCompare(a.datum));
  const kreslene = new Set(kresleneVse.slice(0, MAX_ZNACEK).map((u) => u.id));

  let prekryvu = 0;
  pritomne.forEach((klic, ri) => {
    const y = HLAVICKA + ri * VYSKA_PRUHU;
    const stred = y + VYSKA_PRUHU / 2;
    const barva = barvaPruhu.get(klic) ?? cssBarvaSlotu(null);
    const vPruhu = platne.filter((u) => u.druh === klic && kreslene.has(u.id));

    casti.push(
      `<text class="g-radek-nazev" x="0" y="${(stred + 4).toFixed(1)}">${escSvg(nazevDruhu(klic))}</text>`,
      `<line class="osa-linka" x1="${SIRKA_POPISKU}" y1="${stred.toFixed(1)}" x2="${(SIRKA_POPISKU + pw).toFixed(1)}" y2="${stred.toFixed(1)}"/>`,
    );

    const obsazeno: number[] = UROVNE_POSUNU.map(() => -Infinity);

    for (const u of vPruhu) {
      const r = rokZIso(u.datum) as number;
      const px = x(r, pozicevRoce(u.datum));
      const rDo = rokZIso(u.datum_do);
      const pxDo = rDo === null ? null : x(rDo, pozicevRoce(u.datum_do));

      let uroven = obsazeno.findIndex((konec) => px - konec > 13);
      if (uroven === -1) {
        uroven = 0;
        prekryvu++;
      }
      obsazeno[uroven] = pxDo !== null ? Math.max(px, pxDo) : px;
      const cy = stred + UROVNE_POSUNU[uroven];

      const odhad = jeOdhad(u.jistota);
      const sporne = jeSporne(u.jistota);
      const tridy = ['osa-znacka'];
      if (odhad) tridy.push('osa-znacka--odhad');
      else if (sporne) tridy.push('osa-znacka--sporne');

      const radky: TipRadek[] = [
        { l: 'Kdy', v: popisDatumu(u) },
        { l: 'Druh', v: nazevDruhu(u.druh) },
      ];
      if (u.detail) radky.push({ l: 'Detail', v: u.detail });
      if (u.popis) radky.push({ l: 'Popis', v: orez(u.popis, 150) });
      radky.push({ l: 'Jistota', v: popisekJistoty(u.jistota) });
      if (u.jistotaDuvod) radky.push({ l: 'Proč', v: orez(u.jistotaDuvod, 150) });
      if (u.zdroj) radky.push({ l: 'Zdroj', v: u.zdroj });

      const vypln = odhad ? 'var(--surface)' : barva;
      const obrys = odhad ? ` stroke="${barva}"` : '';
      const telo =
        pxDo !== null && pxDo - px > 3
          ? `<rect x="${px.toFixed(1)}" y="${(cy - 5.5).toFixed(1)}" width="${(pxDo - px).toFixed(1)}" height="11" rx="5.5" fill="${vypln}"${obrys}/>`
          : `<circle cx="${px.toFixed(1)}" cy="${cy.toFixed(1)}" r="5.5" fill="${vypln}"${obrys}/>`;

      const popis = `${popisDatumu(u)} — ${u.nadpis}${odhad || sporne ? ` (${popisekJistoty(u.jistota)})` : ''}`;
      // Značky jsou mimo pořadí tabulátoru; kompletní seznam i s odkazy nese
      // povinná tabulka pod osou (web/DESIGN.md §2 bod 5).
      const atributy = `${tipAtribut(u.nadpis, radky, odhad ? undefined : barva, false)} tabindex="-1" aria-hidden="true" class="${tridy.join(' ')}"`;
      const vnitrek = `<title>${escSvg(popis)}</title>${telo}`;
      casti.push(
        u.odkaz && u.odkaz.startsWith('/')
          ? `<a href="${escSvg(u.odkaz)}" ${atributy}>${vnitrek}</a>`
          : `<g ${atributy}>${vnitrek}</g>`,
      );
    }
  });

  const poznamky: string[] = [];
  if (kresleneVse.length > kreslene.size) {
    poznamky.push(
      `Na ose je vykresleno ${cislo(kreslene.size)} nejnovějších z ${cislo(kresleneVse.length)} událostí. Starší se z osy vešly jen do rozsahu, ne do značek — jinak by se z pruhu stala souvislá čára.`,
    );
  }
  if (prekryvu > 0) {
    poznamky.push(
      `Značky se ${prekryvu === 1 ? 'na jednom místě překrývají' : `na ${cislo(prekryvu)} místech překrývají`} — víc událostí padne na stejný bod osy. Úplný výčet je v tabulce pod osou.`,
    );
  }
  const podezrelych = udalosti.filter((u) => u.podezrele).length;
  if (podezrelych > 0) {
    poznamky.push(
      `${cislo(podezrelych)} ${podezrelych === 1 ? 'událost má' : 'událostí má'} ve zdroji zjevně zkomolené datum. Zdroj je takto sám označuje; do osy nevstupují, aby jedna useknutá číslice neroztáhla rozsah o staletí.`,
    );
  }

  const doTabulky = kresleneVse.slice(0, MAX_RADKU_TABULKY);

  return {
    svg:
      `<svg class="graf-svg osa-svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" ` +
      `preserveAspectRatio="xMinYMin meet" role="group" aria-label="${escSvg(`${nazev}: časová osa, ${platne.length} událostí, roky ${rokOd}–${rokDo}`)}">` +
      casti.join('') +
      '</svg>',
    sirka: W,
    legenda: pritomne.map((k) => ({
      nazev: nazevDruhu(k),
      barva: barvaPruhu.get(k) ?? cssBarvaSlotu(null),
      tvar: 'rect' as const,
    })),
    legendaJistoty: legendaJistot(platne),
    tabulka: {
      hlavicka: [
        { nazev: 'Kdy' },
        { nazev: 'Druh' },
        { nazev: 'Událost' },
        { nazev: 'Jistota' },
        { nazev: 'Zdroj' },
      ],
      radky: doTabulky.map((u) => [
        popisDatumu(u),
        nazevDruhu(u.druh),
        u.nadpis + (u.detail ? ` — ${u.detail}` : ''),
        popisekJistoty(u.jistota) + (u.jistotaDuvod ? ` (${u.jistotaDuvod})` : ''),
        u.zdroj ?? 'neuveden',
      ]),
    },
    poznamky,
    rokOd,
    rokDo,
    pocet: platne.length,
    vykresleno: kreslene.size,
    vynechanoVTabulce: Math.max(0, kresleneVse.length - doTabulky.length),
  };
}

function legendaJistot(u: UdalostOsy[]): { nazev: string; trida: string }[] {
  const ven: { nazev: string; trida: string }[] = [];
  if (u.some((x) => x.jistota === 'fakt' || x.jistota === null)) {
    ven.push({ nazev: 'doložený záznam — plná značka', trida: '' });
  }
  if (u.some((x) => jeSporne(x.jistota))) {
    ven.push({
      nazev: 'prameny se rozcházejí — plná značka s přerušovaným obrysem, důvod je v tabulce',
      trida: 'legenda__znacka--sporne',
    });
  }
  if (u.some((x) => jeOdhad(x.jistota))) {
    ven.push({
      nazev: 'odhad spojení — dutá značka s přerušovaným obrysem, není to doložený fakt',
      trida: 'legenda__znacka--odhad',
    });
  }
  return ven;
}

/* ──────────────────────────  Stavba událostí  ──────────────────────── */

/** Zkratka pro sestavení události z vlastních dat stránky. */
export function udalost(
  cast: Partial<UdalostOsy> & { id: string; datum: string; druh: string; nadpis: string },
): UdalostOsy {
  return {
    datum_do: null,
    presnost: null,
    rok: rokZIso(cast.datum),
    podezrele: false,
    popis: null,
    castka_czk: null,
    jistota: null,
    jistotaDuvod: null,
    odkaz: null,
    zdroj: null,
    detail: null,
    osoby: [],
    firmy: [],
    tagy: [],
    ...cast,
  };
}

/** Sloučí události z víc zdrojů, zahodí duplicitní `id` a seřadí podle času. */
export function slucUdalosti(...skupiny: UdalostOsy[][]): UdalostOsy[] {
  const podleId = new Map<string, UdalostOsy>();
  for (const s of skupiny) {
    for (const u of s) if (!podleId.has(u.id)) podleId.set(u.id, u);
  }
  return [...podleId.values()].sort((a, b) => a.datum.localeCompare(b.datum));
}

/** Lidsky čitelný seznam modulů, ze kterých se osa skládá. */
export function popisModulu(moduly: string[]): string[] {
  const nazvy: Record<string, string> = {
    historie: 'dějiny města (historie/)',
    usneseni: 'usnesení rady a zastupitelstva',
    hlasovani: 'jmenovitá hlasování',
    smlouvy: 'registr smluv (peníze)',
    retez: 'řetěz usnesení → smlouva (odhad)',
    zpravodaj: 'Městský zpravodaj',
    media: 'mediální monitoring',
    volby: 'výsledky voleb',
    firmy: 'rejstřík firem (ARES)',
    funkce: 'funkce a mandáty',
    opendata: 'otevřená data',
    penize: 'registr smluv (peníze)',
  };
  return [...new Set(moduly.map((m) => nazvy[m] ?? m))];
}
