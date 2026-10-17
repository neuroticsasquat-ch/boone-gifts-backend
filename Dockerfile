FROM python:3.14-slim AS dev

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/opt/venv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .

ENV PATH="/opt/venv/bin:$PATH"

# The OpenTelemetry SDK is off in dev (NEU-1599): the dev server runs plain uvicorn with
# --reload, which auto-instrumentation does not survive, and there is no collector to
# export to. Set OTEL_SDK_DISABLED=false to try `opentelemetry-instrument` by hand.
ENV OTEL_SDK_DISABLED=true

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
