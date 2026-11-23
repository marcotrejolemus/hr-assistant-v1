"""Observabilidad: log JSON, auditoría de herramientas, etapas y trazas LangSmith.

- ``JsonLogger`` escribe una línea JSON por evento con ``ts`` (ISO 8601 UTC),
  ``service``, ``event`` y ``request_id``.
- ``Tracer`` manda corridas padre/hijo a LangSmith con el cliente inyectado. Es
  a prueba de fallos: toda excepción del cliente se registra como
  ``telemetry_error`` (solo el nombre de la clase) y nunca rompe la respuesta.
- ``RequestObserver`` existe una vez por petición: une log, auditoría y trazas
  de las etapas del Supervisor sin estado compartido entre peticiones.

Nunca se registra el texto de preguntas, historial, respuestas ni salidas de
herramientas, ni la clave de LangSmith.
"""

import importlib
import json
import re
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timezone
from typing import Any, Callable, Dict, Iterator, List, Optional

from app.clock import Clock
from app.config import Settings
from app.pii import redact_pii

LogSink = Callable[[str], None]
ClientFactory = Callable[..., Any]

REQUEST_ID_SHAPE = re.compile(r"[A-Za-z0-9._:\-]{1,128}")
DOTTED_ORDER_TIME = "%Y%m%dT%H%M%S%fZ"


def _write_stdout(line: str) -> None:
    """Destino por omisión del log: la salida estándar, una línea por evento.

    :param line: Línea JSON sin saltos.
    :type line: str
    """
    print(line, flush=True)


def accept_request_id(candidate: Optional[str]) -> str:
    """Respeta el ``X-Request-ID`` del cliente o genera un UUID.

    Solo se acepta un id corto con caracteres seguros (letras, dígitos y
    ``._:-``, hasta 128); cualquier otro valor se reemplaza por un UUID nuevo.

    :param candidate: Valor del encabezado, si vino.
    :type candidate: str or None
    :return: El id de la petición.
    :rtype: str
    """
    if candidate and REQUEST_ID_SHAPE.fullmatch(candidate):
        return candidate
    return str(uuid.uuid4())


class JsonLogger:
    """Logger estructurado: una línea JSON por evento.

    :param service: Valor del campo ``service``.
    :type service: str
    :param clock: Reloj inyectado que da ``ts``.
    :type clock: Clock
    :param sink: Destino de cada línea; por omisión la salida estándar.
    :type sink: Callable[[str], None] or None
    """

    def __init__(self, *, service: str, clock: Clock, sink: Optional[LogSink] = None):
        self._service = service
        self._clock = clock
        self._sink = sink or _write_stdout

    @property
    def clock(self) -> Clock:
        """Reloj del logger, compartido con las trazas.

        :return: El reloj inyectado.
        :rtype: Clock
        """
        return self._clock

    def log(self, event: str, request_id: Optional[str], **fields: Any) -> None:
        """Escribe un evento.

        :param event: Nombre del evento (``request``, ``audit``...).
        :type event: str
        :param request_id: Id de la petición, o ``None`` fuera de una petición.
        :type request_id: str or None
        :param fields: Campos propios del evento (nunca texto privado).
        :type fields: Any
        """
        record = {
            "ts": self._clock.now().astimezone(timezone.utc).isoformat(),
            "service": self._service,
            "event": event,
            "request_id": request_id,
            **fields,
        }
        self._sink(json.dumps(record, ensure_ascii=False, default=str))


@dataclass
class _TraceState:
    """Estado de una traza (una petición): si el cliente ya falló."""

    failed: bool = False


@dataclass
class Span:
    """Corrida abierta en LangSmith.

    :param run_id: Id de la corrida.
    :type run_id: uuid.UUID
    :param trace_id: Id de la corrida raíz.
    :type trace_id: uuid.UUID
    :param dotted_order: Orden jerárquico que exige LangSmith.
    :type dotted_order: str
    :param request_id: Id de la petición, para ``telemetry_error``.
    :type request_id: str
    :param state: Estado compartido por todas las corridas de la petición.
    :type state: _TraceState
    """

    run_id: uuid.UUID
    trace_id: uuid.UUID
    dotted_order: str
    request_id: str
    state: _TraceState = field(default_factory=_TraceState)


def langsmith_client_factory(**kwargs: Any) -> Any:
    """Fábrica real: crea ``langsmith.Client`` solo cuando se pide.

    La importación es dinámica a propósito: ``langsmith`` es opcional y el
    producto debe arrancar sin él mientras las trazas estén apagadas.

    :param kwargs: ``api_key``, ``hide_inputs`` y ``hide_outputs``.
    :type kwargs: Any
    :return: Cliente de LangSmith.
    :rtype: langsmith.Client
    :raises ImportError: Si ``langsmith`` no está instalado.
    """
    module = importlib.import_module("langsmith")
    return module.Client(**kwargs)


class Tracer:
    """Trazas padre/hijo en LangSmith, a prueba de fallos.

    Con ``client=None`` está apagado y no hace nada. Las entradas y salidas se
    vacían aquí mismo si ``hide_inputs``/``hide_outputs`` están activos, además
    de pasar esas banderas al cliente.

    :param client: Cliente de LangSmith o ``None``.
    :type client: Any
    :param logger: Logger para ``telemetry_error``.
    :type logger: JsonLogger
    :param project: Proyecto de LangSmith.
    :type project: str
    :param hidden: Par ``(hide_inputs, hide_outputs)``.
    :type hidden: tuple[bool, bool]
    """

    def __init__(
        self,
        client: Any,
        logger: JsonLogger,
        project: str,
        hidden: tuple = (True, True),
    ):
        self._client = client
        self._logger = logger
        self._project = project
        self._hide_inputs, self._hide_outputs = hidden

    @property
    def enabled(self) -> bool:
        """Indica si hay cliente de trazas.

        :return: ``True`` si las trazas están encendidas.
        :rtype: bool
        """
        return self._client is not None

    def _call(self, span: Span, method: str, **kwargs: Any) -> None:
        """Llama al cliente sin dejar escapar ninguna excepción.

        Tras el primer fallo de una petición ya no se insiste en esa traza.

        :param span: Corrida afectada.
        :type span: Span
        :param method: ``create_run`` o ``update_run``.
        :type method: str
        :param kwargs: Argumentos del método.
        :type kwargs: Any
        """
        if span.state.failed:
            return
        try:
            getattr(self._client, method)(**kwargs)
        except Exception as error:  # pylint: disable=broad-exception-caught
            # La telemetría nunca rompe la respuesta: solo se anota el tipo.
            span.state.failed = True
            self._logger.log(
                "telemetry_error", span.request_id, error_type=type(error).__name__
            )

    def start(  # pylint: disable=too-many-arguments
        self,
        request_id: str,
        name: str,
        *,
        run_type: str = "chain",
        parent: Optional[Span] = None,
        inputs: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Span]:
        """Abre una corrida, hija de ``parent`` si se da.

        :param request_id: Id de la petición (va en los metadatos).
        :type request_id: str
        :param name: Nombre de la corrida (``supervisor``, ``llm``...).
        :type name: str
        :param run_type: Tipo de LangSmith (``chain``, ``llm``, ``tool``).
        :type run_type: str
        :param parent: Corrida padre.
        :type parent: Span or None
        :param inputs: Entradas ya redactadas.
        :type inputs: dict or None
        :param metadata: Metadatos de conjunto cerrado.
        :type metadata: dict or None
        :return: La corrida abierta, o ``None`` si el tracer está apagado.
        :rtype: Span or None
        """
        if not self.enabled:
            return None
        started = self._logger.clock.now()
        run_id = uuid.uuid4()
        stamp = f"{started.strftime(DOTTED_ORDER_TIME)}{run_id}"
        if parent is None:
            span = Span(run_id, run_id, stamp, request_id)
        else:
            span = Span(
                run_id,
                parent.trace_id,
                f"{parent.dotted_order}.{stamp}",
                request_id,
                parent.state,
            )
        self._call(
            span,
            "create_run",
            name=name,
            run_type=run_type,
            inputs={} if self._hide_inputs else dict(inputs or {}),
            project_name=self._project,
            id=run_id,
            trace_id=span.trace_id,
            dotted_order=span.dotted_order,
            parent_run_id=parent.run_id if parent else None,
            start_time=started,
            extra={"metadata": {"request_id": request_id, **(metadata or {})}},
        )
        return span

    def end(
        self,
        span: Optional[Span],
        outputs: Optional[Dict[str, Any]] = None,
        error_type: Optional[str] = None,
    ) -> None:
        """Cierra una corrida con sus salidas o con el tipo de error.

        :param span: Corrida abierta (``None`` si el tracer está apagado).
        :type span: Span or None
        :param outputs: Salidas ya redactadas.
        :type outputs: dict or None
        :param error_type: Nombre de la clase del error, si hubo.
        :type error_type: str or None
        """
        if span is None:
            return
        self._call(
            span,
            "update_run",
            run_id=span.run_id,
            trace_id=span.trace_id,
            dotted_order=span.dotted_order,
            end_time=self._logger.clock.now(),
            outputs={} if self._hide_outputs else dict(outputs or {}),
            error=error_type,
        )


def build_tracer(
    settings: Settings,
    logger: JsonLogger,
    client_factory: Optional[ClientFactory] = None,
) -> Tracer:
    """Crea el tracer; solo llama a la fábrica con bandera y clave.

    Sin ``LANGSMITH_TRACING=true`` y ``LANGSMITH_API_KEY`` no se crea el
    cliente, así que no hay conexiones. Si la fábrica falla (por ejemplo, sin
    ``langsmith`` instalado), se registra ``telemetry_error`` y se apaga.

    :param settings: Configuración validada.
    :type settings: Settings
    :param logger: Logger del producto.
    :type logger: JsonLogger
    :param client_factory: Fábrica de clientes; por omisión
        ``langsmith_client_factory``.
    :type client_factory: Callable or None
    :return: El tracer (apagado o encendido).
    :rtype: Tracer
    """
    hidden = (settings.hide_inputs, settings.hide_outputs)
    project = settings.langsmith_project
    if not (settings.langsmith_tracing and settings.langsmith_api_key):
        return Tracer(None, logger, project, hidden)
    factory = client_factory or langsmith_client_factory
    try:
        client = factory(
            api_key=settings.langsmith_api_key,
            hide_inputs=settings.hide_inputs,
            hide_outputs=settings.hide_outputs,
        )
    except Exception as error:  # pylint: disable=broad-exception-caught
        # Sin cliente el producto sigue igual; solo se anota el tipo.
        logger.log("telemetry_error", None, error_type=type(error).__name__)
        return Tracer(None, logger, project, hidden)
    return Tracer(client, logger, project, hidden)


class RequestObserver:
    """Observación de una sola petición: etapas, llamadas, tools y resumen.

    Guarda la pila de corridas abiertas de esta petición (variable de
    instancia, nunca global); dentro de una petición las etapas son
    secuenciales.

    :param request_id: Id de la petición.
    :type request_id: str
    :param logger: Logger del producto.
    :type logger: JsonLogger
    :param tracer: Tracer del producto.
    :type tracer: Tracer
    :param client: Nombre del cliente autenticado (nunca su clave).
    :type client: str or None
    """

    def __init__(
        self,
        request_id: str,
        logger: JsonLogger,
        tracer: Tracer,
        client: Optional[str] = None,
    ):
        self.request_id = request_id
        self.client = client
        self._logger = logger
        self._tracer = tracer
        self._open: List[Optional[Span]] = []

    def audit(self, action: str, outcome: str, **fields: Any) -> None:
        """Escribe un evento ``audit`` con el cliente (nunca claves ni texto).

        :param action: Acción auditada (``policy_block``, ``pii_redacted``...).
        :type action: str
        :param outcome: Resultado de la decisión.
        :type outcome: str
        :param fields: Campos de conjunto cerrado (categoría, tipos...).
        :type fields: Any
        """
        self._logger.log(
            "audit",
            self.request_id,
            client=self.client,
            action=action,
            outcome=outcome,
            **fields,
        )

    @contextmanager
    def span(
        self,
        name: str,
        *,
        run_type: str = "chain",
        inputs: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Abre una corrida hija de la actual; entrega un dict de salidas.

        :param name: Nombre de la corrida.
        :type name: str
        :param run_type: Tipo de LangSmith.
        :type run_type: str
        :param inputs: Entradas ya redactadas.
        :type inputs: dict or None
        :param metadata: Metadatos de conjunto cerrado.
        :type metadata: dict or None
        :return: Diccionario que el llamador llena con las salidas.
        :rtype: Iterator[dict]
        """
        parent = self._open[-1] if self._open else None
        span = self._tracer.start(
            self.request_id,
            name,
            run_type=run_type,
            parent=parent,
            inputs=inputs,
            metadata={"client": self.client, **(metadata or {})},
        )
        self._open.append(span)
        outputs: Dict[str, Any] = {}
        try:
            yield outputs
        except BaseException as error:
            self._tracer.end(span, error_type=type(error).__name__)
            raise
        else:
            self._tracer.end(span, outputs=outputs)
        finally:
            self._open.pop()

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        """Mide una etapa del Supervisor: evento ``stage`` y corrida.

        :param name: ``input_guard``, ``directory_specialist``,
            ``reviewer_agent`` u ``output_guard``.
        :type name: str
        :return: Nada; el bloque es la etapa.
        :rtype: Iterator[None]
        """
        clock = self._logger.clock
        started = clock.monotonic()
        fields: Dict[str, Any] = {"stage": name, "status": "ok"}
        try:
            with self.span(name):
                yield
        except BaseException as error:
            fields.update(status="error", error_type=type(error).__name__)
            raise
        finally:
            fields["duration_ms"] = round((clock.monotonic() - started) * 1000, 3)
            self._logger.log("stage", self.request_id, **fields)

    def llm_call(self, model: str, messages: List[Dict[str, str]]):
        """Corrida ``llm`` de una llamada al modelo (mensajes ya redactados).

        :param model: Nombre del modelo.
        :type model: str
        :param messages: Mensajes de la llamada.
        :type messages: list[dict]
        :return: Administrador de contexto que entrega el dict de salidas.
        :rtype: contextlib.AbstractContextManager
        """
        return self.span(
            "llm",
            run_type="llm",
            inputs={"messages": messages},
            metadata={"model": model},
        )

    @contextmanager
    def tool_call(self, name: str, args: Dict[str, str]) -> Iterator[None]:
        """Corrida ``tool:<nombre>`` y auditoría ``tool_call`` de una herramienta.

        :param name: Nombre de la herramienta.
        :type name: str
        :param args: Argumentos ya validados.
        :type args: dict
        :return: Nada; el bloque es la ejecución de la herramienta.
        :rtype: Iterator[None]
        """
        # Los argumentos ya están validados; se redactan por si traen PII.
        safe_args = {key: redact_pii(value).text for key, value in args.items()}
        outcome = "ok"
        try:
            with self.span(
                f"tool:{name}", run_type="tool", inputs={"args": safe_args}
            ):
                yield
        except BaseException:
            outcome = "error"
            raise
        finally:
            self.audit("tool_call", outcome, tool=name, args=safe_args)

    def tool_denied(self, name: str) -> None:
        """Auditoría ``tool_denied`` de una herramienta rechazada.

        :param name: Nombre permitido de la herramienta o ``unknown``; nunca
            los argumentos, que controla el modelo.
        :type name: str
        """
        self.audit("tool_denied", "denied", tool=name)

    def agent_run(self, **fields: Any) -> None:
        """Escribe el resumen ``agent_run`` (solo conteos, nunca texto).

        :param fields: ``question_chars``, ``history_messages``, ``steps``,
            ``tools``, ``input_tokens``, ``output_tokens``, ``stopped``...
        :type fields: Any
        """
        self._logger.log("agent_run", self.request_id, client=self.client, **fields)
