"""Delivery receipts for sign-in codes sent through Orange's SMS API.

    POST /webhooks/orange/sms-dr/{ORANGE_DR_TOKEN}

The notification URL given to Orange (developer.orange.com/sms-api-queries).
Within 24 hours of each SMS, Orange posts:

    {"deliveryInfoNotification": {"callbackData": "<resource id>",
      "deliveryInfo": {"address": "tel:+225...", "deliveryStatus": "DeliveredToTerminal"}}}

Orange signs nothing, so the URL carries a secret (`ORANGE_DR_TOKEN`, 64 hex
characters: `openssl rand -hex 32`); without it set, the endpoint answers 404
like any unknown path. A receipt holds the recipient's number: only its
network (Orange 07, MTN 05, Moov 01) is kept, counted with the status in
`fidelia_otp_sms_delivery_total`. That is how a network that stops receiving
codes shows up (OtpSmsNotDelivered), without storing anyone's number.

Every receipt with the right token gets 200, even one that cannot be read:
an error would only make Orange send it again.
"""

import hmac
import logging
import os

from fastapi import APIRouter, HTTPException, Request

from ..metrics import OTP_SMS_DELIVERY

router = APIRouter()
log = logging.getLogger("fidelia.otp")

MIN_TOKEN_LENGTH = 32
STATUSES = frozenset({
    "DeliveredToTerminal", "DeliveredToNetwork", "DeliveryUncertain", "DeliveryImpossible", "MessageWaiting",
})
# Ivorian mobile prefixes since the 2021 ten-digit numbering.
NETWORKS = {"07": "orange", "05": "mtn", "01": "moov"}


def check_settings() -> None:
    token = os.getenv("ORANGE_DR_TOKEN")
    if token and len(token) < MIN_TOKEN_LENGTH:
        raise RuntimeError(f"ORANGE_DR_TOKEN needs at least {MIN_TOKEN_LENGTH} characters (openssl rand -hex 32)")


def network_of(address: str) -> str:
    number = address.removeprefix("tel:")
    if number.startswith("+225") and len(number) == 14:
        return NETWORKS.get(number[4:6], "other")
    return "other"


@router.post("/webhooks/orange/sms-dr/{token}", include_in_schema=False)
async def delivery_receipt(token: str, request: Request):
    expected = os.getenv("ORANGE_DR_TOKEN")
    if not expected or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(status_code=404)
    try:
        info = (await request.json())["deliveryInfoNotification"]["deliveryInfo"]
        address, status = str(info["address"]), str(info["deliveryStatus"])
    except (ValueError, KeyError, TypeError):
        log.warning("Orange delivery receipt unreadable; ignored")
        return {"ok": True}
    network = network_of(address)
    OTP_SMS_DELIVERY.labels(network=network, status=status if status in STATUSES else "unknown").inc()
    if status == "DeliveryImpossible":
        log.info("Orange could not deliver a sign-in code (%s network)", network)
    return {"ok": True}
