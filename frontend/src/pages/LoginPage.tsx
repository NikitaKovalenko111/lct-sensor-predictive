import { ArrowRight, Eye, EyeOff, Flame, LockKeyhole, ShieldCheck, UserRound } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'

const demoAccounts = [
  { label: 'Диспетчер', username: 'dispatcher', password: 'DispatchPredict2026!' },
  { label: 'Аналитик', username: 'analyst', password: 'AnalystPredict2026!' },
  { label: 'Администратор', username: 'admin', password: 'AdminPredict2026!' },
]

export function LoginPage() {
  const { login } = useAuth()
  const [username, setUsername] = useState('dispatcher')
  const [password, setPassword] = useState('DispatchPredict2026!')
  const [visible, setVisible] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

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
      <section className="login-visual">
        <div className="login-brand"><span><ShieldCheck size={24} /></span><strong>КОНТУР</strong></div>
        <div className="login-visual__content">
          <p className="eyebrow eyebrow--light">Предиктивный мониторинг</p>
          <h1>Риск виден<br />до инцидента.</h1>
          <p>Единое рабочее пространство для контроля пожароопасности и несанкционированного доступа в инженерных коллекторах Москвы.</p>
          <div className="login-features">
            <div><span><Flame size={20} /></span><div><strong>Пожароопасность</strong><p>Раннее выявление температурных и дымовых аномалий</p></div></div>
            <div><span><LockKeyhole size={20} /></span><div><strong>Контроль НСД</strong><p>Оценка риска и фиксация вероятных событий доступа</p></div></div>
          </div>
        </div>
        <p className="login-visual__footer">АО «Москоллектор» · технологический прототип</p>
      </section>

      <section className="login-form-panel">
        <form className="login-form" onSubmit={submit}>
          <p className="eyebrow">Защищённый контур</p>
          <h2>Вход в систему</h2>
          <p className="login-form__lead">Используйте корпоративную учётную запись</p>

          <label className="field-label">Логин</label>
          <div className="input-wrap"><UserRound size={18} /><input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required /></div>
          <label className="field-label">Пароль</label>
          <div className="input-wrap"><LockKeyhole size={18} /><input type={visible ? 'text' : 'password'} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" minLength={12} required /><button type="button" onClick={() => setVisible((value) => !value)} aria-label="Показать пароль">{visible ? <EyeOff size={18} /> : <Eye size={18} />}</button></div>

          {error && <div className="form-error">{error}</div>}
          <button className="button button--primary button--wide" disabled={loading}>{loading ? <span className="spinner spinner--light" /> : <>Войти <ArrowRight size={18} /></>}</button>

          <div className="demo-accounts">
            <span>Демо-доступ</span>
            <div>{demoAccounts.map((account) => <button type="button" key={account.username} onClick={() => { setUsername(account.username); setPassword(account.password) }}>{account.label}</button>)}</div>
          </div>
        </form>
      </section>
    </main>
  )
}
