import { useEffect, useState } from 'react'
import { getToken } from '../lib/api'

type Props = {
  assetId: string
  className?: string
  width?: number
  height?: number
}

/** 列表封面：请求 /poster（服务端缓存的小图），不下载整段视频。 */
export function AuthVideoThumb({
  assetId,
  className,
  width = 72,
  height = 48,
}: Props) {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState(false)
  const fill = Boolean(className?.includes('lt-media-card-thumb-fill'))

  useEffect(() => {
    let revoked: string | null = null
    let cancelled = false
    setError(false)
    setUrl(null)
    ;(async () => {
      try {
        const token = getToken()
        const headers: HeadersInit = {}
        if (token) headers.Authorization = `Bearer ${token}`
        const res = await fetch(`/api/v1/assets/${assetId}/poster`, { headers })
        if (!res.ok) throw new Error(String(res.status))
        const blob = await res.blob()
        if (cancelled) return
        const objectUrl = URL.createObjectURL(blob)
        revoked = objectUrl
        setUrl(objectUrl)
      } catch {
        if (!cancelled) setError(true)
      }
    })()
    return () => {
      cancelled = true
      if (revoked) URL.revokeObjectURL(revoked)
    }
  }, [assetId])

  const box = fill
    ? {
        width: '100%' as const,
        height: '100%' as const,
        objectFit: 'cover' as const,
        display: 'block' as const,
      }
    : {
        width,
        height,
        flexShrink: 0,
        borderRadius: 4,
        overflow: 'hidden' as const,
        background: 'var(--lt-bg-canvas)',
        objectFit: 'cover' as const,
      }

  if (error) {
    return (
      <div
        className={className}
        style={{
          ...box,
          display: 'grid',
          placeItems: 'center',
          fontSize: 11,
          color: 'var(--lt-fg-subtle)',
          background: 'var(--lt-bg-canvas)',
        }}
      >
        ▶
      </div>
    )
  }
  if (!url) {
    return (
      <div
        className={className}
        style={{ ...box, background: 'var(--lt-bg-canvas)' }}
      />
    )
  }
  return (
    <img
      className={className}
      src={url}
      alt=""
      style={box}
      draggable={false}
    />
  )
}
