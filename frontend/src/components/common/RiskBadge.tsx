import type { RiskLevel } from '../../types/api'
import { riskLabel } from '../../lib/format'

export function RiskBadge({ level, compact = false }: { level: RiskLevel; compact?: boolean }) {
  return <span className={`risk-badge risk-badge--${level} ${compact ? 'risk-badge--compact' : ''}`}><i />{riskLabel[level]}</span>
}
