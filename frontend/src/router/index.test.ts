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
      'admin-jobs',
      'admin-evaluations',
      'profile',
      'change-password',
      'stock-detail',
      'hot-news',
      'analysis-workbench',
      'watchlist',
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

it('registers the watchlist route', () => {
  const route = router.getRoutes().find((item) => item.name === 'watchlist')
  expect(route).toBeDefined()
  expect(route?.path).toBe('/watchlist')
})

it('registers the admin evaluations route', () => {
  const route = router.getRoutes().find((item) => item.name === 'admin-evaluations')
  expect(route).toBeDefined()
  expect(route?.path).toBe('/admin/evaluations')
  expect(route?.meta.requiresAdmin).toBe(true)
})
