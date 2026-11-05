/**
 * Tailwind preset shared by the Host, Player and Admin apps (T9).
 *
 * It *replaces* Tailwind's colour palette with the semantic tokens of tokens.css, so
 * a raw `bg-slate-800` generates nothing and only token classes style the apps.
 * Deliberately import-free (frontend/shared has no node_modules); each app types it
 * as `Partial<Config>`.
 *
 * The two `as const` lists below are parsed by tests/unit (keep one quoted name per
 * item): TOKENS must match tokens.css, and CUSTOM_CLASSES must match each app's
 * THEME_CLASS_GROUPS in src/lib/utils.ts. See docs/plans/t9-theming.md §4.3.
 */
export const TOKENS = [
    'canvas',
    'surface',
    'surface-raised',
    'surface-sunken',
    'surface-hover',
    'fg',
    'fg-muted',
    'fg-subtle',
    'on-color',
    'line',
    'line-strong',
    'accent',
    'accent-hover',
    'accent-fg',
    'accent-subtle',
    'success',
    'success-fg',
    'success-subtle',
    'danger',
    'danger-fg',
    'danger-subtle',
    'warning',
    'warning-fg',
    'warning-subtle',
    'focus',
    'answer-1',
    'answer-2',
    'answer-3',
    'answer-4',
    'answer-5',
    'answer-6',
    'answer-7',
    'answer-8',
    'qr',
    'scrim',
    'shadow',
    'scene-rose',
    'scene-violet',
    'scene-blue',
];
export const CUSTOM_CLASSES = {
    fontSize: ['display', 'host-lg', 'host-xl', 'host-2xl'],
    boxShadow: ['card', 'raised', 'press'],
    borderRadius: ['card', 'control'],
};
const token = (name) => `rgb(var(--c-${name}) / <alpha-value>)`;
const preset = {
    theme: {
        colors: {
            transparent: 'transparent',
            current: 'currentColor',
            inherit: 'inherit',
            ...Object.fromEntries(TOKENS.map((name) => [name, token(name)])),
        },
        extend: {
            borderColor: { DEFAULT: token('line') },
            ringColor: { DEFAULT: token('focus') },
            boxShadow: {
                card: '0 1px 2px 0 rgb(var(--c-shadow) / 0.06), 0 1px 3px 0 rgb(var(--c-shadow) / 0.10)',
                raised: '0 10px 25px -5px rgb(var(--c-shadow) / 0.20), 0 8px 10px -6px rgb(var(--c-shadow) / 0.12)',
                // Hover/press overlay for filled answer buttons: darkens the fill, not the text.
                press: 'inset 0 0 0 999px rgb(var(--c-shadow) / 0.12)',
            },
            borderRadius: {
                card: '0.75rem',
                control: '0.5rem',
            },
            fontSize: {
                display: ['clamp(2.25rem, 1.5rem + 2vw, 3.5rem)', { lineHeight: '1.15', fontWeight: '700' }],
                'host-lg': ['1.5rem', { lineHeight: '2rem' }],
                'host-xl': ['2rem', { lineHeight: '2.5rem' }],
                'host-2xl': ['2.75rem', { lineHeight: '3rem' }],
            },
            fontFamily: {
                sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'Helvetica', 'Arial', 'sans-serif'],
            },
        },
    },
};
export default preset;
