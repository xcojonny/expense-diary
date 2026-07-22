import { ref } from 'vue'
import type { Receipt, ReceiptStatus } from '~/types/models'

const TERMINAL: ReceiptStatus[] = ['done', 'needs_review', 'failed']

// Live-polling (no WebSocket, by design — the backend is stateless): after an
// upload the extraction runs async, so poll the receipt every `intervalMs`
// until it reaches a terminal status. Wired up to the real endpoints in step 3.
export function useReceiptPolling(intervalMs = 2000) {
  const { api } = useApi()
  const receipt = ref<Receipt | null>(null)
  const polling = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null

  function stop() {
    polling.value = false
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  async function tick(id: string) {
    const data = await api<Receipt>(`/receipts/${id}`)
    receipt.value = data
    if (TERMINAL.includes(data.status)) stop()
  }

  function start(id: string) {
    stop()
    polling.value = true
    void tick(id)
    timer = setInterval(() => void tick(id), intervalMs)
  }

  return { receipt, polling, start, stop }
}
