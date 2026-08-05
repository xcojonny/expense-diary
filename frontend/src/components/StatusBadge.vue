<script setup lang="ts">
/** Bon-Status — eine Quelle für Beschriftung und Farbe, statt pro Seite neu. */
import { computed } from 'vue'

import type { ReceiptStatus } from '@/types/api'
import UiBadge from '@/ui/UiBadge.vue'

const props = defineProps<{ status: ReceiptStatus }>()

const MAP: Record<
  ReceiptStatus,
  { label: string; tone: 'neutral' | 'info' | 'success' | 'warn' | 'danger' }
> = {
  uploaded: { label: 'In Warteschlange', tone: 'neutral' },
  processing: { label: 'Wird gelesen', tone: 'info' },
  done: { label: 'Fertig', tone: 'success' },
  needs_review: { label: 'Prüfen', tone: 'warn' },
  failed: { label: 'Fehler', tone: 'danger' },
}

const entry = computed(() => MAP[props.status] ?? MAP.uploaded)
</script>

<template>
  <UiBadge :tone="entry.tone">{{ entry.label }}</UiBadge>
</template>
