const BASE = '/api';

/** App errors send {message}; FastAPI sends {detail} as a string or a validation list. */
async function errorFrom(res: Response): Promise<Error> {
  const body = (await res.json().catch(() => ({}))) as {
    detail?: string | { msg?: string }[];
    message?: string;
  };
  if (typeof body.detail === 'string') return new Error(body.detail);
  if (Array.isArray(body.detail) && body.detail[0]?.msg) {
    return new Error(body.detail[0].msg.replace(/^Value error, /, ''));
  }
  return new Error(body.message ?? `HTTP ${res.status}`);
}

async function apiFetch<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('token');
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers as Record<string, string> ?? {}),
    },
  });
  if (!res.ok) throw await errorFrom(res);
  const text = await res.text();
  return text ? (JSON.parse(text) as T) : ({} as T);
}

export const api = {
  get: <T>(path: string) => apiFetch<T>(path),
  post: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: 'POST', body: body !== undefined ? JSON.stringify(body) : undefined }),
};
