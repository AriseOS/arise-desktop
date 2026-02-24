import axios from 'axios'
import { useAuthStore } from '@/stores/auth'

const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// Request interceptor: attach JWT token
api.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.accessToken) {
    config.headers.Authorization = `Bearer ${auth.accessToken}`
  }
  return config
})

// Response interceptor: auto-refresh on 401
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config
    const auth = useAuthStore()
    // Only attempt refresh if we have tokens and haven't retried yet
    if (error.response?.status === 401 && !original._retry && auth.accessToken) {
      original._retry = true
      const refreshed = await auth.refresh()
      if (refreshed) {
        original.headers.Authorization = `Bearer ${auth.accessToken}`
        return api(original)
      }
      auth.logout()
    }
    return Promise.reject(error)
  }
)

export default api
