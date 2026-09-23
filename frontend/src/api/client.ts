import type {
  AuditEntry,
  Channel,
  Incident,
  IncidentDecision,
  IncidentDecisionType,
  IncidentDetail,
  InfrastructureObject,
  LoginResponse,
  Page,
  Prediction,
  PredictionType,
  RiskLevel,
  Role,
  SensorEvent,
  User,
  WorkOrderDraft,
  WorkOrderPriority,
} from '../types/api'
import {
  mockAudit,
  mockChannels,
  mockIncidents,
  mockObjects,
  mockPredictions,
  mockSensorEvents,
  mockUsers,
} from './mockData'

export interface PredictionFilters {
  object_id?: number
  prediction_type?: PredictionType
  risk_level?: RiskLevel
  alert_only?: boolean
}

export interface IncidentFilters {
  object_id?: number
  status?: Incident['status']
  risk_level?: RiskLevel
}

export interface PredictiveApi {
  login(username: string, password: string): Promise<LoginResponse>
  listPredictions(filters?: PredictionFilters): Promise<Page<Prediction>>
  requestPrediction(objectId: number, predictionTypes: PredictionType[]): Promise<{ predictions: Prediction[] }>
  listIncidents(filters?: IncidentFilters): Promise<Page<Incident>>
  getIncident(id: string): Promise<IncidentDetail>
  assignIncident(id: string, assignedTo: string): Promise<Incident>
  addDecision(id: string, payload: { decision: IncidentDecisionType; actor: string; comment: string }): Promise<IncidentDecision>
  resolveIncident(id: string): Promise<Incident>
  createWorkOrder(id: string, payload: { title: string; description: string; priority: WorkOrderPriority }): Promise<WorkOrderDraft>
  listObjects(search?: string): Promise<Page<InfrastructureObject>>
  listChannels(objectId?: number): Promise<Page<Channel>>
  listSensorEvents(objectId?: number): Promise<Page<SensorEvent>>
  listUsers(): Promise<Page<User>>
  createUser(payload: { username: string; password: string; role: Role }): Promise<User>
  listAudit(): Promise<Page<AuditEntry>>
}

const delay = (ms = 180) => new Promise((resolve) => window.setTimeout(resolve, ms))
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T

const STORAGE_KEY = 'lct_predictive_mock_state_v1'

interface MockState {
  incidents: IncidentDetail[]
  predictions: Prediction[]
  users: User[]
}

const getMockState = (): MockState => {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved) {
    try {
      return JSON.parse(saved) as MockState
    } catch {
      localStorage.removeItem(STORAGE_KEY)
    }
  }
  const initial = { incidents: clone(mockIncidents), predictions: clone(mockPredictions), users: clone(mockUsers) }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(initial))
  return initial
}

const saveMockState = (state: MockState) => localStorage.setItem(STORAGE_KEY, JSON.stringify(state))

const credentials: Record<string, { password: string; role: Role }> = {
  admin: { password: 'AdminPredict2026!', role: 'admin' },
  dispatcher: { password: 'DispatchPredict2026!', role: 'dispatcher' },
  analyst: { password: 'AnalystPredict2026!', role: 'analyst' },
  manager: { password: 'ManagerPredict2026!', role: 'manager' },
}

class MockApi implements PredictiveApi {
  async login(username: string, password: string) {
    await delay(350)
    const account = credentials[username]
    if (!account || account.password !== password) throw new Error('Неверный логин или пароль')
    const user = getMockState().users.find((item) => item.username === username)
    if (!user) throw new Error('Пользователь не найден')
    return {
      access_token: `mock-token-${username}`,
      token_type: 'Bearer' as const,
      expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
      user,
    }
  }

  async listPredictions(filters: PredictionFilters = {}) {
    await delay()
    const items = getMockState().predictions.filter((item) =>
      (!filters.object_id || item.object_id === filters.object_id) &&
      (!filters.prediction_type || item.prediction_type === filters.prediction_type) &&
      (!filters.risk_level || item.risk_level === filters.risk_level) &&
      (!filters.alert_only || item.is_alert === true),
    )
    return { items: clone(items) }
  }

  async requestPrediction(objectId: number, predictionTypes: PredictionType[]) {
    await delay(650)
    const state = getMockState()
    const source = state.predictions.filter((item) => item.object_id === objectId && predictionTypes.includes(item.prediction_type))
    const predictions = source.length ? source : state.predictions.filter((item) => predictionTypes.includes(item.prediction_type)).slice(0, 2).map((item) => ({ ...item, object_id: objectId }))
    return { predictions: clone(predictions) }
  }

  async listIncidents(filters: IncidentFilters = {}) {
    await delay()
    const items = getMockState().incidents.filter((item) =>
      (!filters.object_id || item.object_id === filters.object_id) &&
      (!filters.status || item.status === filters.status) &&
      (!filters.risk_level || item.risk_level === filters.risk_level),
    )
    return { items: clone(items) }
  }

  async getIncident(id: string) {
    await delay(120)
    const incident = getMockState().incidents.find((item) => item.incident_id === id)
    if (!incident) throw new Error('Инцидент не найден')
    return clone(incident)
  }

  async assignIncident(id: string, assignedTo: string) {
    await delay()
    const state = getMockState()
    const incident = state.incidents.find((item) => item.incident_id === id)
    if (!incident) throw new Error('Инцидент не найден')
    incident.assigned_to = assignedTo
    incident.status = 'in_review'
    incident.updated_at = new Date().toISOString()
    saveMockState(state)
    return clone(incident)
  }

  async addDecision(id: string, payload: { decision: IncidentDecisionType; actor: string; comment: string }) {
    await delay()
    const state = getMockState()
    const incident = state.incidents.find((item) => item.incident_id === id)
    if (!incident) throw new Error('Инцидент не найден')
    const decision: IncidentDecision = {
      decision_id: crypto.randomUUID(), incident_id: id, ...payload, created_at: new Date().toISOString(),
    }
    incident.decisions.push(decision)
    incident.status = payload.decision === 'false_alarm' ? 'dismissed' : 'in_review'
    incident.updated_at = decision.created_at
    if (payload.decision === 'false_alarm') incident.resolved_at = decision.created_at
    saveMockState(state)
    return clone(decision)
  }

  async resolveIncident(id: string) {
    await delay()
    const state = getMockState()
    const incident = state.incidents.find((item) => item.incident_id === id)
    if (!incident) throw new Error('Инцидент не найден')
    incident.status = 'resolved'
    incident.resolved_at = new Date().toISOString()
    incident.updated_at = incident.resolved_at
    saveMockState(state)
    return clone(incident)
  }

  async createWorkOrder(id: string, payload: { title: string; description: string; priority: WorkOrderPriority }) {
    await delay()
    const state = getMockState()
    const incident = state.incidents.find((item) => item.incident_id === id)
    if (!incident) throw new Error('Инцидент не найден')
    const now = new Date().toISOString()
    const workOrder: WorkOrderDraft = {
      work_order_id: incident.work_order?.work_order_id ?? crypto.randomUUID(), incident_id: id, ...payload,
      status: 'draft', created_at: incident.work_order?.created_at ?? now, updated_at: now,
    }
    incident.work_order = workOrder
    incident.updated_at = now
    saveMockState(state)
    return clone(workOrder)
  }

  async listObjects(search = '') {
    await delay()
    const query = search.toLowerCase()
    return { items: clone(mockObjects.filter((item) => item.dispatcher_name.toLowerCase().includes(query))) }
  }

  async listChannels(objectId?: number) {
    await delay(120)
    return { items: clone(mockChannels.filter((item) => !objectId || item.object_id === objectId)) }
  }

  async listSensorEvents(objectId?: number) {
    await delay(120)
    return { items: clone(mockSensorEvents.filter((item) => !objectId || item.object_id === objectId)) }
  }

  async listUsers() { await delay(); return { items: clone(getMockState().users) } }

  async createUser(payload: { username: string; password: string; role: Role }) {
    await delay()
    const state = getMockState()
    if (state.users.some((item) => item.username === payload.username)) throw new Error('Пользователь уже существует')
    const user: User = { user_id: crypto.randomUUID(), username: payload.username, role: payload.role, active: true, created_at: new Date().toISOString() }
    state.users.push(user)
    saveMockState(state)
    return clone(user)
  }

  async listAudit() { await delay(); return { items: clone(mockAudit) } }
}

class LiveApi implements PredictiveApi {
  private baseUrl = import.meta.env.VITE_API_URL || ''
  private token = () => localStorage.getItem('lct_access_token')

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(this.token() ? { Authorization: `Bearer ${this.token()}` } : {}),
        ...init.headers,
      },
    })
    if (!response.ok) {
      const message = response.status === 401 ? 'Сессия истекла. Войдите снова.' : `Ошибка API: ${response.status}`
      throw new Error(message)
    }
    if (response.status === 204) return undefined as T
    return response.json() as Promise<T>
  }

  login(username: string, password: string) { return this.request<LoginResponse>('/api/v1/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }) }
  listPredictions(filters: PredictionFilters = {}) { return this.request<Page<Prediction>>(`/api/v1/predictions?${new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== undefined).map(([key, value]) => [key, String(value)]))}`) }
  requestPrediction(objectId: number, predictionTypes: PredictionType[]) { return this.request<{ predictions: Prediction[] }>('/api/v1/predictions/request', { method: 'POST', body: JSON.stringify({ object_id: objectId, prediction_types: predictionTypes }) }) }
  listIncidents(filters: IncidentFilters = {}) { return this.request<Page<Incident>>(`/api/v1/incidents?${new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== undefined).map(([key, value]) => [key, String(value)]))}`) }
  getIncident(id: string) { return this.request<IncidentDetail>(`/api/v1/incidents/${id}`) }
  assignIncident(id: string, assignedTo: string) { return this.request<Incident>(`/api/v1/incidents/${id}/assignment`, { method: 'PATCH', body: JSON.stringify({ assigned_to: assignedTo }) }) }
  addDecision(id: string, payload: { decision: IncidentDecisionType; actor: string; comment: string }) { return this.request<IncidentDecision>(`/api/v1/incidents/${id}/decisions`, { method: 'POST', body: JSON.stringify(payload) }) }
  resolveIncident(id: string) { return this.request<Incident>(`/api/v1/incidents/${id}/resolve`, { method: 'POST' }) }
  createWorkOrder(id: string, payload: { title: string; description: string; priority: WorkOrderPriority }) { return this.request<WorkOrderDraft>(`/api/v1/incidents/${id}/work-order-draft`, { method: 'POST', body: JSON.stringify(payload) }) }
  listObjects(search = '') { return this.request<Page<InfrastructureObject>>(`/api/v1/objects?${new URLSearchParams({ search })}`) }
  listChannels(objectId?: number) { return this.request<Page<Channel>>(`/api/v1/channels?${objectId ? `object_id=${objectId}` : ''}`) }
  listSensorEvents(objectId?: number) { return this.request<Page<SensorEvent>>(`/api/v1/sensor-events?${objectId ? `object_id=${objectId}` : ''}`) }
  listUsers() { return this.request<Page<User>>('/api/v1/users') }
  createUser(payload: { username: string; password: string; role: Role }) { return this.request<User>('/api/v1/users', { method: 'POST', body: JSON.stringify(payload) }) }
  listAudit() { return this.request<Page<AuditEntry>>('/api/v1/audit-logs') }
}

export const api: PredictiveApi = import.meta.env.VITE_API_MODE === 'live' ? new LiveApi() : new MockApi()
