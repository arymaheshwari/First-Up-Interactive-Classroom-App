import { useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';
import { useTheme } from '../../lib/useTheme';
import { cn } from '../../lib/utils';
import { THEME_EVENT, VISUAL_THEMES, currentVisualTheme, setVisualTheme, type VisualTheme } from '../../../../shared/theme/theme';

interface ThemeToggleProps {
  /** `inline` sits in a sidebar or panel; `floating` is fixed to the viewport's top right. */
  variant?: 'inline' | 'floating';
  className?: string;
}

/** Light/dark switch (T9). The icon shows the theme it switches to. */
export function ThemeToggle({ variant = 'inline', className }: ThemeToggleProps) {
  const [theme, toggle] = useTheme();
  const [visualTheme, updateVisualTheme] = useState<VisualTheme>(currentVisualTheme);
  useEffect(() => {
    const sync = () => updateVisualTheme(currentVisualTheme());
    window.addEventListener(THEME_EVENT, sync);
    return () => window.removeEventListener(THEME_EVENT, sync);
  }, []);
  const label = `Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`;
  return (
    <div className={cn('appearance-controls', variant === 'floating' && 'appearance-controls--floating')}>
      <select
        aria-label="Visual theme"
        title="Visual theme"
        value={visualTheme}
        onChange={(event) => setVisualTheme(event.target.value as VisualTheme)}
        className="appearance-controls__select"
      >
        {VISUAL_THEMES.map((choice) => <option key={choice.id} value={choice.id}>{choice.label}</option>)}
      </select>
    <button
      type="button"
      onClick={toggle}
      aria-label={label}
      title={label}
      className={cn(
        'inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-control text-fg-muted transition-colors hover:bg-surface-hover hover:text-fg',
        variant === 'floating' && 'border border-line bg-surface shadow-card',
        className,
      )}
    >
      {theme === 'dark' ? <Sun size={20} aria-hidden="true" /> : <Moon size={20} aria-hidden="true" />}
    </button>
    </div>
  );
}
