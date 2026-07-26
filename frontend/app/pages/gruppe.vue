<script setup lang="ts">
import { computed, ref } from 'vue'
import type { GroupSummary } from '~/types/models'
import { useAuthStore } from '~/stores/auth'

const auth = useAuthStore()
const { api } = useApi()

const { data: groups, refresh } = await useAsyncData('groups', () =>
  api<GroupSummary[]>('/groups'),
)

const activeRole = computed(
  () => auth.user?.memberships.find((m) => m.group_id === auth.activeGroupId)?.role,
)

const message = ref<string | null>(null)
const error = ref<string | null>(null)

const inviteEmail = ref('')
const inviteRole = ref('member')
async function invite() {
  if (!inviteEmail.value.trim()) return
  message.value = null
  error.value = null
  try {
    await api('/groups/invitations', {
      method: 'POST',
      body: { email: inviteEmail.value.trim(), role: inviteRole.value },
    })
    message.value = `Einladung an ${inviteEmail.value.trim()} verschickt.`
    inviteEmail.value = ''
  } catch (e) {
    error.value = (e as { data?: { detail?: string } }).data?.detail ?? 'Einladung fehlgeschlagen.'
  }
}

const newGroup = ref('')
async function createGroup() {
  if (!newGroup.value.trim()) return
  await api('/groups', { method: 'POST', body: { name: newGroup.value.trim() } })
  newGroup.value = ''
  await auth.fetchMe() // refresh the membership list / switcher
  await refresh()
}
</script>

<template>
  <section class="space-y-5">
    <h1 class="text-xl font-semibold">Gruppe</h1>

    <p v-if="message" class="text-sm text-green-700">{{ message }}</p>
    <p v-if="error" class="text-sm text-red-600">{{ error }}</p>

    <div class="rounded border bg-white p-4">
      <h2 class="mb-2 font-medium">Meine Haushalte</h2>
      <ul class="text-sm">
        <li
          v-for="g in groups ?? []"
          :key="g.id"
          class="flex justify-between border-b py-1 last:border-0"
        >
          <span>{{ g.name }}</span>
          <span class="text-gray-500">{{ g.role }}</span>
        </li>
      </ul>
    </div>

    <div class="rounded border bg-white p-4">
      <h2 class="mb-2 font-medium">Neuen Haushalt anlegen</h2>
      <div class="flex gap-2">
        <input v-model="newGroup" placeholder="Name" class="w-56 rounded border px-2 py-1 text-sm">
        <button class="rounded bg-green-600 px-3 py-1.5 text-sm text-white" @click="createGroup">
          Anlegen
        </button>
      </div>
    </div>

    <div v-if="activeRole === 'admin'" class="rounded border bg-white p-4">
      <h2 class="mb-2 font-medium">Mitglied einladen (aktiver Haushalt)</h2>
      <div class="flex flex-wrap items-center gap-2">
        <input
          v-model="inviteEmail"
          type="email"
          placeholder="E-Mail"
          class="w-56 rounded border px-2 py-1 text-sm"
        >
        <select v-model="inviteRole" class="rounded border px-2 py-1 text-sm">
          <option value="member">Mitglied</option>
          <option value="admin">Admin</option>
        </select>
        <button class="rounded bg-green-600 px-3 py-1.5 text-sm text-white" @click="invite">
          Einladen
        </button>
      </div>
    </div>
  </section>
</template>
