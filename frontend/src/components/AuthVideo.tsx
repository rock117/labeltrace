import { useEffect, useRef, useState } from 'react'
import { useAuthBlobUrl } from '../hooks/useAuthBlobUrl'

type Props = {
  assetId: string
  className?: string
  maxHeight?: number
}

function formatTime(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return '0:00'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

/** 带鉴权拉取视频并本地播放；可看进度条上某一时刻的画面。 */
export function AuthVideo({ assetId, className, maxHeight = 360 }: Props) {
  const { url, error, loading } = useAuthBlobUrl(assetId)
  const videoRef = useRef<HTMLVideoElement>(null)
  const [frameUrl, setFrameUrl] = useState<string | null>(null)
  const [t, setT] = useState(0)

  useEffect(() => {
    setFrameUrl(null)
    setT(0)
  }, [url])

  const grabFrame = () => {
    const video = videoRef.current
    if (!video || video.readyState < 2) return
    try {
      const canvas = document.createElement('canvas')
      canvas.width = video.videoWidth || 320
      canvas.height = video.videoHeight || 180
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.drawImage(video, 0, 0)
      setFrameUrl(canvas.toDataURL('image/jpeg', 0.85))
      setT(video.currentTime)
    } catch {
      /* ignore */
    }
  }

  if (error) {
    return (
      <div
        className={className}
        style={{
          background: 'var(--lt-bg-muted)',
          minHeight: 160,
          display: 'grid',
          placeItems: 'center',
          color: 'var(--lt-danger)',
          fontSize: 13,
          borderRadius: 'var(--lt-radius)',
        }}
      >
        视频加载失败
      </div>
    )
  }
  if (loading || !url) {
    return (
      <div
        className={className}
        style={{
          background: '#0a0a0a',
          minHeight: 160,
          display: 'grid',
          placeItems: 'center',
          color: 'var(--lt-fg-muted)',
          fontSize: 13,
          borderRadius: 'var(--lt-radius)',
        }}
      >
        加载视频中…
      </div>
    )
  }
  return (
    <div className={className} style={{ display: 'grid', gap: 8 }}>
      <video
        ref={videoRef}
        src={url}
        controls
        playsInline
        preload="metadata"
        onSeeked={grabFrame}
        onPause={grabFrame}
        style={{
          display: 'block',
          width: '100%',
          maxHeight,
          background: '#000',
          borderRadius: 'var(--lt-radius)',
        }}
      />
      <div
        style={{
          display: 'flex',
          gap: 10,
          alignItems: 'flex-start',
          flexWrap: 'wrap',
        }}
      >
        <button type="button" className="lt-btn" onClick={grabFrame}>
          截取当前画面
        </button>
        <span style={{ fontSize: 12, color: 'var(--lt-fg-muted)', paddingTop: 6 }}>
          拖动进度条或暂停后可查看某一时刻画面
          {frameUrl ? ` · ${formatTime(t)}` : ''}
        </span>
      </div>
      {frameUrl ? (
        <div>
          <div
            style={{
              fontSize: 12,
              color: 'var(--lt-fg-muted)',
              marginBottom: 4,
            }}
          >
            当前画面（{formatTime(t)}）
          </div>
          <img
            src={frameUrl}
            alt={`frame@${formatTime(t)}`}
            style={{
              display: 'block',
              width: '100%',
              maxHeight: 200,
              objectFit: 'contain',
              background: '#000',
              borderRadius: 'var(--lt-radius)',
              border: '1px solid var(--lt-border)',
            }}
          />
        </div>
      ) : null}
    </div>
  )
}
