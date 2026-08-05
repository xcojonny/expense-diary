<script setup lang="ts">
/**
 * Einladung einlösen (`/einladung?token=…`).
 *
 * Reihenfolge: anmelden, dann beitreten. Ist man noch nicht angemeldet, zeigt
 * `App.vue` den Login — die Route bleibt aber stehen, und sobald die Anmeldung
 * durch ist, mountet diese Seite und löst den Token ein. Der Token liegt in der
 * URL und wird nirgends zwischengespeichert.
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/lib/api'
import { navigation } from '@/lib/navigation'
import { useSession } from '@/stores/session'
import UiButton from '@/ui/UiButton.vue'
import UiCard from '@/ui/UiCard.vue'
import UiIcon from '@/ui/UiIcon.vue'

const route = useRoute()
const router = useRouter()
const { acceptInvitation } = useSession()

const token = computed(() => {
  const raw = route.query.token
  return typeof raw === 'string' ? raw : ''
})

type Phase = 'working' | 'done' | 'failed'

const phase = ref<Phase>('working')
const message = ref('')
const householdName = ref('')

async function accept(): Promise<void> {
  if (!token.value) {
    phase.value = 'failed'
    message.value = 'Dieser Link enthält keinen Einladungscode.'
    return
  }
  phase.value = 'working'
  try {
    const info = await acceptInvitation(token.value)
    householdName.value =
      info.user?.memberships.find((m) => m.household_id === info.active_household_id)
        ?.household_name ?? 'dem Haushalt'
    phase.value = 'done'
  } catch (caught) {
    phase.value = 'failed'
    message.value =
      caught instanceof ApiError ? caught.message : 'Die Einladung konnte nicht eingelöst werden.'
  }
}

/** Nach dem Beitritt neu laden, damit jedes Widget die Daten des neuen Haushalts holt. */
function enter(): void {
  navigation.goto('/')
}

onMounted(() => void accept())
</script>

<template>
  <div class="invitation">
    <UiCard>
      <div v-if="phase === 'working'" class="state">
        <span class="state__mark state__mark--info"><UiIcon name="clock" :size="20" /></span>
        <h1>Einladung wird eingelöst…</h1>
        <p class="subtle">Einen Moment.</p>
      </div>

      <div v-else-if="phase === 'done'" class="state">
        <span class="state__mark state__mark--success"><UiIcon name="check" :size="20" /></span>
        <h1>Willkommen in „{{ householdName }}“</h1>
        <p class="subtle">
          Du siehst ab jetzt die Bons dieses Haushalts und kannst eigene hinzufügen.
        </p>
        <UiButton variant="primary" @click="enter">Zur Übersicht</UiButton>
      </div>

      <div v-else class="state">
        <span class="state__mark state__mark--danger"><UiIcon name="warning" :size="20" /></span>
        <h1>Einladung nicht eingelöst</h1>
        <p class="subtle">{{ message }}</p>
        <div class="state__actions">
          <UiButton v-if="token" variant="secondary" icon="refresh" @click="accept">
            Erneut versuchen
          </UiButton>
          <UiButton variant="ghost" @click="router.push('/')">Zur Übersicht</UiButton>
        </div>
      </div>
    </UiCard>
  </div>
</template>

<style scoped>
.invitation {
  max-width: 460px;
  margin: 40px auto 0;
}

.state {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  padding: 12px 4px;
  text-align: center;
}

.state h1 {
  font-size: 1.0625rem;
}

.state__mark {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  margin-bottom: 4px;
  border-radius: var(--radius-full);
}

.state__mark--info {
  color: var(--info);
  background: var(--info-soft);
}

.state__mark--success {
  color: var(--success);
  background: var(--success-soft);
}

.state__mark--danger {
  color: var(--danger);
  background: var(--danger-soft);
}

.state__actions {
  display: flex;
  gap: 8px;
  margin-top: 6px;
}

.state :deep(.btn) {
  margin-top: 6px;
}
</style>
