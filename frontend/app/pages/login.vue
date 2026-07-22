<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
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

// Cross-browser pairing:
const showCodeForm = ref(false) // requesting browser: enter the code shown elsewhere
const codeInput = ref('')
const displayCode = ref<string | null>(null) // this browser opened someone else's link
let poll: ReturnType<typeof setInterval> | null = null

function stopPoll() {
  if (poll) {
    clearInterval(poll)
    poll = null
  }
}
onUnmounted(stopPoll)

async function finish() {
  stopPoll()
  await router.replace((route.query.redirect as string) || '/')
}

async function tick() {
  const status = await auth.loginStatus().catch(() => 'pending')
  if (status === 'code') showCodeForm.value = true
  else if (status === 'used') {
    if (await auth.tryRefresh()) {
      await auth.fetchMe()
      if (auth.isAuthenticated) return finish()
    }
  }
}

onMounted(async () => {
  config.value = await $fetch<AuthConfig>('/api/v1/auth/config').catch(() => null)

  if (route.query.error === 'sso') {
    error.value = 'Anmeldung über SSO fehlgeschlagen.'
    return
  }
  try {
    if (typeof route.query.token === 'string') {
      const r = await auth.verify(route.query.token)
      if (r.status === 'session') return finish()
      // This browser opened a link requested elsewhere → show the pairing code.
      displayCode.value = r.code ?? null
      return
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
    poll = setInterval(tick, 2000) // wait for the link to be opened
  } catch {
    error.value = 'Anmeldung fehlgeschlagen.'
  } finally {
    busy.value = false
  }
}

async function submitCode() {
  if (!codeInput.value.trim()) return
  error.value = null
  try {
    await auth.verifyCode(codeInput.value.trim())
    return finish()
  } catch {
    error.value = 'Code ungültig oder abgelaufen.'
  }
}
</script>

<template>
  <div class="mx-auto mt-16 max-w-sm rounded border bg-white p-6">
    <h1 class="mb-1 text-xl font-semibold text-green-700">Haushaltsbuch</h1>
    <p class="mb-4 text-sm text-gray-500">Anmeldung</p>

    <p v-if="error" class="mb-3 text-sm text-red-600">{{ error }}</p>

    <!-- This browser opened a link that was requested in another browser -->
    <div v-if="displayCode" class="text-sm text-gray-700">
      <p class="mb-2">Gib diesen Code im ursprünglichen Browser/Tab ein:</p>
      <p class="text-center text-2xl font-bold tracking-widest text-green-700">{{ displayCode }}</p>
    </div>

    <!-- Requesting browser: link was opened elsewhere → enter the code -->
    <form v-else-if="showCodeForm" class="space-y-3" @submit.prevent="submitCode">
      <p class="text-sm text-gray-700">
        Der Link wurde in einem anderen Browser geöffnet. Gib den dort angezeigten
        Code ein:
      </p>
      <input
        v-model="codeInput"
        placeholder="z. B. ABC-234"
        class="w-full rounded border px-3 py-2 text-center text-lg tracking-widest"
      >
      <button type="submit" class="w-full rounded bg-green-600 px-3 py-2 text-sm font-medium text-white">
        Anmelden
      </button>
    </form>

    <!-- Link requested; waiting for it to be opened -->
    <div v-else-if="sent" class="text-sm text-gray-700">
      Wenn ein Konto existiert, wurde ein Anmeldelink an
      <span class="font-medium">{{ email }}</span> geschickt. Öffne ihn in diesem Browser —
      oder gib hier den Code ein, falls du ihn woanders öffnest.
    </div>

    <!-- Initial: request a link -->
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

    <template v-if="config?.oidc_enabled && !displayCode && !showCodeForm">
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
