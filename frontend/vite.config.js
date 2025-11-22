import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vite configuration for React + TailwindCSS
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: true,
    proxy: {
      // Proxy API requests to the backend gateway
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
        timeout: 30000,  // 30 second timeout
        proxyTimeout: 30000,  // 30 second proxy timeout
      }
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  }
})
