import { create } from 'zustand'
import { applyTheme, getStoredTheme, type Theme, toggleTheme } from '../lib/theme'
import {
  clearSession,
  getAuthUser,
  setSession,
  type AuthUser,
} from '../lib/api'
import {
  clearWorkspaceProject,
  readWorkspaceProject,
  setWorkspaceProject,
} from '../lib/workspaceStorage'

const boot = readWorkspaceProject()

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
  projectId: boot?.id ?? null,
  projectName: boot?.name || null,
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
    clearWorkspaceProject()
    set({ user: null, projectId: null, projectName: null })
  },
  setProject: (id, name = null) => {
    setWorkspaceProject(id, name)
    if (!id) {
      set({ projectId: null, projectName: null })
      return
    }
    const stored = readWorkspaceProject()
    set({
      projectId: id,
      projectName: name ?? stored?.name ?? null,
    })
  },
}))

applyTheme(getStoredTheme())
