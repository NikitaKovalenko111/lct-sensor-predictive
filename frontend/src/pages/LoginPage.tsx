import { ArrowRight, BarChart3, Eye, EyeOff, Headphones, LockKeyhole, Settings, UserRound } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'

const demoAccounts = [
  { label: 'Диспетчер', description: 'Работа с инцидентами', username: 'dispatcher', password: 'DispatchPredict2026!', icon: Headphones },
  { label: 'Аналитик', description: 'Прогнозы и данные', username: 'analyst', password: 'AnalystPredict2026!', icon: BarChart3 },
  { label: 'Администратор', description: 'Пользователи и роли', username: 'admin', password: 'AdminPredict2026!', icon: Settings },
]

export function LoginPage() {
  const { login } = useAuth()
  const [username, setUsername] = useState('dispatcher')
  const [password, setPassword] = useState('DispatchPredict2026!')
  const [visible, setVisible] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const selectDemoAccount = (account: (typeof demoAccounts)[number]) => {
    setUsername(account.username)
    setPassword(account.password)
    setError('')
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setLoading(true)
    try { await login(username.trim(), password) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось войти') }
    finally { setLoading(false) }
  }

  return (
    <main className="login-page">
      <section className="login-stack">
        <div className="login-form-panel">
        <form className="login-form" onSubmit={submit}>
          <h2>Вход в систему</h2>

          <label className="field-label">Логин</label>
          <div className="input-wrap"><UserRound size={18} /><input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required /></div>
          <label className="field-label">Пароль</label>
          <div className="input-wrap"><LockKeyhole size={18} /><input type={visible ? 'text' : 'password'} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" minLength={12} required /><button type="button" onClick={() => setVisible((value) => !value)} aria-label="Показать пароль">{visible ? <EyeOff size={18} /> : <Eye size={18} />}</button></div>

          {error && <div className="form-error">{error}</div>}
          <button className="button button--primary button--wide" disabled={loading}>{loading ? <span className="spinner spinner--light" /> : <>Войти <ArrowRight size={18} /></>}</button>
        </form>
        </div>

        <section className="login-test-accounts">
          <div className="login-test-accounts__head"><div><strong>Тестовые аккаунты</strong><span>Нажмите, чтобы подставить данные</span></div><b>Демо</b></div>
          <div className="login-test-accounts__grid">
            {demoAccounts.map((account) => {
              const Icon = account.icon
              const active = username === account.username
              return <button type="button" className={active ? 'test-account test-account--active' : 'test-account'} key={account.username} onClick={() => selectDemoAccount(account)} aria-pressed={active}><span><Icon size={20} /></span><div><strong>{account.label}</strong><small>{account.username}</small></div></button>
            })}
          </div>
        </section>
      </section>
    </main>
  )
}
