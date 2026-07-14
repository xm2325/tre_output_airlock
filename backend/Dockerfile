FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

RUN python -m pip install --no-cache-dir uv==0.10.0
COPY pyproject.toml uv.lock alembic.ini entrypoint.sh ./
COPY alembic ./alembic
COPY app ./app
RUN uv sync --frozen --no-dev --no-editable \
    && chmod +x /app/entrypoint.sh \
    && mkdir -p /app/data /app/quarantine

EXPOSE 8000
CMD ["/app/entrypoint.sh"]
