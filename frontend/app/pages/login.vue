<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { AuthConfig } from '~/types/models'
import { useAuthStore } from '~/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const email = ref('')
const sent = ref(false)
const error = ref<string | null>(null)
const busy = ref(false)
const config = ref<AuthConfig | null>(null)

async function finish() {
  const redirect = (route.query.redirect as string) || '/'
  await router.replace(redirect)
}

onMounted(async () => {
  config.value = await $fetch<AuthConfig>('/api/v1/auth/config').catch(() => null)

  if (route.query.error === 'sso') {
    error.value = 'Anmeldung über SSO fehlgeschlagen.'
    return
  }
  // Complete a magic-link / invitation / SSO flow if a token is present.
  try {
    if (typeof route.query.token === 'string') {
      await auth.verify(route.query.token)
      return finish()
    }
    if (typeof route.query.invite === 'string') {
      await auth.acceptInvite(route.query.invite)
      return finish()
    }
    if (route.query.sso === 'ok') {
      await auth.bootstrap()
      if (auth.isAuthenticated) return finish()
    }
  } catch {
    error.value = 'Link ungültig oder abgelaufen.'
  }
})

async function submit() {
  if (!email.value.trim()) return
  busy.value = true
  error.value = null
  try {
    await auth.requestMagicLink(email.value.trim())
    sent.value = true
  } catch {
    error.value = 'Anmeldung fehlgeschlagen.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="mx-auto mt-16 max-w-sm rounded border bg-white p-6">
    <h1 class="mb-1 text-xl font-semibold text-green-700">Haushaltsbuch</h1>
    <p class="mb-4 text-sm text-gray-500">Anmeldung</p>

    <p v-if="error" class="mb-3 text-sm text-red-600">{{ error }}</p>

    <div v-if="sent" class="text-sm text-gray-700">
      Wenn ein Konto existiert, wurde ein Anmeldelink an
      <span class="font-medium">{{ email }}</span> geschickt. Bitte E-Mail prüfen.
    </div>

    <form v-else class="space-y-3" @submit.prevent="submit">
      <input
        v-model="email"
        type="email"
        required
        placeholder="E-Mail-Adresse"
        class="w-full rounded border px-3 py-2 text-sm"
      >
      <button
        type="submit"
        :disabled="busy"
        class="w-full rounded bg-green-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        Anmeldelink senden
      </button>
    </form>

    <template v-if="config?.oidc_enabled">
      <div class="my-4 flex items-center gap-2 text-xs text-gray-400">
        <span class="h-px flex-1 bg-gray-200" /> oder <span class="h-px flex-1 bg-gray-200" />
      </div>
      <a
        href="/api/v1/auth/oidc/login"
        class="block rounded border border-green-600 px-3 py-2 text-center text-sm text-green-700"
      >
        Mit {{ config.oidc_provider_name }} anmelden
      </a>
    </template>
  </div>
</template>
