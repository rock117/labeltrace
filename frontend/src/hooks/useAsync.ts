import { useCallback, useState } from 'react'
import { ApiError } from '../lib/api'

export function formatError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 403) return '无权限执行此操作'
    if (err.status === 401) return '未登录或缺少用户标识'
    if (err.status === 404) return '资源不存在'
    if (err.status === 409) return typeof err.detail === 'string' ? err.detail : '资源冲突'
    if (typeof err.detail === 'string') return err.detail
    return err.message
  }
  if (err instanceof Error) return err.message
  return '未知错误'
}

export function useAsync<T>() {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = useCallback(async (fn: () => Promise<T>) => {
    setLoading(true)
    setError(null)
    try {
      const result = await fn()
      setData(result)
      return result
    } catch (e) {
      setError(formatError(e))
      throw e
    } finally {
      setLoading(false)
    }
  }, [])

  return { data, setData, loading, error, setError, run }
}
