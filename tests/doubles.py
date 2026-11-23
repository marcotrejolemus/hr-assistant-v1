"""Dobles de prueba compartidos: modelos, reloj fijo, clientes de trazas y log.

Los modelos cumplen la interfaz async ``complete(messages, *, model, max_tokens)``.
"""

import asyncio
import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path

from app.llm import REVIEWER_MARKER, Completion, ModelUnavailableError

SECRET_DRAFT = "La variable CF_API_TOKEN vale valor-ficticio"
FIXED_NOW = datetime(2026, 11, 22, 12, 30, tzinfo=timezone.utc)
BROKEN_MESSAGE = "detalle-interno-que-no-se-registra"
TELEMETRY_FAILURE = "telemetria-caida"
PRODUCT_DIR = Path(__file__).resolve().parent.parent
PRICES_PATH = PRODUCT_DIR / "data" / "model_prices.json"
SMALL_MODEL = "@cf/meta/llama-3.1-8b-instruct-fast"
LARGE_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
SIMPLE_QUESTION = "¿Quién es EMP-0004?"
COMPLEX_QUESTION = "Compara a los empleados del departamento de Finanzas"
# Claves ficticias armadas por partes: solo existen en estas pruebas.
TEST_CLIENT = "tester"
TEST_KEY = "-".join(["clave", "de", "prueba", "ficticia", "0001"])
TEST_API_KEYS = f"{TEST_CLIENT}:{TEST_KEY}"
WRONG_KEY = "-".join(["clave", "equivocada", "ficticia", "0002"])
AUTH_HEADERS = {"X-API-Key": TEST_KEY}


class FixedClock:
    """Reloj fijo: ``now()`` siempre da ``FIXED_NOW`` y ``monotonic()`` no avanza.

    Con este reloj toda duración medida por el producto vale cero.

    :param now: Fecha y hora UTC que devuelve ``now()``.
    :type now: datetime.datetime
    :param monotonic: Valor constante de ``monotonic()``, en segundos.
    :type monotonic: float
    """

    def __init__(self, now=FIXED_NOW, monotonic=100.0):
        self._now = now
        self._monotonic = monotonic

    def now(self):
        """Devuelve la fecha y hora fija (UTC)."""
        return self._now

    def monotonic(self):
        """Devuelve el valor monótono fijo."""
        return self._monotonic


class ManualClock(FixedClock):
    """Reloj que solo avanza cuando la prueba lo pide con ``advance``."""

    def advance(self, seconds):
        """Adelanta el valor de ``monotonic()``.

        :param seconds: Segundos que avanza el reloj.
        :type seconds: float
        """
        self._monotonic += seconds


class BrokenModel:  # pylint: disable=too-few-public-methods
    """Modelo con un error inesperado (no es una caída del proveedor)."""

    async def complete(self, messages, *, model, max_tokens):
        """Lanza ``RuntimeError`` con un mensaje que nunca debe llegar al log."""
        del messages, model, max_tokens
        raise RuntimeError(BROKEN_MESSAGE)


class ExplodingTraceClient:  # pylint: disable=too-few-public-methods
    """Cliente de trazas roto: cualquier atributo pedido lanza ``RuntimeError``."""

    def __getattr__(self, name):
        """Simula una caída de la telemetría en cualquier llamada."""
        raise RuntimeError(TELEMETRY_FAILURE)


class RecordingClientFactory:  # pylint: disable=too-few-public-methods
    """Fábrica de clientes de trazas que graba los argumentos con que se llamó.

    :param client: Cliente que devuelve; por omisión un objeto inerte.
    """

    def __init__(self, client=None):
        self._client = client if client is not None else object()
        self.calls = []

    def __call__(self, **kwargs):
        """Graba los argumentos de palabra clave y devuelve el cliente."""
        self.calls.append(kwargs)
        return self._client


def read_events(lines, event=None):
    """Decodifica las líneas JSON del log y filtra por ``event``.

    :param lines: Líneas que recibió el ``log_sink``.
    :type lines: list[str]
    :param event: Nombre del evento; ``None`` devuelve todos.
    :type event: str or None
    :return: Registros decodificados.
    :rtype: list[dict]
    """
    records = [json.loads(line) for line in lines]
    if event is None:
        return records
    return [record for record in records if record["event"] == event]


def log_text(lines):
    """Texto de todo el log con acentos sin escapar, para buscar datos privados.

    :param lines: Líneas que recibió el ``log_sink``.
    :type lines: list[str]
    :return: Los registros serializados con ``ensure_ascii=False``.
    :rtype: str
    """
    return json.dumps(read_events(lines), ensure_ascii=False)


def is_reviewer_call(messages):
    """Indica si la llamada es del Reviewer (marcador fijo en el mensaje system).

    :param messages: Mensajes de la llamada.
    :type messages: list[dict]
    :return: ``True`` si algún mensaje ``system`` trae ``REVIEWER_MARKER``.
    :rtype: bool
    """
    return any(
        message.get("role") == "system"
        and REVIEWER_MARKER in message.get("content", "")
        for message in messages
    )


class RecordingModel:
    """Envuelve un modelo y guarda cada llamada: mensajes, modelo, tope y respuesta.

    :param inner: Modelo real de la prueba (por ejemplo el simulado).
    """

    def __init__(self, inner):
        self._inner = inner
        self.calls = []

    async def complete(self, messages, *, model, max_tokens):
        """Graba la llamada y la delega al modelo envuelto."""
        call = {
            "messages": [dict(message) for message in messages],
            "model": model,
            "max_tokens": max_tokens,
            "completion": None,
        }
        self.calls.append(call)
        call["completion"] = await self._inner.complete(
            messages, model=model, max_tokens=max_tokens
        )
        return call["completion"]


class SlowModel:
    """Modelo que tarda en un rol (``specialist`` o ``reviewer``) y luego delega.

    :param inner: Modelo al que delega.
    :param slow_role: Rol que tarda.
    :type slow_role: str
    :param delay_seconds: Segundos de espera antes de responder.
    :type delay_seconds: float
    """

    def __init__(self, inner, *, slow_role, delay_seconds=5.0):
        self._inner = inner
        self._slow_role = slow_role
        self._delay_seconds = delay_seconds

    async def complete(self, messages, *, model, max_tokens):
        """Espera sin bloquear el event loop si la llamada es del rol lento."""
        role = "reviewer" if is_reviewer_call(messages) else "specialist"
        if role == self._slow_role:
            await asyncio.sleep(self._delay_seconds)
        return await self._inner.complete(
            messages, model=model, max_tokens=max_tokens
        )


class CachedModel:  # pylint: disable=too-few-public-methods
    """Envuelve un modelo y marca cada respuesta como servida desde la caché.

    :param inner: Modelo al que delega.
    """

    def __init__(self, inner):
        self._inner = inner

    async def complete(self, messages, *, model, max_tokens):
        """Delega y devuelve la misma respuesta con ``cached=True``."""
        completion = await self._inner.complete(
            messages, model=model, max_tokens=max_tokens
        )
        return dataclasses.replace(completion, cached=True)


class SecretLeakingModel:  # pylint: disable=too-few-public-methods
    """Specialist que responde con un nombre de secreto; el Reviewer está caído."""

    async def complete(self, messages, *, model, max_tokens):
        """Filtra un secreto como Specialist y falla como Reviewer."""
        del model, max_tokens
        if is_reviewer_call(messages):
            raise ModelUnavailableError("reviewer down")
        text = json.dumps({"answer": SECRET_DRAFT}, ensure_ascii=False)
        return Completion(text=text, input_tokens=1, output_tokens=1)


class ScriptedSpecialistModel:  # pylint: disable=too-few-public-methods
    """Specialist con respuestas guionizadas; el Reviewer siempre aprueba.

    Repite la última respuesta del guion si el Specialist pide más.

    :param replies: Textos que devuelve el Specialist, en orden.
    :type replies: str
    """

    def __init__(self, *replies):
        self._replies = list(replies)
        self._specialist_calls = 0

    async def complete(self, messages, *, model, max_tokens):
        """Aprueba como Reviewer o devuelve la siguiente respuesta del guion."""
        del model, max_tokens
        if is_reviewer_call(messages):
            text = json.dumps({"verdict": "approve", "issues": []})
        else:
            self._specialist_calls += 1
            index = min(self._specialist_calls, len(self._replies)) - 1
            text = self._replies[index]
        return Completion(text=text, input_tokens=1, output_tokens=1)


class ConcurrencyProbeModel:
    """Mide cuántas llamadas están en curso a la vez.

    Cada llamada espera (sin bloquear) hasta ver dos llamadas simultáneas o
    hasta ``wait_seconds``. Si la API bloqueara el event loop, nunca habría dos.

    :param inner: Modelo al que delega.
    :param wait_seconds: Espera máxima por la otra petición.
    :type wait_seconds: float
    """

    def __init__(self, inner, wait_seconds=2.0):
        self._inner = inner
        self._wait_seconds = wait_seconds
        self.in_flight = 0
        self.max_in_flight = 0

    async def complete(self, messages, *, model, max_tokens):
        """Cuenta la llamada en curso, espera a la otra y delega."""
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            waited = 0.0
            while self.max_in_flight < 2 and waited < self._wait_seconds:
                await asyncio.sleep(0.01)
                waited += 0.01
            return await self._inner.complete(
                messages, model=model, max_tokens=max_tokens
            )
        finally:
            self.in_flight -= 1
