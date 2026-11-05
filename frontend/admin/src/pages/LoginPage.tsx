import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Card, CardContent, CardHeader } from '../components/ui/card';
import { ThemeToggle } from '../components/ui/ThemeToggle';
import { LockKeyhole, UserRound } from 'lucide-react';
import '../../../shared/theme/auth-scene.css';

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await api.post<{ access_token: string }>('/auth/login', { username, password });
      localStorage.setItem('token', data.access_token);
      navigate('/users');
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
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-accent-fg">Buzzer · Admin</p>
          <h1 className="mt-3 text-3xl font-bold tracking-tight text-fg">Welcome back</h1>
        </CardHeader>
        <CardContent className="auth-scene__content">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="admin-username" className="mb-2 block text-sm font-medium text-fg">Username</label>
              <div className="relative">
                <UserRound size={18} className="auth-scene__field-icon text-fg-muted" aria-hidden="true" />
                <Input
                  id="admin-username"
                  placeholder="Enter your username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  className="h-12 pl-11 bg-surface-sunken/70"
                  required
                />
              </div>
            </div>
            <div>
              <label htmlFor="admin-password" className="mb-2 block text-sm font-medium text-fg">Password</label>
              <div className="relative">
                <LockKeyhole size={18} className="auth-scene__field-icon text-fg-muted" aria-hidden="true" />
                <Input
                  id="admin-password"
                  type="password"
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  className="h-12 pl-11 bg-surface-sunken/70"
                  required
                />
              </div>
            </div>
            {error && <p role="alert" className="text-danger-fg text-sm">{error}</p>}
            <Button type="submit" size="lg" className="auth-scene__primary w-full" disabled={loading}>
              {loading ? 'Signing in…' : 'Sign In'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
