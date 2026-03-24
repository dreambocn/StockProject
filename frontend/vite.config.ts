/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    Components({
      // 关闭 d.ts 产物，避免在仓库根目录额外生成自动声明文件。
      dts: false,
      // Element Plus 采用组件级别按需引入，并同步拉取对应 CSS。
      resolvers: [ElementPlusResolver({ importStyle: 'css' })],
    }),
  ],
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
    server: {
      deps: {
        // 关键测试配置：按需引入会让 Element Plus 子路径携带 CSS 副作用；
        // 这里强制内联转换，避免 Vitest 将其外置给 Node 直接加载 CSS。
        inline: ['element-plus'],
      },
    },
  },
})
