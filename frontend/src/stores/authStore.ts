import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authService, type UserInfo } from '@/services/authService'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('ragent_token') || '')
  const user = ref<UserInfo | null>(JSON.parse(localStorage.getItem('ragent_user') || 'null'))

  const isAuthenticated = computed(() => !!token.value)

  async function login(username: string, password: string) {
    const response = await authService.login(username, password)
    token.value = response.data.token
    user.value = response.data.user
    localStorage.setItem('ragent_token', token.value)
    localStorage.setItem('ragent_user', JSON.stringify(user.value))
  }

  async function logout() {
    try {
      await authService.logout()
    } finally {
      token.value = ''
      user.value = null
      localStorage.removeItem('ragent_token')
      localStorage.removeItem('ragent_user')
    }
  }

  return { token, user, isAuthenticated, login, logout }
})
