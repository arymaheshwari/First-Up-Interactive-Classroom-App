import { useEffect, useState } from 'react';
import { Plus, Users, Pencil } from 'lucide-react';
import { api } from '../lib/api';
import { hostAppLink } from '../lib/hostApp';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader } from '../components/ui/card';
import { Input } from '../components/ui/input';

type GuestPolicy = 'ROSTER_ONLY' | 'OPEN' | 'DISABLED';

const GUEST_POLICIES: { value: GuestPolicy; label: string; help: string }[] = [
  { value: 'ROSTER_ONLY', label: 'Roster emails only', help: 'Guests must join with an email on this course roster' },
  { value: 'OPEN', label: 'Anyone with the room code', help: 'For parties and open events' },
  { value: 'DISABLED', label: 'No guests', help: 'Only NetID and course accounts can join' },
];

interface Course {
  id: number;
  name: string;
  semester: string;
  guest_policy: GuestPolicy;
  created_at: string;
}

function GuestPolicySelect({
  value,
  onChange,
}: {
  value: GuestPolicy;
  onChange: (v: GuestPolicy) => void;
}) {
  return (
    <label className="w-full text-sm text-fg-muted">
      <span className="block text-xs text-fg-muted mb-1">Guest access</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as GuestPolicy)}
        className="w-full rounded-control border border-line-strong bg-surface-sunken px-3 py-2 text-fg focus:border-focus"
      >
        {GUEST_POLICIES.map((p) => (
          <option key={p.value} value={p.value}>{p.label}</option>
        ))}
      </select>
      <span className="block text-xs text-fg-subtle mt-1">
        {GUEST_POLICIES.find((p) => p.value === value)?.help}
      </span>
    </label>
  );
}

export default function CoursesPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [semester, setSemester] = useState('');
  const [guestPolicy, setGuestPolicy] = useState<GuestPolicy>('ROSTER_ONLY');
  const [saving, setSaving] = useState(false);
  const [editingCourse, setEditingCourse] = useState<Course | null>(null);
  const [editName, setEditName] = useState('');
  const [editSemester, setEditSemester] = useState('');
  const [editGuestPolicy, setEditGuestPolicy] = useState<GuestPolicy>('ROSTER_ONLY');
  const [editSaving, setEditSaving] = useState(false);

  async function load() {
    try {
      const data = await api.get<Course[]>('/admin/courses');
      setCourses(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load courses');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post('/admin/courses', { name, semester, guest_policy: guestPolicy });
      setName('');
      setSemester('');
      setGuestPolicy('ROSTER_ONLY');
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create course');
    } finally {
      setSaving(false);
    }
  }

  function startEdit(c: Course) {
    setEditingCourse(c);
    setEditName(c.name);
    setEditSemester(c.semester);
    setEditGuestPolicy(c.guest_policy);
    setShowForm(false);
  }

  async function handleEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!editingCourse) return;
    setEditSaving(true);
    setError('');
    try {
      await api.put(`/admin/courses/${editingCourse.id}`, {
        name: editName,
        semester: editSemester,
        guest_policy: editGuestPolicy,
      });
      setEditingCourse(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update course');
    } finally {
      setEditSaving(false);
    }
  }

  return (
    <div className="p-6 max-w-7xl space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold tracking-tight text-fg">Courses</h2>
        <Button onClick={() => { setShowForm(!showForm); setEditingCourse(null); }} size="sm">
          <Plus size={16} className="mr-1" /> New Course
        </Button>
      </div>

      {error && <p className="text-danger-fg text-sm">{error}</p>}

      {showForm && (
        <Card>
          <CardHeader><h3 className="text-base font-semibold text-fg">Create Course</h3></CardHeader>
          <CardContent>
            <form onSubmit={handleCreate} className="flex gap-3 flex-wrap">
              <Input
                placeholder="Course name (e.g. CS 537)"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="flex-1 min-w-48"
                required
              />
              <Input
                placeholder="Semester (e.g. Fall 2026)"
                value={semester}
                onChange={(e) => setSemester(e.target.value)}
                className="flex-1 min-w-48"
                required
              />
              <GuestPolicySelect value={guestPolicy} onChange={setGuestPolicy} />
              <Button size="sm" type="submit" disabled={saving}>{saving ? 'Creating…' : 'Create'}</Button>
              <Button size="sm" type="button" variant="ghost" onClick={() => setShowForm(false)}>Cancel</Button>
            </form>
          </CardContent>
        </Card>
      )}

      {editingCourse && (
        <Card>
          <CardHeader><h3 className="text-base font-semibold text-fg">Edit Course</h3></CardHeader>
          <CardContent>
            <form onSubmit={handleEdit} className="flex gap-3 flex-wrap">
              <Input
                placeholder="Course name"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                className="flex-1 min-w-48"
                required
              />
              <Input
                placeholder="Semester"
                value={editSemester}
                onChange={(e) => setEditSemester(e.target.value)}
                className="flex-1 min-w-48"
                required
              />
              <GuestPolicySelect value={editGuestPolicy} onChange={setEditGuestPolicy} />
              <Button size="sm" type="submit" disabled={editSaving}>{editSaving ? 'Saving…' : 'Save'}</Button>
              <Button size="sm" type="button" variant="ghost" onClick={() => setEditingCourse(null)}>Cancel</Button>
            </form>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <p className="text-fg-muted">Loading…</p>
      ) : courses.length === 0 ? (
        <p className="text-fg-muted">No courses yet. Create one above.</p>
      ) : (
        <div className="space-y-3">
          {courses.map((c) => (
            <Card key={c.id} className="flex items-center justify-between px-6 py-4">
              <div>
                <p className="font-semibold text-fg">{c.name}</p>
                <p className="text-fg-muted text-sm">
                  {c.semester}
                  <span className="text-fg-subtle">
                    {' · Guests: '}
                    {GUEST_POLICIES.find((p) => p.value === c.guest_policy)?.label}
                  </span>
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => startEdit(c)}
                >
                  <Pencil size={14} />
                </Button>
                <a
                  href={hostAppLink(`manage/courses/${c.id}/roster`)}
                  title="Opens in the Host app"
                  className="inline-flex items-center rounded-control border border-line-strong px-3 py-1.5 text-sm font-medium text-fg-muted hover:bg-surface-hover hover:text-fg transition-colors"
                >
                  <Users size={14} className="mr-1" /> Roster
                </a>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
