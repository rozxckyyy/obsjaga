FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 dorm \
    && useradd --uid 10001 --gid dorm --no-create-home dorm

COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY app/ ./app/
COPY --chmod=755 docker-entrypoint.sh /usr/local/bin/dorm-entrypoint

USER dorm
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/dorm-entrypoint"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
