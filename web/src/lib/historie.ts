/**
 * Dějiny města — `data/historie/prehled.json` a `udalosti.json`.
 *
 * U historie platí §3.7 dvojnásob: událost ze staré literatury a událost
 * z městské kroniky nejsou stejně jistá věc. Proto se `jistota` čte a
 * propisuje až do značky na ose i do tabulky — a když ji zdroj neuvádí,
 * napíše se „jistota v datech není", ne „doloženo".
 *
 * Přesnost data se nedoplňuje: „1865" zůstane rokem, nestane se z něj
 * 1. leden 1865.
 */
import { nactiJson, slug, type Nacteno } from './data';
import { isoDatum, jeObjekt, objekty, rokZ, rokZIso, texty, txt, type Zaznam } from './tolerantni';
import { normalizujDruh, udalost, type UdalostOsy } from './osa';

export interface Obdobi {
  id: string;
  nazev: string;
  od: number | null;
  do: number | null;
  popis: string | null;
  zdroje: string[];
}

export interface UdalostHistorie {
  id: string;
  datum: string;
  datum_do: string | null;
  rok: number | null;
  nazev: string;
  popis: string | null;
  obdobi: string | null;
  osoby: string[];
  zdroje: string[];
  odkaz: string | null;
  jistota: string | null;
  druh: string | null;
}

export interface Prehled {
  nazev: string | null;
  uvod: string | null;
  obdobi: Obdobi[];
  zdroje: string[];
}

/* ─────────────────────────  historie/prehled.json  ─────────────────── */

export function nactiPrehledHistorie(): Nacteno<Prehled> {
  const v = nactiJson<unknown>('historie/prehled.json', null);
  const koren = jeObjekt(v.data) ? v.data : {};
  const surova = Array.isArray(v.data)
    ? v.data.filter(jeObjekt)
    : objekty(koren, 'obdobi', 'období', 'etapy', 'kapitoly', 'periods', 'prehled');

  const videna = new Set<string>();
  const obdobi: Obdobi[] = surova
    .map((z, i) => {
      const nazev = txt(z, 'nazev', 'název', 'obdobi', 'období', 'titul', 'title');
      if (!nazev) return null;
      const zaklad = txt(z, 'id', 'klic') ?? slug(nazev) || `obdobi-${i + 1}`;
      let id = zaklad;
      for (let k = 2; videna.has(id); k++) id = `${zaklad}-${k}`;
      videna.add(id);
      return {
        id,
        nazev,
        od: rokZ(z, 'od', 'rok_od', 'zacatek', 'začátek', 'from'),
        do: rokZ(z, 'do', 'rok_do', 'konec', 'to'),
        popis: txt(z, 'popis', 'text', 'shrnuti', 'shrnutí', 'description', 'perex'),
        zdroje: texty(z, 'zdroje', 'zdroj', 'sources', 'literatura'),
      };
    })
    .filter((o): o is Obdobi => o !== null)
    .sort((a, b) => (a.od ?? Infinity) - (b.od ?? Infinity));

  return {
    stav: v.stav,
    zdroj: v.zdroj,
    poznamka: v.poznamka,
    data: {
      nazev: txt(koren, 'nazev', 'název', 'title'),
      uvod: txt(koren, 'uvod', 'úvod', 'perex', 'popis', 'intro'),
      obdobi,
      zdroje: texty(koren, 'zdroje', 'zdroj', 'sources', 'literatura'),
    },
  };
}

/* ────────────────────────  historie/udalosti.json  ─────────────────── */

export function nactiUdalostiHistorie(): Nacteno<UdalostHistorie[]> {
  const v = nactiJson<unknown>('historie/udalosti.json', null);
  const surove = Array.isArray(v.data)
    ? v.data.filter(jeObjekt)
    : jeObjekt(v.data)
      ? objekty(v.data, 'udalosti', 'události', 'events', 'zaznamy', 'polozky')
      : [];

  const videna = new Set<string>();
  const ven: UdalostHistorie[] = [];

  surove.forEach((z: Zaznam) => {
    const nazev = txt(z, 'nazev', 'název', 'nadpis', 'udalost', 'událost', 'titul', 'title');
    if (!nazev) return;
    const datum =
      isoDatum(z, 'datum', 'date', 'datum_od', 'od', 'kdy') ??
      (() => {
        const r = rokZ(z, 'rok', 'year', 'rok_od');
        return r === null ? null : String(r);
      })();
    if (!datum) return;

    const doIso =
      isoDatum(z, 'datum_do', 'do', 'konec') ??
      (() => {
        const r = rokZ(z, 'rok_do', 'do_roku');
        return r === null ? null : String(r);
      })();

    const zaklad = txt(z, 'id', 'ID') ?? `${slug(nazev) || 'udalost'}-${datum}`;
    let id = zaklad;
    for (let k = 2; videna.has(id); k++) id = `${zaklad}-${k}`;
    videna.add(id);

    ven.push({
      id,
      datum,
      datum_do: doIso && doIso >= datum ? doIso : null,
      rok: rokZIso(datum),
      nazev,
      popis: txt(z, 'popis', 'text', 'description', 'perex'),
      obdobi: txt(z, 'obdobi', 'období', 'etapa', 'kapitola', 'obdobi_id'),
      osoby: texty(z, 'osoby', 'lide', 'lidé', 'osoba_id', 'osobnosti'),
      zdroje: texty(z, 'zdroje', 'zdroj', 'sources', 'literatura'),
      odkaz: txt(z, 'odkaz', 'url', 'link'),
      jistota: txt(z, 'jistota', 'spolehlivost', 'certainty'),
      druh: txt(z, 'druh', 'typ', 'kategorie'),
    });
  });

  ven.sort((a, b) => a.datum.localeCompare(b.datum));
  return { stav: v.stav, zdroj: v.zdroj, poznamka: v.poznamka, data: ven };
}

/* ──────────────────  Převod na jednotnou časovou osu  ──────────────── */

export function historieNaOsu(udalosti: UdalostHistorie[], obdobi: Obdobi[]): UdalostOsy[] {
  const nazvyObdobi = new Map(obdobi.map((o) => [o.id, o.nazev]));

  const zObdobi: UdalostOsy[] = obdobi
    .filter((o) => o.od !== null)
    .map((o) =>
      udalost({
        id: `obdobi-${o.id}`,
        datum: String(o.od),
        datum_do: o.do === null ? null : String(o.do),
        druh: 'historie',
        nadpis: o.nazev,
        popis: o.popis,
        odkaz: `#obdobi-${o.id}`,
        zdroj: 'historie/prehled.json',
        detail: 'období dějin města',
      }),
    );

  const zUdalosti: UdalostOsy[] = udalosti.map((u) =>
    udalost({
      id: `historie-${u.id}`,
      datum: u.datum,
      datum_do: u.datum_do,
      druh: u.druh ? normalizujDruh(u.druh) : 'historie',
      nadpis: u.nazev,
      popis: u.popis,
      odkaz: u.odkaz,
      jistota: normalizujJistotuText(u.jistota),
      zdroj: u.zdroje.length > 0 ? u.zdroje.join(', ') : 'historie/udalosti.json',
      detail: u.obdobi ? (nazvyObdobi.get(u.obdobi) ?? u.obdobi) : null,
      osoby: u.osoby,
    }),
  );

  return [...zObdobi, ...zUdalosti];
}

function normalizujJistotuText(v: string | null): UdalostOsy['jistota'] {
  if (!v) return null;
  const s = v.trim().toLowerCase();
  if (s.startsWith('vysok') || s === 'high' || s.startsWith('dolož') || s.startsWith('dolozen')) return 'vysoka';
  if (s.startsWith('stredn') || s.startsWith('střed') || s === 'medium') return 'stredni';
  if (s.startsWith('nizk') || s.startsWith('nízk') || s === 'low' || s.startsWith('nejist') || s.startsWith('trad') || s.startsWith('legend')) {
    return 'nizka';
  }
  return null;
}
