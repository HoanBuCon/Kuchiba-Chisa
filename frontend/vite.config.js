import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
// Development serves the SPA and proxies /api to FastAPI so the browser sees a
// single origin, matching production (Caddy) and the account refresh cookie path.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: false },
    },
  },
})
