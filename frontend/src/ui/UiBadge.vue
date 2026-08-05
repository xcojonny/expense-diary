<script setup lang="ts">
withDefaults(
  defineProps<{ tone?: 'neutral' | 'info' | 'success' | 'warn' | 'danger' | 'accent' }>(),
  { tone: 'neutral' },
)
</script>

<template>
  <span :class="['badge', `badge--${tone}`]"><slot /></span>
</template>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 9px;
  border-radius: var(--radius-full);
  font-size: 0.75rem;
  font-weight: 550;
  white-space: nowrap;
}

.badge--neutral {
  background: var(--surface-muted);
  color: var(--text-muted);
}

.badge--info {
  background: var(--info-soft);
  color: var(--info);
}

.badge--success {
  background: var(--success-soft);
  color: var(--success);
}

.badge--warn {
  background: var(--warn-soft);
  color: var(--warn);
}

.badge--danger {
  background: var(--danger-soft);
  color: var(--danger);
}

.badge--accent {
  background: var(--accent-soft);
  color: var(--accent);
}
</style>
