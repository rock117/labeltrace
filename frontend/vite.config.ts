import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        // Compose 开发挂载时用 api:8000；本机默认 8001
        target: process.env.VITE_API_PROXY || 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
})
