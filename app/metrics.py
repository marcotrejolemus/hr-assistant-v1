"""Agregador de métricas del proceso para ``GET /metrics``.

Es estado de instancia creado en ``create_app`` (nunca global, ADR 0001) y
protegido con un lock. Solo guarda contadores y una ventana acotada de
latencias; nunca ``request_id``, clientes ni texto. Las etiquetas de
``errors_by_type`` son nombres de clase de error (conjunto cerrado).
"""

import threading
from collections import Counter, deque
from typing import Any, Deque, Dict, Mapping, Optional, Sequence

DEFAULT_WINDOW_SIZE = 1000
SERVER_ERROR_STATUS = 500
COST_BILLED_NOT_AVAILABLE = "not_available"


def nearest_rank_percentile(values: Sequence[float], percent: int) -> float:
    """Calcula un percentil por rango más cercano.

    :param values: Valores observados.
    :type values: Sequence[float]
    :param percent: Percentil entre 1 y 100.
    :type percent: int
    :return: El valor del percentil; ``0`` si no hay valores.
    :rtype: float
    """
    if not values:
        return 0
    ordered = sorted(values)
    rank = -(-percent * len(ordered) // 100)
    return ordered[max(rank, 1) - 1]


class Metrics:
    """Contadores de peticiones, latencias, tokens y errores de este proceso.

    :param slo_p95_ms: Meta de latencia p95 en milisegundos.
    :type slo_p95_ms: int
    :param window_size: Número de latencias recientes que se conservan.
    :type window_size: int
    :raises ValueError: Si ``window_size`` es menor que uno.
    """

    def __init__(self, *, slo_p95_ms: int, window_size: int = DEFAULT_WINDOW_SIZE):
        if window_size < 1:
            raise ValueError("window_size must be at least 1")
        self._slo_p95_ms = slo_p95_ms
        self._lock = threading.Lock()
        self._latencies: Deque[float] = deque(maxlen=window_size)
        self._counts: Counter = Counter()
        self._errors_by_type: Counter = Counter()
        self._cost_by_model: Counter = Counter()
        self._requests_by_route: Counter = Counter()

    def record_request(self, status: int, latency_ms: float) -> None:
        """Registra una petición terminada.

        :param status: Código HTTP de la respuesta.
        :type status: int
        :param latency_ms: Latencia de la petición en milisegundos.
        :type latency_ms: float
        """
        with self._lock:
            self._counts["requests"] += 1
            if status >= SERVER_ERROR_STATUS:
                self._counts["server_errors"] += 1
            self._latencies.append(latency_ms)

    def record_usage(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        model_calls: int,
        cost_by_model: Optional[Mapping[str, float]] = None,
        route: Optional[str] = None,
    ) -> None:
        """Suma el consumo de una petición atendida.

        :param input_tokens: Tokens de entrada de la petición.
        :type input_tokens: int
        :param output_tokens: Tokens de salida de la petición.
        :type output_tokens: int
        :param model_calls: Llamadas al modelo de la petición.
        :type model_calls: int
        :param cost_by_model: Costo estimado en USD por modelo (conjunto
            cerrado de nombres de modelo).
        :type cost_by_model: Mapping[str, float] or None
        :param route: Motivo del enrutador (conjunto cerrado).
        :type route: str or None
        """
        with self._lock:
            self._counts["input_tokens"] += input_tokens
            self._counts["output_tokens"] += output_tokens
            self._counts["model_calls"] += model_calls
            for model, cost in (cost_by_model or {}).items():
                self._cost_by_model[model] += cost
            if route is not None:
                self._requests_by_route[route] += 1

    def record_error(self, error_type: str) -> None:
        """Cuenta un error por su tipo (nombre de clase, nunca el mensaje).

        :param error_type: Nombre de la clase del error.
        :type error_type: str
        """
        with self._lock:
            self._errors_by_type[error_type] += 1

    def snapshot(self) -> Dict[str, Any]:
        """Devuelve una copia consistente de las métricas.

        :return: ``requests``, ``error_rate``, ``latency_ms``, ``tokens``,
            ``slo``, ``model_calls``, ``errors_by_type``, ``cost_usd``,
            ``cost_estimated_usd_by_model``, ``requests_by_route`` y
            ``cost_billed`` (siempre ``not_available``).
        :rtype: dict
        """
        with self._lock:
            latencies = list(self._latencies)
            counts = dict(self._counts)
            errors = dict(self._errors_by_type)
            cost_by_model = dict(self._cost_by_model)
            routes = dict(self._requests_by_route)
        requests = counts.get("requests", 0)
        server_errors = counts.get("server_errors", 0)
        p95 = nearest_rank_percentile(latencies, 95)
        return {
            "requests": requests,
            "error_rate": round(server_errors / requests, 4) if requests else 0.0,
            "latency_ms": {
                "p50": nearest_rank_percentile(latencies, 50),
                "p95": p95,
            },
            "tokens": {
                "input": counts.get("input_tokens", 0),
                "output": counts.get("output_tokens", 0),
            },
            "slo": {
                "p95_ms_target": self._slo_p95_ms,
                "met": p95 < self._slo_p95_ms,
            },
            "model_calls": counts.get("model_calls", 0),
            "errors_by_type": errors,
            "cost_usd": sum(cost_by_model.values()),
            "cost_estimated_usd_by_model": cost_by_model,
            "requests_by_route": routes,
            # El costo facturado solo lo conoce Cloudflare: se declara así.
            "cost_billed": COST_BILLED_NOT_AVAILABLE,
        }
