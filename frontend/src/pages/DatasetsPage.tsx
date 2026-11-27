import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import type {
  Asset,
  Dataset,
  DatasetAsset,
  Folder,
  MemberSource,
} from '../lib/types'
import { useAppStore } from '../store/appStore'
import { formatError } from '../hooks/useAsync'
import { AuthImage } from '../components/AuthImage'
import { LoadingBlock, StateBlock } from '../components/StateBlock'
import { RequireProject } from '../components/RequireProject'
import { appConfirm, appPrompt } from '../store/dialogStore'

const EXTRACT_KEY = 'labeltrace.lastExtractJobId'
const DATASET_KEY = 'labeltrace.datasetId'

async function listAllFolders(projectId: string): Promise<Folder[]> {
  const out: Folder[] = []
  const walk = async (parentId: string | null) => {
    const q = parentId ? `?parent_id=${parentId}` : ''
    const kids = await api<Folder[]>(`/v1/projects/${projectId}/folders${q}`)
    for (const f of kids) {
      out.push(f)
      await walk(f.id)
    }
  }
  await walk(null)
  return out
}

function DatasetsInner() {
  const projectId = useAppStore((s) => s.projectId)!
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [folders, setFolders] = useState<Folder[]>([])
  const [libraryFolderId, setLibraryFolderId] = useState('')
  const [libraryImages, setLibraryImages] = useState<Asset[]>([])
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [activeId, setActiveId] = useState<string | null>(
    localStorage.getItem(DATASET_KEY),
  )
  const [active, setActive] = useState<Dataset | null>(null)
  const [members, setMembers] = useState<DatasetAsset[]>([])
  const [sources, setSources] = useState<MemberSource[]>([])
  const [name, setName] = useState('')
  const [classesText, setClassesText] = useState('person,car')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const selectDataset = useCallback(async (id: string) => {
    setActiveId(id)
    localStorage.setItem(DATASET_KEY, id)
    const [ds, mem, src] = await Promise.all([
      api<Dataset>(`/v1/datasets/${id}`),
      api<DatasetAsset[]>(`/v1/datasets/${id}/assets`),
      api<MemberSource[]>(`/v1/datasets/${id}/member-sources`),
    ])
    setActive(ds)
    setMembers(mem)
    setSources(src)
  }, [])

  const reload = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [list, folderList] = await Promise.all([
        api<Dataset[]>(`/v1/projects/${projectId}/datasets`),
        listAllFolders(projectId),
      ])
      setDatasets(list)
      setFolders(folderList)
      const firstFolder = folderList[0]?.id || ''
      setLibraryFolderId((prev) =>
        prev && folderList.some((f) => f.id === prev) ? prev : firstFolder,
      )
      const prefer =
        (activeId && list.find((d) => d.id === activeId)?.id) ||
        list[0]?.id ||
        null
      if (prefer) await selectDataset(prefer)
      else {
        setActive(null)
        setMembers([])
        setSources([])
      }
    } catch (e) {
      setError(formatError(e))
    } finally {
      setLoading(false)
    }
  }, [projectId, activeId, selectDataset])

  useEffect(() => {
    void reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 仅随项目切换
  }, [projectId])

  const create = async () => {
    if (!name.trim()) return
    setBusy(true)
    setError(null)
    try {
      const classes = classesText
        .split(/[,，\s]+/)
        .map((s) => s.trim())
        .filter(Boolean)
      const ds = await api<Dataset>(`/v1/projects/${projectId}/datasets`, {
        method: 'POST',
        body: JSON.stringify({
          name: name.trim(),
          classes,
          enabledAnnotationTypes: ['rect'],
        }),
      })
      setName('')
      setDatasets((prev) => [ds, ...prev])
      await selectDataset(ds.id)
      setMessage(`已创建数据集 ${ds.name}`)
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusy(false)
    }
  }

  const addFromExtract = async () => {
    if (!active) return
    const extractId = localStorage.getItem(EXTRACT_KEY)
    if (!extractId) {
      setError('没有最近的抽帧任务，请先在素材库抽帧并审查')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const added = await api<DatasetAsset[]>(
        `/v1/datasets/${active.id}/assets/from-extract`,
        {
          method: 'POST',
          body: JSON.stringify({
            extract_job_id: extractId,
            split: 'unassigned',
          }),
        },
      )
      await selectDataset(active.id)
      setMessage(`已加入审查剩余帧 ${added.length} 张`)
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusy(false)
    }
  }

  const loadLibraryImages = useCallback(async (folderId: string) => {
    if (!folderId) {
      setLibraryImages([])
      setPicked(new Set())
      return
    }
    const list = await api<Asset[]>(`/v1/folders/${folderId}/assets`)
    setLibraryImages(list.filter((a) => a.media_kind === 'image'))
    setPicked(new Set())
  }, [])

  useEffect(() => {
    if (!libraryFolderId) {
      setLibraryImages([])
      return
    }
    void loadLibraryImages(libraryFolderId).catch((e) =>
      setError(formatError(e)),
    )
  }, [libraryFolderId, loadLibraryImages])

  const togglePick = (id: string) => {
    setPicked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const renameDataset = async () => {
    if (!active) return
    const next = await appPrompt({
      title: '重命名数据集',
      label: '数据集名称',
      defaultValue: active.name,
      confirmLabel: '保存',
    })
    if (next == null) return
    const name = next.trim()
    if (!name || name === active.name) return
    setBusy(true)
    setError(null)
    try {
      const ds = await api<Dataset>(`/v1/datasets/${active.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ name }),
      })
      setDatasets((prev) => prev.map((d) => (d.id === ds.id ? ds : d)))
      setActive(ds)
      setMessage(`已重命名为 ${ds.name}`)
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusy(false)
    }
  }

  const removeMember = async (assetId: string) => {
    if (!active) return
    const ok = await appConfirm({
      title: '移出数据集成员',
      description: '从数据集移出该素材？不会删除素材库中的文件。',
      confirmLabel: '移出',
      danger: true,
    })
    if (!ok) return
    setBusy(true)
    setError(null)
    try {
      await api(`/v1/datasets/${active.id}/assets/${assetId}`, {
        method: 'DELETE',
      })
      await selectDataset(active.id)
      setMessage('已从数据集移出')
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusy(false)
    }
  }

  const addFromLibrary = async () => {
    if (!active) return
    if (picked.size === 0) {
      setError('请先勾选素材库中的图片')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const added = await api<DatasetAsset[]>(`/v1/datasets/${active.id}/assets`, {
        method: 'POST',
        body: JSON.stringify({
          asset_ids: [...picked],
          split: 'unassigned',
        }),
      })
      setPicked(new Set())
      await selectDataset(active.id)
      setMessage(`已从素材库加入 ${added.length} 张`)
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <LoadingBlock />

  return (
    <div>
      <div className="lt-page-head">
        <div>
          <h1>数据集</h1>
          <p>
            图片/视频请在素材库上传；本页只从库勾选入集或加入抽帧剩余帧 → 标注 → 发版。
          </p>
        </div>
      </div>

      {error ? (
        <StateBlock tone="error" title="出错了" description={error} />
      ) : null}
      {message ? (
        <p style={{ color: 'var(--lt-fg-muted)', marginTop: 0 }}>{message}</p>
      ) : null}

      <div className="lt-panel" style={{ padding: '1rem', marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            className="lt-input"
            placeholder="数据集名称"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className="lt-input"
            placeholder="类别，逗号分隔"
            value={classesText}
            onChange={(e) => setClassesText(e.target.value)}
            style={{ maxWidth: 240 }}
          />
          <button
            type="button"
            className="lt-btn lt-btn-primary"
            disabled={busy || !name.trim()}
            onClick={() => void create()}
          >
            创建
          </button>
        </div>
      </div>

      {datasets.length === 0 ? (
        <StateBlock title="暂无数据集" description="创建数据集后，可将审查剩余帧或上传图加入。" />
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '220px 1fr',
            gap: '1rem',
            alignItems: 'start',
          }}
        >
          <aside className="lt-panel" style={{ padding: '0.5rem' }}>
            {datasets.map((d) => (
              <button
                key={d.id}
                type="button"
                className="lt-btn"
                style={{
                  width: '100%',
                  justifyContent: 'flex-start',
                  marginBottom: 4,
                  background:
                    d.id === active?.id ? 'var(--lt-accent-soft)' : undefined,
                }}
                onClick={() => void selectDataset(d.id)}
              >
                {d.name}
              </button>
            ))}
          </aside>

          {active ? (
            <section>
              <div className="lt-panel" style={{ padding: '1rem', marginBottom: '1rem' }}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    gap: 12,
                    flexWrap: 'wrap',
                    alignItems: 'center',
                  }}
                >
                  <div>
                    <h2 style={{ margin: 0 }}>{active.name}</h2>
                    <p style={{ margin: '0.25rem 0 0', color: 'var(--lt-fg-muted)' }}>
                      类别：{active.classes.join(', ') || '（无）'} · 工具：
                      {active.enabled_annotation_types.join(', ')}
                    </p>
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                    <button
                      type="button"
                      className="lt-btn"
                      disabled={busy}
                      onClick={() => void renameDataset()}
                    >
                      重命名
                    </button>
                    <button
                      type="button"
                      className="lt-btn lt-btn-primary"
                      disabled={busy}
                      onClick={() => void addFromExtract()}
                    >
                      加入审查剩余帧
                    </button>
                    <Link to="/library" className="lt-btn">
                      去素材库上传
                    </Link>
                    <Link
                      to={`/annotate?dataset=${active.id}`}
                      className="lt-btn"
                    >
                      打开标注台
                    </Link>
                    <Link
                      to={`/versions?dataset=${active.id}`}
                      className="lt-btn"
                    >
                      版本
                    </Link>
                  </div>
                </div>
              </div>

              <div className="lt-panel" style={{ padding: '1rem', marginBottom: '1rem' }}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    gap: 12,
                    flexWrap: 'wrap',
                    alignItems: 'center',
                    marginBottom: '0.75rem',
                  }}
                >
                  <h3 style={{ margin: 0, fontSize: '0.95rem' }}>从素材库加入</h3>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                    {folders.length === 0 ? (
                      <Link to="/library" className="lt-btn">
                        先去素材库建目录并上传
                      </Link>
                    ) : (
                      <>
                        <select
                          className="lt-select"
                          value={libraryFolderId}
                          onChange={(e) => setLibraryFolderId(e.target.value)}
                          style={{ maxWidth: 200 }}
                        >
                          {folders.map((f) => (
                            <option key={f.id} value={f.id}>
                              {f.path}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          className="lt-btn lt-btn-primary"
                          disabled={busy || picked.size === 0}
                          onClick={() => void addFromLibrary()}
                        >
                          加入所选（{picked.size}）
                        </button>
                      </>
                    )}
                  </div>
                </div>
                {folders.length > 0 && libraryImages.length === 0 ? (
                  <StateBlock
                    title="该目录没有图片"
                    description="到素材库上传图片，或换一个目录；视频请抽帧后再入集。"
                  />
                ) : null}
                {libraryImages.length > 0 ? (
                  <div className="lt-thumb-grid">
                    {libraryImages.map((img) => {
                      const already = members.some((m) => m.asset_id === img.id)
                      const on = picked.has(img.id)
                      return (
                        <button
                          key={img.id}
                          type="button"
                          className={`lt-thumb${on ? ' selected' : ''}`}
                          disabled={already}
                          title={
                            already
                              ? '已在数据集中'
                              : img.filename
                          }
                          onClick={() => togglePick(img.id)}
                          style={{ opacity: already ? 0.45 : 1 }}
                        >
                          <AuthImage assetId={img.id} alt={img.filename} />
                          <div className="lt-thumb-meta">
                            {already ? '已入集' : img.filename}
                          </div>
                        </button>
                      )
                    })}
                  </div>
                ) : null}
              </div>

              <div className="lt-panel" style={{ padding: '1rem', marginBottom: '1rem' }}>
                <h3 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>
                  来源摘要
                </h3>
                {sources.length === 0 ? (
                  <StateBlock title="尚无成员" description="上方从素材库勾选图片加入，或抽帧入集 / 上传新图。" />
                ) : (
                  <div style={{ display: 'grid', gap: 8 }}>
                    {sources.map((s, i) => (
                      <div
                        key={i}
                        style={{
                          padding: '0.65rem 0.75rem',
                          background: 'var(--lt-bg-muted)',
                          borderRadius: 'var(--lt-radius)',
                        }}
                      >
                        {s.kind === 'extract' ? (
                          <>
                            <span className="lt-badge">抽帧</span>{' '}
                            {s.videoName || s.videoId} · {s.frameCount} 帧
                            {s.mode === 'stride_frames' && s.stride != null
                              ? ` · stride ${s.stride}`
                              : null}
                          </>
                        ) : null}
                        {s.kind === 'upload' ? (
                          <>
                            <span className="lt-badge">上传</span> {s.imageCount}{' '}
                            张图
                          </>
                        ) : null}
                        {s.kind === 'import' ? (
                          <>
                            <span className="lt-badge">导入</span> {s.imageCount}{' '}
                            张
                          </>
                        ) : null}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="lt-panel" style={{ padding: '1rem' }}>
                <h3 style={{ margin: '0 0 0.35rem', fontSize: '0.95rem' }}>
                  成员（{members.length}）
                </h3>
                <p
                  style={{
                    margin: '0 0 0.75rem',
                    color: 'var(--lt-fg-muted)',
                    fontSize: 13,
                  }}
                >
                  划分在发版时按比例随机指定；工作区不展示未分配状态。
                </p>
                {members.length === 0 ? (
                  <StateBlock
                    title="空数据集"
                    description="请在素材库上传后，在下方从库勾选加入，或加入抽帧剩余帧。"
                  />
                ) : (
                  <div className="lt-thumb-grid">
                    {members.map((m) => (
                      <div key={m.asset_id} className="lt-thumb" style={{ position: 'relative' }}>
                        <Link
                          to={`/annotate?dataset=${active.id}&asset=${m.asset_id}`}
                          title={m.filename}
                          style={{ display: 'block', color: 'inherit' }}
                        >
                          <AuthImage assetId={m.asset_id} alt={m.filename} />
                          <div className="lt-thumb-meta">{m.filename}</div>
                        </Link>
                        <button
                          type="button"
                          className="lt-btn lt-btn-danger"
                          disabled={busy}
                          style={{
                            position: 'absolute',
                            top: 4,
                            right: 4,
                            height: 24,
                            padding: '0 6px',
                            fontSize: 11,
                          }}
                          title="从数据集移出"
                          onClick={() => void removeMember(m.asset_id)}
                        >
                          移出
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>
          ) : null}
        </div>
      )}
    </div>
  )
}

export function DatasetsPage() {
  return (
    <RequireProject>
      <DatasetsInner />
    </RequireProject>
  )
}
