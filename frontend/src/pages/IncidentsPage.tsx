import { ArrowRight, ClipboardCheck, FileText, Filter, Flame, Search, ShieldAlert, UserCheck, X } from 'lucide-react'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { EmptyState } from '../components/common/EmptyState'
import { PageHeader } from '../components/common/PageHeader'
import { RiskBadge } from '../components/common/RiskBadge'
import { StatusBadge } from '../components/common/StatusBadge'
import { useAuth } from '../context/AuthContext'
import { useData } from '../context/DataContext'
import { canMutateIncidents, formatFullDateTime, formatPercent, predictionTypeLabel } from '../lib/format'
import type { Incident, IncidentDecisionType, IncidentDetail, IncidentStatus, WorkOrderPriority } from '../types/api'

type StatusFilter = 'open' | 'all' | IncidentStatus

export function IncidentsPage() {
  const { incidents, objects, assignIncident, decideIncident, resolveIncident, createWorkOrder } = useData()
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<StatusFilter>('open')
  const [detail, setDetail] = useState<IncidentDetail | null>(null)
  const [decision, setDecision] = useState<IncidentDecisionType>('monitor')
  const [comment, setComment] = useState('')
  const [workOrderOpen, setWorkOrderOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const selectedId = params.get('selected')

  useEffect(() => {
    if (!selectedId) { setDetail(null); return }
    void api.getIncident(selectedId).then(setDetail)
  }, [selectedId, incidents])

  const filtered = useMemo(() => incidents.filter((incident) => {
    const object = objects.find((item) => item.object_id === incident.object_id)
    const matchesStatus = status === 'all' || (status === 'open' ? incident.status === 'new' || incident.status === 'in_review' : incident.status === status)
    const matchesSearch = !search || incident.title.toLowerCase().includes(search.toLowerCase()) || object?.dispatcher_name.toLowerCase().includes(search.toLowerCase())
    return matchesStatus && matchesSearch
  }), [incidents, objects, search, status])

  const run = async (action: () => Promise<void>) => {
    setBusy(true)
    try { await action(); if (selectedId) setDetail(await api.getIncident(selectedId)) }
    finally { setBusy(false) }
  }

  const submitDecision = (event: FormEvent) => {
    event.preventDefault()
    if (!detail || !user) return
    void run(async () => { await decideIncident(detail.incident_id, decision, user.username, comment); setComment('') })
  }

  const openIncident = (incident: Incident) => setParams({ selected: incident.incident_id })
  const close = () => setParams({})

  return (
    <div className="page">
      <PageHeader eyebrow="Рабочая очередь" title="Инциденты" description="Проверка, фиксация решений и формирование заявок на обслуживание" />
      <section className="filter-bar">
        <div className="search-field"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Инцидент или объект" /></div>
        <div className="select-wrap"><Filter size={16} /><select value={status} onChange={(event) => setStatus(event.target.value as StatusFilter)}><option value="open">Активные</option><option value="all">Все статусы</option><option value="new">Новые</option><option value="in_review">На проверке</option><option value="resolved">Завершённые</option><option value="dismissed">Отклонённые</option></select></div>
      </section>

      <section className="incidents-board">
        <div className="incidents-board__head"><span>Инцидент</span><span>Объект</span><span>Риск</span><span>Статус</span><span>Создан</span><span /></div>
        {filtered.length === 0 ? <EmptyState /> : filtered.map((incident) => {
          const object = objects.find((item) => item.object_id === incident.object_id)
          const isFire = incident.incident_type === 'fire_risk'
          return <button className="incident-row" key={incident.incident_id} onClick={() => openIncident(incident)}>
            <span className={`incident-row__icon incident-row__icon--${isFire ? 'fire' : 'nsd'}`}>{isFire ? <Flame size={19} /> : <ShieldAlert size={19} />}</span>
            <span className="incident-row__main"><small>{predictionTypeLabel[incident.incident_type]}</small><strong>{incident.title}</strong></span>
            <span className="incident-row__object"><strong>{object?.dispatcher_name ?? `Объект №${incident.object_id}`}</strong><small>#{incident.object_id}</small></span>
            <span className="incident-row__score"><strong>{formatPercent(incident.risk_score)}</strong><RiskBadge level={incident.risk_level} compact /></span>
            <StatusBadge status={incident.status} />
            <span className="incident-row__date">{formatFullDateTime(incident.created_at)}</span>
            <ArrowRight size={17} />
          </button>
        })}
      </section>

      {selectedId && <button className="drawer-backdrop" onClick={close} aria-label="Закрыть карточку" />}
      <aside className={`incident-drawer ${selectedId ? 'incident-drawer--open' : ''}`}>
        {detail && <>
          <header className="drawer-head"><div><p className="eyebrow">Карточка инцидента</p><h2>{detail.title}</h2></div><button className="icon-button" onClick={close}><X size={20} /></button></header>
          <div className="drawer-body">
            <div className="incident-summary">
              <div><span>Вероятность</span><strong>{formatPercent(detail.risk_score)}</strong></div><RiskBadge level={detail.risk_level} /><StatusBadge status={detail.status} />
            </div>
            <dl className="details-list"><div><dt>Направление</dt><dd>{predictionTypeLabel[detail.incident_type]}</dd></div><div><dt>Объект</dt><dd>{objects.find((item) => item.object_id === detail.object_id)?.dispatcher_name ?? `№${detail.object_id}`}</dd></div><div><dt>Создан</dt><dd>{formatFullDateTime(detail.created_at)}</dd></div><div><dt>Ответственный</dt><dd>{detail.assigned_to ?? 'Не назначен'}</dd></div></dl>
            <div className="drawer-description"><p className="eyebrow">Основание прогноза</p><p>{detail.description || 'Описание отсутствует'}</p></div>

            {canMutateIncidents(user?.role) && detail.status === 'new' && <button className="button button--primary button--wide" disabled={busy} onClick={() => user && void run(() => assignIncident(detail.incident_id, user.username))}><UserCheck size={17} />Принять на проверку</button>}

            <section className="drawer-section"><div className="drawer-section__head"><h3>История решений</h3><span>{detail.decisions.length}</span></div>{detail.decisions.length === 0 ? <p className="muted">Решений пока нет.</p> : <div className="timeline">{detail.decisions.map((item) => <div key={item.decision_id}><i /><div><strong>{decisionLabels[item.decision]}</strong><span>{item.actor} · {formatFullDateTime(item.created_at)}</span><p>{item.comment}</p></div></div>)}</div>}</section>

            {canMutateIncidents(user?.role) && (detail.status === 'new' || detail.status === 'in_review') && <form className="drawer-section decision-form" onSubmit={submitDecision}><h3>Зафиксировать решение</h3><div className="decision-options">{Object.entries(decisionLabels).map(([value, label]) => <label key={value}><input type="radio" name="decision" value={value} checked={decision === value} onChange={() => setDecision(value as IncidentDecisionType)} /><span>{label}</span></label>)}</div><textarea value={comment} onChange={(event) => setComment(event.target.value)} placeholder={decision === 'false_alarm' ? 'Укажите причину ложного срабатывания' : 'Комментарий диспетчера'} required /><button className="button button--primary" disabled={busy}><ClipboardCheck size={17} />Сохранить решение</button></form>}

            <section className="drawer-section"><div className="drawer-section__head"><h3>Заявка на работы</h3>{detail.work_order && <span>Черновик</span>}</div>{detail.work_order ? <div className="work-order"><FileText size={20} /><div><strong>{detail.work_order.title}</strong><p>{detail.work_order.description}</p><small>Приоритет: {priorityLabels[detail.work_order.priority]}</small></div></div> : canMutateIncidents(user?.role) ? <button className="button button--secondary" onClick={() => setWorkOrderOpen(true)}><FileText size={17} />Сформировать черновик</button> : <p className="muted">Черновик не создан.</p>}</section>

            {canMutateIncidents(user?.role) && detail.status === 'in_review' && detail.decisions.length > 0 && <button className="button button--success button--wide" disabled={busy} onClick={() => void run(() => resolveIncident(detail.incident_id))}>Завершить обработку</button>}
          </div>
        </>}
      </aside>

      {workOrderOpen && detail && <WorkOrderModal incident={detail} onClose={() => setWorkOrderOpen(false)} onSubmit={(payload) => run(async () => { await createWorkOrder(detail.incident_id, payload); setWorkOrderOpen(false) })} />}
    </div>
  )
}

const decisionLabels: Record<IncidentDecisionType, string> = { confirmed: 'Событие подтверждено', false_alarm: 'Ложное срабатывание', monitor: 'Продолжить наблюдение', dispatch_crew: 'Направить бригаду' }
const priorityLabels: Record<WorkOrderPriority, string> = { normal: 'Обычный', high: 'Высокий', emergency: 'Аварийный' }

function WorkOrderModal({ incident, onClose, onSubmit }: { incident: IncidentDetail; onClose: () => void; onSubmit: (payload: { title: string; description: string; priority: WorkOrderPriority }) => Promise<void> }) {
  const [title, setTitle] = useState(`Проверка объекта №${incident.object_id}`)
  const [description, setDescription] = useState(incident.description ?? '')
  const [priority, setPriority] = useState<WorkOrderPriority>(incident.risk_level === 'critical' ? 'emergency' : 'high')
  const [busy, setBusy] = useState(false)
  const submit = async (event: FormEvent) => { event.preventDefault(); setBusy(true); try { await onSubmit({ title, description, priority }) } finally { setBusy(false) } }
  return <div className="modal-layer"><button className="modal-backdrop" onClick={onClose} /><form className="modal" onSubmit={submit}><header><div><p className="eyebrow">Черновик заявки</p><h2>Профилактические работы</h2></div><button type="button" className="icon-button" onClick={onClose}><X size={19} /></button></header><label className="field-label">Название</label><input className="input" value={title} onChange={(event) => setTitle(event.target.value)} required /><label className="field-label">Описание работ</label><textarea className="input" rows={5} value={description} onChange={(event) => setDescription(event.target.value)} required /><label className="field-label">Приоритет</label><select className="input" value={priority} onChange={(event) => setPriority(event.target.value as WorkOrderPriority)}><option value="normal">Обычный</option><option value="high">Высокий</option><option value="emergency">Аварийный</option></select><footer><button type="button" className="button button--ghost" onClick={onClose}>Отмена</button><button className="button button--primary" disabled={busy}>Создать черновик</button></footer></form></div>
}
