/**
 * Grafy pro sekci Hospodaření — doplněk k `grafy.ts` a `grafy_rady.ts`.
 *
 * Dvě věci, které základní generátory neumějí a rozpočet je potřebuje:
 *
 *   1. **Záporné hodnoty.** Saldo hospodaření je schodek nebo přebytek;
 *      osa musí mít nulu uvnitř, ne na spodku. Základní sloupcový graf
 *      kreslí jen od nuly nahoru — schodek by tiše zmizel.
 *   2. **Vyznačená období.** „Tady byl covid" se nedá říct barvou sloupce
 *      (barva nesmí nést význam sama) — kreslí se podkladové pásmo přes
 *      dotčené roky a k němu textový popisek. Popisek je text v barvě
 *      popisků os, pásmo jen `--surface-2`; kdo pásmo nevidí, dočte se
 *      totéž v poznámce pod grafem, kterou přidává volající.
 *
 * Jinak platí všechna pravidla z web/DESIGN.md §2: nikdy dvě osy Y,
 * ke každému grafu tabulka, legenda při 2+ sériích, čísla v barvě textu.
 */
import { cislo, kc, kcZkraceno } from './format';
import {
  escSvg as esc,
  obalSvgGrafu,
  osaYGrafu,
  sloupecPath,
  tipAtribut,
  zkratNazev,
  type Graf,
  type TipRadek,
} from './grafy';

/** Vyznačené období na ose let — covid, ale klidně i cokoliv dalšího. */
export interface UdobiOsy {
  odRok: number;
  doRok: number;
  /** Krátký popisek do grafu („covid"). Delší vysvětlení patří do poznámky. */
  popisek: string;
}

export interface SerieKc {
  klic: string;
  nazev: string;
  /** CSS token barvy (`var(--g1)`). Barva patří veličině, ne pořadí — příjmy
   *  jsou ve všech grafech sekce stejnou barvou. */
  barva: string;
  /** Hodnoty v pořadí `roky`; `null` = údaj není, čára se přeruší. */
  hodnoty: (number | null)[];
}

const MAX_SLOUPEC = 24;

/**
 * Osa Y s nulou uvnitř. Krok se počítá z většího z |max| a |min|, aby
 * záporná část nedostala jinou hustotu než kladná.
 */
function osaYPlusMinus(hodnoty: number[]): { horni: number; dolni: number; tiky: number[] } {
  const max = Math.max(0, ...hodnoty);
  const min = Math.min(0, ...hodnoty);
  const { horni: zaklad, tiky: zakladniTiky } = osaYGrafu(Math.max(max, -min));
  const krok = zakladniTiky.length > 1 ? zakladniTiky[1] - zakladniTiky[0] : zaklad;
  const horni = max > 0 ? Math.ceil(max / krok) * krok : 0;
  const dolni = min < 0 ? -Math.ceil(-min / krok) * krok : 0;
  const tiky: number[] = [];
  for (let v = dolni; v <= horni + krok * 1e-9; v += krok) tiky.push(Number(v.toFixed(6)));
  return { horni: horni || krok, dolni, tiky };
}

/** Podkladová pásma vyznačených období + jejich popisky. */
function pasmaUdobi(
  udobi: UdobiOsy[],
  roky: number[],
  x: (i: number) => number,
  polovinaSlotu: number,
  mT: number,
  vyskaPlochy: number,
): string {
  const casti: string[] = [];
  for (const u of udobi) {
    const iOd = roky.indexOf(u.odRok);
    const iDo = roky.indexOf(u.doRok);
    if (iOd < 0 || iDo < 0) continue;
    const x0 = x(iOd) - polovinaSlotu;
    const x1 = x(iDo) + polovinaSlotu;
    casti.push(
      `<rect class="g-udobi" x="${x0.toFixed(1)}" y="${mT}" width="${(x1 - x0).toFixed(1)}" height="${vyskaPlochy}"/>`,
      `<text class="g-popisek g-popisek--pasmo" x="${((x0 + x1) / 2).toFixed(1)}" y="${mT + 13}">${esc(u.popisek)}</text>`,
    );
  }
  return casti.join('');
}

/* ─────────────────────  Spojnice v korunách s pásmy  ────────────────── */

/**
 * Spojnicový graf řad v Kč. Všechny řady jsou ve stejné jednotce (Kč) —
 * míchat sem procenta nebo počty je zakázané (nikdy dvě osy Y).
 */
export function grafRadyKc(
  roky: number[],
  serie: SerieKc[],
  titulek: string,
  udobi: UdobiOsy[] = [],
): Graf {
  const W = 900;
  const H = 340;
  const m = { t: 24, r: 20, b: 46, l: 88 };
  const pw = W - m.l - m.r;
  const ph = H - m.t - m.b;

  const vse = serie.flatMap((s) => s.hodnoty).filter((v): v is number => v !== null);
  const { horni, dolni, tiky } = osaYPlusMinus(vse);
  const y = (v: number) => m.t + ph - ((v - dolni) / (horni - dolni || 1)) * ph;
  const x = (i: number) => m.l + (roky.length > 1 ? (i / (roky.length - 1)) * pw : pw / 2);
  const polovina = roky.length > 1 ? pw / (roky.length - 1) / 2 : pw / 2;

  const casti: string[] = [];
  // Pásma pod vším ostatním — jsou to podklady, ne data.
  casti.push(pasmaUdobi(udobi, roky, x, polovina, m.t, ph));

  for (const t of tiky) {
    casti.push(
      `<line class="g-mrizka" x1="${m.l}" y1="${y(t).toFixed(1)}" x2="${m.l + pw}" y2="${y(t).toFixed(1)}"/>`,
      `<text class="g-popisek g-popisek--y" x="${m.l - 12}" y="${(y(t) + 4).toFixed(1)}">${esc(kcZkraceno(t))}</text>`,
    );
  }
  // Nula je zvýrazněná osou — u salda je to hranice mezi přebytkem a schodkem.
  casti.push(`<line class="g-osa" x1="${m.l}" y1="${y(0).toFixed(1)}" x2="${m.l + pw}" y2="${y(0).toFixed(1)}"/>`);

  serie.forEach((s) => {
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
      casti.push(`<path class="g-spojnice" d="${useky.join('')}" stroke="${s.barva}" fill="none"/>`);
    }
    s.hodnoty.forEach((v, i) => {
      if (v === null) return;
      casti.push(`<circle class="g-bod" cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="3" fill="${s.barva}"/>`);
    });
  });

  const krokPopisku = roky.length > 16 ? Math.ceil(roky.length / 16) : 1;
  roky.forEach((rok, i) => {
    const radky: TipRadek[] = serie.map((s) => ({
      l: zkratNazev(s.nazev),
      v: s.hodnoty[i] === null || s.hodnoty[i] === undefined ? 'údaj není' : kc(s.hodnoty[i] as number),
    }));
    const uTohotoRoku = udobi.find((u) => rok >= u.odRok && rok <= u.doRok);
    if (uTohotoRoku) radky.push({ l: 'Období', v: uTohotoRoku.popisek });
    casti.push(
      `<g class="g-sloupec" ${tipAtribut(String(rok), radky)} role="img" aria-label="${esc(String(rok))}">`,
      `<rect class="g-terc" x="${(x(i) - polovina).toFixed(1)}" y="${m.t}" width="${(polovina * 2).toFixed(1)}" height="${ph}"/>`,
      '</g>',
    );
    if (i % krokPopisku === 0) {
      casti.push(`<text class="g-popisek g-popisek--x" x="${x(i).toFixed(1)}" y="${m.t + ph + 24}">${rok}</text>`);
    }
  });

  return {
    sirka: W,
    svg: obalSvgGrafu(W, H, casti.join(''), `${titulek}: spojnicový graf, ${serie.length} řad, ${roky.length} let`),
    legenda:
      serie.length > 1
        ? serie.map((s) => ({ nazev: s.nazev, barva: s.barva, tvar: 'rect' as const }))
        : null,
    tabulka: {
      hlavicka: [{ nazev: 'Rok' }, ...serie.map((s) => ({ nazev: s.nazev, cislo: true }))],
      // Od nejnovějšího roku — čtenář hledá nejdřív poslední rok.
      radky: roky
        .map((rok, i) => [
          String(rok),
          ...serie.map((s) => (s.hodnoty[i] === null || s.hodnoty[i] === undefined ? 'údaj není' : kc(s.hodnoty[i] as number))),
        ])
        .reverse(),
    },
    poznamky: [],
  };
}

/* ─────────────────────  Saldo — sloupce kolem nuly  ─────────────────── */

export interface BodSalda {
  rok: number;
  /** `null` = údaj není (mezera), ne nula. */
  hodnota: number | null;
  /** Plánované (schválené) saldo — jde do tooltipu I do tabulky. */
  plan?: number | null;
  /** Doplňkové řádky jen do tooltipu. */
  doplnky?: TipRadek[];
}

/**
 * Sloupcový graf salda: přebytek roste od nuly nahoru, schodek klesá dolů.
 * Znaménko nese POZICE sloupce vůči nulové ose, ne barva — barva je u obou
 * stejná, aby nevznikl dojem dvou kategorií tam, kde je jedna veličina.
 */
export function grafSaldoPoLetech(
  body: BodSalda[],
  titulek: string,
  udobi: UdobiOsy[] = [],
): Graf {
  const W = 900;
  const H = 330;
  const m = { t: 24, r: 20, b: 46, l: 88 };
  const pw = W - m.l - m.r;
  const ph = H - m.t - m.b;

  const hodnoty = body.map((b) => b.hodnota).filter((v): v is number => v !== null);
  const { horni, dolni, tiky } = osaYPlusMinus(hodnoty);
  const y = (v: number) => m.t + ph - ((v - dolni) / (horni - dolni || 1)) * ph;
  const n = Math.max(1, body.length);
  const band = pw / n;
  const bw = Math.min(MAX_SLOUPEC, band * 0.6);
  const roky = body.map((b) => b.rok);
  const xStred = (i: number) => m.l + band * i + band / 2;

  const casti: string[] = [];
  casti.push(pasmaUdobi(udobi, roky, xStred, band / 2, m.t, ph));

  for (const t of tiky) {
    casti.push(
      `<line class="g-mrizka" x1="${m.l}" y1="${y(t).toFixed(1)}" x2="${m.l + pw}" y2="${y(t).toFixed(1)}"/>`,
      `<text class="g-popisek g-popisek--y" x="${m.l - 12}" y="${(y(t) + 4).toFixed(1)}">${esc(kcZkraceno(t))}</text>`,
    );
  }
  casti.push(`<line class="g-osa" x1="${m.l}" y1="${y(0).toFixed(1)}" x2="${m.l + pw}" y2="${y(0).toFixed(1)}"/>`);

  body.forEach((b, i) => {
    const xLevy = m.l + band * i + (band - bw) / 2;
    const radky: TipRadek[] = [
      { l: 'Saldo', v: b.hodnota === null ? 'údaj není' : kc(b.hodnota) },
      ...(b.hodnota !== null ? [{ l: 'Výsledek', v: b.hodnota >= 0 ? 'přebytek' : 'schodek' }] : []),
      ...(b.plan !== undefined ? [{ l: 'Plánované saldo', v: b.plan === null ? 'údaj není' : kc(b.plan) }] : []),
      ...(b.doplnky ?? []),
    ];
    casti.push(
      `<g class="g-sloupec" ${tipAtribut(String(b.rok), radky, 'var(--g1)')} role="img" aria-label="${esc(`${b.rok}: ${b.hodnota === null ? 'údaj není' : kc(b.hodnota)}`)}">`,
      `<rect class="g-terc" x="${(m.l + band * i).toFixed(1)}" y="${m.t}" width="${band.toFixed(1)}" height="${ph}"/>`,
    );
    if (b.hodnota === null) {
      // Chybějící údaj je tečka u osy, ne nulový sloupec.
      casti.push(`<circle class="g-chybi" cx="${xStred(i).toFixed(1)}" cy="${(y(0) - 5).toFixed(1)}" r="2.5"/>`);
    } else if (b.hodnota !== 0) {
      const vyska = Math.max(1.5, (Math.abs(b.hodnota) / (horni - dolni || 1)) * ph);
      if (b.hodnota > 0) {
        casti.push(`<path class="g-vypln" d="${sloupecPath(xLevy, y(0) - vyska, bw, vyska)}" fill="var(--g1)"/>`);
      } else {
        // Schodek visí pod nulou; zaoblení dolů udělá zrcadlený path.
        casti.push(
          `<rect class="g-vypln" x="${xLevy.toFixed(1)}" y="${y(0).toFixed(1)}" width="${bw}" height="${vyska.toFixed(1)}" rx="4" fill="var(--g1)"/>`,
        );
      }
    } else {
      // Vykázaná nula: 1px proužek na ose — nula a neznámo nesmí splynout.
      casti.push(`<rect class="g-vypln" x="${xLevy.toFixed(1)}" y="${(y(0) - 1).toFixed(1)}" width="${bw}" height="1" fill="var(--g1)"/>`);
    }
    casti.push('</g>');
    casti.push(`<text class="g-popisek g-popisek--x" x="${xStred(i).toFixed(1)}" y="${m.t + ph + 24}">${b.rok}</text>`);
  });

  const chybejicich = body.filter((b) => b.hodnota === null).length;
  // Plánované saldo patří i do tabulky, ne jen do tooltipu — kdo tabulku
  // otevře místo najíždění myší, musí mít stejné srovnání plánu a výsledku.
  const maPlan = body.some((b) => b.plan !== undefined);
  return {
    sirka: W,
    svg: obalSvgGrafu(W, H, casti.join(''), `${titulek}: sloupcový graf salda, ${body.length} let`),
    legenda: null,
    tabulka: {
      hlavicka: [
        { nazev: 'Rok' },
        { nazev: 'Saldo', cislo: true },
        { nazev: 'Výsledek' },
        ...(maPlan ? [{ nazev: 'Plánované saldo', cislo: true }] : []),
      ],
      radky: [...body]
        .reverse()
        .map((b) => [
          String(b.rok),
          b.hodnota === null ? 'údaj není' : kc(b.hodnota),
          b.hodnota === null ? '—' : b.hodnota >= 0 ? 'přebytek' : 'schodek',
          ...(maPlan ? [b.plan === null || b.plan === undefined ? 'údaj není' : kc(b.plan)] : []),
        ]),
    },
    poznamky: chybejicich
      ? [`Za ${cislo(chybejicich)} ${chybejicich === 1 ? 'rok' : chybejicich < 5 ? 'roky' : 'let'} údaj v datech není — v grafu je tečka u osy, ne nula.`]
      : [],
  };
}

/* ───────────────  Řady v procentech (plnění rozpočtu)  ──────────────── */

/** Formát procent do os a tooltipů: „105,9 %". */
export function procenta(v: number): string {
  return `${v.toFixed(1).replace('.', ',')} %`;
}

/**
 * Spojnice řad v procentech, s vodicí linkou na 100 %. Jednotka je u všech
 * řad stejná (%), takže smí do jednoho grafu.
 */
export function grafProcentaPoLetech(
  roky: number[],
  serie: SerieKc[],
  titulek: string,
  udobi: UdobiOsy[] = [],
): Graf {
  const W = 900;
  const H = 320;
  const m = { t: 24, r: 20, b: 46, l: 70 };
  const pw = W - m.l - m.r;
  const ph = H - m.t - m.b;

  const vse = serie.flatMap((s) => s.hodnoty).filter((v): v is number => v !== null);
  const { horni, dolni, tiky } = osaYPlusMinus(vse);
  const y = (v: number) => m.t + ph - ((v - dolni) / (horni - dolni || 1)) * ph;
  const x = (i: number) => m.l + (roky.length > 1 ? (i / (roky.length - 1)) * pw : pw / 2);
  const polovina = roky.length > 1 ? pw / (roky.length - 1) / 2 : pw / 2;

  const casti: string[] = [];
  casti.push(pasmaUdobi(udobi, roky, x, polovina, m.t, ph));

  for (const t of tiky) {
    casti.push(
      `<line class="g-mrizka" x1="${m.l}" y1="${y(t).toFixed(1)}" x2="${m.l + pw}" y2="${y(t).toFixed(1)}"/>`,
      `<text class="g-popisek g-popisek--y" x="${m.l - 12}" y="${(y(t) + 4).toFixed(1)}">${esc(`${cislo(t)} %`)}</text>`,
    );
  }
  // 100 % = plán splněný přesně; linka je orientační bod celého grafu.
  if (dolni <= 100 && horni >= 100) {
    casti.push(`<line class="g-osa" x1="${m.l}" y1="${y(100).toFixed(1)}" x2="${m.l + pw}" y2="${y(100).toFixed(1)}"/>`);
  }
  casti.push(`<line class="g-osa" x1="${m.l}" y1="${(m.t + ph).toFixed(1)}" x2="${m.l + pw}" y2="${(m.t + ph).toFixed(1)}"/>`);

  serie.forEach((s) => {
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
      casti.push(`<path class="g-spojnice" d="${useky.join('')}" stroke="${s.barva}" fill="none"/>`);
    }
    s.hodnoty.forEach((v, i) => {
      if (v === null) return;
      casti.push(`<circle class="g-bod" cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="3" fill="${s.barva}"/>`);
    });
  });

  const krokPopisku = roky.length > 16 ? Math.ceil(roky.length / 16) : 1;
  roky.forEach((rok, i) => {
    const radky: TipRadek[] = serie.map((s) => ({
      l: zkratNazev(s.nazev),
      v: s.hodnoty[i] === null || s.hodnoty[i] === undefined ? 'údaj není' : procenta(s.hodnoty[i] as number),
    }));
    casti.push(
      `<g class="g-sloupec" ${tipAtribut(String(rok), radky)} role="img" aria-label="${esc(String(rok))}">`,
      `<rect class="g-terc" x="${(x(i) - polovina).toFixed(1)}" y="${m.t}" width="${(polovina * 2).toFixed(1)}" height="${ph}"/>`,
      '</g>',
    );
    if (i % krokPopisku === 0) {
      casti.push(`<text class="g-popisek g-popisek--x" x="${x(i).toFixed(1)}" y="${m.t + ph + 24}">${rok}</text>`);
    }
  });

  return {
    sirka: W,
    svg: obalSvgGrafu(W, H, casti.join(''), `${titulek}: spojnicový graf v procentech, ${serie.length} řad`),
    legenda:
      serie.length > 1
        ? serie.map((s) => ({ nazev: s.nazev, barva: s.barva, tvar: 'rect' as const }))
        : null,
    tabulka: {
      hlavicka: [{ nazev: 'Rok' }, ...serie.map((s) => ({ nazev: `${s.nazev} (%)`, cislo: true }))],
      radky: roky
        .map((rok, i) => [
          String(rok),
          ...serie.map((s) => (s.hodnoty[i] === null || s.hodnoty[i] === undefined ? 'údaj není' : procenta(s.hodnoty[i] as number))),
        ])
        .reverse(),
    },
    poznamky: [],
  };
}
