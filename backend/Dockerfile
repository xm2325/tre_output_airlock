FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml alembic.ini entrypoint.sh ./
COPY alembic ./alembic
COPY app ./app
RUN pip install --no-cache-dir . && chmod +x /app/entrypoint.sh && mkdir -p /app/data /app/quarantine
EXPOSE 8000
CMD ["/app/entrypoint.sh"]
