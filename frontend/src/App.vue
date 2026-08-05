<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'

import { UNAUTHORIZED_EVENT } from '@/lib/api'
import AppShell from '@/components/AppShell.vue'
import LoginPage from '@/pages/LoginPage.vue'
import { useSession } from '@/stores/session'
import UiSkeleton from '@/ui/UiSkeleton.vue'
import UiToasts from '@/ui/UiToasts.vue'

const { ready, authenticated, bootstrap, markUnauthenticated } = useSession()

// Läuft die Session ab, während man arbeitet, tauscht die App die Ansicht gegen
// den Login — statt in jedem Widget einen 401-Fehler anzuzeigen.
function onUnauthorized(): void {
  markUnauthenticated()
}

onMounted(() => {
  window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  void bootstrap()
})

onBeforeUnmount(() => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized))
</script>

<template>
  <div v-if="!ready" class="boot">
    <UiSkeleton :lines="4" height="22px" />
  </div>

  <LoginPage v-else-if="!authenticated" />

  <AppShell v-else>
    <RouterView v-slot="{ Component }">
      <Transition name="fade" mode="out-in">
        <component :is="Component" />
      </Transition>
    </RouterView>
  </AppShell>

  <UiToasts />
</template>

<style scoped>
.boot {
  max-width: 420px;
  padding: 60px 20px;
  margin: 0 auto;
}
</style>
