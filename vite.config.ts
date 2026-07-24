import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import viteCompression from 'vite-plugin-compression'
import path from 'path'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    viteCompression({
      algorithm: 'gzip',
      threshold: 10240,
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes('node_modules/react/') || id.includes('node_modules/react-dom/') || id.includes('node_modules/react-router-dom/') || id.includes('node_modules/scheduler/')) {
            return 'vendor-react'
          }
          if (id.includes('node_modules/@radix-ui/')) {
            return 'vendor-ui'
          }
          if (id.includes('node_modules/@tanstack/') || id.includes('node_modules/axios/') || id.includes('node_modules/date-fns/')) {
            return 'vendor-data'
          }
          if (id.includes('node_modules/lucide-react/') || id.includes('node_modules/react-markdown/') || id.includes('node_modules/remark-gfm/')) {
            return 'vendor-markdown'
          }
          if (id.includes('node_modules/sonner/') || id.includes('node_modules/react-hook-form/') || id.includes('node_modules/@hookform/')) {
            return 'vendor-form'
          }
        },
      },
    },
  },
  server: {
    host: '0.0.0.0',
    port: 8848,
    proxy: {
      '/api': {
        target: 'http://localhost:8456',
        changeOrigin: true,
      },
    },
  },
})
