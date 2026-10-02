"""Turns an uploaded photo or video into what a 2G phone can afford.

Photos (Pillow): rotated upright from EXIF, then saved as three WebP sizes
with no metadata at all, so a phone's GPS position never leaks:

    thumb   320 px wide, ~10-20 KB   lists and the shop page, loaded by default
    medium  720 px wide, ~40-70 KB   opened full screen on a phone
    large  1280 px wide              the admin screen and tablets

Videos (ffmpeg): at most 60 s, re-encoded to H.264 Main + AAC mono with the
short side at most 480 px and the bitrate capped at ~600 kbit/s (about 4.5 MB
a minute), `faststart` so playback begins before the download ends, plus a
720 px WebP poster. The apps show the poster and the size, and download the
video only on tap.

ffmpeg comes from, in order: `FFMPEG_BINARY`, the system's `ffmpeg` (the
Docker image installs it), or the static build shipped inside the
`imageio-ffmpeg` wheel, which is what runs on Render's native Python runtime,
where nothing can be apt-installed. That build has no ffprobe, so video facts
(duration, size) are read from ffmpeg's own report instead.

One video converts at a time (`MEDIA_VIDEO_JOBS`, default 1): Render's free
instance has 512 MB and a fraction of a CPU, and two 1080p decodes at once
would starve the API. A 60 s clip there takes a few minutes; the upload
answers at once and the row turns `ready` when done.
"""

import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

# Decompression bombs: a 20 KB file can claim 100 000 x 100 000 pixels.
Image.MAX_IMAGE_PIXELS = 50_000_000

IMAGE_SIZES = {"thumb": (320, 60), "medium": (720, 70), "large": (1280, 75)}
MAX_VIDEO_SECONDS = 60
VIDEO_SHORT_SIDE = 480
FFMPEG_TIMEOUT_S = int(os.getenv("MEDIA_FFMPEG_TIMEOUT_S", "900"))
_video_slots = threading.BoundedSemaphore(int(os.getenv("MEDIA_VIDEO_JOBS", "1")))


class MediaRejected(ValueError):
    """The file cannot be used; the message is shown to whoever uploaded it."""


@dataclass
class Processed:
    # variant name -> (local file path, info such as width/height/bytes)
    files: dict[str, tuple[str, dict]] = field(default_factory=dict)
    duration_s: int | None = None


def _save_webp(img: Image.Image, width: int, quality: int, out: Path) -> dict:
    copy = img.copy()
    if copy.width > width:
        copy = copy.resize((width, round(copy.height * width / copy.width)), Image.LANCZOS)
    # A fresh save writes no EXIF/XMP/ICC: nothing about the phone or place.
    copy.save(out, "WEBP", quality=quality, method=6)
    return {"width": copy.width, "height": copy.height, "bytes": out.stat().st_size}


def process_image(src: str, workdir: str) -> Processed:
    try:
        with Image.open(src) as opened:
            opened.verify()  # cheap integrity check before decoding
        with Image.open(src) as opened:
            img = ImageOps.exif_transpose(opened)
            img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError) as exc:
        raise MediaRejected("Image illisible ou trop grande") from exc
    result = Processed()
    for name, (width, quality) in IMAGE_SIZES.items():
        out = Path(workdir) / f"{name}.webp"
        result.files[name] = (str(out), _save_webp(img, width, quality, out))
    return result


def ffmpeg_binary() -> str:
    configured = os.getenv("FFMPEG_BINARY") or shutil.which("ffmpeg")
    if configured:
        return configured
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("ffmpeg not found: install it or the imageio-ffmpeg package") from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


_DURATION = re.compile(r"Duration: (\d+):(\d{2}):(\d{2}(?:\.\d+)?)")
_VIDEO = re.compile(r"Stream #\d+:\d+.*?: Video: .*?(?<![0-9x])(\d{2,5})x(\d{2,5})(?![0-9])")


@dataclass
class Probe:
    duration: float
    width: int | None
    height: int | None
    has_video: bool


def probe(src: str) -> Probe:
    """What ffmpeg reports about a file when given no output: it exits with
    an error by design, and prints the container and streams on stderr."""
    try:
        report = subprocess.run(
            [ffmpeg_binary(), "-hide_banner", "-i", src], capture_output=True, text=True, timeout=60
        ).stderr
    except subprocess.TimeoutExpired as exc:
        raise MediaRejected("Video illisible") from exc
    d = _DURATION.search(report)
    v = _VIDEO.search(report)
    duration = int(d[1]) * 3600 + int(d[2]) * 60 + float(d[3]) if d else 0.0
    return Probe(duration, int(v[1]) if v else None, int(v[2]) if v else None, v is not None)


def process_video(src: str, workdir: str) -> Processed:
    with _video_slots:
        return _process_video(src, workdir)


def _process_video(src: str, workdir: str) -> Processed:
    ffmpeg = ffmpeg_binary()
    info = probe(src)
    if not info.has_video:
        raise MediaRejected("Ce fichier ne contient pas de video")
    duration = info.duration
    if duration <= 0:
        raise MediaRejected("Video illisible")
    if duration > MAX_VIDEO_SECONDS + 1:
        raise MediaRejected(f"Video trop longue : {MAX_VIDEO_SECONDS} secondes maximum")

    out = Path(workdir) / "video.mp4"
    # Short side capped at 480 px whatever the orientation, never upscaled;
    # dimensions kept even, as H.264 requires.
    scale = (
        f"scale=w='if(gt(iw,ih),-2,min({VIDEO_SHORT_SIDE},iw))'"
        f":h='if(gt(iw,ih),min({VIDEO_SHORT_SIDE},ih),-2)'"
    )
    cmd = [
        ffmpeg, "-y", "-v", "error", "-i", src, "-t", str(MAX_VIDEO_SECONDS),
        "-vf", scale, "-r", "30",
        "-c:v", "libx264", "-preset", "veryfast", "-profile:v", "main", "-pix_fmt", "yuv420p",
        "-crf", "30", "-maxrate", "600k", "-bufsize", "1200k",
        "-c:a", "aac", "-b:a", "64k", "-ac", "1",
        "-map_metadata", "-1", "-movflags", "+faststart", str(out),
    ]
    poster_jpg = Path(workdir) / "poster.jpg"
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=FFMPEG_TIMEOUT_S)
        subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-ss", str(min(1.0, duration / 2)), "-i", str(out),
             "-frames:v", "1", str(poster_jpg)],
            capture_output=True, check=True, timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise MediaRejected("La video n'a pas pu etre convertie") from exc

    encoded = probe(str(out))
    result = Processed(duration_s=round(min(duration, MAX_VIDEO_SECONDS)))
    result.files["video"] = (str(out), {"width": encoded.width, "height": encoded.height, "bytes": out.stat().st_size})
    with Image.open(poster_jpg) as poster:
        poster_out = Path(workdir) / "poster.webp"
        result.files["poster"] = (str(poster_out), _save_webp(poster.convert("RGB"), 720, 70, poster_out))
    return result
