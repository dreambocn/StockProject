export class ApiError extends Error {
  status: number
  payload?: unknown

  constructor(message: string, status: number, payload?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
  }
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

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

  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: options.method ?? 'GET',
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  })

  const contentType =
    typeof response.headers?.get === 'function' ? response.headers.get('content-type') : null
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

    throw new ApiError(detail, response.status, payload)
  }

  return payload as T
}
