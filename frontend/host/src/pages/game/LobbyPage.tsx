import { QRCodeSVG } from 'qrcode.react';
import { Users } from 'lucide-react';
import { useGame } from './GameLayout';
import { Button } from '../../components/ui/button';

export default function LobbyPage() {
  const { roomCode, gameTitle, playerCount, emitAdvance, autoAdvance, setAutoAdvance, reactionsEnabled, setReactionsEnabled, reactionSettingError } = useGame();

  const playerJoinUrl = `${window.location.origin}/player/join?code=${roomCode}`;

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-8 lg:p-12 gap-8">
      {/* Quiz name */}
      {gameTitle && (
        <h1 className="text-display tracking-tight text-fg text-center max-w-5xl">{gameTitle}</h1>
      )}

      {/* Join instructions */}
      <p className="text-fg-muted text-host-lg">
        Scan the QR code or go to <span className="text-fg font-semibold">{window.location.host}/player</span>
      </p>

      {/* QR code + room code side by side. The QR keeps a white tile so it scans in any theme. */}
      <div className="flex items-center gap-10">
        <div className="rounded-card bg-qr p-4 shadow-card">
          <QRCodeSVG value={playerJoinUrl} size={200} />
        </div>

        <div className="text-center">
          <p className="text-fg-muted text-host-lg uppercase tracking-widest mb-2">Room code</p>
          <div className="rounded-card border-2 border-accent bg-surface px-10 py-5 inline-block shadow-card">
            <p className="text-8xl font-black tracking-widest text-fg font-mono">{roomCode}</p>
          </div>
        </div>
      </div>

      {/* Player count */}
      <div className="flex items-center gap-3 text-fg text-host-xl font-semibold">
        <Users className="w-8 h-8 text-accent-fg" aria-hidden="true" />
        <span>
          {playerCount === 0
            ? 'Waiting for players to join…'
            : `${playerCount} player${playerCount !== 1 ? 's' : ''} joined`}
        </span>
      </div>

      {/* Auto-advance switch (an operator control: smaller type is fine here) */}
      <button
        type="button"
        role="switch"
        aria-checked={autoAdvance}
        className="flex items-center gap-3 group rounded-control px-2 py-1"
        onClick={() => setAutoAdvance(!autoAdvance)}
      >
        <span
          className={`relative inline-block h-6 w-12 shrink-0 rounded-full transition-colors ${autoAdvance ? 'bg-accent' : 'bg-line-strong'}`}
          aria-hidden="true"
        >
          <span
            className={`absolute left-1 top-1 h-4 w-4 rounded-full bg-on-color shadow-card transition-transform ${autoAdvance ? 'translate-x-6' : 'translate-x-0'}`}
          />
        </span>
        <span /* theme-check: small-text controls */ className="text-fg-muted text-base group-hover:text-fg transition-colors select-none">
          Auto-advance — run the game hands-free
        </span>
      </button>

      <div className="flex flex-col items-center gap-1">
        <button
          type="button"
          role="switch"
          aria-checked={reactionsEnabled}
          className="flex items-center gap-3 group rounded-control px-2 py-1"
          onClick={() => setReactionsEnabled(!reactionsEnabled)}
        >
          <span className={`relative inline-block h-6 w-12 shrink-0 rounded-full transition-colors ${reactionsEnabled ? 'bg-accent' : 'bg-line-strong'}`} aria-hidden="true">
            <span className={`absolute left-1 top-1 h-4 w-4 rounded-full bg-on-color shadow-card transition-transform ${reactionsEnabled ? 'translate-x-6' : 'translate-x-0'}`} />
          </span>
          <span /* theme-check: small-text controls */ className="text-fg-muted text-base group-hover:text-fg transition-colors select-none">
            Player reactions and messages
          </span>
        </button>
        <p /* theme-check: small-text controls */ className="text-sm text-fg-muted">Short player messages appear briefly on this screen.</p>
        {reactionSettingError && <p /* theme-check: small-text controls */ role="alert" className="text-sm text-danger-fg">{reactionSettingError}</p>}
      </div>

      {/* Start button */}
      <Button size="xl" onClick={emitAdvance} disabled={playerCount === 0} className="px-12">
        {playerCount === 0 ? 'Waiting for players…' : 'Start Game'}
      </Button>
    </div>
  );
}
