# Enkel och tydlig Makefile för lokal körning
# Antag att du redan har kört:
#   uv venv --python python3.13
#   source .venv/bin/activate

PYTHON ?= python
APP_MODULE ?= app.main:app
HOST ?= 0.0.0.0
PORT ?= 8000

.PHONY: install dev run lint fmt test clean

install:
	uv pip install --upgrade pip
	uv pip install -r requirements.txt

dev:
	uvicorn $(APP_MODULE) --reload --host $(HOST) --port $(PORT)

run:
	uvicorn $(APP_MODULE) --host $(HOST) --port $(PORT)

lint:
	ruff check .

fmt:
	ruff format .

test:
	pytest -q || true

clean:
	rm -rf __pycache__ .pytest_cache .ruff_cache
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete
