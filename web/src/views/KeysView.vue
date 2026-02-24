<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { keysApi } from '@/api/keys'

interface ApiKey {
  id: number | null
  name: string
  key_preview: string
  created_at: string | null
}

const keys = ref<ApiKey[]>([])
const loading = ref(true)
const showCreate = ref(false)
const newKeyName = ref('')
const createdKey = ref('')
const createLoading = ref(false)
const error = ref('')

async function loadKeys() {
  loading.value = true
  try {
    const { data } = await keysApi.list()
    keys.value = data.keys || []
  } catch {
    error.value = 'Failed to load keys'
  } finally {
    loading.value = false
  }
}

async function createKey() {
  createLoading.value = true
  error.value = ''
  try {
    const { data } = await keysApi.create(newKeyName.value)
    createdKey.value = data.key
    newKeyName.value = ''
    await loadKeys()
  } catch (e: any) {
    error.value = e.response?.data?.error?.message || 'Failed to create key'
  } finally {
    createLoading.value = false
  }
}

async function revokeKey(keyId: number) {
  if (!confirm('Revoke this API key? This cannot be undone.')) return
  try {
    await keysApi.revoke(keyId)
    await loadKeys()
  } catch (e: any) {
    error.value = e.response?.data?.error?.message || 'Failed to revoke key'
  }
}

function copyKey() {
  navigator.clipboard.writeText(createdKey.value)
}

onMounted(loadKeys)
</script>

<template>
  <div>
    <div class="flex items-center justify-between">
      <h2 class="text-2xl font-bold text-gray-900">API Keys</h2>
      <button @click="showCreate = true; createdKey = ''"
        class="px-4 py-2 bg-primary-600 text-white text-sm rounded-md hover:bg-primary-700">
        Create Key
      </button>
    </div>

    <div v-if="error" class="mt-4 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
      {{ error }}
    </div>

    <!-- Created key banner -->
    <div v-if="createdKey" class="mt-4 bg-green-50 border border-green-200 rounded-lg p-4">
      <p class="text-sm font-medium text-green-800">Key created! Copy it now - it won't be shown again.</p>
      <div class="mt-2 flex items-center gap-2">
        <code class="flex-1 bg-white border rounded px-3 py-2 text-sm font-mono select-all">{{ createdKey }}</code>
        <button @click="copyKey"
          class="px-3 py-2 bg-green-600 text-white text-sm rounded hover:bg-green-700">
          Copy
        </button>
      </div>
    </div>

    <!-- Create dialog -->
    <div v-if="showCreate && !createdKey" class="mt-4 bg-white rounded-lg shadow p-6">
      <h3 class="text-lg font-medium text-gray-900 mb-4">Create API Key</h3>
      <div class="flex gap-3 max-w-md">
        <input v-model="newKeyName" type="text" placeholder="Key name (e.g. my-app)" required
          class="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:ring-primary-500" />
        <button @click="createKey" :disabled="createLoading || !newKeyName"
          class="px-4 py-2 bg-primary-600 text-white text-sm rounded-md hover:bg-primary-700 disabled:opacity-50">
          {{ createLoading ? 'Creating...' : 'Create' }}
        </button>
        <button @click="showCreate = false"
          class="px-4 py-2 text-gray-600 text-sm rounded-md hover:bg-gray-100">
          Cancel
        </button>
      </div>
    </div>

    <!-- Keys list -->
    <div v-if="loading" class="mt-8 text-gray-400">Loading keys...</div>
    <div v-else-if="keys.length === 0" class="mt-8 text-center text-gray-500 py-12">
      <p>No API keys yet. Create one to get started.</p>
    </div>
    <div v-else class="mt-6">
      <table class="w-full">
        <thead>
          <tr class="text-left text-sm text-gray-500 border-b">
            <th class="pb-3 font-medium">Name</th>
            <th class="pb-3 font-medium">Key</th>
            <th class="pb-3 font-medium">Created</th>
            <th class="pb-3 font-medium"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(key, index) in keys" :key="key.id ?? index" class="border-b border-gray-100">
            <td class="py-3 text-sm font-medium text-gray-900">{{ key.name }}</td>
            <td class="py-3 text-sm text-gray-500 font-mono">{{ key.key_preview }}</td>
            <td class="py-3 text-sm text-gray-500">{{ key.created_at?.split('T')[0] || '-' }}</td>
            <td class="py-3 text-right">
              <button v-if="key.id" @click="revokeKey(key.id)"
                class="text-sm text-red-600 hover:text-red-700">
                Revoke
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
