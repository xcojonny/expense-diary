<script setup lang="ts">
import { useAuthStore } from '~/stores/auth'

const auth = useAuthStore()

const links = [
  { to: '/', label: 'Dashboard' },
  { to: '/upload', label: 'Bon hochladen' },
  { to: '/bericht', label: 'Bericht' },
  { to: '/kategorien', label: 'Kategorien' },
  { to: '/gruppe', label: 'Gruppe' },
  { to: '/einstellungen', label: 'Einstellungen' },
]

async function logout() {
  await auth.logout()
  await navigateTo('/login')
}
</script>

<template>
  <div class="min-h-screen bg-gray-50 text-gray-900">
    <template v-if="!auth.ready">
      <p class="p-8 text-center text-gray-500">Lädt …</p>
    </template>

    <template v-else-if="auth.isAuthenticated">
      <header class="border-b bg-white">
        <nav class="mx-auto flex max-w-3xl flex-wrap items-center gap-4 p-4">
          <span class="font-semibold text-green-600">Haushaltsbuch</span>
          <NuxtLink
            v-for="link in links"
            :key="link.to"
            :to="link.to"
            class="text-sm text-gray-600 hover:text-green-600"
          >
            {{ link.label }}
          </NuxtLink>
          <div class="ml-auto flex items-center gap-3">
            <GroupSwitcher />
            <button class="text-sm text-gray-500 hover:text-red-600" @click="logout">
              Abmelden
            </button>
          </div>
        </nav>
      </header>
      <main class="mx-auto max-w-3xl p-4">
        <NuxtPage />
      </main>
    </template>

    <template v-else>
      <NuxtPage />
    </template>
  </div>
</template>
