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
  const requestInit: RequestInit = { ...init };
  const method = (requestInit.method ?? 'GET').toUpperCase();
  const hasBody = requestInit.body != null;
  const isGetWithoutBody = method === 'GET' && !hasBody;
  const headers = new Headers(requestInit.headers ?? {});

  if (isGetWithoutBody) {
    headers.delete('Content-Type');
  } else if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const res = await fetch(`/api${path}`, {
    ...requestInit,
    headers,
  });
  if (!res.ok) {
    let body: unknown;
    try { body = await res.json(); } catch { body = null; }
    throw makeApiError(res.status, body);
  }
  return res.json() as Promise<T>;
}

export function get<T>(
  path: string,
  options?: Omit<RequestInit, 'method' | 'body'>,
): Promise<T> {
  return request<T>(path, { method: 'GET', ...options });
}

export function post<T>(
  path: string,
  body: unknown,
  options?: Omit<RequestInit, 'method' | 'body'>,
): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    body: JSON.stringify(body),
    ...options,
  });
}

export async function postForm<T>(
  path: string,
  form: FormData,
  options?: Omit<RequestInit, 'method' | 'body'>,
): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...options,
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    let body: unknown;
    try { body = await res.json(); } catch { body = null; }
    throw makeApiError(res.status, body);
  }
  return res.json() as Promise<T>;
}
