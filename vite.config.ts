import { defineConfig } from 'vite';

export default defineConfig({
  // Relative asset paths so the build works from any GitHub Pages sub-path.
  base: './',
  build: { chunkSizeWarningLimit: 3000 },
});
