/**
 * Příprava podkladů pro dashboard peněz.
 *
 * Vše se počítá při buildu z `data/penize/agregace/protistrany.json`.
 * Počty smluv za jednotlivé roky v agregaci nejsou — dopočítávají se
 * z `data/penize/smlouvy/*.json`, pokud existují. Když ne, do UI se napíše
 * „v datech není". Nic se nedohaduje.
 */
import { klicProtistrany as klicZ, type Protistrana, type SmlouvySubjektu } from './data';
import { souvisleRoky, type RadekHeatmapy, type SerieSkladana } from './grafy';
import { sestavRegistr, type RegistrBarev } from './barvy';
import { rokZData } from './format';

export type Smer = 'vydaj' | 'prijem';

export const MAX_RADKU_HEATMAPY = 40;

/**
 * Index počtů smluv.
 *
 * `smery` drží, pro které směry zdroj vůbec nějakou smlouvu obsahoval.
 * Bez toho by se „tenhle směr ve zdroji není" tvářilo jako „nula smluv" —
 * což je přesně ta záměna „nic se nestalo" a „nepodařilo se načíst",
 * které se projekt vyhýbá.
 */
export interface IndexSmluv {
  dostupny: boolean;
  smery: Set<string>;
  poRoce: Map<string, number>;
  poProtistrane: Map<string, number>;
}

const klicRoku = (smer: string, rok: number) => `${smer}|${rok}`;
const klicBunky = (smer: string, klic: string, rok: number) => `${smer}|${klic}|${rok}`;

export function indexujSmlouvy(soubory: SmlouvySubjektu[]): IndexSmluv {
  const poRoce = new Map<string, number>();
  const poProtistrane = new Map<string, number>();
  const smery = new Set<string>();
  let videno = 0;

  for (const soubor of soubory) {
    for (const s of soubor?.smlouvy ?? []) {
      const rok = rokZData(s?.datum);
      if (rok === null) continue;
      videno++;
      const smer = String(s.smer ?? '');
      smery.add(smer);
      poRoce.set(klicRoku(smer, rok), (poRoce.get(klicRoku(smer, rok)) ?? 0) + 1);
      // Klíč se počítá stejně jako v agregaci, aby seděl i u smluv bez IČO.
      const k = klicBunky(smer, klicZ(s.protistrana_ico, s.protistrana), rok);
      poProtistrane.set(k, (poProtistrane.get(k) ?? 0) + 1);
    }
  }
  return { dostupny: videno > 0, smery, poRoce, poProtistrane };
}

export function smluvZaRok(index: IndexSmluv, smer: Smer, rok: number): number | null {
  if (!index.dostupny || !index.smery.has(smer)) return null;
  return index.poRoce.get(klicRoku(smer, rok)) ?? 0;
}

export function smluvProtistranyZaRok(
  index: IndexSmluv,
  smer: Smer,
  protistrana: Pick<Protistrana, 'klic'>,
  rok: number,
): number | null {
  if (!index.dostupny || !index.smery.has(smer)) return null;
  return index.poProtistrane.get(klicBunky(smer, protistrana.klic, rok)) ?? 0;
}

/** Roky, které se mají objevit na ose. Chybějící rok uvnitř rozsahu = nula, ne díra. */
export function rokyZProtistran(ps: Protistrana[]): number[] {
  const roky: number[] = [];
  for (const p of ps) {
    for (const k of Object.keys(p.po_letech ?? {})) {
      const r = Number(k);
      if (Number.isFinite(r)) roky.push(r);
    }
    if (Number.isFinite(p.prvni_rok)) roky.push(p.prvni_rok);
    if (Number.isFinite(p.posledni_rok)) roky.push(p.posledni_rok);
  }
  return souvisleRoky(roky);
}

export function vRoce(p: Protistrana, rok: number): number {
  const v = p.po_letech?.[String(rok)];
  return typeof v === 'number' && Number.isFinite(v) ? v : 0;
}

export function podleSmeru(ps: Protistrana[], smer: Smer): Protistrana[] {
  return ps.filter((p) => p.smer === smer);
}

export function celkem(ps: Protistrana[]): number {
  return ps.reduce((s, p) => s + (p.celkem_czk ?? 0), 0);
}

/**
 * Šest největších + „Ostatní". Barvy se berou z registru podle IČO, takže
 * přepnutí pohledu ani filtr nikdy nepřebarví zbylé firmy.
 */
export function serieTop(
  ps: Protistrana[],
  roky: number[],
  registr: RegistrBarev,
): { serie: SerieSkladana[]; pocetOstatnich: number } {
  const serazene = [...ps].sort((a, b) => (b.celkem_czk ?? 0) - (a.celkem_czk ?? 0));
  const top = serazene.filter((p) => registr.sloty.has(p.klic));
  const zbytek = serazene.filter((p) => !registr.sloty.has(p.klic));

  const serie: SerieSkladana[] = top.map((p) => ({
    klic: p.klic,
    nazev: p.nazev,
    barva: registr.barva(p.klic),
    hodnoty: roky.map((r) => vRoce(p, r)),
    smluv: p.smluv ?? null,
  }));

  if (zbytek.length > 0) {
    serie.push({
      klic: null,
      nazev: `Ostatní (${zbytek.length})`,
      barva: 'var(--g-ost)',
      hodnoty: roky.map((r) => zbytek.reduce((s, p) => s + vRoce(p, r), 0)),
      smluv: zbytek.reduce((s, p) => s + (p.smluv ?? 0), 0),
    });
  }

  return { serie, pocetOstatnich: zbytek.length };
}

/** Registr barev pro daný směr. Staví se jednou z celé množiny, ne z filtrovaného výřezu. */
export function registrProSmer(ps: Protistrana[], smer: Smer): RegistrBarev {
  return sestavRegistr(podleSmeru(ps, smer).map((p) => ({ ico: p.klic, celkem_czk: p.celkem_czk ?? 0 })));
}

/**
 * Řádky heatmapy: řazeno podle `prvni_rok` (DESIGN §3.3), při shodě podle objemu.
 * Nula v `hodnoty` znamená „v tom roce žádné peníze" — vykresluje se jako
 * prázdná buňka, ne jako nejsvětlejší krok rampy.
 */
export function radkyHeatmapy(
  ps: Protistrana[],
  roky: number[],
  pocetSmluv?: (protistrana: Protistrana, rok: number) => number | null,
  limit = MAX_RADKU_HEATMAPY,
): {
  radky: RadekHeatmapy[];
  vynechano: number;
} {
  const vybrane = [...ps]
    .sort((a, b) => (b.celkem_czk ?? 0) - (a.celkem_czk ?? 0))
    .slice(0, limit)
    .sort((a, b) => (a.prvni_rok ?? 0) - (b.prvni_rok ?? 0) || (b.celkem_czk ?? 0) - (a.celkem_czk ?? 0));

  return {
    radky: vybrane.map((p) => ({
      klic: p.klic,
      nazev: p.nazev,
      hodnoty: roky.map((r) => vRoce(p, r)),
      pocty: pocetSmluv ? roky.map((r) => pocetSmluv(p, r)) : undefined,
      celkem: p.celkem_czk ?? 0,
      smluv: p.smluv ?? 0,
      prvni_rok: p.prvni_rok ?? roky[0] ?? 0,
      posledni_rok: p.posledni_rok ?? roky[roky.length - 1] ?? 0,
    })),
    vynechano: Math.max(0, ps.length - vybrane.length),
  };
}

/** Převede K-index na stavovou úroveň. Barva jde vždy s textem, nikdy sama. */
export function urovenKindexu(stupen: string | number | null | undefined): {
  uroven: 'dobre' | 'pozor' | 'vazne' | 'neznamo';
  text: string;
} {
  if (stupen === null || stupen === undefined || stupen === '') {
    return { uroven: 'neznamo', text: 'hodnocení není v datech' };
  }
  const s = String(stupen).trim().toUpperCase();
  if (s === 'A' || s === 'B') return { uroven: 'dobre', text: 'nízké riziko' };
  if (s === 'C') return { uroven: 'pozor', text: 'zvýšené riziko' };
  if (s === 'D' || s === 'E' || s === 'F') return { uroven: 'vazne', text: 'vysoké riziko' };
  return { uroven: 'neznamo', text: 'stupeň mimo škálu A–F' };
}
