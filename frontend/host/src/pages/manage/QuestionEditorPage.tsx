import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Plus, Trash2, ChevronUp, ChevronDown, Download, ImagePlus, X } from 'lucide-react';
import { api } from '../../lib/api';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Card, CardContent, CardHeader } from '../../components/ui/card';
import { GridCanvas } from '../../components/question/GridCanvas';
import { ImagePicker } from '../../components/images/ImagePicker';
import { type ImageInfo, imageUrl } from '../../lib/images';
import { formatPoint, withUnit } from '../../lib/format';
import type { Grid, Point, QuestionType } from '../../types/game';

type GradingType = 'ACCURACY' | 'COMPLETENESS';
type ToleranceMode = 'relative' | 'absolute';

/** Distance-scored types: points_value is the maximum award, entered directly. */
const DISTANCE_TYPES: ReadonlySet<QuestionType> = new Set(['pin_drop', 'estimate']);

interface Question {
  id: number;
  type: QuestionType;
  grading_type: GradingType;
  prompt: string;
  config: Record<string, unknown>;
  answer_data: Record<string, unknown>;
  time_limit_seconds: number;
  points_value: number;
  order_index: number;
}

interface Game { id: number; course_id: number; title: string }

// ---- helpers for building config/answer_data per type ----

/** An image the form points at (T8). The size is 0 until it's known. */
interface ImageRef { id: string; width: number; height: number }

const refOf = (img: ImageInfo): ImageRef => ({ id: img.id, width: img.width, height: img.height });

/** Each option row keeps its text, points and image together, so they stay aligned. */
interface McOption { text: string; points: number; image?: ImageRef | null }

/** `optionImages` only when at least one option has a picture (T8 D4). */
function optionImagesOf(options: McOption[]) {
  return options.some((o) => o.image) ? { optionImages: options.map((o) => o.image?.id ?? null) } : {};
}

function buildMcPayload(options: McOption[], _grading: GradingType) {
  return {
    config: { options: options.map((o) => o.text), ...optionImagesOf(options) },
    answer_data: { answer_points: options.map((o) => o.points) },
  };
}

function buildTfPayload(truePoints: number, falsePoints: number) {
  return {
    config: {},
    answer_data: { answer_points: { true: truePoints, false: falsePoints } },
  };
}

function buildMsPayload(options: McOption[]) {
  return {
    config: { options: options.map((o) => o.text), ...optionImagesOf(options) },
    answer_data: { answer_points: options.map((o) => o.points) },
  };
}

interface FibAnswer { text: string; points: number }

function buildFibPayload(answers: FibAnswer[], editDistance: number) {
  return {
    config: {},
    answer_data: {
      acceptedAnswers: answers.map((a) => a.text),
      answerPoints: answers.map((a) => a.points),
      editDistance,
    },
  };
}

/**
 * Mirrors the backend's grid rules (services/question_types.py) so the editor can
 * say what's wrong before saving; the backend still validates every save.
 */
function gridProblem(g: Grid): string | null {
  const nums = [g.xMin, g.xMax, g.yMin, g.yMax, g.step];
  if (nums.some((n) => !Number.isFinite(n) || Math.abs(n) > 1000)) return 'Grid values must be numbers between −1000 and 1000.';
  if (g.xMin >= g.xMax || g.yMin >= g.yMax) return 'Each axis needs min < max.';
  if (g.step <= 0) return 'Step must be greater than 0.';
  for (const [axis, span] of [['x', g.xMax - g.xMin], ['y', g.yMax - g.yMin]] as const) {
    const cells = span / g.step;
    if (Math.abs(cells - Math.round(cells)) > 1e-9) return `The ${axis} range must be a whole number of steps.`;
    if (Math.round(cells) > 20) return `The ${axis} axis has ${Math.round(cells)} cells; at most 20 fit on a phone.`;
  }
  const ratio = (g.xMax - g.xMin) / (g.yMax - g.yMin);
  if (ratio < 0.5 || ratio > 2) return 'The x:y range ratio must be between 1:2 and 2:1.';
  return null;
}

function snapPoint(p: Point, g: Grid): Point {
  const snap = (v: number, min: number) => Number((min + Math.round((v - min) / g.step) * g.step).toFixed(6));
  return { x: snap(p.x, g.xMin), y: snap(p.y, g.yMin) };
}

/** Image-mode defaults (T8 §5.2): the centre, and 5% / 15% of the image width. */
const IMAGE_CENTRE: Point = { x: 0.5, y: 0.5 };
const IMAGE_RADII = { full: 0.05, zero: 0.15 };
const GRID_RADII = { full: 1, zero: 3 };

const gridCentre = (g: Grid): Point => ({ x: (g.xMin + g.xMax) / 2, y: (g.yMin + g.yMax) / 2 });

function buildPinPayload(form: FormState) {
  return {
    config:
      form.pinMode === 'image'
        ? { image: { imageId: form.pinImage?.id ?? '' } }
        : { grid: form.pinGrid, snap: form.pinSnap },
    answer_data:
      form.grading === 'ACCURACY'
        ? { target: form.pinTarget, fullRadius: form.pinFull, zeroRadius: form.pinZero }
        : {},
  };
}

function buildEstimatePayload(form: FormState) {
  const unit = form.estUnit.trim();
  return {
    config: { ...(unit ? { unit } : {}), integer: form.estInteger },
    answer_data:
      form.grading === 'ACCURACY'
        ? { answer: form.estAnswer, tolerance: { mode: form.estMode, full: form.estFull, zero: form.estZero } }
        : {},
  };
}

// ---- QuestionForm subcomponent ----

interface FormState {
  type: QuestionType;
  grading: GradingType;
  prompt: string;
  /** Any type (T8): shown with the prompt on the projector. */
  promptImage: ImageRef | null;
  timeLimitSeconds: number;
  pointsValue: number;
  // multiple_choice
  mcOptions: McOption[];
  // true_false
  tfTruePoints: number;
  tfFalsePoints: number;
  // fill_in_the_blank
  fibAnswers: FibAnswer[];
  fibEditDistance: number;
  // multi_select
  msOptions: McOption[];
  // pin_drop — on a grid, or on an image (T8; target and radii are then fractions)
  pinMode: 'grid' | 'image';
  pinImage: ImageRef | null;
  pinGrid: Grid;
  pinSnap: boolean;
  pinTarget: Point;
  pinFull: number;
  pinZero: number;
  // estimate
  estAnswer: number;
  estUnit: string;
  estInteger: boolean;
  estMode: ToleranceMode;
  estFull: number;
  estZero: number;
}

const defaultForm = (): FormState => ({
  type: 'multiple_choice',
  grading: 'ACCURACY',
  prompt: '',
  promptImage: null,
  timeLimitSeconds: 30,
  pointsValue: 1,
  mcOptions: [{ text: '', points: 1 }, { text: '', points: 0 }],
  tfTruePoints: 1,
  tfFalsePoints: 0,
  fibAnswers: [{ text: '', points: 1 }],
  fibEditDistance: 0,
  msOptions: [{ text: '', points: 1 }, { text: '', points: 1 }],
  pinMode: 'grid',
  pinImage: null,
  pinGrid: { xMin: -5, xMax: 5, yMin: -5, yMax: 5, step: 1 },
  pinSnap: true,
  pinTarget: { x: 0, y: 0 },
  pinFull: 1,
  pinZero: 3,
  estAnswer: 100,
  estUnit: '',
  estInteger: false,
  estMode: 'relative',
  estFull: 5,
  estZero: 25,
});

function questionToForm(q: Question): FormState {
  const base: FormState = {
    ...defaultForm(),
    type: q.type,
    grading: q.grading_type,
    prompt: q.prompt,
    timeLimitSeconds: q.time_limit_seconds,
    pointsValue: q.points_value,
  };
  const promptImageId = q.config['promptImageId'];
  if (typeof promptImageId === 'string') base.promptImage = { id: promptImageId, width: 0, height: 0 };
  const optionImages = (q.config['optionImages'] as (string | null)[] | undefined) ?? [];
  const optionImage = (i: number): ImageRef | null =>
    optionImages[i] ? { id: optionImages[i] as string, width: 0, height: 0 } : null;
  if (q.type === 'multiple_choice') {
    const opts = (q.config['options'] as string[]) ?? [];
    const pts = (q.answer_data['answer_points'] as number[]) ?? [];
    base.mcOptions = opts.map((text, i) => ({ text, points: pts[i] ?? 0, image: optionImage(i) }));
  } else if (q.type === 'true_false') {
    const ap = q.answer_data['answer_points'] as { true: number; false: number } | undefined;
    base.tfTruePoints = ap?.true ?? 1;
    base.tfFalsePoints = ap?.false ?? 0;
  } else if (q.type === 'fill_in_the_blank') {
    const accepted = (q.answer_data['acceptedAnswers'] as string[]) ?? [];
    const pts = (q.answer_data['answerPoints'] as number[]) ?? [];
    base.fibAnswers = accepted.length
      ? accepted.map((text, i) => ({ text, points: pts[i] ?? 1 }))
      : [{ text: '', points: 1 }];
    base.fibEditDistance = (q.answer_data['editDistance'] as number) ?? 0;
  } else if (q.type === 'multi_select') {
    const opts = (q.config['options'] as string[]) ?? [];
    const pts = (q.answer_data['answer_points'] as number[]) ?? [];
    base.msOptions = opts.length
      ? opts.map((text, i) => ({ text, points: pts[i] ?? 1, image: optionImage(i) }))
      : [{ text: '', points: 1 }, { text: '', points: 1 }];
  } else if (q.type === 'pin_drop') {
    const grid = q.config['grid'] as Grid | undefined;
    if (grid) base.pinGrid = grid;
    const image = q.config['image'] as { imageId: string; width: number; height: number } | undefined;
    if (image) {
      base.pinMode = 'image';
      base.pinImage = { id: image.imageId, width: image.width, height: image.height };
      base.pinTarget = IMAGE_CENTRE;
      base.pinFull = IMAGE_RADII.full;
      base.pinZero = IMAGE_RADII.zero;
    }
    base.pinSnap = !!q.config['snap'];
    const target = q.answer_data['target'] as Point | undefined;
    if (target) base.pinTarget = target;
    base.pinFull = (q.answer_data['fullRadius'] as number) ?? base.pinFull;
    base.pinZero = (q.answer_data['zeroRadius'] as number) ?? base.pinZero;
  } else if (q.type === 'estimate') {
    base.estUnit = (q.config['unit'] as string) ?? '';
    base.estInteger = !!q.config['integer'];
    base.estAnswer = (q.answer_data['answer'] as number) ?? base.estAnswer;
    const tol = q.answer_data['tolerance'] as { mode: ToleranceMode; full: number; zero: number } | undefined;
    if (tol) {
      base.estMode = tol.mode;
      base.estFull = tol.full;
      base.estZero = tol.zero;
    }
  }
  return base;
}

function formToPayload(form: FormState) {
  let config: Record<string, unknown> = {};
  let answer_data: Record<string, unknown> = {};
  if (form.type === 'multiple_choice') {
    const p = buildMcPayload(form.mcOptions, form.grading);
    config = p.config;
    answer_data = p.answer_data;
  } else if (form.type === 'true_false') {
    const p = buildTfPayload(form.tfTruePoints, form.tfFalsePoints);
    config = p.config;
    answer_data = p.answer_data;
  } else if (form.type === 'multi_select') {
    const p = buildMsPayload(form.msOptions.filter((o) => o.text.trim()));
    config = p.config;
    answer_data = p.answer_data;
  } else if (form.type === 'pin_drop') {
    const p = buildPinPayload(form);
    config = p.config;
    answer_data = p.answer_data;
  } else if (form.type === 'estimate') {
    const p = buildEstimatePayload(form);
    config = p.config;
    answer_data = p.answer_data;
  } else {
    const p = buildFibPayload(form.fibAnswers.filter((a) => a.text.trim()), form.fibEditDistance);
    config = p.config;
    answer_data = p.answer_data;
  }
  if (form.promptImage) config = { ...config, promptImageId: form.promptImage.id };
  const points_value =
    form.grading === 'COMPLETENESS' || DISTANCE_TYPES.has(form.type)
      ? form.pointsValue
      : form.type === 'multiple_choice'
      ? Math.max(0, ...form.mcOptions.map((o) => o.points))
      : form.type === 'true_false'
      ? Math.max(form.tfTruePoints, form.tfFalsePoints)
      : form.type === 'multi_select'
      ? form.msOptions.reduce((sum, o) => sum + (o.points > 0 ? o.points : 0), 0)
      : Math.max(0, ...form.fibAnswers.map((a) => a.points));
  return {
    type: form.type,
    grading_type: form.grading,
    prompt: form.prompt,
    config,
    answer_data,
    time_limit_seconds: form.timeLimitSeconds,
    points_value,
  };
}

type SetField = <K extends keyof FormState>(key: K, value: FormState[K]) => void;

function NumField({ label, value, onChange, className = 'w-24' }: {
  label: string; value: number; onChange: (v: number) => void; className?: string;
}) {
  return (
    <label className="block">
      <span className="block text-xs text-fg-muted mb-1">{label}</span>
      <Input
        type="number"
        step="any"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className={`${className} text-sm`}
      />
    </label>
  );
}

/**
 * Pick / preview / remove one image from the course library (T8). `compact` is the
 * small square used on option rows.
 */
function ImageField({
  courseId,
  value,
  onChange,
  label,
  compact = false,
}: {
  courseId: number;
  value: ImageRef | null;
  onChange: (image: ImageInfo | null) => void;
  label: string;
  compact?: boolean;
}) {
  const [picking, setPicking] = useState(false);
  const picker = picking && (
    <ImagePicker
      courseId={courseId}
      title={label}
      onPick={(img) => {
        setPicking(false);
        onChange(img);
      }}
      onClose={() => setPicking(false)}
    />
  );

  if (compact) {
    return (
      <>
        {value ? (
          <span className="relative shrink-0">
            <button type="button" onClick={() => setPicking(true)} aria-label={`Change ${label.toLowerCase()}`}>
              <img src={imageUrl(value.id)} alt="" className="h-9 w-9 rounded object-cover border border-line-strong" />
            </button>
            <button
              type="button"
              onClick={() => onChange(null)}
              aria-label={`Remove ${label.toLowerCase()}`}
              className="absolute -top-1.5 -right-1.5 rounded-full bg-surface-sunken text-fg-muted hover:text-fg"
            >
              <X size={12} />
            </button>
          </span>
        ) : (
          <Button type="button" variant="ghost" size="sm" onClick={() => setPicking(true)} aria-label={`Add ${label.toLowerCase()}`}>
            <ImagePlus size={14} />
          </Button>
        )}
        {picker}
      </>
    );
  }

  return (
    <div>
      <span className="block text-xs text-fg-muted mb-1">{label}</span>
      {value ? (
        <div className="flex items-start gap-3">
          <img src={imageUrl(value.id)} alt="" className="max-h-32 max-w-[12rem] rounded-control border border-line-strong object-contain" />
          <div className="flex flex-col gap-1">
            <Button type="button" variant="outline" size="sm" onClick={() => setPicking(true)}>Change</Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => onChange(null)}>Remove</Button>
          </div>
        </div>
      ) : (
        <Button type="button" variant="outline" size="sm" onClick={() => setPicking(true)}>
          <ImagePlus size={14} className="mr-1" /> Add image
        </Button>
      )}
      {picker}
    </div>
  );
}

function OptionThumb({ id }: { id: string | null | undefined }) {
  return id ? <img src={imageUrl(id)} alt="" loading="lazy" className="h-6 w-6 rounded object-cover" /> : null;
}

const samePoint = (a: Point, b: Point) => Math.abs(a.x - b.x) < 1e-9 && Math.abs(a.y - b.y) < 1e-9;
/** Fractions shown as percentages in the image-mode inputs. */
const pct = (f: number) => Number((f * 100).toFixed(2));

function PinDropFields({ form, set, courseId }: { form: FormState; set: SetField; courseId: number }) {
  const grid = form.pinGrid;
  const onImage = form.pinMode === 'image';
  const problem = onImage ? null : gridProblem(grid);
  const accuracy = form.grading === 'ACCURACY';
  const setGrid = (key: keyof Grid, v: number) => set('pinGrid', { ...grid, [key]: v });
  const [aspectNote, setAspectNote] = useState('');

  // Grid <-> image changes the units, so the answer starts over (T8 section 5.2).
  function switchMode(mode: 'grid' | 'image') {
    if (mode === form.pinMode) return;
    const centre = onImage ? IMAGE_CENTRE : gridCentre(grid);
    if (
      accuracy &&
      !samePoint(form.pinTarget, centre) &&
      !confirm('Switching the background resets the target and the credit circles. Continue?')
    ) {
      return;
    }
    const radii = mode === 'image' ? IMAGE_RADII : GRID_RADII;
    set('pinMode', mode);
    set('pinTarget', mode === 'image' ? IMAGE_CENTRE : gridCentre(grid));
    set('pinFull', radii.full);
    set('pinZero', radii.zero);
    setAspectNote('');
  }

  // A different picture keeps the target and radii: they are fractions, so still valid.
  function pickImage(img: ImageInfo | null) {
    const before = form.pinImage;
    if (img && before && before.width && before.height) {
      const was = before.width / before.height;
      const now = img.width / img.height;
      setAspectNote(
        Math.abs(now - was) / was > 0.01
          ? 'This picture has a different shape from the last one. Check the target and circles below.'
          : '',
      );
    }
    set('pinImage', img ? refOf(img) : null);
  }

  const background = (
    <div className="flex items-center gap-3 text-sm text-fg-muted">
      <span className="text-xs text-fg-muted">Background</span>
      {(['grid', 'image'] as const).map((mode) => (
        <label key={mode} className="flex items-center gap-1">
          <input type="radio" name="pin-background" checked={form.pinMode === mode} onChange={() => switchMode(mode)} />
          {mode === 'grid' ? 'Grid' : 'Image'}
        </label>
      ))}
    </div>
  );

  if (onImage) {
    const image = form.pinImage;
    return (
      <div className="space-y-3">
        {background}
        <ImageField courseId={courseId} value={image} onChange={pickImage} label="Background image" />
        {aspectNote && <p className="text-warning-fg text-xs">{aspectNote}</p>}
        {accuracy && (
          <div className="flex flex-wrap gap-3 items-end">
            <NumField label="Target across (%)" value={pct(form.pinTarget.x)} onChange={(v) => set('pinTarget', { ...form.pinTarget, x: v / 100 })} className="w-32" />
            <NumField label="Target down (%)" value={pct(form.pinTarget.y)} onChange={(v) => set('pinTarget', { ...form.pinTarget, y: v / 100 })} className="w-32" />
            <NumField label="Full credit within (% of width)" value={pct(form.pinFull)} onChange={(v) => set('pinFull', v / 100)} className="w-40" />
            <NumField label="No credit beyond (% of width)" value={pct(form.pinZero)} onChange={(v) => set('pinZero', v / 100)} className="w-40" />
          </div>
        )}
        {image && image.width > 0 ? (
          <div className="max-w-md">
            {accuracy && (
              <p className="text-xs text-fg-muted mb-1">
                Click the picture to set the target ({pct(form.pinTarget.x)}% across, {pct(form.pinTarget.y)}% down).
                Points fall off linearly between the two circles.
              </p>
            )}
            <GridCanvas
              image={{ url: imageUrl(image.id), width: image.width, height: image.height }}
              target={accuracy ? form.pinTarget : null}
              fullRadius={accuracy ? form.pinFull : undefined}
              zeroRadius={accuracy ? form.pinZero : undefined}
              onPick={
                accuracy
                  ? (p) => set('pinTarget', { x: Number(p.x.toFixed(4)), y: Number(p.y.toFixed(4)) })
                  : undefined
              }
              maxHeightVh={0.5}
              label={accuracy ? 'Click to set the target, or use the arrow keys' : 'Image preview'}
            />
          </div>
        ) : (
          !image && <p className="text-fg-subtle text-xs">Choose the picture players will pin on.</p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {background}
      <div>
        <span className="block text-xs text-fg-muted mb-2">Coordinate grid (x and y share one unit, so cells are square)</span>
        <div className="flex flex-wrap gap-3 items-end">
          <NumField label="x min" value={grid.xMin} onChange={(v) => setGrid('xMin', v)} />
          <NumField label="x max" value={grid.xMax} onChange={(v) => setGrid('xMax', v)} />
          <NumField label="y min" value={grid.yMin} onChange={(v) => setGrid('yMin', v)} />
          <NumField label="y max" value={grid.yMax} onChange={(v) => setGrid('yMax', v)} />
          <NumField label="Step" value={grid.step} onChange={(v) => setGrid('step', v)} />
          <label className="flex items-center gap-2 text-sm text-fg-muted pb-2">
            <input type="checkbox" checked={form.pinSnap} onChange={(e) => set('pinSnap', e.target.checked)} />
            Snap pins to grid points
          </label>
        </div>
        {problem && <p className="text-warning-fg text-xs mt-1">{problem}</p>}
      </div>

      {accuracy && (
        <div className="flex flex-wrap gap-3 items-end">
          <NumField label="Target x" value={form.pinTarget.x} onChange={(v) => set('pinTarget', { ...form.pinTarget, x: v })} />
          <NumField label="Target y" value={form.pinTarget.y} onChange={(v) => set('pinTarget', { ...form.pinTarget, y: v })} />
          <NumField label="Full credit within" value={form.pinFull} onChange={(v) => set('pinFull', v)} className="w-32" />
          <NumField label="No credit beyond" value={form.pinZero} onChange={(v) => set('pinZero', v)} className="w-32" />
        </div>
      )}

      {!problem && (
        <div className="max-w-md">
          {accuracy && (
            <p className="text-xs text-fg-muted mb-1">
              Click the grid to set the target {formatPoint(form.pinTarget)}. Points fall off linearly
              between the two circles.
            </p>
          )}
          <GridCanvas
            grid={grid}
            target={accuracy ? form.pinTarget : null}
            fullRadius={accuracy ? form.pinFull : undefined}
            zeroRadius={accuracy ? form.pinZero : undefined}
            onPick={
              accuracy
                ? (p) => set('pinTarget', form.pinSnap ? snapPoint(p, grid) : { x: Number(p.x.toFixed(2)), y: Number(p.y.toFixed(2)) })
                : undefined
            }
            maxHeightVh={0.5}
            label={accuracy ? 'Click to set the target, or use the arrow keys' : 'Grid preview'}
          />
        </div>
      )}
    </div>
  );
}

function EstimateFields({ form, set }: { form: FormState; set: SetField }) {
  const unitSuffix = form.estMode === 'relative' ? '%' : form.estUnit.trim() || 'units';
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-3 items-end">
        <label className="block">
          <span className="block text-xs text-fg-muted mb-1">Unit (optional)</span>
          <Input
            value={form.estUnit}
            maxLength={20}
            placeholder="e.g. years"
            onChange={(e) => set('estUnit', e.target.value)}
            className="w-36 text-sm"
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-fg-muted pb-2">
          <input type="checkbox" checked={form.estInteger} onChange={(e) => set('estInteger', e.target.checked)} />
          Whole numbers only
        </label>
      </div>

      {form.grading === 'ACCURACY' && (
        <>
          <div className="flex flex-wrap gap-3 items-end">
            <NumField label="Correct answer" value={form.estAnswer} onChange={(v) => set('estAnswer', v)} className="w-36" />
            <label className="block">
              <span className="block text-xs text-fg-muted mb-1">Tolerance</span>
              <select
                className="rounded-control border border-line-strong bg-surface-sunken px-3 py-2 text-fg text-sm focus:border-focus"
                value={form.estMode}
                onChange={(e) => set('estMode', e.target.value as ToleranceMode)}
              >
                <option value="relative">Percent of the answer</option>
                <option value="absolute">Fixed amount (units)</option>
              </select>
            </label>
            <NumField label={`Full credit within (${unitSuffix})`} value={form.estFull} onChange={(v) => set('estFull', v)} className="w-36" />
            <NumField label={`No credit beyond (${unitSuffix})`} value={form.estZero} onChange={(v) => set('estZero', v)} className="w-36" />
          </div>
          <p className="text-fg-subtle text-xs">
            Full points within {form.estFull}
            {form.estMode === 'relative' ? '%' : ` ${unitSuffix}`} of {withUnit(form.estAnswer, form.estUnit.trim())},
            falling linearly to none at {form.estZero}
            {form.estMode === 'relative' ? '%' : ` ${unitSuffix}`}. Use a fixed amount for years and small
            ranges (2015 is only 0.5% away from 2005).
          </p>
        </>
      )}
    </div>
  );
}

function QuestionForm({
  initial,
  courseId,
  onSave,
  onCancel,
  saving,
}: {
  initial: FormState;
  courseId: number;
  onSave: (payload: ReturnType<typeof formToPayload>) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [form, setForm] = useState<FormState>(initial);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <div className="space-y-4">
      {/* Type + grading */}
      <div className="flex gap-3">
        <div className="flex-1">
          <label className="block text-xs text-fg-muted mb-1">Question type</label>
          <select
            className="w-full rounded-control border border-line-strong bg-surface-sunken px-3 py-2 text-fg text-sm focus:border-focus"
            value={form.type}
            onChange={(e) => set('type', e.target.value as QuestionType)}
          >
            <option value="multiple_choice">Multiple Choice</option>
            <option value="true_false">True / False</option>
            <option value="fill_in_the_blank">Fill in the Blank</option>
            <option value="multi_select">Multi-Select (Select All That Apply)</option>
            <option value="pin_drop">Pin It (place a point on a grid or picture)</option>
            <option value="estimate">Estimate (closest number wins points)</option>
          </select>
        </div>
        <div className="flex-1">
          <label className="block text-xs text-fg-muted mb-1">Grading</label>
          <select
            className="w-full rounded-control border border-line-strong bg-surface-sunken px-3 py-2 text-fg text-sm focus:border-focus"
            value={form.grading}
            onChange={(e) => set('grading', e.target.value as GradingType)}
          >
            <option value="ACCURACY">Accuracy</option>
            <option value="COMPLETENESS">Completeness</option>
          </select>
        </div>
      </div>

      {/* Prompt */}
      <div>
        <label className="block text-xs text-fg-muted mb-1">Prompt</label>
        <textarea
          className="w-full rounded-control border border-line-strong bg-surface-sunken px-3 py-2 text-fg placeholder:text-fg-subtle resize-none text-sm focus:border-focus"
          rows={3}
          placeholder="Question text…"
          value={form.prompt}
          onChange={(e) => set('prompt', e.target.value)}
          required
        />
      </div>

      <ImageField
        courseId={courseId}
        value={form.promptImage}
        onChange={(img) => set('promptImage', img ? refOf(img) : null)}
        label="Prompt image (optional, shown on the projector)"
      />

      {/* Type-specific */}
      {form.type === 'multiple_choice' && (
        <div>
          <label className="block text-xs text-fg-muted mb-2">Options</label>
          {form.grading === 'ACCURACY' && (
            <div className="flex gap-2 mb-1 px-0.5">
              <span className="w-9 text-xs text-fg-subtle">Image</span>
              <span className="flex-1 text-xs text-fg-subtle">Text / alt text</span>
              <span className="w-24 text-xs text-fg-subtle">Points</span>
              {form.mcOptions.length > 2 && <span className="w-7" />}
            </div>
          )}
          <div className="space-y-2">
            {form.mcOptions.map((opt, i) => (
              <div key={i} className="flex gap-2 items-center">
                <span className="w-9 flex justify-center">
                  <ImageField
                    compact
                    courseId={courseId}
                    value={opt.image ?? null}
                    onChange={(img) => {
                      const opts = [...form.mcOptions];
                      opts[i] = { ...opts[i], image: img ? refOf(img) : null };
                      set('mcOptions', opts);
                    }}
                    label={`Image for option ${i + 1}`}
                  />
                </span>
                <Input
                  placeholder={`Option ${i + 1}`}
                  value={opt.text}
                  onChange={(e) => {
                    const opts = [...form.mcOptions];
                    opts[i] = { ...opts[i], text: e.target.value };
                    set('mcOptions', opts);
                  }}
                  className="flex-1 text-sm"
                />
                {form.grading === 'ACCURACY' && (
                  <Input
                    type="number"
                    placeholder="pts"
                    value={opt.points}
                    onChange={(e) => {
                      const opts = [...form.mcOptions];
                      opts[i] = { ...opts[i], points: Number(e.target.value) };
                      set('mcOptions', opts);
                    }}
                    className="w-24 text-sm"
                    min="0"
                    step="any"
                  />
                )}
                {form.mcOptions.length > 2 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => set('mcOptions', form.mcOptions.filter((_, j) => j !== i))}
                  >
                    <Trash2 size={12} />
                  </Button>
                )}
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => set('mcOptions', [...form.mcOptions, { text: '', points: 0 }])}
            >
              <Plus size={12} className="mr-1" /> Add option
            </Button>
          </div>
        </div>
      )}

      {form.type === 'multi_select' && (
        <div>
          <label className="block text-xs text-fg-muted mb-2">Options</label>
          {form.grading === 'ACCURACY' && (
            <div className="flex gap-2 mb-1 px-0.5">
              <span className="w-9 text-xs text-fg-subtle">Image</span>
              <span className="flex-1 text-xs text-fg-subtle">Text / alt text</span>
              <span className="w-24 text-xs text-fg-subtle">Points (neg = penalty)</span>
              {form.msOptions.length > 2 && <span className="w-7" />}
            </div>
          )}
          <div className="space-y-2">
            {form.msOptions.map((opt, i) => (
              <div key={i} className="flex gap-2 items-center">
                <span className="w-9 flex justify-center">
                  <ImageField
                    compact
                    courseId={courseId}
                    value={opt.image ?? null}
                    onChange={(img) => {
                      const opts = [...form.msOptions];
                      opts[i] = { ...opts[i], image: img ? refOf(img) : null };
                      set('msOptions', opts);
                    }}
                    label={`Image for option ${i + 1}`}
                  />
                </span>
                <Input
                  placeholder={`Option ${i + 1}`}
                  value={opt.text}
                  onChange={(e) => {
                    const opts = [...form.msOptions];
                    opts[i] = { ...opts[i], text: e.target.value };
                    set('msOptions', opts);
                  }}
                  className="flex-1 text-sm"
                />
                {form.grading === 'ACCURACY' && (
                  <Input
                    type="number"
                    placeholder="pts"
                    value={opt.points}
                    onChange={(e) => {
                      const opts = [...form.msOptions];
                      opts[i] = { ...opts[i], points: Number(e.target.value) };
                      set('msOptions', opts);
                    }}
                    className="w-24 text-sm"
                    step="any"
                  />
                )}
                {form.msOptions.length > 2 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => set('msOptions', form.msOptions.filter((_, j) => j !== i))}
                  >
                    <Trash2 size={12} />
                  </Button>
                )}
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => set('msOptions', [...form.msOptions, { text: '', points: 1 }])}
            >
              <Plus size={12} className="mr-1" /> Add option
            </Button>
          </div>
          {form.grading === 'ACCURACY' && (
            <p className="text-fg-subtle text-xs mt-1">
              Correct options: positive pts. Distractors: negative pts (penalty). Score = sum of selected, capped at 0.
            </p>
          )}
        </div>
      )}

      {form.type === 'true_false' && form.grading === 'ACCURACY' && (
        <div>
          <label className="block text-xs text-fg-muted mb-2">Points per answer</label>
          <div className="flex gap-4">
            <div>
              <span className="text-fg-muted text-sm">True:</span>
              <Input
                type="number"
                value={form.tfTruePoints}
                onChange={(e) => set('tfTruePoints', Number(e.target.value))}
                className="w-28 mt-1 text-sm"
                min="0"
                step="any"
              />
            </div>
            <div>
              <span className="text-fg-muted text-sm">False:</span>
              <Input
                type="number"
                value={form.tfFalsePoints}
                onChange={(e) => set('tfFalsePoints', Number(e.target.value))}
                className="w-28 mt-1 text-sm"
                min="0"
                step="any"
              />
            </div>
          </div>
        </div>
      )}

      {form.type === 'fill_in_the_blank' && form.grading === 'ACCURACY' && (
        <div className="space-y-3">
          <div>
            <label className="block text-xs text-fg-muted mb-2">Accepted answers</label>
            <div className="flex gap-2 mb-1 px-0.5">
              <span className="flex-1 text-xs text-fg-subtle">Answer text</span>
              <span className="w-24 text-xs text-fg-subtle">Points</span>
              {form.fibAnswers.length > 1 && <span className="w-7" />}
            </div>
            <div className="space-y-2">
              {form.fibAnswers.map((ans, i) => (
                <div key={i} className="flex gap-2 items-center">
                  <Input
                    placeholder={`Answer ${i + 1}`}
                    value={ans.text}
                    onChange={(e) => {
                      const answers = [...form.fibAnswers];
                      answers[i] = { ...answers[i], text: e.target.value };
                      set('fibAnswers', answers);
                    }}
                    className="flex-1 text-sm"
                  />
                  <Input
                    type="number"
                    placeholder="pts"
                    value={ans.points}
                    onChange={(e) => {
                      const answers = [...form.fibAnswers];
                      answers[i] = { ...answers[i], points: Number(e.target.value) };
                      set('fibAnswers', answers);
                    }}
                    className="w-24 text-sm"
                    min="0"
                    step="any"
                  />
                  {form.fibAnswers.length > 1 && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => set('fibAnswers', form.fibAnswers.filter((_, j) => j !== i))}
                    >
                      <Trash2 size={12} />
                    </Button>
                  )}
                </div>
              ))}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => set('fibAnswers', [...form.fibAnswers, { text: '', points: 1 }])}
              >
                <Plus size={12} className="mr-1" /> Add answer
              </Button>
            </div>
          </div>
          <div>
            <label className="block text-xs text-fg-muted mb-1">Edit distance tolerance (fuzzy match)</label>
            <Input
              type="number"
              value={form.fibEditDistance}
              onChange={(e) => set('fibEditDistance', Number(e.target.value))}
              className="w-28 text-sm"
              min="0"
            />
          </div>
        </div>
      )}

      {form.type === 'pin_drop' && <PinDropFields form={form} set={set} courseId={courseId} />}

      {form.type === 'estimate' && <EstimateFields form={form} set={set} />}

      {/* Time + points */}
      <div className="flex gap-4">
        <div>
          <label className="block text-xs text-fg-muted mb-1">Time limit (seconds)</label>
          <Input
            type="number"
            value={form.timeLimitSeconds}
            onChange={(e) => set('timeLimitSeconds', Number(e.target.value))}
            className="w-28 text-sm"
            min="2"
            max="300"
          />
        </div>
        {(form.grading === 'COMPLETENESS' || DISTANCE_TYPES.has(form.type)) && (
          <div>
            <label className="block text-xs text-fg-muted mb-1">
              {form.grading === 'ACCURACY' ? 'Points for a perfect answer' : 'Points value'}
            </label>
            <Input
              type="number"
              value={form.pointsValue}
              onChange={(e) => set('pointsValue', Number(e.target.value))}
              className="w-28 text-sm"
              min="0"
              max="100000"
              step="any"
            />
          </div>
        )}
      </div>

      <div className="flex gap-3">
        <Button type="button" onClick={() => onSave(formToPayload(form))} disabled={saving}>
          {saving ? 'Saving\u2026' : 'Save Question'}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </div>
  );
}

// ---- Main page ----

export default function QuestionEditorPage() {
  const { gameId } = useParams<{ gameId: string }>();
  const navigate = useNavigate();
  const [game, setGame] = useState<Game | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [downloading, setDownloading] = useState(false);

  async function load() {
    try {
      const [g, qs] = await Promise.all([
        api.get<Game>(`/host/games/${gameId}`),
        api.get<Question[]>(`/host/games/${gameId}/questions`),
      ]);
      setGame(g);
      setQuestions(qs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [gameId]);

  async function addQuestion(payload: ReturnType<typeof formToPayload>) {
    setSaving(true);
    setError('');
    try {
      await api.post(`/host/games/${gameId}/questions`, payload);
      setShowAddForm(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save question');
    } finally {
      setSaving(false);
    }
  }

  async function updateQuestion(id: number, payload: ReturnType<typeof formToPayload>) {
    setSaving(true);
    setError('');
    try {
      await api.put(`/host/games/${gameId}/questions/${id}`, payload);
      setEditingId(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update question');
    } finally {
      setSaving(false);
    }
  }

  async function deleteQuestion(id: number) {
    if (!confirm('Delete this question?')) return;
    try {
      await api.delete(`/host/games/${gameId}/questions/${id}`);
      setQuestions((prev) => prev.filter((q) => q.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete question');
    }
  }

  async function moveQuestion(index: number, direction: -1 | 1) {
    const newOrder = [...questions];
    const target = index + direction;
    if (target < 0 || target >= newOrder.length) return;
    [newOrder[index], newOrder[target]] = [newOrder[target], newOrder[index]];
    try {
      await api.post(`/host/games/${gameId}/questions/reorder`, {
        order: newOrder.map((q) => q.id),
      });
      setQuestions(newOrder);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reorder');
    }
  }

  async function handleExport() {
    setDownloading(true);
    setError('');
    try {
      await api.download(`/host/games/${gameId}/export`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed');
    } finally {
      setDownloading(false);
    }
  }

  const typeLabel: Record<QuestionType, string> = {
    multiple_choice: 'MC',
    true_false: 'T/F',
    fill_in_the_blank: 'Fill',
    multi_select: 'Multi',
    pin_drop: 'Pin It',
    estimate: 'Estimate',
  };

  if (loading) return <div className="p-8 text-fg-muted">Loading…</div>;

  return (
    <div className="p-8 max-w-4xl space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <button
            onClick={() => navigate(game ? `/manage/games?course=${game.course_id}` : '/manage/games')}
            className="flex items-center gap-2 text-fg-muted hover:text-fg text-sm mb-2"
          >
            <ArrowLeft size={14} /> Back to Games
          </button>
          <h2 className="text-2xl font-bold text-fg">{game?.title}</h2>
          <p className="text-fg-muted text-sm mt-0.5">{questions.length} question{questions.length !== 1 ? 's' : ''}</p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void handleExport()}
            disabled={downloading}
          >
            <Download size={14} className="mr-1" />
            {downloading ? 'Exporting\u2026' : 'Export JSON'}
          </Button>
          <Button size="sm" onClick={() => { setShowAddForm(true); setEditingId(null); }}>
            <Plus size={14} className="mr-1" /> Add Question
          </Button>
        </div>
      </div>

      {error && <p className="text-danger-fg text-sm">{error}</p>}

      {/* Add question form */}
      {showAddForm && (
        <Card>
          <CardHeader><h3 className="font-semibold text-fg">New Question</h3></CardHeader>
          <CardContent>
            <QuestionForm
              initial={defaultForm()}
              courseId={game?.course_id ?? 0}
              onSave={(payload) => void addQuestion(payload)}
              onCancel={() => setShowAddForm(false)}
              saving={saving}
            />
          </CardContent>
        </Card>
      )}

      {/* Question list */}
      {questions.length === 0 && !showAddForm && (
        <p className="text-fg-muted">No questions yet. Add one above.</p>
      )}

      <div className="space-y-4">
        {questions.map((q, i) => (
          <Card key={q.id}>
            {editingId === q.id ? (
              <>
                <CardHeader>
                  <h3 className="font-semibold text-fg">Edit Question {i + 1}</h3>
                </CardHeader>
                <CardContent>
                  <QuestionForm
                    initial={questionToForm(q)}
                    courseId={game?.course_id ?? 0}
                    onSave={(payload) => void updateQuestion(q.id, payload)}
                    onCancel={() => setEditingId(null)}
                    saving={saving}
                  />
                </CardContent>
              </>
            ) : (
              <div className="flex items-start gap-4 px-6 py-4">
                {/* Reorder buttons */}
                <div className="flex flex-col gap-1 mt-1">
                  <button
                    onClick={() => void moveQuestion(i, -1)}
                    disabled={i === 0}
                    className="text-fg-subtle hover:text-fg disabled:opacity-20"
                  >
                    <ChevronUp size={16} />
                  </button>
                  <button
                    onClick={() => void moveQuestion(i, 1)}
                    disabled={i === questions.length - 1}
                    className="text-fg-subtle hover:text-fg disabled:opacity-20"
                  >
                    <ChevronDown size={16} />
                  </button>
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-fg-subtle text-xs font-mono">Q{i + 1}</span>
                    <span className="px-1.5 py-0.5 rounded text-xs bg-surface-hover text-fg-muted">
                      {typeLabel[q.type]}
                    </span>
                    <span className="px-1.5 py-0.5 rounded text-xs bg-surface-hover text-fg-muted">
                      {q.grading_type}
                    </span>
                    <span className="text-fg-subtle text-xs">{q.time_limit_seconds}s · {q.points_value}pts</span>
                  </div>
                  <p className="text-fg text-sm leading-relaxed">{q.prompt}</p>
                  {typeof q.config['promptImageId'] === 'string' && (
                    <img
                      src={imageUrl(q.config['promptImageId'])}
                      alt=""
                      loading="lazy"
                      className="mt-2 max-h-24 rounded border border-line object-contain"
                    />
                  )}

                  {q.type === 'multiple_choice' && (
                    <div className="mt-2 space-y-1">
                      {((q.config['options'] as string[]) ?? []).map((opt, oi) => {
                        const pts = ((q.answer_data['answer_points'] as number[]) ?? [])[oi] ?? 0;
                        return (
                          <div key={oi} className="flex items-center gap-2 text-xs">
                            <span className={pts > 0 ? 'text-success-fg' : 'text-fg-subtle'}>
                              {pts > 0 ? '\u2713' : '\u25cb'}
                            </span>
                            <OptionThumb id={((q.config['optionImages'] as (string | null)[]) ?? [])[oi]} />
                            <span className={pts > 0 ? 'text-fg' : 'text-fg-muted'}>{opt}</span>
                            {pts > 0 && <span className="text-fg-subtle">({pts}pts)</span>}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {q.type === 'true_false' && (
                    <div className="mt-2 flex gap-4 text-xs">
                      {(['true', 'false'] as const).map((k) => {
                        const pts = (q.answer_data['answer_points'] as Record<string, number>)?.[k] ?? 0;
                        return (
                          <span key={k} className={pts > 0 ? 'text-success-fg' : 'text-fg-subtle'}>
                            {k.charAt(0).toUpperCase() + k.slice(1)}: {pts}pts
                          </span>
                        );
                      })}
                    </div>
                  )}

                  {q.type === 'fill_in_the_blank' && (
                    <div className="mt-2 text-xs text-fg-muted">
                      Accepted: {((q.answer_data['acceptedAnswers'] as string[]) ?? []).join(', ')}
                      {(q.answer_data['editDistance'] as number) > 0 && (
                        <span className="ml-2 text-fg-subtle">(±{q.answer_data['editDistance'] as number} edit distance)</span>
                      )}
                    </div>
                  )}

                  {q.type === 'pin_drop' && (() => {
                    const g = q.config['grid'] as Grid | undefined;
                    const t = q.answer_data['target'] as Point | undefined;
                    const img = q.config['image'] as { imageId: string; width: number; height: number } | undefined;
                    if (img) {
                      const full = q.answer_data['fullRadius'] as number | undefined;
                      const zero = q.answer_data['zeroRadius'] as number | undefined;
                      return (
                        <div className="mt-2 flex items-center gap-2 text-xs text-fg-muted">
                          <img src={imageUrl(img.imageId)} alt="" loading="lazy" className="h-10 rounded border border-line" />
                          <span>On an image ({img.width}×{img.height})</span>
                          {t && full !== undefined && zero !== undefined && (
                            <span className="text-success-fg">
                              Target {pct(t.x)}% across, {pct(t.y)}% down · full within {pct(full)}%, none beyond {pct(zero)}% of the width
                            </span>
                          )}
                        </div>
                      );
                    }
                    return (
                      <div className="mt-2 text-xs text-fg-muted">
                        {g && <>Grid x {g.xMin}…{g.xMax}, y {g.yMin}…{g.yMax}, step {g.step}{q.config['snap'] ? ' · snaps' : ''}</>}
                        {t && (
                          <span className="ml-2 text-success-fg">
                            Target {formatPoint(t)} · full within {q.answer_data['fullRadius'] as number}, none beyond {q.answer_data['zeroRadius'] as number}
                          </span>
                        )}
                      </div>
                    );
                  })()}

                  {q.type === 'estimate' && (() => {
                    const unit = (q.config['unit'] as string | undefined) ?? '';
                    const tol = q.answer_data['tolerance'] as { mode: ToleranceMode; full: number; zero: number } | undefined;
                    const suffix = tol?.mode === 'relative' ? '%' : unit ? ` ${unit}` : '';
                    return (
                      <div className="mt-2 text-xs text-fg-muted">
                        {typeof q.answer_data['answer'] === 'number' && (
                          <span className="text-success-fg">Answer {withUnit(q.answer_data['answer'] as number, unit)}</span>
                        )}
                        {tol && <span className="ml-2">full within {tol.full}{suffix}, none beyond {tol.zero}{suffix}</span>}
                        {q.config['integer'] ? <span className="ml-2 text-fg-subtle">· whole numbers</span> : null}
                        {!tol && unit && <span>Unit: {unit}</span>}
                      </div>
                    );
                  })()}

                  {q.type === 'multi_select' && (
                    <div className="mt-2 space-y-1">
                      {((q.config['options'] as string[]) ?? []).map((opt, oi) => {
                        const pts = ((q.answer_data['answer_points'] as number[]) ?? [])[oi] ?? 0;
                        const isCorrect = pts > 0;
                        return (
                          <div key={oi} className="flex items-center gap-2 text-xs">
                            <span className={isCorrect ? 'text-success-fg' : pts < 0 ? 'text-danger-fg' : 'text-fg-subtle'}>
                              {isCorrect ? '\u2713' : pts < 0 ? '\u2212' : '\u25cb'}
                            </span>
                            <OptionThumb id={((q.config['optionImages'] as (string | null)[]) ?? [])[oi]} />
                            <span className={isCorrect ? 'text-fg' : 'text-fg-muted'}>{opt}</span>
                            {pts !== 0 && <span className="text-fg-subtle">({pts > 0 ? '+' : ''}{pts}pts)</span>}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                <div className="flex gap-1 shrink-0">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => { setEditingId(q.id); setShowAddForm(false); }}
                  >
                    Edit
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => void deleteQuestion(q.id)}
                  >
                    <Trash2 size={14} />
                  </Button>
                </div>
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
