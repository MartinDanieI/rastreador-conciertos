# Fase 0 — Fuentes de conciertos en Colombia

Revisado el 2026-11-20. Cada fuente se probó con una sola petición a la portada,
la cartelera, el detalle de un evento y su `robots.txt`.

## Resultado

| Fuente | Qué es hoy | Cómo vienen los eventos | Protección | robots.txt / T&C | Veredicto |
|---|---|---|---|---|---|
| **Tuboleta** (tuboleta.com) | Boletera grande (Breakfast). DAVIarena, El Corazón de Bogotá (ex Movistar Arena), Campín, teatros | HTML (Drupal), 245 conciertos en una página. Detalle con JSON-LD (fecha/hora/precio) y preventas en texto | Cloudflare sin captcha | Permite categorías y eventos. T&C no mencionan bots | ✅ **En el bot** |
| **Ticketmaster Colombia** (ticketmaster.co) | Absorbió a **eTicket** (2025) y **La Tiquetera** (jul 2026). Karol G, Carlos Vives, Maná, The Strokes, Slipknot, Don Omar | HTML (plataforma Crowder), 40 conciertos en /page/CONCIERTOS. Fecha en texto libre; detalle con lugar/municipio y preventas | Captcha (AWS WAF / Turnstile) solo en la compra | robots solo regula a Google. T&C 3.10 prohíbe bots para **comprar**, no para leer | ✅ **En el bot** |
| eTicket (eticket.co) | **Ya no existe**: migró a Ticketmaster. El dominio ahora es un sitio de apuestas | — | — | — | ❌ Descartada (no visitar) |
| Primera Fila (primerafila.co) | **Ya no existe**: dominio en venta | — | — | — | ❌ Descartada |
| TaquillaLive (taquillalive.com) | Boletera mediana | Fila virtual **Queue-it en toda la web**, incluso la portada | Queue-it | robots bloquea las páginas de eventos | ❌ No se puede leer sin saltarse la fila |
| Passline (passline.com) | Boletera multipaís, eventos pequeños (fiestas, teatro) | App de JavaScript con API privada (api.passline.com) | Cloudflare también en la API | Bloquea /ticket* | ❌ Difícil y de poco valor |
| Boletomóvil (boletomovil.co) | Boletera regional (Bucaramanga) | App de JavaScript | — | — | ⏸️ Más adelante, si se amplía a regiones |
| Ocesa Colombia (ocesa.co) | Promotor. Vende por Ticketmaster/Tuboleta | Eventos escritos dentro del código, desactualizados ("Green Day este 2025") | — | — | ❌ No aporta |
| Páramo Presenta (paramopresenta.com) | Promotor (Estéreo Picnic). Vende por Ticketmaster/Tuboleta | WordPress. Tiene sección "PRÓXIMAMENTE" | — | — | ⏸️ Candidata v2: anuncios antes de la venta |
| Move Concerts (moveconcerts.com) | Promotor. Vende por Ticketmaster | WordPress con Elementor | Sucuri | Solo bloquea /wp-admin | ⏸️ Candidata v2 (mismo motivo) |
| El Corazón de Bogotá (ex Movistar Arena) | Escenario. Vende por **Tuboleta** | WordPress | — | Permite todo | ✅ Ya cubierto por Tuboleta |
| Coliseo MedPlus | Escenario (Cota). Vende por Ticketmaster/Tuboleta | WordPress | — | — | ✅ Ya cubierto |

## APIs oficiales

| API | Cubre Colombia | Condiciones | Veredicto |
|---|---|---|---|
| Ticketmaster Discovery API | No confirmado: la de Colombia corre en otra plataforma (Crowder), y Colombia no figura en los mercados listados | Llave gratis con registro | ⏸️ Probar con `countryCode=CO` si se saca la llave |
| Bandsintown API | Sí, pero por artista (hay que preguntar uno por uno) | Solo para artistas o equipos que actúan en su nombre, con permiso escrito | ❌ No disponible para una app como esta |
| Songkick | — | No da llaves nuevas | ❌ |

## Actualización 2026-11-21: Ticketmaster bloquea a GitHub

Desde el PC de la casa Ticketmaster responde bien, pero desde GitHub Actions
devuelve **403 Forbidden**: su firewall (AWS WAF) bloquea las IPs de servidores.
No se intenta saltar ese bloqueo. Por eso en GitHub `FUENTES_ACTIVAS=tuboleta`.
Un VPS tendría el mismo problema (también son IPs de servidor). Opciones para
recuperar Ticketmaster:

1. Pedir acceso oficial a Ticketmaster Colombia (API o feed para socios).
2. Correr esa fuente desde un computador de casa (IP residencial) cuando esté prendido.

## Elegidas

1. **Tuboleta**
2. **Ticketmaster Colombia**

Entre las dos cubren casi todo el mercado de conciertos grandes: el resto de
boleteras grandes desapareció o se integró a Ticketmaster. Lo que puede faltar:
eventos pequeños (Passline, TaquillaLive) y anuncios de promotores antes de que
salgan a la venta (Páramo, Move). Eso es lo que hay que vigilar en las 2 semanas de prueba.

Nota: un mismo concierto puede estar en las dos boleteras (por ejemplo, Anuel AA
tiene fecha en Medellín por Tuboleta y en Bogotá por Ticketmaster). Para la app
(Fase 2) conviene unirlos por `artista_norm` + `fecha` + `ciudad`.
