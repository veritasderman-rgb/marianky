/**
 * Loadery pro Slibník a Účet volebního období.
 *
 * Obojí počítá pipeline (`pipeline/slibnik.py`, `pipeline/ucet_obdobi.py`)
 * z textů usnesení a jmenovitých hlasování — tady se jen čte a typuje.
 *
 * Dvě věci, které si každý odběratel musí odnést z metodik v datech:
 *
 *   1. **Slibník netvrdí „nesplněno".** Kontrola plnění usnesení je vždy
 *      jen v příloze, kterou město nezveřejňuje — `termin_uplynul` znamená
 *      jen „termín je pryč a veřejná stopa o výsledku neexistuje".
 *   2. **Zdroj zveřejňuje jen SCHVÁLENÁ hlasování.** „Klíčová hlasování"
 *      v účtu období jsou nejtěsněji schválená, ne nejspornější vůbec.
 */
import { nactiJson, type Nacteno } from './data';

/* ─────────────────────────────  Slibník  ────────────────────────────── */

export interface NavazujiciUsneseni {
  datum: string | null;
  organ: string | null;
  cislo_usneseni: string | null;
  nazev: string | null;
  url: string | null;
}

export interface Ukol {
  organ: string | null;
  datum_ulozeni: string | null;
  cislo_bodu: string | null;
  cislo_usneseni: string | null;
  nazev: string | null;
  url: string | null;
  tagy: string[];
  adresat: string | null;
  adresat_typ: string;
  termin: string | null;
  termin_text: string | null;
  stav: 'bezi' | 'termin_uplynul' | 'bez_terminu' | string;
  citace: string;
  navazujici: NavazujiciUsneseni[];
}

export interface Slibnik {
  hodnoceno_k?: string;
  metodika?: string[];
  souhrn: {
    ukolu: number;
    s_terminem: number;
    bezi: number;
    termin_uplynul: number;
    bez_terminu: number;
    s_navaznosti: number;
    po_letech: Record<string, number>;
    podle_adresata: Record<string, number>;
  };
  ukoly: Ukol[];
}

export function nactiSlibnik(): Nacteno<Slibnik> {
  return nactiJson<Slibnik>('slibnik/ukoly.json', {
    souhrn: {
      ukolu: 0, s_terminem: 0, bezi: 0, termin_uplynul: 0,
      bez_terminu: 0, s_navaznosti: 0, po_letech: {}, podle_adresata: {},
    },
    ukoly: [],
  });
}

/* ──────────────────────  Účet volebního období  ─────────────────────── */

export interface KlicoveHlasovani {
  id: string | null;
  datum: string | null;
  nazev: string | null;
  tagy: string[];
  pro: number | null;
  proti: number | null;
  zdrzel: number | null;
  nepritomen: number | null;
  castka_czk: number | null;
  url: string | null;
  /** {klub: {pro/proti/zdrzel: počet}} — jen věcné hlasy. */
  kluby: Record<string, Record<string, number>>;
}

export interface ZastupitelUctu {
  osoba_id: string;
  jmeno: string | null;
  strana: string;
  zmena_strany: boolean;
  hlasovani: number;
  pritomen: number;
  ucast_pct: number | null;
  klub_delene: number;
  s_klubem: number;
  /** `null` = míň než 10 dělených hlasování, procento by bylo šum. */
  s_klubem_pct: number | null;
}

export interface KlubUctu {
  strana: string;
  clenove: number;
  soudrznost_pct: number | null;
  delenych_hlasu: number;
}

export interface UcetObdobi {
  obdobi?: {
    volby: string;
    od: string;
    do: string | null;
    prvni_jednani: string | null;
    posledni_jednani: string | null;
  };
  metodika?: string[];
  souhrn: {
    jednani: number;
    hlasovani: number;
    ne_zcela_jednomyslnych: number;
    s_protihlasy_3plus: number;
    zastupitelu: number;
    po_letech?: Record<string, { hlasovani: number; ne_zcela_jednomyslnych: number }>;
  };
  klicova_hlasovani: KlicoveHlasovani[];
  zastupitele: ZastupitelUctu[];
  kluby: KlubUctu[];
}

export function nactiUcetObdobi(): Nacteno<UcetObdobi> {
  return nactiJson<UcetObdobi>('obdobi/ucet.json', {
    souhrn: {
      jednani: 0, hlasovani: 0, ne_zcela_jednomyslnych: 0,
      s_protihlasy_3plus: 0, zastupitelu: 0,
    },
    klicova_hlasovani: [],
    zastupitele: [],
    kluby: [],
  });
}
