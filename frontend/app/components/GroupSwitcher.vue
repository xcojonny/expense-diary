<script setup lang="ts">
import { useAuthStore } from '~/stores/auth'

const auth = useAuthStore()

async function onChange(event: Event) {
  auth.setActiveGroup((event.target as HTMLSelectElement).value)
  await refreshNuxtData() // re-fetch the current page's data for the new group
}
</script>

<template>
  <select
    v-if="auth.user && auth.user.memberships.length > 1"
    :value="auth.activeGroupId ?? ''"
    class="rounded border px-2 py-1 text-sm"
    @change="onChange"
  >
    <option v-for="m in auth.user.memberships" :key="m.group_id" :value="m.group_id">
      {{ m.group_name }}
    </option>
  </select>
</template>
