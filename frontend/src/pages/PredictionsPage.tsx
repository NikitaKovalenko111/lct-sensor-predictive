import { Activity, Filter, Flame, RefreshCw, Search, ShieldAlert, Sparkles } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { EmptyState } from '../components/common/EmptyState'
import { PageHeader } from '../components/common/PageHeader'
import { RiskBadge } from '../components/common/RiskBadge'
import { useData } from '../context/DataContext'
import { formatDateTime, formatPercent, getHorizonHours, getRecommendation, predictionTypeLabel } from '../lib/format'
import type { PredictionType, RiskLevel } from '../types/api'

type TypeFilter = 'all' | Extract<PredictionType, 'fire_risk' | 'nsd_event' | 'nsd_risk'>
type RiskFilter = 'all' | RiskLevel

export function PredictionsPage() {
  const { predictions, objects, loading, refresh } = useData()
  const [params] = useSearchParams()
  const [search, setSearch] = useState(params.get('object') ?? '')
  const [type, setType] = useState<TypeFilter>('all')
  const [risk, setRisk] = useState<RiskFilter>('all')
  const [alertsOnly, setAlertsOnly] = useState(false)

  const filtered = useMemo(() => predictions.filter((prediction) => {
    const object = objects.find((item) => item.object_id === prediction.object_id)
    const matchesSearch = !search || String(prediction.object_id).includes(search) || object?.dispatcher_name.toLowerCase().includes(search.toLowerCase())
    return matchesSearch && (type === 'all' || prediction.prediction_type === type) && (risk === 'all' || prediction.risk_level === risk) && (!alertsOnly || prediction.is_alert)
  }), [predictions, objects, search, type, risk, alertsOnly])

  return (
    <div className="page">
      <PageHeader eyebrow="Журнал модели" title="Прогнозы" description="Результаты моделей пожароопасности и несанкционированного доступа" actions={<button className="button button--secondary" onClick={() => void refresh()}><RefreshCw size={16} className={loading ? 'spin' : ''} />Запросить обновление</button>} />

      <section className="filter-bar">
        <div className="search-field"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Объект или идентификатор" /></div>
        <div className="select-wrap"><Filter size={16} /><select value={type} onChange={(event) => setType(event.target.value as TypeFilter)}><option value="all">Все направления</option><option value="fire_risk">Пожароопасность</option><option value="nsd_event">Событие НСД</option><option value="nsd_risk">Риск НСД</option></select></div>
        <div className="select-wrap"><Activity size={16} /><select value={risk} onChange={(event) => setRisk(event.target.value as RiskFilter)}><option value="all">Любой риск</option><option value="critical">Критический</option><option value="high">Высокий</option><option value="medium">Средний</option><option value="low">Низкий</option></select></div>
        <label className="switch"><input type="checkbox" checked={alertsOnly} onChange={(event) => setAlertsOnly(event.target.checked)} /><span /><b>Только тревоги</b></label>
      </section>

      <div className="results-caption"><span>Найдено прогнозов: <b>{filtered.length}</b></span><span><Sparkles size={15} /> Версии моделей отображаются для воспроизводимости</span></div>

      {filtered.length === 0 ? <EmptyState /> : (
        <section className="prediction-grid">
          {filtered.map((prediction) => {
            const object = objects.find((item) => item.object_id === prediction.object_id)
            const isFire = prediction.prediction_type === 'fire_risk'
            return <article className={`prediction-card ${prediction.is_alert ? 'prediction-card--alert' : ''}`} key={prediction.prediction_id}>
              <div className="prediction-card__head">
                <span className={`prediction-card__icon prediction-card__icon--${isFire ? 'fire' : 'nsd'}`}>{isFire ? <Flame size={21} /> : <ShieldAlert size={21} />}</span>
                <div><span>{predictionTypeLabel[prediction.prediction_type]}</span><strong>{object?.dispatcher_name ?? `Объект №${prediction.object_id}`}</strong></div>
                <RiskBadge level={prediction.risk_level} />
              </div>
              <div className="prediction-score"><div><span>Вероятность</span><strong>{formatPercent(prediction.risk_score)}</strong></div><div className="prediction-score__bar"><i style={{ width: formatPercent(prediction.risk_score) }} /></div><div><span>Горизонт</span><b>{getHorizonHours(prediction.features_used)} ч</b></div></div>
              <p className="prediction-card__recommendation">{getRecommendation(prediction.features_used)}</p>
              <dl className="prediction-card__features">
                {Object.entries(prediction.features_used).filter(([key]) => !['horizon_hours', 'recommendation'].includes(key)).slice(0, 3).map(([key, value]) => <div key={key}><dt>{featureLabels[key] ?? key}</dt><dd>{String(value)}</dd></div>)}
              </dl>
              <footer><span>{formatDateTime(prediction.predicted_at)}</span><span>{prediction.model_version}</span></footer>
            </article>
          })}
        </section>
      )}
    </div>
  )
}

const featureLabels: Record<string, string> = {
  temperature_c: 'Температура', smoke_index: 'Индекс дыма', trend: 'Рост за час',
  door_state: 'Состояние двери', movement_count: 'Событий движения', failed_access_attempts: 'Ошибок доступа',
}
