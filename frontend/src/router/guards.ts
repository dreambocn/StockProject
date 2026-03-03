type RouteLike = {
  fullPath: string
  query: Record<string, unknown>
  meta: {
    requiresAuth?: boolean
    guestOnly?: boolean
  }
}

type GuardStoreLike = {
  initialized: boolean
  isAuthenticated: boolean
  initialize: () => Promise<void>
}

export const createAuthGuard = (authStore: GuardStoreLike) => {
  return async (to: RouteLike) => {
    if (!authStore.initialized) {
      await authStore.initialize()
    }

    if (to.meta.requiresAuth && !authStore.isAuthenticated) {
      return {
        path: '/login',
        query: { redirect: to.fullPath },
      }
    }

    if (to.meta.guestOnly && authStore.isAuthenticated) {
      const redirect = typeof to.query.redirect === 'string' ? to.query.redirect : '/'
      return { path: redirect }
    }

    return true
  }
}
