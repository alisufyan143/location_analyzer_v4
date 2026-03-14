import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    allowedHosts: true,
    hmr: {
      clientPort: 443
    },
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
