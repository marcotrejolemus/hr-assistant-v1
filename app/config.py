"""Configuración del producto leída y validada desde variables de entorno.

Es el único punto del producto que lee el entorno (ADR 0003). Un valor inválido
lanza ``ValueError`` con un mensaje que nombra la variable y nunca muestra
valores secretos.
"""

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Mapping, Optional

from app.security import enforce_production_rules, parse_api_keys

SUPPORTED_PROVIDERS = ("fake", "gateway")
DEFAULT_PROVIDER = "fake"
DEFAULT_MAX_STEPS = 3
DEFAULT_MAX_QUESTION_CHARS = 2000
DEFAULT_EMPLOYEES_PATH = "data/employees.json"
DEFAULT_REVIEWER_MAX_CALLS = 1
DEFAULT_MAX_MODEL_CALLS = 4
DEFAULT_MODEL_MAX_TOKENS = 300
DEFAULT_INPUT_TOKEN_BUDGET = 4000
DEFAULT_MODEL_TIMEOUT_SECONDS = 15.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_HISTORY_MESSAGES = 50
DEFAULT_MAX_ANSWER_CHARS = 4000
DEFAULT_MODEL_SMALL = "@cf/meta/llama-3.1-8b-instruct-fast"
DEFAULT_MODEL_LARGE = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
DEFAULT_SERVICE_NAME = "hr-assistant"
DEFAULT_SLO_P95_MS = 2000
DEFAULT_LANGSMITH_PROJECT = "hr-assistant-v1"
DEFAULT_ROUTER_MAX_CHARS = 80
DEFAULT_HISTORY_WINDOW = 6
DEFAULT_MODEL_TEMPERATURE = 0.0
DEFAULT_CACHE_TTL_SECONDS = 0
DEFAULT_PRICES_PATH = "data/model_prices.json"
DEFAULT_CF_GATEWAY_ID = "default"
DEFAULT_ENVIRONMENT = "development"
DEFAULT_RATE_LIMIT_PER_MINUTE = 30
PRODUCTION_ENVIRONMENT = "production"
GATEWAY_REQUIRED = ("CF_ACCOUNT_ID", "CF_GATEWAY_ID", "CF_API_TOKEN")
REVIEWER_VERDICTS = ("approve", "reject")
TRUE_VALUES = ("true", "1", "yes", "on")
FALSE_VALUES = ("false", "0", "no", "off", "")


@dataclass(frozen=True)
class Settings:  # pylint: disable=too-many-instance-attributes
    """Configuración inmutable del HR Assistant.

    :param model_provider: Proveedor del modelo de lenguaje.
    :type model_provider: str
    :param agent_max_steps: Tope de vueltas del Directory Specialist.
    :type agent_max_steps: int
    :param max_question_chars: Largo máximo de la pregunta.
    :type max_question_chars: int
    :param employees_path: Ruta del archivo de empleados.
    :type employees_path: pathlib.Path
    :param reviewer_max_calls: Tope de llamadas del Reviewer por petición.
    :type reviewer_max_calls: int
    :param max_model_calls_per_request: Tope total de llamadas al modelo.
    :type max_model_calls_per_request: int
    :param model_max_tokens: Tope de tokens de salida en cada llamada.
    :type model_max_tokens: int
    :param request_input_token_budget: Suma máxima estimada de tokens de entrada.
    :type request_input_token_budget: int
    :param model_timeout_seconds: Tiempo máximo de una llamada al modelo.
    :type model_timeout_seconds: float
    :param request_timeout_seconds: Tiempo máximo de una petición.
    :type request_timeout_seconds: float
    :param max_history_messages: Número máximo de mensajes del historial.
    :type max_history_messages: int
    :param max_answer_chars: Largo máximo de la respuesta que sale.
    :type max_answer_chars: int
    :param model_small: Nombre del modelo pequeño (Reviewer).
    :type model_small: str
    :param model_large: Nombre del modelo grande.
    :type model_large: str
    :param fake_model_fail: El modelo simulado falla en toda llamada.
    :type fake_model_fail: bool
    :param fake_reviewer_verdict: Veredicto del Reviewer simulado.
    :type fake_reviewer_verdict: str
    :param fake_reviewer_fail: El Reviewer simulado falla.
    :type fake_reviewer_fail: bool
    :param service_name: Valor del campo ``service`` del log.
    :type service_name: str
    :param slo_p95_ms: Meta de latencia p95 en milisegundos.
    :type slo_p95_ms: int
    :param langsmith_tracing: Enciende las trazas en LangSmith.
    :type langsmith_tracing: bool
    :param langsmith_api_key: Clave de LangSmith; nunca se muestra en ``repr``.
    :type langsmith_api_key: str or None
    :param langsmith_project: Proyecto de LangSmith.
    :type langsmith_project: str
    :param hide_inputs: No mandar entradas a LangSmith.
    :type hide_inputs: bool
    :param hide_outputs: No mandar salidas a LangSmith.
    :type hide_outputs: bool
    :param routing: Enciende el enrutamiento por pregunta.
    :type routing: bool
    :param router_max_chars: Preguntas más largas van al modelo grande.
    :type router_max_chars: int
    :param history_window: Mensajes de historial que recibe el Specialist.
    :type history_window: int
    :param model_temperature: Temperatura de cada llamada.
    :type model_temperature: float
    :param cache_ttl_seconds: Caché del gateway en segundos (0: apagada).
    :type cache_ttl_seconds: int
    :param prices_path: Ruta de la tabla de precios por modelo.
    :type prices_path: pathlib.Path
    :param cf_account_id: Cuenta de Cloudflare; nunca se muestra en ``repr``.
    :type cf_account_id: str
    :param cf_gateway_id: Id del AI Gateway.
    :type cf_gateway_id: str
    :param cf_api_token: Token de Cloudflare; nunca se muestra en ``repr``.
    :type cf_api_token: str
    :param environment: Entorno (``development`` o ``production``).
    :type environment: str
    :param api_keys: Clave de cada cliente; nunca se muestra en ``repr``.
    :type api_keys: dict[str, str]
    :param rate_limit_per_minute: Peticiones por cliente por minuto.
    :type rate_limit_per_minute: int
    """

    model_provider: str
    agent_max_steps: int
    max_question_chars: int
    employees_path: Path
    reviewer_max_calls: int = DEFAULT_REVIEWER_MAX_CALLS
    max_model_calls_per_request: int = DEFAULT_MAX_MODEL_CALLS
    model_max_tokens: int = DEFAULT_MODEL_MAX_TOKENS
    request_input_token_budget: int = DEFAULT_INPUT_TOKEN_BUDGET
    model_timeout_seconds: float = DEFAULT_MODEL_TIMEOUT_SECONDS
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    max_history_messages: int = DEFAULT_MAX_HISTORY_MESSAGES
    max_answer_chars: int = DEFAULT_MAX_ANSWER_CHARS
    model_small: str = DEFAULT_MODEL_SMALL
    model_large: str = DEFAULT_MODEL_LARGE
    fake_model_fail: bool = False
    fake_reviewer_verdict: str = "approve"
    fake_reviewer_fail: bool = False
    service_name: str = DEFAULT_SERVICE_NAME
    slo_p95_ms: int = DEFAULT_SLO_P95_MS
    langsmith_tracing: bool = False
    langsmith_api_key: Optional[str] = field(default=None, repr=False)
    langsmith_project: str = DEFAULT_LANGSMITH_PROJECT
    hide_inputs: bool = True
    hide_outputs: bool = True
    routing: bool = True
    router_max_chars: int = DEFAULT_ROUTER_MAX_CHARS
    history_window: int = DEFAULT_HISTORY_WINDOW
    model_temperature: float = DEFAULT_MODEL_TEMPERATURE
    cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS
    prices_path: Path = Path(DEFAULT_PRICES_PATH)
    cf_account_id: str = field(default="", repr=False)
    cf_gateway_id: str = DEFAULT_CF_GATEWAY_ID
    cf_api_token: str = field(default="", repr=False)
    environment: str = DEFAULT_ENVIRONMENT
    api_keys: Dict[str, str] = field(default_factory=dict, repr=False, compare=False)
    rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE


def _non_negative_number(
    environ: Mapping[str, str], name: str, default: float
) -> float:
    """Lee un número finito mayor o igual que cero.

    :param environ: Variables de entorno.
    :type environ: Mapping[str, str]
    :param name: Nombre de la variable.
    :type name: str
    :param default: Valor por omisión si la variable no está.
    :type default: float
    :return: El número leído.
    :rtype: float
    :raises ValueError: Si el valor no es un número mayor o igual que cero.
    """
    raw = environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw.strip())
    except ValueError as error:
        raise ValueError(f"{name} must be a number >= 0") from error
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a number >= 0")
    return value


def _positive_int(environ: Mapping[str, str], name: str, default: int) -> int:
    """Lee un entero positivo de ``environ``.

    :param environ: Variables de entorno.
    :type environ: Mapping[str, str]
    :param name: Nombre de la variable.
    :type name: str
    :param default: Valor por omisión si la variable no está.
    :type default: int
    :return: El entero leído.
    :rtype: int
    :raises ValueError: Si el valor no es un entero mayor que cero.
    """
    raw = environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except ValueError as error:
        raise ValueError(f"{name} must be a positive integer") from error
    if value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _positive_float(
    environ: Mapping[str, str], name: str, default: float
) -> float:
    """Lee un número positivo (acepta fracciones como ``0.05``).

    :param environ: Variables de entorno.
    :type environ: Mapping[str, str]
    :param name: Nombre de la variable.
    :type name: str
    :param default: Valor por omisión si la variable no está.
    :type default: float
    :return: El número leído.
    :rtype: float
    :raises ValueError: Si el valor no es un número mayor que cero.
    """
    raw = environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw.strip())
    except ValueError as error:
        raise ValueError(f"{name} must be a positive number") from error
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return value


def _flag(environ: Mapping[str, str], name: str, default: bool = False) -> bool:
    """Lee una bandera booleana (``true``/``false``).

    :param environ: Variables de entorno.
    :type environ: Mapping[str, str]
    :param name: Nombre de la variable.
    :type name: str
    :param default: Valor si la variable no está definida.
    :type default: bool
    :return: ``True`` si la bandera está encendida.
    :rtype: bool
    :raises ValueError: Si el valor no es reconocible como booleano.
    """
    if name not in environ:
        return default
    raw = environ[name].strip().lower()
    if raw in TRUE_VALUES:
        return True
    if raw in FALSE_VALUES:
        return False
    raise ValueError(f"{name} must be true or false")


def _required_text(environ: Mapping[str, str], name: str, default: str) -> str:
    """Lee un texto que no puede quedar vacío (nombre de modelo, servicio...).

    :param environ: Variables de entorno.
    :type environ: Mapping[str, str]
    :param name: Nombre de la variable.
    :type name: str
    :param default: Valor por omisión.
    :type default: str
    :return: El texto sin espacios sobrantes.
    :rtype: str
    :raises ValueError: Si el nombre está vacío.
    """
    value = environ.get(name, default).strip()
    if not value:
        raise ValueError(f"{name} must not be empty")
    return value


def _fake_switches(environ: Mapping[str, str], provider: str) -> dict:
    """Lee los ``FAKE_*`` y exige ``MODEL_PROVIDER=fake`` si alguno está activo.

    Esta regla se valida antes que la de proveedor no soportado, para que el
    error nombre el ``FAKE_*`` responsable.

    :param environ: Variables de entorno.
    :type environ: Mapping[str, str]
    :param provider: Proveedor ya normalizado.
    :type provider: str
    :return: Campos ``fake_*`` de ``Settings``.
    :rtype: dict
    :raises ValueError: Si un valor es inválido o un ``FAKE_*`` está activo con
        otro proveedor.
    """
    verdict = environ.get("FAKE_REVIEWER_VERDICT", "approve").strip().lower()
    if verdict not in REVIEWER_VERDICTS:
        raise ValueError("FAKE_REVIEWER_VERDICT must be approve or reject")
    switches = {
        "fake_model_fail": _flag(environ, "FAKE_MODEL_FAIL"),
        "fake_reviewer_verdict": verdict,
        "fake_reviewer_fail": _flag(environ, "FAKE_REVIEWER_FAIL"),
    }
    active = {
        "FAKE_MODEL_FAIL": switches["fake_model_fail"],
        "FAKE_REVIEWER_VERDICT": verdict != "approve",
        "FAKE_REVIEWER_FAIL": switches["fake_reviewer_fail"],
    }
    if provider != "fake":
        for name, is_active in active.items():
            if is_active:
                raise ValueError(f"{name} is only allowed with MODEL_PROVIDER=fake")
    return switches


def _limits(environ: Mapping[str, str]) -> dict:
    """Lee y valida los límites de llamadas, tokens, tiempos y tamaños.

    :param environ: Variables de entorno.
    :type environ: Mapping[str, str]
    :return: Campos de límites de ``Settings``.
    :rtype: dict
    :raises ValueError: Si algún límite es inválido o el presupuesto de
        llamadas no cubre al Specialist más el Reviewer.
    """
    limits = {
        "agent_max_steps": _positive_int(
            environ, "AGENT_MAX_STEPS", DEFAULT_MAX_STEPS
        ),
        "max_question_chars": _positive_int(
            environ, "MAX_QUESTION_CHARS", DEFAULT_MAX_QUESTION_CHARS
        ),
        "reviewer_max_calls": _positive_int(
            environ, "REVIEWER_MAX_CALLS", DEFAULT_REVIEWER_MAX_CALLS
        ),
        "max_model_calls_per_request": _positive_int(
            environ, "MAX_MODEL_CALLS_PER_REQUEST", DEFAULT_MAX_MODEL_CALLS
        ),
        "model_max_tokens": _positive_int(
            environ, "MODEL_MAX_TOKENS", DEFAULT_MODEL_MAX_TOKENS
        ),
        "request_input_token_budget": _positive_int(
            environ, "REQUEST_INPUT_TOKEN_BUDGET", DEFAULT_INPUT_TOKEN_BUDGET
        ),
        "model_timeout_seconds": _positive_float(
            environ, "MODEL_TIMEOUT_SECONDS", DEFAULT_MODEL_TIMEOUT_SECONDS
        ),
        "request_timeout_seconds": _positive_float(
            environ, "REQUEST_TIMEOUT_SECONDS", DEFAULT_REQUEST_TIMEOUT_SECONDS
        ),
        "max_history_messages": _positive_int(
            environ, "MAX_HISTORY_MESSAGES", DEFAULT_MAX_HISTORY_MESSAGES
        ),
        "max_answer_chars": _positive_int(
            environ, "MAX_ANSWER_CHARS", DEFAULT_MAX_ANSWER_CHARS
        ),
    }
    needed = limits["agent_max_steps"] + limits["reviewer_max_calls"]
    if limits["max_model_calls_per_request"] < needed:
        raise ValueError(
            "MAX_MODEL_CALLS_PER_REQUEST must be at least "
            "AGENT_MAX_STEPS + REVIEWER_MAX_CALLS"
        )
    return limits


def _observability(environ: Mapping[str, str]) -> dict:
    """Lee la configuración de logs, métricas y trazas (``spec/02``).

    La clave de LangSmith se guarda tal cual, pero ningún error la muestra.

    :param environ: Variables de entorno.
    :type environ: Mapping[str, str]
    :return: Campos de observabilidad de ``Settings``.
    :rtype: dict
    :raises ValueError: Si algún valor es inválido; el mensaje nombra la
        variable y nunca su valor.
    """
    api_key = environ.get("LANGSMITH_API_KEY", "").strip()
    return {
        "service_name": _required_text(
            environ, "SERVICE_NAME", DEFAULT_SERVICE_NAME
        ),
        "slo_p95_ms": _positive_int(environ, "SLO_P95_MS", DEFAULT_SLO_P95_MS),
        "langsmith_tracing": _flag(environ, "LANGSMITH_TRACING"),
        "langsmith_api_key": api_key or None,
        "langsmith_project": _required_text(
            environ, "LANGSMITH_PROJECT", DEFAULT_LANGSMITH_PROJECT
        ),
        "hide_inputs": _flag(environ, "HIDE_INPUTS", default=True),
        "hide_outputs": _flag(environ, "HIDE_OUTPUTS", default=True),
    }


def _non_negative_int(environ: Mapping[str, str], name: str, default: int) -> int:
    """Lee un entero mayor o igual que cero.

    :param environ: Variables de entorno.
    :type environ: Mapping[str, str]
    :param name: Nombre de la variable.
    :type name: str
    :param default: Valor por omisión si la variable no está.
    :type default: int
    :return: El entero leído.
    :rtype: int
    :raises ValueError: Si el valor no es un entero mayor o igual que cero.
    """
    raw = environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except ValueError as error:
        raise ValueError(f"{name} must be an integer >= 0") from error
    if value < 0:
        raise ValueError(f"{name} must be an integer >= 0")
    return value


def _costs(environ: Mapping[str, str]) -> dict:
    """Lee las palancas de costo de ``spec/03``.

    :param environ: Variables de entorno.
    :type environ: Mapping[str, str]
    :return: Campos de costo de ``Settings``.
    :rtype: dict
    :raises ValueError: Si algún valor es inválido; el mensaje nombra la
        variable.
    """
    return {
        "routing": _flag(environ, "ROUTING", default=True),
        "router_max_chars": _positive_int(
            environ, "ROUTER_MAX_CHARS", DEFAULT_ROUTER_MAX_CHARS
        ),
        "history_window": _positive_int(
            environ, "HISTORY_WINDOW", DEFAULT_HISTORY_WINDOW
        ),
        "model_temperature": _non_negative_number(
            environ, "MODEL_TEMPERATURE", DEFAULT_MODEL_TEMPERATURE
        ),
        "cache_ttl_seconds": _non_negative_int(
            environ, "CACHE_TTL_SECONDS", DEFAULT_CACHE_TTL_SECONDS
        ),
        "prices_path": Path(
            _required_text(environ, "PRICES_PATH", DEFAULT_PRICES_PATH)
        ),
    }


def _cloudflare(environ: Mapping[str, str], provider: str) -> dict:
    """Lee las credenciales de Cloudflare; con ``gateway`` son obligatorias.

    Los mensajes de error nombran la variable y nunca muestran su valor.

    :param environ: Variables de entorno.
    :type environ: Mapping[str, str]
    :param provider: Proveedor ya normalizado.
    :type provider: str
    :return: Campos ``cf_*`` de ``Settings``.
    :rtype: dict
    :raises ValueError: Si el proveedor es ``gateway`` y falta una variable o
        está en blanco.
    """
    values = {
        "CF_ACCOUNT_ID": environ.get("CF_ACCOUNT_ID", "").strip(),
        "CF_GATEWAY_ID": environ.get("CF_GATEWAY_ID", DEFAULT_CF_GATEWAY_ID).strip(),
        "CF_API_TOKEN": environ.get("CF_API_TOKEN", "").strip(),
    }
    if provider == "gateway":
        for name in GATEWAY_REQUIRED:
            if not values[name]:
                raise ValueError(f"{name} is required with MODEL_PROVIDER=gateway")
    return {
        "cf_account_id": values["CF_ACCOUNT_ID"],
        "cf_gateway_id": values["CF_GATEWAY_ID"],
        "cf_api_token": values["CF_API_TOKEN"],
    }


def _environment(environ: Mapping[str, str], cache_ttl_seconds: int) -> str:
    """Lee ``ENVIRONMENT`` y aplica la regla de caché aprobada (ADR 0006).

    :param environ: Variables de entorno.
    :type environ: Mapping[str, str]
    :param cache_ttl_seconds: Valor ya validado de ``CACHE_TTL_SECONDS``.
    :type cache_ttl_seconds: int
    :return: El entorno en minúsculas.
    :rtype: str
    :raises ValueError: Si es ``production`` y la caché está encendida.
    """
    environment = (
        _required_text(environ, "ENVIRONMENT", DEFAULT_ENVIRONMENT).lower()
    )
    if environment == PRODUCTION_ENVIRONMENT and cache_ttl_seconds > 0:
        # La caché del gateway no aísla por cliente: prohibida en producción.
        raise ValueError("CACHE_TTL_SECONDS must be 0 when ENVIRONMENT=production")
    return environment


def load_settings(environ: Optional[Mapping[str, str]] = None) -> Settings:
    """Construye la configuración a partir de las variables de entorno.

    Las variables que no conoce (por ejemplo las de incrementos posteriores)
    se ignoran sin impedir el arranque.

    :param environ: Variables de entorno; si es ``None`` se usa ``os.environ``.
    :type environ: Mapping[str, str] or None
    :return: La configuración validada.
    :rtype: Settings
    :raises ValueError: Si algún valor es inválido o, con
        ``ENVIRONMENT=production``, si la configuración es insegura; el mensaje
        nombra la variable y nunca un valor secreto.
    """
    if environ is None:
        environ = os.environ
    provider = environ.get("MODEL_PROVIDER", DEFAULT_PROVIDER).strip().lower()
    switches = _fake_switches(environ, provider)
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"MODEL_PROVIDER must be one of {', '.join(SUPPORTED_PROVIDERS)}"
        )
    employees_path = environ.get("EMPLOYEES_PATH", DEFAULT_EMPLOYEES_PATH).strip()
    if not employees_path:
        raise ValueError("EMPLOYEES_PATH must not be empty")
    costs = _costs(environ)
    settings = Settings(
        model_provider=provider,
        employees_path=Path(employees_path),
        model_small=_required_text(environ, "MODEL_SMALL", DEFAULT_MODEL_SMALL),
        model_large=_required_text(environ, "MODEL_LARGE", DEFAULT_MODEL_LARGE),
        environment=_environment(environ, costs["cache_ttl_seconds"]),
        api_keys=parse_api_keys(environ.get("API_KEYS", "")),
        rate_limit_per_minute=_positive_int(
            environ, "RATE_LIMIT_PER_MINUTE", DEFAULT_RATE_LIMIT_PER_MINUTE
        ),
        **_limits(environ),
        **switches,
        **_observability(environ),
        **costs,
        **_cloudflare(environ, provider),
    )
    if settings.environment == PRODUCTION_ENVIRONMENT:
        # Compliance como código (spec/04): se niega a arrancar si es inseguro.
        enforce_production_rules(
            environ,
            provider=settings.model_provider,
            api_keys=settings.api_keys,
            tracing=settings.langsmith_tracing,
            hide_inputs=settings.hide_inputs,
            hide_outputs=settings.hide_outputs,
        )
    return settings
