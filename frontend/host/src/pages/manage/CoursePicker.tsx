import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../../lib/api';

export interface HostedCourse {
  id: number;
  name: string;
  semester: string;
}

export const NO_COURSES_MESSAGE =
  "You don't host any courses yet — ask an admin for HOST access.";

/** Courses the user hosts, with the selected one kept in the URL as ?course=<id>. */
export function useHostedCourse() {
  const [courses, setCourses] = useState<HostedCourse[] | null>(null);
  const [error, setError] = useState('');
  const [params, setParams] = useSearchParams();

  useEffect(() => {
    api
      .get<HostedCourse[]>('/game/my-courses')
      .then(setCourses)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load courses'));
  }, []);

  const requested = Number(params.get('course'));
  const courseId =
    courses?.some((c) => c.id === requested) ? requested : (courses?.[0]?.id ?? null);

  function selectCourse(id: number) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set('course', String(id));
        return next;
      },
      { replace: true },
    );
  }

  return { courses, courseId, selectCourse, error };
}

export function CoursePicker({
  courses,
  courseId,
  onSelect,
}: {
  courses: HostedCourse[];
  courseId: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <select
      aria-label="Course"
      value={courseId ?? ''}
      onChange={(e) => onSelect(Number(e.target.value))}
      className="rounded-control border border-line-strong bg-surface-sunken px-3 py-2 text-sm text-fg focus:border-focus"
    >
      {courses.map((c) => (
        <option key={c.id} value={c.id}>
          {c.name} ({c.semester})
        </option>
      ))}
    </select>
  );
}
