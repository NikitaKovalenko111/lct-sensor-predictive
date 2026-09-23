import { Flame, ShieldAlert } from 'lucide-react'
import { useMemo, useState } from 'react'
import { objectPresentation } from '../../api/mockData'
import type { Incident, InfrastructureObject } from '../../types/api'
import { formatPercent, predictionTypeShortLabel } from '../../lib/format'

export function RiskMap({ objects, incidents, onSelect }: { objects: InfrastructureObject[]; incidents: Incident[]; onSelect: (incident: Incident) => void }) {
  const [active, setActive] = useState<string | null>(null)
  const activeIncidents = useMemo(() => incidents.filter((item) => item.status === 'new' || item.status === 'in_review'), [incidents])

  return (
    <div className="risk-map" aria-label="Схематическая карта объектов">
      <svg className="risk-map__lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <path d="M5 36 C24 29, 31 41, 48 34 S74 20, 94 34" />
        <path d="M7 67 C24 55, 34 76, 51 62 S73 49, 95 68" />
        <path d="M28 8 C35 29, 29 45, 42 58 S61 76, 70 93" />
      </svg>
      <div className="risk-map__district risk-map__district--one">ЦАО</div>
      <div className="risk-map__district risk-map__district--two">СВАО</div>
      <div className="risk-map__district risk-map__district--three">ЮАО</div>
      {objects.map((object) => {
        const position = objectPresentation[object.object_id]
        if (!position) return null
        const incident = activeIncidents.find((item) => item.object_id === object.object_id)
        const isActive = incident?.incident_id === active
        return (
          <button
            key={object.object_id}
            className={`map-point ${incident ? `map-point--${incident.risk_level}` : ''} ${isActive ? 'map-point--active' : ''}`}
            style={{ left: `${position.x}%`, top: `${position.y}%` }}
            onClick={() => { setActive(incident?.incident_id ?? null); if (incident) onSelect(incident) }}
            title={object.dispatcher_name}
          >
            <span>{incident ? incident.incident_type === 'fire_risk' ? <Flame size={15} /> : <ShieldAlert size={15} /> : null}</span>
            {incident && <i />}
            {isActive && <div className="map-tooltip"><small>{predictionTypeShortLabel[incident.incident_type]}</small><strong>{object.dispatcher_name}</strong><b>{formatPercent(incident.risk_score)}</b></div>}
          </button>
        )
      })}
      <div className="risk-map__legend"><span><i className="legend-dot legend-dot--critical" />Критический</span><span><i className="legend-dot legend-dot--high" />Высокий</span><span><i className="legend-dot" />Без тревог</span></div>
      <div className="risk-map__note">Схематическая геометрия · не навигационная карта</div>
    </div>
  )
}
