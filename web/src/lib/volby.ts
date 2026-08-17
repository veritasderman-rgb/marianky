/**
 * Výsledky voleb po volebních okrscích — `data/opendata/volby/`.
 *
 * Formát zatím nikde zapsaný není, čte se proto tolerantně (viz `tolerantni.ts`).
 * Pravidla, která se tu drží:
 *
 *   – **Účast se nedopočítává potichu.** Když ji zdroj neuvádí a dá se spočítat
 *     z vydaných obálek a zapsaných voličů, spočítá se — ale záznam si nese
 *     příznak `ucastDopocitana` a stránka to napíše.
 *   – **Absolutní počty jsou povinné** (web/DESIGN.md §3.6). Procenta bez
 *     počtu voličů z volební mapy dělají lháře: velká plocha nemusí znamenat
 *     mnoho hlasů.
 *   – Chybějící údaj je `null`, nikdy nula.
 */
import { nactiAdresarSoubory, slug, type Nacteno } from './data';
import { sestavRegistr, type RegistrBarev } from './barvy';
import { cisloOkrsku, type GeoSoubor, type PrvekZdroje } from './geodata';
import { cis, isoDatum, jeObjekt, objekty, podil as podilZ, rokZ, txt, type Zaznam } from './tolerantni';

type PrvekVrstvy = PrvekZdroje;

export interface StranaVOkrsku {
  nazev: string;
  /** Klíč pro přidělení barvy — barva patří straně, ne pořadí ve výsledku. */
  klic: string;
  hlasy: number | null;
  podil: number | null;
}

export interface Okrsek {
  cislo: string;
  nazev: string | null;
  /** Kde se volí — škola, dům s pečovatelskou službou apod. */
  sidlo: string | null;
  volicu: number | null;
  obalky: number | null;
  platne: number | null;
  ucast: number | null;
  ucastDopocitana: boolean;
  strany: StranaVOkrsku[];
  vitez: StranaVOkrsku | null;
}

export interface Zvoleny {
  jmeno: string;
  strana: string | null;
  hlasy: number | null;
  poradi: number | null;
  osoba_id: string | null;
  nahradnik: boolean;
}

export interface VysledekStrany {
  nazev: string;
  klic: string;
  hlasy: number | null;
  podil: number | null;
  mandaty: number | null;
}

export type TypVoleb = 'komunalni' | 'parlamentni' | 'jine';

export interface VolebniCyklus {
  id: string;
  typ: TypVoleb;
  typNazev: string;
  rok: number;
  datum: string | null;
  nazev: string;
  okrsky: Okrsek[];
  celkem: {
    volicu: number | null;
    obalky: number | null;
    platne: number | null;
    ucast: number | null;
    ucastDopocitana: boolean;
  };
  strany: VysledekStrany[];
  zvoleni: Zvoleny[];
  zdroj: string | null;
  cesta: string;
}

/* ─────────────────────────  Rozbor jednoho cyklu  ──────────────────── */

function typVoleb(hodnota: string | null, cesta: string): { typ: TypVoleb; nazev: string } {
  const s = `${hodnota ?? ''} ${cesta}`.toLowerCase();
  if (s.includes('komunal') || s.includes('komunál') || s.includes('zastupitel') || s.includes('obecn')) {
    return { typ: 'komunalni', nazev: 'komunální volby' };
  }
  if (s.includes('snemov') || s.includes('sněmov') || s.includes('parlament') || s.includes('ps20') || s.includes('poslane')) {
    return { typ: 'parlamentni', nazev: 'volby do Poslanecké sněmovny' };
  }
  if (s.includes('senat') || s.includes('senát')) return { typ: 'jine', nazev: 'volby do Senátu' };
  if (s.includes('prezident')) return { typ: 'jine', nazev: 'volba prezidenta' };
  if (s.includes('evrop') || s.includes('ep20')) return { typ: 'jine', nazev: 'volby do Evropského parlamentu' };
  if (s.includes('kraj')) return { typ: 'jine', nazev: 'krajské volby' };
  return { typ: 'jine', nazev: 'volby' };
}

const KLICE_STRAN = ['strany', 'vysledky', 'výsledky', 'kandidatky', 'kandidátky', 'subjekty', 'hlasy_stran', 'results'];

function stranyZe(z: Zaznam | null | undefined): StranaVOkrsku[] {
  if (!z) return [];
  for (const k of KLICE_STRAN) {
    const v = z[k];
    if (Array.isArray(v)) {
      return v
        .filter(jeObjekt)
        .map((s) => {
          const nazev = txt(s, 'nazev', 'název', 'strana', 'kandidatka', 'kandidátka', 'nazev_strany', 'subjekt', 'name');
          if (!nazev) return null;
          return {
            nazev,
            klic: slug(nazev) || nazev,
            hlasy: cis(s, 'hlasy', 'pocet_hlasu', 'počet_hlasů', 'votes', 'platne_hlasy'),
            podil: podilZ(s, 'podil', 'podíl', 'procenta', 'proc_hlasu', 'share', 'pct'),
          };
        })
        .filter((s): s is StranaVOkrsku => s !== null);
    }
    // `{ "ANO 2011": 412, "ODS": 210 }`
    if (jeObjekt(v)) {
      return Object.entries(v)
        .map(([nazev, hlasy]) => ({
          nazev,
          klic: slug(nazev) || nazev,
          hlasy: typeof hlasy === 'number' && Number.isFinite(hlasy) ? hlasy : null,
          podil: null,
        }))
        .filter((s) => s.hlasy !== null);
    }
  }
  return [];
}

function dopocitejPodily(strany: StranaVOkrsku[], platne: number | null): StranaVOkrsku[] {
  const soucet = platne ?? strany.reduce((s, x) => s + (x.hlasy ?? 0), 0);
  if (!(soucet > 0)) return strany;
  return strany.map((s) => ({ ...s, podil: s.podil ?? (s.hlasy === null ? null : s.hlasy / soucet) }));
}

function vitezZe(strany: StranaVOkrsku[]): StranaVOkrsku | null {
  const sHlasy = strany.filter((s) => s.hlasy !== null);
  if (sHlasy.length === 0) return null;
  return sHlasy.reduce((a, b) => ((b.hlasy ?? 0) > (a.hlasy ?? 0) ? b : a));
}

function okrsekZe(z: Zaznam, poradi: number): Okrsek | null {
  const cislo = cisloOkrsku(z) ?? String(poradi + 1);
  const volicu = cis(z, 'volicu', 'voličů', 'zapsani_volici', 'zapsaní_voliči', 'zapsanych', 'zapsaných', 'volici_seznam', 'volici', 'voliči', 'registered');
  const obalky = cis(z, 'obalky', 'obálky', 'vydane_obalky', 'vydané_obálky', 'vydanych_obalek', 'odevzdane_obalky', 'ballots');
  const platne = cis(z, 'platne', 'platné', 'platne_hlasy', 'platné_hlasy', 'platnych_hlasu', 'valid');

  let ucast = podilZ(z, 'ucast', 'účast', 'ucast_pct', 'volebni_ucast', 'volební_účast', 'turnout');
  let dopocitana = false;
  if (ucast === null && volicu !== null && volicu > 0 && obalky !== null) {
    ucast = obalky / volicu;
    dopocitana = true;
  }

  const strany = dopocitejPodily(stranyZe(z), platne);

  return {
    cislo,
    nazev: txt(z, 'nazev', 'název', 'popis', 'oblast', 'cast', 'část'),
    sidlo: txt(z, 'sidlo', 'sídlo', 'misto', 'místo', 'adresa', 'volebni_mistnost', 'volební_místnost'),
    volicu,
    obalky,
    platne,
    ucast,
    ucastDopocitana: dopocitana,
    strany,
    vitez: vitezZe(strany),
  };
}

function cyklusZe(z: Zaznam, cesta: string, jmeno: string, poradi: number): VolebniCyklus | null {
  const surove = objekty(z, 'okrsky', 'okrsek', 'districts', 'obvody', 'volebni_okrsky');
  const rok = rokZ(z, 'rok', 'year') ?? rokZ({ x: `${cesta} ${jmeno}` }, 'x');
  if (surove.length === 0 && rok === null) return null;

  const { typ, nazev: typNazev } = typVoleb(txt(z, 'typ', 'druh', 'volby', 'type'), `${cesta} ${jmeno}`);
  const okrsky = surove.map(okrsekZe).filter((o): o is Okrsek => o !== null);
  okrsky.sort((a, b) => (Number(a.cislo) || 0) - (Number(b.cislo) || 0) || a.cislo.localeCompare(b.cislo, 'cs-CZ'));

  const celkemZ = jeObjekt(z.celkem) ? z.celkem : jeObjekt(z.souhrn) ? z.souhrn : null;
  const soucet = (vyber: (o: Okrsek) => number | null): number | null => {
    const hodnoty = okrsky.map(vyber).filter((v): v is number => v !== null);
    return hodnoty.length > 0 ? hodnoty.reduce((s, v) => s + v, 0) : null;
  };

  const volicu = cis(celkemZ, 'volicu', 'zapsani_volici', 'zapsanych', 'volici') ?? soucet((o) => o.volicu);
  const obalky = cis(celkemZ, 'obalky', 'vydane_obalky', 'vydanych_obalek') ?? soucet((o) => o.obalky);
  const platne = cis(celkemZ, 'platne', 'platne_hlasy', 'platnych_hlasu') ?? soucet((o) => o.platne);
  let ucast = podilZ(celkemZ, 'ucast', 'ucast_pct', 'volebni_ucast') ?? podilZ(z, 'ucast', 'volebni_ucast');
  let ucastDopocitana = false;
  if (ucast === null && volicu !== null && volicu > 0 && obalky !== null) {
    ucast = obalky / volicu;
    ucastDopocitana = true;
  }

  // Celkové výsledky stran: buď je zdroj uvádí, nebo se sečtou z okrsků.
  let strany: VysledekStrany[] = [];
  const zeZdroje = stranyZe(celkemZ ?? {}).length > 0 ? stranyZe(celkemZ ?? {}) : stranyZe(z);
  if (zeZdroje.length > 0) {
    strany = zeZdroje.map((s) => ({
      nazev: s.nazev,
      klic: s.klic,
      hlasy: s.hlasy,
      podil: s.podil,
      mandaty: null,
    }));
  } else {
    const podleKlice = new Map<string, VysledekStrany>();
    for (const o of okrsky) {
      for (const s of o.strany) {
        const stav = podleKlice.get(s.klic) ?? { nazev: s.nazev, klic: s.klic, hlasy: null, podil: null, mandaty: null };
        if (s.hlasy !== null) stav.hlasy = (stav.hlasy ?? 0) + s.hlasy;
        podleKlice.set(s.klic, stav);
      }
    }
    strany = [...podleKlice.values()];
  }
  const soucetHlasu = strany.reduce((s, x) => s + (x.hlasy ?? 0), 0);
  if (soucetHlasu > 0) {
    strany = strany.map((s) => ({ ...s, podil: s.podil ?? (s.hlasy === null ? null : s.hlasy / soucetHlasu) }));
  }

  // Mandáty a zvolení zastupitelé.
  const zvoleniZ = objekty(z, 'zvoleni', 'zvolení', 'zastupitele', 'zastupitelé', 'mandaty', 'mandáty', 'elected');
  const zvoleni: Zvoleny[] = zvoleniZ
    .map((k) => {
      const jmeno = txt(k, 'jmeno', 'jméno', 'nazev', 'name', 'kandidat', 'kandidát');
      if (!jmeno) return null;
      return {
        jmeno,
        strana: txt(k, 'strana', 'kandidatka', 'kandidátka', 'subjekt', 'party'),
        hlasy: cis(k, 'hlasy', 'pocet_hlasu', 'votes'),
        poradi: cis(k, 'poradi', 'pořadí', 'mandat_poradi', 'rank'),
        osoba_id: txt(k, 'osoba_id', 'osoba', 'id_osoby'),
        nahradnik: /nahrad|náhrad/i.test(txt(k, 'stav', 'role', 'poznamka') ?? ''),
      };
    })
    .filter((k): k is Zvoleny => k !== null);

  const mandatyPodleStran = new Map<string, number>();
  for (const zv of zvoleni) {
    if (!zv.strana || zv.nahradnik) continue;
    const k = slug(zv.strana) || zv.strana;
    mandatyPodleStran.set(k, (mandatyPodleStran.get(k) ?? 0) + 1);
  }
  strany = strany.map((s) => ({ ...s, mandaty: s.mandaty ?? mandatyPodleStran.get(s.klic) ?? null }));
  strany.sort((a, b) => (b.hlasy ?? 0) - (a.hlasy ?? 0));

  const rokFinal = rok ?? 0;
  const nazev = txt(z, 'nazev', 'název', 'title') ?? `${typNazev.charAt(0).toUpperCase()}${typNazev.slice(1)} ${rokFinal || ''}`.trim();

  return {
    id: `${typ}-${rokFinal || `x${poradi}`}`,
    typ,
    typNazev,
    rok: rokFinal,
    datum: isoDatum(z, 'datum', 'date', 'datum_konani', 'konani'),
    nazev,
    okrsky,
    celkem: { volicu, obalky, platne, ucast, ucastDopocitana },
    strany,
    zvoleni,
    zdroj: txt(z, 'zdroj', 'source', 'url', 'zdroj_dat'),
    cesta,
  };
}

/** Všechny volební cykly z `opendata/volby/`, od nejnovějšího. */
export function nactiVolby(): Nacteno<VolebniCyklus[]> {
  const v = nactiAdresarSoubory<unknown>('opendata/volby', ['.json']);
  const ven: VolebniCyklus[] = [];
  const videna = new Set<string>();

  for (const s of v.data) {
    const kandidati: Zaznam[] = Array.isArray(s.data)
      ? s.data.filter(jeObjekt)
      : jeObjekt(s.data)
        ? (() => {
            const vnorene = objekty(s.data, 'volby', 'cykly', 'cyklus', 'elections');
            return vnorene.length > 0 ? vnorene : [s.data];
          })()
        : [];

    kandidati.forEach((k, i) => {
      const c = cyklusZe(k, s.cesta, s.jmeno, i);
      if (!c) return;
      let id = c.id;
      for (let n = 2; videna.has(id); n++) id = `${c.id}-${n}`;
      videna.add(id);
      ven.push({ ...c, id });
    });
  }

  ven.sort((a, b) => b.rok - a.rok || a.typ.localeCompare(b.typ));
  return { stav: v.stav, zdroj: v.zdroj, poznamka: v.poznamka, data: ven };
}

/* ────────────────────────────  Pomocníci  ──────────────────────────── */

/**
 * Registr barev stran. Barva patří straně (podle jejího klíče), ne pořadí ve
 * výsledku — když se přepne rok nebo okrsek, strana si barvu podrží
 * (web/DESIGN.md §2 bod 2, §3.6).
 */
export function registrStran(cykly: VolebniCyklus[]): RegistrBarev {
  const soucty = new Map<string, number>();
  for (const c of cykly) {
    for (const s of c.strany) {
      soucty.set(s.klic, (soucty.get(s.klic) ?? 0) + (s.hlasy ?? 0));
    }
  }
  return sestavRegistr([...soucty.entries()].map(([ico, celkem_czk]) => ({ ico, celkem_czk })));
}

/** Názvy stran podle klíče — pro legendu, když se v okrsku objeví jiný zápis. */
export function nazvyStran(cykly: VolebniCyklus[]): Map<string, string> {
  const m = new Map<string, string>();
  for (const c of cykly) for (const s of c.strany) if (!m.has(s.klic)) m.set(s.klic, s.nazev);
  return m;
}

/**
 * Najde geometrickou vrstvu, která sedí na okrsky daného cyklu. Vrací i to,
 * kolik okrsků se spárovat nepodařilo — mapa má povinnost to napsat.
 */
export function geometrieOkrsku(
  geo: GeoSoubor[],
  cisla: string[],
): { vrstva: GeoSoubor | null; podleCisla: Map<string, PrvekVrstvy>; nesparovano: string[] } {
  const hledana = new Set(cisla);
  let nejlepsi: { vrstva: GeoSoubor; mapa: Map<string, PrvekVrstvy> } | null = null;

  for (const g of geo) {
    const mapa = new Map<string, PrvekVrstvy>();
    for (const p of g.prvky) {
      const c = cisloOkrsku(p.vlastnosti);
      if (c && hledana.has(c) && !mapa.has(c) && p.tvary.length > 0) mapa.set(c, p);
    }
    if (mapa.size > 0 && (!nejlepsi || mapa.size > nejlepsi.mapa.size)) nejlepsi = { vrstva: g, mapa };
  }

  if (!nejlepsi) return { vrstva: null, podleCisla: new Map(), nesparovano: cisla };
  const nalezene = nejlepsi.mapa;
  return {
    vrstva: nejlepsi.vrstva,
    podleCisla: nalezene,
    nesparovano: cisla.filter((c) => !nalezene.has(c)),
  };
}
