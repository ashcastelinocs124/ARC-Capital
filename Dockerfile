# The daily refresh + publish server on Fly.io (fly.toml). data/ is a persistent volume, not part of the image.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates tzdata \
 && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && npm install -g vercel \
 && curl -fsSLo /usr/local/bin/supercronic \
    https://github.com/aptible/supercronic/releases/download/v0.2.33/supercronic-linux-amd64 \
 && chmod +x /usr/local/bin/supercronic \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/app/.venv PATH=/app/.venv/bin:$PATH
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --python 3.12 --extra browser --no-install-project \
 && playwright install --with-deps chromium
COPY frontend/package.json frontend/package-lock.json frontend/
RUN cd frontend && npm ci

COPY . .
RUN uv sync --frozen --python 3.12 --extra browser \
 && mkdir -p seed-data && cp data/*.yaml data/*.csv seed-data/

CMD ["deploy/start.sh"]
