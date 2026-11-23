import os

from slowapi import Limiter

from .edge import client_ip

# One limiter for the whole app. Counted per caller address (app/edge.py: never
# the address the caller wrote itself). Counters live in RATE_LIMIT_STORAGE_URI
# (Render Key Value in production, so they survive deploys and are shared by
# every instance); in memory when unset (development, tests). If the store is
# unreachable, the limiter counts in memory until it is back rather than
# failing every request.
limiter = Limiter(
    key_func=client_ip,
    storage_uri=os.getenv("RATE_LIMIT_STORAGE_URI", "memory://"),
    in_memory_fallback_enabled=True,
    key_prefix="fidelia-rl",
)


def public_read_limit() -> str:
	"""Per-IP limit on the catalogue anyone can read without an account
	(offers, shops, pharmacies). Generous for a person scrolling, tight for a
	scraper. Read at request time so tests and operators can change it."""
	return os.getenv("PUBLIC_READ_RATE_LIMIT", "120/minute")

def exempt_for_internal_ips(app, internal_cidrs=None):
	"""Mark the app as exempt from rate limits for specific internal CIDRs.

	Usage: exempt_for_internal_ips(app, ["10.0.0.0/8"])
	"""
	# slowapi exposes a way to exempt routes; we attach a helper to app.state
	app.state._rate_limit_internal_cidrs = internal_cidrs or []
