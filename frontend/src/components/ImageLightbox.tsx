import { useEffect } from 'react'
import { AuthImage } from './AuthImage'
import { AuthVideo } from './AuthVideo'

export type LightboxItem = {
  id: string
  title: string
  subtitle?: string
  kind?: 'image' | 'video'
}

type Props = {
  items: LightboxItem[]
  index: number
  onClose: () => void
  onIndexChange: (index: number) => void
  /** 可选：当前项是否已选中（抽帧审查） */
  selected?: boolean
  onToggleSelect?: () => void
}

export function ImageLightbox({
  items,
  index,
  onClose,
  onIndexChange,
  selected,
  onToggleSelect,
}: Props) {
  const safeIndex =
    items.length === 0 ? -1 : Math.min(Math.max(0, index), items.length - 1)
  const current = safeIndex >= 0 ? items[safeIndex] : null
  const canPrev = safeIndex > 0
  const canNext = safeIndex >= 0 && safeIndex < items.length - 1
  const isVideo = current?.kind === 'video'

  useEffect(() => {
    if (!current) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
        return
      }
      if (e.key === 'ArrowLeft' && canPrev) {
        e.preventDefault()
        onIndexChange(safeIndex - 1)
        return
      }
      if (e.key === 'ArrowRight' && canNext) {
        e.preventDefault()
        onIndexChange(safeIndex + 1)
        return
      }
      // 视频留给播放器空格暂停/播放；仅图片/帧用空格切选中
      if (
        !isVideo &&
        (e.key === ' ' || e.key === 'Enter') &&
        onToggleSelect
      ) {
        e.preventDefault()
        onToggleSelect()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [
    current,
    canPrev,
    canNext,
    safeIndex,
    onClose,
    onIndexChange,
    onToggleSelect,
    isVideo,
  ])

  if (!current) return null

  return (
    <div className="lt-lightbox-root" role="presentation">
      <button
        type="button"
        className="lt-lightbox-backdrop"
        aria-label="关闭预览"
        onClick={onClose}
      />
      <div
        className="lt-lightbox"
        role="dialog"
        aria-modal="true"
        aria-label={current.title}
      >
        <div className="lt-lightbox-head">
          <div className="lt-lightbox-meta">
            <strong title={current.title}>{current.title}</strong>
            <span>
              {safeIndex + 1} / {items.length}
              {current.subtitle ? ` · ${current.subtitle}` : ''}
              {isVideo ? ' · 视频' : ''}
            </span>
          </div>
          <button type="button" className="lt-btn lt-btn-ghost" onClick={onClose}>
            关闭
          </button>
        </div>

        <div className="lt-lightbox-stage">
          <button
            type="button"
            className="lt-btn lt-lightbox-nav"
            disabled={!canPrev}
            aria-label="上一张"
            onClick={() => onIndexChange(safeIndex - 1)}
          >
            上一张
          </button>
          <div className="lt-lightbox-image-wrap">
            {isVideo ? (
              <AuthVideo
                key={current.id}
                assetId={current.id}
                playerOnly
                maxHeight={900}
                className="lt-lightbox-video"
              />
            ) : (
              <AuthImage
                key={current.id}
                assetId={current.id}
                alt={current.title}
                className="lt-lightbox-image"
              />
            )}
          </div>
          <button
            type="button"
            className="lt-btn lt-lightbox-nav"
            disabled={!canNext}
            aria-label="下一张"
            onClick={() => onIndexChange(safeIndex + 1)}
          >
            下一张
          </button>
        </div>

        <div className="lt-lightbox-foot">
          <span className="lt-lightbox-hint">
            {isVideo
              ? '← → 翻页 · Esc 关闭 · 使用播放器控件播放'
              : onToggleSelect
                ? '← → 翻页 · Esc 关闭 · 空格选中'
                : '← → 翻页 · Esc 关闭'}
          </span>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {onToggleSelect ? (
              <button
                type="button"
                className={selected ? 'lt-btn lt-btn-primary' : 'lt-btn'}
                onClick={onToggleSelect}
              >
                {selected ? '取消选中' : '选中此帧'}
              </button>
            ) : null}
            <button
              type="button"
              className="lt-btn"
              disabled={!canPrev}
              onClick={() => onIndexChange(safeIndex - 1)}
            >
              上一张
            </button>
            <button
              type="button"
              className="lt-btn"
              disabled={!canNext}
              onClick={() => onIndexChange(safeIndex + 1)}
            >
              下一张
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
