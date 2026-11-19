FROM node:24-bookworm-slim AS web
WORKDIR /build/web
COPY web/package*.json ./
RUN npm ci
COPY web/src/ ./src/
COPY web/public/ ./public/
COPY web/index.html web/tsconfig.json web/vite.config.ts ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.14 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src/ src/
RUN uv sync --locked --no-dev
COPY --from=web /build/web/dist /app/web/dist
RUN useradd --create-home fil && mkdir /app/data && chown fil:fil /app/data
USER fil
ENV FIL_DB_PATH=/app/data/fil.sqlite
EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "fil_shop.main:app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
