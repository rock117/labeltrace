import { useEffect, useRef, useState } from 'react'
import { Modal } from './Modal'
import { useDialogStore } from '../store/dialogStore'

export function DialogHost() {
  const current = useDialogStore((s) => s.current)
  const close = useDialogStore((s) => s.close)
  const [value, setValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (current?.kind === 'prompt') {
      setValue(current.defaultValue ?? '')
      const t = window.setTimeout(() => inputRef.current?.select(), 0)
      return () => window.clearTimeout(t)
    }
  }, [current])

  if (!current) return null

  if (current.kind === 'prompt') {
    const submit = () => {
      const v = value.trim()
      current.resolve(v ? v : null)
      useDialogStore.setState({ current: null })
    }
    return (
      <Modal
        open
        title={current.title}
        onClose={close}
        footer={
          <>
            <button type="button" className="lt-btn" onClick={close}>
              取消
            </button>
            <button
              type="button"
              className="lt-btn lt-btn-primary"
              disabled={!value.trim()}
              onClick={submit}
            >
              {current.confirmLabel ?? '确定'}
            </button>
          </>
        }
      >
        {current.label ? (
          <label className="lt-field">
            <span>{current.label}</span>
            <input
              ref={inputRef}
              className="lt-input"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') submit()
              }}
              style={{ maxWidth: '100%', marginTop: 6 }}
            />
          </label>
        ) : (
          <input
            ref={inputRef}
            className="lt-input"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') submit()
            }}
            style={{ maxWidth: '100%' }}
          />
        )}
      </Modal>
    )
  }

  return (
    <Modal
      open
      title={current.title}
      onClose={close}
      footer={
        <>
          <button type="button" className="lt-btn" onClick={close}>
            取消
          </button>
          <button
            type="button"
            className={current.danger ? 'lt-btn lt-btn-danger' : 'lt-btn lt-btn-primary'}
            onClick={() => {
              current.resolve(true)
              useDialogStore.setState({ current: null })
            }}
          >
            {current.confirmLabel ?? '确定'}
          </button>
        </>
      }
    >
      {current.description ? (
        <p style={{ margin: 0, whiteSpace: 'pre-wrap', color: 'var(--lt-fg-muted)' }}>
          {current.description}
        </p>
      ) : null}
    </Modal>
  )
}
