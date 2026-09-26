import { useEffect, useMemo, useRef, useState } from 'react'
import type { Incident, InfrastructureObject } from '../../types/api'
import { formatPercent, predictionTypeShortLabel } from '../../lib/format'

interface YandexPlacemark {
  events: { add: (event: string, handler: () => void) => void }
}

interface YandexMapInstance {
  geoObjects: { add: (object: YandexPlacemark) => void }
  destroy: () => void
}

interface YandexMapsApi {
  ready: (callback: () => void) => void
  Map: new (element: HTMLElement, state: Record<string, unknown>) => YandexMapInstance
  Placemark: new (coordinates: number[], properties: Record<string, unknown>, options: Record<string, unknown>) => YandexPlacemark
}

declare global {
  interface Window { ymaps?: YandexMapsApi }
}

const coordinates: Record<number, [number, number]> = {
  5122: [55.7601, 37.6062],
  5123: [55.7708, 37.6214],
  5124: [55.782, 37.633],
  5339: [55.7564, 37.6912],
  5340: [55.7312, 37.6675],
  20: [55.7088, 37.6195],
  111: [55.7421, 37.5354],
  958: [55.748, 37.625],
}

function coordinatesFromGeometry(geometry?: Record<string, unknown>): [number, number] | undefined {
  const points: Array<[number, number]> = []
  const collect = (value: unknown) => {
    if (!Array.isArray(value)) return
    if (value.length >= 2 && typeof value[0] === 'number' && typeof value[1] === 'number') {
      points.push([value[1], value[0]])
      return
    }
    value.forEach(collect)
  }
  collect(geometry?.coordinates)
  if (!points.length) return undefined
  const total = points.reduce(([latitude, longitude], point) => [latitude + point[0], longitude + point[1]], [0, 0])
  return [total[0] / points.length, total[1] / points.length]
}

let mapsPromise: Promise<YandexMapsApi> | null = null

function loadYandexMaps() {
  if (window.ymaps) return Promise.resolve(window.ymaps)
  if (mapsPromise) return mapsPromise
  mapsPromise = new Promise((resolve, reject) => {
    const existing = document.getElementById('yandex-maps-api') as HTMLScriptElement | null
    const finish = () => window.ymaps ? resolve(window.ymaps) : reject(new Error('API Яндекс.Карт не инициализирован'))
    if (existing) { existing.addEventListener('load', finish, { once: true }); existing.addEventListener('error', () => reject(new Error('Не удалось загрузить Яндекс.Карты')), { once: true }); return }
    const script = document.createElement('script')
    const apiKey = import.meta.env.VITE_YANDEX_MAPS_API_KEY
    const params = new URLSearchParams({ lang: 'ru_RU' })
    if (apiKey) params.set('apikey', apiKey)
    script.id = 'yandex-maps-api'
    script.src = `https://api-maps.yandex.ru/2.1/?${params.toString()}`
    script.async = true
    script.onload = finish
    script.onerror = () => reject(new Error('Не удалось загрузить Яндекс.Карты'))
    document.head.appendChild(script)
  })
  return mapsPromise
}

const escapeHtml = (value: string) => value.replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]!)

export function YandexRiskMap({ objects, incidents, onSelect }: { objects: InfrastructureObject[]; incidents: Incident[]; onSelect: (incident: Incident) => void }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [error, setError] = useState('')
  const activeIncidents = useMemo(() => incidents.filter((item) => item.status === 'new' || item.status === 'in_review'), [incidents])

  useEffect(() => {
    let disposed = false
    let map: YandexMapInstance | null = null
    setError('')
    void loadYandexMaps().then((ymaps) => ymaps.ready(() => {
      if (disposed || !containerRef.current) return
      map = new ymaps.Map(containerRef.current, { center: [55.751244, 37.618423], zoom: 11, controls: ['zoomControl', 'typeSelector', 'fullscreenControl'] })
      objects.forEach((object) => {
        const point = coordinatesFromGeometry(object.geometry) ?? coordinates[object.object_id]
        if (!point) return
        const incident = activeIncidents.find((item) => item.object_id === object.object_id)
        const color = incident?.risk_level === 'critical' ? 'red' : incident?.risk_level === 'high' ? 'orange' : 'blue'
        const content = incident
          ? `<strong>${escapeHtml(incident.title)}</strong><br><span>${escapeHtml(object.dispatcher_name)}</span><br><b>Вероятность: ${formatPercent(incident.risk_score)}</b><br><small>${escapeHtml(predictionTypeShortLabel[incident.incident_type])}</small>`
          : `<strong>${escapeHtml(object.dispatcher_name)}</strong><br><span>Активных тревог нет</span>`
        const placemark = new ymaps.Placemark(point, { balloonContent: content, hintContent: object.dispatcher_name }, { preset: `islands#${color}DotIcon` })
        if (incident) placemark.events.add('click', () => onSelect(incident))
        map?.geoObjects.add(placemark)
      })
    })).catch((cause: unknown) => { if (!disposed) setError(cause instanceof Error ? cause.message : 'Яндекс.Карты недоступны') })
    return () => { disposed = true; map?.destroy() }
  }, [objects, activeIncidents, onSelect])

  return <div className="yandex-map-wrap"><div ref={containerRef} className="yandex-map" />{error && <div className="map-error"><strong>Карта временно недоступна</strong><span>{error}</span></div>}<div className="map-legend"><span><i className="legend-dot legend-dot--critical" />Критический</span><span><i className="legend-dot legend-dot--high" />Высокий</span><span><i className="legend-dot legend-dot--normal" />Без тревог</span></div></div>
}
