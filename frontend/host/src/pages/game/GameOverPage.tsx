import { Flag, ThumbsDown, ThumbsUp } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useGame } from './GameLayout';
import { Button } from '../../components/ui/button';
import { GridCanvas } from '../../components/question/GridCanvas';
import { NumberLine } from '../../components/question/NumberLine';
import { asNumbers, asPoints, formatImagePoint, formatPoint, median, withUnit } from '../../lib/format';
import { imageUrl } from '../../lib/images';
import type { AnswerReveal, FeedbackCounts, HostQuestionSummaryItem } from '../../types/game';

const TARGET_BUCKETS = 8;

interface Bucket {
  label: string;
  count: number;
  rangeStart: number;
  rangeEnd: number;
}

function chooseWidth(ceiling: number): number {
  const N = ceiling + 1;
  let bestW = 1;
  let bestDiff = Infinity;
  for (let w = 1; w * w <= N; w++) {
    if (N % w !== 0) continue;
    for (const cand of [w, N / w]) {
      const numBins = N / cand;
      if (numBins < 2) continue;
      const diff = Math.abs(numBins - TARGET_BUCKETS);
      if (diff < bestDiff) { bestDiff = diff; bestW = cand; }
    }
  }
  if (bestDiff > TARGET_BUCKETS) bestW = Math.max(1, Math.ceil(N / TARGET_BUCKETS));
  return bestW;
}

function buildBuckets(scores: number[], maxPossibleScore: number): Bucket[] {
  const ceiling = Math.max(maxPossibleScore, 1);
  const width = chooseWidth(ceiling);
  const numBuckets = Math.ceil((ceiling + 1) / width);
  const buckets: Bucket[] = Array.from({ length: numBuckets }, (_, i) => {
    const start = i * width;
    const end = Math.min(start + width - 1, ceiling);
    const label = start === end ? `${start}` : `${start}–${end}`;
    return { label, count: 0, rangeStart: start, rangeEnd: end };
  });
  for (const score of scores) {
    const idx = Math.min(Math.floor(score / width), numBuckets - 1);
    buckets[idx].count++;
  }
  return buckets;
}

// ---------------------------------------------------------------------------
// Per-question summary card
// ---------------------------------------------------------------------------

function optionLabel(i: number) { return String.fromCharCode(65 + i); }

function AnswerBar({ label, count, total, correct, colorClass }: {
  label: string; count: number; total: number; correct: boolean; colorClass: string;
}) {
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <div className="flex items-center gap-3">
      <span /* theme-check: small-text breakdown */ className={`w-6 text-center font-bold text-base shrink-0 ${correct ? 'text-success-fg' : 'text-fg-muted'}`}>
        {label}
      </span>
      <div className="flex-1 h-6 bg-surface-sunken rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${colorClass}`}
          style={{ width: `${Math.max(pct, count > 0 ? 2 : 0)}%` }}
        />
      </div>
      <span /* theme-check: small-text breakdown */ className={`w-8 text-right text-base font-semibold shrink-0 ${correct ? 'text-success-fg' : 'text-fg-muted'}`}>
        {count}
      </span>
      {correct && <span /* theme-check: small-text breakdown */ className="text-success-fg text-base font-bold shrink-0">✓</span>}
      {!correct && <span className="w-4 shrink-0" />}
    </div>
  );
}

function QuestionCard({ item, index }: { item: HostQuestionSummaryItem; index: number }) {
  const { type, gradingType, prompt, config, answerReveal, answerDistribution, totalAnswered, totalPlayers, correctCount, avgAnswerTimeMs, pointsValue, feedback } = item;

  const typeLabel: Record<string, string> = {
    multiple_choice: 'Multiple Choice',
    true_false: 'True / False',
    fill_in_the_blank: 'Fill in the Blank',
    multi_select: 'Multi-Select',
    pin_drop: 'Pin It',
    estimate: 'Estimate',
  };

  const answeredPct = totalPlayers > 0 ? Math.round((totalAnswered / totalPlayers) * 100) : 0;
  const correctPct = totalAnswered > 0 ? Math.round((correctCount / totalAnswered) * 100) : 0;

  const reveal = answerReveal as AnswerReveal;

  function isCorrectIndex(i: number): boolean {
    if (reveal.type === 'multiple_choice') {
      return (reveal as { type: 'multiple_choice'; correctIndices: number[] }).correctIndices.includes(i);
    }
    if (reveal.type === 'multi_select') {
      return ((reveal as { type: 'multi_select'; answerPoints: number[] }).answerPoints[i] ?? 0) > 0;
    }
    return false;
  }
  function isCorrectTF(val: 'true' | 'false'): boolean {
    if (reveal.type !== 'true_false') return false;
    const rv = reveal as { type: 'true_false'; correctValue: boolean };
    return val === 'true' ? rv.correctValue : !rv.correctValue;
  }

  return (
    <div className="w-full bg-surface border border-line rounded-card shadow-card p-6 space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span /* theme-check: small-text breakdown */ className="text-fg-subtle text-base uppercase tracking-widest font-semibold">
            Q{index + 1}
          </span>
          <span className="text-fg-subtle">·</span>
          <span /* theme-check: small-text breakdown */ className="text-fg-muted text-base uppercase tracking-widest">
            {typeLabel[type] ?? type}
          </span>
          <span className="text-fg-subtle">·</span>
          <span /* theme-check: small-text breakdown */ className={`text-base uppercase tracking-widest font-semibold ${gradingType === 'COMPLETENESS' ? 'text-warning-fg' : 'text-accent-fg'}`}>
            {gradingType === 'COMPLETENESS' ? 'Participation' : 'Accuracy'}
          </span>
          <span className="text-fg-subtle">·</span>
          <span /* theme-check: small-text breakdown */ className="text-fg-muted text-base">{pointsValue} {pointsValue === 1 ? 'pt' : 'pts'}</span>
        </div>
        <div /* theme-check: small-text breakdown */ className="text-right text-base text-fg-subtle shrink-0">
          <span className="text-fg-muted font-semibold">{totalAnswered}</span>/{totalPlayers} answered
          {avgAnswerTimeMs !== null && (
            <span className="ml-2 text-fg-subtle">· avg {(avgAnswerTimeMs / 1000).toFixed(1)}s</span>
          )}
        </div>
      </div>

      {/* Prompt */}
      <p className="text-fg text-xl font-semibold leading-snug">{prompt}</p>

      {/* Distribution */}
      <div className="space-y-2">
        {(type === 'multiple_choice' || type === 'multi_select') && (config.options ?? []).map((opt, i) => {
          const count = answerDistribution[String(i)] ?? 0;
          const correct = isCorrectIndex(i);
          return (
            <div key={i} className="space-y-0.5">
              <div /* theme-check: small-text breakdown */ className="flex items-center gap-2 text-base text-fg-muted">
                {config.optionImages?.[i] && (
                  <img src={imageUrl(config.optionImages[i] as string)} alt="" className="h-6 w-6 rounded object-cover" />
                )}
                <span className={`font-bold ${correct ? 'text-success-fg' : ''}`}>{optionLabel(i)}.</span>
                <span className={correct ? 'text-success-fg' : ''}>{opt}</span>
              </div>
              <AnswerBar
                label={optionLabel(i)}
                count={count}
                total={totalPlayers}
                correct={correct}
                colorClass={correct ? 'bg-success' : 'bg-line-strong'}
              />
            </div>
          );
        })}

        {type === 'true_false' && (['true', 'false'] as const).map((val) => {
          const count = answerDistribution[val] ?? 0;
          const correct = isCorrectTF(val);
          return (
            <AnswerBar
              key={val}
              label={val === 'true' ? 'T' : 'F'}
              count={count}
              total={totalPlayers}
              correct={correct}
              colorClass={correct ? 'bg-success' : 'bg-line-strong'}
            />
          );
        })}

        {type === 'pin_drop' && (config.grid || config.image) && (
          <div className="flex items-center gap-5">
            <div className="w-56 shrink-0">
              <GridCanvas
                grid={config.grid}
                image={
                  config.image
                    ? { url: imageUrl(config.image.imageId), width: config.image.width, height: config.image.height }
                    : undefined
                }
                pins={asPoints(item.values)}
                target={reveal.type === 'pin_drop' ? reveal.target : null}
                fullRadius={reveal.type === 'pin_drop' ? reveal.fullRadius : undefined}
                zeroRadius={reveal.type === 'pin_drop' ? reveal.zeroRadius : undefined}
                maxHeightVh={0.3}
                label={`Pins for question ${index + 1}`}
              />
            </div>
            {reveal.type === 'pin_drop' && (
              <p /* theme-check: small-text breakdown */ className="text-fg-muted text-base">
                Target{' '}
                <span className="text-success-fg font-semibold">
                  {config.image ? formatImagePoint(reveal.target) : formatPoint(reveal.target)}
                </span>
                <span className="text-fg-subtle">
                  {config.image
                    ? ` · full credit within ${Number((reveal.fullRadius * 100).toFixed(1))}%, none beyond ${Number((reveal.zeroRadius * 100).toFixed(1))}% of the width`
                    : ` · full credit within ${reveal.fullRadius}, none beyond ${reveal.zeroRadius}`}
                </span>
              </p>
            )}
          </div>
        )}

        {type === 'estimate' && (() => {
          const guesses = asNumbers(item.values);
          const mid = median(guesses);
          return (
            <div className="space-y-1">
              {guesses.length > 0 && (
                <NumberLine
                  values={guesses}
                  answer={reveal.type === 'estimate' ? reveal.answer : null}
                  unit={config.unit}
                  compact
                />
              )}
              <p /* theme-check: small-text breakdown */ className="text-fg-muted text-base">
                {reveal.type === 'estimate' && (
                  <>Answer <span className="text-success-fg font-semibold">{withUnit(reveal.answer, config.unit)}</span></>
                )}
                {mid !== null && (
                  <span className="text-fg-subtle">
                    {reveal.type === 'estimate' ? ' · ' : ''}median guess {withUnit(mid, config.unit)}
                  </span>
                )}
              </p>
            </div>
          );
        })()}

        {type === 'fill_in_the_blank' && (
          <div className="space-y-2">
            {reveal.type === 'fill_in_the_blank' && (
              <p /* theme-check: small-text breakdown */ className="text-fg-muted text-base">
                Accepted:{' '}
                {(reveal as { type: 'fill_in_the_blank'; acceptedAnswers: string[]; editDistance: number }).acceptedAnswers.map((a, i, arr) => (
                  <span key={i}>
                    <span className="text-success-fg font-mono">"{a}"</span>
                    {i < arr.length - 1 && <span className="text-fg-subtle">, </span>}
                  </span>
                ))}
                {(reveal as { type: 'fill_in_the_blank'; acceptedAnswers: string[]; editDistance: number }).editDistance > 0 && (
                  <span className="text-fg-subtle ml-1">
                    (±{(reveal as { type: 'fill_in_the_blank'; acceptedAnswers: string[]; editDistance: number }).editDistance} typo)
                  </span>
                )}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Footer stats */}
      <div /* theme-check: small-text breakdown */ className="flex items-center gap-4 pt-1 border-t border-line text-base">
        {gradingType === 'ACCURACY' ? (
          <>
            <span className="text-success-fg font-semibold">{correctCount} correct</span>
            <span className="text-fg-subtle">·</span>
            <span className="text-fg-muted">{correctPct}% accuracy</span>
            <span className="text-fg-subtle">·</span>
            <span className="text-fg-muted">{answeredPct}% responded</span>
          </>
        ) : (
          <>
            <span className="text-warning-fg font-semibold">{totalAnswered} completed</span>
            <span className="text-fg-subtle">·</span>
            <span className="text-fg-muted">{answeredPct}% response rate</span>
          </>
        )}
        {feedback && <FeedbackSummary counts={feedback} />}
      </div>
    </div>
  );
}

/** Players' thumbs and flags for one question: counts only, since this is on the projector. */
function FeedbackSummary({ counts }: { counts: FeedbackCounts }) {
  const { up, down, flagged } = counts;
  const label = `Player feedback: ${up} thumbs up, ${down} thumbs down, ${flagged} flagged as hard`;
  return (
    <span className="ml-auto flex items-center gap-3 text-fg-muted" role="img" aria-label={label} title={label}>
      <span className="flex items-center gap-1"><ThumbsUp size={18} aria-hidden="true" /><span className="text-fg font-semibold">{up}</span></span>
      <span className="flex items-center gap-1"><ThumbsDown size={18} aria-hidden="true" /><span className="text-fg font-semibold">{down}</span></span>
      <span className={`flex items-center gap-1 ${flagged > 0 ? 'text-warning-fg' : ''}`}>
        <Flag size={18} aria-hidden="true" fill={flagged > 0 ? 'currentColor' : 'none'} />
        <span className="font-semibold">{flagged}</span>
      </span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function GameOverPage() {
  const { gameOver } = useGame();
  const navigate = useNavigate();

  if (!gameOver) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-fg-muted text-host-lg">Loading final results…</p>
      </div>
    );
  }

  const { scores, playerCount, maxPossibleScore, questionSummary = [] } = gameOver;
  const buckets = buildBuckets(scores, maxPossibleScore);
  const maxCount = Math.max(...buckets.map(b => b.count), 1);

  const avg = scores.length > 0
    ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length)
    : 0;
  const high = scores.length > 0 ? Math.max(...scores) : 0;

  return (
    <div className="min-h-screen flex flex-col items-center p-8 lg:p-12 gap-8">
      <div className="text-center">
        <h1 className="text-display tracking-tight text-fg">Game Over!</h1>
        <p className="text-fg-muted text-host-lg mt-2">{playerCount} players · Max possible: {maxPossibleScore.toLocaleString()} pts</p>
      </div>

      {/* Histogram */}
      <div className="w-full max-w-4xl">
        <p className="text-fg-muted text-xl uppercase tracking-widest text-center mb-6">Score distribution</p>
        <div className="flex items-end gap-2 h-48">
          {buckets.map((bucket, i) => {
            const heightPct = (bucket.count / maxCount) * 100;
            return (
              <div key={i} className="flex-1 flex flex-col items-center gap-1">
                <span /* theme-check: small-text histogram */ className="text-fg-muted text-base font-semibold">
                  {bucket.count > 0 ? bucket.count : ''}
                </span>
                <div className="w-full bg-surface-sunken rounded-t-control relative" style={{ height: '160px' }}>
                  <div
                    className="absolute bottom-0 left-0 right-0 bg-accent rounded-t-control transition-all duration-700"
                    style={{ height: `${Math.max(heightPct, bucket.count > 0 ? 4 : 0)}%` }}
                  />
                </div>
                <span /* theme-check: small-text histogram */ className="text-fg-subtle text-base">{bucket.label}</span>
              </div>
            );
          })}
        </div>
        <p /* theme-check: small-text histogram */ className="text-fg-subtle text-base text-center mt-1">Score (points) →</p>
      </div>

      {/* Summary stats */}
      <div className="flex gap-12 text-center">
        <div>
          <p className="text-fg-muted text-xl uppercase tracking-widest">Average</p>
          <p className="text-fg text-host-xl font-bold">{avg.toLocaleString()}</p>
        </div>
        <div>
          <p className="text-fg-muted text-xl uppercase tracking-widest">High Score</p>
          <p className="text-fg text-host-xl font-bold">{high.toLocaleString()}</p>
        </div>
        <div>
          <p className="text-fg-muted text-xl uppercase tracking-widest">Players</p>
          <p className="text-fg text-host-xl font-bold">{playerCount}</p>
        </div>
      </div>

      <Button size="lg" onClick={() => navigate('/home')}>New Game</Button>

      {/* Per-question breakdown */}
      {questionSummary.length > 0 && (
        <div className="w-full max-w-4xl space-y-4 pb-8">
          <p className="text-fg-muted text-xl uppercase tracking-widest text-center">
            Question Breakdown
          </p>
          {questionSummary.map((item, i) => (
            <QuestionCard key={item.questionId} item={item} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}
