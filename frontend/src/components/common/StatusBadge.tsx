import type { IncidentStatus } from '../../types/api'
import { statusLabel } from '../../lib/format'

export function StatusBadge({ status }: { status: IncidentStatus }) {
  return <span className={`status-badge status-badge--${status}`}>{statusLabel[status]}</span>
}
