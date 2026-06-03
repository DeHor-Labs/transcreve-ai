/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        heading: ['"Space Grotesk"', 'sans-serif'],
        body: ['Inter', 'sans-serif'],
      },
      colors: {
        bg: 'oklch(11% 0.005 260)',
        surface1: 'oklch(15% 0.007 260)',
        surface2: 'oklch(19% 0.008 260)',
        border: 'oklch(26% 0.010 260)',
        accent: 'oklch(82% 0.20 102)',
        'accent-dim': 'oklch(82% 0.10 102)',
        'text-primary': 'oklch(96% 0.004 260)',
        'text-secondary': 'oklch(65% 0.008 260)',
        'text-muted': 'oklch(44% 0.006 260)',
        'status-queued': 'oklch(70% 0.08 240)',
        'status-running': 'oklch(76% 0.15 200)',
        'status-completed': 'oklch(78% 0.18 145)',
        'status-failed': 'oklch(65% 0.20 25)',
      },
      animation: {
        'pulse-slow': 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in': 'fadeIn 0.24s ease-out both',
        'slide-in': 'slideIn 0.24s cubic-bezier(0.16,1,0.3,1) both',
      },
      keyframes: {
        fadeIn: {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        slideIn: {
          from: { opacity: '0', transform: 'translateY(12px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}

