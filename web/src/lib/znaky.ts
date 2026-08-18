/**
 * Znaky sekcí — miniaturní datová grafika do rozcestníku.
 *
 * Projekt nemá ikonovou sadu a nemá ji mít: obrazová složka je výhradně
 * datová (web/DESIGN.md, „Pozadí a obrazy"). Znak sekce proto není piktogram,
 * ale malý graf ze skutečných dat té sekce — sloupce ročních výdajů u peněz,
 * skutečná hranice katastru u mapy, 21 teček u zastupitelstva.
 *
 * Data počítá `pipeline/znaky_sekci.py` do `data/znaky/sekce.json`; tenhle
 * soubor je jen vykresluje. Rozdělení je záměrné — kdyby si web počítal sám,
 * musel by při každém buildu projít 27 MB hlasování.
 *
 * PRAVIDLA, KTERÁ TENHLE SOUBOR DRŽÍ
 *   – `null` je NEZNÁMO a kreslí se jako mezera, nikdy jako nulový sloupec
 *   – barvy jsou CSS tokeny (`var(--accent)`, `var(--r5)`), ne hexy, takže
 *     jeden vygenerovaný SVG obslouží světlý i tmavý motiv
 *   – znak je dekorativní vůči čtečce (`aria-hidden`), protože totéž, co
 *     ukazuje, je vedle napsané slovy — jinak by screen reader četl dvakrát
 *   – žádný runtime JavaScript; SVG vzniká při buildu
 */
import { KROKU_RAMPY, cssKrokRampy } from './barvy';
import { nactiJson, type Nacteno } from './data';

/* ───────────────────────────────  Typy  ─────────────────────────────── */

export type TvarZnaku =
  | 'sloupce'
  | 'pruh'
  | 'mrizka'
  | 'body'
  | 'retez'
  | 'sit'
  | 'obrys'
  | 'useky'
  | 'chybi';

export interface Znak {
  tvar: TvarZnaku;
  /** Číselný počet záznamů sekce. `null`, když ho zdroj nedal. */
  pocet?: number | null;
  /** Naformátované hlavní číslo („12 890", „3,83 mld."). */
  hodnota: string;
  jednotka: string;
  /** Jedna věta, co znak ukazuje. Píše se pod znak na velkých obrazovkách. */
  veta: string;
  stav: 'ok' | 'chybi';
  zdroj: string;

  /* podle tvaru */
  osa?: string[];
  hodnoty?: (number | null)[];
  /** Část z `hodnoty`, kreslí se na vrcholu sloupce druhou barvou. */
  hodnoty2?: (number | null)[];
  policka?: { v: number | null; p: string }[];
  bunky?: { v: number | null; p: string }[];
  /** Kolik sloupců má mřížka nebo pruh. */
  sloupcu?: number;
  skupiny?: { nazev: string; pocet: number }[];
  kroky?: { nazev: string; pocet: number | null }[];
  vlevo?: number;
  vpravo?: number;
  hran?: number;
  path?: string;
  useky?: { od: number; do: number; nazev: string }[];
}

export interface SouborZnaku {
  znaky: Record<string, Znak>;
  znaku?: number;
  chybejicich?: number;
}

export function nactiZnaky(): Nacteno<SouborZnaku> {
  return nactiJson<SouborZnaku>('znaky/sekce.json', { znaky: {} });
}

/* ────────────────────────────  Kreslení  ────────────────────────────── */

/** Plátno znaku. Čtvercové, aby se dlaždice v mřížce nerozjížděly. */
const W = 100;
const H = 100;

function zaokrouhli(n: number): number {
  return Math.round(n * 100) / 100;
}

/**
 * Krok sekvenční rampy pro hodnotu.
 *
 * Zařazení je logaritmické (web/DESIGN.md §2) — rozdíl mezi 1 a 10 je pro
 * čtenáře stejně velký jako mezi 100 a 1000, a lineární škála by na jednom
 * odlehlém roce spálila celou rampu.
 */
function krokProHodnotu(v: number, max: number): number {
  if (max <= 0) return 0;
  const podil = Math.log1p(Math.max(0, v)) / Math.log1p(max);
  return Math.min(KROKU_RAMPY - 1, Math.max(0, Math.round(podil * (KROKU_RAMPY - 1))));
}

function svg(obsah: string, popis: string): string {
  return (
    `<svg class="znak__kresba" viewBox="0 0 ${W} ${H}" role="img" aria-label="${escXml(popis)}" ` +
    `preserveAspectRatio="xMidYMid meet" focusable="false">${obsah}</svg>`
  );
}

function escXml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* ── sloupce ─────────────────────────────────────────────────────────────
   Klasické sloupce. `null` je mezera, ne nulový sloupec: nulový sloupec by
   tvrdil „v tom roce nebylo nic", což je jiné tvrzení než „nevíme".
   Chybějící hodnota se navíc označí tečkovanou patkou u osy, aby mezera
   nešla přečíst jako konec dat. */
function kresliSloupce(z: Znak): string {
  const hodnoty = z.hodnoty ?? [];
  if (!hodnoty.length) return '';

  const znameHodnoty = hodnoty.filter((h): h is number => h !== null);
  const max = znameHodnoty.length ? Math.max(...znameHodnoty) : 0;
  const dno = H - 8;
  const mezera = hodnoty.length > 24 ? 1 : 2;
  const sirka = (W - mezera * (hodnoty.length - 1)) / hodnoty.length;

  const kusy: string[] = [];
  hodnoty.forEach((h, i) => {
    const x = zaokrouhli(i * (sirka + mezera));
    if (h === null) {
      kusy.push(
        `<rect x="${x}" y="${dno + 2}" width="${zaokrouhli(sirka)}" height="2" ` +
          `fill="var(--ink-faint)" opacity=".45"/>`,
      );
      return;
    }
    // I nulová hodnota dostane 1px proužek — jinak by se „nula" a „mezera"
    // vykreslily stejně, tedy nijak.
    const vyska = max > 0 ? Math.max(1, (h / max) * (dno - 4)) : 1;
    kusy.push(
      `<rect x="${x}" y="${zaokrouhli(dno - vyska)}" width="${zaokrouhli(sirka)}" ` +
        `height="${zaokrouhli(vyska)}" fill="var(--accent)" rx=".6"/>`,
    );

    /* Druhá série je ČÁST té první (nejednomyslná hlasování z celkových),
       proto se kreslí na vrcholu sloupce, ne vedle něj. Vedle by to byly
       dvě veličiny a součet by přestal platit. */
    const cast = z.hodnoty2?.[i];
    if (typeof cast === 'number' && cast > 0 && max > 0) {
      const vyskaCasti = Math.min(vyska, Math.max(1, (cast / max) * (dno - 4)));
      kusy.push(
        `<rect x="${x}" y="${zaokrouhli(dno - vyska)}" width="${zaokrouhli(sirka)}" ` +
          `height="${zaokrouhli(vyskaCasti)}" fill="var(--g2)" rx=".6"/>`,
      );
    }
  });
  kusy.push(`<line x1="0" y1="${dno + 1}" x2="${W}" y2="${dno + 1}" stroke="var(--graf-osa)" stroke-width="1"/>`);
  return kusy.join('');
}

/* ── pruh ────────────────────────────────────────────────────────────────
   Řada políček v sekvenční rampě: hustota v čase. Používá se tam, kde jde
   o rytmus vydávání (týdenní přehled, ročníky zpravodaje), ne o objem. */
function kresliPruh(z: Znak): string {
  const policka = z.policka ?? [];
  if (!policka.length) return '';

  const zname = policka.map((p) => p.v).filter((v): v is number => v !== null);
  const max = zname.length ? Math.max(...zname) : 0;
  /* Bez zadaného počtu sloupců se mřížka rozloží do čtverce. Původně se
     bralo `min(n, 12)`, takže třináct políček vyšlo jako dva tenké řádky
     nahoře a zbytek dlaždice byl prázdný — z odstupu to vypadalo jako
     tečkovaná čára, ne jako graf. */
  const sloupcu = z.sloupcu ?? Math.max(1, Math.ceil(Math.sqrt(policka.length)));
  const radku = Math.ceil(policka.length / sloupcu);
  const mezera = 2.5;
  const w = (W - mezera * (sloupcu - 1)) / sloupcu;
  const h = Math.min(w, (H - mezera * (radku - 1)) / radku);
  const posunX = (W - (w * sloupcu + mezera * (sloupcu - 1))) / 2;
  const posunY = (H - (h * radku + mezera * (radku - 1))) / 2;

  return policka
    .map((p, i) => {
      const x = zaokrouhli(posunX + (i % sloupcu) * (w + mezera));
      const y = zaokrouhli(posunY + Math.floor(i / sloupcu) * (h + mezera));
      if (p.v === null) {
        return (
          `<rect x="${x}" y="${y}" width="${zaokrouhli(w)}" height="${zaokrouhli(h)}" rx="1.5" ` +
          `fill="none" stroke="var(--graf-osa)" stroke-width=".8" stroke-dasharray="1.6 1.6"/>`
        );
      }
      const barva = p.v === 0 ? 'var(--surface-2)' : cssKrokRampy(krokProHodnotu(p.v, max));
      return (
        `<rect x="${x}" y="${y}" width="${zaokrouhli(w)}" height="${zaokrouhli(h)}" rx="1.5" ` +
        `fill="${barva}"${p.v === 0 ? ' stroke="var(--rule)" stroke-width=".6"' : ''}/>`
      );
    })
    .join('');
}

/* ── mřížka ──────────────────────────────────────────────────────────────
   Buňky s hodnotou 0..1 — poměr, ne objem. Prázdná buňka je přerušovaný
   obrys, plná je krok rampy. */
function kresliMrizku(z: Znak): string {
  const bunky = z.bunky ?? [];
  if (!bunky.length) return '';

  const sloupcu = z.sloupcu ?? 8;
  const radku = Math.ceil(bunky.length / sloupcu);
  const mezera = 2.5;
  const w = (W - mezera * (sloupcu - 1)) / sloupcu;
  const h = Math.min(w, (H - mezera * (radku - 1)) / radku);
  const posunY = (H - (h * radku + mezera * (radku - 1))) / 2;

  return bunky
    .map((b, i) => {
      const x = zaokrouhli((i % sloupcu) * (w + mezera));
      const y = zaokrouhli(posunY + Math.floor(i / sloupcu) * (h + mezera));
      if (b.v === null) {
        return (
          `<rect x="${x}" y="${y}" width="${zaokrouhli(w)}" height="${zaokrouhli(h)}" rx="1.5" ` +
          `fill="none" stroke="var(--graf-osa)" stroke-width=".8" stroke-dasharray="1.6 1.6"/>`
        );
      }
      const krok = Math.min(KROKU_RAMPY - 1, Math.max(0, Math.round(b.v * (KROKU_RAMPY - 1))));
      return (
        `<rect x="${x}" y="${y}" width="${zaokrouhli(w)}" height="${zaokrouhli(h)}" rx="1.5" ` +
        `fill="${cssKrokRampy(krok)}"/>`
      );
    })
    .join('');
}

/* ── body ────────────────────────────────────────────────────────────────
   Jedna tečka = jeden člověk. Skupiny dostávají barvy kategorií v pořadí
   podle velikosti; sedmá a další skupina spadne do „Ostatní" (--g-ost),
   stejně jako v grafech. */
function kresliBody(z: Znak): string {
  const skupiny = z.skupiny ?? [];
  const tecky: string[] = [];
  skupiny.forEach((s, gi) => {
    const barva = gi < 6 ? `var(--g${gi + 1})` : 'var(--g-ost)';
    for (let i = 0; i < s.pocet; i++) tecky.push(barva);
  });
  if (!tecky.length) return '';

  const sloupcu = Math.ceil(Math.sqrt(tecky.length * 1.2));
  const radku = Math.ceil(tecky.length / sloupcu);
  const rozestup = Math.min(W / sloupcu, H / radku);
  const r = rozestup * 0.32;
  const posunX = (W - rozestup * (sloupcu - 1)) / 2;
  const posunY = (H - rozestup * (radku - 1)) / 2;

  return tecky
    .map((barva, i) => {
      const cx = zaokrouhli(posunX + (i % sloupcu) * rozestup);
      const cy = zaokrouhli(posunY + Math.floor(i / sloupcu) * rozestup);
      return `<circle cx="${cx}" cy="${cy}" r="${zaokrouhli(r)}" fill="${barva}"/>`;
    })
    .join('');
}

/* ── řetěz ───────────────────────────────────────────────────────────────
   Tři uzly za sebou: usnesení → smlouva → doložená jistota. Poslední uzel
   je dutý, protože vazba mezi usnesením a smlouvou je odhad, ne fakt —
   totéž pravidlo jako u značek na časové ose (DESIGN.md §3.7). */
function kresliRetez(z: Znak): string {
  const kroky = (z.kroky ?? []).slice(0, 3);
  if (!kroky.length) return '';

  const y = H / 2;
  const r = 13;
  const rozestup = (W - r * 2) / Math.max(1, kroky.length - 1);
  const kusy: string[] = [];

  for (let i = 0; i < kroky.length - 1; i++) {
    const x1 = zaokrouhli(r + i * rozestup + r);
    const x2 = zaokrouhli(r + (i + 1) * rozestup - r);
    kusy.push(
      `<line x1="${x1}" y1="${y}" x2="${x2}" y2="${y}" stroke="var(--graf-osa)" ` +
        `stroke-width="2" stroke-dasharray="3 2.5"/>`,
    );
  }
  kroky.forEach((_, i) => {
    const cx = zaokrouhli(r + i * rozestup);
    const posledni = i === kroky.length - 1;
    kusy.push(
      posledni
        ? `<circle cx="${cx}" cy="${y}" r="${r}" fill="var(--surface)" stroke="var(--accent)" ` +
            `stroke-width="2.5" stroke-dasharray="3.5 2.5"/>`
        : `<circle cx="${cx}" cy="${y}" r="${r}" fill="var(--accent)"/>`,
    );
  });
  return kusy.join('');
}

/* ── síť ─────────────────────────────────────────────────────────────────
   Vlevo osoby, vpravo firmy, čára je doložené angažmá. Počty uzlů se kvůli
   čitelnosti zastropují; že je jich ve skutečnosti víc, říká číslo vedle. */
function kresliSit(z: Znak): string {
  const vlevo = Math.min(z.vlevo ?? 0, 7);
  const vpravo = Math.min(z.vpravo ?? 0, 9);
  if (!vlevo || !vpravo) return '';

  const xa = 16;
  const xb = W - 16;
  const ya = (i: number) => zaokrouhli(((i + 1) * H) / (vlevo + 1));
  const yb = (i: number) => zaokrouhli(((i + 1) * H) / (vpravo + 1));

  const hrany: string[] = [];
  // Deterministické „rozdání" hran: i-tá osoba se váže na firmy s odstupem,
  // aby obrázek nevypadal jako mřížka a přitom byl při každém buildu stejný.
  for (let i = 0; i < vlevo; i++) {
    for (let k = 0; k < 2; k++) {
      const j = (i * 2 + k * 3) % vpravo;
      hrany.push(
        `<line x1="${xa}" y1="${ya(i)}" x2="${xb}" y2="${yb(j)}" stroke="var(--graf-osa)" stroke-width=".9"/>`,
      );
    }
  }
  const uzly = [
    ...Array.from({ length: vlevo }, (_, i) => `<circle cx="${xa}" cy="${ya(i)}" r="4.6" fill="var(--accent)"/>`),
    ...Array.from({ length: vpravo }, (_, i) => `<circle cx="${xb}" cy="${yb(i)}" r="3.4" fill="var(--g2)"/>`),
  ];
  return hrany.join('') + uzly.join('');
}

/* ── obrys ───────────────────────────────────────────────────────────────
   Skutečná hranice katastru z RÚIAN, ne stylizovaný tvar. Path počítá
   pipeline; tady se jen obarví. */
function kresliObrys(z: Znak): string {
  if (!z.path) return '';
  return (
    `<path d="${z.path}" fill="var(--accent)" fill-opacity=".14" stroke="var(--accent)" ` +
    `stroke-width="1.6" stroke-linejoin="round" fill-rule="evenodd"/>`
  );
}

/* ── úseky ───────────────────────────────────────────────────────────────
   Období dějin na společné ose. Úseky se skládají do řádků pod sebe, aby
   bylo vidět, že navazují a jak jsou dlouhé. */
function kresliUseky(z: Znak): string {
  const useky = z.useky ?? [];
  if (!useky.length) return '';

  const od = Math.min(...useky.map((u) => u.od));
  const doo = Math.max(...useky.map((u) => u.do));
  const rozsah = doo - od || 1;
  /* Úseky vyplní plochu shora dolů. Dřív měly strop 9 px a u deseti období
     zabraly půlku dlaždice; zbytek byl prázdný. */
  const rozestup = H / useky.length;
  const vyska = rozestup * 0.72;

  return useky
    .map((u, i) => {
      const x1 = zaokrouhli(((u.od - od) / rozsah) * W);
      const x2 = zaokrouhli(((u.do - od) / rozsah) * W);
      const y = zaokrouhli(i * rozestup);
      return (
        `<rect x="${x1}" y="${y}" width="${zaokrouhli(Math.max(2, x2 - x1))}" ` +
        `height="${zaokrouhli(vyska)}" rx="1.2" fill="var(--accent)" ` +
        `opacity="${zaokrouhli(0.45 + (0.5 * i) / Math.max(1, useky.length - 1))}"/>`
      );
    })
    .join('');
}

/* ── chybí ───────────────────────────────────────────────────────────────
   Sekce, jejíž data se nepodařilo načíst. Kreslí se prázdný rám, ne prázdná
   plocha: prázdná plocha by tvrdila, že v sekci nic není. */
function kresliChybi(): string {
  return (
    `<rect x="6" y="6" width="${W - 12}" height="${H - 12}" rx="4" fill="none" ` +
    `stroke="var(--graf-osa)" stroke-width="1.4" stroke-dasharray="4 3.5"/>` +
    `<line x1="34" y1="${H / 2}" x2="${W - 34}" y2="${H / 2}" stroke="var(--ink-faint)" stroke-width="2"/>`
  );
}

/** Vykreslí znak do hotového `<svg>`. Vrací prázdný řetězec, když není co kreslit. */
export function kresliZnak(z: Znak | undefined, popis: string): string {
  if (!z) return '';
  let obsah = '';
  switch (z.tvar) {
    case 'sloupce':
      obsah = kresliSloupce(z);
      break;
    case 'pruh':
      obsah = kresliPruh(z);
      break;
    case 'mrizka':
      obsah = kresliMrizku(z);
      break;
    case 'body':
      obsah = kresliBody(z);
      break;
    case 'retez':
      obsah = kresliRetez(z);
      break;
    case 'sit':
      obsah = kresliSit(z);
      break;
    case 'obrys':
      obsah = kresliObrys(z);
      break;
    case 'useky':
      obsah = kresliUseky(z);
      break;
    case 'chybi':
      obsah = kresliChybi();
      break;
  }
  // Tvar, který se nepodařilo naplnit daty, spadne na „chybí" — prázdné
  // <svg> by v mřížce vyrobilo díru bez vysvětlení.
  return svg(obsah || kresliChybi(), popis);
}
