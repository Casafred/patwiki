import axios from 'axios'

/**
 * 根据运行环境决定后端 API 地址：
 * - 开发模式（vite dev server）：用 /api，由 Vite proxy 转发到 127.0.0.1:8765
 * - 生产模式（Tauri 打包后）：直连 http://127.0.0.1:8765/api（后端已开启 CORS）
 */
const isTauri = !!(window as any).__TAURI_INTERNALS__ || !!(window as any).__TAURI__
const BACKEND_PORT = 8765
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`

const api = axios.create({
  baseURL: isTauri ? `${BACKEND_URL}/api` : '/api',
  timeout: 60000,
})

// 后端启动需要几秒，Tauri 模式下首次请求失败时重试
api.interceptors.response.use(
  (response) => response.data,
  async (error) => {
    // 仅在 Tauri 模式下、网络错误时重试（连接被拒绝 = 后端还没起来）
    if (isTauri && (error.code === 'ERR_NETWORK' || error.message?.includes('Network Error'))) {
      const config = error.config
      if (!config.__retryCount) config.__retryCount = 0
      if (config.__retryCount < 10) {
        config.__retryCount += 1
        await new Promise((r) => setTimeout(r, 800))
        return api.request(config)
      }
    }
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

export default api
export { BACKEND_URL, BACKEND_PORT }
