<script setup lang="ts">
/**
 * Der Hauptweg in die App: Bon erfassen.
 *
 * Der Altstand hatte hier ein nacktes `<input type="file">` — keine Kamera,
 * kein Ziehen, keine Vorschau, kein Fortschritt, kein Mehrfach-Upload. Für
 * „Bon an der Kasse abfotografieren" war das die schwächste Stelle der App,
 * obwohl es die häufigste Handlung ist.
 *
 * Hier: Kamera-Auslöser (`capture="environment"`), Dateiauswahl, Drag & Drop,
 * Einfügen aus der Zwischenablage, Vorschaubilder und eine Warteschlange mit
 * Zustand pro Datei.
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'

import UiButton from '@/ui/UiButton.vue'
import UiIcon from '@/ui/UiIcon.vue'

export interface PendingFile {
  id: number
  file: File
  previewUrl: string | null
  state: 'queued' | 'uploading' | 'done' | 'error'
  message?: string
  receiptId?: number
}

const emit = defineEmits<{ files: [files: File[]] }>()
const props = defineProps<{ items: PendingFile[]; busy?: boolean }>()

const dragging = ref(false)
const cameraInput = ref<HTMLInputElement>()
const fileInput = ref<HTMLInputElement>()

const ACCEPT = 'image/jpeg,image/png,image/webp,image/heic,image/heif,application/pdf'

function take(list: FileList | null | undefined): void {
  const files = Array.from(list ?? [])
  if (files.length) emit('files', files)
}

function onDrop(event: DragEvent): void {
  dragging.value = false
  take(event.dataTransfer?.files)
}

/** Screenshot eines eBons direkt aus der Zwischenablage einfügen. */
function onPaste(event: ClipboardEvent): void {
  const files = Array.from(event.clipboardData?.files ?? [])
  if (files.length) emit('files', files)
}

onMounted(() => document.addEventListener('paste', onPaste))
onBeforeUnmount(() => document.removeEventListener('paste', onPaste))
</script>

<template>
  <div class="upload">
    <div
      :class="['dropzone', { 'dropzone--active': dragging }]"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    >
      <span class="dropzone__badge"><UiIcon name="camera" :size="24" /></span>
      <p class="dropzone__title">Bon erfassen</p>
      <p class="dropzone__hint">
        Foto aufnehmen, Datei wählen, hierher ziehen oder aus der Zwischenablage einfügen.
        Mehrere Bons auf einmal sind möglich.
      </p>

      <div class="dropzone__actions">
        <UiButton variant="primary" size="lg" icon="camera" @click="cameraInput?.click()">
          Foto aufnehmen
        </UiButton>
        <UiButton variant="secondary" size="lg" icon="upload" @click="fileInput?.click()">
          Datei wählen
        </UiButton>
      </div>

      <p class="dropzone__formats">JPEG, PNG, WebP, HEIC oder PDF · max. 15 MB</p>

      <!-- capture="environment" öffnet auf dem Handy direkt die Rückkamera. -->
      <input
        ref="cameraInput"
        type="file"
        class="sr-only"
        :accept="ACCEPT"
        capture="environment"
        multiple
        @change="take(($event.target as HTMLInputElement).files)"
      >
      <input
        ref="fileInput"
        type="file"
        class="sr-only"
        :accept="ACCEPT"
        multiple
        @change="take(($event.target as HTMLInputElement).files)"
      >
    </div>

    <ul v-if="props.items.length" class="queue">
      <li v-for="item in props.items" :key="item.id" class="queue__item">
        <span class="queue__thumb">
          <img v-if="item.previewUrl" :src="item.previewUrl" :alt="item.file.name">
          <UiIcon v-else name="file" :size="20" />
        </span>

        <span class="queue__info">
          <span class="queue__name truncate">{{ item.file.name }}</span>
          <span class="queue__meta">
            {{ (item.file.size / 1024).toFixed(0) }} kB
            <template v-if="item.message"> · {{ item.message }}</template>
          </span>
        </span>

        <span :class="['queue__state', `queue__state--${item.state}`]">
          <span v-if="item.state === 'uploading'" class="queue__spinner" aria-hidden="true" />
          <UiIcon v-else-if="item.state === 'done'" name="check" :size="16" />
          <UiIcon v-else-if="item.state === 'error'" name="warning" :size="16" />
          <UiIcon v-else name="clock" :size="16" />
        </span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.upload {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.dropzone {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  padding: 30px 20px;
  text-align: center;
  background: var(--surface);
  border: 2px dashed var(--border-strong);
  border-radius: var(--radius-lg);
  transition:
    border-color var(--transition),
    background var(--transition);
}

.dropzone--active {
  background: var(--accent-soft);
  border-color: var(--accent);
}

.dropzone__badge {
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  color: var(--accent-fg);
  background: var(--accent);
  border-radius: var(--radius-full);
}

.dropzone__title {
  font-size: 1.0625rem;
  font-weight: 600;
}

.dropzone__hint {
  max-width: 46ch;
  font-size: 0.875rem;
  color: var(--text-muted);
}

.dropzone__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-top: 6px;
}

.dropzone__formats {
  font-size: 0.75rem;
  color: var(--text-subtle);
}

.queue {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.queue__item {
  display: flex;
  gap: 11px;
  align-items: center;
  padding: 9px 11px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.queue__thumb {
  display: grid;
  flex: none;
  place-items: center;
  width: 42px;
  height: 42px;
  overflow: hidden;
  color: var(--text-subtle);
  background: var(--surface-muted);
  border-radius: var(--radius-sm);
}

.queue__thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.queue__info {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.queue__name {
  font-size: 0.875rem;
  font-weight: 500;
}

.queue__meta {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.queue__state {
  display: grid;
  flex: none;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: var(--radius-full);
}

.queue__state--queued {
  color: var(--text-subtle);
  background: var(--surface-muted);
}

.queue__state--uploading {
  color: var(--info);
  background: var(--info-soft);
}

.queue__state--done {
  color: var(--success);
  background: var(--success-soft);
}

.queue__state--error {
  color: var(--danger);
  background: var(--danger-soft);
}

.queue__spinner {
  width: 13px;
  height: 13px;
  border: 2px solid currentcolor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 620ms linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
