import { useEffect, useRef, useState } from 'react';

interface TimerBarProps {
  totalSeconds: number;
  initialSeconds?: number;
  paused?: boolean;
}

export function TimerBar({ totalSeconds, initialSeconds, paused = false }: TimerBarProps) {
  const startFrom = initialSeconds ?? totalSeconds;
  const [timeLeft, setTimeLeft] = useState(startFrom);
  const pausedRef = useRef(paused);
  const endTimeRef = useRef(Date.now() + startFrom * 1000);
  const frozenRef = useRef(startFrom);

  // Keep pausedRef in sync; on resume, reset endTime from the frozen value
  useEffect(() => {
    pausedRef.current = paused;
    if (!paused) {
      endTimeRef.current = Date.now() + frozenRef.current * 1000;
    }
  }, [paused]);

  useEffect(() => {
    if (totalSeconds <= 0) return;

    const id = setInterval(() => {
      if (pausedRef.current) {
        // Slide endTime forward so resume continues from the frozen value
        endTimeRef.current = Date.now() + frozenRef.current * 1000;
        return;
      }
      const remaining = Math.max(0, (endTimeRef.current - Date.now()) / 1000);
      frozenRef.current = remaining;
      setTimeLeft(remaining);
    }, 100);

    return () => clearInterval(id);
  }, []); // runs once on mount; parent uses key={questionId} to remount per question

  const fraction = Math.max(0, Math.min(1, timeLeft / totalSeconds));
  const displaySeconds = Math.ceil(timeLeft);

  const barColor =
    fraction > 0.6 ? 'bg-success' :
    fraction > 0.3 ? 'bg-warning' :
    'bg-danger';

  return (
    <div className="w-full flex items-center gap-4">
      <div className="flex-1 h-6 bg-surface-sunken rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-[width] duration-100 ease-linear ${barColor}`}
          style={{ width: `${fraction * 100}%` }}
        />
      </div>
      <span className="text-fg font-mono text-host-lg font-semibold w-16 text-right tabular-nums shrink-0">
        {displaySeconds}s
      </span>
    </div>
  );
}
