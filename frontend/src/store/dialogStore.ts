import { create } from 'zustand'

type PromptReq = {
  kind: 'prompt'
  title: string
  label?: string
  defaultValue?: string
  confirmLabel?: string
  resolve: (value: string | null) => void
}

type ConfirmReq = {
  kind: 'confirm'
  title: string
  description?: string
  confirmLabel?: string
  danger?: boolean
  resolve: (ok: boolean) => void
}

type DialogReq = PromptReq | ConfirmReq

function dismissCurrent(cur: DialogReq | null) {
  if (!cur) return
  if (cur.kind === 'prompt') cur.resolve(null)
  else cur.resolve(false)
}

type DialogState = {
  current: DialogReq | null
  prompt: (opts: {
    title: string
    label?: string
    defaultValue?: string
    confirmLabel?: string
  }) => Promise<string | null>
  confirm: (opts: {
    title: string
    description?: string
    confirmLabel?: string
    danger?: boolean
  }) => Promise<boolean>
  close: () => void
}

export const useDialogStore = create<DialogState>((set, get) => ({
  current: null,
  prompt: ({ title, label, defaultValue, confirmLabel }) =>
    new Promise((resolve) => {
      dismissCurrent(get().current)
      set({
        current: {
          kind: 'prompt',
          title,
          label,
          defaultValue: defaultValue ?? '',
          confirmLabel,
          resolve,
        },
      })
    }),
  confirm: ({ title, description, confirmLabel, danger }) =>
    new Promise((resolve) => {
      dismissCurrent(get().current)
      set({
        current: {
          kind: 'confirm',
          title,
          description,
          confirmLabel,
          danger,
          resolve,
        },
      })
    }),
  close: () => {
    dismissCurrent(get().current)
    set({ current: null })
  },
}))

export function appPrompt(opts: {
  title: string
  label?: string
  defaultValue?: string
  confirmLabel?: string
}): Promise<string | null> {
  return useDialogStore.getState().prompt(opts)
}

export function appConfirm(opts: {
  title: string
  description?: string
  confirmLabel?: string
  danger?: boolean
}): Promise<boolean> {
  return useDialogStore.getState().confirm(opts)
}
