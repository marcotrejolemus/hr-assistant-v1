"""Pasos de ``features/observability.feature``: el ``request_id`` de cada respuesta.

Cada escenario arma la app con reloj fijo y log capturado (``make_observed_client``).
"""

import uuid

import pytest
from doubles import BROKEN_MESSAGE, BrokenModel, log_text, read_events
from pytest_bdd import given, parsers, scenarios, then, when

scenarios("features/observability.feature")


@pytest.fixture
def context():
    """Estado de un escenario: configuración, modelo, id enviado y respuestas."""
    return {"environ": {}, "model": None, "request_id": None, "responses": []}


def _client(make_observed_client, context):
    """Construye el cliente con la configuración y el modelo del escenario."""
    return make_observed_client(model=context["model"], **context["environ"])


def _headers(context):
    """Encabezados de la petición: ``X-Request-ID`` solo si el escenario lo fijó."""
    if context["request_id"] is None:
        return {}
    return {"X-Request-ID": context["request_id"]}


def _last(context):
    """La última respuesta recibida en el escenario."""
    return context["responses"][-1]


@given("the HR Assistant is running with the fake model")
def running_with_fake_model(context):
    """El escenario parte de la configuración por omisión."""
    context["environ"]["MODEL_PROVIDER"] = "fake"


@given("the model provider is down")
def provider_down(context):
    """Toda llamada al modelo simulado falla."""
    context["environ"]["FAKE_MODEL_FAIL"] = "true"


@given("the model breaks with an unexpected error")
def model_breaks(context):
    """El modelo lanza un error que no es una caída del proveedor."""
    context["model"] = BrokenModel()


@given(parsers.parse('the client sends the request id "{request_id}"'))
def client_sends_request_id(context, request_id):
    """El cliente manda su propio ``X-Request-ID``."""
    context["request_id"] = request_id


@when(parsers.re(r'I ask "(?P<question>[^"]+)"'))
def ask(make_observed_client, context, question):
    """Envía una pregunta sin historial."""
    client = _client(make_observed_client, context)
    response = client.post(
        "/ask", json={"question": question}, headers=_headers(context)
    )
    context["responses"].append(response)


@when("I send an empty question")
def send_empty_question(make_observed_client, context):
    """Envía una pregunta vacía, que el esquema rechaza."""
    client = _client(make_observed_client, context)
    response = client.post("/ask", json={"question": ""}, headers=_headers(context))
    context["responses"].append(response)


@when("I check the health endpoint")
def check_health(make_observed_client, context):
    """Consulta ``GET /health``."""
    client = _client(make_observed_client, context)
    context["responses"].append(client.get("/health", headers=_headers(context)))


@when("I open the home page")
def open_home_page(make_observed_client, context):
    """Pide la página web."""
    context["responses"].append(_client(make_observed_client, context).get("/"))


@then(parsers.parse("the response status is {status:d}"))
def response_status(context, status):
    """La última respuesta tiene el código esperado."""
    assert _last(context).status_code == status


@then("the response carries a generated request id")
def generated_request_id(context):
    """Sin encabezado del cliente, el servidor genera un UUID válido."""
    assert uuid.UUID(_last(context).headers["X-Request-ID"])


@then(parsers.parse('the response header request id is "{request_id}"'))
def header_request_id(context, request_id):
    """El encabezado ``X-Request-ID`` devuelve el id de la petición."""
    assert _last(context).headers["X-Request-ID"] == request_id


@then(parsers.parse('the body request id is "{request_id}"'))
def body_request_id(context, request_id):
    """El cuerpo trae el mismo ``request_id`` que el encabezado."""
    assert _last(context).json()["request_id"] == request_id


@then(parsers.parse('the error detail is "{detail}"'))
def error_detail(context, detail):
    """El cuerpo de error trae el ``detail`` fijo de la API."""
    assert _last(context).json()["detail"] == detail


@then("the error log keeps only the error type")
def error_log_keeps_only_the_type(context, log_lines):
    """El evento ``error`` nombra el tipo de error y nunca su mensaje."""
    (error,) = read_events(log_lines, "error")
    assert error["error_type"] == "RuntimeError"
    assert error["request_id"] == context["request_id"]
    assert BROKEN_MESSAGE not in log_text(log_lines)


@then("the page has a place for the request id")
def page_shows_request_id(context):
    """La página muestra el ``request_id`` sin usar ``innerHTML``."""
    page = _last(context).text
    assert "request_id" in page
    assert 'data-testid="request-id"' in page
    assert "innerHTML" not in page
