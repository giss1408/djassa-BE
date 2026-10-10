"""Push alerts to the customer app when a merchant publishes a deal.

Sent to Firebase Cloud Messaging *topics*, never to stored device tokens. The
customer app subscribes the phone to `offers_<commune>` (the commune the
customer chose) and to `venue_<id>` for each favourite shop; one message goes
to "anyone on this commune's topic or this shop's topic", and FCM delivers it
once per phone. Fidelia therefore never learns who receives what: the
favourites stay on the phone (lib/core/personal_lists.dart in the app), as
they always have.

WhatsApp and SMS are not used: customers in Abidjan do not follow them
(docs/business/CONCEPT.md § 12). A push costs nothing per message.

Chosen with `PUSH_PROVIDER`:

* `console` (default): writes the alert to the server log. Harmless anywhere,
  since a deal is public; it is simply silent for customers.
* `fcm`: Firebase Cloud Messaging HTTP v1. Needs `FCM_PROJECT_ID` and
  `FCM_SERVICE_ACCOUNT_JSON` (the service account key file's content, from
  Firebase console > Project settings > Service accounts). The key is signed
  into a short-lived OAuth token here, so no Google SDK is added.
"""

import json
import logging
import os
import re
import time
import unicodedata
from datetime import timedelta

import httpx
from jose import jwt
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .. import models
from ..db import AsyncSessionLocal

log = logging.getLogger("fidelia.push")

# One alert per venue per this window, whatever it publishes: the pilot is
# free, so nothing else stops a merchant from buzzing every phone in the
# commune five times a day, and an app that buzzes too often is uninstalled.
ALERT_COOLDOWN = timedelta(hours=24)

# A deal scheduled to start later is not announced: there is no worker on the
# test server to send it at the right time (render.yaml), and an alert for an
# offer the customer cannot use yet is worse than none.
FUTURE_TOLERANCE = timedelta(minutes=5)

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


class PushFailed(RuntimeError):
    pass


def topic_slug(value: str) -> str:
    """"Cocody" -> "cocody", "Port-Bouët" -> "port_bouet".

    The customer app computes the same slug (lib/core/push/topics.dart); both
    sides must agree or the alert reaches nobody. FCM topics allow only
    [a-zA-Z0-9-_.~%].
    """
    ascii_only = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_only.lower()).strip("_")


def commune_topic(commune: str) -> str:
    return f"offers_{topic_slug(commune)}"


def venue_topic(venue_id: int) -> str:
    return f"venue_{venue_id}"


def offer_words(deal: models.Deal) -> str:
    """The offer in a few words, the way the apps write it."""

    def francs(amount: int) -> str:
        return f"{amount:,}".replace(",", " ") + " F"

    if deal.price is not None:
        if deal.original_price is not None:
            return f"{francs(deal.price)} au lieu de {francs(deal.original_price)}"
        return francs(deal.price)
    if deal.discount_percent is not None:
        return f"-{deal.discount_percent} %"
    return ""


def deal_alert(deal: models.Deal) -> dict:
    """The FCM message for a deal, without the `message` envelope."""
    offer = offer_words(deal)
    return {
        # Either topic: FCM delivers once to a phone subscribed to both.
        "condition": f"'{commune_topic(deal.venue.commune)}' in topics || '{venue_topic(deal.venue_id)}' in topics",
        "notification": {
            "title": f"Bon plan · {deal.venue.name}",
            "body": f"{deal.title} — {offer}" if offer else deal.title,
        },
        # Strings only (FCM's rule). The app opens the shop page on tap.
        "data": {"type": "deal", "deal_id": str(deal.id), "venue_id": str(deal.venue_id)},
        "android": {
            # Normal priority: an offer can wait for the phone's next wake-up;
            # high priority is for things a person must see at once.
            "priority": "normal",
            "notification": {"channel_id": "offers", "tag": f"deal_{deal.id}"},
            # Gone after a day: an alert for an offer that may be over is noise.
            "ttl": "86400s",
        },
    }


class ConsoleSender:
    name = "console"

    async def send(self, message: dict) -> None:
        log.info("push (console): %s | %s", message.get("condition"), message.get("notification"))


class FcmSender:
    name = "fcm"

    def __init__(self, project_id: str, service_account: dict):
        self._project_id = project_id
        self._account = service_account
        self._token: str | None = None
        self._token_expires = 0.0

    async def _access_token(self, client: httpx.AsyncClient) -> str:
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        now = int(time.time())
        assertion = jwt.encode(
            {
                "iss": self._account["client_email"],
                "scope": _SCOPE,
                "aud": _TOKEN_URL,
                "iat": now,
                "exp": now + 3600,
            },
            self._account["private_key"],
            algorithm="RS256",
        )
        response = await client.post(
            _TOKEN_URL,
            data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
        )
        if response.status_code >= 300:
            raise PushFailed(f"Google token endpoint answered {response.status_code}")
        body = response.json()
        self._token = body["access_token"]
        self._token_expires = time.time() + int(body.get("expires_in", 3600))
        return self._token

    async def send(self, message: dict) -> None:
        url = f"https://fcm.googleapis.com/v1/projects/{self._project_id}/messages:send"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                token = await self._access_token(client)
                response = await client.post(url, json={"message": message}, headers={"Authorization": f"Bearer {token}"})
        except httpx.HTTPError as exc:
            raise PushFailed("FCM unreachable") from exc
        if response.status_code >= 300:
            raise PushFailed(f"FCM answered {response.status_code}: {response.text[:200]}")


_sender = None


def get_sender():
    """Built once per process, so the FCM token is reused between alerts."""
    global _sender
    if _sender is not None:
        return _sender
    name = os.getenv("PUSH_PROVIDER", "console")
    if name == "console":
        _sender = ConsoleSender()
    elif name == "fcm":
        project_id, raw = os.getenv("FCM_PROJECT_ID"), os.getenv("FCM_SERVICE_ACCOUNT_JSON")
        if not project_id or not raw:
            raise RuntimeError("PUSH_PROVIDER=fcm needs FCM_PROJECT_ID and FCM_SERVICE_ACCOUNT_JSON")
        _sender = FcmSender(project_id, json.loads(raw))
    else:
        raise RuntimeError(f"Unknown PUSH_PROVIDER: {name!r}")
    return _sender


async def announce_deal(deal_id: int, now) -> str:
    """Send the alert for a newly published deal, once. Returns the status.

    Runs after the merchant's request has been answered (a FastAPI background
    task), in its own session: a slow or failing FCM never delays publishing,
    and a failure is recorded on the deal instead of surfacing to the merchant.
    """
    async with AsyncSessionLocal() as db:
        deal = (
            await db.execute(select(models.Deal).options(selectinload(models.Deal.venue)).where(models.Deal.id == deal_id))
        ).scalar_one_or_none()
        if deal is None or deal.notify_status is not None:
            return "ignored"

        if deal.venue.is_sample:
            status = "skipped_sample"
        elif deal.starts_at > now + FUTURE_TOLERANCE:
            status = "skipped_future"
        else:
            recent = (
                await db.execute(
                    select(models.Deal.id).where(
                        models.Deal.venue_id == deal.venue_id,
                        models.Deal.id != deal.id,
                        models.Deal.notify_status == "sent",
                        models.Deal.notified_at > now - ALERT_COOLDOWN,
                    ).limit(1)
                )
            ).first()
            if recent is not None:
                status = "skipped_recent"
            else:
                try:
                    await get_sender().send(deal_alert(deal))
                    status = "sent"
                except Exception:  # noqa: BLE001 -- any failure is recorded, never raised to the merchant
                    log.exception("push for deal %s failed", deal.id)
                    status = "failed"

        deal.notify_status = status
        deal.notified_at = now
        await db.commit()
        return status
