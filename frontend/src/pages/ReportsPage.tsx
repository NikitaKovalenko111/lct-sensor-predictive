import { BarChart3, Download, Flame, Printer, ShieldAlert, Target, Timer } from 'lucide-react'
import { useMemo } from 'react'
import { PageHeader } from '../components/common/PageHeader'
import { useData } from '../context/DataContext'
import { formatDateTime, formatPercent, predictionTypeLabel, riskLabel, statusLabel } from '../lib/format'
import type { PredictionType } from '../types/api'

const dayKey = (date: Date) => [
  date.getFullYear(),
  String(date.getMonth() + 1).padStart(2, '0'),
  String(date.getDate()).padStart(2, '0'),
].join('-')

const percent = (value: number, total: number) => total ? Math.round(value / total * 100) : 0

export function ReportsPage() {
  const { incidents, predictions, objects } = useData()
  const analytics = useMemo(() => {
    const now = new Date()
    const days = Array.from({ length: 7 }, (_, index) => {
      const date = new Date(now)
      date.setHours(0, 0, 0, 0)
      date.setDate(date.getDate() - 6 + index)
      return {
        key: dayKey(date),
        day: date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }).replace('.', ''),
        fire: 0,
        nsd: 0,
      }
    })
    const dayByKey = new Map(days.map((item) => [item.key, item]))
    for (const prediction of predictions) {
      const day = dayByKey.get(dayKey(new Date(prediction.predicted_at)))
      if (!day) continue
      if (prediction.prediction_type === 'fire_risk') day.fire++
      if (prediction.prediction_type === 'nsd_event' || prediction.prediction_type === 'nsd_risk') day.nsd++
    }

    const confirmed = incidents.filter((item) => item.status === 'resolved').length
    const falseAlarms = incidents.filter((item) => item.status === 'dismissed').length
    const monitoring = incidents.filter((item) => item.status === 'in_review').length
    const processed = confirmed + falseAlarms + monitoring
    const evaluated = confirmed + falseAlarms
    const responseMinutes = incidents
      .filter((item) => item.status === 'resolved' || item.status === 'dismissed')
      .map((item) => (new Date(item.resolved_at ?? item.updated_at).getTime() - new Date(item.created_at).getTime()) / 60_000)
      .filter((value) => Number.isFinite(value) && value >= 0)
    const avgResponse = responseMinutes.length
      ? Math.round(responseMinutes.reduce((sum, value) => sum + value, 0) / responseMinutes.length)
      : null

    const modelTypes: PredictionType[] = ['fire_risk', 'nsd_event', 'nsd_risk', 'equipment_failure']
    const modelRows = modelTypes.flatMap((type) => {
      const typed = predictions.filter((item) => item.prediction_type === type)
      if (!typed.length) return []
      const latest = [...typed].sort((left, right) =>
        new Date(right.predicted_at).getTime() - new Date(left.predicted_at).getTime())[0]
      const versionItems = typed.filter((item) => item.model_version === latest.model_version)
      return [{
        type,
        version: latest.model_version,
        predictions: versionItems.length,
        alerts: versionItems.filter((item) => item.is_alert === true).length,
        updatedAt: latest.predicted_at,
      }]
    })

    return {
      days,
      confirmed,
      falseAlarms,
      monitoring,
      processed,
      accuracy: evaluated ? confirmed / evaluated : null,
      avgResponse,
      responseSamples: responseMinutes.length,
      modelRows,
    }
  }, [incidents, predictions])

  const fire = predictions.filter((item) => item.prediction_type === 'fire_risk')
  const nsd = predictions.filter((item) => item.prediction_type === 'nsd_event' || item.prediction_type === 'nsd_risk')
  const maxDaily = Math.max(1, ...analytics.days.flatMap((item) => [item.fire, item.nsd]))
  const confirmedPct = percent(analytics.confirmed, analytics.processed)
  const monitoringPct = percent(analytics.monitoring, analytics.processed)
  const falsePct = analytics.processed ? Math.max(0, 100 - confirmedPct - monitoringPct) : 0
  const confirmedStop = confirmedPct
  const monitoringStop = confirmedPct + monitoringPct

  const exportCsv = () => {
    const header = ['ID', 'Тип', 'Объект', 'Вероятность', 'Уровень', 'Статус', 'Создан']
    const rows = incidents.map((item) => [item.incident_id, predictionTypeLabel[item.incident_type], objects.find((object) => object.object_id === item.object_id)?.dispatcher_name ?? item.object_id, formatPercent(item.risk_score), riskLabel[item.risk_level], statusLabel[item.status], item.created_at])
    const csv = `\uFEFF${[header, ...rows].map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(';')).join('\n')}`
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a'); link.href = url; link.download = `incident-report-${new Date().toISOString().slice(0, 10)}.csv`; link.click(); URL.revokeObjectURL(url)
  }

  return (
    <div className="page reports-page">
      <PageHeader eyebrow="Управленческая аналитика" title="Аналитика и отчёты" description="Сводка по фактическим прогнозам и отработке инцидентов" actions={<><button className="button button--secondary" onClick={() => window.print()}><Printer size={16} />Печать / PDF</button><button className="button button--primary" onClick={exportCsv}><Download size={16} />Экспорт CSV</button></>} />

      <section className="metrics-grid metrics-grid--reports">
        <article className="metric-card"><span className="metric-card__icon metric-card__icon--object"><Target size={20} /></span><div><span>Завершено без отклонения</span><strong>{analytics.accuracy === null ? '—' : formatPercent(analytics.accuracy)}</strong><small>{analytics.confirmed + analytics.falseAlarms} завершённых проверок</small></div><b>{analytics.confirmed} заверш.</b></article>
        <article className="metric-card"><span className="metric-card__icon"><Timer size={20} /></span><div><span>Среднее время реакции</span><strong>{analytics.avgResponse === null ? '—' : `${analytics.avgResponse} мин`}</strong><small>От создания до завершения</small></div><b>{analytics.responseSamples} замеров</b></article>
        <article className="metric-card"><span className="metric-card__icon metric-card__icon--fire"><Flame size={20} /></span><div><span>Пожарные прогнозы</span><strong>{fire.length}</strong><small>{fire.filter((item) => item.is_alert).length} тревожных</small></div><b>{fire.length ? formatPercent(fire.reduce((sum, item) => sum + item.risk_score, 0) / fire.length) : '—'}</b></article>
        <article className="metric-card"><span className="metric-card__icon metric-card__icon--nsd"><ShieldAlert size={20} /></span><div><span>Прогнозы НСД</span><strong>{nsd.length}</strong><small>{nsd.filter((item) => item.is_alert).length} тревожных</small></div><b>{nsd.length ? formatPercent(nsd.reduce((sum, item) => sum + item.risk_score, 0) / nsd.length) : '—'}</b></article>
      </section>

      <section className="reports-grid">
        <article className="panel report-chart"><div className="panel__head"><div><p className="eyebrow">Последние 7 дней</p><h2>Прогнозы по направлениям</h2></div><BarChart3 size={20} /></div><div className="bar-chart">{analytics.days.map((item) => <div key={item.key}><div><i className="bar-fire" style={{ height: item.fire ? `${Math.max(5, item.fire / maxDaily * 150)}px` : 0 }} /><i className="bar-nsd" style={{ height: item.nsd ? `${Math.max(5, item.nsd / maxDaily * 150)}px` : 0 }} /></div><span>{item.day}</span></div>)}</div><div className="chart-summary"><span><i className="legend-dot legend-dot--critical" />Пожароопасность</span><span><i className="legend-dot legend-dot--high" />НСД</span></div></article>
        <article className="panel report-donut"><div className="panel__head"><div><p className="eyebrow">Фактические статусы</p><h2>Исходы инцидентов</h2></div></div><div className="donut-wrap"><div className="donut" style={{ background: analytics.processed ? `conic-gradient(#2d8b69 0 ${confirmedStop}%, #4d8cad ${confirmedStop}% ${monitoringStop}%, #d98a27 ${monitoringStop}% 100%)` : '#e8ecef' }}><div><strong>{analytics.processed}</strong><span>обработано</span></div></div><ul><li><i className="donut-color donut-color--confirmed" /><span>Подтверждено</span><b>{confirmedPct}%</b></li><li><i className="donut-color donut-color--monitor" /><span>Наблюдение</span><b>{monitoringPct}%</b></li><li><i className="donut-color donut-color--false" /><span>Ложные тревоги</span><b>{falsePct}%</b></li></ul></div></article>
        <article className="panel report-table"><div className="panel__head"><div><p className="eyebrow">Фактические запуски</p><h2>Статистика моделей</h2></div></div><div className="compact-table"><div className="compact-table__head"><span>Модель</span><span>Версия</span><span>Прогнозов</span><span>Тревог</span><span>Последний прогноз</span></div>{analytics.modelRows.map((row) => <div className="compact-table__row" key={row.type}><strong>{predictionTypeLabel[row.type]}</strong><span>{row.version}</span><b>{row.predictions}</b><b>{row.alerts}</b><span>{formatDateTime(row.updatedAt)}</span></div>)}</div></article>
      </section>
    </div>
  )
}
