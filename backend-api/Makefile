PY=python3
VENV=.venv

.PHONY: venv install up down migrate run worker

.PHONY: start-monitoring start-all

venv:
	$(PY) -m venv $(VENV)

install: venv
	. $(VENV)/bin/activate && pip install --upgrade pip && pip install -r requirements.txt

up:
	docker compose -f docker-compose.dev.yml up -d db redis

down:
	docker compose -f docker-compose.dev.yml down

migrate:
	. $(VENV)/bin/activate && export DATABASE_URL=postgresql+asyncpg://fidelia:fidelia@127.0.0.1:5432/fidelia && alembic -c alembic.ini upgrade head

run:
	. $(VENV)/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	. $(VENV)/bin/activate && export CELERY_BROKER_URL=redis://127.0.0.1:6379/0 && celery -A app.celery_app.celery_app worker --loglevel=info

start-monitoring:
	# Start only monitoring stack (uses templates in ../monitoring)
	bash ../scripts/start-monitoring.sh

start-all:
	# Build backend image for local arch and start all services (db, redis, api, monitoring)
	bash ../scripts/start-all.sh
