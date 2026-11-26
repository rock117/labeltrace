import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, getUserId } from '../lib/api'
import type {
  Annotation,
  Asset,
  AssetLineage,
  Dataset,
  DatasetAsset,
  RectShape,
} from '../lib/types'
import { resolveToolbarTools } from '../annotation/toolRegistry'
import { AnnotatorCanvas, classColorCss } from '../annotation/AnnotatorCanvas'
import { formatError } from '../hooks/useAsync'
import { LoadingBlock, StateBlock } from '../components/StateBlock'
import { RequireProject } from '../components/RequireProject'

const DATASET_KEY = 'labeltrace.datasetId'

function AnnotateInner() {
  const [params, setParams] = useSearchParams()
  const datasetParam = params.get('dataset') || localStorage.getItem(DATASET_KEY)
  const assetParam = params.get('asset')

  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [members, setMembers] = useState<DatasetAsset[]>([])
  const [index, setIndex] = useState(0)
  const [asset, setAsset] = useState<Asset | null>(null)
  const [lineage, setLineage] = useState<AssetLineage | null>(null)
  const [shapes, setShapes] = useState<RectShape[]>([])
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [activeClass, setActiveClass] = useState(0)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const tools = useMemo(
    () => resolveToolbarTools(dataset?.enabled_annotation_types ?? ['rect']),
    [dataset],
  )

  const loadDataset = useCallback(async (id: string) => {
    const [ds, mem] = await Promise.all([
      api<Dataset>(`/v1/datasets/${id}`),
      api<DatasetAsset[]>(`/v1/datasets/${id}/assets`),
    ])
    setDataset(ds)
    setMembers(mem)
    localStorage.setItem(DATASET_KEY, id)
    return mem
  }, [])

  const loadAssetAt = useCallback(
    async (dsId: string, mem: DatasetAsset[], idx: number) => {
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
      setParams({ dataset: dsId, asset: member.asset_id }, { replace: true })

      const [a, ann, lin] = await Promise.all([
        api<Asset>(`/v1/assets/${member.asset_id}`),
        api<Annotation>(
          `/v1/datasets/${dsId}/assets/${member.asset_id}/annotation`,
        ),
        api<AssetLineage>(`/v1/assets/${member.asset_id}/lineage`),
      ])
      setAsset(a)
      setLineage(lin)
      const items = (ann.shapes?.items ?? []).filter(
        (s): s is RectShape => s.type === 'rect',
      )
      setShapes(items)

      const res = await fetch(`/api/v1/assets/${member.asset_id}/content`, {
        headers: { 'X-User-Id': getUserId() },
      })
      if (!res.ok) throw new Error('无法加载图片')
      const blob = await res.blob()
      setImageUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev)
        return URL.createObjectURL(blob)
      })
    },
    [setParams],
  )

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      if (!datasetParam) {
        setLoading(false)
        return
      }
      setLoading(true)
      setError(null)
      try {
        const mem = await loadDataset(datasetParam)
        if (cancelled) return
        let idx = 0
        if (assetParam) {
          const found = mem.findIndex((m) => m.asset_id === assetParam)
          if (found >= 0) idx = found
        }
        await loadAssetAt(datasetParam, mem, idx)
      } catch (e) {
        if (!cancelled) setError(formatError(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [datasetParam, assetParam, loadDataset, loadAssetAt])

  useEffect(() => {
    return () => {
      if (imageUrl) URL.revokeObjectURL(imageUrl)
    }
  }, [imageUrl])

  const save = async (status: 'draft' | 'submitted' = 'draft') => {
    if (!dataset || !asset) return
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

  const go = async (delta: number) => {
    if (!dataset || members.length === 0) return
    const next = (index + delta + members.length) % members.length
    setLoading(true)
    try {
      await loadAssetAt(dataset.id, members, next)
    } catch (e) {
      setError(formatError(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return
      if (e.key === 'a' || e.key === 'ArrowLeft') void go(-1)
      if (e.key === 'd' || e.key === 'ArrowRight') void go(1)
      if (e.key >= '1' && e.key <= '9') {
        const cls = Number(e.key) - 1
        if (dataset && cls < dataset.classes.length) setActiveClass(cls)
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
  }, [dataset, members, index, shapes, asset])

  if (!datasetParam) {
    return (
      <StateBlock
        title="未选择数据集"
        description="请先在数据集页创建或打开一个数据集。"
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

  if (!dataset || members.length === 0) {
    return (
      <StateBlock
        title="数据集没有可标注成员"
        description="请先将审查剩余帧或图片加入数据集。"
        action={
          <Link to="/datasets" className="lt-btn lt-btn-primary">
            返回数据集
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
            {dataset.name} · {index + 1}/{members.length}
            {asset ? ` · ${asset.filename}` : ''}
            {tools.length === 0 ? ' · 无可启用工具' : ' · 检测框'}
            {' · '}
            右侧选类别 → 图上拖拽画框 → 保存
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button type="button" className="lt-btn" disabled={saving} onClick={() => void go(-1)}>
            上一张
          </button>
          <button type="button" className="lt-btn" disabled={saving} onClick={() => void go(1)}>
            下一张
          </button>
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
          {imageUrl && asset ? (
            <AnnotatorCanvas
              imageUrl={imageUrl}
              naturalWidth={nw}
              naturalHeight={nh}
              shapes={shapes}
              activeClass={activeClass}
              onChange={setShapes}
            />
          ) : (
            <LoadingBlock />
          )}
        </div>

        <aside className="lt-panel" style={{ padding: '0.85rem' }}>
          <h3 style={{ margin: '0 0 0.5rem', fontSize: '0.9rem' }}>类别</h3>
          <div style={{ display: 'grid', gap: 4 }}>
            {(dataset.classes.length ? dataset.classes : ['class0']).map(
              (name, i) => (
                <button
                  key={i}
                  type="button"
                  className="lt-btn"
                  style={{
                    justifyContent: 'flex-start',
                    borderLeft: `3px solid ${classColorCss(i)}`,
                    background:
                      activeClass === i ? 'var(--lt-accent-soft)' : undefined,
                  }}
                  onClick={() => setActiveClass(i)}
                >
                  <span className="mono" style={{ opacity: 0.7 }}>
                    {i + 1}
                  </span>{' '}
                  {name}
                </button>
              ),
            )}
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

          <h3 style={{ margin: '1rem 0 0.5rem', fontSize: '0.9rem' }}>框列表</h3>
          {shapes.length === 0 ? (
            <p style={{ margin: 0, color: 'var(--lt-fg-subtle)', fontSize: 13 }}>
              在画布拖拽绘制检测框
            </p>
          ) : (
            <ul style={{ margin: 0, paddingLeft: '1.1rem', fontSize: 13 }}>
              {shapes.map((s, i) => (
                <li key={i}>
                  cls {s.cls} · [{s.bbox.map((n) => Math.round(n)).join(', ')}]
                </li>
              ))}
            </ul>
          )}
          <button
            type="button"
            className="lt-btn lt-btn-danger"
            style={{ marginTop: 8 }}
            disabled={shapes.length === 0}
            onClick={() => setShapes((p) => p.slice(0, -1))}
          >
            撤销上一框
          </button>
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
