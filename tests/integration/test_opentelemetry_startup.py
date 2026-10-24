"""The production server starts under `opentelemetry-instrument` (NEU-1599).

`start.sh` runs `opentelemetry-instrument uvicorn main:app --workers 2`. These tests start
that same command in a subprocess, because what can break is the wrapper itself: an
instrumentation that fails to import, or a worker that dies under it, never shows up in a
TestClient run.
"""

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from opentelemetry.instrumentation.sqlalchemy import (
    package as sqlalchemy_instrumentation,
)
from packaging.requirements import Requirement

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENTELEMETRY_INSTRUMENT = Path(sys.executable).parent / "opentelemetry-instrument"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def _serve(tmp_path: Path, otel_env: dict[str, str]) -> Iterator[tuple[str, list[str]]]:
    """Run the production command until the block exits; yield its base URL and a list
    that holds the process's combined output once it has stopped."""
    port = _free_port()
    env = {
        **os.environ,
        # `opentelemetry-instrument` finds `uvicorn` on PATH, as Dockerfile.prod arranges.
        "PATH": f"{OPENTELEMETRY_INSTRUMENT.parent}{os.pathsep}{os.environ.get('PATH', '')}",
        "APP_DATABASE_URL": f"sqlite:///{tmp_path / 'smoke.db'}",
        "APP_JWT_SECRET": "0123456789abcdef0123456789abcdef",
        "APP_SENTRY_DSN": "",
        **otel_env,
    }
    proc = subprocess.Popen(
        [
            str(OPENTELEMETRY_INSTRUMENT),
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--workers",
            "2",
        ],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    output: list[str] = []
    try:
        yield f"http://127.0.0.1:{port}", output
    finally:
        proc.terminate()
        try:
            out, _ = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
        output.append(out)


def _wait_healthy(base_url: str) -> httpx.Response:
    deadline = time.monotonic() + 30
    while True:
        try:
            return httpx.get(f"{base_url}/health", timeout=2)
        except httpx.TransportError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.2)


def test_the_app_serves_under_opentelemetry_instrument_with_the_sdk_disabled(tmp_path):
    """The dev image's default, and the one a deploy falls back to without a collector:
    the wrapper must be inert, not fatal."""
    with _serve(tmp_path, {"OTEL_SDK_DISABLED": "true"}) as (base_url, _):
        assert _wait_healthy(base_url).status_code == 200


def _serve_traced(tmp_path: Path) -> str:
    """Serve one `/health` request with the SDK on and return everything the process
    printed. The console exporters stand in for the collector, so nothing needs a
    network."""
    otel_env = {
        "OTEL_SDK_DISABLED": "false",
        "OTEL_TRACES_EXPORTER": "console",
        "OTEL_LOGS_EXPORTER": "console",
        "OTEL_METRICS_EXPORTER": "none",
        "OTEL_SERVICE_NAME": "boone-gifts-backend",
        # Export promptly instead of on the default 5s timer, so a span is out well
        # before the process is stopped.
        "OTEL_BSP_SCHEDULE_DELAY": "100",
        "OTEL_BLRP_SCHEDULE_DELAY": "100",
    }
    with _serve(tmp_path, otel_env) as (base_url, output):
        assert _wait_healthy(base_url).status_code == 200
        time.sleep(1)

    [out] = output
    return out


def test_a_request_produces_a_trace(tmp_path):
    out = _serve_traced(tmp_path)
    assert '"name": "GET /health"' in out


def test_an_app_log_record_is_exported_with_its_trace_id(tmp_path):
    """The logs half of the contract: under the wrapper, a record logged inside a span
    reaches the logs exporter carrying that span's trace id (the handler is on by default
    since OpenTelemetry Python 1.40).

    Not asserted through the server, because nothing on a healthy request logs at
    WARNING -- the app sets no logging level, so the root logger's WARNING decides what
    reaches the handler, and uvicorn's own loggers do not propagate to the root at all.
    """
    script = (
        "import logging, main\n"
        "from opentelemetry import trace\n"
        "with trace.get_tracer('smoke').start_as_current_span('smoke') as span:\n"
        "    logging.getLogger('app.smoke').warning('smoke-log-record')\n"
        "    print('TRACE_ID=0x%032x' % span.get_span_context().trace_id)\n"
    )
    env = {
        **os.environ,
        "APP_DATABASE_URL": f"sqlite:///{tmp_path / 'smoke.db'}",
        "APP_JWT_SECRET": "0123456789abcdef0123456789abcdef",
        "APP_SENTRY_DSN": "",
        "OTEL_SDK_DISABLED": "false",
        "OTEL_TRACES_EXPORTER": "none",
        "OTEL_METRICS_EXPORTER": "none",
        "OTEL_LOGS_EXPORTER": "console",
    }
    result = subprocess.run(
        [str(OPENTELEMETRY_INSTRUMENT), sys.executable, "-c", script],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )

    [trace_id] = [
        line.removeprefix("TRACE_ID=")
        for line in result.stdout.splitlines()
        if line.startswith("TRACE_ID=")
    ]
    assert trace_id != "0x" + "0" * 32
    assert '"body": "smoke-log-record"' in result.stdout
    assert f'"trace_id": "{trace_id}"' in result.stdout


def test_the_health_check_query_is_a_span(tmp_path):
    """The SQLAlchemy instrumentation skips itself on a version outside its supported
    range, silently -- this is what notices."""
    out = _serve_traced(tmp_path)
    assert '"db.system": "sqlite"' in out or '"db.system.name": "sqlite"' in out


@pytest.mark.xfail(
    strict=True,
    reason="opentelemetry-instrumentation-sqlalchemy 0.66b1 supports only sqlalchemy<2.1, "
    "so pyproject.toml caps sqlalchemy below 2.1. Upstream contrib #5120 (merged "
    "2026-10-14) lifts the cap to <2.2; once a release with it lands this passes, and CI "
    "fails until the sqlalchemy cap, its Dependabot ignore and this test are removed.",
)
def test_the_sqlalchemy_instrumentation_supports_sqlalchemy_2_1():
    [requirement] = [
        Requirement(spec) for spec in sqlalchemy_instrumentation._instruments
    ]
    assert requirement.specifier.contains("2.1.0")
