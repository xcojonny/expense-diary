<script setup lang="ts">
import UiIcon from './UiIcon.vue'

withDefaults(
  defineProps<{ icon?: string; title: string; hint?: string; compact?: boolean }>(),
  { icon: 'receipt' },
)
</script>

<template>
  <div :class="['empty', { 'empty--compact': compact }]">
    <span class="empty__badge">
      <UiIcon :name="icon" :size="compact ? 18 : 22" />
    </span>
    <p class="empty__title">{{ title }}</p>
    <p v-if="hint" class="empty__hint">{{ hint }}</p>
    <div v-if="$slots.default" class="empty__action">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 7px;
  padding: 34px 20px;
  text-align: center;
}

.empty--compact {
  padding: 20px 14px;
}

.empty__badge {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  margin-bottom: 3px;
  color: var(--accent);
  background: var(--accent-soft);
  border-radius: var(--radius-full);
}

.empty--compact .empty__badge {
  width: 34px;
  height: 34px;
}

.empty__title {
  font-weight: 550;
}

.empty__hint {
  max-width: 42ch;
  font-size: 0.8125rem;
  color: var(--text-muted);
}

.empty__action {
  margin-top: 6px;
}
</style>
