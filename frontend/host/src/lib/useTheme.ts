import { useEffect, useState } from 'react';
import { THEME_EVENT, currentTheme, setTheme, type Theme } from '../../../shared/theme/theme';

/** The current theme and a toggle, kept in step with <html data-theme> (T9). */
export function useTheme(): [Theme, () => void] {
  const [theme, setThemeState] = useState<Theme>(currentTheme);

  useEffect(() => {
    const sync = () => setThemeState(currentTheme());
    window.addEventListener(THEME_EVENT, sync);
    const observer = new MutationObserver(sync);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => {
      window.removeEventListener(THEME_EVENT, sync);
      observer.disconnect();
    };
  }, []);

  return [theme, () => setTheme(theme === 'dark' ? 'light' : 'dark')];
}
