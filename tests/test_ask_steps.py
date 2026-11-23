"""Pasos de ``features/ask.feature`` contra la API con dependencias inyectadas."""

import os

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

scenarios("features/ask.feature")


@pytest.fixture
def context():
    """Estado de un escenario: configuración extra y respuestas recibidas."""
    return {"environ": {}, "responses": []}


def _client(make_client, context):
    """Construye el cliente con la configuración que fijó el escenario."""
    return make_client(**context["environ"])


def _last(context):
    """La última respuesta recibida en el escenario."""
    return context["responses"][-1]


@given("the HR Assistant is running with the fake model")
def running_with_fake_model(context):
    """El escenario parte de la configuración por omisión."""
    context["environ"]["MODEL_PROVIDER"] = "fake"


@given(parsers.parse("the agent may take at most {count:d} steps"))
def agent_step_cap(context, count):
    """Fija el tope de vueltas del bucle."""
    context["environ"]["AGENT_MAX_STEPS"] = str(count)


@when(parsers.re(r'I ask "(?P<question>[^"]+)"'))
def ask(make_client, context, question):
    """Envía una pregunta sin historial."""
    response = _client(make_client, context).post("/ask", json={"question": question})
    context["responses"].append(response)


@when(
    parsers.re(
        r'I ask "(?P<question>[^"]+)" with a previous message "(?P<previous>[^"]+)"'
    )
)
def ask_with_history(make_client, context, question, previous):
    """Envía una pregunta con un historial armado por el cliente."""
    history = [{"role": "user", "content": previous}]
    payload = {"question": question, "history": history}
    response = _client(make_client, context).post("/ask", json=payload)
    context["responses"].append(response)


@when(parsers.re(r'I ask "(?P<question>[^"]+)" again without history'))
def ask_again(make_client, context, question):
    """Repite la pregunta sin historial en otra petición."""
    ask(make_client, context, question)


@when(
    parsers.re(
        r'I ask "(?P<question>[^"]+)" with a previous message of '
        r"(?P<length>\d+) characters"
    ),
    converters={"length": int},
)
def ask_with_long_history(make_client, context, question, length):
    """Envía una pregunta cuyo historial trae un mensaje del largo indicado."""
    history = [{"role": "user", "content": "a" * length}]
    payload = {"question": question, "history": history}
    response = _client(make_client, context).post("/ask", json=payload)
    context["responses"].append(response)


@when(parsers.parse("I ask a question of {length:d} characters"))
def ask_with_length(make_client, context, length):
    """Envía una pregunta del largo indicado."""
    payload = {"question": "a" * length}
    response = _client(make_client, context).post("/ask", json=payload)
    context["responses"].append(response)


@when("I check the health endpoint")
def check_health(make_client, context):
    """Consulta ``GET /health``."""
    context["responses"].append(_client(make_client, context).get("/health"))


@then(parsers.parse("the response status is {status:d}"))
def response_status(context, status):
    """La última respuesta tiene el código esperado."""
    assert _last(context).status_code == status


@then(parsers.parse('the answer mentions "{text}"'))
def answer_mentions(context, text):
    """La respuesta contiene el texto, con acentos intactos."""
    assert text in _last(context).json()["answer"]


@then(parsers.parse('the answer is "{text}"'))
def answer_is(context, text):
    """La respuesta es exactamente el texto."""
    assert _last(context).json()["answer"] == text


@then(parsers.parse('the tools used are "{tool}"'))
def tools_used(context, tool):
    """El agente usó exactamente esa herramienta una vez."""
    assert _last(context).json()["tools_used"] == [tool]


@then("no tools were used")
def no_tools_used(context):
    """El agente respondió sin herramientas."""
    assert _last(context).json()["tools_used"] == []


@then(parsers.parse("the agent took {count:d} steps"))
def agent_steps(context, count):
    """``steps`` cuenta las llamadas al modelo."""
    assert _last(context).json()["steps"] == count


@then("both answers are the same")
def both_answers_are_the_same(context):
    """La API no guarda nada entre peticiones."""
    first, second = context["responses"]
    assert first.json()["answer"] == second.json()["answer"]


@then(parsers.parse('the health status is "{status}" with the process id'))
def health_status(context, status):
    """``/health`` informa el estado y el pid del proceso que atendió."""
    body = _last(context).json()
    assert body == {"status": status, "pid": os.getpid()}
