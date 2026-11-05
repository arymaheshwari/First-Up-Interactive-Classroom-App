import { useGame } from './GameLayout';

export default function LobbyPage() {
  const { roomCode, playerCount, gameStatus } = useGame();

  const statusText = gameStatus === 'IN_PROGRESS'
    ? 'Waiting for next question…'
    : 'Waiting for host to start…';

  return (
    <div className="player-status-screen">
      <section className="player-glass player-status-card text-center">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent-fg">Room code</p>
        <h1 className="mt-2 text-4xl font-black font-mono tracking-widest text-fg break-all">{roomCode}</h1>
        <div className="player-loading-dots" aria-hidden="true">
          <span /><span /><span />
        </div>
        <p role="status" className="text-fg text-lg font-semibold">{statusText}</p>
        <p className="mt-2 text-fg-muted text-base">{playerCount} player{playerCount !== 1 ? 's' : ''} in room</p>
      </section>
    </div>
  );
}
