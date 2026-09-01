import axios from 'axios'

/**
 * 根据运行环境决定后端 API 地址：
 * - 开发模式（vite dev server）：用 /api，由 Vite proxy 转发到 127.0.0.1:8765
 * - 生产模式（Tauri 打包后）：直连 http://127.0.0.1:8765/api（后端已开启 CORS）
 */
const isTauri = '__TAURI_INTERNALS__' in window || '__TAURI__' in window
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
    // Download endpoints intentionally use responseType=blob. FastAPI error
    // responses therefore arrive as a Blob too, which used to hide the real
    // validation message behind a generic export failure.
    const responseData = error.response?.data
    if (responseData instanceof Blob) {
      try {
        const text = await responseData.text()
        if (text) error.response.data = JSON.parse(text)
      } catch {
        // Keep the original Blob when it is a non-JSON response.
      }
    }
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

export default api
export { BACKEND_URL, BACKEND_PORT }
