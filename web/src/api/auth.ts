import api from './client'

export const authApi = {
  login(username: string, password: string) {
    return api.post('/auth/login', { username, password })
  },
  register(username: string, email: string, password: string) {
    return api.post('/auth/register', { username, email, password })
  },
  refresh(refreshToken: string) {
    return api.post('/auth/refresh', { refresh_token: refreshToken })
  },
  getMe() {
    return api.get('/auth/me')
  },
  changePassword(currentPassword: string, newPassword: string) {
    return api.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    })
  },
  forgotPassword(email: string) {
    return api.post('/auth/forgot-password', { email })
  },
  resetPassword(email: string, token: string, newPassword: string) {
    return api.post('/auth/reset-password', { email, token, new_password: newPassword })
  },
  sendVerifyCode(email: string) {
    return api.post('/auth/send-verify-code', { email })
  },
  logout(refreshToken?: string) {
    return api.post('/auth/logout', { refresh_token: refreshToken })
  },
  revokeAllSessions() {
    return api.post('/auth/revoke-all-sessions')
  },
  getCredentials() {
    return api.get('/auth/credentials')
  },
}
