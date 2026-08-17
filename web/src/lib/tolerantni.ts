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

/** Uklidí IČO na osm číslic. `null`, když to IČO zjevně není. */
export function ico(o: Zaznam | null | undefined, ...klice: string[]): string | null {
  const s = txt(o, ...klice);
  if (!s) return null;
  const cisty = s.replace(/\D/g, '');
  if (cisty.length === 0 || cisty.length > 8) return null;
  return cisty.padStart(8, '0');
}
