export class ApiError extends Error {
  status: number
  payload?: unknown
  requestId?: string | null

  constructor(message: string, status: number, payload?: unknown, requestId?: string | null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
    this.requestId = requestId ?? null
  }
}

// 未配置时回退本地地址，便于本机调试与测试环境直接启动。
const apiBaseUrl = normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL)

function normalizeApiBaseUrl(value: string | undefined) {
  if (value === undefined) {
    return 'http://127.0.0.1:8000'
  }

  return value.trim().replace(/\/+$/, '')
}

export function buildApiUrl(path: string) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  if (!apiBaseUrl) {
    return normalizedPath
  }

  // Docker 同源部署时前端基址可能配置为 /api，而业务 API path 已经以 /api 开头；
  // 这里在统一入口消除重复前缀，避免请求落到后端不存在的 /api/api/*。
  if (
    apiBaseUrl.endsWith('/api') &&
    (normalizedPath === '/api' || normalizedPath.startsWith('/api/'))
  ) {
    return `${apiBaseUrl.slice(0, -'/api'.length)}${normalizedPath}`
  }

  return `${apiBaseUrl}${normalizedPath}`
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  accessToken?: string | null
}

export const requestJson = async <T>(path: string, options: RequestOptions = {}) => {
  // 统一 API 请求入口：集中处理鉴权头、JSON 解析和错误归一化。
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }

  if (options.accessToken) {
    headers.Authorization = `Bearer ${options.accessToken}`
  }

  const response = await fetch(buildApiUrl(path), {
    method: options.method ?? 'GET',
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  })

  const contentType =
    typeof response.headers?.get === 'function' ? response.headers.get('content-type') : null
  const requestId =
    typeof response.headers?.get === 'function' ? response.headers.get('x-request-id') : null
  // 部分异常响应可能不是 JSON，避免强行解析导致二次错误。
  const isJson = contentType?.includes('application/json') ?? true
  const payload = isJson ? await response.json() : null

  if (!response.ok) {
    // 优先提取后端 detail/message，确保前端 i18n 映射有稳定输入。
    const detailValue = payload && typeof payload === 'object' && 'detail' in payload ? payload.detail : null
    const detail =
      typeof detailValue === 'string'
        ? detailValue
        : detailValue && typeof detailValue === 'object' && 'message' in detailValue
          ? String(detailValue.message)
        : `Request failed with status ${response.status}`

    throw new ApiError(detail, response.status, payload, requestId)
  }

  return payload as T
}

const parseEventPayload = (event: MessageEvent<string>) => {
  try {
    return JSON.parse(event.data) as Record<string, unknown>
  } catch {
    return { detail: event.data }
  }
}

type SseHandlerMap = Partial<Record<'status' | 'reused' | 'delta' | 'completed' | 'error', (payload: Record<string, unknown>) => void>>

export const openEventSource = (path: string, handlers: SseHandlerMap) => {
  const source = new EventSource(buildApiUrl(path))
  const eventNames: Array<keyof SseHandlerMap> = ['status', 'reused', 'delta', 'completed', 'error']

  for (const eventName of eventNames) {
    const handler = handlers[eventName]
    if (!handler) {
      continue
    }
    source.addEventListener(eventName, (event) => {
      handler(parseEventPayload(event as MessageEvent<string>))
    })
  }

  source.onerror = () => {
    // EventSource 断线时统一回调错误分支，交给上层决定是否重试。
    handlers.error?.({ detail: 'eventsource_error' })
  }

  return () => source.close()
}
