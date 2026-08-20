/**
 * Generátory grafů. SVG se skládá při buildu — data jsou v tu chvíli známá,
 * takže runtime grafová knihovna by jen zdržovala. Klientský JS dělá jen hover
 * a tooltip (obsluha je v src/layouts/Zaklad.astro).
 *
 * Barvy jsou CSS tokeny (`var(--g1)`, `var(--r5)`), ne natvrdo zapsané hexy —
 * díky tomu jeden vygenerovaný SVG obslouží světlý i tmavý režim a nemusí
 * existovat dvě verze obrázku.
 *
 * Pravidla, která tenhle soubor drží (web/DESIGN.md §2):
 *   – nikdy dvě osy Y
 *   – barva podle IČO, ne podle indexu
 *   – 7. a další subjekt → „Ostatní"
 *   – ke každému grafu patří tabulkový pohled (staví ho GrafKarta.astro z `tabulka`)
 *   – popisky a čísla v barvě textu, nikdy v barvě série
 */
import { cssKrokRampy, krokRampy, KROKU_RAMPY } from './barvy';
import { cislo, kc, kcZkraceno } from './format';
import type { PasmoObdobi } from './obdobi';

/* ───────────────────────────────  Typy  ─────────────────────────────── */

export interface LegendaPolozka {
  nazev: string;
  barva: string;
  /** `rect` pro plochy a sloupce, `ramp` pro sekvenční škálu, `prazdno` pro „bez plateb". */
  tvar: 'rect' | 'ramp' | 'prazdno';
  odkaz?: string;
}

export interface Sloupec {
  nazev: string;
  /** Číselné sloupce se zarovnávají doprava a dostanou tabular-nums. */
  cislo?: boolean;
}

export interface Tabulka {
  hlavicka: Sloupec[];
  radky: string[][];
}

export interface Graf {
  svg: string;
  /** `null` = jedna série, legenda se nekreslí (název grafu ji pojmenuje). */
  legenda: LegendaPolozka[] | null;
  tabulka: Tabulka;
  /** Poznámky pod graf — např. „zobrazeno 40 ze 128 protistran". */
  poznamky: string[];
  /** Vnitřní šířka SVG v px — kontejner podle ní pozná, kdy scrollovat. */
  sirka: number;
}

/* ─────────────────────────────  Pomocníci  ──────────────────────────── */

function esc(s: string): string {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export interface TipRadek {
  l: string;
  v: string;
}

/**
 * Vyrobí atribut `data-tip`. Obsah čte klientský skript a vkládá přes textContent.
 * `fokus: false` u prvků, které už fokusovatelné jsou (odkazy) nebo kterých je
 * tolik, že by z tabulátoru udělaly nekonečnou cestu (buňky heatmapy).
 */
function tip(nadpis: string, radky: TipRadek[], barva?: string, fokus = true): string {
  const payload = JSON.stringify({ t: nadpis, r: radky.map((x) => [x.l, x.v]), c: barva ?? null });
  return `data-tip="${esc(payload)}"${fokus ? ' tabindex="0"' : ''}`;
}

/** Sloupec se zaoblenou horní hranou a rovnou patou na základní čáře. */
function sloupecPath(x: number, y: number, w: number, h: number, r = 4): string {
  if (!(h > 0) || !(w > 0)) return '';
  const rr = Math.min(r, w / 2, h);
  return `M${x} ${y + h} L${x} ${y + rr} Q${x} ${y} ${x + rr} ${y} L${x + w - rr} ${y} Q${x + w} ${y} ${x + w} ${y + rr} L${x + w} ${y + h} Z`;
}

function osaY(max: number, pocetTiku = 4): { horni: number; tiky: number[] } {
  if (!(max > 0)) return { horni: 1, tiky: [0, 1] };
  const hruby = max / pocetTiku;
  const exp = Math.floor(Math.log10(hruby));
  const zaklad = 10 ** exp;
  const podil = hruby / zaklad;
  const krok = (podil <= 1 ? 1 : podil <= 2 ? 2 : podil <= 5 ? 5 : 10) * zaklad;
  const horni = Math.ceil(max / krok) * krok;
  const tiky: number[] = [];
  for (let v = 0; v <= horni + krok * 1e-9; v += krok) tiky.push(Number(v.toFixed(6)));
  return { horni, tiky };
}

/** Doplní chybějící roky nulou. Bez tohohle se časová osa scvrkne a lže. */
export function souvisleRoky(roky: number[]): number[] {
  const platne = roky.filter((r) => Number.isFinite(r));
  if (platne.length === 0) return [];
  const od = Math.min(...platne);
  const doo = Math.max(...platne);
  const ven: number[] = [];
  for (let r = od; r <= doo; r++) ven.push(r);
  return ven;
}

const MAX_SLOUPEC = 24; // DESIGN/dataviz: sloupec nikdy nevyplní celý slot

/* ───────────────────  3.1 Objem plateb města po letech  ─────────────── */

export interface BodObjemu {
  rok: number;
  castka: number;
  /** `null`, když se počet smluv za rok z dat nedá zjistit — nedopočítáváme ho. */
  smluv: number | null;
}

export function grafObjemPoLetech(body: BodObjemu[], titulek = 'Objem plateb po letech'): Graf {
  const W = 900;
  const H = 330;
  const m = { t: 24, r: 20, b: 46, l: 82 };
  const pw = W - m.l - m.r;
  const ph = H - m.t - m.b;

  const { horni, tiky } = osaY(Math.max(0, ...body.map((b) => b.castka)));
  const n = Math.max(1, body.length);
  const band = pw / n;
  const bw = Math.min(MAX_SLOUPEC, band * 0.6);
  const y = (v: number) => m.t + ph - (v / horni) * ph;

  const maxCastka = Math.max(0, ...body.map((b) => b.castka));
  const krokPopisku = body.length > 16 ? 2 : 1;

  const casti: string[] = [];

  // Mřížka a osa Y
  for (const t of tiky) {
    casti.push(
      `<line class="g-mrizka" x1="${m.l}" y1="${y(t).toFixed(1)}" x2="${m.l + pw}" y2="${y(t).toFixed(1)}"/>`,
      `<text class="g-popisek g-popisek--y" x="${m.l - 12}" y="${(y(t) + 4).toFixed(1)}">${esc(kcZkraceno(t))}</text>`,
    );
  }
  casti.push(`<line class="g-osa" x1="${m.l}" y1="${m.t + ph}" x2="${m.l + pw}" y2="${m.t + ph}"/>`);

  body.forEach((b, i) => {
    const x = m.l + band * i + (band - bw) / 2;
    const h = b.castka > 0 ? Math.max(1.5, (b.castka / horni) * ph) : 0;
    const top = m.t + ph - h;
    const radky: TipRadek[] = [{ l: 'Objem', v: kc(b.castka) }];
    if (b.smluv !== null) radky.push({ l: 'Smluv', v: cislo(b.smluv) });
    else radky.push({ l: 'Smluv', v: 'v datech není' });

    casti.push(`<g class="g-sloupec" ${tip(String(b.rok), radky, 'var(--g1)')} role="img" aria-label="${esc(`${b.rok}: ${kc(b.castka)}`)}">`);
    // Průhledný terč přes celý slot — hover nemá záviset na trefení 24px pruhu.
    casti.push(`<rect class="g-terc" x="${(m.l + band * i).toFixed(1)}" y="${m.t}" width="${band.toFixed(1)}" height="${ph}"/>`);
    if (h > 0) casti.push(`<path class="g-vypln" d="${sloupecPath(x, top, bw, h)}" fill="var(--g1)"/>`);
    // Přímý popisek jen u maxima — číslo u každého sloupce se nečte.
    if (b.castka > 0 && b.castka === maxCastka) {
      casti.push(`<text class="g-hodnota" x="${(x + bw / 2).toFixed(1)}" y="${(top - 9).toFixed(1)}">${esc(kcZkraceno(b.castka))}</text>`);
    }
    casti.push('</g>');

    if (i % krokPopisku === 0) {
      casti.push(`<text class="g-popisek g-popisek--x" x="${(m.l + band * i + band / 2).toFixed(1)}" y="${m.t + ph + 24}">${b.rok}</text>`);
    }
  });

  return {
    sirka: W,
    svg: obalSvg(W, H, casti.join(''), `${titulek}: sloupcový graf, ${body.length} let`),
    legenda: null, // jedna série — legenda by jen zopakovala název grafu
    tabulka: {
      hlavicka: [{ nazev: 'Rok' }, { nazev: 'Objem', cislo: true }, { nazev: 'Smluv', cislo: true }],
      // Tabulka jde od NEJNOVĚJŠÍHO roku, graf zůstává chronologicky.
      // Čtenář hledá nejdřív poslední rok; kdyby výpis začínal rokem 1994,
      // vidí na prvních řádcích prázdné buňky a musí se prorolovat.
      radky: [...body]
        .reverse()
        .map((b) => [String(b.rok), kc(b.castka), b.smluv === null ? 'v datech není' : cislo(b.smluv)]),
    },
    poznamky: [],
  };
}

/* ──────────────  Vodorovný sloupcový graf — jedna série  ────────────── */

export interface BodVodorovny {
  nazev: string;
  hodnota: number;
  /** Volitelný odkaz z popisku řádku. */
  odkaz?: string;
  /** Doplňkové řádky do tooltipu — např. „z toho pro: 12". */
  doplnky?: { l: string; v: string }[];
}

/**
 * Vodorovné sloupce se hodí tam, kde jsou popisky dlouhé (názvy témat, druhy
 * hlasů, jména firem) — svislý graf by je musel otáčet a to se špatně čte.
 *
 * Jedna série, tedy podle web/DESIGN.md §2 bez legendy: název grafu ji
 * pojmenuje. Čísla jsou v barvě textu, nikdy v barvě sloupce.
 */
export function grafVodorovny(
  body: BodVodorovny[],
  titulek: string,
  formatuj: (v: number) => string = (v) => cislo(v),
): Graf {
  const SIRKA_POPISKU = 210;
  const W = 900;
  const VYSKA_RADKU = 22;
  const MEZERA = 8;
  const m = { t: 10, r: 96, b: 34 };
  const pw = W - SIRKA_POPISKU - m.r;
  const H = m.t + body.length * (VYSKA_RADKU + MEZERA) + m.b;

  const { horni, tiky } = osaY(Math.max(0, ...body.map((b) => b.hodnota)), 4);
  const x = (v: number) => SIRKA_POPISKU + (v / horni) * pw;

  const casti: string[] = [];
  const spodek = m.t + body.length * (VYSKA_RADKU + MEZERA);

  for (const t of tiky) {
    casti.push(
      `<line class="g-mrizka" x1="${x(t).toFixed(1)}" y1="${m.t}" x2="${x(t).toFixed(1)}" y2="${spodek}"/>`,
      `<text class="g-popisek g-popisek--x" x="${x(t).toFixed(1)}" y="${spodek + 20}">${esc(formatuj(t))}</text>`,
    );
  }
  casti.push(`<line class="g-osa" x1="${SIRKA_POPISKU}" y1="${m.t}" x2="${SIRKA_POPISKU}" y2="${spodek}"/>`);

  body.forEach((b, i) => {
    const y = m.t + i * (VYSKA_RADKU + MEZERA);
    const sirka = b.hodnota > 0 ? Math.max(1.5, (b.hodnota / horni) * pw) : 0;
    const popisek = zkratNazev(b.nazev);

    casti.push(
      b.odkaz
        ? `<a href="${esc(b.odkaz)}" class="g-radek-odkaz"><text class="g-radek-nazev" x="0" y="${(y + VYSKA_RADKU - 6).toFixed(1)}">${esc(popisek)}</text></a>`
        : `<text class="g-radek-nazev" x="0" y="${(y + VYSKA_RADKU - 6).toFixed(1)}">${esc(popisek)}</text>`,
    );

    const radky: TipRadek[] = [{ l: 'Hodnota', v: formatuj(b.hodnota) }, ...(b.doplnky ?? [])];
    casti.push(
      `<g class="g-sloupec" ${tip(b.nazev, radky, 'var(--g1)')} role="img" aria-label="${esc(`${b.nazev}: ${formatuj(b.hodnota)}`)}">`,
      `<rect class="g-terc" x="${SIRKA_POPISKU}" y="${y}" width="${pw}" height="${VYSKA_RADKU}"/>`,
    );
    if (sirka > 0) {
      casti.push(
        `<rect class="g-vypln" x="${SIRKA_POPISKU}" y="${y}" width="${sirka.toFixed(1)}" height="${VYSKA_RADKU}" rx="3" fill="var(--g1)"/>`,
      );
    }
    casti.push(
      `<text class="g-hodnota g-hodnota--vlevo" x="${(SIRKA_POPISKU + sirka + 8).toFixed(1)}" y="${(y + VYSKA_RADKU - 6).toFixed(1)}">${esc(formatuj(b.hodnota))}</text>`,
      '</g>',
    );
  });

  return {
    sirka: W,
    svg: obalSvg(W, H, casti.join(''), `${titulek}: vodorovný sloupcový graf, ${body.length} položek`),
    legenda: null,
    tabulka: {
      hlavicka: [{ nazev: 'Položka' }, { nazev: 'Hodnota', cislo: true }],
      radky: body.map((b) => [b.nazev, formatuj(b.hodnota)]),
    },
    poznamky: [],
  };
}

/* ────────────────────  3.2 Kdo od města dostává peníze  ─────────────── */

export interface SerieSkladana {
  /** Klíč protistrany pro odkaz. `null` u agregované série „Ostatní". */
  klic: string | null;
  nazev: string;
  barva: string;
  /** Hodnoty v pořadí `roky`. */
  hodnoty: number[];
  smluv?: number | null;
}

export function grafSkladany(roky: number[], serie: SerieSkladana[], titulek: string): Graf {
  const W = 900;
  const H = 360;
  const m = { t: 24, r: 20, b: 46, l: 82 };
  const pw = W - m.l - m.r;
  const ph = H - m.t - m.b;
  const MEZERA = 2; // 2px mezera v barvě povrchu mezi segmenty (DESIGN §3.2)

  const soucty = roky.map((_, i) => serie.reduce((s, x) => s + (x.hodnoty[i] ?? 0), 0));
  const { horni, tiky } = osaY(Math.max(0, ...soucty));
  const n = Math.max(1, roky.length);
  const band = pw / n;
  const bw = Math.min(MAX_SLOUPEC, band * 0.6);
  const y = (v: number) => m.t + ph - (v / horni) * ph;

  const casti: string[] = [];
  for (const t of tiky) {
    casti.push(
      `<line class="g-mrizka" x1="${m.l}" y1="${y(t).toFixed(1)}" x2="${m.l + pw}" y2="${y(t).toFixed(1)}"/>`,
      `<text class="g-popisek g-popisek--y" x="${m.l - 12}" y="${(y(t) + 4).toFixed(1)}">${esc(kcZkraceno(t))}</text>`,
    );
  }
  casti.push(`<line class="g-osa" x1="${m.l}" y1="${m.t + ph}" x2="${m.l + pw}" y2="${m.t + ph}"/>`);

  const krokPopisku = roky.length > 16 ? 2 : 1;

  roky.forEach((rok, i) => {
    const x = m.l + band * i + (band - bw) / 2;
    let kumul = 0;
    const nenulove = serie.filter((s) => (s.hodnoty[i] ?? 0) > 0);

    // Terč přes celý slot: tooltip vypíše všechny série za daný rok najednou.
    const radkyRoku: TipRadek[] = nenulove
      .slice()
      .reverse()
      .map((s) => ({ l: s.nazev, v: kc(s.hodnoty[i] ?? 0) }));
    radkyRoku.push({ l: 'Celkem', v: kc(soucty[i]) });
    casti.push(
      `<g class="g-sloupec" ${tip(String(rok), radkyRoku)} role="img" aria-label="${esc(`${rok}: celkem ${kc(soucty[i])}`)}">`,
      `<rect class="g-terc" x="${(m.l + band * i).toFixed(1)}" y="${m.t}" width="${band.toFixed(1)}" height="${ph}"/>`,
    );

    nenulove.forEach((s, poradiOdSpodu) => {
      const v = s.hodnoty[i] ?? 0;
      const celaVyska = (v / horni) * ph;
      const spodek = m.t + ph - (kumul / horni) * ph;
      kumul += v;
      const jeHorni = poradiOdSpodu === nenulove.length - 1;
      const vyska = Math.max(1, celaVyska - MEZERA);
      const top = spodek - MEZERA / 2 - vyska;
      const d = jeHorni ? sloupecPath(x, top, bw, vyska, 4) : `M${x} ${top} h${bw} v${vyska} h${-bw} Z`;
      if (d) casti.push(`<path class="g-vypln" d="${d}" fill="${s.barva}"/>`);
    });

    casti.push('</g>');

    if (i % krokPopisku === 0) {
      casti.push(`<text class="g-popisek g-popisek--x" x="${(m.l + band * i + band / 2).toFixed(1)}" y="${m.t + ph + 24}">${rok}</text>`);
    }
  });

  return {
    sirka: W,
    svg: obalSvg(W, H, casti.join(''), `${titulek}: skládaný sloupcový graf, ${serie.length} sérií, ${roky.length} let`),
    // Legenda v pořadí podle objemu (stejně jako se stohuje odspodu),
    // aby šlo přiřadit barvu k firmě bez luštění pořadí v sloupci.
    legenda: serie.map((s) => ({
      nazev: s.nazev,
      barva: s.barva,
      tvar: 'rect' as const,
      odkaz: s.klic ? `/penize/${s.klic}` : undefined,
    })),
    tabulka: {
      hlavicka: [{ nazev: 'Rok' }, ...serie.map((s) => ({ nazev: s.nazev, cislo: true })), { nazev: 'Celkem', cislo: true }],
      // Od nejnovějšího roku — viz poznámka u sloupcového grafu.
      radky: roky
        .map((rok, i) => [String(rok), ...serie.map((s) => kc(s.hodnoty[i] ?? 0)), kc(soucty[i])])
        .reverse(),
    },
    poznamky: [],
  };
}

/* ────────────  3.3 Časová osa protistran — heatmapa  ───────────── */

export interface RadekHeatmapy {
  klic: string;
  nazev: string;
  /** Délka odpovídá `roky`. `0` znamená „v tom roce žádné peníze". */
  hodnoty: number[];
  /** Počty smluv za rok. `null` = z dat se nedají zjistit, nedopočítáváme je. */
  pocty?: (number | null)[];
  celkem: number;
  smluv: number;
  prvni_rok: number;
  posledni_rok: number;
}

export interface HeatmapaVysledek extends Graf {
  /** Hranice rampy pro legendu — od / do v Kč. */
  rampaOd: number;
  rampaDo: number;
}

export function grafHeatmapa(
  roky: number[],
  radky: RadekHeatmapy[],
  /**
   * Pásma volebních období nad osou let. Nesou význam textem (roky a jména),
   * ne barvou — střídavý podklad pásma jen odděluje sousedy. Podklad se kreslí
   * POUZE v hlavičce: tónovat celé sloupce by posunulo vnímané odstíny rampy
   * a heatmapa by lhala o částkách.
   */
  obdobi: PasmoObdobi[] = [],
): HeatmapaVysledek {
  const SIRKA_POPISKU = 226;
  const CW = 34;
  const CH = 21;
  const MEZERA = 3;
  const pasma = obdobi.filter((p) => roky.includes(p.odRok) || roky.includes(p.doRok));
  const VYSKA_PASEM = pasma.length > 0 ? 34 : 0;
  const HLAVICKA = 30 + VYSKA_PASEM;
  const SPODEK = 8;

  const W = SIRKA_POPISKU + roky.length * (CW + MEZERA) + 12;
  const H = HLAVICKA + radky.length * (CH + MEZERA) + SPODEK;

  // Rozsah rampy počítáme jen z kladných hodnot. Nula do rampy nepatří —
  // je to prázdná buňka, ne nejsvětlejší krok.
  const kladne: number[] = [];
  for (const r of radky) for (const v of r.hodnoty) if (v > 0) kladne.push(v);
  const rampaOd = kladne.length ? Math.min(...kladne) : 0;
  const rampaDo = kladne.length ? Math.max(...kladne) : 0;

  const casti: string[] = [];

  // Pásma volebních období: podklad + dva řádky textu (roky, starostové)
  // a svislý předěl mezi obdobími přes celou výšku mřížky.
  // Text pásma se musí vejít do jeho šířky — oříznuté pásmo na kraji osy má
  // třeba jen jeden sloupec a přetékající popisek by se slil se sousedním.
  // Úplný výčet jmen se stranami nese věta pod grafem, tady je jen zkratka.
  const doSirky = (s: string, sirkaPx: number): string | null => {
    const max = Math.floor(sirkaPx / 6.5); // ~šířka znaku při 10,5px sans
    if (max < 5) return null;
    const cely = s.replace(/\s+/g, ' ').trim();
    return cely.length <= max ? cely : `${cely.slice(0, max - 1).trimEnd()}…`;
  };

  pasma.forEach((p, pi) => {
    const iOd = roky.indexOf(p.odRok);
    const iDo = roky.indexOf(p.doRok);
    if (iOd < 0 || iDo < 0) return;
    const x0 = SIRKA_POPISKU + iOd * (CW + MEZERA);
    const x1 = SIRKA_POPISKU + iDo * (CW + MEZERA) + CW;
    const stred = (x0 + x1) / 2;
    // Střídavý podklad jen odděluje sousední pásma; význam nese text.
    if (pi % 2 === 0) {
      casti.push(`<rect class="g-pasmo" x="${x0.toFixed(1)}" y="2" width="${(x1 - x0).toFixed(1)}" height="${VYSKA_PASEM - 6}" rx="3"/>`);
    }
    if (pi > 0) {
      casti.push(
        `<line class="g-predel" x1="${(x0 - MEZERA / 2).toFixed(1)}" y1="2" x2="${(x0 - MEZERA / 2).toFixed(1)}" y2="${(H - SPODEK).toFixed(1)}"/>`,
      );
    }
    const radek1 = doSirky(p.nazev, x1 - x0);
    const radek2 = doSirky(p.starostove, x1 - x0);
    if (radek1) casti.push(`<text class="g-popisek g-popisek--pasmo" x="${stred.toFixed(1)}" y="14">${esc(radek1)}</text>`);
    if (radek2) casti.push(`<text class="g-popisek g-popisek--pasmo" x="${stred.toFixed(1)}" y="26">${esc(radek2)}</text>`);
  });

  roky.forEach((rok, i) => {
    const x = SIRKA_POPISKU + i * (CW + MEZERA) + CW / 2;
    casti.push(`<text class="g-popisek g-popisek--x" x="${x.toFixed(1)}" y="${HLAVICKA - 12}">${rok}</text>`);
  });

  radky.forEach((r, ri) => {
    const y = HLAVICKA + ri * (CH + MEZERA);
    casti.push(
      `<a href="/penize/${esc(r.klic)}" class="g-radek-odkaz" aria-label="${esc(`Detail protistrany ${r.nazev}`)}">` +
        `<text class="g-radek-nazev" x="0" y="${(y + CH - 6).toFixed(1)}">${esc(zkratNazev(r.nazev))}</text>` +
        `</a>`,
    );

    roky.forEach((rok, ci) => {
      const x = SIRKA_POPISKU + ci * (CW + MEZERA);
      const v = r.hodnoty[ci] ?? 0;
      const maPenize = v > 0;

      const radkyTipu: TipRadek[] = [
        { l: 'Rok', v: String(rok) },
        { l: 'Částka', v: maPenize ? kc(v) : 'žádná platba' },
      ];
      const pocet = r.pocty?.[ci];
      if (maPenize) {
        radkyTipu.push({ l: 'Smluv', v: pocet === null || pocet === undefined ? 'v datech není' : cislo(pocet) });
      }
      if (!maPenize) {
        radkyTipu.push({
          l: 'Poznámka',
          v: rok < r.prvni_rok ? 'před první smlouvou' : rok > r.posledni_rok ? 'po poslední smlouvě' : 'v tomto roce nic',
        });
      }

      const popis = `${r.nazev}, ${rok}: ${maPenize ? kc(v) : 'žádná platba'}`;
      const spolecne = `x="${x}" y="${y}" width="${CW}" height="${CH}" rx="2"`;

      // Buňky jsou mimo pořadí tabulátoru — u 40 řádků × 10 let by z nich byly
      // stovky zastávek. Kompletní data nese povinný tabulkový pohled pod grafem.
      casti.push(
        `<a href="/penize/${esc(r.klic)}" ${tip(r.nazev, radkyTipu, undefined, false)} tabindex="-1" aria-hidden="true" title="${esc(popis)}" class="g-bunka-odkaz">`,
      );
      if (maPenize) {
        casti.push(`<rect class="g-bunka" ${spolecne} fill="${cssKrokRampy(krokRampy(v, rampaOd, rampaDo))}"/>`);
      } else {
        // ZÁSADNÍ: prázdná buňka je barva povrchu s tenkým rámečkem,
        // NIKDY nejsvětlejší krok rampy — jinak graf lže o tom, kdy firma
        // začala a přestala brát peníze (web/DESIGN.md §3.3).
        casti.push(`<rect class="g-bunka g-bunka--prazdna" ${spolecne}/>`);
      }
      casti.push('</a>');
    });
  });

  return {
    sirka: W,
    rampaOd,
    rampaDo,
    svg: obalSvg(W, H, casti.join(''), `Heatmapa: ${radky.length} protistran, roky ${roky[0] ?? '?'}–${roky[roky.length - 1] ?? '?'}`),
    legenda: null, // heatmapa má vlastní legendu rampy, staví ji GrafKarta
    tabulka: {
      hlavicka: [{ nazev: 'Protistrana' }, { nazev: 'Od', cislo: true }, { nazev: 'Do', cislo: true }, ...roky.map((r) => ({ nazev: String(r), cislo: true })), { nazev: 'Celkem', cislo: true }],
      radky: radky.map((r) => [
        r.nazev,
        String(r.prvni_rok),
        String(r.posledni_rok),
        ...r.hodnoty.map((v) => (v > 0 ? kc(v) : '—')),
        kc(r.celkem),
      ]),
    },
    poznamky: [],
  };
}

/** Legenda rampy pro heatmapu — včetně odděleného políčka „bez plateb". */
export function legendaRampy(od: number, doo: number): LegendaPolozka[] {
  const kroky: LegendaPolozka[] = [];
  for (let i = 0; i < KROKU_RAMPY; i++) {
    kroky.push({ nazev: '', barva: cssKrokRampy(i), tvar: 'ramp' });
  }
  const polozky: LegendaPolozka[] = [
    { nazev: 'bez plateb', barva: 'var(--surface)', tvar: 'prazdno' },
    ...kroky,
  ];
  return polozky.map((p, i) =>
    i === 1 ? { ...p, nazev: kcZkraceno(od) } : i === KROKU_RAMPY ? { ...p, nazev: kcZkraceno(doo) } : p,
  );
}

function zkratNazev(s: string): string {
  const cisty = s.replace(/\s+/g, ' ').trim();
  return cisty.length > 30 ? `${cisty.slice(0, 29).trimEnd()}…` : cisty;
}

function obalSvg(w: number, h: number, obsah: string, popis: string): string {
  return (
    // role="group", ne "img" — uvnitř jsou fokusovatelné prvky a odkazy,
    // které by se pod role="img" staly pro odečítač nedosažitelné.
    `<svg class="graf-svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" ` +
    `preserveAspectRatio="xMinYMin meet" role="group" aria-label="${esc(popis)}">` +
    obsah +
    '</svg>'
  );
}

/* ─────────  Sdílené stavební kameny pro mapy a časové osy  ─────────
 * Mapa (§3.6) i časová osa (§3.7) se kreslí při buildu do SVG úplně stejně
 * jako grafy. Aby escapovaly, obalovaly a tooltipovaly shodně — a aby se
 * chování nezačalo rozcházet ve dvou kopiích téhož kódu — vyváží se tyhle
 * funkce beze změny. Nic se tím v grafech nemění.
 */
export {
  esc as escSvg,
  tip as tipAtribut,
  obalSvg as obalSvgGrafu,
  zkratNazev,
  osaY as osaYGrafu,
  sloupecPath,
};
