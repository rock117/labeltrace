import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import type { Project } from '../lib/types'
import { useAppStore } from '../store/appStore'
import { formatError } from '../hooks/useAsync'
import { useActionPending } from '../hooks/useActionPending'
import { LoadingBlock, StateBlock } from '../components/StateBlock'
import { appPrompt } from '../store/dialogStore'

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
  const { is, run } = useActionPending()

  const [membersOf, setMembersOf] = useState<string | null>(null)
  const [members, setMembers] = useState<Member[]>([])
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
    setError(null)
    await run(`rename:${p.id}`, async () => {
      try {
        const updated = await api<Project>(`/v1/projects/${p.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ name }),
        })
        if (p.id === projectId) setProject(updated.id, updated.name)
        await reload()
      } catch (e) {
        setError(formatError(e))
      }
    })
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
      const list = await api<Member[]>(`/v1/projects/${pid}/members`)
      setMembers(list)
    } catch (e) {
      setError(formatError(e))
      setMembers([])
    } finally {
      setMembersLoading(false)
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
    setError(null)
    await run(`add-member:${pid}`, async () => {
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
      }
    })
  }

  const saveRoles = async (pid: string, uid: string, roles: ProjectRole[]) => {
    if (roles.length === 0) {
      setError('至少保留一个角色')
      return
    }
    setError(null)
    await run(`roles:${pid}:${uid}`, async () => {
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
      }
    })
  }

  useEffect(() => {
    void reload()
  }, [])

  const create = async () => {
    if (!name.trim()) return
    setError(null)
    await run('create', async () => {
      try {
        const p = await api<Project>('/v1/projects', {
          method: 'POST',
          body: JSON.stringify({ name: name.trim() }),
        })
        setName('')
        enterProject(p.id, p.name)
      } catch (e) {
        setError(formatError(e))
      }
    })
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
            disabled={is('create') || !name.trim()}
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
                    onClick={() => toggleMembers(p.id)}
                  >
                    {open ? '收起成员' : '成员'}
                  </button>
                  <button
                    type="button"
                    className="lt-btn"
                    disabled={is(`rename:${p.id}`)}
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
                                        cursor: is(`roles:${p.id}:${m.user_id}`)
                                          ? 'default'
                                          : 'pointer',
                                      }}
                                    >
                                      <input
                                        type="checkbox"
                                        checked={on}
                                        disabled={is(`roles:${p.id}:${m.user_id}`)}
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
                          is(`add-member:${p.id}`) ||
                          !newMemberId.trim() ||
                          newMemberRoles.length === 0
                        }
                        onClick={() => void addMember(p.id)}
                      >
                        添加成员
                      </button>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}
