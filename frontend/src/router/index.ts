import { createRouter, createWebHistory } from 'vue-router'

import HomeView from '../views/HomeView.vue'
import ChangePasswordView from '../views/ChangePasswordView.vue'
import LoginView from '../views/LoginView.vue'
import ProfileView from '../views/ProfileView.vue'
import RegisterView from '../views/RegisterView.vue'
import ResetPasswordView from '../views/ResetPasswordView.vue'
import { useAuthStore } from '../stores/auth'
import { createAuthGuard } from './guards'

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    guestOnly?: boolean
  }
}

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
    },
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { guestOnly: true },
    },
    {
      path: '/register',
      name: 'register',
      component: RegisterView,
      meta: { guestOnly: true },
    },
    {
      path: '/reset-password',
      name: 'reset-password',
      component: ResetPasswordView,
      meta: { guestOnly: true },
    },
    {
      path: '/profile',
      name: 'profile',
      component: ProfileView,
      meta: { requiresAuth: true },
    },
    {
      path: '/profile/change-password',
      name: 'change-password',
      component: ChangePasswordView,
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
      guestOnly: to.meta.guestOnly,
    },
  })
})
