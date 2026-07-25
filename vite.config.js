import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // 'base: "./"' usa percorsi relativi per tutti i file statici (JS, CSS, JSON).
  // È FONDAMENTALE per far funzionare correttamente l'app su GitHub Pages senza errori 404.
  base: './',
  resolve: {
    alias: {
      // Ti permette di usare import puliti tipo: import Map from '@/components/Map'
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    open: true,
  },
})
