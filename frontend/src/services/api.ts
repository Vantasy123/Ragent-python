import axios from 'axios'

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

function notifyUnauthorized() {
  window.dispatchEvent(new Event('ragent:unauthorized'))
}

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('ragent_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const response = error.response
    const payload = response?.data
    let detail = payload?.detail

    if (response?.status === 401 && !String(response.config?.url || '').includes('/auth/login')) {
      notifyUnauthorized()
    }

    if (!detail && typeof payload === 'string') {
      if (response?.status === 413) {
        detail = '上传文件过大，已被前端网关拒绝。'
      } else if (payload.includes('<html')) {
        detail = `请求失败，网关返回 ${response?.status || 'unknown'}。`
      } else {
        detail = payload
      }
    }

    return Promise.reject({
      status: response?.status,
      detail,
      message: error.message,
      raw: payload,
    })
  },
)

export default apiClient
