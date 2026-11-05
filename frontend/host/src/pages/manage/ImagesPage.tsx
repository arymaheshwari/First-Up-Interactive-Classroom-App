import { useEffect, useRef, useState } from 'react';
import { ImagePlus, RefreshCw, Trash2, X } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { CoursePicker, NO_COURSES_MESSAGE, useHostedCourse } from './CoursePicker';
import {
  type ImageInfo,
  type ImageUsage,
  deleteImage,
  formatBytes,
  imageUrl,
  listImages,
  questionCount,
  replaceImage,
  uploadImage,
  usagesFromError,
} from '../../lib/images';

/** Mirrors the backend's per-course quota (image_service.COURSE_QUOTA_BYTES). */
const QUOTA_BYTES = 200 * 1024 * 1024;

function usageLabel(u: ImageUsage): string {
  const where = u.field === 'prompt' ? 'prompt' : u.field === 'option' ? 'answer option' : 'Pin It background';
  return `${u.game_title} — Q${u.question_number} (${where})`;
}

/** Reads a local file's pixel size, to warn before a replace changes a Pin It image's shape. */
function readSize(file: File): Promise<{ width: number; height: number } | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const probe = new Image();
    probe.onload = () => {
      resolve({ width: probe.naturalWidth, height: probe.naturalHeight });
      URL.revokeObjectURL(url);
    };
    probe.onerror = () => {
      resolve(null);
      URL.revokeObjectURL(url);
    };
    probe.src = url;
  });
}

export default function ImagesPage() {
  const { courses, courseId, selectCourse, error: courseError } = useHostedCourse();
  const [images, setImages] = useState<ImageInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [blockedBy, setBlockedBy] = useState<{ name: string; usages: ImageUsage[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [viewing, setViewing] = useState<ImageInfo | null>(null);
  // Images replaced in this visit get a cache-busting suffix so thumbnails refresh at once.
  const [versions, setVersions] = useState<Record<string, string>>({});
  const uploadRef = useRef<HTMLInputElement>(null);
  const replaceRef = useRef<HTMLInputElement>(null);
  const replacing = useRef<ImageInfo | null>(null);
  const latestCourse = useRef<number | null>(null);

  async function load(course: number) {
    latestCourse.current = course;
    try {
      const data = await listImages(course);
      if (latestCourse.current === course) setImages(data);
    } catch (err) {
      if (latestCourse.current === course) {
        setError(err instanceof Error ? err.message : 'Failed to load images');
      }
    } finally {
      if (latestCourse.current === course) setLoading(false);
    }
  }

  useEffect(() => {
    if (courseId === null) return;
    setLoading(true);
    setNotice('');
    setBlockedBy(null);
    void load(courseId);
  }, [courseId]);

  useEffect(() => {
    if (!viewing) return;
    const close = (e: KeyboardEvent) => e.key === 'Escape' && setViewing(null);
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [viewing]);

  const src = (img: ImageInfo) => imageUrl(img.id) + (versions[img.id] ? `?v=${versions[img.id]}` : '');

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (!files.length || courseId === null) return;
    setBusy(true);
    setError('');
    setNotice('');
    setBlockedBy(null);
    const duplicates: string[] = [];
    try {
      for (const file of files) {
        const result = await uploadImage(courseId, file);
        if (result.deduplicated) duplicates.push(`${file.name} (already in the library as ${result.filename})`);
      }
      if (duplicates.length) setNotice(`Not added again: ${duplicates.join(', ')}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setBusy(false);
      if (uploadRef.current) uploadRef.current.value = '';
      await load(courseId);
    }
  }

  function startReplace(img: ImageInfo) {
    replacing.current = img;
    replaceRef.current?.click();
  }

  async function handleReplace(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    const img = replacing.current;
    if (replaceRef.current) replaceRef.current.value = '';
    if (!file || !img || courseId === null) return;

    const pinUses = img.used_by.filter((u) => u.field === 'pin_drop');
    if (pinUses.length) {
      const size = await readSize(file);
      const oldAspect = img.width / img.height;
      const changed = size !== null && Math.abs(size.width / size.height - oldAspect) / oldAspect > 0.01;
      const games = [...new Set(pinUses.map((u) => u.game_title))].join(', ');
      const ok = confirm(
        `This image is the background of Pin It questions in: ${games}.\n` +
          (changed
            ? 'The new image has a different shape, so the targets will sit somewhere else on the picture.\n'
            : '') +
          'Reports of past sessions will also show the new image. Replace anyway?',
      );
      if (!ok) return;
    }

    setBusy(true);
    setError('');
    setNotice('');
    setBlockedBy(null);
    try {
      await replaceImage(img.id, file);
      setVersions((prev) => ({ ...prev, [img.id]: String(Date.now()) }));
      setNotice(`Replaced ${img.filename}.`);
    } catch (err) {
      const usages = usagesFromError(err);
      if (usages.length) setBlockedBy({ name: img.filename, usages });
      setError(err instanceof Error ? err.message : 'Replace failed');
    } finally {
      setBusy(false);
      await load(courseId);
    }
  }

  async function handleDelete(img: ImageInfo) {
    if (!confirm(`Delete ${img.filename}? This cannot be undone.`)) return;
    setError('');
    setNotice('');
    setBlockedBy(null);
    try {
      await deleteImage(img.id);
      setImages((prev) => prev.filter((i) => i.id !== img.id));
    } catch (err) {
      const usages = usagesFromError(err);
      if (usages.length) setBlockedBy({ name: img.filename, usages });
      setError(err instanceof Error ? err.message : 'Delete failed');
    }
  }

  const used = images.reduce((sum, i) => sum + i.byte_size, 0);

  return (
    <div className="p-8 max-w-5xl">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-2xl font-bold text-fg">Images</h2>
        {courses && courses.length > 0 && (
          <div className="flex gap-2">
            <CoursePicker courses={courses} courseId={courseId} onSelect={selectCourse} />
            <input
              ref={uploadRef}
              type="file"
              accept="image/png,image/jpeg,image/gif,image/webp"
              multiple
              className="hidden"
              onChange={handleUpload}
            />
            <Button size="sm" onClick={() => uploadRef.current?.click()} disabled={busy}>
              <ImagePlus size={14} className="mr-1" /> {busy ? 'Working…' : 'Upload images'}
            </Button>
          </div>
        )}
      </div>
      <input ref={replaceRef} type="file" accept="image/png,image/jpeg,image/gif,image/webp" className="hidden" onChange={handleReplace} />

      {courses && courses.length > 0 && (
        <p className="text-fg-muted text-sm mb-6">
          PNG, JPEG, GIF or WebP, up to 5 MB. Images are resized to at most 1600 px and their metadata
          (such as location) is removed; animations keep only their first frame. Anyone with an image's link can
          view it. Library: {formatBytes(used)} of {formatBytes(QUOTA_BYTES)}.
        </p>
      )}

      {(error || courseError) && <p className="text-danger-fg mb-2 text-sm">{error || courseError}</p>}
      {blockedBy && (
        <div className="mb-4 rounded-control border border-warning/40 bg-warning p-3 text-sm text-warning-fg">
          <p className="font-semibold mb-1">{blockedBy.name} is used by:</p>
          <ul className="list-disc pl-5 space-y-0.5">
            {blockedBy.usages.map((u) => (
              <li key={`${u.question_id}-${u.field}`}>{usageLabel(u)}</li>
            ))}
          </ul>
        </div>
      )}
      {notice && <p className="text-fg-muted mb-4 text-sm">{notice}</p>}
      {courses?.length === 0 && <p className="text-fg-muted">{NO_COURSES_MESSAGE}</p>}

      {loading && courses && courses.length > 0 ? (
        <p className="text-fg-muted">Loading…</p>
      ) : images.length === 0 && courses && courses.length > 0 ? (
        <p className="text-fg-muted">No images yet. Upload some to use them in questions.</p>
      ) : (
        <ul className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {images.map((img) => {
            const count = questionCount(img.used_by);
            return (
              <li key={img.id} className="rounded-card border border-line bg-surface overflow-hidden flex flex-col">
                <button
                  type="button"
                  onClick={() => setViewing(img)}
                  className="focus-inset aspect-[4/3] bg-surface-sunken flex items-center justify-center"
                  aria-label={`View ${img.filename}`}
                >
                  <img src={src(img)} alt={img.filename} loading="lazy" decoding="async" className="max-h-full max-w-full object-contain" />
                </button>
                <div className="p-3 flex-1 flex flex-col gap-1">
                  <p className="text-fg text-sm font-medium truncate" title={img.filename}>{img.filename}</p>
                  <p className="text-fg-subtle text-xs">
                    {img.width}×{img.height} · {formatBytes(img.byte_size)}
                  </p>
                  <p
                    className={`text-xs ${count ? 'text-fg-muted' : 'text-fg-subtle'}`}
                    title={img.used_by.map(usageLabel).join('\n') || undefined}
                  >
                    {count ? `Used by ${count} question${count === 1 ? '' : 's'}` : 'Not used yet'}
                  </p>
                  <div className="flex gap-1 mt-auto pt-2">
                    <Button variant="outline" size="sm" onClick={() => startReplace(img)} disabled={busy}>
                      <RefreshCw size={12} className="mr-1" /> Replace
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => void handleDelete(img)} aria-label={`Delete ${img.filename}`}>
                      <Trash2 size={14} />
                    </Button>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {viewing && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={viewing.filename}
          className="fixed inset-0 z-50 bg-scrim/60 flex items-center justify-center p-6"
          onClick={() => setViewing(null)}
        >
          <button
            className="absolute top-4 right-4 text-fg hover:text-fg"
            aria-label="Close"
            onClick={() => setViewing(null)}
          >
            <X size={24} />
          </button>
          <figure className="max-h-full max-w-full" onClick={(e) => e.stopPropagation()}>
            <img src={src(viewing)} alt={viewing.filename} className="max-h-[80vh] max-w-full object-contain rounded-control" />
            <figcaption className="text-center text-fg-muted text-sm mt-2">
              {viewing.filename} · {viewing.width}×{viewing.height} · {formatBytes(viewing.byte_size)}
            </figcaption>
          </figure>
        </div>
      )}
    </div>
  );
}
