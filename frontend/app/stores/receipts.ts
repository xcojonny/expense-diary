import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Receipt } from '~/types/models'

// Placeholder store — fleshed out in step 3 (list, upload, detail editing).
export const useReceiptsStore = defineStore('receipts', () => {
  const receipts = ref<Receipt[]>([])
  return { receipts }
})
