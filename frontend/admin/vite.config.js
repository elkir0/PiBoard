import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  base: '/admin/',
  build: {
    outDir: '../../backend/admin/static',
    emptyOutDir: true,
  },
});
