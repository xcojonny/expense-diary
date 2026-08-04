<script setup lang="ts">
import { computed, ref } from 'vue'

import { ApiError } from '@/lib/api'
import { useSession } from '@/stores/session'
import UiButton from '@/ui/UiButton.vue'
import UiField from '@/ui/UiField.vue'
import UiIcon from '@/ui/UiIcon.vue'
import UiInput from '@/ui/UiInput.vue'

const { login, authMode, loginRequired } = useSession()

const password = ref('')
const error = ref<string | null>(null)
const busy = ref(false)

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    await login(password.value)
  } catch (caught) {
    error.value =
      caught instanceof ApiError ? caught.message : 'Anmeldung fehlgeschlagen.'
    password.value = ''
  } finally {
    busy.value = false
  }
}

/** Bei `trusted_header` gibt es keine Maske — dann fehlt der Proxy-Header. */
const proxyMode = computed(() => authMode.value === 'trusted_header' || !loginRequired.value)
</script>

<template>
  <main class="login">
    <div class="login__card">
      <span class="login__mark"><UiIcon name="receipt" :size="24" /></span>
      <h1 class="login__title">Haushaltsbuch</h1>
      <p class="login__sub">Kassenbon fotografieren, Ausgaben auswerten.</p>

      <form v-if="!proxyMode" class="login__form" @submit.prevent="submit">
        <UiField v-slot="{ id }" label="Passwort" :error="error">
          <UiInput
            :id="id"
            v-model="password"
            type="password"
            autocomplete="current-password"
            placeholder="••••••••"
            :invalid="!!error"
          />
        </UiField>
        <UiButton variant="primary" size="lg" type="submit" block :loading="busy">
          Anmelden
        </UiButton>
      </form>

      <div v-else class="login__proxy">
        <UiIcon name="warning" :size="18" />
        <p>
          Diese Instanz erwartet die Anmeldung über den Reverse Proxy, hat aber keinen
          Benutzer-Header erhalten. Bitte über den Proxy aufrufen.
        </p>
      </div>
    </div>
  </main>
</template>

<style scoped>
.login {
  display: grid;
  place-items: center;
  min-height: 100dvh;
  padding: 20px;
}

.login__card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: center;
  width: 100%;
  max-width: 350px;
  padding: 32px 26px;
  text-align: center;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow);
}

.login__mark {
  display: grid;
  place-items: center;
  width: 50px;
  height: 50px;
  margin-bottom: 6px;
  color: var(--accent-fg);
  background: var(--accent);
  border-radius: var(--radius);
}

.login__title {
  font-size: 1.25rem;
}

.login__sub {
  font-size: 0.875rem;
  color: var(--text-muted);
}

.login__form {
  display: flex;
  flex-direction: column;
  gap: 14px;
  width: 100%;
  margin-top: 18px;
  text-align: left;
}

.login__proxy {
  display: flex;
  gap: 10px;
  margin-top: 18px;
  padding: 12px;
  font-size: 0.8125rem;
  color: var(--text-muted);
  text-align: left;
  background: var(--warn-soft);
  border-radius: var(--radius);
}

.login__proxy svg {
  flex: none;
  color: var(--warn);
}
</style>
