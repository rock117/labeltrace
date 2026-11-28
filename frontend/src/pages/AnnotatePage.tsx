import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, getToken } from '../lib/api'
import type {
  Annotation,
  Asset,
  AssetLineage,
  Dataset,
  DatasetAsset,
  DatasetClass,
  ProjectMember,
  Version,
  VersionManifest,
  VersionManifestEntry,
} from '../lib/types'
import {
  parseAnnotationItems,
  shapeSummary,
  shapesKey,
  type AnnotationShape,
} from '../lib/annotationShapes'
import {
  resolveToolbarTools,
  toolHint,
  type AnnotationToolType,
} from '../annotation/toolRegistry'
import { AnnotatorCanvas, classColorCss } from '../annotation/AnnotatorCanvas'
import { formatError } from '../hooks/useAsync'
import { AuthImage } from '../components/AuthImage'
import { LoadingBlock, StateBlock } from '../components/StateBlock'
import { RequireProject } from '../components/RequireProject'
import { useAppStore } from '../store/appStore'
import { appConfirm } from '../store/dialogStore'
import {
  getStoredDatasetAssetId,
  getStoredDatasetId,
  setStoredDataset,
  setStoredDatasetAssetId,
  setStoredDatasetVersionId,
} from '../lib/workspaceStorage'

type MemberFilter = 'all' | 'none' | 'draft' | 'submitted'
type MemberAnnStatus = 'submitted' | 'draft' | 'none'

function normalizeClasses(raw: unknown): DatasetClass[] {
  if (!Array.isArray(raw)) return []
  return raw
    .map((item, i) => {
      if (typeof item === 'string') {
        return { id: `legacy-${i}`, name: item, idx: i, color: null }
      }
      if (item && typeof item === 'object') {
        const o = item as Record<string, unknown>
        const id = typeof o.id === 'string' ? o.id : `legacy-${i}`
        const name = typeof o.name === 'string' ? o.name : `class${i}`
        return {
          id,
          name,
          idx: typeof o.idx === 'number' ? o.idx : i,
          color: typeof o.color === 'string' ? o.color : null,
        }
      }
      return null
    })
    .filter((c): c is DatasetClass => c != null)
}

function statusLabel(s: MemberAnnStatus, pending = false): string {
  if (s === 'submitted') return '已提交'
  if (s === 'draft') return pending ? '编辑中' : '草稿'
  return '未标注'
}

function AnnotateInner() {
  const projectId = useAppStore((s) => s.projectId)
  const me = useAppStore((s) => s.user)
  const [params, setParams] = useSearchParams()
  const versionParam = params.get('version')
  const datasetParam =
    params.get('dataset') ||
    (!versionParam ? getStoredDatasetId() : null)
  /** URL 优先；无 ?asset 时用 dataset.assetId 恢复 */
  const assetParam =
    params.get('asset') ||
    (!versionParam ? getStoredDatasetAssetId() : null)
  const readOnly = Boolean(versionParam)

  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [version, setVersion] = useState<Version | null>(null)
  const [snapshotEntries, setSnapshotEntries] = useState<VersionManifestEntry[]>(
    [],
  )
  const [members, setMembers] = useState<DatasetAsset[]>([])
  const [index, setIndex] = useState(0)
  const [asset, setAsset] = useState<Asset | null>(null)
  const [lineage, setLineage] = useState<AssetLineage | null>(null)
  const [shapes, setShapes] = useState<AnnotationShape[]>([])
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [activeClassId, setActiveClassId] = useState<string | null>(null)
  const [activeTool, setActiveTool] = useState<AnnotationToolType>('rect')
  const [selectedShape, setSelectedShape] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [applying, setApplying] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [memberFilter, setMemberFilter] = useState<MemberFilter>('all')
  const [isOwner, setIsOwner] = useState(false)
  /** owner 可切全部；annotator 后端强制 mine */
  const [memberScope, setMemberScope] = useState<'mine' | 'all'>('all')
  const stripRef = useRef<HTMLDivElement>(null)
  const baselineKeyRef = useRef('')
  const shapesRef = useRef<AnnotationShape[]>([])
  const dirtyRef = useRef(false)
  const selectedShapeRef = useRef<number | null>(null)
  const datasetRef = useRef<Dataset | null>(null)
  const assetRef = useRef<Asset | null>(null)
  const readOnlyRef = useRef(readOnly)

  useEffect(() => {
    shapesRef.current = shapes
  }, [shapes])
  useEffect(() => {
    dirtyRef.current = dirty
  }, [dirty])
  useEffect(() => {
    selectedShapeRef.current = selectedShape
  }, [selectedShape])
  useEffect(() => {
    datasetRef.current = dataset
  }, [dataset])
  useEffect(() => {
    assetRef.current = asset
  }, [asset])
  useEffect(() => {
    readOnlyRef.current = readOnly
  }, [readOnly])

  const markShapes = useCallback((next: AnnotationShape[]) => {
    setShapes(next)
    const dirtyNext = shapesKey(next) !== baselineKeyRef.current
    setDirty(dirtyNext)
    dirtyRef.current = dirtyNext
  }, [])

  const toggleClassification = useCallback(
    (classId: string) => {
      if (readOnly || activeTool !== 'classification') {
        setActiveClassId(classId)
        return
      }
      setActiveClassId(classId)
      const cur = shapesRef.current
      const idx = cur.findIndex(
        (s) => s.type === 'classification' && s.classId === classId,
      )
      if (idx >= 0) {
        markShapes(cur.filter((_, i) => i !== idx))
      } else {
        markShapes([...cur, { type: 'classification', classId }])
      }
    },
    [readOnly, activeTool, markShapes],
  )

  const applyVersionToWorkspace = async () => {
    if (!versionParam || !version) return
    const ok = await appConfirm({
      title: '应用到工作区',
      description:
        `将版本「${version.name}」合并应用到工作区？\n` +
        `· 同图：覆盖工作区标注（变为草稿）\n` +
        `· 快照多出的图：加入工作区\n` +
        `· 工作区多出的图：保留\n` +
        `不会修改该版本快照本身。`,
      confirmLabel: '应用',
    })
    if (!ok) return
    setApplying(true)
    setError(null)
    try {
      const r = await api<{
        added: number
        overwritten: number
        skipped: number
        dataset_id: string
      }>(`/v1/versions/${versionParam}/apply-to-workspace`, { method: 'POST' })
      setStoredDataset({ id: r.dataset_id, name: '' }, { projectId })
      setStoredDatasetVersionId(null, {
        projectId,
        datasetId: r.dataset_id,
      })
      setMessage(
        `已应用到工作区：新增 ${r.added} · 覆盖 ${r.overwritten}` +
          (r.skipped ? ` · 跳过 ${r.skipped}` : '') +
          '，可点「打开工作区」继续编辑',
      )
    } catch (e) {
      setError(formatError(e))
    } finally {
      setApplying(false)
    }
  }

  const enabledTypes = useMemo(() => {
    if (readOnly && version) {
      return (version.enabled_annotation_types as string[]) ?? ['rect']
    }
    return dataset?.enabled_annotation_types ?? ['rect']
  }, [readOnly, version, dataset])

  const tools = useMemo(
    () => resolveToolbarTools(enabledTypes),
    [enabledTypes],
  )

  const classes: DatasetClass[] = useMemo(() => {
    if (readOnly && version) return normalizeClasses(version.classes)
    return normalizeClasses(dataset?.classes)
  }, [readOnly, version, dataset])

  useEffect(() => {
    if (!classes.length) {
      setActiveClassId(null)
      return
    }
    setActiveClassId((prev) =>
      prev && classes.some((c) => c.id === prev) ? prev : classes[0].id,
    )
  }, [classes])

  const titleName = readOnly
    ? version?.name ?? '版本'
    : dataset?.name ?? '数据集'

  const memberStatusAt = useCallback(
    (i: number): MemberAnnStatus => {
      if (readOnly) {
        const s = snapshotEntries[i]?.annotationStatus
        if (s === 'submitted') return 'submitted'
        if (s === 'draft') return 'draft'
        // 快照里有框也视为已有标注，不进「未标注」
        const items = snapshotEntries[i]?.shapes?.items
        if (items && items.length > 0) return 'draft'
        return 'none'
      }
      // 当前图：画布上已有框或正在编辑 → 绝不能算「未标注」（列表状态可能滞后）
      if (i === index && (dirty || shapes.length > 0)) {
        const s = members[i]?.annotation_status
        if (s === 'submitted') return 'submitted'
        return 'draft'
      }
      const s = members[i]?.annotation_status
      if (s === 'submitted') return 'submitted'
      if (s === 'draft') return 'draft'
      return 'none'
    },
    [members, readOnly, snapshotEntries, dirty, index, shapes.length],
  )

  const progress = useMemo(() => {
    const total = members.length
    let submitted = 0
    let draft = 0
    for (let i = 0; i < total; i++) {
      const s = memberStatusAt(i)
      if (s === 'submitted') submitted += 1
      else if (s === 'draft') draft += 1
    }
    return {
      total,
      submitted,
      draft,
      unlabeled: Math.max(0, total - submitted - draft),
    }
  }, [members.length, memberStatusAt])

  const filteredMemberIndices = useMemo(() => {
    return members
      .map((_, i) => i)
      .filter((i) => {
        const s = memberStatusAt(i)
        if (memberFilter === 'all') return true
        const matches =
          (memberFilter === 'none' && s === 'none') ||
          (memberFilter === 'draft' && s === 'draft') ||
          (memberFilter === 'submitted' && s === 'submitted')
        // 仅「编辑中」的当前图临时留在筛选结果里，避免一画框就从「未标」消失；
        // 一旦已提交/不再匹配，就不再塞进未标注等分组
        if (i === index && dirty && !readOnly && !matches) return true
        return matches
      })
  }, [members, memberFilter, memberStatusAt, index, dirty, readOnly])

  useEffect(() => {
    if (tools.length === 0) return
    if (!tools.some((t) => t.type === activeTool)) {
      setActiveTool(tools[0].type)
    }
  }, [tools, activeTool])

  const loadContent = useCallback(async (assetId: string) => {
    const token = getToken()
    const headers: HeadersInit = {}
    if (token) headers.Authorization = `Bearer ${token}`
    const res = await fetch(`/api/v1/assets/${assetId}/content`, { headers })
    if (!res.ok) throw new Error('无法加载图片')
    const blob = await res.blob()
    setImageUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev)
      return URL.createObjectURL(blob)
    })
  }, [])

  const showMember = useCallback(
    async (opts: {
      dsId: string | null
      verId: string | null
      mem: DatasetAsset[]
      entries: VersionManifestEntry[]
      idx: number
    }) => {
      const { dsId, verId, mem, entries, idx } = opts
      if (mem.length === 0) {
        setAsset(null)
        setShapes([])
        setLineage(null)
        setImageUrl(null)
        baselineKeyRef.current = ''
        setDirty(false)
        dirtyRef.current = false
        return
      }
      const safe = Math.max(0, Math.min(idx, mem.length - 1))
      setIndex(safe)
      const member = mem[safe]
      const nextParams: Record<string, string> = { asset: member.asset_id }
      if (verId) nextParams.version = verId
      if (dsId) nextParams.dataset = dsId
      setParams(nextParams, { replace: true })
      if (dsId && projectId) {
        setStoredDatasetAssetId(member.asset_id, {
          projectId,
          datasetId: dsId,
        })
        setStoredDatasetVersionId(verId, { projectId, datasetId: dsId })
      }

      if (verId) {
        const entry = entries[safe]
        const [a, lin] = await Promise.all([
          api<Asset>(`/v1/assets/${member.asset_id}`),
          api<AssetLineage>(`/v1/assets/${member.asset_id}/lineage`),
        ])
        const loaded = parseAnnotationItems(entry?.shapes?.items)
        setAsset(a)
        setLineage(lin)
        setShapes(loaded)
        shapesRef.current = loaded
        baselineKeyRef.current = shapesKey(loaded)
        setSelectedShape(null)
        setDirty(false)
        dirtyRef.current = false
        await loadContent(member.asset_id)
        return
      }

      if (!dsId) return
      const [a, ann, lin] = await Promise.all([
        api<Asset>(`/v1/assets/${member.asset_id}`),
        api<Annotation>(
          `/v1/datasets/${dsId}/assets/${member.asset_id}/annotation`,
        ),
        api<AssetLineage>(`/v1/assets/${member.asset_id}/lineage`),
      ])
      const loaded = parseAnnotationItems(ann.shapes?.items)
      // 与库中真实标注对齐：列表状态可能滞后；有记录/有框时同步到 members
      const syncedStatus: 'draft' | 'submitted' | null =
        ann.updated_at != null || loaded.length > 0
          ? ann.status === 'submitted'
            ? 'submitted'
            : 'draft'
          : null
      setMembers((prev) =>
        prev.map((m) =>
          m.asset_id === member.asset_id
            ? { ...m, annotation_status: syncedStatus }
            : m,
        ),
      )
      setAsset(a)
      setLineage(lin)
      setShapes(loaded)
      shapesRef.current = loaded
      baselineKeyRef.current = shapesKey(loaded)
      setSelectedShape(null)
      setDirty(false)
      dirtyRef.current = false
      await loadContent(member.asset_id)
    },
    [setParams, loadContent, projectId],
  )

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      if (!versionParam && !datasetParam) {
        setLoading(false)
        return
      }
      setLoading(true)
      setError(null)
      try {
        if (versionParam) {
          const [ver, manifest] = await Promise.all([
            api<Version>(`/v1/versions/${versionParam}`),
            api<VersionManifest>(`/v1/versions/${versionParam}/manifest`),
          ])
          if (cancelled) return
          setVersion(ver)
          setDataset(null)
          const entries = manifest.entries ?? []
          setSnapshotEntries(entries)
          const mem: DatasetAsset[] = entries.map((e) => ({
            asset_id: e.assetId,
            split: e.split,
            media_kind: e.mediaKind,
            filename: e.filename,
          }))
          setMembers(mem)
          // 版本浏览：校验所属数据集是否在当前项目
          try {
            const dsOfVer = await api<Dataset>(
              `/v1/datasets/${ver.dataset_id}`,
            )
            if (projectId && dsOfVer.project_id !== projectId) {
              setStoredDataset(null, { projectId })
              setVersion(null)
              setMembers([])
              setParams({}, { replace: true })
              setError('该版本不属于当前项目')
              return
            }
            setStoredDataset(
              { id: dsOfVer.id, name: dsOfVer.name },
              { projectId },
            )
          } catch {
            setStoredDataset(
              { id: ver.dataset_id, name: '' },
              { projectId },
            )
          }
          let idx = 0
          if (assetParam) {
            const found = mem.findIndex((m) => m.asset_id === assetParam)
            if (found >= 0) idx = found
          }
          await showMember({
            dsId: ver.dataset_id,
            verId: versionParam,
            mem,
            entries,
            idx,
          })
        } else if (datasetParam) {
          setVersion(null)
          setSnapshotEntries([])
          const ds = await api<Dataset>(`/v1/datasets/${datasetParam}`)
          if (cancelled) return
          if (projectId && ds.project_id !== projectId) {
            setStoredDataset(null, { projectId })
            setDataset(null)
            setMembers([])
            setParams({}, { replace: true })
            setError('该数据集不属于当前项目，请从数据集页重新打开')
            return
          }
          let owner = false
          if (projectId && me?.id) {
            try {
              const roster = await api<ProjectMember[]>(
                `/v1/projects/${projectId}/members`,
              )
              if (cancelled) return
              owner = roster.some(
                (m) => m.user_id === me.id && m.roles.includes('owner'),
              )
              setIsOwner(owner)
            } catch {
              setIsOwner(false)
            }
          }
          const scopeMine = !owner || memberScope === 'mine'
          const mem = await api<DatasetAsset[]>(
            `/v1/datasets/${datasetParam}/assets${scopeMine ? '?mine=1' : ''}`,
          )
          if (cancelled) return
          setDataset(ds)
          setMembers(mem)
          setStoredDataset({ id: ds.id, name: ds.name }, { projectId })
          let idx = 0
          if (assetParam) {
            const found = mem.findIndex((m) => m.asset_id === assetParam)
            if (found >= 0) idx = found
          }
          await showMember({
            dsId: datasetParam,
            verId: null,
            mem,
            entries: [],
            idx,
          })
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
    // 仅随 dataset/version/项目/分配范围 切换重载；asset 翻页走 go()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetParam, versionParam, projectId, memberScope, me?.id])

  useEffect(() => {
    return () => {
      if (imageUrl) URL.revokeObjectURL(imageUrl)
    }
  }, [imageUrl])

  const save = async (
    status: 'draft' | 'submitted' = 'draft',
    opts?: { silent?: boolean; items?: AnnotationShape[] },
  ): Promise<boolean> => {
    if (readOnly || !dataset || !asset) return false
    const items = opts?.items ?? shapes
    setSaving(true)
    setError(null)
    try {
      await api(`/v1/datasets/${dataset.id}/assets/${asset.id}/annotation`, {
        method: 'PUT',
        body: JSON.stringify({
          shapes: { format: 'xyxy_abs', items },
          status,
        }),
      })
      baselineKeyRef.current = shapesKey(items)
      setDirty(false)
      dirtyRef.current = false
      const aid = asset.id
      setMembers((prev) =>
        prev.map((m) =>
          m.asset_id === aid ? { ...m, annotation_status: status } : m,
        ),
      )
      if (!opts?.silent) {
        setMessage(
          status === 'submitted'
            ? '已提交'
            : '已保存草稿',
        )
      } else if (status === 'submitted') {
        setMessage('已随切图提交')
      } else {
        setMessage('已自动保存草稿')
      }
      return true
    } catch (e) {
      setError(formatError(e))
      return false
    } finally {
      setSaving(false)
    }
  }

  /** 切图：有改动则提交（submitted），无需再点提交。 */
  const flushOnNavigate = async (): Promise<boolean> => {
    if (readOnly || !dirtyRef.current) return true
    if (!dataset || !asset) return true
    return save('submitted', { silent: true, items: shapesRef.current })
  }

  /** 关页/刷新：尽力提交未保存改动（与切图一致，免最后一张再点提交）。 */
  const flushSubmitKeepalive = () => {
    if (readOnlyRef.current || !dirtyRef.current) return
    const ds = datasetRef.current
    const a = assetRef.current
    if (!ds || !a) return
    const token = getToken()
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }
    if (token) headers.Authorization = `Bearer ${token}`
    void fetch(`/api/v1/datasets/${ds.id}/assets/${a.id}/annotation`, {
      method: 'PUT',
      headers,
      body: JSON.stringify({
        shapes: { format: 'xyxy_abs', items: shapesRef.current },
        status: 'submitted',
      }),
      keepalive: true,
    })
  }

  useEffect(() => {
    const onLeave = () => flushSubmitKeepalive()
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!dirtyRef.current || readOnlyRef.current) return
      flushSubmitKeepalive()
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('pagehide', onLeave)
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => {
      window.removeEventListener('pagehide', onLeave)
      window.removeEventListener('beforeunload', onBeforeUnload)
      // SPA 内跳转离开标注台时 beforeunload 不触发，卸载时补一次
      flushSubmitKeepalive()
    }
  }, [])

  const goTo = async (next: number) => {
    if (members.length === 0) return
    if (next < 0 || next >= members.length) return
    if (next === index && asset) return
    setLoading(true)
    try {
      const ok = await flushOnNavigate()
      if (!ok) return
      await showMember({
        dsId: dataset?.id ?? version?.dataset_id ?? null,
        verId: versionParam,
        mem: members,
        entries: snapshotEntries,
        idx: next,
      })
    } catch (e) {
      setError(formatError(e))
    } finally {
      setLoading(false)
    }
  }

  /** 在当前筛选结果内的位置；不在筛选中则为 -1 */
  const filterPos = useMemo(
    () => filteredMemberIndices.indexOf(index),
    [filteredMemberIndices, index],
  )
  const canGoPrevInFilter =
    filterPos > 0 ||
    (filterPos < 0 && filteredMemberIndices.some((i) => i < index))
  const canGoNextInFilter =
    (filterPos >= 0 && filterPos < filteredMemberIndices.length - 1) ||
    (filterPos < 0 && filteredMemberIndices.some((i) => i > index))

  /** 上一张/下一张：按当前筛选列表翻，不是全库顺序 */
  const go = async (delta: number) => {
    const list = filteredMemberIndices
    if (list.length === 0) return
    const pos = list.indexOf(index)
    if (pos >= 0) {
      const nextPos = pos + delta
      if (nextPos < 0 || nextPos >= list.length) return
      await goTo(list[nextPos])
      return
    }
    // 当前图不在筛选里（例如在「未标」下刚提交）：跳到筛选中相邻一张
    if (delta > 0) {
      const next = list.find((i) => i > index)
      if (next == null) return
      await goTo(next)
    } else {
      let prev: number | undefined
      for (let k = list.length - 1; k >= 0; k--) {
        if (list[k] < index) {
          prev = list[k]
          break
        }
      }
      if (prev == null) return
      await goTo(prev)
    }
  }

  const goNextUnlabeled = async () => {
    if (members.length === 0) return
    for (let i = index + 1; i < members.length; i++) {
      if (memberStatusAt(i) === 'none') {
        await goTo(i)
        return
      }
    }
    for (let i = 0; i < index; i++) {
      if (memberStatusAt(i) === 'none') {
        await goTo(i)
        return
      }
    }
    setMessage('没有未标注的图片了')
  }

  const submitAllDrafts = async () => {
    if (readOnly || !dataset) return
    const draftN = members.filter((m) => m.annotation_status === 'draft').length
    const dirtyCurrent = dirty
    if (draftN === 0 && !dirtyCurrent) {
      setMessage('没有可提交的草稿')
      return
    }
    const ok = await appConfirm({
      title: '提交全部草稿',
      description:
        `将把本数据集中所有草稿标注改为已提交` +
        (dirtyCurrent ? '（含当前未保存改动，先提交本张）' : '') +
        `。尚无标注记录的图片不会被创建空标注。`,
      confirmLabel: '全部提交',
    })
    if (!ok) return
    setSaving(true)
    setError(null)
    try {
      if (dirtyCurrent) {
        const saved = await save('submitted', {
          silent: true,
          items: shapesRef.current,
        })
        if (!saved) return
      }
      const r = await api<{
        updated: number
        already_submitted: number
        without_annotation: number
      }>(`/v1/datasets/${dataset.id}/annotations/submit-drafts`, {
        method: 'POST',
      })
      setMembers((prev) =>
        prev.map((m) =>
          m.annotation_status === 'draft'
            ? { ...m, annotation_status: 'submitted' }
            : m,
        ),
      )
      setMessage(
        r.updated > 0
          ? `已提交 ${r.updated} 张草稿` +
              (r.without_annotation
                ? `（另有 ${r.without_annotation} 张尚无标注）`
                : '')
          : r.without_annotation
            ? `没有草稿；尚有 ${r.without_annotation} 张未标注`
            : '没有需要提交的草稿',
      )
    } catch (e) {
      setError(formatError(e))
    } finally {
      setSaving(false)
    }
  }

  useEffect(() => {
    const strip = stripRef.current
    if (!strip) return
    const el = strip.querySelector<HTMLElement>(
      `[data-member-index="${index}"]`,
    )
    if (!el) return
    // 只用胶片条自身滚动；scrollIntoView 会连带滚动画布祖先，导致主图“飞出”视口
    const vertical = strip.scrollHeight > strip.clientHeight + 4
    if (vertical) {
      const top =
        el.offsetTop - (strip.clientHeight - el.clientHeight) / 2
      strip.scrollTo({ top: Math.max(0, top), behavior: 'smooth' })
    } else {
      const left =
        el.offsetLeft - (strip.clientWidth - el.clientWidth) / 2
      strip.scrollTo({ left: Math.max(0, left), behavior: 'smooth' })
    }
  }, [index])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return
      if (
        (e.key === 'a' || e.key === 'ArrowLeft') &&
        canGoPrevInFilter
      ) {
        void go(-1)
      }
      if (
        (e.key === 'd' || e.key === 'ArrowRight') &&
        canGoNextInFilter
      ) {
        void go(1)
      }
      if (readOnly) return
      const toolKey = e.key.length === 1 ? e.key.toLowerCase() : ''
      const toolMap: Record<string, AnnotationToolType> = {
        b: 'rect',
        p: 'polygon',
        w: 'mask',
        k: 'keypoint',
        o: 'obb',
        c: 'classification',
      }
      if (toolMap[toolKey] && tools.some((t) => t.type === toolMap[toolKey])) {
        setActiveTool(toolMap[toolKey])
        return
      }
      if (e.key >= '1' && e.key <= '9') {
        const cls = Number(e.key) - 1
        if (cls >= 0 && cls < classes.length) {
          const id = classes[cls].id
          if (activeTool === 'classification') toggleClassification(id)
          else setActiveClassId(id)
        }
      }
      if (e.key === 's' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault()
        void save('draft')
      }
      if (e.key === 'Backspace' || e.key === 'Delete') {
        const sel = selectedShapeRef.current
        if (sel != null) {
          markShapes(shapesRef.current.filter((_, i) => i !== sel))
          setSelectedShape(null)
        } else {
          markShapes(shapesRef.current.slice(0, -1))
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    dataset,
    version,
    members,
    index,
    asset,
    readOnly,
    classes,
    markShapes,
    canGoPrevInFilter,
    canGoNextInFilter,
    filteredMemberIndices,
  ])

  if (!versionParam && !datasetParam) {
    return (
      <StateBlock
        title="未选择数据集"
        description="请先在数据集页创建或打开一个数据集；或从版本页查看快照。"
        action={
          <Link to="/datasets" className="lt-btn lt-btn-primary">
            前往数据集
          </Link>
        }
      />
    )
  }

  if (loading && !asset) return <LoadingBlock label="加载标注台…" />

  if (error && !asset) {
    return <StateBlock tone="error" title="加载失败" description={error} />
  }

  if (members.length === 0) {
    return (
      <StateBlock
        title={
          readOnly
            ? '该版本没有成员'
            : memberScope === 'mine' || !isOwner
              ? '没有分给你的成员'
              : '数据集没有可标注成员'
        }
        description={
          readOnly
            ? '此快照为空。'
            : memberScope === 'mine' || !isOwner
              ? '请让负责人在数据集页把图片分配给你，或（负责人）切换到「全部」。'
              : '请先将审查剩余帧或图片加入数据集。'
        }
        action={
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {isOwner && !readOnly ? (
              <button
                type="button"
                className="lt-btn"
                onClick={() =>
                  setMemberScope((s) => (s === 'mine' ? 'all' : 'mine'))
                }
              >
                {memberScope === 'mine' ? '查看全部' : '只看我的'}
              </button>
            ) : null}
            <Link
              to={
                readOnly
                  ? `/versions?dataset=${version?.dataset_id ?? ''}`
                  : '/datasets'
              }
              className="lt-btn lt-btn-primary"
            >
              返回
            </Link>
          </div>
        }
      />
    )
  }

  const nw = asset?.width || 640
  const nh = asset?.height || 480

  return (
    <div>
      <div className="lt-page-head">
        <div>
          <h1>标注台</h1>
          <p>
            <span className="lt-badge" style={{ marginRight: 8 }}>
              {readOnly ? '版本 · 只读' : '工作区 · 可编辑'}
            </span>
            {titleName}
            {filterPos >= 0
              ? ` · 筛选 ${filterPos + 1}/${filteredMemberIndices.length}`
              : ''}
            {` · 全局 ${index + 1}/${members.length}`}
            {asset ? ` · ${asset.filename}` : ''}
            {` · 已提交 ${progress.submitted}`}
            {progress.draft > 0 ? ` · 草稿 ${progress.draft}` : ''}
            {progress.unlabeled > 0
              ? ` · 未标注 ${progress.unlabeled}`
              : ''}
            {` / 共 ${progress.total}`}
            {tools.length === 0
              ? ' · 无可启用工具'
              : ` · ${tools.map((t) => t.label).join('/')}`}
            {!readOnly
              ? dirty
                ? ' · 已画框（编辑中）· 点下一张即提交本张'
                : ' · 上一张/下一张按当前筛选翻页'
              : ''}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {isOwner && !readOnly ? (
            <button
              type="button"
              className="lt-btn"
              onClick={() =>
                setMemberScope((s) => (s === 'mine' ? 'all' : 'mine'))
              }
              title="负责人可切换只看自己的分配或全部成员"
            >
              {memberScope === 'mine' ? '范围：只看我的' : '范围：全部'}
            </button>
          ) : null}
          {readOnly ? (
            <>
              <Link
                to={`/versions?dataset=${version?.dataset_id ?? ''}`}
                className="lt-btn"
              >
                返回版本列表
              </Link>
              <button
                type="button"
                className="lt-btn"
                disabled={applying}
                onClick={() => void applyVersionToWorkspace()}
              >
                {applying ? '应用中…' : '应用到工作区'}
              </button>
              <Link
                to={`/annotate?dataset=${version?.dataset_id ?? ''}`}
                className="lt-btn lt-btn-primary"
              >
                打开工作区
              </Link>
            </>
          ) : (
            <Link
              to={`/versions?dataset=${dataset?.id ?? ''}`}
              className="lt-btn"
            >
              版本
            </Link>
          )}
          <button
            type="button"
            className="lt-btn"
            disabled={saving || loading || !canGoPrevInFilter}
            title={
              !canGoPrevInFilter
                ? '已是当前筛选的第一张'
                : '按当前筛选（全部/未标/草稿/已提交）翻到上一张'
            }
            onClick={() => void go(-1)}
          >
            上一张
          </button>
          <button
            type="button"
            className="lt-btn lt-btn-primary"
            disabled={saving || loading || !canGoNextInFilter}
            title={
              !canGoNextInFilter
                ? '已是当前筛选的最后一张'
                : '按当前筛选翻到下一张；有改动时会先提交本张'
            }
            onClick={() => void go(1)}
          >
            下一张
          </button>
          {!readOnly ? (
            <>
              <button
                type="button"
                className="lt-btn"
                disabled={saving || loading || progress.unlabeled === 0}
                title="跳到下一张尚未标注的图片"
                onClick={() => void goNextUnlabeled()}
              >
                下一张未标注
                {progress.unlabeled > 0 ? `（${progress.unlabeled}）` : ''}
              </button>
              <button
                type="button"
                className="lt-btn"
                disabled={saving || !dirty}
                title="中途停手：存为草稿（不算发版就绪）"
                onClick={() => void save('draft')}
              >
                仅存草稿
              </button>
              <button
                type="button"
                className="lt-btn"
                disabled={saving}
                title="提交本张并留在当前图"
                onClick={() => void save('submitted')}
              >
                提交本张
              </button>
              <button
                type="button"
                className="lt-btn"
                disabled={
                  saving ||
                  (progress.draft === 0 && !dirty)
                }
                title="将所有草稿改为已提交；未标注的图片不变"
                onClick={() => void submitAllDrafts()}
              >
                提交全部草稿
                {progress.draft > 0 ? `（${progress.draft}）` : ''}
              </button>
            </>
          ) : null}
        </div>
      </div>

      {error ? (
        <StateBlock tone="error" title="操作失败" description={error} />
      ) : null}
      {message ? (
        <p style={{ color: 'var(--lt-success)', marginTop: 0 }}>{message}</p>
      ) : null}

      <div className="lt-annotate-layout">
        <aside className="lt-filmstrip-wrap" aria-label="全部图片">
          <div className="lt-filmstrip-head">
            <span>图片</span>
            <span
              className="lt-muted mono"
              title={`已提交 ${progress.submitted} · 草稿 ${progress.draft} · 未标注 ${progress.unlabeled}`}
            >
              {progress.submitted}/{progress.total}
            </span>
          </div>
          <div className="lt-filmstrip-filters" role="tablist" aria-label="按状态筛选">
            {(
              [
                ['all', '全部', progress.total],
                ['none', '未标', progress.unlabeled],
                ['draft', '草稿', progress.draft],
                ['submitted', '已提交', progress.submitted],
              ] as const
            ).map(([key, label, count]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={memberFilter === key}
                className={`lt-filmstrip-filter${memberFilter === key ? ' active' : ''}`}
                onClick={() => setMemberFilter(key)}
              >
                {label}
                <span className="mono">{count}</span>
              </button>
            ))}
          </div>
          <div className="lt-filmstrip" ref={stripRef}>
            {filteredMemberIndices.length === 0 ? (
              <div className="lt-filmstrip-empty">
                {memberFilter === 'none'
                  ? '没有未标注图片'
                  : memberFilter === 'draft'
                    ? '没有草稿'
                    : memberFilter === 'submitted'
                      ? '没有已提交'
                      : '暂无图片'}
              </div>
            ) : (
              filteredMemberIndices.map((i) => {
                const m = members[i]
                const status = memberStatusAt(i)
                const pending = dirty && i === index && !readOnly
                const mark = statusLabel(status, pending)
                return (
                  <button
                    key={m.asset_id}
                    type="button"
                    data-member-index={i}
                    className={`lt-filmstrip-item${i === index ? ' active' : ''}${status === 'none' ? ' unlabeled' : ''}`}
                    title={`${m.filename} · ${mark}`}
                    disabled={saving || applying}
                    onClick={() => void goTo(i)}
                  >
                    <AuthImage assetId={m.asset_id} alt={m.filename} />
                    <span className="lt-filmstrip-idx">{i + 1}</span>
                    <span
                      className={`lt-filmstrip-mark${status === 'draft' ? ' draft' : ''}${status === 'none' ? ' none' : ''}${pending ? ' pending' : ''}`}
                    >
                      {mark}
                    </span>
                  </button>
                )
              })
            )}
          </div>
        </aside>

        <div style={{ minWidth: 0 }}>
          {!readOnly && tools.length > 0 ? (
            <div style={{ marginBottom: 8 }}>
              <div
                style={{
                  display: 'flex',
                  gap: 6,
                  flexWrap: 'wrap',
                  alignItems: 'center',
                }}
              >
                <span className="lt-muted" style={{ marginRight: 4 }}>
                  工具
                </span>
                {tools.map((t) => (
                  <button
                    key={t.type}
                    type="button"
                    className="lt-btn"
                    style={{
                      background:
                        activeTool === t.type
                          ? 'var(--lt-accent-soft)'
                          : undefined,
                      color:
                        activeTool === t.type ? 'var(--lt-accent)' : undefined,
                    }}
                    onClick={() => setActiveTool(t.type)}
                    title={
                      t.shortcut
                        ? `${t.hint}（${t.shortcut}）`
                        : t.hint
                    }
                  >
                    {t.label}
                    {t.shortcut ? (
                      <span
                        className="mono"
                        style={{ opacity: 0.55, marginLeft: 4 }}
                      >
                        {t.shortcut}
                      </span>
                    ) : null}
                  </button>
                ))}
              </div>
              <p
                style={{
                  margin: '6px 0 0',
                  fontSize: 12,
                  color: 'var(--lt-fg-muted)',
                }}
              >
                {toolHint(tools, activeTool)}
                {activeTool === 'polygon'
                  ? ' · Esc 取消'
                  : activeTool === 'classification'
                    ? ' · 再点一次取消标签'
                    : ' · Del 删选中 / 末条'}
              </p>
            </div>
          ) : null}
          {imageUrl && asset ? (
            <AnnotatorCanvas
              imageUrl={imageUrl}
              naturalWidth={nw}
              naturalHeight={nh}
              shapes={shapes}
              classes={classes}
              activeClassId={activeClassId}
              activeTool={activeTool}
              readOnly={readOnly}
              selectedIndex={selectedShape}
              onSelect={setSelectedShape}
              onChange={markShapes}
            />
          ) : (
            <LoadingBlock />
          )}
        </div>

        <aside className="lt-panel" style={{ padding: '0.85rem' }}>
          <h3 style={{ margin: '0 0 0.5rem', fontSize: '0.9rem' }}>
            {activeTool === 'classification' ? '整图标签' : '类别'}
          </h3>
          {classes.length === 0 ? (
            <p style={{ margin: 0, color: 'var(--lt-fg-subtle)', fontSize: 13 }}>
              本数据集还没启用类别。请先在 YOLO类别页创建；已有类别可在数据集页重新勾选。
            </p>
          ) : (
            <div style={{ display: 'grid', gap: 4 }}>
              {classes.map((c, i) => {
                const tagged = shapes.some(
                  (s) =>
                    s.type === 'classification' && s.classId === c.id,
                )
                const active =
                  activeTool === 'classification'
                    ? tagged
                    : activeClassId === c.id
                return (
                  <button
                    key={c.id}
                    type="button"
                    className="lt-btn"
                    disabled={readOnly}
                    style={{
                      justifyContent: 'flex-start',
                      borderLeft: `3px solid ${classColorCss(c, i)}`,
                      background: active
                        ? 'var(--lt-accent-soft)'
                        : undefined,
                    }}
                    onClick={() =>
                      !readOnly && toggleClassification(c.id)
                    }
                  >
                    <span className="mono" style={{ opacity: 0.7 }}>
                      {i + 1}
                    </span>{' '}
                    {c.name}
                    {activeTool === 'classification' && tagged ? (
                      <span style={{ marginLeft: 'auto', fontSize: 12 }}>
                        ✓
                      </span>
                    ) : null}
                  </button>
                )
              })}
            </div>
          )}

          <h3 style={{ margin: '1rem 0 0.5rem', fontSize: '0.9rem' }}>血缘</h3>
          {lineage?.mediaKind === 'frame' ? (
            <div style={{ fontSize: 13, color: 'var(--lt-fg-muted)' }}>
              <div>
                源视频{' '}
                <span className="mono">{lineage.parentVideoId?.slice(0, 8)}…</span>
              </div>
              <div>
                帧号 <strong>{lineage.frameIndex ?? '—'}</strong>
              </div>
            </div>
          ) : (
            <div style={{ fontSize: 13, color: 'var(--lt-fg-muted)' }}>
              {lineage?.mediaKind || asset?.media_kind} · {lineage?.origin}
            </div>
          )}

          <h3 style={{ margin: '1rem 0 0.5rem', fontSize: '0.9rem' }}>标注列表</h3>
          {shapes.length === 0 ? (
            <p style={{ margin: 0, color: 'var(--lt-fg-subtle)', fontSize: 13 }}>
              {readOnly
                ? '该帧在快照中无标注'
                : '选择工具后在画布标注；分类工具点右侧类别'}
            </p>
          ) : (
            <ul style={{ margin: 0, padding: 0, listStyle: 'none', fontSize: 13 }}>
              {shapes.map((s, i) => {
                const cls = classes.find((c) => c.id === s.classId)
                const idx = classes.findIndex((c) => c.id === s.classId)
                const on = selectedShape === i
                return (
                  <li key={i}>
                    <button
                      type="button"
                      className="lt-btn"
                      style={{
                        width: '100%',
                        justifyContent: 'flex-start',
                        marginBottom: 4,
                        background: on
                          ? 'var(--lt-accent-soft)'
                          : undefined,
                      }}
                      onClick={() => setSelectedShape(i)}
                    >
                      <span
                        style={{
                          display: 'inline-block',
                          width: 8,
                          height: 8,
                          borderRadius: 2,
                          background: classColorCss(cls, idx >= 0 ? idx : i),
                          marginRight: 6,
                          flexShrink: 0,
                        }}
                      />
                      <span style={{ textAlign: 'left' }}>
                        {cls?.name ?? s.classId.slice(0, 8)} ·{' '}
                        {shapeSummary(s)}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
          {!readOnly ? (
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <button
                type="button"
                className="lt-btn lt-btn-danger"
                disabled={shapes.length === 0}
                onClick={() => {
                  if (selectedShape != null) {
                    markShapes(shapes.filter((_, i) => i !== selectedShape))
                    setSelectedShape(null)
                  } else {
                    markShapes(shapes.slice(0, -1))
                  }
                }}
              >
                {selectedShape != null ? '删除选中' : '撤销上一条'}
              </button>
            </div>
          ) : null}
        </aside>
      </div>
    </div>
  )
}

export function AnnotatePage() {
  return (
    <RequireProject>
      <AnnotateInner />
    </RequireProject>
  )
}
