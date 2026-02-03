import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:11451',
        changeOrigin: true,
      },
      '/v1': {
        target: 'http://localhost:11451',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:11451/api',
        ws: true,
      },
    },
  },
})
