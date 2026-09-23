import { BarChart3, Download, Flame, Printer, ShieldAlert, Target, Timer } from 'lucide-react'
import { PageHeader } from '../components/common/PageHeader'
import { useData } from '../context/DataContext'
import { formatDateTime, formatPercent, predictionTypeLabel, riskLabel, statusLabel } from '../lib/format'

export function ReportsPage() {
  const { incidents, predictions, objects } = useData()
  const fire = predictions.filter((item) => item.prediction_type === 'fire_risk')
  const nsd = predictions.filter((item) => item.prediction_type === 'nsd_event' || item.prediction_type === 'nsd_risk')
  const resolved = incidents.filter((item) => item.status === 'resolved' || item.status === 'dismissed')
  const falseAlarms = incidents.filter((item) => item.status === 'dismissed').length
  const responseMinutes = resolved.map((item) => (new Date(item.updated_at).getTime() - new Date(item.created_at).getTime()) / 60_000)
  const avgResponse = responseMinutes.length ? Math.round(responseMinutes.reduce((a, b) => a + b, 0) / responseMinutes.length) : 0

  const exportCsv = () => {
    const header = ['ID', 'Тип', 'Объект', 'Вероятность', 'Уровень', 'Статус', 'Создан']
    const rows = incidents.map((item) => [item.incident_id, predictionTypeLabel[item.incident_type], objects.find((object) => object.object_id === item.object_id)?.dispatcher_name ?? item.object_id, formatPercent(item.risk_score), riskLabel[item.risk_level], statusLabel[item.status], item.created_at])
    const csv = `\uFEFF${[header, ...rows].map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(';')).join('\n')}`
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a'); link.href = url; link.download = `incident-report-${new Date().toISOString().slice(0, 10)}.csv`; link.click(); URL.revokeObjectURL(url)
  }

  return (
    <div className="page reports-page">
      <PageHeader eyebrow="Управленческая аналитика" title="Аналитика и отчёты" description="Сводка по качеству прогнозов и отработке инцидентов" actions={<><button className="button button--secondary" onClick={() => window.print()}><Printer size={16} />Печать / PDF</button><button className="button button--primary" onClick={exportCsv}><Download size={16} />Экспорт CSV</button></>} />

      <section className="metrics-grid metrics-grid--reports">
        <article className="metric-card"><span className="metric-card__icon metric-card__icon--object"><Target size={20} /></span><div><span>Точность предупреждений</span><strong>87%</strong><small>По подтверждённым исходам</small></div><b>+4%</b></article>
        <article className="metric-card"><span className="metric-card__icon"><Timer size={20} /></span><div><span>Среднее время реакции</span><strong>{avgResponse || 14} мин</strong><small>От создания до решения</small></div><b>−3 мин</b></article>
        <article className="metric-card"><span className="metric-card__icon metric-card__icon--fire"><Flame size={20} /></span><div><span>Пожарные прогнозы</span><strong>{fire.length}</strong><small>{fire.filter((item) => item.is_alert).length} тревожных</small></div><b>{formatPercent(fire.reduce((sum, item) => sum + item.risk_score, 0) / Math.max(fire.length, 1))}</b></article>
        <article className="metric-card"><span className="metric-card__icon metric-card__icon--nsd"><ShieldAlert size={20} /></span><div><span>Прогнозы НСД</span><strong>{nsd.length}</strong><small>{nsd.filter((item) => item.is_alert).length} тревожных</small></div><b>{falseAlarms} ложн.</b></article>
      </section>

      <section className="reports-grid">
        <article className="panel report-chart"><div className="panel__head"><div><p className="eyebrow">7 дней</p><h2>Прогнозы по направлениям</h2></div><BarChart3 size={20} /></div><div className="bar-chart">{weekData.map((item) => <div key={item.day}><div><i className="bar-fire" style={{ height: `${item.fire * 11}px` }} /><i className="bar-nsd" style={{ height: `${item.nsd * 11}px` }} /></div><span>{item.day}</span></div>)}</div><div className="chart-summary"><span><i className="legend-dot legend-dot--critical" />Пожароопасность</span><span><i className="legend-dot legend-dot--high" />НСД</span></div></article>
        <article className="panel report-donut"><div className="panel__head"><div><p className="eyebrow">Результат проверки</p><h2>Исходы инцидентов</h2></div></div><div className="donut-wrap"><div className="donut"><div><strong>{resolved.length}</strong><span>обработано</span></div></div><ul><li><i className="donut-color donut-color--confirmed" /><span>Подтверждено</span><b>54%</b></li><li><i className="donut-color donut-color--monitor" /><span>Наблюдение</span><b>29%</b></li><li><i className="donut-color donut-color--false" /><span>Ложные тревоги</span><b>17%</b></li></ul></div></article>
        <article className="panel report-table"><div className="panel__head"><div><p className="eyebrow">Последние результаты</p><h2>Качество прогнозирования</h2></div></div><div className="compact-table"><div className="compact-table__head"><span>Модель</span><span>Версия</span><span>Precision</span><span>Recall</span><span>Обновление</span></div><div className="compact-table__row"><strong>Пожароопасность</strong><span>1.4.2</span><b>0,91</b><b>0,86</b><span>{formatDateTime('2026-09-22T21:00:00+03:00')}</span></div><div className="compact-table__row"><strong>Событие НСД</strong><span>0.9.7</span><b>0,88</b><b>0,92</b><span>{formatDateTime('2026-09-22T21:00:00+03:00')}</span></div><div className="compact-table__row"><strong>Риск НСД</strong><span>1.1.0</span><b>0,84</b><b>0,81</b><span>{formatDateTime('2026-09-22T21:00:00+03:00')}</span></div></div></article>
      </section>
    </div>
  )
}

const weekData = [{ day: '17 сен', fire: 3, nsd: 2 }, { day: '18 сен', fire: 4, nsd: 3 }, { day: '19 сен', fire: 2, nsd: 5 }, { day: '20 сен', fire: 5, nsd: 4 }, { day: '21 сен', fire: 7, nsd: 3 }, { day: '22 сен', fire: 6, nsd: 6 }, { day: '23 сен', fire: 8, nsd: 7 }]
