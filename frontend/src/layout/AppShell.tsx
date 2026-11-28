import { Link, NavLink, Navigate, Outlet, useLocation } from 'react-router-dom'
import { DialogHost } from '../components/DialogHost'
import { useAppStore } from '../store/appStore'
import './shell.css'

const nav = [
  { to: '/library', label: '素材库' },
  { to: '/classes', label: 'YOLO类别' },
  { to: '/tags', label: '标签' },
  { to: '/datasets', label: '数据集' },
  { to: '/annotate', label: '标注台' },
  { to: '/versions', label: '版本' },
]

export function AppShell() {
  const theme = useAppStore((s) => s.theme)
  const flipTheme = useAppStore((s) => s.flipTheme)
  const user = useAppStore((s) => s.user)
  const logout = useAppStore((s) => s.logout)
  const projectName = useAppStore((s) => s.projectName)
  const location = useLocation()
  const onProjects = location.pathname === '/projects'

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return (
    <div className="lt-shell">
      <aside className="lt-sidebar">
        <div className="lt-brand">
          <span className="lt-brand-mark">LT</span>
          <div>
            <div className="lt-brand-name">LabelTrace</div>
            <div className="lt-brand-sub">YOLO 标注工作台</div>
          </div>
        </div>

        <div className="lt-project-context">
          <div className="lt-muted">当前项目</div>
          <Link
            to="/projects"
            className={
              onProjects ? 'lt-project-switcher active' : 'lt-project-switcher'
            }
            title="切换或创建项目"
          >
            <span className="lt-project-switcher-name">
              {projectName || '未选择项目'}
            </span>
            <span className="lt-project-switcher-action">切换</span>
          </Link>
        </div>

        <nav className="lt-nav" aria-label="项目内工作区">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                isActive ? 'lt-nav-item active' : 'lt-nav-item'
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="lt-sidebar-foot" />
      </aside>
      <div className="lt-main">
        <header className="lt-topbar">
          <div className="lt-topbar-title">
            {projectName ? (
              <>
                <span className="lt-topbar-project">{projectName}</span>
                <span className="lt-topbar-sep" aria-hidden>
                  /
                </span>
                <span>工作区</span>
              </>
            ) : (
              '选择项目'
            )}
          </div>
          <div className="lt-topbar-actions">
            <span className="lt-user-chip" title={user.id}>
              {user.username}
            </span>
            <button type="button" className="lt-btn lt-btn-ghost" onClick={logout}>
              退出
            </button>
            <button type="button" className="lt-btn lt-btn-ghost" onClick={flipTheme}>
              {theme === 'light' ? '深色' : '浅色'}
            </button>
          </div>
        </header>
        <main className="lt-content">
          <Outlet />
        </main>
      </div>
      <DialogHost />
    </div>
  )
}
