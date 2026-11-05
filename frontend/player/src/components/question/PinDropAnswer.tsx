import { useState } from 'react';
import type { Grid, Point, QuestionImage } from '../../types/game';
import { formatImagePoint, formatPoint } from '../../lib/answers';
import { canvasImage } from '../../lib/images';
import { GridCanvas } from './GridCanvas';

/** Nearest grid intersection (xMin + i·step, yMin + j·step). */
function snapToGrid(p: Point, grid: Grid): Point {
  const snap = (v: number, min: number) =>
    Number((min + Math.round((v - min) / grid.step) * grid.step).toFixed(6));
  return { x: snap(p.x, grid.xMin), y: snap(p.y, grid.yMin) };
}

/** 2-decimal pin, clamped after rounding so it can never leave the grid. */
function roundPoint(p: Point, grid: Grid): Point {
  const round = (v: number, min: number, max: number) =>
    Math.min(Math.max(Number(v.toFixed(2)), min), max);
  return { x: round(p.x, grid.xMin, grid.xMax), y: round(p.y, grid.yMin, grid.yMax) };
}

/** On a picture: fractions to 4 decimals, clamped to [0, 1] (T8 D5). */
function roundFraction(p: Point): Point {
  const round = (v: number) => Math.min(Math.max(Number(v.toFixed(4)), 0), 1);
  return { x: round(p.x), y: round(p.y) };
}

interface PinDropAnswerProps {
  /** The grid, or (T8) the picture, to pin on. */
  grid?: Grid;
  image?: QuestionImage;
  snap: boolean;
  disabled: boolean;
  onSubmit: (point: Point) => void;
}

/** Tap (or drag, or use the arrow keys) to place a pin, then Submit. */
export function PinDropAnswer({ grid, image, snap, disabled, onSubmit }: PinDropAnswerProps) {
  const [pin, setPin] = useState<Point | null>(null);

  function place(p: Point) {
    if (disabled) return;
    if (!grid) setPin(roundFraction(p));
    else setPin(snap ? snapToGrid(p, grid) : roundPoint(p, grid));
  }
  const surface = grid ? 'grid' : 'picture';

  return (
    <div className="flex flex-col gap-3">
      <GridCanvas
        grid={grid}
        image={!grid && image ? canvasImage(image) : undefined}
        ownPin={pin}
        onPick={disabled ? undefined : place}
        label={`${grid ? 'Coordinate grid' : 'Picture'}. Tap to place your pin, or use the arrow keys.`}
      />
      <p className="text-center text-fg text-lg font-semibold min-h-7" aria-live="polite">
        {pin
          ? `Your pin: ${grid ? formatPoint(pin) : formatImagePoint(pin)}`
          : `Tap the ${surface} to place your pin`}
      </p>
      {!disabled && (
        <>
          <p className="text-center text-fg-muted text-base">Press Submit to lock in your pin.</p>
          <button
            disabled={!pin}
            onClick={() => pin && onSubmit(pin)}
            className="player-question__submit w-full min-h-14 rounded-card py-5 text-on-color font-black text-2xl bg-accent hover:bg-accent-hover active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Submit
          </button>
        </>
      )}
    </div>
  );
}
