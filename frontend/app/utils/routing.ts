// Trailing-slash-insensitive path compare.
//
// A reverse-proxy / nginx directory redirect turns `/login` into `/login/`
// (the static build emits a `login/` directory, and `try_files $uri $uri/`
// 301s to the slashed form). Vue Router keeps that trailing slash in
// `route.path`, so an exact `to.path === '/login'` check misfires and the route
// guard bounces the (not-yet-authenticated) visitor to `/login` — dropping the
// magic-link `?token` before the login page can redeem it. Compare paths
// slash-insensitively so the token always survives.
export function samePath(a: string, b: string): boolean {
  const strip = (p: string): string => (p.length > 1 ? p.replace(/\/+$/, '') : p)
  return strip(a) === strip(b)
}
