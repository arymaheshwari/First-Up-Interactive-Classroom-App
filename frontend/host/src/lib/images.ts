/**
 * The course image library (T8): typed wrappers over /api/host/... image routes and
 * the public /api/images/{id} URL. See docs/plans/t8-image-support.md §4.3 / §5.1.
 */
import { api, ApiError } from './api';
import type { QuestionConfig } from '../types/game';

export interface ImageUsage {
  game_id: number;
  game_title: string;
  question_id: number;
  /** 1-based, as the question editor numbers questions. */
  question_number: number;
  field: 'prompt' | 'option' | 'pin_drop';
}

export interface ImageInfo {
  id: string;
  course_id: number;
  filename: string;
  content_type: string;
  width: number;
  height: number;
  byte_size: number;
  sha256: string;
  created_at: string;
  updated_at: string;
  url: string;
  used_by: ImageUsage[];
}

export interface UploadedImage extends ImageInfo {
  /** True when an identical image was already in the library (it's returned instead). */
  deduplicated: boolean;
}

/** Public URL; needs no login, so plain <img src> works on every screen. */
export function imageUrl(id: string): string {
  return `/api/images/${id}`;
}

export function listImages(courseId: number): Promise<ImageInfo[]> {
  return api.get<ImageInfo[]>(`/host/courses/${courseId}/images`);
}

function fileForm(file: File): FormData {
  const form = new FormData();
  form.append('file', file);
  return form;
}

export function uploadImage(courseId: number, file: File): Promise<UploadedImage> {
  return api.postForm<UploadedImage>(`/host/courses/${courseId}/images`, fileForm(file));
}

export function replaceImage(id: string, file: File): Promise<ImageInfo> {
  return api.putForm<ImageInfo>(`/host/images/${id}`, fileForm(file));
}

export function deleteImage(id: string): Promise<void> {
  return api.delete<void>(`/host/images/${id}`);
}

/** The `used_by` list a 409 carries (image in use, or used by a live room), if any. */
export function usagesFromError(err: unknown): ImageUsage[] {
  if (err instanceof ApiError && err.status === 409) {
    const body = err.body as { used_by?: ImageUsage[] };
    return body.used_by ?? [];
  }
  return [];
}

/** "Used by 2 questions" counts distinct questions, not (question, field) entries. */
export function questionCount(usages: ImageUsage[]): number {
  return new Set(usages.map((u) => u.question_id)).size;
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

// ---------------------------------------------------------------------------
// Game screens (T8 §5.3)
// ---------------------------------------------------------------------------

const preloaded = new Set<string>();

/** Start downloading images now, so they're cached when their question appears. */
export function preloadImages(ids: (string | null | undefined)[] | undefined): void {
  for (const id of ids ?? []) {
    if (!id || preloaded.has(id)) continue;
    preloaded.add(id);
    const img = new Image();
    img.decoding = 'async';
    img.src = imageUrl(id);
  }
}

/** Every image a question shows on the projector: prompt, options and the Pin It picture. */
export function questionImageIds(config: QuestionConfig | undefined): string[] {
  if (!config) return [];
  return [config.promptImageId, ...(config.optionImages ?? []), config.image?.imageId].filter(
    (id): id is string => !!id,
  );
}

/**
 * A prompt as plain text for alt attributes: <br> becomes a space and other tags are
 * dropped. DOMParser documents are inert (no <img onerror> runs), unlike innerHTML.
 */
export function promptAltText(prompt: string): string {
  const html = prompt.replace(/<br\s*\/?>/gi, ' ');
  const text = new DOMParser().parseFromString(html, 'text/html').body.textContent ?? '';
  return text.replace(/\s+/g, ' ').trim();
}
