import { Activity, ArrowUpRight, Building2, Clock3, Flame, RefreshCw, ShieldAlert, Siren } from 'lucide-react'
import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { RiskBadge } from '../components/common/RiskBadge'
import { PageHeader } from '../components/common/PageHeader'
import { YandexRiskMap } from '../components/dashboard/YandexRiskMap'
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
  const dashboardStats = useMemo(() => {
    const now = Date.now()
    const periodMs = 4 * 60 * 60 * 1000
    const bucketCount = 12
    const bucketMs = periodMs / bucketCount
    const periodStart = now - periodMs
    const buckets = Array.from({ length: bucketCount }, () => ({ sum: 0, count: 0 }))
    const recentPredictions = predictions.filter((prediction) => {
      const timestamp = new Date(prediction.predicted_at).getTime()
      if (!Number.isFinite(timestamp) || timestamp < periodStart || timestamp > now) return false
      const index = Math.min(bucketCount - 1, Math.floor((timestamp - periodStart) / bucketMs))
      buckets[index].sum += prediction.risk_score * 100
      buckets[index].count += 1
      return true
    })
    const values = buckets.map((bucket) => bucket.count ? bucket.sum / bucket.count : null)
    const populatedValues = buckets.filter((bucket) => bucket.count).map((bucket) => bucket.sum / bucket.count)
    const riskDelta = populatedValues.length > 1 ? populatedValues.at(-1)! - populatedValues[0] : null
    const fireCount = recentPredictions.filter((prediction) => prediction.prediction_type === 'fire_risk').length
    const nsdCount = recentPredictions.filter((prediction) => prediction.prediction_type === 'nsd_event' || prediction.prediction_type === 'nsd_risk').length
    const typedCount = fireCount + nsdCount
    const latestPrediction = [...predictions].sort((a, b) => new Date(b.predicted_at).getTime() - new Date(a.predicted_at).getTime())[0]
    const latestByObject = new Map<number, number>()
    predictions.forEach((prediction) => {
      const timestamp = new Date(prediction.predicted_at).getTime()
      if (Number.isFinite(timestamp) && timestamp > (latestByObject.get(prediction.object_id) ?? 0)) latestByObject.set(prediction.object_id, timestamp)
    })
    const freshObjects = objects.filter((object) => now - (latestByObject.get(object.object_id) ?? 0) <= 5 * 60 * 1000).length
    const freshness = objects.length ? freshObjects / objects.length : null
    const latestAgeSeconds = latestPrediction ? Math.max(0, Math.round((now - new Date(latestPrediction.predicted_at).getTime()) / 1000)) : null
    const formatTime = (timestamp: number) => new Date(timestamp).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })

    return {
      values,
      labels: [formatTime(periodStart), formatTime(periodStart + periodMs / 2), formatTime(now)] as [string, string, string],
      riskDelta,
      fireShare: typedCount ? fireCount / typedCount : null,
      nsdShare: typedCount ? nsdCount / typedCount : null,
      latestPrediction,
      freshness,
      latestAgeSeconds,
    }
  }, [objects, predictions])

  const formatAverageRisk = (items: Incident[]) => items.length
    ? formatPercent(items.reduce((sum, item) => sum + item.risk_score, 0) / items.length)
    : '—'

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
        <article className="metric-card"><span className="metric-card__icon metric-card__icon--fire"><Flame size={20} /></span><div><span>Пожароопасность</span><strong>{fire.length}</strong><small>Активных инцидентов</small></div><b>{formatAverageRisk(fire)}</b></article>
        <article className="metric-card"><span className="metric-card__icon metric-card__icon--nsd"><ShieldAlert size={20} /></span><div><span>Риски НСД</span><strong>{nsd.length}</strong><small>Активных инцидентов</small></div><b>{formatAverageRisk(nsd)}</b></article>
        <article className="metric-card"><span className="metric-card__icon metric-card__icon--object"><Building2 size={20} /></span><div><span>Объекты в контуре</span><strong>{objects.length}</strong><small>Состояние отслеживается</small></div><b>{active.length ? formatPercent(avgRisk) : '—'}</b></article>
      </section>

      <section className="dashboard-grid">
        <article className="panel panel--map">
          <div className="panel__head"><div><p className="eyebrow">География рисков</p><h2>Состояние объектов</h2></div><button className="text-button" onClick={() => navigate('/objects')}>Все объекты <ArrowUpRight size={15} /></button></div>
          <YandexRiskMap objects={objects} incidents={incidents} onSelect={openIncident} />
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
          <div className="panel__head"><div><p className="eyebrow">Последние 4 часа</p><h2>Динамика совокупного риска</h2></div><span className="trend-value"><b>{dashboardStats.riskDelta === null ? '—' : `${dashboardStats.riskDelta >= 0 ? '+' : ''}${Math.round(dashboardStats.riskDelta)} п.п.`}</b> к началу периода</span></div>
          <TrendChart values={dashboardStats.values} labels={dashboardStats.labels} />
          <div className="chart-summary"><span><i className="legend-dot legend-dot--critical" />Пожароопасность <b>{dashboardStats.fireShare === null ? '—' : formatPercent(dashboardStats.fireShare)}</b></span><span><i className="legend-dot legend-dot--high" />НСД <b>{dashboardStats.nsdShare === null ? '—' : formatPercent(dashboardStats.nsdShare)}</b></span></div>
        </article>

        <article className="panel panel--freshness">
          <div className="panel__head"><div><p className="eyebrow">Качество данных</p><h2>Актуальность прогнозов</h2></div><Activity size={19} /></div>
          <div className="freshness-score"><strong>{dashboardStats.freshness === null ? '—' : formatPercent(dashboardStats.freshness)}</strong><span>объектов с прогнозом за последние 5 минут</span></div>
          <div className="progress"><i style={{ width: `${(dashboardStats.freshness ?? 0) * 100}%` }} /></div>
          <div className="freshness-meta"><span><Clock3 size={15} /> Последний прогноз</span><b>{dashboardStats.latestPrediction ? formatDateTime(dashboardStats.latestPrediction.predicted_at) : '—'}</b></div>
          <div className="freshness-meta"><span><Activity size={15} /> Возраст последнего прогноза</span><b>{dashboardStats.latestAgeSeconds === null ? '—' : dashboardStats.latestAgeSeconds < 60 ? `${dashboardStats.latestAgeSeconds} сек` : `${Math.ceil(dashboardStats.latestAgeSeconds / 60)} мин`}</b></div>
        </article>
      </section>
    </div>
  )
}
