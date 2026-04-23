import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { MotionPlugin } from '@vueuse/motion'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('element-plus/theme-chalk/base.css', () => ({}))
vi.mock('element-plus/theme-chalk/el-button.css', () => ({}))
vi.mock('element-plus/theme-chalk/el-card.css', () => ({}))
vi.mock('element-plus/theme-chalk/el-descriptions.css', () => ({}))
vi.mock('element-plus/theme-chalk/el-tag.css', () => ({}))

import ProfileView from './ProfileView.vue'
import { i18n, setAppLocale } from '../i18n'
import { useAuthStore } from '../stores/auth'
import { setAppTheme } from '../theme'

const ElCardStub = {
  name: 'ElCard',
  template: '<article class="el-card"><slot /></article>',
}

const ElDescriptionsStub = {
  name: 'ElDescriptions',
  template: '<div class="el-descriptions"><slot /></div>',
}

const ElDescriptionsItemStub = {
  name: 'ElDescriptionsItem',
  props: {
    label: { type: String, default: '' },
  },
  template: `
    <div class="el-descriptions-item">
      <strong>{{ label }}</strong>
      <div><slot /></div>
    </div>
  `,
}

const ElTagStub = {
  name: 'ElTag',
  template: '<span class="el-tag"><slot /></span>',
}

const ElButtonStub = {
  name: 'ElButton',
  emits: ['click'],
  template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>',
}

describe('ProfileView', () => {
  let pinia: ReturnType<typeof createPinia>

  beforeEach(() => {
    setAppLocale('zh-CN')
    setAppTheme('light')
    pinia = createPinia()
    setActivePinia(pinia)
  })

  it('renders account overview and security action in light theme', async () => {
    const authStore = useAuthStore()
    authStore.initialized = true
    authStore.accessToken = 'token'
    authStore.user = {
      id: 'user-1',
      username: 'dreambo',
      email: 'dreambo@example.com',
      is_active: true,
      user_level: 'admin',
    }

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/profile', component: ProfileView },
        { path: '/profile/change-password', component: { template: '<div>change-password</div>' } },
      ],
    })
    await router.push('/profile')
    await router.isReady()

    const wrapper = mount(ProfileView, {
      global: {
        plugins: [pinia, router, i18n, MotionPlugin],
        components: {
          ElCard: ElCardStub,
          ElDescriptions: ElDescriptionsStub,
          ElDescriptionsItem: ElDescriptionsItemStub,
          ElTag: ElTagStub,
          ElButton: ElButtonStub,
        },
      },
    })

    expect(document.documentElement.dataset.theme).toBe('light')
    expect(wrapper.text()).toContain('个人中心')
    expect(wrapper.text()).toContain('dreambo')
    expect(wrapper.text()).toContain('dreambo@example.com')
    expect(wrapper.text()).toContain('账户安全')
    expect(wrapper.text()).toContain('进入修改密码')
    expect(wrapper.find('[data-testid="profile-overview-card"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="profile-security-card"]').exists()).toBe(true)
  })
})
