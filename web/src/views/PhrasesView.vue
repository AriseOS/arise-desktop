<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { memoryApi } from '@/api/memory'

interface Phrase {
  id: string
  label: string
  description: string
  access_count?: number
  success_count?: number
  created_at?: string
}

const phrases = ref<Phrase[]>([])
const loading = ref(true)

async function loadPhrases() {
  loading.value = true
  try {
    const { data } = await memoryApi.listPhrases()
    phrases.value = data.phrases || []
  } catch {
    // Failed to load
  } finally {
    loading.value = false
  }
}

async function sharePhrase(phraseId: string) {
  try {
    await memoryApi.sharePhrase(phraseId)
    alert('Phrase shared to community!')
  } catch (e: any) {
    alert(e.response?.data?.error?.message || 'Share failed')
  }
}

async function deletePhrase(phraseId: string) {
  if (!confirm('Delete this phrase?')) return
  try {
    await memoryApi.deletePhrase(phraseId)
    phrases.value = phrases.value.filter(p => p.id !== phraseId)
  } catch (e: any) {
    alert(e.response?.data?.error?.message || 'Delete failed')
  }
}

onMounted(loadPhrases)
</script>

<template>
  <div>
    <h2 class="text-2xl font-bold text-gray-900">My Phrases</h2>
    <p class="mt-1 text-gray-500">Workflow recordings from your memory</p>

    <div v-if="loading" class="mt-8 text-gray-400">Loading phrases...</div>
    <div v-else-if="phrases.length === 0" class="mt-8 text-center text-gray-500 py-12">
      <p>No phrases yet. Record workflows in the Ami app to see them here.</p>
    </div>
    <div v-else class="mt-6 space-y-4">
      <div v-for="phrase in phrases" :key="phrase.id"
        class="bg-white rounded-lg shadow p-5 flex items-start justify-between">
        <div class="flex-1 min-w-0">
          <h3 class="text-sm font-medium text-gray-900 truncate">{{ phrase.label || phrase.id }}</h3>
          <p class="mt-1 text-sm text-gray-500 line-clamp-2">{{ phrase.description || 'No description' }}</p>
          <div class="mt-2 flex gap-4 text-xs text-gray-400">
            <span v-if="phrase.access_count">Used {{ phrase.access_count }}x</span>
            <span v-if="phrase.created_at">{{ phrase.created_at.split('T')[0] }}</span>
          </div>
        </div>
        <div class="ml-4 flex gap-2 flex-shrink-0">
          <button @click="sharePhrase(phrase.id)"
            class="px-3 py-1 text-xs text-primary-600 border border-primary-200 rounded hover:bg-primary-50">
            Share
          </button>
          <button @click="deletePhrase(phrase.id)"
            class="px-3 py-1 text-xs text-red-600 border border-red-200 rounded hover:bg-red-50">
            Delete
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
