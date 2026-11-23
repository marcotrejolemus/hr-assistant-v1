"""Pruebas de la API: inyección de dependencias y página web."""

import json

from app.llm import Completion

ORIGINAL_FIELDS = ("answer", "steps", "tools_used", "input_tokens", "output_tokens")


class FixedAnswerModel:  # pylint: disable=too-few-public-methods
    """Modelo de prueba que siempre responde lo mismo."""

    async def complete(self, messages, *, model, max_tokens):
        """Responde una frase fija sin pedir herramientas."""
        del messages, model, max_tokens
        return Completion(
            text=json.dumps({"answer": "Respuesta inyectada"}),
            input_tokens=1,
            output_tokens=2,
        )


def test_create_app_uses_the_injected_model(make_client):
    client = make_client(model=FixedAnswerModel())

    body = client.post("/ask", json={"question": "Hola"}).json()

    # El Reviewer también usa el modelo inyectado: los tokens suman todas las
    # llamadas, y cada llamada de este modelo cuesta 1 de entrada y 2 de salida.
    calls = body["model_calls"]
    assert {key: body[key] for key in ORIGINAL_FIELDS} == {
        "answer": "Respuesta inyectada",
        "steps": 1,
        "tools_used": [],
        "input_tokens": 1 * calls,
        "output_tokens": 2 * calls,
    }


def test_home_page_has_the_form_and_never_uses_inner_html(make_client):
    response = make_client().get("/")

    assert response.status_code == 200
    for test_id in ("question", "send", "answer"):
        assert f'data-testid="{test_id}"' in response.text
    assert "innerHTML" not in response.text
