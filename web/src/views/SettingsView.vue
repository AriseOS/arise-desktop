<script setup lang="ts">
import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'

const auth = useAuthStore()

// Password
const currentPassword = ref('')
const newPassword = ref('')
const pwMsg = ref('')
const pwLoading = ref(false)

async function changePassword() {
  pwLoading.value = true
  pwMsg.value = ''
  try {
    await authApi.changePassword(currentPassword.value, newPassword.value)
    pwMsg.value = 'Password changed'
    currentPassword.value = ''
    newPassword.value = ''
  } catch (e: any) {
    pwMsg.value = e.response?.data?.error?.message || 'Change failed'
  } finally {
    pwLoading.value = false
  }
}

// Sessions
const sessionMsg = ref('')

async function revokeAll() {
  if (!confirm('Revoke all sessions? You will need to log in again on all devices.')) return
  try {
    await authApi.revokeAllSessions()
    sessionMsg.value = 'All sessions revoked'
    setTimeout(() => auth.logout(), 1500)
  } catch (e: any) {
    sessionMsg.value = e.response?.data?.error?.message || 'Failed'
  }
}
</script>

<template>
  <div class="space-y-8">
    <h2 class="text-2xl font-bold text-gray-900">Settings</h2>

    <!-- Profile (read-only) -->
    <section class="bg-white rounded-lg shadow p-6">
      <h3 class="text-lg font-medium text-gray-900 mb-4">Profile</h3>
      <div class="space-y-4 max-w-md">
        <div>
          <label class="block text-sm font-medium text-gray-700">Username</label>
          <input :value="auth.username" disabled
            class="mt-1 block w-full rounded-md border border-gray-300 bg-gray-50 px-3 py-2 text-gray-500" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700">Email</label>
          <input :value="auth.email" disabled
            class="mt-1 block w-full rounded-md border border-gray-300 bg-gray-50 px-3 py-2 text-gray-500" />
        </div>
      </div>
    </section>

    <!-- Security -->
    <section class="bg-white rounded-lg shadow p-6">
      <h3 class="text-lg font-medium text-gray-900 mb-4">Security</h3>
      <div class="space-y-4 max-w-md">
        <div>
          <label class="block text-sm font-medium text-gray-700">Current Password</label>
          <input v-model="currentPassword" type="password"
            class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-primary-500 focus:ring-primary-500" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700">New Password</label>
          <input v-model="newPassword" type="password" minlength="6"
            class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-primary-500 focus:ring-primary-500" />
        </div>
        <div class="flex items-center gap-3">
          <button @click="changePassword" :disabled="pwLoading"
            class="px-4 py-2 bg-primary-600 text-white text-sm rounded-md hover:bg-primary-700 disabled:opacity-50">
            Change Password
          </button>
          <span v-if="pwMsg" class="text-sm text-gray-600">{{ pwMsg }}</span>
        </div>
      </div>

      <div class="mt-6 pt-6 border-t">
        <h4 class="text-sm font-medium text-gray-900">Sessions</h4>
        <p class="text-sm text-gray-500 mt-1">Sign out from all devices</p>
        <div class="flex items-center gap-3 mt-3">
          <button @click="revokeAll"
            class="px-4 py-2 bg-red-50 text-red-700 text-sm rounded-md hover:bg-red-100 border border-red-200">
            Revoke All Sessions
          </button>
          <span v-if="sessionMsg" class="text-sm text-gray-600">{{ sessionMsg }}</span>
        </div>
      </div>
    </section>

    <!-- Plan -->
    <section class="bg-white rounded-lg shadow p-6">
      <h3 class="text-lg font-medium text-gray-900 mb-2">Subscription</h3>
      <p class="text-gray-600">
        Current plan: <span class="font-medium capitalize">{{ auth.plan }}</span>
      </p>
      <p class="text-sm text-gray-500 mt-2">Contact admin to change your plan.</p>
    </section>
  </div>
</template>
