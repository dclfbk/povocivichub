/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        hub: {
          50: '#f0f4ff',
          100: '#e0e9fe',
          500: '#6366f1',
          600: '#4f46e5',
          900: '#0f172a',
          card: 'rgba(15, 23, 42, 0.82)'
        }
      },
      fontFamily: {
        sans: ['Outfit', 'Inter', 'sans-serif']
      }
    },
  },
  plugins: [],
}
