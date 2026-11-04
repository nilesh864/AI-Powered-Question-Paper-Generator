/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#101a18',
        panel: '#172320',
        muted: '#8d9a94',
        mint: '#b9f4d6',
        coral: '#ff9b7b',
      },
      fontFamily: { sans: ['Manrope', 'sans-serif'], mono: ['IBM Plex Mono', 'monospace'] },
    },
  },
  plugins: [],
}