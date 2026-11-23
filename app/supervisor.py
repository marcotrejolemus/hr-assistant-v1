"""Supervisor determinista: orquesta guardas, Specialist y Reviewer (ADR 0004).

Orden fijo por petición: Input Guard -> enrutador de costo -> Directory
Specialist -> Reviewer -> Output Guard. Cada petición crea su propio presupuesto
(llamadas, tokens de entrada, tiempo y costo) y su propio observador (log de
etapas, auditoría y trazas); no hay estado compartido entre peticiones.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from app.agent import AgentResult, DirectorySpecialistAgent
from app.config import Settings
from app.costs import PriceTable
from app.directory import EmployeeDirectory
from app.guards import GuardedInput, InputGuard, OutputGuard, merge_types
from app.llm import (
    CallBudgetExceededError,
    CallOptions,
    Completion,
    LanguageModel,
    Message,
    ModelUnavailableError,
    estimate_input_tokens,
)
from app.observability import RequestObserver
from app.reviewer import ReviewerAgent, ReviewOutcome
from app.router import RouteDecision, apply_history_window, route_question

Monotonic = Callable[[], float]


@dataclass(frozen=True)
class RequestLimits:
    """Límites de una petición.

    :param max_calls: Tope total de llamadas al modelo.
    :type max_calls: int
    :param input_token_budget: Suma máxima de tokens de entrada.
    :type input_token_budget: int
    :param model_timeout: Tiempo máximo de una llamada, en segundos.
    :type model_timeout: float
    :param request_timeout: Tiempo máximo de la petición, en segundos.
    :type request_timeout: float
    """

    max_calls: int
    input_token_budget: int
    model_timeout: float
    request_timeout: float

    @classmethod
    def from_settings(cls, settings: Settings) -> "RequestLimits":
        """Toma los límites de la configuración.

        :param settings: Configuración validada.
        :type settings: Settings
        :return: Límites de una petición.
        :rtype: RequestLimits
        """
        return cls(
            max_calls=settings.max_model_calls_per_request,
            input_token_budget=settings.request_input_token_budget,
            model_timeout=settings.model_timeout_seconds,
            request_timeout=settings.request_timeout_seconds,
        )


class ObservedModel:  # pylint: disable=too-few-public-methods
    """Envuelve el modelo real y deja una corrida ``llm`` por llamada.

    :param model: Modelo real.
    :type model: LanguageModel
    :param observer: Observador de la petición.
    :type observer: RequestObserver
    """

    def __init__(self, model: LanguageModel, observer: RequestObserver):
        self._model = model
        self._observer = observer

    async def complete(
        self, messages: List[Message], *, model: str, max_tokens: int
    ) -> Completion:
        """Llama al modelo real dentro de la corrida ``llm``.

        :param messages: Mensajes con ``role`` y ``content`` (ya redactados).
        :type messages: list[dict]
        :param model: Nombre del modelo.
        :type model: str
        :param max_tokens: Tope de tokens de salida.
        :type max_tokens: int
        :return: La respuesta del modelo.
        :rtype: Completion
        """
        with self._observer.llm_call(model, messages) as outputs:
            completion = await self._model.complete(
                messages, model=model, max_tokens=max_tokens
            )
            outputs.update(
                text=completion.text,
                input_tokens=completion.input_tokens,
                output_tokens=completion.output_tokens,
            )
        return completion


class BudgetedModel:  # pylint: disable=too-many-instance-attributes
    """Modelo de una sola petición que aplica presupuestos y tiempos.

    Cada llamada usa ``asyncio.wait_for`` con el menor entre el tiempo por
    llamada y el tiempo restante de la petición. Lleva la cuenta de llamadas y
    tokens de todos los agentes de la petición, y el costo estimado por modelo.

    :param model: Modelo real (en el Supervisor, ya observado).
    :type model: LanguageModel
    :param limits: Límites de la petición.
    :type limits: RequestLimits
    :param monotonic: Reloj monótono inyectado, en segundos.
    :type monotonic: Callable[[], float]
    :param prices: Tabla de precios; una llamada cacheada no cuesta.
    :type prices: PriceTable
    """

    def __init__(
        self,
        model: LanguageModel,
        limits: RequestLimits,
        monotonic: Monotonic,
        prices: PriceTable,
    ):
        self._model = model
        self._limits = limits
        self._monotonic = monotonic
        self._prices = prices
        self._deadline = monotonic() + limits.request_timeout
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cached_calls = 0
        self.cost_by_model: Dict[str, float] = {}

    @property
    def cost_usd(self) -> float:
        """Costo estimado de todas las llamadas de la petición.

        :return: Suma en USD.
        :rtype: float
        """
        return sum(self.cost_by_model.values())

    def _charge(self, model: str, completion: Completion) -> None:
        """Suma el costo de una llamada; una llamada cacheada no cuesta.

        :param model: Nombre del modelo pedido.
        :type model: str
        :param completion: Respuesta con sus tokens.
        :type completion: Completion
        """
        if completion.cached:
            self.cached_calls += 1
            return
        cost = self._prices.cost(
            model,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
        )
        self.cost_by_model[model] = self.cost_by_model.get(model, 0.0) + cost

    def _check_budget(self, messages: Sequence[Message]) -> None:
        """Comprueba que la siguiente llamada cabe en el presupuesto.

        :param messages: Mensajes de la llamada.
        :type messages: Sequence[dict]
        :raises CallBudgetExceededError: Si rebasa llamadas o tokens de entrada.
        """
        if self.calls >= self._limits.max_calls:
            raise CallBudgetExceededError("model call budget exhausted")
        estimate = estimate_input_tokens(messages)
        if self.input_tokens + estimate > self._limits.input_token_budget:
            raise CallBudgetExceededError("input token budget exhausted")

    async def complete(
        self, messages: List[Message], *, model: str, max_tokens: int
    ) -> Completion:
        """Llama al modelo real dentro de los presupuestos de la petición.

        :param messages: Mensajes con ``role`` y ``content``.
        :type messages: list[dict]
        :param model: Nombre del modelo.
        :type model: str
        :param max_tokens: Tope de tokens de salida.
        :type max_tokens: int
        :return: La respuesta del modelo.
        :rtype: Completion
        :raises CallBudgetExceededError: Si la llamada rebasa el presupuesto.
        :raises ModelUnavailableError: Si el proveedor falla o se agota el tiempo.
        """
        self._check_budget(messages)
        timeout = min(self._limits.model_timeout, self._deadline - self._monotonic())
        if timeout <= 0:
            raise ModelUnavailableError("request time exhausted")
        self.calls += 1
        try:
            completion = await asyncio.wait_for(
                self._model.complete(messages, model=model, max_tokens=max_tokens),
                timeout=timeout,
            )
        except asyncio.TimeoutError as error:
            raise ModelUnavailableError("model call timed out") from error
        self.input_tokens += completion.input_tokens
        self.output_tokens += completion.output_tokens
        self._charge(model, completion)
        return completion


@dataclass(frozen=True)
class SupervisorResult:  # pylint: disable=too-many-instance-attributes
    """Resultado final de una petición.

    :param answer: Respuesta que decidió el Output Guard.
    :type answer: str
    :param review_status: ``approved``, ``rejected`` o ``unavailable``.
    :type review_status: str
    :param issue_count: Problemas reportados por el Reviewer.
    :type issue_count: int
    :param redactions: Tipos de PII redactados en entrada y salida.
    :type redactions: tuple[str, ...]
    :param tools_used: Herramientas ejecutadas.
    :type tools_used: list[str]
    :param steps: Llamadas del Directory Specialist.
    :type steps: int
    :param model_calls: Llamadas al modelo de todos los agentes.
    :type model_calls: int
    :param input_tokens: Tokens de entrada de todas las llamadas.
    :type input_tokens: int
    :param output_tokens: Tokens de salida de todas las llamadas.
    :type output_tokens: int
    :param model: Modelo que eligió el enrutador para el Specialist.
    :type model: str
    :param route: Motivo del enrutador.
    :type route: str
    :param cached_calls: Llamadas servidas desde la caché del gateway.
    :type cached_calls: int
    :param cost_by_model: Costo estimado en USD por modelo.
    :type cost_by_model: dict[str, float]
    """

    answer: str
    review_status: str
    issue_count: int
    redactions: Tuple[str, ...]
    tools_used: List[str]
    steps: int
    model_calls: int
    input_tokens: int
    output_tokens: int
    model: str
    route: str
    cached_calls: int
    cost_by_model: Dict[str, float]

    @property
    def cost_usd(self) -> float:
        """Costo estimado de todas las llamadas (Specialist y Reviewer).

        :return: Suma en USD.
        :rtype: float
        """
        return sum(self.cost_by_model.values())


class Supervisor:
    """Orquestación determinista de una pregunta (no es un agente LLM).

    :param settings: Configuración validada.
    :type settings: Settings
    :param model: Modelo de lenguaje compartido (sin estado por petición).
    :type model: LanguageModel
    :param directory: Directorio de empleados de solo lectura.
    :type directory: EmployeeDirectory
    :param prices: Tabla de precios por modelo.
    :type prices: PriceTable
    :param monotonic: Reloj monótono; por omisión ``time.monotonic``.
    :type monotonic: Callable[[], float] or None
    """

    def __init__(
        self,
        settings: Settings,
        model: LanguageModel,
        directory: EmployeeDirectory,
        prices: PriceTable,
        monotonic: Optional[Monotonic] = None,
    ):
        self._settings = settings
        self._model = model
        self._directory = directory
        self._prices = prices
        self._monotonic = monotonic or time.monotonic
        self._input_guard = InputGuard()
        self._output_guard = OutputGuard(max_answer_chars=settings.max_answer_chars)

    async def answer(
        self,
        question: str,
        history: Sequence[Dict[str, str]],
        observer: RequestObserver,
    ) -> SupervisorResult:
        """Atiende una pregunta de principio a fin.

        Cada etapa queda en el log (evento ``stage``) y como corrida hija de
        ``supervisor`` en la traza. Al terminar escribe ``agent_run``.

        :param question: Pregunta original del cliente.
        :type question: str
        :param history: Historial enviado por el cliente.
        :type history: Sequence[dict]
        :param observer: Observador de esta petición.
        :type observer: RequestObserver
        :return: Respuesta final y datos de la ejecución.
        :rtype: SupervisorResult
        :raises app.guards.PolicyViolationError: Si hay inyección o exfiltración.
        :raises ModelUnavailableError: Si el Specialist no obtiene respuesta del
            proveedor (falla o tiempo agotado).
        """
        summary = {"question_chars": len(question), "history_messages": len(history)}
        with observer.span("supervisor", inputs=summary):
            with observer.stage("input_guard"):
                guarded = self._input_guard.check(question, history)
            if guarded.redactions:
                # Solo los tipos de PII, nunca los valores.
                observer.audit(
                    "pii_redacted", "redacted", types=list(guarded.redactions)
                )
            route = route_question(guarded.question, self._settings)
            budget = BudgetedModel(
                ObservedModel(self._model, observer),
                RequestLimits.from_settings(self._settings),
                self._monotonic,
                self._prices,
            )
            draft, review = await self._run_agents(guarded, route, budget, observer)
            with observer.stage("output_guard"):
                decision = self._output_guard.decide(draft.answer, review.status)
            self._audit_decisions(observer, review.status, decision.blocked)
        result = SupervisorResult(
            answer=decision.answer,
            steps=draft.steps,
            tools_used=list(draft.tools_used),
            input_tokens=budget.input_tokens,
            output_tokens=budget.output_tokens,
            model_calls=budget.calls,
            review_status=review.status,
            issue_count=review.issue_count,
            redactions=merge_types(guarded.redactions, decision.redactions),
            model=route.model,
            route=route.reason,
            cached_calls=budget.cached_calls,
            cost_by_model=dict(budget.cost_by_model),
        )
        observer.agent_run(
            **summary,
            steps=result.steps,
            tools=result.tools_used,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            stopped=draft.stopped,
            model_calls=result.model_calls,
            review_status=result.review_status,
            model=result.model,
            route=result.route,
            cached_calls=result.cached_calls,
            cost_usd=result.cost_usd,
        )
        return result

    @staticmethod
    def _audit_decisions(
        observer: RequestObserver, review_status: str, blocked: bool
    ) -> None:
        """Audita el rechazo del Reviewer y el bloqueo del Output Guard.

        :param observer: Observador de esta petición.
        :type observer: RequestObserver
        :param review_status: ``approved``, ``rejected`` o ``unavailable``.
        :type review_status: str
        :param blocked: ``True`` si salió la respuesta segura fija.
        :type blocked: bool
        """
        if review_status == "rejected":
            observer.audit("review_verdict", "rejected")
        if blocked:
            observer.audit("output_blocked", "safe_answer")

    async def _run_agents(
        self,
        guarded: GuardedInput,
        route: RouteDecision,
        budget: BudgetedModel,
        observer: RequestObserver,
    ) -> Tuple[AgentResult, ReviewOutcome]:
        """Corre el Directory Specialist y luego el Reviewer, cada uno en su etapa.

        El Specialist usa el modelo del enrutador y solo los últimos
        ``HISTORY_WINDOW`` mensajes; el Reviewer usa siempre ``MODEL_SMALL``.

        :param guarded: Entrada ya revisada y redactada.
        :type guarded: GuardedInput
        :param route: Decisión del enrutador.
        :type route: RouteDecision
        :param budget: Modelo con los presupuestos de la petición.
        :type budget: BudgetedModel
        :param observer: Observador de esta petición.
        :type observer: RequestObserver
        :return: Borrador del Specialist y resultado de la revisión.
        :rtype: tuple[AgentResult, ReviewOutcome]
        :raises ModelUnavailableError: Si el Specialist no obtiene respuesta.
        """
        settings = self._settings
        specialist = DirectorySpecialistAgent(
            model=budget,
            directory=self._directory,
            max_steps=settings.agent_max_steps,
            options=CallOptions(route.model, settings.model_max_tokens),
            observe_tool=observer.tool_call,
            observe_denied=observer.tool_denied,
        )
        history = apply_history_window(guarded.history, settings.history_window)
        with observer.stage("directory_specialist"):
            draft = await specialist.run(guarded.question, history)
        reviewer = ReviewerAgent(
            budget,
            CallOptions(settings.model_small, settings.model_max_tokens),
            settings.reviewer_max_calls,
        )
        with observer.stage("reviewer_agent"):
            review = await reviewer.review(
                guarded.question, draft.answer, draft.evidence
            )
        return draft, review
