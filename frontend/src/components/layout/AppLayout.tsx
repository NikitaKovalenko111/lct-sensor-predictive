import {
  Activity,
  BarChart3,
  Bell,
  Building2,
  ChevronDown,
  Flame,
  LayoutDashboard,
  LogOut,
  Menu,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  X,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { useData } from '../../context/DataContext'
import { formatDateTime, predictionTypeShortLabel, roleLabel } from '../../lib/format'

const navigation = [
  { to: '/', label: 'Обзор', icon: LayoutDashboard, end: true },
  { to: '/predictions', label: 'Прогнозы', icon: Activity },
  { to: '/incidents', label: 'Инциденты', icon: ShieldAlert },
  { to: '/objects', label: 'Объекты', icon: Building2 },
  { to: '/reports', label: 'Аналитика', icon: BarChart3 },
]

export function AppLayout() {
  const { user, logout } = useAuth()
  const { incidents, predictions, error, refresh } = useData()
  const [menuOpen, setMenuOpen] = useState(false)
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const navigate = useNavigate()
  const critical = useMemo(() => incidents.filter((item) => item.status === 'new' && item.risk_level === 'critical'), [incidents])
  const latest = predictions.filter((item) => item.is_alert).slice(0, 4)

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${menuOpen ? 'sidebar--open' : ''}`}>
        <div className="brand">
          <div className="brand__mark"><ShieldCheck size={22} /></div>
          <div><strong>КОНТУР</strong><span>АО «Москоллектор»</span></div>
          <button className="icon-button sidebar__close" onClick={() => setMenuOpen(false)} aria-label="Закрыть меню"><X size={20} /></button>
        </div>

        <div className="sidebar__context">
          <span className="live-dot" />
          <div><strong>Контур наблюдения</strong><span>Система работает штатно</span></div>
        </div>

        <nav className="sidebar__nav">
          <p className="sidebar__label">Рабочее пространство</p>
          {navigation.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} onClick={() => setMenuOpen(false)} className={({ isActive }) => `nav-item ${isActive ? 'nav-item--active' : ''}`}>
              <Icon size={19} /> <span>{label}</span>
              {to === '/incidents' && critical.length > 0 && <b>{critical.length}</b>}
            </NavLink>
          ))}
          {user?.role === 'admin' && (
            <>
              <p className="sidebar__label sidebar__label--spaced">Система</p>
              <NavLink to="/admin" onClick={() => setMenuOpen(false)} className={({ isActive }) => `nav-item ${isActive ? 'nav-item--active' : ''}`}>
                <SlidersHorizontal size={19} /><span>Администрирование</span>
              </NavLink>
            </>
          )}
        </nav>

        <div className="sidebar__footer">
          <div className="sidebar__user"><div className="avatar">{user?.username.slice(0, 2).toUpperCase()}</div><div><strong>{user?.username}</strong><span>{user && roleLabel[user.role]}</span></div></div>
          <button className="icon-button" onClick={handleLogout} title="Выйти"><LogOut size={18} /></button>
        </div>
      </aside>

      {menuOpen && <button className="sidebar-backdrop" onClick={() => setMenuOpen(false)} aria-label="Закрыть меню" />}

      <div className="workspace">
        <header className="topbar">
          <button className="icon-button topbar__menu" onClick={() => setMenuOpen(true)} aria-label="Открыть меню"><Menu size={21} /></button>
          <div className="topbar__status"><span className="live-dot" /><span>Данные обновлены</span><strong>{new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}</strong></div>
          <div className="topbar__actions">
            <div className="notifications-wrap">
              <button className="icon-button icon-button--notification" onClick={() => setNotificationsOpen((value) => !value)} aria-label="Уведомления">
                <Bell size={19} />{critical.length > 0 && <span>{critical.length}</span>}
              </button>
              {notificationsOpen && (
                <div className="notifications-popover">
                  <div className="popover-head"><div><p className="eyebrow">Оповещения</p><h3>Последние сигналы</h3></div><button className="icon-button" onClick={() => setNotificationsOpen(false)}><X size={17} /></button></div>
                  <div className="notification-list">
                    {latest.map((item) => (
                      <button key={item.prediction_id} onClick={() => { setNotificationsOpen(false); navigate(`/predictions?object=${item.object_id}`) }}>
                        <span className={`notification-icon notification-icon--${item.prediction_type === 'fire_risk' ? 'fire' : 'nsd'}`}>{item.prediction_type === 'fire_risk' ? <Flame size={17} /> : <ShieldAlert size={17} />}</span>
                        <div><strong>{predictionTypeShortLabel[item.prediction_type]}</strong><span>Объект №{item.object_id} · {formatDateTime(item.predicted_at)}</span></div>
                      </button>
                    ))}
                  </div>
                  <button className="popover-link" onClick={() => { setNotificationsOpen(false); navigate('/incidents') }}>Открыть центр инцидентов <ChevronDown size={16} /></button>
                </div>
              )}
            </div>
            <div className="topbar__identity"><div className="avatar">{user?.username.slice(0, 2).toUpperCase()}</div><div><strong>{user?.username}</strong><span>{user && roleLabel[user.role]}</span></div></div>
          </div>
        </header>

        {error && <div className="global-error">{error}<button onClick={() => void refresh()}>Повторить</button></div>}
        <main className="workspace__content"><Outlet /></main>
      </div>
    </div>
  )
}
