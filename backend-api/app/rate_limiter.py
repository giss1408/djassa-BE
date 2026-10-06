import os

from slowapi import Limiter
from slowapi.util import get_remote_address

# Central limiter instance for the app; import from other modules
from slowapi import Limiter
from slowapi.util import get_remote_address

# Centralized rate limiter with exemption helper
limiter = Limiter(key_func=get_remote_address)


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
