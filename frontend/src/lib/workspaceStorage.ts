/**
 * 当前项目工作区上下文（单一 JSON），按领域归属嵌套（可达 3～4 层）。
 * localStorage 只作「上次选中」提示；打开页面必须用 API 校验归属，不符则清空。
 *
 * 归属树：
 *   Project
 *   ├── library（素材库浏览面）
 *   │     └── folder → Project
 *   │           └── video → Project（folder_id 约束）
 *   │                 └── extractJobId → video
 *   └── dataset → Project
 *         ├── assetId（标注上次成员）
 *         └── versionId → Dataset
 *
 * labeltrace.project = {
 *   id, name,
 *   library: {
 *     browseKind: 'video' | 'image',
 *     folder: {
 *       id, name,
 *       video: { id, name, extractJobId } | null
 *     } | null
 *   },
 *   dataset: { id, name, assetId, versionId } | null
 * }
 *
 * 非项目域：
 *   labeltrace.session = { token, user: { id, username } }
 *   labeltrace.theme          ← 设备 UI 偏好，独立
 */

const PROJECT_KEY = 'labeltrace.project'

const LEGACY_FLAT = {
  projectId: 'labeltrace.projectId',
  projectName: 'labeltrace.projectName',
  datasetId: 'labeltrace.datasetId',
  folderId: 'labeltrace.folderId',
  extractJobId: 'labeltrace.lastExtractJobId',
} as const

export type WorkspaceNamedRef = {
  id: string
  name: string
}

export type WorkspaceLibraryVideo = {
  id: string
  name: string
  extractJobId: string | null
}

export type WorkspaceLibraryFolder = {
  id: string
  name: string
  video: WorkspaceLibraryVideo | null
}

export type WorkspaceLibrary = {
  browseKind: 'video' | 'image'
  folder: WorkspaceLibraryFolder | null
}

export type WorkspaceDataset = {
  id: string
  name: string
  /** 标注页上次成员；URL ?asset= 优先 */
  assetId: string | null
  /** 只读浏览版本；URL ?version= 优先 */
  versionId: string | null
}

export type WorkspaceProject = {
  id: string
  name: string
  library: WorkspaceLibrary
  dataset: WorkspaceDataset | null
}

function emptyLibrary(): WorkspaceLibrary {
  return { browseKind: 'video', folder: null }
}

function emptyProject(id: string, name: string): WorkspaceProject {
  return {
    id,
    name,
    library: emptyLibrary(),
    dataset: null,
  }
}

function asLibraryVideo(v: unknown): WorkspaceLibraryVideo | null {
  if (!v || typeof v !== 'object') return null
  const o = v as { id?: unknown; name?: unknown; extractJobId?: unknown }
  if (typeof o.id !== 'string' || !o.id) return null
  return {
    id: o.id,
    name: typeof o.name === 'string' ? o.name : '',
    extractJobId:
      typeof o.extractJobId === 'string' && o.extractJobId
        ? o.extractJobId
        : null,
  }
}

function asLibraryFolder(v: unknown): WorkspaceLibraryFolder | null {
  if (!v || typeof v !== 'object') return null
  const o = v as { id?: unknown; name?: unknown; video?: unknown }
  if (typeof o.id !== 'string' || !o.id) return null
  return {
    id: o.id,
    name: typeof o.name === 'string' ? o.name : '',
    video: asLibraryVideo(o.video),
  }
}

function asDataset(v: unknown): WorkspaceDataset | null {
  if (!v || typeof v !== 'object') return null
  const o = v as {
    id?: unknown
    name?: unknown
    assetId?: unknown
    versionId?: unknown
  }
  if (typeof o.id !== 'string' || !o.id) return null
  return {
    id: o.id,
    name: typeof o.name === 'string' ? o.name : '',
    assetId: typeof o.assetId === 'string' && o.assetId ? o.assetId : null,
    versionId:
      typeof o.versionId === 'string' && o.versionId ? o.versionId : null,
  }
}

function asBrowseKind(v: unknown): 'video' | 'image' {
  return v === 'image' ? 'image' : 'video'
}

/** 兼容：v2 library.folder + library.video 并列；v1 folderId/extractJobId 根级 */
function normalizeFromAny(raw: unknown): WorkspaceProject | null {
  if (!raw || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  if (typeof o.id !== 'string' || !o.id) return null
  const name = typeof o.name === 'string' ? o.name : ''

  let library: WorkspaceLibrary = emptyLibrary()

  if (o.library && typeof o.library === 'object') {
    const lib = o.library as Record<string, unknown>
    library.browseKind = asBrowseKind(lib.browseKind)

    const nestedFolder = asLibraryFolder(lib.folder)
    if (nestedFolder) {
      library.folder = nestedFolder
    } else if (lib.folder && typeof lib.folder === 'object') {
      // v2：folder 与 video 并列
      const f = lib.folder as { id?: unknown; name?: unknown }
      if (typeof f.id === 'string' && f.id) {
        const video =
          asLibraryVideo(lib.video) ||
          // 仅有 extractJobId、无 video id 的迁移残留：丢弃（无法挂到 folder.video）
          null
        library.folder = {
          id: f.id,
          name: typeof f.name === 'string' ? f.name : '',
          video,
        }
      }
    }
  } else {
    const folderId = typeof o.folderId === 'string' ? o.folderId : null
    if (folderId) {
      library.folder = {
        id: folderId,
        name: '',
        video: null,
      }
    }
  }

  const dataset = asDataset(o.dataset)

  return { id: o.id, name, library, dataset }
}

function migrateLegacyFlat(): WorkspaceProject | null {
  const id = localStorage.getItem(LEGACY_FLAT.projectId)
  if (!id) {
    for (const k of Object.values(LEGACY_FLAT)) localStorage.removeItem(k)
    return null
  }
  const name = localStorage.getItem(LEGACY_FLAT.projectName) || ''
  const datasetId = localStorage.getItem(LEGACY_FLAT.datasetId)
  const folderId = localStorage.getItem(LEGACY_FLAT.folderId)
  const next: WorkspaceProject = {
    id,
    name,
    library: {
      browseKind: 'video',
      folder: folderId
        ? { id: folderId, name: '', video: null }
        : null,
    },
    dataset: datasetId
      ? { id: datasetId, name: '', assetId: null, versionId: null }
      : null,
  }
  // 旧 extractJobId 无 video 无法可靠挂靠，丢弃（进目录选视频后会重新写入）
  void localStorage.getItem(LEGACY_FLAT.extractJobId)
  localStorage.setItem(PROJECT_KEY, JSON.stringify(next))
  for (const k of Object.values(LEGACY_FLAT)) localStorage.removeItem(k)
  return next
}

export function readWorkspaceProject(): WorkspaceProject | null {
  const raw = localStorage.getItem(PROJECT_KEY)
  if (raw) {
    try {
      const normalized = normalizeFromAny(JSON.parse(raw))
      if (normalized) {
        localStorage.setItem(PROJECT_KEY, JSON.stringify(normalized))
        return normalized
      }
    } catch {
      /* fall through */
    }
  }
  return migrateLegacyFlat()
}

export function writeWorkspaceProject(p: WorkspaceProject | null): void {
  if (!p) {
    localStorage.removeItem(PROJECT_KEY)
    return
  }
  localStorage.setItem(PROJECT_KEY, JSON.stringify(p))
}

function update(mutator: (p: WorkspaceProject) => WorkspaceProject): void {
  const cur = readWorkspaceProject()
  if (!cur) return
  writeWorkspaceProject(mutator(cur))
}

function assertProject(projectId?: string | null): WorkspaceProject | null {
  const cur = readWorkspaceProject()
  if (!cur) return null
  if (projectId && cur.id !== projectId) return null
  return cur
}

export function setWorkspaceProject(
  id: string | null,
  name: string | null = null,
): void {
  if (!id) {
    writeWorkspaceProject(null)
    return
  }
  const prev = readWorkspaceProject()
  if (prev && prev.id === id) {
    writeWorkspaceProject({
      ...prev,
      name: name ?? prev.name,
    })
    return
  }
  writeWorkspaceProject(emptyProject(id, name || ''))
}

export function clearWorkspaceProject(): void {
  writeWorkspaceProject(null)
  for (const k of Object.values(LEGACY_FLAT)) localStorage.removeItem(k)
}

/* ── dataset → Project ──────────────────────────────── */

export function getStoredDataset(): WorkspaceDataset | null {
  return readWorkspaceProject()?.dataset ?? null
}

export function getStoredDatasetId(): string | null {
  return getStoredDataset()?.id ?? null
}

export function setStoredDataset(
  dataset: { id: string; name: string } | null,
  *,
  projectId?: string | null,
  keepChildren?: boolean,
): void {
  if (!assertProject(projectId)) return
  update((p) => {
    if (!dataset) return { ...p, dataset: null }
    const same = p.dataset?.id === dataset.id
    return {
      ...p,
      dataset: {
        id: dataset.id,
        name: dataset.name,
        assetId: same || keepChildren ? p.dataset?.assetId ?? null : null,
        versionId: same || keepChildren ? p.dataset?.versionId ?? null : null,
      },
    }
  })
}

export function getStoredDatasetAssetId(): string | null {
  return getStoredDataset()?.assetId ?? null
}

export function setStoredDatasetAssetId(
  assetId: string | null,
  *,
  projectId?: string | null,
  datasetId?: string | null,
): void {
  if (!assertProject(projectId)) return
  update((p) => {
    if (!p.dataset) return p
    if (datasetId && p.dataset.id !== datasetId) return p
    return { ...p, dataset: { ...p.dataset, assetId } }
  })
}

export function getStoredDatasetVersionId(): string | null {
  return getStoredDataset()?.versionId ?? null
}

export function setStoredDatasetVersionId(
  versionId: string | null,
  *,
  projectId?: string | null,
  datasetId?: string | null,
): void {
  if (!assertProject(projectId)) return
  update((p) => {
    if (!p.dataset) return p
    if (datasetId && p.dataset.id !== datasetId) return p
    return { ...p, dataset: { ...p.dataset, versionId } }
  })
}

/* ── library.folder → Project ───────────────────────── */

export function getStoredFolder(): WorkspaceLibraryFolder | null {
  return readWorkspaceProject()?.library.folder ?? null
}

export function getStoredFolderId(): string | null {
  return getStoredFolder()?.id ?? null
}

/** 换目录时整棵 folder 子树（含 video/extract）替换 */
export function setStoredFolder(
  folder: { id: string; name: string } | null,
  *,
  projectId?: string | null,
): void {
  if (!assertProject(projectId)) return
  update((p) => {
    if (!folder) {
      return { ...p, library: { ...p.library, folder: null } }
    }
    const same = p.library.folder?.id === folder.id
    return {
      ...p,
      library: {
        ...p.library,
        folder: {
          id: folder.id,
          name: folder.name,
          video: same ? p.library.folder?.video ?? null : null,
        },
      },
    }
  })
}

/** @deprecated 用 setStoredFolder */
export function setStoredFolderId(
  folderId: string | null,
  opts: { projectId?: string | null } = {},
): void {
  setStoredFolder(folderId ? { id: folderId, name: '' } : null, opts)
}

/* ── library.folder.video → folder ──────────────────── */

export function getStoredLibraryVideo(): WorkspaceLibraryVideo | null {
  return getStoredFolder()?.video ?? null
}

export function getStoredExtractJobId(): string | null {
  return getStoredLibraryVideo()?.extractJobId ?? null
}

export function setStoredLibraryVideo(
  video: { id: string; name?: string; extractJobId?: string | null } | null,
  *,
  projectId?: string | null,
): void {
  if (!assertProject(projectId)) return
  update((p) => {
    const folder = p.library.folder
    if (!folder) return p
    if (!video) {
      return {
        ...p,
        library: {
          ...p.library,
          folder: { ...folder, video: null },
        },
      }
    }
    const same = folder.video?.id === video.id
    return {
      ...p,
      library: {
        ...p.library,
        folder: {
          ...folder,
          video: {
            id: video.id,
            name: video.name ?? (same ? folder.video?.name ?? '' : ''),
            extractJobId:
              video.extractJobId !== undefined
                ? video.extractJobId
                : same
                  ? folder.video?.extractJobId ?? null
                  : null,
          },
        },
      },
    }
  })
}

export function setStoredExtractJobId(
  extractJobId: string | null,
  *,
  projectId?: string | null,
  videoId?: string | null,
): void {
  if (!assertProject(projectId)) return
  update((p) => {
    const folder = p.library.folder
    if (!folder) return p
    const vid = folder.video
    if (!vid) {
      if (!extractJobId || !videoId) return p
      return {
        ...p,
        library: {
          ...p.library,
          folder: {
            ...folder,
            video: { id: videoId, name: '', extractJobId },
          },
        },
      }
    }
    if (videoId && vid.id !== videoId) return p
    return {
      ...p,
      library: {
        ...p.library,
        folder: {
          ...folder,
          video: { ...vid, extractJobId },
        },
      },
    }
  })
}

export function getStoredBrowseKind(): 'video' | 'image' {
  return readWorkspaceProject()?.library.browseKind ?? 'video'
}

export function setStoredBrowseKind(
  browseKind: 'video' | 'image',
  *,
  projectId?: string | null,
): void {
  if (!assertProject(projectId)) return
  update((p) => ({
    ...p,
    library: { ...p.library, browseKind },
  }))
}

export function clearProjectScopedStorage(): void {
  const cur = readWorkspaceProject()
  if (!cur) {
    clearWorkspaceProject()
    return
  }
  writeWorkspaceProject({
    ...cur,
    library: emptyLibrary(),
    dataset: null,
  })
}
