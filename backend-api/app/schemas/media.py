from pydantic import BaseModel


class MediaOut(BaseModel):
    id: int
    kind: str
    status: str
    position: int
    error: str | None = None
    width: int | None = None
    height: int | None = None
    # Photos: three sizes. Load `thumb_url` by default; the others on demand.
    thumb_url: str | None = None
    medium_url: str | None = None
    large_url: str | None = None
    # Videos: show the poster and the size; download `video_url` only on tap.
    poster_url: str | None = None
    video_url: str | None = None
    video_bytes: int | None = None
    duration_s: int | None = None
