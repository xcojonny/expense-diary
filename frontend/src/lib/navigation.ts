/**
 * Harte Navigation — an einer Stelle statt fünfmal `window.location`.
 *
 * Nach einem Haushaltswechsel ist ein echter Seitenaufbau das Ehrlichste: jedes
 * Widget holt seine Ressource neu, statt dass irgendwo noch Zahlen des alten
 * Haushalts stehenbleiben. Und der SSO-Start muss eine echte Navigation sein,
 * weil der Server mit einer Umleitung zum Identity Provider antwortet — die
 * kann der Router nicht gehen.
 *
 * Gebündelt, damit Tests die beiden Funktionen ersetzen können, ohne
 * `window.location` zu verbiegen.
 */
export const navigation = {
  /** Aktuelle Seite komplett neu laden. */
  reload(): void {
    window.location.reload()
  },

  /** Zu einer URL navigieren — auch außerhalb der SPA (z. B. `/api/...`). */
  goto(url: string): void {
    window.location.assign(url)
  },
}
