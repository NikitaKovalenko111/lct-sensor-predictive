export const ACCESS_TOKEN_KEY = 'lct_access_token'
export const CURRENT_USER_KEY = 'lct_current_user'

const normalizeBaseUrl = (value: string | undefined) => (value ?? '').trim().replace(/\/$/, '')
const parseTimeout = (value: string | undefined) => {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed >= 1_000 ? parsed : 15_000
}

export const apiRuntime = {
  mode: import.meta.env.VITE_API_MODE === 'live' ? 'live' : 'mock',
  baseUrl: normalizeBaseUrl(import.meta.env.VITE_API_URL),
  timeoutMs: parseTimeout(import.meta.env.VITE_API_TIMEOUT_MS),
  incidentStreamEnabled: import.meta.env.VITE_ENABLE_INCIDENT_STREAM === 'true',
  userMutationsEnabled: import.meta.env.VITE_ENABLE_USER_MUTATIONS === 'true',
} as const

export const accessTokenStore = {
  get: () => localStorage.getItem(ACCESS_TOKEN_KEY),
  set: (token: string) => localStorage.setItem(ACCESS_TOKEN_KEY, token),
  clear: () => localStorage.removeItem(ACCESS_TOKEN_KEY),
}
