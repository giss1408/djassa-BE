"""Hosted Postgres URLs are accepted as the provider shows them (app/db.py).

Render's free web service talks to Neon: pasting Neon's connection string into
DATABASE_URL must just work, including on its pooled (PgBouncer) endpoint.
"""

from app.db import normalize_database_url


def test_neon_direct_string_is_converted_for_asyncpg():
    url, args = normalize_database_url(
        "postgresql://u:p@ep-x-1.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    )
    assert url == "postgresql+asyncpg://u:p@ep-x-1.eu-central-1.aws.neon.tech/neondb?ssl=require"
    assert args == {}


def test_neon_pooled_endpoint_disables_the_prepared_statement_cache():
    url, args = normalize_database_url("postgresql://u:p@ep-x-1-pooler.neon.tech/neondb?sslmode=require")
    assert "ssl=require" in url and "prepared_statement_cache_size=0" in url
    assert args == {"statement_cache_size": 0}


def test_short_postgres_scheme_and_local_urls():
    assert normalize_database_url("postgres://u:p@h/db")[0] == "postgresql+asyncpg://u:p@h/db"
    local = "postgresql+asyncpg://hossouko:hossouko@127.0.0.1:5432/hossouko"
    assert normalize_database_url(local) == (local, {})
    assert normalize_database_url("sqlite+aiosqlite:///./test.db") == ("sqlite+aiosqlite:///./test.db", {})
