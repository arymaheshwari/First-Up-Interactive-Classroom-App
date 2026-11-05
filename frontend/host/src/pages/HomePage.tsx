import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader } from '../components/ui/card';
import { ThemeToggle } from '../components/ui/ThemeToggle';
import { GlassSelect } from '../components/ui/GlassSelect';
import './home.css';

interface Course { id: number; name: string; semester: string }
interface Game { id: number; title: string }
interface ActiveSession {
  session_id: string;
  room_code: string;
  status: string;
  game_title: string;
  course_name: string;
  course_semester: string;
}

export default function HomePage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [games, setGames] = useState<Game[]>([]);
  const [activeSessions, setActiveSessions] = useState<ActiveSession[]>([]);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [courseId, setCourseId] = useState<number | ''>('');
  const [gameId, setGameId] = useState<number | ''>('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [gamesLoading, setGamesLoading] = useState(false);
  const [gamesLoadFailed, setGamesLoadFailed] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([
      api.get<Course[]>('/game/my-courses'),
      api.get<ActiveSession[]>('/game/my-active-sessions'),
    ]).then(([c, s]) => {
      setCourses(c);
      setActiveSessions(s);
      if (c.length === 1) setCourseId(c[0].id);
    }).catch(() => setError('Failed to load courses or games. Are you still logged in?'))
      .finally(() => setInitialLoading(false));
  }, []);

  // Games belong to one course, so the quiz list follows the selected course.
  useEffect(() => {
    setGameId('');
    setGamesLoadFailed(false);
    if (courseId === '') {
      setGames([]);
      setGamesLoading(false);
      return;
    }
    let current = true; // ignore responses for a course the user has switched away from
    setGames([]);
    setGamesLoading(true);
    api.get<Game[]>(`/game/my-games?course_id=${courseId}`)
      .then((g) => {
        if (!current) return;
        setGames(g);
        if (g.length === 1) setGameId(g[0].id);
      })
      .catch(() => {
        if (current) {
          setGamesLoadFailed(true);
          setError('Failed to load quizzes for this course.');
        }
      })
      .finally(() => { if (current) setGamesLoading(false); });
    return () => {
      current = false;
    };
  }, [courseId]);

  async function deleteSession(sessionId: string) {
    try {
      await api.delete(`/game/sessions/${sessionId}`);
      setActiveSessions(prev => prev.filter(s => s.session_id !== sessionId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete session');
    } finally {
      setConfirmDelete(null);
    }
  }

  async function createRoom() {
    if (!courseId || !gameId) return;
    setError('');
    setLoading(true);
    try {
      const data = await api.post<{ room_code: string }>('/game/rooms', {
        course_id: courseId,
        game_id: gameId,
      });
      navigate(`/game/${data.room_code}/lobby`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create room');
      setLoading(false);
    }
  }

  function logout() {
    localStorage.removeItem('token');
    navigate('/login');
  }

  return (
    <main className="host-home">
      <div className="host-home__shell">
        <header className="host-home__top">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-accent-fg">Buzzer · Host</p>
            <h1 className="mt-3 text-3xl font-bold tracking-tight text-fg sm:text-4xl">Host dashboard</h1>
          </div>
          <div className="host-home__tools">
            <Button variant="outline" onClick={() => navigate('/manage')} className="host-home__tool">
              Manage games & rosters
            </Button>
            <Button variant="ghost" onClick={logout} className="host-home__tool">Sign Out</Button>
            <ThemeToggle className="host-home__theme-toggle" />
          </div>
        </header>

        <div className="host-home__grid">
          <Card className="host-home__panel">
            <CardHeader className="host-home__panel-header">
              <p className="text-xs font-semibold uppercase tracking-widest text-accent-fg">New session</p>
              <h2 className="mt-2 text-2xl font-bold tracking-tight text-fg">Create a room</h2>
              <p className="mt-1 text-sm text-fg-muted">Choose a course and quiz to begin.</p>
            </CardHeader>
            <CardContent className="host-home__panel-content space-y-5">
              <GlassSelect
                id="host-home-course"
                label="Course"
                value={courseId}
                onChange={setCourseId}
                placeholder="Select a course…"
                options={courses.map(c => ({ value: c.id, label: `${c.name} — ${c.semester}` }))}
                disabled={initialLoading || courses.length === 0}
              />
              <div>
                <GlassSelect
                  id="host-home-quiz"
                  label="Quiz"
                  value={gameId}
                  onChange={setGameId}
                  placeholder={courseId === '' ? 'Select a course first' : gamesLoading ? 'Loading quizzes…' : 'Select a quiz…'}
                  options={games.map(g => ({ value: g.id, label: g.title }))}
                  disabled={courseId === '' || gamesLoading || games.length === 0}
                />
                {courseId !== '' && !gamesLoading && !gamesLoadFailed && games.length === 0 && (
                  <p className="mt-2 text-xs text-fg-subtle">No quizzes you can run in this course yet.</p>
                )}
              </div>
              {error && <p role="alert" className="text-sm text-danger-fg">{error}</p>}
              <Button
                className="host-home__primary w-full"
                size="lg"
                onClick={createRoom}
                disabled={!courseId || !gameId || loading}
              >
                {loading ? 'Creating room…' : 'Create Room'}
              </Button>
            </CardContent>
          </Card>

          <div className="host-home__sessions-slot">
            <Card className="host-home__panel host-home__sessions-panel">
              <CardHeader className="host-home__panel-header">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-widest text-accent-fg">Continue hosting</p>
                    <h2 className="mt-2 text-2xl font-bold tracking-tight text-fg">Active sessions</h2>
                  </div>
                  <span className="host-home__count text-sm font-semibold text-fg" aria-label={`${activeSessions.length} active sessions`}>
                    {activeSessions.length}
                  </span>
                </div>
              </CardHeader>
              <CardContent className="host-home__panel-content host-home__sessions-content">
                {initialLoading ? (
                  <p role="status" className="text-sm text-fg-muted">Loading sessions…</p>
                ) : activeSessions.length === 0 ? (
                  <div className="host-home__empty">
                    <p className="font-medium text-fg">No active sessions</p>
                    <p className="mt-1 text-sm text-fg-muted">Rooms you start will appear here.</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {activeSessions.map(s => (
                      <div key={s.session_id} className="host-home__session">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="min-w-0 font-semibold text-fg break-words">{s.game_title}</p>
                            <span className={s.status === 'IN_PROGRESS' ? 'host-home__status bg-success-subtle text-success-fg' : 'host-home__status bg-warning-subtle text-warning-fg'}>
                              {s.status === 'IN_PROGRESS' ? 'In Progress' : 'Lobby'}
                            </span>
                          </div>
                          <p className="mt-1 text-sm text-fg-muted">{s.course_name} · {s.course_semester}</p>
                          <p className="mt-2 text-xs text-fg-muted">Room <span className="font-mono font-semibold text-fg">{s.room_code}</span></p>
                        </div>
                        <div className="host-home__session-actions">
                          {confirmDelete === s.session_id ? (
                            <>
                              <p role="status" className="w-full text-xs font-medium text-danger-fg">Delete all data?</p>
                              <Button size="sm" variant="destructive" onClick={() => deleteSession(s.session_id)}>Confirm</Button>
                              <Button size="sm" variant="outline" onClick={() => setConfirmDelete(null)}>Cancel</Button>
                            </>
                          ) : (
                            <>
                              <Button size="sm" variant="outline" onClick={() => navigate(`/game/${s.room_code}/lobby`)}>Rejoin</Button>
                              <Button size="sm" variant="destructive" onClick={() => setConfirmDelete(s.session_id)}>Delete</Button>
                            </>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </main>
  );
}
