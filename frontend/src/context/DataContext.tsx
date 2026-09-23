import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from '../api/client'
import type { Incident, IncidentDecisionType, InfrastructureObject, Prediction, WorkOrderPriority } from '../types/api'

interface DataContextValue {
  incidents: Incident[]
  predictions: Prediction[]
  objects: InfrastructureObject[]
  loading: boolean
  error: string
  refresh: () => Promise<void>
  assignIncident: (id: string, username: string) => Promise<void>
  decideIncident: (id: string, decision: IncidentDecisionType, actor: string, comment: string) => Promise<void>
  resolveIncident: (id: string) => Promise<void>
  createWorkOrder: (id: string, payload: { title: string; description: string; priority: WorkOrderPriority }) => Promise<void>
}

const DataContext = createContext<DataContextValue | null>(null)

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
      const [incidentPage, predictionPage, objectPage] = await Promise.all([
        api.listIncidents(), api.listPredictions(), api.listObjects(),
      ])
      setIncidents(incidentPage.items)
      setPredictions(predictionPage.items)
      setObjects(objectPage.items)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось загрузить данные')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void refresh() }, [refresh])

  const value = useMemo<DataContextValue>(() => ({
    incidents, predictions, objects, loading, error, refresh,
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
