"""Un módulo por boletera. Cada uno expone obtener_eventos() con el mismo formato."""

from . import ticketmaster, tuboleta

# nombre -> módulo. Para sumar una boletera: crear fuentes/<nombre>.py y agregarla aquí.
# Por qué estas dos: ver FUENTES.md (Fase 0).
FUENTES = {
    tuboleta.FUENTE: tuboleta,
    ticketmaster.FUENTE: ticketmaster,
}
