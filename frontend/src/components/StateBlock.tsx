import type { ReactNode } from 'react'

type Props = {
  title: string
  description?: string
  action?: ReactNode
  tone?: 'muted' | 'error'
}

export function StateBlock({ title, description, action, tone = 'muted' }: Props) {
  return (
    <div className="lt-state" style={tone === 'error' ? { color: 'var(--lt-danger)' } : undefined}>
      <h3>{title}</h3>
      {description ? <p>{description}</p> : null}
      {action}
    </div>
  )
}

export function LoadingBlock({ label = '加载中…' }: { label?: string }) {
  return <div className="lt-state"><p>{label}</p></div>
}
