import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, requestJson } from './http'

describe('requestJson', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('keeps error payload on ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        headers: {
          get: () => 'application/json',
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
  })
})
