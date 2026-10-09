"""Shop photos and videos: limits, shrinking for 2G, privacy, who may touch them.

Runs the real Pillow and ffmpeg against local storage in a temp directory.
ffmpeg is the system's or, failing that, the one bundled in imageio-ffmpeg,
which is what runs on Render's native Python runtime.
"""

import io
import subprocess
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import select

from app import models
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.seed import seed_sample_data

from app.services import media_processing

try:
    FFMPEG = media_processing.ffmpeg_binary()
except RuntimeError:
    FFMPEG = None
has_ffmpeg = FFMPEG is not None


@pytest.fixture(autouse=True)
def _local_media(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_STORAGE", "local")
    monkeypatch.setenv("MEDIA_LOCAL_DIR", str(tmp_path / "media"))
    monkeypatch.delenv("FIDELIA_ENV", raising=False)
    return tmp_path / "media"


@pytest_asyncio.fixture
async def client():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await seed_sample_data()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _auth(ac, username, password):
    r = await ac.post("/api/token", data={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _photo(width=3000, height=2000, gps=True) -> bytes:
    img = Image.new("RGB", (width, height), (200, 120, 40))
    exif = Image.Exif()
    if gps:
        exif[0x8825] = {1: "N", 2: (5.0, 19.0, 11.0), 3: "W", 4: (4.0, 1.0, 0.0)}  # GPSInfo
    exif[0x010F] = "PhoneMaker"
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95, exif=exif)
    return buf.getvalue()


def _video(tmp_path: Path, seconds=3, size="1280x720") -> bytes:
    out = tmp_path / f"in-{seconds}-{size}.mp4"
    subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size={size}:rate=30",
         "-f", "lavfi", "-i", f"sine=duration={seconds}", "-c:v", "libx264", "-b:v", "4M", "-c:a", "aac", "-shortest", str(out)],
        check=True,
    )
    return out.read_bytes()


async def _upload(ac, h, data, name, content_type, path="/api/merchant/media"):
    return await ac.post(path, files={"file": (name, data, content_type)}, headers=h)


def _file(media_root: Path, url: str) -> Path:
    return media_root / url.split("/media/", 1)[1]


@pytest.mark.asyncio
async def test_a_photo_is_shrunk_to_webp_and_stripped_of_its_gps(client, _local_media):
    merchant = await _auth(client, "demo", "demo123")
    original = _photo()
    r = await _upload(client, merchant, original, "shop.jpg", "image/jpeg")
    assert r.status_code == 201, r.text
    media = r.json()
    assert media["status"] == "ready"
    assert (media["width"], media["height"]) == (1280, 853)

    thumb = _file(_local_media, media["thumb_url"])
    assert thumb.suffix == ".webp"
    assert thumb.stat().st_size < 30_000
    assert _file(_local_media, media["medium_url"]).stat().st_size < len(original)
    with Image.open(thumb) as img:
        assert img.width == 320
        assert not img.getexif()  # no GPS, no phone model

    # Served by the API in development.
    r = await client.get(media["thumb_url"].replace("http://localhost:8000", ""))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_customers_see_ready_media_on_the_shop_page(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    await _upload(client, merchant, _photo(800, 600), "a.png", "image/jpeg")
    async with AsyncSessionLocal() as db:
        venue_id = (await db.execute(select(models.Venue.id).where(models.Venue.owner_username == "demo"))).scalar_one()
    detail = (await client.get(f"/api/venues/{venue_id}", headers=customer)).json()
    assert len(detail["media"]) == 1
    assert detail["media"][0]["thumb_url"].endswith("thumb.webp")


@pytest.mark.asyncio
async def test_ten_photos_maximum_and_junk_refused(client):
    merchant = await _auth(client, "demo", "demo123")
    small = _photo(400, 300, gps=False)
    for _ in range(10):
        assert (await _upload(client, merchant, small, "p.jpg", "image/jpeg")).status_code == 201
    r = await _upload(client, merchant, small, "p.jpg", "image/jpeg")
    assert r.status_code == 409

    assert (await _upload(client, merchant, b"%PDF-1.4", "doc.pdf", "application/pdf")).status_code == 415


@pytest.mark.asyncio
async def test_a_broken_image_fails_with_a_reason(client):
    merchant = await _auth(client, "demo", "demo123")
    r = await _upload(client, merchant, b"not really a jpeg", "x.jpg", "image/jpeg")
    assert r.status_code == 201
    assert r.json()["status"] == "failed"
    assert "illisible" in r.json()["error"]
    # A failed upload does not count against the limit; deleting clears it.
    assert (await client.delete(f"/api/merchant/media/{r.json()['id']}", headers=merchant)).status_code == 204


@pytest.mark.asyncio
@pytest.mark.skipif(not has_ffmpeg, reason="ffmpeg not installed")
async def test_a_video_is_reencoded_small_with_a_poster(client, tmp_path, _local_media):
    merchant = await _auth(client, "demo", "demo123")
    original = _video(tmp_path)
    r = await _upload(client, merchant, original, "clip.mp4", "video/mp4")
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "processing"

    # The conversion ran after the response; the list shows the outcome.
    media = (await client.get("/api/merchant/media", headers=merchant)).json()[0]
    assert media["status"] == "ready", media
    assert media["height"] == 480 and media["width"] == 854
    assert media["duration_s"] == 3
    assert media["video_bytes"] < len(original)
    assert media["poster_url"].endswith("poster.webp")
    report = subprocess.run([FFMPEG, "-hide_banner", "-i", str(_file(_local_media, media["video_url"]))],
                            capture_output=True, text=True).stderr
    assert "Video: h264" in report
    assert "mono" in report


@pytest.mark.asyncio
@pytest.mark.skipif(not has_ffmpeg, reason="ffmpeg not installed")
async def test_portrait_video_keeps_its_orientation(client, tmp_path):
    merchant = await _auth(client, "demo", "demo123")
    await _upload(client, merchant, _video(tmp_path, 2, "720x1280"), "v.mp4", "video/mp4")
    media = (await client.get("/api/merchant/media", headers=merchant)).json()[0]
    assert (media["width"], media["height"]) == (480, 854)


@pytest.mark.asyncio
@pytest.mark.skipif(not has_ffmpeg, reason="ffmpeg not installed")
async def test_three_videos_maximum_and_sixty_seconds(client, tmp_path):
    merchant = await _auth(client, "demo", "demo123")
    clip = _video(tmp_path, 1, "320x240")
    for _ in range(3):
        assert (await _upload(client, merchant, clip, "v.mp4", "video/mp4")).status_code == 201
    assert (await _upload(client, merchant, clip, "v.mp4", "video/mp4")).status_code == 409

    admin = await _auth(client, "admin", "admin123")
    async with AsyncSessionLocal() as db:
        other = (await db.execute(select(models.Venue.id).where(models.Venue.owner_username.is_(None)))).scalars().first()
    long_clip = _video(tmp_path, 62, "160x120")
    await _upload(client, admin, long_clip, "long.mp4", "video/mp4", f"/api/admin/venues/{other}/media")
    media = (await client.get(f"/api/admin/venues/{other}/media", headers=admin)).json()[0]
    assert media["status"] == "failed"
    assert "60 secondes" in media["error"]


@pytest.mark.asyncio
async def test_reorder_and_delete_remove_the_files(client, _local_media):
    merchant = await _auth(client, "demo", "demo123")
    first = (await _upload(client, merchant, _photo(400, 300), "1.jpg", "image/jpeg")).json()
    second = (await _upload(client, merchant, _photo(400, 300), "2.jpg", "image/jpeg")).json()

    ordered = (await client.put("/api/merchant/media/order", json={"ids": [second["id"], first["id"]]}, headers=merchant)).json()
    assert [m["id"] for m in ordered] == [second["id"], first["id"]]
    assert (await client.put("/api/merchant/media/order", json={"ids": [first["id"]]}, headers=merchant)).status_code == 422

    thumb = _file(_local_media, first["thumb_url"])
    assert thumb.exists()
    assert (await client.delete(f"/api/merchant/media/{first['id']}", headers=merchant)).status_code == 204
    assert not thumb.exists()


@pytest.mark.asyncio
async def test_merchants_touch_only_their_shop_and_admins_any(client):
    merchant = await _auth(client, "demo", "demo123")
    admin = await _auth(client, "admin", "admin123")
    customer = await _auth(client, "client", "client123")
    async with AsyncSessionLocal() as db:
        other = (await db.execute(select(models.Venue.id).where(models.Venue.owner_username.is_(None)))).scalars().first()

    r = await _upload(client, admin, _photo(400, 300), "a.jpg", "image/jpeg", f"/api/admin/venues/{other}/media")
    assert r.status_code == 201
    theirs = r.json()["id"]
    # The merchant cannot delete another shop's photo.
    assert (await client.delete(f"/api/merchant/media/{theirs}", headers=merchant)).status_code == 404
    assert (await client.get(f"/api/admin/venues/{other}/media", headers=merchant)).status_code == 403
    assert (await _upload(client, customer, _photo(400, 300), "a.jpg", "image/jpeg")).status_code == 403
    assert (await client.delete(f"/api/admin/venues/{other}/media/{theirs}", headers=admin)).status_code == 204


def test_production_refuses_local_storage(monkeypatch):
    from app.services.media_storage import get_storage

    monkeypatch.setenv("FIDELIA_ENV", "production")
    with pytest.raises(RuntimeError):
        get_storage()
    monkeypatch.setenv("MEDIA_STORAGE", "r2")
    with pytest.raises(RuntimeError, match="R2_BUCKET"):
        get_storage()


def test_the_bundled_ffmpeg_converts_a_video(tmp_path, monkeypatch):
    """Render's native Python runtime has no system ffmpeg: only the static
    build inside the imageio-ffmpeg wheel. It must do the whole job alone."""
    imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")
    bundled = imageio_ffmpeg.get_ffmpeg_exe()
    monkeypatch.setenv("FFMPEG_BINARY", bundled)
    src = tmp_path / "in.mp4"
    subprocess.run(
        [bundled, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=1280x720:rate=30",
         "-f", "lavfi", "-i", "sine=duration=2", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(src)],
        check=True,
    )
    work = tmp_path / "work"
    work.mkdir()
    result = media_processing.process_video(str(src), str(work))
    assert result.duration_s == 2
    path, info = result.files["video"]
    assert (info["width"], info["height"]) == (854, 480)
    assert info["bytes"] < src.stat().st_size
    assert result.files["poster"][1]["width"] == 720


def test_probe_reads_ffmpeg_report_without_ffprobe():
    report = (
        "Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'x.mp4':\n"
        "  Duration: 00:01:02.50, start: 0.000000, bitrate: 6123 kb/s\n"
        "  Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p(progressive), 1920x1080 [SAR 1:1 DAR 16:9], 6000 kb/s, 30 fps\n"
        "  Stream #0:1[0x2](und): Audio: aac (LC) (mp4a / 0x6134706D), 44100 Hz, stereo, fltp, 128 kb/s\n"
    )
    d = media_processing._DURATION.search(report)
    v = media_processing._VIDEO.search(report)
    assert int(d[2]) * 60 + float(d[3]) == 62.5
    assert (int(v[1]), int(v[2])) == (1920, 1080)


@pytest.mark.asyncio
async def test_a_conversion_cut_off_by_a_restart_is_reported(client):
    from datetime import datetime, timedelta, timezone

    merchant = await _auth(client, "demo", "demo123")
    async with AsyncSessionLocal() as db:
        venue_id = (await db.execute(select(models.Venue.id).where(models.Venue.owner_username == "demo"))).scalar_one()
        db.add(models.VenueMedia(venue_id=venue_id, kind="video", status="processing", position=1,
                                 uploaded_by="demo", created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)))
        await db.commit()
    media = (await client.get("/api/merchant/media", headers=merchant)).json()[0]
    assert media["status"] == "failed"
    assert "renvoyez" in media["error"]


@pytest.mark.asyncio
async def test_lists_carry_the_first_photo_as_a_small_cover(client):
    merchant = await _auth(client, "demo", "demo123")
    customer = await _auth(client, "client", "client123")
    first = (await _upload(client, merchant, _photo(800, 600, gps=False), "a.jpg", "image/jpeg")).json()
    second = (await _upload(client, merchant, _photo(800, 600, gps=False), "b.jpg", "image/jpeg")).json()
    async with AsyncSessionLocal() as db:
        venue_id = (await db.execute(select(models.Venue.id).where(models.Venue.owner_username == "demo"))).scalar_one()

    listed = {v["id"]: v for v in (await client.get("/api/venues", headers=customer)).json()}
    assert listed[venue_id]["cover_url"] == first["thumb_url"]
    assert sum(1 for v in listed.values() if v["cover_url"]) == 1  # shops without photos: none

    await client.put("/api/merchant/media/order", json={"ids": [second["id"], first["id"]]}, headers=merchant)
    detail = (await client.get(f"/api/venues/{venue_id}", headers=customer)).json()
    assert detail["cover_url"] == second["thumb_url"]
