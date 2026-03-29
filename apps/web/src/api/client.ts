import { resolveApiUrl } from '../lib/api';

export interface RequestOptions extends RequestInit {
  noStore?: boolean;
}

function withDefaults(options: RequestOptions = {}): RequestInit {
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };
  const { noStore, ...rest } = options;
  return {
    cache: noStore ? 'no-store' : rest.cache,
    ...rest,
    headers,
  };
}

export async function getJSON<T>(url: string, options: RequestOptions = {}): Promise<T> {
  const res = await fetch(resolveApiUrl(url), withDefaults({ ...options, method: 'GET' }));
  return (await res.json()) as T;
}

export async function postJSON<T>(url: string, body?: unknown, options: RequestOptions = {}): Promise<{ ok: boolean; status: number; data: T }> {
  const res = await fetch(
    resolveApiUrl(url),
    withDefaults({
      ...options,
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
  const data = (await res.json()) as T;
  return { ok: res.ok, status: res.status, data };
}
