import { cn } from '../../lib/utils';

type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

export function Input({ className, ...props }: InputProps) {
  return (
    <input
      className={cn(
        'w-full rounded-control border border-line-strong bg-surface-sunken h-12 px-4 text-base',
        'text-fg placeholder:text-fg-subtle',
        // The global outline marks keyboard focus; the border colour also cues mouse users.
        'focus:border-focus',
        className,
      )}
      {...props}
    />
  );
}
