"""API web sin estado del HR Assistant.

Uso: ``uvicorn app.main:app`` desde la carpeta ``product/``.

Toda respuesta lleva ``X-Request-ID`` (el del cliente si es seguro, o un UUID
nuevo) y deja un evento ``request`` en el log JSON y en las métricas.
"""

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Literal, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, field_validator

from app.clock import Clock, SystemClock
from app.config import Settings, load_settings
from app.costs import load_prices, require_configured_prices
from app.directory import EmployeeDirectory
from app.guards import PolicyViolationError
from app.llm import LanguageModel, ModelUnavailableError, build_model
from app.metrics import Metrics
from app.observability import (
    ClientFactory,
    JsonLogger,
    LogSink,
    RequestObserver,
    Tracer,
    accept_request_id,
    build_tracer,
)
from app.security import (
    API_KEY_HEADER,
    INVALID_KEY_DETAIL,
    RATE_LIMITED_DETAIL,
    RateLimiter,
    find_client,
)
from app.supervisor import Supervisor

INDEX_PATH = Path(__file__).resolve().parent / "static" / "index.html"
REQUEST_ID_HEADER = "X-Request-ID"
POLICY_BLOCKED_DETAIL = "request blocked by policy"
MODEL_UNAVAILABLE_DETAIL = "model unavailable"
INTERNAL_ERROR_DETAIL = "internal error"

Lifespan = Callable[[FastAPI], Any]


class HistoryMessage(BaseModel):
    """Mensaje previo de la conversación, enviado por el cliente.

    :param role: ``user`` o ``assistant``.
    :type role: str
    :param content: Texto del mensaje.
    :type content: str
    """

    role: Literal["user", "assistant"]
    content: str


class ReviewInfo(BaseModel):
    """Resumen de la revisión; el texto de los problemas nunca se devuelve.

    :param status: ``approved``, ``rejected`` o ``unavailable``.
    :type status: str
    :param issue_count: Número de problemas reportados.
    :type issue_count: int
    """

    status: Literal["approved", "rejected", "unavailable"]
    issue_count: int


class AskResponse(BaseModel):
    """Respuesta de ``POST /ask``.

    :param answer: Respuesta en español.
    :type answer: str
    :param steps: Llamadas del Directory Specialist al modelo.
    :type steps: int
    :param tools_used: Herramientas usadas.
    :type tools_used: list[str]
    :param input_tokens: Tokens de entrada de todas las llamadas.
    :type input_tokens: int
    :param output_tokens: Tokens de salida de todas las llamadas.
    :type output_tokens: int
    :param model_calls: Llamadas al modelo de todos los agentes.
    :type model_calls: int
    :param review: Estado de la revisión.
    :type review: ReviewInfo
    :param redactions: Tipos de PII redactados, sin repetir.
    :type redactions: list[str]
    :param request_id: Id de la petición, igual al encabezado ``X-Request-ID``.
    :type request_id: str
    :param model: Modelo que eligió el enrutador para el Specialist.
    :type model: str
    :param route: Motivo del enrutador.
    :type route: str
    :param cached_calls: Llamadas servidas desde la caché del gateway.
    :type cached_calls: int
    :param cost_usd: Costo estimado de todas las llamadas, en USD.
    :type cost_usd: float
    """

    answer: str
    steps: int
    tools_used: List[str]
    input_tokens: int
    output_tokens: int
    model_calls: int
    review: ReviewInfo
    redactions: List[str]
    request_id: str
    model: str
    route: str
    cached_calls: int
    cost_usd: float


class ErrorResponse(BaseModel):
    """Cuerpo de los errores 400, 500 y 502 de ``POST /ask``.

    :param detail: Mensaje fijo de la API.
    :type detail: str
    :param request_id: Id de la petición, para soporte.
    :type request_id: str
    """

    detail: str
    request_id: str


class HealthResponse(BaseModel):
    """Respuesta de ``GET /health``.

    :param status: Estado del proceso.
    :type status: str
    :param pid: Id del proceso que atendió.
    :type pid: int
    """

    status: str
    pid: int


@dataclass(frozen=True)
class _Services:
    """Dependencias armadas una vez por aplicación (estado de instancia).

    :param settings: Configuración validada.
    :type settings: Settings
    :param supervisor: Orquestador de las preguntas.
    :type supervisor: Supervisor
    :param clock: Reloj inyectado.
    :type clock: Clock
    :param logger: Logger JSON.
    :type logger: JsonLogger
    :param tracer: Trazas de LangSmith (apagadas o encendidas).
    :type tracer: Tracer
    :param metrics: Métricas de esta aplicación.
    :type metrics: Metrics
    :param rate_limiter: Límite de peticiones por cliente de esta aplicación.
    :type rate_limiter: RateLimiter
    """

    settings: Settings
    supervisor: Supervisor
    clock: Clock
    logger: JsonLogger
    tracer: Tracer
    metrics: Metrics
    rate_limiter: RateLimiter

    def record_error(self, request_id: str, error: BaseException) -> None:
        """Registra un error por su tipo en el log y en las métricas.

        :param request_id: Id de la petición.
        :type request_id: str
        :param error: Error ocurrido; solo se usa el nombre de su clase.
        :type error: BaseException
        """
        error_type = type(error).__name__
        self.logger.log("error", request_id, error_type=error_type)
        self.metrics.record_error(error_type)


def _build_request_model(settings: Settings) -> type:
    """Crea el modelo de petición con los tamaños máximos configurados.

    :param settings: Configuración con ``max_question_chars`` (pregunta y cada
        ``content`` del historial) y ``max_history_messages``.
    :type settings: Settings
    :return: Clase Pydantic de la petición de ``POST /ask``.
    :rtype: type
    """
    max_chars = settings.max_question_chars

    class LimitedHistoryMessage(HistoryMessage):
        """Mensaje previo con el mismo largo máximo que la pregunta."""

        content: str = Field(max_length=max_chars)

    class AskRequest(BaseModel):
        """Cuerpo de ``POST /ask``."""

        question: str = Field(min_length=1, max_length=max_chars)
        history: List[LimitedHistoryMessage] = Field(
            default_factory=list, max_length=settings.max_history_messages
        )

        @field_validator("question")
        @classmethod
        def _not_blank(cls, value: str) -> str:
            """Rechaza preguntas que solo tienen espacios."""
            if not value.strip():
                raise ValueError("question must not be blank")
            return value

    return AskRequest


def _error_response(status: int, detail: str, request_id: str) -> JSONResponse:
    """Arma una respuesta de error con el ``request_id`` en el cuerpo.

    :param status: Código HTTP.
    :type status: int
    :param detail: Mensaje fijo de la API.
    :type detail: str
    :param request_id: Id de la petición.
    :type request_id: str
    :return: Respuesta JSON.
    :rtype: fastapi.responses.JSONResponse
    """
    return JSONResponse(
        status_code=status, content={"detail": detail, "request_id": request_id}
    )


def _add_request_middleware(application: FastAPI, services: _Services) -> None:
    """Agrega el middleware de ``request_id``, log ``request`` y métricas.

    Un error inesperado se convierte aquí en ``500 internal error`` con el
    ``request_id``; el log guarda solo el tipo de error, nunca su mensaje.

    :param application: Aplicación FastAPI.
    :type application: fastapi.FastAPI
    :param services: Dependencias de la aplicación.
    :type services: _Services
    """

    @application.middleware("http")
    async def observe_request(request: Request, call_next: Any) -> Response:
        """Fija el ``request_id``, atiende y registra la petición."""
        request_id = accept_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        started = services.clock.monotonic()
        try:
            response = await call_next(request)
        except Exception as error:  # pylint: disable=broad-exception-caught
            # Red de seguridad: nunca sale un traceback ni el mensaje del error.
            services.record_error(request_id, error)
            response = _error_response(500, INTERNAL_ERROR_DETAIL, request_id)
        latency_ms = round((services.clock.monotonic() - started) * 1000, 3)
        response.headers[REQUEST_ID_HEADER] = request_id
        client = getattr(request.state, "client", None)
        services.logger.log(
            "request",
            request_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            latency_ms=latency_ms,
            **({"client": client} if client else {}),
        )
        services.metrics.record_request(response.status_code, latency_ms)
        return response


def _build_client_dependency(services: _Services) -> Callable[..., Any]:
    """Crea la dependencia que exige ``X-API-Key`` y aplica el límite.

    Usa ``APIKeyHeader`` con ``auto_error=False`` para declarar el esquema en
    OpenAPI y responder 401 (no el 403 por omisión). Sin ``API_KEYS`` nadie
    entra; no existe ningún bypass. La clave recibida nunca se registra.

    :param services: Dependencias de la aplicación.
    :type services: _Services
    :return: Dependencia de FastAPI que devuelve el nombre del cliente.
    :rtype: Callable
    """
    scheme = APIKeyHeader(
        name=API_KEY_HEADER,
        auto_error=False,
        description="Clave del cliente (una por cliente, en API_KEYS).",
    )

    async def require_client(
        request: Request, api_key: Optional[str] = Security(scheme)
    ) -> str:
        """Autentica al cliente y cuenta la petición en su límite.

        :param request: Petición en curso.
        :type request: fastapi.Request
        :param api_key: Valor de ``X-API-Key``, si vino.
        :type api_key: str or None
        :return: Nombre del cliente autenticado.
        :rtype: str
        :raises HTTPException: 401 sin clave o con una inválida; 429 si el
            cliente rebasó ``RATE_LIMIT_PER_MINUTE``.
        """
        request_id = request.state.request_id
        client = find_client(services.settings.api_keys, api_key)
        if client is None:
            services.logger.log(
                "audit",
                request_id,
                client=None,
                action="auth_denied",
                outcome="denied",
                path=request.url.path,
            )
            raise HTTPException(status_code=401, detail=INVALID_KEY_DETAIL)
        request.state.client = client
        retry_after = services.rate_limiter.check(client)
        if retry_after is not None:
            services.logger.log(
                "audit",
                request_id,
                client=client,
                action="rate_limited",
                outcome="denied",
                retry_after=retry_after,
            )
            raise HTTPException(
                status_code=429,
                detail=RATE_LIMITED_DETAIL,
                headers={"Retry-After": str(retry_after)},
            )
        return client

    return require_client


def _add_routes(application: FastAPI, services: _Services, page: str) -> None:
    """Registra las rutas de la API.

    :param application: Aplicación FastAPI.
    :type application: fastapi.FastAPI
    :param services: Dependencias de la aplicación.
    :type services: _Services
    :param page: HTML de la página web.
    :type page: str
    """
    ask_request = _build_request_model(services.settings)
    require_client = _build_client_dependency(services)
    denied = {
        401: {"description": "Sin clave o con una clave inválida"},
        429: {"description": "Límite de peticiones por minuto superado"},
    }

    @application.get("/", response_class=HTMLResponse)
    async def home() -> str:
        """Sirve la página web."""
        return page

    @application.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        """Informa el estado y el pid del proceso."""
        return HealthResponse(status="ok", pid=os.getpid())

    @application.get(
        "/metrics", dependencies=[Depends(require_client)], responses=denied
    )
    async def metrics() -> Dict[str, Any]:
        """Métricas de este proceso, sin ``request_id`` ni texto."""
        return {"pid": os.getpid(), **services.metrics.snapshot()}

    @application.post(
        "/ask",
        response_model=AskResponse,
        responses={
            400: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
            502: {"model": ErrorResponse},
            **denied,
        },
    )
    async def ask(
        payload: ask_request,  # type: ignore[valid-type]
        request: Request,
        client: str = Depends(require_client),
    ) -> Any:
        """Responde una pregunta sin guardar nada entre peticiones."""
        request_id = request.state.request_id
        observer = RequestObserver(
            request_id, services.logger, services.tracer, client=client
        )
        history = [message.model_dump() for message in payload.history]
        try:
            result = await services.supervisor.answer(
                payload.question, history, observer
            )
        except PolicyViolationError as error:
            observer.audit("policy_block", "blocked", category=error.category)
            return _error_response(400, POLICY_BLOCKED_DETAIL, request_id)
        except ModelUnavailableError as error:
            services.record_error(request_id, error)
            return _error_response(502, MODEL_UNAVAILABLE_DETAIL, request_id)
        services.metrics.record_usage(
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            model_calls=result.model_calls,
            cost_by_model=result.cost_by_model,
            route=result.route,
        )
        return AskResponse(
            answer=result.answer,
            steps=result.steps,
            tools_used=result.tools_used,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            model_calls=result.model_calls,
            review=ReviewInfo(
                status=result.review_status, issue_count=result.issue_count
            ),
            redactions=list(result.redactions),
            request_id=request_id,
            model=result.model,
            route=result.route,
            cached_calls=result.cached_calls,
            cost_usd=result.cost_usd,
        )


def _lifespan(http_client: Optional[httpx.AsyncClient]) -> Lifespan:
    """Ciclo de vida que cierra el cliente HTTP creado por ``create_app``.

    :param http_client: Cliente propio de la app, o ``None`` si no creó uno
        (los modelos inyectados los cierra quien los creó).
    :type http_client: httpx.AsyncClient or None
    :return: Función de ciclo de vida para FastAPI.
    :rtype: Callable
    """

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Atiende mientras la app vive y al apagar cierra el cliente."""
        del application
        try:
            yield
        finally:
            if http_client is not None:
                await http_client.aclose()

    return lifespan


def create_app(  # pylint: disable=too-many-arguments,too-many-locals
    settings: Optional[Settings] = None,
    model: Optional[LanguageModel] = None,
    directory: Optional[EmployeeDirectory] = None,
    *,
    clock: Optional[Clock] = None,
    log_sink: Optional[LogSink] = None,
    trace_client_factory: Optional[ClientFactory] = None,
) -> FastAPI:
    """Arma la aplicación FastAPI con sus dependencias.

    Las dependencias que falten se construyen desde el entorno.

    :param settings: Configuración; por omisión ``load_settings()``.
    :type settings: Settings or None
    :param model: Modelo de lenguaje; por omisión ``build_model``.
    :type model: LanguageModel or None
    :param directory: Directorio de empleados; por omisión se carga de
        ``settings.employees_path``.
    :type directory: EmployeeDirectory or None
    :param clock: Reloj; por omisión ``SystemClock``.
    :type clock: Clock or None
    :param log_sink: Recibe cada línea JSON del log; por omisión la salida
        estándar.
    :type log_sink: Callable[[str], None] or None
    :param trace_client_factory: Fábrica de clientes de LangSmith; por omisión
        ``langsmith.Client`` (solo se usa con trazas encendidas y clave).
    :type trace_client_factory: Callable or None
    :return: La aplicación lista para servir.
    :rtype: fastapi.FastAPI
    :raises ValueError: Si la configuración o los datos son inválidos, o si
        ``MODEL_SMALL`` o ``MODEL_LARGE`` no tienen precio.
    """
    settings = settings or load_settings()
    clock = clock or SystemClock()
    directory = directory or EmployeeDirectory(settings.employees_path)
    prices = load_prices(settings.prices_path)
    require_configured_prices(prices, settings)
    http_client = None
    if model is None:
        if settings.model_provider == "gateway":
            http_client = httpx.AsyncClient(timeout=settings.model_timeout_seconds)
        model = build_model(settings, directory, http_client)
    logger = JsonLogger(service=settings.service_name, clock=clock, sink=log_sink)
    services = _Services(
        settings=settings,
        supervisor=Supervisor(
            settings=settings,
            model=model,
            directory=directory,
            prices=prices,
            monotonic=clock.monotonic,
        ),
        clock=clock,
        logger=logger,
        tracer=build_tracer(settings, logger, trace_client_factory),
        metrics=Metrics(slo_p95_ms=settings.slo_p95_ms),
        rate_limiter=RateLimiter(
            limit_per_minute=settings.rate_limit_per_minute,
            monotonic=clock.monotonic,
        ),
    )
    application = FastAPI(title="HR Assistant", lifespan=_lifespan(http_client))
    _add_request_middleware(application, services)
    _add_routes(application, services, INDEX_PATH.read_text(encoding="utf-8"))
    return application


app = create_app()
