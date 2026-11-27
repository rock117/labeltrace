import { create } from 'zustand'
import { applyTheme, getStoredTheme, type Theme, toggleTheme } from '../lib/theme'
import {
  clearSession,
  getAuthUser,
  setSession,
  type AuthUser,
} from '../lib/api'

type AppState = {
  theme: Theme
  user: AuthUser | null
  projectId: string | null
  projectName: string | null
  setTheme: (t: Theme) => void
  flipTheme: () => void
  setAuth: (token: string, user: AuthUser) => void
  logout: () => void
  setProject: (id: string | null, name?: string | null) => void
}

export const useAppStore = create<AppState>((set, get) => ({
  theme: getStoredTheme(),
  user: getAuthUser(),
  projectId: localStorage.getItem('labeltrace.projectId'),
  projectName: localStorage.getItem('labeltrace.projectName'),
  setTheme: (t) => {
    applyTheme(t)
    set({ theme: t })
  },
  flipTheme: () => {
    const next = toggleTheme(get().theme)
    set({ theme: next })
  },
  setAuth: (token, user) => {
    setSession(token, user)
    set({ user })
  },
  logout: () => {
    clearSession()
    localStorage.removeItem('labeltrace.projectId')
    localStorage.removeItem('labeltrace.projectName')
    set({ user: null, projectId: null, projectName: null })
  },
  setProject: (id, name = null) => {
    if (id) localStorage.setItem('labeltrace.projectId', id)
    else localStorage.removeItem('labeltrace.projectId')
    if (name) localStorage.setItem('labeltrace.projectName', name)
    else localStorage.removeItem('labeltrace.projectName')
    set({ projectId: id, projectName: name })
  },
}))

applyTheme(getStoredTheme())
