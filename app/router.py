"""Enrutador de costo determinista y ventana de historial (``spec/03``, ADR 0006).

Es una regla en código, no otro modelo: decide qué modelo atiende al Directory
Specialist y por qué. No cobra nada; el costo lo calcula ``app.costs``.
"""

from dataclasses import dataclass
from typing import List, Sequence

from app.config import Settings
from app.llm import Message

COMPLEX_KEYWORDS = ("compara", "resume", "explica", "por qué", "analiza", "todos")
REASON_ROUTING_DISABLED = "routing_disabled"
REASON_LONG_QUESTION = "long_question"
REASON_COMPLEX_KEYWORD = "complex_keyword"
REASON_SIMPLE = "simple"


@dataclass(frozen=True)
class RouteDecision:
    """Modelo elegido para el Specialist y el motivo (conjunto cerrado).

    :param model: Nombre del modelo.
    :type model: str
    :param reason: ``routing_disabled``, ``long_question``, ``complex_keyword``
        o ``simple``.
    :type reason: str
    """

    model: str
    reason: str


def route_question(question: str, settings: Settings) -> RouteDecision:
    """Elige ``MODEL_LARGE`` o ``MODEL_SMALL`` para una pregunta.

    :param question: Pregunta (ya redactada por el Input Guard).
    :type question: str
    :param settings: Configuración con ``routing`` y ``router_max_chars``.
    :type settings: Settings
    :return: Modelo y motivo de la decisión.
    :rtype: RouteDecision
    """
    if not settings.routing:
        return RouteDecision(settings.model_large, REASON_ROUTING_DISABLED)
    if len(question) > settings.router_max_chars:
        return RouteDecision(settings.model_large, REASON_LONG_QUESTION)
    lowered = question.casefold()
    if any(keyword in lowered for keyword in COMPLEX_KEYWORDS):
        return RouteDecision(settings.model_large, REASON_COMPLEX_KEYWORD)
    return RouteDecision(settings.model_small, REASON_SIMPLE)


def apply_history_window(history: Sequence[Message], window: int) -> List[Message]:
    """Conserva solo los últimos ``window`` mensajes del historial.

    :param history: Historial completo (ya revisado y redactado).
    :type history: Sequence[dict]
    :param window: Número de mensajes que se mandan al modelo (>= 1).
    :type window: int
    :return: Los últimos ``window`` mensajes, en orden.
    :rtype: list[dict]
    """
    return list(history[-window:])
