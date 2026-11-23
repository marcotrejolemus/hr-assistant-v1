"""Pruebas de precios, costo por respuesta, caché y configuración de costos.

El costo de cada llamada sale del nombre del modelo pedido y de sus tokens, con
los precios de ``data/model_prices.json`` (USD por millón de tokens).
"""

from pathlib import Path

import pytest
from doubles import (
    COMPLEX_QUESTION,
    LARGE_MODEL,
    PRICES_PATH,
    SIMPLE_QUESTION,
    SMALL_MODEL,
    CachedModel,
    RecordingModel,
)

from app.config import load_settings
from app.costs import load_prices
from app.llm import FakeLanguageModel

# Valores ficticios armados por partes: no son credenciales.
FAKE_TOKEN = "-".join(["token", "ficticio", "de", "prueba"])
FAKE_API_KEY = "cliente:" + "k" * 24


@pytest.fixture
def prices():
    """Tabla de precios del producto."""
    return load_prices(PRICES_PATH)


@pytest.fixture
def fake_model(directory):
    """El modelo simulado con los departamentos de los datos."""
    return FakeLanguageModel(directory.departments())


def test_cost_uses_the_price_per_million_tokens(prices):
    one_million = prices.cost(
        SMALL_MODEL, input_tokens=1_000_000, output_tokens=1_000_000
    )
    large = prices.cost(LARGE_MODEL, input_tokens=2000, output_tokens=100)

    assert one_million == pytest.approx(0.045 + 0.384)
    assert large == pytest.approx((2000 * 0.293 + 100 * 2.253) / 1_000_000)
    assert prices.cost("fake", input_tokens=500, output_tokens=500) == 0


def test_answer_cost_adds_up_every_model_call(make_client, fake_model, prices):
    model = RecordingModel(fake_model)

    body = make_client(model=model).post(
        "/ask", json={"question": SIMPLE_QUESTION}
    ).json()

    expected = sum(
        prices.cost(
            call["model"],
            input_tokens=call["completion"].input_tokens,
            output_tokens=call["completion"].output_tokens,
        )
        for call in model.calls
    )
    assert body["model_calls"] == len(model.calls) == 3
    assert body["cost_usd"] > 0
    assert body["cost_usd"] == pytest.approx(expected)
    assert body["cached_calls"] == 0


def test_cached_calls_are_counted_and_cost_nothing(make_client, fake_model):
    body = make_client(model=CachedModel(fake_model)).post(
        "/ask", json={"question": SIMPLE_QUESTION}
    ).json()

    assert body["cached_calls"] == body["model_calls"] == 3
    assert body["cost_usd"] == 0


def test_a_configured_model_without_price_prevents_startup(make_app):
    with pytest.raises(ValueError) as error:
        make_app(MODEL_LARGE="@cf/vendor/model-without-price")

    assert "MODEL_LARGE" in str(error.value)


def test_metrics_report_cost_by_model_and_requests_by_route(make_client):
    client = make_client()
    answers = [
        client.post("/ask", json={"question": question}).json()
        for question in (SIMPLE_QUESTION, COMPLEX_QUESTION)
    ]

    metrics = client.get("/metrics").json()

    total = sum(answer["cost_usd"] for answer in answers)
    by_model = metrics["cost_estimated_usd_by_model"]
    assert metrics["cost_usd"] == pytest.approx(total)
    assert by_model[SMALL_MODEL] > 0
    assert by_model[LARGE_MODEL] > 0
    assert sum(by_model.values()) == pytest.approx(total)
    assert metrics["requests_by_route"]["simple"] == 1
    assert metrics["requests_by_route"]["complex_keyword"] == 1
    assert metrics["cost_billed"] == "not_available"


def test_cost_settings_have_documented_defaults():
    settings = load_settings({})

    assert settings.routing is True
    assert settings.router_max_chars == 80
    assert settings.history_window == 6
    assert settings.model_temperature == 0
    assert settings.cache_ttl_seconds == 0
    assert Path(settings.prices_path) == Path("data/model_prices.json")
    assert settings.cf_gateway_id == "default"
    assert not settings.cf_account_id
    assert not settings.cf_api_token
    # La línea base de ``verification evaluate`` usa una ventana "sin límite".
    assert load_settings({"HISTORY_WINDOW": "1000"}).history_window == 1000


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("ROUTING", "maybe"),
        ("ROUTER_MAX_CHARS", "0"),
        ("HISTORY_WINDOW", "-1"),
        ("MODEL_TEMPERATURE", "hot"),
        ("CACHE_TTL_SECONDS", "-5"),
    ],
)
def test_invalid_cost_setting_names_the_variable(variable, value):
    with pytest.raises(ValueError) as error:
        load_settings({variable: value})

    assert variable in str(error.value)


def test_gateway_cache_is_refused_in_production():
    """Regla aprobada (ADR 0006): la caché no aísla por cliente."""
    environ = {
        "MODEL_PROVIDER": "gateway",
        "CF_ACCOUNT_ID": "cuenta-de-prueba",
        "CF_GATEWAY_ID": "gw-prueba",
        "CF_API_TOKEN": FAKE_TOKEN,
        "API_KEYS": FAKE_API_KEY,
        "CACHE_TTL_SECONDS": "60",
    }

    development = load_settings({**environ, "ENVIRONMENT": "development"})
    with pytest.raises(ValueError) as error:
        load_settings({**environ, "ENVIRONMENT": "production"})

    assert development.cache_ttl_seconds == 60
    assert "CACHE_TTL_SECONDS" in str(error.value)
    assert FAKE_TOKEN not in str(error.value)
