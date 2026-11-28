import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import type {
  Asset,
  AssetsPage,
  Dataset,
  ExtractJob,
  Folder,
  FrameCandidate,
  Tag,
} from '../lib/types'
import { useAppStore } from '../store/appStore'
import { formatError } from '../hooks/useAsync'
import { useActionPending } from '../hooks/useActionPending'
import { AuthImage } from '../components/AuthImage'
import { AuthVideo } from '../components/AuthVideo'
import { AuthVideoThumb } from '../components/AuthVideoThumb'
import { LoadingBlock, StateBlock } from '../components/StateBlock'
import { RequireProject } from '../components/RequireProject'
import { appConfirm, appPrompt } from '../store/dialogStore'
import { appToast } from '../store/toastStore'
import {
  getStoredBrowseKind,
  getStoredExtractJobId,
  getStoredFolderId,
  getStoredLibraryVideo,
  setStoredBrowseKind,
  setStoredExtractJobId,
  setStoredFolder,
  setStoredLibraryVideo,
} from '../lib/workspaceStorage'

const PAGE_SIZE = 60

type BrowseKind = 'video' | 'image'

function LibraryInner() {
  const projectId = useAppStore((s) => s.projectId)!
  const [trail, setTrail] = useState<Folder[]>([])
  const [childFolders, setChildFolders] = useState<Folder[]>([])
  const [folder, setFolder] = useState<Folder | null>(null)
  const [browseKind, setBrowseKind] = useState<BrowseKind>(getStoredBrowseKind())
  const [assets, setAssets] = useState<Asset[]>([])
  const [total, setTotal] = useState(0)
  const [videoCount, setVideoCount] = useState(0)
  const [imageCount, setImageCount] = useState(0)
  const [page, setPage] = useState(0)
  const [selectedVideo, setSelectedVideo] = useState<Asset | null>(null)
  const [selectedImage, setSelectedImage] = useState<Asset | null>(null)
  const [videoJobs, setVideoJobs] = useState<ExtractJob[]>([])
  const [extractJob, setExtractJob] = useState<ExtractJob | null>(null)
  const [frames, setFrames] = useState<FrameCandidate[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [stride, setStride] = useState(30)
  const [newFolderName, setNewFolderName] = useState('')
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [projectTags, setProjectTags] = useState<Tag[]>([])
  const [targetDatasetId, setTargetDatasetId] = useState('')
  const [loading, setLoading] = useState(true)
  const { is, run } = useActionPending()
  const [uploadProgress, setUploadProgress] = useState<{
    index: number
    total: number
    name: string
  } | null>(null)
  const [assetMenu, setAssetMenu] = useState<{
    x: number
    y: number
    asset: Asset
  } | null>(null)
  const [folderMenu, setFolderMenu] = useState<{
    x: number
    y: number
    folder: Folder
  } | null>(null)
  const [tagEditor, setTagEditor] = useState<{
    asset: Asset
    picked: Set<string>
  } | null>(null)

  const currentParentId = folder?.id ?? null
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const loadChildren = useCallback(
    async (parentId: string | null) => {
      const q = parentId ? `?parent_id=${parentId}` : ''
      return api<Folder[]>(`/v1/projects/${projectId}/folders${q}`)
    },
    [projectId],
  )

  const loadAssetsPage = useCallback(
    async (folderId: string, kind: BrowseKind, pageIndex: number) => {
      const offset = pageIndex * PAGE_SIZE
      const other: BrowseKind = kind === 'video' ? 'image' : 'video'
      const [data, otherPage] = await Promise.all([
        api<AssetsPage>(
          `/v1/folders/${folderId}/assets?media_kind=${kind}&limit=${PAGE_SIZE}&offset=${offset}`,
        ),
        api<AssetsPage>(
          `/v1/folders/${folderId}/assets?media_kind=${other}&limit=1&offset=0`,
        ),
      ])
      setAssets(data.items)
      setTotal(data.total)
      setPage(pageIndex)
      if (kind === 'video') {
        setVideoCount(data.total)
        setImageCount(otherPage.total)
      } else {
        setImageCount(data.total)
        setVideoCount(otherPage.total)
      }
    },
    [],
  )

  const loadVideoJobs = useCallback(async (videoId: string) => {
    const jobs = await api<ExtractJob[]>(`/v1/assets/${videoId}/extract-jobs`)
    setVideoJobs(jobs)
    return jobs
  }, [])

  const openExtractJob = useCallback(async (job: ExtractJob, videoId?: string) => {
    if (job.project_id && job.project_id !== projectId) {
      setStoredExtractJobId(null, { projectId, videoId })
      setExtractJob(null)
      setFrames([])
      return
    }
    setExtractJob(job)
    setStoredExtractJobId(job.id, {
      projectId,
      videoId: videoId || selectedVideo?.id || undefined,
    })
    setSelected(new Set())
    if (job.status === 'succeeded') {
      const fr = await api<FrameCandidate[]>(`/v1/extract-jobs/${job.id}/frames`)
      setFrames(fr)
    } else {
      setFrames([])
    }
  }, [projectId, selectedVideo?.id])

  const selectVideo = useCallback(
    async (video: Asset) => {
      if (video.project_id && video.project_id !== projectId) {
        appToast.error('该素材不属于当前项目')
        return
      }
      setSelectedVideo(video)
      setSelectedImage(null)
      setFrames([])
      setSelected(new Set())
      const prevVideo = getStoredLibraryVideo()
      const savedJobId =
        prevVideo && (prevVideo.id === video.id || !prevVideo.id)
          ? prevVideo.extractJobId
          : null
      setStoredLibraryVideo(
        {
          id: video.id,
          name: video.filename,
          extractJobId: savedJobId,
        },
        { projectId },
      )
      try {
        const jobs = await loadVideoJobs(video.id)
        const preferred =
          (savedJobId &&
            jobs.find(
              (j) =>
                j.id === savedJobId &&
                (!j.project_id || j.project_id === projectId),
            )) ||
          jobs[0] ||
          null
        if (preferred) await openExtractJob(preferred, video.id)
        else {
          setStoredExtractJobId(null, { projectId, videoId: video.id })
          setExtractJob(null)
          setVideoJobs(jobs)
        }
      } catch (e) {
        appToast.error(formatError(e))
      }
    },
    [loadVideoJobs, openExtractJob, projectId],
  )

  const enterFolder = useCallback(
    async (
      next: Folder | null,
      nextTrail: Folder[],
      opts?: { restoreVideo?: boolean },
    ) => {
      if (next && next.project_id !== projectId) {
        setStoredFolder(null, { projectId })
        appToast.error('该目录不属于当前项目')
        return
      }
      setFolder(next)
      setTrail(nextTrail)
      setVideoCount(0)
      setImageCount(0)
      setSelectedVideo(null)
      setSelectedImage(null)
      setAssets([])
      setTotal(0)
      setPage(0)
      setExtractJob(null)
      setFrames([])
      setVideoJobs([])
      if (next) {
        setStoredFolder({ id: next.id, name: next.name }, { projectId })
        const [kids] = await Promise.all([
          loadChildren(next.id),
          loadAssetsPage(next.id, browseKind, 0),
        ])
        setChildFolders(kids)
        if (opts?.restoreVideo) {
          const hint = getStoredLibraryVideo()
          if (hint?.id) {
            try {
              const video = await api<Asset>(`/v1/assets/${hint.id}`)
              if (
                video.project_id === projectId &&
                video.folder_id === next.id &&
                video.media_kind === 'video'
              ) {
                await selectVideo(video)
                return
              }
            } catch {
              /* 失效则清空 */
            }
            setStoredLibraryVideo(null, { projectId })
          }
        }
      } else {
        setStoredFolder(null, { projectId })
        setChildFolders(await loadChildren(null))
      }
    },
    [browseKind, loadAssetsPage, loadChildren, projectId, selectVideo],
  )

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        const roots = await loadChildren(null)
        if (cancelled) return
        setChildFolders(roots)
        setFolder(null)
        setTrail([])
        setAssets([])

        try {
          const [dsList, tagList] = await Promise.all([
            api<Dataset[]>(`/v1/projects/${projectId}/datasets`),
            api<Tag[]>(`/v1/projects/${projectId}/tags`),
          ])
          if (!cancelled) {
            setDatasets(dsList)
            setProjectTags(tagList)
            setTargetDatasetId((prev) =>
              prev && dsList.some((d) => d.id === prev)
                ? prev
                : dsList[0]?.id || '',
            )
          }
        } catch {
          /* 数据集/标签列表失败不阻塞素材库 */
        }

        const savedId = getStoredFolderId()
        if (savedId) {
          try {
            const f = await api<Folder>(`/v1/folders/${savedId}`)
            if (!cancelled && f.project_id === projectId) {
              await enterFolder(f, [f], { restoreVideo: true })
            } else {
              setStoredFolder(null, { projectId })
            }
          } catch {
            setStoredFolder(null, { projectId })
          }
        }
      } catch (e) {
        if (!cancelled) appToast.error(formatError(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  const switchBrowseKind = async (kind: BrowseKind) => {
    setBrowseKind(kind)
    setStoredBrowseKind(kind, { projectId })
    if (kind === browseKind || !folder) return
    setSelectedVideo(null)
    setSelectedImage(null)
    setExtractJob(null)
    setFrames([])
    setVideoJobs([])
    if (kind !== 'video') setStoredLibraryVideo(null, { projectId })
    await run('assets', async () => {
      try {
        await loadAssetsPage(folder.id, kind, 0)
      } catch (e) {
        appToast.error(formatError(e))
      }
    })
  }

  const goPage = async (nextPage: number) => {
    if (!folder || nextPage < 0 || nextPage >= pageCount) return
    await run('assets', async () => {
      try {
        await loadAssetsPage(folder.id, browseKind, nextPage)
      } catch (e) {
        appToast.error(formatError(e))
      }
    })
  }

  const createFolder = async () => {
    const name = newFolderName.trim()
    if (!name) return
    await run('create-folder', async () => {
    try {
      const created = await api<Folder>(`/v1/projects/${projectId}/folders`, {
        method: 'POST',
        body: JSON.stringify({
          name,
          parent_id: currentParentId,
        }),
      })
      setNewFolderName('')
      appToast.success(`已创建目录：${created.path}`)
      await enterFolder(created, [...trail, created])
    } catch (e) {
      appToast.error(formatError(e))
    }
    })
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
    await run('rename-folder', async () => {
    try {
      const updated = await api<Folder>(`/v1/folders/${target.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ name }),
      })
      appToast.success(`已重命名目录：${updated.path}`)
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
      appToast.error(formatError(e))
    }
    })
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
    await run(`rename-asset:${asset.id}`, async () => {
    try {
      const updated = await api<Asset>(`/v1/assets/${asset.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ filename }),
      })
      if (folder) await loadAssetsPage(folder.id, browseKind, page)
      if (selectedVideo?.id === updated.id) setSelectedVideo(updated)
      if (selectedImage?.id === updated.id) setSelectedImage(updated)
      appToast.success(`已重命名：${updated.filename}`)
    } catch (e) {
      appToast.error(formatError(e))
    }
    })
  }

  const openTagEditor = async (asset: Asset) => {
    try {
      const [tagList, current] = await Promise.all([
        projectTags.length
          ? Promise.resolve(projectTags)
          : api<Tag[]>(`/v1/projects/${projectId}/tags`),
        api<Tag[]>(`/v1/assets/${asset.id}/tags`),
      ])
      setProjectTags(tagList)
      setTagEditor({
        asset,
        picked: new Set(current.map((t) => t.id)),
      })
    } catch (e) {
      appToast.error(formatError(e))
    }
  }

  const saveAssetTags = async () => {
    if (!tagEditor) return
    const { asset, picked } = tagEditor
    await run(`tags:${asset.id}`, async () => {
      try {
        await api(`/v1/assets/${asset.id}/tags`, {
          method: 'PUT',
          body: JSON.stringify({ tag_ids: [...picked] }),
        })
        setTagEditor(null)
        appToast.success(`已更新「${asset.filename}」的标签`)
      } catch (e) {
        appToast.error(formatError(e))
      }
    })
  }

  const deleteAsset = async (asset: Asset) => {
    const ok = await appConfirm({
      title: '删除素材',
      description: `删除「${asset.filename}」？文件会被移除。若仍被数据集或版本引用，删除会被拒绝。`,
      confirmLabel: '删除',
      danger: true,
    })
    if (!ok) return
    await run(`delete-asset:${asset.id}`, async () => {
    try {
      await api(`/v1/assets/${asset.id}`, { method: 'DELETE' })
      if (selectedVideo?.id === asset.id) {
        setSelectedVideo(null)
        setExtractJob(null)
        setFrames([])
        setVideoJobs([])
        setStoredLibraryVideo(null, { projectId })
      }
      if (selectedImage?.id === asset.id) setSelectedImage(null)
      if (folder) await loadAssetsPage(folder.id, browseKind, page)
      appToast.success(`已删除：${asset.filename}`)
    } catch (e) {
      appToast.error(formatError(e))
    }
    })
  }

  useEffect(() => {
    if (!assetMenu && !folderMenu) return
    const close = () => {
      setAssetMenu(null)
      setFolderMenu(null)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
    }
    window.addEventListener('click', close)
    window.addEventListener('scroll', close, true)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('click', close)
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('keydown', onKey)
    }
  }, [assetMenu, folderMenu])

  const upload = async (files: FileList | File[]) => {
    if (!folder) {
      appToast.error('请先创建或选择一个目录，再上传')
      return
    }
    const list = Array.from(files)
    if (list.length === 0) return
    setUploadProgress({ index: 0, total: list.length, name: list[0].name })
    await run('upload', async () => {
    try {
      let lastVideo: Asset | null = null
      let nImg = 0
      let nVid = 0
      for (let i = 0; i < list.length; i++) {
        const file = list[i]
        setUploadProgress({
          index: i + 1,
          total: list.length,
          name: file.name,
        })
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
      const prefer: BrowseKind =
        nVid > 0 && nImg === 0
          ? 'video'
          : nImg > 0 && nVid === 0
            ? 'image'
            : browseKind
      setBrowseKind(prefer)
      setStoredBrowseKind(prefer, { projectId })
      await loadAssetsPage(folder.id, prefer, 0)
      if (lastVideo) {
        setBrowseKind('video')
        setStoredBrowseKind('video', { projectId })
        await loadAssetsPage(folder.id, 'video', 0)
        await selectVideo(lastVideo)
      }
      const parts: string[] = []
      if (nImg) parts.push(`${nImg} 张图片`)
      if (nVid) parts.push(`${nVid} 个视频`)
      appToast.success(`已上传 ${parts.join('、')}`)
    } catch (e) {
      appToast.error(formatError(e))
    } finally {
      setUploadProgress(null)
    }
    })
  }

  const startExtract = async () => {
    if (!selectedVideo) return
    appToast.info('抽帧任务已提交…', { id: 'extract', duration: 0 })
    setFrames([])
    setSelected(new Set())
    await run('extract', async () => {
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
      setStoredExtractJobId(job.id, {
        projectId,
        videoId: selectedVideo.id,
      })
      await pollExtract(job.id)
      await loadVideoJobs(selectedVideo.id)
    } catch (e) {
      appToast.error(formatError(e), { id: 'extract' })
    }
    })
  }

  const pollExtract = async (id: string) => {
    for (let i = 0; i < 120; i++) {
      const job = await api<ExtractJob>(`/v1/extract-jobs/${id}`)
      setExtractJob(job)
      if (job.status === 'succeeded') {
        const fr = await api<FrameCandidate[]>(`/v1/extract-jobs/${id}/frames`)
        setFrames(fr)
        const videoId = selectedVideo?.id
        if (videoId) {
          setAssets((prev) =>
            prev.map((a) =>
              a.id === videoId ? { ...a, extracted: true } : a,
            ),
          )
          setSelectedVideo((cur) =>
            cur && cur.id === videoId ? { ...cur, extracted: true } : cur,
          )
        }
        appToast.success(
          `抽帧完成，共 ${fr.length} 帧（按时间升序；不进入目录列表）`,
          { id: 'extract' },
        )
        return
      }
      if (job.status === 'failed') {
        appToast.error(job.error_message || '抽帧失败', { id: 'extract' })
        return
      }
      appToast.info(`抽帧进行中… ${job.status}`, { id: 'extract', duration: 0 })
      await new Promise((r) => setTimeout(r, 800))
    }
    appToast.error('抽帧超时，请稍后刷新查看', { id: 'extract' })
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
    await run('discard', async () => {
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
      appToast.success(`已删除 ${n} 帧，剩余 ${fr.length}`)
    } catch (e) {
      appToast.error(formatError(e))
    }
    })
  }

  const addCurrentJobToDataset = async () => {
    if (!extractJob || !targetDatasetId || frames.length === 0) return
    await run('add-frames', async () => {
    try {
      const added = await api<{ asset_id: string }[]>(
        `/v1/datasets/${targetDatasetId}/assets/from-extract`,
        {
          method: 'POST',
          body: JSON.stringify({
            extract_job_id: extractJob.id,
            split: 'unassigned',
          }),
        },
      )
      const dsName =
        datasets.find((d) => d.id === targetDatasetId)?.name || '数据集'
      appToast.success(`已将当前任务 ${added.length} 帧加入「${dsName}」`)
    } catch (e) {
      appToast.error(formatError(e))
    }
    })
  }

  if (loading) return <LoadingBlock />

  return (
    <div>
      <div className="lt-page-head">
        <div>
          <h1>素材库</h1>
          <p>
            目录归档源素材（视频 / 上传图，分页浏览）。抽帧图只在所选视频的任务下审查，不进目录列表。
          </p>
        </div>
        <label
          className="lt-btn lt-btn-primary"
          style={{
            cursor: folder && !uploadProgress ? 'pointer' : 'not-allowed',
            opacity: folder && !uploadProgress ? 1 : 0.65,
            pointerEvents: uploadProgress ? 'none' : undefined,
          }}
          title={
            uploadProgress
              ? `正在上传 ${uploadProgress.name}`
              : folder
                ? '上传到当前目录'
                : '请先选择目录'
          }
        >
          {uploadProgress
            ? `上传中 ${uploadProgress.index}/${uploadProgress.total}…`
            : '上传到当前目录'}
          <input
            type="file"
            accept="video/*,image/*"
            multiple
            hidden
            disabled={!folder || uploadProgress != null}
            onChange={(e) => {
              if (e.target.files?.length) void upload(e.target.files)
              e.target.value = ''
            }}
          />
        </label>
      </div>

      {uploadProgress ? (
        <p style={{ color: 'var(--lt-fg-muted)', marginTop: 0 }}>
          正在上传 {uploadProgress.index}/{uploadProgress.total} ·{' '}
          {uploadProgress.name}
        </p>
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
        <nav
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 4,
            alignItems: 'center',
          }}
        >
          <button
            type="button"
            className="lt-btn lt-btn-ghost"
            onClick={() => void enterFolder(null, [])}
          >
            根目录
          </button>
          {trail.map((f, i) => (
            <span
              key={f.id}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
            >
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
          disabled={is('create-folder') || !newFolderName.trim()}
          onClick={() => void createFolder()}
        >
          新建目录
        </button>
        {folder ? (
          <button
            type="button"
            className="lt-btn"
            disabled={is('rename-folder')}
            onClick={() => void renameFolder(folder)}
          >
            重命名当前目录
          </button>
        ) : null}
      </div>

      <div className="lt-library-layout">
        <section className="lt-panel lt-library-dirs">
          <h2 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>子目录</h2>
          {childFolders.length === 0 ? (
            <StateBlock
              title={folder ? '无子目录' : '还没有目录'}
              description={
                folder
                  ? '可在上方新建子目录，或直接上传到当前目录。'
                  : '按规格须先创建目录，再上传素材。'
              }
            />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {childFolders.map((f) => (
                <div
                  key={f.id}
                  onContextMenu={(e) => {
                    e.preventDefault()
                    setAssetMenu(null)
                    setFolderMenu({
                      folder: f,
                      x: Math.max(
                        8,
                        Math.min(e.clientX, window.innerWidth - 148 - 8),
                      ),
                      y: Math.max(
                        8,
                        Math.min(e.clientY, window.innerHeight - 44 - 8),
                      ),
                    })
                  }}
                >
                  <button
                    type="button"
                    className="lt-btn"
                    title={f.path}
                    style={{
                      width: '100%',
                      justifyContent: 'flex-start',
                      height: 'auto',
                      padding: '0.55rem 0.65rem',
                      minWidth: 0,
                    }}
                    onClick={() => void enterFolder(f, [...trail, f])}
                  >
                    <span style={{ textAlign: 'left', minWidth: 0, width: '100%' }}>
                      <div
                        style={{
                          fontWeight: 600,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {f.name}
                      </div>
                      <div
                        className="mono"
                        style={{
                          fontSize: 11,
                          color: 'var(--lt-fg-subtle)',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        视频 {f.video_count ?? 0} · 图片 {f.image_count ?? 0}
                      </div>
                    </span>
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="lt-panel lt-library-browse">
          {!folder ? (
            <StateBlock
              title="请选择目录"
              description="点左侧子目录或上方面包屑进入后，即可分页浏览视频与上传图片。"
            />
          ) : (
            <>
              <div
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: 8,
                  alignItems: 'center',
                  marginBottom: '0.75rem',
                }}
              >
                <div className="lt-seg">
                  <button
                    type="button"
                    className={
                      browseKind === 'video' ? 'lt-seg-item active' : 'lt-seg-item'
                    }
                    onClick={() => void switchBrowseKind('video')}
                  >
                    视频 {videoCount}
                  </button>
                  <button
                    type="button"
                    className={
                      browseKind === 'image' ? 'lt-seg-item active' : 'lt-seg-item'
                    }
                    onClick={() => void switchBrowseKind('image')}
                  >
                    上传图片 {imageCount}
                  </button>
                </div>
                <span
                  className="mono"
                  style={{ fontSize: 12, color: 'var(--lt-fg-subtle)' }}
                >
                  第 {page + 1}/{pageCount} 页
                </span>
                <span style={{ flex: 1 }} />
                <button
                  type="button"
                  className="lt-btn"
                  disabled={is('assets') || page <= 0}
                  onClick={() => void goPage(page - 1)}
                >
                  上一页
                </button>
                <button
                  type="button"
                  className="lt-btn"
                  disabled={is('assets') || page + 1 >= pageCount}
                  onClick={() => void goPage(page + 1)}
                >
                  下一页
                </button>
              </div>

              {assets.length === 0 ? (
                <StateBlock
                  title={browseKind === 'video' ? '暂无视频' : '暂无上传图片'}
                  description={
                    browseKind === 'video'
                      ? '上传 mp4 / mov 等到当前目录。抽帧产生的图不会出现在这里。'
                      : '上传图片到当前目录；抽帧帧请在右侧视频任务中查看。'
                  }
                />
              ) : (
                <div className="lt-media-grid">
                  {assets.map((a) => {
                    const isActive =
                      (a.media_kind === 'video' && selectedVideo?.id === a.id) ||
                      (a.media_kind === 'image' && selectedImage?.id === a.id)
                    return (
                      <div
                        key={a.id}
                        className={`lt-media-card${isActive ? ' selected' : ''}`}
                        onContextMenu={(e) => {
                          e.preventDefault()
                          const menuW = 148
                          const menuH = 108
                          setFolderMenu(null)
                          setAssetMenu({
                            asset: a,
                            x: Math.max(
                              8,
                              Math.min(e.clientX, window.innerWidth - menuW - 8),
                            ),
                            y: Math.max(
                              8,
                              Math.min(e.clientY, window.innerHeight - menuH - 8),
                            ),
                          })
                        }}
                      >
                        <button
                          type="button"
                          className="lt-media-card-main"
                          title={a.filename}
                          onClick={() => {
                            if (a.media_kind === 'video') void selectVideo(a)
                            else {
                              setSelectedImage(a)
                              setSelectedVideo(null)
                              setExtractJob(null)
                              setFrames([])
                              setVideoJobs([])
                              setStoredLibraryVideo(null, { projectId })
                            }
                          }}
                        >
                          <div className="lt-media-card-thumb">
                            {a.media_kind === 'video' ? (
                              <AuthVideoThumb
                                assetId={a.id}
                                className="lt-media-card-thumb-fill"
                              />
                            ) : (
                              <AuthImage assetId={a.id} alt={a.filename} />
                            )}
                            {a.media_kind === 'video' && a.extracted ? (
                              <span className="lt-media-card-flag">已抽帧</span>
                            ) : null}
                          </div>
                          <div className="lt-media-card-meta">
                            <div className="lt-media-card-name">{a.filename}</div>
                            <div className="mono lt-media-card-sub">
                              {a.media_kind === 'video'
                                ? a.duration_ms != null
                                  ? `${(a.duration_ms / 1000).toFixed(1)}s`
                                  : '视频'
                                : a.width && a.height
                                  ? `${a.width}×${a.height}`
                                  : '图片'}
                              {a.media_kind === 'video' && a.fps != null
                                ? ` · ${a.fps.toFixed(1)} fps`
                                : ''}
                              {a.media_kind === 'video' && a.extracted
                                ? ' · 已抽帧'
                                : ''}
                            </div>
                          </div>
                        </button>
                      </div>
                    )
                  })}
                </div>
              )}
            </>
          )}
        </section>

        <section className="lt-panel lt-library-detail">
          {selectedVideo ? (
            <div className="lt-library-detail-stack">
              <div>
                <div
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    marginBottom: 6,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                  title={selectedVideo.filename}
                >
                  预览 · {selectedVideo.filename}
                </div>
                <AuthVideo assetId={selectedVideo.id} maxHeight={220} />
              </div>

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
                disabled={is('extract')}
                onClick={() => void startExtract()}
              >
                开始抽帧
              </button>

              {videoJobs.length > 0 ? (
                <div>
                  <div
                    style={{
                      fontSize: 12,
                      color: 'var(--lt-fg-muted)',
                      marginBottom: 6,
                    }}
                  >
                    该视频的抽帧任务
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {videoJobs.map((j) => (
                      <button
                        key={j.id}
                        type="button"
                        className="lt-btn"
                        style={{
                          justifyContent: 'flex-start',
                          height: 'auto',
                          padding: '0.4rem 0.55rem',
                          background:
                            extractJob?.id === j.id
                              ? 'var(--lt-accent-soft)'
                              : undefined,
                        }}
                        onClick={() => void openExtractJob(j)}
                      >
                        <span style={{ textAlign: 'left', fontSize: 12 }}>
                          <div className="mono">{j.id.slice(0, 8)}…</div>
                          <div style={{ color: 'var(--lt-fg-subtle)' }}>
                            {j.status}
                            {j.mode === 'stride_frames' && j.stride != null
                              ? ` · 每 ${j.stride} 帧`
                              : ''}
                          </div>
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}

              <div
                style={{
                  borderTop: '1px solid var(--lt-border)',
                  paddingTop: '0.75rem',
                  marginTop: '0.25rem',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: 8,
                    flexWrap: 'wrap',
                    marginBottom: 8,
                  }}
                >
                  <div>
                    <h2 style={{ margin: 0, fontSize: '0.95rem' }}>
                      候选帧审查
                    </h2>
                    <p
                      style={{
                        margin: '0.2rem 0 0',
                        color: 'var(--lt-fg-muted)',
                        fontSize: 12,
                      }}
                    >
                      {extractJob
                        ? `任务 ${extractJob.status} · 已选 ${selected.size} / ${frames.length}`
                        : '抽帧后在此按时间审查（不进左侧目录）'}
                    </p>
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      className="lt-btn lt-btn-danger"
                      disabled={is('discard') || selected.size === 0}
                      onClick={() => void discardSelected()}
                    >
                      删除所选
                    </button>
                    <Link to="/datasets" className="lt-btn">
                      多任务入集
                    </Link>
                  </div>
                </div>
                {frames.length > 0 && extractJob?.status === 'succeeded' ? (
                  <div
                    style={{
                      display: 'flex',
                      flexWrap: 'wrap',
                      gap: 8,
                      alignItems: 'center',
                      marginBottom: 8,
                    }}
                  >
                    {datasets.length === 0 ? (
                      <Link to="/datasets" className="lt-btn lt-btn-primary">
                        先创建数据集再入集
                      </Link>
                    ) : (
                      <>
                        <select
                          className="lt-select"
                          value={targetDatasetId}
                          onChange={(e) => setTargetDatasetId(e.target.value)}
                          style={{ maxWidth: 180 }}
                        >
                          {datasets.map((d) => (
                            <option key={d.id} value={d.id}>
                              {d.name}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          className="lt-btn lt-btn-primary"
                          disabled={is('add-frames') || !targetDatasetId}
                          onClick={() => void addCurrentJobToDataset()}
                        >
                          将当前任务剩余帧入集
                        </button>
                      </>
                    )}
                  </div>
                ) : null}
                {frames.length === 0 ? (
                  <StateBlock
                    title="暂无候选帧"
                    description="对该视频抽帧或选择已有任务后，帧按时间升序展示。"
                  />
                ) : (
                  <div className="lt-thumb-grid lt-thumb-grid-compact">
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
              </div>
            </div>
          ) : selectedImage ? (
            <div>
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  marginBottom: 6,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
                title={selectedImage.filename}
              >
                预览 · {selectedImage.filename}
              </div>
              <div
                style={{
                  borderRadius: 8,
                  overflow: 'hidden',
                  background: 'var(--lt-bg-canvas)',
                  maxHeight: 360,
                }}
              >
                <AuthImage assetId={selectedImage.id} alt={selectedImage.filename} />
              </div>
              <p
                style={{
                  marginTop: 10,
                  fontSize: 13,
                  color: 'var(--lt-fg-muted)',
                }}
              >
                上传图片可在数据集页从库勾选加入。抽帧图请选视频后在任务中查看。
              </p>
            </div>
          ) : (
            <StateBlock
              title="选择素材"
              description="在中间网格点选视频以预览并抽帧；点选上传图片可预览。抽帧结果只出现在本栏，不会混进目录封面。"
            />
          )}
        </section>
      </div>
      {assetMenu ? (
        <div
          className="lt-context-menu"
          style={{ left: assetMenu.x, top: assetMenu.y }}
          onContextMenu={(e) => e.preventDefault()}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            onClick={() => {
              const asset = assetMenu.asset
              setAssetMenu(null)
              void renameAsset(asset)
            }}
          >
            重命名
          </button>
          <button
            type="button"
            onClick={() => {
              const asset = assetMenu.asset
              setAssetMenu(null)
              void openTagEditor(asset)
            }}
          >
            打标签
          </button>
          <button
            type="button"
            className="danger"
            onClick={() => {
              const asset = assetMenu.asset
              setAssetMenu(null)
              void deleteAsset(asset)
            }}
          >
            删除
          </button>
        </div>
      ) : null}
      {tagEditor ? (
        <div
          className="lt-panel"
          style={{
            position: 'fixed',
            left: '50%',
            top: '20%',
            transform: 'translateX(-50%)',
            zIndex: 40,
            padding: '1rem',
            minWidth: 280,
            maxWidth: '90vw',
            boxShadow: '0 8px 28px rgba(0,0,0,0.18)',
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <h3 style={{ margin: '0 0 0.5rem', fontSize: '0.95rem' }}>
            打标签 · {tagEditor.asset.filename}
          </h3>
          {projectTags.length === 0 ? (
            <p style={{ margin: '0 0 0.75rem', fontSize: 13 }}>
              还没有标签。请先到{' '}
              <Link to="/tags">标签</Link> 页创建。
            </p>
          ) : (
            <div style={{ display: 'grid', gap: 6, marginBottom: 12 }}>
              {projectTags.map((t) => {
                const on = tagEditor.picked.has(t.id)
                return (
                  <label
                    key={t.id}
                    style={{
                      display: 'inline-flex',
                      gap: 6,
                      alignItems: 'center',
                      cursor: 'pointer',
                      fontSize: 13,
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={on}
                      onChange={() =>
                        setTagEditor((prev) => {
                          if (!prev) return prev
                          const next = new Set(prev.picked)
                          if (on) next.delete(t.id)
                          else next.add(t.id)
                          return { ...prev, picked: next }
                        })
                      }
                    />
                    {t.name}
                  </label>
                )
              })}
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button
              type="button"
              className="lt-btn"
              onClick={() => setTagEditor(null)}
            >
              取消
            </button>
            <button
              type="button"
              className="lt-btn lt-btn-primary"
              disabled={is(`tags:${tagEditor.asset.id}`) || projectTags.length === 0}
              onClick={() => void saveAssetTags()}
            >
              保存
            </button>
          </div>
        </div>
      ) : null}
      {folderMenu ? (
        <div
          className="lt-context-menu"
          style={{ left: folderMenu.x, top: folderMenu.y }}
          onContextMenu={(e) => e.preventDefault()}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            onClick={() => {
              const target = folderMenu.folder
              setFolderMenu(null)
              void renameFolder(target)
            }}
          >
            重命名
          </button>
        </div>
      ) : null}
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
