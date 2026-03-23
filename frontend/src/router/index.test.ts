import { describe, expect, it } from 'vitest'

import { router } from './index'

describe('router lazy routes', () => {
  it('uses lazy-loaded view components for page routes', () => {
    const routeNames = [
      'home',
      'login',
      'register',
      'reset-password',
      'admin-console',
      'admin-users',
      'admin-stocks',
      'profile',
      'change-password',
      'stock-detail',
      'hot-news',
      'analysis-workbench',
    ]

    for (const routeName of routeNames) {
      const route = router.getRoutes().find((item) => item.name === routeName)
      expect(route).toBeDefined()
      expect(typeof route?.components?.default).toBe('function')
    }
  })
})

it('registers the analysis workbench route', () => {
  const route = router.getRoutes().find((item) => item.name === 'analysis-workbench')
  expect(route).toBeDefined()
  expect(route?.path).toBe('/analysis')
})
