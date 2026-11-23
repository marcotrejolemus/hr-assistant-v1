"""Pruebas del bucle del Directory Specialist con un modelo guionizado."""

import asyncio
import json

import pytest

from app.agent import SPECIALIST_MARKER, Agent, DirectorySpecialistAgent
from app.llm import REVIEWER_MARKER, Completion, FakeLanguageModel

CAP_MESSAGE = "No pude completar la respuesta. Intenta con una pregunta más concreta."
TOOL_PREFIX = "Resultado de la herramienta: "


class ScriptedModel:
    """Modelo de prueba que devuelve respuestas guionizadas en orden.

    Repite la última respuesta si el agente pide más de las que hay, y guarda una
    copia de los mensajes de cada llamada.
    """

    def __init__(self, *replies, input_tokens=5, output_tokens=2):
        self._replies = list(replies)
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self.calls = []

    async def complete(self, messages, *, model, max_tokens):
        """Devuelve la siguiente respuesta del guion."""
        del model, max_tokens
        self.calls.append([dict(message) for message in messages])
        text = self._replies[min(len(self.calls), len(self._replies)) - 1]
        return Completion(
            text=text,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
        )


def _tool(name, **args):
    """Respuesta del modelo que pide una herramienta."""
    return json.dumps({"tool": name, "args": args})


def _answer(text):
    """Respuesta final del modelo."""
    return json.dumps({"answer": text})


def _run(agent, question, history):
    """Corre el bucle async del agente desde una prueba síncrona."""
    return asyncio.run(agent.run(question, history))


def test_history_is_placed_before_the_question(directory):
    model = ScriptedModel(_answer("Hola"))
    history = [
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": "¿En qué te ayudo?"},
    ]

    result = _run(
        Agent(model=model, directory=directory, max_steps=3),
        "¿Quién es EMP-0004?",
        history,
    )

    # El prompt de sistema del Specialist se prueba aparte; aquí solo importa
    # que el historial y la pregunta lleguen completos y en orden.
    conversation = [m for m in model.calls[0] if m["role"] != "system"]
    assert conversation == history + [
        {"role": "user", "content": "¿Quién es EMP-0004?"}
    ]
    assert (result.answer, result.steps, result.tools_used) == ("Hola", 1, [])


def test_every_specialist_call_starts_with_the_system_prompt(directory):
    """El prompt explica herramientas y protocolo JSON a un modelo real."""
    model = ScriptedModel(_tool("get_employee", employee_id="EMP-0004"), _answer("Ok"))
    history = [{"role": "user", "content": "Hola"}]

    _run(
        Agent(model=model, directory=directory, max_steps=3),
        "¿Quién es EMP-0004?",
        history,
    )

    first_call = model.calls[0]
    system = first_call[0]
    assert system["role"] == "system"
    for expected in (
        SPECIALIST_MARKER,
        "get_employee",
        "employee_id",
        "search_by_department",
        '"tool"',
        '"args"',
        '"answer"',
    ):
        assert expected in system["content"]
    assert REVIEWER_MARKER not in system["content"]
    assert first_call[1:] == history + [
        {"role": "user", "content": "¿Quién es EMP-0004?"}
    ]
    second_call = model.calls[1]
    assert second_call[0] == system
    assert [m["role"] for m in second_call].count("system") == 1


def test_fake_model_still_answers_with_the_system_prompt_in_two_steps(directory):
    """El simulado sigue decidiendo por el último mensaje (contrato de sesión 1)."""
    model = FakeLanguageModel(directory.departments())

    result = _run(
        Agent(model=model, directory=directory, max_steps=3),
        "¿Quién es EMP-0004?",
        [],
    )

    assert result.steps == 2
    assert result.tools_used == ["get_employee"]
    assert "Jorge Díaz" in result.answer


def test_tool_result_is_added_to_the_conversation_and_tokens_are_summed(directory):
    model = ScriptedModel(_tool("get_employee", employee_id="EMP-0004"), _answer("Ok"))

    result = _run(
        Agent(model=model, directory=directory, max_steps=3),
        "¿Quién es EMP-0004?",
        [],
    )

    last_message = model.calls[1][-1]
    assert last_message["role"] == "user"
    assert last_message["content"].startswith(TOOL_PREFIX)
    assert "Jorge Díaz" in last_message["content"]
    assert result.answer == "Ok"
    assert result.steps == 2
    assert result.tools_used == ["get_employee"]
    assert (result.input_tokens, result.output_tokens) == (10, 4)


@pytest.mark.parametrize(
    "bad_reply",
    [
        "this is not json",
        _tool("fire_employee", employee_id="EMP-0004"),
        _tool("get_employee", wrong_argument="EMP-0004"),
    ],
    ids=["invalid_json", "unknown_tool", "invalid_arguments"],
)
def test_malformed_model_reply_does_not_break_the_loop(directory, bad_reply):
    model = ScriptedModel(bad_reply, _answer("Ok"))

    result = _run(Agent(model=model, directory=directory, max_steps=3), "Hola", [])

    assert result.answer == "Ok"
    assert result.steps == 2


def test_step_cap_returns_the_fixed_message(directory):
    model = ScriptedModel(_tool("search_by_department", department="Ventas"))

    result = _run(Agent(model=model, directory=directory, max_steps=3), "Ventas", [])

    assert result.answer == CAP_MESSAGE
    assert result.steps == 3
    assert len(model.calls) == 3


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("get_employee", {"employee_id": "EMP-12"}),
        ("get_employee", {"employee_id": "../data/employees.json"}),
        ("search_by_department", {"department": "x" * 65}),
    ],
    ids=["short_id", "path_as_id", "department_too_long"],
)
def test_tool_arguments_outside_the_allowed_shape_are_denied(directory, tool, args):
    """Solo ids ``EMP-NNNN`` y departamentos de hasta 64 caracteres pasan."""
    model = ScriptedModel(json.dumps({"tool": tool, "args": args}), _answer("Ok"))
    agent = DirectorySpecialistAgent(model=model, directory=directory, max_steps=3)

    result = _run(agent, "Hola", [])

    feedback = model.calls[1][-1]["content"]
    assert result.tools_used == []
    assert feedback.startswith(TOOL_PREFIX)
    assert "error" in feedback
    assert result.answer == "Ok"
