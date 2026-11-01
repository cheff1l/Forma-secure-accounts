import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    allowedHosts: ['forma.localtest.me'],
    proxy: {
      '^/(session|sessions|account|login|logout|register|activate|profile|2fa|forgot|reset|support|admin|dev-mail|google|captcha|style\\.css|register\\.js)(?=/|\\?|$)': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
