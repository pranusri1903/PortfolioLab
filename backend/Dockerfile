FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
COPY app app
RUN pip install --no-cache-dir .
COPY alembic.ini .
COPY migrations migrations
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed --market-only && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
