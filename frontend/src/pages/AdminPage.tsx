import { FileClock, Plus, ServerCog, ShieldCheck, Trash2, Users, X } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../api/client'
import { apiRuntime } from '../api/runtime'
import { PageHeader } from '../components/common/PageHeader'
import { useAuth } from '../context/AuthContext'
import { formatFullDateTime, roleLabel } from '../lib/format'
import type { AuditEntry, BackendStatus, Role, User } from '../types/api'

const roles: Role[] = ['dispatcher', 'analyst', 'admin']

export function AdminPage() {
  const { user: currentUser } = useAuth()
  const [tab, setTab] = useState<'users' | 'audit' | 'system'>('users')
  const [users, setUsers] = useState<User[]>([])
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [modalOpen, setModalOpen] = useState(false)
  const [error, setError] = useState('')
  const [busyUserId, setBusyUserId] = useState('')
  const [backendStatus, setBackendStatus] = useState<BackendStatus | null>(null)

  const load = async () => {
    const [userPage, auditPage] = await Promise.all([api.listUsers(), api.listAudit()])
    setUsers(userPage.items)
    setAudit(auditPage.items)
  }

  useEffect(() => { void load() }, [])
  useEffect(() => {
    if (tab !== 'system') return
    void api.getBackendStatus().then(setBackendStatus).catch(() => setBackendStatus({ live: false, ready: false }))
  }, [tab])

  const changeRole = async (user: User, role: Role) => {
    setError('')
    setBusyUserId(user.user_id)
    try {
      await api.updateUserRole(user.user_id, role)
      await load()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось изменить роль')
    } finally {
      setBusyUserId('')
    }
  }

  const removeUser = async (user: User) => {
    if (!window.confirm(`Удалить пользователя «${user.username}»?`)) return
    setError('')
    setBusyUserId(user.user_id)
    try {
      await api.deleteUser(user.user_id)
      await load()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось удалить пользователя')
    } finally {
      setBusyUserId('')
    }
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow="Системное управление"
        title="Администрирование"
        description="Пользователи, роли, аудит действий и готовность интеграций"
        actions={tab === 'users' && <button className="button button--primary" onClick={() => setModalOpen(true)}><Plus size={18} />Добавить пользователя</button>}
      />

      <nav className="section-tabs">
        <button className={tab === 'users' ? 'active' : ''} onClick={() => setTab('users')}><Users size={19} />Пользователи и роли</button>
        <button className={tab === 'audit' ? 'active' : ''} onClick={() => setTab('audit')}><FileClock size={19} />Журнал аудита</button>
        <button className={tab === 'system' ? 'active' : ''} onClick={() => setTab('system')}><ServerCog size={19} />Система</button>
      </nav>

      {error && <div className="global-error admin-error">{error}</div>}

      {tab === 'users' && (
        <section className="panel admin-table">
          <div className="compact-table compact-table--users">
            <div className="compact-table__head"><span>Пользователь</span><span>Роль</span><span>Статус</span><span>Последний вход</span><span>Действия</span></div>
            {users.map((user) => (
              <div className="compact-table__row" key={user.user_id}>
                <strong>{user.username}</strong>
                <select className="role-select" value={user.role} disabled={busyUserId === user.user_id || currentUser?.user_id === user.user_id} onChange={(event) => void changeRole(user, event.target.value as Role)} aria-label={`Роль пользователя ${user.username}`} title={currentUser?.user_id === user.user_id ? 'Нельзя изменить собственную роль' : undefined}>
                  {roles.map((role) => <option key={role} value={role}>{roleLabel[role]}</option>)}
                </select>
                <span className={user.active ? 'table-normal' : 'table-alarm'}>{user.active ? 'Активен' : 'Отключён'}</span>
                <span>{user.last_login_at ? formatFullDateTime(user.last_login_at) : 'Ещё не входил'}</span>
                <button className="delete-user-button" disabled={currentUser?.user_id === user.user_id || busyUserId === user.user_id} onClick={() => void removeUser(user)} title={currentUser?.user_id === user.user_id ? 'Нельзя удалить текущего пользователя' : 'Удалить пользователя'}><Trash2 size={17} />Удалить</button>
              </div>
            ))}
          </div>
        </section>
      )}

      {tab === 'audit' && (
        <section className="panel admin-table">
          <div className="compact-table compact-table--audit">
            <div className="compact-table__head"><span>Время</span><span>Пользователь</span><span>Действие</span><span>Ресурс</span><span>Адрес</span></div>
            {audit.map((entry) => <div className="compact-table__row" key={entry.audit_id}><span>{formatFullDateTime(entry.created_at)}</span><strong>{entry.username}</strong><span>{auditLabels[entry.action] ?? entry.action}</span><span>{entry.resource_type}{entry.resource_id ? ` · ${entry.resource_id.slice(0, 8)}` : ''}</span><span>{entry.remote_ip ?? '—'}</span></div>)}
          </div>
        </section>
      )}

      {tab === 'system' && (
        <section className="system-grid">
          <article className="panel system-card"><span className="system-card__icon"><ShieldCheck size={23} /></span><div><p className="eyebrow">Backend API</p><h3>{apiRuntime.mode === 'live' ? 'Подключён к API' : 'Демонстрационные данные'}</h3><p>{apiRuntime.mode === 'live' ? `Готовность зависимостей: ${backendStatus?.ready ? 'подтверждена' : 'не подтверждена'}.` : 'Интерфейс работает автономно.'}</p></div><b className={backendStatus?.live || apiRuntime.mode === 'mock' ? 'table-normal' : 'table-alarm'}>{backendStatus === null ? 'Проверка' : backendStatus.live ? 'Доступен' : 'Недоступен'}</b></article>
          <article className="panel system-card"><span className="system-card__icon"><ServerCog size={23} /></span><div><p className="eyebrow">Поток инцидентов</p><h3>Server-Sent Events</h3><p>Защищённый поток использует Bearer-токен и автоматически переподключается.</p></div><b className={apiRuntime.incidentStreamEnabled ? 'table-normal' : ''}>{apiRuntime.incidentStreamEnabled ? 'Включён' : 'Выключен'}</b></article>
        </section>
      )}

      {modalOpen && <CreateUserModal onClose={() => setModalOpen(false)} onCreated={async () => { await load(); setModalOpen(false) }} />}
    </div>
  )
}

const auditLabels: Record<string, string> = {
  'incident.assign': 'Назначен ответственный',
  'incident.decide': 'Решение по инциденту',
  'incident.resolve': 'Инцидент закрыт',
  'work_order.upsert_draft': 'Черновик заявки обновлён',
  'prediction.request': 'Запрошен прогноз',
  'sensor_event.publish': 'Событие датчика опубликовано',
  'user.create': 'Пользователь создан',
  'user.role.update': 'Роль пользователя изменена',
  'user.delete': 'Пользователь удалён',
  'auth.login.succeeded': 'Успешный вход',
  'auth.login.failed': 'Ошибка входа',
  'incident.decision.created': 'Решение по инциденту',
  'incident.assigned': 'Назначен ответственный',
  'auth.login.success': 'Успешный вход',
}

function CreateUserModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => Promise<void> }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<Role>('dispatcher')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      await api.createUser({ username, password, role })
      await onCreated()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Ошибка создания')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-layer">
      <button className="modal-backdrop" onClick={onClose} aria-label="Закрыть окно" />
      <form className="modal" onSubmit={submit}>
        <header><div><p className="eyebrow">Новая учётная запись</p><h2>Добавить пользователя</h2></div><button type="button" className="icon-button" onClick={onClose}><X size={21} /></button></header>
        <label className="field-label">Логин</label>
        <input className="input" value={username} onChange={(event) => setUsername(event.target.value)} required />
        <label className="field-label">Пароль</label>
        <input className="input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={12} required placeholder="Не менее 12 символов" />
        <label className="field-label">Роль</label>
        <select className="input" value={role} onChange={(event) => setRole(event.target.value as Role)}>{roles.map((item) => <option key={item} value={item}>{roleLabel[item]}</option>)}</select>
        {error && <div className="form-error">{error}</div>}
        <footer><button type="button" className="button button--ghost" onClick={onClose}>Отмена</button><button className="button button--primary" disabled={busy}>Создать пользователя</button></footer>
      </form>
    </div>
  )
}
