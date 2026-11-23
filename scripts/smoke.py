"""Prueba de humo del HR Assistant publicado (spec/04, punto 8).

Uso: ``SMOKE_API_KEY=<clave> python scripts/smoke.py https://<servicio>.onrender.com``

La clave se lee solo de la variable de entorno ``SMOKE_API_KEY``: nunca de un
argumento ni de un archivo, para que no quede en el historial de la terminal. La
clave nunca se imprime, ni tampoco el cuerpo de las respuestas.

Comprueba tres cosas e imprime ``[OK]`` o ``[FAIL]`` en cada una:

- ``GET /health`` responde 200.
- ``POST /ask`` sin clave responde 401.
- ``POST /ask`` con clave responde 200.

Solo usa la biblioteca estándar, así corre sin instalar dependencias.

Código de salida: 0 si todo pasa, 1 si algo falla, 2 si el uso es incorrecto.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping

KEY_VARIABLE = "SMOKE_API_KEY"
API_KEY_HEADER = "X-API-Key"
QUESTION = {"question": "¿Quién es EMP-0004?"}
# Render despierta un servicio dormido en hasta un minuto
TIMEOUT_SECONDS = 90.0
ALLOWED_SCHEMES = ("https://", "http://")
USAGE = "Uso: SMOKE_API_KEY=<clave> python scripts/smoke.py <url>"
NO_RESPONSE = 0

Fetch = Callable[[urllib.request.Request, float], int]


def fetch_status(request: urllib.request.Request, timeout: float) -> int:
    """Manda la petición y devuelve solo el código HTTP.

    :param request: Petición ya armada
    :type request: urllib.request.Request
    :param timeout: Segundos máximos de espera
    :type timeout: float
    :return: Código HTTP, o 0 si no hubo respuesta (red o tiempo agotado)
    :rtype: int
    """
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as error:
        error.close()
        return error.code
    except (urllib.error.URLError, OSError):
        return NO_RESPONSE


def build_checks(url: str, key: str) -> list[tuple[str, int, urllib.request.Request]]:
    """Arma las tres comprobaciones con su código esperado.

    :param url: URL base del servicio, sin ``/`` final
    :type url: str
    :param key: Clave de cliente para la tercera comprobación
    :type key: str
    :return: ``(nombre, código esperado, petición)`` por comprobación
    :rtype: list[tuple[str, int, urllib.request.Request]]
    """
    body = json.dumps(QUESTION).encode("utf-8")
    json_header = {"Content-Type": "application/json"}
    return [
        ("GET /health", 200, urllib.request.Request(f"{url}/health", method="GET")),
        ("POST /ask sin clave", 401, urllib.request.Request(
            f"{url}/ask", data=body, headers=json_header, method="POST"
        )),
        ("POST /ask con clave", 200, urllib.request.Request(
            f"{url}/ask", data=body, headers={**json_header, API_KEY_HEADER: key},
            method="POST",
        )),
    ]


def smoke(url: str, key: str, fetch: Fetch = fetch_status) -> bool:
    """Corre las comprobaciones e imprime el resultado de cada una.

    Imprime el código recibido: con él se ve la causa de una falla (401: la
    clave no coincide; 502: el modelo no responde; 0: no hubo respuesta).

    :param url: URL base del servicio, sin ``/`` final
    :type url: str
    :param key: Clave de cliente; nunca se imprime
    :type key: str
    :param fetch: Función que manda una petición y devuelve su código
    :type fetch: Callable
    :return: ``True`` si las tres comprobaciones pasan
    :rtype: bool
    """
    passed = True
    for name, expected, request in build_checks(url, key):
        status = fetch(request, TIMEOUT_SECONDS)
        label = "OK" if status == expected else "FAIL"
        print(f"  [{label}] {name} -> {status} (esperado {expected})")
        passed = passed and status == expected
    return passed


def main(args: list[str], environ: Mapping[str, str] | None = None,
         fetch: Fetch = fetch_status) -> int:
    """Valida el uso y corre la prueba de humo.

    :param args: Argumentos de la línea de comandos, sin el nombre del script
    :type args: list[str]
    :param environ: Variables de entorno de donde sale la clave; por omisión,
        las del proceso
    :type environ: Mapping[str, str] | None
    :param fetch: Función que manda una petición y devuelve su código
    :type fetch: Callable
    :return: 0 si todo pasa, 1 si algo falla, 2 si el uso es incorrecto
    :rtype: int
    """
    environ = os.environ if environ is None else environ
    key = environ.get(KEY_VARIABLE, "").strip()
    if len(args) != 1 or not args[0].startswith(ALLOWED_SCHEMES):
        print(USAGE)
        return 2
    if not key:
        print(f"Falta la variable {KEY_VARIABLE}. {USAGE}")
        return 2
    return 0 if smoke(args[0].rstrip("/"), key, fetch) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
