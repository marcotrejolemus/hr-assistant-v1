"""Guardas deterministas de entrada y de salida (ADR 0005).

El Input Guard bloquea la inyección y la exfiltración (español e inglés,
normalizado sin acentos) en la pregunta y en el historial, y redacta la PII
antes del proveedor. El Output Guard decide siempre la respuesta final.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from app.agent import SPECIALIST_MARKER
from app.llm import REVIEWER_MARKER
from app.pii import redact_pii

SAFE_ANSWER = (
    "No puedo compartir esa respuesta. Intenta con otra pregunta sobre "
    "empleados o departamentos."
)
REVIEW_REJECTED = "rejected"

# Patrones sobre texto en minúsculas y sin acentos.
_INJECTION_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\b(ignor|olvid|forget|disregard|omit|salta|skip|bypass)\w*\b"
        r".{0,60}\b(instruc|regla|rule|indicacion|prompt|polic)",
        r"\b(actua|actuar|act|behave|comportate)\s+(como|as)\b",
        r"\b(you are now|ahora eres|ahora seras|pretend|finge|fingir)\b",
        r"\b(jailbreak|developer mode|modo desarrollador|dan mode)\b",
        r"\bprompts?\b",
        r"\b(system|sistema)\s+(message|mensaje|instructions?)\b",
        r"\binstrucciones\s+(del|de)\s+sistema\b",
    )
)
_EXFILTRATION_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\bvariables?\s+(de\s+)?(entorno|ambiente)\b",
        r"\b(environment|env)\s+var",
        r"\.env\b",
        r"\bapi[\s_-]?keys?\b",
        r"\b(tokens?|secrets?|secretos?|passwords?|contrasenas?)\b",
        r"\b(credenciales?|credentials?)\b",
        r"\bclaves?\s+(de\s+)?(api|acceso|secretas?)\b",
    )
)
# Marcadores de los prompts de sistema: si salen, es una fuga del prompt.
_PROMPT_MARKERS = (SPECIALIST_MARKER, REVIEWER_MARKER)
_SECRET_OUTPUT_PATTERNS = (
    re.compile(
        r"\b(CF_API_TOKEN|CF_ACCOUNT_ID|LANGSMITH_API_KEY|API_KEYS|"
        r"SMOKE_API_KEY|E2E_API_KEY)\b"
    ),
    re.compile(r"\b[A-Z][A-Z0-9]*_(API_)?(KEY|KEYS|TOKEN|SECRET|PASSWORD)\b"),
    re.compile(r"\b(sk|pk|ghp|lsv2)[-_][A-Za-z0-9_-]{12,}\b"),
)


class PolicyViolationError(Exception):
    """La petición contiene inyección de instrucciones o exfiltración.

    :param category: Categoría cerrada: ``injection`` o ``exfiltration``.
    :type category: str
    """

    def __init__(self, category: str):
        super().__init__(f"request blocked by policy: {category}")
        self.category = category


def normalize(text: str) -> str:
    """Pasa a minúsculas, quita acentos y colapsa espacios.

    :param text: Texto original.
    :type text: str
    :return: Texto normalizado para comparar patrones.
    :rtype: str
    """
    decomposed = unicodedata.normalize("NFKD", text)
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(plain.casefold().split())


def classify_attack(text: str) -> str:
    """Clasifica un texto como ataque o no.

    :param text: Texto de la pregunta o de un mensaje del historial.
    :type text: str
    :return: ``injection``, ``exfiltration`` o cadena vacía si no hay ataque.
    :rtype: str
    """
    plain = normalize(text)
    if any(pattern.search(plain) for pattern in _INJECTION_PATTERNS):
        return "injection"
    if any(pattern.search(plain) for pattern in _EXFILTRATION_PATTERNS):
        return "exfiltration"
    return ""


def merge_types(*groups: Sequence[str]) -> Tuple[str, ...]:
    """Une listas de tipos sin repetir y conservando el orden.

    :param groups: Listas de tipos.
    :type groups: Sequence[str]
    :return: Tipos únicos.
    :rtype: tuple[str, ...]
    """
    merged: List[str] = []
    for group in groups:
        for kind in group:
            if kind not in merged:
                merged.append(kind)
    return tuple(merged)


@dataclass(frozen=True)
class GuardedInput:
    """Entrada ya revisada y redactada.

    :param question: Pregunta con la PII redactada.
    :type question: str
    :param history: Historial con la PII redactada.
    :type history: list[dict]
    :param redactions: Tipos de PII redactados, sin repetir.
    :type redactions: tuple[str, ...]
    """

    question: str
    history: List[Dict[str, str]]
    redactions: Tuple[str, ...]


class InputGuard:
    """Guarda determinista de entrada: bloquea ataques y redacta PII."""

    def check(
        self, question: str, history: Sequence[Dict[str, str]]
    ) -> GuardedInput:
        """Revisa la pregunta y el historial antes de llamar al modelo.

        :param question: Pregunta original.
        :type question: str
        :param history: Mensajes previos con ``role`` y ``content``.
        :type history: Sequence[dict]
        :return: Pregunta e historial redactados, con los tipos encontrados.
        :rtype: GuardedInput
        :raises PolicyViolationError: Si hay inyección o exfiltración.
        """
        for text in [question] + [item["content"] for item in history]:
            category = classify_attack(text)
            if category:
                raise PolicyViolationError(category)
        redacted_question = redact_pii(question)
        redacted_history = []
        groups = [redacted_question.types]
        for item in history:
            redacted = redact_pii(item["content"])
            groups.append(redacted.types)
            redacted_history.append({"role": item["role"], "content": redacted.text})
        return GuardedInput(
            question=redacted_question.text,
            history=redacted_history,
            redactions=merge_types(*groups),
        )


@dataclass(frozen=True)
class OutputDecision:
    """Decisión final del Output Guard.

    :param answer: Respuesta que sale hacia el cliente.
    :type answer: str
    :param redactions: Tipos de PII redactados en la salida.
    :type redactions: tuple[str, ...]
    :param blocked: ``True`` si se cambió por la respuesta segura fija.
    :type blocked: bool
    """

    answer: str
    redactions: Tuple[str, ...]
    blocked: bool


class OutputGuard:
    """Guarda determinista de salida: decide siempre la respuesta final.

    :param max_answer_chars: Largo máximo de la respuesta.
    :type max_answer_chars: int
    """

    def __init__(self, max_answer_chars: int):
        self._max_answer_chars = max_answer_chars

    def _must_block(self, draft: str, review_status: str) -> bool:
        """Indica si el borrador debe cambiarse por la respuesta segura.

        :param draft: Borrador del Specialist.
        :type draft: str
        :param review_status: ``approved``, ``rejected`` o ``unavailable``.
        :type review_status: str
        :return: ``True`` si se bloquea.
        :rtype: bool
        """
        if review_status == REVIEW_REJECTED:
            return True
        if len(draft) > self._max_answer_chars:
            return True
        if any(marker in draft for marker in _PROMPT_MARKERS):
            return True
        return any(pattern.search(draft) for pattern in _SECRET_OUTPUT_PATTERNS)

    def decide(self, draft: str, review_status: str) -> OutputDecision:
        """Decide la respuesta final a partir del borrador y la revisión.

        :param draft: Borrador del Specialist.
        :type draft: str
        :param review_status: ``approved``, ``rejected`` o ``unavailable``.
        :type review_status: str
        :return: Respuesta final, tipos redactados y si se bloqueó.
        :rtype: OutputDecision
        """
        if self._must_block(draft, review_status):
            return OutputDecision(answer=SAFE_ANSWER, redactions=(), blocked=True)
        redacted = redact_pii(draft)
        return OutputDecision(
            answer=redacted.text, redactions=redacted.types, blocked=False
        )
