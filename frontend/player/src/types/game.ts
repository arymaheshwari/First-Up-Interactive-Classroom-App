export interface SyncStatePayload {
  status: 'LOBBY' | 'IN_PROGRESS' | 'COMPLETED' | 'ABANDONED';
  playerCount: number;
  reactionsEnabled?: boolean;
  questionLocked?: boolean;
  /** Images to download now, for the question that comes next (T8). */
  prefetchImageIds?: string[];
}

export interface PlayerJoinedPayload {
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
  prompt: string;
  config: QuestionConfig;
  timeLimitSeconds: number;
  pointsValue: number;
}

export interface AnswerResultPayload {
  questionId: number;
  isCorrect: boolean;
  pointsAwarded: number;
  totalScore: number;
  alreadyAnswered?: boolean;
}

export interface EstimateTolerance {
  mode: 'relative' | 'absolute';
  full: number;
  zero: number;
}

export type PlayerAnswerReveal =
  | { type: 'multiple_choice'; correctIndices: number[] }
  | { type: 'true_false'; correctValue: boolean }
  | { type: 'fill_in_the_blank'; acceptedAnswers: string[]; editDistance: number }
  | { type: 'completeness' }
  | { type: 'multi_select'; answerPoints: number[] }
  | { type: 'pin_drop'; target: Point; fullRadius: number; zeroRadius: number }
  | { type: 'estimate'; answer: number; unit: string; tolerance: EstimateTolerance };

export interface PlayerResultsPayload {
  questionId: number;
  answerReveal: PlayerAnswerReveal;
  yourPoints: number;
  yourScore: number;
  yourRank: number;
  playerCount: number;
  /** Images to download now, for the question that comes next (T8). */
  prefetchImageIds?: string[];
}

export interface PlayerAnswer {
  selectedIndex?: number;
  selectedValue?: boolean;
  text?: string;
  selectedIndices?: number[];
  point?: Point;
  value?: number;
}

export interface QuestionSummaryItem {
  questionId: number;
  prompt: string;
  type: QuestionType;
  gradingType: 'ACCURACY' | 'COMPLETENESS';
  config: QuestionConfig;
  pointsAwarded: number;
  maxPoints: number;
  answerTimeMs: number | null;
  playerAnswer: PlayerAnswer | null;
  answerReveal: PlayerAnswerReveal;
}

export interface PlayerGameOverPayload {
  yourFinalScore: number;
  yourFinalRank: number;
  playerCount: number;
  questionSummary: QuestionSummaryItem[];
}

export type PlayerPhase = 'lobby' | 'question' | 'feedback' | 'results' | 'gameover';
