/** Theme: Systemvorgabe folgen oder ausdrücklich wählen. */

import { ref } from 'vue'

export type ThemeChoice = 'system' | 'light' | 'dark'

const STORAGE_KEY = 'expense-diary:theme'

function readStored(): ThemeChoice {
  const stored = localStorage.getItem(STORAGE_KEY)
  return stored === 'light' || stored === 'dark' ? stored : 'system'
}

export const theme = ref<ThemeChoice>(readStored())

export function applyTheme(choice: ThemeChoice): void {
  theme.value = choice
  const root = document.documentElement
  if (choice === 'system') {
    // Attribut entfernen, damit die `prefers-color-scheme`-Regel greift.
    root.removeAttribute('data-theme')
    localStorage.removeItem(STORAGE_KEY)
  } else {
    root.setAttribute('data-theme', choice)
    localStorage.setItem(STORAGE_KEY, choice)
  }
}

export function initTheme(): void {
  applyTheme(theme.value)
}
