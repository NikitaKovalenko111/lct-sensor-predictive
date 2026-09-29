import { accessTokenStore, apiRuntime } from './runtime'

export interface IncidentNotification {
  event: 'incident.created' | 'incident.updated'
  incident_id: string
}

export interface IncidentStreamHandlers {
  onIncident: (notification: IncidentNotification) => void
  onError?: (error: Error) => void
  onReady?: () => void
}

export function createIncidentStream(handlers: IncidentStreamHandlers) {
  const controller = new AbortController()

  const connect = async () => {
    if (!apiRuntime.incidentStreamEnabled) return
    while (!controller.signal.aborted) {
      const token = accessTokenStore.get()
      try {
        const response = await fetch(`${apiRuntime.baseUrl}/api/v1/incidents/stream`, {
          headers: { Accept: 'text/event-stream', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          signal: controller.signal,
        })
        if (!response.ok || !response.body) throw new Error(`Поток инцидентов недоступен: ${response.status}`)

        const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
        let buffer = ''
        while (!controller.signal.aborted) {
          const { value, done } = await reader.read()
          if (done) break
          buffer += value
          const events = buffer.split('\n\n')
          buffer = events.pop() ?? ''
          events.forEach((chunk) => {
            const event = chunk.match(/^event:\s*(.+)$/m)?.[1]
            const data = chunk.match(/^data:\s*(.+)$/m)?.[1]
            if (event === 'ready') handlers.onReady?.()
            if (event === 'incident' && data) {
              const notification = JSON.parse(data) as Partial<IncidentNotification>
              if (notification.incident_id && notification.event) {
                handlers.onIncident(notification as IncidentNotification)
              }
            }
          })
        }
      } catch (cause) {
        if (!controller.signal.aborted) handlers.onError?.(cause instanceof Error ? cause : new Error('Ошибка потока инцидентов'))
      }
      if (!controller.signal.aborted) await new Promise((resolve) => window.setTimeout(resolve, 3_000))
    }
  }

  return { connect, close: () => controller.abort() }
}
