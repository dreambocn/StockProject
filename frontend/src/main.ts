import { createApp } from 'vue'
import { MotionPlugin } from '@vueuse/motion'
import { createPinia } from 'pinia'
import './style.css'
import App from './App.vue'
import { i18n } from './i18n'
import { router } from './router'

// 插件注册顺序在入口收口，确保路由、状态和 i18n 在全局可用后再挂载应用。
createApp(App).use(createPinia()).use(router).use(i18n).use(MotionPlugin).mount('#app')
