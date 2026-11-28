import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import type { ProjectClass } from '../lib/types'
import { useAppStore } from '../store/appStore'
import { formatError } from '../hooks/useAsync'
import { useActionPending } from '../hooks/useActionPending'
import { LoadingBlock } from '../components/StateBlock'
import { RequireProject } from '../components/RequireProject'
import { appConfirm, appPrompt } from '../store/dialogStore'
import { appToast } from '../store/toastStore'

type ProjectRole = 'owner' | 'annotator' | 'viewer'

type Member = {
  user_id: string
  roles: ProjectRole[] | string[]
}

function ClassesInner() {
  const projectId = useAppStore((s) => s.projectId)!
  const me = useAppStore((s) => s.user)
  const [classes, setClasses] = useState<ProjectClass[]>([])
  const [canWrite, setCanWrite] = useState(false)
  const [className, setClassName] = useState('')
  const [classColor, setClassColor] = useState('#0f766e')
  const [loading, setLoading] = useState(true)
  const { is, run } = useActionPending()

  const reload = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      const [list, members] = await Promise.all([
        api<ProjectClass[]>(`/v1/projects/${projectId}/classes`),
        api<Member[]>(`/v1/projects/${projectId}/members`),
      ])
      setClasses(list)
      const mine = members.find((m) => m.user_id === me?.id)
      const roles = (mine?.roles ?? []) as string[]
      setCanWrite(roles.some((r) => r === 'owner' || r === 'annotator'))
    } catch (e) {
      appToast.error(formatError(e))
      setClasses([])
    } finally {
      setLoading(false)
    }
  }, [projectId, me?.id])

  useEffect(() => {
    void reload()
  }, [reload])

  const addClass = async () => {
    const next = className.trim()
    if (!next) return
    await run('add', async () => {
      try {
        await api<ProjectClass>(`/v1/projects/${projectId}/classes`, {
          method: 'POST',
          body: JSON.stringify({ name: next, color: classColor }),
        })
        setClassName('')
        await reload(true)
      } catch (e) {
        appToast.error(formatError(e))
      }
    })
  }

  const renameClass = async (cls: ProjectClass) => {
    const next = await appPrompt({
      title: '重命名类别',
      label: '名称',
      defaultValue: cls.name,
      confirmLabel: '保存',
    })
    if (next == null) return
    const name = next.trim()
    if (!name || name === cls.name) return
    await run(`rename:${cls.id}`, async () => {
      try {
        await api(`/v1/projects/${projectId}/classes/${cls.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ name }),
        })
        await reload(true)
      } catch (e) {
        appToast.error(formatError(e))
      }
    })
  }

  const removeClass = async (cls: ProjectClass) => {
    const ok = await appConfirm({
      title: '删除类别',
      description: `删除「${cls.name}」？若仍被数据集选用、标注引用或已写入版本，删除会被拒绝。`,
      confirmLabel: '删除',
      danger: true,
    })
    if (!ok) return
    await run(`delete:${cls.id}`, async () => {
      try {
        await api(`/v1/projects/${projectId}/classes/${cls.id}`, { method: 'DELETE' })
        await reload(true)
      } catch (e) {
        appToast.error(formatError(e))
      }
    })
  }

  if (loading) return <LoadingBlock label="加载类别…" />

  return (
    <div>
      <div className="lt-page-head">
        <div>
          <h1>YOLO类别</h1>
          <p>
            类别属于当前项目。新建后会自动出现在各数据集里；不需要的到数据集页取消勾选。
          </p>
        </div>
      </div>


      <div className="lt-panel" style={{ padding: '1rem' }}>
        {canWrite ? (
          <div
            style={{
              display: 'flex',
              gap: 8,
              flexWrap: 'wrap',
              alignItems: 'center',
              marginBottom: classes.length ? 16 : 0,
            }}
          >
            <input
              className="lt-input"
              placeholder="新类别名"
              value={className}
              onChange={(e) => setClassName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && void addClass()}
              style={{ maxWidth: 220 }}
            />
            <input
              type="color"
              title="颜色"
              value={classColor}
              onChange={(e) => setClassColor(e.target.value)}
              style={{ width: 36, height: 32, padding: 0, border: 'none' }}
            />
            <button
              type="button"
              className="lt-btn lt-btn-primary"
              disabled={is('add') || !className.trim()}
              onClick={() => void addClass()}
            >
              添加类别
            </button>
            <Link to="/datasets" className="lt-btn">
              去数据集
            </Link>
          </div>
        ) : (
          <p style={{ margin: '0 0 0.75rem', fontSize: 13, color: 'var(--lt-fg-muted)' }}>
            当前角色只能查看。负责人和标注员可以添加、改名和删除。
          </p>
        )}
        {classes.length === 0 ? (
          <p style={{ margin: 0 }}>还没有类别。</p>
        ) : (
          <ul
            style={{
              listStyle: 'none',
              margin: 0,
              padding: 0,
              display: 'grid',
              gap: 8,
            }}
          >
            {classes.map((c) => (
              <li
                key={c.id}
                style={{
                  display: 'flex',
                  gap: 8,
                  alignItems: 'center',
                  flexWrap: 'wrap',
                }}
              >
                <span
                  style={{
                    width: 14,
                    height: 14,
                    borderRadius: 3,
                    background: c.color || '#0f766e',
                  }}
                />
                <span>{c.name}</span>
                {canWrite ? (
                  <>
                    <button
                      type="button"
                      className="lt-btn"
                      disabled={is(`rename:${c.id}`)}
                      onClick={() => void renameClass(c)}
                    >
                      改名
                    </button>
                    <button
                      type="button"
                      className="lt-btn lt-btn-danger"
                      disabled={is(`delete:${c.id}`)}
                      onClick={() => void removeClass(c)}
                    >
                      删除
                    </button>
                  </>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

export function ClassesPage() {
  return (
    <RequireProject>
      <ClassesInner />
    </RequireProject>
  )
}
