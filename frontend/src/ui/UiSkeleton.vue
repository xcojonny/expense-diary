<script setup lang="ts">
/** Platzhalter beim Laden — deutlich ruhiger als ein springendes „Lädt …". */
withDefaults(
  defineProps<{ lines?: number; height?: string; rounded?: boolean }>(),
  { lines: 1, height: '14px' },
)
</script>

<template>
  <div class="skeleton-group" role="status" aria-label="Lädt">
    <span
      v-for="line in lines"
      :key="line"
      class="skeleton"
      :class="{ 'skeleton--rounded': rounded }"
      :style="{ height, width: lines > 1 && line === lines ? '62%' : '100%' }"
    />
  </div>
</template>

<style scoped>
.skeleton-group {
  display: flex;
  flex-direction: column;
  gap: 9px;
  width: 100%;
}

.skeleton {
  display: block;
  border-radius: var(--radius-sm);
  background: linear-gradient(
    90deg,
    var(--surface-muted) 25%,
    var(--surface-hover) 50%,
    var(--surface-muted) 75%
  );
  background-size: 220% 100%;
  animation: shimmer 1.35s ease-in-out infinite;
}

.skeleton--rounded {
  border-radius: var(--radius);
}

@keyframes shimmer {
  from {
    background-position: 130% 0;
  }

  to {
    background-position: -30% 0;
  }
}
</style>
