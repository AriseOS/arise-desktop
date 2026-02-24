<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { memoryApi } from '@/api/memory'

const auth = useAuthStore()

const stats = ref({
  total_states: 0,
  total_intent_sequences: 0,
  total_page_instances: 0,
  total_actions: 0,
  domains: [] as string[],
})
const loading = ref(true)

onMounted(async () => {
  try {
    const { data } = await memoryApi.getStats()
    if (data.stats) stats.value = data.stats
  } catch {
    // Stats unavailable
  } finally {
    loading.value = false
  }
})

const cards = [
  { label: 'States', key: 'total_states', color: 'bg-blue-500' },
  { label: 'Actions', key: 'total_actions', color: 'bg-green-500' },
  { label: 'Sequences', key: 'total_intent_sequences', color: 'bg-purple-500' },
  { label: 'Domains', key: 'domains', color: 'bg-orange-500', isDomains: true },
]
</script>

<template>
  <div>
    <h2 class="text-2xl font-bold text-gray-900">Dashboard</h2>
    <p class="mt-1 text-gray-500">Welcome back, {{ auth.username }}</p>

    <div v-if="loading" class="mt-8 text-gray-400">Loading stats...</div>

    <div v-else class="mt-8 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
      <div v-for="card in cards" :key="card.label"
        class="bg-white rounded-lg shadow p-6">
        <div class="flex items-center">
          <div :class="[card.color, 'w-10 h-10 rounded-lg flex items-center justify-center text-white text-sm font-bold']">
            {{ card.label[0] }}
          </div>
          <div class="ml-4">
            <p class="text-sm text-gray-500">{{ card.label }}</p>
            <p class="text-2xl font-bold text-gray-900">
              {{ card.isDomains ? stats.domains.length : (stats as any)[card.key] }}
            </p>
          </div>
        </div>
      </div>
    </div>

    <div v-if="stats.domains.length > 0" class="mt-8">
      <h3 class="text-lg font-medium text-gray-900 mb-3">Domains</h3>
      <div class="flex flex-wrap gap-2">
        <span v-for="domain in stats.domains" :key="domain"
          class="inline-flex items-center px-3 py-1 rounded-full text-sm bg-gray-100 text-gray-700">
          {{ domain }}
        </span>
      </div>
    </div>
  </div>
</template>
