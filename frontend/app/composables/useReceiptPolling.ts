import { ref } from 'vue'
import { TERMINAL_STATUSES, type ReceiptDetail } from '~/types/models'

// Live-polling (no WebSocket, by design — the backend is stateless): after an
// upload the extraction runs async, so poll the receipt every `intervalMs`
// until it reaches a terminal status (done | needs_review | failed).
export function useReceiptPolling(intervalMs = 2000) {
  const { api } = useApi()
  const receipt = ref<ReceiptDetail | null>(null)
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
    const data = await api<ReceiptDetail>(`/receipts/${id}`)
    receipt.value = data
    if (TERMINAL_STATUSES.includes(data.status)) stop()
  }

  function start(id: string) {
    stop()
    polling.value = true
    void tick(id)
    timer = setInterval(() => void tick(id), intervalMs)
  }

  return { receipt, polling, start, stop }
}
