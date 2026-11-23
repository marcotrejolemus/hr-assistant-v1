"""Pruebas de I7 (F1 y F2): tolerancia solo en el envoltorio del JSON del modelo.

Un modelo pequeño real envuelve el JSON en bloques de código o agrega texto. La
función ``extract_json_object`` quita ese envoltorio y después se aplica la
misma validación estricta de siempre: sin alias ni campos extra.
"""

import asyncio
import json

import pytest
from doubles import RecordingModel, ScriptedSpecialistModel

from app.agent import DirectorySpecialistAgent
from app.llm import TOOL_RESULT_PREFIX, extract_json_object
from app.reviewer import parse_verdict

TOOL_REQUEST = {"tool": "get_employee", "args": {"employee_id": "EMP-0004"}}


def _fenced(payload, language="json"):
    """Envuelve un objeto en un bloque de código como lo hace un modelo real.

    :param payload: Objeto que se serializa en JSON.
    :type payload: dict
    :param language: Etiqueta del bloque; vacía para un bloque sin lenguaje.
    :type language: str
    :return: Texto con el bloque de código.
    :rtype: str
    """
    return f"```{language}\n{json.dumps(payload)}\n```"


def _run(agent, question):
    """Corre el bucle async del agente sin historial."""
    return asyncio.run(agent.run(question, []))


def test_extract_json_object_unwraps_code_fences():
    answer = {"answer": "Hola"}

    assert extract_json_object(_fenced(answer)) == answer
    assert extract_json_object(_fenced(answer, language="")) == answer


def test_extract_json_object_accepts_a_single_object_among_plain_text():
    """Un único objeto se acepta aunque lo rodee texto con llaves sueltas."""
    explained_fence = f"Aquí va:\n{_fenced(TOOL_REQUEST)}\nEspero que sirva."
    loose_braces = 'Usa {nombre} si hace falta. {"answer": "Hola"} Y {apellido}.'
    nested = f"Claro, aquí está: {json.dumps(TOOL_REQUEST)} Listo."

    assert extract_json_object(explained_fence) == TOOL_REQUEST
    assert extract_json_object(loose_braces) == {"answer": "Hola"}
    assert extract_json_object(nested) == TOOL_REQUEST


ONE = {"answer": "uno"}
TWO = {"answer": "dos"}


@pytest.mark.parametrize(
    "texts",
    [
        ["No sé qué responder."],
        ['["approve", "reject"]'],
        ['{"answer": "sin cerrar"'],
        [
            f"{json.dumps(ONE)}\n{json.dumps(TWO)}",
            f"{_fenced(ONE)}\n{_fenced(TWO)}",
            f"```json\n{json.dumps(ONE)}\n{json.dumps(TWO)}\n```",
        ],
        [f'{json.dumps(ONE)} ["dos"]', f'["uno"] {json.dumps(TWO)}'],
    ],
    ids=["no_object", "array", "invalid_json", "two_objects", "object_and_array"],
)
def test_extract_json_object_rejects_anything_but_exactly_one_object(texts):
    """Varios valores JSON son ambiguos: se rechazan en vez de elegir uno."""
    for text in texts:
        with pytest.raises(ValueError):
            extract_json_object(text)


def test_fenced_tool_request_runs_the_tool_and_keeps_its_evidence(directory):
    """El Specialist acepta el envoltorio y guarda el resultado de la tool."""
    model = ScriptedSpecialistModel(
        _fenced(TOOL_REQUEST), 'Listo: {"answer": "Ok"} Gracias.'
    )
    agent = DirectorySpecialistAgent(model=model, directory=directory, max_steps=3)

    result = _run(agent, "¿Quién es EMP-0004?")

    assert result.answer == "Ok"
    assert result.steps == 2
    assert result.tools_used == ["get_employee"]
    assert result.evidence == [directory.get_employee("EMP-0004")]


def test_fenced_tool_request_with_an_alias_for_args_is_still_denied(directory):
    """Quitar el envoltorio no relaja el esquema: ``arguments`` no es ``args``."""
    alias = {"tool": "get_employee", "arguments": {"employee_id": "EMP-0004"}}
    model = ScriptedSpecialistModel(_fenced(alias), json.dumps({"answer": "Ok"}))
    denied = []
    agent = DirectorySpecialistAgent(
        model=model, directory=directory, max_steps=3, observe_denied=denied.append
    )

    result = _run(agent, "¿Quién es EMP-0004?")

    assert denied == ["get_employee"]
    assert result.tools_used == []
    assert result.evidence == []


def test_invalid_reply_feedback_reminds_the_exact_json_format(directory):
    """El error que vuelve al modelo repite el formato sin gastar más llamadas."""
    inner = ScriptedSpecialistModel("Hola, soy el asistente.", '{"answer": "Ok"}')
    model = RecordingModel(inner)
    agent = DirectorySpecialistAgent(model=model, directory=directory, max_steps=3)

    result = _run(agent, "¿Quién es EMP-0004?")

    feedback = model.calls[1]["messages"][-1]["content"]
    assert feedback.startswith(TOOL_RESULT_PREFIX)
    for literal in ('"tool"', '"args"', '"answer"'):
        assert literal in feedback
    assert (result.answer, result.steps, len(model.calls)) == ("Ok", 2, 2)


def test_fenced_verdict_is_accepted_but_an_extra_field_is_still_invalid():
    """Un campo extra sigue lanzando ``ValueError`` (Reviewer ``unavailable``)."""
    approve = {"verdict": "approve", "issues": []}

    verdict = parse_verdict(_fenced(approve))

    assert (verdict.verdict, verdict.issues) == ("approve", ())
    with pytest.raises(ValueError):
        parse_verdict(_fenced({**approve, "answer": "otra"}))
