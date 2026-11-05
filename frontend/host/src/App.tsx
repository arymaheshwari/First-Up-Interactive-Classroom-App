import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import LoginPage from './pages/LoginPage';
import HomePage from './pages/HomePage';
import GameLayout from './pages/game/GameLayout';
import LobbyPage from './pages/game/LobbyPage';
import QuestionPage from './pages/game/QuestionPage';
import ResultsPage from './pages/game/ResultsPage';
import GameOverPage from './pages/game/GameOverPage';
import ManageLayout from './pages/manage/ManageLayout';
import GamesPage from './pages/manage/GamesPage';
import QuestionEditorPage from './pages/manage/QuestionEditorPage';
import RostersPage from './pages/manage/RostersPage';
import ImagesPage from './pages/manage/ImagesPage';
import RosterPage from './pages/manage/RosterPage';
import SessionsPage from './pages/manage/SessionsPage';
import SessionDetailPage from './pages/manage/SessionDetailPage';

function RequireAuth({ children }: { children: React.ReactNode }) {
  if (!localStorage.getItem('token')) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/home" element={<RequireAuth><HomePage /></RequireAuth>} />
        <Route path="/manage" element={<RequireAuth><ManageLayout /></RequireAuth>}>
          <Route index element={<Navigate to="games" replace />} />
          <Route path="games" element={<GamesPage />} />
          <Route path="games/:gameId/questions" element={<QuestionEditorPage />} />
          <Route path="rosters" element={<RostersPage />} />
          <Route path="images" element={<ImagesPage />} />
          <Route path="courses/:courseId/roster" element={<RosterPage />} />
          <Route path="sessions" element={<SessionsPage />} />
          <Route path="sessions/:sessionId" element={<SessionDetailPage />} />
        </Route>
        <Route path="/game/:code" element={<RequireAuth><GameLayout /></RequireAuth>}>
          <Route path="lobby" element={<LobbyPage />} />
          <Route path="question" element={<QuestionPage />} />
          <Route path="results" element={<ResultsPage />} />
          <Route path="gameover" element={<GameOverPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
