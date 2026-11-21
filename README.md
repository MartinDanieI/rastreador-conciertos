# Rastreador de conciertos en Colombia

Bot que revisa las boleteras cada 30 minutos y avisa por Telegram cuando aparece un
concierto nuevo (Fase 1 del plan de la app).

## Cómo funciona

1. `fuentes/<boletera>.py` descarga la lista de eventos (`obtener_eventos()`).
2. `rastreador.py` compara con `eventos.json`: un evento es nuevo si su id
   (`fuente:link`) no estaba guardado.
3. Solo para los nuevos abre la página del evento (`completar_detalle()`): fecha y
   hora exactas, precio desde y etapas de preventa.
4. `normalizar.py` deja el artista comparable (`artista_norm`: sin tildes ni
   mayúsculas) y la ciudad estándar (Sabaneta → Medellín, Chía → Bogotá; el
   municipio real queda en `municipio`).
5. Avisa por Telegram y guarda `eventos.json`. Si una fuente falla o devuelve 0
   eventos, avisa "dejó de responder" una sola vez y otra cuando vuelve.

## Formato de cada evento

| Campo | Ejemplo |
|---|---|
| `artista` / `artista_norm` | `Beéle` / `beele` |
| `evento` | `BEÉLE \| BORONDO TOUR 2026 - MEDELLÍN` |
| `fecha` / `hora` | `2026-11-28` / `19:00` (hora de Colombia) |
| `ciudad` / `municipio` | `Medellín` / `Sabaneta` |
| `lugar` | `DAVIarena` |
| `link` | `https://www.tuboleta.com/es/eventos/...` |
| `preventa` / `preventas` | `2026-08-31T10:00` / lista de etapas con nombre e inicio |
| `precio_desde` | `108000` (si se conoce) |
| `detectado` | cuándo lo vio el bot por primera vez (UTC) |

## Uso local

```
pip install -r requirements.txt
copy .env.example .env      # y llenar TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
python rastreador.py --telegram-chat-id
python rastreador.py --test-telegram
python rastreador.py --dry-run
python rastreador.py
```

## GitHub Actions

`.github/workflows/rastreador.yml` corre cada 30 minutos y hace commit de
`eventos.json` solo cuando cambia. Requiere los Secrets `TELEGRAM_BOT_TOKEN` y
`TELEGRAM_CHAT_ID` (Settings → Secrets and variables → Actions).

## Agregar una boletera

Crear `fuentes/<nombre>.py` con `FUENTE`, `obtener_eventos(session)` (y opcional
`completar_detalle(evento, session)`) devolviendo el mismo formato, y registrarla
en `fuentes/__init__.py`.

## Tuboleta (revisado el 2026-11-20)

- Lista: `/es/categorias/conciertos`, todos los eventos en el HTML (Drupal), sin
  JavaScript. Cloudflare sin captcha. robots.txt permite categorías y eventos.
- Detalle: dos tipos de página. HubSpot (`eventos.tuboleta.com`) con JSON-LD
  `MusicEvent` (hora real, artista, precio). Drupal con JSON-LD `Event` (fecha
  correcta, hora falsa 07:00; la hora se toma del texto "Hora: 8:00 p.m.").
- Las preventas vienen como texto libre ("Preventa Clientes Movistar Total: Martes 1
  de septiembre a las 12:00 p.m. …").
