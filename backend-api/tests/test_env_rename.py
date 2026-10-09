"""The old DJASSA_* and HOSSOUKO_* environment names still configure the API."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read_after_import(env: dict[str, str], name: str) -> str:
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("FIDELIA_", "HOSSOUKO_", "DJASSA_"))}
    out = subprocess.run(
        [sys.executable, "-c", f"import os, app; print(os.environ.get('{name}', '<unset>'))"],
        cwd=ROOT, env={**clean, **env}, capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def test_old_names_fill_the_new_ones():
    assert _read_after_import({"DJASSA_PUBLIC_URL": "d"}, "FIDELIA_PUBLIC_URL") == "d"
    assert _read_after_import({"HOSSOUKO_PUBLIC_URL": "h"}, "FIDELIA_PUBLIC_URL") == "h"


def test_newest_name_wins():
    env = {"DJASSA_PUBLIC_URL": "d", "HOSSOUKO_PUBLIC_URL": "h"}
    assert _read_after_import(env, "FIDELIA_PUBLIC_URL") == "h"
    assert _read_after_import({**env, "FIDELIA_PUBLIC_URL": "f"}, "FIDELIA_PUBLIC_URL") == "f"
