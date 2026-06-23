FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV SCRAPER_BROWSER=playwright

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen
RUN uv run playwright install --with-deps chromium

COPY . .

CMD ["uv", "run", "python", "main.py", "run", "--quiet"]
