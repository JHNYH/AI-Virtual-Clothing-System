/**
 * 后端接口封装（学生演示项目）
 *
 * 供页面直接调用，不在此处写业务参数含义，由调用方传参。
 * - 登录：sendCode（发验证码）、auth（登录/注册）、logout（退出）。
 * - 图片：uploadMyImage（上传）、myImages（我的图片列表）、editImage（单图编辑）、mergeImages（双图合并）、searchImages（文搜图/图搜图）。
 * - 记录：myRecords（历史记录列表）。
 */
import http from './http'

const FORM_URLENCODED_HEADERS = { 'Content-Type': 'application/x-www-form-urlencoded' }
const JSON_HEADERS = { 'Content-Type': 'application/json' }
const PYTHON_TIMEOUT = 300000
/** 上传链路内部会串行调用 Python（图片审核 + 向量化），比普通接口慢很多，用默认 60s 会超时 */
const UPLOAD_TIMEOUT = 300000

/**
 * 后端文件大小上限，与 application.yml 的 spring.servlet.multipart.max-file-size、
 * aliyun.oss.max-size 保持一致（50MB）。前端先拦：超限请求会被容器拒绝且连错误响应都收不到，
 * 用户只会看到 Network Error。
 */
export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024

// ---------- 登录 ----------
export function sendCode(email) {
  return http.post('/user/send-code', { email })
}

export function auth(payload) {
  return http.post('/user/auth', payload)
}

export function logout(token) {
  if (token) {
    return http.post('/user/logout', null, {
      headers: { Authorization: `Bearer ${token}` },
    })
  }
  return http.post('/user/logout')
}

// ---------- 图片 ----------
export function uploadMyImage(file) {
  const fd = new FormData()
  fd.append('file', file)
  return http.post('/file/upload/image', fd, {
    timeout: UPLOAD_TIMEOUT,
  })
}

export function editImage(params) {
  return http.post('/file/edit', params, {
    headers: JSON_HEADERS,
    timeout: PYTHON_TIMEOUT,
  })
}

export function mergeImages(params) {
  return http.post('/file/merge', params, {
    headers: JSON_HEADERS,
    timeout: PYTHON_TIMEOUT,
  })
}

/** 文搜图传 query；图搜图传 file（或 image 为已有图 URL），有 file 时用 FormData，否则用 URLSearchParams */
export function searchImages(params) {
  if (params.file) {
    const fd = new FormData()
    if (params.query?.trim()) fd.append('query', params.query.trim())
    fd.append('file', params.file)
    return http.post('/file/search', fd)
  }
  const body = new URLSearchParams()
  if (params.query?.trim()) body.append('query', params.query.trim())
  if (params.image?.trim()) body.append('image', params.image.trim())
  return http.post('/file/search', body, {
    headers: FORM_URLENCODED_HEADERS,
  })
}

export function myImages() {
  return http.get('/file/my-images')
}

// ---------- 记录 ----------
export function myRecords() {
  return http.get('/record/my')
}

