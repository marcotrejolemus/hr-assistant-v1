"""Pasos de ``features/security.feature``: clave por cliente, límite y política.

Cada escenario usa un solo cliente (el límite de peticiones vive en la app) y
manda la clave en cada petición según lo que fijó el escenario.
"""

import pytest
from doubles import TEST_KEY, WRONG_KEY
from pytest_bdd import given, parsers, scenarios, then, when

scenarios("features/security.feature")

KEYS_BY_KIND = {
    "no API key": None,
    "a wrong API key": WRONG_KEY,
    "its API key": TEST_KEY,
}
REPEATED_ASK = r'the client asks "(?P<question>[^"]+)" (?P<count>\d+) times in a row'
READ_ONLY_TOOLS = {"get_employee", "search_by_department"}


@pytest.fixture
def context():
    """Estado de un escenario: configuración, clave, cliente y respuestas."""
    return {"environ": {}, "api_key": TEST_KEY, "client": None, "responses": []}


def _client(make_client, context):
    """Crea el cliente una vez por escenario, sin clave por omisión."""
    if context["client"] is None:
        context["client"] = make_client(api_key=None, **context["environ"])
    return context["client"]


def _headers(context):
    """Encabezados de la petición: ``X-API-Key`` solo si el escenario manda clave."""
    if context["api_key"] is None:
        return {}
    return {"X-API-Key": context["api_key"]}


def _ask(make_client, context, question):
    """Envía una pregunta con la clave del escenario y guarda la respuesta."""
    response = _client(make_client, context).post(
        "/ask", json={"question": question}, headers=_headers(context)
    )
    context["responses"].append(response)


def _last(context):
    """La última respuesta recibida en el escenario."""
    return context["responses"][-1]


@given("the HR Assistant is running with the fake model")
def running_with_fake_model(context):
    """El escenario parte de la configuración por omisión."""
    context["environ"]["MODEL_PROVIDER"] = "fake"


@given(parsers.parse("the client sends {kind}"))
def client_sends(context, kind):
    """Fija qué clave manda el cliente: ninguna, una equivocada o la suya."""
    context["api_key"] = KEYS_BY_KIND[kind]


@given(parsers.parse("the limit is {limit:d} requests per minute"))
def rate_limit(context, limit):
    """Configura ``RATE_LIMIT_PER_MINUTE``."""
    context["environ"]["RATE_LIMIT_PER_MINUTE"] = str(limit)


@given("no API keys are configured")
def no_api_keys(context):
    """``API_KEYS`` vacía en desarrollo: nadie puede entrar."""
    context["environ"]["API_KEYS"] = ""


@when(parsers.re(r'I ask "(?P<question>[^"]+)"'))
def ask(make_client, context, question):
    """Envía una pregunta sin historial."""
    _ask(make_client, context, question)


@when(parsers.re(REPEATED_ASK))
def ask_many_times(make_client, context, question, count):
    """Envía la misma pregunta varias veces con el mismo cliente."""
    for _ in range(int(count)):
        _ask(make_client, context, question)


@when(parsers.parse('I open "{path}"'))
def open_path(make_client, context, path):
    """Pide una ruta con ``GET`` y la clave del escenario."""
    response = _client(make_client, context).get(path, headers=_headers(context))
    context["responses"].append(response)


@then(parsers.parse("the response status is {status:d}"))
def response_status(context, status):
    """La última respuesta tiene el código esperado."""
    assert _last(context).status_code == status


@then(parsers.parse('the statuses are "{statuses}"'))
def statuses_are(context, statuses):
    """Los códigos de todas las respuestas, en orden."""
    expected = [int(status) for status in statuses.split(", ")]
    assert [response.status_code for response in context["responses"]] == expected


@then(parsers.parse('the body is exactly "{detail}"'))
def body_is_exactly(context, detail):
    """En 401 y 429 el cuerpo es solo ``detail``; el id va en el encabezado."""
    assert _last(context).json() == {"detail": detail}


@then(parsers.parse('the error detail is "{detail}"'))
def error_detail(context, detail):
    """El cuerpo de error trae el ``detail`` fijo de la API."""
    assert _last(context).json()["detail"] == detail


@then("the response carries a request id")
def carries_request_id(context):
    """También un 401 lleva ``X-Request-ID``."""
    assert _last(context).headers["X-Request-ID"]


@then("the response asks to retry after some seconds")
def retry_after(context):
    """El 429 dice en ``Retry-After`` cuántos segundos faltan."""
    assert int(_last(context).headers["Retry-After"]) > 0


@then("only read-only tools were used")
def only_read_only_tools(context):
    """Pedir un cambio se bloquea o se atiende solo con herramientas de lectura."""
    response = _last(context)
    assert response.status_code in (200, 400)
    if response.status_code == 200:
        assert set(response.json()["tools_used"]) <= READ_ONLY_TOOLS


@then(parsers.parse('the answer mentions "{text}"'))
def answer_mentions(context, text):
    """La respuesta contiene el texto."""
    assert text in _last(context).json()["answer"]
