import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import { MotionPlugin } from '@vueuse/motion'
import { createPinia } from 'pinia'
import 'element-plus/dist/index.css'
import './style.css'
import App from './App.vue'
import { i18n } from './i18n'
import { router } from './router'

createApp(App).use(createPinia()).use(router).use(i18n).use(ElementPlus).use(MotionPlugin).mount('#app')
