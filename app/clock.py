"""Reloj inyectable del producto (QA.md: nada de ``datetime.now()`` directo).

Todo el producto obtiene la hora a través de un objeto con ``now()`` y
``monotonic()``; las pruebas inyectan un reloj fijo y así las duraciones y
marcas de tiempo son deterministas.
"""

import time
from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    """Interfaz del reloj que reciben ``create_app`` y la observabilidad."""

    def now(self) -> datetime:
        """Devuelve la fecha y hora actual en UTC, con zona horaria.

        :return: Fecha y hora con ``tzinfo`` UTC.
        :rtype: datetime.datetime
        """

    def monotonic(self) -> float:
        """Devuelve un valor monótono en segundos, para medir duraciones.

        :return: Segundos desde un origen arbitrario.
        :rtype: float
        """


class SystemClock:
    """Reloj real del sistema; es el único lugar que consulta la hora."""

    def now(self) -> datetime:
        """Devuelve la fecha y hora actual en UTC.

        :return: Fecha y hora con ``tzinfo`` UTC.
        :rtype: datetime.datetime
        """
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        """Devuelve ``time.monotonic()``.

        :return: Segundos desde un origen arbitrario.
        :rtype: float
        """
        return time.monotonic()
