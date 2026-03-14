import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: true,
    proxy: {
      '/predict': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/export-plot': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
