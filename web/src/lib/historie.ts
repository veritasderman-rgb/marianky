/**
 * Dějiny města — `data/historie/prehled.json` a `udalosti.json`.
 *
 * Zdroj sám formuluje pravidlo, které tenhle soubor jen přenáší:
 *
 *   > Pole `jistota` nabývá hodnot `dolozeno` (údaj se v použitých pramenech
 *   > shoduje) a `nejiste` (prameny se rozcházejí). U nejistých záznamů je
 *   > rozpor popsán v poli `poznamka`. **Web nesmí nejistý údaj zobrazit jako
 *   > doložený.**
 *
 * A druhé: `presnost` říká, jak přesně je událost datovaná (den / mesic / rok /
 * obdobi). Přesnost se NEDOPLŇUJE — „1193" zůstane rokem.
 *
 * Zdroje se u období i událostí odkazují přes `zdroje_ids` do rejstříku
 * `zdroje_rejstrik`; web z nich sestaví odkazy a nic si nedomýšlí.
 */
import { nactiJson, type Nacteno } from './data';
import { cis, jeObjekt, objekty, texty, txt, type Zaznam } from './tolerantni';
import {
  normalizujDruh,
  normalizujJistotu,
  rokZIso,
  udalost,
  type JistotaOsy,
  type Presnost,
  type UdalostOsy,
} from './osa';

export interface Zdroj {
  id: string;
  nazev: string;
  url: string | null;
  typ: string | null;
}

export interface Obdobi {
  id: string;
  poradi: number | null;
  nazev: string;
  od: number | null;
  do: number | null;
  /** `priblizna` u období, jehož hranice zdroj sám označuje za přibližné. */
  presnostRozsahu: string | null;
  text: string | null;
  osobnosti: string[];
  zdrojeIds: string[];
}

export interface UdalostHistorie {
  id: string;
  datum: string;
  datum_do: string | null;
  presnost: Presnost;
  rok: number | null;
  obdobi: string | null;
  kategorie: string | null;
  nazev: string;
  popis: string | null;
  osoby: string[];
  tagy: string[];
  jistota: JistotaOsy;
  /** Čím se prameny rozcházejí. Povinné u nejistého záznamu. */
  poznamka: string | null;
  odkaz: string | null;
  zdrojeIds: string[];
}

export interface Prehled {
  nazev: string | null;
  uvod: string | null;
  obdobi: Obdobi[];
  zdroje: Map<string, Zdroj>;
  metodika: { klic: string; text: string }[];
  statistika: { obdobi: number | null; udalosti: number | null; rozsah: [number, number] | null };
}

function presnostZ(v: string | null): Presnost {
  const s = (v ?? '').trim().toLowerCase();
  return s === 'den' || s === 'mesic' || s === 'rok' || s === 'obdobi' ? s : null;
}

function rejstrikZdroju(k: Zaznam): Map<string, Zdroj> {
  const ven = new Map<string, Zdroj>();
  const r = jeObjekt(k.zdroje_rejstrik) ? k.zdroje_rejstrik : null;
  if (!r) return ven;
  for (const [id, z] of Object.entries(r)) {
    if (!jeObjekt(z)) continue;
    ven.set(id, {
      id,
      nazev: txt(z, 'nazev') ?? id,
      url: txt(z, 'url'),
      typ: txt(z, 'typ'),
    });
  }
  return ven;
}

export function nactiPrehledHistorie(): Nacteno<Prehled> {
  const v = nactiJson<unknown>('historie/prehled.json', null);
  const k = jeObjekt(v.data) ? v.data : {};
  const metodika = jeObjekt(k.metodika) ? k.metodika : {};
  const statistika = jeObjekt(k.statistika) ? k.statistika : null;
  const rozsah = statistika && Array.isArray(statistika.rozsah_let) ? statistika.rozsah_let : null;

  const obdobi: Obdobi[] = objekty(k, 'obdobi')
    .map((z, i) => {
      const nazev = txt(z, 'nazev');
      if (!nazev) return null;
      return {
        id: txt(z, 'id') ?? `obdobi-${i + 1}`,
        poradi: cis(z, 'poradi'),
        nazev,
        od: cis(z, 'od'),
        do: cis(z, 'do'),
        presnostRozsahu: txt(z, 'presnost_rozsahu'),
        text: txt(z, 'text', 'popis'),
        osobnosti: texty(z, 'osobnosti', 'osoby'),
        zdrojeIds: texty(z, 'zdroje_ids'),
      };
    })
    .filter((o): o is Obdobi => o !== null)
    .sort((a, b) => (a.poradi ?? 999) - (b.poradi ?? 999) || (a.od ?? 0) - (b.od ?? 0));

  return {
    ...v,
    data: {
      nazev: txt(k, 'nazev'),
      uvod: txt(k, 'uvod'),
      obdobi,
      zdroje: rejstrikZdroju(k),
      metodika: Object.entries(metodika)
        .filter(([, x]) => typeof x === 'string')
        .map(([klic, text]) => ({ klic, text: text as string })),
      statistika: {
        obdobi: cis(statistika, 'obdobi'),
        udalosti: cis(statistika, 'udalosti'),
        rozsah:
          rozsah && rozsah.length === 2 && typeof rozsah[0] === 'number' && typeof rozsah[1] === 'number'
            ? [rozsah[0], rozsah[1]]
            : null,
      },
    },
  };
}

export function nactiUdalostiHistorie(): Nacteno<{ udalosti: UdalostHistorie[]; zdroje: Map<string, Zdroj> }> {
  const v = nactiJson<unknown>('historie/udalosti.json', null);
  const k = jeObjekt(v.data) ? v.data : {};
  const surove = Array.isArray(v.data) ? (v.data as unknown[]).filter(jeObjekt) : objekty(k, 'udalosti');

  const udalosti: UdalostHistorie[] = surove
    .map((z, i) => {
      const nazev = txt(z, 'nazev', 'nadpis');
      const datum = txt(z, 'datum');
      if (!nazev || !datum) return null;
      const doIso = txt(z, 'datum_do');
      return {
        id: txt(z, 'id') ?? `udalost-${i + 1}`,
        datum,
        datum_do: doIso && doIso >= datum ? doIso : null,
        presnost: presnostZ(txt(z, 'presnost')),
        rok: cis(z, 'rok') ?? rokZIso(datum),
        obdobi: txt(z, 'obdobi'),
        kategorie: txt(z, 'kategorie'),
        nazev,
        popis: txt(z, 'popis'),
        osoby: texty(z, 'osoby'),
        tagy: texty(z, 'tagy'),
        jistota: normalizujJistotu(txt(z, 'jistota')),
        poznamka: txt(z, 'poznamka'),
        odkaz: txt(z, 'odkaz', 'url'),
        zdrojeIds: texty(z, 'zdroje_ids'),
      };
    })
    .filter((u): u is UdalostHistorie => u !== null)
    .sort((a, b) => a.datum.localeCompare(b.datum));

  return { ...v, data: { udalosti, zdroje: rejstrikZdroju(k) } };
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
        presnost: 'obdobi',
        druh: 'historie',
        nadpis: o.nazev,
        popis: o.text,
        odkaz: `#obdobi-${o.id}`,
        zdroj: 'historie/prehled.json',
        detail:
          o.presnostRozsahu === 'priblizna'
            ? 'období dějin města — hranice let jsou podle zdroje přibližné'
            : 'období dějin města',
        // Přibližný rozsah není doložený letopočet; zdroj to sám říká.
        jistota: o.presnostRozsahu === 'priblizna' ? 'sporne' : 'fakt',
        jistotaDuvod:
          o.presnostRozsahu === 'priblizna'
            ? 'Zdroj označuje rozsah období za přibližný — hranice let nejsou přesné datum.'
            : null,
      }),
    );

  const zUdalosti: UdalostOsy[] = udalosti.map((u) =>
    udalost({
      id: `historie-${u.id}`,
      datum: u.datum,
      datum_do: u.datum_do,
      presnost: u.presnost,
      druh: u.kategorie ? normalizujDruh('historie') : 'historie',
      nadpis: u.nazev,
      popis: u.popis,
      odkaz: u.odkaz,
      jistota: u.jistota,
      jistotaDuvod: u.poznamka,
      zdroj: 'historie/udalosti.json',
      detail: u.obdobi ? (nazvyObdobi.get(u.obdobi) ?? u.obdobi) : u.kategorie,
      osoby: u.osoby,
      tagy: u.tagy,
    }),
  );

  return [...zObdobi, ...zUdalosti];
}
