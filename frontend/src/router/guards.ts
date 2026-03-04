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
    // 守卫首次执行时先完成会话恢复，避免刷新页面后路由误判。
    if (!authStore.initialized) {
      await authStore.initialize()
    }

    // 受保护页面：未登录则跳转登录并携带 redirect，便于登录后回跳。
    if (to.meta.requiresAuth && !authStore.isAuthenticated) {
      return {
        path: '/login',
        query: { redirect: to.fullPath },
      }
    }

    // 访客页面：已登录用户不应再次进入登录/注册页。
    if (to.meta.guestOnly && authStore.isAuthenticated) {
      const redirect = typeof to.query.redirect === 'string' ? to.query.redirect : '/'
      return { path: redirect }
    }

    return true
  }
}
