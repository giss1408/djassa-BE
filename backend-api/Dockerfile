# The Fidelia API image: what Render runs (test and production), what CI
# tests, and what docker-compose runs locally. The same image is the Celery
# worker, started with another command (render*.yaml `dockerCommand`).
FROM python:3.11-slim-bookworm
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create a non-root user and group
RUN groupadd -r app && useradd --no-log-init -r -g app app

# ffmpeg re-encodes shop videos for low bandwidth (app/services/media_processing.py),
# with ffprobe and security updates from the base image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# requirements.lock pins every package, including indirect ones: a new release
# reaches the image only through `make lock`.
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt -c requirements.lock

COPY ./app ./app
COPY ./alembic ./alembic
COPY ./alembic.ini ./alembic.ini

# Ensure files are owned by non-root user and switch
RUN chown -R app:app /app
USER app

# Render sets PORT; 8000 elsewhere.
# --proxy-headers: the scheme (https) from Render's proxy. The caller's address
#   is never taken from it: app/edge.py reads it from the right header.
# --no-access-log: uvicorn's access log prints query strings, which carry
#   phone numbers. The API writes its own access line (app/observability.py).
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*' --no-access-log"]
