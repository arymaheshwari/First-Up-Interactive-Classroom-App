import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ThemeToggle } from '../components/ui/ThemeToggle';
import { Card, CardContent, CardHeader } from '../components/ui/card';
import '../../../shared/theme/auth-scene.css';

/**
 * Landing page for OAuth2 returns (/player/login?from=oauth2#oauth2_data=...).
 * Exchanges the temp token for a full access token, then sends the player
 * back to the room they were trying to join (stored in sessionStorage).
 */
export default function LoginPage() {
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    if (searchParams.get('from') !== 'oauth2') {
      navigate('/join', { replace: true });
      return;
    }

    const oauthError = searchParams.get('error');
    if (oauthError) {
      setError(oauthError);
      return;
    }

    const match = window.location.hash.match(/oauth2_data=([^&]+)/);
    if (!match) {
      setError('Invalid authentication response');
      return;
    }

    let tempToken: string;
    try {
      const data = JSON.parse(decodeURIComponent(match[1]));
      tempToken = data.temp_token;
      if (!tempToken) throw new Error();
    } catch {
      setError('Invalid authentication response');
      return;
    }

    fetch('/api/auth/exchange-temp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tempToken}` },
    })
      .then(res => res.ok ? res.json() : res.json().then((e: { detail?: string }) => Promise.reject(e.detail ?? 'Sign-in failed')))
      .then((data: { access_token: string }) => {
        localStorage.setItem('token', data.access_token);
        window.history.replaceState(null, '', window.location.pathname);
        const roomCode = sessionStorage.getItem('joinRoomCode');
        sessionStorage.removeItem('joinRoomCode');
        navigate(roomCode ? `/name/${roomCode}` : '/join', { replace: true });
      })
      .catch((msg: unknown) => {
        setError(typeof msg === 'string' ? msg : 'Sign-in failed. Please try again.');
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="auth-scene">
      <ThemeToggle variant="floating" className="bg-surface/85 backdrop-blur-xl" />
      <Card className="auth-scene__card">
        <CardHeader className="auth-scene__header">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-accent-fg">Buzzer · Player</p>
          <h1 className="mt-3 text-3xl font-bold tracking-tight text-fg">
            {error ? 'Sign in failed' : 'Signing in…'}
          </h1>
        </CardHeader>
        <CardContent className="auth-scene__content text-center">
          {error ? (
            <>
              <p role="alert" className="text-danger-fg text-base">{error}</p>
              <button
                onClick={() => navigate('/join')}
                className="mt-4 min-h-12 px-4 text-accent-fg hover:underline text-base"
              >
                ← Back to join
              </button>
            </>
          ) : (
            <p role="status" className="text-fg-muted text-base">Connecting to your room</p>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
