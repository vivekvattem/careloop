FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN python -m pip install --upgrade pip && python -m pip wheel --wheel-dir /wheels .

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/careloop/.local/bin:${PATH}"
WORKDIR /app
RUN addgroup --system careloop && adduser --system --ingroup careloop careloop
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/* && rm -rf /wheels
COPY --chown=careloop:careloop backend/app ./app
COPY --chown=careloop:careloop backend/alembic ./alembic
COPY --chown=careloop:careloop backend/alembic.ini ./alembic.ini
USER careloop
EXPOSE 8000
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
