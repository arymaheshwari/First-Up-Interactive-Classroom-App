import { useEffect, useState } from 'react';
import { useGame } from './GameLayout';
import { Button } from '../../components/ui/button';
import { GridCanvas } from '../../components/question/GridCanvas';
import { imageUrl } from '../../lib/images';
import { NumberLine } from '../../components/question/NumberLine';
import { asNumbers, asPoints, closestTo, formatImagePoint, formatPoint, median, pinDistance, withUnit } from '../../lib/format';
import type { AnswerReveal, HostResultsPayload, QuestionPayload } from '../../types/game';

const RESULTS_DISPLAY_SECONDS = 10;

function optionLabel(i: number): string {
  return String.fromCharCode(65 + i);
}

// ---------------------------------------------------------------------------
// Levenshtein distance — used to colour word-cloud entries for FITB questions
// ---------------------------------------------------------------------------

function levenshtein(a: string, b: string): number {
  const m = a.length, n = b.length;
  const dp: number[][] = Array.from({ length: m + 1 }, (_, i) =>
    Array.from({ length: n + 1 }, (_, j) => (i === 0 ? j : j === 0 ? i : 0))
  );
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] =
        a[i - 1] === b[j - 1]
          ? dp[i - 1][j - 1]
          : 1 + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
    }
  }
  return dp[m][n];
}

// ---------------------------------------------------------------------------
// Word Cloud — for fill_in_the_blank questions
// ---------------------------------------------------------------------------

interface WordCloudProps {
  distribution: Record<string, number>;
  answerReveal: AnswerReveal;
  totalAnswered: number;
  totalPlayers: number;
}

function WordCloud({ distribution, answerReveal, totalAnswered, totalPlayers }: WordCloudProps) {
  const entries = Object.entries(distribution).sort(([, a], [, b]) => b - a);
  const maxCount = Math.max(...entries.map(([, c]) => c), 1);

  const isAccuracy =
    'type' in answerReveal && answerReveal.type === 'fill_in_the_blank';
  const acceptedAnswers: string[] =
    isAccuracy && 'acceptedAnswers' in answerReveal
      ? (answerReveal as { type: 'fill_in_the_blank'; acceptedAnswers: string[]; editDistance: number }).acceptedAnswers.map(a => a.toLowerCase())
      : [];
  const editDistance: number =
    isAccuracy && 'editDistance' in answerReveal
      ? (answerReveal as { type: 'fill_in_the_blank'; acceptedAnswers: string[]; editDistance: number }).editDistance
      : 0;

  function sizeClass(count: number): string {
    const f = count / maxCount;
    if (f > 0.75) return 'text-5xl font-black';
    if (f > 0.5)  return 'text-4xl font-bold';
    if (f > 0.25) return 'text-3xl font-semibold';
    if (f > 0.1)  return 'text-2xl font-medium';
    return 'text-xl';
  }

  function isCorrectWord(word: string): boolean {
    if (!isAccuracy || acceptedAnswers.length === 0) return false;
    return acceptedAnswers.some(a => levenshtein(word.toLowerCase(), a) <= editDistance);
  }

  return (
    <div className="w-full max-w-5xl flex flex-col gap-4">
      {isAccuracy && acceptedAnswers.length > 0 && (
        <p className="text-center text-fg-muted text-host-lg">
          Correct answer:{' '}
          <span className="text-success-fg font-semibold">
            {(answerReveal as { acceptedAnswers: string[] }).acceptedAnswers.join(' / ')}
            {editDistance > 0 && (
              <span className="text-fg-muted font-normal text-xl ml-2">(±{editDistance} typo{editDistance === 1 ? '' : 's'})</span>
            )}
          </span>
        </p>
      )}

      <div className="flex flex-wrap gap-x-6 gap-y-3 justify-center items-center min-h-32 p-6 rounded-card border border-line bg-surface shadow-card">
        {entries.map(([word, count]) => (
          <span
            key={word}
            title={`${count} player${count !== 1 ? 's' : ''}`}
            className={`${sizeClass(count)} transition-colors ${
              isCorrectWord(word) ? 'text-success-fg' : 'text-fg-muted'
            }`}
          >
            {/* Colour isn't the only cue: accepted answers also carry a check (WCAG 1.4.1). */}
            {isCorrectWord(word) && <span aria-label="accepted">✓ </span>}
            {word}
          </span>
        ))}
        {entries.length === 0 && (
          <p className="text-fg-muted text-host-lg">No answers submitted</p>
        )}
      </div>

      <p className="text-fg text-host-lg text-right">
        {totalAnswered} / {totalPlayers} answered
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Bar Chart — for multiple_choice and true_false
// ---------------------------------------------------------------------------

interface BarChartProps {
  bars: { label: string; count: number; correct: boolean | null; image?: string | null }[];
  totalAnswered: number;
  totalPlayers: number;
}

function AnswerBarChart({ bars, totalAnswered, totalPlayers }: BarChartProps) {
  const maxCount = Math.max(...bars.map(b => b.count), 1);
  const anyImage = bars.some(b => b.image);

  return (
    <div className="w-full max-w-6xl space-y-4">
      {bars.map((bar, i) => {
        const pct = Math.round((bar.count / maxCount) * 100);
        // Fills are graphics: each is >= 3:1 against the sunken track (§4.2).
        const barColor =
          bar.correct === true ? 'bg-success' : bar.correct === false ? 'bg-line-strong' : 'bg-accent';

        return (
          <div key={i} className="flex flex-col gap-2 lg:flex-row lg:items-center lg:gap-5">
            <div className="flex min-w-0 items-start gap-3 lg:w-[28rem] lg:shrink-0">
              {anyImage &&
                (bar.image ? (
                  <img src={imageUrl(bar.image)} alt="" className="h-12 w-12 rounded-control object-cover shrink-0" />
                ) : (
                  <span className="h-12 w-12 shrink-0" />
                ))}
              <div className="min-w-0">
                <span className="block break-words text-fg text-host-lg font-semibold" title={bar.label}>
                  {bar.label}
                </span>
                {bar.correct === true && (
                  <span className="block text-success-fg text-xl font-semibold">✓ Correct</span>
                )}
              </div>
            </div>
            <div className="flex w-full min-w-0 items-center gap-4 lg:w-auto lg:flex-1">
              <div className="h-10 min-w-0 flex-1 rounded-full bg-surface-sunken overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${barColor}`}
                  style={{ width: `${Math.max(pct, bar.count > 0 ? 4 : 0)}%` }}
                />
              </div>
              {/* The count sits in its own column, never on the fill. */}
              <span className="w-16 shrink-0 text-right tabular-nums text-fg text-host-lg font-bold">
                {bar.count}
              </span>
            </div>
          </div>
        );
      })}

      <p className="text-fg text-host-lg text-right pt-1">
        {totalAnswered} / {totalPlayers} answered
      </p>
    </div>
  );
}

function buildBars(
  reveal: AnswerReveal,
  distribution: Record<string, number>,
  options: string[] | undefined,
  optionImages: (string | null)[] = [],
): BarChartProps['bars'] {
  if (reveal.type === 'multiple_choice') {
    const opts = options ?? [];
    return opts.map((opt, i) => ({
      label: `${optionLabel(i)}  ${opt}`,
      count: distribution[String(i)] ?? 0,
      correct: reveal.correctIndices.includes(i),
      image: optionImages[i],
    }));
  }

  if (reveal.type === 'multi_select') {
    const opts = options ?? [];
    return opts.map((opt, i) => ({
      label: `${optionLabel(i)}  ${opt}`,
      count: distribution[String(i)] ?? 0,
      correct: (reveal.answerPoints[i] ?? 0) > 0,
      image: optionImages[i],
    }));
  }

  if (reveal.type === 'true_false') {
    return [
      { label: 'True', count: distribution['true'] ?? 0, correct: reveal.correctValue === true },
      { label: 'False', count: distribution['false'] ?? 0, correct: reveal.correctValue === false },
    ];
  }

  // completeness (non-FITB) — no right/wrong
  if (options && options.length > 0) {
    return options.map((opt, i) => ({
      label: `${optionLabel(i)}  ${opt}`,
      count: distribution[String(i)] ?? 0,
      correct: null,
      image: optionImages[i],
    }));
  }

  if ('true' in distribution || 'false' in distribution) {
    return [
      { label: 'True', count: distribution['true'] ?? 0, correct: null },
      { label: 'False', count: distribution['false'] ?? 0, correct: null },
    ];
  }

  return [];
}

// ---------------------------------------------------------------------------
// pin_drop and estimate — every submitted value, not bucket counts
// ---------------------------------------------------------------------------

function Stat({ label, value, tone = 'text-fg' }: { label: string; value: string; tone?: string }) {
  return (
    <div className="text-center">
      <p className="text-fg-muted text-xl uppercase tracking-widest whitespace-nowrap">{label}</p>
      <p className={`text-host-xl font-bold whitespace-nowrap ${tone}`}>{value}</p>
    </div>
  );
}

function PinResults({ question, results }: { question: QuestionPayload; results: HostResultsPayload }) {
  const { grid, image } = question.config;
  if (!grid && !image) return null;
  const pins = asPoints(results.answerValues);
  const reveal = results.answerReveal.type === 'pin_drop' ? results.answerReveal : null;
  // On a picture, distances are in image widths (T8 D5) and points read as percentages.
  const aspect = image ? image.height / image.width : 1;
  const where = image ? formatImagePoint : formatPoint;
  const dist = (p: { x: number; y: number }) =>
    reveal ? pinDistance(p, reveal.target, aspect) : Infinity;
  const full = reveal ? pins.filter(p => dist(p) <= reveal.fullRadius + 1e-9).length : 0;
  const scored = reveal ? pins.filter(p => dist(p) < reveal.zeroRadius).length : 0;

  return (
    <div className="w-full max-w-4xl flex flex-col gap-6">
      <GridCanvas
        grid={grid}
        image={image ? { url: imageUrl(image.imageId), width: image.width, height: image.height } : undefined}
        pins={pins}
        target={reveal?.target ?? null}
        fullRadius={reveal?.fullRadius}
        zeroRadius={reveal?.zeroRadius}
        label={`${pins.length} pins${reveal ? `, target ${where(reveal.target)}` : ''}`}
      />
      <div className="flex flex-wrap justify-center gap-x-8 gap-y-6">
        {reveal && <Stat label="Target" value={where(reveal.target)} tone="text-success-fg" />}
        {reveal && <Stat label="Full credit" value={`${full}`} tone="text-success-fg" />}
        {reveal && <Stat label="Earned points" value={`${scored}`} />}
        <Stat label="Answered" value={`${results.totalAnswered} / ${results.totalPlayers}`} />
      </div>
    </div>
  );
}

function EstimateResults({ question, results }: { question: QuestionPayload; results: HostResultsPayload }) {
  const values = asNumbers(results.answerValues);
  const reveal = results.answerReveal.type === 'estimate' ? results.answerReveal : null;
  const unit = question.config.unit;
  const mid = median(values);
  const closest = reveal ? closestTo(values, reveal.answer) : null;

  return (
    <div className="w-full max-w-5xl flex flex-col gap-6">
      {values.length > 0 ? (
        <NumberLine values={values} answer={reveal?.answer ?? null} unit={unit} />
      ) : (
        <p className="text-fg-muted text-host-lg text-center py-8">No answers submitted</p>
      )}
      <div className="flex flex-wrap justify-center gap-x-8 gap-y-6">
        {reveal && <Stat label="Answer" value={withUnit(reveal.answer, unit)} tone="text-success-fg" />}
        {mid !== null && <Stat label="Median guess" value={withUnit(mid, unit)} />}
        {closest !== null && <Stat label="Closest guess" value={withUnit(closest, unit)} tone="text-warning-fg" />}
        <Stat label="Answered" value={`${results.totalAnswered} / ${results.totalPlayers}`} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ResultsPage() {
  const { questionResults, currentQuestion, autoAdvance, emitAdvance } = useGame();
  const [countdown, setCountdown] = useState(RESULTS_DISPLAY_SECONDS);

  const isLast = currentQuestion
    ? currentQuestion.questionNumber >= currentQuestion.totalQuestions
    : false;

  useEffect(() => {
    if (!autoAdvance) return;
    setCountdown(RESULTS_DISPLAY_SECONDS);
    const interval = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) { clearInterval(interval); emitAdvance(); return 0; }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [autoAdvance, questionResults, emitAdvance]);

  const isFitb = currentQuestion?.type === 'fill_in_the_blank';

  const bars =
    !isFitb && questionResults
      ? buildBars(
          questionResults.answerReveal,
          questionResults.answerDistribution,
          currentQuestion?.config?.options,
          currentQuestion?.config?.optionImages,
        )
      : [];

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-8 lg:p-12 gap-8">
      <h2 className="text-host-xl font-semibold tracking-tight text-fg">
        Question {currentQuestion?.questionNumber} Results
      </h2>

      {currentQuestion && (
        <p className="text-fg-muted text-host-lg text-center max-w-4xl">
          {currentQuestion.prompt}
        </p>
      )}

      {questionResults && currentQuestion?.type === 'pin_drop' ? (
        <PinResults question={currentQuestion} results={questionResults} />
      ) : questionResults && currentQuestion?.type === 'estimate' ? (
        <EstimateResults question={currentQuestion} results={questionResults} />
      ) : questionResults && isFitb ? (
        <WordCloud
          distribution={questionResults.answerDistribution}
          answerReveal={questionResults.answerReveal}
          totalAnswered={questionResults.totalAnswered}
          totalPlayers={questionResults.totalPlayers}
        />
      ) : questionResults ? (
        <AnswerBarChart
          bars={bars}
          totalAnswered={questionResults.totalAnswered}
          totalPlayers={questionResults.totalPlayers}
        />
      ) : null}

      <div className="flex flex-col items-center gap-2">
        <Button size="xl" onClick={emitAdvance} className="px-10">
          {isLast ? 'Show Final Results' : 'Next Question'}
        </Button>
        {autoAdvance && (
          <p /* theme-check: small-text controls */ className="text-fg-muted text-base tabular-nums">
            Auto-advancing in {countdown}s
          </p>
        )}
      </div>
    </div>
  );
}
