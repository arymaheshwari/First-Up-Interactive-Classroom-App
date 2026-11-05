/**
 * SVG number line for estimate results: every guess as a dot (stacked where they
 * overlap), the true value as a marker, and the closest guess highlighted.
 * Colours use the same --canvas-* CSS variables as GridCanvas (the T9 hook).
 */
import { closestTo, withUnit } from '../../lib/format';

interface NumberLineProps {
  values: number[];
  answer?: number | null;
  unit?: string;
  /** Smaller variant for the game-over breakdown. */
  compact?: boolean;
}

const WIDTH = 800;

export function NumberLine({ values, answer = null, unit, compact = false }: NumberLineProps) {
  const height = compact ? 90 : 170;
  const base = height - 34;
  const pad = 40;
  const dotR = compact ? 5 : 8;

  const all = answer !== null ? [...values, answer] : values;
  let lo = Math.min(...all);
  let hi = Math.max(...all);
  if (!Number.isFinite(lo)) return null;
  if (lo === hi) {
    lo -= 1;
    hi += 1;
  }
  const span = hi - lo;
  lo -= span * 0.05;
  hi += span * 0.05;
  const x = (v: number) => pad + ((v - lo) / (hi - lo)) * (WIDTH - 2 * pad);

  const closest = answer !== null ? closestTo(values, answer) : null;
  const stacks = new Map<number, number>();
  const dots = [...values]
    .sort((a, b) => a - b)
    .map((v, i) => {
      const bucket = Math.round(x(v) / (dotR * 2));
      const level = stacks.get(bucket) ?? 0;
      stacks.set(bucket, level + 1);
      const cy = Math.max(base - dotR - 3 - level * (dotR * 2 + 1), dotR);
      const isClosest = closest !== null && v === closest;
      return (
        <circle
          key={i}
          cx={x(v)}
          cy={cy}
          r={isClosest ? dotR + 2 : dotR}
          fill={isClosest ? 'var(--canvas-highlight)' : 'var(--canvas-pin)'}
          opacity={isClosest ? 1 : 0.8}
        >
          <title>{withUnit(v, unit)}</title>
        </circle>
      );
    });

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${height}`}
      className="w-full"
      role="img"
      aria-label={`Number line of ${values.length} guesses${answer !== null ? `, answer ${withUnit(answer, unit)}` : ''}`}
    >
      <line x1={pad} y1={base} x2={WIDTH - pad} y2={base} stroke="var(--canvas-axis)" strokeWidth={2} />
      <text x={pad} y={base + 24} fill="var(--canvas-label)" fontSize={compact ? 13 : 18} textAnchor="middle">
        {withUnit(Number((lo + span * 0.05).toFixed(4)), '')}
      </text>
      <text x={WIDTH - pad} y={base + 24} fill="var(--canvas-label)" fontSize={compact ? 13 : 18} textAnchor="middle">
        {withUnit(Number((hi - span * 0.05).toFixed(4)), '')}
      </text>
      {dots}
      {answer !== null && (
        <>
          <line
            x1={x(answer)}
            y1={compact ? 6 : 24}
            x2={x(answer)}
            y2={base + 8}
            stroke="var(--canvas-target)"
            strokeWidth={compact ? 3 : 4}
          />
          {!compact && (
            <text x={x(answer)} y={18} fill="var(--canvas-target)" fontSize={18} fontWeight={700} textAnchor="middle">
              {withUnit(answer, unit)}
            </text>
          )}
        </>
      )}
    </svg>
  );
}
