<script setup lang="ts">
/**
 * Lade-, Fehler- und Leerzustand für **ein** Widget.
 *
 * Das ist die strukturelle Antwort auf „ein Fehler leert die ganze Seite": jedes
 * Widget bekommt seine eigene Grenze samt Wiederholen-Knopf, statt dass ein
 * `Promise.all` alles mitreißt.
 */
import UiButton from '@/ui/UiButton.vue'
import UiEmpty from '@/ui/UiEmpty.vue'
import UiIcon from '@/ui/UiIcon.vue'
import UiSkeleton from '@/ui/UiSkeleton.vue'

withDefaults(
  defineProps<{
    loading: boolean
    error?: string | null
    empty?: boolean
    emptyTitle?: string
    emptyHint?: string
    emptyIcon?: string
    skeletonLines?: number
    skeletonHeight?: string
  }>(),
  { emptyTitle: 'Noch keine Daten', skeletonLines: 3, skeletonHeight: '16px' },
)

const emit = defineEmits<{ retry: [] }>()
</script>

<template>
  <UiSkeleton v-if="loading" :lines="skeletonLines" :height="skeletonHeight" />

  <div v-else-if="error" class="failure">
    <UiIcon name="warning" :size="17" class="failure__icon" />
    <div class="failure__text">
      <p class="failure__title">Konnte nicht geladen werden</p>
      <p class="failure__detail">{{ error }}</p>
    </div>
    <UiButton variant="secondary" size="sm" icon="refresh" @click="emit('retry')">
      Erneut
    </UiButton>
  </div>

  <slot v-else-if="!empty" />

  <slot v-else name="empty">
    <UiEmpty :icon="emptyIcon" :title="emptyTitle" :hint="emptyHint" compact />
  </slot>
</template>

<style scoped>
.failure {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 13px 14px;
  background: var(--danger-soft);
  border-radius: var(--radius);
}

.failure__icon {
  color: var(--danger);
}

.failure__text {
  flex: 1;
  min-width: 0;
}

.failure__title {
  font-size: 0.875rem;
  font-weight: 550;
}

.failure__detail {
  font-size: 0.8125rem;
  color: var(--text-muted);
  overflow-wrap: anywhere;
}
</style>
