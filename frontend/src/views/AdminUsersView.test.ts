import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { MotionPlugin } from '@vueuse/motion'

import { i18n, setAppLocale } from '../i18n'
import { useAuthStore } from '../stores/auth'
import AdminUsersView from './AdminUsersView.vue'

const jsonResponse = (payload: unknown) => ({
  ok: true,
  status: 200,
  headers: {
    get: () => 'application/json',
  },
  json: async () => payload,
})

const mountAdminUsersView = async () => {
  setAppLocale('zh-CN')
  const pinia = createPinia()
  const authStore = useAuthStore(pinia)
  authStore.accessToken = 'admin-access-token'

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/admin/users', component: AdminUsersView }],
  })
  await router.push('/admin/users')
  await router.isReady()

  return mount(AdminUsersView, {
    global: {
      plugins: [pinia, router, i18n, ElementPlus, MotionPlugin],
    },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('AdminUsersView', () => {
  it('renders neo users dashboard shell and themed table', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse([
          {
            id: 'u-1',
            username: 'admin',
            email: 'admin@example.com',
            is_active: true,
            user_level: 'admin',
            created_at: '2026-03-01T00:00:00Z',
            updated_at: '2026-03-01T00:00:00Z',
            last_login_at: '2026-03-05T00:14:08Z',
          },
        ]),
      ),
    )

    const wrapper = await mountAdminUsersView()
    await flushPromises()

    expect(wrapper.find('[data-testid="admin-users-neo-shell"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="admin-users-table"]').classes()).toContain('theme-table')
    expect(wrapper.text()).toContain('用户管理中心')
    expect(wrapper.text()).toContain('admin@example.com')
  })

  it('creates user then reloads user list', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse([
          {
            id: 'u-1',
            username: 'admin',
            email: 'admin@example.com',
            is_active: true,
            user_level: 'admin',
            created_at: '2026-03-01T00:00:00Z',
            updated_at: '2026-03-01T00:00:00Z',
            last_login_at: '2026-03-05T00:14:08Z',
          },
        ]),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          id: 'u-2',
          username: 'neo_user',
          email: 'neo_user@example.com',
          is_active: true,
          user_level: 'user',
          created_at: '2026-03-05T00:00:00Z',
          updated_at: '2026-03-05T00:00:00Z',
          last_login_at: null,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            id: 'u-1',
            username: 'admin',
            email: 'admin@example.com',
            is_active: true,
            user_level: 'admin',
            created_at: '2026-03-01T00:00:00Z',
            updated_at: '2026-03-01T00:00:00Z',
            last_login_at: '2026-03-05T00:14:08Z',
          },
          {
            id: 'u-2',
            username: 'neo_user',
            email: 'neo_user@example.com',
            is_active: true,
            user_level: 'user',
            created_at: '2026-03-05T00:00:00Z',
            updated_at: '2026-03-05T00:00:00Z',
            last_login_at: null,
          },
        ]),
      )
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = await mountAdminUsersView()
    await flushPromises()

    const inputs = wrapper.findAll('input')
    expect(inputs.length).toBeGreaterThanOrEqual(3)
    await inputs[0]!.setValue('neo_user')
    await inputs[1]!.setValue('neo_user@example.com')
    await inputs[2]!.setValue('Abc@1234!')

    await wrapper.get('[data-testid="admin-users-create"]').trigger('click')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(3)

    const createCall = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(createCall[0]).toContain('/api/admin/users')
    expect(createCall[1].method).toBe('POST')

    const refreshCall = fetchMock.mock.calls[2] as [string, RequestInit]
    expect(refreshCall[0]).toContain('/api/admin/users')
    expect(refreshCall[1].method).toBe('GET')
    expect(wrapper.text()).toContain('neo_user@example.com')
  })
})
