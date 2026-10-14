import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  /** 后端 API 地址，开发时将所有 /api 请求代理到此地址（可在 .env.development 中设置 PROXY_TARGET） */
  const proxyTarget = env.PROXY_TARGET || 'http://localhost:8080'

  /**
   * 指定用哪个浏览器打开开发页。
   * 注意：Vite 读的是 BROWSER 环境变量，server.open 的值只能表示「打开哪个路径」，
   * 写成 open: 'chrome' 只会打开 /chrome 这个路由，不会换浏览器。
   * 这里默认用本机 Chrome，避免被系统默认浏览器（Edge）接管；换机器时在 .env 里配 BROWSER 覆盖。
   */
  if (!process.env.BROWSER) {
    process.env.BROWSER = env.BROWSER || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
  }

  return {
    plugins: [vue()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      open: true,
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
  }
})

