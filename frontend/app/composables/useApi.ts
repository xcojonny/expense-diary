// Thin typed wrapper around $fetch with the shared /api base. Auth headers
// will be layered on here once magic-link login lands in a later step.
export function useApi() {
  const api = $fetch.create({
    baseURL: '/api/v1',
  })
  return { api }
}
