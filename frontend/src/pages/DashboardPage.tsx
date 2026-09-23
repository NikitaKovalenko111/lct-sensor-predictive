import { Activity, ArrowUpRight, Building2, Clock3, Flame, RefreshCw, ShieldAlert, Siren } from 'lucide-react'
import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { RiskBadge } from '../components/common/RiskBadge'
import { PageHeader } from '../components/common/PageHeader'
import { RiskMap } from '../components/dashboard/RiskMap'
import { TrendChart } from '../components/dashboard/TrendChart'
import { useData } from '../context/DataContext'
import { formatDateTime, formatPercent, getHorizonHours, predictionTypeShortLabel, statusLabel } from '../lib/format'
import type { Incident } from '../types/api'

export function DashboardPage() {
  const { incidents, predictions, objects, loading, refresh } = useData()
  const navigate = useNavigate()
  const active = incidents.filter((item) => item.status === 'new' || item.status === 'in_review')
  const critical = active.filter((item) => item.risk_level === 'critical')
  const fire = active.filter((item) => item.incident_type === 'fire_risk')
  const nsd = active.filter((item) => item.incident_type === 'nsd_event' || item.incident_type === 'nsd_risk')
  const topIncidents = [...active].sort((a, b) => b.risk_score - a.risk_score).slice(0, 4)
  const avgRisk = active.length ? active.reduce((sum, item) => sum + item.risk_score, 0) / active.length : 0
  const latestPrediction = useMemo(() => predictions[0], [predictions])

  const openIncident = (incident: Incident) => navigate(`/incidents?selected=${incident.incident_id}`)

  return (
    <div className="page">
      <PageHeader
        eyebrow="Оперативная обстановка"
        title="Центр предиктивного мониторинга"
        description="Пожароопасность и несанкционированный доступ · Московский контур"
        actions={<button className="button button--secondary" onClick={() => void refresh()} disabled={loading}><RefreshCw size={16} className={loading ? 'spin' : ''} />Обновить данные</button>}
      />

      <section className="metrics-grid">
        <article className="metric-card metric-card--danger"><span className="metric-card__icon"><Siren size={20} /></span><div><span>Критические сигналы</span><strong>{critical.length}</strong><small>Требуют реакции</small></div><b>сейчас</b></article>
        <article className="metric-card"><span className="metric-card__icon metric-card__icon--fire"><Flame size={20} /></span><div><span>Пожароопасность</span><strong>{fire.length}</strong><small>Активных прогнозов</small></div><b>{fire.length ? '↑ 1' : 'норма'}</b></article>
        <article className="metric-card"><span className="metric-card__icon metric-card__icon--nsd"><ShieldAlert size={20} /></span><div><span>Риски НСД</span><strong>{nsd.length}</strong><small>События и риски</small></div><b>{nsd.length ? '↑ 2' : 'норма'}</b></article>
        <article className="metric-card"><span className="metric-card__icon metric-card__icon--object"><Building2 size={20} /></span><div><span>Объекты в контуре</span><strong>{objects.length}</strong><small>Состояние отслеживается</small></div><b>{formatPercent(avgRisk)}</b></article>
      </section>

      <section className="dashboard-grid">
        <article className="panel panel--map">
          <div className="panel__head"><div><p className="eyebrow">География рисков</p><h2>Состояние объектов</h2></div><button className="text-button" onClick={() => navigate('/objects')}>Все объекты <ArrowUpRight size={15} /></button></div>
          <RiskMap objects={objects} incidents={incidents} onSelect={openIncident} />
        </article>

        <article className="panel panel--incidents">
          <div className="panel__head"><div><p className="eyebrow">Очередь диспетчера</p><h2>Приоритетные инциденты</h2></div><span className="counter">{active.length}</span></div>
          <div className="priority-list">
            {topIncidents.map((incident) => {
              const object = objects.find((item) => item.object_id === incident.object_id)
              const prediction = predictions.find((item) => item.prediction_id === incident.prediction_id)
              return <button key={incident.incident_id} onClick={() => openIncident(incident)} className="priority-item">
                <span className={`priority-item__symbol priority-item__symbol--${incident.incident_type === 'fire_risk' ? 'fire' : 'nsd'}`}>{incident.incident_type === 'fire_risk' ? <Flame size={19} /> : <ShieldAlert size={19} />}</span>
                <div><span className="priority-item__meta">{predictionTypeShortLabel[incident.incident_type]} · {statusLabel[incident.status]}</span><strong>{incident.title}</strong><small>{object?.dispatcher_name ?? `Объект №${incident.object_id}`} · прогноз {prediction ? getHorizonHours(prediction.features_used) : 24} ч</small></div>
                <div className="priority-item__risk"><strong>{formatPercent(incident.risk_score)}</strong><RiskBadge level={incident.risk_level} compact /></div>
              </button>
            })}
          </div>
          <button className="panel__footer-link" onClick={() => navigate('/incidents')}>Перейти ко всем инцидентам <ArrowUpRight size={15} /></button>
        </article>

        <article className="panel panel--trend">
          <div className="panel__head"><div><p className="eyebrow">Последние 4 часа</p><h2>Динамика совокупного риска</h2></div><span className="trend-value"><b>+18%</b> к 12:00</span></div>
          <TrendChart />
          <div className="chart-summary"><span><i className="legend-dot legend-dot--critical" />Пожароопасность <b>61%</b></span><span><i className="legend-dot legend-dot--high" />НСД <b>39%</b></span></div>
        </article>

        <article className="panel panel--freshness">
          <div className="panel__head"><div><p className="eyebrow">Качество данных</p><h2>Актуальность контура</h2></div><Activity size={19} /></div>
          <div className="freshness-score"><strong>98,7%</strong><span>каналов передают данные вовремя</span></div>
          <div className="progress"><i style={{ width: '98.7%' }} /></div>
          <div className="freshness-meta"><span><Clock3 size={15} /> Последний прогноз</span><b>{latestPrediction ? formatDateTime(latestPrediction.predicted_at) : '—'}</b></div>
          <div className="freshness-meta"><span><Activity size={15} /> Задержка обработки</span><b>42 сек</b></div>
        </article>
      </section>
    </div>
  )
}
