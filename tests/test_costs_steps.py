"""Pasos de ``features/costs.feature``: enrutamiento y costo por respuesta.

Todo el escenario usa un mismo cliente, para que las métricas acumulen las
preguntas que hizo.
"""

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

scenarios("features/costs.feature")


@pytest.fixture
def context():
    """Estado de un escenario: configuración, cliente y respuestas."""
    return {"environ": {}, "client": None, "responses": []}


def _client(make_client, context):
    """Crea el cliente una sola vez por escenario."""
    if context["client"] is None:
        context["client"] = make_client(**context["environ"])
    return context["client"]


def _last(context):
    """Cuerpo de la última respuesta recibida."""
    return context["responses"][-1].json()


@given("the HR Assistant is running with the fake model")
def running_with_fake_model(context):
    """El escenario parte de la configuración por omisión con el simulado."""
    context["environ"]["MODEL_PROVIDER"] = "fake"


@when(parsers.re(r'I ask "(?P<question>[^"]+)"'))
def ask(make_client, context, question):
    """Envía una pregunta sin historial."""
    response = _client(make_client, context).post("/ask", json={"question": question})
    context["responses"].append(response)


@then(parsers.parse("the response status is {status:d}"))
def response_status(context, status):
    """La última respuesta tiene el código esperado."""
    assert context["responses"][-1].status_code == status


@then(parsers.parse('the model used is "{model}"'))
def model_used(context, model):
    """El campo ``model`` es el modelo que eligió el enrutador."""
    assert _last(context)["model"] == model


@then(parsers.parse('the route is "{route}"'))
def route_is(context, route):
    """El campo ``route`` es el motivo del enrutador."""
    assert _last(context)["route"] == route


@then("the answer cost is greater than zero")
def cost_is_positive(context):
    """El modelo simulado también cuesta, con el precio de su nombre."""
    assert _last(context)["cost_usd"] > 0


@then("no call was cached")
def nothing_cached(context):
    """La caché está apagada por omisión."""
    assert _last(context)["cached_calls"] == 0


@then("the metrics cost equals the sum of both answers")
def metrics_add_up(make_client, context):
    """``/metrics`` acumula el ``cost_usd`` de cada respuesta."""
    answered = sum(response.json()["cost_usd"] for response in context["responses"])
    metrics = _client(make_client, context).get("/metrics").json()
    context["metrics"] = metrics
    assert answered > 0
    assert metrics["cost_usd"] == pytest.approx(answered)


@then(parsers.parse('the billed cost is "{value}"'))
def billed_cost(context, value):
    """El costo facturado no se conoce: se declara así."""
    assert context["metrics"]["cost_billed"] == value
