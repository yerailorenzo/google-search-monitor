# Monitor de Google Search

Avisa al móvil y al ordenador, en cuanto ocurre, de:

| Fuente | Cada cuánto | Qué avisa |
|---|---|---|
| [Search Status Dashboard](https://status.search.google.com/) | 10 min | Core updates, spam updates e incidencias: anuncio, actualizaciones y **fin** |
| [Latest documentation updates](https://developers.google.com/search/updates) y [changelog de crawling](https://developers.google.com/crawling/docs/changelog) | 10 min | Lo que Google anuncia como cambio de documentación |
| [Blog de Search Central](https://developers.google.com/search/blog) | 10 min | Entradas nuevas |
| Rangos de IP de los rastreadores de Google | 10 min | Rangos añadidos o eliminados |
| Toda la documentación de `/search/docs` y `/crawling/docs` (~200 páginas) | 30 min | **Cualquier** cambio de texto, aunque Google no lo anuncie, con el diff exacto. También páginas nuevas, eliminadas o redirigidas |
| PDF de las Quality Rater Guidelines | 30 min | Versión nueva |

Funciona con GitHub Actions en este repositorio público (minutos gratis e ilimitados). La carpeta
`state/` guarda la última versión de todo, así que el historial de git es también un archivo de
cada cambio: cada aviso de documentación enlaza al historial de esa página.

## Activar las notificaciones

Ve a **Settings → Secrets and variables → Actions → New repository secret** y crea los del canal
que quieras (puedes usar los dos a la vez).

### Opción A: Telegram (recomendada)

1. En Telegram, habla con **@BotFather**, envía `/newbot` y sigue los pasos. Te dará un token.
2. Abre el chat con tu bot nuevo y envíale cualquier mensaje (por ejemplo `hola`).
3. Abre `https://api.telegram.org/bot<TOKEN>/getUpdates` en el navegador y copia el número de
   `"chat":{"id": ...}`.
4. Crea los secrets `TELEGRAM_BOT_TOKEN` (el token) y `TELEGRAM_CHAT_ID` (el número).

### Opción B: ntfy

1. Instala la app **ntfy** en el móvil (y, si quieres, abre <https://ntfy.sh> en el ordenador).
2. Suscríbete a un tema con un nombre largo y difícil de adivinar, por ejemplo
   `google-search-7f3k9q2m`. El nombre hace de contraseña: quien lo sepa puede leer los avisos.
3. Crea el secret `NTFY_TOPIC` con ese nombre.

### Opcional: resumen en español con Claude

Crea el secret `ANTHROPIC_API_KEY` con una API key de <https://console.anthropic.com>. Cada aviso
llevará 2–4 frases explicando qué ha cambiado y qué implica para SEO. Solo se llama a Claude
cuando hay un cambio real, así que el coste es de céntimos al mes. Sin la key, los avisos llegan
igual, con el diff pero sin el resumen.

### Probar

En **Actions → Prueba de notificación → Run workflow** se envía un aviso de prueba a los canales
configurados.

## Ejecutar en local

```bash
pip install -r requirements.txt
python monitor.py test --dry-run        # imprime un aviso de ejemplo
STATE_DIR=/tmp/estado python monitor.py all --dry-run   # rastreo completo sin enviar nada
```
