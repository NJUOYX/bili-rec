import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发期通过代理把 /api 与 /ws 转发到本地后端（默认 :2233），
// 前后端可独立热更（见 frontend-design.md §4/§12）。
const BACKEND = process.env.VITE_BACKEND ?? 'http://127.0.0.1:2233'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/ws': { target: BACKEND, changeOrigin: true, ws: true },
    },
  },
})
