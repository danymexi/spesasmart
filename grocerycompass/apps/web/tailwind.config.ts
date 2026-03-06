import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  darkMode: 'media',
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#1A8C4E',
          light: '#E8F5EE',
          dark: '#0F5C33',
        },
        savings: {
          DEFAULT: '#F59E0B',
          bg: '#FFFBEB',
        },
        surface: '#FFFFFF',
        background: '#FAFAF9',
      },
      fontFamily: {
        display: ['Bricolage Grotesque', 'sans-serif'],
        body: ['DM Sans', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      spacing: {
        '18': '4.5rem',
        '88': '22rem',
      },
    },
  },
  plugins: [],
}

export default config
