/**
 * 登录会话（非项目域）：token 与 user 同属一次会话，嵌套存放。
 * labeltrace.session = { token, user: { id, username } }
 * 旧扁平 labeltrace.token / labeltrace.user 读一次后迁移删除。
 */
const SESSION_KEY = 'labeltrace.session'
const LEGACY_TOKEN_KEY = 'labeltrace.token'
const LEGACY_USER_KEY = 'labeltrace.user'

export type AuthUser = { id: string; username: string }

type Session = { token: string; user: AuthUser }

function parseUser(raw: unknown): AuthUser | null {
  if (!raw || typeof raw !== 'object') return null
  const o = raw as { id?: unknown; username?: unknown }
  if (typeof o.id !== 'string' || !o.id) return null
  if (typeof o.username !== 'string') return null
  return { id: o.id, username: o.username }
}

function readSession(): Session | null {
  const raw = localStorage.getItem(SESSION_KEY)
  if (raw) {
    try {
      const o = JSON.parse(raw) as { token?: unknown; user?: unknown }
      const user = parseUser(o.user)
      if (typeof o.token === 'string' && o.token && user) {
        return { token: o.token, user }
      }
    } catch {
      /* migrate below */
    }
  }
  const token = localStorage.getItem(LEGACY_TOKEN_KEY)
  const userRaw = localStorage.getItem(LEGACY_USER_KEY)
  if (token && userRaw) {
    try {
      const user = parseUser(JSON.parse(userRaw))
      if (user) {
        const session = { token, user }
        localStorage.setItem(SESSION_KEY, JSON.stringify(session))
        localStorage.removeItem(LEGACY_TOKEN_KEY)
        localStorage.removeItem(LEGACY_USER_KEY)
        return session
      }
    } catch {
      /* fall through */
    }
  }
  localStorage.removeItem(LEGACY_TOKEN_KEY)
  localStorage.removeItem(LEGACY_USER_KEY)
  return null
}

export function getToken(): string | null {
  return readSession()?.token ?? null
}

export function getAuthUser(): AuthUser | null {
  return readSession()?.user ?? null
}

export function setSession(token: string, user: AuthUser): void {
  const session: Session = { token, user }
  localStorage.setItem(SESSION_KEY, JSON.stringify(session))
  localStorage.removeItem(LEGACY_TOKEN_KEY)
  localStorage.removeItem(LEGACY_USER_KEY)
}

export function clearSession(): void {
  localStorage.removeItem(SESSION_KEY)
  localStorage.removeItem(LEGACY_TOKEN_KEY)
  localStorage.removeItem(LEGACY_USER_KEY)
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
