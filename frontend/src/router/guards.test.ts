import { describe, expect, it } from 'vitest'

import { createAuthGuard } from './guards'

describe('createAuthGuard', () => {
  it('redirects unauthenticated users to login', async () => {
    const guard = createAuthGuard({
      initialized: true,
      isAuthenticated: false,
      user: null,
      initialize: async () => {},
    })

    const result = await guard({
      fullPath: '/profile',
      query: {},
      meta: { requiresAuth: true },
    })

    expect(result).toEqual({
      path: '/login',
      query: { redirect: '/profile' },
    })
  })

  it('redirects authenticated user away from guest pages', async () => {
    const guard = createAuthGuard({
      initialized: true,
      isAuthenticated: true,
      user: null,
      initialize: async () => {},
    })

    const result = await guard({
      fullPath: '/login',
      query: { redirect: '/profile' },
      meta: { guestOnly: true },
    })

    expect(result).toEqual({ path: '/profile' })
  })

  it('redirects authenticated non-admin away from admin pages', async () => {
    const guard = createAuthGuard({
      initialized: true,
      isAuthenticated: true,
      user: { user_level: 'user' },
      initialize: async () => {},
    })

    const result = await guard({
      fullPath: '/admin/users',
      query: {},
      meta: { requiresAuth: true, requiresAdmin: true },
    })

    expect(result).toEqual({ path: '/' })
  })
})
