import { useCallback, useRef, useState } from 'react'

/**
 * 进行中的操作按 key 分开。
 * 只有发起该操作的控件调用 is(key)；不要拿一个 key 去禁用页面上无关的按钮。
 */
export function useActionPending() {
  const pendingRef = useRef(new Set<string>())
  const [pending, setPending] = useState<ReadonlySet<string>>(() => new Set())

  const run = useCallback(async (key: string, fn: () => Promise<void>) => {
    if (pendingRef.current.has(key)) return
    pendingRef.current.add(key)
    setPending(new Set(pendingRef.current))
    try {
      await fn()
    } finally {
      pendingRef.current.delete(key)
      setPending(new Set(pendingRef.current))
    }
  }, [])

  const is = useCallback((key: string) => pending.has(key), [pending])

  return { is, run }
}
