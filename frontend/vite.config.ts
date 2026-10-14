/// <reference types="vitest/config" />
import path from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { tanstackRouter } from '@tanstack/router-plugin/vite'
import { playwright } from '@vitest/browser-playwright'

// 冷启动时 Vite 中途发现新依赖会重新预构建并整页重载，偶发加载两份 React（QA：reticle-page.test.tsx 首轮失败、重跑通过）。
// 预置 React 与项目用到的 @radix-ui 包，并强制单例。
const RADIX = [
  'alert-dialog',
  'avatar',
  'checkbox',
  'collapsible',
  'dialog',
  'direction',
  'dropdown-menu',
  'icons',
  'label',
  'popover',
  'radio-group',
  'scroll-area',
  'select',
  'separator',
  'slot',
  'switch',
  'tabs',
  'tooltip',
].map((n) => `@radix-ui/react-${n}`)

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    tanstackRouter({
      target: 'react',
      autoCodeSplitting: true,
    }),
    react(),
    tailwindcss(),
  ],
  optimizeDeps: {
    include: [
      'react',
      'react-dom',
      'react-dom/client',
      'react/jsx-runtime',
      'react/jsx-dev-runtime',
      ...RADIX,
    ],
  },
  resolve: {
    dedupe: ['react', 'react-dom'],
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    silent: 'passed-only',
    unstubEnvs: true,
    setupFiles: ['./src/test-utils/setup.ts'],
    browser: {
      enabled: true,
      provider: playwright(),
      instances: [{ browser: 'chromium' }],
    },
    coverage: {
      // include: ['src/**/*.{js,jsx,ts,tsx}'], // Uncomment to expand the report to all src/**/* so untested modules appear as 0% coverage.
      exclude: [
        'src/components/ui/**',
        'src/assets/**',
        'src/tanstack-table.d.ts',
        'src/routeTree.gen.ts',
        'src/test-utils/**',
        'src/routes/**',
      ],
    },
  },
})
