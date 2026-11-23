"""Alerts to the Fidelia team's phones through ntfy (https://ntfy.sh).

One HTTP POST per event; the team installs the ntfy app and subscribes to the
topic. No Firebase project, nothing in the admin app. Run as a background task
so the customer or merchant never waits on it, and a failure is only logged.

* `NTFY_TOPIC`: the topic to publish to. Empty (default) disables alerts.
  Anyone who knows a public topic can read it: use a long random name, or
  reserve it on an ntfy.sh account and set `NTFY_TOKEN`.
* `NTFY_TOKEN`: optional access token for a reserved topic.
* `NTFY_URL`: the server, `https://ntfy.sh` unless self-hosted.

Messages carry shop names and categories, never phone numbers or message text.
"""

import logging
import os

import httpx

log = logging.getLogger("fidelia.admin_alerts")

# Filled instead of sending when NTFY_URL is "memory" (tests).
SENT: list[dict] = []


async def send(title: str, message: str, *, priority: int = 3, tags: list[str] | None = None) -> None:
    topic = os.getenv("NTFY_TOPIC", "").strip()
    if not topic:
        return
    payload = {"topic": topic, "title": title, "message": message, "priority": priority, "tags": tags or ["bell"]}
    url = os.getenv("NTFY_URL", "https://ntfy.sh").rstrip("/")
    if url == "memory":
        SENT.append(payload)
        return
    token = os.getenv("NTFY_TOKEN", "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        # JSON publishing (not headers) so French accents arrive intact.
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            log.warning("ntfy alert refused: %s %s", resp.status_code, resp.text[:200])
    except httpx.HTTPError as exc:
        log.warning("ntfy alert failed: %s", exc)
