import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { ArrowLeft, Check, Flag, ThumbsDown, ThumbsUp, X } from 'lucide-react';
import { api } from '../../lib/api';
import { promptAltText } from '../../lib/images';
import { TYPE_LABELS, describeAnswer, describeCorrect, formatSeconds } from '../../lib/answerLabels';
import type { FeedbackCounts, QuestionConfig } from '../../types/game';
import './manage.css';

/**
 * Private per-session detail (docs/plans/question-feedback.md §4.7): who answered what,
 * and each player's thumbs and "hard" flag. Only people who may download the session's
 * reports can open it; nothing here is shown on the projector.
 */

interface DetailResponse {
  user_id: string;
  answer_data: Record<string, unknown> | null;
  is_correct: boolean | null;
  points: number | null;
  answer_time_ms: number | null;
  rating: 'UP' | 'DOWN' | null;
  flagged: boolean;
}

interface DetailQuestion {
  question_id: number;
  order_index: number;
  type: string;
  grading_type: string;
  prompt: string;
  config: QuestionConfig;
  answer_data: Record<string, unknown>;
  points_value: number;
  feedback: FeedbackCounts;
  responses: DetailResponse[];
}

interface DetailPlayer {
  user_id: string;
  display_name: string;
  identifier: string;
  kind: 'netid' | 'local' | 'guest';
  total_points: number;
}

interface SessionDetail {
  session: {
    session_id: string;
    room_code: string;
    status: string;
    game_title: string;
    course_name: string;
    course_semester: string;
    created_at: string | null;
    completed_at: string | null;
    host_display_name: string | null;
  };
  players: DetailPlayer[];
  questions: DetailQuestion[];
}

const KIND_LABELS: Record<DetailPlayer['kind'], string> = { netid: 'NetID', local: 'Local', guest: 'Guest' };

function fmtDateTime(iso: string | null): string {
  if (!iso) return '';
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function fmtPoints(n: number | null): string {
  if (n === null) return '—';
  return Number.isInteger(n) ? n.toLocaleString() : n.toFixed(1);
}

export default function SessionDetailPage() {
  const { sessionId = '' } = useParams<{ sessionId: string }>();
  const { search } = useLocation();
  const [data, setData] = useState<SessionDetail | null>(null);
  const [error, setError] = useState('');
  const [flaggedOnly, setFlaggedOnly] = useState(false);

  useEffect(() => {
    setData(null);
    setError('');
    api
      .get<SessionDetail>(`/host/sessions/${sessionId}/detail`)
      .then(setData)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Could not load this session'));
  }, [sessionId]);

  const players = useMemo(
    () => new Map((data?.players ?? []).map(p => [p.user_id, p])),
    [data],
  );

  const back = (
    <Link
      to={{ pathname: '/manage/sessions', search }}
      className="inline-flex items-center gap-1.5 text-sm font-medium text-fg-muted hover:text-fg"
    >
      <ArrowLeft size={16} aria-hidden="true" /> Sessions
    </Link>
  );

  if (error) {
    return (
      <div className="manage-page">
        {back}
        <p role="alert" className="mt-4 text-sm text-danger-fg">{error}</p>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="manage-page">
        {back}
        <p role="status" className="mt-4 text-fg-muted">Loading session…</p>
      </div>
    );
  }

  const { session, questions } = data;
  const totals = questions.reduce(
    (acc, q) => ({
      up: acc.up + q.feedback.up,
      down: acc.down + q.feedback.down,
      flagged: acc.flagged + q.feedback.flagged,
    }),
    { up: 0, down: 0, flagged: 0 },
  );
  const shown = flaggedOnly ? questions.filter(q => q.feedback.flagged > 0) : questions;

  return (
    <div className="manage-page space-y-6">
      <header className="manage-page__heading">
        {back}
        <p className="mt-3 text-xs font-semibold uppercase tracking-[0.22em] text-accent-fg">Session report</p>
        <h2 className="manage-page__title">{session.game_title}</h2>
        <p className="manage-page__intro">
          {session.course_name} · {session.course_semester} · {fmtDateTime(session.completed_at ?? session.created_at)}
          {' · '}Room <span className="font-mono">{session.room_code}</span>
          {' · '}{data.players.length} player{data.players.length === 1 ? '' : 's'}
          {session.status !== 'COMPLETED' && <> · {session.status === 'IN_PROGRESS' ? 'In progress' : 'Abandoned'}</>}
        </p>
        <p className="mt-1 text-sm text-fg-muted">
          Private to you: player names, answers and feedback are never shown on the projector.
        </p>
      </header>

      {/* Questions at a glance */}
      <section className="manage-panel rounded-card border border-line bg-surface p-6 shadow-card" aria-labelledby="sd-summary">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 id="sd-summary" className="text-lg font-semibold text-fg">Questions</h3>
            <p className="text-sm text-fg-muted">
              <FeedbackInline counts={totals} /> across the game
            </p>
          </div>
          <button
            type="button"
            aria-pressed={flaggedOnly}
            onClick={() => setFlaggedOnly(v => !v)}
            className={`inline-flex items-center gap-2 rounded-control border px-3 py-1.5 text-sm font-medium transition-colors ${
              flaggedOnly
                ? 'border-warning bg-warning-subtle text-warning-fg'
                : 'border-line-strong text-fg-muted hover:bg-surface-hover hover:text-fg'
            }`}
          >
            <Flag size={16} aria-hidden="true" fill={flaggedOnly ? 'currentColor' : 'none'} />
            Flagged only
          </button>
        </div>
        {shown.length === 0 ? (
          <p className="text-sm text-fg-muted">No question was flagged as hard.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-line text-xs font-medium uppercase tracking-wide text-fg-muted">
                  <th scope="col" className="py-2 pr-3">#</th>
                  <th scope="col" className="py-2 pr-3">Question</th>
                  <th scope="col" className="py-2 pr-3">Type</th>
                  <th scope="col" className="py-2 pr-3">Result</th>
                  <th scope="col" className="py-2 pr-3 text-right">Feedback</th>
                </tr>
              </thead>
              <tbody>
                {shown.map(q => {
                  const n = questions.indexOf(q) + 1;
                  const answered = q.responses.filter(r => r.answer_data !== null);
                  const correct = answered.filter(r => r.is_correct).length;
                  return (
                    <tr key={q.question_id} className="border-b border-line last:border-0">
                      <td className="py-2 pr-3 text-fg-muted">{n}</td>
                      <td className="py-2 pr-3">
                        <a href={`#q-${q.question_id}`} className="focus-inset text-fg hover:underline">
                          {promptAltText(q.prompt) || `Question ${n}`}
                        </a>
                      </td>
                      <td className="py-2 pr-3 whitespace-nowrap text-fg-muted">{TYPE_LABELS[q.type] ?? q.type}</td>
                      <td className="py-2 pr-3 whitespace-nowrap text-fg-muted">
                        {q.grading_type === 'ACCURACY'
                          ? `${correct} / ${answered.length} correct`
                          : `${answered.length} answered`}
                      </td>
                      <td className="py-2 text-right whitespace-nowrap">
                        <FeedbackInline counts={q.feedback} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Players */}
      <section className="manage-panel rounded-card border border-line bg-surface p-6 shadow-card" aria-labelledby="sd-players">
        <h3 id="sd-players" className="mb-4 text-lg font-semibold text-fg">Players</h3>
        {data.players.length === 0 ? (
          <p className="text-sm text-fg-muted">Nobody answered or gave feedback in this session.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-line text-xs font-medium uppercase tracking-wide text-fg-muted">
                  <th scope="col" className="py-2 pr-3">Rank</th>
                  <th scope="col" className="py-2 pr-3">Player</th>
                  <th scope="col" className="py-2 pr-3">Account</th>
                  <th scope="col" className="py-2 text-right">Points</th>
                </tr>
              </thead>
              <tbody>
                {data.players.map((p, i) => (
                  <tr key={p.user_id} className="border-b border-line last:border-0">
                    <td className="py-2 pr-3 text-fg-muted">{i + 1}</td>
                    <td className="py-2 pr-3 font-medium text-fg">{p.display_name}</td>
                    <td className="py-2 pr-3 text-fg-muted">
                      {KIND_LABELS[p.kind]}
                      {p.identifier && <span className="text-fg-subtle"> · {p.identifier}</span>}
                    </td>
                    <td className="py-2 text-right font-semibold tabular-nums text-fg">{fmtPoints(p.total_points)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* One card per question */}
      {shown.map(q => {
        const n = questions.indexOf(q) + 1;
        const key = describeCorrect(q.type, q.grading_type, q.config, q.answer_data);
        return (
          <section
            key={q.question_id}
            id={`q-${q.question_id}`}
            aria-labelledby={`q-${q.question_id}-title`}
            className="manage-panel scroll-mt-6 rounded-card border border-line bg-surface p-6 shadow-card"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-medium uppercase tracking-wide text-fg-muted">
                  Q{n} · {TYPE_LABELS[q.type] ?? q.type} · {q.grading_type === 'ACCURACY' ? 'Accuracy' : 'Participation'} · {fmtPoints(q.points_value)} pts
                </p>
                <h3 id={`q-${q.question_id}-title`} className="mt-1 text-lg font-semibold text-fg">
                  {promptAltText(q.prompt) || `Question ${n}`}
                </h3>
                {key && (
                  <p className="mt-1 text-sm text-fg-muted">
                    Answer: <span className="font-medium text-success-fg">{key}</span>
                  </p>
                )}
              </div>
              <FeedbackInline counts={q.feedback} />
            </div>

            {q.responses.length === 0 ? (
              <p className="mt-4 text-sm text-fg-muted">No answers or feedback for this question.</p>
            ) : (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-line text-xs font-medium uppercase tracking-wide text-fg-muted">
                      <th scope="col" className="py-2 pr-3">Player</th>
                      <th scope="col" className="py-2 pr-3">Answer</th>
                      <th scope="col" className="py-2 pr-3">Result</th>
                      <th scope="col" className="py-2 pr-3 text-right">Points</th>
                      <th scope="col" className="py-2 pr-3 text-right">Time</th>
                      <th scope="col" className="py-2">Feedback</th>
                    </tr>
                  </thead>
                  <tbody>
                    {q.responses.map(r => {
                      const player = players.get(r.user_id);
                      return (
                        <tr key={r.user_id} className="border-b border-line last:border-0">
                          <td className="py-2 pr-3 font-medium text-fg">{player?.display_name ?? 'Player'}</td>
                          <td className="py-2 pr-3 text-fg">{describeAnswer(q.type, q.config, r.answer_data)}</td>
                          <td className="py-2 pr-3"><ResultCell q={q} r={r} /></td>
                          <td className="py-2 pr-3 text-right tabular-nums text-fg">{fmtPoints(r.points)}</td>
                          <td className="py-2 pr-3 text-right tabular-nums text-fg-muted">{formatSeconds(r.answer_time_ms)}</td>
                          <td className="py-2"><PlayerFeedback r={r} /></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}

function ResultCell({ q, r }: { q: DetailQuestion; r: DetailResponse }) {
  if (r.answer_data === null) return <span className="text-fg-muted">No answer</span>;
  if (q.grading_type !== 'ACCURACY') return <span className="text-fg-muted">Recorded</span>;
  if (r.is_correct) {
    return (
      <span className="inline-flex items-center gap-1 font-medium text-success-fg">
        <Check size={16} aria-hidden="true" /> Correct
      </span>
    );
  }
  if ((r.points ?? 0) > 0) return <span className="font-medium text-warning-fg">Partial</span>;
  return (
    <span className="inline-flex items-center gap-1 font-medium text-danger-fg">
      <X size={16} aria-hidden="true" /> Wrong
    </span>
  );
}

function PlayerFeedback({ r }: { r: DetailResponse }) {
  if (!r.rating && !r.flagged) return <span className="text-fg-subtle">—</span>;
  return (
    <span className="inline-flex items-center gap-2">
      {r.rating === 'UP' && (
        <span className="inline-flex items-center gap-1 text-fg-muted">
          <ThumbsUp size={16} aria-hidden="true" /> Liked
        </span>
      )}
      {r.rating === 'DOWN' && (
        <span className="inline-flex items-center gap-1 text-fg-muted">
          <ThumbsDown size={16} aria-hidden="true" /> Disliked
        </span>
      )}
      {r.flagged && (
        <span className="inline-flex items-center gap-1 font-medium text-warning-fg">
          <Flag size={16} aria-hidden="true" fill="currentColor" /> Hard
        </span>
      )}
    </span>
  );
}

function FeedbackInline({ counts }: { counts: FeedbackCounts }) {
  const label = `${counts.up} thumbs up, ${counts.down} thumbs down, ${counts.flagged} flagged as hard`;
  return (
    <span className="inline-flex items-center gap-3 text-sm text-fg-muted" role="img" aria-label={label} title={label}>
      <span className="inline-flex items-center gap-1">
        <ThumbsUp size={16} aria-hidden="true" />
        <span className="font-semibold text-fg">{counts.up}</span>
      </span>
      <span className="inline-flex items-center gap-1">
        <ThumbsDown size={16} aria-hidden="true" />
        <span className="font-semibold text-fg">{counts.down}</span>
      </span>
      <span className={`inline-flex items-center gap-1 ${counts.flagged > 0 ? 'text-warning-fg' : ''}`}>
        <Flag size={16} aria-hidden="true" fill={counts.flagged > 0 ? 'currentColor' : 'none'} />
        <span className="font-semibold">{counts.flagged}</span>
      </span>
    </span>
  );
}
