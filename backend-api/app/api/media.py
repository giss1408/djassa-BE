"""Shop photos and videos.

    Merchant (their own shop)              Admin (any shop)
    GET    /api/merchant/media             GET    /api/admin/venues/{id}/media
    POST   /api/merchant/media   (file)    POST   /api/admin/venues/{id}/media
    DELETE /api/merchant/media/{media}     DELETE /api/admin/venues/{id}/media/{media}
    PUT    /api/merchant/media/order       PUT    /api/admin/venues/{id}/media/order

Up to 10 photos and 3 videos per shop. A photo is processed during the upload
request (a second or two) and comes back `ready`. A video comes back
`processing` and is converted after the response; the list shows when it is
`ready` or `failed` (with the reason). Customers see only `ready` media, in
`position` order, on the shop page (`GET /api/venues/{id}`).

How files are shrunk: app/services/media_processing.py. Where they go:
app/services/media_storage.py.
"""

import json
import secrets
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..core.security import SHOP_STAFF, require_role
from ..db import AsyncSessionLocal, get_db
from ..schemas.media import MediaOut
from ..services.media_processing import MediaRejected, process_image, process_video
from ..services.media_storage import get_storage
from .payment_requests import _my_venue

router = APIRouter()

MAX_IMAGES = 10
MAX_VIDEOS = 3
MAX_BYTES = {"image": 15 * 1024 * 1024, "video": 150 * 1024 * 1024}
_TYPES = {
    "image/jpeg": "image", "image/png": "image", "image/webp": "image",
    "video/mp4": "video", "video/quicktime": "video", "video/3gpp": "video", "video/webm": "video",
}


class OrderIn(BaseModel):
    ids: list[int] = Field(max_length=MAX_IMAGES + MAX_VIDEOS)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def media_out(m: models.VenueMedia) -> MediaOut:
    out = MediaOut(id=m.id, kind=m.kind, status=m.status, position=m.position, error=m.error, duration_s=m.duration_s)
    if m.status != "ready" or not m.variants:
        return out
    variants = json.loads(m.variants)
    storage = get_storage()

    def url(name: str) -> str | None:
        return storage.url(variants[name]["key"]) if name in variants else None

    if m.kind == "image":
        out.thumb_url, out.medium_url, out.large_url = url("thumb"), url("medium"), url("large")
        out.width, out.height = variants["large"]["width"], variants["large"]["height"]
    else:
        out.poster_url, out.video_url = url("poster"), url("video")
        out.thumb_url = out.poster_url
        out.video_bytes = variants["video"]["bytes"]
        out.width, out.height = variants["video"]["width"], variants["video"]["height"]
    return out


async def ready_media(db: AsyncSession, venue_id: int) -> list[MediaOut]:
    """What customers see on the shop page."""
    rows = (
        await db.execute(
            select(models.VenueMedia)
            .where(models.VenueMedia.venue_id == venue_id, models.VenueMedia.status == "ready")
            .order_by(models.VenueMedia.position, models.VenueMedia.id)
        )
    ).scalars().all()
    return [media_out(m) for m in rows]


# Longer than any conversion. A video still `processing` after this was cut
# off by a restart (a deploy, or a free instance going to sleep): say so,
# rather than leave the merchant waiting forever.
STALE_AFTER = timedelta(minutes=30)


async def cover_urls(db: AsyncSession, venue_ids: list[int]) -> dict[int, str]:
    """Each shop's first ready photo, as its 320 px thumbnail (~15 KB): what
    a list card shows. One query for the whole list."""
    if not venue_ids:
        return {}
    rows = (
        await db.execute(
            select(models.VenueMedia)
            .where(
                models.VenueMedia.venue_id.in_(venue_ids),
                models.VenueMedia.kind == "image",
                models.VenueMedia.status == "ready",
            )
            .order_by(models.VenueMedia.venue_id, models.VenueMedia.position, models.VenueMedia.id)
        )
    ).scalars().all()
    covers: dict[int, str] = {}
    for m in rows:
        if m.venue_id not in covers:
            covers[m.venue_id] = media_out(m).thumb_url
    return covers


async def _all_media(db: AsyncSession, venue_id: int) -> list[MediaOut]:
    await db.execute(
        update(models.VenueMedia)
        .where(
            models.VenueMedia.venue_id == venue_id,
            models.VenueMedia.status == "processing",
            models.VenueMedia.created_at < utcnow() - STALE_AFTER,
        )
        .values(status="failed", error="Traitement interrompu : supprimez et renvoyez la video")
    )
    await db.commit()
    rows = (
        await db.execute(
            select(models.VenueMedia)
            .where(models.VenueMedia.venue_id == venue_id)
            .order_by(models.VenueMedia.position, models.VenueMedia.id)
        )
    ).scalars().all()
    return [media_out(m) for m in rows]


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


async def _finish(media_id: int, venue_id: int, kind: str, src: str, workdir: str) -> None:
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


async def _receive(upload: UploadFile, kind: str, workdir: str) -> str:
    """Copies the upload to our own file, refusing it past the size limit
    without reading the rest."""
    dest = Path(workdir) / "original"
    limit, size = MAX_BYTES[kind], 0
    with open(dest, "wb") as out:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                raise HTTPException(status_code=413, detail=f"Fichier trop lourd : {limit // (1024 * 1024)} Mo maximum")
            out.write(chunk)
    if size == 0:
        raise HTTPException(status_code=422, detail="Fichier vide")
    return str(dest)


async def _add(
    db: AsyncSession, venue: models.Venue, upload: UploadFile, uploaded_by: str, background: BackgroundTasks
) -> MediaOut:
    kind = _TYPES.get((upload.content_type or "").split(";")[0].strip().lower())
    if kind is None:
        raise HTTPException(status_code=415, detail="Envoyez une photo (JPEG, PNG, WebP) ou une video (MP4, MOV, 3GP, WebM)")
    count = (
        await db.execute(
            select(func.count(models.VenueMedia.id)).where(
                models.VenueMedia.venue_id == venue.id,
                models.VenueMedia.kind == kind,
                models.VenueMedia.status != "failed",
            )
        )
    ).scalar_one()
    limit = MAX_IMAGES if kind == "image" else MAX_VIDEOS
    if count >= limit:
        what = "photos" if kind == "image" else "videos"
        raise HTTPException(status_code=409, detail=f"{limit} {what} maximum par commerce. Supprimez-en une d'abord.")

    workdir = tempfile.mkdtemp(prefix="djassa-media-")
    try:
        src = await _receive(upload, kind, workdir)
    except HTTPException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    last = (
        await db.execute(select(func.max(models.VenueMedia.position)).where(models.VenueMedia.venue_id == venue.id))
    ).scalar_one()
    media = models.VenueMedia(
        venue_id=venue.id, kind=kind, status="processing", position=(last or 0) + 1,
        uploaded_by=uploaded_by, created_at=utcnow(),
    )
    db.add(media)
    await db.commit()

    if kind == "image":
        # A second or two: answer with the finished photo.
        await _finish(media.id, venue.id, kind, src, workdir)
        await db.refresh(media)
    else:
        # Minutes on a small server: answer now, convert after the response.
        background.add_task(_finish, media.id, venue.id, kind, src, workdir)
    return media_out(media)


async def _delete(db: AsyncSession, venue_id: int, media_id: int) -> None:
    media = await db.get(models.VenueMedia, media_id)
    if media is None or media.venue_id != venue_id:
        raise HTTPException(status_code=404, detail="Media not found")
    keys = [v["key"] for v in json.loads(media.variants).values()] if media.variants else []
    await db.delete(media)
    await db.commit()
    storage = get_storage()
    for key in keys:
        await run_in_threadpool(storage.delete, key)


async def _reorder(db: AsyncSession, venue_id: int, ids: list[int]) -> list[MediaOut]:
    rows = {
        m.id: m
        for m in (await db.execute(select(models.VenueMedia).where(models.VenueMedia.venue_id == venue_id))).scalars()
    }
    if set(ids) != set(rows):
        raise HTTPException(status_code=422, detail="Send every media id of the shop, in the new order")
    for position, media_id in enumerate(ids, start=1):
        rows[media_id].position = position
    await db.commit()
    return await _all_media(db, venue_id)


# --- Merchant: their own shop -----------------------------------------------


@router.get("/merchant/media", response_model=list[MediaOut])
async def my_media(db: AsyncSession = Depends(get_db), user=Depends(require_role(*SHOP_STAFF))):
    venue = await _my_venue(db, user, require_wallet=False)
    return await _all_media(db, venue.id)


@router.post("/merchant/media", response_model=MediaOut, status_code=201)
async def add_my_media(
    background: BackgroundTasks, file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant")),
):
    venue = await _my_venue(db, user, require_wallet=False)
    return await _add(db, venue, file, user["username"], background)


@router.delete("/merchant/media/{media_id}", status_code=204)
async def delete_my_media(media_id: int, db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))):
    venue = await _my_venue(db, user, require_wallet=False)
    await _delete(db, venue.id, media_id)


@router.put("/merchant/media/order", response_model=list[MediaOut])
async def order_my_media(payload: OrderIn, db: AsyncSession = Depends(get_db), user=Depends(require_role("merchant"))):
    venue = await _my_venue(db, user, require_wallet=False)
    return await _reorder(db, venue.id, payload.ids)


# --- Admin: any shop ---------------------------------------------------------


async def _venue(db: AsyncSession, venue_id: int) -> models.Venue:
    venue = await db.get(models.Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="Venue not found")
    return venue


@router.get("/admin/venues/{venue_id}/media", response_model=list[MediaOut])
async def admin_media(venue_id: int, db: AsyncSession = Depends(get_db), admin=Depends(require_role("admin"))):
    await _venue(db, venue_id)
    return await _all_media(db, venue_id)


@router.post("/admin/venues/{venue_id}/media", response_model=MediaOut, status_code=201)
async def admin_add_media(
    venue_id: int, background: BackgroundTasks, file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db), admin=Depends(require_role("admin")),
):
    return await _add(db, await _venue(db, venue_id), file, admin["username"], background)


@router.delete("/admin/venues/{venue_id}/media/{media_id}", status_code=204)
async def admin_delete_media(venue_id: int, media_id: int, db: AsyncSession = Depends(get_db), admin=Depends(require_role("admin"))):
    await _delete(db, venue_id, media_id)


@router.put("/admin/venues/{venue_id}/media/order", response_model=list[MediaOut])
async def admin_order_media(venue_id: int, payload: OrderIn, db: AsyncSession = Depends(get_db), admin=Depends(require_role("admin"))):
    await _venue(db, venue_id)
    return await _reorder(db, venue_id, payload.ids)
