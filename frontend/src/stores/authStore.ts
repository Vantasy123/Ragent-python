import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authService, type UserInfo } from '@/services/authService'

const TOKEN_KEY = 'ragent_token'
const USER_KEY = 'ragent_user'

function readStoredUser(): UserInfo | null {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed as UserInfo : null
  } catch {
    localStorage.removeItem(USER_KEY)
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem(TOKEN_KEY) || '')
  const user = ref<UserInfo | null>(readStoredUser())
  const initialized = ref(false)
  const initializing = ref<Promise<void> | null>(null)

  const isAuthenticated = computed(() => !!token.value && !!user.value)

  function persistSession(nextToken: string, nextUser: UserInfo) {
    token.value = nextToken
    user.value = nextUser
    localStorage.setItem(TOKEN_KEY, nextToken)
    localStorage.setItem(USER_KEY, JSON.stringify(nextUser))
  }

  function clearSession() {
    token.value = ''
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }

  async function login(username: string, password: string) {
    const response = await authService.login(username.trim(), password)
    const data = response.data
    if (!data?.token || !data?.user) {
      throw new Error('登录响应缺少用户会话信息')
    }
    persistSession(data.token, data.user)
    initialized.value = true
  }

  async function restoreSession() {
    if (initialized.value) return
    if (initializing.value) return initializing.value

    initializing.value = (async () => {
      try {
        if (!token.value) {
          user.value = null
          return
        }
        const response = await authService.me()
        const currentUser = response.data as UserInfo | undefined
        if (!currentUser?.id) {
          clearSession()
          return
        }
        persistSession(token.value, currentUser)
      } catch {
        clearSession()
      } finally {
        initialized.value = true
        initializing.value = null
      }
    })()
    return initializing.value
  }

  async function logout() {
    try {
      if (token.value) {
        await authService.logout()
      }
    } finally {
      clearSession()
      initialized.value = true
    }
  }

  return {
    token,
    user,
    initialized,
    isAuthenticated,
    login,
    logout,
    restoreSession,
    clearSession,
  }
})
