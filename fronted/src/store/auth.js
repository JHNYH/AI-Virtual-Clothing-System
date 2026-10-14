/**
 * 登录态 Store（Pinia）（学生演示项目）
 *
 * 作用：集中存放 token 与用户信息，并持久化到 localStorage，刷新页面不丢失。
 * - state.token：请求头 Authorization 会用到（见 services/http.js 拦截器）。
 * - state.user：如 userId、username、email，可用于顶栏展示。
 * - setAuth(token, user)：登录成功后由 LoginView 调用，写入 state 并同步到 localStorage。
 * - clear()：退出登录时由 AppHeader 调用，清空 state 与 localStorage。
 */
import { defineStore } from 'pinia'

const TOKEN_KEY = 'mengtu_token'
const USER_KEY = 'mengtu_user'

/** base64url 解码为字符串：JWT 声明里可能有中文用户名，不能直接用 atob */
function decodeBase64Url(value) {
  const base64 = value.replace(/-/g, '+').replace(/_/g, '/')
  const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=')
  const bytes = Uint8Array.from(atob(padded), (char) => char.charCodeAt(0))
  return new TextDecoder().decode(bytes)
}

/**
 * 判断 token 是否已过期（读 JWT 的 exp 声明）。
 * 解析失败一律按“已过期”处理，避免格式异常的脏 token 留在本地还能进主界面。
 */
function isTokenExpired(token) {
  if (!token) return true
  try {
    const payload = token.split('.')[1]
    if (!payload) return true
    const { exp } = JSON.parse(decodeBase64Url(payload))
    if (typeof exp !== 'number') return true
    return exp * 1000 <= Date.now()
  } catch {
    return true
  }
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || '',
    user: (() => {
      const raw = localStorage.getItem(USER_KEY)
      try {
        return raw ? JSON.parse(raw) : null
      } catch {
        return null
      }
    })(),
  }),
  getters: {
    /** 是否已登录（路由守卫与顶栏根据此判断）：token 存在且未过期 */
    isLoggedIn: (state) => !!state.token && !isTokenExpired(state.token),
  },
  actions: {
    /** 登录成功：写入 token 与 user，并持久化 */
    setAuth(token, user) {
      this.token = token
      this.user = user
      localStorage.setItem(TOKEN_KEY, token)
      localStorage.setItem(USER_KEY, JSON.stringify(user))
    },
    /** 退出登录：清空内存与 localStorage */
    clear() {
      this.token = ''
      this.user = null
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
    },
  },
})

