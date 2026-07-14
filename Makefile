.PHONY: install backend frontend lint typecheck test benchmark openapi migration audit validate run docker clean

install:
	cd backend && uv sync --frozen --all-extras
	cd frontend && npm ci

backend:
	cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev -- --host 0.0.0.0

lint:
	cd backend && uv run ruff check app tests alembic

typecheck:
	cd backend && uv run mypy app
	cd frontend && npm run typecheck

test:
	cd backend && uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=90
	cd frontend && npm test
	cd frontend && npm run build

benchmark:
	cd backend && PYTHONPATH=. uv run python -m app.evaluation --manifest ../benchmark/manifest.json --samples ../samples --output ../benchmark/results.json

openapi:
	cd backend && PYTHONPATH=. uv run python ../scripts/export_openapi.py

migration:
	cd backend && uv run alembic upgrade head

audit:
	cd frontend && npm audit --audit-level=high
	cd backend && uv run pip-audit

validate: lint typecheck test benchmark openapi audit

docker:
	docker compose up --build

run: docker

clean:
	rm -rf backend/.pytest_cache backend/.ruff_cache backend/.mypy_cache backend/.coverage backend/.venv
	rm -rf backend/data backend/quarantine frontend/dist frontend/node_modules
