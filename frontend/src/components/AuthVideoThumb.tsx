import { useEffect, useState } from 'react'
import { useAuthBlobUrl } from '../hooks/useAuthBlobUrl'

type Props = {
  assetId: string
  /** 取画面的时间（秒）；默认 1s，不足则取中间 */
  atSec?: number
  className?: string
  width?: number
  height?: number
}

/** 从视频截取一帧作为缩略图。 */
export function AuthVideoThumb({
  assetId,
  atSec = 1,
  className,
  width = 72,
  height = 48,
}: Props) {
  const { url, error, loading } = useAuthBlobUrl(assetId)
  const [poster, setPoster] = useState<string | null>(null)

  useEffect(() => {
    if (!url) {
      setPoster(null)
      return
    }
    let cancelled = false
    let shot: string | null = null
    const video = document.createElement('video')
    video.muted = true
    video.playsInline = true
    video.preload = 'auto'
    video.src = url

    const fail = () => {
      if (!cancelled) setPoster(null)
    }

    const capture = () => {
      try {
        const w = video.videoWidth || 320
        const h = video.videoHeight || 180
        const canvas = document.createElement('canvas')
        canvas.width = w
        canvas.height = h
        const ctx = canvas.getContext('2d')
        if (!ctx) return fail()
        ctx.drawImage(video, 0, 0)
        shot = canvas.toDataURL('image/jpeg', 0.72)
        if (!cancelled) setPoster(shot)
      } catch {
        fail()
      }
    }

    const onMeta = () => {
      const dur = Number.isFinite(video.duration) ? video.duration : 0
      const t =
        dur > 0 ? Math.min(Math.max(atSec, 0.05), Math.max(dur * 0.1, 0.05)) : atSec
      const onSeeked = () => {
        video.removeEventListener('seeked', onSeeked)
        capture()
      }
      video.addEventListener('seeked', onSeeked)
      try {
        video.currentTime = t
      } catch {
        // 部分编码无法 seek，直接抓第 0 帧
        capture()
      }
    }

    video.addEventListener('loadedmetadata', onMeta)
    video.addEventListener('error', fail)

    return () => {
      cancelled = true
      video.removeEventListener('loadedmetadata', onMeta)
      video.removeEventListener('error', fail)
      video.src = ''
      video.load()
    }
  }, [url, atSec])

  const box = {
    width,
    height,
    flexShrink: 0,
    borderRadius: 4,
    overflow: 'hidden' as const,
    background: 'var(--lt-bg-canvas)',
    objectFit: 'cover' as const,
  }

  if (error) {
    return <div className={className} style={box} title="缩略图失败" />
  }
  if (loading || !poster) {
    return <div className={className} style={box} />
  }
  return (
    <img
      className={className}
      src={poster}
      alt=""
      style={box}
      draggable={false}
    />
  )
}
