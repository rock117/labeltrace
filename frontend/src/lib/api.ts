const TOKEN_KEY = 'labeltrace.token'
const USER_KEY = 'labeltrace.user'

export type AuthUser = { id: string; username: string }

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function getAuthUser(): AuthUser | null {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as AuthUser
  } catch {
    return null
  }
}

export function setSession(token: string, user: AuthUser): void {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

/** @deprecated 兼容旧调用；现用登录会话 */
export function getUserId(): string {
  return getAuthUser()?.id ?? ''
}

export function setUserId(_id: string): void {
  // no-op：身份由登录会话决定
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
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
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
