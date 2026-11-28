import { useToastStore } from '../store/toastStore'

const toneLabel: Record<string, string> = {
  error: '出错了',
  success: '完成',
  info: '提示',
}

export function ToastHost() {
  const items = useToastStore((s) => s.items)
  const dismiss = useToastStore((s) => s.dismiss)

  if (items.length === 0) return null

  return (
    <div className="lt-toast-host" aria-live="polite" aria-relevant="additions text">
      {items.map((t) => (
        <div
          key={t.id}
          className={`lt-toast lt-toast-${t.tone}`}
          role={t.tone === 'error' ? 'alert' : 'status'}
        >
          <div className="lt-toast-body">
            <strong className="lt-toast-title">{toneLabel[t.tone] ?? '提示'}</strong>
            <p className="lt-toast-msg">{t.message}</p>
          </div>
          <button
            type="button"
            className="lt-toast-close"
            aria-label="关闭"
            onClick={() => dismiss(t.id)}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  )
}
