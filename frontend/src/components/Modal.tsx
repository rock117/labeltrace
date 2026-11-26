import type { ReactNode } from 'react'
import { useEffect } from 'react'

type Props = {
  open: boolean
  title: string
  children: ReactNode
  onClose: () => void
  /** 底部操作区 */
  footer?: ReactNode
}

export function Modal({ open, title, children, onClose, footer }: Props) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="lt-modal-root" role="presentation">
      <button
        type="button"
        className="lt-modal-backdrop"
        aria-label="关闭"
        onClick={onClose}
      />
      <div
        className="lt-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="lt-modal-title"
      >
        <div className="lt-modal-head">
          <h2 id="lt-modal-title">{title}</h2>
          <button type="button" className="lt-btn lt-btn-ghost" onClick={onClose}>
            关闭
          </button>
        </div>
        <div className="lt-modal-body">{children}</div>
        {footer ? <div className="lt-modal-foot">{footer}</div> : null}
      </div>
    </div>
  )
}
