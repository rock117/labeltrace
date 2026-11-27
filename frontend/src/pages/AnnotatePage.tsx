import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, getToken } from '../lib/api'
import type {
  Annotation,
  Asset,
  AssetLineage,
  Dataset,
  DatasetAsset,
  RectShape,
  Version,
  VersionManifest,
  VersionManifestEntry,
} from '../lib/types'
import {
  resolveToolbarTools,
  type AnnotationToolType,
} from '../annotation/toolRegistry'
import { AnnotatorCanvas, classColorCss } from '../annotation/AnnotatorCanvas'
import { formatError } from '../hooks/useAsync'
import { AuthImage } from '../components/AuthImage'
import { LoadingBlock, StateBlock } from '../components/StateBlock'
import { RequireProject } from '../components/RequireProject'
import { appConfirm } from '../store/dialogStore'

const DATASET_KEY = 'labeltrace.datasetId'

function rectItems(shapes: { items?: { type: string }[] } | null | undefined) {
  return (shapes?.items ?? []).filter(
    (s): s is RectShape => s.type === 'rect',
  )
}

function AnnotateInner() {
  const [params, setParams] = useSearchParams()
  const versionParam = params.get('version')
  const datasetParam =
    params.get('dataset') ||
    (!versionParam ? localStorage.getItem(DATASET_KEY) : null)
  const assetParam = params.get('asset')
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
  const [shapes, setShapes] = useState<RectShape[]>([])
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [activeClass, setActiveClass] = useState(0)
  const [activeTool, setActiveTool] = useState<AnnotationToolType>('rect')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [applying, setApplying] = useState(false)
  const stripRef = useRef<HTMLDivElement>(null)

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
      localStorage.setItem(DATASET_KEY, r.dataset_id)
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

  const classNames = useMemo(() => {
    if (readOnly && version) {
      return version.classes.length ? version.classes : ['class0']
    }
    return dataset?.classes.length ? dataset.classes : ['class0']
  }, [readOnly, version, dataset])

  const titleName = readOnly
    ? version?.name ?? '版本'
    : dataset?.name ?? '数据集'

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
        return
      }
      const safe = Math.max(0, Math.min(idx, mem.length - 1))
      setIndex(safe)
      const member = mem[safe]
      const nextParams: Record<string, string> = { asset: member.asset_id }
      if (verId) nextParams.version = verId
      if (dsId) nextParams.dataset = dsId
      setParams(nextParams, { replace: true })

      if (verId) {
        const entry = entries[safe]
        const [a, lin] = await Promise.all([
          api<Asset>(`/v1/assets/${member.asset_id}`),
          api<AssetLineage>(`/v1/assets/${member.asset_id}/lineage`),
        ])
        setAsset(a)
        setLineage(lin)
        setShapes(rectItems(entry?.shapes))
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
      setAsset(a)
      setLineage(lin)
      setShapes(rectItems(ann.shapes))
      await loadContent(member.asset_id)
    },
    [setParams, loadContent],
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
          localStorage.setItem(DATASET_KEY, ver.dataset_id)
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
          const [ds, mem] = await Promise.all([
            api<Dataset>(`/v1/datasets/${datasetParam}`),
            api<DatasetAsset[]>(`/v1/datasets/${datasetParam}/assets`),
          ])
          if (cancelled) return
          setDataset(ds)
          setMembers(mem)
          localStorage.setItem(DATASET_KEY, datasetParam)
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
    // 仅随 dataset/version 切换重载；asset 翻页走 go()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetParam, versionParam])

  useEffect(() => {
    return () => {
      if (imageUrl) URL.revokeObjectURL(imageUrl)
    }
  }, [imageUrl])

  const save = async (status: 'draft' | 'submitted' = 'draft') => {
    if (readOnly || !dataset || !asset) return
    setSaving(true)
    setError(null)
    try {
      await api(`/v1/datasets/${dataset.id}/assets/${asset.id}/annotation`, {
        method: 'PUT',
        body: JSON.stringify({
          shapes: { format: 'xyxy_abs', items: shapes },
          status,
        }),
      })
      setMessage(status === 'submitted' ? '已提交' : '已保存草稿')
    } catch (e) {
      setError(formatError(e))
    } finally {
      setSaving(false)
    }
  }

  const goTo = async (next: number) => {
    if (members.length === 0) return
    const safe = ((next % members.length) + members.length) % members.length
    if (safe === index && asset) return
    setLoading(true)
    try {
      await showMember({
        dsId: dataset?.id ?? version?.dataset_id ?? null,
        verId: versionParam,
        mem: members,
        entries: snapshotEntries,
        idx: safe,
      })
    } catch (e) {
      setError(formatError(e))
    } finally {
      setLoading(false)
    }
  }

  const go = async (delta: number) => {
    await goTo(index + delta)
  }

  useEffect(() => {
    const strip = stripRef.current
    if (!strip) return
    const el = strip.querySelector<HTMLElement>(
      `[data-member-index="${index}"]`,
    )
    if (!el) return
    // 只用胶片条自身滚动；scrollIntoView 会连带滚动画布祖先，导致主图“飞出”视口
    const left =
      el.offsetLeft - (strip.clientWidth - el.clientWidth) / 2
    strip.scrollTo({ left: Math.max(0, left), behavior: 'smooth' })
  }, [index])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return
      if (e.key === 'a' || e.key === 'ArrowLeft') void go(-1)
      if (e.key === 'd' || e.key === 'ArrowRight') void go(1)
      if (readOnly) return
      if (e.key >= '1' && e.key <= '9') {
        const cls = Number(e.key) - 1
        if (cls < classNames.length) setActiveClass(cls)
      }
      if (e.key === 's' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault()
        void save('draft')
      }
      if (e.key === 'Backspace' || e.key === 'Delete') {
        setShapes((prev) => prev.slice(0, -1))
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataset, version, members, index, shapes, asset, readOnly, classNames])

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
        title={readOnly ? '该版本没有成员' : '数据集没有可标注成员'}
        description={
          readOnly
            ? '此快照为空。'
            : '请先将审查剩余帧或图片加入数据集。'
        }
        action={
          <Link
            to={readOnly ? `/versions?dataset=${version?.dataset_id ?? ''}` : '/datasets'}
            className="lt-btn lt-btn-primary"
          >
            返回
          </Link>
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
            {titleName} · {index + 1}/{members.length}
            {asset ? ` · ${asset.filename}` : ''}
            {tools.length === 0 ? ' · 无可启用工具' : ' · 检测框'}
            {!readOnly ? ' · 右侧选类别 → 拖拽画框 → 提交' : ''}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
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
          <button type="button" className="lt-btn" disabled={saving} onClick={() => void go(-1)}>
            上一张
          </button>
          <button type="button" className="lt-btn" disabled={saving} onClick={() => void go(1)}>
            下一张
          </button>
          {!readOnly ? (
            <>
              <button
                type="button"
                className="lt-btn lt-btn-primary"
                disabled={saving}
                onClick={() => void save('draft')}
              >
                保存
              </button>
              <button
                type="button"
                className="lt-btn"
                disabled={saving}
                onClick={() => void save('submitted')}
              >
                提交
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

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 220px',
          gap: '1rem',
          alignItems: 'start',
        }}
      >
        <div>
          {!readOnly && tools.length > 0 ? (
            <div
              style={{
                display: 'flex',
                gap: 6,
                flexWrap: 'wrap',
                marginBottom: 8,
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
                  title={t.shortcut ? `快捷键 ${t.shortcut}` : undefined}
                >
                  {t.label}
                  {t.shortcut ? (
                    <span className="mono" style={{ opacity: 0.55, marginLeft: 4 }}>
                      {t.shortcut}
                    </span>
                  ) : null}
                </button>
              ))}
            </div>
          ) : null}
          {imageUrl && asset ? (
            <AnnotatorCanvas
              imageUrl={imageUrl}
              naturalWidth={nw}
              naturalHeight={nh}
              shapes={shapes}
              classNames={classNames}
              activeClass={activeClass}
              activeTool={activeTool}
              readOnly={readOnly}
              onChange={setShapes}
            />
          ) : (
            <LoadingBlock />
          )}

          <div className="lt-filmstrip-wrap">
            <div className="lt-filmstrip-head">
              <span>全部图片</span>
              <span className="lt-muted">
                {index + 1} / {members.length}
              </span>
            </div>
            <div className="lt-filmstrip" ref={stripRef}>
              {members.map((m, i) => {
                const snapStatus = snapshotEntries[i]?.annotationStatus
                return (
                  <button
                    key={m.asset_id}
                    type="button"
                    data-member-index={i}
                    className={`lt-filmstrip-item${i === index ? ' active' : ''}`}
                    title={m.filename}
                    disabled={saving || applying}
                    onClick={() => void goTo(i)}
                  >
                    <AuthImage assetId={m.asset_id} alt={m.filename} />
                    <span className="lt-filmstrip-idx">{i + 1}</span>
                    {readOnly && snapStatus === 'submitted' ? (
                      <span className="lt-filmstrip-mark">已提交</span>
                    ) : null}
                  </button>
                )
              })}
            </div>
          </div>
        </div>

        <aside className="lt-panel" style={{ padding: '0.85rem' }}>
          <h3 style={{ margin: '0 0 0.5rem', fontSize: '0.9rem' }}>类别</h3>
          <div style={{ display: 'grid', gap: 4 }}>
            {classNames.map((name, i) => (
              <button
                key={i}
                type="button"
                className="lt-btn"
                disabled={readOnly}
                style={{
                  justifyContent: 'flex-start',
                  borderLeft: `3px solid ${classColorCss(i)}`,
                  background:
                    !readOnly && activeClass === i
                      ? 'var(--lt-accent-soft)'
                      : undefined,
                }}
                onClick={() => !readOnly && setActiveClass(i)}
              >
                <span className="mono" style={{ opacity: 0.7 }}>
                  {i + 1}
                </span>{' '}
                {name}
              </button>
            ))}
          </div>

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
              {readOnly ? '该帧在快照中无框' : '在画布拖拽绘制检测框'}
            </p>
          ) : (
            <ul style={{ margin: 0, paddingLeft: '1.1rem', fontSize: 13 }}>
              {shapes.map((s, i) => (
                <li key={i}>
                  <span
                    style={{
                      display: 'inline-block',
                      width: 8,
                      height: 8,
                      borderRadius: 2,
                      background: `var(--lt-class-${s.cls % 5})`,
                      marginRight: 6,
                    }}
                  />
                  {classNames[s.cls] ?? `class${s.cls}`} · [
                  {s.bbox.map((n) => Math.round(n)).join(', ')}]
                </li>
              ))}
            </ul>
          )}
          {!readOnly ? (
            <button
              type="button"
              className="lt-btn lt-btn-danger"
              style={{ marginTop: 8 }}
              disabled={shapes.length === 0}
              onClick={() => setShapes((p) => p.slice(0, -1))}
            >
              撤销上一框
            </button>
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
