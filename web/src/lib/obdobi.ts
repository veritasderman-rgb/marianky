/**
 * Volební období samosprávy — pásma pro časové osy peněz.
 *
 * Čtenář se u peněz ptá „kdo byl u toho": smlouva z roku 2016 se podepisovala
 * za jiného vedení než smlouva z roku 2024. Pásma volebních období tu odpověď
 * kreslí přímo do osy let.
 *
 * Dvě zásady:
 *
 *   1. **Roky voleb jsou fakt, jména se berou z dat.** Komunální volby se
 *      konají v pevném čtyřletém cyklu — to je znalost o světě a smí být
 *      zapsaná tady. Kdo byl starostou, se ale čte z `lide/osobnosti.json`
 *      (funkce s rozsahem od–do); nic se nedomýšlí a kdyby data chyběla,
 *      pásmo nese jen roky bez jména.
 *   2. **Rok voleb patří končícímu období.** Komunální volby jsou na podzim,
 *      takže většinu roku voleb úřadovalo staré vedení — smlouvy toho roku
 *      jdou převážně za ním. Pásmo „2018–2022" proto pokrývá sloupce
 *      2019 až 2022. Tohle pravidlo musí stát i v textu u grafu, ne jen tady.
 */
import type { Osobnost } from './data';

/**
 * Roky komunálních voleb. Pevný čtyřletý cyklus od obnovení samosprávy;
 * seznam sahá schválně i před první rok dat (1994), aby nejstarší sloupce
 * nezůstaly bez pásma.
 */
const ROKY_VOLEB = [1990, 1994, 1998, 2002, 2006, 2010, 2014, 2018, 2022, 2026];

export interface StarostaObdobi {
  jmeno: string;
  prijmeni: string;
  strana: string | null;
  od: string | null;
  do: string | null;
  /** `true`, když v období jen pokračuje z minulého mandátu (nezačal v něm). */
  pokracuje: boolean;
}

export interface PasmoObdobi {
  /** První a poslední sloupec pásma PO oříznutí na osu grafu. */
  odRok: number;
  doRok: number;
  /** „2018–2022" — od voleb do voleb. */
  nazev: string;
  /** Krátký popisek do pásma: příjmení, při střídání „Franta → Třešňák". */
  starostove: string;
  detail: StarostaObdobi[];
}

function rokZ(s: string | null | undefined): number | null {
  const m = /^(\d{4})/.exec(String(s ?? ''));
  return m ? Number(m[1]) : null;
}

function prijmeni(jmeno: string): string {
  const casti = jmeno.trim().split(/\s+/);
  return casti[casti.length - 1] ?? jmeno;
}

interface Mandat {
  jmeno: string;
  strana: string | null;
  od: string | null;
  do: string | null;
  odRok: number;
}

/** Mandáty starostů od roku 1990, seřazené podle začátku. */
function mandatyStarostu(lide: Osobnost[]): Mandat[] {
  const ven: Mandat[] = [];
  for (const o of lide) {
    for (const f of o.funkce ?? []) {
      const nazev = (f.nazev ?? '').toLowerCase();
      // „starosta 2018 - 2022", „starostka…", „dočasný starosta…" — vždy na
      // začátku názvu funkce. Místostarosty pásmo nenese, bylo by přeplněné.
      if (!/^(dočasn[ýá] )?starost(a|ka)\b/.test(nazev)) continue;
      const odRok = rokZ(f.od);
      if (odRok === null || odRok < ROKY_VOLEB[0]) continue;
      ven.push({ jmeno: o.jmeno, strana: o.strana ?? null, od: f.od ?? null, do: f.do ?? null, odRok });
    }
  }
  return ven.sort((a, b) => String(a.od ?? '').localeCompare(String(b.od ?? '')));
}

/**
 * Pásma volebních období pro dané roky osy. Vrací jen pásma, která se s osou
 * protínají, oříznutá na její rozsah.
 */
export function volebniObdobi(roky: number[], lide: Osobnost[]): PasmoObdobi[] {
  if (roky.length === 0) return [];
  // Osa může běžet i od nejnovějšího roku doleva — rozsah se bere z min/max,
  // ne z krajních prvků pole.
  const prvni = Math.min(...roky);
  const posledni = Math.max(...roky);
  const mandaty = mandatyStarostu(lide);

  const ven: PasmoObdobi[] = [];
  for (let i = 0; i < ROKY_VOLEB.length - 1; i++) {
    const volby = ROKY_VOLEB[i];
    const dalsi = ROKY_VOLEB[i + 1];
    // Rok voleb patří končícímu období — pásmo běží od roku PO volbách
    // do roku dalších voleb včetně.
    const odRok = Math.max(volby + 1, prvni);
    const doRok = Math.min(dalsi, posledni);
    if (odRok > doRok) continue;

    // Starostové, kteří v tomhle mandátu nastoupili. Nástup v roce voleb se
    // počítá sem (volby jsou na podzim, nové vedení nastupuje hned po nich).
    const zacinajici = mandaty.filter((m) => m.odRok >= volby && m.odRok < dalsi);
    const detail: StarostaObdobi[] = zacinajici.map((m) => ({
      jmeno: m.jmeno,
      prijmeni: prijmeni(m.jmeno),
      strana: m.strana,
      od: m.od,
      do: m.do,
      pokracuje: false,
    }));
    if (detail.length === 0) {
      // Nikdo nový nenastoupil — pokračuje starosta z minulého mandátu
      // (Král vedl město 2006–2014, tedy dvě období po sobě).
      const drivejsi = mandaty.filter((m) => m.odRok < volby);
      const pokracujici = drivejsi[drivejsi.length - 1];
      if (pokracujici && (pokracujici.do === null || (rokZ(pokracujici.do) ?? 0) > volby)) {
        detail.push({
          jmeno: pokracujici.jmeno,
          prijmeni: prijmeni(pokracujici.jmeno),
          strana: pokracujici.strana,
          od: pokracujici.od,
          do: pokracujici.do,
          pokracuje: true,
        });
      }
    }

    ven.push({
      odRok,
      doRok,
      nazev: `${volby}–${dalsi}`,
      starostove: detail.map((d) => d.prijmeni).join(' → '),
      detail,
    });
  }
  return ven;
}

/**
 * Věta pod graf: „Volební období a starostové: 1994–1998 Luděk Nosek; …".
 * Strana se píše tam, kde ji data uvádějí — pásmo samo na jména nemá místo.
 */
export function popisObdobi(pasma: PasmoObdobi[]): string | null {
  const casti = pasma
    .filter((p) => p.detail.length > 0)
    .map((p) => {
      const jmena = p.detail
        .map((d) => `${d.jmeno}${d.strana ? ` (${d.strana})` : ''}${d.pokracuje ? ', pokračuje z minulého období' : ''}`)
        .join(', pak ');
      return `${p.nazev} ${jmena}`;
    });
  if (casti.length === 0) return null;
  return `Volební období a starostové: ${casti.join('; ')}.`;
}
