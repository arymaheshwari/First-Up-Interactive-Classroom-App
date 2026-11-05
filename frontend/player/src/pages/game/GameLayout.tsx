import { createContext, useContext, useEffect, useRef, useState } from 'react';
import { Outlet, useNavigate, useParams } from 'react-router-dom';
import { isTokenExpired } from '../../lib/utils';
import { phoneImageIds, preloadImages } from '../../lib/images';
import { ThemeToggle } from '../../components/ui/ThemeToggle';
import { io, Socket } from 'socket.io-client';
import { MessageCircleHeart } from 'lucide-react';
import './player-game.css';
import './reaction-composer.css';
import type {
  AnswerResultPayload,
  PlayerGameOverPayload,
  PlayerJoinedPayload,
  PlayerPhase,
  PlayerResultsPayload,
  QuestionPayload,
  SyncStatePayload,
} from '../../types/game';

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

interface GameContextValue {
  phase: PlayerPhase;
  gameStatus: 'LOBBY' | 'IN_PROGRESS';
  roomCode: string;
  playerCount: number;
  hostDisconnected: boolean;
  currentQuestion: QuestionPayload | null;
  questionLocked: boolean;
  lastAnswerData: Record<string, unknown> | null;
  answerResult: AnswerResultPayload | null;
  questionResults: PlayerResultsPayload | null;
  gameOver: PlayerGameOverPayload | null;
  emitAnswer: (questionId: number, answerData: Record<string, unknown>, answerTimeMs: number) => void;
  /** This player's thumbs/flag per question, kept across Feedback → Results. */
  feedback: Record<number, QuestionFeedbackState>;
  sendFeedback: (questionId: number, rating: FeedbackRating, flagged: boolean) => void;
}

export type FeedbackRating = 'UP' | 'DOWN' | null;

export interface QuestionFeedbackState {
  rating: FeedbackRating;
  flagged: boolean;
  /** 'saving' until the server echoes it; 'error' after a rejection (reverted). */
  status: 'saving' | 'saved' | 'error';
}

const NO_FEEDBACK = { rating: null as FeedbackRating, flagged: false };

const GameContext = createContext<GameContextValue | null>(null);

export function useGame(): GameContextValue {
  const ctx = useContext(GameContext);
  if (!ctx) throw new Error('useGame must be used within GameLayout');
  return ctx;
}

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

export default function GameLayout() {
  const { code = '' } = useParams<{ code: string }>();
  const navigate = useNavigate();
  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;
  const socketRef = useRef<Socket | null>(null);
  // Ref mirrors phase so socket event closures (registered once) can read current value.
  const phaseRef = useRef<PlayerPhase>('lobby');

  const [phase, setPhase] = useState<PlayerPhase>('lobby');
  const [gameStatus, setGameStatus] = useState<'LOBBY' | 'IN_PROGRESS'>('LOBBY');
  const [playerCount, setPlayerCount] = useState(0);
  const [hostDisconnected, setHostDisconnected] = useState(false);
  const [currentQuestion, setCurrentQuestion] = useState<QuestionPayload | null>(null);
  const [questionLocked, setQuestionLocked] = useState(false);
  const [lastAnswerData, setLastAnswerData] = useState<Record<string, unknown> | null>(null);
  const [answerResult, setAnswerResult] = useState<AnswerResultPayload | null>(null);
  const [questionResults, setQuestionResults] = useState<PlayerResultsPayload | null>(null);
  const [gameOver, setGameOver] = useState<PlayerGameOverPayload | null>(null);
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState<Record<number, QuestionFeedbackState>>({});
  const [reactionsEnabled, setReactionsEnabled] = useState(true);
  const [reactionOpen, setReactionOpen] = useState(false);
  const [reactionText, setReactionText] = useState('');
  const [reactionStatus, setReactionStatus] = useState('');
  // What the server last confirmed per question, to revert to on a rejection.
  const savedFeedbackRef = useRef<Record<number, { rating: FeedbackRating; flagged: boolean }>>({});

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token || isTokenExpired(token)) {
      localStorage.removeItem('token');
      navigateRef.current(code ? `/name/${code}` : '/join', { replace: true });
      return;
    }
    if (!code) {
      navigateRef.current('/join', { replace: true });
      return;
    }

    const sock = io({
      path: '/socket.io',
      auth: (cb) => cb({ token: localStorage.getItem('token') ?? '' }),
      transports: ['websocket', 'polling'],
    });
    socketRef.current = sock;

    sock.on('connect', () => {
      setError('');
      if (phaseRef.current !== 'gameover') {
        sock.emit('join_room', { room_code: code, role: 'PLAYER' });
      }
    });

    sock.on('connect_error', (err) => {
      if (phaseRef.current !== 'gameover') {
        setError(`Connection error: ${err.message}`);
      }
    });

    sock.on('sync_state', (data: SyncStatePayload) => {
      setReactionsEnabled(data.reactionsEnabled ?? true);
      if (data.reactionsEnabled === false) setReactionOpen(false);
      preloadImages(data.prefetchImageIds); // T8: the lobby hints at the first question's images
      setPlayerCount(data.playerCount ?? 0);
      if (data.questionLocked) setQuestionLocked(true);
      if (data.status === 'LOBBY') {
        setGameStatus('LOBBY');
        setPhase('lobby');
        navigateRef.current(`/game/${code}/lobby`, { replace: true });
      } else if (data.status === 'IN_PROGRESS') {
        // Game already running — update state but don't navigate; new_question
        // (or question_results) will drive routing to the correct page.
        setGameStatus('IN_PROGRESS');
      }
    });

    sock.on('player_joined', (data: PlayerJoinedPayload) => {
      setPlayerCount(data.playerCount);
    });

    sock.on('reactions_enabled', (data: { enabled: boolean }) => {
      setReactionsEnabled(data.enabled);
      if (!data.enabled) setReactionOpen(false);
    });

    sock.on('reaction_error', (data: { message: string }) => {
      setReactionStatus(data.message);
    });

    sock.on('new_question', (data: QuestionPayload) => {
      preloadImages(phoneImageIds(data.config)); // late joiners missed the prefetch
      setCurrentQuestion(data);
      setQuestionLocked(false);
      setLastAnswerData(null);
      setAnswerResult(null);
      setQuestionResults(null);
      setHostDisconnected(false);
      // The poll is only for the question just played; start each question clean.
      setFeedback({});
      savedFeedbackRef.current = {};
      setPhase('question');
      navigateRef.current(`/game/${code}/question`);
    });

    sock.on('question_locked', () => {
      setQuestionLocked(true);
    });

    sock.on('question_unlocked', () => {
      setQuestionLocked(false);
    });

    sock.on('answer_received', (data: AnswerResultPayload) => {
      if (data.alreadyAnswered) return; // ignore duplicate-submit echo
      setAnswerResult(data);
      setPhase('feedback');
      navigateRef.current(`/game/${code}/feedback`);
    });

    sock.on('question_results', (data: PlayerResultsPayload) => {
      preloadImages(data.prefetchImageIds); // the next question's, while results show
      setQuestionResults(data);
      setPhase('results');
      navigateRef.current(`/game/${code}/results`);
    });

    sock.on('game_over', (data: PlayerGameOverPayload) => {
      phaseRef.current = 'gameover';
      setGameOver(data);
      setPhase('gameover');
      navigateRef.current(`/game/${code}/gameover`);
      sock.disconnect();
    });

    sock.on(
      'question_feedback_saved',
      (data: { questionId: number; rating: FeedbackRating; flagged: boolean }) => {
        savedFeedbackRef.current[data.questionId] = { rating: data.rating, flagged: data.flagged };
        setFeedback(prev => {
          const mine = prev[data.questionId];
          // A newer tap is still in flight: keep showing it until its own echo.
          if (mine && (mine.rating !== data.rating || mine.flagged !== data.flagged)) return prev;
          return { ...prev, [data.questionId]: { rating: data.rating, flagged: data.flagged, status: 'saved' } };
        });
      },
    );

    // Feedback has its own error event, so a late tap never ends the game screen.
    sock.on('question_feedback_error', (data: { questionId: number | null }) => {
      if (typeof data.questionId !== 'number') return;
      const qid = data.questionId;
      const saved = savedFeedbackRef.current[qid] ?? NO_FEEDBACK;
      setFeedback(prev => ({ ...prev, [qid]: { ...saved, status: 'error' } }));
    });

    sock.on('host_disconnected', () => {
      setHostDisconnected(true);
    });

    sock.on('game_abandoned', () => {
      navigateRef.current('/join', { replace: true });
    });

    sock.on('error', (data: { message: string }) => {
      if (phaseRef.current !== 'gameover') {
        setError(data.message);
      }
    });

    return () => {
      sock.disconnect();
      socketRef.current = null;
    };
  }, [code]);

  function emitAnswer(questionId: number, answerData: Record<string, unknown>, answerTimeMs: number) {
    setLastAnswerData(answerData);
    socketRef.current?.emit('submit_answer', { question_id: questionId, answer_data: answerData, answer_time_ms: answerTimeMs });
  }

  function sendFeedback(questionId: number, rating: FeedbackRating, flagged: boolean) {
    const sock = socketRef.current;
    if (!sock?.connected) {
      // Offline: say so instead of showing a choice that was never sent.
      const saved = savedFeedbackRef.current[questionId] ?? NO_FEEDBACK;
      setFeedback(prev => ({ ...prev, [questionId]: { ...saved, status: 'error' } }));
      return;
    }
    setFeedback(prev => ({ ...prev, [questionId]: { rating, flagged, status: 'saving' } }));
    sock.emit('question_feedback', { question_id: questionId, rating, flagged });
  }

  function sendReaction(kind: 'emoji' | 'text', value: string) {
    if (!socketRef.current?.connected) {
      setReactionStatus('Reconnecting — try again in a moment');
      return;
    }
    socketRef.current.emit('player_reaction', { kind, value });
    setReactionStatus('Sent');
    if (kind === 'text') setReactionText('');
  }

  if (error && phase !== 'gameover') {
    return (
      <main className="player-game">
        <div className="player-game__shell">
          <div className="player-game__top">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent-fg">Buzzer · Player</p>
            <ThemeToggle className="player-game__theme-toggle" />
          </div>
          <div className="player-status-screen">
            <div className="player-glass player-status-card text-center">
              <p role="alert" className="text-danger-fg text-lg">{error}</p>
              <button className="mt-4 min-h-12 px-4 text-accent-fg text-base font-semibold underline" onClick={() => navigate('/join')}>
                Back to Join
              </button>
            </div>
          </div>
        </div>
      </main>
    );
  }

  return (
    <GameContext.Provider
      value={{ phase, gameStatus, roomCode: code, playerCount, hostDisconnected, currentQuestion, questionLocked, lastAnswerData, answerResult, questionResults, gameOver, emitAnswer, feedback, sendFeedback }}
    >
      {hostDisconnected && phase !== 'gameover' && (
        <div role="status" className="fixed top-0 inset-x-0 bg-warning text-on-color text-center font-semibold py-2 text-base z-50">
          Host disconnected — waiting for them to reconnect…
        </div>
      )}
      <main className="player-game">
        <div className="player-game__shell">
          <header className="player-game__top">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent-fg">Buzzer · Player</p>
            <div className="player-game__top-tools">
              {reactionsEnabled && phase !== 'gameover' && (
                <div className="player-reaction-anchor">
                  <button
                    type="button"
                    className="player-reaction-trigger"
                    aria-label="Send a reaction or short message to the Host"
                    aria-expanded={reactionOpen}
                    aria-controls="player-reaction-panel"
                    onClick={() => { setReactionOpen(open => !open); setReactionStatus(''); }}
                  >
                    <MessageCircleHeart size={20} aria-hidden="true" />
                  </button>
                  {reactionOpen && (
                    <div id="player-reaction-panel" className="player-reaction-panel">
                      <p className="player-reaction-heading">Send to Host</p>
                      <p className="player-reaction-hint">Appears briefly on the Host screen</p>
                      <div className="player-reaction-choices" aria-label="Quick reactions">
                        {['👏', '❤️', '🎉', '😂', '😮', '👍'].map(emoji => (
                          <button key={emoji} type="button" aria-label={`Send ${emoji} reaction`} onClick={() => sendReaction('emoji', emoji)}>{emoji}</button>
                        ))}
                      </div>
                      <form onSubmit={(event) => { event.preventDefault(); if (reactionText.trim()) sendReaction('text', reactionText.trim()); }}>
                        <label htmlFor="player-reaction-text">Short message</label>
                        <div className="player-reaction-input-row">
                          <input id="player-reaction-text" value={reactionText} maxLength={80} onChange={event => setReactionText(event.target.value)} placeholder="Nice one!" />
                          <button type="submit" disabled={!reactionText.trim()}>Send</button>
                        </div>
                        <small>{reactionText.length}/80</small>
                      </form>
                      {reactionStatus && <p role="status" className="player-reaction-status">{reactionStatus}</p>}
                    </div>
                  )}
                </div>
              )}
              <span className="player-game__room-code" aria-label={`Room ${code}`}>{code}</span>
              <ThemeToggle className="player-game__theme-toggle" />
            </div>
          </header>
          <Outlet />
        </div>
      </main>
    </GameContext.Provider>
  );
}
