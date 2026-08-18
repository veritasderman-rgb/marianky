/**
 * Jedna položka hlasování — společná definice pro server i prohlížeč.
 *
 * PROČ TO JE TADY A NE JEN V .ASTRO KOMPONENTĚ
 * Stránka /hlasovani vypisovala všech 12 349 hlasování rovnou do HTML.
 * Vyšlo z toho 14,9 MB a 250 289 DOM uzlů; telefon se na tom zasekl dřív,
 * než se stihlo něco vykreslit. Po drátě přitom šlo jen 1,2 MB — brotli
 * text zmenší, ale prohlížeč z něj stejně musí postavit čtvrt milionu
 * elementů, a to je ta drahá část.
 *
 * Seznam se proto vykresluje po částech: server vysází první stránku,
 * zbytek leží v datovém ostrůvku jako JSON a prohlížeč z něj skládá další
 * položky, až když jsou potřeba. Aby se serverová a klientská verze
 * nerozešly, staví obě tahle jediná funkce.
 *
 * ESCAPOVÁNÍ: názvy bodů, jména a názvy firem jsou cizí data z portálu
 * města. Do HTML jdou výhradně přes `esc()`. Kdo sem přidá další pole,
 * musí ho protáhnout taky — jinak stačí jeden název s `<` a stránka se
 * rozbije, nebo hůř.
 */
import { kc, nazevHlasu, nazevVysledku, nazevOrganu, datumKratke, bezDiakritiky } from './format';
import { tridaVysledku } from './prehledy';
import type { PolozkaHlasovani } from './prehledy';
/* Jen typ — `import type` se při překladu zahodí, takže se do prohlížeče
   nedostane nic z `vazby.ts`, které čte soubory z disku. */
import type { VazbaHlasovani } from './vazby';
import { popisVztahu } from './vztahy';

/* ─────────────────────────────  Záznam  ─────────────────────────────── */

/**
 * Co o jednom hlasování potřebuje seznam. Schválně jen tohle — každé pole
 * navíc se v ostrůvku násobí dvanácti tisíci.
 *
 * Jmenovité hlasy tu NEJSOU. Ty mají vlastní ostrůvek (JmenoviteData.astro)
 * a skládají se až při rozbalení; je jich 121 935 a v seznamu je nikdo
 * nečte najednou.
 */
export interface ZaznamHlasovani {
  id: string;
  organ: string;
  rok: number | null;
  datum: string;
  bod: string;
  nazev: string;
  tagy: string[];
  vysledek: string;
  pro: number;
  proti: number;
  zdrzel: number;
  nehlasoval: number;
  /** Kolik jmenovitých hlasů k tomuhle bodu je. Nula = rozpis se nekreslí. */
  jmenovitych: number;
  vazby: VazbaHlasovani[];
  /** IČO protistran, na které vede stránka `/penize/[ico]`. */
  seStrankou: string[];
}

export function zaznamZPolozky(
  h: PolozkaHlasovani,
  vazby: VazbaHlasovani[],
  zname: Set<string> | undefined,
): ZaznamHlasovani {
  return {
    id: h.id,
    organ: h.organ,
    rok: h.rok,
    datum: h.datum,
    bod: h.bod,
    nazev: h.nazev,
    tagy: h.tagy,
    vysledek: h.vysledek,
    pro: h.pro,
    proti: h.proti,
    zdrzel: h.zdrzel,
    nehlasoval: h.nehlasoval,
    jmenovitych: h.jmenovite.length,
    vazby,
    seStrankou: vazby
      .map((v) => v.ico)
      .filter((i): i is string => Boolean(i && zname?.has(i))),
  };
}

/* ──────────────────────────  Escapování  ───────────────────────────── */

export function esc(s: unknown): string {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/* ────────────────────────────  Kreslení  ───────────────────────────── */

const POPIS_OVERENI: Record<string, string> = {
  potvrzeno: 'identita potvrzena',
  pravdepodobne: 'identita jen pravděpodobná',
  nejednoznacne: 'identita nejednoznačná',
  nenalezeno: 'identita nedohledána',
};

function vazbyHtml(z: ZaznamHlasovani): string {
  if (!z.vazby.length) return '';
  const seStrankou = new Set(z.seStrankou);

  const radky = z.vazby
    .map((v) => {
      const osoba = v.osoba_id
        ? `<a href="/lide/${esc(v.osoba_id)}">${esc(v.jmeno ?? v.osoba_id)}</a>`
        : esc(v.jmeno ?? 'neuvedena');
      const overeni =
        v.overeni && v.overeni !== 'potvrzeno'
          ? `<br><span class="stav-dat__zdroj">${esc(POPIS_OVERENI[v.overeni] ?? v.overeni)}</span>`
          : '';
      const firma =
        v.ico && seStrankou.has(v.ico)
          ? `<a href="/penize/${esc(v.ico)}">${esc(v.firma ?? v.ico)}</a>`
          : esc(v.firma ?? v.ico ?? 'neuvedena');
      const ico = v.ico ? `<br><span class="mono">${esc(v.ico)}</span>` : '';
      return (
        `<tr><td>${osoba}${overeni}</td>` +
        `<td>${esc(v.hlas ? nazevHlasu(v.hlas) : 'v datech není')}</td>` +
        `<td>${firma}${ico}</td>` +
        `<td>${esc(popisVztahu(v.vztah))}</td>` +
        `<td>${esc(v.role.length > 0 ? v.role.join(', ') : 'v datech není')}</td>` +
        `<td class="cislo">${esc(v.od_mesta_czk === null ? 'v datech není' : kc(v.od_mesta_czk))}</td></tr>`
      );
    })
    .join('');

  const shrnuti =
    z.vazby.length === 1
      ? 'Jeden z hlasujících je ve firmě, které se bod týká, veden jako angažovaný'
      : `Hlasujících s uvedenou vazbou na dotčenou firmu: ${z.vazby.length}`;

  return (
    `<details class="vazby"><summary>` +
    `<span class="znacka znacka--vazba">vazba na dotčenou firmu</span>` +
    `<span>${esc(shrnuti)}</span></summary>` +
    `<p class="vazby__popis">Věcný výpis ze zdrojů: kdo hlasoval, jak hlasoval, v jaké roli je ve ` +
    `firmě uveden a kolik firma od města a jeho organizací dostala. Přehled z toho nevyvozuje žádný ` +
    `závěr a nehodnotí, jestli měl někdo hlasovat jinak. Řada dotčených firem jsou organizace ` +
    `samotného města.</p>` +
    `<div class="tabulka-obal"><table><thead><tr>` +
    `<th scope="col">Osoba</th><th scope="col">Hlas</th><th scope="col">Firma</th>` +
    `<th scope="col">Vztah firmy k městu</th><th scope="col">Role ve firmě</th>` +
    `<th scope="col" class="cislo">Od města celkem</th>` +
    `</tr></thead><tbody>${radky}</tbody></table></div></details>`
  );
}

/** Text, ve kterém hledá filtr. Bez diakritiky, ať „usneseni" najde „usnesení". */
export function hledatText(z: ZaznamHlasovani, nazvyTagu: Record<string, string>): string {
  const tagy = z.tagy.map((t) => nazvyTagu[t] ?? t).join(' ');
  return bezDiakritiky(`${z.nazev} ${z.bod} ${tagy} ${nazevOrganu(z.organ)}`);
}

/**
 * Jedna položka seznamu jako HTML.
 *
 * Rozpis jmenovitých hlasů se vykreslí jako prázdný `<details>` — obsah do
 * něj doplní až skript v layoutu z ostrůvku, když ho někdo otevře.
 */
export function polozkaHtml(z: ZaznamHlasovani, nazvyTagu: Record<string, string>): string {
  const znacky = z.tagy.length
    ? `<span class="znacky">${z.tagy
        .map((t) => {
          const nazev = nazvyTagu[t] ?? t;
          return `<a class="znacka" href="/temata/${esc(t)}" data-pagefind-filter="téma:${esc(nazev)}">${esc(nazev)}</a>`;
        })
        .join('')}</span>`
    : '';

  const nehlasoval = z.nehlasoval > 0 ? `<span>nehlasovalo ${z.nehlasoval}</span>` : '';

  const rozpis = z.jmenovitych
    ? `<details class="tabulkovy-pohled" data-jmenovite="${esc(z.id)}">` +
      `<summary>Jmenovité hlasování (${z.jmenovitych})</summary>` +
      `<div class="mrizka-2" data-jmenovite-obsah></div></details>`
    : '';

  return (
    `<li class="polozka" data-hlasovani data-tagy="${esc(z.tagy.join(' '))}" ` +
    `data-organ="${esc(z.organ)}" data-rok="${esc(z.rok ?? '')}" ` +
    `data-vysledek="${esc(z.vysledek)}" data-hledat="${esc(hledatText(z, nazvyTagu))}"` +
    (z.vazby.length ? ' data-vazba="1"' : '') +
    `>` +
    `<div class="polozka__hlava"><span>${esc(nazevOrganu(z.organ))}</span>` +
    `<span>${esc(datumKratke(z.datum))}</span>` +
    `<span class="mono">bod ${esc(z.bod)}</span></div>` +
    `<h3 class="polozka__nazev">${esc(z.nazev)}</h3>` +
    `<div class="polozka__meta">` +
    `<span class="vysledek vysledek--${esc(tridaVysledku(z.vysledek))}">` +
    `<span class="vysledek__tecka" aria-hidden="true"></span>${esc(nazevVysledku(z.vysledek))}</span>` +
    `<span class="rozdeleni-hlasu"><span>pro ${z.pro}</span><span>proti ${z.proti}</span>` +
    `<span>zdrželo se ${z.zdrzel}</span>${nehlasoval}</span>` +
    `${znacky}</div>` +
    `${vazbyHtml(z)}${rozpis}</li>`
  );
}
