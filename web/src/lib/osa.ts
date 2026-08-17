/**
 * Časové osy (web/DESIGN.md §3.7).
 *
 * Jedna komponenta pro celý web: profil osoby, detail protistrany, téma, firma,
 * dějiny města i volby. Události ze všech zdrojů se převedou na jeden tvar
 * `UdalostOsy` a osa je pak kreslí stejně.
 *
 * Tři pravidla, která tenhle soubor drží tvrdě:
 *
 *   1. **Osa nepřeskakuje prázdné roky.** Čas je spojitá lineární škála, ne
 *      seznam let, ve kterých se něco stalo. Mezera je informace stejně jako
 *      značka — deset let ticha musí být vidět jako deset let ticha.
 *   2. **Nízká jistota se nesmí tvářit jako fakt.** Nejistá značka je dutá,
 *      s přerušovaným obrysem, má vlastní položku v legendě a v tabulce je
 *      jistota vypsaná slovy. Rozdíl nikdy nestojí jen na barvě.
 *   3. **U osy jedné entity se uvádí, z jakých zdrojů se skládá.** Jinak
 *      vypadá jako úplný obraz, ačkoliv obsahuje jen to, co je v našich datech.
 */
import { nactiAdresarSoubory, type Nacteno } from './data';
import { escSvg, tipAtribut, type LegendaPolozka, type Tabulka, type TipRadek } from './grafy';
import { cssBarvaSlotu, MAX_KATEGORII } from './barvy';
import { datumKratke, orez } from './format';
import { isoDatum, jeObjekt, pozicevRoce, rokZ, rokZIso, texty, txt, type Zaznam } from './tolerantni';
import type { Jistota } from './vazby';

/* ─────────────────────────────  Událost  ───────────────────────────── */

export interface UdalostOsy {
  id: string;
  /** ISO v přesnosti, kterou zdroj skutečně uvádí: `YYYY`, `YYYY-MM` i `YYYY-MM-DD`. */
  datum: string;
  /** Konec období. `null` u bodové události. */
  datum_do: string | null;
  /** Klíč pruhu — určuje barvu i řádek osy. */
  druh: string;
  nadpis: string;
  popis: string | null;
  odkaz: string | null;
  /** `null` = zdroj o jistotě nic neříká. Není to totéž jako „jisté". */
  jistota: Jistota;
  /** Odkud údaj pochází — vypisuje se pod osou. */
  zdroj: string | null;
  /** Doplňkové řádky do tooltipu a poslední sloupec tabulky. */
  detail: string | null;
  osoby: string[];
  ica: string[];
  temata: string[];
}

/**
 * Kanonické pruhy. Pořadí je zároveň pořadím řádků na ose a pořadím, ve kterém
 * se rozdávají barvy — nejvýše šesti pruhům, zbytek spadne do „Ostatní"
 * (web/DESIGN.md §2, bod 3). Barvu určuje identita pruhu, ne pořadí událostí
 * v datech, takže se dvě osy nad stejnými daty nikdy neobarví jinak.
 */
export const PRUHY: { klic: string; nazev: string }[] = [
  { klic: 'funkce', nazev: 'Funkce a mandáty' },
  { klic: 'usneseni', nazev: 'Usnesení' },
  { klic: 'hlasovani', nazev: 'Hlasování' },
  { klic: 'smlouva', nazev: 'Smlouvy a platby' },
  { klic: 'zpravodaj', nazev: 'Zpravodaj a média' },
  { klic: 'firma', nazev: 'Firma' },
  { klic: 'volby', nazev: 'Volby' },
  { klic: 'historie', nazev: 'Dějiny města' },
  { klic: 'ostatni', nazev: 'Ostatní' },
];

const NAZVY_PRUHU = new Map(PRUHY.map((p) => [p.klic, p.nazev]));

/** Sjednotí, jak jednotlivé moduly píšou druh události. */
export function normalizujDruh(v: string | null | undefined): string {
  const s = (v ?? '').trim().toLowerCase();
  if (!s) return 'ostatni';
  if (s.startsWith('usnes')) return 'usneseni';
  if (s.startsWith('hlas')) return 'hlasovani';
  if (s.startsWith('smlouv') || s.startsWith('penize') || s.startsWith('peníze') || s.startsWith('platb') || s.startsWith('zakazk')) return 'smlouva';
  if (s.startsWith('zpravodaj') || s.startsWith('clanek') || s.startsWith('článek') || s.startsWith('media') || s.startsWith('médi') || s.startsWith('tisk')) return 'zpravodaj';
  if (s.startsWith('funkc') || s.startsWith('mandat') || s.startsWith('mandát') || s.startsWith('role')) return 'funkce';
  if (s.startsWith('firm') || s.startsWith('subjekt') || s.startsWith('vznik') || s.startsWith('zanik') || s.startsWith('zánik')) return 'firma';
  if (s.startsWith('volb') || s.startsWith('vysledk') || s.startsWith('výsledk')) return 'volby';
  if (s.startsWith('histor') || s.startsWith('dejin') || s.startsWith('dějin') || s.startsWith('udalost') || s.startsWith('událost')) return 'historie';
  return 'ostatni';
}

export function nazevDruhu(klic: string): string {
  return NAZVY_PRUHU.get(klic) ?? 'Ostatní';
}

function normalizujJistotu(v: string | null): Jistota {
  if (!v) return null;
  const s = v.trim().toLowerCase();
  if (s.startsWith('vysok') || s.startsWith('vysoč') || s === 'high' || s === 'jista' || s === 'jistá') return 'vysoka';
  if (s.startsWith('stredn') || s.startsWith('střed') || s === 'medium') return 'stredni';
  if (s.startsWith('nizk') || s.startsWith('nízk') || s === 'low' || s.startsWith('domnenk') || s.startsWith('domněnk')) return 'nizka';
  if (s.startsWith('varov')) return 'varovani';
  return null;
}

/** Nejistá událost = ta, která se nesmí tvářit jako doložený fakt. */
export function jeNejista(j: Jistota): boolean {
  return j === 'nizka' || j === 'varovani';
}

export function popisekJistoty(j: Jistota): string {
  if (j === 'vysoka') return 'vysoká jistota';
  if (j === 'stredni') return 'střední jistota';
  if (j === 'nizka') return 'nízká jistota — nepotvrzená domněnka';
  if (j === 'varovani') return 'upozornění — sled událostí nesedí';
  return 'jistota v datech není';
}

/* ──────────────────────  Čtení data/casova_osa/  ───────────────────── */

function udalostZeZaznamu(z: Zaznam, poradi: number, puvod: string): UdalostOsy | null {
  const datum =
    isoDatum(z, 'datum', 'date', 'datum_od', 'od', 'zacatek', 'začátek', 'start', 'kdy') ??
    (() => {
      const r = rokZ(z, 'rok', 'year', 'rok_od');
      return r === null ? null : String(r);
    })();
  if (!datum) return null;

  const doIso =
    isoDatum(z, 'datum_do', 'do', 'konec', 'end') ??
    (() => {
      const r = rokZ(z, 'rok_do', 'do_roku');
      return r === null ? null : String(r);
    })();

  const nadpis = txt(z, 'nadpis', 'nazev', 'název', 'titul', 'title', 'udalost', 'událost', 'text', 'popis');
  if (!nadpis) return null;

  const druh = normalizujDruh(txt(z, 'druh', 'typ', 'kategorie', 'type', 'zdroj_druh', 'oblast'));

  return {
    id: txt(z, 'id', 'ID') ?? `${puvod}-${poradi + 1}`,
    datum,
    datum_do: doIso && doIso >= datum ? doIso : null,
    druh,
    nadpis,
    popis: txt(z, 'popis', 'perex', 'description', 'text', 'shrnuti'),
    odkaz: txt(z, 'odkaz', 'url', 'link', 'cesta', 'href'),
    jistota: normalizujJistotu(txt(z, 'jistota', 'certainty', 'spolehlivost', 'duvera', 'důvěra')),
    zdroj: txt(z, 'zdroj', 'source', 'puvod', 'původ', 'modul'),
    detail: txt(z, 'detail', 'poznamka', 'note', 'meta'),
    osoby: texty(z, 'osoby', 'lide', 'lidé', 'osoba_id', 'osoba'),
    ica: texty(z, 'ica', 'ico', 'firmy', 'protistrany', 'subjekty'),
    temata: texty(z, 'temata', 'témata', 'tagy', 'tags', 'tema', 'téma'),
  };
}

/**
 * Jednotné události ze všech zdrojů projektu. Soubor může být pole i objekt
 * s obalovým klíčem; oboje se přečte. Záznam bez data nebo bez nadpisu se
 * vynechá — na ose by neměl kam sednout.
 */
export function nactiCasovouOsu(): Nacteno<UdalostOsy[]> {
  const v = nactiAdresarSoubory<unknown>('casova_osa', ['.json']);
  const ven: UdalostOsy[] = [];
  const videna = new Set<string>();

  for (const s of v.data) {
    const obsah = s.data;
    const zaznamy: Zaznam[] = Array.isArray(obsah)
      ? obsah.filter(jeObjekt)
      : jeObjekt(obsah)
        ? (['udalosti', 'události', 'casova_osa', 'osa', 'events', 'zaznamy', 'polozky'] as const)
            .map((k) => obsah[k])
            .filter(Array.isArray)
            .flat()
            .filter(jeObjekt)
        : [];

    zaznamy.forEach((z, i) => {
      const u = udalostZeZaznamu(z, i, s.jmeno);
      if (!u) return;
      let id = u.id;
      for (let k = 2; videna.has(id); k++) id = `${u.id}-${k}`;
      videna.add(id);
      ven.push({ ...u, id, zdroj: u.zdroj ?? `casova_osa/${s.jmeno}` });
    });
  }

  ven.sort((a, b) => a.datum.localeCompare(b.datum));
  return { stav: v.stav, zdroj: v.zdroj, poznamka: v.poznamka, data: ven };
}

/* ───────────────────────────────  Výběry  ──────────────────────────── */

export function proOsobu(u: UdalostOsy[], id: string): UdalostOsy[] {
  return u.filter((x) => x.osoby.includes(id));
}
export function proIco(u: UdalostOsy[], ico: string): UdalostOsy[] {
  return u.filter((x) => x.ica.includes(ico));
}
export function proTema(u: UdalostOsy[], tag: string): UdalostOsy[] {
  return u.filter((x) => x.temata.includes(tag));
}

/* ──────────────────────────  Kreslení osy  ─────────────────────────── */

export interface Osa {
  svg: string;
  sirka: number;
  legenda: LegendaPolozka[];
  /** Legenda jistoty — tvar značky, ne barva. */
  legendaJistoty: { nazev: string; nejista: boolean }[];
  tabulka: Tabulka;
  poznamky: string[];
  rokOd: number;
  rokDo: number;
  pocet: number;
  /** Kolik událostí se do tabulky nevešlo. */
  vynechanoVTabulce: number;
}

const VYSKA_PRUHU = 38;
const SIRKA_POPISKU = 168;
const HLAVICKA = 30;
const SPODEK = 34;
const MAX_RADKU_TABULKY = 400;
const UROVNE_POSUNU = [0, -10, 10];

function krokLet(rozsah: number): number {
  for (const k of [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500]) {
    if (rozsah / k <= 12) return k;
  }
  return 1000;
}

/**
 * Osa událostí. `sirka` je vnitřní šířka SVG; kontejner `.graf-plocha` podle ní
 * pozná, kdy scrollovat.
 */
export function grafCasovaOsa(udalosti: UdalostOsy[], nazev: string, sirka = 900): Osa {
  const platne = udalosti.filter((u) => rokZIso(u.datum) !== null);
  const roky = platne.map((u) => rokZIso(u.datum) as number);
  const rokyDo = platne.map((u) => rokZIso(u.datum_do) ?? (rokZIso(u.datum) as number));
  const rokOd = roky.length ? Math.min(...roky) : new Date().getFullYear();
  const rokDo = rokyDo.length ? Math.max(...rokyDo) : rokOd;

  // Pruhy v kanonickém pořadí, ale jen ty, které v datech opravdu jsou.
  const pritomne = PRUHY.map((p) => p.klic).filter((k) => platne.some((u) => u.druh === k));
  const barvaPruhu = new Map<string, string>();
  pritomne.forEach((k, i) => {
    // Sedmý a další pruh se neobarvuje novou barvou — spadne do „Ostatní".
    barvaPruhu.set(k, k === 'ostatni' ? cssBarvaSlotu(null) : cssBarvaSlotu(i < MAX_KATEGORII ? i : null));
  });

  const W = sirka;
  const pw = W - SIRKA_POPISKU - 16;
  const H = HLAVICKA + Math.max(1, pritomne.length) * VYSKA_PRUHU + SPODEK;

  const rozsah = rokDo + 1 - rokOd;
  const x = (rok: number, frakce: number) => SIRKA_POPISKU + ((rok + frakce - rokOd) / rozsah) * pw;

  const casti: string[] = [];

  /* Mřížka let. Krok se volí tak, aby popisky nesplývaly — ale osa zůstává
     spojitá, takže prázdné roky se NEPŘESKAKUJÍ, jen nemají vlastní popisek. */
  const krok = krokLet(rozsah);
  const prvni = Math.ceil(rokOd / krok) * krok;
  const spodekMrizky = HLAVICKA + Math.max(1, pritomne.length) * VYSKA_PRUHU;
  for (let r = prvni; r <= rokDo + 1; r += krok) {
    const px = x(r, 0);
    if (px > W) break;
    casti.push(
      `<line class="g-mrizka" x1="${px.toFixed(1)}" y1="${HLAVICKA - 8}" x2="${px.toFixed(1)}" y2="${spodekMrizky}"/>`,
      `<text class="g-popisek g-popisek--x" x="${px.toFixed(1)}" y="${HLAVICKA - 14}">${r}</text>`,
    );
  }
  casti.push(
    `<line class="g-osa" x1="${SIRKA_POPISKU}" y1="${spodekMrizky}" x2="${(SIRKA_POPISKU + pw).toFixed(1)}" y2="${spodekMrizky}"/>`,
  );

  /* Pruhy a značky. */
  let prekryvu = 0;
  pritomne.forEach((klic, ri) => {
    const y = HLAVICKA + ri * VYSKA_PRUHU;
    const stred = y + VYSKA_PRUHU / 2;
    const barva = barvaPruhu.get(klic) ?? cssBarvaSlotu(null);

    casti.push(
      `<text class="g-radek-nazev" x="0" y="${(stred + 4).toFixed(1)}">${escSvg(nazevDruhu(klic))}</text>`,
      `<line class="osa-linka" x1="${SIRKA_POPISKU}" y1="${stred.toFixed(1)}" x2="${(SIRKA_POPISKU + pw).toFixed(1)}" y2="${stred.toFixed(1)}"/>`,
    );

    const vPruhu = platne
      .filter((u) => u.druh === klic)
      .sort((a, b) => a.datum.localeCompare(b.datum));

    const obsazeno: number[] = UROVNE_POSUNU.map(() => -Infinity);

    for (const u of vPruhu) {
      const r = rokZIso(u.datum) as number;
      const px = x(r, pozicevRoce(u.datum));
      const rDo = rokZIso(u.datum_do);
      const pxDo = rDo === null ? null : x(rDo, pozicevRoce(u.datum_do));

      // Značky ve stejném místě se posunou svisle, aby se nepřekryly úplně.
      let uroven = obsazeno.findIndex((konec) => px - konec > 13);
      if (uroven === -1) {
        uroven = 0;
        prekryvu++;
      }
      obsazeno[uroven] = pxDo !== null ? Math.max(px, pxDo) : px;
      const cy = stred + UROVNE_POSUNU[uroven];

      const nejista = jeNejista(u.jistota);
      const tridy = ['osa-znacka'];
      if (nejista) tridy.push('osa-znacka--nejista');
      else if (u.jistota === 'stredni') tridy.push('osa-znacka--stredni');

      const radky: TipRadek[] = [
        { l: 'Kdy', v: popisDatumu(u) },
        { l: 'Druh', v: nazevDruhu(u.druh) },
      ];
      if (u.detail) radky.push({ l: 'Detail', v: u.detail });
      if (u.popis) radky.push({ l: 'Popis', v: orez(u.popis, 140) });
      radky.push({ l: 'Jistota', v: popisekJistoty(u.jistota) });
      if (u.zdroj) radky.push({ l: 'Zdroj', v: u.zdroj });

      const vypln = nejista ? 'var(--surface)' : barva;
      const obrys = nejista ? ` stroke="${barva}"` : '';
      const telo =
        pxDo !== null && pxDo - px > 3
          ? `<rect x="${px.toFixed(1)}" y="${(cy - 5.5).toFixed(1)}" width="${(pxDo - px).toFixed(1)}" height="11" rx="5.5" fill="${vypln}"${obrys}/>`
          : `<circle cx="${px.toFixed(1)}" cy="${cy.toFixed(1)}" r="5.5" fill="${vypln}"${obrys}/>`;

      const popis = `${popisDatumu(u)} — ${u.nadpis}${nejista ? ` (${popisekJistoty(u.jistota)})` : ''}`;
      // Značky jsou mimo pořadí tabulátoru; kompletní seznam i s odkazy nese
      // povinná tabulka pod osou (web/DESIGN.md §2, bod 5).
      const atributy = `${tipAtribut(u.nadpis, radky, nejista ? undefined : barva, false)} tabindex="-1" aria-hidden="true" class="${tridy.join(' ')}"`;
      const vnitrek = `<title>${escSvg(popis)}</title>${telo}`;
      casti.push(
        u.odkaz && !u.odkaz.startsWith('http')
          ? `<a href="${escSvg(u.odkaz)}" ${atributy}>${vnitrek}</a>`
          : `<g ${atributy}>${vnitrek}</g>`,
      );
    }
  });

  const poznamky: string[] = [];
  if (prekryvu > 0) {
    poznamky.push(
      `Značky se v ${prekryvu === 1 ? 'jednom místě' : `${prekryvu} místech`} překrývají — víc událostí padne na stejný bod osy. Úplný výčet je v tabulce pod osou.`,
    );
  }

  const seradene = [...platne].sort((a, b) => b.datum.localeCompare(a.datum));
  const doTabulky = seradene.slice(0, MAX_RADKU_TABULKY);

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
        popisekJistoty(u.jistota),
        u.zdroj ?? 'neuveden',
      ]),
    },
    poznamky,
    rokOd,
    rokDo,
    pocet: platne.length,
    vynechanoVTabulce: Math.max(0, seradene.length - doTabulky.length),
  };
}

function legendaJistot(u: UdalostOsy[]): { nazev: string; nejista: boolean }[] {
  const ven: { nazev: string; nejista: boolean }[] = [];
  if (u.some((x) => !jeNejista(x.jistota) && x.jistota !== 'stredni')) {
    ven.push({ nazev: 'doložená událost — plná značka', nejista: false });
  }
  if (u.some((x) => x.jistota === 'stredni')) {
    ven.push({ nazev: 'střední jistota — plná značka s přerušovaným obrysem', nejista: false });
  }
  if (u.some((x) => jeNejista(x.jistota))) {
    ven.push({ nazev: 'nízká jistota — dutá značka s přerušovaným obrysem, není to doložený fakt', nejista: true });
  }
  return ven;
}

/** Datum tak přesně, jak ho zdroj uvádí. Rok se nedoplňuje na 1. leden. */
export function popisDatumu(u: UdalostOsy): string {
  const jeden = (iso: string): string => {
    if (/^\d{4}-\d{2}-\d{2}/.test(iso)) return datumKratke(iso);
    const m = /^(\d{4})-(\d{2})$/.exec(iso);
    if (m) return `${Number(m[2])}/${m[1]}`;
    return iso;
  };
  return u.datum_do && u.datum_do !== u.datum ? `${jeden(u.datum)} – ${jeden(u.datum_do)}` : jeden(u.datum);
}

/* ──────────────────────────  Stavba událostí  ──────────────────────── */

/** Zkratka pro sestavení události z vlastních dat stránky. */
export function udalost(
  cast: Partial<UdalostOsy> & { id: string; datum: string; druh: string; nadpis: string },
): UdalostOsy {
  return {
    datum_do: null,
    popis: null,
    odkaz: null,
    jistota: null,
    zdroj: null,
    detail: null,
    osoby: [],
    ica: [],
    temata: [],
    ...cast,
  };
}

/** Sloučí události z víc zdrojů, zahodí duplicitní `id` a seřadí podle času. */
export function slucUdalosti(...skupiny: UdalostOsy[][]): UdalostOsy[] {
  const podleId = new Map<string, UdalostOsy>();
  for (const s of skupiny) {
    for (const u of s) {
      if (!podleId.has(u.id)) podleId.set(u.id, u);
    }
  }
  return [...podleId.values()].sort((a, b) => a.datum.localeCompare(b.datum));
}
