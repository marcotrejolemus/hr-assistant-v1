"""Pruebas de observabilidad: log JSON, auditoría, etapas y trazas a prueba de fallos.

Usan un reloj fijo y capturan el log con un ``log_sink`` inyectado; nunca abren
conexiones de red (las fábricas de clientes de trazas son dobles).
"""

from datetime import datetime

import pytest
from doubles import (
    FIXED_NOW,
    TELEMETRY_FAILURE,
    ExplodingTraceClient,
    FixedClock,
    RecordingClientFactory,
    log_text,
    read_events,
)

from app.observability import JsonLogger, build_tracer

QUESTION = "¿Quién es EMP-0004?"
ANSWER_NAME = "Jorge Díaz"
PRIVATE_HISTORY = "Mensaje previo privado"
FAKE_TRACE_KEY = "clave-ficticia-de-prueba"
LOG_FIELDS = {"ts", "service", "event", "request_id"}
STAGES = ["input_guard", "directory_specialist", "reviewer_agent", "output_guard"]


def _logger(lines):
    """Logger JSON con reloj fijo que escribe en ``lines``."""
    return JsonLogger(service="hr-test", clock=FixedClock(), sink=lines.append)


def _pick(record, keys):
    """Subconjunto de un registro, para comparar solo los campos documentados."""
    return {key: record[key] for key in keys}


def test_request_log_line_has_the_documented_fields_with_a_fixed_clock(
    make_observed_client, log_lines
):
    client = make_observed_client(SERVICE_NAME="hr-assistant-test")

    client.get("/health", headers={"X-Request-ID": "log-1"})

    assert log_lines
    assert all("\n" not in line for line in log_lines)
    for record in read_events(log_lines):
        assert LOG_FIELDS <= record.keys()
        assert record["service"] == "hr-assistant-test"
        assert datetime.fromisoformat(record["ts"]) == FIXED_NOW
    (request,) = read_events(log_lines, "request")
    keys = ("request_id", "method", "path", "status", "latency_ms")
    assert _pick(request, keys) == {
        "request_id": "log-1",
        "method": "GET",
        "path": "/health",
        "status": 200,
        "latency_ms": 0,
    }


def test_agent_run_is_logged_without_the_question_or_the_answer(
    make_observed_client, log_lines
):
    history = [{"role": "user", "content": PRIVATE_HISTORY}]

    response = make_observed_client().post(
        "/ask", json={"question": QUESTION, "history": history}
    )

    body = response.json()
    (run,) = read_events(log_lines, "agent_run")
    keys = (
        "request_id",
        "question_chars",
        "history_messages",
        "steps",
        "tools",
        "input_tokens",
        "output_tokens",
        "stopped",
    )
    assert _pick(run, keys) == {
        "request_id": response.headers["X-Request-ID"],
        "question_chars": len(QUESTION),
        "history_messages": 1,
        "steps": 2,
        "tools": ["get_employee"],
        "input_tokens": body["input_tokens"],
        "output_tokens": body["output_tokens"],
        "stopped": False,
    }
    text = log_text(log_lines)
    for private in (QUESTION, PRIVATE_HISTORY, ANSWER_NAME):
        assert private not in text


def test_each_tool_call_is_audited_with_its_arguments_only(
    make_observed_client, log_lines
):
    response = make_observed_client().post(
        "/ask", json={"question": "¿Quiénes trabajan en Finanzas?"}
    )

    audits = [
        record
        for record in read_events(log_lines, "audit")
        if record["action"] == "tool_call"
    ]
    assert len(audits) == 1
    keys = ("request_id", "action", "outcome", "tool", "args")
    assert _pick(audits[0], keys) == {
        "request_id": response.headers["X-Request-ID"],
        "action": "tool_call",
        "outcome": "ok",
        "tool": "search_by_department",
        "args": {"department": "Finanzas"},
    }
    assert "Sofía Gómez" not in log_text(log_lines)


def test_each_stage_is_logged_in_order_with_duration_and_status(
    make_observed_client, log_lines
):
    response = make_observed_client().post("/ask", json={"question": QUESTION})

    stages = read_events(log_lines, "stage")
    assert [stage["stage"] for stage in stages] == STAGES
    for stage in stages:
        assert stage["request_id"] == response.headers["X-Request-ID"]
        assert stage["status"] == "ok"
        assert stage["duration_ms"] == 0


@pytest.mark.parametrize(
    "environ",
    [{"LANGSMITH_TRACING": "true"}, {"LANGSMITH_API_KEY": FAKE_TRACE_KEY}],
    ids=["flag_without_key", "key_without_flag"],
)
def test_tracing_stays_off_without_both_the_flag_and_the_key(make_settings, environ):
    """Sin bandera y clave no se crea el cliente: no hay red."""
    factory = RecordingClientFactory()

    tracer = build_tracer(make_settings(**environ), _logger([]), client_factory=factory)

    assert tracer.enabled is False
    assert not factory.calls


@pytest.mark.parametrize(
    ("environ", "hidden"),
    [({}, True), ({"HIDE_INPUTS": "false", "HIDE_OUTPUTS": "false"}, False)],
    ids=["safe_defaults", "explicitly_shown"],
)
def test_hide_flags_are_applied_to_the_langsmith_client(
    make_settings, environ, hidden
):
    factory = RecordingClientFactory()
    settings = make_settings(
        LANGSMITH_TRACING="true", LANGSMITH_API_KEY=FAKE_TRACE_KEY, **environ
    )

    tracer = build_tracer(settings, _logger([]), client_factory=factory)

    assert tracer.enabled is True
    assert len(factory.calls) == 1
    assert _pick(factory.calls[0], ("api_key", "hide_inputs", "hide_outputs")) == {
        "api_key": FAKE_TRACE_KEY,
        "hide_inputs": hidden,
        "hide_outputs": hidden,
    }


def test_a_failing_trace_client_never_breaks_the_answer(
    make_observed_client, log_lines
):
    client = make_observed_client(
        trace_client_factory=RecordingClientFactory(ExplodingTraceClient()),
        LANGSMITH_TRACING="true",
        LANGSMITH_API_KEY=FAKE_TRACE_KEY,
    )

    response = client.post("/ask", json={"question": QUESTION})

    assert response.status_code == 200
    assert ANSWER_NAME in response.json()["answer"]
    failures = read_events(log_lines, "telemetry_error")
    assert failures
    assert {failure["error_type"] for failure in failures} == {"RuntimeError"}
    text = log_text(log_lines)
    assert TELEMETRY_FAILURE not in text
    assert FAKE_TRACE_KEY not in text
