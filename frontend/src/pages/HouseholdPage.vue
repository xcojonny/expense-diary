<script setup lang="ts">
/**
 * Haushalt: Name, Mitglieder, Einladungen.
 *
 * Alles auf einer Seite, weil die drei Dinge zusammen eine Frage beantworten —
 * „wer sieht meine Bons?". Verwaltungsaktionen (umbenennen, Rolle ändern,
 * einladen, löschen) sind nur für Admins sichtbar; der Server prüft dieselbe
 * Regel noch einmal, das Ausblenden ist reine Höflichkeit.
 */
import { computed, ref } from 'vue'

import { api, ApiError } from '@/lib/api'
import { formatDate } from '@/lib/format'
import { navigation } from '@/lib/navigation'
import { toast } from '@/lib/toast'
import { useResource } from '@/lib/useResource'
import PageHeader from '@/components/PageHeader.vue'
import ResourceBoundary from '@/components/ResourceBoundary.vue'
import { useSession } from '@/stores/session'
import type { Household, Invitation, InvitationCreated, Member } from '@/types/api'
import UiBadge from '@/ui/UiBadge.vue'
import UiButton from '@/ui/UiButton.vue'
import UiCard from '@/ui/UiCard.vue'
import UiField from '@/ui/UiField.vue'
import UiIcon from '@/ui/UiIcon.vue'
import UiInput from '@/ui/UiInput.vue'
import UiModal from '@/ui/UiModal.vue'
import UiSelect from '@/ui/UiSelect.vue'

const { user, memberships, activeMembership, isAdmin, multiUser, refresh, switchHousehold } =
  useSession()

const ROLE_OPTIONS = [
  { value: 'member', label: 'Mitglied' },
  { value: 'admin', label: 'Admin' },
]

const ROLE_LABELS: Record<string, string> = { admin: 'Admin', member: 'Mitglied' }

const members = useResource(() => api.get<Member[]>('/households/active/members'))
// Einladungen sind Admin-Sache — als Mitglied gar nicht erst anfragen, sonst
// stünde hier ein 403 als „Fehler", der keiner ist.
const invitations = useResource(() => api.get<Invitation[]>('/households/active/invitations'), {
  lazy: !isAdmin.value,
})

const householdName = ref(activeMembership.value?.household_name ?? '')
const renaming = ref(false)

const inviteEmail = ref('')
// `string`, nicht `Role`: `UiSelect` modelliert `string`, und ein Auswahlfeld,
// dessen Werte wir selbst vorgeben, braucht hier keine engere Zusicherung.
const inviteRole = ref('member')
const inviting = ref(false)
const created = ref<InvitationCreated | null>(null)
const linkCopied = ref(false)

const newHouseholdName = ref('')
const creatingHousehold = ref(false)

const memberToRemove = ref<Member | null>(null)
const invitationToRevoke = ref<Invitation | null>(null)
const confirmDelete = ref(false)
const deleting = ref(false)

const nameChanged = computed(
  () =>
    householdName.value.trim().length > 0 &&
    householdName.value.trim() !== activeMembership.value?.household_name,
)

/** Sich selbst herauswerfen ist kein Verwaltungsvorgang — das wäre „verlassen". */
function isSelf(member: Member): boolean {
  return member.user_id === user.value?.id
}

function fail(caught: unknown, fallback: string): void {
  toast.error(caught instanceof ApiError ? caught.message : fallback)
}

async function rename(): Promise<void> {
  renaming.value = true
  try {
    await api.patch<Household>('/households/active', { name: householdName.value.trim() })
    await refresh()
    toast.success('Haushalt umbenannt.')
  } catch (caught) {
    fail(caught, 'Umbenennen fehlgeschlagen.')
  } finally {
    renaming.value = false
  }
}

async function setRole(member: Member, role: string): Promise<void> {
  try {
    await api.patch(`/households/active/members/${member.id}`, { role })
    await members.reload()
    await refresh()
  } catch (caught) {
    fail(caught, 'Rolle ändern fehlgeschlagen.')
    await members.reload() // Auswahlfeld auf den Serverstand zurückholen
  }
}

async function removeMember(): Promise<void> {
  const member = memberToRemove.value
  if (!member) return
  try {
    await api.delete(`/households/active/members/${member.id}`)
    await members.reload()
    toast.success(`${member.display_name} entfernt.`)
  } catch (caught) {
    fail(caught, 'Entfernen fehlgeschlagen.')
  } finally {
    memberToRemove.value = null
  }
}

async function invite(): Promise<void> {
  inviting.value = true
  try {
    created.value = await api.post<InvitationCreated>('/households/active/invitations', {
      email: inviteEmail.value.trim(),
      role: inviteRole.value,
    })
    linkCopied.value = false
    inviteEmail.value = ''
    inviteRole.value = 'member' // Nächste Einladung wieder mit dem Regelfall

    await invitations.reload()
  } catch (caught) {
    fail(caught, 'Einladen fehlgeschlagen.')
  } finally {
    inviting.value = false
  }
}

async function copyLink(): Promise<void> {
  if (!created.value) return
  try {
    await navigator.clipboard.writeText(created.value.link)
    linkCopied.value = true
  } catch {
    toast.error('Kopieren nicht möglich — bitte manuell markieren.')
  }
}

async function revokeInvitation(): Promise<void> {
  const invitation = invitationToRevoke.value
  if (!invitation) return
  try {
    await api.delete(`/households/active/invitations/${invitation.id}`)
    await invitations.reload()
    toast.success('Einladung zurückgezogen.')
  } catch (caught) {
    fail(caught, 'Zurückziehen fehlgeschlagen.')
  } finally {
    invitationToRevoke.value = null
  }
}

async function createHousehold(): Promise<void> {
  creatingHousehold.value = true
  try {
    const household = await api.post<Household>('/households', {
      name: newHouseholdName.value.trim(),
    })
    newHouseholdName.value = ''
    await switchHousehold(household.id)
    navigation.reload()
  } catch (caught) {
    fail(caught, 'Anlegen fehlgeschlagen.')
  } finally {
    creatingHousehold.value = false
  }
}

async function deleteHousehold(): Promise<void> {
  deleting.value = true
  try {
    await api.delete('/households/active')
    // Nach dem Löschen ist der aktive Haushalt weg — neu laden lässt den Server
    // den nächsten wählen, statt hier zu raten.
    navigation.goto('/')
  } catch (caught) {
    fail(caught, 'Löschen fehlgeschlagen.')
    deleting.value = false
    confirmDelete.value = false
  }
}
</script>

<template>
  <div>
    <PageHeader
      title="Haushalt"
      :subtitle="activeMembership?.household_name ?? 'Kein Haushalt aktiv'"
    >
      <template #actions>
        <UiBadge :tone="isAdmin ? 'accent' : 'neutral'">
          {{ ROLE_LABELS[activeMembership?.role ?? 'member'] }}
        </UiBadge>
      </template>
    </PageHeader>

    <div class="stack">
      <!-- Name -->
      <UiCard
        title="Name"
        hint="Erscheint im Wechsler und in Einladungen."
      >
        <form v-if="isAdmin" class="inline-form" @submit.prevent="rename">
          <UiField v-slot="{ id }" label="Bezeichnung">
            <UiInput :id="id" v-model="householdName" maxlength="120" />
          </UiField>
          <UiButton
            variant="primary"
            type="submit"
            icon="check"
            :loading="renaming"
            :disabled="!nameChanged"
          >
            Speichern
          </UiButton>
        </form>
        <p v-else class="subtle">
          Nur Admins können den Haushalt umbenennen.
        </p>
      </UiCard>

      <!-- Mitglieder -->
      <UiCard title="Mitglieder" hint="Alle sehen dieselben Bons, Artikel und Berichte.">
        <template #actions>
          <UiButton variant="ghost" size="sm" icon="refresh" @click="members.reload">
            Aktualisieren
          </UiButton>
        </template>

        <ResourceBoundary
          :loading="members.loading.value"
          :error="members.error.value"
          :empty="(members.data.value?.length ?? 0) === 0"
          :skeleton-lines="2"
          empty-title="Keine Mitglieder"
          empty-icon="users"
          @retry="members.reload"
        >
          <ul class="rows">
            <li v-for="member in members.data.value ?? []" :key="member.id" class="row-item">
              <span class="row-item__info">
                <span class="row-item__name">
                  {{ member.display_name }}
                  <UiBadge v-if="isSelf(member)" tone="info">du</UiBadge>
                </span>
                <span class="subtle">{{ member.email }}</span>
              </span>

              <div class="row-item__actions">
                <UiSelect
                  v-if="isAdmin"
                  :model-value="member.role"
                  :options="ROLE_OPTIONS"
                  class="role-select"
                  :aria-label="`Rolle von ${member.display_name}`"
                  @update:model-value="setRole(member, $event)"
                />
                <UiBadge v-else :tone="member.role === 'admin' ? 'accent' : 'neutral'">
                  {{ ROLE_LABELS[member.role] }}
                </UiBadge>

                <UiButton
                  v-if="isAdmin && !isSelf(member)"
                  variant="danger"
                  size="sm"
                  @click="memberToRemove = member"
                >
                  Entfernen
                </UiButton>
              </div>
            </li>
          </ul>
        </ResourceBoundary>
      </UiCard>

      <!-- Einladungen -->
      <UiCard
        v-if="isAdmin"
        title="Einladungen"
        hint="Der Eingeladene meldet sich an und tritt über den Link bei."
      >
        <div class="stack-sm">
          <form class="invite-form" @submit.prevent="invite">
            <UiField v-slot="{ id }" label="E-Mail">
              <UiInput
                :id="id"
                v-model="inviteEmail"
                type="email"
                placeholder="name@example.org"
                autocomplete="off"
              />
            </UiField>
            <UiField v-slot="{ id }" label="Rolle">
              <UiSelect :id="id" v-model="inviteRole" :options="ROLE_OPTIONS" />
            </UiField>
            <UiButton
              variant="primary"
              type="submit"
              icon="mail"
              :loading="inviting"
              :disabled="!inviteEmail.trim()"
            >
              Einladen
            </UiButton>
          </form>

          <ResourceBoundary
            :loading="invitations.loading.value"
            :error="invitations.error.value"
            :empty="(invitations.data.value?.length ?? 0) === 0"
            :skeleton-lines="2"
            empty-title="Keine offenen Einladungen"
            empty-hint="Eingelöste und abgelaufene Einladungen werden hier nicht mehr geführt."
            empty-icon="mail"
            @retry="invitations.reload"
          >
            <ul class="rows">
              <li
                v-for="invitation in invitations.data.value ?? []"
                :key="invitation.id"
                class="row-item"
              >
                <span class="row-item__info">
                  <span class="row-item__name">{{ invitation.email }}</span>
                  <span class="subtle">
                    Als {{ ROLE_LABELS[invitation.role] }} · gültig bis
                    {{ formatDate(invitation.expires_at) }}
                  </span>
                </span>
                <UiButton variant="secondary" size="sm" @click="invitationToRevoke = invitation">
                  Zurückziehen
                </UiButton>
              </li>
            </ul>
          </ResourceBoundary>
        </div>
      </UiCard>

      <!-- Weiterer Haushalt -->
      <UiCard
        v-if="multiUser"
        title="Weiterer Haushalt"
        hint="Getrennte Bons, getrennte Artikel, getrennte Berichte — z. B. privat und WG."
      >
        <form class="inline-form" @submit.prevent="createHousehold">
          <UiField v-slot="{ id }" label="Bezeichnung">
            <UiInput :id="id" v-model="newHouseholdName" placeholder="z. B. WG Bergstraße" />
          </UiField>
          <UiButton
            variant="secondary"
            type="submit"
            icon="plus"
            :loading="creatingHousehold"
            :disabled="!newHouseholdName.trim()"
          >
            Anlegen und wechseln
          </UiButton>
        </form>
        <p class="subtle count">
          Du bist in {{ memberships.length }}
          {{ memberships.length === 1 ? 'Haushalt' : 'Haushalten' }}.
        </p>
      </UiCard>

      <!-- Löschen -->
      <UiCard
        v-if="isAdmin && memberships.length > 1"
        title="Haushalt löschen"
        :hint="`Entfernt Bons, Artikel und Berichte von „${activeMembership?.household_name}“ unwiderruflich.`"
      >
        <!-- Der Name steht im Hinweis, nicht auf dem Knopf: lange Namen liefen
             auf dem Handy aus der Karte heraus. -->
        <UiButton variant="danger" icon="trash" @click="confirmDelete = true">
          Diesen Haushalt löschen
        </UiButton>
      </UiCard>
    </div>

    <!-- Einladung erstellt -->
    <UiModal
      v-if="created"
      title="Einladung erstellt"
      confirm-label="Fertig"
      @close="created = null"
      @confirm="created = null"
    >
      <p v-if="created.mail_sent">
        Die Einladung ist an <strong>{{ created.invitation.email }}</strong> unterwegs. Der Link
        steht hier zur Sicherheit noch einmal:
      </p>
      <p v-else>
        Es ist kein SMTP-Server hinterlegt (<code>SMTP_HOST</code>), also wurde keine Mail
        verschickt. Diesen Link an
        <strong>{{ created.invitation.email }}</strong> weitergeben:
      </p>
      <div class="secret">
        <code>{{ created.link }}</code>
        <UiButton
          variant="secondary"
          size="sm"
          :icon="linkCopied ? 'check' : 'file'"
          @click="copyLink"
        >
          {{ linkCopied ? 'Kopiert' : 'Kopieren' }}
        </UiButton>
      </div>
      <p class="subtle">
        Gültig bis {{ formatDate(created.invitation.expires_at) }}. Wer den Link hat, kann
        beitreten — also nicht öffentlich posten.
      </p>
    </UiModal>

    <UiModal
      v-if="memberToRemove"
      title="Mitglied entfernen?"
      confirm-label="Entfernen"
      danger
      @close="memberToRemove = null"
      @confirm="removeMember"
    >
      {{ memberToRemove.display_name }} verliert den Zugang zu diesem Haushalt. Die Bons bleiben
      erhalten — sie gehören dem Haushalt, nicht der Person.
    </UiModal>

    <UiModal
      v-if="invitationToRevoke"
      title="Einladung zurückziehen?"
      confirm-label="Zurückziehen"
      danger
      @close="invitationToRevoke = null"
      @confirm="revokeInvitation"
    >
      Der Link für {{ invitationToRevoke.email }} funktioniert danach nicht mehr.
    </UiModal>

    <UiModal
      v-if="confirmDelete"
      title="Haushalt löschen?"
      :confirm-label="deleting ? 'Löscht…' : 'Endgültig löschen'"
      danger
      @close="confirmDelete = false"
      @confirm="deleteHousehold"
    >
      <p>
        <strong>„{{ activeMembership?.household_name }}“</strong> wird mit allen Bons, Artikeln
        und Auswertungen gelöscht. Das lässt sich nicht zurücknehmen.
      </p>
      <p class="subtle note-danger">
        <UiIcon name="warning" :size="15" />
        Auch die hochgeladenen Bon-Bilder werden entfernt.
      </p>
    </UiModal>
  </div>
</template>

<style scoped>
.inline-form,
.invite-form {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: end;
}

.inline-form :deep(.field) {
  flex: 1;
  min-width: 180px;
}

.invite-form :deep(.field):first-child {
  flex: 1;
  min-width: 200px;
}

.rows {
  padding: 0;
  margin: 0;
  list-style: none;
}

.row-item {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
  padding: 9px 0;
}

.row-item + .row-item {
  border-top: 1px solid var(--border);
}

.row-item__info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.row-item__name {
  display: flex;
  gap: 7px;
  align-items: center;
  font-size: 0.875rem;
  font-weight: 550;
}

.row-item__actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.role-select {
  width: 130px;
}

.count {
  margin-top: 10px;
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

.note-danger {
  display: flex;
  gap: 7px;
  align-items: center;
  margin-top: 10px;
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
