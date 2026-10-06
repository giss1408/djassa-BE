#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# start db and redis
docker compose -f docker-compose.dev.yml up -d db redis

# create venv and install
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# migrations
export DATABASE_URL=postgresql+asyncpg://hossouko:hossouko@127.0.0.1:5432/hossouko
alembic -c alembic.ini upgrade head

# run server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
