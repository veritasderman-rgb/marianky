/**
 * Výsledky voleb po volebních okrscích — `data/opendata/volby/`.
 *
 * Struktura zdroje:
 *   prehled.json         — obec, zdroj, licence, seznam cyklů, kde je geometrie
 *   cykly/{cyklus}.json  — jeden volební cyklus; uvnitř `volby[]` (kola)
 *   okrsky_geo/{rok}.json— hranice okrsků platné k roku (GeoJSON, WGS-84)
 *   zastupitele.json     — zvolení zastupitelé napříč komunálními volbami
 *   okrsky.json          — co o okrscích víme a co ne
 *
 * Dvě věci, které zdroj výslovně říká a web je musí přenést:
 *   – **Shodné číslo okrsku ve dvou volbách NEZNAMENÁ shodné území.** ČSÚ
 *     hranice k jednotlivým volbám nepublikuje; geometrie existuje jen jako
 *     vrstva k roku.
 *   – **Okrsková data u komunálních voleb počítají hlasy pro kandidáty**, ne
 *     pro voliče. Proto je „platných hlasů" mnohonásobně víc než voličů —
 *     každý volič má tolik hlasů, kolik se volí zastupitelů.
 */
import { nactiAdresarSoubory, nactiConfig, nactiJson, slug, type Nacteno } from './data';
import { sestavRegistr, type RegistrBarev } from './barvy';
import { cisloOkrsku, type GeoSoubor, type PrvekZdroje } from './geodata';
import { tvaryZGeometrie } from './mapy';
import { cis, jeObjekt, objekty, txt, type Zaznam } from './tolerantni';

export interface StranaVOkrsku {
  nazev: string;
  /** Klíč pro přidělení barvy — barva patří straně, ne pořadí ve výsledku. */
  klic: string;
  hlasy: number | null;
  podil: number | null;
}

export interface Okrsek {
  cislo: string;
  volicu: number | null;
  obalky: number | null;
  odevzdane: number | null;
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
  hlasyProc: number | null;
  poradiMandatu: number | null;
  osoba_id: string | null;
  povolani: string | null;
}

export interface VysledekStrany {
  nazev: string;
  zkratka: string | null;
  klic: string;
  hlasy: number | null;
  podil: number | null;
  mandaty: number | null;
}

export type TypVoleb =
  | 'komunalni'
  | 'snemovni'
  | 'krajske'
  | 'senatni'
  | 'prezidentske'
  | 'evropske'
  | 'jine';

/** Jedno hlasování — u dvoukolových voleb je kolo samostatná položka. */
export interface Volba {
  id: string;
  kolo: number | null;
  datum: string | null;
  mandatu: number | null;
  celkem: {
    volicu: number | null;
    obalky: number | null;
    odevzdane: number | null;
    platne: number | null;
    ucast: number | null;
  };
  okrsky: Okrsek[];
  strany: VysledekStrany[];
  zvoleni: Zvoleny[];
  kandidatu: number | null;
}

export interface VolebniCyklus {
  id: string;
  typ: TypVoleb;
  typNazev: string;
  rok: number;
  nazev: string;
  /** `ok`, `neucastnila_se` apod. — přebírá se ze zdroje beze změny. */
  stav: string | null;
  volby: Volba[];
  zdroj: string | null;
  cesta: string;
}

export interface PrehledVoleb {
  obec: string | null;
  zdroj: string | null;
  licence: string | null;
  /** Ke kterým rokům zdroj publikuje hranice okrsků. */
  geometrieK: { platiK: string; soubor: string | null; okrsku: number | null }[];
}

/* ────────────────────────────  Typ voleb  ──────────────────────────── */

const TYPY: Record<string, { typ: TypVoleb; nazev: string }> = {
  komunalni: { typ: 'komunalni', nazev: 'komunální volby' },
  snemovni: { typ: 'snemovni', nazev: 'volby do Poslanecké sněmovny' },
  krajske: { typ: 'krajske', nazev: 'krajské volby' },
  senatni: { typ: 'senatni', nazev: 'volby do Senátu' },
  prezidentske: { typ: 'prezidentske', nazev: 'volba prezidenta' },
  evropske: { typ: 'evropske', nazev: 'volby do Evropského parlamentu' },
};

export const NAZVY_TYPU: { klic: TypVoleb; nazev: string; kratky: string }[] = [
  { klic: 'komunalni', nazev: 'komunální volby', kratky: 'Komunální' },
  { klic: 'snemovni', nazev: 'volby do Poslanecké sněmovny', kratky: 'Sněmovní' },
  { klic: 'krajske', nazev: 'krajské volby', kratky: 'Krajské' },
  { klic: 'prezidentske', nazev: 'volba prezidenta', kratky: 'Prezidentské' },
  { klic: 'evropske', nazev: 'volby do Evropského parlamentu', kratky: 'Evropské' },
  { klic: 'senatni', nazev: 'volby do Senátu', kratky: 'Senátní' },
  { klic: 'jine', nazev: 'volby', kratky: 'Ostatní' },
];

function typVoleb(druh: string | null): { typ: TypVoleb; nazev: string } {
  const s = (druh ?? '').trim().toLowerCase();
  return TYPY[s] ?? { typ: 'jine', nazev: 'volby' };
}

/* ────────────────────────────  Rozbor cyklu  ───────────────────────── */

function stranyCelkem(v: Zaznam): VysledekStrany[] {
  return objekty(v, 'strany')
    .map((s) => {
      const nazev = txt(s, 'nazev', 'kandidat', 'jmeno');
      if (!nazev) return null;
      const podil = cis(s, 'hlasy_proc');
      return {
        nazev,
        zkratka: txt(s, 'zkratka'),
        klic: slug(nazev) || nazev,
        hlasy: cis(s, 'hlasy'),
        podil: podil === null ? null : podil / 100,
        mandaty: cis(s, 'mandaty'),
      };
    })
    .filter((s): s is VysledekStrany => s !== null);
}

/**
 * Okrsek. Hlasy stran jsou ve zdroji jako `hlasy_stran: { "1": 1723, … }`,
 * kde klíč je POŘADÍ strany v poli `strany` téhož hlasování — ne její název.
 * Bez převodu přes `poradi` by se v okrsku ukázala čísla bez jmen.
 */
function okrsekZe(z: Zaznam, poradiNaStranu: Map<string, VysledekStrany>): Okrsek | null {
  const cislo = cisloOkrsku(z);
  if (!cislo) return null;

  const volicu = cis(z, 'volicu_v_seznamu');
  const obalky = cis(z, 'vydane_obalky');
  const odevzdane = cis(z, 'odevzdane_obalky');
  const platne = cis(z, 'platne_hlasy');
  const ucastProc = cis(z, 'ucast_proc');

  let ucast = ucastProc === null ? null : ucastProc / 100;
  let dopocitana = false;
  if (ucast === null && volicu !== null && volicu > 0 && obalky !== null) {
    ucast = obalky / volicu;
    dopocitana = true;
  }

  const hlasyStran = jeObjekt(z.hlasy_stran) ? z.hlasy_stran : null;
  const strany: StranaVOkrsku[] = [];
  if (hlasyStran) {
    const soucet = Object.values(hlasyStran).reduce<number>(
      (s, v) => s + (typeof v === 'number' && Number.isFinite(v) ? v : 0),
      0,
    );
    for (const [poradi, hlasy] of Object.entries(hlasyStran)) {
      const info = poradiNaStranu.get(poradi);
      const h = typeof hlasy === 'number' && Number.isFinite(hlasy) ? hlasy : null;
      strany.push({
        nazev: info?.nazev ?? `Kandidátka č. ${poradi}`,
        klic: info?.klic ?? `poradi-${poradi}`,
        hlasy: h,
        podil: h === null || !(soucet > 0) ? null : h / soucet,
      });
    }
  }

  const sHlasy = strany.filter((s) => s.hlasy !== null);
  const vitez = sHlasy.length > 0 ? sHlasy.reduce((a, b) => ((b.hlasy ?? 0) > (a.hlasy ?? 0) ? b : a)) : null;

  return { cislo, volicu, obalky, odevzdane, platne, ucast, ucastDopocitana: dopocitana, strany, vitez };
}

function zvolenyZe(z: Zaznam): Zvoleny | null {
  const jmeno = txt(z, 'cele_jmeno') ?? [txt(z, 'jmeno'), txt(z, 'prijmeni')].filter(Boolean).join(' ');
  if (!jmeno) return null;
  const proc = cis(z, 'hlasy_proc');
  return {
    jmeno,
    strana: txt(z, 'strana'),
    hlasy: cis(z, 'hlasy'),
    hlasyProc: proc === null ? null : proc / 100,
    poradiMandatu: cis(z, 'poradi_mandatu'),
    osoba_id: txt(z, 'osoba_id'),
    povolani: txt(z, 'povolani'),
  };
}

function volbaZe(z: Zaznam, idCyklu: string, poradi: number): Volba {
  const strany = stranyCelkem(z);
  const poradiNaStranu = new Map<string, VysledekStrany>();
  objekty(z, 'strany').forEach((s, i) => {
    const p = cis(s, 'poradi');
    const nazev = txt(s, 'nazev', 'kandidat', 'jmeno');
    const cil = strany.find((x) => x.nazev === nazev) ?? strany[i];
    if (cil) poradiNaStranu.set(String(p ?? i + 1), cil);
  });

  const ucast = jeObjekt(z.ucast) ? z.ucast : null;
  const volicu = cis(ucast, 'volicu_v_seznamu');
  const obalky = cis(ucast, 'vydane_obalky');
  const ucastProc = cis(ucast, 'ucast_proc');

  const okrsky = objekty(z, 'okrsky')
    .map((o) => okrsekZe(o, poradiNaStranu))
    .filter((o): o is Okrsek => o !== null)
    .sort((a, b) => (Number(a.cislo) || 0) - (Number(b.cislo) || 0));

  const kolo = cis(z, 'kolo');

  return {
    id: `${idCyklu}${kolo === null ? (poradi > 0 ? `-${poradi + 1}` : '') : `-kolo${kolo}`}`,
    kolo,
    datum: txt(z, 'datum'),
    mandatu: cis(z, 'mandatu'),
    celkem: {
      volicu,
      obalky,
      odevzdane: cis(ucast, 'odevzdane_obalky'),
      platne: cis(ucast, 'platne_hlasy'),
      ucast:
        ucastProc !== null
          ? ucastProc / 100
          : volicu !== null && volicu > 0 && obalky !== null
            ? obalky / volicu
            : null,
    },
    okrsky,
    strany,
    zvoleni: objekty(z, 'zvoleni')
      .map(zvolenyZe)
      .filter((x): x is Zvoleny => x !== null)
      .sort((a, b) => (a.poradiMandatu ?? 999) - (b.poradiMandatu ?? 999)),
    kandidatu: objekty(z, 'kandidati').length || null,
  };
}

/** Všechny volební cykly z `opendata/volby/cykly/`, od nejnovějšího. */
export function nactiVolby(): Nacteno<VolebniCyklus[]> {
  const v = nactiAdresarSoubory<unknown>('opendata/volby/cykly', ['.json']);
  const ven: VolebniCyklus[] = [];

  for (const s of v.data) {
    if (!jeObjekt(s.data)) continue;
    const z = s.data;
    const { typ, nazev: typNazev } = typVoleb(txt(z, 'druh'));
    const rok = cis(z, 'rok') ?? 0;
    const id = txt(z, 'cyklus') ?? s.jmeno;

    ven.push({
      id,
      typ,
      typNazev,
      rok,
      nazev: txt(z, 'nazev') ?? typNazev,
      stav: txt(z, 'stav'),
      volby: objekty(z, 'volby').map((x, i) => volbaZe(x, id, i)),
      zdroj: txt(z, 'zdroj'),
      cesta: s.cesta,
    });
  }

  ven.sort((a, b) => b.rok - a.rok || a.typ.localeCompare(b.typ));
  return { stav: v.stav, zdroj: v.zdroj, poznamka: v.poznamka, data: ven };
}

export function nactiPrehledVoleb(): Nacteno<PrehledVoleb> {
  const v = nactiJson<unknown>('opendata/volby/prehled.json', null);
  const k = jeObjekt(v.data) ? v.data : {};
  return {
    ...v,
    data: {
      obec: jeObjekt(k.obec) ? txt(k.obec, 'nazev') : null,
      zdroj: txt(k, 'zdroj'),
      licence: txt(k, 'licence'),
      geometrieK: objekty(k, 'geometrie_okrsku').map((g) => ({
        platiK: txt(g, 'plati_k') ?? '',
        soubor: txt(g, 'soubor'),
        okrsku: cis(g, 'okrsku'),
      })),
    },
  };
}

/** Výhrada zdroje k porovnávání okrsků mezi lety — přebírá se doslova. */
export function nactiVyhraduOkrsku(): Nacteno<{ poznamka: string | null; coVime: string | null; coNevime: string | null }> {
  const v = nactiJson<unknown>('opendata/volby/okrsky.json', null);
  const k = jeObjekt(v.data) ? v.data : {};
  return {
    ...v,
    data: {
      poznamka: txt(k, 'poznamka'),
      coVime: txt(k, 'co_vime'),
      coNevime: txt(k, 'co_nevime'),
    },
  };
}

/** Zvolení zastupitelé napříč komunálními volbami. */
export interface ZastupitelZaznam extends Zvoleny {
  cyklus: string;
  rok: number | null;
  datum: string | null;
}

/**
 * Sjednocení `osoba_id` u lidí, které zdroje vedou pod dvěma jmény.
 *
 * ČSÚ bere jméno z kandidátní listiny, web města a profily z pozdějšího
 * úřadování — u „Samuel Zabolotnij" versus „Samuel Zabolotný" se liší i po
 * odstranění diakritiky, takže je automatika nespáruje a týž člověk by se
 * na stránce objevil dvakrát: jednou jako zvolený, podruhé (mylně) jako
 * někdo, kdo nastoupil až během období.
 *
 * Sloučení je proto RUČNÍ a stojí v `config/tataz_osoba.json` i s dokladem.
 * Spojit dva lidi do jednoho je horší chyba než je nechat nespárované, tak
 * se sem nic nepřidává odhadem. Správné místo pro opravu je sběrač, který
 * `osoba_id` přiděluje; tohle je záplata do té doby.
 */
interface TatazOsoba {
  aliasy?: { id?: string; jina_id?: string[] }[];
}
function prevodIdOsob(): Map<string, string> {
  const v = nactiConfig<TatazOsoba>('tataz_osoba.json', {});
  const mapa = new Map<string, string>();
  for (const a of v.data?.aliasy ?? []) {
    if (!a?.id) continue;
    for (const jine of a.jina_id ?? []) if (jine) mapa.set(jine, a.id);
  }
  return mapa;
}

export function nactiZastupitele(): Nacteno<ZastupitelZaznam[]> {
  const v = nactiJson<unknown>('opendata/volby/zastupitele.json', null);
  const surove = Array.isArray(v.data) ? v.data.filter(jeObjekt) : [];
  const prevod = prevodIdOsob();
  return {
    ...v,
    data: surove
      .map((z) => {
        const zaklad = zvolenyZe(z);
        if (!zaklad) return null;
        const id = zaklad.osoba_id;
        return {
          ...zaklad,
          osoba_id: id ? (prevod.get(id) ?? id) : id,
          cyklus: txt(z, 'cyklus') ?? '',
          rok: cis(z, 'rok'),
          datum: txt(z, 'datum'),
        };
      })
      .filter((x): x is ZastupitelZaznam => x !== null),
  };
}

/* ────────────────────────────  Pomocníci  ──────────────────────────── */

/**
 * Registr barev stran. Barva patří straně (podle jejího klíče), ne pořadí ve
 * výsledku — když se přepne rok nebo okrsek, strana si barvu podrží
 * (web/DESIGN.md §2 bod 2, §3.6).
 */
export function registrStran(volby: Volba[]): RegistrBarev {
  const soucty = new Map<string, number>();
  for (const v of volby) {
    for (const s of v.strany) soucty.set(s.klic, (soucty.get(s.klic) ?? 0) + (s.hlasy ?? 0));
  }
  return sestavRegistr([...soucty.entries()].map(([ico, celkem_czk]) => ({ ico, celkem_czk })));
}

/** Hlavní hlasování cyklu — u dvoukolových voleb první kolo. */
export function hlavniVolba(c: VolebniCyklus): Volba | null {
  if (c.volby.length === 0) return null;
  return c.volby.find((v) => v.kolo === null || v.kolo === 1) ?? c.volby[0];
}

/**
 * Najde geometrickou vrstvu, která sedí na okrsky daného hlasování, a vrátí
 * i to, kolik okrsků se spárovat nepodařilo — mapa má povinnost to napsat.
 */
export function geometrieOkrsku(
  geo: GeoSoubor[],
  cisla: string[],
): { vrstva: GeoSoubor | null; podleCisla: Map<string, PrvekZdroje>; nesparovano: string[] } {
  const hledana = new Set(cisla);
  let nejlepsi: { vrstva: GeoSoubor; mapa: Map<string, PrvekZdroje> } | null = null;

  for (const g of geo) {
    const mapa = new Map<string, PrvekZdroje>();
    for (const p of g.prvky) {
      const c = cisloOkrsku(p.vlastnosti);
      if (c && hledana.has(c) && !mapa.has(c) && p.tvary.length > 0) mapa.set(c, p);
    }
    if (mapa.size > 0 && (!nejlepsi || mapa.size > nejlepsi.mapa.size)) nejlepsi = { vrstva: g, mapa };
  }

  if (!nejlepsi) return { vrstva: null, podleCisla: new Map(), nesparovano: cisla };
  const nalezene = nejlepsi.mapa;
  return { vrstva: nejlepsi.vrstva, podleCisla: nalezene, nesparovano: cisla.filter((c) => !nalezene.has(c)) };
}

/**
 * Hranice okrsků — `opendata/volby/okrsky_geo/{rok}.json`. Zdroj u každé vrstvy
 * uvádí, ke kterému roku platí; jiné roky se z ní odvozovat nesmí, protože
 * hranice se mezi volbami mění.
 */
export interface VrstvaOkrsku {
  platiK: string;
  rok: number | null;
  vrstva: GeoSoubor;
  poznamka: string | null;
}

export function nactiGeometrieOkrsku(): Nacteno<VrstvaOkrsku[]> {
  const v = nactiAdresarSoubory<unknown>('opendata/volby/okrsky_geo', ['.json', '.geojson']);
  const ven: VrstvaOkrsku[] = [];

  for (const s of v.data) {
    if (!jeObjekt(s.data)) continue;
    const features = Array.isArray(s.data.features) ? s.data.features.filter(jeObjekt) : [];
    const platiK = txt(s.data, 'plati_k') ?? s.jmeno;
    ven.push({
      platiK,
      rok: cis({ x: platiK }, 'x'),
      poznamka: txt(s.data, 'poznamka'),
      vrstva: {
        klic: `okrsky-${slug(platiK) || s.jmeno}`,
        nazev: `Volební okrsky platné k roku ${platiK}`,
        popis: txt(s.data, 'poznamka'),
        cesta: s.cesta,
        prvky: features.map((f, i) => {
          const p = jeObjekt(f.properties) ? f.properties : {};
          const c = cisloOkrsku(p);
          return {
            id: c ?? String(i + 1),
            nazev: c ? `Okrsek ${c}` : `Prvek ${i + 1}`,
            tvary: tvaryZGeometrie(f.geometry),
            vlastnosti: p,
          };
        }),
        zdroj: txt(s.data, 'zdroj'),
        licence: txt(s.data, 'licence'),
        bezGeometrie: 0,
      },
    });
  }

  ven.sort((a, b) => (b.rok ?? 0) - (a.rok ?? 0));
  return { stav: v.stav, zdroj: v.zdroj, poznamka: v.poznamka, data: ven };
}

/**
 * Vybere vrstvu okrsků pro dané volby. Vrací i to, jestli rok geometrie sedí
 * na rok voleb — pokud ne, mapa to musí napsat: hranice se mezi volbami mění
 * a zdroj o starších letech geometrii nemá.
 */
export function vrstvaProRok(vrstvy: VrstvaOkrsku[], rok: number): { vrstva: VrstvaOkrsku; sedi: boolean } | null {
  if (vrstvy.length === 0) return null;
  const presna = vrstvy.find((v) => v.rok === rok);
  if (presna) return { vrstva: presna, sedi: true };
  // Nejbližší nižší rok; když žádný takový není, nejstarší dostupný.
  const nizsi = vrstvy.filter((v) => (v.rok ?? 0) <= rok).sort((a, b) => (b.rok ?? 0) - (a.rok ?? 0))[0];
  return { vrstva: nizsi ?? vrstvy[vrstvy.length - 1], sedi: false };
}
