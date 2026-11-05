/**
 * Base URL of the Host app, where host tools (games, rosters, sessions) now live.
 * Same-origin /host/ in the nginx build, so the admin's login carries over; the
 * Vite dev server runs on its own origin, so there the Host app asks to log in.
 */
export const HOST_APP_URL: string =
  import.meta.env.VITE_HOST_APP_URL ??
  (import.meta.env.PROD ? '/host/' : 'http://localhost:5173/');

export function hostAppLink(path: string): string {
  return `${HOST_APP_URL}${path.replace(/^\//, '')}`;
}
