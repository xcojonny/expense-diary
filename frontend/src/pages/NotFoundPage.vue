<script setup lang="ts">
import UiButton from '@/ui/UiButton.vue'
import UiEmpty from '@/ui/UiEmpty.vue'
</script>

<template>
  <UiEmpty
    icon="search"
    title="Seite nicht gefunden"
    hint="Diese Adresse gibt es nicht (mehr)."
  >
    <UiButton variant="primary" @click="$router.push('/')">Zur Übersicht</UiButton>
  </UiEmpty>
</template>
