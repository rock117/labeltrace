import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { Project } from '../lib/types'
import { useAppStore } from '../store/appStore'
import { formatError } from '../hooks/useAsync'
import { LoadingBlock, StateBlock } from '../components/StateBlock'

export function ProjectsPage() {
  const setProject = useAppStore((s) => s.setProject)
  const projectId = useAppStore((s) => s.projectId)
  const [items, setItems] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)

  const reload = async () => {
    setLoading(true)
    setError(null)
    try {
      const list = await api<Project[]>('/v1/projects')
      setItems(list)
    } catch (e) {
      setError(formatError(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void reload()
  }, [])

  const create = async () => {
    if (!name.trim()) return
    setBusy(true)
    setError(null)
    try {
      const p = await api<Project>('/v1/projects', {
        method: 'POST',
        body: JSON.stringify({ name: name.trim() }),
      })
      setName('')
      setProject(p.id, p.name)
      await reload()
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="lt-page-head">
        <div>
          <h1>项目</h1>
          <p>选择工作项目；后续素材与数据集均归属当前项目。</p>
        </div>
      </div>

      <div className="lt-panel" style={{ padding: '1rem', marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            className="lt-input"
            placeholder="新项目名称"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && void create()}
          />
          <button
            type="button"
            className="lt-btn lt-btn-primary"
            disabled={busy || !name.trim()}
            onClick={() => void create()}
          >
            创建项目
          </button>
        </div>
      </div>

      {loading ? <LoadingBlock /> : null}
      {error ? (
        <StateBlock
          tone="error"
          title="加载失败"
          description={error}
          action={
            <button type="button" className="lt-btn" onClick={() => void reload()}>
              重试
            </button>
          }
        />
      ) : null}
      {!loading && !error && items.length === 0 ? (
        <StateBlock title="还没有项目" description="创建一个项目开始上传视频与标注。" />
      ) : null}

      <div style={{ display: 'grid', gap: '0.5rem' }}>
        {items.map((p) => {
          const active = p.id === projectId
          return (
            <button
              key={p.id}
              type="button"
              className="lt-panel"
              style={{
                padding: '0.85rem 1rem',
                textAlign: 'left',
                cursor: 'pointer',
                borderColor: active ? 'var(--lt-accent)' : undefined,
                background: active ? 'var(--lt-accent-soft)' : undefined,
              }}
              onClick={() => setProject(p.id, p.name)}
            >
              <div style={{ fontWeight: 600 }}>{p.name}</div>
              <div className="mono" style={{ color: 'var(--lt-fg-subtle)', fontSize: 12 }}>
                {p.id}
              </div>
              {active ? <span className="lt-badge" style={{ marginTop: 6 }}>当前</span> : null}
            </button>
          )
        })}
      </div>
    </div>
  )
}
