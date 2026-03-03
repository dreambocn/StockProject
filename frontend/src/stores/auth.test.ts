import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useAuthStore } from './auth'

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.unstubAllGlobals()
  })

  it('stores token and user after login', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            access_token: 'access-001',
            refresh_token: 'refresh-001',
            token_type: 'bearer',
          }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            id: 'u-1',
            username: 'alice',
            email: 'alice@example.com',
            is_active: true,
          }),
        }),
    )

    const store = useAuthStore()
    await store.login('alice', 'Passw0rd!123')

    expect(store.isAuthenticated).toBe(true)
    expect(store.user?.email).toBe('alice@example.com')
    expect(localStorage.getItem('auth.accessToken')).toBe('access-001')
    expect(localStorage.getItem('auth.refreshToken')).toBe('refresh-001')
  })

  it('hydrates token values from local storage', () => {
    localStorage.setItem('auth.accessToken', 'access-cache')
    localStorage.setItem('auth.refreshToken', 'refresh-cache')

    const store = useAuthStore()
    store.hydrateFromStorage()

    expect(store.accessToken).toBe('access-cache')
    expect(store.refreshToken).toBe('refresh-cache')
    expect(store.isAuthenticated).toBe(true)
  })

  it('passes captcha fields to login api payload', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          access_token: 'access-001',
          refresh_token: 'refresh-001',
          token_type: 'bearer',
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'u-1',
          username: 'alice',
          email: 'alice@example.com',
          is_active: true,
        }),
      })
    vi.stubGlobal('fetch', fetchMock)

    const store = useAuthStore()
    await store.login('alice', 'Passw0rd!123', {
      captcha_id: 'challenge-1',
      captcha_code: 'ABCD',
    })

    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/api/auth/login')
    expect(options.body).toContain('"captcha_id":"challenge-1"')
    expect(options.body).toContain('"captcha_code":"ABCD"')
  })
})
