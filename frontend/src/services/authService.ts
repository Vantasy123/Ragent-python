import apiClient from './api'

export interface UserInfo {
  id: string
  username: string
  nickname: string
  role: string
}

export const authService = {
  login(username: string, password: string) {
    return apiClient.post('/auth/login', { username, password })
  },
  me() {
    return apiClient.get('/user/me')
  },
  logout() {
    return apiClient.post('/auth/logout')
  },
}
