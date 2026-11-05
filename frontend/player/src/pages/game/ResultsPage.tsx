import { useGame } from './GameLayout';
import { GridCanvas } from '../../components/question/GridCanvas';
import { QuestionPoll } from '../../components/question/QuestionPoll';
import { canvasImage } from '../../lib/images';
import {
  DISTANCE_TYPES,
  describeCorrectAnswer,
  describeMiss,
  describePlayerAnswer,
} from '../../lib/answers';
import type { PlayerAnswer } from '../../types/game';

export default function ResultsPage() {
  const { questionResults, currentQuestion, lastAnswerData } = useGame();

  if (!questionResults) {
    return (
      <div className="player-status-screen">
        <p className="text-fg-muted text-base">Loading results…</p>
      </div>
    );
  }

  const { answerReveal, yourPoints, yourScore, yourRank, playerCount } = questionResults;
  const type = currentQuestion?.type;
  const config = currentQuestion?.config ?? {};
  const myAnswer = lastAnswerData as PlayerAnswer | null;
  const answeredLabel = type && myAnswer ? describePlayerAnswer(type, myAnswer, config) : null;
  const isCompleteness = answerReveal.type === 'completeness';
  const isDistance = type !== undefined && DISTANCE_TYPES.has(type);
  const isCorrect = !isCompleteness && yourPoints > 0;
  const isFull = currentQuestion ? yourPoints >= currentQuestion.pointsValue : isCorrect;

  // Distance-scored types say how close you were; the others keep right/wrong.
  let verdict: { text: string; className: string };
  if (isCompleteness) verdict = { text: 'Answer recorded!', className: 'text-accent-fg' };
  else if (isDistance && myAnswer && isFull) verdict = { text: 'Spot on!', className: 'text-success-fg' };
  else if (isDistance && myAnswer && isCorrect) verdict = { text: 'Close!', className: 'text-warning-fg' };
  else if (isDistance) verdict = { text: myAnswer ? 'Too far off' : 'No answer', className: 'text-danger-fg' };
  else if (isCorrect) verdict = { text: 'Correct!', className: 'text-success-fg' };
  else verdict = { text: 'Incorrect', className: 'text-danger-fg' };

  const showCorrect =
    !isCompleteness &&
    (answerReveal.type === 'fill_in_the_blank' || (isDistance && !isFull));
  const miss = describeMiss(myAnswer, answerReveal, config);

  return (
    <div className="player-status-screen">
      <div className="player-glass player-result-card flex flex-col items-center gap-5 text-center">
        <div>
          <p className="text-accent-fg text-xs font-bold uppercase tracking-[0.2em] mb-3">Question result</p>
          <h1 className={`${verdict.className} text-4xl font-black`}>{verdict.text}</h1>
        </div>

        {/* pin_drop: your pin against the target and its full / zero-credit rings */}
        {answerReveal.type === 'pin_drop' && (config.grid || config.image) && (
          <div className="w-full max-w-md">
            <GridCanvas
              grid={config.grid}
              image={config.image ? canvasImage(config.image) : undefined}
              ownPin={myAnswer?.point ?? null}
              target={answerReveal.target}
              fullRadius={answerReveal.fullRadius}
              zeroRadius={answerReveal.zeroRadius}
              label="Your pin and the target"
            />
          </div>
        )}

        {/* What the player answered */}
        {answeredLabel && (
          <p className="text-fg-muted text-base break-words max-w-full">
            You answered: <span className="text-fg font-semibold">{answeredLabel}</span>
            {miss && !isCompleteness && <span className="text-fg-muted"> · {miss}</span>}
          </p>
        )}

        {showCorrect && (
          <p className="text-fg-muted text-base break-words max-w-full">
            Correct:{' '}
            <span className="text-success-fg font-semibold">
              {answerReveal.type === 'fill_in_the_blank'
                ? answerReveal.acceptedAnswers.join(' / ')
                : describeCorrectAnswer(answerReveal, config)}
            </span>
          </p>
        )}

        {/* Points for this question */}
        <div className="player-result-stat w-full">
          <p className="text-accent-fg text-xs font-bold uppercase tracking-[0.16em]">This question</p>
          <p className="text-fg text-3xl font-black mt-1">+{yourPoints.toLocaleString()} pts</p>
        </div>

        {/* Running total and rank */}
        <div className="grid grid-cols-2 gap-3 w-full">
          <div className="player-result-stat">
            <p className="text-fg-muted text-sm">Total score</p>
            <p className="font-bold text-xl text-fg">{yourScore.toLocaleString()}</p>
          </div>
          <div className="player-result-stat">
            <p className="text-fg-muted text-sm">Rank</p>
            <p className="font-bold text-xl text-fg">#{yourRank} <span className="text-sm font-medium text-fg-muted">of {playerCount}</span></p>
          </div>
        </div>

        {currentQuestion && <QuestionPoll questionId={currentQuestion.questionId} />}

        <p className="text-fg-muted text-base">Waiting for next question…</p>
      </div>
    </div>
  );
}
