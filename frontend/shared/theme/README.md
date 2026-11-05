# Theme tokens (T9)

The colours, theme switching and base styles shared by the Host, Player and Admin apps.
Full design and contrast figures: [docs/plans/t9-theming.md](../../../docs/plans/t9-theming.md).

| File | What it holds |
|---|---|
| `tokens.css` | Every colour as a CSS variable, for the light (`:root`) and dark (`[data-theme="dark"]`) themes, plus the `--canvas-*` colours the canvases read |
| `base.css` | Body colours, the one focus outline, `.focus-inset`, `::selection`; imported after Tailwind's preflight |
| `tailwind-preset.ts` | Replaces Tailwind's palette with the tokens; adds the shadow, radius and font-size scales |
| `theme.ts` | Light/dark and visual skin state, stored separately for Host, Player and Admin |
| `auth-scene.css` | Shared entry flow layout and glass components for every visual skin |
| `visual-themes.css` | Imports optional palettes and the shared visual template |
| `visual-theme-template.css` | Shared appearance control, surfaces, decoration anchors, and motion for optional pixel themes |
| `pixel-cats.css` / `pixel-classroom.css` | Each skin's light/dark palette and two swappable sprite assignments |
| `assets/*.svg` | Pixel sprites for the optional skins |

`data-theme="light|dark"` remains the required mode. The optional visual skin is
`data-visual-theme="aurora|pixel-cats|pixel-classroom"`; each skin works in both modes. The chooser and the
light/dark button appear together wherever the original toggle was available.
Each app stores its own keys (`buzzer-theme-host`, `buzzer-visual-theme-host`, etc.),
so a Host or Admin choice does not change Player preferences on the same origin.
The original `buzzer-theme` key is read once as a fallback for existing users.
The three apps' entry flows share `auth-scene.css` while retaining their own forms.

To add another visual skin, add its id and label to `VISUAL_THEMES`, implement its
light and dark semantic token overrides in a CSS file, then assign two decorative
asset URLs to `--theme-decor-one/two`. Import that file through `visual-themes.css`
and add its id to the shared template selector. Page layout
selectors in the shared auth scene and the Host/Player scene files apply to every
skin. Keep decoration on the scene anchors or body pseudo-elements, with
`pointer-events: none`, and check the route list in
`docs/plans/pixel-classroom-theme.md`. The existing `tokens.css` light/dark values stay
untouched.

## Using the tokens

Components use **only** these colour classes. Raw palette classes (`bg-slate-800`), `dark:`
variants, focus-ring utilities and colour literals are rejected by
`scripts/check_theme_tokens.py`.

| Token | Use it for |
|---|---|
| `canvas` | the page background |
| `surface` | cards, panels, sidebars |
| `surface-raised` | dialogs, popovers, menus (with `shadow-raised`) |
| `surface-sunken` | inputs, wells, a panel nested in a card, bar tracks, image letterboxes |
| `surface-hover` | the hover of rows, list and nav items, ghost/outline buttons (inside a sunken area use `hover:bg-surface`) |
| `fg` / `fg-muted` / `fg-subtle` | primary / secondary / hint text |
| `on-color` | text and icons on a filled colour (accent, status, answer) |
| `line` / `line-strong` | dividers and card borders / control borders |
| `accent`, `accent-hover` | primary buttons and their hover |
| `accent-fg` | accent-coloured text, icons and the selection bar |
| `accent-subtle` | selection (always with a non-colour cue: the `border-l-4 border-accent-fg` bar, `font-semibold`, `aria-current`) |
| `success` / `danger` / `warning` | fills (with `on-color` text) |
| `*-fg` / `*-subtle` | status text / status backgrounds |
| `focus` | the focus outline (set globally in `base.css`) |
| `answer-1` … `answer-8` | the player's answer buttons; hover/press with `shadow-press` |
| `qr` | only the tile directly behind the QR code |
| `scrim` | modal backdrops, at an alpha (`bg-scrim/60`) |
| `scene-rose`, `scene-violet`, `scene-blue` | decorative background light only; place readable content on a `surface` layer |

Outside classes (inline styles, SVG attributes) write `rgb(var(--c-<token>))`, or
`rgb(var(--c-<token>) / 0.5)` for transparency.

## Adding a token

1. Add the variable to **both** blocks in `tokens.css`.
2. Add its name to `TOKENS` in `tailwind-preset.ts`.
3. If text sits on it or it sits on something, add the pair to `tests/unit/test_theme_contrast.py`
   and run it: text needs 4.5:1, control borders and graphics 3:1.
