/**
 * Čtení geometrie a památek z `data/opendata/`.
 *
 * Formát těchhle souborů nikde zapsaný není — vznikají v jiném modulu. Čte se
 * proto tolerantně: přijme se FeatureCollection, jednotlivý Feature, holá
 * geometrie, pole prvků i obal `{ "geojson": … }`. Co se přečíst nedá, se
 * vynechá a napíše se to na stránku; build nepadá.
 *
 * Zdroj a licence se u map uvádět MUSÍ (web/DESIGN.md §3.6, OpenStreetMap to
 * vyžaduje). Hledají se v datech; když je zdroj neuvede, stránka to řekne
 * naplno místo aby si nějakou licenci vymyslela.
 */
import { nactiAdresarSoubory, slug, type Nacteno } from './data';
import { bodZeZaznamu, tvaryZGeometrie, type Tvar } from './mapy';
import { ano, cis, ico as icoZ, jeObjekt, rokZ, txt, type Zaznam } from './tolerantni';

export interface PrvekZdroje {
  id: string;
  nazev: string;
  tvary: Tvar[];
  vlastnosti: Zaznam;
}

export interface GeoSoubor {
  /** Klíč vrstvy — odvozený od jména souboru, tedy stabilní. */
  klic: string;
  nazev: string;
  popis: string | null;
  cesta: string;
  prvky: PrvekZdroje[];
  zdroj: string | null;
  licence: string | null;
  /** Kolik prvků mělo záznam, ale ne použitelnou geometrii. */
  bezGeometrie: number;
}

/* ─────────────────────────  Rozbalení GeoJSONu  ────────────────────── */

function features(v: unknown, hloubka = 0): Zaznam[] {
  if (hloubka > 4) return [];
  if (Array.isArray(v)) return v.filter(jeObjekt);
  if (!jeObjekt(v)) return [];

  const typ = typeof v.type === 'string' ? v.type : '';
  if (typ === 'FeatureCollection') return Array.isArray(v.features) ? v.features.filter(jeObjekt) : [];
  if (typ === 'Feature') return [v];
  if (typ && typeof v.coordinates !== 'undefined') return [{ geometry: v }];

  for (const k of ['geojson', 'features', 'prvky', 'data', 'items', 'objekty', 'zaznamy', 'seznam']) {
    const vnorene = v[k];
    if (typeof vnorene !== 'undefined') {
      const ven = features(vnorene, hloubka + 1);
      if (ven.length > 0) return ven;
    }
  }
  return [];
}

/** Vlastnosti prvku. GeoJSON je má v `properties`, volnější zápisy přímo. */
function vlastnostiPrvku(f: Zaznam): Zaznam {
  const p = f.properties ?? f.vlastnosti ?? f.attributes;
  return jeObjekt(p) ? p : f;
}

function geometriePrvku(f: Zaznam): unknown {
  for (const k of ['geometry', 'geometrie', 'geom', 'tvar']) {
    if (typeof f[k] !== 'undefined') return f[k];
  }
  return typeof f.type === 'string' && typeof f.coordinates !== 'undefined' ? f : null;
}

const KLICE_NAZVU = [
  'nazev', 'název', 'name', 'NAZEV', 'NÁZEV', 'NAME', 'title', 'titul',
  'popis', 'label', 'oznaceni', 'označení', 'ulice', 'adresa',
];

function nazevPrvku(v: Zaznam, poradi: number): string {
  const n = txt(v, ...KLICE_NAZVU);
  if (n) return n;
  const c = txt(v, 'cislo', 'číslo', 'okrsek', 'OKRSEK', 'kod', 'kód', 'id', 'ID');
  return c ? `č. ${c}` : `Prvek ${poradi + 1}`;
}

function idPrvku(v: Zaznam, f: Zaznam, poradi: number): string {
  return (
    txt(v, 'id', 'ID', 'cislo', 'číslo', 'okrsek', 'OKRSEK', 'kod', 'kód', 'ident') ??
    txt(f, 'id', 'ID') ??
    String(poradi + 1)
  );
}

/** Hezčí název vrstvy z jména souboru: `volebni_okrsky` → „Volební okrsky". */
export function nazevZeJmena(jmeno: string): string {
  const s = jmeno.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
  if (!s) return 'Vrstva';
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function klicZeJmena(soubor: string): string {
  return slug(soubor.replace(/\.[^.]+$/, '')) || 'vrstva';
}

function rozborSouboru(cesta: string, jmeno: string, obsah: unknown): GeoSoubor {
  const koren = jeObjekt(obsah) ? obsah : {};
  const metadata = jeObjekt(koren.metadata) ? koren.metadata : koren;

  const surove = features(obsah);
  const prvky: PrvekZdroje[] = [];
  let bezGeometrie = 0;

  surove.forEach((f, i) => {
    const v = vlastnostiPrvku(f);
    let tvary = tvaryZGeometrie(geometriePrvku(f));
    if (tvary.length === 0) {
      // Bod zapsaný jako `lat`/`lon` přímo u záznamu — mimo GeoJSON, ale běžné.
      const b = bodZeZaznamu(v) ?? bodZeZaznamu(f);
      if (b) tvary = [{ druh: 'bod', prstence: [[b]] }];
    }
    if (tvary.length === 0) bezGeometrie++;
    prvky.push({ id: idPrvku(v, f, i), nazev: nazevPrvku(v, i), tvary, vlastnosti: v });
  });

  return {
    klic: klicZeJmena(cesta.split('/').pop() ?? jmeno),
    nazev: txt(metadata, ...KLICE_NAZVU) ?? nazevZeJmena(jmeno),
    popis: txt(metadata, 'popis', 'description', 'poznamka'),
    cesta,
    prvky,
    zdroj: txt(metadata, 'zdroj', 'source', 'attribution', 'zdroj_dat', 'provider'),
    licence: txt(metadata, 'licence', 'license', 'licence_dat', 'podminky'),
    bezGeometrie,
  };
}

/** Všechny geometrické vrstvy z `opendata/geo/`. Přijímá `.json` i `.geojson`. */
export function nactiGeo(): Nacteno<GeoSoubor[]> {
  const v = nactiAdresarSoubory<unknown>('opendata/geo', ['.json', '.geojson']);
  return {
    stav: v.stav,
    zdroj: v.zdroj,
    poznamka: v.poznamka,
    data: v.data.map((s) => rozborSouboru(s.cesta, s.jmeno, s.data)).filter((g) => g.prvky.length > 0),
  };
}

/* ────────────────────────────  Památky  ────────────────────────────── */

export interface Pamatka {
  id: string;
  nazev: string;
  druh: string | null;
  adresa: string | null;
  /** Rejstříkové číslo ÚSKP — jediný spolehlivý identifikátor památky. */
  rejstrik: string | null;
  /** `true` jen když to data výslovně říkají. `null` = neuvedeno, ne „ne". */
  unesco: boolean | null;
  ochrana: string | null;
  rok: number | null;
  url: string | null;
  poznamka: string | null;
  tvary: Tvar[];
  maPolohu: boolean;
}

export interface Pamatky {
  pamatky: Pamatka[];
  zdroj: string | null;
  licence: string | null;
}

/**
 * Památky z `opendata/pamatky/`. Poloha je nepovinná — památka bez souřadnic
 * se do mapy nedostane, ale ze seznamu nezmizí.
 */
export function nactiPamatky(): Nacteno<Pamatky> {
  const v = nactiAdresarSoubory<unknown>('opendata/pamatky', ['.json', '.geojson']);
  const ven: Pamatka[] = [];
  let zdroj: string | null = null;
  let licence: string | null = null;
  const videna = new Set<string>();

  for (const s of v.data) {
    const koren = jeObjekt(s.data) ? s.data : {};
    const metadata = jeObjekt(koren.metadata) ? koren.metadata : koren;
    zdroj = zdroj ?? txt(metadata, 'zdroj', 'source', 'attribution', 'zdroj_dat');
    licence = licence ?? txt(metadata, 'licence', 'license', 'podminky');

    const zaznamy = features(s.data);
    zaznamy.forEach((f, i) => {
      const p = vlastnostiPrvku(f);
      let tvary = tvaryZGeometrie(geometriePrvku(f));
      if (tvary.length === 0) {
        const b = bodZeZaznamu(p) ?? bodZeZaznamu(f);
        if (b) tvary = [{ druh: 'bod', prstence: [[b]] }];
      }
      const rejstrik = txt(p, 'rejstrik', 'rejstříkové_číslo', 'cislo_rejstriku', 'uskp', 'id_uskp', 'katalog');
      const zaklad = rejstrik ?? txt(p, 'id', 'ID') ?? `${s.jmeno}-${i + 1}`;
      let id = zaklad;
      for (let k = 2; videna.has(id); k++) id = `${zaklad}-${k}`;
      videna.add(id);

      ven.push({
        id,
        nazev: nazevPrvku(p, i),
        druh: txt(p, 'druh', 'typ', 'kategorie', 'type', 'kategorie_pamatky'),
        adresa: txt(p, 'adresa', 'ulice', 'misto', 'místo', 'lokalita', 'address'),
        rejstrik,
        unesco: ano(p, 'unesco', 'UNESCO', 'svetove_dedictvi', 'world_heritage'),
        ochrana: txt(p, 'ochrana', 'stupen_ochrany', 'ochranny_rezim', 'pamatkova_ochrana'),
        rok: rokZ(p, 'rok', 'rok_zapisu', 'zapis', 'vznik', 'datum_zapisu', 'year'),
        url: txt(p, 'url', 'odkaz', 'link', 'zdroj_url'),
        poznamka: txt(p, 'poznamka', 'popis', 'description', 'note'),
        tvary,
        maPolohu: tvary.length > 0,
      });
    });
  }

  ven.sort((a, b) => a.nazev.localeCompare(b.nazev, 'cs-CZ'));
  return { stav: v.stav, zdroj: v.zdroj, poznamka: v.poznamka, data: { pamatky: ven, zdroj, licence } };
}

/* ────────────────────  Pomocníci pro párování vrstev  ──────────────── */

/** Číslo okrsku z libovolného prvku — pro spárování geometrie s výsledky voleb. */
export function cisloOkrsku(v: Zaznam | null | undefined): string | null {
  const c = cis(v, 'okrsek', 'OKRSEK', 'cislo_okrsku', 'cislo', 'číslo', 'kod', 'kód', 'id', 'ID', 'number', 'okrsk');
  if (c !== null && Number.isFinite(c)) return String(Math.trunc(c));
  const s = txt(v, 'okrsek', 'OKRSEK', 'cislo_okrsku', 'cislo', 'číslo', 'kod', 'kód', 'id', 'ID');
  if (!s) return null;
  const m = /(\d{1,4})/.exec(s);
  return m ? String(Number(m[1])) : null;
}

/** IČO z prvku — pro spárování geometrie s firmou nebo majetkem. */
export function icoPrvku(v: Zaznam | null | undefined): string | null {
  return icoZ(v, 'ico', 'IČO', 'ICO', 'ic', 'subjekt_ico');
}
