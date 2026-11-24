import { defineConfig } from 'vite';
import { readFileSync } from 'node:fs';

const { version } = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8'));

export default defineConfig({
  // Relative asset URLs, so the site works from any GitHub Pages sub-path.
  base: './',
  build: {
    // Material Web, jsQR and the color utilities add up to ~145 kB gzipped.
    chunkSizeWarningLimit: 700,
  },
  define: {
    __APP_VERSION__: JSON.stringify(version),
  },
});
