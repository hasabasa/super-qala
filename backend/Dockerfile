FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml ./
ARG INSTALL_DEV=true
RUN uv pip install --system --no-cache -r pyproject.toml && \
    if [ "$INSTALL_DEV" = "true" ]; then \
      uv pip install --system --no-cache pytest pytest-asyncio ruff mypy; \
    fi

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
