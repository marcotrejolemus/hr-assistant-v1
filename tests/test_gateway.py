"""Pruebas de ``GatewayLanguageModel`` con ``httpx.MockTransport`` (sin red real).

Las credenciales son ficticias y se arman por partes.
"""

import asyncio
import json

import httpx
import pytest
from doubles import AUTH_HEADERS, SIMPLE_QUESTION, SMALL_MODEL
from fastapi.testclient import TestClient

from app.config import load_settings
from app.llm import GatewayLanguageModel
from app.main import create_app

ACCOUNT = "cuenta-de-prueba"
GATEWAY = "gw-prueba"
TOKEN = "-".join(["token", "ficticio", "de", "prueba"])
GATEWAY_ENVIRON = {
    "MODEL_PROVIDER": "gateway",
    "CF_ACCOUNT_ID": ACCOUNT,
    "CF_GATEWAY_ID": GATEWAY,
    "CF_API_TOKEN": TOKEN,
}
EXPECTED_URL = (
    f"https://gateway.ai.cloudflare.com/v1/{ACCOUNT}/{GATEWAY}"
    "/workers-ai/v1/chat/completions"
)
MESSAGES = [{"role": "user", "content": SIMPLE_QUESTION}]


def _reply(text="{}", headers=None):
    """Respuesta del gateway con el formato de chat completions y ``usage``."""
    body = {
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 5},
    }
    return httpx.Response(200, json=body, headers=headers or {})


def _complete(settings, handler):
    """Hace una llamada al gateway con el transporte simulado."""

    async def call():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            model = GatewayLanguageModel(settings=settings, client=client)
            return await model.complete(MESSAGES, model=SMALL_MODEL, max_tokens=77)

    return asyncio.run(call())


def test_gateway_sends_the_documented_request_and_reads_usage(make_settings):
    settings = make_settings(**GATEWAY_ENVIRON)
    seen = []

    def handler(request):
        seen.append(request)
        return _reply('{"answer": "hola"}')

    completion = _complete(settings, handler)

    request = seen[0]
    assert str(request.url) == EXPECTED_URL
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert "cf-aig-cache-ttl" not in request.headers
    assert json.loads(request.content) == {
        "model": SMALL_MODEL,
        "messages": MESSAGES,
        "max_tokens": 77,
        "temperature": 0,
    }
    assert completion.text == '{"answer": "hola"}'
    assert (completion.input_tokens, completion.output_tokens) == (12, 5)
    assert completion.cached is False
    assert TOKEN not in repr(settings)


@pytest.mark.parametrize(("status", "cached"), [("HIT", True), ("MISS", False)])
def test_gateway_sends_the_cache_header_and_counts_a_hit_as_cached(
    make_settings, status, cached
):
    settings = make_settings(**GATEWAY_ENVIRON, CACHE_TTL_SECONDS="60")
    seen = []

    def handler(request):
        seen.append(request)
        return _reply(headers={"cf-aig-cache-status": status})

    completion = _complete(settings, handler)

    assert seen[0].headers["cf-aig-cache-ttl"] == "60"
    assert completion.cached is cached


def _server_error(request):
    """El gateway responde con un error del proveedor."""
    del request
    return httpx.Response(500, json={"error": "upstream failure"})


def _timeout(request):
    """El gateway no responde a tiempo."""
    raise httpx.ReadTimeout("timed out", request=request)


def _connection_refused(request):
    """No hay conexión con el gateway."""
    raise httpx.ConnectError("connection refused", request=request)


@pytest.mark.parametrize("handler", [_server_error, _timeout, _connection_refused])
def test_gateway_failure_or_timeout_returns_502(make_settings, directory, handler):
    settings = make_settings(**GATEWAY_ENVIRON)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    model = GatewayLanguageModel(settings=settings, client=client)
    app = create_app(settings=settings, model=model, directory=directory)

    response = TestClient(app, headers=AUTH_HEADERS).post(
        "/ask", json={"question": SIMPLE_QUESTION}
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "model unavailable"
    assert response.json()["request_id"]
    assert TOKEN not in response.text


@pytest.mark.parametrize(
    ("variable", "value"),
    [("CF_ACCOUNT_ID", None), ("CF_API_TOKEN", None), ("CF_GATEWAY_ID", "  ")],
)
def test_gateway_without_a_cloudflare_variable_refuses_to_start(variable, value):
    environ = dict(GATEWAY_ENVIRON)
    if value is None:
        del environ[variable]
    else:
        environ[variable] = value

    with pytest.raises(ValueError) as error:
        load_settings(environ)

    message = str(error.value)
    assert variable in message
    assert TOKEN not in message
    assert ACCOUNT not in message
