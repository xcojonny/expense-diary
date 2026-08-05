<script setup lang="ts">
/**
 * Einstellungen: Design, API-Tokens, Systemzustand.
 *
 * Der Systemzustand ersetzt die Admin-Log-Ansicht des Altstands: statt eines
 * Redis-Log-Rings zeigt die App die drei Dinge, die man bei „irgendwas läuft
 * nicht" wirklich braucht — ist ein Modell einsatzbereit, stauen sich Jobs, und
 * welche Version läuft. Alles Weitere steht in `docker logs` (ADR-002).
 */
import { ref } from 'vue'

import { api, ApiError } from '@/lib/api'
import { useResource } from '@/lib/useResource'
import { formatDateTime } from '@/lib/format'
import { applyTheme, theme, type ThemeChoice } from '@/lib/theme'
import { toast } from '@/lib/toast'
import PageHeader from '@/components/PageHeader.vue'
import ResourceBoundary from '@/components/ResourceBoundary.vue'
import { useSession } from '@/stores/session'
import type { ApiToken, ApiTokenCreated } from '@/types/api'
import UiBadge from '@/ui/UiBadge.vue'
import UiButton from '@/ui/UiButton.vue'
import UiCard from '@/ui/UiCard.vue'
import UiField from '@/ui/UiField.vue'
import UiIcon from '@/ui/UiIcon.vue'
import UiInput from '@/ui/UiInput.vue'
import UiModal from '@/ui/UiModal.vue'
import UiSegmented from '@/ui/UiSegmented.vue'

const { health, refreshHealth, logout, canLogout, user, multiUser } = useSession()

const tokens = useResource(() => api.get<ApiToken[]>('/tokens'))

const newTokenName = ref('')
const creating = ref(false)
const created = ref<ApiTokenCreated | null>(null)
const toRevoke = ref<ApiToken | null>(null)
const copied = ref(false)

const THEME_SEGMENTS = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Hell' },
  { value: 'dark', label: 'Dunkel' },
]

const AUTH_LABELS: Record<string, string> = {
  password: 'Passwort (ein Haushalt)',
  oidc: 'Single Sign-on (OIDC)',
  trusted_header: 'Reverse Proxy (vertrauter Header)',
  none: 'Kein Schutz',
}

function setTheme(value: string): void {
  applyTheme(value as ThemeChoice)
}

async function createToken(): Promise<void> {
  creating.value = true
  try {
    created.value = await api.post<ApiTokenCreated>('/tokens', { name: newTokenName.value })
    newTokenName.value = ''
    copied.value = false
    await tokens.reload()
  } catch (caught) {
    toast.error(caught instanceof ApiError ? caught.message : 'Anlegen fehlgeschlagen.')
  } finally {
    creating.value = false
  }
}

async function copyToken(): Promise<void> {
  if (!created.value) return
  try {
    await navigator.clipboard.writeText(created.value.plaintext)
    copied.value = true
  } catch {
    toast.error('Kopieren nicht möglich — bitte manuell markieren.')
  }
}

async function revoke(): Promise<void> {
  if (!toRevoke.value) return
  try {
    await api.delete(`/tokens/${toRevoke.value.id}`)
    await tokens.reload()
    toast.success('Token widerrufen.')
  } catch (caught) {
    toast.error(caught instanceof ApiError ? caught.message : 'Widerrufen fehlgeschlagen.')
  } finally {
    toRevoke.value = null
  }
}
</script>

<template>
  <div>
    <PageHeader title="Einstellungen" />

    <div class="stack">
      <!-- Design -->
      <UiCard title="Design" hint="Gilt nur in diesem Browser.">
        <UiSegmented
          :model-value="theme"
          :segments="THEME_SEGMENTS"
          aria-label="Design"
          @update:model-value="setTheme"
        />
      </UiCard>

      <!-- Systemzustand -->
      <UiCard title="Systemzustand">
        <template #actions>
          <UiButton variant="ghost" size="sm" icon="refresh" @click="refreshHealth">
            Aktualisieren
          </UiButton>
        </template>

        <dl v-if="health" class="facts">
          <div class="fact">
            <dt>Version</dt>
            <dd class="num">{{ health.version }}</dd>
          </div>
          <div class="fact">
            <dt>Anmeldung</dt>
            <dd>{{ AUTH_LABELS[health.auth_mode] ?? health.auth_mode }}</dd>
          </div>
          <div class="fact">
            <dt>Texterkennung</dt>
            <dd>
              <UiBadge :tone="health.llm_ready ? 'success' : 'warn'">
                {{ health.llm_ready ? health.llm_provider : 'kein Modell' }}
              </UiBadge>
            </dd>
          </div>
          <div class="fact">
            <dt>Warteschlange</dt>
            <dd>
              <UiBadge :tone="health.queued_jobs > 0 ? 'info' : 'neutral'">
                {{ health.queued_jobs }} offen
              </UiBadge>
            </dd>
          </div>
          <div v-if="multiUser" class="fact">
            <dt>Einladungsmails</dt>
            <dd>
              <UiBadge :tone="health.mail_ready ? 'success' : 'neutral'">
                {{ health.mail_ready ? 'SMTP aktiv' : 'nur Link' }}
              </UiBadge>
            </dd>
          </div>
        </dl>
        <p v-else class="subtle">Zustand nicht abrufbar.</p>

        <p v-if="health && !health.llm_ready" class="note">
          <UiIcon name="info" :size="15" />
          <span>
            Ohne Vision-Modell werden nur digitale eBon-PDFs automatisch gelesen; Fotos landen
            zum manuellen Erfassen unter „Prüfen“. Ein Modell wird per
            <code>LLM_PROVIDER</code>, <code>LLM_MODEL</code> und <code>LLM_API_KEY</code>
            hinterlegt.
          </span>
        </p>
      </UiCard>

      <!-- API-Tokens -->
      <UiCard
        title="API-Tokens"
        hint="Für den iOS-Kurzbefehl: Bon direkt aus dem Teilen-Menü hochladen."
      >
        <div class="stack-sm">
          <form class="token-form" @submit.prevent="createToken">
            <UiField v-slot="{ id }" label="Bezeichnung">
              <UiInput :id="id" v-model="newTokenName" placeholder="z. B. iPhone" />
            </UiField>
            <UiButton
              variant="primary"
              type="submit"
              icon="key"
              :loading="creating"
              :disabled="!newTokenName.trim()"
            >
              Token erstellen
            </UiButton>
          </form>

          <ResourceBoundary
            :loading="tokens.loading.value"
            :error="tokens.error.value"
            :empty="(tokens.data.value?.length ?? 0) === 0"
            :skeleton-lines="2"
            empty-title="Noch kein Token"
            empty-hint="Ein Token brauchst du nur für Uploads von außerhalb des Browsers."
            empty-icon="key"
            @retry="tokens.reload"
          >
            <ul class="tokens">
              <li v-for="token in tokens.data.value ?? []" :key="token.id" class="token">
                <span class="token__info">
                  <span class="token__name">{{ token.name }}</span>
                  <span class="subtle">
                    Erstellt {{ formatDateTime(token.created_at) }} ·
                    {{
                      token.last_used_at
                        ? `zuletzt genutzt ${formatDateTime(token.last_used_at)}`
                        : 'noch nicht genutzt'
                    }}
                  </span>
                </span>
                <UiButton variant="danger" size="sm" @click="toRevoke = token">Widerrufen</UiButton>
              </li>
            </ul>
          </ResourceBoundary>
        </div>
      </UiCard>

      <!-- Sitzung -->
      <UiCard v-if="canLogout" title="Sitzung" :hint="user ? user.email : undefined">
        <UiButton variant="secondary" icon="logout" @click="logout">Abmelden</UiButton>
      </UiCard>
    </div>

    <!-- Neues Token: Klartext genau einmal -->
    <UiModal
      v-if="created"
      title="Token erstellt"
      confirm-label="Verstanden"
      @close="created = null"
      @confirm="created = null"
    >
      <p>
        Dieser Wert ist <strong>nur jetzt</strong> sichtbar — gespeichert wird nur sein Hash.
      </p>
      <div class="secret">
        <code>{{ created.plaintext }}</code>
        <UiButton variant="secondary" size="sm" :icon="copied ? 'check' : 'file'" @click="copyToken">
          {{ copied ? 'Kopiert' : 'Kopieren' }}
        </UiButton>
      </div>
      <p class="subtle">
        Im iOS-Kurzbefehl als Header <code>Authorization: Bearer &lt;Token&gt;</code> an
        <code>POST /api/receipts</code> senden.
      </p>
    </UiModal>

    <UiModal
      v-if="toRevoke"
      title="Token widerrufen?"
      confirm-label="Widerrufen"
      danger
      @close="toRevoke = null"
      @confirm="revoke"
    >
      „{{ toRevoke.name }}“ funktioniert danach nicht mehr. Bereits hochgeladene Bons bleiben
      erhalten.
    </UiModal>
  </div>
</template>

<style scoped>
.facts {
  display: grid;
  gap: 12px;
  margin: 0;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
}

.fact dt {
  font-size: 0.75rem
;
  font-weight: 550;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.fact dd {
  margin: 3px 0 0;
  font-size: 0.9375rem;
  font-weight: 550;
}

.note {
  display: flex;
  gap: 9px;
  align-items: flex-start;
  margin-top: 14px;
  padding: 11px 13px;
  font-size: 0.8125rem;
  color: var(--text-muted);
  background: var(--info-soft);
  border-radius: var(--radius);
}

.note svg {
  flex: none;
  color: var(--info);
}

.token-form {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: end;
}

.token-form :deep(.field) {
  flex: 1;
  min-width: 170px;
}

.tokens {
  padding: 0;
  margin: 0;
  list-style: none;
}

.token {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
  padding: 9px 0;
}

.token + .token {
  border-top: 1px solid var(--border);
}

.token__info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.token__name {
  font-size: 0.875rem;
  font-weight: 550;
}

.secret {
  display: flex;
  gap: 9px;
  align-items: center;
  margin: 12px 0;
  padding: 10px 12px;
  background: var(--surface-muted);
  border-radius: var(--radius-sm);
}

.secret code {
  flex: 1;
  min-width: 0;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--text);
  overflow-wrap: anywhere;
}

code {
  padding: 1px 4px;
  font-family: var(--font-mono);
  font-size: 0.8125em;
  background: var(--surface-muted);
  border-radius: 4px;
}
</style>
