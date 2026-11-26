import { useEffect, useState } from 'react'
import { getUserId } from '../lib/api'

type Props = {
  assetId: string
  alt?: string
  className?: string
}

/** 带 X-User-Id 拉取素材内容，供 <img> 使用。 */
export function AuthImage({ assetId, alt = '', className }: Props) {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let revoked: string | null = null
    let cancelled = false
    setError(false)
    setUrl(null)
    ;(async () => {
      try {
        const res = await fetch(`/api/v1/assets/${assetId}/content`, {
          headers: { 'X-User-Id': getUserId() },
        })
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

  if (error) {
    return <div className={className} style={{ background: 'var(--lt-bg-muted)' }} />
  }
  if (!url) {
    return <div className={className} style={{ background: 'var(--lt-bg-canvas)' }} />
  }
  return <img src={url} alt={alt} className={className} />
}
