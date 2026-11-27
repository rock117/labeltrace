import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import type { Asset, ExtractJob, Folder, FrameCandidate } from '../lib/types'
import { useAppStore } from '../store/appStore'
import { formatError } from '../hooks/useAsync'
import { AuthImage } from '../components/AuthImage'
import { LoadingBlock, StateBlock } from '../components/StateBlock'
import { RequireProject } from '../components/RequireProject'
import { appPrompt } from '../store/dialogStore'

const EXTRACT_KEY = 'labeltrace.lastExtractJobId'
const FOLDER_KEY = 'labeltrace.folderId'

function LibraryInner() {
  const projectId = useAppStore((s) => s.projectId)!
  const [trail, setTrail] = useState<Folder[]>([])
  const [childFolders, setChildFolders] = useState<Folder[]>([])
  const [folder, setFolder] = useState<Folder | null>(null)
  const [assets, setAssets] = useState<Asset[]>([])
  const [selectedVideo, setSelectedVideo] = useState<Asset | null>(null)
  const [extractJob, setExtractJob] = useState<ExtractJob | null>(null)
  const [frames, setFrames] = useState<FrameCandidate[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [stride, setStride] = useState(30)
  const [newFolderName, setNewFolderName] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const currentParentId = folder?.id ?? null

  const loadChildren = useCallback(
    async (parentId: string | null) => {
      const q = parentId ? `?parent_id=${parentId}` : ''
      return api<Folder[]>(`/v1/projects/${projectId}/folders${q}`)
    },
    [projectId],
  )

  const loadAssets = useCallback(async (folderId: string) => {
    const list = await api<Asset[]>(`/v1/folders/${folderId}/assets`)
    setAssets(list)
  }, [])

  const enterFolder = useCallback(
    async (next: Folder | null, nextTrail: Folder[]) => {
      setFolder(next)
      setTrail(nextTrail)
      setSelectedVideo(null)
      setAssets([])
      if (next) {
        localStorage.setItem(FOLDER_KEY, next.id)
        const [kids] = await Promise.all([
          loadChildren(next.id),
          loadAssets(next.id),
        ])
        setChildFolders(kids)
      } else {
        localStorage.removeItem(FOLDER_KEY)
        setChildFolders(await loadChildren(null))
      }
    },
    [loadAssets, loadChildren],
  )

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError(null)
      try {
        const roots = await loadChildren(null)
        if (cancelled) return
        setChildFolders(roots)
        setFolder(null)
        setTrail([])
        setAssets([])

        const savedId = localStorage.getItem(FOLDER_KEY)
        if (savedId) {
          try {
            const f = await api<Folder>(`/v1/folders/${savedId}`)
            if (!cancelled && f.project_id === projectId) {
              await enterFolder(f, [f])
            } else if (f.project_id !== projectId) {
              localStorage.removeItem(FOLDER_KEY)
            }
          } catch {
            localStorage.removeItem(FOLDER_KEY)
          }
        }

        const lastId = localStorage.getItem(EXTRACT_KEY)
        if (lastId) {
          try {
            const job = await api<ExtractJob>(`/v1/extract-jobs/${lastId}`)
            if (!cancelled && job.project_id === projectId) {
              setExtractJob(job)
              if (job.status === 'succeeded') {
                const fr = await api<FrameCandidate[]>(
                  `/v1/extract-jobs/${lastId}/frames`,
                )
                if (!cancelled) setFrames(fr)
              }
            }
          } catch {
            localStorage.removeItem(EXTRACT_KEY)
          }
        }
      } catch (e) {
        if (!cancelled) setError(formatError(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
    // 仅项目切换时重载；enterFolder 稳定用于恢复已选目录
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  const createFolder = async () => {
    const name = newFolderName.trim()
    if (!name) return
    setBusy(true)
    setError(null)
    try {
      const created = await api<Folder>(`/v1/projects/${projectId}/folders`, {
        method: 'POST',
        body: JSON.stringify({
          name,
          parent_id: currentParentId,
        }),
      })
      setNewFolderName('')
      setMessage(`已创建目录：${created.path}`)
      await enterFolder(created, [...trail, created])
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusy(false)
    }
  }

  const renameFolder = async (target: Folder) => {
    const next = await appPrompt({
      title: '重命名目录',
      label: '目录名称',
      defaultValue: target.name,
      confirmLabel: '保存',
    })
    if (next == null) return
    const name = next.trim()
    if (!name || name === target.name) return
    setBusy(true)
    setError(null)
    try {
      const updated = await api<Folder>(`/v1/folders/${target.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ name }),
      })
      setMessage(`已重命名目录：${updated.path}`)
      if (folder?.id === updated.id) {
        const nextTrail = [...trail]
        const i = nextTrail.findIndex((f) => f.id === updated.id)
        if (i >= 0) nextTrail[i] = updated
        await enterFolder(updated, nextTrail.length ? nextTrail : [updated])
      } else if (folder) {
        setChildFolders(await loadChildren(folder.id))
      } else {
        setChildFolders(await loadChildren(null))
      }
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusy(false)
    }
  }

  const renameAsset = async (asset: Asset) => {
    const next = await appPrompt({
      title: '重命名素材',
      label: '显示名称',
      defaultValue: asset.filename,
      confirmLabel: '保存',
    })
    if (next == null) return
    const filename = next.trim()
    if (!filename || filename === asset.filename) return
    setBusy(true)
    setError(null)
    try {
      const updated = await api<Asset>(`/v1/assets/${asset.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ filename }),
      })
      if (folder) await loadAssets(folder.id)
      if (selectedVideo?.id === updated.id) setSelectedVideo(updated)
      setMessage(`已重命名：${updated.filename}`)
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusy(false)
    }
  }

  const upload = async (files: FileList | File[]) => {
    if (!folder) {
      setError('请先创建或选择一个目录，再上传')
      return
    }
    const list = Array.from(files)
    if (list.length === 0) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      let lastVideo: Asset | null = null
      let nImg = 0
      let nVid = 0
      for (const file of list) {
        const fd = new FormData()
        fd.append('file', file)
        const asset = await api<Asset>(`/v1/folders/${folder.id}/assets`, {
          method: 'POST',
          body: fd,
        })
        if (asset.media_kind === 'video') {
          nVid += 1
          lastVideo = asset
        } else {
          nImg += 1
        }
      }
      await loadAssets(folder.id)
      if (lastVideo) setSelectedVideo(lastVideo)
      const parts: string[] = []
      if (nImg) parts.push(`${nImg} 张图片`)
      if (nVid) parts.push(`${nVid} 个视频`)
      setMessage(`已上传 ${parts.join('、')}`)
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
          <p>先建/选目录，再上传视频 → 抽帧 → 按时间审查删帧，再加入数据集。</p>
        </div>
        <label
          className="lt-btn lt-btn-primary"
          style={{
            cursor: folder ? 'pointer' : 'not-allowed',
            opacity: folder ? 1 : 0.5,
          }}
          title={folder ? '上传到当前目录' : '请先选择目录'}
        >
          上传到当前目录
          <input
            type="file"
            accept="video/*,image/*"
            multiple
            hidden
            disabled={busy || !folder}
            onChange={(e) => {
              if (e.target.files?.length) void upload(e.target.files)
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
        className="lt-panel"
        style={{
          padding: '0.85rem',
          marginBottom: '1rem',
          display: 'flex',
          flexWrap: 'wrap',
          gap: 8,
          alignItems: 'center',
        }}
      >
        <nav style={{ display: 'flex', flexWrap: 'wrap', gap: 4, alignItems: 'center' }}>
          <button
            type="button"
            className="lt-btn lt-btn-ghost"
            onClick={() => void enterFolder(null, [])}
          >
            根目录
          </button>
          {trail.map((f, i) => (
            <span key={f.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <span className="lt-muted">/</span>
              <button
                type="button"
                className="lt-btn lt-btn-ghost"
                onClick={() => void enterFolder(f, trail.slice(0, i + 1))}
              >
                {f.name}
              </button>
            </span>
          ))}
        </nav>
        <span style={{ flex: 1 }} />
        <input
          className="lt-input"
          placeholder={folder ? '在此目录下新建子目录' : '新建根目录名称'}
          value={newFolderName}
          onChange={(e) => setNewFolderName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && void createFolder()}
          style={{ maxWidth: 220 }}
        />
        <button
          type="button"
          className="lt-btn"
          disabled={busy || !newFolderName.trim()}
          onClick={() => void createFolder()}
        >
          新建目录
        </button>
        {folder ? (
          <button
            type="button"
            className="lt-btn"
            disabled={busy}
            onClick={() => void renameFolder(folder)}
          >
            重命名当前目录
          </button>
        ) : null}
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(220px, 280px) 1fr',
          gap: '1rem',
          alignItems: 'start',
        }}
      >
        <section className="lt-panel" style={{ padding: '0.85rem' }}>
          <h2 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>
            {folder ? '子目录与素材' : '目录'}
          </h2>

          {childFolders.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }}>
              {childFolders.map((f) => (
                <div key={f.id} style={{ display: 'flex', gap: 6, alignItems: 'stretch' }}>
                  <button
                    type="button"
                    className="lt-btn"
                    style={{
                      flex: 1,
                      justifyContent: 'flex-start',
                      height: 'auto',
                      padding: '0.55rem 0.65rem',
                    }}
                    onClick={() => void enterFolder(f, [...trail, f])}
                  >
                    <span style={{ textAlign: 'left' }}>
                      <div style={{ fontWeight: 600 }}>{f.name}</div>
                      <div className="mono" style={{ fontSize: 11, color: 'var(--lt-fg-subtle)' }}>
                        {f.path}
                      </div>
                    </span>
                  </button>
                  <button
                    type="button"
                    className="lt-btn"
                    disabled={busy}
                    title="重命名目录"
                    onClick={() => void renameFolder(f)}
                  >
                    改名
                  </button>
                </div>
              ))}
            </div>
          ) : null}

          {!folder ? (
            <StateBlock
              title={childFolders.length === 0 ? '还没有目录' : '请选择目录'}
              description={
                childFolders.length === 0
                  ? '按规格须先创建目录，再上传素材到该目录。'
                  : '点左侧/上方目录进入后才能上传。'
              }
            />
          ) : (
            <>
              <h2 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>视频</h2>
              {videos.length === 0 ? (
                <StateBlock
                  title="暂无视频"
                  description="上传 mp4 / mov 等到当前目录后开始抽帧。"
                />
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {videos.map((v) => (
                    <div key={v.id} style={{ display: 'flex', gap: 6 }}>
                      <button
                        type="button"
                        className="lt-btn"
                        style={{
                          flex: 1,
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
                          <div
                            className="mono"
                            style={{ fontSize: 11, color: 'var(--lt-fg-subtle)' }}
                          >
                            {v.duration_ms != null
                              ? `${(v.duration_ms / 1000).toFixed(1)}s`
                              : '—'}
                            {v.fps != null ? ` · ${v.fps.toFixed(1)} fps` : ''}
                          </div>
                        </span>
                      </button>
                      <button
                        type="button"
                        className="lt-btn"
                        disabled={busy}
                        onClick={() => void renameAsset(v)}
                      >
                        改名
                      </button>
                    </div>
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
                      <div key={img.id} className="lt-thumb" style={{ position: 'relative' }}>
                        <AuthImage assetId={img.id} alt={img.filename} />
                        <div className="lt-thumb-meta">{img.filename}</div>
                        <button
                          type="button"
                          className="lt-btn"
                          disabled={busy}
                          style={{
                            position: 'absolute',
                            top: 4,
                            right: 4,
                            height: 24,
                            padding: '0 6px',
                            fontSize: 11,
                          }}
                          onClick={() => void renameAsset(img)}
                        >
                          改名
                        </button>
                      </div>
                    ))}
                  </div>
                </>
              ) : null}
            </>
          )}
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
              <p
                style={{
                  margin: '0.2rem 0 0',
                  color: 'var(--lt-fg-muted)',
                  fontSize: 13,
                }}
              >
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
