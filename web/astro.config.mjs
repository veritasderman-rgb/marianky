// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

// Statický výstup pro Vercel. Žádný adaptér — build produkuje čisté HTML do dist/,
// které Vercel servíruje jako statické soubory.
export default defineConfig({
  // Veřejná adresa. Potřebná pro sitemap a pro absolutní odkazy v náhledech
  // při sdílení — bez ní by se generovaly relativní a náhled by nefungoval.
  site: 'https://marianky.vercel.app',
  integrations: [sitemap()],
  output: 'static',
  trailingSlash: 'ignore',
  build: {
    format: 'directory',
  },
  devToolbar: {
    enabled: false,
  },
  compressHTML: true,
});
