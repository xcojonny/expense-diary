import { describe, expect, it } from 'vitest'
import { samePath } from '../app/utils/routing'

// Regression guard: a proxy directory-redirect can turn /login into /login/,
// and the auth middleware must still treat it as the login page — otherwise it
// bounces the visitor and strips the magic-link ?token (login loop).
describe('samePath', () => {
  it('treats a trailing slash as the same path', () => {
    expect(samePath('/login/', '/login')).toBe(true)
    expect(samePath('/login', '/login')).toBe(true)
    expect(samePath('/login//', '/login')).toBe(true)
  })

  it('does not conflate different paths', () => {
    expect(samePath('/login-foo', '/login')).toBe(false)
    expect(samePath('/upload', '/login')).toBe(false)
  })

  it('keeps root distinct', () => {
    expect(samePath('/', '/login')).toBe(false)
    expect(samePath('/', '/')).toBe(true)
  })
})
