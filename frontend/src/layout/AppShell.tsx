import { NavLink, Outlet } from 'react-router-dom'
import { useAppStore } from '../store/appStore'
import './shell.css'

const nav = [
  { to: '/', end: true, label: '项目' },
  { to: '/library', label: '素材库' },
  { to: '/datasets', label: '数据集' },
  { to: '/annotate', label: '标注台' },
  { to: '/versions', label: '版本' },
]

export function AppShell() {
  const theme = useAppStore((s) => s.theme)
  const flipTheme = useAppStore((s) => s.flipTheme)
  const userId = useAppStore((s) => s.userId)
  const setUserId = useAppStore((s) => s.setUserId)
  const projectName = useAppStore((s) => s.projectName)

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
        <nav className="lt-nav">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                isActive ? 'lt-nav-item active' : 'lt-nav-item'
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="lt-sidebar-foot">
          <div className="lt-muted">
            当前项目
            <div className="lt-project-chip">{projectName || '未选择'}</div>
          </div>
        </div>
      </aside>
      <div className="lt-main">
        <header className="lt-topbar">
          <div className="lt-topbar-title">工作区</div>
          <div className="lt-topbar-actions">
            <label className="lt-user-field">
              <span>用户</span>
              <input
                className="lt-input"
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                title="X-User-Id"
              />
            </label>
            <button type="button" className="lt-btn lt-btn-ghost" onClick={flipTheme}>
              {theme === 'light' ? '深色' : '浅色'}
            </button>
          </div>
        </header>
        <main className="lt-content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
