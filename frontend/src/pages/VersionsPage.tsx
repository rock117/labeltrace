import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import type { Dataset, Version } from '../lib/types'
import { formatError } from '../hooks/useAsync'
import { LoadingBlock, StateBlock } from '../components/StateBlock'
import { RequireProject } from '../components/RequireProject'
import { appConfirm } from '../store/dialogStore'

const DATASET_KEY = 'labeltrace.datasetId'

function VersionsInner() {
  const [params] = useSearchParams()
  const datasetId =
    params.get('dataset') || localStorage.getItem(DATASET_KEY)

  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [versions, setVersions] = useState<Version[]>([])
  const [name, setName] = useState('')
  const [note, setNote] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const applyToWorkspace = async (versionId: string, versionName: string) => {
    const ok = await appConfirm({
      title: '应用到工作区',
      description:
        `将版本「${versionName}」合并应用到工作区？\n` +
        `· 同图：覆盖工作区标注（变为草稿）\n` +
        `· 快照多出的图：加入工作区\n` +
        `· 工作区多出的图：保留\n` +
        `不会修改该版本快照本身。`,
      confirmLabel: '应用',
    })
    if (!ok) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const r = await api<{
        added: number
        overwritten: number
        skipped: number
        dataset_id: string
      }>(`/v1/versions/${versionId}/apply-to-workspace`, { method: 'POST' })
      setMessage(
        `已应用到工作区：新增 ${r.added} · 覆盖 ${r.overwritten}` +
          (r.skipped ? ` · 跳过 ${r.skipped}` : ''),
      )
      localStorage.setItem(DATASET_KEY, r.dataset_id)
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusy(false)
    }
  }

  const reload = useCallback(async (id: string) => {
    setLoading(true)
    setError(null)
    try {
      const [ds, vers] = await Promise.all([
        api<Dataset>(`/v1/datasets/${id}`),
        api<Version[]>(`/v1/datasets/${id}/versions`),
      ])
      setDataset(ds)
      setVersions(vers)
      localStorage.setItem(DATASET_KEY, id)
    } catch (e) {
      setError(formatError(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (datasetId) void reload(datasetId)
    else setLoading(false)
  }, [datasetId, reload])

  const publish = async () => {
    if (!datasetId || !name.trim()) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const parent = versions[0]?.id ?? null
      const ver = await api<Version>(`/v1/datasets/${datasetId}/versions`, {
        method: 'POST',
        body: JSON.stringify({
          name: name.trim(),
          note: note.trim() || null,
          parent_id: parent,
        }),
      })
      setName('')
      setNote('')
      setMessage(`已发版 ${ver.name}（${ver.entry_count} 条）`)
      await reload(datasetId)
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusy(false)
    }
  }

  if (!datasetId) {
    return (
      <StateBlock
        title="未选择数据集"
        description="在数据集页打开后再发版。"
        action={
          <Link to="/datasets" className="lt-btn lt-btn-primary">
            前往数据集
          </Link>
        }
      />
    )
  }

  if (loading) return <LoadingBlock />

  return (
    <div>
      <div className="lt-page-head">
        <div>
          <h1>版本</h1>
          <p>
            {dataset?.name ?? '数据集'} · 全部成员须已「提交」标注后方可发版；已发版本可只读查看快照。
          </p>
        </div>
        <Link to={`/annotate?dataset=${datasetId}`} className="lt-btn">
          工作区标注
        </Link>
      </div>

      {error ? (
        <StateBlock tone="error" title="出错了" description={error} />
      ) : null}
      {message ? (
        <p style={{ color: 'var(--lt-success)', marginTop: 0 }}>{message}</p>
      ) : null}

      <div className="lt-panel" style={{ padding: '1rem', marginBottom: '1rem' }}>
        <h2 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>发版</h2>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            className="lt-input"
            placeholder="版本名，如 v1"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className="lt-input"
            placeholder="备注（可选）"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            style={{ maxWidth: 280 }}
          />
          <button
            type="button"
            className="lt-btn lt-btn-primary"
            disabled={busy || !name.trim()}
            onClick={() => void publish()}
          >
            {busy ? '发版中…' : '发布版本'}
          </button>
        </div>
        <p style={{ margin: '0.65rem 0 0', color: 'var(--lt-fg-subtle)', fontSize: 13 }}>
          父版本：{versions[0]?.name ?? '（首版无父）'} · 未提交完会被拒绝 · YOLO
          导出可后置
        </p>
      </div>

      {versions.length === 0 ? (
        <StateBlock
          title="尚无版本"
          description="完成标注后发版，可查看相对父版本的增删改标摘要。"
        />
      ) : (
        <div style={{ display: 'grid', gap: 10 }}>
          {versions.map((v) => (
            <article key={v.id} className="lt-panel" style={{ padding: '1rem' }}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  gap: 12,
                  flexWrap: 'wrap',
                }}
              >
                <div>
                  <h3 style={{ margin: 0 }}>{v.name}</h3>
                  <p
                    style={{
                      margin: '0.25rem 0 0',
                      color: 'var(--lt-fg-muted)',
                      fontSize: 13,
                    }}
                  >
                    {new Date(v.created_at).toLocaleString()} · by {v.created_by} ·{' '}
                    {v.entry_count} 成员
                    {v.note ? ` · ${v.note}` : ''}
                  </p>
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                  {v.change_summary ? (
                    <>
                      <span className="lt-badge">
                        +{v.change_summary.added ?? 0} 增
                      </span>
                      <span className="lt-badge">
                        −{v.change_summary.removed ?? 0} 删
                      </span>
                      <span className="lt-badge">
                        ~{v.change_summary.changedAnnotations ?? 0} 改标
                      </span>
                    </>
                  ) : (
                    <span className="lt-badge">首版</span>
                  )}
                  <Link to={`/annotate?version=${v.id}`} className="lt-btn">
                    查看快照
                  </Link>
                  <button
                    type="button"
                    className="lt-btn lt-btn-primary"
                    disabled={busy}
                    onClick={() => void applyToWorkspace(v.id, v.name)}
                  >
                    应用到工作区
                  </button>
                </div>
              </div>
              {Array.isArray(v.member_sources) && v.member_sources.length > 0 ? (
                <p
                  style={{
                    margin: '0.65rem 0 0',
                    fontSize: 13,
                    color: 'var(--lt-fg-subtle)',
                  }}
                >
                  快照来源 {v.member_sources.length} 项（发版后固定）
                </p>
              ) : null}
            </article>
          ))}
        </div>
      )}
    </div>
  )
}

export function VersionsPage() {
  return (
    <RequireProject>
      <VersionsInner />
    </RequireProject>
  )
}
