import { formatImagePoint, formatNumber, formatPoint, withUnit } from './format';
import type { Point, QuestionConfig } from '../types/game';

/**
 * Plain-text labels for stored answers and answer keys, used by the private session
 * detail page (docs/plans/question-feedback.md §4.7). Shapes follow
 * backend/app/services/question_types.py.
 */

type Json = Record<string, unknown>;

const letter = (i: number) => String.fromCharCode(65 + i);

function option(config: QuestionConfig, i: number): string {
  const text = config.options?.[i];
  return text ? `${letter(i)} — ${text}` : letter(i);
}

function point(config: QuestionConfig, p: Point): string {
  return config.image ? formatImagePoint(p) : formatPoint(p);
}

function isPoint(v: unknown): v is Point {
  return typeof v === 'object' && v !== null && typeof (v as Point).x === 'number' && typeof (v as Point).y === 'number';
}

/** What a player answered, e.g. "B — Mars", "True", "(2, −3)". */
export function describeAnswer(type: string, config: QuestionConfig, answer: Json | null): string {
  if (!answer) return '—';
  switch (type) {
    case 'multiple_choice':
      return typeof answer.selectedIndex === 'number' ? option(config, answer.selectedIndex) : '—';
    case 'true_false':
      return typeof answer.selectedValue === 'boolean' ? (answer.selectedValue ? 'True' : 'False') : '—';
    case 'fill_in_the_blank':
      return typeof answer.text === 'string' ? `“${answer.text}”` : '—';
    case 'multi_select': {
      const picked = Array.isArray(answer.selectedIndices) ? (answer.selectedIndices as number[]) : [];
      return picked.length ? [...picked].sort((a, b) => a - b).map(i => option(config, i)).join(', ') : 'None';
    }
    case 'pin_drop':
      return isPoint(answer.point) ? point(config, answer.point) : '—';
    case 'estimate':
      return typeof answer.value === 'number' ? withUnit(answer.value, config.unit) : '—';
    default:
      return JSON.stringify(answer);
  }
}

/** The answer key in words, or null for participation-graded questions. */
export function describeCorrect(
  type: string,
  gradingType: string,
  config: QuestionConfig,
  key: Json,
): string | null {
  if (gradingType !== 'ACCURACY') return null;
  switch (type) {
    case 'multiple_choice':
    case 'multi_select': {
      const pts = Array.isArray(key.answer_points) ? (key.answer_points as number[]) : [];
      const best = type === 'multiple_choice' ? Math.max(0, ...pts) : 0;
      const right = pts
        .map((p, i) => ({ p, i }))
        .filter(({ p }) => (type === 'multiple_choice' ? p > 0 && p === best : p > 0))
        .map(({ i }) => option(config, i));
      return right.length ? right.join(', ') : null;
    }
    case 'true_false': {
      const pts = (key.answer_points ?? {}) as Record<string, number>;
      if ((pts.true ?? 0) === (pts.false ?? 0)) return null;
      return (pts.true ?? 0) > (pts.false ?? 0) ? 'True' : 'False';
    }
    case 'fill_in_the_blank':
      return Array.isArray(key.acceptedAnswers) ? (key.acceptedAnswers as string[]).join(' / ') : null;
    case 'pin_drop':
      return isPoint(key.target) ? point(config, key.target) : null;
    case 'estimate':
      return typeof key.answer === 'number' ? withUnit(key.answer, config.unit) : null;
    default:
      return null;
  }
}

/** Seconds with one decimal, e.g. 1.3 s. */
export function formatSeconds(ms: number | null): string {
  return ms === null ? '—' : `${formatNumber(Math.round(ms / 100) / 10)} s`;
}

export const TYPE_LABELS: Record<string, string> = {
  multiple_choice: 'Multiple choice',
  true_false: 'True / False',
  fill_in_the_blank: 'Fill in the blank',
  multi_select: 'Multi-select',
  pin_drop: 'Pin It',
  estimate: 'Estimate',
};
