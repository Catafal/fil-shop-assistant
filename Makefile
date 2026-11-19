.PHONY: install check check-python check-web build demo run
install:
	uv sync --locked
	npm --prefix web ci
check: check-python check-web
check-python:
	uv run --locked ruff check src tests scripts
	uv run --locked pytest
check-web:
	npm --prefix web test
	npm --prefix web run build
build:
	npm --prefix web run build
demo:
	uv run --locked python scripts/guided_demo.py
run:
	uv run --locked uvicorn fil_shop.main:app --factory --host 127.0.0.1 --port 8000 --env-file .env --no-proxy-headers
