import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import type {
  Asset,
  Dataset,
  DatasetAsset,
  Folder,
  MemberSource,
  ProjectClass,
  ProjectExtractJob,
} from '../lib/types'
import { useAppStore } from '../store/appStore'
import { formatError } from '../hooks/useAsync'
import { useActionPending } from '../hooks/useActionPending'
import { AuthImage } from '../components/AuthImage'
import { AuthVideoThumb } from '../components/AuthVideoThumb'
import { LoadingBlock, StateBlock } from '../components/StateBlock'
import { RequireProject } from '../components/RequireProject'
import { appConfirm, appPrompt } from '../store/dialogStore'
import {
  getStoredDatasetId,
  setStoredDataset,
} from '../lib/workspaceStorage'

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
  const [extractJobs, setExtractJobs] = useState<ProjectExtractJob[]>([])
  const [pickedJobs, setPickedJobs] = useState<Set<string>>(new Set())
  const [pickedMembers, setPickedMembers] = useState<Set<string>>(new Set())
  const [activeId, setActiveId] = useState<string | null>(getStoredDatasetId())
  const [active, setActive] = useState<Dataset | null>(null)
  const [members, setMembers] = useState<DatasetAsset[]>([])
  const [sources, setSources] = useState<MemberSource[]>([])
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(true)
  const { is, run } = useActionPending()
  const [importName, setImportName] = useState('')
  const [projectClasses, setProjectClasses] = useState<ProjectClass[]>([])
  const [enabledIds, setEnabledIds] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const loadExtractJobs = useCallback(
    async (datasetId: string | null) => {
      const q = datasetId ? `?status=succeeded&dataset_id=${datasetId}` : '?status=succeeded'
      const jobs = await api<ProjectExtractJob[]>(
        `/v1/projects/${projectId}/extract-jobs${q}`,
      )
      setExtractJobs(jobs)
      setPickedJobs(new Set())
    },
    [projectId],
  )

  const selectDataset = useCallback(
    async (id: string) => {
      const [ds, mem, src] = await Promise.all([
        api<Dataset>(`/v1/datasets/${id}`),
        api<DatasetAsset[]>(`/v1/datasets/${id}/assets`),
        api<MemberSource[]>(`/v1/datasets/${id}/member-sources`),
      ])
      if (ds.project_id !== projectId) {
        setStoredDataset(null, { projectId })
        setActiveId(null)
        setActive(null)
        setMembers([])
        setSources([])
        setError('该数据集不属于当前项目，已清空选择')
        return []
      }
      setActiveId(id)
      setStoredDataset({ id: ds.id, name: ds.name }, { projectId })
      setActive(ds)
      setEnabledIds(ds.classes.map((c) => c.id))
      setMembers(mem)
      setSources(src)
      setPickedMembers(new Set())
      await loadExtractJobs(id)
      return mem
    },
    [loadExtractJobs, projectId],
  )

  const saveEnabledClasses = async (classIds: string[]) => {
    if (!active) return
    const prev = enabledIds
    setEnabledIds(classIds)
    setError(null)
    await run('classes', async () => {
      try {
        const ds = await api<Dataset>(`/v1/datasets/${active.id}/classes`, {
          method: 'PUT',
          body: JSON.stringify({ classIds }),
        })
        setActive(ds)
        setEnabledIds(ds.classes.map((c) => c.id))
        setDatasets((prevDs) => prevDs.map((d) => (d.id === ds.id ? ds : d)))
      } catch (e) {
        setEnabledIds(prev)
        setError(formatError(e))
      }
    })
  }

  const reload = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [list, folderList, vocabulary] = await Promise.all([
        api<Dataset[]>(`/v1/projects/${projectId}/datasets`),
        listAllFolders(projectId),
        api<ProjectClass[]>(`/v1/projects/${projectId}/classes`),
      ])
      setDatasets(list)
      setProjectClasses(vocabulary)
      setFolders(folderList)
      const firstFolder = folderList[0]?.id || ''
      setLibraryFolderId((prev) =>
        prev && folderList.some((f) => f.id === prev) ? prev : firstFolder,
      )
      const hint = getStoredDatasetId()
      const prefer =
        (hint && list.find((d) => d.id === hint)?.id) ||
        list[0]?.id ||
        null
      if (prefer) await selectDataset(prefer)
      else {
        setStoredDataset(null, { projectId })
        setActiveId(null)
        setActive(null)
        setMembers([])
        setSources([])
        setExtractJobs([])
        setPickedJobs(new Set())
        setPickedMembers(new Set())
      }
    } catch (e) {
      setError(formatError(e))
    } finally {
      setLoading(false)
    }
  }, [projectId, selectDataset])

  useEffect(() => {
    void reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 仅随项目切换
  }, [projectId])

  const create = async () => {
    if (!name.trim()) return
    setError(null)
    await run('create', async () => {
    try {
      const ds = await api<Dataset>(`/v1/projects/${projectId}/datasets`, {
        method: 'POST',
        body: JSON.stringify({
          name: name.trim(),
          enabledAnnotationTypes: ['rect'],
        }),
      })
      setName('')
      setDatasets((prev) => [ds, ...prev])
      await selectDataset(ds.id)
      setMessage(`已创建数据集 ${ds.name}`)
    } catch (e) {
      setError(formatError(e))
    }
    })
  }

  const importYoloZip = async (file: File) => {
    const dsName = importName.trim() || file.name.replace(/\.zip$/i, '') || 'imported'
    setError(null)
    setMessage(`正在导入 ${file.name}…`)
    await run('import', async () => {
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('datasetName', dsName)
      const imp = await api<{
        id: string
        dataset_id: string | null
        status: string
        error_message: string | null
        stats: Record<string, unknown>
      }>(`/v1/projects/${projectId}/dataset-imports`, {
        method: 'POST',
        body: fd,
      })
      let row = imp
      for (let i = 0; i < 120; i++) {
        row = await api<typeof imp>(`/v1/dataset-imports/${imp.id}`)
        if (row.status === 'succeeded' || row.status === 'failed') break
        setMessage(`导入进行中… ${row.status}`)
        await new Promise((r) => setTimeout(r, 500))
      }
      if (row.status !== 'succeeded') {
        throw new Error(row.error_message || '导入失败或超时')
      }
      const n = (row.stats?.images as number | undefined) ?? null
      const reused = (row.stats?.reused as number | undefined) ?? 0
      setImportName('')
      await reload()
      if (row.dataset_id) await selectDataset(row.dataset_id)
      setMessage(
        `导入完成${n != null ? `：${n} 张` : ''}` +
          (reused ? `（复用 ${reused}）` : '') +
          ` · 数据集 ${dsName}`,
      )
    } catch (e) {
      setError(formatError(e))
      setMessage(null)
    }
    })
  }

  const toggleJob = (id: string) => {
    setPickedJobs((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const addFromExtractJobs = async () => {
    if (!active || pickedJobs.size === 0) return
    setError(null)
    await run('add-extract', async () => {
    try {
      const before = members.length
      const jobIds = [...pickedJobs]
      for (const jobId of jobIds) {
        await api<DatasetAsset[]>(
          `/v1/datasets/${active.id}/assets/from-extract`,
          {
            method: 'POST',
            body: JSON.stringify({
              extract_job_id: jobId,
              split: 'unassigned',
            }),
          },
        )
      }
      const mem = await selectDataset(active.id)
      const delta = Math.max(0, mem.length - before)
      setMessage(
        delta > 0
          ? `已从 ${jobIds.length} 个抽帧任务新加入 ${delta} 张帧`
          : `所选 ${jobIds.length} 个任务无新帧可加（可能已全部在集中或已删光）`,
      )
    } catch (e) {
      setError(formatError(e))
    }
    })
  }

  const loadLibraryImages = useCallback(async (folderId: string) => {
    if (!folderId) {
      setLibraryImages([])
      setPicked(new Set())
      return
    }
    const page = await api<{ items: Asset[] }>(
      `/v1/folders/${folderId}/assets?media_kind=image&limit=200&offset=0`,
    )
    setLibraryImages(page.items)
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
    setError(null)
    await run('rename', async () => {
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
    }
    })
  }

  const toggleMember = (assetId: string) => {
    setPickedMembers((prev) => {
      const next = new Set(prev)
      if (next.has(assetId)) next.delete(assetId)
      else next.add(assetId)
      return next
    })
  }

  const toggleAllMembers = () => {
    if (pickedMembers.size === members.length) {
      setPickedMembers(new Set())
      return
    }
    setPickedMembers(new Set(members.map((m) => m.asset_id)))
  }

  const removeSelectedMembers = async () => {
    if (!active || pickedMembers.size === 0) return
    const n = pickedMembers.size
    const ok = await appConfirm({
      title: '批量移出成员',
      description: `从数据集移出已选 ${n} 张？不会删除素材库或抽帧文件。`,
      confirmLabel: '移出',
      danger: true,
    })
    if (!ok) return
    setError(null)
    await run('remove-members', async () => {
    try {
      for (const assetId of pickedMembers) {
        await api(`/v1/datasets/${active.id}/assets/${assetId}`, {
          method: 'DELETE',
        })
      }
      await selectDataset(active.id)
      setMessage(`已移出 ${n} 张`)
    } catch (e) {
      setError(formatError(e))
    }
    })
  }

  const addFromLibrary = async () => {
    if (!active) return
    if (picked.size === 0) {
      setError('请先勾选素材库中的图片')
      return
    }
    setError(null)
    await run('add-library', async () => {
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
    }
    })
  }

  if (loading) return <LoadingBlock />

  return (
    <div>
      <div className="lt-page-head">
        <div>
          <h1>数据集</h1>
          <p>
            图片/视频在素材库上传与抽帧审查；也可导入已有 YOLO zip；本页勾选抽帧任务或库内图片入集 →
            标注 → 发版。
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
            onKeyDown={(e) => e.key === 'Enter' && void create()}
          />
          <button
            type="button"
            className="lt-btn lt-btn-primary"
            disabled={is('create') || !name.trim()}
            onClick={() => void create()}
          >
            创建
          </button>
        </div>
        <div
          style={{
            display: 'flex',
            gap: 8,
            flexWrap: 'wrap',
            alignItems: 'center',
            marginTop: 12,
            paddingTop: 12,
            borderTop: '1px solid var(--lt-border)',
          }}
        >
          <span style={{ fontSize: 13, color: 'var(--lt-fg-muted)' }}>
            导入 YOLO zip
          </span>
          <input
            className="lt-input"
            placeholder="新建数据集名（可空，默认用文件名）"
            value={importName}
            onChange={(e) => setImportName(e.target.value)}
            style={{ maxWidth: 260 }}
          />
          <label className="lt-btn" style={{ cursor: is('import') ? 'not-allowed' : 'pointer' }}>
            {is('import') ? '处理中…' : '选择 zip'}
            <input
              type="file"
              accept=".zip,application/zip"
              disabled={is('import')}
              style={{ display: 'none' }}
              onChange={(e) => {
                const f = e.target.files?.[0]
                e.target.value = ''
                if (f) void importYoloZip(f)
              }}
            />
          </label>
          <span style={{ fontSize: 12, color: 'var(--lt-fg-subtle)' }}>
            需含 data.yaml + train|val|test/images|labels；仅负责人；导入图不进素材库目录
          </span>
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
                      类别：
                      {active.classes.map((c) => c.name).join(', ') || '（无）'} ·
                      工具：
                      {active.enabled_annotation_types.join(', ')}
                    </p>
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                    <button
                      type="button"
                      className="lt-btn"
                      disabled={is('rename')}
                      onClick={() => void renameDataset()}
                    >
                      重命名
                    </button>
                    <Link to="/library" className="lt-btn">
                      去素材库
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
                <h3 style={{ margin: '0 0 0.5rem', fontSize: '0.95rem' }}>类别</h3>
                <p
                  style={{
                    margin: '0 0 0.75rem',
                    fontSize: 13,
                    color: 'var(--lt-fg-muted)',
                  }}
                >
                  默认全部启用。勾选只表示本数据集用不用这个类别，没有编号。仍被本集标注引用的类别不能取消。编号在发版时才生成。
                </p>
                {projectClasses.length === 0 ? (
                  <p style={{ margin: 0, fontSize: 13 }}>
                    项目还没有类别。请先到 YOLO类别页创建。
                  </p>
                ) : (
                  <div style={{ display: 'grid', gap: 6 }}>
                    {projectClasses.map((cls) => {
                      const checked = enabledIds.includes(cls.id)
                      return (
                        <label
                          key={cls.id}
                          style={{
                            display: 'flex',
                            gap: 8,
                            alignItems: 'center',
                            cursor: is('classes') ? 'default' : 'pointer',
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={is('classes')}
                            onChange={() => {
                              const next = checked
                                ? enabledIds.filter((id) => id !== cls.id)
                                : [...enabledIds, cls.id]
                              void saveEnabledClasses(next)
                            }}
                          />
                          <span
                            style={{
                              width: 14,
                              height: 14,
                              borderRadius: 3,
                              background: cls.color || '#0f766e',
                            }}
                          />
                          <span>{cls.name}</span>
                        </label>
                      )
                    })}
                    <div>
                      <Link to="/classes" className="lt-btn">
                        去 YOLO类别
                      </Link>
                    </div>
                  </div>
                )}
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
                  <div>
                    <h3 style={{ margin: 0, fontSize: '0.95rem' }}>
                      从抽帧任务加入
                    </h3>
                    <p
                      style={{
                        margin: '0.25rem 0 0',
                        color: 'var(--lt-fg-muted)',
                        fontSize: 13,
                      }}
                    >
                      多视频各自审查后，在此勾选任务，将剩余帧批量入集（不进素材库目录列表）。
                    </p>
                  </div>
                  <button
                    type="button"
                    className="lt-btn lt-btn-primary"
                    disabled={is('add-extract') || pickedJobs.size === 0}
                    onClick={() => void addFromExtractJobs()}
                  >
                    加入所选任务（{pickedJobs.size}）
                  </button>
                </div>
                {extractJobs.length === 0 ? (
                  <StateBlock
                    title="暂无成功的抽帧任务"
                    description="请先在素材库对视频抽帧并审查，再回到此处勾选任务入集。"
                  />
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {extractJobs.map((j) => {
                      const on = pickedJobs.has(j.id)
                      const inDs = j.in_dataset_count ?? 0
                      const remain = j.remaining_frame_count
                      const allIn = remain > 0 && inDs >= remain
                      return (
                        <label
                          key={j.id}
                          style={{
                            display: 'flex',
                            gap: 10,
                            alignItems: 'center',
                            padding: '0.55rem 0.65rem',
                            borderRadius: 'var(--lt-radius)',
                            border: `1px solid ${on ? 'var(--lt-accent)' : 'var(--lt-border)'}`,
                            background: on ? 'var(--lt-accent-soft)' : 'transparent',
                            cursor: remain === 0 ? 'not-allowed' : 'pointer',
                            opacity: remain === 0 ? 0.55 : 1,
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={on}
                            disabled={remain === 0}
                            onChange={() => toggleJob(j.id)}
                          />
                          <AuthVideoThumb assetId={j.video_asset_id} width={64} height={40} />
                          <span style={{ flex: 1, minWidth: 0 }}>
                            <div
                              style={{
                                fontWeight: 600,
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                              }}
                              title={j.video_filename || j.video_asset_id}
                            >
                              {j.video_filename || '未命名视频'}
                            </div>
                            <div
                              className="mono"
                              style={{ fontSize: 11, color: 'var(--lt-fg-subtle)' }}
                            >
                              {j.mode === 'stride_frames' && j.stride != null
                                ? `每 ${j.stride} 帧`
                                : j.mode}
                              {` · 剩余 ${remain} 帧`}
                              {j.in_dataset_count != null
                                ? ` · 已在本集 ${inDs}`
                                : ''}
                              {allIn ? ' · 已全部在集' : ''}
                            </div>
                          </span>
                        </label>
                      )
                    })}
                  </div>
                )}
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
                  <h3 style={{ margin: 0, fontSize: '0.95rem' }}>从素材库加入图片</h3>
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
                          disabled={is('add-library') || picked.size === 0}
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
                  <StateBlock
                    title="尚无成员"
                    description="勾选上方抽帧任务加入剩余帧，或从素材库勾选上传图片。"
                  />
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
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    gap: 12,
                    flexWrap: 'wrap',
                    alignItems: 'center',
                    marginBottom: '0.35rem',
                  }}
                >
                  <h3 style={{ margin: 0, fontSize: '0.95rem' }}>
                    成员（{members.length}）
                    {pickedMembers.size > 0
                      ? ` · 已选 ${pickedMembers.size}`
                      : ''}
                  </h3>
                  {members.length > 0 ? (
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      <button
                        type="button"
                        className="lt-btn"
                        onClick={toggleAllMembers}
                      >
                        {pickedMembers.size === members.length
                          ? '取消全选'
                          : '全选'}
                      </button>
                      <button
                        type="button"
                        className="lt-btn lt-btn-danger"
                        disabled={is('remove-members') || pickedMembers.size === 0}
                        onClick={() => void removeSelectedMembers()}
                      >
                        移出所选（{pickedMembers.size}）
                      </button>
                      {pickedMembers.size === 1 ? (
                        <Link
                          to={`/annotate?dataset=${active.id}&asset=${[...pickedMembers][0]}`}
                          className="lt-btn"
                        >
                          标注所选
                        </Link>
                      ) : (
                        <Link
                          to={`/annotate?dataset=${active.id}`}
                          className="lt-btn"
                        >
                          打开标注台
                        </Link>
                      )}
                    </div>
                  ) : null}
                </div>
                <p
                  style={{
                    margin: '0 0 0.75rem',
                    color: 'var(--lt-fg-muted)',
                    fontSize: 13,
                  }}
                >
                  点击缩略图多选后批量移出（只删引用）。划分在发版时指定。
                </p>
                {members.length === 0 ? (
                  <StateBlock
                    title="空数据集"
                    description="勾选抽帧任务加入剩余帧，或从素材库勾选上传图片。"
                  />
                ) : (
                  <div className="lt-thumb-grid">
                    {members.map((m) => {
                      const on = pickedMembers.has(m.asset_id)
                      return (
                        <button
                          key={m.asset_id}
                          type="button"
                          className={`lt-thumb${on ? ' selected' : ''}`}
                          title={m.filename}
                          onClick={() => toggleMember(m.asset_id)}
                        >
                          <AuthImage assetId={m.asset_id} alt={m.filename} />
                          <div className="lt-thumb-meta">{m.filename}</div>
                        </button>
                      )
                    })}
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
