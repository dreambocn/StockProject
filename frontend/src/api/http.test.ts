import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, buildApiUrl, requestJson } from './http'

describe('requestJson', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it('does not duplicate api prefix when base url already points to api root', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '/api')
    vi.resetModules()

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      headers: {
        get: () => 'application/json',
      },
      json: async () => ({ ok: true }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const { requestJson: requestWithDockerBase } = await import('./http')

    await requestWithDockerBase('/api/auth/login', { method: 'POST', body: {} })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/login',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('keeps error payload on ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        headers: {
          get: (name: string) => (name === 'x-request-id' ? 'req-001' : 'application/json'),
        },
        json: async () => ({
          detail: {
            message: 'captcha required',
            captcha_required: true,
          },
        }),
      }),
    )

    let captured: unknown
    try {
      await requestJson('/api/auth/login', { method: 'POST', body: {} })
    } catch (error) {
      captured = error
    }

    expect(captured).toBeInstanceOf(ApiError)
    expect((captured as ApiError).status).toBe(401)
    expect((captured as ApiError).payload).toEqual({
      detail: {
        message: 'captcha required',
        captcha_required: true,
      },
    })
    expect((captured as ApiError).requestId).toBe('req-001')
  })

  it('exports API URL builder for direct download requests', () => {
    expect(buildApiUrl('/api/analysis/reports/r-1/export?format=package')).toContain(
      '/api/analysis/reports/r-1/export?format=package',
    )
  })
})
