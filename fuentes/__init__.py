"""Un módulo por boletera. Cada uno expone obtener_eventos() con el mismo formato."""

from . import tuboleta

# nombre -> módulo. Para sumar una boletera: crear fuentes/<nombre>.py y agregarla aquí.
FUENTES = {
    tuboleta.FUENTE: tuboleta,
}
