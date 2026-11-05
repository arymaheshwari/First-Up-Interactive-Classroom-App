import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, List, Upload, Trash2, Pencil } from 'lucide-react';
import { api } from '../../lib/api';
import { Button } from '../../components/ui/button';
import { Card, CardContent, CardHeader } from '../../components/ui/card';
import { Input } from '../../components/ui/input';
import { GlassSelect } from '../../components/ui/GlassSelect';
import { NO_COURSES_MESSAGE, useHostedCourse } from './CoursePicker';

interface Game {
  id: number;
  course_id: number;
  title: string;
  description: string;
  max_players: number;
  created_at: string;
}

export default function GamesPage() {
  const { courses, courseId, selectCourse, error: courseError } = useHostedCourse();
  const [games, setGames] = useState<Game[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [maxPlayers, setMaxPlayers] = useState('150');
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const [editingGame, setEditingGame] = useState<Game | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editMaxPlayers, setEditMaxPlayers] = useState('');
  const [editSaving, setEditSaving] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  // Ignore responses for a course the user has switched away from.
  const latestCourse = useRef<number | null>(null);

  async function load(course: number) {
    latestCourse.current = course;
    try {
      const data = await api.get<Game[]>(`/host/courses/${course}/games`);
      if (latestCourse.current === course) setGames(data);
    } catch (err) {
      if (latestCourse.current === course) {
        setError(err instanceof Error ? err.message : 'Failed to load games');
      }
    } finally {
      if (latestCourse.current === course) setLoading(false);
    }
  }

  useEffect(() => {
    if (courseId === null) return;
    setLoading(true);
    setGames([]);
    setError('');
    void load(courseId);
  }, [courseId]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      if (courseId === null) return;
      await api.post('/host/games', {
        course_id: courseId,
        title,
        description,
        max_players: Number(maxPlayers),
      });
      setTitle(''); setDescription(''); setMaxPlayers('150');
      setShowForm(false);
      await load(courseId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create game');
    } finally {
      setSaving(false);
    }
  }

  function startEdit(g: Game) {
    setEditingGame(g);
    setEditTitle(g.title);
    setEditDescription(g.description);
    setEditMaxPlayers(String(g.max_players));
  }

  async function handleEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!editingGame) return;
    setEditSaving(true);
    setError('');
    try {
      await api.put(`/host/games/${editingGame.id}`, {
        title: editTitle,
        description: editDescription,
        max_players: Number(editMaxPlayers),
      });
      setEditingGame(null);
      await load(editingGame.course_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update game');
    } finally {
      setEditSaving(false);
    }
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || courseId === null) return;
    setImporting(true);
    setError('');
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('course_id', String(courseId));
      const result = await api.postForm<{ game_id: number }>('/host/games/import', form);
      navigate(`/manage/games/${result.game_id}/questions`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed');
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  async function deleteGame(id: number) {
    if (!confirm('Delete this game and all its sessions? This cannot be undone.')) return;
    try {
      await api.delete(`/host/games/${id}`);
      setGames((prev) => prev.filter((g) => g.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete game');
    }
  }

  return (
    <div className="manage-page">
      <header className="manage-page__heading">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-accent-fg">Quiz library</p>
        <h2 className="manage-page__title">Games</h2>
        <p className="manage-page__intro">Create games, edit questions, and import a quiz.</p>
      </header>

      {courses && courses.length > 0 && (
        <div className="manage-panel manage-toolbar">
          <div className="manage-toolbar__course">
            <GlassSelect
              id="manage-games-course"
              label="Course"
              value={courseId ?? ''}
              onChange={selectCourse}
              placeholder="Select a course…"
              options={courses.map(c => ({ value: c.id, label: `${c.name} — ${c.semester}` }))}
            />
          </div>
          <div className="manage-toolbar__actions">
            <input ref={fileRef} type="file" accept=".json" className="hidden" onChange={handleImport} />
            <Button variant="outline" onClick={() => fileRef.current?.click()} disabled={importing} className="manage-toolbar__action">
              <Upload size={16} aria-hidden="true" />
              {importing ? 'Importing…' : 'Import JSON'}
            </Button>
            <Button onClick={() => setShowForm(!showForm)} className="manage-toolbar__primary">
              <Plus size={18} aria-hidden="true" /> New Game
            </Button>
          </div>
        </div>
      )}

      {(error || courseError) && <p role="alert" className="mt-4 text-sm text-danger-fg">{error || courseError}</p>}
      {courses === null && <p role="status" className="text-fg-muted">Loading courses…</p>}
      {courses?.length === 0 && <p className="text-fg-muted">{NO_COURSES_MESSAGE}</p>}

      {showForm && (
        <Card className="manage-panel manage-form-panel">
          <CardHeader><h3 className="text-lg font-semibold text-fg">Create Game</h3></CardHeader>
          <CardContent>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label htmlFor="manage-new-title" className="manage-form-label">Title</label>
                <Input id="manage-new-title" value={title} onChange={(e) => setTitle(e.target.value)} required className="manage-form-input" />
              </div>
              <div>
                <label htmlFor="manage-new-description" className="manage-form-label">Description <span className="font-normal text-fg-muted">(optional)</span></label>
                <textarea
                  id="manage-new-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="manage-form-input w-full border border-line-strong px-3 py-2 text-fg resize-y"
                  rows={3}
                />
              </div>
              <div>
                <label htmlFor="manage-new-max" className="manage-form-label">Max players</label>
                <Input id="manage-new-max" type="number" value={maxPlayers} onChange={(e) => setMaxPlayers(e.target.value)} min="1" max="500" className="manage-form-input" />
              </div>
              <div className="flex flex-wrap gap-3">
                <Button type="submit" disabled={saving}>{saving ? 'Creating…' : 'Create Game'}</Button>
                <Button type="button" variant="outline" onClick={() => setShowForm(false)}>Cancel</Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {editingGame && (
        <Card className="manage-panel manage-form-panel">
          <CardHeader><h3 className="text-lg font-semibold text-fg">Edit Game</h3></CardHeader>
          <CardContent>
            <form onSubmit={handleEdit} className="space-y-4">
              <div>
                <label htmlFor="manage-edit-title" className="manage-form-label">Title</label>
                <Input id="manage-edit-title" value={editTitle} onChange={(e) => setEditTitle(e.target.value)} required className="manage-form-input" />
              </div>
              <div>
                <label htmlFor="manage-edit-description" className="manage-form-label">Description <span className="font-normal text-fg-muted">(optional)</span></label>
                <textarea
                  id="manage-edit-description"
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  className="manage-form-input w-full border border-line-strong px-3 py-2 text-fg resize-y"
                  rows={3}
                />
              </div>
              <div>
                <label htmlFor="manage-edit-max" className="manage-form-label">Max players</label>
                <Input id="manage-edit-max" type="number" value={editMaxPlayers} onChange={(e) => setEditMaxPlayers(e.target.value)} min="1" max="500" className="manage-form-input" />
              </div>
              <div className="flex flex-wrap gap-3">
                <Button type="submit" disabled={editSaving}>{editSaving ? 'Saving…' : 'Save Changes'}</Button>
                <Button type="button" variant="outline" onClick={() => setEditingGame(null)}>Cancel</Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {courses && courses.length > 0 && (
        <section className="manage-panel manage-list-panel" aria-labelledby="manage-games-list-title">
          <header className="manage-list-panel__header">
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest text-accent-fg">Selected course</p>
              <h3 id="manage-games-list-title" className="mt-1 text-xl font-bold text-fg">Available games</h3>
            </div>
            <span className="manage-list-panel__count" aria-label={`${games.length} games`}>{games.length}</span>
          </header>
          <div className="manage-list-panel__body">
            {loading ? (
              <p role="status" className="text-sm text-fg-muted">Loading games…</p>
            ) : games.length === 0 ? (
              <p className="text-sm text-fg-muted">No games in this course yet.</p>
            ) : games.map(g => (
              <article key={g.id} className="manage-item">
                <div className="min-w-0">
                  <p className="font-semibold text-fg break-words">{g.title}</p>
                  {g.description && <p className="mt-1 text-sm text-fg-muted break-words">{g.description}</p>}
                  <p className="mt-2 text-xs text-fg-subtle">Max {g.max_players} players</p>
                </div>
                <div className="manage-item__actions">
                  <Button variant="outline" size="sm" onClick={() => startEdit(g)} aria-label={`Edit ${g.title}`}>
                    <Pencil size={14} aria-hidden="true" /> Edit
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => navigate(`/manage/games/${g.id}/questions`)}>
                    <List size={14} aria-hidden="true" /> Questions
                  </Button>
                  <Button variant="destructive" size="sm" onClick={() => void deleteGame(g.id)} aria-label={`Delete ${g.title}`}>
                    <Trash2 size={14} aria-hidden="true" /> Delete
                  </Button>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
