/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: '#FF4500', // Fire Orange
        dark: '#0B0F19',
        card: '#1A2235',
      }
    },
  },
  plugins: [],
}
