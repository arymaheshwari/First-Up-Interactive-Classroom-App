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

/** Returns true if the token is missing, malformed, or past its exp claim. */
export function isTokenExpired(token: string | null): boolean {
  if (!token) return true;
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return Date.now() / 1000 >= (payload.exp ?? 0);
  } catch {
    return true;
  }
}
