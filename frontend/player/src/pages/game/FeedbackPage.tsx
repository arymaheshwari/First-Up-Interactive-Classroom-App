import { LockKeyhole } from 'lucide-react';
import { useGame } from './GameLayout';
import { QuestionPoll } from '../../components/question/QuestionPoll';

export default function FeedbackPage() {
  const { currentQuestion } = useGame();
  return (
    <div className="player-status-screen">
      <section className="player-glass player-status-card text-center">
        <div className="player-status-icon"><LockKeyhole size={32} aria-hidden="true" /></div>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent-fg">Answer sent</p>
        <h1 className="mt-2 text-fg text-2xl font-bold">Answer locked in!</h1>
        <div className="player-loading-dots" aria-hidden="true">
          <span /><span /><span />
        </div>
        <p role="status" className="text-fg-muted text-base">Waiting for host to reveal results…</p>
        {currentQuestion && (
          <div className="mt-5">
            <QuestionPoll questionId={currentQuestion.questionId} />
          </div>
        )}
      </section>
    </div>
  );
}
