import { useEffect } from 'react';
import { useGame } from './GameLayout';
import { Button } from '../../components/ui/button';
import { TimerBar } from '../../components/ui/TimerBar';
import { GridCanvas } from '../../components/question/GridCanvas';
import { imageUrl, promptAltText } from '../../lib/images';
import type { QuestionConfig } from '../../types/game';

/**
 * T8: when an image question's options have pictures, the projector shows the options
 * too (text-only questions are unchanged): up to 4 cards a row, letter, picture and text.
 */
function OptionCards({ config }: { config: QuestionConfig }) {
  const options = config.options ?? [];
  const images = config.optionImages ?? [];
  const columns = Math.min(options.length, 4);
  return (
    <ul
      className="w-full grid gap-4"
      style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`, maxWidth: `${columns * 18}rem` }}
    >
      {options.map((text, i) => (
        <li key={i} className="rounded-card border border-line bg-surface overflow-hidden flex flex-col">
          {/* Height from the viewport, so prompt, picture and options fit one projector screen. */}
          <div className="h-[22vh] bg-surface-sunken flex items-center justify-center">
            {images[i] ? (
              <img src={imageUrl(images[i] as string)} alt={text} className="max-h-full max-w-full object-contain" />
            ) : (
              <span className="text-fg text-host-xl font-semibold px-4 text-center">{text}</span>
            )}
          </div>
          <p className="px-4 py-3 text-fg text-host-lg">
            <span className="font-bold text-accent-fg mr-2">{String.fromCharCode(65 + i)}</span>
            {images[i] ? text : ''}
          </p>
        </li>
      ))}
    </ul>
  );
}

export default function QuestionPage() {
  const { currentQuestion, answeredCount, playerCount, allAnswered, answerPhaseEnded, questionLocked, lockedTimerSeconds, autoAdvance, emitAdvance, emitLockQuestion } = useGame();

  useEffect(() => {
    if (!autoAdvance || !answerPhaseEnded) return;
    const id = setTimeout(emitAdvance, 1500);
    return () => clearTimeout(id);
  }, [autoAdvance, answerPhaseEnded, emitAdvance]);

  if (!currentQuestion) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-fg-muted text-host-lg">Loading question…</p>
      </div>
    );
  }

  const typeLabel: Record<string, string> = {
    multiple_choice: 'Multiple Choice',
    true_false: 'True / False',
    fill_in_the_blank: 'Fill in the Blank',
    multi_select: 'Multi-Select',
    pin_drop: 'Pin It',
    estimate: 'Estimate',
  };

  function editDistanceLabel(d: number): string {
    if (d === 0) return 'Exact spelling required';
    if (d === 1) return 'Up to 1 typo allowed';
    return `Up to ${d} typos allowed`;
  }

  const remainingSeconds = questionLocked && lockedTimerSeconds !== null
    ? lockedTimerSeconds
    : currentQuestion.startedAt
      ? Math.max(0, currentQuestion.timeLimitSeconds - (Date.now() - new Date(currentQuestion.startedAt).getTime()) / 1000)
      : currentQuestion.timeLimitSeconds;

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-8 lg:p-12 gap-8">
      <div className="flex items-center gap-3 text-xl uppercase tracking-wider">
        <span className="text-fg-muted">
          Question {currentQuestion.questionNumber} of {currentQuestion.totalQuestions}
        </span>
        <span className="text-fg-subtle">·</span>
        <span className="text-fg-muted">{typeLabel[currentQuestion.type] ?? currentQuestion.type}</span>
        <span className="text-fg-subtle">·</span>
        <span className={currentQuestion.gradingType === 'COMPLETENESS' ? 'text-warning-fg' : 'text-accent-fg'}>
          {currentQuestion.gradingType === 'COMPLETENESS' ? 'Participation' : 'Accuracy'}
        </span>
        {currentQuestion.type === 'fill_in_the_blank' && currentQuestion.gradingType === 'ACCURACY' && (
          <>
            <span className="text-fg-subtle">·</span>
            <span className="text-fg-muted normal-case">
              {editDistanceLabel(currentQuestion.editDistance ?? 0)}
            </span>
          </>
        )}
      </div>

      <div className="w-full max-w-5xl">
        <TimerBar
          key={currentQuestion.questionId}
          totalSeconds={currentQuestion.timeLimitSeconds}
          initialSeconds={remainingSeconds}
          paused={questionLocked}
        />
      </div>

      {!questionLocked && (
        <h2 className="text-display tracking-tight text-fg text-center max-w-5xl">
          {currentQuestion.prompt}
        </h2>
      )}

      {!questionLocked && currentQuestion.config.promptImageId && (
        <img
          src={imageUrl(currentQuestion.config.promptImageId)}
          alt={promptAltText(currentQuestion.prompt)}
          className={`${(currentQuestion.config.optionImages ?? []).some(Boolean) ? 'max-h-[30vh]' : 'max-h-[40vh]'} max-w-full object-contain rounded-card`}
        />
      )}

      {!questionLocked &&
        (currentQuestion.type === 'multiple_choice' || currentQuestion.type === 'multi_select') &&
        (currentQuestion.config.optionImages ?? []).some(Boolean) && <OptionCards config={currentQuestion.config} />}

      {/* The empty grid or picture players are pinning on — no target, so nothing is given away */}
      {!questionLocked && currentQuestion.type === 'pin_drop' && currentQuestion.config.grid && (
        <div className="w-full max-w-xl">
          <GridCanvas
            grid={currentQuestion.config.grid}
            maxHeightVh={0.45}
            label="The grid players are placing pins on"
          />
        </div>
      )}
      {!questionLocked && currentQuestion.type === 'pin_drop' && currentQuestion.config.image && (
        <div className="w-full max-w-3xl">
          <GridCanvas
            image={{
              url: imageUrl(currentQuestion.config.image.imageId),
              width: currentQuestion.config.image.width,
              height: currentQuestion.config.image.height,
            }}
            maxHeightVh={0.5}
            label="The picture players are placing pins on"
          />
        </div>
      )}

      {!questionLocked && currentQuestion.type === 'estimate' && (
        <p className="text-fg-muted text-host-lg">
          Guess a number
          {currentQuestion.config.unit && (
            <> in <span className="text-fg font-semibold">{currentQuestion.config.unit}</span></>
          )}
          {currentQuestion.config.integer && ' · whole numbers only'}
        </p>
      )}

      <div className="text-fg text-host-xl font-semibold">
        {answeredCount} / {playerCount} answered
        {allAnswered && <span className="ml-3 text-success-fg font-semibold">All answered!</span>}
        {questionLocked && <span className="ml-3 text-warning-fg font-semibold">· Answers locked</span>}
      </div>

      <div className="flex gap-4">
        <Button
          size="lg"
          variant="outline"
          onClick={emitLockQuestion}
          className={`px-10 ${questionLocked ? 'border-warning text-warning-fg hover:bg-warning-subtle' : ''}`}
        >
          {questionLocked ? 'Unlock Question' : 'Lock Question'}
        </Button>
        <Button size="xl" onClick={emitAdvance} className="px-10">
          Show Results
        </Button>
      </div>
    </div>
  );
}
