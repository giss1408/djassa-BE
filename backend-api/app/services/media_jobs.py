"""Converting an upload and recording the outcome, in the API or in a worker.

Chosen with `MEDIA_PROCESSING`:

* `inline` (default): the API converts videos itself, after the response.
  Fine on a laptop and on the free test instance (which can have no worker),
  but a 60 s clip keeps ffmpeg busy for minutes in the same 512 MB as the API.
* `worker`: the API copies the original to storage under `incoming/` and
  queues `media.process_upload`; the Celery worker downloads it, converts it,
  stores the variants, updates the row and deletes the original. The API
  stays responsive whatever merchants upload. Needs storage both processes
  reach (R2) and the Celery broker. If the queue cannot be reached, the API
  converts the video itself rather than lose it.

Photos are always converted during the upload request: a second or two.

`incoming/` sits in the media bucket under a random 128-bit key and lives only
until the worker is done. Still the untouched original (GPS and all), so the
bucket gets a lifecycle rule deleting `incoming/` after a day, and the media
domain a rule refusing `/incoming/*` (docs/technical/PRODUCTION.md).
"""

import json
import os
import secrets
import shutil
import tempfile
from pathlib import Path

from fastapi.concurrency import run_in_threadpool

from .. import models
from ..db import AsyncSessionLocal, engine
from .media_processing import MediaRejected, process_image, process_video
from .media_storage import get_storage

TASK_NAME = "media.process_upload"


def use_worker() -> bool:
    return os.getenv("MEDIA_PROCESSING", "inline") == "worker"


def _process_and_store(media_id: int, venue_id: int, kind: str, src: str, workdir: str) -> tuple[dict, int | None]:
    """CPU and network work, run off the event loop."""
    processed = (process_image if kind == "image" else process_video)(src, workdir)
    storage = get_storage()
    token = secrets.token_hex(6)
    variants = {}
    for name, (path, info) in processed.files.items():
        key = f"venues/{venue_id}/{media_id}-{token}/{name}{Path(path).suffix}"
        storage.put(key, path)
        variants[name] = {"key": key, **info}
    return variants, processed.duration_s


async def finish(media_id: int, venue_id: int, kind: str, src: str, workdir: str) -> None:
    """Processes one upload and records the outcome. Never raises: a failure
    is stored on the row for whoever uploaded it to read."""
    try:
        variants, duration = await run_in_threadpool(_process_and_store, media_id, venue_id, kind, src, workdir)
        status, error = "ready", None
    except MediaRejected as exc:
        variants, duration, status, error = None, None, "failed", str(exc)
    except Exception:  # storage down, ffmpeg crashed...
        variants, duration, status, error = None, None, "failed", "Traitement impossible, reessayez plus tard"
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    await _record(media_id, variants, duration, status, error)


async def _record(media_id: int, variants: dict | None, duration: int | None, status: str, error: str | None) -> None:
    async with AsyncSessionLocal() as db:
        media = await db.get(models.VenueMedia, media_id)
        if media is None:  # deleted while processing: drop what was stored
            if variants:
                for v in variants.values():
                    await run_in_threadpool(get_storage().delete, v["key"])
            return
        media.status, media.error, media.duration_s = status, error, duration
        media.variants = json.dumps(variants) if variants else None
        await db.commit()


def stage(src: str) -> str:
    """Copies an original where the worker can reach it; returns its key."""
    key = f"incoming/{secrets.token_hex(16)}/original"
    get_storage().put(key, src)
    return key


def enqueue(media_id: int, venue_id: int, kind: str, key: str) -> None:
    from ..celery_app import celery_app

    celery_app.send_task(TASK_NAME, args=[media_id, venue_id, kind, key])


async def process_staged(media_id: int, venue_id: int, kind: str, key: str) -> None:
    """The worker's side: fetch the staged original, convert, clean up."""
    storage = get_storage()
    workdir = tempfile.mkdtemp(prefix="fidelia-media-")
    try:
        async with AsyncSessionLocal() as db:
            if await db.get(models.VenueMedia, media_id) is None:
                return  # deleted before its turn came
        src = str(Path(workdir) / "original")
        try:
            await run_in_threadpool(storage.get, key, src)
        except Exception:
            await _record(media_id, None, None, "failed", "Traitement impossible, reessayez plus tard")
            return
        await finish(media_id, venue_id, kind, src, workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        await run_in_threadpool(storage.delete, key)


def process_staged_sync(media_id: int, venue_id: int, kind: str, key: str) -> None:
    import asyncio

    async def run():
        try:
            await process_staged(media_id, venue_id, kind, key)
        finally:
            # Each task gets a fresh event loop; pooled connections belong to
            # the previous one and must not be reused.
            await engine.dispose()

    asyncio.run(run())
