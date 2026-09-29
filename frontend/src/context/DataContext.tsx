import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from '../api/client'
import { createIncidentStream } from '../api/incidentStream'
import type { Incident, IncidentDecisionType, InfrastructureObject, Prediction, WorkOrderPriority } from '../types/api'

interface DataContextValue {
  incidents: Incident[]
  predictions: Prediction[]
  objects: InfrastructureObject[]
  loading: boolean
  error: string
  refresh: () => Promise<void>
  requestPrediction: (objectId: number) => Promise<void>
  assignIncident: (id: string, username: string) => Promise<void>
  decideIncident: (id: string, decision: IncidentDecisionType, actor: string, comment: string) => Promise<void>
  resolveIncident: (id: string) => Promise<void>
  createWorkOrder: (id: string, payload: { title: string; description: string; priority: WorkOrderPriority }) => Promise<void>
}

const DataContext = createContext<DataContextValue | null>(null)

const PAGE_SIZE = 200

async function loadAllPages<T>(loader: (offset: number) => Promise<{ items: T[] }>) {
  const items: T[] = []
  for (let offset = 0; ; offset += PAGE_SIZE) {
    const page = await loader(offset)
    items.push(...page.items)
    if (page.items.length < PAGE_SIZE) return items
  }
}

function mergeObjects(
  registry: InfrastructureObject[],
  predictions: Prediction[],
  incidents: Incident[],
) {
  const objectsByID = new Map(registry.map((item) => [item.object_id, item]))

  for (const objectID of [...predictions, ...incidents].map((item) => item.object_id)) {
    if (!objectsByID.has(objectID)) {
      objectsByID.set(objectID, {
        object_id: objectID,
        parent_id: null,
        hierarchy_level: 0,
        object_type: 'unknown',
        dispatcher_name: `Объект №${objectID}`,
      })
    }
  }

  return [...objectsByID.values()].sort((left, right) => left.object_id - right.object_id)
}

function keepObjectsReference(
  current: InfrastructureObject[],
  next: InfrastructureObject[],
) {
  return JSON.stringify(current) === JSON.stringify(next) ? current : next
}

export function DataProvider({ children }: { children: ReactNode }) {
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [predictions, setPredictions] = useState<Prediction[]>([])
  const [objects, setObjects] = useState<InfrastructureObject[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [incidentItems, predictionItems, objectItems] = await Promise.all([
        loadAllPages((offset) => api.listIncidents({ limit: PAGE_SIZE, offset })),
        loadAllPages((offset) => api.listPredictions({ limit: PAGE_SIZE, offset })),
        loadAllPages((offset) => api.listObjects('', PAGE_SIZE, offset)),
      ])
      setIncidents(incidentItems)
      setPredictions(predictionItems)
      setObjects((current) => keepObjectsReference(
        current,
        mergeObjects(objectItems, predictionItems, incidentItems),
      ))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось загрузить данные')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void refresh() }, [refresh])

  useEffect(() => {
    const timer = window.setInterval(() => {
      void Promise.all([
        loadAllPages((offset) => api.listPredictions({ limit: PAGE_SIZE, offset })),
        loadAllPages((offset) => api.listObjects('', PAGE_SIZE, offset)),
      ])
        .then(([predictionItems, objectItems]) => {
          setPredictions(predictionItems)
          setObjects((current) => keepObjectsReference(
            current,
            mergeObjects(objectItems, predictionItems, incidents),
          ))
        })
        .catch(() => undefined)
    }, 10_000)
    return () => window.clearInterval(timer)
  }, [incidents])

  useEffect(() => {
    const stream = createIncidentStream({
      onIncident: (notification) => {
        void api.getIncident(notification.incident_id).then((incident) => {
          setIncidents((current) => {
            const exists = current.some((item) => item.incident_id === incident.incident_id)
            return exists
              ? current.map((item) => item.incident_id === incident.incident_id ? incident : item)
              : [incident, ...current]
          })
        }).catch(() => void refresh())
      },
    })
    void stream.connect()
    return stream.close
  }, [refresh])

  const value = useMemo<DataContextValue>(() => ({
    incidents, predictions, objects, loading, error, refresh,
    requestPrediction: async (objectId) => {
      const response = await api.requestPrediction(objectId, [])
      setPredictions((current) => [
        ...response.predictions,
        ...current.filter((item) =>
          !response.predictions.some((prediction) =>
            prediction.prediction_id === item.prediction_id)),
      ])
    },
    assignIncident: async (id, username) => { await api.assignIncident(id, username); await refresh() },
    decideIncident: async (id, decision, actor, comment) => { await api.addDecision(id, { decision, actor, comment }); await refresh() },
    resolveIncident: async (id) => { await api.resolveIncident(id); await refresh() },
    createWorkOrder: async (id, payload) => { await api.createWorkOrder(id, payload); await refresh() },
  }), [incidents, predictions, objects, loading, error, refresh])

  return <DataContext.Provider value={value}>{children}</DataContext.Provider>
}

export function useData() {
  const context = useContext(DataContext)
  if (!context) throw new Error('useData must be used inside DataProvider')
  return context
}
