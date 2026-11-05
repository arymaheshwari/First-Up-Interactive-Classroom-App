import { BrowserRouter, Navigate, Outlet, Route, Routes, useNavigate, NavLink } from 'react-router-dom';
import { BookOpen, Users, Gamepad2, UserX, LogOut, History, ClipboardList, Images, Play, ExternalLink } from 'lucide-react';
import { hostAppLink } from './lib/hostApp';
import { ThemeToggle } from './components/ui/ThemeToggle';
import LoginPage from './pages/LoginPage';
import CoursesPage from './pages/CoursesPage';
import UsersPage from './pages/UsersPage';
import UserDetailPage from './pages/UserDetailPage';
import GuestsPage from './pages/GuestsPage';

function RequireAdmin() {
  const token = localStorage.getItem('token');
  if (!token) return <Navigate to="/login" replace />;
  return <Outlet />;
}

// Host tools live in the Host app; admins pass every host permission check there.
const HOST_TOOLS = [
  { label: 'Games', path: 'manage/games', icon: Gamepad2 },
  { label: 'Rosters', path: 'manage/rosters', icon: ClipboardList },
  { label: 'Images', path: 'manage/images', icon: Images },
  { label: 'Sessions', path: 'manage/sessions', icon: History },
  { label: 'Run a game', path: 'home', icon: Play },
];

function AdminLayout() {
  const navigate = useNavigate();

  function logout() {
    localStorage.removeItem('token');
    navigate('/login');
  }

  // The active link is marked by more than its tint: a left bar, bold text, and the
  // aria-current="page" NavLink sets. Every link reserves the bar's 4 px so nothing shifts.
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 border-l-4 px-3 py-2 rounded-control text-sm transition-colors ${
      isActive
        ? 'border-accent-fg bg-accent-subtle text-fg font-semibold'
        : 'border-transparent font-medium text-fg-muted hover:bg-surface-hover hover:text-fg'
    }`;

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 bg-surface border-r border-line flex flex-col">
        <div className="px-6 py-5 border-b border-line">
          <h1 className="text-lg font-semibold tracking-tight text-fg">Buzzer Admin</h1>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          <NavLink to="/users" className={linkClass}>
            <Users size={16} /> Users
          </NavLink>
          <NavLink to="/courses" className={linkClass}>
            <BookOpen size={16} /> Courses
          </NavLink>
          <NavLink to="/guests" className={linkClass}>
            <UserX size={16} /> Guests
          </NavLink>

          <p className="px-4 pt-5 pb-1 text-xs font-medium uppercase tracking-wide text-fg-muted">
            Host tools
          </p>
          {HOST_TOOLS.map(({ label, path, icon: Icon }) => (
            <a
              key={path}
              href={hostAppLink(path)}
              title="Opens in the Host app"
              className="flex items-center gap-3 border-l-4 border-transparent px-3 py-2 rounded-control text-sm font-medium text-fg-muted hover:bg-surface-hover hover:text-fg transition-colors"
            >
              <Icon size={16} /> {label}
              <ExternalLink size={12} className="ml-auto" aria-hidden="true" />
            </a>
          ))}
        </nav>
        <div className="admin-appearance-footer p-3 border-t border-line flex items-center gap-1">
          <button
            onClick={logout}
            className="flex flex-1 items-center gap-3 border-l-4 border-transparent px-3 py-2 rounded-control text-sm font-medium text-fg-muted hover:bg-surface-hover hover:text-fg transition-colors"
          >
            <LogOut size={16} /> Logout
          </button>
          <ThemeToggle />
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAdmin />}>
          <Route element={<AdminLayout />}>
            <Route path="/users" element={<UsersPage />} />
            <Route path="/users/:userId" element={<UserDetailPage />} />
            <Route path="/courses" element={<CoursesPage />} />
            <Route path="/guests" element={<GuestsPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/users" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
