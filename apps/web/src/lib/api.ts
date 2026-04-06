const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

export function resolveApiUrl(path: string): string {
  if (!path) {
    return BASE_URL
  }
  if (/^https?:\/\//.test(path)) {
    return path
  }
  if (path.startsWith('/api')) {
    return `${BASE_URL}${path.slice(4)}`
  }
  if (path.startsWith('/')) {
    return `${BASE_URL}${path}`
  }
  return `${BASE_URL}/${path}`
}
