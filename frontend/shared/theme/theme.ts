/** Appearance is local to this browser and to the app (Host, Player or Admin). */
export type Theme = 'light' | 'dark';
export type VisualTheme = 'aurora' | 'pixel-cats' | 'pixel-classroom';
export type ThemeApp = 'host' | 'player' | 'admin';

export const THEME_KEY = 'buzzer-theme'; // Legacy choice, read only for migration.
export const THEME_EVENT = 'buzzer-theme-change';
export const VISUAL_THEMES: ReadonlyArray<{ id: VisualTheme; label: string }> = [
  { id: 'aurora', label: 'Aurora' },
  { id: 'pixel-cats', label: 'Pixel Cats' },
  { id: 'pixel-classroom', label: 'Classroom' },
];

const DARK_QUERY = '(prefers-color-scheme: dark)';
let activeApp: ThemeApp = 'host';
const modeKey = () => `buzzer-theme-${activeApp}`;
const visualKey = () => `buzzer-visual-theme-${activeApp}`;
const read = (key: string): string | null => {
  try { return localStorage.getItem(key); } catch { return null; }
};
const write = (key: string, value: string): void => {
  try { localStorage.setItem(key, value); } catch { /* Choice lasts for this view. */ }
};
const isTheme = (value: unknown): value is Theme => value === 'light' || value === 'dark';
const isVisualTheme = (value: unknown): value is VisualTheme => VISUAL_THEMES.some(choice => choice.id === value);

export function storedTheme(): Theme | null {
  const value = read(modeKey()) ?? read(THEME_KEY);
  return isTheme(value) ? value : null;
}
export function systemTheme(): Theme {
  return typeof window.matchMedia === 'function' && window.matchMedia(DARK_QUERY).matches ? 'dark' : 'light';
}
export function resolveTheme(): Theme { return storedTheme() ?? systemTheme(); }
export function currentTheme(): Theme { return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'; }
export function currentVisualTheme(): VisualTheme {
  const value = document.documentElement.dataset.visualTheme;
  return isVisualTheme(value) ? value : 'aurora';
}
export function applyTheme(theme: Theme): void { document.documentElement.dataset.theme = theme; }
export function applyVisualTheme(theme: VisualTheme): void { document.documentElement.dataset.visualTheme = theme; }
const announce = () => window.dispatchEvent(new CustomEvent(THEME_EVENT));

export function setTheme(theme: Theme): void {
  write(modeKey(), theme);
  applyTheme(theme);
  announce();
}
export function setVisualTheme(theme: VisualTheme): void {
  write(visualKey(), theme);
  applyVisualTheme(theme);
  announce();
}

export function initTheme(app: ThemeApp): () => void {
  activeApp = app;
  document.documentElement.dataset.app = app;
  applyTheme(resolveTheme());
  const visual = read(visualKey());
  applyVisualTheme(isVisualTheme(visual) ? visual : 'aurora');
  const media = typeof window.matchMedia === 'function' ? window.matchMedia(DARK_QUERY) : null;
  const onSystemChange = () => {
    if (storedTheme() === null) { applyTheme(systemTheme()); announce(); }
  };
  const onStorage = (event: StorageEvent) => {
    if (event.key !== null && event.key !== modeKey() && event.key !== visualKey() && event.key !== THEME_KEY) return;
    applyTheme(resolveTheme());
    const next = read(visualKey());
    applyVisualTheme(isVisualTheme(next) ? next : 'aurora');
    announce();
  };
  media?.addEventListener('change', onSystemChange);
  window.addEventListener('storage', onStorage);
  return () => {
    media?.removeEventListener('change', onSystemChange);
    window.removeEventListener('storage', onStorage);
  };
}
