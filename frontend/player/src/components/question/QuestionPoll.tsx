import { useId } from 'react';
import { Flag, ThumbsDown, ThumbsUp, type LucideIcon } from 'lucide-react';
import { useGame, type FeedbackRating } from '../../pages/game/GameLayout';

/**
 * The optional "Liked the question?" poll under "Answer locked in!" and the question's
 * results (docs/plans/question-feedback.md §4.8). Thumbs up or down (one or neither) and
 * a separate "hard" flag; tapping a pressed button clears it. The professor sees counts
 * after the game and, privately, who said what.
 */
export function QuestionPoll({ questionId }: { questionId: number }) {
  const { feedback, sendFeedback } = useGame();
  const titleId = useId();
  const mine = feedback[questionId];
  const rating = mine?.rating ?? null;
  const flagged = mine?.flagged ?? false;

  function rate(next: Exclude<FeedbackRating, null>) {
    sendFeedback(questionId, rating === next ? null : next, flagged);
  }

  const said = rating !== null || flagged;
  let status = '';
  if (mine?.status === 'error') status = 'Couldn’t save — try again';
  else if (mine?.status === 'saved' && said) status = 'Thanks — your professor will see this';

  return (
    <section aria-labelledby={titleId} className="player-poll w-full text-center">
      <p id={titleId} className="text-fg text-base font-semibold">
        Liked the question? <span className="text-fg-muted font-normal">(optional)</span>
      </p>
      <div role="group" aria-labelledby={titleId} className="mt-3 flex items-center justify-center gap-3">
        <PollButton
          icon={ThumbsUp}
          label="Thumbs up"
          pressed={rating === 'UP'}
          tone="accent"
          onClick={() => rate('UP')}
        />
        <PollButton
          icon={ThumbsDown}
          label="Thumbs down"
          pressed={rating === 'DOWN'}
          tone="accent"
          onClick={() => rate('DOWN')}
        />
        <span className="mx-1 h-8 w-px bg-line" aria-hidden="true" />
        <PollButton
          icon={Flag}
          label="Flag as hard"
          pressed={flagged}
          tone="warning"
          onClick={() => sendFeedback(questionId, rating, !flagged)}
        />
      </div>
      <p className="mt-3 text-fg-muted text-sm">
        Flag the question if it was hard — it lets your professor know.
      </p>
      <p
        role="status"
        aria-live="polite"
        className={`mt-1 min-h-5 text-sm ${mine?.status === 'error' ? 'text-danger-fg' : 'text-success-fg'}`}
      >
        {status}
      </p>
    </section>
  );
}

function PollButton({
  icon: Icon,
  label,
  pressed,
  tone,
  onClick,
}: {
  icon: LucideIcon;
  label: string;
  pressed: boolean;
  tone: 'accent' | 'warning';
  onClick: () => void;
}) {
  // Pressed is carried by aria-pressed and a filled icon as well as colour (WCAG 1.4.1).
  const pressedClass =
    tone === 'warning'
      ? 'bg-warning-subtle border-warning text-warning-fg'
      : 'bg-accent-subtle border-accent-fg text-accent-fg';
  return (
    <button
      type="button"
      aria-pressed={pressed}
      aria-label={label}
      title={label}
      onClick={onClick}
      className={`flex h-12 w-14 items-center justify-center rounded-control border-2 transition-colors active:scale-95 ${
        pressed ? pressedClass : 'border-line-strong bg-surface text-fg-muted hover:bg-surface-hover hover:text-fg'
      }`}
    >
      <Icon size={22} aria-hidden="true" fill={pressed ? 'currentColor' : 'none'} />
    </button>
  );
}
