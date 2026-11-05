import { cn } from '../../lib/utils';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'outline' | 'ghost' | 'destructive';
  size?: 'sm' | 'md' | 'lg' | 'xl';
}

const VARIANTS = {
  default: 'bg-accent text-on-color hover:bg-accent-hover',
  outline: 'border border-line-strong text-fg hover:bg-surface-hover',
  ghost: 'text-fg-muted hover:bg-surface-hover hover:text-fg',
  // Darken on hover (shadow-press), so the white text keeps its contrast.
  destructive: 'bg-danger text-on-color hover:shadow-press',
};

/** Fixed heights, so rows of mixed buttons line up (docs/plans/t9-theming.md §4.6). */
const SIZES = {
  sm: 'h-8 px-3 text-sm',
  md: 'h-10 px-4 text-sm',
  lg: 'h-12 px-6 text-base',
  // Host game screens' primary actions (Start Game, Show Results, Next Question).
  xl: 'h-14 px-8 text-host-lg',
};

export function Button({ className, variant = 'default', size = 'md', ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center gap-1 font-semibold transition-colors rounded-control',
        'disabled:pointer-events-none disabled:opacity-50',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    />
  );
}
