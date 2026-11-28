import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import type { Project, ProjectClass } from '../lib/types'
import { useAppStore } from '../store/appStore'
import { formatError } from '../hooks/useAsync'
import { LoadingBlock, StateBlock } from '../components/StateBlock'
import { appConfirm, appPrompt } from '../store/dialogStore'

type ProjectRole = 'owner' | 'annotator' | 'viewer'

type Member = {
  user_id: string
  username: string
  roles: ProjectRole[] | string[]
}

const ROLE_OPTIONS: { value: ProjectRole; label: string }[] = [
  { value: 'owner', label: '负责人' },
  { value: 'annotator', label: '标注员' },
  { value: 'viewer', label: '只读' },
]

function roleLabel(role: string): string {
  return ROLE_OPTIONS.find((o) => o.value === role)?.label ?? role
}

function rolesLabel(roles: string[]): string {
  return roles.map(roleLabel).join(' · ') || '（无）'
}

function toggleRole(roles: ProjectRole[], role: ProjectRole): ProjectRole[] {
  return roles.includes(role)
    ? roles.filter((r) => r !== role)
    : [...roles, role]
}

export function ProjectsPage() {
  const navigate = useNavigate()
  const setProject = useAppStore((s) => s.setProject)
  const projectId = useAppStore((s) => s.projectId)
  const me = useAppStore((s) => s.user)
  const [items, setItems] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)

  const [membersOf, setMembersOf] = useState<string | null>(null)
  const [members, setMembers] = useState<Member[]>([])
  const [classes, setClasses] = useState<ProjectClass[]>([])
  const [className, setClassName] = useState('')
  const [classColor, setClassColor] = useState('#0f766e')
  const [membersLoading, setMembersLoading] = useState(false)
  const [newMemberId, setNewMemberId] = useState('')
  const [newMemberRoles, setNewMemberRoles] = useState<ProjectRole[]>([
    'annotator',
  ])

  const enterProject = (id: string, projectName: string) => {
    setProject(id, projectName)
    navigate('/library')
  }

  const rename = async (p: Project) => {
    const next = await appPrompt({
      title: '重命名项目',
      label: '项目名称',
      defaultValue: p.name,
      confirmLabel: '保存',
    })
    if (next == null) return
    const name = next.trim()
    if (!name || name === p.name) return
    setBusy(true)
    setError(null)
    try {
      const updated = await api<Project>(`/v1/projects/${p.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ name }),
      })
      if (p.id === projectId) setProject(updated.id, updated.name)
      await reload()
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusy(false)
    }
  }

  const reload = async () => {
    setLoading(true)
    setError(null)
    try {
      const list = await api<Project[]>('/v1/projects')
      setItems(list)
    } catch (e) {
      setError(formatError(e))
    } finally {
      setLoading(false)
    }
  }

  const loadMembers = async (pid: string) => {
    setMembersLoading(true)
    setError(null)
    try {
      const [list, vocabulary] = await Promise.all([
        api<Member[]>(`/v1/projects/${pid}/members`),
        api<ProjectClass[]>(`/v1/projects/${pid}/classes`),
      ])
      setMembers(list)
      setClasses(vocabulary)
    } catch (e) {
      setError(formatError(e))
      setMembers([])
      setClasses([])
    } finally {
      setMembersLoading(false)
    }
  }

  const addClass = async (pid: string) => {
    const next = className.trim()
    if (!next) return
    setBusy(true)
    setError(null)
    try {
      await api<ProjectClass>(`/v1/projects/${pid}/classes`, {
        method: 'POST',
        body: JSON.stringify({ name: next, color: classColor }),
      })
      setClassName('')
      await loadMembers(pid)
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusy(false)
    }
  }

  const renameClass = async (pid: string, cls: ProjectClass) => {
    const next = await appPrompt({
      title: '重命名类别',
      label: '名称',
      defaultValue: cls.name,
      confirmLabel: '保存',
    })
    if (next == null) return
    const name = next.trim()
    if (!name || name === cls.name) return
    setBusy(true)
    setError(null)
    try {
      await api(`/v1/projects/${pid}/classes/${cls.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ name }),
      })
      await loadMembers(pid)
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusy(false)
    }
  }

  const removeClass = async (pid: string, cls: ProjectClass) => {
    const ok = await appConfirm({
      title: '删除类别',
      description: `删除「${cls.name}」？若仍被数据集选用、标注引用或已写入版本，删除会被拒绝。`,
      confirmLabel: '删除',
      danger: true,
    })
    if (!ok) return
    setBusy(true)
    setError(null)
    try {
      await api(`/v1/projects/${pid}/classes/${cls.id}`, { method: 'DELETE' })
      await loadMembers(pid)
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusy(false)
    }
  }

  const toggleMembers = (pid: string) => {
    if (membersOf === pid) {
      setMembersOf(null)
      return
    }
    setMembersOf(pid)
    setNewMemberId('')
    setNewMemberRoles(['annotator'])
    void loadMembers(pid)
  }

  const addMember = async (pid: string) => {
    const uid = newMemberId.trim()
    if (!uid || newMemberRoles.length === 0) return
    setBusy(true)
    setError(null)
    try {
      await api<Member>(`/v1/projects/${pid}/members`, {
        method: 'POST',
        body: JSON.stringify({ username: uid, roles: newMemberRoles }),
      })
      setNewMemberId('')
      setNewMemberRoles(['annotator'])
      await loadMembers(pid)
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusy(false)
    }
  }

  const saveRoles = async (pid: string, uid: string, roles: ProjectRole[]) => {
    if (roles.length === 0) {
      setError('至少保留一个角色')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await api<Member>(
        `/v1/projects/${pid}/members/${encodeURIComponent(uid)}`,
        {
          method: 'PATCH',
          body: JSON.stringify({ roles }),
        },
      )
      await loadMembers(pid)
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void reload()
  }, [])

  const create = async () => {
    if (!name.trim()) return
    setBusy(true)
    setError(null)
    try {
      const p = await api<Project>('/v1/projects', {
        method: 'POST',
        body: JSON.stringify({ name: name.trim() }),
      })
      setName('')
      enterProject(p.id, p.name)
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusy(false)
    }
  }

  const myRoles = (pid: string) =>
    membersOf === pid
      ? (members.find((m) => m.user_id === me?.id)?.roles ?? [])
      : []
  const canManage = (pid: string) => myRoles(pid).includes('owner')

  return (
    <div>
      <div className="lt-page-head">
        <div>
          <h1>选择项目</h1>
          <p>
            登录后创建项目即成为负责人；邀请同事用对方注册的用户名，并勾选角色（可多选，权限取并集）。
          </p>
        </div>
      </div>

      <div className="lt-panel" style={{ padding: '1rem', marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            className="lt-input"
            placeholder="新项目名称"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && void create()}
          />
          <button
            type="button"
            className="lt-btn lt-btn-primary"
            disabled={busy || !name.trim()}
            onClick={() => void create()}
          >
            创建项目
          </button>
        </div>
      </div>

      {loading ? <LoadingBlock /> : null}
      {error ? (
        <StateBlock
          tone="error"
          title="出错了"
          description={error}
          action={
            <button type="button" className="lt-btn" onClick={() => void reload()}>
              重试
            </button>
          }
        />
      ) : null}
      {!loading && !error && items.length === 0 ? (
        <StateBlock title="还没有项目" description="创建一个项目开始上传视频与标注。" />
      ) : null}

      <div style={{ display: 'grid', gap: '0.5rem' }}>
        {items.map((p) => {
          const active = p.id === projectId
          const open = membersOf === p.id
          return (
            <div
              key={p.id}
              className="lt-panel"
              style={{
                padding: '0.85rem 1rem',
                borderColor: active ? 'var(--lt-accent)' : undefined,
                background: active ? 'var(--lt-accent-soft)' : undefined,
              }}
            >
              <div
                style={{
                  display: 'flex',
                  gap: 12,
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <button
                  type="button"
                  style={{
                    flex: 1,
                    textAlign: 'left',
                    background: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    color: 'inherit',
                    padding: 0,
                  }}
                  onClick={() => enterProject(p.id, p.name)}
                >
                  <div style={{ fontWeight: 600 }}>{p.name}</div>
                  <div className="mono" style={{ color: 'var(--lt-fg-subtle)', fontSize: 12 }}>
                    {p.id}
                  </div>
                  {active ? (
                    <span className="lt-badge" style={{ marginTop: 6 }}>
                      当前 · 进入素材库
                    </span>
                  ) : (
                    <span className="lt-muted" style={{ marginTop: 6, display: 'block' }}>
                      进入此项目
                    </span>
                  )}
                </button>
                <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                  <button
                    type="button"
                    className="lt-btn"
                    disabled={busy}
                    onClick={() => toggleMembers(p.id)}
                  >
                    {open ? '收起成员' : '成员'}
                  </button>
                  <button
                    type="button"
                    className="lt-btn"
                    disabled={busy}
                    onClick={() => void rename(p)}
                  >
                    重命名
                  </button>
                </div>
              </div>

              {open ? (
                <div
                  style={{
                    marginTop: 12,
                    paddingTop: 12,
                    borderTop: '1px solid var(--lt-border)',
                  }}
                >
                  <p
                    style={{
                      margin: '0 0 0.5rem',
                      fontSize: 13,
                      color: 'var(--lt-fg-muted)',
                    }}
                  >
                    你在此项目的角色：{rolesLabel(myRoles(p.id) as string[])}。
                    {canManage(p.id)
                      ? ' 负责人可添加成员并勾选多个角色。'
                      : ' 仅负责人可添加或改角色。'}
                  </p>
                  {membersLoading ? (
                    <p style={{ fontSize: 13, color: 'var(--lt-fg-subtle)' }}>加载成员…</p>
                  ) : (
                    <ul
                      style={{
                        listStyle: 'none',
                        margin: '0 0 0.75rem',
                        padding: 0,
                        display: 'grid',
                        gap: 10,
                      }}
                    >
                      {members.map((m) => {
                        const roles = m.roles as ProjectRole[]
                        return (
                          <li
                            key={m.user_id}
                            style={{
                              display: 'flex',
                              gap: 10,
                              alignItems: 'flex-start',
                              flexWrap: 'wrap',
                              fontSize: 13,
                            }}
                          >
                            <span style={{ minWidth: 100, paddingTop: 4 }}>
                              <strong>{m.username || m.user_id}</strong>
                              {m.user_id === me?.id ? '（我）' : ''}
                            </span>
                            {canManage(p.id) ? (
                              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                                {ROLE_OPTIONS.map((o) => {
                                  const on = roles.includes(o.value)
                                  return (
                                    <label
                                      key={o.value}
                                      style={{
                                        display: 'inline-flex',
                                        gap: 4,
                                        alignItems: 'center',
                                        cursor: busy ? 'default' : 'pointer',
                                      }}
                                    >
                                      <input
                                        type="checkbox"
                                        checked={on}
                                        disabled={busy}
                                        onChange={() => {
                                          const next = toggleRole(roles, o.value)
                                          void saveRoles(p.id, m.user_id, next)
                                        }}
                                      />
                                      {o.label}
                                    </label>
                                  )
                                })}
                              </div>
                            ) : (
                              <span className="lt-badge">{rolesLabel(roles)}</span>
                            )}
                          </li>
                        )
                      })}
                    </ul>
                  )}
                  {canManage(p.id) ? (
                    <div
                      style={{
                        display: 'flex',
                        gap: 8,
                        flexWrap: 'wrap',
                        alignItems: 'center',
                      }}
                    >
                      <input
                        className="lt-input"
                        placeholder="对方用户名（需已注册）"
                        value={newMemberId}
                        onChange={(e) => setNewMemberId(e.target.value)}
                        style={{ minWidth: 200 }}
                      />
                      {ROLE_OPTIONS.map((o) => {
                        const on = newMemberRoles.includes(o.value)
                        return (
                          <label
                            key={o.value}
                            style={{
                              display: 'inline-flex',
                              gap: 4,
                              alignItems: 'center',
                              fontSize: 13,
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={on}
                              onChange={() =>
                                setNewMemberRoles((prev) => toggleRole(prev, o.value))
                              }
                            />
                            {o.label}
                          </label>
                        )
                      })}
                      <button
                        type="button"
                        className="lt-btn lt-btn-primary"
                        disabled={
                          busy || !newMemberId.trim() || newMemberRoles.length === 0
                        }
                        onClick={() => void addMember(p.id)}
                      >
                        添加成员
                      </button>
                    </div>
                  ) : null}
                  <div
                    style={{
                      marginTop: 16,
                      paddingTop: 12,
                      borderTop: '1px solid var(--lt-border)',
                    }}
                  >
                    <h3 style={{ margin: '0 0 0.35rem', fontSize: '0.95rem' }}>
                      类别词表
                    </h3>
                    <p
                      style={{
                        margin: '0 0 0.75rem',
                        fontSize: 13,
                        color: 'var(--lt-fg-muted)',
                      }}
                    >
                      类别属于项目。数据集页只选用其中一部分并排导出顺序。改名不改变已有框引用的 id；已发版本保留发版时的名称。
                    </p>
                    {classes.length === 0 ? (
                      <p style={{ margin: '0 0 0.75rem', fontSize: 13 }}>
                        还没有类别。
                      </p>
                    ) : (
                      <ul
                        style={{
                          listStyle: 'none',
                          margin: '0 0 0.75rem',
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
                            {myRoles(p.id).some((r) => r === 'owner' || r === 'annotator') ? (
                              <>
                                <button
                                  type="button"
                                  className="lt-btn"
                                  disabled={busy}
                                  onClick={() => void renameClass(p.id, c)}
                                >
                                  改名
                                </button>
                                <button
                                  type="button"
                                  className="lt-btn lt-btn-danger"
                                  disabled={busy}
                                  onClick={() => void removeClass(p.id, c)}
                                >
                                  删除
                                </button>
                              </>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    )}
                    {myRoles(p.id).some((r) => r === 'owner' || r === 'annotator') ? (
                      <div
                        style={{
                          display: 'flex',
                          gap: 8,
                          flexWrap: 'wrap',
                          alignItems: 'center',
                        }}
                      >
                        <input
                          className="lt-input"
                          placeholder="新类别名"
                          value={className}
                          onChange={(e) => setClassName(e.target.value)}
                          onKeyDown={(e) => e.key === 'Enter' && void addClass(p.id)}
                          style={{ maxWidth: 180 }}
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
                          disabled={busy || !className.trim()}
                          onClick={() => void addClass(p.id)}
                        >
                          添加类别
                        </button>
                      </div>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}
