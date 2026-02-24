import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'
import { authApi } from '@/api/auth'
import router from '@/router'

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref(localStorage.getItem('access_token') || '')
  const refreshToken = ref(localStorage.getItem('refresh_token') || '')
  const userId = ref(localStorage.getItem('user_id') || '')
  const username = ref(localStorage.getItem('username') || '')
  const email = ref('')
  const plan = ref('free')
  const role = ref('user')
  const status = ref('active')

  const isAuthenticated = computed(() => !!accessToken.value)
  const isAdmin = computed(() => role.value === 'admin')

  function setTokens(access: string, refresh: string, uid: string, uname: string) {
    accessToken.value = access
    refreshToken.value = refresh
    userId.value = uid
    username.value = uname
    localStorage.setItem('access_token', access)
    localStorage.setItem('refresh_token', refresh)
    localStorage.setItem('user_id', uid)
    localStorage.setItem('username', uname)
  }

  async function login(user: string, password: string) {
    const { data } = await authApi.login(user, password)
    setTokens(data.access_token, data.refresh_token, data.user_id, data.username)
    await fetchProfile()
  }

  async function register(user: string, emailAddr: string, password: string) {
    const { data } = await authApi.register(user, emailAddr, password)
    setTokens(data.access_token, data.refresh_token, data.user_id, data.username)
    await fetchProfile()
  }

  async function refresh(): Promise<boolean> {
    if (!refreshToken.value) return false
    try {
      const { data } = await authApi.refresh(refreshToken.value)
      accessToken.value = data.access_token
      localStorage.setItem('access_token', data.access_token)
      // Update refresh_token if the server rotated it
      if (data.refresh_token) {
        refreshToken.value = data.refresh_token
        localStorage.setItem('refresh_token', data.refresh_token)
      }
      return true
    } catch {
      return false
    }
  }

  async function fetchProfile() {
    try {
      const { data } = await authApi.getMe()
      email.value = data.email
      plan.value = data.plan || 'free'
      role.value = data.role || 'user'
      status.value = data.status || 'active'
    } catch {
      // Profile fetch failed, tokens may be invalid
    }
  }

  function logout() {
    // Capture token before clearing — the API call needs it for auth header
    const token = refreshToken.value
    const access = accessToken.value

    // Clear local state first to prevent recursive 401 handling
    accessToken.value = ''
    refreshToken.value = ''
    userId.value = ''
    username.value = ''
    email.value = ''
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user_id')
    localStorage.removeItem('username')

    // Fire-and-forget server-side logout with captured token
    if (access && token) {
      axios.post('/api/v1/auth/logout', { refresh_token: token }, {
        headers: { Authorization: `Bearer ${access}` },
      }).catch(() => {})
    }

    router.push('/login')
  }

  return {
    accessToken, refreshToken, userId, username,
    email, plan, role, status,
    isAuthenticated, isAdmin,
    login, register, refresh, fetchProfile, logout, setTokens,
  }
})
