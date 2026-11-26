import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import type { Asset, ExtractJob, Folder, FrameCandidate } from '../lib/types'
import { useAppStore } from '../store/appStore'
import { formatError } from '../hooks/useAsync'
import { AuthImage } from '../components/AuthImage'
import { LoadingBlock, StateBlock } from '../components/StateBlock'
import { RequireProject } from '../components/RequireProject'

const EXTRACT_KEY = 'labeltrace.lastExtractJobId'

async function ensureRootFolder(projectId: string): Promise<Folder> {
  const roots = await api<Folder[]>(`/v1/projects/${projectId}/folders`)
  if (roots.length > 0) return roots[0]
  return api<Folder>(`/v1/projects/${projectId}/folders`, {
    method: 'POST',
    body: JSON.stringify({ name: '素材' }),
  })
}

function LibraryInner() {
  const projectId = useAppStore((s) => s.projectId)!
  const [folder, setFolder] = useState<Folder | null>(null)
  const [assets, setAssets] = useState<Asset[]>([])
  const [selectedVideo, setSelectedVideo] = useState<Asset | null>(null)
  const [extractJob, setExtractJob] = useState<ExtractJob | null>(null)
  const [frames, setFrames] = useState<FrameCandidate[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [stride, setStride] = useState(30)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const loadAssets = useCallback(async (folderId: string) => {
    const list = await api<Asset[]>(`/v1/folders/${folderId}/assets`)
    setAssets(list)
  }, [])

  const bootstrap = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const f = await ensureRootFolder(projectId)
      setFolder(f)
      await loadAssets(f.id)
      const lastId = localStorage.getItem(EXTRACT_KEY)
      if (lastId) {
        try {
          const job = await api<ExtractJob>(`/v1/extract-jobs/${lastId}`)
          if (job.project_id === projectId) {
            setExtractJob(job)
            if (job.status === 'succeeded') {
              const fr = await api<FrameCandidate[]>(`/v1/extract-jobs/${lastId}/frames`)
              setFrames(fr)
            }
          }
        } catch {
          localStorage.removeItem(EXTRACT_KEY)
        }
      }
    } catch (e) {
      setError(formatError(e))
    } finally {
      setLoading(false)
    }
  }, [projectId, loadAssets])

  useEffect(() => {
    void bootstrap()
  }, [bootstrap])

  const upload = async (file: File) => {
    if (!folder) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const asset = await api<Asset>(`/v1/folders/${folder.id}/assets`, {
        method: 'POST',
        body: fd,
      })
      await loadAssets(folder.id)
      if (asset.media_kind === 'video') {
        setSelectedVideo(asset)
        setMessage(`已上传视频：${asset.filename}`)
      } else {
        setMessage(`已上传图片：${asset.filename}`)
      }
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusy(false)
    }
  }

  const startExtract = async () => {
    if (!selectedVideo) return
    setBusy(true)
    setError(null)
    setMessage('抽帧任务已提交…')
    setFrames([])
    setSelected(new Set())
    try {
      const job = await api<ExtractJob>(
        `/v1/assets/${selectedVideo.id}/extract-jobs`,
        {
          method: 'POST',
          body: JSON.stringify({
            mode: 'stride_frames',
            stride,
            max_frames: 120,
          }),
        },
      )
      setExtractJob(job)
      localStorage.setItem(EXTRACT_KEY, job.id)
      await pollExtract(job.id)
    } catch (e) {
      setError(formatError(e))
      setMessage(null)
    } finally {
      setBusy(false)
    }
  }

  const pollExtract = async (id: string) => {
    for (let i = 0; i < 120; i++) {
      const job = await api<ExtractJob>(`/v1/extract-jobs/${id}`)
      setExtractJob(job)
      if (job.status === 'succeeded') {
        const fr = await api<FrameCandidate[]>(`/v1/extract-jobs/${id}/frames`)
        setFrames(fr)
        setMessage(`抽帧完成，共 ${fr.length} 帧（按时间升序）`)
        return
      }
      if (job.status === 'failed') {
        setError(job.error_message || '抽帧失败')
        setMessage(null)
        return
      }
      setMessage(`抽帧进行中… ${job.status}`)
      await new Promise((r) => setTimeout(r, 800))
    }
    setError('抽帧超时，请稍后刷新查看')
  }

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const discardSelected = async () => {
    if (!extractJob || selected.size === 0) return
    setBusy(true)
    setError(null)
    try {
      const result = await api<{ discarded_count?: number; deleted?: number }>(
        `/v1/extract-jobs/${extractJob.id}/frames/batch-delete`,
        {
          method: 'POST',
          body: JSON.stringify({ asset_ids: [...selected] }),
        },
      )
      const fr = await api<FrameCandidate[]>(
        `/v1/extract-jobs/${extractJob.id}/frames`,
      )
      setFrames(fr)
      setSelected(new Set())
      const n = result.discarded_count ?? result.deleted ?? selected.size
      setMessage(`已删除 ${n} 帧，剩余 ${fr.length}`)
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusy(false)
    }
  }

  const videos = assets.filter((a) => a.media_kind === 'video')
  const images = assets.filter((a) => a.media_kind === 'image')

  if (loading) return <LoadingBlock />

  return (
    <div>
      <div className="lt-page-head">
        <div>
          <h1>素材库</h1>
          <p>上传视频 → 抽帧 → 按时间审查删帧，再加入数据集。</p>
        </div>
        <label className="lt-btn lt-btn-primary" style={{ cursor: 'pointer' }}>
          上传文件
          <input
            type="file"
            accept="video/*,image/*"
            hidden
            disabled={busy}
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) void upload(f)
              e.target.value = ''
            }}
          />
        </label>
      </div>

      {error ? (
        <StateBlock tone="error" title="出错了" description={error} />
      ) : null}
      {message ? (
        <p style={{ color: 'var(--lt-fg-muted)', marginTop: 0 }}>{message}</p>
      ) : null}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(220px, 280px) 1fr',
          gap: '1rem',
          alignItems: 'start',
        }}
      >
        <section className="lt-panel" style={{ padding: '0.85rem' }}>
          <h2 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>视频</h2>
          {videos.length === 0 ? (
            <StateBlock title="暂无视频" description="上传 mp4 / mov 等开始抽帧。" />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {videos.map((v) => (
                <button
                  key={v.id}
                  type="button"
                  className="lt-btn"
                  style={{
                    justifyContent: 'flex-start',
                    height: 'auto',
                    padding: '0.55rem 0.65rem',
                    background:
                      selectedVideo?.id === v.id
                        ? 'var(--lt-accent-soft)'
                        : undefined,
                  }}
                  onClick={() => setSelectedVideo(v)}
                >
                  <span style={{ textAlign: 'left' }}>
                    <div style={{ fontWeight: 600 }}>{v.filename}</div>
                    <div className="mono" style={{ fontSize: 11, color: 'var(--lt-fg-subtle)' }}>
                      {v.duration_ms != null
                        ? `${(v.duration_ms / 1000).toFixed(1)}s`
                        : '—'}
                      {v.fps != null ? ` · ${v.fps.toFixed(1)} fps` : ''}
                    </div>
                  </span>
                </button>
              ))}
            </div>
          )}

          {selectedVideo ? (
            <div style={{ marginTop: '1rem', display: 'grid', gap: 8 }}>
              <label style={{ fontSize: 12, color: 'var(--lt-fg-muted)' }}>
                抽帧步长（帧）
                <input
                  className="lt-input"
                  type="number"
                  min={1}
                  value={stride}
                  onChange={(e) => setStride(Number(e.target.value) || 1)}
                  style={{ marginTop: 4, maxWidth: '100%' }}
                />
              </label>
              <button
                type="button"
                className="lt-btn lt-btn-primary"
                disabled={busy}
                onClick={() => void startExtract()}
              >
                开始抽帧
              </button>
            </div>
          ) : null}

          {images.length > 0 ? (
            <>
              <h2 style={{ margin: '1.25rem 0 0.5rem', fontSize: '0.95rem' }}>
                上传图片
              </h2>
              <div className="lt-thumb-grid">
                {images.map((img) => (
                  <div key={img.id} className="lt-thumb">
                    <AuthImage assetId={img.id} alt={img.filename} />
                    <div className="lt-thumb-meta">{img.filename}</div>
                  </div>
                ))}
              </div>
            </>
          ) : null}
        </section>

        <section className="lt-panel" style={{ padding: '0.85rem' }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: '0.75rem',
              marginBottom: '0.75rem',
              flexWrap: 'wrap',
            }}
          >
            <div>
              <h2 style={{ margin: 0, fontSize: '0.95rem' }}>候选帧审查</h2>
              <p style={{ margin: '0.2rem 0 0', color: 'var(--lt-fg-muted)', fontSize: 13 }}>
                {extractJob
                  ? `任务 ${extractJob.status} · 已选 ${selected.size} / ${frames.length}`
                  : '抽帧完成后在此按时间顺序审查'}
              </p>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                type="button"
                className="lt-btn lt-btn-danger"
                disabled={busy || selected.size === 0}
                onClick={() => void discardSelected()}
              >
                删除所选
              </button>
              <Link to="/datasets" className="lt-btn lt-btn-primary">
                去入集
              </Link>
            </div>
          </div>

          {frames.length === 0 ? (
            <StateBlock
              title="暂无候选帧"
              description="选择视频并抽帧后，帧按时间升序展示，可批量删除未入集帧。"
            />
          ) : (
            <div className="lt-thumb-grid">
              {frames.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  className={`lt-thumb${selected.has(f.id) ? ' selected' : ''}`}
                  onClick={() => toggle(f.id)}
                  title={f.filename}
                >
                  <AuthImage assetId={f.id} alt={f.time_label} />
                  <div className="lt-thumb-meta">
                    #{f.frame_index ?? '—'} · {f.time_label}
                  </div>
                </button>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

export function LibraryPage() {
  return (
    <RequireProject>
      <LibraryInner />
    </RequireProject>
  )
}
