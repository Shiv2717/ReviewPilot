.PHONY: dev test lint typecheck eval migrate pre-commit install

install:
	uv pip install -e ".[dev]"
	pre-commit install || true

dev:
	uvicorn app.main:app --host $${API_HOST:-0.0.0.0} --port $${API_PORT:-8000} --reload

worker:
	python -m app.services.worker

test:
	pytest -q --cov=app --cov-report=term-missing

lint:
	ruff check app agents tests
	ruff format --check app agents tests

format:
	ruff check --fix app agents tests
	ruff format app agents tests

typecheck:
	mypy --strict app agents

eval:
	python -m evals.runner

migrate:
	alembic upgrade head

pre-commit:
	pre-commit run --all-files

ci: lint typecheck test
