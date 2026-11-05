import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Gamepad2, History, Images, LogOut, Play, Users } from 'lucide-react';
import { ThemeToggle } from '../../components/ui/ThemeToggle';
import './manage.css';

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `manage-scene__link${isActive ? ' manage-scene__link--active' : ''}`;

export default function ManageLayout() {
  const navigate = useNavigate();
  // Games, Images and Sessions share the ?course= selection, so carry it between them.
  const { search } = useLocation();

  function logout() {
    localStorage.removeItem('token');
    navigate('/login');
  }

  return (
    <div className="manage-scene">
      <aside className="manage-scene__rail">
        <div className="manage-scene__brand">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-accent-fg">Buzzer · Host</p>
          <h1 className="mt-2 text-xl font-bold tracking-tight text-fg">Manage</h1>
        </div>
        <nav aria-label="Host management" className="manage-scene__nav">
          <NavLink to="/home" className={linkClass}>
            <Play size={18} aria-hidden="true" /> Run a game
          </NavLink>
          <NavLink to={{ pathname: '/manage/games', search }} className={linkClass}>
            <Gamepad2 size={18} aria-hidden="true" /> Games
          </NavLink>
          <NavLink to="/manage/rosters" className={linkClass}>
            <Users size={18} aria-hidden="true" /> Rosters
          </NavLink>
          <NavLink to={{ pathname: '/manage/images', search }} className={linkClass}>
            <Images size={18} aria-hidden="true" /> Images
          </NavLink>
          <NavLink to={{ pathname: '/manage/sessions', search }} className={linkClass}>
            <History size={18} aria-hidden="true" /> Sessions
          </NavLink>
        </nav>
        <div className="manage-scene__footer">
          <button
            onClick={logout}
            className="manage-scene__logout"
          >
            <LogOut size={18} aria-hidden="true" /> Sign out
          </button>
          <ThemeToggle className="manage-scene__theme-toggle" />
        </div>
      </aside>
      <main className="manage-scene__main">
        <Outlet />
      </main>
    </div>
  );
}
