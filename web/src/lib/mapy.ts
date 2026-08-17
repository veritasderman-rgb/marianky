/**
 * Mapy jako SVG generované při buildu (web/DESIGN.md §3.6).
 *
 * Žádná mapová knihovna, žádné dlaždice z cizího serveru. Geometrie je při
 * buildu známá, takže runtime knihovna by jen přidala závislost na cizí službě
 * a zpomalila stránku. Barvy jsou CSS tokeny, aby jeden vygenerovaný SVG
 * obsloužil světlý i tmavý režim.
 *
 * Souřadnice se převádějí do jednotné projekce (Web Mercator, EPSG:3857) při
 * buildu. Výřez se počítá ze VŠECH vrstev, i vypnutých — jinak by zapnutí
 * vrstvy mapu posunulo a čtenář by ztratil orientaci.
 *
 * Past volební mapy (§3.6) tenhle soubor neřeší sám: barví se plocha, ale volí
 * lidé. Proto komponenta `MapaKarta.astro` odmítne vykreslit mapu bez
 * doprovodného grafu nebo tabulky s absolutními počty.
 */
import { escSvg, tipAtribut, type LegendaPolozka, type TipRadek, type Tabulka } from './grafy';
import { cssKrokRampy, KROKU_RAMPY } from './barvy';
import { jeObjekt, type Zaznam } from './tolerantni';

/* ────────────────────────────  Geometrie  ──────────────────────────── */

export type Druh = 'plocha' | 'linie' | 'bod';

/** Jeden vykreslitelný tvar. U plochy je `prstence[0]` obrys a další jsou díry. */
export interface Tvar {
  druh: Druh;
  prstence: [number, number][][];
}

const MAX_HLOUBKA = 6;

/**
 * Rozloží GeoJSON geometrii na tvary. Zvládne Point, MultiPoint, LineString,
 * MultiLineString, Polygon, MultiPolygon i GeometryCollection. Cokoliv jiného
 * se tiše vynechá — mapa radši ukáže míň, než aby build spadl na neznámém typu.
 */
export function tvaryZGeometrie(g: unknown, hloubka = 0): Tvar[] {
  if (!jeObjekt(g) || hloubka > MAX_HLOUBKA) return [];
  const typ = typeof g.type === 'string' ? g.type : '';
  const c = g.coordinates;

  switch (typ) {
    case 'Point':
      return bod(c) ? [{ druh: 'bod', prstence: [[bod(c) as [number, number]]] }] : [];
    case 'MultiPoint':
      return (Array.isArray(c) ? c : [])
        .map(bod)
        .filter((b): b is [number, number] => b !== null)
        .map((b) => ({ druh: 'bod' as const, prstence: [[b]] }));
    case 'LineString': {
      const l = prstenec(c);
      return l.length > 1 ? [{ druh: 'linie', prstence: [l] }] : [];
    }
    case 'MultiLineString':
      return (Array.isArray(c) ? c : [])
        .map(prstenec)
        .filter((l) => l.length > 1)
        .map((l) => ({ druh: 'linie' as const, prstence: [l] }));
    case 'Polygon': {
      const p = (Array.isArray(c) ? c : []).map(prstenec).filter((r) => r.length > 2);
      return p.length > 0 ? [{ druh: 'plocha', prstence: p }] : [];
    }
    case 'MultiPolygon':
      return (Array.isArray(c) ? c : [])
        .map((poly) => (Array.isArray(poly) ? poly.map(prstenec).filter((r) => r.length > 2) : []))
        .filter((p) => p.length > 0)
        .map((p) => ({ druh: 'plocha' as const, prstence: p }));
    case 'GeometryCollection': {
      const geometrie = Array.isArray(g.geometries) ? g.geometries : [];
      return geometrie.flatMap((x) => tvaryZGeometrie(x, hloubka + 1));
    }
    default:
      return [];
  }
}

function bod(v: unknown): [number, number] | null {
  if (!Array.isArray(v) || v.length < 2) return null;
  const lon = Number(v[0]);
  const lat = Number(v[1]);
  if (!Number.isFinite(lon) || !Number.isFinite(lat)) return null;
  if (Math.abs(lon) > 180 || Math.abs(lat) > 90) return null;
  return [lon, lat];
}

function prstenec(v: unknown): [number, number][] {
  if (!Array.isArray(v)) return [];
  return v.map(bod).filter((b): b is [number, number] => b !== null);
}

/**
 * Souřadnice z volného zápisu, který GeoJSON není: `lat`/`lon`, `x`/`y`,
 * `souradnice: [lon, lat]` nebo `wgs84`. Používá se u památek, kde bod bývá
 * uvedený přímo u záznamu, ne jako GeoJSON.
 */
export function bodZeZaznamu(z: Zaznam | null | undefined): [number, number] | null {
  if (!z) return null;
  const par = (a: unknown, b: unknown): [number, number] | null => {
    const x = Number(a);
    const y = Number(b);
    return Number.isFinite(x) && Number.isFinite(y) ? bod([x, y]) : null;
  };

  for (const k of ['souradnice', 'coordinates', 'wgs84', 'pozice', 'bod']) {
    const v = z[k];
    const b = bod(v);
    if (b) return b;
    if (jeObjekt(v)) {
      const vn = par(v.lon ?? v.lng ?? v.x ?? v.e, v.lat ?? v.y ?? v.n);
      if (vn) return vn;
    }
  }
  const lat = z.lat ?? z.latitude ?? z.sirka ?? z.y;
  const lon = z.lon ?? z.lng ?? z.longitude ?? z.delka ?? z.x;
  return par(lon, lat);
}

/* ────────────────────────────  Projekce  ───────────────────────────── */

const R_ZEME = 6378137;

/** Web Mercator (EPSG:3857). `y` je otočené, aby sever byl v SVG nahoře. */
function mercator(lon: number, lat: number): { x: number; y: number } {
  const la = Math.max(-85.05112878, Math.min(85.05112878, lat));
  return {
    x: R_ZEME * ((lon * Math.PI) / 180),
    y: -R_ZEME * Math.log(Math.tan(Math.PI / 4 + ((la * Math.PI) / 180) / 2)),
  };
}

interface Vyrez {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  /** Zeměpisná šířka středu — pro měřítko. */
  stredLat: number;
}

/* ─────────────────────────  Vrstvy a prvky  ────────────────────────── */

export interface PrvekMapy {
  id: string;
  nazev: string;
  tvary: Tvar[];
  /** CSS výraz barvy, např. `var(--g1)` nebo `var(--r5)`. */
  barva: string;
  /** `true` u prvku, o kterém data hodnotu nemají — kreslí se jako „bez dat". */
  bezDat?: boolean;
  odkaz?: string | null;
  tip: TipRadek[];
  /** Věta do `title` a pro odečítač. */
  popis: string;
}

export interface VrstvaMapy {
  klic: string;
  nazev: string;
  popis?: string;
  druh: Druh;
  prvky: PrvekMapy[];
  /** Zapnutá při načtení stránky. */
  zapnuta: boolean;
  /**
   * Vrstva s tisíci prvky se kreslí „nalehko": bez tooltipu a bez obalu,
   * jen tvar s `<title>`. U 2 500 adresních míst by plná verze přidala
   * megabajty HTML. Obsah nesou `<title>` a tabulka pod mapou.
   */
  bezTooltipu?: boolean;
  /**
   * Poloprůhledná výplň. Patří vrstvám, které se navzájem překrývají (ochranná
   * území, katastry) — bez ní by největší polygon všechno pod sebou schoval.
   * U choroplethu se NEPOUŽÍVÁ: prosvítající pozadí by posunulo barvu a rozbilo
   * ověřenou škálu.
   */
  pruhledna?: boolean;
  legenda: LegendaPolozka[];
  /** Odkud data pocházejí — u map povinné (§3.6). */
  zdroj: string;
  licence: string | null;
  /** Povinný tabulkový pohled na tuhle vrstvu. */
  tabulka: Tabulka;
}

export interface Mapa {
  svg: string;
  sirka: number;
  vyska: number;
  /** Prázdná mapa = žádný prvek neměl použitelnou geometrii. */
  prazdna: boolean;
  /** Kolik prvků se nevykreslilo, protože jim chyběla geometrie. */
  bezGeometrie: number;
  poznamky: string[];
}

interface Nastaveni {
  sirka?: number;
  maxVyska?: number;
  /** Popis celé mapy pro odečítač. */
  popis: string;
}

const OKRAJ = 14;

/**
 * Složí SVG mapu ze všech vrstev. Výřez se počítá i z vypnutých vrstev, aby
 * zapnutí vrstvy mapou neposunulo.
 */
export function mapaSvg(vrstvy: VrstvaMapy[], nastaveni: Nastaveni): Mapa {
  const W = nastaveni.sirka ?? 900;
  const maxH = nastaveni.maxVyska ?? 620;

  const vyrez = spocitejVyrez(vrstvy);
  const bezGeometrie = vrstvy.reduce((s, v) => s + v.prvky.filter((p) => p.tvary.length === 0).length, 0);

  if (!vyrez) {
    return {
      svg: '',
      sirka: W,
      vyska: 0,
      prazdna: true,
      bezGeometrie,
      poznamky: [],
    };
  }

  const sirkaGeo = Math.max(1, vyrez.maxX - vyrez.minX);
  const vyskaGeo = Math.max(1, vyrez.maxY - vyrez.minY);

  let plochaW = W - 2 * OKRAJ;
  let plochaH = (plochaW * vyskaGeo) / sirkaGeo;
  if (plochaH > maxH - 2 * OKRAJ) {
    plochaH = maxH - 2 * OKRAJ;
    plochaW = (plochaH * sirkaGeo) / vyskaGeo;
  }
  const H = Math.round(plochaH + 2 * OKRAJ);
  const posunX = OKRAJ + (W - 2 * OKRAJ - plochaW) / 2;
  const meritkoPx = plochaW / sirkaGeo;

  const proj = (lon: number, lat: number): [number, number] => {
    const m = mercator(lon, lat);
    return [posunX + (m.x - vyrez.minX) * meritkoPx, OKRAJ + (m.y - vyrez.minY) * meritkoPx];
  };

  // Plochy vespod, linie nad nimi, body úplně nahoře — jinak by velký polygon
  // překryl body, které na něm leží.
  const poradi: Record<Druh, number> = { plocha: 0, linie: 1, bod: 2 };
  const serazene = [...vrstvy].sort((a, b) => poradi[a.druh] - poradi[b.druh]);

  const casti: string[] = [];
  for (const v of serazene) {
    const obsah: string[] = [];
    for (const p of v.prvky) {
      if (p.tvary.length === 0) continue;
      obsah.push(prvekSvg(p, v.druh, proj, v.bezTooltipu === true, v.pruhledna === true));
    }
    if (obsah.length === 0) continue;
    // Barva vrstvy kreslené nalehko sedí na skupině, ne na každém prvku.
    const barvaSkupiny = v.bezTooltipu ? ` fill="${v.prvky[0]?.barva ?? 'var(--g-ost)'}" class="mapa-vrstva mapa-vrstva--nalehko"` : ' class="mapa-vrstva"';
    casti.push(
      `<g${barvaSkupiny} data-vrstva="${escSvg(v.klic)}"${v.zapnuta ? '' : ' data-vypnuta="1"'}>${obsah.join('')}</g>`,
    );
  }

  casti.push(meritkoSvg(vyrez, meritkoPx, OKRAJ, H - 10));

  const svg =
    `<svg class="graf-svg mapa-svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" ` +
    `preserveAspectRatio="xMidYMid meet" role="group" aria-label="${escSvg(nastaveni.popis)}">` +
    casti.join('') +
    '</svg>';

  return { svg, sirka: W, vyska: H, prazdna: false, bezGeometrie, poznamky: [] };
}

function spocitejVyrez(vrstvy: VrstvaMapy[]): Vyrez | null {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  let minLat = Infinity;
  let maxLat = -Infinity;

  for (const v of vrstvy) {
    for (const p of v.prvky) {
      for (const t of p.tvary) {
        for (const prst of t.prstence) {
          for (const [lon, lat] of prst) {
            const m = mercator(lon, lat);
            if (m.x < minX) minX = m.x;
            if (m.x > maxX) maxX = m.x;
            if (m.y < minY) minY = m.y;
            if (m.y > maxY) maxY = m.y;
            if (lat < minLat) minLat = lat;
            if (lat > maxLat) maxLat = lat;
          }
        }
      }
    }
  }
  if (!Number.isFinite(minX) || !Number.isFinite(minY)) return null;

  // Jediný bod nebo svislá čára: rozšířit na ~600 m, ať se dá vůbec vykreslit.
  const MIN_ROZSAH = 600 / Math.cos((((minLat + maxLat) / 2) * Math.PI) / 180);
  if (maxX - minX < MIN_ROZSAH) {
    const s = (minX + maxX) / 2;
    minX = s - MIN_ROZSAH / 2;
    maxX = s + MIN_ROZSAH / 2;
  }
  if (maxY - minY < MIN_ROZSAH) {
    const s = (minY + maxY) / 2;
    minY = s - MIN_ROZSAH / 2;
    maxY = s + MIN_ROZSAH / 2;
  }

  return { minX, minY, maxX, maxY, stredLat: (minLat + maxLat) / 2 };
}

function prvekSvg(
  p: PrvekMapy,
  druh: Druh,
  proj: (lon: number, lat: number) => [number, number],
  nalehko = false,
  pruhledna = false,
): string {
  const tridy = ['mapa-prvek', `mapa-prvek--${druh}`];
  if (p.bezDat) tridy.push('mapa-prvek--bez-dat');
  const tridaPlochy = pruhledna ? 'mapa-plocha mapa-plocha--pruhledna' : 'mapa-plocha';

  // U vrstvy kreslené nalehko nese barvu skupina vrstvy, ne každý prvek —
  // u tisíců bodů ušetří opakovaný atribut stovky kilobajtů HTML.
  const vypln = nalehko ? '' : ` fill="${p.barva}"`;

  const telo: string[] = [];
  for (const t of p.tvary) {
    if (t.druh === 'bod') {
      const b = t.prstence[0]?.[0];
      if (!b) continue;
      const [x, y] = proj(b[0], b[1]);
      telo.push(
        nalehko
          ? `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4"/>`
          : `<circle class="mapa-bod" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="5"${vypln}/>`,
      );
    } else if (t.druh === 'linie') {
      const d = cesta(t.prstence, proj, false);
      if (d) telo.push(`<path class="mapa-linie" d="${d}"${nalehko ? '' : ` stroke="${p.barva}"`} fill="none"/>`);
    } else {
      const d = cesta(t.prstence, proj, true);
      if (d) {
        telo.push(
          p.bezDat
            ? `<path class="mapa-plocha mapa-plocha--bez-dat" d="${d}" fill-rule="evenodd"/>`
            : `<path class="${tridaPlochy}" d="${d}"${vypln} fill-rule="evenodd"/>`,
        );
      }
    }
  }
  if (telo.length === 0) return '';

  // Nalehko: jen tvar s `<title>`, bez tooltipu a bez tříd na každém prvku.
  if (nalehko) {
    return `<g><title>${escSvg(p.popis)}</title>${telo.join('')}</g>`;
  }

  // Prvky jsou mimo pořadí tabulátoru — u stovek polygonů a bodů by z nich byly
  // stovky zastávek. Kompletní data i odkazy nese povinný tabulkový pohled.
  const atributy =
    `${tipAtribut(p.nazev, p.tip, p.bezDat ? undefined : p.barva, false)} tabindex="-1" aria-hidden="true" ` +
    `class="${tridy.join(' ')}"`;
  const vnitrek = `<title>${escSvg(p.popis)}</title>${telo.join('')}`;

  return p.odkaz
    ? `<a href="${escSvg(p.odkaz)}" ${atributy}>${vnitrek}</a>`
    : `<g ${atributy}>${vnitrek}</g>`;
}

/** Cesta z prstenců. Body blíž než 0.35 px se vynechávají — na oko nepoznáte, v HTML ano. */
function cesta(
  prstence: [number, number][][],
  proj: (lon: number, lat: number) => [number, number],
  uzavrit: boolean,
): string {
  const casti: string[] = [];
  for (const prst of prstence) {
    let posledni: [number, number] | null = null;
    const body: string[] = [];
    for (const [lon, lat] of prst) {
      const [x, y] = proj(lon, lat);
      if (posledni && Math.abs(x - posledni[0]) < 0.35 && Math.abs(y - posledni[1]) < 0.35) continue;
      body.push(`${x.toFixed(1)} ${y.toFixed(1)}`);
      posledni = [x, y];
    }
    if (body.length < 2) continue;
    casti.push(`M${body.join('L')}${uzavrit ? 'Z' : ''}`);
  }
  return casti.join('');
}

/* ─────────────────────────  Rampa a legendy  ───────────────────────── */

/**
 * Krok sekvenční rampy pro veličinu, která se nemění o řády — účast, podíl
 * hlasů, hustota. `krokRampy()` z `barvy.ts` je logaritmický (částky se liší
 * o řády); na účasti v pásmu 40–65 % by logaritmus splácl všechno do jednoho
 * odstínu.
 */
export function krokRampyLinearni(hodnota: number, min: number, max: number): number {
  if (!(max > min)) return Math.floor(KROKU_RAMPY / 2);
  const t = (hodnota - min) / (max - min);
  return Math.min(KROKU_RAMPY - 1, Math.max(0, Math.round(t * (KROKU_RAMPY - 1))));
}

/**
 * Legenda sekvenční rampy s vlastními popisky krajů. Políčko „bez dat" je
 * oddělené — plocha bez údaje se nesmí splést s nejnižším krokem rampy.
 */
export function legendaRampyObecna(od: string, doo: string, bezDat = 'bez údaje'): LegendaPolozka[] {
  const polozky: LegendaPolozka[] = [{ nazev: bezDat, barva: 'var(--surface-2)', tvar: 'prazdno' }];
  for (let i = 0; i < KROKU_RAMPY; i++) {
    polozky.push({
      nazev: i === 0 ? od : i === KROKU_RAMPY - 1 ? doo : '',
      barva: cssKrokRampy(i),
      tvar: 'ramp',
    });
  }
  return polozky;
}

/** Grafické měřítko. Bez něj mapa neříká, jestli je vidět ulice, nebo okres. */
function meritkoSvg(vyrez: Vyrez, meritkoPx: number, x: number, y: number): string {
  // V Mercatoru je vzdálenost nadhodnocená o 1/cos(šířka) — zpět na metry v terénu.
  const metryNaPx = Math.cos((vyrez.stredLat * Math.PI) / 180) / meritkoPx;
  const cil = 120 * metryNaPx;
  const exp = Math.floor(Math.log10(Math.max(1, cil)));
  const zaklad = 10 ** exp;
  const podil = cil / zaklad;
  const delkaM = (podil >= 5 ? 5 : podil >= 2 ? 2 : 1) * zaklad;
  const px = delkaM / metryNaPx;
  const popisek = delkaM >= 1000 ? `${(delkaM / 1000).toLocaleString('cs-CZ')} km` : `${delkaM} m`;

  return (
    `<g class="mapa-meritko" aria-hidden="true">` +
    `<line x1="${x}" y1="${y}" x2="${(x + px).toFixed(1)}" y2="${y}"/>` +
    `<line x1="${x}" y1="${y - 4}" x2="${x}" y2="${y + 4}"/>` +
    `<line x1="${(x + px).toFixed(1)}" y1="${y - 4}" x2="${(x + px).toFixed(1)}" y2="${y + 4}"/>` +
    `<text class="g-popisek" x="${(x + px + 8).toFixed(1)}" y="${y + 4}">${escSvg(popisek)}</text>` +
    `</g>`
  );
}
