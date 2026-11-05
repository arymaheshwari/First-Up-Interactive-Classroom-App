const BASE = '/api';

function authHeader(): Record<string, string> {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** A failed request: the readable message, plus the HTTP status and parsed body. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly body: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/** App errors send {message}; FastAPI sends {detail} as a string or a validation list. */
async function errorFrom(res: Response): Promise<ApiError> {
  const body = (await res.json().catch(() => ({}))) as {
    detail?: string | { msg?: string }[];
    message?: string;
  };
  let message = body.message ?? `HTTP ${res.status}`;
  if (typeof body.detail === 'string') message = body.detail;
  else if (Array.isArray(body.detail) && body.detail[0]?.msg) {
    message = body.detail[0].msg.replace(/^Value error, /, '');
  }
  return new ApiError(message, res.status, body);
}

async function parse<T>(res: Response): Promise<T> {
  if (!res.ok) throw await errorFrom(res);
  const text = await res.text();
  return (text ? JSON.parse(text) : {}) as T;
}

function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  return fetch(`${BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...authHeader() },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  }).then((res) => parse<T>(res));
}

function sendForm<T>(method: 'POST' | 'PUT', path: string, form: FormData): Promise<T> {
  return fetch(`${BASE}${path}`, { method, headers: authHeader(), body: form }).then((res) =>
    parse<T>(res),
  );
}

/** Fetch a file and hand it to the browser as a download. */
async function download(path: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, { headers: authHeader() });
  if (!res.ok) throw await errorFrom(res);
  const match = (res.headers.get('Content-Disposition') ?? '').match(/filename="([^"]+)"/);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = match ? match[1] : 'download';
  a.click();
  URL.revokeObjectURL(url);
}

export const api = {
  get: <T>(path: string) => send<T>('GET', path),
  post: <T>(path: string, body?: unknown) => send<T>('POST', path, body),
  put: <T>(path: string, body?: unknown) => send<T>('PUT', path, body),
  patch: <T>(path: string, body?: unknown) => send<T>('PATCH', path, body),
  delete: <T>(path: string) => send<T>('DELETE', path),
  /** POST multipart/form-data (file uploads); the browser sets the boundary header. */
  postForm: <T>(path: string, form: FormData) => sendForm<T>('POST', path, form),
  /** PUT multipart/form-data (replacing an uploaded file). */
  putForm: <T>(path: string, form: FormData) => sendForm<T>('PUT', path, form),
  download,
};
