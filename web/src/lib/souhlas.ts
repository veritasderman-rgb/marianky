/*
 * Souhlas s cookies (GDPR / Google Consent Mode v2).
 *
 * Klíč v localStorage čte inline skript v <head> — ten nastaví výchozí stav
 * souhlasu ještě před načtením GA — i lišta `SouhlasSCookies`, která volbu
 * ukládá a promítne do gtag.
 */
export const KLIC_SOUHLASU = 'marianky.cookieConsent.v1';

export type Volba = 'granted' | 'denied';

/** Měřicí kód GA4. Bez proměnné prostředí se analytika vůbec nenačte. */
export const GA_ID = import.meta.env.PUBLIC_GA_ID ?? '';
