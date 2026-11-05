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
export declare const TOKENS: readonly ["canvas", "surface", "surface-raised", "surface-sunken", "surface-hover", "fg", "fg-muted", "fg-subtle", "on-color", "line", "line-strong", "accent", "accent-hover", "accent-fg", "accent-subtle", "success", "success-fg", "success-subtle", "danger", "danger-fg", "danger-subtle", "warning", "warning-fg", "warning-subtle", "focus", "answer-1", "answer-2", "answer-3", "answer-4", "answer-5", "answer-6", "answer-7", "answer-8", "qr", "scrim", "shadow", "scene-rose", "scene-violet", "scene-blue"];
export declare const CUSTOM_CLASSES: {
    readonly fontSize: readonly ["display", "host-lg", "host-xl", "host-2xl"];
    readonly boxShadow: readonly ["card", "raised", "press"];
    readonly borderRadius: readonly ["card", "control"];
};
/** Tailwind's [size, { lineHeight, fontWeight }] form (a tuple, not an array). */
type FontSize = [string, {
    lineHeight: string;
    fontWeight?: string;
}];
declare const preset: {
    theme: {
        colors: {
            transparent: string;
            current: string;
            inherit: string;
        };
        extend: {
            borderColor: {
                DEFAULT: string;
            };
            ringColor: {
                DEFAULT: string;
            };
            boxShadow: {
                card: string;
                raised: string;
                press: string;
            };
            borderRadius: {
                card: string;
                control: string;
            };
            fontSize: {
                display: FontSize;
                'host-lg': FontSize;
                'host-xl': FontSize;
                'host-2xl': FontSize;
            };
            fontFamily: {
                sans: string[];
            };
        };
    };
};
export default preset;
