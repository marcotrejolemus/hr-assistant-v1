"""Pruebas de la configuración leída de variables de entorno."""

from pathlib import Path

import pytest

from app.config import load_settings


def test_defaults_are_used_when_the_environment_is_empty():
    settings = load_settings({})

    assert settings.model_provider == "fake"
    assert settings.agent_max_steps == 3
    assert settings.max_question_chars == 2000
    assert Path(settings.employees_path) == Path("data/employees.json")


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("AGENT_MAX_STEPS", "0"),
        ("AGENT_MAX_STEPS", "-2"),
        ("AGENT_MAX_STEPS", "three"),
        ("MAX_QUESTION_CHARS", "0"),
        ("MODEL_PROVIDER", "openai"),
    ],
)
def test_invalid_value_is_rejected_with_a_clear_message(variable, value):
    with pytest.raises(ValueError) as error:
        load_settings({variable: value})

    assert variable in str(error.value)


def test_new_limits_have_documented_defaults():
    settings = load_settings({})

    assert settings.reviewer_max_calls == 1
    assert settings.max_model_calls_per_request == 4
    assert settings.model_max_tokens == 300
    assert settings.request_input_token_budget == 4000
    assert settings.model_timeout_seconds == 15
    assert settings.request_timeout_seconds == 30
    assert settings.max_history_messages == 50
    assert settings.max_answer_chars == 4000
    assert settings.model_small == "@cf/meta/llama-3.1-8b-instruct-fast"
    assert settings.model_large == "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    assert settings.fake_model_fail is False
    assert settings.fake_reviewer_verdict == "approve"
    assert settings.fake_reviewer_fail is False


@pytest.mark.parametrize(
    ("environ", "variable"),
    [
        ({"REVIEWER_MAX_CALLS": "0"}, "REVIEWER_MAX_CALLS"),
        ({"MAX_MODEL_CALLS_PER_REQUEST": "3"}, "MAX_MODEL_CALLS_PER_REQUEST"),
        ({"AGENT_MAX_STEPS": "4"}, "MAX_MODEL_CALLS_PER_REQUEST"),
        ({"MODEL_MAX_TOKENS": "0"}, "MODEL_MAX_TOKENS"),
        ({"REQUEST_INPUT_TOKEN_BUDGET": "many"}, "REQUEST_INPUT_TOKEN_BUDGET"),
        ({"MODEL_TIMEOUT_SECONDS": "0"}, "MODEL_TIMEOUT_SECONDS"),
        ({"REQUEST_TIMEOUT_SECONDS": "-1"}, "REQUEST_TIMEOUT_SECONDS"),
        ({"MAX_HISTORY_MESSAGES": "0"}, "MAX_HISTORY_MESSAGES"),
        ({"MAX_ANSWER_CHARS": "0"}, "MAX_ANSWER_CHARS"),
        ({"MODEL_SMALL": "  "}, "MODEL_SMALL"),
        ({"FAKE_REVIEWER_VERDICT": "maybe"}, "FAKE_REVIEWER_VERDICT"),
    ],
)
def test_invalid_limit_names_the_variable(environ, variable):
    """El presupuesto de llamadas debe cubrir al Specialist más el Reviewer."""
    with pytest.raises(ValueError) as error:
        load_settings(environ)

    assert variable in str(error.value)


def test_observability_settings_have_safe_defaults():
    settings = load_settings({})

    assert settings.service_name == "hr-assistant"
    assert settings.slo_p95_ms == 2000
    assert settings.langsmith_tracing is False
    assert settings.langsmith_project == "hr-assistant-v1"
    assert settings.hide_inputs is True
    assert settings.hide_outputs is True


def test_invalid_slo_target_names_the_variable():
    with pytest.raises(ValueError) as error:
        load_settings({"SLO_P95_MS": "fast"})

    assert "SLO_P95_MS" in str(error.value)


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("FAKE_MODEL_FAIL", "true"),
        ("FAKE_REVIEWER_VERDICT", "reject"),
        ("FAKE_REVIEWER_FAIL", "true"),
    ],
)
def test_fake_switches_require_the_fake_provider(variable, value):
    """Con otro proveedor, el error nombra el ``FAKE_*`` (se valida antes que él)."""
    load_settings({"MODEL_PROVIDER": "fake", variable: value})

    with pytest.raises(ValueError) as error:
        load_settings({"MODEL_PROVIDER": "gateway", variable: value})

    assert variable in str(error.value)
