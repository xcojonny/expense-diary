<script setup lang="ts">
/** Bon-Liste — geteilt zwischen Übersicht und Bon-Seite. */
import { formatCents } from '@/lib/money'
import { formatDate, pluralize } from '@/lib/format'
import type { ReceiptSummary } from '@/types/api'
import UiIcon from '@/ui/UiIcon.vue'
import StatusBadge from './StatusBadge.vue'

defineProps<{ receipts: ReceiptSummary[] }>()
</script>

<template>
  <ul class="list">
    <li v-for="receipt in receipts" :key="receipt.id">
      <RouterLink :to="`/bons/${receipt.id}`" class="entry">
        <span class="entry__icon"><UiIcon name="store" :size="17" /></span>

        <span class="entry__main">
          <span class="entry__store truncate">{{ receipt.store_name ?? 'Unbekannter Markt' }}</span>
          <span class="entry__meta">
            {{ formatDate(receipt.purchased_at ?? receipt.created_at) }}
            <template v-if="receipt.line_item_count">
              · {{ pluralize(receipt.line_item_count, 'Position', 'Positionen') }}
            </template>
          </span>
        </span>

        <span class="entry__right">
          <span class="entry__total num">{{ formatCents(receipt.total_cents) }}</span>
          <StatusBadge :status="receipt.status" />
        </span>

        <UiIcon name="chevronRight" :size="16" class="entry__chevron" />
      </RouterLink>
    </li>
  </ul>
</template>

<style scoped>
.list {
  padding: 0;
  margin: 0;
  list-style: none;
}

.list li + li {
  border-top: 1px solid var(--border);
}

.entry {
  display: flex;
  gap: 11px;
  align-items: center;
  padding: 11px 16px;
  color: inherit;
  text-decoration: none;
  transition: background var(--transition);
}

.entry:hover {
  background: var(--surface-hover);
  text-decoration: none;
}

.entry__icon {
  display: grid;
  flex: none;
  place-items: center;
  width: 34px;
  height: 34px;
  color: var(--text-muted);
  background: var(--surface-muted);
  border-radius: var(--radius-sm);
}

.entry__main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.entry__store {
  font-size: 0.9375rem;
  font-weight: 550;
}

.entry__meta {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.entry__right {
  display: flex;
  flex: none;
  gap: 10px;
  align-items: center;
}

.entry__total {
  font-size: 0.9375rem;
  font-weight: 560;
}

.entry__chevron {
  flex: none;
  color: var(--text-subtle);
}

@media (width <= 520px) {
  .entry__right {
    flex-direction: column;
    align-items: flex-end;
    gap: 3px;
  }

  .entry__chevron {
    display: none;
  }
}
</style>
