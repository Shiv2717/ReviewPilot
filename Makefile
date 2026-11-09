.PHONY: dev worker test lint typecheck eval migrate pre-commit install ci format load-test

install:
	uv pip install -e ".[dev]"
	pre-commit install || true

dev:
	uvicorn app.main:app --host $${API_HOST:-0.0.0.0} --port $${API_PORT:-8000} --reload

worker:
	python -m app.services.worker

test:
	pytest -q --cov=app --cov=agents --cov-report=term-missing

lint:
	ruff check app agents evals tests
	ruff format --check app agents evals tests

format:
	ruff check --fix app agents evals tests
	ruff format app agents evals tests

typecheck:
	mypy --strict app agents evals

eval:
	python -m evals.runner

migrate:
	alembic upgrade head

pre-commit:
	pre-commit run --all-files

load-test:
	python scripts/load_test.py --count 50

ci: lint typecheck test eval
