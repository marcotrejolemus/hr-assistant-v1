"""Pasos de ``features/review.feature``: supervisor, guardas y Reviewer.

Cada escenario arma la app con la configuración que fijó y envuelve el modelo en
un ``RecordingModel`` para comprobar qué llegó al proveedor.
"""

import pytest
from fastapi.testclient import TestClient
from doubles import AUTH_HEADERS, RecordingModel, SecretLeakingModel
from pytest_bdd import given, parsers, scenarios, then, when

from app.guards import SAFE_ANSWER
from app.llm import build_model
from app.main import create_app

scenarios("features/review.feature")


@pytest.fixture
def context():
    """Estado de un escenario: configuración, modelo, grabadora y respuestas."""
    return {"environ": {}, "model": None, "recorder": None, "responses": []}


def _client(make_settings, directory, context):
    """Construye el cliente con la configuración y el modelo del escenario."""
    settings = make_settings(**context["environ"])
    inner = context["model"] or build_model(settings, directory)
    context["recorder"] = RecordingModel(inner)
    app = create_app(settings=settings, model=context["recorder"], directory=directory)
    # Desde I4 /ask exige clave: se manda la de prueba ficticia.
    return TestClient(app, headers=AUTH_HEADERS)


def _last(context):
    """La última respuesta recibida en el escenario."""
    return context["responses"][-1]


def _received_text(context):
    """Todo el texto que recibió el modelo en el escenario."""
    return " ".join(
        message["content"]
        for call in context["recorder"].calls
        for message in call["messages"]
    )


@given("the HR Assistant is running with the fake model")
def running_with_fake_model(context):
    """El escenario parte de la configuración por omisión."""
    context["environ"]["MODEL_PROVIDER"] = "fake"


@given("the model provider is down")
def provider_down(context):
    """Toda llamada al modelo simulado falla."""
    context["environ"]["FAKE_MODEL_FAIL"] = "true"


@given("the reviewer rejects every draft")
def reviewer_rejects(context):
    """El Reviewer simulado rechaza todo borrador."""
    context["environ"]["FAKE_REVIEWER_VERDICT"] = "reject"


@given("the reviewer is down")
def reviewer_down(context):
    """El Reviewer simulado falla; el Specialist sí responde."""
    context["environ"]["FAKE_REVIEWER_FAIL"] = "true"


@given("the specialist leaks a secret and the reviewer is down")
def specialist_leaks_secret(context):
    """El Specialist responde con un nombre de secreto y el Reviewer cae."""
    context["model"] = SecretLeakingModel()


@when(parsers.re(r'I ask "(?P<question>[^"]+)"'))
def ask(make_settings, directory, context, question):
    """Envía una pregunta sin historial."""
    client = _client(make_settings, directory, context)
    context["responses"].append(client.post("/ask", json={"question": question}))


@when(parsers.parse('I open "{path}"'))
def open_path(make_settings, directory, context, path):
    """Pide una ruta con ``GET``."""
    client = _client(make_settings, directory, context)
    context["responses"].append(client.get(path))


@then(parsers.parse("the response status is {status:d}"))
def response_status(context, status):
    """La última respuesta tiene el código esperado."""
    assert _last(context).status_code == status


@then(parsers.parse('the answer mentions "{text}"'))
def answer_mentions(context, text):
    """La respuesta contiene el texto."""
    assert text in _last(context).json()["answer"]


@then(parsers.parse('the answer does not mention "{text}"'))
def answer_does_not_mention(context, text):
    """La respuesta no repite el texto."""
    assert text not in _last(context).json()["answer"]


@then("the answer is the safe answer")
def answer_is_safe(context):
    """La respuesta es la respuesta segura fija del Output Guard."""
    assert _last(context).json()["answer"] == SAFE_ANSWER


@then(parsers.parse('the tools used are "{tool}"'))
def tools_used(context, tool):
    """El Specialist usó exactamente esa herramienta una vez."""
    assert _last(context).json()["tools_used"] == [tool]


@then(parsers.parse("the agent took {count:d} steps"))
def agent_steps(context, count):
    """``steps`` cuenta solo las llamadas del Specialist."""
    assert _last(context).json()["steps"] == count


@then(parsers.parse('the review status is "{status}"'))
def review_status(context, status):
    """El campo ``review`` informa el estado y cuántos issues hubo."""
    review = _last(context).json()["review"]
    assert review["status"] == status
    assert isinstance(review["issue_count"], int)


@then("nothing was redacted")
def nothing_redacted(context):
    """Sin PII no hay redacciones."""
    assert _last(context).json()["redactions"] == []


@then(parsers.parse('the redactions are "{kinds}" without repetition'))
def redactions_are(context, kinds):
    """Cada tipo redactado aparece una sola vez."""
    redactions = _last(context).json()["redactions"]
    assert sorted(redactions) == sorted(kinds.split(", "))


@then(parsers.parse('the model never received "{text}"'))
def model_never_received(context, text):
    """La PII se redacta antes de llegar al proveedor."""
    assert text not in _received_text(context)


@then(parsers.parse("the model was called {count:d} times"))
def model_called(context, count):
    """``model_calls`` cuenta todas las llamadas (Specialist y Reviewer)."""
    assert len(context["recorder"].calls) == count
    assert _last(context).json()["model_calls"] == count


@then("the model was never called")
def model_never_called(context):
    """Una petición bloqueada no llega al proveedor."""
    assert context["recorder"].calls == []


@then(parsers.parse('the error detail is "{detail}"'))
def error_detail(context, detail):
    """El cuerpo de error trae el ``detail`` fijo de la API."""
    assert _last(context).json()["detail"] == detail
