import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Card, CardContent, CardHeader } from '../components/ui/card';
import { ThemeToggle } from '../components/ui/ThemeToggle';
import { ArrowRight, LockKeyhole, UserRound } from 'lucide-react';
import '../../../shared/theme/auth-scene.css';

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Handle return from OAuth2 — exchange temp token for full access token
  useEffect(() => {
    if (searchParams.get('from') !== 'oauth2') return;

    const oauthError = searchParams.get('error');
    if (oauthError) {
      setError(oauthError);
      return;
    }

    const match = window.location.hash.match(/oauth2_data=([^&]+)/);
    if (!match) return;

    let tempToken: string;
    try {
      const data = JSON.parse(decodeURIComponent(match[1]));
      tempToken = data.temp_token;
      if (!tempToken) throw new Error();
    } catch {
      setError('Invalid authentication response');
      return;
    }

    setLoading(true);
    fetch('/api/auth/exchange-temp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tempToken}` },
    })
      .then(res => res.ok ? res.json() : res.json().then((e: { detail?: string }) => Promise.reject(e.detail ?? 'Sign-in failed')))
      .then((data: { access_token: string }) => {
        localStorage.setItem('token', data.access_token);
        window.history.replaceState(null, '', window.location.pathname);
        navigate('/home');
      })
      .catch((msg: unknown) => {
        setError(typeof msg === 'string' ? msg : 'Sign-in failed');
        setLoading(false);
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await api.post<{ access_token: string }>('/auth/login', { username, password });
      localStorage.setItem('token', data.access_token);
      navigate('/home');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-scene">
      <ThemeToggle variant="floating" className="bg-surface/85 backdrop-blur-xl" />
      <Card className="auth-scene__card">
        <CardHeader className="auth-scene__header">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-accent-fg">Buzzer · Host</p>
          <h1 className="mt-3 text-3xl font-bold tracking-tight text-fg">Welcome back</h1>
        </CardHeader>
        <CardContent className="auth-scene__content space-y-5">
          {/* Primary: UW NetID SSO */}
          <a
            href="/api/auth/oauth2-callback?redirect_to=/host/login"
            className={`flex h-12 items-center justify-center gap-2 w-full px-4 rounded-control font-semibold transition-colors
              ${loading
                ? 'bg-surface-hover text-fg-subtle pointer-events-none'
                : 'auth-scene__primary text-on-color'
              }`}
          >
            Sign in with UW NetID
            <ArrowRight size={18} aria-hidden="true" />
          </a>

          <div className="flex items-center gap-3">
            <div className="flex-1 h-px bg-line" />
            <span className="text-fg-muted text-xs">or use a local account</span>
            <div className="flex-1 h-px bg-line" />
          </div>

          {/* Secondary: username/password for admin & local accounts */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="host-username" className="mb-2 block text-sm font-medium text-fg">Username</label>
              <div className="relative">
                <UserRound size={18} className="auth-scene__field-icon text-fg-muted" aria-hidden="true" />
                <Input
                  id="host-username"
                  type="text"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  placeholder="Enter your username"
                  autoComplete="username"
                  className="h-12 pl-11 bg-surface-sunken/70"
                  required
                />
              </div>
            </div>
            <div>
              <label htmlFor="host-password" className="mb-2 block text-sm font-medium text-fg">Password</label>
              <div className="relative">
                <LockKeyhole size={18} className="auth-scene__field-icon text-fg-muted" aria-hidden="true" />
                <Input
                  id="host-password"
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  className="h-12 pl-11 bg-surface-sunken/70"
                  required
                />
              </div>
            </div>
            {error && <p role="alert" className="text-danger-fg text-sm">{error}</p>}
            <Button type="submit" variant="outline" size="lg" className="w-full bg-surface/55" disabled={loading}>
              {loading ? 'Signing in…' : 'Sign In'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
