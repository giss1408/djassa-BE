"""Runs every scenario in features/; the steps live in conftest.py."""

from pathlib import Path

from pytest_bdd import scenarios

# Absolute, from this file's real location: pytest-bdd otherwise resolves a
# relative path from the caller's compiled filename, which a stale __pycache__
# keeps pointing at wherever the repository used to live.
scenarios(Path(__file__).resolve().parent / "features")
