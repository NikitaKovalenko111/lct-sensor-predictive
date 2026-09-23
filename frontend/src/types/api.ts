export type Role = 'admin' | 'dispatcher' | 'analyst' | 'manager'
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'
export type PredictionType = 'fire_risk' | 'nsd_event' | 'nsd_risk' | 'equipment_failure'
export type IncidentStatus = 'new' | 'in_review' | 'resolved' | 'dismissed'
export type IncidentDecisionType = 'confirmed' | 'false_alarm' | 'monitor' | 'dispatch_crew'
export type WorkOrderPriority = 'normal' | 'high' | 'emergency'

export interface User {
  user_id: string
  username: string
  role: Role
  active: boolean
  created_at: string
  last_login_at?: string | null
}

export interface LoginResponse {
  access_token: string
  token_type: 'Bearer'
  expires_at: string
  user: User
}

export interface Prediction {
  schema_version?: number
  prediction_id?: string
  object_id: number
  prediction_type: PredictionType
  risk_score: number
  risk_level: RiskLevel
  is_alert?: boolean | null
  predicted_at: string
  features_used: Record<string, unknown>
  model_version: string
}

export interface Incident {
  incident_id: string
  prediction_id: string
  object_id: number
  incident_type: PredictionType
  risk_score: number
  risk_level: RiskLevel
  status: IncidentStatus
  title: string
  description?: string
  assigned_to?: string
  created_at: string
  updated_at: string
  resolved_at?: string | null
}

export interface IncidentDecision {
  decision_id: string
  incident_id: string
  decision: IncidentDecisionType
  actor: string
  comment: string
  created_at: string
}

export interface WorkOrderDraft {
  work_order_id: string
  incident_id: string
  title: string
  description: string
  priority: WorkOrderPriority
  status: 'draft'
  created_at: string
  updated_at: string
}

export interface IncidentDetail extends Incident {
  decisions: IncidentDecision[]
  work_order?: WorkOrderDraft | null
}

export interface InfrastructureObject {
  object_id: number
  parent_id?: number | null
  hierarchy_level: number
  object_type: string
  dispatcher_name: string
  geometry?: Record<string, unknown>
}

export interface Channel {
  channel_id: string
  object_id: number
  sensor_type: string
  engineering_system?: string
  engineering_system_tag?: string
  sensor_name?: string
}

export interface SensorEvent {
  schema_version?: number
  event_id: string
  object_id: number
  channel_id: string
  sensor_type: string
  engineering_system: string
  value: string
  is_alarm: boolean
  timestamp: string
}

export interface AuditEntry {
  audit_id: number
  user_id?: string
  username: string
  action: string
  resource_type: string
  resource_id?: string
  method: string
  path: string
  remote_ip?: string
  details: Record<string, unknown>
  created_at: string
}

export interface ImportJob {
  import_id: string
  import_kind: 'objects' | 'channels' | 'events'
  file_name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  processed_rows: number
  failed_rows: number
  error_message?: string
  started_at?: string | null
  finished_at?: string | null
}

export interface Page<T> {
  items: T[]
}

export interface ObjectPresentation {
  x: number
  y: number
  address: string
  district: string
  health: number
}
