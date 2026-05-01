# syntax=docker/dockerfile:1.7

# ----- builder: install deps into a user-local prefix --------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# psycopg[binary] bundles its native lib, so no system packages needed.
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ----- runtime: copy only what we need from the builder ------------------
FROM python:3.11-slim AS runtime

# Run as a non-root user. Cheap, prevents a class of container-escape bugs.
RUN useradd --create-home --uid 1000 app
WORKDIR /home/app

COPY --from=builder --chown=app:app /root/.local /home/app/.local
COPY --chown=app:app app ./app

ENV PATH="/home/app/.local/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app
EXPOSE 8000

# Liveness probe: hit /docs (cheap, served by FastAPI). 30s interval is the
# standard tradeoff between detection lag and noise.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://localhost:8000/docs',timeout=2).status==200 else 1)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
