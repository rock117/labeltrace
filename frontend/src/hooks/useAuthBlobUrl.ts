import { useEffect, useState } from 'react'
import { getToken } from '../lib/api'

type Entry = { url: string; refs: number; promise?: Promise<string> }

const cache = new Map<string, Entry>()

async function loadBlobUrl(assetId: string): Promise<string> {
  const existing = cache.get(assetId)
  if (existing?.url) return existing.url
  if (existing?.promise) return existing.promise

  const promise = (async () => {
    const token = getToken()
    const headers: HeadersInit = {}
    if (token) headers.Authorization = `Bearer ${token}`
    const res = await fetch(`/api/v1/assets/${assetId}/content`, { headers })
    if (!res.ok) throw new Error(String(res.status))
    const blob = await res.blob()
    const objectUrl = URL.createObjectURL(blob)
    const cur = cache.get(assetId)
    cache.set(assetId, { url: objectUrl, refs: cur?.refs ?? 0 })
    return objectUrl
  })()

  cache.set(assetId, { url: '', refs: existing?.refs ?? 0, promise })
  try {
    return await promise
  } catch (e) {
    cache.delete(assetId)
    throw e
  }
}

function retain(assetId: string, url: string) {
  const cur = cache.get(assetId)
  if (cur) cur.refs += 1
  else cache.set(assetId, { url, refs: 1 })
}

function release(assetId: string) {
  const cur = cache.get(assetId)
  if (!cur) return
  cur.refs -= 1
  if (cur.refs <= 0) {
    if (cur.url) URL.revokeObjectURL(cur.url)
    cache.delete(assetId)
  }
}

/** 带 Bearer 拉取素材二进制为 blob URL（同 asset 多组件共享，避免重复下载）。 */
export function useAuthBlobUrl(assetId: string | null | undefined): {
  url: string | null
  error: boolean
  loading: boolean
} {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!assetId) {
      setUrl(null)
      setError(false)
      setLoading(false)
      return
    }
    let cancelled = false
    let held = false
    setError(false)
    setUrl(null)
    setLoading(true)
    ;(async () => {
      try {
        const objectUrl = await loadBlobUrl(assetId)
        if (cancelled) return
        retain(assetId, objectUrl)
        held = true
        setUrl(objectUrl)
      } catch {
        if (!cancelled) setError(true)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
      if (held) release(assetId)
    }
  }, [assetId])

  return { url, error, loading }
}
