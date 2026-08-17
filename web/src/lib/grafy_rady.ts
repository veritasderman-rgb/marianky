/**
 * Grafy časových řad — doplněk k `grafy.ts` pro nefinanční veličiny.
 *
 * `grafy.ts` má sloupcový graf natvrdo v korunách; obyvatelstvo, nezaměstnanost
 * ani přenocování hostů se v korunách neměří. Tenhle soubor proto přidává dvě
 * podoby téhož: sloupce jedné řady a spojnice více řad — se stejnými pravidly
 * z web/DESIGN.md §2:
 *
 *   – **Nikdy dvě osy Y.** Řady v různých jednotkách se nesmí smíchat do
 *     jednoho grafu; buď každá svůj graf, nebo index ke společnému základu
 *     (`grafIndexu`).
 *   – Ke každému grafu patří tabulkový pohled — sestavuje se tady a vykresluje
 *     ho `GrafKarta.astro`.
 *   – Popisky a čísla v barvě textu, nikdy v barvě série.
 */
import { cssBarvaSlotu, MAX_KATEGORII } from './barvy';
import { cislo } from './format';
import { escSvg, obalSvgGrafu, osaYGrafu, sloupecPath, tipAtribut, zkratNazev, type Graf, type TipRadek } from './grafy';

export interface BodRady {
  rok: number;
  /** `null` znamená „za tenhle rok údaj není" — kreslí se jako mezera, ne nula. */
  hodnota: number | null;
  poznamka?: string | null;
}

const MAX_SLOUPEC = 24;

/**
 * Sloupcový graf jedné řady po letech. Roky se nepřeskakují — volající je
 * doplní přes `souvisleRoky()`. Rok bez údaje je prázdné místo s popiskem
 * „údaj chybí", nikdy nulový sloupec: nula a „nezjištěno" nejsou totéž.
 */
export function grafRadaPoLetech(
  body: BodRady[],
  titulek: string,
  jednotka: string | null,
  formatuj: (v: number) => string = cislo,
): Graf {
  const W = 900;
  const H = 320;
  const m = { t: 24, r: 20, b: 46, l: 88 };
  const pw = W - m.l - m.r;
  const ph = H - m.t - m.b;

  const hodnoty = body.map((b) => b.hodnota).filter((v): v is number => v !== null);
  const { horni, tiky } = osaYGrafu(Math.max(0, ...hodnoty));
  const n = Math.max(1, body.length);
  const band = pw / n;
  const bw = Math.min(MAX_SLOUPEC, band * 0.6);
  const y = (v: number) => m.t + ph - (v / horni) * ph;
  const max = hodnoty.length ? Math.max(...hodnoty) : 0;
  const krokPopisku = body.length > 16 ? Math.ceil(body.length / 16) : 1;

  const casti: string[] = [];
  for (const t of tiky) {
    casti.push(
      `<line class="g-mrizka" x1="${m.l}" y1="${y(t).toFixed(1)}" x2="${m.l + pw}" y2="${y(t).toFixed(1)}"/>`,
      `<text class="g-popisek g-popisek--y" x="${m.l - 12}" y="${(y(t) + 4).toFixed(1)}">${escSvg(formatuj(t))}</text>`,
    );
  }
  casti.push(`<line class="g-osa" x1="${m.l}" y1="${m.t + ph}" x2="${m.l + pw}" y2="${m.t + ph}"/>`);

  body.forEach((b, i) => {
    const x = m.l + band * i + (band - bw) / 2;
    const radky: TipRadek[] = [
      { l: jednotka ?? 'Hodnota', v: b.hodnota === null ? 'údaj za tenhle rok není' : formatuj(b.hodnota) },
    ];
    if (b.poznamka) radky.push({ l: 'Poznámka', v: b.poznamka });

    casti.push(
      `<g class="g-sloupec" ${tipAtribut(String(b.rok), radky, 'var(--g1)')} role="img" aria-label="${escSvg(`${b.rok}: ${b.hodnota === null ? 'údaj není' : formatuj(b.hodnota)}`)}">`,
      `<rect class="g-terc" x="${(m.l + band * i).toFixed(1)}" y="${m.t}" width="${band.toFixed(1)}" height="${ph}"/>`,
    );
    if (b.hodnota !== null && b.hodnota > 0) {
      const h = Math.max(1.5, (b.hodnota / horni) * ph);
      casti.push(`<path class="g-vypln" d="${sloupecPath(x, m.t + ph - h, bw, h)}" fill="var(--g1)"/>`);
      if (b.hodnota === max) {
        casti.push(
          `<text class="g-hodnota" x="${(x + bw / 2).toFixed(1)}" y="${(m.t + ph - h - 9).toFixed(1)}">${escSvg(formatuj(b.hodnota))}</text>`,
        );
      }
    } else if (b.hodnota === null) {
      // Chybějící údaj je vidět jako tečka u osy, ne jako nulový sloupec.
      casti.push(
        `<circle class="g-chybi" cx="${(x + bw / 2).toFixed(1)}" cy="${(m.t + ph - 5).toFixed(1)}" r="2.5"/>`,
      );
    }
    casti.push('</g>');

    if (i % krokPopisku === 0) {
      casti.push(
        `<text class="g-popisek g-popisek--x" x="${(m.l + band * i + band / 2).toFixed(1)}" y="${m.t + ph + 24}">${b.rok}</text>`,
      );
    }
  });

  const chybejicich = body.filter((b) => b.hodnota === null).length;
  const poznamky = chybejicich
    ? [
        `Za ${cislo(chybejicich)} ${chybejicich === 1 ? 'rok' : chybejicich < 5 ? 'roky' : 'let'} údaj v datech není. Takový rok je v grafu prázdný a označený tečkou u osy — není to nula.`,
      ]
    : [];

  return {
    sirka: W,
    svg: obalSvgGrafu(W, H, casti.join(''), `${titulek}: sloupcový graf, ${body.length} let`),
    legenda: null,
    tabulka: {
      hlavicka: [{ nazev: 'Rok' }, { nazev: jednotka ?? 'Hodnota', cislo: true }],
      radky: body.map((b) => [String(b.rok), b.hodnota === null ? 'údaj není' : formatuj(b.hodnota)]),
    },
    poznamky,
  };
}

/* ────────────────────────  Spojnice více řad  ──────────────────────── */

export interface SerieRady {
  klic: string;
  nazev: string;
  /** Hodnoty v pořadí `roky`; `null` = mezera, čára se přeruší. */
  hodnoty: (number | null)[];
}

/**
 * Spojnicový graf. Používat JEN pro řady ve stejné jednotce, nebo pro index
 * ke společnému základu — dvě osy Y jsou zakázané (web/DESIGN.md §2 bod 1).
 * Barvu určuje klíč série, ne pořadí; sedmá a další série spadne do „Ostatní".
 */
export function grafSpojnice(
  /** Popisky os X v pořadí — roky, měsíce, cokoliv spojitého. */
  roky: (number | string)[],
  serie: SerieRady[],
  titulek: string,
  jednotka: string | null,
  formatuj: (v: number) => string = cislo,
): Graf {
  const W = 900;
  const H = 340;
  const m = { t: 24, r: 20, b: 46, l: 88 };
  const pw = W - m.l - m.r;
  const ph = H - m.t - m.b;

  const vse = serie.flatMap((s) => s.hodnoty).filter((v): v is number => v !== null);
  const min = vse.length ? Math.min(...vse) : 0;
  const { horni, tiky } = osaYGrafu(Math.max(0, ...vse));
  const dolni = min < 0 ? Math.min(0, min) : 0;
  const y = (v: number) => m.t + ph - ((v - dolni) / (horni - dolni || 1)) * ph;
  const x = (i: number) => m.l + (roky.length > 1 ? (i / (roky.length - 1)) * pw : pw / 2);

  const casti: string[] = [];
  for (const t of tiky) {
    casti.push(
      `<line class="g-mrizka" x1="${m.l}" y1="${y(t).toFixed(1)}" x2="${m.l + pw}" y2="${y(t).toFixed(1)}"/>`,
      `<text class="g-popisek g-popisek--y" x="${m.l - 12}" y="${(y(t) + 4).toFixed(1)}">${escSvg(formatuj(t))}</text>`,
    );
  }
  casti.push(`<line class="g-osa" x1="${m.l}" y1="${m.t + ph}" x2="${m.l + pw}" y2="${m.t + ph}"/>`);

  const barva = (i: number) => cssBarvaSlotu(i < MAX_KATEGORII ? i : null);

  serie.forEach((s, si) => {
    const useky: string[] = [];
    let aktualni: string[] = [];
    s.hodnoty.forEach((v, i) => {
      if (v === null) {
        if (aktualni.length > 1) useky.push(`M${aktualni.join('L')}`);
        aktualni = [];
        return;
      }
      aktualni.push(`${x(i).toFixed(1)} ${y(v).toFixed(1)}`);
    });
    if (aktualni.length > 1) useky.push(`M${aktualni.join('L')}`);
    if (useky.length > 0) {
      casti.push(`<path class="g-spojnice" d="${useky.join('')}" stroke="${barva(si)}" fill="none"/>`);
    }
    s.hodnoty.forEach((v, i) => {
      if (v === null) return;
      casti.push(`<circle class="g-bod" cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="3" fill="${barva(si)}"/>`);
    });
  });

  // Terč přes celý rok: tooltip vypíše všechny série za daný rok najednou.
  const sirkaTerce = roky.length > 1 ? pw / (roky.length - 1) : pw;
  const krokPopisku = roky.length > 16 ? Math.ceil(roky.length / 16) : 1;
  roky.forEach((rok, i) => {
    const radky: TipRadek[] = serie.map((s) => ({
      l: zkratNazev(s.nazev),
      v: s.hodnoty[i] === null || s.hodnoty[i] === undefined ? 'údaj není' : formatuj(s.hodnoty[i] as number),
    }));
    casti.push(
      `<g class="g-sloupec" ${tipAtribut(String(rok), radky)} role="img" aria-label="${escSvg(String(rok))}">`,
      `<rect class="g-terc" x="${(x(i) - sirkaTerce / 2).toFixed(1)}" y="${m.t}" width="${sirkaTerce.toFixed(1)}" height="${ph}"/>`,
      '</g>',
    );
    if (i % krokPopisku === 0) {
      casti.push(
        `<text class="g-popisek g-popisek--x" x="${x(i).toFixed(1)}" y="${m.t + ph + 24}">${escSvg(String(rok))}</text>`,
      );
    }
  });

  return {
    sirka: W,
    svg: obalSvgGrafu(W, H, casti.join(''), `${titulek}: spojnicový graf, ${serie.length} řad, ${roky.length} období`),
    legenda:
      serie.length > 1
        ? serie.map((s, i) => ({ nazev: s.nazev, barva: barva(i), tvar: 'rect' as const }))
        : null,
    tabulka: {
      hlavicka: [{ nazev: 'Období' }, ...serie.map((s) => ({ nazev: `${s.nazev}${jednotka ? ` (${jednotka})` : ''}`, cislo: true }))],
      radky: roky.map((rok, i) => [
        String(rok),
        ...serie.map((s) => (s.hodnoty[i] === null || s.hodnoty[i] === undefined ? 'údaj není' : formatuj(s.hodnoty[i] as number))),
      ]),
    },
    poznamky: [],
  };
}
