<script setup lang="ts">
/**
 * Anmeldung — je nach `AUTH_MODE` drei verschiedene Masken (ADR-004):
 *
 * - `password`: Passwortfeld
 * - `oidc`: ein Knopf, der zum Identity Provider führt
 * - `trusted_header`/`none`: gar keine Maske — steht sie doch hier, fehlt der
 *   Header, und das ist ein Konfigurationsfehler, den man benennen muss
 */
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'

import { ApiError } from '@/lib/api'
import { navigation } from '@/lib/navigation'
import { useSession } from '@/stores/session'
import UiButton from '@/ui/UiButton.vue'
import UiField from '@/ui/UiField.vue'
import UiIcon from '@/ui/UiIcon.vue'
import UiInput from '@/ui/UiInput.vue'

const route = useRoute()
const { login, authMode, loginRequired, ssoAvailable } = useSession()

const password = ref('')
const error = ref<string | null>(null)
const busy = ref(false)

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    await login(password.value)
  } catch (caught) {
    error.value = caught instanceof ApiError ? caught.message : 'Anmeldung fehlgeschlagen.'
    password.value = ''
  } finally {
    busy.value = false
  }
}

/**
 * Kein Router-Sprung, sondern ein echter Seitenwechsel: der Endpoint antwortet
 * mit einer Umleitung zum Identity Provider, und die muss der Browser gehen.
 */
function startSso(): void {
  navigation.goto('/api/auth/oidc/login')
}

/** Der OIDC-Callback leitet Fehler als `?sso_error=…` hierher zurück. */
const ssoError = computed(() => {
  const raw = route.query.sso_error
  return typeof raw === 'string' && raw ? raw : null
})

/** Wer über einen Einladungslink kommt, soll wissen, warum hier ein Login steht. */
const invited = computed(() => route.path === '/einladung' && !!route.query.token)

const showPassword = computed(() => authMode.value === 'password')
const showSso = computed(() => ssoAvailable.value)
/** Weder Passwort noch SSO: der Proxy sollte uns einen Benutzer mitgeben. */
const proxyExpected = computed(() => !showPassword.value && !showSso.value && !loginRequired.value)
</script>

<template>
  <main class="login">
    <div class="login__card">
      <span class="login__mark"><UiIcon name="receipt" :size="24" /></span>
      <h1 class="login__title">Haushaltsbuch</h1>
      <p class="login__sub">Kassenbon fotografieren, Ausgaben auswerten.</p>

      <p v-if="invited" class="login__note login__note--info">
        <UiIcon name="mail" :size="16" />
        <span>Du wurdest zu einem Haushalt eingeladen. Melde dich an, um beizutreten.</span>
      </p>

      <p v-if="ssoError" class="login__note login__note--danger">
        <UiIcon name="warning" :size="16" />
        <span>{{ ssoError }}</span>
      </p>

      <form v-if="showPassword" class="login__form" @submit.prevent="submit">
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

      <div v-else-if="showSso" class="login__form">
        <UiButton variant="primary" size="lg" block icon="shield" @click="startSso">
          Mit Single Sign-on anmelden
        </UiButton>
        <p class="subtle">Die Anmeldung läuft über den Identity Provider dieser Instanz.</p>
      </div>

      <div v-else class="login__note login__note--warn">
        <UiIcon name="warning" :size="18" />
        <p v-if="proxyExpected">
          Diese Instanz erwartet die Anmeldung über den Reverse Proxy, hat aber keinen
          Benutzer-Header erhalten. Bitte über den Proxy aufrufen.
        </p>
        <p v-else>
          Für diese Instanz ist kein Anmeldeverfahren eingerichtet. Bitte
          <code>AUTH_MODE</code> prüfen.
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

.login__form .subtle {
  text-align: center;
}

.login__note {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  width: 100%;
  margin-top: 18px;
  padding: 12px;
  font-size: 0.8125rem;
  color: var(--text-muted);
  text-align: left;
  border-radius: var(--radius);
}

.login__note svg {
  flex: none;
}

.login__note--info {
  background: var(--info-soft);
}

.login__note--info svg {
  color: var(--info);
}

.login__note--warn {
  background: var(--warn-soft);
}

.login__note--warn svg {
  color: var(--warn);
}

.login__note--danger {
  background: var(--danger-soft);
}

.login__note--danger svg {
  color: var(--danger);
}

code {
  padding: 1px 4px;
  font-family: var(--font-mono);
  font-size: 0.8125em;
  background: var(--surface-muted);
  border-radius: 4px;
}
</style>
