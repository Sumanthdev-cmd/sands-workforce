import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react()],
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
      allowedHosts: (env.VITE_DEV_ALLOWED_HOSTS || '')
        .split(',').map(host => host.trim()).filter(Boolean),
      proxy: {
        '/api': 'http://127.0.0.1:8000',
        '/openapi.json': 'http://127.0.0.1:8000',
      },
    },
  }
})
