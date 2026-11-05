import { type ClassValue, clsx } from 'clsx';
import { extendTailwindMerge } from 'tailwind-merge';

/**
 * The custom classes of the shared theme preset (frontend/shared/theme/tailwind-preset.ts,
 * CUSTOM_CLASSES). Without them tailwind-merge reads `text-display` as a text colour and
 * drops `text-fg` in `cn('text-fg', 'text-display')`. tests/unit checks the lists match.
 */
const THEME_CLASS_GROUPS = {
  'font-size': ['display', 'host-lg', 'host-xl', 'host-2xl'],
  shadow: ['card', 'raised', 'press'],
  rounded: ['card', 'control'],
};

const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      'font-size': [{ text: THEME_CLASS_GROUPS['font-size'] }],
      shadow: [{ shadow: THEME_CLASS_GROUPS.shadow }],
      rounded: [{ rounded: THEME_CLASS_GROUPS.rounded }],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
