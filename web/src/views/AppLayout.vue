<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

onMounted(() => {
  auth.fetchProfile()
})

const navItems = [
  { label: 'Dashboard', to: '/', icon: 'H' },
  { label: 'My Phrases', to: '/phrases', icon: 'P' },
  { label: 'Community', to: '/community', icon: 'C' },
  { label: 'API Keys', to: '/keys', icon: 'K' },
  { label: 'Settings', to: '/settings', icon: 'S' },
]
</script>

<template>
  <div class="min-h-screen flex">
    <!-- Sidebar -->
    <aside class="w-64 bg-white border-r border-gray-200 flex flex-col">
      <div class="p-6">
        <h1 class="text-xl font-bold text-primary-600">Ami</h1>
      </div>
      <nav class="flex-1 px-3 space-y-1">
        <router-link
          v-for="item in navItems" :key="item.to"
          :to="item.to"
          class="flex items-center px-3 py-2 text-sm font-medium rounded-md transition-colors"
          :class="$route.path === item.to
            ? 'bg-primary-50 text-primary-700'
            : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'"
        >
          <span class="w-6 h-6 flex items-center justify-center text-xs font-bold rounded bg-gray-100 mr-3">
            {{ item.icon }}
          </span>
          {{ item.label }}
        </router-link>
      </nav>
      <div class="p-4 border-t border-gray-200">
        <div class="flex items-center justify-between">
          <div class="text-sm">
            <div class="font-medium text-gray-900">{{ auth.username }}</div>
            <div class="text-gray-500 text-xs capitalize">{{ auth.plan }} plan</div>
          </div>
          <button @click="auth.logout()" class="text-gray-400 hover:text-gray-600 text-sm">Logout</button>
        </div>
      </div>
    </aside>

    <!-- Main content -->
    <main class="flex-1 overflow-y-auto">
      <div class="max-w-6xl mx-auto p-8">
        <router-view />
      </div>
    </main>
  </div>
</template>
