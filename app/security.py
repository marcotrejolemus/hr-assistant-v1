"""Seguridad del HR Assistant: claves por cliente, límite y compliance (spec/04).

- ``parse_api_keys`` lee ``API_KEYS`` (``cliente:clave,cliente2:clave2``); un
  error nombra la entrada y su largo, nunca su valor.
- ``find_client`` compara la clave recibida con ``hmac.compare_digest`` contra
  todas las claves configuradas.
- ``RateLimiter`` cuenta peticiones por cliente en una ventana de un minuto que
  empieza con la primera petición; usa el reloj monótono inyectado.
- ``enforce_production_rules`` impide arrancar con ``ENVIRONMENT=production`` y
  una configuración insegura.

Ninguna función de este módulo escribe una clave en un log ni en un error.
"""

import hmac
import math
import threading
from typing import Callable, Dict, List, Mapping, Optional, Tuple

API_KEY_HEADER = "X-API-Key"
INVALID_KEY_DETAIL = "invalid or missing API key"
RATE_LIMITED_DETAIL = "rate limit exceeded"
MIN_PRODUCTION_KEY_CHARS = 16
RATE_WINDOW_SECONDS = 60.0
FAKE_PREFIX = "FAKE_"

Monotonic = Callable[[], float]


def _malformed(index: int, entry: str, reason: str) -> ValueError:
    """Arma el error de una entrada inválida de ``API_KEYS`` sin su valor.

    :param index: Posición de la entrada, desde 0.
    :type index: int
    :param entry: Texto de la entrada; solo se usa su largo.
    :type entry: str
    :param reason: Motivo fijo del rechazo.
    :type reason: str
    :return: Error que nombra la variable, la entrada y el largo.
    :rtype: ValueError
    """
    return ValueError(
        f"API_KEYS entry {index} (length {len(entry)}) is malformed: {reason}"
    )


def parse_api_keys(raw: str) -> Dict[str, str]:
    """Lee ``API_KEYS`` con la forma ``cliente:clave,cliente2:clave2``.

    Una cadena vacía da un diccionario vacío (nadie puede entrar).

    :param raw: Valor de la variable.
    :type raw: str
    :return: Clave de cada cliente, en el orden de la variable.
    :rtype: dict[str, str]
    :raises ValueError: Si una entrada no tiene ``:``, tiene el cliente o la
        clave vacíos, o repite un cliente o una clave. El mensaje dice
        ``entry {i}`` y ``length {n}``, nunca el valor.
    """
    keys: Dict[str, str] = {}
    if not raw.strip():
        return keys
    for index, item in enumerate(raw.split(",")):
        entry = item.strip()
        client, separator, key = entry.partition(":")
        client, key = client.strip(), key.strip()
        if not separator:
            raise _malformed(index, entry, "expected client:key")
        if not client or not key:
            raise _malformed(index, entry, "client and key must not be empty")
        if client in keys:
            raise _malformed(index, entry, "client is repeated")
        if any(_same_key(key, known) for known in keys.values()):
            raise _malformed(index, entry, "key is repeated")
        keys[client] = key
    return keys


def _same_key(first: str, second: str) -> bool:
    """Compara dos claves en tiempo constante (también con caracteres no ASCII).

    :param first: Una clave.
    :type first: str
    :param second: Otra clave.
    :type second: str
    :return: ``True`` si son iguales.
    :rtype: bool
    """
    return hmac.compare_digest(first.encode("utf-8"), second.encode("utf-8"))


def find_client(
    api_keys: Mapping[str, str], candidate: Optional[str]
) -> Optional[str]:
    """Busca el cliente dueño de una clave con comparación de tiempo constante.

    Se compara contra todas las claves, sin salir antes, para no revelar por
    tiempo cuál coincidió.

    :param api_keys: Clave de cada cliente.
    :type api_keys: Mapping[str, str]
    :param candidate: Clave recibida en ``X-API-Key``, o ``None``.
    :type candidate: str or None
    :return: Nombre del cliente, o ``None`` si la clave falta o no coincide.
    :rtype: str or None
    """
    if not candidate:
        return None
    found: Optional[str] = None
    for client, key in api_keys.items():
        if _same_key(candidate, key) and found is None:
            found = client
    return found


class RateLimiter:
    """Límite de peticiones por cliente en ventanas de un minuto.

    La ventana de cada cliente empieza con su primera petición y se reinicia
    cuando pasa un minuto. Es estado de instancia protegido con un lock; solo
    guarda clientes ya autenticados, así que su tamaño está acotado.

    :param limit_per_minute: Peticiones permitidas por cliente por minuto.
    :type limit_per_minute: int
    :param monotonic: Reloj monótono inyectado, en segundos.
    :type monotonic: Callable[[], float]
    """

    def __init__(self, *, limit_per_minute: int, monotonic: Monotonic):
        self._limit = limit_per_minute
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._windows: Dict[str, Tuple[float, int]] = {}

    def check(self, client: str) -> Optional[int]:
        """Cuenta una petición del cliente si cabe en su ventana.

        :param client: Nombre del cliente autenticado.
        :type client: str
        :return: ``None`` si se permite; si se niega, los segundos enteros que
            faltan para que termine la ventana (``Retry-After``, mayor que 0).
        :rtype: int or None
        """
        now = self._monotonic()
        with self._lock:
            started, count = self._windows.get(client, (now, 0))
            if now - started >= RATE_WINDOW_SECONDS:
                started, count = now, 0
            if count >= self._limit:
                remaining = started + RATE_WINDOW_SECONDS - now
                return max(1, math.ceil(remaining))
            self._windows[client] = (started, count + 1)
            return None


def enforce_production_rules(  # pylint: disable=too-many-arguments
    environ: Mapping[str, str],
    *,
    provider: str,
    api_keys: Mapping[str, str],
    tracing: bool,
    hide_inputs: bool,
    hide_outputs: bool,
) -> None:
    """Aplica las reglas de compliance de ``ENVIRONMENT=production``.

    El mensaje nombra la variable responsable y nunca muestra un valor.

    :param environ: Variables de entorno (para ver los ``FAKE_*`` definidos).
    :type environ: Mapping[str, str]
    :param provider: Proveedor ya normalizado.
    :type provider: str
    :param api_keys: Claves ya leídas.
    :type api_keys: Mapping[str, str]
    :param tracing: ``LANGSMITH_TRACING`` encendido.
    :type tracing: bool
    :param hide_inputs: Valor de ``HIDE_INPUTS``.
    :type hide_inputs: bool
    :param hide_outputs: Valor de ``HIDE_OUTPUTS``.
    :type hide_outputs: bool
    :raises ValueError: Si alguna regla no se cumple.
    """
    suffix = "when ENVIRONMENT=production"
    if provider == "fake":
        raise ValueError(f"MODEL_PROVIDER must not be fake {suffix}")
    if not api_keys:
        raise ValueError(f"API_KEYS must not be empty {suffix}")
    for index, key in enumerate(api_keys.values()):
        if len(key) < MIN_PRODUCTION_KEY_CHARS:
            raise ValueError(
                f"API_KEYS entry {index} has a key shorter than "
                f"{MIN_PRODUCTION_KEY_CHARS} characters {suffix}"
            )
    hidden = {"HIDE_INPUTS": hide_inputs, "HIDE_OUTPUTS": hide_outputs}
    for name, is_hidden in hidden.items():
        if tracing and not is_hidden:
            raise ValueError(f"{name} must be true with LANGSMITH_TRACING {suffix}")
    switches: List[str] = sorted(n for n in environ if n.startswith(FAKE_PREFIX))
    if switches:
        raise ValueError(f"{switches[0]} must not be defined {suffix}")
