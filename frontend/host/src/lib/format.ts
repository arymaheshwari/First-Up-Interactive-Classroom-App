/** Display helpers for the distance-scored question types (pin_drop, estimate). */
import type { Point } from '../types/game';

/** 2005, 3.5, −0.25: up to 4 decimals, with a real minus sign. */
export function formatNumber(n: number): string {
  const rounded = Number.isInteger(n) ? n : Number(n.toFixed(4));
  return String(rounded).replace('-', '−');
}

export function formatPoint(p: Point): string {
  return `(${formatNumber(p.x)}, ${formatNumber(p.y)})`;
}

export function withUnit(n: number, unit: string | undefined): string {
  return unit ? `${formatNumber(n)} ${unit}` : formatNumber(n);
}

export function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/** The guess nearest the answer (display only — scoring never ranks guesses). */
export function closestTo(values: number[], answer: number): number | null {
  if (values.length === 0) return null;
  return values.reduce((best, v) => (Math.abs(v - answer) < Math.abs(best - answer) ? v : best));
}

/** Split results values into pins or numbers (the payload carries one kind per type). */
export function asPoints(values: (Point | number)[] | undefined): Point[] {
  return (values ?? []).filter((v): v is Point => typeof v === 'object' && v !== null);
}

export function asNumbers(values: (Point | number)[] | undefined): number[] {
  return (values ?? []).filter((v): v is number => typeof v === 'number');
}

/** A point on a Pin It picture (fractions of it): "42% across, 61% down". */
export function formatImagePoint(p: Point): string {
  return `${formatNumber(Number((p.x * 100).toFixed(1)))}% across, ${formatNumber(Number((p.y * 100).toFixed(1)))}% down`;
}

/**
 * Distance from a pin to the target: grid units, or image widths on a picture,
 * where a height step counts `aspect` (height / width) of a width step.
 */
export function pinDistance(p: Point, target: Point, aspect = 1): number {
  return Math.hypot(p.x - target.x, (p.y - target.y) * aspect);
}
