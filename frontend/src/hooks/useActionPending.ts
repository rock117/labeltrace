import { useCallback, useState } from 'react'

/**
 * 进行中的操作按 key 分开。
 * 只有发起该操作的控件调用 is(key)；不要拿一个 key 去禁用页面上无关的按钮。
 */
export function useActionPending() {
  const [pending, setPending] = useState<ReadonlySet<string>>(() => new Set())

  const run = useCallback(async (key: string, fn: () => Promise<void>) => {
    let started = false
    setPending((prev) => {
      if (prev.has(key)) return prev
      started = true
      const next = new Set(prev)
      next.add(key)
      return next
    })
    if (!started) return
    try {
      await fn()
    } finally {
      setPending((prev) => {
        if (!prev.has(key)) return prev
        const next = new Set(prev)
        next.delete(key)
        return next
      })
    }
  }, [])

  const is = useCallback((key: string) => pending.has(key), [pending])

  return { is, run }
}
