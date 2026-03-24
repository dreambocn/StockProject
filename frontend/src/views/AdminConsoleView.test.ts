import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { MotionPlugin } from '@vueuse/motion'

import { i18n, setAppLocale } from '../i18n'
import AdminConsoleView from './AdminConsoleView.vue'

const mountAdminConsole = async () => {
  setAppLocale('zh-CN')
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/admin', component: AdminConsoleView },
      { path: '/admin/users', component: { template: '<div>users</div>' } },
      { path: '/admin/stocks', component: { template: '<div>stocks</div>' } },
      { path: '/admin/evaluations', component: { template: '<div>evaluations</div>' } },
    ],
  })
  await router.push('/admin')
  await router.isReady()

  return mount(AdminConsoleView, {
    global: {
      plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
    },
  })
}

describe('AdminConsoleView', () => {
  it('shows three admin feature entries', async () => {
    const wrapper = await mountAdminConsole()

    expect(wrapper.text()).toContain('后台管理中心')
    expect(wrapper.text()).toContain('用户管理中心')
    expect(wrapper.text()).toContain('股票管理中心')
    expect(wrapper.text()).toContain('实验评估中心')
    expect(wrapper.html()).toContain('/admin/users')
    expect(wrapper.html()).toContain('/admin/stocks')
    expect(wrapper.html()).toContain('/admin/evaluations')
  })
})
