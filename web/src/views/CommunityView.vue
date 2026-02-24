<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { memoryApi } from '@/api/memory'

interface PublicPhrase {
  id: string
  label: string
  description: string
  contributor_id?: string
  use_count?: number
  upvote_count?: number
  state_count?: number
  contributed_at?: string
}

const phrases = ref<PublicPhrase[]>([])
const loading = ref(true)
const sort = ref('popular')

async function loadPhrases() {
  loading.value = true
  try {
    const { data } = await memoryApi.listPublicPhrases(50, sort.value)
    phrases.value = data.phrases || []
  } catch {
    // Failed to load
  } finally {
    loading.value = false
  }
}

function changeSort(newSort: string) {
  sort.value = newSort
  loadPhrases()
}

onMounted(loadPhrases)
</script>

<template>
  <div>
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">Community Phrases</h2>
        <p class="mt-1 text-gray-500">Shared workflow recordings from the community</p>
      </div>
      <div class="flex gap-2">
        <button @click="changeSort('popular')"
          :class="sort === 'popular' ? 'bg-primary-100 text-primary-700' : 'bg-gray-100 text-gray-600'"
          class="px-3 py-1 text-sm rounded-full">Popular</button>
        <button @click="changeSort('recent')"
          :class="sort === 'recent' ? 'bg-primary-100 text-primary-700' : 'bg-gray-100 text-gray-600'"
          class="px-3 py-1 text-sm rounded-full">Recent</button>
      </div>
    </div>

    <div v-if="loading" class="mt-8 text-gray-400">Loading...</div>
    <div v-else-if="phrases.length === 0" class="mt-8 text-center text-gray-500 py-12">
      <p>No community phrases yet.</p>
    </div>
    <div v-else class="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
      <div v-for="phrase in phrases" :key="phrase.id"
        class="bg-white rounded-lg shadow p-5">
        <h3 class="text-sm font-medium text-gray-900 truncate">{{ phrase.label || phrase.id }}</h3>
        <p class="mt-1 text-sm text-gray-500 line-clamp-2">{{ phrase.description || 'No description' }}</p>
        <div class="mt-3 flex gap-4 text-xs text-gray-400">
          <span v-if="phrase.use_count">{{ phrase.use_count }} uses</span>
          <span v-if="phrase.state_count">{{ phrase.state_count }} steps</span>
        </div>
      </div>
    </div>
  </div>
</template>
