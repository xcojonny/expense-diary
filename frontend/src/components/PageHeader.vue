<script setup lang="ts">
defineProps<{ title: string; subtitle?: string }>()
</script>

<template>
  <header class="page-head">
    <div class="page-head__titles">
      <h1>{{ title }}</h1>
      <p v-if="subtitle" class="page-head__subtitle">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.actions" class="page-head__actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.page-head {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 18px;
}

.page-head__titles {
  min-width: 0;
}

.page-head__subtitle {
  margin-top: 2px;
  font-size: 0.875rem;
  color: var(--text-muted);
}

.page-head__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
</style>
