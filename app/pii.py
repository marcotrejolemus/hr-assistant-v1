"""Detección y redacción determinista de PII (ADR 0005).

Tipos: ``email``, ``phone`` (10 dígitos, con o sin +52), ``curp``, ``rfc`` y
``card`` (validada con Luhn). Cada hallazgo se reemplaza por
``[REDACTED:<tipo>]``. No se redactan ids ``EMP-NNNN``, fechas ISO ni años.
"""

import re
from dataclasses import dataclass
from typing import List, Match, Pattern, Tuple

_EMAIL = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
)
_CURP = re.compile(r"\b[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d\b")
_RFC = re.compile(r"\b[A-Z&]{3,4}\d{6}[A-Z0-9]{3}\b")
_CARD = re.compile(r"(?<![\w-])\d(?:[ -]?\d){12,18}(?![\w-])")
_PHONE = re.compile(
    r"(?<![\w+-])(?:\+52[ .-]?)?"
    r"(?:\d{2}[ .-]?\d{4}[ .-]?\d{4}|\d{3}[ .-]?\d{3}[ .-]?\d{4})"
    r"(?![\w-])"
)


@dataclass(frozen=True)
class Redaction:
    """Texto redactado y tipos de PII encontrados.

    :param text: Texto con la PII reemplazada por ``[REDACTED:<tipo>]``.
    :type text: str
    :param types: Tipos encontrados, sin repetir, en orden de detección.
    :type types: tuple[str, ...]
    """

    text: str
    types: Tuple[str, ...]


def redaction_label(kind: str) -> str:
    """Devuelve el marcador que reemplaza a un dato del tipo dado.

    :param kind: Tipo de PII.
    :type kind: str
    :return: Marcador ``[REDACTED:<tipo>]``.
    :rtype: str
    """
    return f"[REDACTED:{kind}]"


def passes_luhn(digits: str) -> bool:
    """Valida un número de tarjeta con el algoritmo de Luhn.

    :param digits: Solo dígitos.
    :type digits: str
    :return: ``True`` si la suma de control es válida.
    :rtype: bool
    """
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _is_card(match: Match[str]) -> bool:
    """Indica si el hallazgo es una tarjeta válida.

    :param match: Coincidencia del patrón de tarjeta.
    :type match: re.Match
    :return: ``True`` si pasa Luhn.
    :rtype: bool
    """
    return passes_luhn(re.sub(r"\D", "", match.group(0)))


_DETECTORS: Tuple[Tuple[str, Pattern[str]], ...] = (
    ("email", _EMAIL),
    ("curp", _CURP),
    ("rfc", _RFC),
    ("card", _CARD),
    ("phone", _PHONE),
)


def redact_pii(text: str) -> Redaction:
    """Reemplaza la PII del texto y devuelve los tipos encontrados.

    :param text: Texto original.
    :type text: str
    :return: Texto redactado y tipos sin repetir.
    :rtype: Redaction
    """
    found: List[str] = []
    for kind, pattern in _DETECTORS:

        def _replace(match: Match[str], kind: str = kind) -> str:
            """Reemplaza una coincidencia si es PII de verdad."""
            if kind == "card" and not _is_card(match):
                return match.group(0)
            if kind not in found:
                found.append(kind)
            return redaction_label(kind)

        text = pattern.sub(_replace, text)
    return Redaction(text=text, types=tuple(found))
