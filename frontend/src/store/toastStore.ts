import { create } from 'zustand'

export type ToastTone = 'error' | 'success' | 'info'

export type ToastItem = {
  id: string
  tone: ToastTone
  message: string
  /** ms；0 = 不自动关闭 */
  duration: number
}

type ToastOpts = {
  id?: string
  duration?: number
}

type ToastState = {
  items: ToastItem[]
  show: (tone: ToastTone, message: string, opts?: ToastOpts) => string
  dismiss: (id: string) => void
  clear: () => void
}

let seq = 0
const timers = new Map<string, number>()

function clearTimer(id: string) {
  const t = timers.get(id)
  if (t != null) {
    window.clearTimeout(t)
    timers.delete(id)
  }
}

function scheduleDismiss(id: string, duration: number) {
  clearTimer(id)
  if (duration <= 0) return
  const t = window.setTimeout(() => {
    timers.delete(id)
    useToastStore.getState().dismiss(id)
  }, duration)
  timers.set(id, t)
}

export const useToastStore = create<ToastState>((set) => ({
  items: [],
  show: (tone, message, opts) => {
    const id = opts?.id ?? `toast-${++seq}`
    const duration =
      opts?.duration ??
      (tone === 'error' ? 5600 : tone === 'success' ? 3600 : 4200)
    const next: ToastItem = { id, tone, message, duration }
    clearTimer(id)
    set((s) => ({
      items: [...s.items.filter((t) => t.id !== id), next],
    }))
    scheduleDismiss(id, duration)
    return id
  },
  dismiss: (id) => {
    clearTimer(id)
    set((s) => ({ items: s.items.filter((t) => t.id !== id) }))
  },
  clear: () => {
    for (const id of timers.keys()) clearTimer(id)
    set({ items: [] })
  },
}))

export const appToast = {
  error(message: string, opts?: ToastOpts) {
    return useToastStore.getState().show('error', message, opts)
  },
  success(message: string, opts?: ToastOpts) {
    return useToastStore.getState().show('success', message, opts)
  },
  info(message: string, opts?: ToastOpts) {
    return useToastStore.getState().show('info', message, opts)
  },
  dismiss(id: string) {
    useToastStore.getState().dismiss(id)
  },
}
