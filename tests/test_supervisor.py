"""Pruebas del Supervisor a través de ``create_app``: llamadas, presupuestos y tiempos.

Se prueba por la API para no atar las pruebas a la forma interna del Supervisor.
"""

import asyncio

import httpx
import pytest
from doubles import (
    AUTH_HEADERS,
    ConcurrencyProbeModel,
    RecordingModel,
    SlowModel,
    is_reviewer_call,
)

from app.llm import FakeLanguageModel

QUESTION = {"question": "¿Quién es EMP-0004?"}
CAP_MESSAGE = "No pude completar la respuesta. Intenta con una pregunta más concreta."


@pytest.fixture
def fake_model(directory):
    """El modelo simulado con los departamentos de los datos."""
    return FakeLanguageModel(directory.departments())


def test_steps_count_the_specialist_and_model_calls_count_all(make_client, fake_model):
    model = RecordingModel(fake_model)

    body = make_client(model=model).post("/ask", json=QUESTION).json()

    assert body["steps"] == 2
    assert body["model_calls"] == len(model.calls) == 3
    assert body["input_tokens"] == sum(
        call["completion"].input_tokens for call in model.calls
    )
    assert body["output_tokens"] == sum(
        call["completion"].output_tokens for call in model.calls
    )
    assert body["review"] == {"status": "approved", "issue_count": 0}


def test_reviewer_uses_the_small_model_without_history(make_client, fake_model):
    # Desde I3 todo modelo configurado necesita precio: "fake" lo tiene (0 USD).
    model = RecordingModel(fake_model)
    client = make_client(model=model, MODEL_SMALL="fake", MODEL_MAX_TOKENS="123")
    history = [{"role": "user", "content": "Mensaje previo de prueba"}]

    client.post("/ask", json={**QUESTION, "history": history})

    reviewer_calls = [c for c in model.calls if is_reviewer_call(c["messages"])]
    assert len(reviewer_calls) == 1
    assert reviewer_calls[0]["model"] == "fake"
    assert "Mensaje previo de prueba" not in str(reviewer_calls[0]["messages"])
    assert {call["max_tokens"] for call in model.calls} == {123}


def test_input_token_budget_stops_before_calling_the_model(make_client, fake_model):
    model = RecordingModel(fake_model)

    response = make_client(model=model, REQUEST_INPUT_TOKEN_BUDGET="1").post(
        "/ask", json=QUESTION
    )

    body = response.json()
    assert response.status_code == 200
    assert body["answer"] == CAP_MESSAGE
    assert not model.calls
    assert body["model_calls"] == 0
    assert body["review"]["status"] == "unavailable"


@pytest.mark.parametrize(
    ("slow_role", "status", "expected"),
    [
        ("specialist", 502, {"detail": "model unavailable"}),
        ("reviewer", 200, {"review": {"status": "unavailable", "issue_count": 0}}),
    ],
)
def test_a_slow_model_call_times_out(
    make_client, fake_model, slow_role, status, expected
):
    """``MODEL_TIMEOUT_SECONDS`` acepta fracciones; la espera se cancela."""
    model = SlowModel(fake_model, slow_role=slow_role, delay_seconds=5.0)

    response = make_client(model=model, MODEL_TIMEOUT_SECONDS="0.05").post(
        "/ask", json=QUESTION
    )

    assert response.status_code == status
    assert expected.items() <= response.json().items()


def test_two_concurrent_requests_stay_independent(make_app, fake_model):
    """Las dos peticiones están en curso a la vez y no mezclan resultados."""
    model = ConcurrencyProbeModel(fake_model)
    app = make_app(model)

    async def ask_both():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://t", headers=AUTH_HEADERS
        ) as api:
            return await asyncio.gather(
                api.post("/ask", json=QUESTION),
                api.post("/ask", json={"question": "¿Quiénes trabajan en Finanzas?"}),
            )

    employee, department = (response.json() for response in asyncio.run(ask_both()))

    assert model.max_in_flight == 2
    assert "Jorge Díaz" in employee["answer"]
    assert "Sofía Gómez" not in employee["answer"]
    assert employee["tools_used"] == ["get_employee"]
    assert "Sofía Gómez" in department["answer"]
    assert "Jorge Díaz" not in department["answer"]
    assert department["tools_used"] == ["search_by_department"]
