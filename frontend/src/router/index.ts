import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '../stores/auth'
import { createAuthGuard } from './guards'

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    requiresAdmin?: boolean
    guestOnly?: boolean
  }
}

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('../views/HomeView.vue'),
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { guestOnly: true },
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('../views/RegisterView.vue'),
      meta: { guestOnly: true },
    },
    {
      path: '/reset-password',
      name: 'reset-password',
      component: () => import('../views/ResetPasswordView.vue'),
      meta: { guestOnly: true },
    },
    {
      path: '/admin',
      name: 'admin-console',
      component: () => import('../views/AdminConsoleView.vue'),
      // 管理台页面统一走 requiresAuth + requiresAdmin 守卫。
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/admin/users',
      name: 'admin-users',
      component: () => import('../views/AdminUsersView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/admin/stocks',
      name: 'admin-stocks',
      component: () => import('../views/AdminStocksView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/admin/jobs',
      name: 'admin-jobs',
      component: () => import('../views/AdminJobsView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/profile',
      name: 'profile',
      component: () => import('../views/ProfileView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/profile/change-password',
      name: 'change-password',
      component: () => import('../views/ChangePasswordView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/stocks/:tsCode',
      name: 'stock-detail',
      component: () => import('../views/StockDetailView.vue'),
    },
    {
      path: '/news/hot',
      name: 'hot-news',
      component: () => import('../views/HotNewsView.vue'),
    },
    {
      path: '/analysis',
      name: 'analysis-workbench',
      component: () => import('../views/AnalysisWorkbenchView.vue'),
    },
    {
      path: '/watchlist',
      name: 'watchlist',
      component: () => import('../views/WatchlistView.vue'),
      meta: { requiresAuth: true },
    },
  ],
})

router.beforeEach(async (to) => {
  // 每次导航都经由统一守卫，确保鉴权与重定向策略一致生效。
  const authStore = useAuthStore()
  const guard = createAuthGuard(authStore)
  return guard({
    fullPath: to.fullPath,
    query: to.query,
    meta: {
      requiresAuth: to.meta.requiresAuth,
      requiresAdmin: to.meta.requiresAdmin,
      guestOnly: to.meta.guestOnly,
    },
  })
})
