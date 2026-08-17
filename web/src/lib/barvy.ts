/**
 * Přidělování barev grafů.
 *
 * Závazné pravidlo z web/DESIGN.md §2:
 *   „Barva patří subjektu, ne pořadí." — přiřazuj podle IČO, ne podle indexu v poli.
 *   Sedmá a další firma se neobarvuje novou barvou, spadne do „Ostatní".
 *
 * Proto se registr sestaví JEDNOU nad celou množinou dat a pak se jen dotazuje.
 * Když uživatel filtruje (legenda, přepínač), barvy zbylých firem se nemění,
 * protože se nikde nepřepočítávají z indexu.
 *
 * Konkrétní hodnoty barev tu nejsou — jsou to CSS tokeny (--g1…--g6, --g-ost),
 * aby se světlý a tmavý režim přepnul bez druhého renderu SVG.
 */

export const MAX_KATEGORII = 6;

/** Slot 0–5 = barevná kategorie, `null` = „Ostatní". */
export type Slot = number | null;

export interface RegistrBarev {
  /** IČO → slot 0–5. Kdo tu není, je „Ostatní". */
  sloty: Map<string, number>;
  slot(ico: string): Slot;
  barva(ico: string): string;
}

export function cssBarvaSlotu(slot: Slot): string {
  if (slot === null || slot < 0 || slot >= MAX_KATEGORII) return 'var(--g-ost)';
  return `var(--g${slot + 1})`;
}

/**
 * Sestaví registr z pořadí podle objemu. Pořadí barev je podle DESIGN.md
 * bezpečnostní mechanismus (odstup při barvosleposti klesá s pořadím),
 * proto se přiděluje od nejsilnějšího subjektu dolů.
 */
export function sestavRegistr(seznam: { ico: string; celkem_czk: number }[]): RegistrBarev {
  const serazene = [...seznam]
    .filter((p) => p && typeof p.ico === 'string')
    .sort((a, b) => (b.celkem_czk ?? 0) - (a.celkem_czk ?? 0));

  const sloty = new Map<string, number>();
  for (const p of serazene.slice(0, MAX_KATEGORII)) {
    if (!sloty.has(p.ico)) sloty.set(p.ico, sloty.size);
  }

  return {
    sloty,
    slot(ico: string) {
      const s = sloty.get(ico);
      return s === undefined ? null : s;
    },
    barva(ico: string) {
      return cssBarvaSlotu(this.slot(ico));
    },
  };
}

/** Sekvenční ramp z DESIGN.md §2 — 8 kroků, málo → hodně. Tokeny --r1…--r8. */
export const KROKU_RAMPY = 8;

export function cssKrokRampy(i: number): string {
  const k = Math.min(KROKU_RAMPY - 1, Math.max(0, i));
  return `var(--r${k + 1})`;
}

/**
 * Zařadí kladnou hodnotu do kroku rampy. Logaritmicky — částky se u smluv
 * liší o řády a lineární škála by sloučila skoro všechno do prvního kroku.
 *
 * POZOR: nula sem nepatří. Rok bez peněz NENÍ krok 0 rampy, ale prázdná buňka
 * v barvě povrchu (DESIGN.md §3.3). Volající to musí ošetřit dřív.
 */
export function krokRampy(hodnota: number, min: number, max: number): number {
  if (!(hodnota > 0)) return 0;
  if (!(max > min)) return Math.floor(KROKU_RAMPY / 2);
  const t = (Math.log(hodnota) - Math.log(min)) / (Math.log(max) - Math.log(min));
  return Math.min(KROKU_RAMPY - 1, Math.max(0, Math.round(t * (KROKU_RAMPY - 1))));
}

/**
 * Stavová barva (K-index apod.). Vždy se doplňuje textovým popiskem — barva
 * sama význam nenese (web/DESIGN.md §3.4).
 *
 * Úrovně jsou jen čtyři, protože DESIGN.md stavovou paletu nedefinuje a
 * vymýšlet novou barvu (např. červenou pro „kritické") by znamenalo přidat
 * neověřený odstín. K-index A–F se proto mapuje do těchto čtyř.
 */
export type StavovaUroven = 'dobre' | 'pozor' | 'vazne' | 'neznamo';

export function cssStav(u: StavovaUroven): string {
  return `var(--stav-${u})`;
}
