/**
 * Question images on the phone (T8): the public /api/images/{id} URL and preloading.
 * See docs/plans/t8-image-support.md §5.3.
 */
import type { QuestionConfig, QuestionImage } from '../types/game';

/** Public URL; needs no login, so plain <img src> works. */
export function imageUrl(id: string): string {
  return `/api/images/${id}`;
}

/** GridCanvas's `image` prop for a Pin It picture. */
export function canvasImage(image: QuestionImage) {
  return { url: imageUrl(image.imageId), width: image.width, height: image.height };
}

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

/**
 * The images a phone shows for a question: option pictures and the Pin It picture.
 * Never the prompt image, which only the projector shows.
 */
export function phoneImageIds(config: QuestionConfig | undefined): string[] {
  if (!config) return [];
  return [...(config.optionImages ?? []), config.image?.imageId].filter((id): id is string => !!id);
}
