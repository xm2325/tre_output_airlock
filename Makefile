.PHONY: install backend frontend lint typecheck test benchmark openapi migration audit validate run docker clean

install:
	cd backend && python -m pip install -e '.[dev]'
	cd frontend && npm install --no-audit --no-fund

backend:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev -- --host 0.0.0.0

lint:
	cd backend && python -m ruff check app tests alembic

typecheck:
	cd backend && python -m mypy app
	cd frontend && npm run typecheck

test:
	cd backend && python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=90
	cd frontend && npm test
	cd frontend && npm run build

benchmark:
	cd backend && PYTHONPATH=. python -m app.evaluation --manifest ../benchmark/manifest.json --samples ../samples --output ../benchmark/results.json

openapi:
	cd backend && PYTHONPATH=. python ../scripts/export_openapi.py --output ../docs/openapi.generated.json

migration:
	cd backend && alembic upgrade head

audit:
	cd frontend && npm audit --audit-level=high
	cd backend && python -m pip_audit

validate: lint typecheck test benchmark openapi audit

docker:
	docker compose up --build

run: docker

clean:
	rm -rf backend/.pytest_cache backend/.ruff_cache backend/.mypy_cache backend/.coverage
	rm -rf backend/data backend/quarantine frontend/dist frontend/node_modules
