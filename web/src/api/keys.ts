import api from './client'

export const keysApi = {
  list() {
    return api.get('/keys')
  },
  create(name: string) {
    return api.post('/keys', { name })
  },
  revoke(keyId: number) {
    return api.delete(`/keys/${keyId}`)
  },
}
