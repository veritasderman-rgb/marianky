/**
 * Firmy se sídlem ve městě — `data/firmy/`.
 *
 * Zdroj má připravené i to nejdůležitější: `prehled/dulezite.json` nese ke
 * každé zvýrazněné firmě seznam **kritérií**, podle kterých se do přehledu
 * dostala, včetně metodiky. Web si tedy žádná kritéria nevymýšlí — přebírá je
 * a jen je přeloží do věty, kterou je vidět u firmy.
 *
 * Zásady, které zdroj výslovně formuluje a web je musí přenést beze změny:
 *   – `datum_zaniku: null` znamená **nevíme**, ne „trvá". Adresní index ARES
 *     dávno zaniklé firmy nevede vůbec, takže osa zániků je neúplná.
 *   – Počet zaměstnanců je **pásmo**, ne číslo, a u většiny subjektů chybí.
 *     Chybějící údaj není nula.
 *   – Obrat ARES nezveřejňuje. Pásmo obratu je jen u firem doplněných
 *     z Hlídače státu.
 *   – Chybějící kritérium „dotace" znamená NEVÍME, ne „dotace nedostává".
 */
import { nactiJson, slug, type Nacteno } from './data';
import { cis, ico as icoZ, jeObjekt, objekty, texty, txt, type Zaznam } from './tolerantni';
import { datumVolneKratke } from './format';

export interface Firma {
  ico: string | null;
  /** Stabilní klíč do URL — IČO tam, kde je, jinak slug z názvu. */
  klic: string;
  nazev: string;
  vznik: string | null;
  /** `null` = zdroj datum výmazu nemá. NENÍ to „firma trvá". */
  zanik: string | null;
  /** `aktivni` | `v_likvidaci` | `zanikla` — přebírá se ze zdroje. */
  stav: string | null;
  pravniForma: string | null;
  adresa: string | null;
  /** `false` = ARES váže firmu k městu jen historickou adresou. */
  sidloVObci: boolean | null;
  obor: string | null;
  oborSekce: string | null;
  oborKod: string | null;
  zamestnancuRozsah: string | null;
}

/** Kritérium, podle kterého je firma v přehledu zvýrazněná. */
export interface Kriterium {
  kod: string;
  nazev: string;
  /** Čím konkrétně je kritérium naplněné — částka, pásmo, rok. */
  detail: string | null;
  zdroj: string | null;
}

export interface HlidacDoplnek {
  obratPasmo: string | null;
  zamestnancuPasmo: string | null;
  obor: string | null;
  platceDph: boolean | null;
  osobVeVedeni: number | null;
  osobSVazbouNaPolitiku: number | null;
  odkaz: string | null;
}

export interface DuleziaFirma extends Firma {
  kriteria: Kriterium[];
  hlidac: HlidacDoplnek | null;
  /** Objem od města z registru smluv, když je firma protistranou. */
  odMesta: number | null;
  smluv: number | null;
  prvniRok: number | null;
  posledniRok: number | null;
  /** `true` u subjektů městského holdingu — přesun peněz uvnitř města. */
  mestskyHolding: boolean;
  vnitromestskyPrevod: boolean;
  smer: string | null;
}

/* ─────────────────────  firmy/subjekty.json (všechny)  ─────────────── */

export interface Subjekty {
  firmy: Firma[];
  zdroj: string | null;
  uplnost: { hlasi: number | null; stazeno: number | null; chybi: number | null };
  metodika: { klic: string; text: string }[];
}

function firmaZe(z: Zaznam): Firma | null {
  const nazev = txt(z, 'nazev');
  if (!nazev) return null;
  const ico = icoZ(z, 'ico');
  return {
    ico,
    klic: ico ?? `n-${slug(nazev) || 'firma'}`,
    nazev,
    vznik: txt(z, 'datum_vzniku'),
    zanik: txt(z, 'datum_zaniku'),
    stav: txt(z, 'stav'),
    pravniForma: txt(z, 'pravni_forma_nazev'),
    adresa: txt(z, 'adresa'),
    sidloVObci: typeof z.sidlo_v_obci === 'boolean' ? z.sidlo_v_obci : null,
    obor: txt(z, 'nace_prevazujici_nazev', 'obor'),
    oborSekce: txt(z, 'nace_sekce_nazev', 'obor_sekce'),
    oborKod: txt(z, 'nace_prevazujici', 'obor_kod'),
    zamestnancuRozsah: txt(z, 'zamestnancu_rozsah'),
  };
}

export function nactiSubjektyFirem(): Nacteno<Subjekty> {
  const v = nactiJson<unknown>('firmy/subjekty.json', null);
  const k = jeObjekt(v.data) ? v.data : {};
  const uplnost = jeObjekt(k.uplnost) ? k.uplnost : null;
  const metodika = jeObjekt(k.metodika) ? k.metodika : {};

  const videne = new Set<string>();
  const firmy = objekty(k, 'subjekty')
    .map(firmaZe)
    .filter((f): f is Firma => f !== null)
    .filter((f) => {
      if (videne.has(f.klic)) return false;
      videne.add(f.klic);
      return true;
    })
    .sort((a, b) => a.nazev.localeCompare(b.nazev, 'cs-CZ'));

  return {
    ...v,
    data: {
      firmy,
      zdroj: txt(k, 'zdroj'),
      uplnost: {
        hlasi: cis(uplnost, 'ares_hlasi'),
        stazeno: cis(uplnost, 'stazeno'),
        chybi: cis(uplnost, 'chybi'),
      },
      metodika: Object.entries(metodika)
        .filter(([, x]) => typeof x === 'string')
        .map(([klic, text]) => ({ klic, text: text as string })),
    },
  };
}

/* ───────────────────  firmy/prehled/dulezite.json  ─────────────────── */

const NAZVY_KRITERII: Record<string, string> = {
  obchoduje_s_mestem: 'obchoduje s městem',
  mestsky_holding: 'subjekt městského holdingu',
  zamestnavatel: 'zaměstnavatel s doloženým počtem pracovníků',
  pametnik: 'pamětník — právnická osoba starší roku 1995',
  dotace: 'doložená dotace',
  sledovany_subjekt: 'sledovaný subjekt projektu',
  obor_lazenskeho_mesta: 'obor lázeňského města',
  forma_s_kapitalem: 'právní forma se základním kapitálem',
};

function kriteriumZe(z: Zaznam, kcFormat: (v: number | null) => string, cisloFormat: (v: number | null) => string): Kriterium | null {
  const kod = txt(z, 'kod');
  if (!kod) return null;
  const popis = txt(z, 'popis');
  const jednotka = txt(z, 'jednotka');
  const hodnotaCislo = typeof z.hodnota === 'number' ? z.hodnota : null;
  const hodnotaText = typeof z.hodnota === 'string' ? z.hodnota : null;

  const kusy: string[] = [];
  if (popis) kusy.push(popis);

  if (kod === 'obchoduje_s_mestem') {
    const smluv = cis(z, 'smluv');
    const bezCeny = cis(z, 'smluv_bez_ceny');
    const od = cis(z, 'prvni_rok');
    const doo = cis(z, 'posledni_rok');
    const cast: string[] = [];
    if (hodnotaCislo !== null) cast.push(jednotka === 'Kč' ? kcFormat(hodnotaCislo) : `${cisloFormat(hodnotaCislo)} ${jednotka ?? ''}`.trim());
    if (smluv !== null) cast.push(`${cisloFormat(smluv)} smluv`);
    if (bezCeny !== null && bezCeny > 0) cast.push(`z toho ${cisloFormat(bezCeny)} bez uvedené ceny`);
    if (od !== null && doo !== null) cast.push(`roky ${od}–${doo}`);
    if (z.vnitromestsky_prevod === true) cast.push('jde o přesun uvnitř města, ne platbu cizí firmě');
    if (cast.length > 0) kusy.push(cast.join(', '));
  } else if (hodnotaText) {
    // Hodnota kritéria bývá datum (zápis do rejstříku) — do textu patří česky.
    kusy.push(datumVolneKratke(hodnotaText));
  } else if (hodnotaCislo !== null) {
    kusy.push(jednotka === 'Kč' ? kcFormat(hodnotaCislo) : `${cisloFormat(hodnotaCislo)}${jednotka ? ` ${jednotka}` : ''}`);
  }

  const nazevCinnosti = txt(z, 'nazev_cinnosti');
  if (nazevCinnosti && kod === 'obor_lazenskeho_mesta') kusy.push(nazevCinnosti);

  return {
    kod,
    nazev: NAZVY_KRITERII[kod] ?? kod.replace(/_/g, ' '),
    detail: kusy.length > 0 ? kusy.join(' — ') : null,
    zdroj: txt(z, 'zdroj'),
  };
}

function hlidacZe(z: Zaznam | null): HlidacDoplnek | null {
  if (!z) return null;
  return {
    obratPasmo: txt(z, 'obrat_pasmo'),
    zamestnancuPasmo: txt(z, 'zamestnancu_pasmo'),
    obor: txt(z, 'obor'),
    platceDph: typeof z.platce_dph === 'boolean' ? z.platce_dph : null,
    osobVeVedeni: cis(z, 'osob_ve_vedeni'),
    osobSVazbouNaPolitiku: cis(z, 'osoby_s_vazbou_na_politiku'),
    odkaz: txt(z, 'odkaz'),
  };
}

export interface Dulezite {
  firmy: DuleziaFirma[];
  metodika: { klic: string; text: string }[];
  poctyPodleKriteria: { kod: string; nazev: string; pocet: number }[];
  silnaKriteria: string[];
  zebricky: { klic: string; nazev: string; polozky: { ico: string | null; nazev: string; popis: string | null }[] }[];
}

const NAZVY_ZEBRICKU: Record<string, string> = {
  nejvetsi_zamestnavatele: 'Největší zaměstnavatelé',
  nejvetsi_protistrany_mesta: 'Největší protistrany města',
  nejstarsi: 'Nejstarší subjekty',
  lazenstvi_a_cestovni_ruch: 'Lázeňství a cestovní ruch',
};

export function nactiDulezite(
  kcFormat: (v: number | null) => string,
  cisloFormat: (v: number | null) => string,
): Nacteno<Dulezite> {
  const v = nactiJson<unknown>('firmy/prehled/dulezite.json', null);
  const k = jeObjekt(v.data) ? v.data : {};
  const metodika = jeObjekt(k.metodika) ? k.metodika : {};
  const pocty = jeObjekt(k.pocty_podle_kriteria) ? k.pocty_podle_kriteria : {};
  const zebrickyZ = jeObjekt(k.zebricky) ? k.zebricky : {};

  const firmy: DuleziaFirma[] = objekty(k, 'firmy')
    .map((z) => {
      const zaklad = firmaZe(z);
      if (!zaklad) return null;
      const kriteria = objekty(z, 'kriteria')
        .map((x) => kriteriumZe(x, kcFormat, cisloFormat))
        .filter((x): x is Kriterium => x !== null);
      const obchod = objekty(z, 'kriteria').find((x) => txt(x, 'kod') === 'obchoduje_s_mestem') ?? null;

      return {
        ...zaklad,
        kriteria,
        hlidac: hlidacZe(jeObjekt(z.hlidac_statu) ? z.hlidac_statu : null),
        odMesta: obchod ? (typeof obchod.hodnota === 'number' ? obchod.hodnota : null) : null,
        smluv: cis(obchod, 'smluv'),
        prvniRok: cis(obchod, 'prvni_rok'),
        posledniRok: cis(obchod, 'posledni_rok'),
        mestskyHolding: kriteria.some((x) => x.kod === 'mestsky_holding'),
        vnitromestskyPrevod: obchod?.vnitromestsky_prevod === true,
        smer: obchod ? txt(obchod, 'smer') : null,
      };
    })
    .filter((f): f is DuleziaFirma => f !== null);

  return {
    ...v,
    data: {
      firmy,
      metodika: Object.entries(metodika)
        .filter(([, x]) => typeof x === 'string')
        .map(([klic, text]) => ({ klic, text: text as string })),
      poctyPodleKriteria: Object.entries(pocty)
        .filter(([, x]) => typeof x === 'number')
        .map(([kod, pocet]) => ({ kod, nazev: NAZVY_KRITERII[kod] ?? kod.replace(/_/g, ' '), pocet: pocet as number }))
        .sort((a, b) => b.pocet - a.pocet),
      silnaKriteria: Array.isArray(metodika.silna_kriteria)
        ? (metodika.silna_kriteria as unknown[]).filter((x): x is string => typeof x === 'string')
        : texty(metodika, 'silna_kriteria'),
      zebricky: Object.entries(zebrickyZ)
        .filter(([, x]) => Array.isArray(x))
        .map(([klic, x]) => ({
          klic,
          nazev: NAZVY_ZEBRICKU[klic] ?? klic.replace(/_/g, ' '),
          polozky: (x as unknown[]).filter(jeObjekt).map((p) => ({
            ico: icoZ(p, 'ico'),
            nazev: txt(p, 'nazev') ?? 'neuvedeno',
            popis:
              txt(p, 'zamestnancu_rozsah', 'obor', 'popis') ??
              (cis(p, 'celkem_czk') !== null ? kcFormat(cis(p, 'celkem_czk')) : null),
          })),
        })),
    },
  };
}

/* ──────────────────  firmy/prehled/mesto_a_firmy.json  ─────────────── */

export interface FirmaSMestem {
  ico: string;
  nazev: string;
  smer: string | null;
  celkem: number | null;
  smluv: number | null;
  smluvBezCeny: number | null;
  prvniRok: number | null;
  posledniRok: number | null;
  aktivni: boolean | null;
  vnitromestskyPrevod: boolean;
  mestskyHolding: boolean;
  poLetech: Map<number, number>;
}

export interface MestoAFirmy {
  firmy: FirmaSMestem[];
  souhrn: {
    protistranSIcem: number | null;
    veMeste: number | null;
    mimoMesto: number | null;
    objemVeMeste: number | null;
    objemVsech: number | null;
  };
  metodika: { klic: string; text: string }[];
}

export function nactiMestoAFirmy(): Nacteno<MestoAFirmy> {
  const v = nactiJson<unknown>('firmy/prehled/mesto_a_firmy.json', null);
  const k = jeObjekt(v.data) ? v.data : {};
  const souhrn = jeObjekt(k.souhrn) ? k.souhrn : null;
  const metodika = jeObjekt(k.metodika) ? k.metodika : {};

  const firmy: FirmaSMestem[] = objekty(k, 'firmy')
    .map((z) => {
      const ico = icoZ(z, 'ico');
      const nazev = txt(z, 'nazev_ares', 'nazev', 'nazev_v_registru');
      if (!ico || !nazev) return null;
      const poLetech = new Map<number, number>();
      if (jeObjekt(z.po_letech)) {
        for (const [rok, castka] of Object.entries(z.po_letech)) {
          const r = Number(rok);
          if (Number.isFinite(r) && typeof castka === 'number') poLetech.set(r, castka);
        }
      }
      return {
        ico,
        nazev,
        smer: txt(z, 'smer'),
        celkem: cis(z, 'celkem_czk'),
        smluv: cis(z, 'smluv'),
        smluvBezCeny: cis(z, 'smluv_bez_ceny'),
        prvniRok: cis(z, 'prvni_rok'),
        posledniRok: cis(z, 'posledni_rok'),
        aktivni: typeof z.aktivni_v_poslednim_roce === 'boolean' ? z.aktivni_v_poslednim_roce : null,
        vnitromestskyPrevod: z.vnitromestsky_prevod === true,
        mestskyHolding: z.mestsky_holding === true,
        poLetech,
      };
    })
    .filter((f): f is FirmaSMestem => f !== null)
    .sort((a, b) => (b.celkem ?? 0) - (a.celkem ?? 0));

  return {
    ...v,
    data: {
      firmy,
      souhrn: {
        protistranSIcem: cis(souhrn, 'protistran_mesta_s_icem'),
        veMeste: cis(souhrn, 'z_toho_se_sidlem_ve_meste'),
        mimoMesto: cis(souhrn, 'z_toho_mimo_mesto'),
        objemVeMeste: cis(souhrn, 'objem_protistran_ve_meste_czk'),
        objemVsech: cis(souhrn, 'objem_vsech_protistran_czk'),
      },
      metodika: Object.entries(metodika)
        .filter(([, x]) => typeof x === 'string')
        .map(([klic, text]) => ({ klic, text: text as string })),
    },
  };
}

/* ─────────────────────  firmy/prehled/obory.json  ──────────────────── */

export interface PohledOboru {
  klic: string;
  nazev: string;
  polozky: { nazev: string; pocet: number }[];
}

export interface Obory {
  pohledy: PohledOboru[];
  /** Který pohled zdroj doporučuje číst a proč. */
  kteryCist: string | null;
  mereni: string | null;
  bezOboru: { vsechny: number | null; pravnicke: number | null; poznamka: string | null };
}

const NAZVY_POHLEDU: Record<string, string> = {
  sekce_podnikatelske_subjekty: 'Podnikatelské subjekty podle sekce',
  sekce_vsechny_subjekty: 'Všechny subjekty podle sekce',
  sekce_pravnicke_osoby: 'Právnické osoby podle sekce',
  oddily_podnikatelske_subjekty: 'Podnikatelské subjekty podle oddílu',
  oddily: 'Všechny subjekty podle oddílu',
};

export function nactiObory(): Nacteno<Obory> {
  const v = nactiJson<unknown>('firmy/prehled/obory.json', null);
  const k = jeObjekt(v.data) ? v.data : {};
  const bez = jeObjekt(k.bez_urceneho_oboru) ? k.bez_urceneho_oboru : null;

  const pohledy: PohledOboru[] = Object.keys(NAZVY_POHLEDU)
    .filter((klic) => Array.isArray(k[klic]))
    .map((klic) => ({
      klic,
      nazev: NAZVY_POHLEDU[klic],
      polozky: (k[klic] as unknown[])
        .filter(jeObjekt)
        .map((p) => ({ nazev: txt(p, 'nazev') ?? '—', pocet: cis(p, 'subjektu') ?? 0 }))
        .sort((a, b) => b.pocet - a.pocet),
    }));

  return {
    ...v,
    data: {
      pohledy,
      kteryCist: txt(k, 'ktery_pohled_cist'),
      mereni: txt(k, 'mereni'),
      bezOboru: {
        vsechny: cis(bez, 'vsechny_subjekty'),
        pravnicke: cis(bez, 'pravnicke_osoby'),
        poznamka: txt(bez, 'poznamka'),
      },
    },
  };
}

/* ────────────────  firmy/prehled/casova_osa.json a souhrn  ─────────── */

export interface CasovaRadaFirem {
  vzniky: Map<number, number>;
  zaniky: Map<number, number>;
  mereniVzniku: string | null;
  mereniZaniku: string | null;
  stavZaniku: string | null;
  dohledanoZaniku: number | null;
}

function mapaLet(z: Zaznam | null): Map<number, number> {
  const ven = new Map<number, number>();
  const p = z && jeObjekt(z.po_letech) ? z.po_letech : null;
  if (!p) return ven;
  for (const [rok, pocet] of Object.entries(p)) {
    const r = Number(rok);
    if (Number.isFinite(r) && typeof pocet === 'number') ven.set(r, pocet);
  }
  return ven;
}

export function nactiCasovouRaduFirem(): Nacteno<CasovaRadaFirem> {
  const v = nactiJson<unknown>('firmy/prehled/casova_osa.json', null);
  const k = jeObjekt(v.data) ? v.data : {};
  const vzniky = jeObjekt(k.vzniky) ? k.vzniky : null;
  const zaniky = jeObjekt(k.zaniky) ? k.zaniky : null;
  return {
    ...v,
    data: {
      vzniky: mapaLet(vzniky),
      zaniky: mapaLet(zaniky),
      mereniVzniku: txt(vzniky, 'mereni'),
      mereniZaniku: txt(zaniky, 'mereni'),
      stavZaniku: txt(zaniky, 'stav'),
      dohledanoZaniku: cis(zaniky, 'dohledano_celkem'),
    },
  };
}

export interface SouhrnFirem {
  celkem: number | null;
  podleStavu: { nazev: string; pocet: number }[];
  pravnickychOsob: number | null;
  fyzickychOsob: number | null;
  sidloMimoObec: { pocet: number | null; poznamka: string | null };
  velikost: { sUdajem: number | null; bezUdaje: number | null; od10: number | null; od100: number | null; poznamka: string | null };
  vPrehleduDulezitych: number | null;
  napojenychNaRegistr: number | null;
  vznikyRozsah: { od: number | null; do: number | null };
  zdroj: string | null;
}

export function nactiSouhrnFirem(): Nacteno<SouhrnFirem> {
  const v = nactiJson<unknown>('firmy/prehled/souhrn.json', null);
  const k = jeObjekt(v.data) ? v.data : {};
  const stavy = jeObjekt(k.podle_stavu) ? k.podle_stavu : {};
  const mimo = jeObjekt(k.sidlo_dnes_mimo_obec) ? k.sidlo_dnes_mimo_obec : null;
  const velikost = jeObjekt(k.velikost) ? k.velikost : null;
  const rozsah = jeObjekt(k.vzniky_rozsah) ? k.vzniky_rozsah : null;

  const NAZVY_STAVU: Record<string, string> = {
    aktivni: 'aktivní',
    v_likvidaci: 'v likvidaci',
    zanikla: 'zaniklé',
  };

  return {
    ...v,
    data: {
      celkem: cis(k, 'subjektu_celkem'),
      podleStavu: Object.entries(stavy)
        .filter(([, x]) => typeof x === 'number')
        .map(([klic, pocet]) => ({ nazev: NAZVY_STAVU[klic] ?? klic.replace(/_/g, ' '), pocet: pocet as number }))
        .sort((a, b) => b.pocet - a.pocet),
      pravnickychOsob: cis(k, 'pravnickych_osob'),
      fyzickychOsob: cis(k, 'podnikajicich_fyzickych_osob'),
      sidloMimoObec: { pocet: cis(mimo, 'pocet'), poznamka: txt(mimo, 'poznamka') },
      velikost: {
        sUdajem: cis(velikost, 's_udajem_o_poctu_pracovniku'),
        bezUdaje: cis(velikost, 'bez_udaje'),
        od10: cis(velikost, 'od_10_zamestnancu'),
        od100: cis(velikost, 'od_100_zamestnancu'),
        poznamka: txt(velikost, 'poznamka'),
      },
      vPrehleduDulezitych: cis(k, 'v_prehledu_dulezitych'),
      napojenychNaRegistr: cis(k, 'napojenych_na_registr_smluv_mesta'),
      vznikyRozsah: { od: cis(rozsah, 'od'), do: cis(rozsah, 'do') },
      zdroj: txt(k, 'zdroj'),
    },
  };
}

/* ────────────────────────────  Pomocníci  ──────────────────────────── */

/** Souvislá řada roků z mapy — chybějící rok uvnitř rozsahu je nula, ne díra. */
export function souvisleRokyMapy(...mapy: Map<number, number>[]): number[] {
  const roky = mapy.flatMap((m) => [...m.keys()]);
  if (roky.length === 0) return [];
  const od = Math.min(...roky);
  const doo = Math.max(...roky);
  const ven: number[] = [];
  for (let r = od; r <= doo; r++) ven.push(r);
  return ven;
}

/** Firmy s aspoň jedním kritériem, řazené podle objemu obchodu s městem. */
export function seradDulezite(firmy: DuleziaFirma[]): DuleziaFirma[] {
  return [...firmy].sort(
    (a, b) =>
      (b.odMesta ?? 0) - (a.odMesta ?? 0) ||
      b.kriteria.length - a.kriteria.length ||
      a.nazev.localeCompare(b.nazev, 'cs-CZ'),
  );
}
