export type ApiRequestError = {
  readonly _tag: 'ApiRequestError';
  readonly status: number;
  readonly body: unknown;
  readonly message: string;
};

export function makeApiError(status: number, body: unknown): ApiRequestError {
  return { _tag: 'ApiRequestError', status, body, message: `HTTP ${status}` };
}

export function isApiError(e: unknown): e is ApiRequestError {
  return typeof e === 'object' && e !== null && (e as ApiRequestError)._tag === 'ApiRequestError';
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    let body: unknown;
    try { body = await res.json(); } catch { body = null; }
    throw makeApiError(res.status, body);
  }
  return res.json() as Promise<T>;
}

export function get<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'GET', headers: {} });
}

export function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', body: JSON.stringify(body) });
}

export async function postForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`/api${path}`, { method: 'POST', body: form });
  if (!res.ok) {
    let body: unknown;
    try { body = await res.json(); } catch { body = null; }
    throw makeApiError(res.status, body);
  }
  return res.json() as Promise<T>;
}
