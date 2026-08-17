// @ts-check
import { defineConfig } from 'astro/config';

// Statický výstup pro Vercel. Žádný adaptér — build produkuje čisté HTML do dist/,
// které Vercel servíruje jako statické soubory.
export default defineConfig({
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
