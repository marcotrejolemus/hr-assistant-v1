"""Interfaz async del modelo de lenguaje y modelo simulado determinista.

La interfaz conserva el nombre ``complete`` de ADR 0002 y pasa a async con el
nombre del modelo y el tope de salida por palabra clave (ADR 0004).
"""

import json
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Protocol

import httpx

from app.config import DEFAULT_MODEL_LARGE, DEFAULT_MODEL_MAX_TOKENS, Settings
from app.directory import EmployeeDirectory

GATEWAY_URL = (
    "https://gateway.ai.cloudflare.com/v1/{account}/{gateway}"
    "/workers-ai/v1/chat/completions"
)
CACHE_TTL_HEADER = "cf-aig-cache-ttl"
CACHE_STATUS_HEADER = "cf-aig-cache-status"
CACHE_HIT = "HIT"
TOOL_RESULT_PREFIX = "Resultado de la herramienta: "
HELP_MESSAGE = "Pregúntame por un empleado (EMP-0001) o un departamento."
EMPLOYEE_ID_PATTERN = re.compile(r"EMP-\d{4}")
REVIEWER_MARKER = "[hr-assistant-reviewer-v1]"
FAKE_REJECT_ISSUE = "el revisor simulado rechaza el borrador"

Message = Dict[str, str]


def extract_json_object(text: str) -> dict:
    """Quita el envoltorio del JSON del modelo y devuelve su único objeto.

    Solo tolera el envoltorio. Recorre cada ``{`` y ``[`` del texto completo
    (dentro y fuera de bloques de código Markdown, cuyas marcas no traen llaves
    ni corchetes) y conserva los valores JSON válidos de primer nivel, saltando
    las posiciones que caen dentro de un valor ya decodificado. Las llaves que
    no forman JSON (por ejemplo ``{nombre}``) se ignoran. Debe quedar
    exactamente un valor y debe ser un objeto: varios valores, sea en un mismo
    bloque, en varios bloques o fuera de ellos, son ambiguos. Quien llama
    valida después el esquema.

    Caso límite: si un objeto exterior queda sin cerrar y contiene un objeto
    interior completo, el exterior no es JSON y se acepta el interior; el
    esquema estricto de quien llama decide si es válido.

    :param text: Texto devuelto por el modelo.
    :type text: str
    :return: El único objeto JSON de la respuesta.
    :rtype: dict
    :raises ValueError: Si no hay ningún valor JSON, hay más de uno, el único
        valor es un arreglo o el JSON es inválido.
    """
    decoder = json.JSONDecoder()
    values = []
    position = 0
    while position < len(text):
        if text[position] not in "{[":
            position += 1
            continue
        try:
            value, end = decoder.raw_decode(text, position)
        except ValueError:
            position += 1
            continue
        values.append(value)
        position = end
    if len(values) != 1 or not isinstance(values[0], dict):
        raise ValueError("model reply must contain exactly one JSON object")
    return values[0]


@dataclass(frozen=True)
class Completion:
    """Respuesta de un modelo.

    :param text: Texto de la respuesta (un objeto JSON).
    :type text: str
    :param input_tokens: Tokens de entrada.
    :type input_tokens: int
    :param output_tokens: Tokens de salida.
    :type output_tokens: int
    :param cached: ``True`` si la respuesta salió de la caché del gateway (no
        cuesta).
    :type cached: bool
    """

    text: str
    input_tokens: int
    output_tokens: int
    cached: bool = False


@dataclass(frozen=True)
class CallOptions:
    """Opciones de cada llamada al modelo.

    :param model: Nombre del modelo que se pide al proveedor.
    :type model: str
    :param max_tokens: Tope de tokens de salida.
    :type max_tokens: int
    """

    model: str = DEFAULT_MODEL_LARGE
    max_tokens: int = DEFAULT_MODEL_MAX_TOKENS


class ModelUnavailableError(Exception):
    """El proveedor del modelo falló o no respondió a tiempo."""


class CallBudgetExceededError(Exception):
    """La siguiente llamada rebasaría el presupuesto de la petición."""


class LanguageModel(Protocol):  # pylint: disable=too-few-public-methods
    """Interfaz que cumple cualquier modelo que usen los agentes."""

    async def complete(
        self, messages: List[Message], *, model: str, max_tokens: int
    ) -> Completion:
        """Responde a una conversación.

        :param messages: Mensajes con ``role`` y ``content``.
        :type messages: list[dict]
        :param model: Nombre del modelo.
        :type model: str
        :param max_tokens: Tope de tokens de salida.
        :type max_tokens: int
        :return: La respuesta del modelo.
        :rtype: Completion
        :raises ModelUnavailableError: Si el proveedor no está disponible.
        """


def count_words(text: str) -> int:
    """Cuenta palabras separadas por espacios (tokens aproximados).

    :param text: Texto a contar.
    :type text: str
    :return: Número de palabras.
    :rtype: int
    """
    return len(text.split())


def estimate_input_tokens(messages: Iterable[Message]) -> int:
    """Estima los tokens de entrada de una llamada como palabras totales.

    :param messages: Mensajes con ``content``.
    :type messages: Iterable[dict]
    :return: Tokens estimados.
    :rtype: int
    """
    return sum(count_words(message.get("content", "")) for message in messages)


def is_reviewer_request(messages: Iterable[Message]) -> bool:
    """Indica si la llamada es del Reviewer (marcador en un mensaje ``system``).

    :param messages: Mensajes de la llamada.
    :type messages: Iterable[dict]
    :return: ``True`` si algún mensaje ``system`` trae ``REVIEWER_MARKER``.
    :rtype: bool
    """
    return any(
        message.get("role") == "system"
        and REVIEWER_MARKER in message.get("content", "")
        for message in messages
    )


class FakeLanguageModel:  # pylint: disable=too-few-public-methods
    """Modelo simulado: decide con reglas fijas, sin red ni costo.

    Como Specialist aplica las cuatro reglas de ``spec/01`` sobre el último
    mensaje; como Reviewer devuelve un veredicto fijo.

    :param departments: Departamentos que existen en los datos.
    :type departments: Iterable[str]
    :param fail: Si es ``True``, toda llamada falla.
    :type fail: bool
    :param reviewer_verdict: Veredicto del Reviewer (``approve`` o ``reject``).
    :type reviewer_verdict: str
    :param reviewer_fail: Si es ``True``, solo fallan las llamadas del Reviewer.
    :type reviewer_fail: bool
    """

    def __init__(
        self,
        departments: Iterable[str],
        *,
        fail: bool = False,
        reviewer_verdict: str = "approve",
        reviewer_fail: bool = False,
    ):
        self._departments = tuple(departments)
        self._fail = fail
        self._reviewer_verdict = reviewer_verdict
        self._reviewer_fail = reviewer_fail

    def _decide(self, last: str) -> dict:
        """Aplica las cuatro reglas del Specialist simulado.

        :param last: Contenido del último mensaje.
        :type last: str
        :return: Objeto de respuesta (herramienta o respuesta final).
        :rtype: dict
        """
        if last.startswith(TOOL_RESULT_PREFIX):
            result = last[len(TOOL_RESULT_PREFIX):]
            return {"answer": f"Según el directorio: {result}"}
        match = EMPLOYEE_ID_PATTERN.search(last)
        if match:
            return {"tool": "get_employee", "args": {"employee_id": match.group(0)}}
        lowered = last.casefold()
        for department in self._departments:
            if department.casefold() in lowered:
                return {
                    "tool": "search_by_department",
                    "args": {"department": department},
                }
        return {"answer": HELP_MESSAGE}

    def _review(self) -> dict:
        """Devuelve el veredicto fijo del Reviewer simulado.

        :return: Objeto ``{"verdict", "issues"}``.
        :rtype: dict
        """
        if self._reviewer_verdict == "reject":
            return {"verdict": "reject", "issues": [FAKE_REJECT_ISSUE]}
        return {"verdict": "approve", "issues": []}

    async def complete(
        self, messages: List[Message], *, model: str, max_tokens: int
    ) -> Completion:
        """Responde según el rol y el último mensaje; cuenta tokens por palabras.

        :param messages: Mensajes con ``role`` y ``content``.
        :type messages: list[dict]
        :param model: Nombre del modelo; el simulado responde igual con
            cualquier nombre y su costo sale del precio de ese nombre.
        :type model: str
        :param max_tokens: Tope de salida (el simulado responde corto).
        :type max_tokens: int
        :return: La respuesta en JSON y el conteo aproximado de tokens.
        :rtype: Completion
        :raises ModelUnavailableError: Si se pidió simular un fallo.
        """
        del model, max_tokens
        reviewer = is_reviewer_request(messages)
        if self._fail or (reviewer and self._reviewer_fail):
            raise ModelUnavailableError("simulated provider failure")
        if reviewer:
            reply = self._review()
        else:
            last = messages[-1]["content"] if messages else ""
            reply = self._decide(last)
        text = json.dumps(reply, ensure_ascii=False)
        return Completion(
            text=text,
            input_tokens=estimate_input_tokens(messages),
            output_tokens=count_words(text),
        )


class GatewayLanguageModel:
    """Modelo real: Cloudflare Workers AI a través de AI Gateway (``spec/03``).

    El cliente HTTP se inyecta; quien lo crea lo cierra. El token solo viaja en
    el encabezado ``Authorization`` y nunca aparece en errores ni logs.

    :param settings: Configuración con las variables ``CF_*``, temperatura y
        caché.
    :type settings: Settings
    :param client: Cliente HTTP async.
    :type client: httpx.AsyncClient
    """

    def __init__(self, *, settings: Settings, client: httpx.AsyncClient):
        self._settings = settings
        self._client = client
        self._url = GATEWAY_URL.format(
            account=settings.cf_account_id, gateway=settings.cf_gateway_id
        )

    def _headers(self) -> Dict[str, str]:
        """Arma los encabezados: token y, si la caché está encendida, su TTL.

        :return: Encabezados de la petición.
        :rtype: dict
        """
        headers = {"Authorization": f"Bearer {self._settings.cf_api_token}"}
        if self._settings.cache_ttl_seconds > 0:
            headers[CACHE_TTL_HEADER] = str(self._settings.cache_ttl_seconds)
        return headers

    async def complete(
        self, messages: List[Message], *, model: str, max_tokens: int
    ) -> Completion:
        """Llama a ``chat/completions`` del gateway.

        :param messages: Mensajes con ``role`` y ``content``.
        :type messages: list[dict]
        :param model: Nombre del modelo de Workers AI.
        :type model: str
        :param max_tokens: Tope de tokens de salida.
        :type max_tokens: int
        :return: Texto, tokens de ``usage`` y si salió de la caché.
        :rtype: Completion
        :raises ModelUnavailableError: Si hay error HTTP, de transporte, tiempo
            agotado o una respuesta con forma inesperada.
        """
        body = {
            "model": model,
            "messages": list(messages),
            "max_tokens": max_tokens,
            "temperature": self._settings.model_temperature,
        }
        try:
            response = await self._client.post(
                self._url, json=body, headers=self._headers()
            )
            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            usage = data["usage"]
            input_tokens = int(usage["prompt_tokens"])
            output_tokens = int(usage["completion_tokens"])
        except httpx.HTTPError as error:
            # Incluye errores HTTP, de transporte y httpx.TimeoutException.
            raise ModelUnavailableError("gateway request failed") from error
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise ModelUnavailableError("gateway reply is malformed") from error
        if not isinstance(text, str):
            raise ModelUnavailableError("gateway reply is malformed")
        status = response.headers.get(CACHE_STATUS_HEADER, "").strip().upper()
        return Completion(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached=status == CACHE_HIT,
        )


def build_model(
    settings: Settings,
    directory: EmployeeDirectory,
    client: Optional[httpx.AsyncClient] = None,
) -> LanguageModel:
    """Crea el modelo indicado por ``MODEL_PROVIDER`` y aplica los ``FAKE_*``.

    :param settings: Configuración validada.
    :type settings: Settings
    :param directory: Directorio de empleados (da la lista de departamentos).
    :type directory: EmployeeDirectory
    :param client: Cliente HTTP para ``gateway``; por omisión uno nuevo con
        ``MODEL_TIMEOUT_SECONDS`` (``create_app`` lo cierra al apagar).
    :type client: httpx.AsyncClient or None
    :return: El modelo de lenguaje.
    :rtype: LanguageModel
    :raises ValueError: Si el proveedor no está soportado.
    """
    if settings.model_provider == "fake":
        return FakeLanguageModel(
            directory.departments(),
            fail=settings.fake_model_fail,
            reviewer_verdict=settings.fake_reviewer_verdict,
            reviewer_fail=settings.fake_reviewer_fail,
        )
    if settings.model_provider == "gateway":
        if client is None:
            client = httpx.AsyncClient(timeout=settings.model_timeout_seconds)
        return GatewayLanguageModel(settings=settings, client=client)
    raise ValueError(f"Unsupported MODEL_PROVIDER {settings.model_provider!r}")
