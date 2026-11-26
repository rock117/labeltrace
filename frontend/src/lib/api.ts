const USER_KEY = 'labeltrace.userId'

export function getUserId(): string {
  let id = localStorage.getItem(USER_KEY)
  if (!id) {
    id = 'demo-user'
    localStorage.setItem(USER_KEY, id)
  }
  return id
}

export function setUserId(id: string): void {
  localStorage.setItem(USER_KEY, id.trim() || 'demo-user')
}

export class ApiError extends Error {
  status: number
  code?: string
  detail: unknown

  constructor(status: number, detail: unknown, code?: string) {
    super(typeof detail === 'string' ? detail : JSON.stringify(detail))
    this.status = status
    this.detail = detail
    this.code = code
  }
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('X-User-Id', getUserId())
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const res = await fetch(`/api${path}`, { ...init, headers })
  if (res.status === 204) return undefined as T
  const text = await res.text()
  let data: unknown = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }
  if (!res.ok) {
    const obj = data as { detail?: unknown; code?: string } | null
    throw new ApiError(res.status, obj?.detail ?? data, obj?.code)
  }
  return data as T
}

export function assetContentUrl(assetId: string): string {
  return `/api/v1/assets/${assetId}/content`
}
