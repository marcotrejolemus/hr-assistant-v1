"""Pruebas del enrutador de costo y de la ventana de historial (``spec/03``).

El enrutador es una regla en código: ``route_question`` devuelve el modelo y el
motivo (``reason``), que la API publica como ``route``.
"""

import pytest
from doubles import (
    COMPLEX_QUESTION,
    LARGE_MODEL,
    SIMPLE_QUESTION,
    SMALL_MODEL,
    RecordingModel,
    is_reviewer_call,
)

from app.llm import FakeLanguageModel
from app.router import route_question


@pytest.fixture
def settings(make_settings):
    """Configuración por omisión (``ROUTER_MAX_CHARS=80``)."""
    return make_settings()


@pytest.mark.parametrize(
    "question",
    [
        "Compara EMP-0001 y EMP-0002",
        "Resume el perfil de EMP-0004",
        "Explica el puesto de EMP-0004",
        "¿Por qué EMP-0004 está en Ventas?",
        "ANALIZA el área de Finanzas",
        "¿Quiénes son todos los de Ventas?",
    ],
)
def test_each_complexity_keyword_routes_to_the_large_model(settings, question):
    decision = route_question(question, settings)

    assert decision.model == LARGE_MODEL
    assert decision.reason == "complex_keyword"


def test_a_short_plain_question_routes_to_the_small_model(settings):
    decision = route_question(SIMPLE_QUESTION, settings)

    assert decision.model == SMALL_MODEL
    assert decision.reason == "simple"


def test_only_questions_longer_than_the_limit_go_to_the_large_model(settings):
    at_limit = route_question("a" * 80, settings)
    over_limit = route_question("a" * 81, settings)

    assert at_limit.model == SMALL_MODEL
    assert over_limit.model == LARGE_MODEL
    assert over_limit.reason == "long_question"


def test_disabled_routing_always_uses_the_large_model(make_settings):
    decision = route_question(SIMPLE_QUESTION, make_settings(ROUTING="false"))

    assert decision.model == LARGE_MODEL
    assert decision.reason == "routing_disabled"


def test_only_the_last_history_messages_reach_the_model(make_client, directory):
    model = RecordingModel(FakeLanguageModel(directory.departments()))
    roles = ("user", "assistant")
    history = [
        {"role": roles[index % 2], "content": f"Mensaje previo {index}"}
        for index in range(1, 6)
    ]

    make_client(model=model, HISTORY_WINDOW="2").post(
        "/ask", json={"question": SIMPLE_QUESTION, "history": history}
    )

    first_call = [m for m in model.calls[0]["messages"] if m["role"] != "system"]
    assert [m["content"] for m in first_call] == [
        "Mensaje previo 4",
        "Mensaje previo 5",
        SIMPLE_QUESTION,
    ]
    assert "Mensaje previo 3" not in str(model.calls)


def test_reviewer_uses_the_small_model_even_for_complex_questions(
    make_client, directory
):
    model = RecordingModel(FakeLanguageModel(directory.departments()))

    body = make_client(model=model).post(
        "/ask", json={"question": COMPLEX_QUESTION}
    ).json()

    reviewer = [c for c in model.calls if is_reviewer_call(c["messages"])]
    specialist = [c for c in model.calls if not is_reviewer_call(c["messages"])]
    assert [call["model"] for call in reviewer] == [SMALL_MODEL]
    assert {call["model"] for call in specialist} == {LARGE_MODEL}
    assert body["model"] == LARGE_MODEL
    assert body["route"] == "complex_keyword"
