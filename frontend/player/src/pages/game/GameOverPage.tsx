import { useNavigate } from 'react-router-dom';
import { useGame } from './GameLayout';
import { Button } from '../../components/ui/button';
import type { QuestionSummaryItem } from '../../types/game';
import { DISTANCE_TYPES, describeCorrectAnswer, describePlayerAnswer } from '../../lib/answers';
import { imageUrl } from '../../lib/images';

function QuestionRow({ item, index }: { item: QuestionSummaryItem; index: number }) {
  const isCompleteness = item.answerReveal.type === 'completeness';
  const noAnswer = !item.playerAnswer;
  const isCorrect = !isCompleteness && !noAnswer && item.pointsAwarded > 0;
  // Distance-scored types give partial credit: show the target unless it was full marks.
  const isPartial =
    isCorrect && DISTANCE_TYPES.has(item.type) && item.pointsAwarded < item.maxPoints;
  const showCorrectAnswer = !isCompleteness && (!isCorrect || isPartial);

  const playerAnswerLabel = describePlayerAnswer(item.type, item.playerAnswer, item.config);
  const correctAnswerLabel = !isCompleteness
    ? describeCorrectAnswer(item.answerReveal, item.config)
    : '';
  // T8: pictures of the options this player chose.
  const chosen =
    item.type === 'multiple_choice' && typeof item.playerAnswer?.selectedIndex === 'number'
      ? [item.playerAnswer.selectedIndex]
      : item.type === 'multi_select'
        ? item.playerAnswer?.selectedIndices ?? []
        : [];
  const chosenImages = chosen
    .map(i => item.config.optionImages?.[i])
    .filter((id): id is string => !!id)
    .slice(0, 3);

  return (
    <div className="player-glass player-recap-row">
      <p className="text-fg-muted text-sm font-medium uppercase tracking-wider mb-1">Q{index + 1}</p>
      <p className="text-fg text-base font-semibold leading-snug mb-3">{item.prompt}</p>

      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-fg-muted text-sm font-medium mb-0.5">Your answer</p>
          <div className="flex items-center gap-2">
            {noAnswer ? (
              <span className="text-fg-subtle text-base">—</span>
            ) : isCompleteness ? (
              <span className="text-accent-fg text-base">●</span>
            ) : isPartial ? (
              <span className="text-warning-fg text-base" title="Partial credit">◐</span>
            ) : isCorrect ? (
              <span className="text-success-fg text-base">✓</span>
            ) : (
              <span className="text-danger-fg text-base">✗</span>
            )}
            {chosenImages.map(id => (
              <img key={id} src={imageUrl(id)} alt="" className="h-8 w-8 rounded-control object-cover shrink-0" />
            ))}
            <span className={`text-base font-semibold min-w-0 break-words ${
              noAnswer ? 'text-fg-subtle' :
              isCompleteness ? 'text-accent-fg' :
              isPartial ? 'text-warning-fg' :
              isCorrect ? 'text-success-fg' : 'text-danger-fg'
            }`}>
              {playerAnswerLabel}
            </span>
          </div>

          {showCorrectAnswer && correctAnswerLabel && (
            <p className="text-fg-muted text-sm mt-1">
              Correct: <span className="text-success-fg font-medium">{correctAnswerLabel}</span>
            </p>
          )}
        </div>

        <div className="text-right shrink-0">
          <p className={`text-base font-bold ${
            item.pointsAwarded > 0 ? 'text-success-fg' : 'text-fg-muted'
          }`}>
            +{item.pointsAwarded.toLocaleString()}
          </p>
          <p className="text-fg-muted text-sm">pts</p>
        </div>
      </div>
    </div>
  );
}

export default function GameOverPage() {
  const { gameOver } = useGame();
  const navigate = useNavigate();

  if (!gameOver) {
    return (
      <div className="player-status-screen">
        <p className="text-fg-muted text-base">Loading final results…</p>
      </div>
    );
  }

  const { yourFinalScore, yourFinalRank, playerCount, questionSummary } = gameOver;

  return (
    <div className="flex flex-col gap-5 pb-6">
      <div className="player-glass player-result-card text-center">
        <p className="text-accent-fg text-xs font-bold uppercase tracking-[0.2em] mb-3">Final standings</p>
        <h1 className="text-4xl font-black text-fg">Game Over!</h1>
        <div className="mt-3 flex items-baseline justify-center gap-3">
          <span className="text-5xl font-black text-accent-fg">#{yourFinalRank}</span>
          <span className="text-fg-muted text-lg">of {playerCount}</span>
        </div>
        <p className="text-fg text-2xl font-bold mt-1">
          {yourFinalScore.toLocaleString()} pts
        </p>
      </div>

      <div className="flex flex-col gap-3">
        <h2 className="text-lg font-bold text-fg">Question recap</h2>
        {questionSummary.map((item, i) => (
          <QuestionRow key={item.questionId} item={item} index={i} />
        ))}
      </div>

      <div className="flex justify-center">
        <Button
          variant="outline"
          size="lg"
          className="player-play-again w-full text-on-color border-0"
          onClick={() => {
            localStorage.removeItem('token');
            navigate('/join');
          }}
        >
          Play Again
        </Button>
      </div>
    </div>
  );
}
