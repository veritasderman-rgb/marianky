/**
 * Firmy se sídlem ve městě — `data/firmy/` (ARES).
 *
 * Web z těchhle dat nic nevyvozuje. Že firma sídlí ve městě, není zásluha ani
 * podezření; že obchoduje s městem, je doložený fakt z registru smluv. Tenhle
 * soubor ty dvě věci drží oddělené a ke každé „důležité" firmě přikládá
 * **kritérium**, podle kterého je za důležitou označená — bez něj by seznam
 * jen tvrdil „tahle je zajímavá" a nikdo by nevěděl proč.
 */
import { nactiAdresarSoubory, slug, type Nacteno, type Protistrana } from './data';
import { ano, ico as icoZ, isoDatum, jeObjekt, rokZIso, txt, type Zaznam } from './tolerantni';
import type { PropojeniOsob } from './vazby';

export interface Firma {
  /** `null` u záznamu, kde zdroj IČO neuvádí. */
  ico: string | null;
  /** Stabilní klíč do URL — IČO tam, kde je, jinak slug z názvu. */
  klic: string;
  nazev: string;
  vznik: string | null;
  zanik: string | null;
  /** `null` = zdroj o tom mlčí. Není to totéž jako „zaniklá". */
  aktivni: boolean | null;
  obor: string | null;
  nace: string | null;
  pravniForma: string | null;
  sidlo: string | null;
  url: string | null;
}

/** Kritérium, podle kterého je firma v přehledu označená za důležitou. */
export interface Duvod {
  klic: string;
  nazev: string;
  /** Čím konkrétně je kritérium naplněné — částka, počet, jména. */
  detail: string | null;
}

export interface FirmaSKontextem extends Firma {
  duvody: Duvod[];
  /** Objem smluv od města. `null` = v registru smluv města firma není. */
  odMesta: number | null;
  mestu: number | null;
  smluv: number | null;
  prvniRok: number | null;
  posledniRok: number | null;
  /** Klíč protistrany pro odkaz na `/penize/[ico]`. */
  protistranaKlic: string | null;
  /** `true` u organizací města. `null` = v datech to není. */
  mestska: boolean | null;
  osoby: { osoba_id: string | null; jmeno: string | null; role: string[] }[];
}

/* ─────────────────────────────  Čtení  ─────────────────────────────── */

const OBALY = ['firmy', 'subjekty', 'zaznamy', 'seznam', 'data', 'items', 'ekonomicke_subjekty'];

function firmaZe(z: Zaznam, poradi: number, puvod: string): Firma | null {
  const nazev = txt(z, 'nazev', 'název', 'obchodni_jmeno', 'obchodní_jméno', 'obchodniJmeno', 'name', 'firma');
  if (!nazev) return null;
  const ico = icoZ(z, 'ico', 'IČO', 'ICO', 'ic', 'ico_subjektu');

  return {
    ico,
    klic: ico ?? `n-${slug(nazev) || `${puvod}-${poradi + 1}`}`,
    nazev,
    vznik: isoDatum(z, 'vznik', 'datum_vzniku', 'datumVzniku', 'zapis', 'zalozeni', 'od', 'zahajeni_cinnosti'),
    zanik: isoDatum(z, 'zanik', 'zánik', 'datum_zaniku', 'datumZaniku', 'vymaz', 'do', 'ukonceni_cinnosti'),
    aktivni: ano(z, 'aktivni', 'aktivní', 'active', 'existuje', 'v_provozu'),
    obor: txt(z, 'obor', 'odvetvi', 'odvětví', 'cinnost', 'činnost', 'predmet_podnikani', 'kategorie', 'sekce'),
    nace: txt(z, 'nace', 'NACE', 'cz_nace', 'nace_kod', 'kod_nace'),
    pravniForma: txt(z, 'pravni_forma', 'právní_forma', 'pravniForma', 'forma', 'typ_subjektu'),
    sidlo: txt(z, 'sidlo', 'sídlo', 'adresa', 'address', 'ulice'),
    url: txt(z, 'url', 'odkaz', 'ares_url', 'link'),
  };
}

/** Všechny firmy z `data/firmy/`. Duplicitní IČO se slučují na první výskyt. */
export function nactiFirmy(): Nacteno<Firma[]> {
  const v = nactiAdresarSoubory<unknown>('firmy', ['.json']);
  const ven: Firma[] = [];
  const videne = new Set<string>();

  for (const s of v.data) {
    const obsah = s.data;
    let zaznamy: Zaznam[] = [];
    if (Array.isArray(obsah)) zaznamy = obsah.filter(jeObjekt);
    else if (jeObjekt(obsah)) {
      const vnorene = OBALY.map((k) => obsah[k]).find(Array.isArray);
      zaznamy = Array.isArray(vnorene) ? vnorene.filter(jeObjekt) : [obsah];
    }

    zaznamy.forEach((z, i) => {
      const f = firmaZe(z, i, s.jmeno);
      if (!f || videne.has(f.klic)) return;
      videne.add(f.klic);
      ven.push(f);
    });
  }

  ven.sort((a, b) => a.nazev.localeCompare(b.nazev, 'cs-CZ'));
  return { stav: v.stav, zdroj: v.zdroj, poznamka: v.poznamka, data: ven };
}

/* ────────────────────  Doplnění kontextu a kritérií  ───────────────── */

export interface Kontext {
  protistrany: Protistrana[];
  propojeni: PropojeniOsob;
  /** IČO organizací města z `config/subjekty.json`. */
  mestskaIca: Set<string>;
  kc: (v: number | null) => string;
  cislo: (v: number | null) => string;
}

/**
 * Přilepí k firmám to, co o nich víme odjinud, a spočítá kritéria důležitosti.
 * Kritéria jsou uzavřený seznam — nová se nevymýšlí a každé nese detail.
 */
export function sKontextem(firmy: Firma[], k: Kontext): FirmaSKontextem[] {
  const podleIca = new Map<string, Protistrana>();
  for (const p of k.protistrany) {
    if (!p.ico) continue;
    const stav = podleIca.get(p.ico);
    // Firma může být zároveň dodavatel i odběratel; pro odkaz stačí ta větší.
    if (!stav || (p.celkem_czk ?? 0) > (stav.celkem_czk ?? 0)) podleIca.set(p.ico, p);
  }
  const vydajePodleIca = new Map<string, Protistrana>();
  const prijmyPodleIca = new Map<string, Protistrana>();
  for (const p of k.protistrany) {
    if (!p.ico) continue;
    (p.smer === 'prijem' ? prijmyPodleIca : vydajePodleIca).set(p.ico, p);
  }

  const osobyUFirmy = new Map<string, { osoba_id: string | null; jmeno: string | null; role: string[] }[]>();
  const mestskeZPropojeni = new Set<string>();
  for (const o of k.propojeni.osoby ?? []) {
    for (const f of o.firmy ?? []) {
      if (!f.ico) continue;
      if (f.vztah === 'mestsky-subjekt') mestskeZPropojeni.add(f.ico);
      const seznam = osobyUFirmy.get(f.ico) ?? [];
      if (!seznam.some((x) => x.osoba_id === o.osoba_id)) {
        seznam.push({ osoba_id: o.osoba_id, jmeno: o.jmeno, role: f.role ?? [] });
      }
      osobyUFirmy.set(f.ico, seznam);
    }
  }

  return firmy.map((f) => {
    const ico = f.ico;
    const vydaj = ico ? (vydajePodleIca.get(ico) ?? null) : null;
    const prijem = ico ? (prijmyPodleIca.get(ico) ?? null) : null;
    const hlavni = ico ? (podleIca.get(ico) ?? null) : null;
    const osoby = ico ? (osobyUFirmy.get(ico) ?? []) : [];
    const mestska = ico ? (k.mestskaIca.has(ico) || mestskeZPropojeni.has(ico) ? true : null) : null;

    const duvody: Duvod[] = [];
    if (mestska === true) {
      duvody.push({
        klic: 'organizace-mesta',
        nazev: 'organizace města',
        detail: 'Vede ji nebo vlastní město — platby jí nejsou platby cizí firmě.',
      });
    }
    if (vydaj) {
      duvody.push({
        klic: 'dodavatel',
        nazev: 'dodavatel města',
        detail: `V registru smluv ${k.kc(vydaj.celkem_czk)} ve ${k.cislo(vydaj.smluv)} smlouvách, roky ${vydaj.prvni_rok}–${vydaj.posledni_rok}.`,
      });
    }
    if (prijem) {
      duvody.push({
        klic: 'odberatel',
        nazev: 'platí městu',
        detail: `Město od ní inkasovalo ${k.kc(prijem.celkem_czk)} ve ${k.cislo(prijem.smluv)} smlouvách.`,
      });
    }
    if (osoby.length > 0) {
      const jmena = osoby.map((o) => o.jmeno ?? o.osoba_id ?? 'neuvedeno').slice(0, 4).join(', ');
      duvody.push({
        klic: 'vazba-na-samospravu',
        nazev: 'je v ní uvedený někdo ze samosprávy',
        detail: `V rejstříku je u firmy uvedeno: ${jmena}${osoby.length > 4 ? ` a další (${osoby.length} celkem)` : ''}. Zápis ve firmě je veřejný údaj — sám o sobě z něj nic neplyne.`,
      });
    }

    return {
      ...f,
      duvody,
      odMesta: vydaj?.celkem_czk ?? null,
      mestu: prijem?.celkem_czk ?? null,
      smluv: hlavni?.smluv ?? null,
      prvniRok: hlavni?.prvni_rok ?? null,
      posledniRok: hlavni?.posledni_rok ?? null,
      protistranaKlic: hlavni?.klic ?? null,
      mestska,
      osoby,
    };
  });
}

/* ────────────────────────────  Přehledy  ───────────────────────────── */

/** Počty vzniků a zániků po letech. Rok bez události zůstává v ose jako nula. */
export function vznikyAZaniky(firmy: Firma[]): {
  roky: number[];
  vzniky: number[];
  zaniky: number[];
  bezData: { vznik: number; zanik: number };
} {
  const vzniky = new Map<number, number>();
  const zaniky = new Map<number, number>();
  let bezVzniku = 0;
  let bezZaniku = 0;

  for (const f of firmy) {
    const rv = rokZIso(f.vznik);
    if (rv === null) bezVzniku++;
    else vzniky.set(rv, (vzniky.get(rv) ?? 0) + 1);
    if (f.zanik) {
      const rz = rokZIso(f.zanik);
      if (rz === null) bezZaniku++;
      else zaniky.set(rz, (zaniky.get(rz) ?? 0) + 1);
    }
  }

  const vsechny = [...vzniky.keys(), ...zaniky.keys()];
  if (vsechny.length === 0) {
    return { roky: [], vzniky: [], zaniky: [], bezData: { vznik: bezVzniku, zanik: bezZaniku } };
  }
  const od = Math.min(...vsechny);
  const doo = Math.max(...vsechny);
  const roky: number[] = [];
  for (let r = od; r <= doo; r++) roky.push(r);

  return {
    roky,
    vzniky: roky.map((r) => vzniky.get(r) ?? 0),
    zaniky: roky.map((r) => zaniky.get(r) ?? 0),
    bezData: { vznik: bezVzniku, zanik: bezZaniku },
  };
}

/** Firmy podle oborů, od nejčetnějšího. Bez oboru se nezahazují. */
export function podleOboru(firmy: Firma[]): { nazev: string; pocet: number }[] {
  const m = new Map<string, number>();
  for (const f of firmy) {
    const o = f.obor ?? f.nace ?? 'obor v datech není';
    m.set(o, (m.get(o) ?? 0) + 1);
  }
  return [...m.entries()]
    .map(([nazev, pocet]) => ({ nazev, pocet }))
    .sort((a, b) => b.pocet - a.pocet || a.nazev.localeCompare(b.nazev, 'cs-CZ'));
}

/** Firmy, které jsou v `data/firmy/` a zároveň v registru smluv města. */
export function obchodujiciSMestem(firmy: FirmaSKontextem[]): FirmaSKontextem[] {
  return firmy.filter((f) => f.duvody.some((d) => d.klic === 'dodavatel' || d.klic === 'odberatel'));
}

/** Počet živých firem na konci každého roku — pro časovou osu vzniků a zániků. */
export function zivychNaKonciRoku(firmy: Firma[], roky: number[]): (number | null)[] {
  if (roky.length === 0) return [];
  // Firmy bez data vzniku by křivku posunuly; do počtu se nezapočítávají.
  const znameVzniky = firmy.filter((f) => rokZIso(f.vznik) !== null);
  return roky.map((r) => {
    let ziva = 0;
    for (const f of znameVzniky) {
      const rv = rokZIso(f.vznik) as number;
      if (rv > r) continue;
      const rz = rokZIso(f.zanik);
      if (rz !== null && rz <= r) continue;
      ziva++;
    }
    return ziva;
  });
}


/** Kolik firem má aspoň jedno kritérium důležitosti. */
export function dulezite(firmy: FirmaSKontextem[]): FirmaSKontextem[] {
  return firmy
    .filter((f) => f.duvody.length > 0)
    .sort(
      (a, b) =>
        (b.odMesta ?? 0) - (a.odMesta ?? 0) ||
        b.duvody.length - a.duvody.length ||
        a.nazev.localeCompare(b.nazev, 'cs-CZ'),
    );
}
