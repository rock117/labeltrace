import { create } from 'zustand'
import { applyTheme, getStoredTheme, type Theme, toggleTheme } from '../lib/theme'
import { getUserId, setUserId } from '../lib/api'

type AppState = {
  theme: Theme
  userId: string
  projectId: string | null
  projectName: string | null
  setTheme: (t: Theme) => void
  flipTheme: () => void
  setUserId: (id: string) => void
  setProject: (id: string | null, name?: string | null) => void
}

export const useAppStore = create<AppState>((set, get) => ({
  theme: getStoredTheme(),
  userId: getUserId(),
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
  setUserId: (id) => {
    setUserId(id)
    set({ userId: id })
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
