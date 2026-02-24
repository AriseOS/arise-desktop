<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { adminApi } from '@/api/admin'

interface AdminUser {
  user_id: string
  username: string
  email: string
  plan: string
  is_active: boolean
  is_admin: boolean
  created_at: string | null
}

interface Health {
  database: string
  surrealdb: string
  sub2api: string
  users_total: number
  users_active: number
}

const users = ref<AdminUser[]>([])
const health = ref<Health | null>(null)
const total = ref(0)
const search = ref('')
const loading = ref(true)

async function loadUsers() {
  loading.value = true
  try {
    const { data } = await adminApi.listUsers(1, 100, search.value || undefined)
    users.value = data.users || []
    total.value = data.total || 0
  } catch {
    // Not admin or error
  } finally {
    loading.value = false
  }
}

async function loadHealth() {
  try {
    const { data } = await adminApi.getHealth()
    health.value = data
  } catch {
    // Health check failed
  }
}

async function setPlan(userId: number, plan: string) {
  try {
    await adminApi.setPlan(userId, plan)
    await loadUsers()
  } catch (e: any) {
    alert(e.response?.data?.error?.message || 'Failed')
  }
}

async function toggleActive(userId: number, isActive: boolean) {
  try {
    await adminApi.setActive(userId, !isActive)
    await loadUsers()
  } catch (e: any) {
    alert(e.response?.data?.error?.message || 'Failed')
  }
}

onMounted(() => {
  loadUsers()
  loadHealth()
})
</script>

<template>
  <div class="space-y-8">
    <h2 class="text-2xl font-bold text-gray-900">Admin</h2>

    <!-- System Health -->
    <section v-if="health" class="bg-white rounded-lg shadow p-6">
      <h3 class="text-lg font-medium text-gray-900 mb-4">System Health</h3>
      <div class="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div>
          <p class="text-sm text-gray-500">Database</p>
          <p :class="health.database.startsWith('ok') ? 'text-green-600' : 'text-red-600'" class="font-medium">{{ health.database }}</p>
        </div>
        <div>
          <p class="text-sm text-gray-500">SurrealDB</p>
          <p :class="health.surrealdb === 'ok' ? 'text-green-600' : 'text-yellow-600'" class="font-medium">{{ health.surrealdb }}</p>
        </div>
        <div>
          <p class="text-sm text-gray-500">Sub2API</p>
          <p :class="health.sub2api === 'ok' ? 'text-green-600' : 'text-red-600'" class="font-medium">{{ health.sub2api }}</p>
        </div>
        <div>
          <p class="text-sm text-gray-500">Total Users</p>
          <p class="font-medium">{{ health.users_total }}</p>
        </div>
        <div>
          <p class="text-sm text-gray-500">Active Users</p>
          <p class="font-medium">{{ health.users_active }}</p>
        </div>
      </div>
    </section>

    <!-- Users -->
    <section class="bg-white rounded-lg shadow p-6">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-lg font-medium text-gray-900">Users ({{ total }})</h3>
        <input v-model="search" @input="loadUsers" type="text" placeholder="Search..."
          class="rounded-md border border-gray-300 px-3 py-1.5 text-sm w-64 focus:border-primary-500 focus:ring-primary-500" />
      </div>

      <div v-if="loading" class="text-gray-400 py-8 text-center">Loading...</div>
      <table v-else class="w-full text-sm">
        <thead>
          <tr class="text-left text-gray-500 border-b">
            <th class="pb-2 font-medium">ID</th>
            <th class="pb-2 font-medium">Username</th>
            <th class="pb-2 font-medium">Email</th>
            <th class="pb-2 font-medium">Plan</th>
            <th class="pb-2 font-medium">Status</th>
            <th class="pb-2 font-medium">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.user_id" class="border-b border-gray-50">
            <td class="py-2 text-gray-400">{{ u.user_id }}</td>
            <td class="py-2 font-medium">
              {{ u.username }}
              <span v-if="u.is_admin" class="ml-1 text-xs bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded">admin</span>
            </td>
            <td class="py-2 text-gray-500">{{ u.email }}</td>
            <td class="py-2">
              <select :value="u.plan" @change="setPlan(Number(u.user_id), ($event.target as HTMLSelectElement).value)"
                class="text-xs border rounded px-2 py-1">
                <option value="free">Free</option>
                <option value="pro">Pro</option>
                <option value="enterprise">Enterprise</option>
              </select>
            </td>
            <td class="py-2">
              <span :class="u.is_active ? 'text-green-600' : 'text-red-600'" class="text-xs">
                {{ u.is_active ? 'Active' : 'Disabled' }}
              </span>
            </td>
            <td class="py-2">
              <button @click="toggleActive(Number(u.user_id), u.is_active)"
                :class="u.is_active ? 'text-red-600 hover:text-red-700' : 'text-green-600 hover:text-green-700'"
                class="text-xs">
                {{ u.is_active ? 'Disable' : 'Enable' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>
