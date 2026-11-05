export interface PlayerInfo {
  userId: string;
  displayName: string;
}

export interface SyncStatePayload {
  status: 'LOBBY' | 'IN_PROGRESS' | 'COMPLETED' | 'ABANDONED';
  players: PlayerInfo[];
  playerCount: number;
  reactionsEnabled?: boolean;
  questionPhase?: 'QUESTION' | 'RESULTS' | null;
  currentQuestion?: QuestionPayload | null;
  questionLocked?: boolean;
  timerRemainingSeconds?: number | null;
  /** Images to download now, for the question that comes next (T8). */
  prefetchImageIds?: string[];
}

export interface PlayerJoinedPayload {
  userId: string;
  displayName: string;
  playerCount: number;
}

export interface PlayerLeftPayload {
  userId: string;
  playerCount: number;
}

export type QuestionType =
  | 'multiple_choice'
  | 'true_false'
  | 'fill_in_the_blank'
  | 'multi_select'
  | 'pin_drop'
  | 'estimate';

/** pin_drop's coordinate grid, in logical units (x and y share one unit). */
export interface Grid {
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
  step: number;
}

export interface Point {
  x: number;
  y: number;
}

/** A pin_drop background image (T8): its id and stored pixel size. */
export interface QuestionImage {
  imageId: string;
  width: number;
  height: number;
}

/** Client-safe question config — the server sends only these fields per type. */
export interface QuestionConfig {
  options?: string[]; // multiple_choice, multi_select
  maxLength?: number; // fill_in_the_blank
  grid?: Grid; // pin_drop
  /** pin_drop on a picture (T8): points are fractions of it. */
  image?: QuestionImage;
  snap?: boolean; // pin_drop
  /** Any type (T8): a picture shown with the prompt, on the host screen only. */
  promptImageId?: string;
  /** multiple_choice / multi_select (T8): one image id (or null) per option. */
  optionImages?: (string | null)[];
  unit?: string; // estimate
  integer?: boolean; // estimate
}

export interface QuestionPayload {
  questionId: number;
  questionNumber: number;
  totalQuestions: number;
  type: QuestionType;
  gradingType: 'ACCURACY' | 'COMPLETENESS';
  prompt: string;
  config: QuestionConfig;
  timeLimitSeconds: number;
  pointsValue: number;
  editDistance?: number;
  startedAt?: string;  // ISO timestamp — only present in sync_state reconnect payloads
}

export interface AnswerStatusPayload {
  userId: string;
  displayName: string;
  answered: boolean;
  answeredCount: number;
  totalPlayers: number;
}

export interface AnswerPhaseEndedPayload {
  questionId: number;
  answeredCount: number;
  totalPlayers: number;
  allAnswered?: boolean; // true only when every player answered (not just timer expiry)
}

export interface LeaderboardEntry {
  userId: string;
  displayName: string;
  score: number;
  rank: number;
}

export type AnswerReveal =
  | { type: 'multiple_choice'; correctIndices: number[] }
  | { type: 'true_false'; correctValue: boolean }
  | { type: 'fill_in_the_blank'; acceptedAnswers: string[]; editDistance: number }
  | { type: 'completeness' }
  | { type: 'multi_select'; answerPoints: number[] }
  | { type: 'pin_drop'; target: Point; fullRadius: number; zeroRadius: number }
  | {
      type: 'estimate';
      answer: number;
      unit: string;
      tolerance: { mode: 'relative' | 'absolute'; full: number; zero: number };
    }
  | Record<string, never>;

export interface HostResultsPayload {
  questionId: number;
  answerReveal: AnswerReveal;
  answerDistribution: Record<string, number>;
  /** pin_drop / estimate: every submitted pin or number (anonymous). */
  answerValues?: (Point | number)[];
  totalAnswered: number;
  totalPlayers: number;
  /** Images to download now, for the question that comes next (T8). */
  prefetchImageIds?: string[];
}

export interface HostQuestionSummaryItem {
  questionId: number;
  questionNumber: number;
  prompt: string;
  type: QuestionType;
  gradingType: 'ACCURACY' | 'COMPLETENESS';
  config: QuestionConfig;
  pointsValue: number;
  answerReveal: AnswerReveal;
  answerDistribution: Record<string, number>;
  /** pin_drop / estimate: every submitted pin or number (empty for other types). */
  values?: (Point | number)[];
  totalAnswered: number;
  totalPlayers: number;
  correctCount: number;
  avgAnswerTimeMs: number | null;
  /** Players' thumbs and "hard" flags: counts only (docs/plans/question-feedback.md D3). */
  feedback: FeedbackCounts;
}

export interface FeedbackCounts {
  up: number;
  down: number;
  flagged: number;
}

export interface HostGameOverPayload {
  scores: number[];
  playerCount: number;
  maxPossibleScore: number;
  questionSummary: HostQuestionSummaryItem[];
}

export type HostPhase = 'lobby' | 'question' | 'results' | 'gameover';
