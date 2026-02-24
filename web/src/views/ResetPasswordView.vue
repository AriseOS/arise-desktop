<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { authApi } from '@/api/auth'

const route = useRoute()

const email = ref('')
const password = ref('')
const done = ref(false)
const error = ref('')
const loading = ref(false)

const token = (route.query.token as string) || ''

async function handleReset() {
  error.value = ''
  loading.value = true
  try {
    await authApi.resetPassword(email.value, token, password.value)
    done.value = true
  } catch (e: any) {
    error.value = e.response?.data?.error?.message || 'Reset failed'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4">
    <div class="max-w-md w-full space-y-8">
      <div class="text-center">
        <h1 class="text-3xl font-bold text-gray-900">Set New Password</h1>
      </div>

      <div v-if="done" class="bg-white shadow rounded-lg p-8 text-center space-y-4">
        <div class="text-green-600 text-lg font-medium">Password reset!</div>
        <p class="text-gray-600">You can now sign in with your new password.</p>
        <router-link to="/login" class="text-primary-600 hover:text-primary-500 font-medium">Go to login</router-link>
      </div>

      <form v-else @submit.prevent="handleReset" class="bg-white shadow rounded-lg p-8 space-y-6">
        <div v-if="error" class="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          {{ error }}
        </div>
        <div v-if="!token" class="bg-yellow-50 border border-yellow-200 text-yellow-700 px-4 py-3 rounded">
          Invalid or missing reset token. Please request a new reset link.
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700">Email</label>
          <input v-model="email" type="email" required
            class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-primary-500 focus:ring-primary-500" />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700">New Password</label>
          <input v-model="password" type="password" required minlength="6"
            class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-primary-500 focus:ring-primary-500" />
        </div>

        <button type="submit" :disabled="loading || !token"
          class="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50">
          {{ loading ? 'Resetting...' : 'Reset password' }}
        </button>
      </form>
    </div>
  </div>
</template>
