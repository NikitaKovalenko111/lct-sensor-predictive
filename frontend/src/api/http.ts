import { accessTokenStore, apiRuntime, CURRENT_USER_KEY } from './runtime'

interface ApiErrorBody {
  error?: string
  message?: string
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: 'http' | 'network' | 'timeout' | 'contract',
    public readonly details?: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

const statusMessages: Record<number, string> = {
  400: 'Запрос содержит некорректные данные.',
  401: 'Сессия истекла. Войдите снова.',
  403: 'Недостаточно прав для выполнения операции.',
  404: 'Запрошенные данные не найдены.',
  409: 'Данные конфликтуют с текущим состоянием системы.',
  429: 'Слишком много запросов. Повторите попытку позже.',
  500: 'Внутренняя ошибка сервера.',
  502: 'Сервис модели вернул некорректный ответ.',
  503: 'Сервис временно недоступен.',
}

const readErrorBody = async (response: Response): Promise<ApiErrorBody | undefined> => {
  const contentType = response.headers.get('content-type') ?? ''
  if (!contentType.includes('application/json')) return undefined
  try { return await response.json() as ApiErrorBody } catch { return undefined }
}

export const buildQuery = <T extends object>(values: T) => {
  const query = new URLSearchParams()
  Object.entries(values).forEach(([key, value]: [string, unknown]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value))
  })
  const serialized = query.toString()
  return serialized ? `?${serialized}` : ''
}

export class HttpClient {
  async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), apiRuntime.timeoutMs)
    const token = accessTokenStore.get()
    const hasBody = init.body !== undefined

    try {
      const response = await fetch(`${apiRuntime.baseUrl}${path}`, {
        ...init,
        signal: controller.signal,
        headers: {
          Accept: 'application/json',
          ...(hasBody ? { 'Content-Type': 'application/json' } : {}),
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...init.headers,
        },
      })

      if (!response.ok) {
        const body = await readErrorBody(response)
        if (response.status === 401 && token) {
          accessTokenStore.clear()
          localStorage.removeItem(CURRENT_USER_KEY)
          window.dispatchEvent(new Event('lct:unauthorized'))
        }
        throw new ApiError(body?.error ?? body?.message ?? statusMessages[response.status] ?? `Ошибка API: ${response.status}`, response.status, 'http', body)
      }
      if (response.status === 204) return undefined as T

      const contentType = response.headers.get('content-type') ?? ''
      if (!contentType.includes('application/json')) {
        throw new ApiError('Ответ API не соответствует ожидаемому JSON-контракту.', response.status, 'contract')
      }
      return await response.json() as T
    } catch (cause) {
      if (cause instanceof ApiError) throw cause
      if (cause instanceof DOMException && cause.name === 'AbortError') {
        throw new ApiError('Сервер не ответил за отведённое время.', 0, 'timeout')
      }
      throw new ApiError('Не удалось подключиться к серверу.', 0, 'network', cause)
    } finally {
      window.clearTimeout(timeout)
    }
  }
}

export const httpClient = new HttpClient()
