<script setup lang="ts">
import { ref } from 'vue'
import { authApi } from '@/api/auth'

const email = ref('')
const sent = ref(false)
const error = ref('')
const loading = ref(false)

async function handleSubmit() {
  error.value = ''
  loading.value = true
  try {
    await authApi.forgotPassword(email.value)
    sent.value = true
  } catch (e: any) {
    error.value = e.response?.data?.error?.message || 'Request failed'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4">
    <div class="max-w-md w-full space-y-8">
      <div class="text-center">
        <h1 class="text-3xl font-bold text-gray-900">Reset Password</h1>
        <p class="mt-2 text-gray-600">Enter your email to receive a reset link</p>
      </div>

      <div v-if="sent" class="bg-white shadow rounded-lg p-8 text-center space-y-4">
        <div class="text-green-600 text-lg font-medium">Check your email</div>
        <p class="text-gray-600">If an account exists for {{ email }}, you'll receive a password reset link.</p>
        <router-link to="/login" class="text-primary-600 hover:text-primary-500 font-medium">Back to login</router-link>
      </div>

      <form v-else @submit.prevent="handleSubmit" class="bg-white shadow rounded-lg p-8 space-y-6">
        <div v-if="error" class="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          {{ error }}
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700">Email</label>
          <input v-model="email" type="email" required autofocus
            class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-primary-500 focus:ring-primary-500" />
        </div>

        <button type="submit" :disabled="loading"
          class="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50">
          {{ loading ? 'Sending...' : 'Send reset link' }}
        </button>

        <p class="text-center text-sm text-gray-600">
          <router-link to="/login" class="text-primary-600 hover:text-primary-500">Back to login</router-link>
        </p>
      </form>
    </div>
  </div>
</template>
