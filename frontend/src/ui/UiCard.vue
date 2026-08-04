<script setup lang="ts">
withDefaults(
  defineProps<{ title?: string; hint?: string; flush?: boolean }>(),
  { flush: false },
)
</script>

<template>
  <section class="card">
    <header v-if="title || $slots.actions" class="card__head">
      <div class="card__titles">
        <h2 class="card__title">{{ title }}</h2>
        <p v-if="hint" class="card__hint">{{ hint }}</p>
      </div>
      <div v-if="$slots.actions" class="card__actions">
        <slot name="actions" />
      </div>
    </header>
    <div :class="['card__body', { 'card__body--flush': flush }]">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.card {
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.card__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px 12px;
  padding: 14px 16px 0;
}

/* Basis 190 px: bleibt daneben Platz, steht die Aktion rechts; sonst rutscht
   sie in die nächste Zeile. Ohne das quetschte ein Umschalter den Titel auf
   Mobil zu einer einzelnen Wortspalte. */
.card__titles {
  flex: 1 1 190px;
  min-width: 0;
}

.card__title {
  font-size: 0.9375rem;
  font-weight: 600;
}

.card__hint {
  margin-top: 2px;
  font-size: 0.8125rem;
  color: var(--text-muted);
}

.card__actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: 6px;
}

.card__body {
  padding: 14px 16px 16px;
}

/* Für Listen, die bis an den Rand laufen sollen. */
.card__body--flush {
  padding: 0;
}
</style>
