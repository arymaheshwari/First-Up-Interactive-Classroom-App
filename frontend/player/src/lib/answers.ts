/**
 * Human-readable answers for every question type, shared by the Results and
 * Game Over pages (they used to format answers independently), plus input
 * parsing for the estimate type.
 */
import type {
  PlayerAnswer,
  PlayerAnswerReveal,
  Point,
  QuestionConfig,
  QuestionType,
} from '../types/game';

/** Types scored by distance, with partial credit (full → linear falloff → zero). */
export const DISTANCE_TYPES: ReadonlySet<QuestionType> = new Set(['pin_drop', 'estimate']);

const letter = (i: number) => String.fromCharCode(65 + i);

function optionLabel(i: number, options: string[] | undefined): string {
  return options?.[i] !== undefined ? `${letter(i)} — ${options[i]}` : letter(i);
}

/** 2005, 3.5, −0.25: up to 4 decimals, with a real minus sign. */
export function formatNumber(n: number): string {
  const rounded = Number.isInteger(n) ? n : Number(n.toFixed(4));
  return String(rounded).replace('-', '−');
}

export function formatPoint(p: Point): string {
  return `(${formatNumber(p.x)}, ${formatNumber(p.y)})`;
}

const percent = (f: number) => `${formatNumber(Number((f * 100).toFixed(1)))}%`;

/** A pin on a Pin It picture (fractions of it), as percentages: "(42%, 61%)". */
export function formatImagePoint(p: Point): string {
  return `(${percent(p.x)}, ${percent(p.y)})`;
}

/** A pin_drop point in its question's units: grid units, or percentages on a picture. */
export function formatPin(p: Point, config: QuestionConfig): string {
  return config.image ? formatImagePoint(p) : formatPoint(p);
}

function withUnit(n: number, unit: string | undefined): string {
  return unit ? `${formatNumber(n)} ${unit}` : formatNumber(n);
}

export function describePlayerAnswer(
  type: QuestionType,
  answer: PlayerAnswer | null,
  config: QuestionConfig,
): string {
  if (!answer) return 'No answer';
  switch (type) {
    case 'multiple_choice':
      return typeof answer.selectedIndex === 'number'
        ? optionLabel(answer.selectedIndex, config.options)
        : '?';
    case 'true_false':
      return answer.selectedValue ? 'True' : 'False';
    case 'fill_in_the_blank':
      return typeof answer.text === 'string' ? answer.text : '—';
    case 'multi_select':
      return answer.selectedIndices?.length
        ? answer.selectedIndices.map(i => optionLabel(i, config.options)).join(', ')
        : 'No selection';
    case 'pin_drop':
      return answer.point ? formatPin(answer.point, config) : '—';
    case 'estimate':
      return typeof answer.value === 'number' ? withUnit(answer.value, config.unit) : '—';
  }
}

export function describeCorrectAnswer(
  reveal: PlayerAnswerReveal,
  config: QuestionConfig,
): string {
  switch (reveal.type) {
    case 'multiple_choice':
      return reveal.correctIndices.map(i => optionLabel(i, config.options)).join(', ');
    case 'true_false':
      return reveal.correctValue ? 'True' : 'False';
    case 'fill_in_the_blank': {
      const label = reveal.acceptedAnswers.join(' / ');
      return reveal.editDistance > 0 ? `${label} (±${reveal.editDistance})` : label;
    }
    case 'multi_select':
      return reveal.answerPoints
        .map((p, i) => ({ p, i }))
        .filter(({ p }) => p > 0)
        .map(({ i }) => optionLabel(i, config.options))
        .join(', ');
    case 'pin_drop':
      return formatPin(reveal.target, config);
    case 'estimate':
      return withUnit(reveal.answer, reveal.unit);
    case 'completeness':
      return '';
  }
}

/**
 * "1.4 away" / "8% of the image width away" / "5 years off" / "12% off" — how far a
 * distance-scored answer was. On a picture distances are in image widths (T8 D5).
 */
export function describeMiss(
  answer: PlayerAnswer | null,
  reveal: PlayerAnswerReveal,
  config: QuestionConfig = {},
): string | null {
  if (reveal.type === 'pin_drop' && answer?.point) {
    const aspect = config.image ? config.image.height / config.image.width : 1;
    const d = Math.hypot(answer.point.x - reveal.target.x, (answer.point.y - reveal.target.y) * aspect);
    return config.image
      ? `${percent(d)} of the image width away`
      : `${formatNumber(Number(d.toFixed(2)))} away`;
  }
  if (reveal.type === 'estimate' && typeof answer?.value === 'number') {
    const diff = Math.abs(answer.value - reveal.answer);
    if (reveal.tolerance.mode === 'relative') {
      return `${formatNumber(Number(((diff / Math.abs(reveal.answer)) * 100).toFixed(1)))}% off`;
    }
    return `${withUnit(Number(diff.toFixed(4)), reveal.unit)} off`;
  }
  return null;
}

export const ESTIMATE_LIMIT = 1e12;

export type EstimateInput =
  | { kind: 'empty' }
  | { kind: 'error'; message: string }
  | { kind: 'ok'; value: number };

/**
 * Parse what a player typed for an estimate. Spaces are ignored and a single
 * comma with no dot is a decimal comma (many phone keyboards type "3,5").
 * Thousands separators aren't supported.
 */
export function parseEstimate(raw: string, integer: boolean): EstimateInput {
  let s = raw.replace(/\s+/g, '');
  if (!s) return { kind: 'empty' };
  if (!s.includes('.') && (s.match(/,/g) ?? []).length === 1) s = s.replace(',', '.');
  if (!/^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(s)) {
    return { kind: 'error', message: 'Enter a number' };
  }
  const value = Number(s);
  if (!Number.isFinite(value) || Math.abs(value) > ESTIMATE_LIMIT) {
    return { kind: 'error', message: 'That number is too large' };
  }
  if (integer && !Number.isInteger(value)) {
    return { kind: 'error', message: 'Whole numbers only' };
  }
  return { kind: 'ok', value };
}
