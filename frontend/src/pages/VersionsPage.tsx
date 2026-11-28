import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, getToken } from '../lib/api'
import type { Dataset, Version } from '../lib/types'
import { formatError } from '../hooks/useAsync'
import { LoadingBlock, StateBlock } from '../components/StateBlock'
import { RequireProject } from '../components/RequireProject'
import { useAppStore } from '../store/appStore'
import { appConfirm } from '../store/dialogStore'
import {
  getStoredDatasetId,
  setStoredDataset,
} from '../lib/workspaceStorage'

type JobStatus = {
  id: string
  status: string
  progress: number | null
  result: Record<string, unknown> | null
  error_message: string | null
}

function VersionsInner() {
  const projectId = useAppStore((s) => s.projectId)
  const [params, setParams] = useSearchParams()
  const datasetId =
    params.get('dataset') || getStoredDatasetId()

  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [versions, setVersions] = useState<Version[]>([])
  const [name, setName] = useState('')
  const [note, setNote] = useState('')
  const [splitTrain, setSplitTrain] = useState(0.7)
  const [splitVal, setSplitVal] = useState(0.2)
  const [splitTest, setSplitTest] = useState(0.1)
  const [splitSeed, setSplitSeed] = useState(42)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [exportingId, setExportingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const splitSum = Math.round((splitTrain + splitVal + splitTest) * 1000) / 1000
  const splitOk = Math.abs(splitSum - 1) < 0.001

  const downloadExportZip = async (versionId: string) => {
    const headers: Record<string, string> = {}
    const token = getToken()
    if (token) headers.Authorization = `Bearer ${token}`
    const res = await fetch(`/api/v1/versions/${versionId}/export/download`, {
      headers,
    })
    if (!res.ok) {
      let detail: unknown = await res.text()
      try {
        detail = JSON.parse(detail as string)
      } catch {
        /* keep text */
      }
      const obj = detail as { detail?: unknown } | null
      throw new Error(
        typeof obj?.detail === 'string'
          ? obj.detail
          : `下载失败（${res.status}）`,
      )
    }
    const blob = await res.blob()
    const cd = res.headers.get('Content-Disposition') || ''
    const star = /filename\*=UTF-8''([^;]+)/i.exec(cd)
    const quoted = /filename="([^"]+)"/i.exec(cd)
    const plain = /filename=([^;]+)/i.exec(cd)
    let filename = 'export.zip'
    const raw = (star?.[1] || quoted?.[1] || plain?.[1] || '').trim()
    if (raw) {
      try {
        filename = decodeURIComponent(raw)
      } catch {
        filename = raw
      }
    }
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const exportYolo = async (versionId: string, versionName: string) => {
    setExportingId(versionId)
    setError(null)
    setMessage(`正在导出 ${versionName}…`)
    try {
      const enq = await api<{ job_id: string; status: string }>(
        `/v1/versions/${versionId}/export`,
        { method: 'POST' },
      )
      let job: JobStatus | null = null
      for (let i = 0; i < 120; i++) {
        job = await api<JobStatus>(`/v1/jobs/${enq.job_id}`)
        if (job.status === 'succeeded' || job.status === 'failed') break
        setMessage(
          `正在导出 ${versionName}… ${job.status}` +
            (job.progress != null ? ` ${Math.round(job.progress * 100)}%` : ''),
        )
        await new Promise((r) => setTimeout(r, 500))
      }
      if (!job || job.status !== 'succeeded') {
        throw new Error(job?.error_message || '导出失败或超时')
      }
      const n = (job.result?.imageCount as number | undefined) ?? null
      setMessage(
        `导出完成${n != null ? `（${n} 张）` : ''}，开始下载…`,
      )
      await downloadExportZip(versionId)
      setMessage(
        `已下载 YOLO 包${n != null ? `（${n} 张）` : ''} · ${versionName}`,
      )
    } catch (e) {
      setError(formatError(e))
      setMessage(null)
    } finally {
      setExportingId(null)
    }
  }

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
      setStoredDataset(
        { id: r.dataset_id, name: dataset?.name || '' },
        { projectId },
      )
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
      if (projectId && ds.project_id !== projectId) {
        setStoredDataset(null, { projectId })
        setDataset(null)
        setVersions([])
        setParams({}, { replace: true })
        setError('该数据集不属于当前项目，请从数据集页重新打开')
        return
      }
      setDataset(ds)
      setVersions(vers)
      setStoredDataset({ id: ds.id, name: ds.name }, { projectId })
    } catch (e) {
      setError(formatError(e))
      setDataset(null)
      setVersions([])
    } finally {
      setLoading(false)
    }
  }, [projectId, setParams])

  useEffect(() => {
    if (datasetId) void reload(datasetId)
    else {
      setDataset(null)
      setVersions([])
      setLoading(false)
    }
  }, [datasetId, reload, projectId])

  const publish = async () => {
    if (!datasetId || !name.trim() || !splitOk) return
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
          split_train: splitTrain,
          split_val: splitVal,
          split_test: splitTest,
          split_seed: splitSeed,
        }),
      })
      setName('')
      setNote('')
      setMessage(
        `已发版 ${ver.name}（${ver.entry_count} 条）· 按 ${splitTrain}/${splitVal}/${splitTest} 随机划分`,
      )
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
            {dataset?.name ?? '数据集'} · 全部成员须已「提交」标注后方可发版；发版时按比例随机划分
            train/val/test；导出为该版本的 YOLO detect zip。
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
        </div>
        <div
          style={{
            display: 'flex',
            gap: 8,
            flexWrap: 'wrap',
            alignItems: 'center',
            marginTop: 10,
          }}
        >
          <label style={{ fontSize: 13, color: 'var(--lt-fg-muted)' }}>
            train
            <input
              className="lt-input"
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={splitTrain}
              onChange={(e) => setSplitTrain(Number(e.target.value))}
              style={{ width: 72, marginLeft: 6 }}
            />
          </label>
          <label style={{ fontSize: 13, color: 'var(--lt-fg-muted)' }}>
            val
            <input
              className="lt-input"
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={splitVal}
              onChange={(e) => setSplitVal(Number(e.target.value))}
              style={{ width: 72, marginLeft: 6 }}
            />
          </label>
          <label style={{ fontSize: 13, color: 'var(--lt-fg-muted)' }}>
            test
            <input
              className="lt-input"
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={splitTest}
              onChange={(e) => setSplitTest(Number(e.target.value))}
              style={{ width: 72, marginLeft: 6 }}
            />
          </label>
          <label style={{ fontSize: 13, color: 'var(--lt-fg-muted)' }}>
            seed
            <input
              className="lt-input"
              type="number"
              value={splitSeed}
              onChange={(e) => setSplitSeed(Number(e.target.value))}
              style={{ width: 80, marginLeft: 6 }}
            />
          </label>
          <button
            type="button"
            className="lt-btn lt-btn-primary"
            disabled={busy || !name.trim() || !splitOk}
            onClick={() => void publish()}
          >
            {busy ? '发版中…' : '发布版本'}
          </button>
        </div>
        <p style={{ margin: '0.65rem 0 0', color: 'var(--lt-fg-subtle)', fontSize: 13 }}>
          父版本：{versions[0]?.name ?? '（首版无父）'} · 比例之和须为 1（当前{' '}
          {splitSum}
          {!splitOk ? '，请调整' : ''}）· 未提交完会被拒绝
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
                    disabled={busy || exportingId === v.id}
                    onClick={() => void exportYolo(v.id, v.name)}
                  >
                    {exportingId === v.id ? '导出中…' : '导出 YOLO'}
                  </button>
                  <button
                    type="button"
                    className="lt-btn"
                    disabled={busy || exportingId != null}
                    onClick={() => void applyToWorkspace(v.id, v.name)}
                  >
                    应用到工作区
                  </button>
                </div>
              </div>
              {(() => {
                const split = v.change_summary?.split
                const ratios = split?.ratios
                const counts = split?.counts
                if (!ratios && !counts && split?.seed == null) return null
                const fmt = (n: number | undefined) =>
                  n == null ? '—' : `${Math.round(n * 100)}%`
                return (
                  <p
                    style={{
                      margin: '0.65rem 0 0',
                      fontSize: 13,
                      color: 'var(--lt-fg-muted)',
                    }}
                  >
                    划分
                    {ratios
                      ? ` train ${fmt(ratios.train)} / val ${fmt(ratios.val)} / test ${fmt(ratios.test)}`
                      : ''}
                    {counts
                      ? ` · ${counts.train ?? 0}/${counts.val ?? 0}/${counts.test ?? 0} 张`
                      : ''}
                    {` · seed ${split?.seed ?? '—'}`}
                  </p>
                )
              })()}
              {Array.isArray(v.member_sources) && v.member_sources.length > 0 ? (
                <p
                  style={{
                    margin: '0.35rem 0 0',
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
