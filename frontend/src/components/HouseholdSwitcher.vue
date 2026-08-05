<script setup lang="ts">
/**
 * Haushaltswechsler.
 *
 * Steht in Sidebar und Topbar, weil die Frage „in welchem Haushalt bin ich
 * gerade?" bei getrennten Daten immer sichtbar beantwortet sein muss — sonst
 * bucht man den Wocheneinkauf in den falschen Haushalt und merkt es erst im
 * Bericht.
 *
 * Bei genau einer Mitgliedschaft ist es nur ein Etikett ohne Menü: ein
 * Umschalter mit einer Option ist Lärm.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { ApiError } from '@/lib/api'
import { navigation } from '@/lib/navigation'
import { toast } from '@/lib/toast'
import { useSession } from '@/stores/session'
import UiIcon from '@/ui/UiIcon.vue'

const { memberships, activeHouseholdId, activeMembership, switchHousehold } = useSession()

const open = ref(false)
const busy = ref(false)
const root = ref<HTMLElement | null>(null)

const label = computed(() => activeMembership.value?.household_name ?? 'Haushalt')
const switchable = computed(() => memberships.value.length > 1)

async function choose(householdId: number): Promise<void> {
  open.value = false
  if (householdId === activeHouseholdId.value || busy.value) return
  busy.value = true
  try {
    await switchHousehold(householdId)
    navigation.reload()
  } catch (caught) {
    toast.error(caught instanceof ApiError ? caught.message : 'Wechsel fehlgeschlagen.')
  } finally {
    busy.value = false
  }
}

function onDocumentClick(event: MouseEvent): void {
  if (root.value && !root.value.contains(event.target as Node)) open.value = false
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') open.value = false
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div ref="root" class="switcher">
    <button
      v-if="switchable"
      type="button"
      class="switcher__button"
      :aria-expanded="open"
      aria-haspopup="listbox"
      :disabled="busy"
      @click="open = !open"
    >
      <UiIcon name="users" :size="15" />
      <span class="switcher__label">{{ label }}</span>
      <UiIcon name="chevronDown" :size="14" class="switcher__caret" />
    </button>

    <span v-else class="switcher__static">
      <UiIcon name="users" :size="15" />
      <span class="switcher__label">{{ label }}</span>
    </span>

    <ul v-if="open" class="menu" role="listbox" :aria-label="'Haushalt wählen'">
      <li v-for="member in memberships" :key="member.household_id">
        <button
          type="button"
          role="option"
          :aria-selected="member.household_id === activeHouseholdId"
          class="menu__item"
          :class="{ 'menu__item--active': member.household_id === activeHouseholdId }"
          @click="choose(member.household_id)"
        >
          <span class="menu__name">{{ member.household_name }}</span>
          <UiIcon
            v-if="member.household_id === activeHouseholdId"
            name="check"
            :size="15"
            class="menu__check"
          />
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.switcher {
  position: relative;
  min-width: 0;
}

.switcher__button,
.switcher__static {
  display: flex;
  gap: 7px;
  align-items: center;
  width: 100%;
  min-width: 0;
  padding: 7px 9px;
  color: var(--text);
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-family: inherit;
  font-size: 0.8125rem;
  font-weight: 550;
  text-align: left;
}

.switcher__button {
  cursor: pointer;
  transition: background var(--transition);
}

.switcher__button:hover:not(:disabled) {
  background: var(--surface-hover);
}

.switcher__button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}

.switcher__label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.switcher__caret {
  color: var(--text-subtle);
}

.switcher svg:first-child {
  color: var(--text-muted);
}

.menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 50;
  min-width: 100%;
  max-width: 260px;
  padding: 4px;
  margin: 0;
  list-style: none;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow);
}

.menu__item {
  display: flex;
  gap: 8px;
  align-items: center;
  width: 100%;
  padding: 7px 8px;
  color: var(--text);
  background: none;
  border: 0;
  border-radius: 6px;
  font-family: inherit;
  font-size: 0.8125rem;
  text-align: left;
  cursor: pointer;
}

.menu__item:hover {
  background: var(--surface-hover);
}

.menu__item--active {
  color: var(--accent);
  font-weight: 550;
}

.menu__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.menu__check {
  flex: none;
}
</style>
