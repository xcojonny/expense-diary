import { describe, expect, it } from 'vitest'
import type { ReceiptStatus } from '../app/types/models'

// A tiny sanity test so the frontend test runner is wired into CI from day one.
// Real component/composable tests land alongside the pages in step 3.
describe('receipt status', () => {
  it('covers the documented lifecycle', () => {
    const lifecycle: ReceiptStatus[] = [
      'uploaded',
      'processing',
      'done',
      'needs_review',
      'failed',
    ]
    expect(new Set(lifecycle).size).toBe(5)
  })
})
