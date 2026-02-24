import api from './client'

export const memoryApi = {
  getStats() {
    return api.get('/memory/stats')
  },
  getPublicStats() {
    return api.get('/memory/stats/public')
  },
  listPhrases(limit = 50) {
    return api.get('/memory/phrases', { params: { limit } })
  },
  getPhrase(phraseId: string, source?: string) {
    return api.get(`/memory/phrases/${phraseId}`, { params: { source } })
  },
  deletePhrase(phraseId: string) {
    return api.delete(`/memory/phrases/${phraseId}`)
  },
  listPublicPhrases(limit = 50, sort = 'popular') {
    return api.get('/memory/public/phrases', { params: { limit, sort } })
  },
  getPublicPhrase(phraseId: string) {
    return api.get(`/memory/public/phrases/${phraseId}`)
  },
  sharePhrase(phraseId: string) {
    return api.post('/memory/share', { phrase_id: phraseId })
  },
  unpublishPhrase(phraseId: string) {
    return api.post('/memory/unpublish', { phrase_id: phraseId })
  },
  getPublishStatus(phraseId: string) {
    return api.get('/memory/publish-status', { params: { phrase_id: phraseId } })
  },
}
