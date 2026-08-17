/**
 * Tolerantní čtení dat z modulů, které se teprve dopisují.
 *
 * Volby, ČSÚ, památky, geometrie, firmy a historie vznikají v jiných modulech
 * a jejich přesný tvar zatím nikde není zapsaný. Web je proto čte přes tyhle
 * pomocníky: u každého údaje zkouší několik obvyklých názvů klíče a přijímá
 * jak holé pole, tak objekt s obalovým klíčem.
 *
 * Dvě pravidla, která se tu drží tvrdě:
 *
 *   1. `null` znamená „v datech to není", NIKDY nulu. Rozdíl se propisuje až
 *      do textu na stránce („v datech není" vs. „nula").
 *   2. Nic se nedohaduje. Když se údaj nedá přečíst, vrátí se `null` a stránka
 *      to napíše — místo aby si dopočítala číslo, které v datech nestojí.
 *
 * Stejný přístup už používá `lib/vazby.ts` pro propojení; tenhle soubor je
 * jeho zobecněná podoba pro nové zdroje.
 */

export type Zaznam = Record<string, unknown>;

export function jeObjekt(v: unknown): v is Zaznam {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** První neprázdný textový údaj z uvedených klíčů. */
export function txt(o: Zaznam | null | undefined, ...klice: string[]): string | null {
  if (!o) return null;
  for (const k of klice) {
    const v = o[k];
    if (typeof v === 'string' && v.trim()) return v.trim();
    if (typeof v === 'number' && Number.isFinite(v)) return String(v);
  }
  return null;
}

/**
 * První číselný údaj z uvedených klíčů. Zvládne i číslo zapsané jako text
 * s mezerami nebo desetinnou čárkou — tak je píšou české otevřené datové sady.
 */
export function cis(o: Zaznam | null | undefined, ...klice: string[]): number | null {
  if (!o) return null;
  for (const k of klice) {
    const v = o[k];
    if (typeof v === 'number' && Number.isFinite(v)) return v;
    if (typeof v === 'string') {
      const cisty = v.replace(/[\s  ]/g, '').replace(',', '.');
      if (/^-?\d+(\.\d+)?$/.test(cisty)) return Number(cisty);
    }
  }
  return null;
}

/** `true` / `false` / `null`, když se o tom v datech nic nepíše. */
export function ano(o: Zaznam | null | undefined, ...klice: string[]): boolean | null {
  if (!o) return null;
  for (const k of klice) {
    const v = o[k];
    if (typeof v === 'boolean') return v;
    if (typeof v === 'number' && (v === 0 || v === 1)) return v === 1;
    if (typeof v === 'string') {
      const s = v.trim().toLowerCase();
      if (s === 'ano' || s === 'true' || s === 'yes' || s === '1') return true;
      if (s === 'ne' || s === 'false' || s === 'no' || s === '0') return false;
    }
  }
  return null;
}

/** Podíl vždy v rozsahu 0–1. Zdroj může psát procenta („62,3") i zlomek („0,623"). */
export function podil(o: Zaznam | null | undefined, ...klice: string[]): number | null {
  const v = cis(o, ...klice);
  if (v === null || v < 0) return null;
  if (v <= 1) return v;
  if (v <= 100) return v / 100;
  return null;
}

/** Seznam objektů z uvedených klíčů. */
export function objekty(o: Zaznam | null | undefined, ...klice: string[]): Zaznam[] {
  if (!o) return [];
  for (const k of klice) {
    const v = o[k];
    if (Array.isArray(v)) return v.filter(jeObjekt);
  }
  return [];
}

/** Seznam řetězců z uvedených klíčů. Přijme i jediný řetězec místo pole. */
export function texty(o: Zaznam | null | undefined, ...klice: string[]): string[] {
  if (!o) return [];
  for (const k of klice) {
    const v = o[k];
    if (Array.isArray(v)) {
      const ven = v
        .map((x) => (typeof x === 'string' ? x.trim() : jeObjekt(x) ? txt(x, 'id', 'nazev', 'jmeno') : null))
        .filter((x): x is string => Boolean(x));
      if (ven.length > 0) return ven;
    }
    if (typeof v === 'string' && v.trim()) return [v.trim()];
  }
  return [];
}

/**
 * Vytáhne pole záznamů ze souboru, který může být buď holé pole, nebo objekt
 * s obalovým klíčem (`{ "okrsky": [...] }`). Když nic nesedí, vrátí prázdno.
 */
export function poleZaznamu(v: unknown, ...klice: string[]): Zaznam[] {
  if (Array.isArray(v)) return v.filter(jeObjekt);
  if (!jeObjekt(v)) return [];
  const primy = objekty(v, ...klice);
  if (primy.length > 0) return primy;
  // Objekt jako slovník `{ "2019": {...}, "2020": {...} }` — klíč se přidá jako `klic`.
  const hodnoty = Object.entries(v).filter(([, x]) => jeObjekt(x));
  if (hodnoty.length > 0 && klice.length === 0) {
    return hodnoty.map(([k, x]) => ({ klic: k, ...(x as Zaznam) }));
  }
  return [];
}

/**
 * Mapa `rok → hodnota` z několika obvyklých tvarů:
 *   { "2019": 13560, "2020": 13480 }
 *   [ { "rok": 2019, "hodnota": 13560 }, … ]
 *   { "hodnoty": [ … ] }
 * Nečíselné hodnoty se zahazují — dohadovat se nic nebude.
 */
export function radaPoLetech(v: unknown, klicHodnoty: string[] = ['hodnota', 'value', 'pocet', 'castka_czk', 'castka']): Map<number, number> {
  const ven = new Map<number, number>();
  const pridej = (r: unknown, h: unknown) => {
    const rok = typeof r === 'number' ? r : typeof r === 'string' ? Number(r.trim().slice(0, 4)) : NaN;
    const hod = typeof h === 'number' ? h : typeof h === 'string' ? cis({ x: h }, 'x') : null;
    if (Number.isFinite(rok) && rok > 1000 && rok < 3000 && hod !== null && Number.isFinite(hod)) {
      ven.set(rok, hod);
    }
  };

  if (Array.isArray(v)) {
    for (const p of v) {
      if (!jeObjekt(p)) continue;
      const r = cis(p, 'rok', 'year', 'obdobi', 'period');
      const h = cis(p, ...klicHodnoty);
      if (r !== null && h !== null) pridej(r, h);
    }
    return ven;
  }
  if (jeObjekt(v)) {
    for (const [k, h] of Object.entries(v)) pridej(k, h);
  }
  return ven;
}

const MESICE_TEXTEM: Record<string, number> = {
  ledna: 1, leden: 1, unora: 2, 'února': 2, unor: 2, 'únor': 2, brezna: 3, 'března': 3,
  dubna: 4, duben: 4, kvetna: 5, 'května': 5, cervna: 6, 'června': 6, cervence: 7, 'července': 7,
  srpna: 8, srpen: 8, zari: 9, 'září': 9, rijna: 10, 'října': 10, listopadu: 11, listopad: 11,
  prosince: 12, prosinec: 12,
};

/**
 * Normalizuje datum na ISO. Vrací `YYYY-MM-DD`, `YYYY-MM` nebo `YYYY` podle
 * toho, co zdroj skutečně uvádí — přesnost se NEDOPLŇUJE. „Rok 1865" nesmí
 * na časové ose vypadat jako „1. ledna 1865".
 */
export function isoDatum(o: Zaznam | null | undefined, ...klice: string[]): string | null {
  if (!o) return null;
  for (const k of klice) {
    const v = o[k];
    const s = typeof v === 'number' ? String(v) : typeof v === 'string' ? v.trim() : '';
    if (!s) continue;
    const norm = normalizujDatum(s);
    if (norm) return norm;
  }
  return null;
}

export function normalizujDatum(s: string): string | null {
  const t = s.trim();
  if (!t) return null;

  let m = /^(\d{4})-(\d{1,2})-(\d{1,2})/.exec(t);
  if (m) return `${m[1]}-${dvojc(m[2])}-${dvojc(m[3])}`;

  m = /^(\d{4})-(\d{1,2})$/.exec(t);
  if (m) return `${m[1]}-${dvojc(m[2])}`;

  m = /^(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})$/.exec(t);
  if (m) return `${m[3]}-${dvojc(m[2])}-${dvojc(m[1])}`;

  m = /^(\d{1,2})\.\s*([a-zá-ž]+)\s+(\d{4})$/i.exec(t);
  if (m) {
    const mes = MESICE_TEXTEM[m[2].toLowerCase()];
    if (mes) return `${m[3]}-${dvojc(String(mes))}-${dvojc(m[1])}`;
  }

  m = /^(\d{1,2})\.\s*(\d{4})$/.exec(t);
  if (m) return `${m[2]}-${dvojc(m[1])}`;

  m = /^(-?\d{3,4})$/.exec(t);
  if (m) {
    const r = Number(m[1]);
    if (r > -3000 && r < 3000) return m[1];
  }
  return null;
}

function dvojc(s: string): string {
  return s.padStart(2, '0');
}

/** Rok z čísla, roku v textu nebo z ISO data. `null`, když se nedá určit. */
export function rokZ(o: Zaznam | null | undefined, ...klice: string[]): number | null {
  if (!o) return null;
  for (const k of klice) {
    const v = o[k];
    if (typeof v === 'number' && Number.isFinite(v) && v > 1000 && v < 3000) return Math.trunc(v);
    if (typeof v === 'string') {
      const m = /(-?\d{3,4})/.exec(v.trim());
      if (m) {
        const r = Number(m[1]);
        if (r > -3000 && r < 3000) return r;
      }
    }
  }
  return null;
}

/** Rok z normalizovaného ISO data (i z holého „1865"). */
export function rokZIso(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const m = /^(-?\d{3,4})/.exec(iso);
  if (!m) return null;
  const r = Number(m[1]);
  return Number.isFinite(r) ? r : null;
}

/**
 * Podíl roku 0–1 podle měsíce a dne. Když zdroj uvádí jen rok, vrací se 0.5 —
 * značka sedí doprostřed roku, ne na 1. ledna, aby nepředstírala přesnost.
 */
export function pozicevRoce(iso: string | null | undefined): number {
  if (!iso) return 0.5;
  const m = /^-?\d{3,4}-(\d{2})(?:-(\d{2}))?/.exec(iso);
  if (!m) return 0.5;
  const mesic = Number(m[1]);
  const den = m[2] ? Number(m[2]) : null;
  if (!Number.isFinite(mesic) || mesic < 1 || mesic > 12) return 0.5;
  const zaklad = (mesic - 1) / 12;
  return den && den >= 1 && den <= 31 ? zaklad + ((den - 1) / 31) * (1 / 12) : zaklad + 1 / 24;
}

/** Uklidí IČO na osm číslic. `null`, když to IČO zjevně není. */
export function ico(o: Zaznam | null | undefined, ...klice: string[]): string | null {
  const s = txt(o, ...klice);
  if (!s) return null;
  const cisty = s.replace(/\D/g, '');
  if (cisty.length === 0 || cisty.length > 8) return null;
  return cisty.padStart(8, '0');
}
