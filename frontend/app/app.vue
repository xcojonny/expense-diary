<script setup lang="ts">
const links = [
  { to: '/', label: 'Dashboard' },
  { to: '/upload', label: 'Bon hochladen' },
  { to: '/bericht', label: 'Bericht' },
  { to: '/kategorien', label: 'Kategorien' },
]
</script>

<template>
  <div class="min-h-screen bg-gray-50 text-gray-900">
    <header class="border-b bg-white">
      <nav class="mx-auto flex max-w-3xl items-center gap-4 p-4">
        <span class="font-semibold text-green-600">Haushaltsbuch</span>
        <NuxtLink
          v-for="link in links"
          :key="link.to"
          :to="link.to"
          class="text-sm text-gray-600 hover:text-green-600"
        >
          {{ link.label }}
        </NuxtLink>
      </nav>
    </header>
    <main class="mx-auto max-w-3xl p-4">
      <NuxtPage />
    </main>
  </div>
</template>
