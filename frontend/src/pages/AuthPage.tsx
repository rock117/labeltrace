import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { api, type AuthUser } from '../lib/api'
import { useAppStore } from '../store/appStore'
import { formatError } from '../hooks/useAsync'
import { StateBlock } from '../components/StateBlock'

type Mode = 'login' | 'register'

type TokenOut = {
  access_token: string
  user: AuthUser
}

export function AuthPage() {
  const navigate = useNavigate()
  const user = useAppStore((s) => s.user)
  const setAuth = useAppStore((s) => s.setAuth)
  const [mode, setMode] = useState<Mode>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (user) return <Navigate to="/projects" replace />

  const submit = async () => {
    if (!username.trim() || !password) return
    setBusy(true)
    setError(null)
    try {
      const path = mode === 'login' ? '/v1/auth/login' : '/v1/auth/register'
      const out = await api<TokenOut>(path, {
        method: 'POST',
        body: JSON.stringify({
          username: username.trim(),
          password,
        }),
      })
      setAuth(out.access_token, out.user)
      navigate('/projects', { replace: true })
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="lt-auth">
      <div className="lt-auth-card lt-panel">
        <div className="lt-brand" style={{ marginBottom: '1.25rem' }}>
          <span className="lt-brand-mark">LT</span>
          <div>
            <div className="lt-brand-name">LabelTrace</div>
            <div className="lt-brand-sub">注册账号后创建项目与标注</div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8, marginBottom: '1rem' }}>
          <button
            type="button"
            className={mode === 'login' ? 'lt-btn lt-btn-primary' : 'lt-btn'}
            onClick={() => setMode('login')}
          >
            登录
          </button>
          <button
            type="button"
            className={mode === 'register' ? 'lt-btn lt-btn-primary' : 'lt-btn'}
            onClick={() => setMode('register')}
          >
            注册
          </button>
        </div>

        {error ? (
          <StateBlock tone="error" title="失败" description={error} />
        ) : null}

        <label className="lt-field">
          <span>用户名</span>
          <input
            className="lt-input"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && void submit()}
          />
        </label>
        <label className="lt-field">
          <span>密码{mode === 'register' ? '（至少 6 位）' : ''}</span>
          <input
            className="lt-input"
            type="password"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && void submit()}
          />
        </label>
        <button
          type="button"
          className="lt-btn lt-btn-primary"
          style={{ width: '100%', marginTop: '0.75rem' }}
          disabled={busy || !username.trim() || password.length < (mode === 'register' ? 6 : 1)}
          onClick={() => void submit()}
        >
          {busy ? '提交中…' : mode === 'login' ? '登录' : '注册并进入'}
        </button>
        <p style={{ margin: '1rem 0 0', fontSize: 13, color: 'var(--lt-fg-muted)' }}>
          注册后你是平台用户；创建项目后自动成为该项目负责人。其他人需先注册，再由负责人在项目成员里按用户名邀请并勾选角色。
        </p>
      </div>
    </div>
  )
}
