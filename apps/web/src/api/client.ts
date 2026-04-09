import { resolveApiUrl } from '../lib/api';

export interface RequestOptions extends RequestInit {
  noStore?: boolean;
}

interface ApiEnvelopeMeta {
  version?: string;
  updated_at?: string;
  source?: string;
  trace_id?: string;
}

interface ApiEnvelopeError {
  error_code?: string;
  message?: string;
  details?: unknown;
}

interface ApiEnvelope<T> {
  data?: T;
  error?: ApiEnvelopeError;
  meta?: ApiEnvelopeMeta;
}

function isApiEnvelope<T>(payload: unknown): payload is ApiEnvelope<T> {
  if (!payload || typeof payload !== 'object') return false;
  const candidate = payload as Record<string, unknown>;
  return !!candidate.meta && typeof candidate.meta === 'object' && ('data' in candidate || 'error' in candidate);
}

function normalizeErrorPayload<T>(error: ApiEnvelopeError | undefined): T {
  const details = error?.details;
  if (details && typeof details === 'object' && !Array.isArray(details)) {
    return {
      ...(details as Record<string, unknown>),
      ok: false,
      error: error?.message,
      message: error?.message,
      error_code: error?.error_code,
    } as T;
  }
  return {
    ok: false,
    error: error?.message,
    message: error?.message,
    error_code: error?.error_code,
  } as T;
}

function withDefaults(options: RequestOptions = {}): RequestInit {
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };
  const { noStore, ...rest } = options;
  return {
    keepalive: true,
    cache: noStore ? 'no-store' : rest.cache,
    ...rest,
    headers,
  };
}

const FETCH_TIMEOUT_MS = 20_000;

function withTimeout(signal?: AbortSignal): { signal: AbortSignal; cleanup: () => void } {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  const cleanup = () => window.clearTimeout(timer);

  if (signal) {
    signal.addEventListener('abort', () => controller.abort());
  }

  return { signal: controller.signal, cleanup };
}

export async function getJSON<T>(url: string, options: RequestOptions = {}): Promise<T> {
  const { signal, cleanup } = withTimeout(options.signal as AbortSignal | undefined);
  const res = await fetch(resolveApiUrl(url), withDefaults({ ...options, method: 'GET', signal })).finally(cleanup);
  const payload = (await res.json()) as T | ApiEnvelope<T>;
  if (isApiEnvelope<T>(payload)) {
    if (payload.error) return normalizeErrorPayload<T>(payload.error);
    return payload.data as T;
  }
  return payload as T;
}

export async function postJSON<T>(
  url: string,
  body?: unknown,
  options: RequestOptions = {},
): Promise<{ ok: boolean; status: number; data: T; meta?: ApiEnvelopeMeta; error?: ApiEnvelopeError }> {
  const res = await fetch(
    resolveApiUrl(url),
    withDefaults({
      ...options,
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
  const payload = (await res.json()) as T | ApiEnvelope<T>;
  if (isApiEnvelope<T>(payload)) {
    if (payload.error) {
      return {
        ok: false,
        status: res.status,
        data: normalizeErrorPayload<T>(payload.error),
        meta: payload.meta,
        error: payload.error,
      };
    }
    return {
      ok: res.ok,
      status: res.status,
      data: payload.data as T,
      meta: payload.meta,
    };
  }
  return { ok: res.ok, status: res.status, data: payload as T };
}
