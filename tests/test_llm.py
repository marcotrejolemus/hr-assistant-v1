"""Pruebas del modelo simulado: reglas, tokens, rol Reviewer y fallos simulados."""

import asyncio
import json

import pytest

from app.llm import REVIEWER_MARKER, FakeLanguageModel, ModelUnavailableError

DEPARTMENTS = ["Tecnología", "Ventas", "Finanzas"]
REVIEWER_MESSAGES = [
    {"role": "system", "content": f"{REVIEWER_MARKER} Revisa el borrador."},
    {"role": "user", "content": "Borrador: Según el directorio: EMP-0004"},
]
SPECIALIST_MESSAGES = [{"role": "user", "content": "¿Quién es EMP-0004?"}]


@pytest.fixture
def model():
    """Modelo simulado con los departamentos de los datos."""
    return FakeLanguageModel(DEPARTMENTS)


def _complete(model, messages):
    """Llama al modelo async con el nombre y el tope de salida obligatorios."""
    return asyncio.run(
        model.complete(messages, model="fake-small", max_tokens=300)
    )


def _reply(model, content):
    """Pide una respuesta al modelo con un solo mensaje y la decodifica."""
    completion = _complete(model, [{"role": "user", "content": content}])
    return json.loads(completion.text)


def test_employee_id_asks_for_get_employee(model):
    reply = _reply(model, "¿Quién es EMP-0004?")

    assert reply == {"tool": "get_employee", "args": {"employee_id": "EMP-0004"}}


def test_known_department_asks_for_search_by_department(model):
    reply = _reply(model, "¿Quiénes trabajan en Finanzas?")

    assert reply == {
        "tool": "search_by_department",
        "args": {"department": "Finanzas"},
    }


def test_tool_result_is_answered_even_if_it_contains_an_id(model):
    result = 'Resultado de la herramienta: {"id": "EMP-0004", "name": "Jorge Díaz"}'

    reply = _reply(model, result)

    assert reply["answer"].startswith("Según el directorio: ")
    assert "Jorge Díaz" in reply["answer"]


def test_tokens_are_counted_as_words(model):
    messages = [
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": "Hola, dime"},
        {"role": "user", "content": "¿Quién es EMP-0004?"},
    ]

    completion = _complete(model, messages)

    assert completion.input_tokens == 6
    assert completion.output_tokens == len(completion.text.split())


def test_fake_model_answers_the_reviewer_role_with_a_verdict(model):
    rejecting = FakeLanguageModel(DEPARTMENTS, reviewer_verdict="reject")

    approved = json.loads(_complete(model, REVIEWER_MESSAGES).text)
    rejected = json.loads(_complete(rejecting, REVIEWER_MESSAGES).text)

    assert approved == {"verdict": "approve", "issues": []}
    assert rejected["verdict"] == "reject"


@pytest.mark.parametrize(
    ("options", "specialist_works"),
    [({"fail": True}, False), ({"reviewer_fail": True}, True)],
    ids=["whole_model_down", "reviewer_down"],
)
def test_fake_failure_switches_raise_model_unavailable(options, specialist_works):
    """``fail`` tumba toda llamada; ``reviewer_fail`` solo la del Reviewer."""
    failing = FakeLanguageModel(DEPARTMENTS, **options)

    with pytest.raises(ModelUnavailableError):
        _complete(failing, REVIEWER_MESSAGES)
    try:
        _complete(failing, SPECIALIST_MESSAGES)
        specialist_answered = True
    except ModelUnavailableError:
        specialist_answered = False
    assert specialist_answered is specialist_works
