import { Activity, Building2, ChevronRight, CircleDot, DoorOpen, Flame, Search, Thermometer } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { objectPresentation } from '../api/mockData'
import { EmptyState } from '../components/common/EmptyState'
import { PageHeader } from '../components/common/PageHeader'
import { RiskBadge } from '../components/common/RiskBadge'
import { useData } from '../context/DataContext'
import { formatDateTime, formatPercent, predictionTypeShortLabel } from '../lib/format'
import type { Channel, InfrastructureObject, SensorEvent } from '../types/api'

export function ObjectsPage() {
  const { objects, predictions } = useData()
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<InfrastructureObject | null>(objects[0] ?? null)
  const [channels, setChannels] = useState<Channel[]>([])
  const [events, setEvents] = useState<SensorEvent[]>([])
  const filtered = useMemo(() => objects.filter((item) => item.dispatcher_name.toLowerCase().includes(search.toLowerCase()) || String(item.object_id).includes(search)), [objects, search])

  useEffect(() => { if (!selected && objects[0]) setSelected(objects[0]) }, [objects, selected])
  useEffect(() => {
    if (!selected) return
    void Promise.all([api.listChannels(selected.object_id), api.listSensorEvents(selected.object_id)]).then(([channelPage, eventPage]) => { setChannels(channelPage.items); setEvents(eventPage.items) })
  }, [selected])

  const objectPredictions = predictions.filter((item) => item.object_id === selected?.object_id)
  const topPrediction = [...objectPredictions].sort((a, b) => b.risk_score - a.risk_score)[0]
  const presentation = selected ? objectPresentation[selected.object_id] : null

  return (
    <div className="page">
      <PageHeader eyebrow="Реестр инфраструктуры" title="Объекты и датчики" description="Состояние оборудования, каналы мониторинга и связанные прогнозы" />
      <section className="objects-layout">
        <aside className="panel object-list-panel">
          <div className="search-field"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Найти объект" /></div>
          <div className="object-list">
            {filtered.length === 0 ? <EmptyState /> : filtered.map((object) => {
              const prediction = predictions.filter((item) => item.object_id === object.object_id).sort((a, b) => b.risk_score - a.risk_score)[0]
              return <button className={`object-list__item ${selected?.object_id === object.object_id ? 'object-list__item--active' : ''}`} key={object.object_id} onClick={() => setSelected(object)}>
                <span className="object-list__icon"><Building2 size={18} /></span><div><strong>{object.dispatcher_name}</strong><small>#{object.object_id} · {object.object_type === 'controlHouse' ? 'Диспетчерский объект' : 'Охраняемый объект'}</small></div>{prediction ? <RiskBadge level={prediction.risk_level} compact /> : <ChevronRight size={17} />}
              </button>
            })}
          </div>
        </aside>

        <div className="object-detail">
          {!selected ? <EmptyState title="Выберите объект" /> : <>
            <article className="panel object-hero">
              <div><p className="eyebrow">Объект №{selected.object_id}</p><h2>{selected.dispatcher_name}</h2><p>{presentation?.address ?? 'Адрес уточняется'} · {presentation?.district}</p></div>
              <div className="object-health"><span>Состояние объекта</span><strong>{presentation?.health ?? 80}%</strong><div className="progress"><i style={{ width: `${presentation?.health ?? 80}%` }} /></div></div>
            </article>

            {topPrediction && <article className="panel object-risk-callout"><span className={`prediction-card__icon prediction-card__icon--${topPrediction.prediction_type === 'fire_risk' ? 'fire' : 'nsd'}`}>{topPrediction.prediction_type === 'fire_risk' ? <Flame size={21} /> : <DoorOpen size={21} />}</span><div><p className="eyebrow">Ведущий прогноз</p><h3>{predictionTypeShortLabel[topPrediction.prediction_type]}</h3><p>Расчёт от {formatDateTime(topPrediction.predicted_at)}</p></div><strong>{formatPercent(topPrediction.risk_score)}</strong><RiskBadge level={topPrediction.risk_level} /></article>}

            <article className="panel">
              <div className="panel__head"><div><p className="eyebrow">Оборудование</p><h2>Каналы данных</h2></div><span className="counter">{channels.length}</span></div>
              <div className="channel-grid">
                {channels.length === 0 ? <EmptyState title="Каналы не найдены" /> : channels.map((channel) => {
                  const latest = [...events].reverse().find((event) => event.channel_id === channel.channel_id)
                  const SensorIcon = channel.sensor_type.includes('температуры') ? Thermometer : channel.sensor_type.includes('дыма') ? Flame : CircleDot
                  return <div className="channel-card" key={channel.channel_id}><span><SensorIcon size={18} /></span><div><strong>{channel.sensor_name ?? channel.sensor_type}</strong><small>{channel.sensor_type} · {channel.engineering_system}</small></div><div><b>{latest?.value ?? 'Нет данных'}</b><small>{latest ? formatDateTime(latest.timestamp) : '—'}</small></div><i className={latest?.is_alarm ? 'channel-state channel-state--alarm' : 'channel-state'} /></div>
                })}
              </div>
            </article>

            <article className="panel">
              <div className="panel__head"><div><p className="eyebrow">Телеметрия</p><h2>Последние события</h2></div><Activity size={19} /></div>
              <div className="compact-table"><div className="compact-table__head"><span>Время</span><span>Датчик</span><span>Значение</span><span>Статус</span></div>{events.slice(-6).reverse().map((event) => <div className="compact-table__row" key={event.event_id}><span>{formatDateTime(event.timestamp)}</span><span>{event.sensor_type}</span><strong>{event.value}</strong><span className={event.is_alarm ? 'table-alarm' : 'table-normal'}>{event.is_alarm ? 'Тревога' : 'Норма'}</span></div>)}</div>
            </article>
          </>}
        </div>
      </section>
    </div>
  )
}
