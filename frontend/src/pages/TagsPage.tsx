import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import type { Tag, TaggedAsset } from '../lib/types'
import { useAppStore } from '../store/appStore'
import { formatError } from '../hooks/useAsync'
import { appToast } from '../store/toastStore'
import { useActionPending } from '../hooks/useActionPending'
import { AuthImage } from '../components/AuthImage'
import { AuthVideoThumb } from '../components/AuthVideoThumb'
import { LoadingBlock, StateBlock } from '../components/StateBlock'
import { RequireProject } from '../components/RequireProject'

function TagsInner() {
  const projectId = useAppStore((s) => s.projectId)!
  const [tags, setTags] = useState<Tag[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [assets, setAssets] = useState<TaggedAsset[]>([])
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(true)
  const [assetsLoading, setAssetsLoading] = useState(false)
  const { is, run } = useActionPending()

  const active = tags.find((t) => t.id === activeId) ?? null

  const reloadTags = useCallback(async () => {
    setLoading(true)
    try {
      const list = await api<Tag[]>(`/v1/projects/${projectId}/tags`)
      setTags(list)
      setActiveId((prev) =>
        prev && list.some((t) => t.id === prev) ? prev : list[0]?.id ?? null,
      )
    } catch (e) {
      appToast.error(formatError(e))
      setTags([])
      setActiveId(null)
    } finally {
      setLoading(false)
    }
  }, [projectId])

  const loadAssets = useCallback(
    async (tagId: string) => {
      setAssetsLoading(true)
      try {
        const list = await api<TaggedAsset[]>(
          `/v1/projects/${projectId}/assets?tag_ids=${encodeURIComponent(tagId)}`,
        )
        setAssets(list)
      } catch (e) {
        appToast.error(formatError(e))
        setAssets([])
      } finally {
        setAssetsLoading(false)
      }
    },
    [projectId],
  )

  useEffect(() => {
    void reloadTags()
  }, [reloadTags])

  useEffect(() => {
    if (activeId) void loadAssets(activeId)
    else setAssets([])
  }, [activeId, loadAssets])

  const create = async () => {
    const next = name.trim()
    if (!next) return
    await run('create', async () => {
      try {
        const tag = await api<Tag>(`/v1/projects/${projectId}/tags`, {
          method: 'POST',
          body: JSON.stringify({ name: next }),
        })
        setName('')
        setTags((prev) => [...prev, tag].sort((a, b) => a.name.localeCompare(b.name)))
        setActiveId(tag.id)
      } catch (e) {
        appToast.error(formatError(e))
      }
    })
  }

  if (loading) return <LoadingBlock label="加载标签…" />

  return (
    <div>
      <div className="lt-page-head">
        <div>
          <h1>标签</h1>
          <p>
            项目内扁平标签，用于跨目录找素材。在素材库右键素材可打标签；这里点标签查看其下的库可见视频/图片。
          </p>
        </div>
      </div>


      <div className="lt-panel" style={{ padding: '1rem', marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            className="lt-input"
            placeholder="新标签名"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && void create()}
            style={{ maxWidth: 220 }}
          />
          <button
            type="button"
            className="lt-btn lt-btn-primary"
            disabled={is('create') || !name.trim()}
            onClick={() => void create()}
          >
            创建标签
          </button>
          <Link to="/library" className="lt-btn">
            去素材库打标签
          </Link>
        </div>
      </div>

      {tags.length === 0 ? (
        <StateBlock
          title="还没有标签"
          description="先创建标签，再到素材库给视频或图片打上，即可在此按标签浏览。"
        />
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
            {tags.map((t) => (
              <button
                key={t.id}
                type="button"
                className="lt-btn"
                style={{
                  width: '100%',
                  justifyContent: 'flex-start',
                  marginBottom: 4,
                  background:
                    t.id === activeId ? 'var(--lt-accent-soft)' : undefined,
                }}
                onClick={() => setActiveId(t.id)}
              >
                {t.name}
              </button>
            ))}
          </aside>

          <section className="lt-panel" style={{ padding: '1rem' }}>
            {active ? (
              <>
                <h2 style={{ margin: '0 0 0.75rem', fontSize: '1rem' }}>
                  {active.name}
                  <span
                    style={{
                      marginLeft: 8,
                      fontWeight: 400,
                      fontSize: 13,
                      color: 'var(--lt-fg-muted)',
                    }}
                  >
                    {assetsLoading ? '加载中…' : `${assets.length} 个素材`}
                  </span>
                </h2>
                {assetsLoading ? (
                  <LoadingBlock label="加载素材…" />
                ) : assets.length === 0 ? (
                  <StateBlock
                    title="该标签下还没有素材"
                    description="到素材库对视频或上传图片右键 → 打标签。"
                    action={
                      <Link to="/library" className="lt-btn lt-btn-primary">
                        去素材库
                      </Link>
                    }
                  />
                ) : (
                  <div className="lt-media-grid">
                    {assets.map((a) => (
                      <div key={a.id} className="lt-media-card">
                        <div className="lt-media-card-thumb">
                          {a.media_kind === 'video' ? (
                            <AuthVideoThumb assetId={a.id} />
                          ) : (
                            <AuthImage assetId={a.id} alt={a.filename} />
                          )}
                        </div>
                        <div className="lt-media-card-meta" title={a.filename}>
                          {a.media_kind === 'video' ? '视频' : '图片'} · {a.filename}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <StateBlock title="选择标签" description="从左侧点一个标签查看素材。" />
            )}
          </section>
        </div>
      )}
    </div>
  )
}

export function TagsPage() {
  return (
    <RequireProject>
      <TagsInner />
    </RequireProject>
  )
}
