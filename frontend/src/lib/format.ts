import type { IncidentStatus, PredictionType, RiskLevel, Role } from '../types/api'

export const predictionTypeLabel: Record<PredictionType, string> = {
  fire_risk: 'Пожароопасность',
  nsd_event: 'Событие НСД',
  nsd_risk: 'Риск НСД',
  equipment_failure: 'Отказ оборудования',
}

export const predictionTypeShortLabel: Record<PredictionType, string> = {
  fire_risk: 'Пожар',
  nsd_event: 'НСД: событие',
  nsd_risk: 'НСД: риск',
  equipment_failure: 'Отказ',
}

export const riskLabel: Record<RiskLevel, string> = {
  low: 'Низкий',
  medium: 'Средний',
  high: 'Высокий',
  critical: 'Критический',
}

export const statusLabel: Record<IncidentStatus, string> = {
  new: 'Новый',
  in_review: 'На проверке',
  resolved: 'Завершён',
  dismissed: 'Отклонён',
}

export const roleLabel: Record<Role, string> = {
  admin: 'Администратор',
  dispatcher: 'Диспетчер',
  analyst: 'Аналитик',
  manager: 'Руководитель',
}

export const formatDateTime = (value: string) =>
  new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))

export const formatFullDateTime = (value: string) =>
  new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(value))

export const formatPercent = (value: number) => `${Math.round(value * 100)}%`

export const getHorizonHours = (features: Record<string, unknown>) => {
  const raw = features.horizon_hours
  return typeof raw === 'number' && Number.isFinite(raw) ? raw : 24
}

export const getRecommendation = (features: Record<string, unknown>) => {
  const raw = features.recommendation
  return typeof raw === 'string' ? raw : 'Проверить показания датчиков и состояние объекта.'
}

export const getFeatureNumber = (features: Record<string, unknown>, key: string) => {
  const raw = features[key]
  return typeof raw === 'number' && Number.isFinite(raw) ? raw : null
}

export const canMutateIncidents = (role?: Role) => role === 'admin' || role === 'dispatcher'
