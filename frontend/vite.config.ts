import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Tauri 用 tauri://localhost 或 asset 协议加载，必须用相对路径
  base: './',
  // Tauri 固定端口，避免每次变化
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
      },
    },
  },
  // 打包产物放到 frontend/dist（Tauri 默认查找路径）
  build: {
    outDir: 'dist',
    target: 'esnext',
    // Tauri 构建时 chunk 大小警告可忽略
    chunkSizeWarningLimit: 1500,
  },
})
