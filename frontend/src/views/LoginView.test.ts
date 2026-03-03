import { describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { MotionPlugin } from '@vueuse/motion'

import { i18n, setAppLocale } from '../i18n'
import LoginView from './LoginView.vue'

const jsonResponse = (ok: boolean, status: number, payload: unknown) => ({
  ok,
  status,
  headers: {
    get: () => 'application/json',
  },
  json: async () => payload,
})

const mountLoginView = async () => {
  setAppLocale('zh-CN')

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div>home</div>' } },
      { path: '/login', component: LoginView },
      { path: '/register', component: { template: '<div>register</div>' } },
    ],
  })
  await router.push('/login')
  await router.isReady()

  return mount(LoginView, {
    global: {
      plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
    },
  })
}

describe('LoginView', () => {
  it('maps backend login error message to localized text', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(false, 401, {
          detail: 'invalid credentials',
        }),
      ),
    )

    const wrapper = await mountLoginView()
    const inputs = wrapper.findAll('input')
    if (!inputs[0] || !inputs[1]) {
      throw new Error('expected account and password inputs')
    }
    await inputs[0].setValue('alice')
    await inputs[1].setValue('wrongpass')

    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.text()).toContain('用户名或密码错误')
  })

  it('shows captcha area after repeated failed login', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(
          jsonResponse(false, 401, {
            detail: 'invalid credentials',
          }),
        )
        .mockResolvedValueOnce(
          jsonResponse(false, 401, {
            detail: {
              message: 'invalid credentials',
              captcha_required: true,
            },
          }),
        )
        .mockResolvedValueOnce(
          jsonResponse(true, 200, {
            captcha_id: 'challenge-1',
            image_base64: 'ZmFrZQ==',
            expires_in: 300,
          }),
        ),
    )

    const wrapper = await mountLoginView()
    const inputs = wrapper.findAll('input')
    if (!inputs[0] || !inputs[1]) {
      throw new Error('expected account and password inputs')
    }
    await inputs[0].setValue('alice')
    await inputs[1].setValue('wrongpass')

    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.text()).toContain('图像验证码')
  })

  it('submits captcha fields when captcha is required', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(false, 401, {
          detail: 'invalid credentials',
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse(false, 401, {
          detail: {
            message: 'invalid credentials',
            captcha_required: true,
          },
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse(true, 200, {
          captcha_id: 'challenge-1',
          image_base64: 'ZmFrZQ==',
          expires_in: 300,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse(true, 200, {
          access_token: 'access-001',
          refresh_token: 'refresh-001',
          token_type: 'bearer',
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse(true, 200, {
          id: 'u-1',
          username: 'alice',
          email: 'alice@example.com',
          is_active: true,
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = await mountLoginView()
    const inputs = wrapper.findAll('input')
    if (!inputs[0] || !inputs[1]) {
      throw new Error('expected account and password inputs')
    }
    await inputs[0].setValue('alice')
    await inputs[1].setValue('wrongpass')

    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    const allInputs = wrapper.findAll('input')
    if (!allInputs[1] || !allInputs[2]) {
      throw new Error('expected password and captcha inputs')
    }
    await allInputs[1].setValue('Passw0rd!123')
    await allInputs[2].setValue('ABCD')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    const loginRequest = fetchMock.mock.calls[3] as [string, RequestInit]
    expect(loginRequest[0]).toContain('/api/auth/login')
    expect(loginRequest[1].body).toContain('"captcha_id":"challenge-1"')
    expect(loginRequest[1].body).toContain('"captcha_code":"ABCD"')
  })
})
