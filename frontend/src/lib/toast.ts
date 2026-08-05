/**
 * Ein Toast-System für die ganze App.
 *
 * Der Altstand baute pro Seite einen eigenen `notice`-Ref — dieselbe Mechanik
 * mehrfach, mit unterschiedlichem Verhalten.
 */

import { readonly, ref } from 'vue'

export type ToastTone = 'success' | 'error' | 'info'

export interface Toast {
  id: number
  tone: ToastTone
  text: string
}

const items = ref<Toast[]>([])
let nextId = 1

export const toasts = readonly(items)

function push(tone: ToastTone, text: string, ttl = 4000): void {
  const id = nextId++
  items.value = [...items.value, { id, tone, text }]
  // Fehler bleiben länger stehen — man will sie lesen können.
  window.setTimeout(() => dismiss(id), tone === 'error' ? ttl * 2 : ttl)
}

export function dismiss(id: number): void {
  items.value = items.value.filter((toast) => toast.id !== id)
}

export const toast = {
  success: (text: string) => push('success', text),
  error: (text: string) => push('error', text),
  info: (text: string) => push('info', text),
}
