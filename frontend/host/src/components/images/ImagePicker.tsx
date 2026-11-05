/**
 * Dialog for choosing an image from a course's library, with an inline upload.
 * Returns the whole ImageInfo (not just the id) so the editor knows the image's
 * size — the Pin It preview needs it before the question is saved (T8 §5.1).
 */
import { useEffect, useRef, useState } from 'react';
import { ImagePlus, X } from 'lucide-react';
import { Button } from '../ui/button';
import { type ImageInfo, imageUrl, listImages, uploadImage } from '../../lib/images';

interface ImagePickerProps {
  courseId: number;
  title?: string;
  onPick: (image: ImageInfo) => void;
  onClose: () => void;
}

export function ImagePicker({ courseId, title = 'Choose an image', onPick, onClose }: ImagePickerProps) {
  const [images, setImages] = useState<ImageInfo[] | null>(null);
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    listImages(courseId)
      .then(setImages)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load images'));
  }, [courseId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (fileRef.current) fileRef.current.value = '';
    if (!file) return;
    setUploading(true);
    setError('');
    try {
      onPick(await uploadImage(courseId, file));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-50 bg-scrim/60 flex items-center justify-center p-6"
      onClick={onClose}
    >
      <div
        className="w-full max-w-3xl max-h-[85vh] flex flex-col rounded-card border border-line bg-surface-raised shadow-raised"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-line">
          <h3 className="font-semibold text-fg">{title}</h3>
          <div className="flex items-center gap-2">
            <input
              ref={fileRef}
              type="file"
              accept="image/png,image/jpeg,image/gif,image/webp"
              className="hidden"
              onChange={handleUpload}
            />
            <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()} disabled={uploading}>
              <ImagePlus size={14} className="mr-1" /> {uploading ? 'Uploading…' : 'Upload new'}
            </Button>
            <button onClick={onClose} aria-label="Close" className="text-fg-muted hover:text-fg">
              <X size={20} />
            </button>
          </div>
        </div>
        <div className="p-5 overflow-auto">
          {error && <p className="text-danger-fg text-sm mb-3">{error}</p>}
          {images === null && !error && <p className="text-fg-muted text-sm">Loading…</p>}
          {images?.length === 0 && (
            <p className="text-fg-muted text-sm">This course has no images yet — upload one.</p>
          )}
          <ul className="grid grid-cols-3 sm:grid-cols-4 gap-3">
            {images?.map((img) => (
              <li key={img.id}>
                <button
                  type="button"
                  onClick={() => onPick(img)}
                  className="focus-inset w-full rounded-control border border-line bg-surface hover:border-accent-fg overflow-hidden"
                >
                  <div className="aspect-[4/3] bg-surface-sunken flex items-center justify-center">
                    <img src={imageUrl(img.id)} alt={img.filename} loading="lazy" decoding="async" className="max-h-full max-w-full object-contain" />
                  </div>
                  <p className="px-2 py-1 text-xs text-fg-muted truncate" title={img.filename}>{img.filename}</p>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
