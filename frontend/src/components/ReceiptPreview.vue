<script setup lang="ts">
/**
 * Originalbeleg neben den Positionen.
 *
 * Der Endpoint ist authentifiziert (kein offener `/media`-Mount), also holt der
 * Client die Bytes und rendert sie als `blob:`-URL. Die URL wird beim Verlassen
 * freigegeben, sonst hält der Browser jedes betrachtete Foto im Speicher.
 */
import { onBeforeUnmount, ref, watch } from 'vue'

import { fetchReceiptFile } from '@/lib/api'
import UiButton from '@/ui/UiButton.vue'
import UiIcon from '@/ui/UiIcon.vue'
import UiSkeleton from '@/ui/UiSkeleton.vue'

const props = defineProps<{ receiptId: number; mediaType: string | null }>()

const url = ref<string | null>(null)
const type = ref('')
const loading = ref(false)
const error = ref<string | null>(null)

function release(): void {
  if (url.value) URL.revokeObjectURL(url.value)
  url.value = null
}

async function load(): Promise<void> {
  release()
  loading.value = true
  error.value = null
  try {
    const result = await fetchReceiptFile(props.receiptId)
    url.value = result.url
    type.value = result.type || props.mediaType || ''
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : 'Beleg nicht verfügbar.'
  } finally {
    loading.value = false
  }
}

watch(() => props.receiptId, load, { immediate: true })
onBeforeUnmount(release)
</script>

<template>
  <div class="preview">
    <UiSkeleton v-if="loading" :lines="1" height="220px" rounded />

    <div v-else-if="error" class="preview__fallback">
      <UiIcon name="warning" :size="18" />
      <p class="subtle">{{ error }}</p>
      <UiButton variant="secondary" size="sm" icon="refresh" @click="load">Erneut</UiButton>
    </div>

    <template v-else-if="url">
      <!-- PDFs kann ein <img> nicht darstellen — dafür ein Objekt-Rahmen. -->
      <object v-if="type.includes('pdf')" :data="url" type="application/pdf" class="preview__pdf">
        <p class="subtle">
          PDF kann hier nicht angezeigt werden.
          <a :href="url" target="_blank" rel="noopener">In neuem Tab öffnen</a>
        </p>
      </object>
      <a v-else :href="url" target="_blank" rel="noopener" class="preview__link">
        <img :src="url" alt="Originalbeleg" class="preview__image">
      </a>
    </template>
  </div>
</template>

<style scoped>
.preview {
  min-height: 120px;
}

.preview__link {
  display: block;
}

.preview__image {
  width: 100%;
  max-height: 70vh;
  object-fit: contain;
  background: var(--surface-muted);
  border-radius: var(--radius);
}

.preview__pdf {
  width: 100%;
  height: min(70vh, 620px);
  background: var(--surface-muted);
  border: none;
  border-radius: var(--radius);
}

.preview__fallback {
  display: flex;
  flex-direction: column;
  gap: 7px;
  align-items: center;
  padding: 22px;
  color: var(--text-muted);
  text-align: center;
}
</style>
