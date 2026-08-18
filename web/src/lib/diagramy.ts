/**
 * Diagramy — schémata projektu a města jako SVG skládané při buildu.
 *
 * Data počítá `pipeline/diagramy.py` do `data/diagramy/*.json`; tenhle
 * soubor je jen kreslí. Rozdělení je stejné jako u znaků sekcí: Python umí
 * projít gigabajty dat, prohlížeč ani build by je procházet neměl.
 *
 * PROČ NE KRESLICÍ NÁSTROJ
 *   – schéma se přepočítá s daty; obrázek nakreslený jednou by za měsíc lhal
 *   – barvy jsou tokeny, takže totéž SVG obslouží světlý, tmavý i lázeňský motiv
 *   – nenačítá se nic z cizího serveru, což má web napsané v patičce
 *
 * ROZMĚRY: diagramy jsou širší než sloupec textu. Kreslí se na pevnou šířku
 * a kontejner je nechá vodorovně rolovat (`.diagram-plocha`), přesně jako
 * grafy — popisky se nesmí scvrknout pod čitelnost (DESIGN.md §2).
 *
 * ESCAPOVÁNÍ: názvy firem, osob a odborů jsou cizí data. Do SVG jdou
 * výhradně přes `esc()`.
 */
import { nactiJson, type Nacteno } from './data';
import { sklonuj } from './format';

/* ───────────────────────────────  Typy  ─────────────────────────────── */

export type TypDiagramu = 'strom' | 'tok' | 'sit' | 'mysl' | 'erd' | 'chybi';

export interface Uzel {
  id?: string | null;
  nazev?: string | null;
  popisek?: string | null;
  hodnota?: number | null;
  duraz?: string | null;
  vztah?: string | null;
  jistota?: string | null;
  pocet?: number | null;
  poznamka?: string | null;
}

export interface Skupina extends Uzel {
  popis?: string | null;
  deti: Uzel[];
}

export interface Vrstva {
  id: string;
  nazev: string;
  popis?: string;
  uzly: Uzel[];
}

export interface Hrana {
  od: string;
  do: string;
  popisek?: string | null;
  jistota?: string | null;
}

export interface Entita {
  id: string;
  nazev: string;
  soubor?: string;
  klic?: string;
  pole?: string[];
  souboru?: number | null;
}

export interface Vztah {
  od: string;
  do: string;
  popis: string;
  kardinalita?: string;
  jistota?: string;
  pres?: string;
}

export interface Diagram {
  id: string;
  nazev: string;
  typ: TypDiagramu;
  popis: string;
  stav: 'ok' | 'chybi';
  zdroj: string;
  metodika?: string[];
  /* strom */
  koren?: Uzel;
  skupiny?: Skupina[];
  stranou?: Uzel[];
  /* tok */
  vrstvy?: Vrstva[];
  /* síť */
  vlevo?: { nazev: string; uzly: Uzel[] };
  vpravo?: { nazev: string; uzly: Uzel[] };
  hrany?: Hrana[];
  legenda?: { klic: string; nazev: string }[];
  /* myšlenková mapa */
  vetve?: Skupina[];
  /* ERD */
  entity?: Entita[];
  vztahy?: Vztah[];
}

export interface RejstrikDiagramu {
  diagramy: { id: string; nazev: string; typ: string; popis: string; stav: string; zdroj: string }[];
  diagramu?: number;
  chybejicich?: number;
}

export function nactiRejstrikDiagramu(): Nacteno<RejstrikDiagramu> {
  return nactiJson<RejstrikDiagramu>('diagramy/index.json', { diagramy: [] });
}

export function nactiDiagram(id: string): Nacteno<Diagram | null> {
  return nactiJson<Diagram | null>(`diagramy/${id}.json`, null);
}

/* ─────────────────────────────  Pomůcky  ───────────────────────────── */

export function esc(s: unknown): string {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Rozdělí text na řádky tak, aby se vešel do dané šířky v znacích. */
function radky(text: string, naRadek: number, maxRadku = 3): string[] {
  const slova = String(text ?? '').split(/\s+/).filter(Boolean);
  const ven: string[] = [];
  let radek = '';
  for (const s of slova) {
    if (!radek) radek = s;
    else if (radek.length + 1 + s.length <= naRadek) radek += ' ' + s;
    else {
      ven.push(radek);
      radek = s;
      if (ven.length === maxRadku) break;
    }
  }
  if (radek && ven.length < maxRadku) ven.push(radek);
  /* Useknutý text musí být poznat. Tři tečky bez varování vypadají jako
     součást názvu. */
  if (ven.length === maxRadku && slova.join(' ').length > ven.join(' ').length) {
    ven[maxRadku - 1] = ven[maxRadku - 1].replace(/.{0,2}$/, '…');
  }
  return ven;
}

/** Barva uzlu podle důrazu nebo vztahu. Vždy token, nikdy hex. */
function barvaUzlu(u: Uzel): string {
  const k = u.duraz ?? u.vztah ?? null;
  if (k === 'povinny') return 'var(--accent)';
  if (k === 'varovani') return 'var(--g2)';
  if (k === 'zdroj') return 'var(--ink-faint)';
  if (k === 'mestsky-subjekt' || k === 'urad') return 'var(--accent)';
  if (k === 'obchoduje-s-mestem' || k === 'stat') return 'var(--g1)';
  if (k === 'media') return 'var(--g4)';
  if (k === 'sekce') return 'var(--g3)';
  return 'var(--ink-soft)';
}

interface Krabice {
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * Krabice s názvem a popiskem.
 *
 * `slaby` kreslí přerušovaný obrys — používá se tam, kde uzel do celku
 * nepatří (nemocnice mimo holding) nebo kde je údaj odhad. Je to totéž
 * pravidlo jako u značek na časové ose (DESIGN.md §3.7).
 */
function krabice(
  b: Krabice,
  nazev: string,
  popisek: string | null | undefined,
  opts: { barva?: string; slaby?: boolean; vypln?: boolean; naRadek?: number } = {},
): string {
  const { barva = 'var(--ink-soft)', slaby = false, vypln = false, naRadek = 24 } = opts;
  const rs = radky(nazev, naRadek, 2);
  const vysRadku = 13;
  const zacatek = b.y + b.h / 2 - ((rs.length - 1) * vysRadku) / 2 - (popisek ? 5 : 0);

  const texty = rs
    .map(
      (r, i) =>
        `<text x="${b.x + b.w / 2}" y="${zacatek + i * vysRadku}" text-anchor="middle" ` +
        `dominant-baseline="middle" class="diagram__nazev">${esc(r)}</text>`,
    )
    .join('');

  const pod = popisek
    ? `<text x="${b.x + b.w / 2}" y="${zacatek + rs.length * vysRadku + 1}" text-anchor="middle" ` +
      `dominant-baseline="middle" class="diagram__popisek">${esc(radky(popisek, naRadek + 6, 1)[0] ?? '')}</text>`
    : '';

  return (
    `<rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="6" ` +
    `fill="${vypln ? barva : 'var(--surface)'}" fill-opacity="${vypln ? 0.12 : 1}" ` +
    `stroke="${barva}" stroke-width="1.6"${slaby ? ' stroke-dasharray="5 4"' : ''}/>` +
    texty +
    pod
  );
}

function spojnice(x1: number, y1: number, x2: number, y2: number, slaby = false): string {
  /* Kolmé lomené spojnice: schéma se čte líp, když čáry nejdou šikmo přes
     ostatní krabice. Ohyb je v půli svislé vzdálenosti. */
  const stred = (y1 + y2) / 2;
  return (
    `<path d="M${x1} ${y1} L${x1} ${stred} L${x2} ${stred} L${x2} ${y2}" fill="none" ` +
    `stroke="var(--graf-osa)" stroke-width="1.4"${slaby ? ' stroke-dasharray="4 3"' : ''}/>`
  );
}

function svg(sirka: number, vyska: number, obsah: string, popis: string): string {
  return (
    `<svg class="diagram__kresba" viewBox="0 0 ${sirka} ${vyska}" width="${sirka}" height="${vyska}" ` +
    `role="img" aria-label="${esc(popis)}">${obsah}</svg>`
  );
}

/* ═══════════════════════════════  strom  ═══════════════════════════════
   Kořen nahoře, skupiny v řadě pod ním, potomci ve sloupci pod skupinou.
   Klasický organizační strom s vertikálním seznamem dětí — na 24 subjektů
   je to jediné rozvržení, které se ještě dá přečíst. */

const S_SIRKA = 190;
const S_MEZERA = 24;

export function kresliStrom(d: Diagram): { svg: string; sirka: number } {
  const skupiny = d.skupiny ?? [];
  const stranou = d.stranou ?? [];
  if (!skupiny.length) return { svg: '', sirka: 0 };

  const sloupcu = skupiny.length + (stranou.length ? 1 : 0);
  const sirka = sloupcu * S_SIRKA + (sloupcu + 1) * S_MEZERA;

  const yKoren = 20;
  const hKoren = 54;
  const ySkupina = yKoren + hKoren + 46;
  const hSkupina = 50;
  const yDeti = ySkupina + hSkupina + 30;
  const hDite = 44;
  const mezeraDeti = 10;

  const nejvicDeti = Math.max(
    ...skupiny.map((s) => s.deti.length),
    stranou.length,
  );
  const vyska = yDeti + nejvicDeti * (hDite + mezeraDeti) + 16;

  const kusy: string[] = [];

  /* kořen */
  const xKoren = sirka / 2 - S_SIRKA / 2;
  kusy.push(
    krabice(
      { x: xKoren, y: yKoren, w: S_SIRKA, h: hKoren },
      d.koren?.nazev ?? '',
      d.koren?.popisek,
      { barva: 'var(--accent)', vypln: true, naRadek: 26 },
    ),
  );

  const sloupce = [...skupiny.map((s) => ({ s, mimo: false })), ...(stranou.length ? [{ s: null, mimo: true }] : [])];

  sloupce.forEach((sl, i) => {
    const x = S_MEZERA + i * (S_SIRKA + S_MEZERA);
    const stredX = x + S_SIRKA / 2;

    if (sl.mimo) {
      /* Sloupec „mimo holding" nemá spojnici ke kořeni — právě to je na něm
         to podstatné. Přerušovaný obrys to říká podruhé. */
      kusy.push(
        krabice({ x, y: ySkupina, w: S_SIRKA, h: hSkupina }, 'Mimo město', 'vlastnicky už nepatří městu', {
          barva: 'var(--ink-faint)',
          slaby: true,
        }),
      );
      stranou.forEach((dite, j) => {
        const y = yDeti + j * (hDite + mezeraDeti);
        kusy.push(
          krabice({ x, y, w: S_SIRKA, h: hDite }, dite.nazev ?? '', dite.popisek, {
            barva: 'var(--ink-faint)',
            slaby: true,
            naRadek: 26,
          }),
        );
      });
      return;
    }

    const s = sl.s!;
    kusy.push(spojnice(sirka / 2, yKoren + hKoren, stredX, ySkupina));
    kusy.push(
      krabice({ x, y: ySkupina, w: S_SIRKA, h: hSkupina }, s.nazev ?? '', `${s.pocet ?? s.deti.length}×`, {
        barva: 'var(--accent)',
      }),
    );

    s.deti.forEach((dite, j) => {
      const y = yDeti + j * (hDite + mezeraDeti);
      if (j === 0) kusy.push(spojnice(stredX, ySkupina + hSkupina, stredX, y));
      else {
        kusy.push(
          `<path d="M${stredX} ${y - mezeraDeti} L${stredX} ${y}" fill="none" ` +
            `stroke="var(--graf-osa)" stroke-width="1.4"/>`,
        );
      }
      kusy.push(
        krabice({ x, y, w: S_SIRKA, h: hDite }, dite.nazev ?? '', dite.popisek, { naRadek: 26 }),
      );
    });
  });

  return { svg: svg(sirka, vyska, kusy.join(''), `${d.nazev}: ${d.popis}`), sirka };
}

/* ════════════════════════════════  tok  ════════════════════════════════
   Vrstvy zleva doprava. Uvnitř vrstvy jdou uzly pod sebou, mezi vrstvami
   vede jedna šipka — jednotlivé hrany by při sedmnácti sběračích udělaly
   z diagramu klubko. */

const T_SIRKA = 210;
const T_MEZERA = 54;

export function kresliTok(d: Diagram): { svg: string; sirka: number } {
  const vrstvy = d.vrstvy ?? [];
  if (!vrstvy.length) return { svg: '', sirka: 0 };

  const sirka = vrstvy.length * T_SIRKA + (vrstvy.length + 1) * T_MEZERA;
  const yHlava = 22;
  const yPopis = 40;
  const yUzly = 66;
  const hUzel = 40;
  const mezera = 9;
  const nejvic = Math.max(...vrstvy.map((v) => v.uzly.length));
  const vyska = yUzly + nejvic * (hUzel + mezera) + 14;

  const kusy: string[] = [];

  vrstvy.forEach((v, i) => {
    const x = T_MEZERA + i * (T_SIRKA + T_MEZERA);

    kusy.push(
      `<text x="${x}" y="${yHlava}" class="diagram__vrstva">${esc(v.nazev)}</text>`,
      `<text x="${x}" y="${yPopis}" class="diagram__popisek">${esc(radky(v.popis ?? '', 34, 1)[0] ?? '')}</text>`,
    );

    /* Šipka mezi vrstvami. Jedna, ne padesát — vrstva jako celek předává
       výsledek další vrstvě. */
    if (i < vrstvy.length - 1) {
      const x1 = x + T_SIRKA + 8;
      const x2 = x + T_SIRKA + T_MEZERA - 8;
      const y = yUzly + 22;
      kusy.push(
        `<path d="M${x1} ${y} L${x2} ${y}" stroke="var(--graf-osa)" stroke-width="2" ` +
          `marker-end="url(#sipka)"/>`,
      );
    }

    v.uzly.forEach((u, j) => {
      const y = yUzly + j * (hUzel + mezera);
      const barva = barvaUzlu(u);
      const popisek =
        typeof u.hodnota === 'number'
          ? u.hodnota.toLocaleString('cs-CZ')
          : (u.popisek ?? null);
      kusy.push(
        krabice({ x, y, w: T_SIRKA, h: hUzel }, u.nazev ?? '', popisek, {
          barva,
          vypln: u.duraz === 'povinny' || u.duraz === 'varovani',
          slaby: u.duraz === 'slaby' || u.duraz === 'zdroj',
          naRadek: 30,
        }),
      );
    });
  });

  const definice =
    `<defs><marker id="sipka" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" ` +
    `markerHeight="6" orient="auto-start-reverse">` +
    `<path d="M0 0 L10 5 L0 10 z" fill="var(--graf-osa)"/></marker></defs>`;

  return { svg: svg(sirka, vyska, definice + kusy.join(''), `${d.nazev}: ${d.popis}`), sirka };
}

/* ════════════════════════════════  síť  ════════════════════════════════
   Dva sloupce uzlů a hrany mezi nimi. Hrany se kreslí jako křivky, aby
   se daly rozeznat i tam, kde vede z jednoho uzlu deset čar. */

/**
 * Seřadí sloupce tak, aby se čáry co nejmíň křížily.
 *
 * Abecední pořadí vpravo vyrábělo klubko: 25 osob a 54 firem daly 72 čar,
 * které se protínaly uprostřed a nedalo se sledovat, co kam vede. Uzel se
 * proto přesune k průměru pozic svých protějšků (barycentrické řazení,
 * dvě kola tam a zpět). Čáry pak vedou skoro rovnoběžně.
 *
 * Pořadí je pouze vizuální. Nic neskrývá a nic nemění — kdo s kým, je
 * v tabulce pod diagramem.
 */
function seradSit(
  vlevo: Uzel[],
  vpravo: Uzel[],
  hrany: Hrana[],
): { vlevo: Uzel[]; vpravo: Uzel[] } {
  const sousedeL = new Map<string, string[]>();
  const sousedeP = new Map<string, string[]>();
  for (const h of hrany) {
    const a = String(h.od);
    const b = String(h.do);
    (sousedeL.get(a) ?? sousedeL.set(a, []).get(a)!).push(b);
    (sousedeP.get(b) ?? sousedeP.set(b, []).get(b)!).push(a);
  }

  let L = [...vlevo];
  let P = [...vpravo];

  function preskladej(uzly: Uzel[], sousede: Map<string, string[]>, poziceProtejsku: Map<string, number>): Uzel[] {
    const teziste = new Map<string, number>();
    uzly.forEach((u, i) => {
      const s = sousede.get(String(u.id)) ?? [];
      const pozice = s.map((x) => poziceProtejsku.get(x)).filter((x): x is number => x !== undefined);
      /* Uzel bez hrany si drží své místo — jinak by se všechny takové
         slily na začátek a vypadalo by to jako skupina, kterou netvoří. */
      teziste.set(String(u.id), pozice.length ? pozice.reduce((a, b) => a + b, 0) / pozice.length : i);
    });
    return [...uzly].sort((a, b) => (teziste.get(String(a.id)) ?? 0) - (teziste.get(String(b.id)) ?? 0));
  }

  for (let kolo = 0; kolo < 2; kolo++) {
    const poziceL = new Map(L.map((u, i) => [String(u.id), i]));
    P = preskladej(P, sousedeP, poziceL);
    const poziceP = new Map(P.map((u, i) => [String(u.id), i]));
    L = preskladej(L, sousedeL, poziceP);
  }

  return { vlevo: L, vpravo: P };
}

export function kresliSit(d: Diagram): { svg: string; sirka: number } {
  const hrany = d.hrany ?? [];
  const serazeno = seradSit(d.vlevo?.uzly ?? [], d.vpravo?.uzly ?? [], hrany);
  const vlevo = serazeno.vlevo;
  const vpravo = serazeno.vpravo;
  if (!vlevo.length || !vpravo.length) return { svg: '', sirka: 0 };

  const wUzel = 250;
  const hUzel = 38;
  const mezera = 7;
  const mezisloupci = 190;
  const sirka = wUzel * 2 + mezisloupci + 60;
  const yHlava = 24;
  const yUzly = 46;
  const vyska = yUzly + Math.max(vlevo.length, vpravo.length) * (hUzel + mezera) + 16;

  const xL = 30;
  const xP = 30 + wUzel + mezisloupci;
  const poziceL = new Map<string, number>();
  const poziceP = new Map<string, number>();
  vlevo.forEach((u, i) => poziceL.set(String(u.id), yUzly + i * (hUzel + mezera) + hUzel / 2));
  vpravo.forEach((u, i) => poziceP.set(String(u.id), yUzly + i * (hUzel + mezera) + hUzel / 2));

  const kusy: string[] = [];

  /* Hrany první, aby vedly pod krabicemi a nepřekrývaly text. */
  for (const h of hrany) {
    const y1 = poziceL.get(String(h.od));
    const y2 = poziceP.get(String(h.do));
    if (y1 === undefined || y2 === undefined) continue;
    const x1 = xL + wUzel;
    const x2 = xP;
    const stred = (x1 + x2) / 2;
    /* Nejednoznačná identita = přerušovaná čára. Vazba se ukazuje, ale
       nesmí se tvářit jako potvrzená. */
    const nejisty = h.jistota === 'nejednoznacne' || h.jistota === 'nenalezeno';
    kusy.push(
      `<path d="M${x1} ${y1} C${stred} ${y1} ${stred} ${y2} ${x2} ${y2}" fill="none" ` +
        `stroke="var(--graf-osa)" stroke-width="1.1" opacity=".75"` +
        (nejisty ? ' stroke-dasharray="4 3"' : '') +
        `/>`,
    );
  }

  kusy.push(
    `<text x="${xL}" y="${yHlava}" class="diagram__vrstva">${esc(d.vlevo?.nazev ?? '')}</text>`,
    `<text x="${xP}" y="${yHlava}" class="diagram__vrstva">${esc(d.vpravo?.nazev ?? '')}</text>`,
  );

  vlevo.forEach((u, i) => {
    const y = yUzly + i * (hUzel + mezera);
    kusy.push(
      krabice({ x: xL, y, w: wUzel, h: hUzel }, u.nazev ?? '', u.popisek, {
        barva: barvaUzlu(u),
        slaby: u.jistota === 'nejednoznacne' || u.jistota === 'nenalezeno',
        naRadek: 34,
      }),
    );
  });
  vpravo.forEach((u, i) => {
    const y = yUzly + i * (hUzel + mezera);
    kusy.push(
      krabice({ x: xP, y, w: wUzel, h: hUzel }, u.nazev ?? '', u.popisek, {
        barva: barvaUzlu(u),
        naRadek: 34,
      }),
    );
  });

  return { svg: svg(sirka, vyska, kusy.join(''), `${d.nazev}: ${d.popis}`), sirka };
}

/* ═══════════════════════  myšlenková mapa  ══════════════════════════════
   Kořen vlevo, větve ve sloupci, listy vpravo od své větve. Ne paprsky —
   u 33 listů by se popisky překrývaly. */

export function kresliMysl(d: Diagram): { svg: string; sirka: number } {
  const vetve = d.vetve ?? [];
  if (!vetve.length) return { svg: '', sirka: 0 };

  const wKoren = 150;
  const wVetev = 190;
  const wList = 230;
  const hList = 30;
  const mezeraListu = 6;
  const mezeraVetvi = 22;
  const sirka = 24 + wKoren + 50 + wVetev + 40 + wList + 24;

  /* Svislé místo každé větve = kolik má listů. */
  const vysky = vetve.map((v) => Math.max(1, v.deti.length) * (hList + mezeraListu) - mezeraListu);
  const vyska = 30 + vysky.reduce((a, b) => a + b + mezeraVetvi, 0) + 10;

  const kusy: string[] = [];
  const xKoren = 24;
  const xVetev = xKoren + wKoren + 50;
  const xList = xVetev + wVetev + 40;

  kusy.push(
    krabice({ x: xKoren, y: vyska / 2 - 30, w: wKoren, h: 60 }, d.koren?.nazev ?? '', d.koren?.popisek, {
      barva: 'var(--accent)',
      vypln: true,
      naRadek: 20,
    }),
  );

  let y = 30;
  vetve.forEach((v, i) => {
    const vyskaVetve = vysky[i];
    const stredVetve = y + vyskaVetve / 2;

    kusy.push(
      `<path d="M${xKoren + wKoren} ${vyska / 2} C${xKoren + wKoren + 30} ${vyska / 2} ` +
        `${xVetev - 30} ${stredVetve} ${xVetev} ${stredVetve}" fill="none" ` +
        `stroke="var(--graf-osa)" stroke-width="1.6"/>`,
    );
    kusy.push(
      krabice(
        { x: xVetev, y: stredVetve - 24, w: wVetev, h: 48 },
        v.nazev ?? '',
        typeof v.hodnota === 'number' ? `${v.hodnota.toLocaleString('cs-CZ')} bodů usnesení` : `${v.deti.length} témat`,
        { barva: 'var(--accent)', naRadek: 24 },
      ),
    );

    v.deti.forEach((list, j) => {
      const yList = y + j * (hList + mezeraListu);
      kusy.push(
        `<path d="M${xVetev + wVetev} ${stredVetve} C${xVetev + wVetev + 20} ${stredVetve} ` +
          `${xList - 20} ${yList + hList / 2} ${xList} ${yList + hList / 2}" fill="none" ` +
          `stroke="var(--graf-osa)" stroke-width="1" opacity=".7"/>`,
      );
      /* Téma, které zatím nikdo nepoužil, je slabé. Nula je zjištěná nula,
         ne neznámo — číselník ho má, jen se nehodilo. */
      const nepouzite = list.hodnota === 0;
      kusy.push(
        krabice(
          { x: xList, y: yList, w: wList, h: hList },
          list.nazev ?? '',
          typeof list.hodnota === 'number' ? `${list.hodnota.toLocaleString('cs-CZ')}×` : null,
          { naRadek: 32, slaby: nepouzite, barva: nepouzite ? 'var(--ink-faint)' : 'var(--ink-soft)' },
        ),
      );
    });

    y += vyskaVetve + mezeraVetvi;
  });

  return { svg: svg(sirka, vyska, kusy.join(''), `${d.nazev}: ${d.popis}`), sirka };
}

/* ════════════════════════════════  ERD  ════════════════════════════════
   Entity v mřížce, pod názvem výpis polí, mezi nimi vztahy. Vztah označený
   jako odhad má přerušovanou čáru — v datech nemá oporu a spočítal ho
   tenhle projekt. */

export function kresliErd(d: Diagram): { svg: string; sirka: number } {
  const entity = d.entity ?? [];
  const vztahy = d.vztahy ?? [];
  if (!entity.length) return { svg: '', sirka: 0 };

  const sloupcu = 4;
  const wE = 230;
  const mezeraX = 46;
  const mezeraY = 56;
  const hlava = 42;
  const radekPole = 15;
  const sirka = sloupcu * wE + (sloupcu + 1) * mezeraX;

  const vysky = entity.map((e) => hlava + (e.pole?.length ?? 0) * radekPole + 10);
  const radku = Math.ceil(entity.length / sloupcu);
  const vyskaRadku: number[] = [];
  for (let r = 0; r < radku; r++) {
    vyskaRadku.push(Math.max(...vysky.slice(r * sloupcu, (r + 1) * sloupcu)));
  }
  const vyska = 20 + vyskaRadku.reduce((a, b) => a + b + mezeraY, 0);

  const pozice = new Map<string, { x: number; y: number; w: number; h: number }>();
  entity.forEach((e, i) => {
    const r = Math.floor(i / sloupcu);
    const c = i % sloupcu;
    const x = mezeraX + c * (wE + mezeraX);
    const y = 20 + vyskaRadku.slice(0, r).reduce((a, b) => a + b + mezeraY, 0);
    pozice.set(e.id, { x, y, w: wE, h: vysky[i] });
  });

  const kusy: string[] = [];

  /* Vztahy nejdřív — vedou pod krabicemi. */
  for (const v of vztahy) {
    const a = pozice.get(v.od);
    const b = pozice.get(v.do);
    if (!a || !b) continue;
    const odhad = v.jistota === 'odhad';
    const overovany = v.jistota === 'overovana';
    const x1 = a.x + a.w / 2;
    const y1 = a.y + a.h;
    const x2 = b.x + b.w / 2;
    const y2 = b.y;
    kusy.push(
      `<path d="M${x1} ${y1} C${x1} ${y1 + 26} ${x2} ${y2 - 26} ${x2} ${y2}" fill="none" ` +
        `stroke="${odhad ? 'var(--g2)' : overovany ? 'var(--g4)' : 'var(--graf-osa)'}" ` +
        `stroke-width="1.6"${odhad || overovany ? ' stroke-dasharray="5 4"' : ''} ` +
        `marker-end="url(#sipka-erd)"/>`,
    );
    const sx = (x1 + x2) / 2;
    const sy = (y1 + y2) / 2;
    kusy.push(
      `<text x="${sx}" y="${sy}" text-anchor="middle" class="diagram__popisek">` +
        `${esc(v.kardinalita ?? '')}</text>`,
    );
  }

  entity.forEach((e) => {
    const p = pozice.get(e.id)!;
    kusy.push(
      `<rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="6" fill="var(--surface)" ` +
        `stroke="var(--accent)" stroke-width="1.6"/>`,
      `<rect x="${p.x}" y="${p.y}" width="${p.w}" height="${hlava - 12}" rx="6" ` +
        `fill="var(--accent)" fill-opacity=".12"/>`,
      `<text x="${p.x + 12}" y="${p.y + 18}" class="diagram__nazev diagram__nazev--vlevo">${esc(e.nazev)}</text>`,
      `<text x="${p.x + 12}" y="${p.y + 33}" class="diagram__popisek diagram__popisek--vlevo">` +
        `${esc(
          typeof e.souboru === 'number'
            ? `${e.souboru.toLocaleString('cs-CZ')} ${sklonuj(e.souboru, 'soubor', 'soubory', 'souborů')}`
            : 'soubory nenalezeny',
        )}</text>`,
    );
    (e.pole ?? []).forEach((pole, j) => {
      kusy.push(
        `<text x="${p.x + 12}" y="${p.y + hlava + 8 + j * radekPole}" ` +
          `class="diagram__pole">${esc(pole)}</text>`,
      );
    });
  });

  const definice =
    `<defs><marker id="sipka-erd" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" ` +
    `markerHeight="5" orient="auto-start-reverse">` +
    `<path d="M0 0 L10 5 L0 10 z" fill="var(--graf-osa)"/></marker></defs>`;

  return { svg: svg(sirka, vyska, definice + kusy.join(''), `${d.nazev}: ${d.popis}`), sirka };
}

/* ═══════════════════════════════  rozcestí  ════════════════════════════ */

export function kresliDiagram(d: Diagram | null | undefined): { svg: string; sirka: number } {
  if (!d || d.stav !== 'ok') return { svg: '', sirka: 0 };
  switch (d.typ) {
    case 'strom':
      return kresliStrom(d);
    case 'tok':
      return kresliTok(d);
    case 'sit':
      return kresliSit(d);
    case 'mysl':
      return kresliMysl(d);
    case 'erd':
      return kresliErd(d);
    default:
      return { svg: '', sirka: 0 };
  }
}

/* ══════════════════════════  tabulkový pohled  ═════════════════════════
   Ke každému grafu s barevnými sériemi patří tabulkový pohled (DESIGN.md §2).
   U diagramů má navíc druhý smysl: schéma se nedá přečíst čtečkou ani
   vytisknout na úzký papír, tabulka ano. */

export interface TabulkaDiagramu {
  hlavicka: string[];
  radky: string[][];
}

export function tabulkaDiagramu(d: Diagram): TabulkaDiagramu | null {
  const cislo = (n: number | null | undefined): string =>
    typeof n === 'number' ? n.toLocaleString('cs-CZ') : '—';

  if (d.typ === 'strom') {
    const radky: string[][] = [];
    for (const s of d.skupiny ?? []) {
      for (const dite of s.deti) {
        radky.push([s.nazev ?? '', dite.nazev ?? '', dite.popisek ?? '—']);
      }
    }
    for (const dite of d.stranou ?? []) {
      radky.push(['Mimo město', dite.nazev ?? '', dite.poznamka ?? dite.popisek ?? '—']);
    }
    return { hlavicka: ['Skupina', 'Subjekt', 'Poznámka'], radky };
  }

  if (d.typ === 'tok') {
    const radky = (d.vrstvy ?? []).flatMap((v) =>
      v.uzly.map((u) => [v.nazev, u.nazev ?? '', typeof u.hodnota === 'number' ? cislo(u.hodnota) : (u.popisek ?? '—')]),
    );
    return { hlavicka: ['Vrstva', 'Krok', 'Počet nebo modul'], radky };
  }

  if (d.typ === 'sit') {
    const jmena = new Map<string, string>();
    for (const u of [...(d.vlevo?.uzly ?? []), ...(d.vpravo?.uzly ?? [])]) {
      jmena.set(String(u.id), u.nazev ?? String(u.id));
    }
    const radky = (d.hrany ?? []).map((h) => [
      jmena.get(String(h.od)) ?? String(h.od),
      jmena.get(String(h.do)) ?? String(h.do),
      h.popisek ?? '—',
      h.jistota ?? '—',
    ]);
    return { hlavicka: [d.vlevo?.nazev ?? 'Vlevo', d.vpravo?.nazev ?? 'Vpravo', 'Role', 'Jistota'], radky };
  }

  if (d.typ === 'mysl') {
    const radky = (d.vetve ?? []).flatMap((v) =>
      v.deti.map((l) => [v.nazev ?? '', l.nazev ?? '', cislo(l.hodnota), l.popisek ?? '—']),
    );
    return { hlavicka: ['Skupina', 'Téma', 'Použití', 'Popis'], radky };
  }

  if (d.typ === 'erd') {
    const jmena = new Map((d.entity ?? []).map((e) => [e.id, e.nazev]));
    const radky = (d.vztahy ?? []).map((v) => [
      jmena.get(v.od) ?? v.od,
      jmena.get(v.do) ?? v.do,
      v.popis,
      v.kardinalita ?? '—',
      v.jistota ?? '—',
      v.pres ?? '—',
    ]);
    return { hlavicka: ['Od', 'K', 'Vztah', 'Kardinalita', 'Jistota', 'Spojeno přes'], radky };
  }

  return null;
}
