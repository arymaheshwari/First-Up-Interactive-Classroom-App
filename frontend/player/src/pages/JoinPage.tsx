import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Card, CardContent, CardHeader } from '../components/ui/card';
import { ThemeToggle } from '../components/ui/ThemeToggle';
import '../../../shared/theme/auth-scene.css';

export default function JoinPage() {
  const [searchParams] = useSearchParams();
  const [roomCode, setRoomCode] = useState(() => searchParams.get('code')?.toUpperCase() ?? '');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function handleJoin(e?: React.FormEvent) {
    e?.preventDefault();
    const code = roomCode.trim().toUpperCase();
    if (code.length !== 6) {
      setError('Room code must be 6 characters');
      return;
    }
    setError('');
    setLoading(true);
    try {
      await api.get(`/game/rooms/${code}/ping`);
      navigate(`/name/${code}`);
    } catch {
      setError('Room not found. Check the code and try again.');
    } finally {
      setLoading(false);
    }
  }

  // Auto-submit when the page loads with a pre-filled code from QR scan
  useEffect(() => {
    if (searchParams.get('code')) {
      handleJoin();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="auth-scene">
      <ThemeToggle variant="floating" className="bg-surface/85 backdrop-blur-xl" />
      <Card className="auth-scene__card">
        <CardHeader className="auth-scene__header">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-accent-fg">Buzzer · Player</p>
          <h1 className="mt-3 text-3xl font-bold tracking-tight text-fg">Join a room</h1>
        </CardHeader>
        <CardContent className="auth-scene__content">
          <form onSubmit={handleJoin} className="space-y-4">
            <div>
              <label htmlFor="player-room-code" className="mb-2 block text-sm font-medium text-fg">Room code</label>
              <Input
                id="player-room-code"
                type="text"
                value={roomCode}
                onChange={e => setRoomCode(e.target.value.toUpperCase())}
                placeholder="XXXXXX"
                maxLength={6}
                className="text-center text-3xl font-mono tracking-widest uppercase bg-surface-sunken/70"
                autoCapitalize="characters"
                autoComplete="off"
                autoFocus
              />
            </div>
            {error && <p role="alert" className="text-danger-fg text-sm text-center">{error}</p>}
            <Button type="submit" className="auth-scene__primary w-full" size="lg" disabled={loading || roomCode.length < 6}>
              {loading ? 'Checking…' : 'Join Game'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
