"""Pruebas del agregador de métricas y de ``GET /metrics``.

Los percentiles se calculan sobre una ventana acotada de latencias; los datos de
las pruebas dan el mismo resultado con rango más cercano o con interpolación.
"""

import os
import threading

import pytest

from app.metrics import Metrics

THREADS = 8
ROUNDS = 500


def test_latency_percentiles_come_from_the_recorded_requests():
    metrics = Metrics(slo_p95_ms=2000)

    for latency in [10] * 40 + [20] * 50 + [1000] * 10:
        metrics.record_request(200, latency)

    assert metrics.snapshot()["latency_ms"] == {"p50": 20, "p95": 1000}


def test_old_latencies_leave_the_bounded_window():
    metrics = Metrics(slo_p95_ms=2000, window_size=10)

    for latency in [5000] * 10 + [5] * 10:
        metrics.record_request(200, latency)

    snapshot = metrics.snapshot()
    assert snapshot["latency_ms"] == {"p50": 5, "p95": 5}
    assert snapshot["requests"] == 20


@pytest.mark.parametrize(("latency", "met"), [(1999, True), (2000, False)])
def test_slo_is_met_only_below_the_p95_target(latency, met):
    metrics = Metrics(slo_p95_ms=2000)

    metrics.record_request(200, latency)

    assert metrics.snapshot()["slo"] == {"p95_ms_target": 2000, "met": met}


def test_error_rate_counts_server_errors_and_errors_are_grouped_by_type():
    metrics = Metrics(slo_p95_ms=2000)

    for status in (200, 200, 422, 500, 502, 503):
        metrics.record_request(status, 1)
    for error_type in ("ModelUnavailableError", "ModelUnavailableError", "KeyError"):
        metrics.record_error(error_type)

    snapshot = metrics.snapshot()
    assert snapshot["error_rate"] == 0.5
    assert snapshot["errors_by_type"] == {"ModelUnavailableError": 2, "KeyError": 1}


def test_counters_stay_exact_with_concurrent_threads():
    metrics = Metrics(slo_p95_ms=2000)
    barrier = threading.Barrier(THREADS)

    def work():
        barrier.wait()
        for _ in range(ROUNDS):
            metrics.record_request(200, 1.0)
            metrics.record_usage(input_tokens=2, output_tokens=3, model_calls=1)

    threads = [threading.Thread(target=work) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    snapshot = metrics.snapshot()
    total = THREADS * ROUNDS
    assert snapshot["requests"] == total
    assert snapshot["tokens"] == {"input": 2 * total, "output": 3 * total}
    assert snapshot["model_calls"] == total


def test_metrics_endpoint_reports_this_app_without_request_ids(make_observed_client):
    client = make_observed_client()
    body = client.post(
        "/ask",
        json={"question": "¿Quién es EMP-0004?"},
        headers={"X-Request-ID": "metrics-req-1"},
    ).json()

    response = client.get("/metrics")

    metrics = response.json()
    assert metrics["pid"] == os.getpid()
    assert metrics["requests"] >= 1
    assert metrics["tokens"] == {
        "input": body["input_tokens"],
        "output": body["output_tokens"],
    }
    assert metrics["model_calls"] == body["model_calls"]
    assert metrics["slo"] == {"p95_ms_target": 2000, "met": True}
    assert "metrics-req-1" not in response.text
    other = make_observed_client().get("/metrics").json()
    assert other["tokens"] == {"input": 0, "output": 0}
