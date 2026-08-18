/**
 * Rejstřík sekcí webu — jediné místo, kde je napsané, co web obsahuje.
 *
 * Dřív žil seznam přímo v `layouts/Zaklad.astro`. Když k navigaci přibyl
 * grafický rozcestník, měly by ho dvě kopie a rozešly by se: sekce přidaná
 * do nabídky by na rozcestníku chyběla. Proto je tu.
 *
 * ADRESY SE NEMĚNÍ. Mění se jen to, co je na nich napsané — odkazy, které
 * někdo poslal dál, musí zůstat platné.
 */

export interface Sekce {
  /** Klíč sekce. Shodný s klíčem znaku v `data/znaky/sekce.json`. */
  klic: string;
  cesta: string;
  nazev: string;
  /** Krátký název pro dlaždici na telefonu, kde se dlouhý nevejde. */
  kratce?: string;
  /** Jednou větou, co za odkazem je. */
  popis: string;
}

export interface SkupinaSekci {
  nazev: string;
  sekce: Sekce[];
}

export const SEKCE_UVOD: Sekce = {
  klic: 'vydani',
  cesta: '/',
  nazev: 'Týdenní přehled',
  kratce: 'Přehled',
  popis: 'Co se ve městě stalo za poslední týden',
};

export const SEKCE_HLEDAT: Sekce = {
  klic: 'hledat',
  cesta: '/hledat',
  nazev: 'Hledat',
  popis: 'Fulltext ve všech sebraných záznamech',
};

export const SKUPINY: SkupinaSekci[] = [
  {
    nazev: 'Radnice',
    sekce: [
      {
        klic: 'usneseni',
        cesta: '/usneseni',
        nazev: 'Usnesení',
        popis: 'Co rada a zastupitelstvo schválily',
      },
      {
        klic: 'hlasovani',
        cesta: '/hlasovani',
        nazev: 'Hlasování',
        popis: 'Kdo jak hlasoval',
      },
    ],
  },
  {
    nazev: 'Peníze',
    sekce: [
      {
        klic: 'penize',
        cesta: '/penize',
        nazev: 'Peníze města',
        popis: 'Komu město platí a kolik',
      },
      {
        klic: 'retez',
        cesta: '/retez',
        nazev: 'Od usnesení k penězům',
        kratce: 'Od usnesení k penězům',
        popis: 'Co se schválilo, co se podepsalo, co se zaplatilo',
      },
    ],
  },
  {
    nazev: 'Lidé a firmy',
    sekce: [
      {
        klic: 'lide',
        cesta: '/lide',
        nazev: 'Lidé',
        popis: 'Kdo ve městě rozhoduje',
      },
      {
        klic: 'firmy',
        cesta: '/firmy',
        nazev: 'Firmy',
        popis: 'Firmy ve městě podle rejstříku',
      },
      {
        klic: 'propojeni',
        cesta: '/propojeni',
        nazev: 'Kdo sedí v jakých firmách',
        kratce: 'Propojení',
        popis: 'Vazby samosprávy na firmy',
      },
    ],
  },
  {
    nazev: 'Město',
    sekce: [
      {
        klic: 'volby',
        cesta: '/volby',
        nazev: 'Volby',
        popis: 'Výsledky a účast po okrscích',
      },
      {
        klic: 'mapa',
        cesta: '/mapa',
        nazev: 'Mapa',
        popis: 'Památky, prameny a další vrstvy',
      },
      {
        klic: 'statistika',
        cesta: '/statistika',
        nazev: 'Čísla o městě',
        kratce: 'Čísla',
        popis: 'Obyvatelé, práce, cestovní ruch',
      },
    ],
  },
  {
    nazev: 'Archiv',
    sekce: [
      {
        klic: 'zpravodaj',
        cesta: '/zpravodaj',
        nazev: 'Zpravodaj',
        popis: 'Archiv čísel a článků',
      },
      {
        klic: 'historie',
        cesta: '/historie',
        nazev: 'Historie města',
        kratce: 'Historie',
        popis: 'Dějiny po obdobích',
      },
    ],
  },
];

/** Všechny sekce v pořadí, ve kterém patří na rozcestník. */
export const VSECHNY_SEKCE: Sekce[] = [
  SEKCE_UVOD,
  ...SKUPINY.flatMap((s) => s.sekce),
  SEKCE_HLEDAT,
];

/** Ve které skupině leží otevřená stránka — ta se v nabídce označí. */
export function skupinaSekce(klic: string | undefined): string | undefined {
  if (!klic) return undefined;
  return SKUPINY.find((s) => s.sekce.some((o) => o.klic === klic))?.nazev;
}
