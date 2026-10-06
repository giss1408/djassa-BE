"""Where shop photos and videos live once processed.

Chosen with `MEDIA_STORAGE`:

* `local` (default outside production): files under `MEDIA_LOCAL_DIR`
  (default `./media`), served by the API itself at `/media/...`. For
  development and tests only: Render's free plan wipes its disk on deploy.
* `r2`: Cloudflare R2 through its S3 API. Free up to 10 GB, and R2 charges
  nothing for bandwidth, so customers watching videos costs nothing. Needs:
    R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET,
    MEDIA_PUBLIC_BASE_URL  (the bucket's public r2.dev URL or a custom domain)
  The access key should be an R2 API token scoped to that one bucket.

Keys carry a random part, so a URL cannot be guessed from a shop id, and
files never change once written: they are served with a one-year immutable
cache, which is what makes a second look at a shop free on prepaid data.
"""

import mimetypes
import os
import shutil
from pathlib import Path

IMMUTABLE = "public, max-age=31536000, immutable"


def _content_type(key: str) -> str:
    return mimetypes.guess_type(key)[0] or "application/octet-stream"


class LocalStorage:
    name = "local"

    def __init__(self, root: str, public_base: str):
        self.root = Path(root)
        self.public_base = public_base.rstrip("/")

    def put(self, key: str, path: str) -> None:
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)

    def delete(self, key: str) -> None:
        try:
            (self.root / key).unlink()
        except FileNotFoundError:
            pass

    def url(self, key: str) -> str:
        return f"{self.public_base}/media/{key}"


class R2Storage:
    name = "r2"

    def __init__(self, account_id: str, access_key: str, secret_key: str, bucket: str, public_base: str):
        import boto3  # only needed when R2 is configured

        self.bucket = bucket
        self.public_base = public_base.rstrip("/")
        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto",
        )

    def put(self, key: str, path: str) -> None:
        self.client.upload_file(
            path, self.bucket, key, ExtraArgs={"ContentType": _content_type(key), "CacheControl": IMMUTABLE}
        )

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def url(self, key: str) -> str:
        return f"{self.public_base}/{key}"


def local_dir() -> str:
    return os.getenv("MEDIA_LOCAL_DIR", "media")


def get_storage():
    name = os.getenv("MEDIA_STORAGE", "local")
    if name == "local":
        if os.getenv("HOSSOUKO_ENV") == "production":
            raise RuntimeError("MEDIA_STORAGE=local is refused when HOSSOUKO_ENV=production (the disk is not durable)")
        from .mobile_money import public_base_url

        return LocalStorage(local_dir(), public_base_url())
    if name == "r2":
        needed = ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "MEDIA_PUBLIC_BASE_URL"]
        missing = [n for n in needed if not os.getenv(n)]
        if missing:
            raise RuntimeError(f"MEDIA_STORAGE=r2 needs {', '.join(missing)}")
        return R2Storage(*(os.environ[n] for n in needed))
    raise RuntimeError(f"Unknown MEDIA_STORAGE: {name!r}")
