import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { NO_COURSES_MESSAGE, useHostedCourse } from './CoursePicker';

export default function RostersPage() {
  const { courses, error } = useHostedCourse();

  return (
    <div className="manage-page">
      <header className="manage-page__heading">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-accent-fg">Course access</p>
        <h2 className="manage-page__title">Rosters</h2>
        <p className="manage-page__intro">Open a course to view and update its roster.</p>
      </header>
      {error && <p role="alert" className="mb-4 text-sm text-danger-fg">{error}</p>}
      <section className="manage-panel manage-list-panel" aria-labelledby="manage-rosters-list-title">
        <header className="manage-list-panel__header">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-accent-fg">Hosted courses</p>
            <h3 id="manage-rosters-list-title" className="mt-1 text-xl font-bold text-fg">Course rosters</h3>
          </div>
          <span className="manage-list-panel__count" aria-label={`${courses?.length ?? 0} courses`}>{courses?.length ?? 0}</span>
        </header>
        <div className="manage-list-panel__body">
          {courses === null ? (
            <p role="status" className="text-sm text-fg-muted">Loading courses…</p>
          ) : courses.length === 0 ? (
            <p className="text-sm text-fg-muted">{NO_COURSES_MESSAGE}</p>
          ) : courses.map(c => (
            <Link key={c.id} to={`/manage/courses/${c.id}/roster`} className="manage-item manage-roster-link">
              <span className="min-w-0">
                <span className="block font-semibold text-fg break-words">{c.name}</span>
                <span className="mt-1 block text-sm text-fg-muted">{c.semester}</span>
              </span>
              <ChevronRight size={20} className="shrink-0 text-fg-subtle" aria-hidden="true" />
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
