import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '../lib/api';
import { isTokenExpired } from '../lib/utils';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Card, CardContent, CardHeader } from '../components/ui/card';
import { ThemeToggle } from '../components/ui/ThemeToggle';
import { ArrowRight, LockKeyhole, Mail, UserRound } from 'lucide-react';
import '../../../shared/theme/auth-scene.css';

type Mode = 'guest' | 'netid' | 'local';

export default function NamePage() {
  const { code = '' } = useParams<{ code: string }>();
  const navigate = useNavigate();

  // Only treat the token as valid if it is present AND not expired
  const isAuthenticated = !isTokenExpired(localStorage.getItem('token'));
  const [mode, setMode] = useState<Mode>(isAuthenticated ? 'netid' : 'guest');

  // Guest fields — pre-fill from localStorage if available
  const [displayName, setDisplayName] = useState(() => localStorage.getItem('playerName') ?? '');
  const [email, setEmail] = useState(() => localStorage.getItem('playerEmail') ?? '');

  // Login fields
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleGuest(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await api.post<{ access_token: string }>('/auth/guest', {
        display_name: displayName.trim(),
        email: email.trim().toLowerCase(),
        room_code: code,
      });
      localStorage.setItem('token', data.access_token);
      localStorage.setItem('playerName', displayName.trim());
      localStorage.setItem('playerEmail', email.trim().toLowerCase());
      navigate(`/game/${code}/lobby`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to join');
    } finally {
      setLoading(false);
    }
  }

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await api.post<{ access_token: string }>('/auth/login', { username, password });
      localStorage.setItem('token', data.access_token);
      navigate(`/game/${code}/lobby`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid credentials');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-scene">
      <ThemeToggle variant="floating" className="bg-surface/85 backdrop-blur-xl" />
      <Card className="auth-scene__card">
        <CardHeader className="auth-scene__header">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-accent-fg">Buzzer · Player</p>
          <h1 className="mt-3 text-3xl font-bold tracking-tight text-fg">Join room {code}</h1>

          {/* Mode toggle — hidden when already authenticated */}
          {!isAuthenticated && (
            <div className="flex mt-6 bg-surface-sunken/70 border border-line-strong/50 rounded-card p-1 gap-1">
              <button
                type="button"
                onClick={() => { setMode('guest'); setError(''); }}
                aria-pressed={mode === 'guest'}
                className={`flex-1 min-h-11 rounded-control text-base font-medium transition-colors ${
                  mode === 'guest'
                    ? 'bg-accent text-on-color'
                    : 'text-fg-muted hover:text-fg'
                }`}
              >
                Join as Guest
              </button>
              <button
                type="button"
                onClick={() => { setMode('netid'); setError(''); }}
                aria-pressed={mode === 'netid' || mode === 'local'}
                className={`flex-1 min-h-11 rounded-control text-base font-medium transition-colors ${
                  mode === 'netid' || mode === 'local'
                    ? 'bg-accent text-on-color'
                    : 'text-fg-muted hover:text-fg'
                }`}
              >
                Sign In
              </button>
            </div>
          )}
        </CardHeader>

        <CardContent className="auth-scene__content">
          {mode === 'guest' && (
            <form onSubmit={handleGuest} className="space-y-4">
              <div>
                <label htmlFor="player-display-name" className="mb-2 block text-sm font-medium text-fg">Display Name</label>
                <div className="relative">
                  <UserRound size={18} className="auth-scene__field-icon text-fg-muted" aria-hidden="true" />
                  <Input
                    id="player-display-name"
                    type="text"
                    value={displayName}
                    onChange={e => setDisplayName(e.target.value)}
                    placeholder="Your name"
                    maxLength={50}
                    className="pl-11 bg-surface-sunken/70"
                    required
                    autoFocus
                  />
                </div>
              </div>
              <div>
                <label htmlFor="player-email" className="mb-2 block text-sm font-medium text-fg">Email</label>
                <div className="relative">
                  <Mail size={18} className="auth-scene__field-icon text-fg-muted" aria-hidden="true" />
                  <Input
                    id="player-email"
                    type="email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    className="pl-11 bg-surface-sunken/70"
                    required
                  />
                </div>
              </div>
              {error && <p role="alert" className="text-danger-fg text-sm text-center">{error}</p>}
              <Button
                type="submit"
                className="auth-scene__primary w-full"
                size="lg"
                disabled={loading || !displayName.trim() || !email.trim()}
              >
                {loading ? 'Joining…' : 'Join Game'}
              </Button>
            </form>
          )}

          {mode === 'netid' && (
            <div className="space-y-3">
              {isAuthenticated ? (
                /* Already signed in via OAuth2 — go straight to lobby */
                <Button
                  className="auth-scene__primary w-full"
                  size="lg"
                  onClick={() => navigate(`/game/${code}/lobby`)}
                >
                  Join Game
                </Button>
              ) : (
                /* Trigger OAuth2 — save room code so we can return here after auth */
                <a
                  href="/api/auth/oauth2-callback?redirect_to=/player/login"
                  onClick={() => sessionStorage.setItem('joinRoomCode', code)}
                  className="auth-scene__primary flex items-center justify-center gap-2 w-full min-h-12 px-4 rounded-control text-base font-semibold text-on-color transition-colors"
                >
                  Sign in with UW NetID
                  <ArrowRight size={18} aria-hidden="true" />
                </a>
              )}
              {error && <p role="alert" className="text-danger-fg text-sm text-center">{error}</p>}
              {!isAuthenticated && (
                <button
                  type="button"
                  onClick={() => { setMode('local'); setError(''); }}
                  className="w-full min-h-12 text-fg-muted text-base hover:text-fg transition-colors"
                >
                  Use local account instead
                </button>
              )}
            </div>
          )}

          {mode === 'local' && (
            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <label htmlFor="player-username" className="mb-2 block text-sm font-medium text-fg">Username</label>
                <div className="relative">
                  <UserRound size={18} className="auth-scene__field-icon text-fg-muted" aria-hidden="true" />
                  <Input
                    id="player-username"
                    type="text"
                    value={username}
                    onChange={e => setUsername(e.target.value)}
                    placeholder="Enter your username"
                    autoComplete="username"
                    className="pl-11 bg-surface-sunken/70"
                    required
                    autoFocus
                  />
                </div>
              </div>
              <div>
                <label htmlFor="player-password" className="mb-2 block text-sm font-medium text-fg">Password</label>
                <div className="relative">
                  <LockKeyhole size={18} className="auth-scene__field-icon text-fg-muted" aria-hidden="true" />
                  <Input
                    id="player-password"
                    type="password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    autoComplete="current-password"
                    className="pl-11 bg-surface-sunken/70"
                    required
                  />
                </div>
              </div>
              {error && <p role="alert" className="text-danger-fg text-sm text-center">{error}</p>}
              <Button
                type="submit"
                className="auth-scene__primary w-full"
                size="lg"
                disabled={loading || !username || !password}
              >
                {loading ? 'Signing in…' : 'Sign In & Join'}
              </Button>
              <button
                type="button"
                onClick={() => { setMode('netid'); setError(''); }}
                className="w-full min-h-12 text-fg-muted text-base hover:text-fg transition-colors"
              >
                ← Back to NetID sign in
              </button>
            </form>
          )}

          <button
            type="button"
            onClick={() => navigate('/join')}
            className="w-full mt-3 min-h-12 text-fg-muted text-base hover:text-fg transition-colors"
          >
            ← Different room code
          </button>
        </CardContent>
      </Card>
    </main>
  );
}
