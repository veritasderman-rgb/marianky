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
import { cis, jeObjekt, txt, type Zaznam } from './tolerantni';

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
  'popis', 'label', 'oznaceni', 'označení', 'adresa', 'ulice',
];

function nazevPrvku(v: Zaznam, poradi: number): string {
  const n = txt(v, ...KLICE_NAZVU);
  if (n) return n;
  const okrsek = txt(v, 'cislo_okrsku', 'okrsek', 'OKRSEK', 'CISLO');
  if (okrsek) return `Okrsek ${okrsek}`;
  const c = txt(v, 'cislo', 'číslo', 'kod', 'kód', 'kod_okrsku', 'kod_ku', 'kod_zsj', 'kod_casti', 'id', 'ID');
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
function nazevZeJmena(jmeno: string): string {
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
  const dolozka = txt(metadata, 'povinna_dolozka', 'dolozka');

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

  const zdroj = txt(metadata, 'zdroj', 'source', 'attribution', 'zdroj_dat', 'provider');
  return {
    klic: klicZeJmena(cesta.split('/').pop() ?? jmeno),
    nazev: txt(metadata, 'name', 'nazev', 'název', 'title') ?? nazevZeJmena(jmeno),
    popis: txt(metadata, 'popis', 'description', 'poznamka'),
    cesta,
    prvky,
    // Povinná doložka (OpenStreetMap, NPÚ) se lepí ke zdroji — musí být vidět.
    zdroj: dolozka ? (zdroj ? `${zdroj} — ${dolozka}` : dolozka) : zdroj,
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
  /** Ze kterého souboru záznam pochází — body, plochy, ochranná území. */
  sada: string;
  /** `objekt`, `areál`… podle ÚSKP. */
  kategorie: string | null;
  /** Slovní typ ochrany: kulturní památka, památková zóna, světové dědictví… */
  ochrana: string | null;
  /** Kód typu ochrany podle NPÚ: KP, NKP, PR, PZ, SD (světové dědictví), NZ. */
  ochranaKod: string | null;
  adresa: string | null;
  /** Rejstříkové číslo ÚSKP — jediný spolehlivý identifikátor památky. */
  rejstrik: string | null;
  /**
   * U bodu: LEŽÍ uvnitř statku světového dědictví. Není to totéž jako „je to
   * památka UNESCO" — zdroj to výslovně vysvětluje a web tenhle rozdíl drží.
   * `null` = zdroj o tom u záznamu nic neříká.
   */
  unesco: boolean | null;
  /** Sám statek světového dědictví (kód ochrany SD). */
  jeStatekUnesco: boolean;
  /** Nárazníková zóna statku světového dědictví (kód NZ). */
  jeNarazkovaZona: boolean;
  chraneno: boolean | null;
  fazeOchrany: string | null;
  rokZapisu: number | null;
  /** Do jakých plošných ochran bod spadá. */
  vUzemich: string[];
  url: string | null;
  anotace: string | null;
  tvary: Tvar[];
  maPolohu: boolean;
}

export interface Pamatky {
  pamatky: Pamatka[];
  zdroj: string | null;
  licence: string | null;
  /** Povinná doložka NPÚ — musí se zobrazit doslova. */
  dolozka: string | null;
  /** Kolik záznamů zdroj sám hlásí jako bez souřadnic. */
  bezSouradnicDleZdroje: number | null;
}

const SADY: Record<string, string> = {
  pamatky: 'body památek',
  pamatky_plochy: 'plochy památek',
  ochranna_uzemi: 'ochranná území',
};

/**
 * Památky z `opendata/pamatky/`. Poloha je nepovinná — památka bez souřadnic
 * se do mapy nedostane, ale ze seznamu nezmizí.
 *
 * UNESCO se NEHÁDÁ z názvu. Bere se z kódu typu ochrany, který NPÚ uvádí:
 * `SD` = světové dědictví, `NZ` = nárazníková zóna statku světového dědictví.
 */
export function nactiPamatky(): Nacteno<Pamatky> {
  const v = nactiAdresarSoubory<unknown>('opendata/pamatky', ['.json', '.geojson']);
  const ven: Pamatka[] = [];
  let zdroj: string | null = null;
  let licence: string | null = null;
  let dolozka: string | null = null;
  let bezSouradnic: number | null = null;
  const videna = new Set<string>();

  for (const s of v.data) {
    const koren = jeObjekt(s.data) ? s.data : {};
    const zaznamy = features(s.data);
    if (zaznamy.length === 0) continue;

    zdroj = zdroj ?? txt(koren, 'zdroj', 'source', 'attribution');
    licence = licence ?? txt(koren, 'licence', 'license');
    dolozka = dolozka ?? txt(koren, 'dolozka', 'povinna_dolozka');
    bezSouradnic = bezSouradnic ?? cis(koren, 'bez_souradnic');

    zaznamy.forEach((f, i) => {
      const p = vlastnostiPrvku(f);
      let tvary = tvaryZGeometrie(geometriePrvku(f));
      if (tvary.length === 0) {
        const b = bodZeZaznamu(p) ?? bodZeZaznamu(f);
        if (b) tvary = [{ druh: 'bod', prstence: [[b]] }];
      }

      // Zdroj přejmenoval pole (`typ_ochrany_kod` → `ochrana_kod`); čte se obojí.
      const kod = txt(p, 'ochrana_kod', 'typ_ochrany_kod');
      const ochrana = txt(p, 'ochrana', 'typ_ochrany');
      const rejstrik = txt(p, 'rejstrik', 'rejstrikove_cislo_uskp', 'cislo_rejstriku');
      const zaklad = txt(p, 'katalogove_cislo', 'prstav_id') ?? rejstrik ?? `${s.jmeno}-${i + 1}`;
      let id = `${s.jmeno}-${zaklad}`;
      for (let k = 2; videna.has(id); k++) id = `${s.jmeno}-${zaklad}-${k}`;
      videna.add(id);

      ven.push({
        id,
        nazev: nazevPrvku(p, i),
        sada: SADY[s.jmeno] ?? s.jmeno,
        kategorie: txt(p, 'kategorie', 'sada'),
        ochrana,
        ochranaKod: kod,
        adresa: txt(p, 'adresa', 'ulice', 'lokalita'),
        rejstrik,
        unesco: typeof p.unesco === 'boolean' ? p.unesco : null,
        jeStatekUnesco: kod === 'SD',
        jeNarazkovaZona: kod === 'NZ',
        chraneno: typeof p.chraneno === 'boolean' ? p.chraneno : null,
        fazeOchrany: txt(p, 'faze_ochrany'),
        rokZapisu: cis(p, 'rok_zapisu'),
        vUzemich: Array.isArray(p.v_uzemich)
          ? p.v_uzemich.filter((x): x is string => typeof x === 'string')
          : [],
        url: txt(p, 'url', 'odkaz'),
        anotace: txt(p, 'anotace', 'popis', 'upresneni_ochrany'),
        tvary,
        maPolohu: tvary.length > 0,
      });
    });
  }

  ven.sort((a, b) => a.nazev.localeCompare(b.nazev, 'cs-CZ'));
  return {
    stav: v.stav,
    zdroj: v.zdroj,
    poznamka: v.poznamka,
    data: { pamatky: ven, zdroj, licence, dolozka, bezSouradnicDleZdroje: bezSouradnic },
  };
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

