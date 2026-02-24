import api from './client'

export const adminApi = {
  listUsers(page = 1, perPage = 50, search?: string, plan?: string) {
    return api.get('/admin/users', { params: { page, per_page: perPage, search, plan } })
  },
  setPlan(userId: number, plan: string) {
    return api.put(`/admin/users/${userId}/plan`, { plan })
  },
  setActive(userId: number, isActive: boolean) {
    return api.put(`/admin/users/${userId}/active`, { is_active: isActive })
  },
  getHealth() {
    return api.get('/admin/health')
  },
}
