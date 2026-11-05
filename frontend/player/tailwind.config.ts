import type { Config } from 'tailwindcss';
import preset from '../shared/theme/tailwind-preset';

// Colours, shadows, radii and type come from the shared theme preset (T9).
export default {
  presets: [preset as Partial<Config>],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
} satisfies Config;
