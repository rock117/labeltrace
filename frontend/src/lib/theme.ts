export type Theme = 'light' | 'dark'

const KEY = 'labeltrace.theme'

export function getStoredTheme(): Theme {
  const v = localStorage.getItem(KEY)
  return v === 'dark' ? 'dark' : 'light'
}

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme)
  localStorage.setItem(KEY, theme)
}

export function toggleTheme(current: Theme): Theme {
  const next: Theme = current === 'light' ? 'dark' : 'light'
  applyTheme(next)
  return next
}
