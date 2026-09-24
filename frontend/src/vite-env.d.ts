/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_MODE?: 'mock' | 'live'
  readonly VITE_API_URL?: string
  readonly VITE_API_TIMEOUT_MS?: string
  readonly VITE_ENABLE_INCIDENT_STREAM?: 'true' | 'false'
  readonly VITE_ENABLE_USER_MUTATIONS?: 'true' | 'false'
  readonly VITE_YANDEX_MAPS_API_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
