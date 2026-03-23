/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  build: {
    // 关键构建策略：当前项目显式依赖 Element Plus，生产包体天然偏大；
    // 将其独立拆包并把告警阈值调到符合现状的范围，避免无效噪音掩盖真实构建问题。
    chunkSizeWarningLimit: 850,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return undefined
          }

          // 关键构建优化：将大体积依赖拆成稳定 vendor chunk，避免入口包持续膨胀并触发构建告警。
          const normalizedId = id.replaceAll('\\', '/')

          if (normalizedId.includes('element-plus')) {
            return 'vendor-element-plus'
          }
          if (normalizedId.includes('@vueuse/motion')) {
            return 'vendor-motion'
          }
          if (normalizedId.includes('vue-i18n')) {
            return 'vendor-i18n'
          }
          if (normalizedId.includes('pinia')) {
            return 'vendor-pinia'
          }
          if (normalizedId.includes('vue-router')) {
            return 'vendor-router'
          }

          return 'vendor-shared'
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
  },
})
