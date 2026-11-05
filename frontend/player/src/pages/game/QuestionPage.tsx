import { useRef, useState, useCallback } from 'react';
import { useGame } from './GameLayout';
import { TimerBar } from '../../components/ui/TimerBar';
import { PinDropAnswer } from '../../components/question/PinDropAnswer';
import { EstimateAnswer } from '../../components/question/EstimateAnswer';
import { imageUrl } from '../../lib/images';

// The eight answer fills (red, blue, gold, green, purple, orange, pink, teal); each carries
// white text at >= 4.5:1, also under the press overlay (docs/plans/t9-theming.md §4.2).
const OPTION_COLORS = [
  'bg-answer-1',
  'bg-answer-2',
  'bg-answer-3',
  'bg-answer-4',
  'bg-answer-5',
  'bg-answer-6',
  'bg-answer-7',
  'bg-answer-8',
];
const PRESS = 'hover:shadow-press active:shadow-press';
const INACTIVE = 'opacity-50 cursor-not-allowed';

function optionLabel(i: number): string {
  return String.fromCharCode(65 + i); // A, B, C, … Z
}

/**
 * T8: options with pictures, as cards (letter, picture, text). Two columns when every
 * option has a picture; one column when any lacks one, with text-only cards as tall
 * as the picture cards so every tap target matches.
 */
function ImageOptions({
  options,
  images,
  disabled,
  cardClass,
  badge,
  onPick,
}: {
  options: string[];
  images: (string | null)[];
  disabled: boolean;
  cardClass: (i: number) => string;
  badge: (i: number) => { text: string; className: string };
  onPick: (i: number) => void;
}) {
  const allPictures = options.every((_, i) => images[i]);
  return (
    <div className={`grid gap-3 ${allPictures ? 'grid-cols-2' : 'grid-cols-1'}`}>
      {options.map((opt, i) => (
        <button
          key={i}
          disabled={disabled}
          onClick={() => onPick(i)}
          className={`player-question__image-option rounded-card border-2 bg-surface text-fg overflow-hidden flex flex-col text-left font-semibold shadow-card transition-all
            ${disabled ? INACTIVE : 'hover:border-line-strong active:scale-95'} ${cardClass(i)}`}
        >
          <span className="h-32 w-full bg-surface-sunken flex items-center justify-center">
            {images[i] ? (
              <img src={imageUrl(images[i] as string)} alt={opt} className="max-h-full max-w-full object-contain" />
            ) : (
              <span className="px-4 text-center text-xl">{opt}</span>
            )}
          </span>
          <span className="flex items-center gap-3 px-3 py-2 text-lg min-h-12">
            <span
              className={`h-8 w-8 shrink-0 rounded-control flex items-center justify-center text-lg font-bold ${badge(i).className}`}
            >
              {badge(i).text}
            </span>
            {images[i] && <span className="min-w-0 break-words">{opt}</span>}
          </span>
        </button>
      ))}
    </div>
  );
}

export default function QuestionPage() {
  const { currentQuestion, questionLocked, emitAnswer } = useGame();
  const startTimeRef = useRef(Date.now());
  const [submitted, setSubmitted] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set());

  const toggleIndex = useCallback((i: number) => {
    if (submitted || questionLocked) return;
    setSelectedIndices(prev => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i); else next.add(i);
      return next;
    });
  }, [submitted, questionLocked]);

  if (!currentQuestion) {
    return (
      <div className="player-status-screen">
        <p className="text-fg-muted text-base">Loading question…</p>
      </div>
    );
  }

  function submit(answerData: Record<string, unknown>) {
    if (submitted) return;
    setSubmitted(true);
    emitAnswer(currentQuestion!.questionId, answerData, Date.now() - startTimeRef.current);
  }

  const questionLabel = (
    <p className="text-accent-fg text-sm font-bold text-center tracking-wide uppercase mb-3">
      Question {currentQuestion.questionNumber} of {currentQuestion.totalQuestions}
    </p>
  );

  const lockedMsg = (
    <p className="player-question__notice text-center text-warning-fg text-base mt-4 font-semibold">
      Answers locked — waiting for results…
    </p>
  );

  if (currentQuestion.type === 'multiple_choice') {
    const options = currentQuestion.config.options ?? [];
    const images = currentQuestion.config.optionImages ?? [];
    return (
      <div className="player-question">
        <div className="player-glass player-question__header">
          {questionLabel}
          <TimerBar key={currentQuestion.questionId} totalSeconds={currentQuestion.timeLimitSeconds} paused={questionLocked} />
        </div>
        {images.some(Boolean) ? (
          <ImageOptions
            options={options}
            images={images}
            disabled={submitted || questionLocked}
            cardClass={() => 'border-line'}
            badge={i => ({ text: optionLabel(i), className: `${OPTION_COLORS[i % OPTION_COLORS.length]} text-on-color` })}
            onPick={i => submit({ selectedIndex: i })}
          />
        ) : options.map((opt, i) => (
          <button
            key={i}
            disabled={submitted || questionLocked}
            onClick={() => submit({ selectedIndex: i })}
            className={`player-question__answer w-full min-h-14 flex items-center gap-4 rounded-card px-5 py-4 text-left text-on-color font-semibold text-lg shadow-card transition-all
              ${submitted || questionLocked ? INACTIVE : `${PRESS} active:scale-95`}
              ${OPTION_COLORS[i % OPTION_COLORS.length]}`}
          >
            <span className="text-2xl font-black w-8 shrink-0">{optionLabel(i)}</span>
            <span>{opt}</span>
          </button>
        ))}
        {submitted && <p className="player-glass player-question__locked text-fg-muted text-base">Answer submitted — waiting for results…</p>}
        {!submitted && questionLocked && lockedMsg}
      </div>
    );
  }

  if (currentQuestion.type === 'true_false') {
    return (
      <div className="player-question player-question--centered">
        <div className="player-glass player-question__header">
          {questionLabel}
          <TimerBar key={currentQuestion.questionId} totalSeconds={currentQuestion.timeLimitSeconds} paused={questionLocked} />
        </div>
        <button
          disabled={submitted || questionLocked}
          onClick={() => submit({ selectedValue: true })}
          className={`player-question__answer w-full rounded-card py-8 text-on-color font-black text-3xl bg-success shadow-card transition-all
            ${submitted || questionLocked ? INACTIVE : `${PRESS} active:scale-95`}`}
        >
          True
        </button>
        <button
          disabled={submitted || questionLocked}
          onClick={() => submit({ selectedValue: false })}
          className={`player-question__answer w-full rounded-card py-8 text-on-color font-black text-3xl bg-danger shadow-card transition-all
            ${submitted || questionLocked ? INACTIVE : `${PRESS} active:scale-95`}`}
        >
          False
        </button>
        {submitted && <p className="player-glass player-question__locked text-fg-muted text-base">Answer submitted — waiting for results…</p>}
        {!submitted && questionLocked && lockedMsg}
      </div>
    );
  }

  if (currentQuestion.type === 'fill_in_the_blank') {
    const maxLength = currentQuestion.config.maxLength ?? 100;
    return (
      <div className="player-question player-question--centered">
        <div className="player-glass player-question__header">
          {questionLabel}
          <TimerBar key={currentQuestion.questionId} totalSeconds={currentQuestion.timeLimitSeconds} paused={questionLocked} />
        </div>

        {submitted ? (
          <div className="player-glass player-question__locked flex flex-col items-center gap-3">
            <div className="text-5xl">🔒</div>
            <p className="text-fg text-xl font-bold">Answer locked in!</p>
            <p className="text-fg-muted text-base italic">"{inputValue.trim()}"</p>
            <p className="text-fg-muted text-base mt-2">Waiting for results…</p>
          </div>
        ) : questionLocked ? (
          <div className="flex flex-col items-center gap-3 mt-4">
            {lockedMsg}
          </div>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const trimmed = inputValue.trim();
              if (trimmed) submit({ text: trimmed });
            }}
            className="flex flex-col gap-4"
          >
            <input
              type="text"
              maxLength={maxLength}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Type your answer…"
              autoFocus
              className="player-question__input w-full rounded-card border-2 border-line-strong bg-surface-sunken px-4 py-4 text-fg text-xl placeholder:text-fg-subtle focus:border-focus"
            />
            <button
              type="submit"
              disabled={!inputValue.trim()}
              className="player-question__submit w-full min-h-14 rounded-card py-5 text-on-color font-black text-2xl bg-accent hover:bg-accent-hover active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Submit
            </button>
          </form>
        )}
      </div>
    );
  }

  if (currentQuestion.type === 'multi_select') {
    const options = currentQuestion.config.options ?? [];
    return (
      <div className="player-question">
        <div className="player-glass player-question__header">
          {questionLabel}
          <TimerBar key={currentQuestion.questionId} totalSeconds={currentQuestion.timeLimitSeconds} paused={questionLocked} />
        </div>
        <p className="text-center text-fg-muted text-base">Select all that apply</p>
        {(currentQuestion.config.optionImages ?? []).some(Boolean) && (
          <ImageOptions
            options={options}
            images={currentQuestion.config.optionImages ?? []}
            disabled={submitted || questionLocked}
            // Selected pictures get a ring in the text colour, offset from the page, so the
            // cue doesn't depend on the picture's own colours.
            cardClass={i =>
              selectedIndices.has(i)
                ? 'border-accent ring-4 ring-fg ring-offset-2 ring-offset-canvas'
                : 'border-line'
            }
            badge={i =>
              selectedIndices.has(i)
                ? { text: '✓', className: 'bg-accent text-on-color' }
                : { text: optionLabel(i), className: 'border-2 border-line-strong text-fg-muted' }
            }
            onPick={toggleIndex}
          />
        )}
        {!(currentQuestion.config.optionImages ?? []).some(Boolean) && options.map((opt, i) => {
          const isSelected = selectedIndices.has(i);
          return (
            <button
              key={i}
              disabled={submitted || questionLocked}
              onClick={() => toggleIndex(i)}
              aria-pressed={isSelected}
              className={`player-question__image-option w-full min-h-14 flex items-center gap-4 rounded-card px-5 py-4 text-left font-semibold text-lg border-2 transition-all
                ${submitted || questionLocked ? INACTIVE : 'active:scale-95'}
                ${isSelected
                  ? 'bg-accent border-accent text-on-color'
                  : 'bg-surface border-line-strong text-fg hover:bg-surface-hover'
                }`}
            >
              {/* Selected: the badge inverts to white with accent text (accent-fg is a light tint
                  in dark, so it can't sit on white). */}
              <span className={`text-xl font-black w-8 h-8 shrink-0 flex items-center justify-center rounded-control border-2 transition-colors
                ${isSelected ? 'border-on-color bg-on-color text-accent' : 'border-line-strong text-fg-muted'}`}>
                {isSelected ? '✓' : optionLabel(i)}
              </span>
              <span>{opt}</span>
            </button>
          );
        })}
        {!submitted && !questionLocked && (
          <button
            disabled={selectedIndices.size === 0}
            onClick={() => submit({ selectedIndices: Array.from(selectedIndices) })}
            className="player-question__submit w-full min-h-14 rounded-card py-5 text-on-color font-black text-2xl bg-accent hover:bg-accent-hover active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed mt-2"
          >
            Submit ({selectedIndices.size} selected)
          </button>
        )}
        {submitted && <p className="player-glass player-question__locked text-fg-muted text-base">Answer submitted — waiting for results…</p>}
        {!submitted && questionLocked && lockedMsg}
      </div>
    );
  }

  if (currentQuestion.type === 'pin_drop' && (currentQuestion.config.grid || currentQuestion.config.image)) {
    return (
      <div className="player-question">
        <div className="player-glass player-question__header">
          {questionLabel}
          <TimerBar key={currentQuestion.questionId} totalSeconds={currentQuestion.timeLimitSeconds} paused={questionLocked} />
        </div>
        <PinDropAnswer
          grid={currentQuestion.config.grid}
          image={currentQuestion.config.image}
          snap={!!currentQuestion.config.snap}
          disabled={submitted || questionLocked}
          onSubmit={point => submit({ point })}
        />
        {submitted && <p className="player-glass player-question__locked text-fg-muted text-base">Pin submitted — waiting for results…</p>}
        {!submitted && questionLocked && lockedMsg}
      </div>
    );
  }

  if (currentQuestion.type === 'estimate') {
    return (
      <div className="player-question player-question--centered">
        <div className="player-glass player-question__header">
          {questionLabel}
          <TimerBar key={currentQuestion.questionId} totalSeconds={currentQuestion.timeLimitSeconds} paused={questionLocked} />
        </div>
        {submitted ? (
          <div className="player-glass player-question__locked flex flex-col items-center gap-3">
            <div className="text-5xl">🔒</div>
            <p className="text-fg text-xl font-bold">Guess locked in!</p>
            <p className="text-fg-muted text-base mt-2">Waiting for results…</p>
          </div>
        ) : questionLocked ? (
          lockedMsg
        ) : (
          <EstimateAnswer
            unit={currentQuestion.config.unit ?? ''}
            integer={!!currentQuestion.config.integer}
            disabled={submitted || questionLocked}
            onSubmit={value => submit({ value })}
          />
        )}
      </div>
    );
  }

  return (
    <div className="player-status-screen">
      <p className="text-fg-muted">Unsupported question type.</p>
    </div>
  );
}
