type RouteLike = {
  fullPath: string
  query: Record<string, unknown>
  meta: {
    requiresAuth?: boolean
    requiresAdmin?: boolean
    guestOnly?: boolean
  }
}

type GuardUserLike = {
  user_level: 'user' | 'admin'
}

type GuardStoreLike = {
  initialized: boolean
  isAuthenticated: boolean
  user: GuardUserLike | null
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

    // 权限边界：后台管理页要求 admin 角色，未登录先回登录，已登录但非 admin 回首页。
    if (to.meta.requiresAdmin) {
      if (!authStore.isAuthenticated) {
        return {
          path: '/login',
          query: { redirect: to.fullPath },
        }
      }

      if (authStore.user?.user_level !== 'admin') {
        return { path: '/' }
      }
    }

    // 访客页面：已登录用户不应再次进入登录/注册页。
    if (to.meta.guestOnly && authStore.isAuthenticated) {
      // 仅允许显式携带的 redirect 生效，避免被异常 query 劫持跳转目标。
      const redirect = typeof to.query.redirect === 'string' ? to.query.redirect : '/'
      return { path: redirect }
    }

    return true
  }
}
