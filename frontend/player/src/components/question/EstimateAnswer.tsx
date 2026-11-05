import { useState } from 'react';
import { parseEstimate } from '../../lib/answers';

interface EstimateAnswerProps {
  unit: string;
  integer: boolean;
  disabled: boolean;
  onSubmit: (value: number) => void;
}

/** One number on the phone's numeric keypad; Submit only enables for a valid number. */
export function EstimateAnswer({ unit, integer, disabled, onSubmit }: EstimateAnswerProps) {
  const [raw, setRaw] = useState('');
  const parsed = parseEstimate(raw, integer);

  return (
    <form
      onSubmit={e => {
        e.preventDefault();
        if (parsed.kind === 'ok' && !disabled) onSubmit(parsed.value);
      }}
      className="flex flex-col gap-3"
    >
      <label htmlFor="estimate-input" className="text-center text-fg-muted text-sm font-medium">
        {integer ? 'Your best guess (whole number)' : 'Your best guess'}
      </label>
      <div className="flex items-center gap-3">
        <input
          id="estimate-input"
          type="text"
          inputMode={integer ? 'numeric' : 'decimal'}
          autoComplete="off"
          value={raw}
          onChange={e => setRaw(e.target.value)}
          disabled={disabled}
          placeholder="0"
          autoFocus
          aria-invalid={parsed.kind === 'error'}
          aria-describedby="estimate-error"
          className="player-question__input flex-1 min-w-0 rounded-card border-2 border-line-strong bg-surface-sunken px-4 py-4 text-fg text-3xl font-bold text-center placeholder:text-fg-subtle focus:border-focus"
        />
        {unit && <span className="text-fg text-xl font-semibold shrink-0">{unit}</span>}
      </div>
      <p id="estimate-error" className="text-center text-warning-fg text-base min-h-6" aria-live="polite">
        {parsed.kind === 'error' ? parsed.message : ''}
      </p>
      <button
        type="submit"
        disabled={disabled || parsed.kind !== 'ok'}
        className="player-question__submit w-full min-h-14 rounded-card py-5 text-on-color font-black text-2xl bg-accent hover:bg-accent-hover active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
      >
        Submit
      </button>
    </form>
  );
}
