import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  base: './', // CRITICAL for GitHub Pages relative asset resolution
  server: {
    port: 3000,
    open: true
  }
});
